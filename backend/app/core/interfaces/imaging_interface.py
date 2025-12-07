"""
Interface for medical imaging service.

Defines the contract for medical image processing operations.
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple
import numpy as np

from app.models.schemas import (
    ImageFormat,
    ImageMetadata,
    ImageSeriesResponse,
    ImageSlice,
    ImageOrientation
)


class IImagingService(ABC):
    """
    Abstract interface for medical imaging operations.

    This interface defines all operations for processing medical images
    (DICOM, NIfTI, etc.). Implementations can use actual image processing
    libraries or mock data for testing.
    """

    @abstractmethod
    def detect_format(self, file_data: bytes, filename: str) -> ImageFormat:
        """
        Detect the format of a medical image file.

        Args:
            file_data: Raw file bytes
            filename: Original filename

        Returns:
            ImageFormat: Detected format (DICOM or NIFTI)

        Raises:
            ValidationException: If format is unsupported
        """
        pass

    @abstractmethod
    def load_dicom(self, file_data: bytes) -> Tuple[np.ndarray, ImageMetadata]:
        """
        Load a DICOM file and extract metadata.

        Args:
            file_data: Raw DICOM file bytes

        Returns:
            Tuple of (pixel_array, metadata)

        Raises:
            ImageProcessingException: If loading fails
        """
        pass

    @abstractmethod
    def load_nifti(self, file_data: bytes) -> Tuple[np.ndarray, ImageMetadata]:
        """
        Load a NIfTI file and extract metadata.

        Args:
            file_data: Raw NIfTI file bytes

        Returns:
            Tuple of (pixel_array, metadata)

        Raises:
            ImageProcessingException: If loading fails
        """
        pass

    @abstractmethod
    async def process_image(
        self,
        file_data: bytes,
        filename: str,
        slice_range: Optional[Tuple[int, int]] = None
    ) -> ImageSeriesResponse:
        """
        Process a medical image file.

        Args:
            file_data: Raw file bytes
            filename: Original filename
            slice_range: Optional tuple of (start_slice, end_slice)

        Returns:
            ImageSeriesResponse with metadata and slices

        Raises:
            ImageProcessingException: If processing fails
            ValidationException: If format is unsupported
        """
        pass

    @abstractmethod
    def apply_window_level(
        self,
        pixel_array: np.ndarray,
        window_center: float,
        window_width: float
    ) -> np.ndarray:
        """
        Apply window/level adjustment to pixel array.

        Args:
            pixel_array: Image pixel data
            window_center: Window center value
            window_width: Window width value

        Returns:
            Windowed pixel array

        Raises:
            ImageProcessingException: If windowing fails
        """
        pass

    @abstractmethod
    def get_slice_2d(
        self,
        file_data: bytes,
        filename: str,
        slice_index: int,
        orientation: ImageOrientation = ImageOrientation.AXIAL,
        window_center: Optional[float] = None,
        window_width: Optional[float] = None
    ) -> ImageSlice:
        """
        Get a single 2D slice from a medical image.

        Args:
            file_data: Raw file bytes
            filename: Original filename
            slice_index: Index of slice to extract
            orientation: Slice orientation (axial, sagittal, coronal)
            window_center: Optional window center
            window_width: Optional window width

        Returns:
            ImageSlice with base64-encoded image data

        Raises:
            ImageProcessingException: If extraction fails
            ValidationException: If parameters are invalid
        """
        pass

    @abstractmethod
    def visualize_with_matplotlib_2d(
        self,
        file_data: bytes,
        filename: str,
        slice_index: int,
        x_min: Optional[int] = None,
        x_max: Optional[int] = None,
        y_min: Optional[int] = None,
        y_max: Optional[int] = None,
        colormap: str = 'gray',
        minimal: bool = False,
        segmentation_data: Optional[bytes] = None,
        segmentation_id: Optional[str] = None,
        window_center: Optional[float] = None,
        window_width: Optional[float] = None
    ) -> bytes:
        """
        Generate a matplotlib visualization of a 2D slice.

        Args:
            file_data: Raw file bytes
            filename: Original filename
            slice_index: Slice to visualize
            x_min, x_max, y_min, y_max: Optional crop bounds
            colormap: Matplotlib colormap name
            minimal: If True, remove axes and labels
            segmentation_data: Optional segmentation overlay
            segmentation_id: Optional segmentation ID
            window_center: Optional window center
            window_width: Optional window width

        Returns:
            PNG image bytes

        Raises:
            ImageProcessingException: If visualization fails
        """
        pass
