"""
Interface for Hierarchical Segmentation Service.

Defines the contract for medical image segmentation operations with
multi-patient, multi-study, multi-expert support following ITK-SNAP
and DICOM SEG standards.

@module core.interfaces.segmentation_interface
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from uuid import UUID

from app.models.segmentation_schemas import (
    SegmentationCreate,
    SegmentationUpdate,
    SegmentationStatusUpdate,
    SegmentationResponse,
    SegmentationSummary,
    SegmentationListResponse,
    SegmentationStatistics,
    PaintStroke,
    PaintStrokeBatch,
    LabelInfo,
    LabelUpdate,
    OverlaySettings,
    ExportRequest,
    ExportResponse,
    SegmentationSearch,
    SegmentationComparisonRequest,
    SegmentationComparisonResponse,
)


class ISegmentationService(ABC):
    """
    Abstract interface for hierarchical segmentation operations.

    This interface defines all operations for creating, managing, and
    exporting medical image segmentations with support for:
    - Multi-patient, multi-study hierarchy
    - Multiple segmentations per series
    - Multi-expert workflow with review status
    - ITK-SNAP style labelmap segmentation
    - DICOM SEG export compatibility
    """

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    @abstractmethod
    async def create_segmentation(
        self,
        patient_id: UUID,
        study_id: UUID,
        series_id: UUID,
        data: SegmentationCreate,
        created_by: str,
        created_by_name: Optional[str] = None
    ) -> SegmentationResponse:
        """
        Create a new segmentation for a series.

        Args:
            patient_id: Patient UUID
            study_id: Study UUID
            series_id: Series UUID (must belong to study)
            data: Segmentation creation data
            created_by: Username of creator
            created_by_name: Full name of creator (optional)

        Returns:
            SegmentationResponse with full metadata

        Raises:
            NotFoundException: If series not found
            ValidationException: If data is invalid
            SegmentationException: If creation fails
        """
        pass

    @abstractmethod
    async def get_segmentation(
        self,
        segmentation_id: UUID
    ) -> Optional[SegmentationResponse]:
        """
        Get a segmentation by ID with full metadata.

        Args:
            segmentation_id: Segmentation UUID

        Returns:
            SegmentationResponse or None if not found
        """
        pass

    @abstractmethod
    async def update_segmentation(
        self,
        segmentation_id: UUID,
        data: SegmentationUpdate
    ) -> SegmentationResponse:
        """
        Update segmentation metadata.

        Args:
            segmentation_id: Segmentation UUID
            data: Update data (name, description)

        Returns:
            Updated SegmentationResponse

        Raises:
            NotFoundException: If segmentation not found
        """
        pass

    @abstractmethod
    async def delete_segmentation(
        self,
        segmentation_id: UUID
    ) -> bool:
        """
        Delete a segmentation and its mask data.

        Args:
            segmentation_id: Segmentation UUID

        Returns:
            True if deleted successfully

        Raises:
            NotFoundException: If segmentation not found
        """
        pass

    # =========================================================================
    # List Operations (Hierarchical)
    # =========================================================================

    @abstractmethod
    async def list_segmentations_by_series(
        self,
        patient_id: UUID,
        study_id: UUID,
        series_id: UUID,
        page: int = 1,
        page_size: int = 20
    ) -> SegmentationListResponse:
        """
        List all segmentations for a specific series.

        Args:
            patient_id: Patient UUID
            study_id: Study UUID
            series_id: Series UUID
            page: Page number (1-based)
            page_size: Items per page

        Returns:
            Paginated list of SegmentationSummary items
        """
        pass

    @abstractmethod
    async def list_segmentations_by_study(
        self,
        patient_id: UUID,
        study_id: UUID,
        page: int = 1,
        page_size: int = 20
    ) -> SegmentationListResponse:
        """
        List all segmentations across all series in a study.

        Args:
            patient_id: Patient UUID
            study_id: Study UUID
            page: Page number (1-based)
            page_size: Items per page

        Returns:
            Paginated list of SegmentationSummary items
        """
        pass

    @abstractmethod
    async def list_segmentations_by_patient(
        self,
        patient_id: UUID,
        page: int = 1,
        page_size: int = 20
    ) -> SegmentationListResponse:
        """
        List all segmentations across all studies for a patient.

        Args:
            patient_id: Patient UUID
            page: Page number (1-based)
            page_size: Items per page

        Returns:
            Paginated list of SegmentationSummary items
        """
        pass

    @abstractmethod
    async def search_segmentations(
        self,
        search: SegmentationSearch
    ) -> SegmentationListResponse:
        """
        Search segmentations with multiple filters.

        Args:
            search: Search parameters (patient, study, status, author, dates)

        Returns:
            Paginated list of matching SegmentationSummary items
        """
        pass

    @abstractmethod
    async def get_segmentation_count_by_series(
        self,
        series_id: UUID
    ) -> int:
        """
        Get count of segmentations for a series (for UI indicators).

        Args:
            series_id: Series UUID

        Returns:
            Number of segmentations
        """
        pass

    # =========================================================================
    # Status and Workflow
    # =========================================================================

    @abstractmethod
    async def update_status(
        self,
        segmentation_id: UUID,
        status_update: SegmentationStatusUpdate,
        updated_by: str,
        updated_by_name: Optional[str] = None
    ) -> SegmentationResponse:
        """
        Update segmentation status (workflow transition).

        Args:
            segmentation_id: Segmentation UUID
            status_update: New status and notes
            updated_by: Username making the change
            updated_by_name: Full name (optional)

        Returns:
            Updated SegmentationResponse

        Raises:
            NotFoundException: If segmentation not found
            ValidationException: If status transition is invalid
        """
        pass

    # =========================================================================
    # Label Management
    # =========================================================================

    @abstractmethod
    async def add_label(
        self,
        segmentation_id: UUID,
        label: LabelInfo
    ) -> SegmentationResponse:
        """
        Add a new label to the segmentation.

        Args:
            segmentation_id: Segmentation UUID
            label: Label definition

        Returns:
            Updated SegmentationResponse

        Raises:
            NotFoundException: If segmentation not found
            ValidationException: If label ID already exists
        """
        pass

    @abstractmethod
    async def update_label(
        self,
        segmentation_id: UUID,
        label_id: int,
        update: LabelUpdate
    ) -> SegmentationResponse:
        """
        Update an existing label.

        Args:
            segmentation_id: Segmentation UUID
            label_id: Label ID (0-255)
            update: Label update data

        Returns:
            Updated SegmentationResponse

        Raises:
            NotFoundException: If segmentation or label not found
        """
        pass

    @abstractmethod
    async def remove_label(
        self,
        segmentation_id: UUID,
        label_id: int
    ) -> SegmentationResponse:
        """
        Remove a label (sets all voxels with this label to 0).

        Args:
            segmentation_id: Segmentation UUID
            label_id: Label ID to remove

        Returns:
            Updated SegmentationResponse

        Raises:
            NotFoundException: If segmentation or label not found
            ValidationException: If trying to remove background (label 0)
        """
        pass

    # =========================================================================
    # Paint Operations
    # =========================================================================

    @abstractmethod
    async def apply_paint_stroke(
        self,
        segmentation_id: UUID,
        stroke: PaintStroke,
        user: str
    ) -> Dict[str, Any]:
        """
        Apply a single paint stroke to the segmentation mask.

        Args:
            segmentation_id: Segmentation UUID
            stroke: Paint stroke data (slice, position, brush, label)
            user: Username applying the stroke

        Returns:
            Dict with updated slice info and modified voxel count

        Raises:
            NotFoundException: If segmentation not found
            ValidationException: If stroke parameters are invalid
        """
        pass

    @abstractmethod
    async def apply_paint_batch(
        self,
        segmentation_id: UUID,
        batch: PaintStrokeBatch,
        user: str
    ) -> Dict[str, Any]:
        """
        Apply multiple paint strokes efficiently.

        Args:
            segmentation_id: Segmentation UUID
            batch: Batch of paint strokes
            user: Username applying the strokes

        Returns:
            Dict with updated info and total modified voxel count

        Raises:
            NotFoundException: If segmentation not found
        """
        pass

    @abstractmethod
    async def save_segmentation(
        self,
        segmentation_id: UUID
    ) -> SegmentationResponse:
        """
        Persist segmentation mask to storage.

        Args:
            segmentation_id: Segmentation UUID

        Returns:
            Updated SegmentationResponse with storage info

        Raises:
            NotFoundException: If segmentation not found
            StorageException: If save fails
        """
        pass

    # =========================================================================
    # Overlay Generation
    # =========================================================================

    @abstractmethod
    async def get_slice_overlay(
        self,
        segmentation_id: UUID,
        slice_index: int,
        settings: Optional[OverlaySettings] = None
    ) -> bytes:
        """
        Generate overlay image for a specific slice.

        Args:
            segmentation_id: Segmentation UUID
            slice_index: Slice index (0-based)
            settings: Overlay rendering settings

        Returns:
            PNG image bytes with RGBA overlay

        Raises:
            NotFoundException: If segmentation not found
            ValidationException: If slice index out of range
        """
        pass

    @abstractmethod
    async def get_slice_mask(
        self,
        segmentation_id: UUID,
        slice_index: int
    ) -> bytes:
        """
        Get raw mask data for a slice (for frontend canvas operations).

        Args:
            segmentation_id: Segmentation UUID
            slice_index: Slice index (0-based)

        Returns:
            Raw mask bytes (uint8 labelmap)

        Raises:
            NotFoundException: If segmentation not found
        """
        pass

    # =========================================================================
    # Statistics and Analysis
    # =========================================================================

    @abstractmethod
    async def get_statistics(
        self,
        segmentation_id: UUID
    ) -> SegmentationStatistics:
        """
        Calculate comprehensive statistics for segmentation.

        Args:
            segmentation_id: Segmentation UUID

        Returns:
            SegmentationStatistics with voxel counts, volumes, etc.

        Raises:
            NotFoundException: If segmentation not found
        """
        pass

    @abstractmethod
    async def compare_segmentations(
        self,
        request: SegmentationComparisonRequest
    ) -> SegmentationComparisonResponse:
        """
        Compare multiple segmentations (inter-rater agreement).

        Args:
            request: Comparison request with segmentation IDs and metrics

        Returns:
            SegmentationComparisonResponse with pairwise metrics

        Raises:
            NotFoundException: If any segmentation not found
            ValidationException: If segmentations are not comparable
        """
        pass

    # =========================================================================
    # Export Operations
    # =========================================================================

    @abstractmethod
    async def export_segmentation(
        self,
        segmentation_id: UUID,
        request: ExportRequest
    ) -> ExportResponse:
        """
        Export segmentation to specified format.

        Args:
            segmentation_id: Segmentation UUID
            request: Export parameters (format, compression, etc.)

        Returns:
            ExportResponse with download URL

        Raises:
            NotFoundException: If segmentation not found
            ExportException: If export fails
        """
        pass

    # =========================================================================
    # Cache Management
    # =========================================================================

    @abstractmethod
    async def load_into_memory(
        self,
        segmentation_id: UUID
    ) -> bool:
        """
        Load segmentation mask into memory cache for editing.

        Args:
            segmentation_id: Segmentation UUID

        Returns:
            True if loaded successfully

        Raises:
            NotFoundException: If segmentation not found
        """
        pass

    @abstractmethod
    async def unload_from_memory(
        self,
        segmentation_id: UUID
    ) -> bool:
        """
        Unload segmentation from memory cache (auto-save first).

        Args:
            segmentation_id: Segmentation UUID

        Returns:
            True if unloaded successfully
        """
        pass
