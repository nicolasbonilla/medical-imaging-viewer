"""
Segmentation service for manual lesion annotation.
Provides ITK-SNAP style manual segmentation capabilities.

Uses Firestore for metadata persistence and GCS for mask storage.
This ensures segmentation data survives Cloud Run instance restarts.
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

from google.cloud import storage as gcs_storage

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.exceptions import SegmentationException, NotFoundException, ValidationException
from app.core.interfaces.cache_interface import ICacheService
from app.core.firebase import get_firestore_client
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

# Firestore collection name for segmentations
SEGMENTATIONS_COLLECTION = "segmentations"


class SegmentationService:
    """Service for managing medical image segmentations (v1 API).

    Uses Firestore for metadata and GCS for mask storage to ensure
    persistence across Cloud Run instance restarts.

    Note: This is the v1 service used by /api/v1/segmentation/ routes.
    For the v2 hierarchical API, see SegmentationServiceFirestore.
    """

    def __init__(
        self,
        storage_path: str = "./data/segmentations",
        cache_service: Optional[ICacheService] = None
    ):
        """
        Initialize segmentation service.

        Args:
            storage_path: Directory to store segmentation files (local fallback)
            cache_service: Optional CacheService for Redis caching
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.cache = cache_service
        self.settings = get_settings()

        # In-memory cache: {segmentation_id: {metadata, masks_3d, dirty_slices}}
        self.segmentations_cache: Dict[str, Dict] = {}

        # Firestore client (lazy initialization)
        self._db = None

        # GCS client (lazy initialization)
        self._gcs_client = None
        self._gcs_bucket = None

    @property
    def db(self):
        """Lazy initialization of Firestore client."""
        if self._db is None:
            self._db = get_firestore_client()
        return self._db

    @property
    def gcs_client(self):
        """Lazy initialization of GCS client."""
        if self._gcs_client is None:
            self._gcs_client = gcs_storage.Client()
        return self._gcs_client

    @property
    def gcs_bucket(self):
        """Lazy initialization of GCS bucket."""
        if self._gcs_bucket is None:
            bucket_name = self.settings.GCS_BUCKET_NAME
            self._gcs_bucket = self.gcs_client.bucket(bucket_name)
        return self._gcs_bucket

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

        # IMPORTANT: Save immediately to persist across Cloud Run instance restarts
        # Without this, paint strokes are lost when requests go to different instances
        try:
            self._save_segmentation(segmentation_id)
            logger.debug("Paint stroke saved to GCS", extra={"segmentation_id": segmentation_id})
        except Exception as e:
            logger.error("Failed to save paint stroke", extra={"error": str(e), "segmentation_id": segmentation_id})
            # Don't fail the request if save fails - the stroke is still in memory
            # The user can try saving again manually

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

        Searches Firestore first, then local storage as fallback.

        Args:
            file_id: Optional file ID to filter by

        Returns:
            List of SegmentationResponse
        """
        results = []
        found_ids = set()

        # First, query Firestore
        try:
            query = self.db.collection(SEGMENTATIONS_COLLECTION)
            if file_id:
                query = query.where("file_id", "==", file_id)

            docs = query.stream()
            for doc in docs:
                seg_id = doc.id
                found_ids.add(seg_id)
                data = doc.to_dict()

                # Load into cache if needed
                if seg_id not in self.segmentations_cache:
                    self._load_segmentation(seg_id)

                if seg_id in self.segmentations_cache:
                    seg_data = self.segmentations_cache[seg_id]
                    metadata = seg_data["metadata"]
                    total_slices = seg_data["masks_3d"].shape[0]  # D,H,W convention
                else:
                    # Use data from Firestore directly
                    mask_shape = data.get("mask_shape", [1, 256, 256])
                    total_slices = mask_shape[0] if mask_shape else 1
                    # Create minimal metadata
                    data.pop('source_format', None)
                    data.pop('mask_shape', None)
                    data.pop('segmentation_id', None)
                    metadata = SegmentationMetadata(**data)

                results.append(SegmentationResponse(
                    segmentation_id=seg_id,
                    file_id=metadata.file_id,
                    metadata=metadata,
                    total_slices=total_slices,
                    masks=None
                ))

            logger.info("Listed segmentations from Firestore", extra={"count": len(results), "file_id": file_id})

        except Exception as e:
            logger.warning("Failed to query Firestore, using local", extra={"error": str(e)})

        # Also check local storage (for backward compatibility)
        for seg_file in self.storage_path.glob("*.json"):
            seg_id = seg_file.stem
            if seg_id in found_ids:
                continue  # Already found in Firestore

            if seg_id not in self.segmentations_cache:
                self._load_segmentation(seg_id)

            if seg_id in self.segmentations_cache:
                seg_data = self.segmentations_cache[seg_id]
                metadata = seg_data["metadata"]

                if file_id is None or metadata.file_id == file_id:
                    results.append(SegmentationResponse(
                        segmentation_id=seg_id,
                        file_id=metadata.file_id,
                        metadata=metadata,
                        total_slices=seg_data["masks_3d"].shape[0],
                        masks=None
                    ))

        return results

    async def save_segmentation_async(self, segmentation_id: str) -> bool:
        """
        Explicitly save a segmentation to persistent storage.

        This should be called by the frontend when changing slices or
        when the user clicks "Save".

        Args:
            segmentation_id: ID of the segmentation to save

        Returns:
            True if successful
        """
        if segmentation_id not in self.segmentations_cache:
            logger.warning("Segmentation not in cache, nothing to save", extra={"segmentation_id": segmentation_id})
            return False

        try:
            self._save_segmentation(segmentation_id)
            logger.info("Segmentation saved successfully", extra={"segmentation_id": segmentation_id})
            return True
        except Exception as e:
            logger.error("Failed to save segmentation", extra={"error": str(e), "segmentation_id": segmentation_id})
            return False

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
        """Save segmentation to Firestore (metadata) and GCS (masks).

        This ensures persistence across Cloud Run instance restarts.
        """
        if segmentation_id not in self.segmentations_cache:
            return

        seg_data = self.segmentations_cache[segmentation_id]
        masks_3d = seg_data["masks_3d"]
        metadata = seg_data["metadata"]
        source_format = seg_data.get("source_format", "nifti")

        # Prepare metadata dict for Firestore
        metadata_dict = metadata.model_dump(mode='json')
        metadata_dict["source_format"] = source_format
        metadata_dict["segmentation_id"] = segmentation_id

        # Convert datetime objects to ISO format strings
        if 'created_at' in metadata_dict and isinstance(metadata_dict['created_at'], datetime):
            metadata_dict['created_at'] = metadata_dict['created_at'].isoformat()
        if 'modified_at' in metadata_dict and isinstance(metadata_dict['modified_at'], datetime):
            metadata_dict['modified_at'] = metadata_dict['modified_at'].isoformat()

        # Add image shape info
        metadata_dict["mask_shape"] = list(masks_3d.shape)

        try:
            # Save metadata to Firestore
            doc_ref = self.db.collection(SEGMENTATIONS_COLLECTION).document(segmentation_id)
            doc_ref.set(metadata_dict)
            logger.info("Saved segmentation metadata to Firestore", extra={"segmentation_id": segmentation_id})

            # Save masks to GCS as compressed numpy array
            self._save_masks_to_gcs(segmentation_id, masks_3d)

        except Exception as e:
            logger.error("Failed to save to Firestore/GCS, falling back to local", extra={"error": str(e)})
            # Fallback to local storage
            self._save_segmentation_local(segmentation_id, masks_3d, metadata, source_format)

    def _save_masks_to_gcs(self, segmentation_id: str, masks_3d: np.ndarray):
        """Save mask data to Google Cloud Storage as NIfTI format (.nii.gz).

        The segmentation NIfTI will have the same affine and header as the original
        MRI image, ensuring perfect spatial alignment for use in tools like ITK-SNAP.
        """
        import tempfile
        import os

        try:
            # Get file_id from segmentation metadata to load original image
            seg_data = self.segmentations_cache.get(segmentation_id)
            file_id = seg_data["metadata"].file_id if seg_data else None

            # Transpose from internal (D,H,W) convention to NIfTI (W,H,D) convention
            nifti_data = transpose_for_nifti(masks_3d, from_convention='DHW')

            # Try to get affine and header from original MRI image
            affine = None
            header = None
            if file_id:
                try:
                    # Download original NIfTI from GCS to get its affine/header
                    original_blob = self.gcs_bucket.blob(file_id)
                    if original_blob.exists():
                        buffer = io.BytesIO()
                        original_blob.download_to_file(buffer)
                        buffer.seek(0)

                        # Load original NIfTI to get affine and header
                        with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as tmp:
                            tmp.write(buffer.read())
                            tmp_path = tmp.name

                        original_nifti = nib.load(tmp_path)
                        affine = original_nifti.affine.copy()
                        header = original_nifti.header.copy()
                        os.unlink(tmp_path)

                        logger.info("Loaded affine/header from original MRI", extra={
                            "file_id": file_id,
                            "original_shape": original_nifti.shape,
                            "seg_shape": nifti_data.shape
                        })
                    else:
                        logger.warning("Original MRI file not found, using identity affine", extra={"file_id": file_id})
                except Exception as e:
                    logger.warning("Could not load original MRI affine/header", extra={"error": str(e), "file_id": file_id})

            # Create NIfTI image with original affine/header if available
            if affine is not None and header is not None:
                # Use the original header but update data-specific fields
                header.set_data_dtype(np.uint8)
                header.set_data_shape(nifti_data.shape)
                nifti_img = nib.Nifti1Image(nifti_data.astype(np.uint8), affine, header)
                logger.info("Created segmentation NIfTI with original MRI affine/header")
            else:
                # Fallback to generic NIfTI with identity affine
                nifti_img = create_nifti_image(nifti_data)
                logger.info("Created segmentation NIfTI with identity affine (original not available)")

            # Save to temp file as compressed NIfTI
            with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as tmp:
                tmp_path = tmp.name
            save_nifti(nifti_img, tmp_path, compress=True)

            # Read the compressed file into buffer
            buffer = io.BytesIO()
            with open(tmp_path, 'rb') as f:
                buffer.write(f.read())
            buffer.seek(0)

            # Clean up temp file
            os.unlink(tmp_path)

            # Upload to GCS as NIfTI
            blob_path = f"segmentations/{segmentation_id}/masks.nii.gz"
            blob = self.gcs_bucket.blob(blob_path)
            blob.upload_from_file(buffer, content_type="application/gzip")

            logger.info("Saved masks to GCS as NIfTI", extra={"segmentation_id": segmentation_id, "path": blob_path})
        except Exception as e:
            logger.error("Failed to save masks to GCS", extra={"error": str(e)})
            raise

    def _load_masks_from_gcs(self, segmentation_id: str) -> Optional[np.ndarray]:
        """Load mask data from Google Cloud Storage (NIfTI or NPZ format)."""
        try:
            # First try NIfTI format (new format)
            nifti_blob_path = f"segmentations/{segmentation_id}/masks.nii.gz"
            nifti_blob = self.gcs_bucket.blob(nifti_blob_path)

            if nifti_blob.exists():
                # Load NIfTI format
                buffer = io.BytesIO()
                nifti_blob.download_to_file(buffer)
                buffer.seek(0)

                # nibabel needs a file, so use temp file
                import tempfile
                import os
                with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as tmp:
                    tmp.write(buffer.read())
                    tmp_path = tmp.name

                import nibabel as nib
                nifti_img = nib.load(tmp_path)
                nifti_data = nifti_img.get_fdata().astype(np.uint8)
                os.unlink(tmp_path)

                # Transpose from NIfTI (W,H,D) to internal (D,H,W)
                masks_3d = np.transpose(nifti_data, (2, 1, 0))

                logger.info("Loaded masks from GCS (NIfTI)", extra={"segmentation_id": segmentation_id, "shape": masks_3d.shape})
                return masks_3d

            # Fallback to NPZ format (legacy)
            npz_blob_path = f"segmentations/{segmentation_id}/masks.npz"
            npz_blob = self.gcs_bucket.blob(npz_blob_path)

            if npz_blob.exists():
                buffer = io.BytesIO()
                npz_blob.download_to_file(buffer)
                buffer.seek(0)

                data = np.load(buffer)
                masks_3d = data["masks"]

                logger.info("Loaded masks from GCS (NPZ legacy)", extra={"segmentation_id": segmentation_id, "shape": masks_3d.shape})
                return masks_3d

            logger.debug("No masks found in GCS", extra={"segmentation_id": segmentation_id})
            return None
        except Exception as e:
            logger.error("Failed to load masks from GCS", extra={"error": str(e)})
            return None

    def _save_segmentation_local(self, segmentation_id: str, masks_3d: np.ndarray, metadata, source_format: str):
        """Fallback: Save segmentation to local disk."""
        # Save metadata as JSON
        metadata_path = self.storage_path / f"{segmentation_id}.json"
        metadata_dict = metadata.model_dump(mode='json')
        metadata_dict["source_format"] = source_format

        if 'created_at' in metadata_dict and isinstance(metadata_dict['created_at'], datetime):
            metadata_dict['created_at'] = metadata_dict['created_at'].isoformat()
        if 'modified_at' in metadata_dict and isinstance(metadata_dict['modified_at'], datetime):
            metadata_dict['modified_at'] = metadata_dict['modified_at'].isoformat()

        with open(metadata_path, 'w') as f:
            json.dump(metadata_dict, f, indent=2)

        # Save masks
        if source_format == "nifti":
            self._save_as_nifti(segmentation_id, masks_3d, metadata)
        else:
            self._save_as_dicom(segmentation_id, masks_3d, metadata)

    def _save_as_nifti(self, segmentation_id: str, masks_3d: np.ndarray, metadata):
        """Save segmentation as NIfTI file (.nii.gz) locally."""
        # Transpose from internal (D,H,W) convention to NIfTI (W,H,D) convention
        nifti_data = transpose_for_nifti(masks_3d, from_convention='DHW')

        # Create NIfTI image using utility function
        nifti_img = create_nifti_image(nifti_data)

        # Create segmentation filename from file_id
        file_id = metadata.file_id
        original_filename = file_id.split('/')[-1] if file_id else segmentation_id

        # Create segmentation filename using utility function
        new_filename = create_segmentation_filename(original_filename)
        if not new_filename.endswith('.nii.gz'):
            new_filename = f"{segmentation_id}_seg.nii.gz"

        logger.debug("Creating segmentation file", extra={"original": original_filename, "new": new_filename})

        # Save locally using utility function
        output_path = self.storage_path / new_filename
        save_nifti(nifti_img, str(output_path), compress=True)
        logger.info("Saved segmentation locally as NIfTI", extra={"output_path": str(output_path)})

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
        """Load segmentation from Firestore (metadata) and GCS (masks).

        Falls back to local disk if cloud storage fails.
        """
        try:
            # First try Firestore
            doc_ref = self.db.collection(SEGMENTATIONS_COLLECTION).document(segmentation_id)
            doc = doc_ref.get()

            if doc.exists:
                metadata_dict = doc.to_dict()
                logger.info("Loaded metadata from Firestore", extra={"segmentation_id": segmentation_id})

                # Extract source_format
                source_format = metadata_dict.pop('source_format', 'nifti')
                mask_shape = metadata_dict.pop('mask_shape', None)
                metadata_dict.pop('segmentation_id', None)  # Remove if present

                # Create metadata object
                metadata = SegmentationMetadata(**metadata_dict)

                # Load masks from GCS
                masks_3d = self._load_masks_from_gcs(segmentation_id)

                if masks_3d is not None:
                    # Cache in memory
                    self.segmentations_cache[segmentation_id] = {
                        "metadata": metadata,
                        "masks_3d": masks_3d,
                        "image_shape": masks_3d.shape,
                        "source_format": source_format
                    }
                    logger.info("Segmentation loaded from Firestore/GCS", extra={"segmentation_id": segmentation_id})
                    return True
                else:
                    # Masks not in GCS, create empty based on mask_shape from Firestore
                    if mask_shape:
                        masks_3d = np.zeros(tuple(mask_shape), dtype=np.uint8)
                    else:
                        # Default to small empty mask if no shape info available
                        logger.warning("No mask_shape in Firestore, using default", extra={"segmentation_id": segmentation_id})
                        masks_3d = np.zeros((1, 256, 256), dtype=np.uint8)

                    self.segmentations_cache[segmentation_id] = {
                        "metadata": metadata,
                        "masks_3d": masks_3d,
                        "image_shape": masks_3d.shape,
                        "source_format": source_format
                    }
                    logger.warning("Masks not found in GCS, using empty", extra={"segmentation_id": segmentation_id})
                    return True

        except Exception as e:
            logger.warning("Failed to load from Firestore/GCS, trying local", extra={"error": str(e)})

        # Fallback to local storage
        return self._load_segmentation_local(segmentation_id)

    def _load_segmentation_local(self, segmentation_id: str) -> bool:
        """Fallback: Load segmentation from local disk."""
        metadata_path = self.storage_path / f"{segmentation_id}.json"
        dicom_dir = self.storage_path / "dicom" / segmentation_id

        if not metadata_path.exists():
            return False

        try:
            # Load metadata
            with open(metadata_path, 'r') as f:
                metadata_dict = json.load(f)

            source_format = metadata_dict.pop('source_format', 'nifti')
            metadata = SegmentationMetadata(**metadata_dict)

            # Load masks from DICOM series
            if dicom_dir.exists():
                dicom_files = sorted(dicom_dir.glob("seg_*.dcm"))

                if len(dicom_files) == 0:
                    logger.warning("No DICOM files found", extra={"directory": str(dicom_dir)})
                    return False

                first_ds = pydicom.dcmread(dicom_files[0])
                height = first_ds.Rows
                width = first_ds.Columns
                depth = len(dicom_files)

                masks_3d = np.zeros((depth, height, width), dtype=np.uint8)

                for idx, dicom_file in enumerate(dicom_files):
                    ds = pydicom.dcmread(dicom_file)
                    pixel_array = ds.pixel_array
                    masks_3d[idx, :, :] = pixel_array.astype(np.uint8)

                logger.debug(f"Loaded segmentation from {len(dicom_files)} DICOM files")
            else:
                # Try NPY format
                masks_path = self.storage_path / f"{segmentation_id}.npy"
                if masks_path.exists():
                    masks_3d = np.load(masks_path)
                    logger.debug("Loaded segmentation from legacy NPY format")
                else:
                    # Try NIfTI format
                    nifti_pattern = f"{segmentation_id}*_seg.nii.gz"
                    nifti_files = list(self.storage_path.glob(nifti_pattern))
                    if nifti_files:
                        nifti_img = nib.load(str(nifti_files[0]))
                        nifti_data = nifti_img.get_fdata().astype(np.uint8)
                        # Transpose from NIfTI (W,H,D) to internal (D,H,W)
                        masks_3d = np.transpose(nifti_data, (2, 1, 0))
                        logger.debug("Loaded segmentation from NIfTI format")
                    else:
                        logger.warning("No segmentation data found", extra={"segmentation_id": segmentation_id})
                        return False

            # Note: We skip dimension validation here since metadata doesn't store image_shape
            # The mask shape is authoritative from the loaded file
            logger.debug("Loaded local segmentation", extra={"shape": masks_3d.shape})

            self.segmentations_cache[segmentation_id] = {
                "metadata": metadata,
                "masks_3d": masks_3d,
                "image_shape": masks_3d.shape,
                "source_format": source_format
            }

            return True
        except Exception as e:
            logger.error("Error loading segmentation locally", extra={"error": str(e)})
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
