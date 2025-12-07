"""
Unit tests for ImagingService.
"""

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from app.services.imaging_service import ImagingService
from app.core.exceptions import ImageProcessingException


@pytest.mark.unit
class TestImagingService:
    """Test suite for imaging service."""

    @pytest.fixture
    def mock_cache(self):
        """Create mock cache service."""
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def imaging_service(self, mock_cache):
        """Create imaging service with mocked cache."""
        return ImagingService(cache_service=mock_cache)

    @pytest.fixture
    def sample_dicom_data(self):
        """Create sample DICOM-like data."""
        # Simple 10x10x5 volume
        return np.random.randint(0, 255, size=(5, 10, 10), dtype=np.uint16)

    def test_generate_file_hash(self, imaging_service):
        """Test file hash generation."""
        # Arrange
        file_data = b"test data"

        # Act
        hash1 = imaging_service._generate_file_hash(file_data)
        hash2 = imaging_service._generate_file_hash(file_data)

        # Assert
        assert hash1 == hash2  # Same data should produce same hash
        assert len(hash1) == 32  # MD5 hash is 32 characters

    def test_file_hash_uniqueness(self, imaging_service):
        """Test that different data produces different hashes."""
        # Arrange
        file_data1 = b"test data 1"
        file_data2 = b"test data 2"

        # Act
        hash1 = imaging_service._generate_file_hash(file_data1)
        hash2 = imaging_service._generate_file_hash(file_data2)

        # Assert
        assert hash1 != hash2

    def test_normalize_slice_to_uint8(self, imaging_service):
        """Test slice normalization to uint8."""
        # Arrange
        slice_data = np.array([[0, 1000, 2000, 3000, 4000]], dtype=np.uint16)

        # Act
        result = imaging_service._normalize_slice_to_uint8(slice_data)

        # Assert
        assert result.dtype == np.uint8
        assert result.min() == 0
        assert result.max() == 255

    def test_normalize_slice_handles_zero_range(self, imaging_service):
        """Test normalization with constant values."""
        # Arrange
        slice_data = np.ones((5, 5), dtype=np.uint16) * 100

        # Act
        result = imaging_service._normalize_slice_to_uint8(slice_data)

        # Assert
        assert result.dtype == np.uint8
        # All values should be the same
        assert np.all(result == result[0, 0])

    def test_apply_window_level(self, imaging_service):
        """Test window/level adjustment."""
        # Arrange
        slice_data = np.array([[0, 50, 100, 150, 200, 250]], dtype=np.uint16)
        window_center = 100
        window_width = 100

        # Act
        result = imaging_service._apply_window_level(slice_data, window_center, window_width)

        # Assert
        assert result.dtype == np.uint8
        # Values below (center - width/2) should be 0
        # Values above (center + width/2) should be 255
        assert result[0, 0] == 0  # 0 < 50 (lower bound)
        assert result[0, -1] == 255  # 250 > 150 (upper bound)

    def test_apply_window_level_edge_cases(self, imaging_service):
        """Test window/level with extreme values."""
        # Arrange
        slice_data = np.array([[0, 500, 1000]], dtype=np.uint16)
        window_center = 500
        window_width = 1000

        # Act
        result = imaging_service._apply_window_level(slice_data, window_center, window_width)

        # Assert
        assert result.dtype == np.uint8
        assert result.shape == slice_data.shape

    def test_slice_to_base64(self, imaging_service):
        """Test conversion of slice to base64."""
        # Arrange
        slice_data = np.random.randint(0, 255, size=(100, 100), dtype=np.uint8)

        # Act
        result = imaging_service._slice_to_base64(slice_data)

        # Assert
        assert isinstance(result, str)
        assert len(result) > 0
        # Base64 string should not contain newlines
        assert '\n' not in result

    def test_slice_to_base64_different_sizes(self, imaging_service):
        """Test base64 conversion with different slice sizes."""
        # Arrange
        small_slice = np.random.randint(0, 255, size=(50, 50), dtype=np.uint8)
        large_slice = np.random.randint(0, 255, size=(512, 512), dtype=np.uint8)

        # Act
        result_small = imaging_service._slice_to_base64(small_slice)
        result_large = imaging_service._slice_to_base64(large_slice)

        # Assert
        assert len(result_large) > len(result_small)

    @pytest.mark.asyncio
    async def test_process_image_with_cache_hit(self, imaging_service, mock_cache):
        """Test process_image when data is in cache."""
        # Arrange
        file_data = b"fake dicom data"
        filename = "test.dcm"
        cached_response = {
            "id": "test_id",
            "name": "test.dcm",
            "format": "dicom",
            "metadata": {},
            "total_slices": 5,
            "slices": [],
        }
        mock_cache.get.return_value = cached_response

        # Act
        result = await imaging_service.process_image(file_data, filename)

        # Assert
        assert result.name == "test.dcm"
        assert result.total_slices == 5
        mock_cache.get.assert_called_once()
        mock_cache.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_image_invalid_format(self, imaging_service):
        """Test process_image with unsupported format."""
        # Arrange
        file_data = b"not a valid image"
        filename = "test.txt"

        # Act & Assert
        with pytest.raises(ImageProcessingException) as exc_info:
            await imaging_service.process_image(file_data, filename)

        assert "Unsupported file format" in str(exc_info.value)

    def test_detect_format_dicom(self, imaging_service):
        """Test format detection for DICOM files."""
        # Arrange
        filename_dcm = "test.dcm"
        filename_dicom = "test.DICOM"

        # Act
        format_dcm = imaging_service._detect_format(filename_dcm)
        format_dicom = imaging_service._detect_format(filename_dicom)

        # Assert
        assert format_dcm == "dicom"
        assert format_dicom == "dicom"

    def test_detect_format_nifti(self, imaging_service):
        """Test format detection for NIfTI files."""
        # Arrange
        filename_nii = "test.nii"
        filename_nii_gz = "test.nii.gz"

        # Act
        format_nii = imaging_service._detect_format(filename_nii)
        format_nii_gz = imaging_service._detect_format(filename_nii_gz)

        # Assert
        assert format_nii == "nifti"
        assert format_nii_gz == "nifti"

    def test_detect_format_unsupported(self, imaging_service):
        """Test format detection for unsupported files."""
        # Arrange
        filename = "test.txt"

        # Act & Assert
        with pytest.raises(ImageProcessingException) as exc_info:
            imaging_service._detect_format(filename)

        assert "Unsupported file format" in str(exc_info.value)

    def test_compute_slice_range(self, imaging_service):
        """Test slice range computation."""
        # Arrange
        total_slices = 100
        slice_range_request = (10, 20)

        # Act
        start, end = imaging_service._compute_slice_range(total_slices, slice_range_request)

        # Assert
        assert start == 10
        assert end == 20

    def test_compute_slice_range_full(self, imaging_service):
        """Test slice range with no request (full range)."""
        # Arrange
        total_slices = 100

        # Act
        start, end = imaging_service._compute_slice_range(total_slices, None)

        # Assert
        assert start == 0
        assert end == 100

    def test_compute_slice_range_clamp(self, imaging_service):
        """Test slice range clamping to valid bounds."""
        # Arrange
        total_slices = 100
        slice_range_request = (-10, 150)  # Out of bounds

        # Act
        start, end = imaging_service._compute_slice_range(total_slices, slice_range_request)

        # Assert
        assert start == 0  # Clamped to 0
        assert end == 100  # Clamped to total_slices

    def test_compute_slice_range_invalid(self, imaging_service):
        """Test slice range with invalid values."""
        # Arrange
        total_slices = 100
        slice_range_request = (50, 30)  # End before start

        # Act
        start, end = imaging_service._compute_slice_range(total_slices, slice_range_request)

        # Assert
        # Should swap or handle gracefully
        assert start <= end
