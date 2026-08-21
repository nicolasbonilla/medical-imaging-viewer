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
from app.core.exceptions import SegmentationException, NotFoundException, ValidationException, ConflictException

# Sentinel for _save_masks_to_gcs/_save_segmentation/persist: "no explicit
# baseline supplied — derive the if_generation_match from the generation this
# instance observed when it loaded the mask (stored in _gcs_generations)."
# Distinct from an explicit None (which callers may legitimately want to mean
# "the client sent no If-Match token"), so the two cases stay separable. (A-2)
_GEN_FROM_CACHE = object()
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

    Note: This is the service used by /api/v1/segmentation/ routes.
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

        # A-2 optimistic concurrency: the GCS object generation observed when THIS
        # instance last loaded each mask. Used as the if_generation_match baseline
        # so a stale whole-mask overwrite from a concurrent instance/tab 412s
        # instead of silently clobbering newer work. None => no trustworthy
        # baseline (create-only write). Populated by _load_masks_from_gcs.
        self._gcs_generations: Dict[str, Optional[int]] = {}

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

    # ------------------------------------------------------------------
    # Public cache accessors
    #
    # These form the supported surface for callers (API routes) so they no
    # longer reach into the private `segmentations_cache` dict or the
    # underscore-prefixed persistence helpers. This keeps the in-memory
    # working set an implementation detail of the service (IEC 62304: a single
    # audited access path to Class C segmentation state).
    # ------------------------------------------------------------------
    def is_cached(self, segmentation_id: str) -> bool:
        """Return True if the segmentation is currently in the in-memory cache."""
        return segmentation_id in self.segmentations_cache

    def get_cached(self, segmentation_id: str) -> Optional[dict]:
        """Return the cached entry without touching durable storage (None if not loaded)."""
        return self.segmentations_cache.get(segmentation_id)

    def discard_cached(self, segmentation_id: str) -> None:
        """Drop ALL in-memory state for a segmentation (mask cache + A-2 generation
        baseline) so the next access reloads the authoritative durable version.

        Used to roll back after a refused (409) stale write: restoring the
        instance's own cached mask could pin a STALE mask + stale generation if
        another instance advanced the durable object (audit A-2 Finding 1), which
        would show the clinician an older segmentation than the truth and trap
        them in a conflict loop. Eviction is the only correct rollback.
        """
        self.segmentations_cache.pop(segmentation_id, None)
        self._gcs_generations.pop(segmentation_id, None)

    def get_generation(self, segmentation_id: str) -> Optional[int]:
        """Return the GCS object generation matching the currently-held mask bytes,
        or None if unknown (local tier / never loaded from GCS). (A-2)

        A client that reads this at load time and round-trips it as `If-Match` on
        save makes ITS OWN observed generation authoritative — which is what
        distinguishes two tabs sharing ONE instance's cache (whose shared
        instance-level baseline cannot tell them apart) and closes the reroute
        silent-clobber case that Increment 1's instance baseline alone does not.
        """
        return self._gcs_generations.get(segmentation_id)

    def get_loaded(self, segmentation_id: str) -> Optional[dict]:
        """Return the segmentation entry, loading it from storage if needed.

        Returns None if the segmentation exists nowhere (caller decides 404 vs
        fallback). This is the faithful, single-source replacement for the
        previous inline `if id not in cache: _load_segmentation(id)` pattern.
        """
        if segmentation_id not in self.segmentations_cache:
            if not self._load_segmentation(segmentation_id):
                return None
        return self.segmentations_cache.get(segmentation_id)

    def get_mask(self, segmentation_id: str) -> Optional[np.ndarray]:
        """Return the 3D mask array (D, H, W), loading if needed. None if absent."""
        entry = self.get_loaded(segmentation_id)
        return entry["masks_3d"] if entry else None

    def set_mask(self, segmentation_id: str, mask: np.ndarray) -> bool:
        """Replace the in-memory 3D mask for a cached segmentation.

        Returns False if the segmentation is not currently cached (caller decides
        whether to load first). Does not persist — call persist() to save.
        """
        entry = self.segmentations_cache.get(segmentation_id)
        if entry is None:
            return False
        entry["masks_3d"] = mask
        return True

    def persist(
        self,
        segmentation_id: str,
        *,
        expected_generation=_GEN_FROM_CACHE,
        force: bool = False,
    ) -> Optional[str]:
        """Persist metadata + mask to durable storage (public form of
        _save_segmentation). Returns the durability tier: "gcs" (durable),
        "local" (ephemeral fallback only), or None (nothing to persist).

        A-2 optimistic concurrency (defaults preserve pre-A-2 behavior):
          - expected_generation: an int GCS generation the caller (client) is
            writing against; omit to use the generation THIS instance observed at
            load. Raises ConflictException (-> 409) if the durable object moved on.
          - force: deliberate unconditional overwrite (clinician chose "overwrite").
        """
        return self._save_segmentation(
            segmentation_id, expected_generation=expected_generation, force=force,
        )

    def array_to_base64(self, array: np.ndarray) -> str:
        """Encode a 2D mask slice to a base64 PNG data string."""
        return array_to_base64(array)

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

        # Defense-in-depth (audit P-1.1): a mask ingested from an immutable buffer
        # (np.frombuffer, memory-mapped load, cache deserialization) can be
        # read-only, which makes the in-place brush below raise. Promote the
        # CACHED array to writable once so the edit persists across strokes.
        if not masks_3d.flags.writeable:
            # .copy() always returns a writable, C-contiguous array (unlike
            # np.ascontiguousarray, which is a no-op on an already-contiguous
            # read-only array and would leave it read-only).
            masks_3d = masks_3d.copy()
            seg_data["masks_3d"] = masks_3d

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

        # Persist FIRST, then invalidate the slice cache. This ordering matters for
        # concurrency (audit P-4.2, lost-update race): the read -> in-place brush ->
        # `_save_segmentation` sequence above/below contains NO `await`, so it runs
        # atomically on the single-threaded event loop. A concurrent upload/delete on
        # the same segmentation therefore cannot interleave at a yield point and orphan
        # this stroke (`_save_segmentation` re-reads `seg_data["masks_3d"]`, so a mid-
        # mutation yield would let a replacement pointer win). The ONLY await —
        # `cache.delete` — is moved AFTER the save so nothing yields mid-mutation.
        # NOTE: `_save_segmentation` is synchronous so the client knows data is durable
        # before this returns (the frontend depends on it to gate slice changes).
        try:
            self._save_segmentation(segmentation_id)
            if self.cache:
                cache_key = f"seg:mask:{segmentation_id}:{stroke.slice_index}"
                await self.cache.delete(cache_key)
                logger.debug(f"Invalidated cache for segmentation slice: {segmentation_id}:{stroke.slice_index}")
            logger.info("Paint stroke saved to GCS", extra={
                "segmentation_id": segmentation_id,
                "slice_index": stroke.slice_index,
                "position": {"x": stroke.x, "y": stroke.y}
            })
        except ConflictException:
            # A-2: a stale-write conflict must surface as a reconcilable 409, not be
            # repackaged as a generic GCS_SAVE_FAILED (500). Propagate verbatim.
            raise
        except Exception as e:
            logger.error("Failed to save paint stroke to GCS", extra={
                "error": str(e),
                "segmentation_id": segmentation_id,
                "slice_index": stroke.slice_index
            })
            # IMPORTANT: Re-raise the exception so the frontend knows the save failed
            # This allows the frontend to keep local paints as backup
            raise SegmentationException(
                message=f"Failed to persist paint stroke to cloud storage: {str(e)}",
                error_code="GCS_SAVE_FAILED",
                details={"segmentation_id": segmentation_id, "slice_index": stroke.slice_index}
            )

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

        In Cloud Run multi-instance environment:
        - If segmentation is NOT in cache: load from GCS (fresh data)
        - If segmentation IS in cache: use it (this instance may have painted)

        The key insight is that paint strokes are saved immediately to GCS,
        so any instance loading fresh will get the latest data. An instance
        that has the segmentation in cache either:
        a) Has fresh data (just painted), or
        b) May have stale data, but will sync on next full reload

        Args:
            segmentation_id: Segmentation ID
            slice_index: Slice index

        Returns:
            2D numpy array with label values, or None if not found
        """
        logger.debug(f"Getting slice mask for {segmentation_id}:{slice_index}")

        # Load from GCS if not in memory cache
        if segmentation_id not in self.segmentations_cache:
            logger.info(f"Loading segmentation {segmentation_id} from GCS (not in cache)")
            if not self._load_segmentation(segmentation_id):
                logger.warning(f"Failed to load segmentation {segmentation_id} from GCS")
                return None

        seg_data = self.segmentations_cache[segmentation_id]
        masks_3d = seg_data["masks_3d"]

        # Check slice index validity (using D, H, W convention)
        if slice_index >= masks_3d.shape[0]:
            logger.warning(f"Slice index {slice_index} out of range (max: {masks_3d.shape[0]-1})")
            return None

        mask = masks_3d[slice_index, :, :].copy()

        # Log non-zero voxels for debugging
        non_zero = np.sum(mask > 0)
        logger.debug(f"Retrieved mask for slice {slice_index}: {non_zero} non-zero voxels")

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

    def list_segmentations(
        self,
        file_id: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
    ) -> List[SegmentationResponse]:
        """
        List all segmentations, optionally filtered by file_id or file_ids.

        Searches Firestore first, then local storage as fallback.

        Args:
            file_id: Optional single file ID to filter by
            file_ids: Optional list of file IDs to filter by (for study-level queries)

        Returns:
            List of SegmentationResponse
        """
        results = []
        found_ids = set()

        # Determine file_id filter set
        filter_set = None
        if file_ids:
            filter_set = set(file_ids)
        elif file_id:
            filter_set = {file_id}

        # First, query Firestore
        try:
            query = self.db.collection(SEGMENTATIONS_COLLECTION)

            if file_ids and len(file_ids) <= 30:
                # Firestore 'in' operator supports up to 30 values
                query = query.where("file_id", "in", file_ids)
            elif file_id:
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

            logger.info("Listed segmentations from Firestore", extra={
                "count": len(results),
                "file_id": file_id,
                "file_ids_count": len(file_ids) if file_ids else 0,
            })

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

                if filter_set is None or metadata.file_id in filter_set:
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
        except ConflictException:
            # A-2: surface a stale-write conflict as a reconcilable 409 rather than
            # collapsing it to False (which the route reports as a misleading 404).
            raise
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

    def _save_segmentation(
        self,
        segmentation_id: str,
        *,
        expected_generation=_GEN_FROM_CACHE,
        force: bool = False,
    ) -> Optional[str]:
        """Save segmentation to Firestore (metadata) and GCS (masks).

        This ensures persistence across Cloud Run instance restarts.

        Returns the durability tier reached so callers can report it honestly
        (audit P-4.3):
          - "gcs":   durably persisted to GCS + Firestore.
          - "local": GCS/Firestore failed; written to the local fallback ONLY,
                     which is EPHEMERAL on Cloud Run (lost on instance restart and
                     invisible to other instances). Not a durable save.
          - None:    nothing to save (segmentation not in cache).
        Raises only if BOTH GCS and the local fallback fail, OR (A-2) if the GCS
        write is refused as a stale overwrite — ConflictException propagates so the
        route returns 409 instead of laundering the conflict into a "local" save.

        expected_generation / force control the A-2 optimistic-concurrency baseline
        (see _save_masks_to_gcs); defaults preserve the pre-A-2 same-instance flow.
        """
        if segmentation_id not in self.segmentations_cache:
            return None

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
            # Save the mask to GCS FIRST (the durable data), then record the
            # Firestore pointer. If GCS fails, the doc is never written, so a load
            # cannot later find a doc pointing at a non-existent mask and surface an
            # all-zero mask as the clinician's data (see the load path).
            self._save_masks_to_gcs(
                segmentation_id, masks_3d,
                expected_generation=expected_generation, force=force,
            )

            doc_ref = self.db.collection(SEGMENTATIONS_COLLECTION).document(segmentation_id)
            doc_ref.set(metadata_dict)
            logger.info("Saved segmentation to GCS + Firestore", extra={"segmentation_id": segmentation_id})
            return "gcs"

        except ConflictException:
            # A-2: a stale-overwrite conflict must reach the route as 409. Do NOT
            # fall through to the local fallback below — that would report a fake
            # ephemeral "local" success while the durable GCS mask (another
            # session's newer work) still stands, hiding the lost update.
            raise
        except Exception as e:
            logger.error("Failed to save to GCS/Firestore, falling back to local", extra={"error": str(e)})
            # Fallback to local storage. NOTE: ephemeral on Cloud Run — the caller
            # is told the save was NOT durable (P-4.3) so it can warn / keep a backup.
            self._save_segmentation_local(segmentation_id, masks_3d, metadata, source_format)
            return "local"

    # RC-031 (HAZ-006): free-text NIfTI header marker distinguishing masks saved
    # in the corrected MRI-native voxel order from legacy ones. Self-contained in
    # the NIfTI, so the low-level loader needs no Firestore lookup.
    _RC031_ORIENT_MARKER = b"RC031-ORIENT-V2"

    @staticmethod
    def _internal_to_nifti_native(masks_3d: np.ndarray) -> np.ndarray:
        """Internal (k, a0, a1) -> MRI-native NIfTI order (a0, a1, k).

        Internal masks are (D,H,W)=(k,a0,a1)=transpose(mri_native,(2,0,1)) — proven
        in test_rc031_display_convention.py — so the inverse (1,2,0) restores the
        MRI's own voxel array order. A directly-served overlay (longitudinal
        NiiVue, ITK-SNAP, ref_file_id) then aligns with the MRI. The legacy save
        used (2,1,0) => (a1,a0,k), the in-plane TRANSPOSE, which mirrored such
        overlays (HAZ-006) even though it round-tripped internally.
        """
        return np.transpose(masks_3d, (1, 2, 0)).astype(np.uint8)

    @staticmethod
    def _nifti_native_to_internal(nifti_data: np.ndarray, oriented_v2: bool) -> np.ndarray:
        """Stored NIfTI -> internal (k, a0, a1). v2 masks are MRI-native (a0,a1,k)
        so (2,0,1); legacy masks are (a1,a0,k) so (2,1,0). Both yield the same
        internal convention, so display/edit is unaffected — only the on-disk
        orientation (and thus direct-serve alignment) differs."""
        return np.transpose(nifti_data, (2, 0, 1) if oriented_v2 else (2, 1, 0))

    @staticmethod
    def _seg_native_to_reference_order(seg_native: np.ndarray, oriented_v2: bool) -> np.ndarray:
        """Reorient a STORED segmentation NIfTI into the reference MRI's native
        voxel order (a0,a1,k) so a directly-served overlay aligns.

        v2 masks are already MRI-native (a0,a1,k); legacy masks are (a1,a0,k), an
        in-plane swap (1,0,2) away. This is deterministic from the header marker,
        replacing the greedy `sorted(seg_shape)==sorted(ref_shape)` permutation
        that CANNOT detect the swap on square (a0==a1) data — where legacy overlays
        were silently mirrored.
        """
        return seg_native if oriented_v2 else np.transpose(seg_native, (1, 0, 2))

    @classmethod
    def _header_has_v2_marker(cls, header) -> bool:
        try:
            return cls._RC031_ORIENT_MARKER in bytes(np.asarray(header["descrip"]).tobytes())
        except Exception:
            return False

    def _save_masks_to_gcs(
        self,
        segmentation_id: str,
        masks_3d: np.ndarray,
        *,
        expected_generation=_GEN_FROM_CACHE,
        force: bool = False,
    ):
        """Save mask data to Google Cloud Storage as NIfTI format (.nii.gz).

        The segmentation NIfTI will have the EXACT same affine, header, dimensions,
        and voxel sizes as the original MRI image, ensuring perfect spatial alignment
        for use in tools like ITK-SNAP.

        RC-031: the mask is stored in the MRI's own voxel array order (a0,a1,k) and
        tagged with a header marker, so a directly-served overlay aligns. Masks
        without the marker are legacy (in-plane transposed on disk) and are read
        back with the legacy transpose for backward compatibility.

        A-2: the write is conditioned on the GCS object generation (see the upload
        block) so concurrent whole-mask overwrites cannot silently clobber. Raises
        ConflictException (mapped to 409) on a generation mismatch.
        """
        import tempfile
        import os
        from google.api_core.exceptions import PreconditionFailed

        try:
            # Get file_id from segmentation metadata to load original image
            seg_data = self.segmentations_cache.get(segmentation_id)
            file_id = seg_data["metadata"].file_id if seg_data else None

            # Try to get affine and header from original MRI image
            affine = None
            header = None
            original_shape = None

            if file_id:
                try:
                    # Download original NIfTI from GCS to get its affine/header
                    original_blob = self.gcs_bucket.blob(file_id)
                    if original_blob.exists():
                        buffer = io.BytesIO()
                        original_blob.download_to_file(buffer)
                        buffer.seek(0)
                        file_bytes = buffer.read()

                        # Detect file type from extension and magic bytes
                        is_gzipped = file_bytes[:2] == b'\x1f\x8b'
                        if file_id.endswith('.nii.gz') or is_gzipped:
                            suffix = '.nii.gz'
                        else:
                            suffix = '.nii'

                        # Load original NIfTI to get affine and header
                        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                            tmp.write(file_bytes)
                            tmp_path = tmp.name

                        original_nifti = nib.load(tmp_path)
                        affine = original_nifti.affine.copy()
                        header = original_nifti.header.copy()
                        original_shape = original_nifti.shape
                        os.unlink(tmp_path)

                        logger.info("Loaded affine/header from original MRI", extra={
                            "file_id": file_id,
                            "original_shape": original_shape,
                            "original_affine_diag": [affine[0,0], affine[1,1], affine[2,2]],
                            "voxel_sizes": list(header.get_zooms()[:3])
                        })
                    else:
                        logger.warning("Original MRI file not found, using identity affine", extra={"file_id": file_id})
                except Exception as e:
                    logger.warning("Could not load original MRI affine/header", extra={"error": str(e), "file_id": file_id})

            # RC-031: store in the MRI's own voxel array order (a0,a1,k) so a
            # directly-served overlay aligns. internal (k,a0,a1) -> (1,2,0).
            nifti_data = self._internal_to_nifti_native(masks_3d)

            if original_shape is not None and nifti_data.shape != tuple(original_shape):
                # The mask does not correspond voxel-for-voxel to this MRI grid.
                # Keep the RC-031 orientation but flag it; the affine/header may
                # not describe this array cleanly.
                logger.warning("Mask shape does not match original MRI after RC-031 orientation", extra={
                    "internal_shape": masks_3d.shape,
                    "nifti_shape": nifti_data.shape,
                    "original_shape": original_shape,
                })
            else:
                logger.info("Segmentation data prepared for NIfTI (RC-031 MRI-native order)", extra={
                    "internal_shape": masks_3d.shape,
                    "nifti_shape": nifti_data.shape,
                    "original_shape": original_shape,
                })

            # Create NIfTI image with original affine/header if available
            if affine is not None and header is not None:
                # Use the original header but update data-specific fields
                header.set_data_dtype(np.uint8)
                header.set_data_shape(nifti_data.shape)
                # Label masks store class IDs verbatim — never intensity-scaled.
                # set_data_dtype(uint8) already makes nibabel recompute scaling on
                # write (verified: an inherited scl_slope from the MRI does NOT
                # corrupt labels 0-255), but we reset slope/inter EXPLICITLY so the
                # "labels are verbatim" invariant does not depend on implicit
                # library behavior. Audit P-4.1.
                header.set_slope_inter(1.0, 0.0)
                header["descrip"] = self._RC031_ORIENT_MARKER  # RC-031 v2 tag
                nifti_img = nib.Nifti1Image(nifti_data.astype(np.uint8), affine, header)
                logger.info("Created segmentation NIfTI with original MRI affine/header", extra={
                    "final_shape": nifti_img.shape,
                    "affine_diag": [affine[0,0], affine[1,1], affine[2,2]]
                })
            else:
                # Fallback to generic NIfTI with identity affine
                nifti_img = create_nifti_image(nifti_data)
                nifti_img.header["descrip"] = self._RC031_ORIENT_MARKER  # RC-031 v2 tag
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

            # A-2 OPTIMISTIC CONCURRENCY. Condition the write on the GCS object
            # generation so a stale whole-mask overwrite from a concurrent
            # instance/tab is REFUSED (412) rather than silently clobbering newer
            # work. Precedence (never write unconditionally on an unknown baseline):
            #   force=True            -> None: deliberate unconditional overwrite.
            #   explicit int token    -> verbatim (client's round-tripped If-Match).
            #   explicit None token   -> treated as UNKNOWN baseline (see below).
            #   _GEN_FROM_CACHE       -> the generation THIS instance observed at load.
            #   unknown baseline      -> 0 (create-only): creates if absent, 412s if a
            #                            blob exists — so an unknown baseline can only
            #                            ADD a conflict, never introduce a new clobber.
            if force:
                gen_match = None
            elif expected_generation is not _GEN_FROM_CACHE:
                if expected_generation is None:
                    cached = self._gcs_generations.get(segmentation_id)
                    gen_match = cached if cached is not None else 0
                else:
                    gen_match = expected_generation
            else:
                cached = self._gcs_generations.get(segmentation_id)
                gen_match = cached if cached is not None else 0

            upload_kwargs = {"content_type": "application/gzip"}
            if gen_match is not None:
                upload_kwargs["if_generation_match"] = gen_match

            try:
                blob.upload_from_file(buffer, **upload_kwargs)
            except PreconditionFailed:
                # 412: the object generation moved since our baseline — another
                # session persisted a newer mask. Surface as a 409 the route maps
                # to a reconcilable conflict; NEVER retry unconditionally here.
                logger.warning(
                    "Refused stale whole-mask overwrite (GCS generation mismatch)",
                    extra={"segmentation_id": segmentation_id, "expected_generation": gen_match},
                )
                raise ConflictException(
                    message=(
                        "This segmentation was modified by another session since you "
                        "loaded it. Your save was refused to avoid overwriting newer "
                        "work. Reload to reconcile, or overwrite deliberately."
                    ),
                    error_code="SEGMENTATION_STALE_WRITE",
                    details={"segmentation_id": segmentation_id, "expected_generation": gen_match},
                )

            # Record the new generation so the NEXT save from this instance matches
            # (else a correct sequential save would self-412 against a stale baseline).
            new_gen = getattr(blob, "generation", None)
            if new_gen is None:
                try:
                    blob.reload()
                    new_gen = getattr(blob, "generation", None)
                except Exception:
                    new_gen = None
            self._gcs_generations[segmentation_id] = new_gen

            logger.info("Saved masks to GCS as NIfTI", extra={
                "segmentation_id": segmentation_id, "path": blob_path,
                "if_generation_match": gen_match, "new_generation": new_gen,
            })
        except ConflictException:
            # Concurrency conflict is a first-class outcome — propagate verbatim so
            # the caller can map it to 409 and NOT to the generic "GCS save failed"
            # path (which would try the local fallback and launder it into a fake
            # ephemeral success, still losing the other session's work). (A-2)
            raise
        except Exception as e:
            logger.error("Failed to save masks to GCS", extra={"error": str(e)})
            raise

    def _get_blob_for_read(self, blob_path: str):
        """Fetch a blob for reading, returning (blob_or_None, generation_or_None).

        Prefers bucket.get_blob() — a SINGLE metadata GET that both proves
        existence (None if absent) and carries the object .generation, so the
        A-2 concurrency baseline costs no extra request over the .exists() GET it
        replaces. Falls back to blob()+exists() for buckets/fakes without
        get_blob(), in which case generation is reported as None (create-only
        writes, still safe). Transient errors propagate to the caller. (A-2)
        """
        get_blob = getattr(self.gcs_bucket, "get_blob", None)
        if callable(get_blob):
            blob = get_blob(blob_path)
            if blob is None:
                return None, None
            return blob, getattr(blob, "generation", None)
        blob = self.gcs_bucket.blob(blob_path)
        if not blob.exists():
            return None, None
        return blob, getattr(blob, "generation", None)

    def _load_masks_from_gcs(self, segmentation_id: str) -> Optional[np.ndarray]:
        """Load mask data from Google Cloud Storage (NIfTI or NPZ format).

        Side effect: records the loaded object's GCS generation in
        self._gcs_generations[segmentation_id] (None if unavailable) so a later
        save can condition its write on the same baseline (A-2). The return type
        is intentionally unchanged (masks or None) so monkeypatched test doubles
        of this method keep working.
        """
        try:
            # First try NIfTI format (new format)
            nifti_blob_path = f"segmentations/{segmentation_id}/masks.nii.gz"
            nifti_blob, nifti_generation = self._get_blob_for_read(nifti_blob_path)

            if nifti_blob is not None:
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
                # RC-031: v2 masks are stored MRI-native (a0,a1,k) and tagged;
                # legacy masks are (a1,a0,k). Read the tag BEFORE unlinking.
                oriented_v2 = self._header_has_v2_marker(nifti_img.header)
                os.unlink(tmp_path)

                masks_3d = self._nifti_native_to_internal(nifti_data, oriented_v2)

                # A-2: record the baseline generation for concurrency-safe writes.
                self._gcs_generations[segmentation_id] = nifti_generation
                logger.info("Loaded masks from GCS (NIfTI)", extra={
                    "segmentation_id": segmentation_id,
                    "shape": masks_3d.shape,
                    "rc031_v2": oriented_v2,
                    "gcs_generation": nifti_generation,
                })
                return masks_3d

            # Fallback to NPZ format (legacy)
            npz_blob_path = f"segmentations/{segmentation_id}/masks.npz"
            npz_blob, npz_generation = self._get_blob_for_read(npz_blob_path)

            if npz_blob is not None:
                buffer = io.BytesIO()
                npz_blob.download_to_file(buffer)
                buffer.seek(0)

                data = np.load(buffer)
                # Force uint8 (audit #11): a non-uint8 legacy NPZ would make tobytes() length
                # (D*H*W*itemsize) mismatch the <III binary header -> frontend garbage overlay
                # + a follow-up Save persisting corruption. The NIfTI branch already coerces.
                masks_3d = np.asarray(data["masks"]).astype(np.uint8)

                # A-2: NPZ is legacy; on the next save the mask is written as NIfTI
                # at a DIFFERENT path, so this NPZ generation is not a valid baseline
                # for that write. Record None => the save is create-only against the
                # (absent) NIfTI object and never clobbers on an unknown baseline.
                self._gcs_generations[segmentation_id] = None
                logger.info("Loaded masks from GCS (NPZ legacy)", extra={"segmentation_id": segmentation_id, "shape": masks_3d.shape})
                return masks_3d

            # No mask object exists yet: clear any stale baseline so a subsequent
            # save is create-only (if_generation_match=0), not conditioned on a
            # generation that no longer applies. (A-2)
            self._gcs_generations.pop(segmentation_id, None)
            logger.debug("No masks found in GCS", extra={"segmentation_id": segmentation_id})
            return None
        except Exception as e:
            # Availability + data-integrity (audit #7): a genuine "not found" already returned
            # None above (blob.exists() False). Reaching HERE means a TRANSIENT read/decode
            # failure (network, corrupt download) — returning None would send it down the
            # caller's "mask absent from GCS" path -> 404, misrepresenting a DURABLE mask as
            # deleted. Re-raise so the route surfaces a retryable 5xx instead.
            logger.error("Transient failure loading masks from GCS", extra={"error": str(e), "segmentation_id": segmentation_id})
            raise SegmentationException(
                message=f"Transient failure reading segmentation masks from storage: {e}",
                error_code="GCS_READ_FAILED",
                details={"segmentation_id": segmentation_id},
            )

    def get_segmentation_nifti(self, segmentation_id: str) -> Optional[bytes]:
        """Get the segmentation NIfTI file as raw bytes for direct serving.

        Returns the NIfTI file (.nii.gz) directly from GCS without any processing.
        This allows WebGL-based viewers like NiiVue to load the segmentation
        as an overlay.

        Args:
            segmentation_id: The segmentation ID

        Returns:
            Raw bytes of the .nii.gz file, or None if not found
        """
        try:
            # Check GCS for the NIfTI file
            nifti_blob_path = f"segmentations/{segmentation_id}/masks.nii.gz"
            nifti_blob = self.gcs_bucket.blob(nifti_blob_path)

            if nifti_blob.exists():
                buffer = io.BytesIO()
                nifti_blob.download_to_file(buffer)
                buffer.seek(0)

                logger.info("Retrieved segmentation NIfTI from GCS", extra={
                    "segmentation_id": segmentation_id,
                    "path": nifti_blob_path,
                    "size_bytes": buffer.getbuffer().nbytes
                })

                return buffer.read()

            logger.warning("Segmentation NIfTI not found in GCS", extra={
                "segmentation_id": segmentation_id,
                "path": nifti_blob_path
            })
            return None

        except Exception as e:
            logger.error("Failed to get segmentation NIfTI", extra={
                "segmentation_id": segmentation_id,
                "error": str(e)
            })
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
                    # DATA-INTEGRITY (HAZ): the Firestore doc exists but its mask is
                    # ABSENT from GCS. That is an inconsistent/corrupt state — a
                    # failed durable save — NOT a valid empty segmentation. The old
                    # code fabricated an all-zero mask and returned success, which
                    # silently presented the clinician with a blank mask in place of
                    # their work. Instead: try the local fallback, and if the mask is
                    # truly unrecoverable, FAIL LOUDLY rather than fabricate data.
                    logger.error(
                        "Segmentation doc exists in Firestore but its mask is missing "
                        "from GCS (possible failed save); attempting local fallback.",
                        extra={"segmentation_id": segmentation_id},
                    )
                    if self._load_segmentation_local(segmentation_id):
                        return True
                    logger.error(
                        "Mask unrecoverable from GCS and local storage — refusing to "
                        "fabricate an empty mask (would silently discard the segmentation).",
                        extra={"segmentation_id": segmentation_id, "mask_shape": mask_shape},
                    )
                    return False

        except SegmentationException:
            # A TRANSIENT GCS read/decode error (audit #7), not a "not found". Try the local
            # fallback for resilience; but if that ALSO fails, RE-RAISE (retryable 5xx) rather
            # than falling through to return False -> 404, which would misrepresent a durable
            # but temporarily-unreadable mask as deleted.
            logger.warning("Transient GCS read error; trying local fallback", extra={"segmentation_id": segmentation_id})
            if self._load_segmentation_local(segmentation_id):
                return True
            raise
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
                        # RC-031: marker-aware transpose (v2 MRI-native vs legacy)
                        masks_3d = self._nifti_native_to_internal(
                            nifti_data, self._header_has_v2_marker(nifti_img.header)
                        )
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
        Delete a segmentation from cache, Firestore, and GCS.

        Args:
            segmentation_id: Segmentation ID

        Returns:
            True if successful
        """
        success = False

        # Remove from cache
        if segmentation_id in self.segmentations_cache:
            del self.segmentations_cache[segmentation_id]
            success = True

        # Delete from Firestore
        try:
            doc_ref = self.db.collection(SEGMENTATIONS_COLLECTION).document(segmentation_id)
            doc = doc_ref.get()
            if doc.exists:
                doc_ref.delete()
                logger.info("Deleted segmentation from Firestore", extra={"segmentation_id": segmentation_id})
                success = True
        except Exception as e:
            logger.error("Failed to delete from Firestore", extra={"segmentation_id": segmentation_id, "error": str(e)})

        # Delete from GCS (masks.nii.gz and masks.npz)
        try:
            for blob_name in [
                f"segmentations/{segmentation_id}/masks.nii.gz",
                f"segmentations/{segmentation_id}/masks.npz",
            ]:
                blob = self.gcs_bucket.blob(blob_name)
                if blob.exists():
                    blob.delete()
                    logger.info("Deleted blob from GCS", extra={"blob": blob_name})
                    success = True
        except Exception as e:
            logger.error("Failed to delete from GCS", extra={"segmentation_id": segmentation_id, "error": str(e)})

        # Also try local disk cleanup (fallback storage)
        metadata_path = self.storage_path / f"{segmentation_id}.json"
        masks_path = self.storage_path / f"{segmentation_id}.npy"
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
