"""
Segmentation service for manual lesion annotation.
Provides ITK-SNAP style manual segmentation capabilities.
"""

import numpy as np
import io
import base64
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from PIL import Image
import uuid
import pydicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import generate_uid
import nibabel as nib

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.exceptions import SegmentationException, NotFoundException, ValidationException
from app.core.interfaces.segmentation_interface import ISegmentationService
from app.core.interfaces.cache_interface import ICacheService
from app.models.schemas import (
    LabelInfo,
    SegmentationMetadata,
    PaintStroke,
    SegmentationMask,
    SegmentationResponse,
    CreateSegmentationRequest
)

# Import shared utilities
from app.utils import (
    normalize_to_uint8,
    array_to_base64,
    hex_to_rgb,
    transpose_for_nifti,
    create_nifti_image,
    save_nifti,
    create_segmentation_filename,
    create_segmentation_dicom,
    save_dicom
)

logger = get_logger(__name__)


class SegmentationService(ISegmentationService):
    """Service for managing medical image segmentations."""

    def __init__(
        self,
        storage_path: str = "./data/segmentations",
        drive_service=None,
        cache_service: Optional[ICacheService] = None
    ):
        """
        Initialize segmentation service.

        Args:
            storage_path: Directory to store segmentation files
            drive_service: Optional DriveService dependency (will be injected via DI)
            cache_service: Optional CacheService for Redis caching
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.drive_service = drive_service  # For future use with DI
        self.cache = cache_service
        self.settings = get_settings()

        # In-memory cache: {segmentation_id: {metadata, masks_3d}}
        self.segmentations_cache: Dict[str, Dict] = {}

    def create_segmentation(
        self,
        file_id: str,
        image_shape: Tuple[int, int, int],
        labels: Optional[List[LabelInfo]] = None,
        description: Optional[str] = None,
        source_format: str = "nifti"  # "nifti" or "dicom"
    ) -> SegmentationResponse:
        """
        Create a new segmentation for an image file.

        Args:
            file_id: Associated image file ID
            image_shape: (height, width, depth) of the image
            labels: Label definitions
            description: Optional description

        Returns:
            SegmentationResponse with new segmentation ID
        """
        segmentation_id = str(uuid.uuid4())

        # Default labels if none provided
        if labels is None:
            labels = [
                LabelInfo(id=0, name="Background", color="#000000", opacity=0.0, visible=False),
                LabelInfo(id=1, name="Lesion", color="#FF0000", opacity=0.5, visible=True)
            ]

        # Create metadata
        metadata = SegmentationMetadata(
            file_id=file_id,
            created_at=datetime.utcnow(),
            modified_at=datetime.utcnow(),
            labels=labels,
            description=description
        )

        # Initialize empty 3D mask using medical imaging convention (depth, height, width)
        height, width, depth = image_shape
        masks_3d = np.zeros((depth, height, width), dtype=np.uint8)

        # Cache in memory
        self.segmentations_cache[segmentation_id] = {
            "metadata": metadata,
            "masks_3d": masks_3d,
            "image_shape": image_shape,
            "source_format": source_format  # Store format for saving
        }

        # Save to disk
        self._save_segmentation(segmentation_id)

        return SegmentationResponse(
            segmentation_id=segmentation_id,
            file_id=file_id,
            metadata=metadata,
            total_slices=depth,
            masks=None
        )

    async def apply_paint_stroke(
        self,
        segmentation_id: str,
        stroke: PaintStroke
    ) -> bool:
        """
        Apply a paint stroke to the segmentation mask.

        Args:
            segmentation_id: Segmentation ID
            stroke: Paint stroke data

        Returns:
            True if successful
        """
        if segmentation_id not in self.segmentations_cache:
            # Try to load from disk
            if not self._load_segmentation(segmentation_id):
                raise NotFoundException(
                    message=f"Segmentation not found: {segmentation_id}",
                    error_code="SEGMENTATION_NOT_FOUND",
                    details={"segmentation_id": segmentation_id}
                )

        seg_data = self.segmentations_cache[segmentation_id]
        masks_3d = seg_data["masks_3d"]

        # Validate slice index (using D,H,W convention)
        if stroke.slice_index >= masks_3d.shape[0]:
            raise ValidationException(
                message=f"Slice index {stroke.slice_index} out of range (max: {masks_3d.shape[0]-1})",
                error_code="SLICE_INDEX_OUT_OF_RANGE",
                details={
                    "slice_index": stroke.slice_index,
                    "max_slice": masks_3d.shape[0]-1,
                    "segmentation_id": segmentation_id
                }
            )

        # Get the slice (using D, H, W convention)
        mask_slice = masks_3d[stroke.slice_index, :, :]

        # Apply circular brush
        label_value = 0 if stroke.erase else stroke.label_id
        self._apply_circular_brush(
            mask_slice,
            stroke.x,
            stroke.y,
            stroke.brush_size,
            label_value
        )

        # Update modification time
        seg_data["metadata"].modified_at = datetime.utcnow()

        # Invalidate cache for this specific slice
        if self.cache:
            cache_key = f"seg:mask:{segmentation_id}:{stroke.slice_index}"
            await self.cache.delete(cache_key)
            logger.debug(f"Invalidated cache for segmentation slice: {segmentation_id}:{stroke.slice_index}")

        # Don't save to disk on every paint stroke - only save when explicitly requested
        # This prevents excessive file writes and Google Drive uploads
        # self._save_segmentation(segmentation_id)

        return True

    def _apply_circular_brush(
        self,
        mask: np.ndarray,
        center_x: int,
        center_y: int,
        brush_size: int,
        value: int
    ):
        """
        Apply square brush to mask (voxel-by-voxel painting).

        Args:
            mask: 2D mask array (modified in place)
            center_x: X coordinate of brush center
            center_y: Y coordinate of brush center
            brush_size: Brush size in voxels (1 = 1x1, 3 = 3x3, etc.)
            value: Label value to paint
        """
        height, width = mask.shape

        # Calculate square brush bounds
        # brush_size=1 paints 1 voxel, brush_size=3 paints 3x3 voxels, etc.
        half_size = brush_size // 2

        # Calculate bounds (inclusive)
        y_min = max(0, center_y - half_size)
        y_max = min(height, center_y + half_size + 1)
        x_min = max(0, center_x - half_size)
        x_max = min(width, center_x + half_size + 1)

        logger.debug(
            "Applying square brush",
            extra={
                "center": {"x": center_x, "y": center_y},
                "brush_size": brush_size,
                "bounds": {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max},
                "voxels_painted": (x_max-x_min)*(y_max-y_min)
            }
        )

        # Apply square brush
        mask[y_min:y_max, x_min:x_max] = value

    async def get_slice_mask(
        self,
        segmentation_id: str,
        slice_index: int
    ) -> Optional[np.ndarray]:
        """
        Get segmentation mask for a specific slice with caching.

        Args:
            segmentation_id: Segmentation ID
            slice_index: Slice index

        Returns:
            2D numpy array with label values, or None if not found
        """
        # Try Redis cache first
        cache_key = f"seg:mask:{segmentation_id}:{slice_index}"
        if self.cache:
            cached_mask = await self.cache.get(cache_key)
            if cached_mask is not None:
                logger.debug(f"Cache hit for segmentation mask: {segmentation_id}:{slice_index}")
                # Convert list back to numpy array
                return np.array(cached_mask, dtype=np.uint8)

        if segmentation_id not in self.segmentations_cache:
            if not self._load_segmentation(segmentation_id):
                return None

        seg_data = self.segmentations_cache[segmentation_id]
        masks_3d = seg_data["masks_3d"]

        # Check slice index validity (using D, H, W convention)
        if slice_index >= masks_3d.shape[0]:
            return None

        mask = masks_3d[slice_index, :, :].copy()

        # Store in Redis cache (convert numpy to list for JSON serialization)
        if self.cache:
            await self.cache.set(
                cache_key,
                mask.tolist(),
                ttl=None  # No expiration for segmentations (invalidate manually)
            )
            logger.debug(f"Cached segmentation mask: {segmentation_id}:{slice_index}")

        return mask

    async def get_metadata(self, segmentation_id: str) -> Optional[SegmentationMetadata]:
        """
        Get segmentation metadata with caching.

        Args:
            segmentation_id: Segmentation ID

        Returns:
            SegmentationMetadata or None
        """
        # Try Redis cache first
        cache_key = f"seg:metadata:{segmentation_id}"
        if self.cache:
            cached_metadata = await self.cache.get(cache_key)
            if cached_metadata:
                logger.debug(f"Cache hit for segmentation metadata: {segmentation_id}")
                return SegmentationMetadata(**cached_metadata)

        if segmentation_id not in self.segmentations_cache:
            if not self._load_segmentation(segmentation_id):
                return None

        metadata = self.segmentations_cache[segmentation_id]["metadata"]

        # Store in Redis cache
        if self.cache:
            await self.cache.set(
                cache_key,
                metadata.model_dump(),
                ttl=None  # No expiration for segmentation metadata
            )
            logger.debug(f"Cached segmentation metadata: {segmentation_id}")

        return metadata

    def list_segmentations(self, file_id: Optional[str] = None) -> List[SegmentationResponse]:
        """
        List all segmentations, optionally filtered by file_id.

        Args:
            file_id: Optional file ID to filter by

        Returns:
            List of SegmentationResponse
        """
        results = []

        # Scan storage directory
        for seg_file in self.storage_path.glob("*.json"):
            seg_id = seg_file.stem

            # Load if not in cache
            if seg_id not in self.segmentations_cache:
                self._load_segmentation(seg_id)

            if seg_id in self.segmentations_cache:
                seg_data = self.segmentations_cache[seg_id]
                metadata = seg_data["metadata"]

                # Filter by file_id if provided
                if file_id is None or metadata.file_id == file_id:
                    results.append(SegmentationResponse(
                        segmentation_id=seg_id,
                        file_id=metadata.file_id,
                        metadata=metadata,
                        total_slices=seg_data["masks_3d"].shape[2],
                        masks=None
                    ))

        return results

    async def generate_overlay_image(
        self,
        base_image: np.ndarray,
        segmentation_id: str,
        slice_index: int,
        show_labels: Optional[List[int]] = None
    ) -> str:
        """
        Generate overlay image with segmentation mask on top of base image.

        Args:
            base_image: Base grayscale image (2D numpy array)
            segmentation_id: Segmentation ID
            slice_index: Slice index
            show_labels: Optional list of label IDs to show (None = all visible labels)

        Returns:
            Base64 encoded PNG image
        """
        # Get mask
        mask = await self.get_slice_mask(segmentation_id, slice_index)
        if mask is None:
            # Return base image if no mask
            return array_to_base64(base_image)

        # Get metadata for label colors
        metadata = await self.get_metadata(segmentation_id)
        if metadata is None:
            return array_to_base64(base_image)

        # Normalize base image to 0-255
        base_normalized = normalize_to_uint8(base_image)

        # Convert grayscale to RGB
        overlay_image = np.stack([base_normalized] * 3, axis=-1)

        # Apply each label
        for label_info in metadata.labels:
            if label_info.id == 0 or not label_info.visible:
                continue

            if show_labels is not None and label_info.id not in show_labels:
                continue

            # Get pixels with this label
            label_mask = (mask == label_info.id)

            if not np.any(label_mask):
                continue

            # Parse hex color
            color_rgb = hex_to_rgb(label_info.color)

            # Blend color with base image using alpha compositing
            for c in range(3):
                overlay_image[:, :, c] = np.where(
                    label_mask,
                    (1 - label_info.opacity) * overlay_image[:, :, c] + label_info.opacity * color_rgb[c],
                    overlay_image[:, :, c]
                )

        # Convert to uint8
        overlay_image = overlay_image.astype(np.uint8)

        return array_to_base64(overlay_image)

    async def generate_segmentation_overlay(
        self,
        segmentation_id: str,
        slice_index: int,
        show_labels: Optional[List[int]] = None
    ) -> str:
        """
        Generate ONLY the segmentation overlay as a transparent PNG.
        Does NOT include the base image - just the colored segmentation mask.

        Args:
            segmentation_id: Segmentation ID
            slice_index: Slice index
            show_labels: Optional list of label IDs to show (None = all visible labels)

        Returns:
            Base64 encoded transparent PNG with only segmentation colors
        """
        # Get mask
        mask = await self.get_slice_mask(segmentation_id, slice_index)
        if mask is None:
            # Return empty transparent image
            empty = np.zeros((10, 10, 4), dtype=np.uint8)
            return array_to_base64(empty)

        # Get metadata for label colors
        metadata = await self.get_metadata(segmentation_id)
        if metadata is None:
            empty = np.zeros((10, 10, 4), dtype=np.uint8)
            return array_to_base64(empty)

        # Create RGBA image (transparent background)
        height, width = mask.shape
        overlay_image = np.zeros((height, width, 4), dtype=np.uint8)

        # Apply each label with transparency
        for label_info in metadata.labels:
            if label_info.id == 0 or not label_info.visible:
                continue

            if show_labels is not None and label_info.id not in show_labels:
                continue

            # Get mask for this label
            label_mask = (mask == label_info.id)
            if not label_mask.any():
                continue

            # Get RGB color
            rgb = hex_to_rgb(label_info.color)

            # Apply color with alpha
            alpha = int(label_info.opacity * 255)
            overlay_image[label_mask, 0] = rgb[0]  # R
            overlay_image[label_mask, 1] = rgb[1]  # G
            overlay_image[label_mask, 2] = rgb[2]  # B
            overlay_image[label_mask, 3] = alpha   # A

        return array_to_base64(overlay_image)

    def _save_segmentation(self, segmentation_id: str):
        """Save segmentation to disk in same format as source (NIfTI or DICOM)."""
        if segmentation_id not in self.segmentations_cache:
            return

        seg_data = self.segmentations_cache[segmentation_id]
        masks_3d = seg_data["masks_3d"]
        metadata = seg_data["metadata"]
        source_format = seg_data.get("source_format", "nifti")  # Default to nifti

        # Save metadata as JSON (for quick access to labels, etc.)
        metadata_path = self.storage_path / f"{segmentation_id}.json"
        metadata_dict = metadata.model_dump(mode='json')
        metadata_dict["source_format"] = source_format  # Store format in metadata

        # Convert datetime objects to ISO format strings for proper JSON serialization
        if 'created_at' in metadata_dict and isinstance(metadata_dict['created_at'], datetime):
            metadata_dict['created_at'] = metadata_dict['created_at'].isoformat()
        if 'modified_at' in metadata_dict and isinstance(metadata_dict['modified_at'], datetime):
            metadata_dict['modified_at'] = metadata_dict['modified_at'].isoformat()

        with open(metadata_path, 'w') as f:
            json.dump(metadata_dict, f, indent=2)

        # Save masks in appropriate format
        if source_format == "nifti":
            self._save_as_nifti(segmentation_id, masks_3d, metadata)
        else:
            self._save_as_dicom(segmentation_id, masks_3d, metadata)

    def _save_as_nifti(self, segmentation_id: str, masks_3d: np.ndarray, metadata):
        """Save segmentation as NIfTI file (.nii.gz) and upload to Google Drive."""
        # Transpose from internal (D,H,W) convention to NIfTI (W,H,D) convention
        nifti_data = transpose_for_nifti(masks_3d, from_convention='DHW')

        # Create NIfTI image using utility function
        nifti_img = create_nifti_image(nifti_data)

        # Get original file metadata from Google Drive
        file_id = metadata.file_id
        try:
            file_metadata = drive_service.get_file_metadata(file_id)
            original_filename = file_metadata['name']
            parent_folder_id = file_metadata['parents'][0] if file_metadata['parents'] else None

            # Create segmentation filename using utility function
            new_filename = create_segmentation_filename(original_filename)

            logger.debug("Renaming segmentation file", extra={"original": original_filename, "new": new_filename})

        except Exception as e:
            logger.warning("Could not get file metadata from Google Drive", extra={"error": str(e)})
            new_filename = f"{segmentation_id}_seg.nii.gz"
            parent_folder_id = None

        # Save locally using utility function
        output_path = self.storage_path / new_filename
        save_nifti(nifti_img, str(output_path), compress=True)
        logger.info("Saved segmentation locally as NIfTI", extra={"output_path": str(output_path)})

        # Upload to Google Drive in the same folder as original image
        try:
            uploaded_file_id = drive_service.upload_file(
                file_path=str(output_path),
                filename=new_filename,
                parent_folder_id=parent_folder_id,
                mime_type='application/gzip'
            )
            logger.info("Uploaded segmentation to Google Drive", extra={"file_id": uploaded_file_id})
        except Exception as e:
            logger.error("Failed to upload segmentation to Google Drive", extra={"error": str(e)})
            logger.warning("Segmentation saved locally only (Google Drive upload failed)", extra={"output_path": str(output_path)})

    def _save_as_dicom(self, segmentation_id: str, masks_3d: np.ndarray, metadata):
        """Save segmentation as DICOM series using utility functions."""
        dicom_dir = self.storage_path / "dicom" / segmentation_id
        dicom_dir.mkdir(parents=True, exist_ok=True)

        depth, height, width = masks_3d.shape

        # Create one DICOM file per slice using utility function
        for slice_idx in range(depth):
            slice_data = masks_3d[slice_idx, :, :]

            # Create DICOM dataset using utility function
            ds = create_segmentation_dicom(
                pixel_data=slice_data,
                rows=height,
                columns=width,
                slice_index=slice_idx,
                patient_id=metadata.file_id,
                series_description=f"Segmentation - {metadata.description or 'Manual'}",
                output_filename=f"seg_{slice_idx:04d}.dcm"
            )

            # Save using utility function
            output_path = dicom_dir / f"seg_{slice_idx:04d}.dcm"
            save_dicom(ds, str(output_path))

        logger.info("Saved segmentation as DICOM series", extra={"num_files": depth, "directory": str(dicom_dir)})

    def _load_segmentation(self, segmentation_id: str) -> bool:
        """Load segmentation from disk (DICOM series)."""
        metadata_path = self.storage_path / f"{segmentation_id}.json"
        dicom_dir = self.storage_path / "dicom" / segmentation_id

        if not metadata_path.exists():
            return False

        try:
            # Load metadata
            with open(metadata_path, 'r') as f:
                metadata_dict = json.load(f)

            # Extract source_format before creating metadata
            source_format = metadata_dict.pop('source_format', 'nifti')

            # Create metadata from dict (Pydantic will validate)
            metadata = SegmentationMetadata(**metadata_dict)

            # Load masks from DICOM series
            if dicom_dir.exists():
                # Get all DICOM files sorted by name
                dicom_files = sorted(dicom_dir.glob("seg_*.dcm"))

                if len(dicom_files) == 0:
                    logger.warning("No DICOM files found", extra={"directory": str(dicom_dir)})
                    return False

                # Read first file to get dimensions
                first_ds = pydicom.dcmread(dicom_files[0])
                height = first_ds.Rows
                width = first_ds.Columns
                depth = len(dicom_files)

                # Create 3D array
                masks_3d = np.zeros((depth, height, width), dtype=np.uint8)

                # Load each slice
                for idx, dicom_file in enumerate(dicom_files):
                    ds = pydicom.dcmread(dicom_file)
                    pixel_array = ds.pixel_array
                    masks_3d[idx, :, :] = pixel_array.astype(np.uint8)

                logger.debug("Loaded segmentation from {len(dicom_files)} DICOM files")
            else:
                # Fallback: try to load from old NPY format
                masks_path = self.storage_path / f"{segmentation_id}.npy"
                if masks_path.exists():
                    masks_3d = np.load(masks_path)
                    logger.debug("Loaded segmentation from legacy NPY format")
                else:
                    logger.warning("No segmentation data found", extra={"segmentation_id": segmentation_id})
                    return False

            # Validate and migrate dimensions if needed (for old segmentations created with wrong convention)
            # Expected: (Depth, Height, Width) medical imaging convention
            # Old incorrect convention: (Height, Width, Depth)
            expected_depth = metadata.image_shape.slices
            expected_height = metadata.image_shape.rows
            expected_width = metadata.image_shape.columns

            actual_shape = masks_3d.shape
            if actual_shape != (expected_depth, expected_height, expected_width):
                # Check if it's in the old (H,W,D) format
                if actual_shape == (expected_height, expected_width, expected_depth):
                    logger.warning(
                        "Migrating old segmentation from (H,W,D) to (D,H,W) convention",
                        extra={
                            "segmentation_id": segmentation_id,
                            "old_shape": actual_shape,
                            "new_shape": (expected_depth, expected_height, expected_width)
                        }
                    )
                    # Transpose from (H,W,D) to (D,H,W)
                    masks_3d = np.transpose(masks_3d, (2, 0, 1))
                else:
                    logger.error(
                        "Segmentation dimensions don't match expected shape",
                        extra={
                            "segmentation_id": segmentation_id,
                            "expected": (expected_depth, expected_height, expected_width),
                            "actual": actual_shape
                        }
                    )
                    return False

            # Cache in memory
            self.segmentations_cache[segmentation_id] = {
                "metadata": metadata,
                "masks_3d": masks_3d,
                "image_shape": masks_3d.shape,
                "source_format": source_format
            }

            return True
        except Exception as e:
            # TODO: Replace with structured logging in Phase 2
            logger.error("Error loading segmentation", extra={"segmentation_id": segmentation_id, "error": str(e)})
            return False

    def export_to_dicom_series(self, segmentation_id: str, output_dir: Optional[str] = None) -> str:
        """
        Export segmentation as DICOM series (one file per slice).

        Args:
            segmentation_id: ID of the segmentation to export
            output_dir: Directory to save DICOM files (default: ./data/segmentations/dicom/)

        Returns:
            Path to the directory containing the DICOM series
        """
        if segmentation_id not in self.segmentations_cache:
            if not self._load_segmentation(segmentation_id):
                raise NotFoundException(
                    message=f"Segmentation not found: {segmentation_id}",
                    error_code="SEGMENTATION_NOT_FOUND",
                    details={"segmentation_id": segmentation_id}
                )

        seg_data = self.segmentations_cache[segmentation_id]
        masks_3d = seg_data["masks_3d"]
        metadata = seg_data["metadata"]

        # Create output directory
        if output_dir is None:
            output_dir = self.storage_path / "dicom" / segmentation_id
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # Get dimensions
        depth, height, width = masks_3d.shape

        # Create one DICOM file per slice
        for slice_idx in range(depth):
            slice_data = masks_3d[slice_idx, :, :]

            # Create DICOM dataset
            file_meta = Dataset()
            file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.7'  # Secondary Capture Image Storage
            file_meta.MediaStorageSOPInstanceUID = generate_uid()
            file_meta.TransferSyntaxUID = '1.2.840.10008.1.2.1'  # Explicit VR Little Endian
            file_meta.ImplementationClassUID = generate_uid()

            # Create file dataset
            ds = FileDataset(
                filename=str(output_dir / f"slice_{slice_idx:04d}.dcm"),
                dataset={},
                file_meta=file_meta,
                preamble=b"\0" * 128
            )

            # Patient information
            ds.PatientName = metadata.file_id[:64]  # Use file_id as patient name
            ds.PatientID = metadata.file_id[:64]

            # Study information
            ds.StudyInstanceUID = generate_uid()
            ds.SeriesInstanceUID = generate_uid()
            ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
            ds.SOPClassUID = file_meta.MediaStorageSOPClassUID

            # Series information
            ds.Modality = 'SEG'  # Segmentation modality
            ds.SeriesDescription = f"Segmentation - {metadata.description or 'Manual'}"
            ds.SeriesNumber = 1
            ds.InstanceNumber = slice_idx + 1

            # Image information
            ds.SamplesPerPixel = 1
            ds.PhotometricInterpretation = 'MONOCHROME2'
            ds.Rows = height
            ds.Columns = width
            ds.BitsAllocated = 16
            ds.BitsStored = 16
            ds.HighBit = 15
            ds.PixelRepresentation = 0  # Unsigned

            # Convert mask to uint16 for DICOM
            pixel_array = slice_data.astype(np.uint16)
            ds.PixelData = pixel_array.tobytes()

            # Slice location
            ds.SliceLocation = float(slice_idx)
            ds.ImagePositionPatient = [0, 0, float(slice_idx)]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]

            # Pixel spacing (use default if not available)
            ds.PixelSpacing = [1.0, 1.0]
            ds.SliceThickness = 1.0

            # Content date/time
            now = datetime.now()
            ds.ContentDate = now.strftime('%Y%m%d')
            ds.ContentTime = now.strftime('%H%M%S')
            ds.StudyDate = now.strftime('%Y%m%d')
            ds.StudyTime = now.strftime('%H%M%S')
            ds.SeriesDate = now.strftime('%Y%m%d')
            ds.SeriesTime = now.strftime('%H%M%S')

            # Save DICOM file
            output_path = output_dir / f"slice_{slice_idx:04d}.dcm"
            ds.save_as(output_path, write_like_original=False)

        logger.info("Exported DICOM slices", extra={"num_slices": depth, "directory": str(output_dir)})
        return str(output_dir)

    def delete_segmentation(self, segmentation_id: str) -> bool:
        """
        Delete a segmentation.

        Args:
            segmentation_id: Segmentation ID

        Returns:
            True if successful
        """
        # Remove from cache
        if segmentation_id in self.segmentations_cache:
            del self.segmentations_cache[segmentation_id]

        # Delete from disk
        metadata_path = self.storage_path / f"{segmentation_id}.json"
        masks_path = self.storage_path / f"{segmentation_id}.npy"

        success = False
        if metadata_path.exists():
            metadata_path.unlink()
            success = True
        if masks_path.exists():
            masks_path.unlink()
            success = True

        return success

    def get_segmentation(self, segmentation_id: str) -> Optional[SegmentationResponse]:
        """
        Get a segmentation by ID.

        Args:
            segmentation_id: Segmentation ID

        Returns:
            SegmentationResponse or None if not found
        """
        if segmentation_id not in self.segmentations_cache:
            if not self._load_segmentation(segmentation_id):
                return None

        seg_data = self.segmentations_cache[segmentation_id]
        metadata = seg_data["metadata"]

        return SegmentationResponse(
            segmentation_id=segmentation_id,
            file_id=metadata.file_id,
            metadata=metadata,
            total_slices=seg_data["masks_3d"].shape[0],  # Using D,H,W convention
            masks=None
        )

    async def get_segmentation_overlay(
        self,
        segmentation_id: str,
        slice_index: int,
        alpha: float = 0.5
    ) -> bytes:
        """
        Generate a PNG overlay for a specific slice.

        Args:
            segmentation_id: Segmentation ID
            slice_index: Slice index
            alpha: Opacity (0.0 to 1.0)

        Returns:
            PNG image bytes
        """
        # Use the existing generate_segmentation_overlay method
        # but convert base64 string to bytes
        base64_img = await self.generate_segmentation_overlay(
            segmentation_id=segmentation_id,
            slice_index=slice_index,
            show_labels=None
        )

        # Extract base64 data from data URL
        if base64_img.startswith("data:image/png;base64,"):
            base64_data = base64_img[len("data:image/png;base64,"):]
            return base64.b64decode(base64_data)

        return b""

    def export_to_nifti(
        self,
        segmentation_id: str,
        output_path: str
    ) -> str:
        """
        Export segmentation to NIfTI format.

        Args:
            segmentation_id: Segmentation ID
            output_path: Path to save NIfTI file

        Returns:
            Path to exported file
        """
        if segmentation_id not in self.segmentations_cache:
            if not self._load_segmentation(segmentation_id):
                raise NotFoundException(
                    message=f"Segmentation not found: {segmentation_id}",
                    error_code="SEGMENTATION_NOT_FOUND",
                    details={"segmentation_id": segmentation_id}
                )

        seg_data = self.segmentations_cache[segmentation_id]
        masks_3d = seg_data["masks_3d"]

        # Transpose from internal (D,H,W) to NIfTI (W,H,D) using utility
        nifti_data = transpose_for_nifti(masks_3d, from_convention='DHW')

        # Create NIfTI image using utility function
        nifti_img = create_nifti_image(nifti_data)

        # Save using utility function
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        save_nifti(nifti_img, str(output_file), compress=output_path.endswith('.gz'))

        logger.info("Exported segmentation to NIfTI", extra={"output_path": str(output_file)})
        return str(output_file)

    def export_to_dicom_seg(
        self,
        segmentation_id: str,
        output_path: str,
        reference_dicom: bytes
    ) -> str:
        """
        Export segmentation to DICOM SEG format.

        Args:
            segmentation_id: Segmentation ID
            output_path: Path to save DICOM SEG file
            reference_dicom: Reference DICOM file bytes

        Returns:
            Path to exported file
        """
        # Use the existing export_to_dicom_series method
        # This creates a directory with DICOM series
        output_dir = self.export_to_dicom_series(segmentation_id, output_path)

        logger.info("Exported segmentation to DICOM series", extra={"output_dir": output_dir})
        return output_dir

    def get_segmentation_statistics(
        self,
        segmentation_id: str
    ) -> Dict[str, Any]:
        """
        Calculate statistics for a segmentation.

        Args:
            segmentation_id: Segmentation ID

        Returns:
            Dictionary with statistics (volume, label counts, etc.)
        """
        if segmentation_id not in self.segmentations_cache:
            if not self._load_segmentation(segmentation_id):
                raise NotFoundException(
                    message=f"Segmentation not found: {segmentation_id}",
                    error_code="SEGMENTATION_NOT_FOUND",
                    details={"segmentation_id": segmentation_id}
                )

        seg_data = self.segmentations_cache[segmentation_id]
        masks_3d = seg_data["masks_3d"]
        metadata = seg_data["metadata"]

        # Calculate statistics for each label
        label_stats = {}
        unique_labels = np.unique(masks_3d)

        for label_id in unique_labels:
            if label_id == 0:  # Skip background
                continue

            # Count voxels for this label
            label_mask = (masks_3d == label_id)
            voxel_count = np.sum(label_mask)

            # Get label info
            label_info = next((l for l in metadata.labels if l.id == label_id), None)
            label_name = label_info.name if label_info else f"Label {label_id}"

            label_stats[str(label_id)] = {
                "name": label_name,
                "voxel_count": int(voxel_count),
                "volume_voxels": int(voxel_count),  # Volume in voxels
                "percentage": float(voxel_count / masks_3d.size * 100)
            }

        return {
            "segmentation_id": segmentation_id,
            "total_voxels": int(masks_3d.size),
            "image_shape": list(masks_3d.shape),
            "label_statistics": label_stats,
            "num_labels": len(label_stats)
        }
