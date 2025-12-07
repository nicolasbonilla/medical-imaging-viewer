"""
Interface for segmentation service.

Defines the contract for medical image segmentation operations.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Tuple, Any
import numpy as np

from app.models.schemas import (
    CreateSegmentationRequest,
    SegmentationResponse,
    PaintStroke,
    LabelInfo
)


class ISegmentationService(ABC):
    """
    Abstract interface for segmentation operations.

    This interface defines all operations for creating, managing, and
    exporting medical image segmentations.
    """

    @abstractmethod
    def create_segmentation(
        self,
        file_id: str,
        image_shape: Tuple[int, int, int],
        labels: List[LabelInfo]
    ) -> SegmentationResponse:
        """
        Create a new segmentation for an image.

        Args:
            file_id: Associated image file ID
            image_shape: Shape of the image (height, width, depth)
            labels: List of segmentation labels

        Returns:
            SegmentationResponse with segmentation metadata

        Raises:
            SegmentationException: If creation fails
        """
        pass

    @abstractmethod
    def get_segmentation(self, segmentation_id: str) -> Optional[SegmentationResponse]:
        """
        Get a segmentation by ID.

        Args:
            segmentation_id: Segmentation ID

        Returns:
            SegmentationResponse or None if not found

        Raises:
            NotFoundException: If segmentation not found
        """
        pass

    @abstractmethod
    def list_segmentations(self, file_id: Optional[str] = None) -> List[SegmentationResponse]:
        """
        List all segmentations, optionally filtered by file ID.

        Args:
            file_id: Optional file ID to filter by

        Returns:
            List of SegmentationResponse objects

        Raises:
            SegmentationException: If listing fails
        """
        pass

    @abstractmethod
    async def apply_paint_stroke(
        self,
        segmentation_id: str,
        stroke: PaintStroke
    ) -> SegmentationResponse:
        """
        Apply a paint stroke to a segmentation.

        Args:
            segmentation_id: Segmentation ID
            stroke: Paint stroke data

        Returns:
            Updated SegmentationResponse

        Raises:
            NotFoundException: If segmentation not found
            ValidationException: If stroke parameters are invalid
            SegmentationException: If stroke application fails
        """
        pass

    @abstractmethod
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

        Raises:
            NotFoundException: If segmentation not found
            SegmentationException: If overlay generation fails
        """
        pass

    @abstractmethod
    def delete_segmentation(self, segmentation_id: str) -> bool:
        """
        Delete a segmentation.

        Args:
            segmentation_id: Segmentation ID

        Returns:
            True if deleted successfully

        Raises:
            NotFoundException: If segmentation not found
        """
        pass

    @abstractmethod
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

        Raises:
            NotFoundException: If segmentation not found
            SegmentationException: If export fails
        """
        pass

    @abstractmethod
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

        Raises:
            NotFoundException: If segmentation not found
            SegmentationException: If export fails
        """
        pass

    @abstractmethod
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

        Raises:
            NotFoundException: If segmentation not found
            SegmentationException: If calculation fails
        """
        pass
