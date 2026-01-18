"""
Segmentation Service with Firestore backend.

Provides ITK-SNAP style manual segmentation with multi-expert support.
Uses Firestore for metadata and GCS for mask storage.

@module services.segmentation_service_firestore
"""

import numpy as np
import io
import base64
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from PIL import Image

from google.cloud import firestore
from google.cloud import storage as gcs_storage

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.exceptions import SegmentationException, NotFoundException, ValidationException
from app.core.firebase import get_firestore_client
from app.core.interfaces.cache_interface import ICacheService
from app.models.segmentation_schemas import (
    SegmentationStatus,
    SegmentationType,
    LabelInfo,
    SegmentationCreate,
    SegmentationUpdate,
    SegmentationStatusUpdate,
    PaintStroke,
    SegmentationResponse,
    SegmentationSummary,
    SegmentationListResponse,
    SegmentationStatistics,
    LabelStatistics,
    SegmentationSearch,
)

# Import shared utilities
from app.utils import (
    normalize_to_uint8,
    array_to_base64,
    hex_to_rgb,
)

logger = get_logger(__name__)


class SegmentationServiceFirestore:
    """
    Segmentation service using Firestore for metadata and GCS for masks.

    Hierarchy:
    - patients/{patient_id}/studies/{study_id}/series/{series_id}/segmentations/{seg_id}

    Storage:
    - Metadata: Firestore document
    - Masks: GCS bucket (RLE compressed or NIfTI)
    """

    def __init__(
        self,
        cache_service: Optional[ICacheService] = None,
        local_storage_path: str = "./data/segmentations"
    ):
        """
        Initialize segmentation service.

        Args:
            cache_service: Optional Redis cache service
            local_storage_path: Local path for temporary mask storage
        """
        self.settings = get_settings()
        self.db = get_firestore_client()
        self.cache = cache_service
        self.local_storage = Path(local_storage_path)
        self.local_storage.mkdir(parents=True, exist_ok=True)

        # In-memory cache for active segmentations (LRU, max 5)
        self._memory_cache: Dict[str, Dict] = {}
        self._memory_cache_order: List[str] = []
        self._max_memory_cache = 5

        # GCS client (lazy initialization)
        self._gcs_client = None
        self._gcs_bucket = None

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

    def _get_segmentation_ref(
        self,
        patient_id: str,
        study_id: str,
        series_id: str,
        segmentation_id: str
    ) -> firestore.DocumentReference:
        """Get Firestore document reference for a segmentation."""
        return (
            self.db.collection("patients")
            .document(patient_id)
            .collection("studies")
            .document(study_id)
            .collection("series")
            .document(series_id)
            .collection("segmentations")
            .document(segmentation_id)
        )

    def _get_segmentations_collection(
        self,
        patient_id: str,
        study_id: str,
        series_id: str
    ) -> firestore.CollectionReference:
        """Get Firestore collection reference for segmentations of a series."""
        return (
            self.db.collection("patients")
            .document(patient_id)
            .collection("studies")
            .document(study_id)
            .collection("series")
            .document(series_id)
            .collection("segmentations")
        )

    async def create_segmentation(
        self,
        patient_id: str,
        study_id: str,
        series_id: str,
        data: SegmentationCreate,
        user_id: str,
        user_name: str,
        image_shape: Tuple[int, int, int],  # (rows, columns, slices)
        file_id: Optional[str] = None
    ) -> SegmentationResponse:
        """
        Create a new segmentation for a series.

        Args:
            patient_id: Patient UUID
            study_id: Study UUID
            series_id: Series UUID
            data: Creation request data
            user_id: Username of creator
            user_name: Full name of creator
            image_shape: Image dimensions (rows, columns, slices)
            file_id: Optional legacy file_id for backward compatibility

        Returns:
            SegmentationResponse with new segmentation
        """
        segmentation_id = str(uuid.uuid4())
        now = datetime.utcnow()

        rows, columns, slices = image_shape

        # Prepare labels with validation
        labels = data.labels
        if not any(label.id == 0 for label in labels):
            labels.insert(0, LabelInfo(
                id=0, name="Background", color="#000000", opacity=0.0, visible=False
            ))

        # Get primary label color (first non-background visible label)
        primary_color = "#FF0000"
        for label in labels:
            if label.id != 0 and label.visible:
                primary_color = label.color
                break

        # GCS path for masks
        gcs_path = f"segmentations/{patient_id}/{study_id}/{series_id}/{segmentation_id}"

        # Firestore document
        doc_data = {
            "id": segmentation_id,
            "patient_id": patient_id,
            "study_id": study_id,
            "series_id": series_id,
            "file_id": file_id,
            "name": data.name,
            "description": data.description,
            "segmentation_type": data.segmentation_type.value,
            "status": SegmentationStatus.DRAFT.value,
            "progress_percentage": 0,
            "slices_annotated": 0,
            "total_slices": slices,
            "created_by": user_id,
            "created_by_name": user_name,
            "reviewed_by": None,
            "reviewed_by_name": None,
            "reviewed_at": None,
            "review_notes": None,
            "labels": [label.model_dump() for label in labels],
            "primary_label_color": primary_color,
            "image_shape": [rows, columns, slices],
            "gcs_path": gcs_path,
            "created_at": now,
            "modified_at": now,
        }

        # Save to Firestore
        ref = self._get_segmentation_ref(patient_id, study_id, series_id, segmentation_id)
        ref.set(doc_data)

        # Initialize empty 3D mask in memory cache
        # Convention: (depth, height, width) = (slices, rows, columns)
        masks_3d = np.zeros((slices, rows, columns), dtype=np.uint8)

        self._add_to_memory_cache(segmentation_id, {
            "metadata": doc_data,
            "masks_3d": masks_3d,
            "image_shape": (rows, columns, slices),
            "dirty_slices": set(),  # Track which slices need saving
        })

        # Update series segmentation count
        await self._update_segmentation_count(patient_id, study_id, series_id, 1)

        logger.info(
            "Created segmentation",
            extra={
                "segmentation_id": segmentation_id,
                "series_id": series_id,
                "created_by": user_id,
            }
        )

        return self._doc_to_response(doc_data)

    async def get_segmentation(
        self,
        segmentation_id: str,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
        series_id: Optional[str] = None,
    ) -> Optional[SegmentationResponse]:
        """
        Get a segmentation by ID.

        If hierarchy IDs are not provided, will search across all collections.
        """
        # Try memory cache first
        if segmentation_id in self._memory_cache:
            return self._doc_to_response(self._memory_cache[segmentation_id]["metadata"])

        # Try Redis cache
        if self.cache:
            cache_key = f"seg:meta:{segmentation_id}"
            cached = await self.cache.get(cache_key)
            if cached:
                return self._doc_to_response(cached)

        # Query Firestore
        doc_data = await self._find_segmentation_doc(
            segmentation_id, patient_id, study_id, series_id
        )

        if not doc_data:
            return None

        # Cache in Redis
        if self.cache:
            await self.cache.set(f"seg:meta:{segmentation_id}", doc_data, ttl=1800)

        return self._doc_to_response(doc_data)

    async def _find_segmentation_doc(
        self,
        segmentation_id: str,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
        series_id: Optional[str] = None,
    ) -> Optional[Dict]:
        """Find segmentation document in Firestore."""
        if patient_id and study_id and series_id:
            # Direct lookup
            ref = self._get_segmentation_ref(patient_id, study_id, series_id, segmentation_id)
            doc = ref.get()
            return doc.to_dict() if doc.exists else None

        # Search with collection group query
        query = self.db.collection_group("segmentations").where("id", "==", segmentation_id)
        docs = list(query.stream())

        if docs:
            return docs[0].to_dict()
        return None

    async def list_segmentations(
        self,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
        series_id: Optional[str] = None,
        search: Optional[SegmentationSearch] = None,
    ) -> SegmentationListResponse:
        """
        List segmentations with filtering and pagination.

        Can filter by patient, study, or series level.
        """
        search = search or SegmentationSearch()

        # Override hierarchy from search params if not provided
        patient_id = patient_id or (str(search.patient_id) if search.patient_id else None)
        study_id = study_id or (str(search.study_id) if search.study_id else None)
        series_id = series_id or (str(search.series_id) if search.series_id else None)

        # Build query based on hierarchy level
        if series_id and study_id and patient_id:
            # Series level - direct collection query
            base_query = self._get_segmentations_collection(patient_id, study_id, series_id)
        else:
            # Use collection group query for broader searches
            base_query = self.db.collection_group("segmentations")

            if patient_id:
                base_query = base_query.where("patient_id", "==", patient_id)
            if study_id:
                base_query = base_query.where("study_id", "==", study_id)

        # Apply filters
        if search.status:
            base_query = base_query.where("status", "==", search.status.value)
        elif search.status_in:
            base_query = base_query.where("status", "in", [s.value for s in search.status_in])

        if search.created_by:
            base_query = base_query.where("created_by", "==", search.created_by)

        if search.created_after:
            base_query = base_query.where("created_at", ">=", search.created_after)

        if search.created_before:
            base_query = base_query.where("created_at", "<=", search.created_before)

        # Sorting
        direction = firestore.Query.DESCENDING if search.sort_order == "desc" else firestore.Query.ASCENDING
        base_query = base_query.order_by(search.sort_by, direction=direction)

        # Execute query
        docs = list(base_query.stream())
        total = len(docs)

        # Manual pagination (Firestore doesn't support offset well)
        start = (search.page - 1) * search.page_size
        end = start + search.page_size
        page_docs = docs[start:end]

        items = [self._doc_to_summary(doc.to_dict()) for doc in page_docs]

        return SegmentationListResponse(
            items=items,
            total=total,
            page=search.page,
            page_size=search.page_size,
            has_more=end < total,
        )

    async def apply_paint_stroke(
        self,
        segmentation_id: str,
        stroke: PaintStroke,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
        series_id: Optional[str] = None,
    ) -> bool:
        """
        Apply a paint stroke to the segmentation mask.

        Args:
            segmentation_id: Segmentation ID
            stroke: Paint stroke data

        Returns:
            True if successful
        """
        # Load segmentation if not in memory
        if segmentation_id not in self._memory_cache:
            await self._load_segmentation_masks(
                segmentation_id, patient_id, study_id, series_id
            )

        if segmentation_id not in self._memory_cache:
            raise NotFoundException(
                message=f"Segmentation not found: {segmentation_id}",
                error_code="SEGMENTATION_NOT_FOUND"
            )

        cache_entry = self._memory_cache[segmentation_id]
        masks_3d = cache_entry["masks_3d"]

        # Validate slice index
        if stroke.slice_index >= masks_3d.shape[0]:
            raise ValidationException(
                message=f"Slice index {stroke.slice_index} out of range",
                error_code="SLICE_INDEX_OUT_OF_RANGE"
            )

        # Apply brush stroke
        label_value = 0 if stroke.erase else stroke.label_id
        self._apply_brush(
            masks_3d[stroke.slice_index],
            stroke.x,
            stroke.y,
            stroke.brush_size,
            label_value
        )

        # Mark slice as dirty
        cache_entry["dirty_slices"].add(stroke.slice_index)

        # Update modified timestamp
        cache_entry["metadata"]["modified_at"] = datetime.utcnow()

        # Update status if still draft
        if cache_entry["metadata"]["status"] == SegmentationStatus.DRAFT.value:
            cache_entry["metadata"]["status"] = SegmentationStatus.IN_PROGRESS.value

        # Invalidate Redis cache for this slice
        if self.cache:
            cache_key = f"seg:overlay:{segmentation_id}:{stroke.slice_index}"
            await self.cache.delete(cache_key)

        return True

    def _apply_brush(
        self,
        mask: np.ndarray,
        center_x: int,
        center_y: int,
        brush_size: int,
        value: int
    ):
        """Apply square brush to mask (ITK-SNAP style)."""
        height, width = mask.shape
        half_size = brush_size // 2

        y_min = max(0, center_y - half_size)
        y_max = min(height, center_y + half_size + 1)
        x_min = max(0, center_x - half_size)
        x_max = min(width, center_x + half_size + 1)

        mask[y_min:y_max, x_min:x_max] = value

    async def get_slice_overlay(
        self,
        segmentation_id: str,
        slice_index: int,
        visible_labels: Optional[List[int]] = None,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
        series_id: Optional[str] = None,
    ) -> str:
        """
        Generate transparent PNG overlay for a slice.

        Returns:
            Base64 encoded RGBA PNG
        """
        # Check Redis cache first
        cache_key = f"seg:overlay:{segmentation_id}:{slice_index}"
        if self.cache and visible_labels is None:
            cached = await self.cache.get(cache_key)
            if cached:
                return cached

        # Load segmentation if needed
        if segmentation_id not in self._memory_cache:
            await self._load_segmentation_masks(
                segmentation_id, patient_id, study_id, series_id
            )

        if segmentation_id not in self._memory_cache:
            raise NotFoundException(
                message=f"Segmentation not found: {segmentation_id}",
                error_code="SEGMENTATION_NOT_FOUND"
            )

        cache_entry = self._memory_cache[segmentation_id]
        masks_3d = cache_entry["masks_3d"]
        metadata = cache_entry["metadata"]

        if slice_index >= masks_3d.shape[0]:
            raise ValidationException(
                message=f"Slice index {slice_index} out of range",
                error_code="SLICE_INDEX_OUT_OF_RANGE"
            )

        mask = masks_3d[slice_index]
        labels = [LabelInfo(**l) for l in metadata["labels"]]

        # Generate RGBA overlay
        overlay = self._generate_rgba_overlay(mask, labels, visible_labels)

        # Convert to base64 PNG
        img = Image.fromarray(overlay, mode='RGBA')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        base64_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
        result = f"data:image/png;base64,{base64_data}"

        # Cache in Redis
        if self.cache and visible_labels is None:
            await self.cache.set(cache_key, result, ttl=1800)

        return result

    def _generate_rgba_overlay(
        self,
        mask: np.ndarray,
        labels: List[LabelInfo],
        visible_labels: Optional[List[int]] = None
    ) -> np.ndarray:
        """Generate RGBA overlay from mask and labels."""
        height, width = mask.shape
        overlay = np.zeros((height, width, 4), dtype=np.uint8)

        for label in labels:
            if label.id == 0 or not label.visible:
                continue

            if visible_labels is not None and label.id not in visible_labels:
                continue

            label_mask = (mask == label.id)
            if not label_mask.any():
                continue

            rgb = hex_to_rgb(label.color)
            alpha = int(label.opacity * 255)

            overlay[label_mask, 0] = rgb[0]  # R
            overlay[label_mask, 1] = rgb[1]  # G
            overlay[label_mask, 2] = rgb[2]  # B
            overlay[label_mask, 3] = alpha   # A

        return overlay

    async def save_segmentation(
        self,
        segmentation_id: str,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
        series_id: Optional[str] = None,
    ) -> bool:
        """
        Save segmentation to persistent storage (Firestore + GCS).

        Returns:
            True if successful
        """
        if segmentation_id not in self._memory_cache:
            return False

        cache_entry = self._memory_cache[segmentation_id]
        metadata = cache_entry["metadata"]
        masks_3d = cache_entry["masks_3d"]
        dirty_slices = cache_entry["dirty_slices"]

        # Calculate progress
        slices_annotated = self._count_annotated_slices(masks_3d)
        total_slices = masks_3d.shape[0]
        progress = int((slices_annotated / total_slices) * 100) if total_slices > 0 else 0

        # Update metadata
        metadata["slices_annotated"] = slices_annotated
        metadata["progress_percentage"] = progress
        metadata["modified_at"] = datetime.utcnow()

        # Get hierarchy IDs from metadata
        patient_id = patient_id or metadata["patient_id"]
        study_id = study_id or metadata["study_id"]
        series_id = series_id or metadata["series_id"]

        # Save metadata to Firestore
        ref = self._get_segmentation_ref(patient_id, study_id, series_id, segmentation_id)
        ref.update({
            "slices_annotated": slices_annotated,
            "progress_percentage": progress,
            "modified_at": metadata["modified_at"],
            "status": metadata["status"],
        })

        # Save dirty slices to GCS
        if dirty_slices:
            await self._save_masks_to_gcs(
                segmentation_id, masks_3d, dirty_slices, metadata["gcs_path"]
            )
            cache_entry["dirty_slices"] = set()

        # Update Redis cache
        if self.cache:
            await self.cache.delete(f"seg:meta:{segmentation_id}")

        logger.info(
            "Saved segmentation",
            extra={
                "segmentation_id": segmentation_id,
                "slices_annotated": slices_annotated,
                "progress": progress,
            }
        )

        return True

    def _count_annotated_slices(self, masks_3d: np.ndarray) -> int:
        """Count slices that have any non-zero labels."""
        count = 0
        for i in range(masks_3d.shape[0]):
            if np.any(masks_3d[i] > 0):
                count += 1
        return count

    async def _save_masks_to_gcs(
        self,
        segmentation_id: str,
        masks_3d: np.ndarray,
        dirty_slices: set,
        gcs_path: str
    ):
        """Save dirty slices to GCS as compressed numpy arrays."""
        for slice_idx in dirty_slices:
            slice_data = masks_3d[slice_idx]

            # Compress using numpy's built-in compression
            buffer = io.BytesIO()
            np.savez_compressed(buffer, mask=slice_data)
            buffer.seek(0)

            # Upload to GCS
            blob_name = f"{gcs_path}/slices/slice_{slice_idx:04d}.npz"
            blob = self.gcs_bucket.blob(blob_name)
            blob.upload_from_file(buffer, content_type="application/octet-stream")

        logger.debug(
            "Saved slices to GCS",
            extra={"segmentation_id": segmentation_id, "slices": list(dirty_slices)}
        )

    async def _load_segmentation_masks(
        self,
        segmentation_id: str,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
        series_id: Optional[str] = None,
    ):
        """Load segmentation masks from GCS into memory cache."""
        # Get metadata first
        doc_data = await self._find_segmentation_doc(
            segmentation_id, patient_id, study_id, series_id
        )

        if not doc_data:
            return

        image_shape = doc_data.get("image_shape", [256, 256, 100])
        rows, columns, slices = image_shape
        gcs_path = doc_data.get("gcs_path")

        # Initialize empty mask
        masks_3d = np.zeros((slices, rows, columns), dtype=np.uint8)

        # Try to load from GCS
        if gcs_path:
            try:
                prefix = f"{gcs_path}/slices/"
                blobs = list(self.gcs_bucket.list_blobs(prefix=prefix))

                for blob in blobs:
                    if blob.name.endswith(".npz"):
                        # Extract slice index from filename
                        filename = blob.name.split("/")[-1]
                        slice_idx = int(filename.replace("slice_", "").replace(".npz", ""))

                        # Download and decompress
                        buffer = io.BytesIO()
                        blob.download_to_file(buffer)
                        buffer.seek(0)

                        data = np.load(buffer)
                        masks_3d[slice_idx] = data["mask"]

                logger.debug(
                    "Loaded masks from GCS",
                    extra={"segmentation_id": segmentation_id, "blobs": len(blobs)}
                )
            except Exception as e:
                logger.warning(
                    "Failed to load masks from GCS, using empty",
                    extra={"segmentation_id": segmentation_id, "error": str(e)}
                )

        # Add to memory cache
        self._add_to_memory_cache(segmentation_id, {
            "metadata": doc_data,
            "masks_3d": masks_3d,
            "image_shape": (rows, columns, slices),
            "dirty_slices": set(),
        })

    def _add_to_memory_cache(self, segmentation_id: str, data: Dict):
        """Add to memory cache with LRU eviction."""
        if segmentation_id in self._memory_cache:
            # Move to end (most recently used)
            self._memory_cache_order.remove(segmentation_id)
            self._memory_cache_order.append(segmentation_id)
        else:
            # Add new entry
            if len(self._memory_cache) >= self._max_memory_cache:
                # Evict oldest
                oldest = self._memory_cache_order.pop(0)
                del self._memory_cache[oldest]
                logger.debug(f"Evicted segmentation from cache: {oldest}")

            self._memory_cache_order.append(segmentation_id)

        self._memory_cache[segmentation_id] = data

    async def update_status(
        self,
        segmentation_id: str,
        update: SegmentationStatusUpdate,
        user_id: str,
        user_name: str,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
        series_id: Optional[str] = None,
    ) -> SegmentationResponse:
        """Update segmentation status."""
        doc_data = await self._find_segmentation_doc(
            segmentation_id, patient_id, study_id, series_id
        )

        if not doc_data:
            raise NotFoundException(
                message=f"Segmentation not found: {segmentation_id}",
                error_code="SEGMENTATION_NOT_FOUND"
            )

        patient_id = doc_data["patient_id"]
        study_id = doc_data["study_id"]
        series_id = doc_data["series_id"]

        # Prepare update
        update_data = {
            "status": update.status.value,
            "modified_at": datetime.utcnow(),
        }

        # Add review info if relevant status
        if update.status in [SegmentationStatus.REVIEWED, SegmentationStatus.APPROVED]:
            update_data["reviewed_by"] = user_id
            update_data["reviewed_by_name"] = user_name
            update_data["reviewed_at"] = datetime.utcnow()
            if update.notes:
                update_data["review_notes"] = update.notes

        # Update Firestore
        ref = self._get_segmentation_ref(patient_id, study_id, series_id, segmentation_id)
        ref.update(update_data)

        # Update memory cache if present
        if segmentation_id in self._memory_cache:
            self._memory_cache[segmentation_id]["metadata"].update(update_data)

        # Invalidate Redis cache
        if self.cache:
            await self.cache.delete(f"seg:meta:{segmentation_id}")

        logger.info(
            "Updated segmentation status",
            extra={
                "segmentation_id": segmentation_id,
                "new_status": update.status.value,
                "by": user_id,
            }
        )

        # Return updated data
        doc_data.update(update_data)
        return self._doc_to_response(doc_data)

    async def delete_segmentation(
        self,
        segmentation_id: str,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
        series_id: Optional[str] = None,
    ) -> bool:
        """Delete a segmentation."""
        doc_data = await self._find_segmentation_doc(
            segmentation_id, patient_id, study_id, series_id
        )

        if not doc_data:
            return False

        patient_id = doc_data["patient_id"]
        study_id = doc_data["study_id"]
        series_id = doc_data["series_id"]
        gcs_path = doc_data.get("gcs_path")

        # Delete from Firestore
        ref = self._get_segmentation_ref(patient_id, study_id, series_id, segmentation_id)
        ref.delete()

        # Delete from GCS
        if gcs_path:
            try:
                blobs = list(self.gcs_bucket.list_blobs(prefix=gcs_path))
                for blob in blobs:
                    blob.delete()
            except Exception as e:
                logger.warning(f"Failed to delete GCS blobs: {e}")

        # Remove from memory cache
        if segmentation_id in self._memory_cache:
            del self._memory_cache[segmentation_id]
            self._memory_cache_order.remove(segmentation_id)

        # Invalidate Redis cache
        if self.cache:
            await self.cache.delete(f"seg:meta:{segmentation_id}")

        # Update count
        await self._update_segmentation_count(patient_id, study_id, series_id, -1)

        logger.info(
            "Deleted segmentation",
            extra={"segmentation_id": segmentation_id}
        )

        return True

    async def _update_segmentation_count(
        self,
        patient_id: str,
        study_id: str,
        series_id: str,
        delta: int
    ):
        """Update segmentation count on series and study documents."""
        # Update series count
        series_ref = (
            self.db.collection("patients")
            .document(patient_id)
            .collection("studies")
            .document(study_id)
            .collection("series")
            .document(series_id)
        )
        series_ref.update({"segmentation_count": firestore.Increment(delta)})

        # Update study count
        study_ref = (
            self.db.collection("patients")
            .document(patient_id)
            .collection("studies")
            .document(study_id)
        )
        study_ref.update({"segmentation_count": firestore.Increment(delta)})

    async def get_statistics(
        self,
        segmentation_id: str,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
        series_id: Optional[str] = None,
    ) -> SegmentationStatistics:
        """Calculate statistics for a segmentation."""
        # Load masks if needed
        if segmentation_id not in self._memory_cache:
            await self._load_segmentation_masks(
                segmentation_id, patient_id, study_id, series_id
            )

        if segmentation_id not in self._memory_cache:
            raise NotFoundException(
                message=f"Segmentation not found: {segmentation_id}",
                error_code="SEGMENTATION_NOT_FOUND"
            )

        cache_entry = self._memory_cache[segmentation_id]
        masks_3d = cache_entry["masks_3d"]
        metadata = cache_entry["metadata"]
        labels = [LabelInfo(**l) for l in metadata["labels"]]

        total_voxels = masks_3d.size
        annotated_voxels = int(np.sum(masks_3d > 0))

        label_stats = []
        for label in labels:
            if label.id == 0:
                continue

            label_mask = (masks_3d == label.id)
            voxel_count = int(np.sum(label_mask))

            if voxel_count > 0:
                slices_present = sum(1 for i in range(masks_3d.shape[0]) if np.any(masks_3d[i] == label.id))
                percentage = (voxel_count / total_voxels) * 100

                label_stats.append(LabelStatistics(
                    label_id=label.id,
                    label_name=label.name,
                    voxel_count=voxel_count,
                    percentage=percentage,
                    slices_present=slices_present,
                ))

        return SegmentationStatistics(
            segmentation_id=uuid.UUID(segmentation_id),
            total_voxels=total_voxels,
            annotated_voxels=annotated_voxels,
            image_shape=list(masks_3d.shape),
            label_statistics=label_stats,
            computed_at=datetime.utcnow(),
        )

    def _doc_to_response(self, doc: Dict) -> SegmentationResponse:
        """Convert Firestore document to SegmentationResponse."""
        return SegmentationResponse(
            id=uuid.UUID(doc["id"]),
            patient_id=uuid.UUID(doc["patient_id"]),
            study_id=uuid.UUID(doc["study_id"]),
            series_id=uuid.UUID(doc["series_id"]),
            file_id=doc.get("file_id"),
            name=doc["name"],
            description=doc.get("description"),
            segmentation_type=SegmentationType(doc["segmentation_type"]),
            status=SegmentationStatus(doc["status"]),
            progress_percentage=doc.get("progress_percentage", 0),
            slices_annotated=doc.get("slices_annotated", 0),
            total_slices=doc.get("total_slices", 0),
            created_by=doc["created_by"],
            created_by_name=doc.get("created_by_name"),
            reviewed_by=doc.get("reviewed_by"),
            reviewed_by_name=doc.get("reviewed_by_name"),
            reviewed_at=doc.get("reviewed_at"),
            review_notes=doc.get("review_notes"),
            labels=[LabelInfo(**l) for l in doc.get("labels", [])],
            gcs_path=doc.get("gcs_path"),
            created_at=doc["created_at"],
            modified_at=doc["modified_at"],
        )

    def _doc_to_summary(self, doc: Dict) -> SegmentationSummary:
        """Convert Firestore document to SegmentationSummary."""
        labels = doc.get("labels", [])
        label_count = len([l for l in labels if l.get("id", 0) != 0])

        return SegmentationSummary(
            id=uuid.UUID(doc["id"]),
            name=doc["name"],
            status=SegmentationStatus(doc["status"]),
            progress_percentage=doc.get("progress_percentage", 0),
            slices_annotated=doc.get("slices_annotated", 0),
            total_slices=doc.get("total_slices", 0),
            created_by=doc["created_by"],
            created_by_name=doc.get("created_by_name"),
            created_at=doc["created_at"],
            modified_at=doc["modified_at"],
            label_count=label_count,
            primary_label_color=doc.get("primary_label_color", "#FF0000"),
        )
