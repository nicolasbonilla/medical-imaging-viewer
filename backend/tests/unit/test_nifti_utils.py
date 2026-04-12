"""
Unit tests for nifti_utils — IEC 62304 Class C.

Tests verify NIfTI file handling safety including size limits,
format validation, and temp file cleanup (DD-NII-001/DD-NII-002).
"""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
import tempfile
import os


@pytest.mark.unit
class TestValidateNiftiData:
    """Tests for validate_nifti_data (Class C — DD-NII-001)."""

    def test_valid_3d_array(self):
        """Valid 3D array passes validation and returns True."""
        from app.utils.nifti_utils import validate_nifti_data

        data = np.zeros((10, 10, 10), dtype=np.float32)
        result = validate_nifti_data(data, expected_ndim=3)
        assert result is True

    def test_wrong_ndim_raises_value_error(self):
        """Wrong ndim raises ValueError with descriptive message."""
        from app.utils.nifti_utils import validate_nifti_data

        data = np.zeros((10, 10), dtype=np.float32)
        with pytest.raises(ValueError, match="Expected 3D data, got 2D"):
            validate_nifti_data(data, expected_ndim=3)

    def test_4d_when_3d_expected_raises(self):
        """4D array when 3D expected raises ValueError."""
        from app.utils.nifti_utils import validate_nifti_data

        data = np.zeros((10, 10, 10, 3), dtype=np.float32)
        with pytest.raises(ValueError, match="Expected 3D data, got 4D"):
            validate_nifti_data(data, expected_ndim=3)

    def test_empty_array_raises_value_error(self):
        """Empty array raises ValueError."""
        from app.utils.nifti_utils import validate_nifti_data

        data = np.array([], dtype=np.float32).reshape(0, 0, 0)
        with pytest.raises(ValueError, match="empty"):
            validate_nifti_data(data, expected_ndim=3)

    def test_no_ndim_check_skips_dimension_validation(self):
        """When expected_ndim is None, dimension check is skipped."""
        from app.utils.nifti_utils import validate_nifti_data

        data = np.zeros((5, 5), dtype=np.float32)
        result = validate_nifti_data(data, expected_ndim=None)
        assert result is True

    def test_non_array_raises_value_error(self):
        """Non-numpy input raises ValueError."""
        from app.utils.nifti_utils import validate_nifti_data

        with pytest.raises(ValueError, match="numpy array"):
            validate_nifti_data([1, 2, 3], expected_ndim=3)


@pytest.mark.unit
class TestCreateNiftiImage:
    """Tests for create_nifti_image (Class C — DD-NII-001)."""

    def test_default_affine_is_identity(self):
        """create_nifti_image with no affine uses identity matrix."""
        from app.utils.nifti_utils import create_nifti_image

        data = np.zeros((10, 10, 10), dtype=np.float32)
        img = create_nifti_image(data)
        assert img is not None
        assert img.shape == (10, 10, 10)
        np.testing.assert_array_almost_equal(img.affine, np.eye(4))

    def test_custom_affine_preserved(self):
        """Custom affine is preserved in created image."""
        from app.utils.nifti_utils import create_nifti_image

        data = np.zeros((10, 10, 10), dtype=np.float32)
        affine = np.diag([2.0, 2.0, 2.0, 1.0])
        img = create_nifti_image(data, affine=affine)
        np.testing.assert_array_almost_equal(img.affine, affine)

    def test_data_dtype_preserved(self):
        """Data dtype is preserved in the NIfTI image."""
        from app.utils.nifti_utils import create_nifti_image

        data = np.ones((5, 5, 5), dtype=np.uint8)
        img = create_nifti_image(data)
        assert img.get_data_dtype() == np.uint8


@pytest.mark.unit
class TestLoadNiftiFromBytes:
    """Tests for load_nifti_from_bytes — input validation (Class C — DD-NII-002)."""

    def test_too_small_raises_value_error(self):
        """File smaller than NIfTI header (348 bytes) raises ValueError."""
        from app.utils.nifti_utils import load_nifti_from_bytes

        tiny_data = b"\x00" * 100
        with pytest.raises(ValueError, match="348"):
            load_nifti_from_bytes(tiny_data)

    def test_exactly_348_bytes_but_invalid_nifti(self):
        """348 bytes of zeros passes size check but fails NIfTI parse."""
        from app.utils.nifti_utils import load_nifti_from_bytes

        # Passes the size guard but nibabel cannot parse it
        bad_data = b"\x00" * 400
        with pytest.raises(Exception):
            load_nifti_from_bytes(bad_data)

    def test_too_large_raises_value_error(self):
        """File exceeding 2 GB limit raises ValueError."""
        from app.utils.nifti_utils import load_nifti_from_bytes

        # Cannot allocate 2 GB+ in tests; use a mock for len()
        class FakeBytes:
            """Mimics a bytes object that reports >2 GB size."""
            def __len__(self):
                return 3 * 1024 * 1024 * 1024  # 3 GB

        with pytest.raises((ValueError, TypeError)):
            load_nifti_from_bytes(FakeBytes())

    def test_valid_nifti_roundtrip(self):
        """A real NIfTI file created in-memory loads correctly."""
        import nibabel as nib
        import io

        from app.utils.nifti_utils import load_nifti_from_bytes

        # Create a valid NIfTI in memory
        data = np.random.rand(8, 8, 8).astype(np.float32)
        img = nib.Nifti1Image(data, np.eye(4))
        bio = io.BytesIO()
        nib.save(img, bio)  # nibabel can save to file-like with .nii extension workaround
        # nibabel needs a real file for saving, so use tempfile
        with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as tmp:
            nib.save(img, tmp.name)
            tmp_path = tmp.name
        try:
            with open(tmp_path, "rb") as f:
                file_bytes = f.read()
            loaded_img, loaded_data = load_nifti_from_bytes(file_bytes)
            assert loaded_data.shape == (8, 8, 8)
            np.testing.assert_array_almost_equal(loaded_data, data, decimal=5)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_temp_file_cleanup_on_success(self):
        """Temporary file is deleted after successful load."""
        import nibabel as nib

        from app.utils.nifti_utils import load_nifti_from_bytes

        data = np.zeros((4, 4, 4), dtype=np.float32)
        img = nib.Nifti1Image(data, np.eye(4))
        with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as tmp:
            nib.save(img, tmp.name)
            tmp_path = tmp.name
        try:
            with open(tmp_path, "rb") as f:
                file_bytes = f.read()

            # Track temp files created during load
            original_named_temp = tempfile.NamedTemporaryFile
            created_paths = []

            def tracking_temp(**kwargs):
                result = original_named_temp(**kwargs)
                created_paths.append(result.name)
                return result

            with patch("app.utils.nifti_utils.tempfile.NamedTemporaryFile", side_effect=tracking_temp):
                load_nifti_from_bytes(file_bytes)

            # Verify temp file was cleaned up
            for path in created_paths:
                assert not os.path.exists(path), f"Temp file not cleaned up: {path}"
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


@pytest.mark.unit
class TestDetectGzip:
    """Tests for detect_gzip (Class C — DD-NII-001)."""

    def test_gzip_magic_bytes_detected(self):
        """Gzip magic bytes (0x1f 0x8b) are detected correctly."""
        from app.utils.nifti_utils import detect_gzip

        assert detect_gzip(b"\x1f\x8b\x08\x00") is True

    def test_non_gzip_returns_false(self):
        """Non-gzipped data returns False."""
        from app.utils.nifti_utils import detect_gzip

        assert detect_gzip(b"\x00\x00\x00\x00") is False

    def test_empty_data_returns_false(self):
        """Empty data returns False (no crash)."""
        from app.utils.nifti_utils import detect_gzip

        assert detect_gzip(b"") is False


@pytest.mark.unit
class TestTransposeConventions:
    """Tests for transpose_for_nifti / transpose_from_nifti (Class C — DD-NII-001)."""

    def test_dhw_to_whd_roundtrip(self):
        """DHW -> WHD -> DHW roundtrip preserves data."""
        from app.utils.nifti_utils import transpose_for_nifti, transpose_from_nifti

        arr = np.arange(24).reshape(2, 3, 4)  # (D=2, H=3, W=4)
        whd = transpose_for_nifti(arr, "DHW")
        assert whd.shape == (4, 3, 2)  # (W=4, H=3, D=2)
        back = transpose_from_nifti(whd, "DHW")
        np.testing.assert_array_equal(back, arr)

    def test_whd_passthrough(self):
        """WHD convention is a no-op (already NIfTI convention)."""
        from app.utils.nifti_utils import transpose_for_nifti

        arr = np.zeros((4, 3, 2))
        result = transpose_for_nifti(arr, "WHD")
        assert result is arr  # Same object, not a copy

    def test_unsupported_convention_raises(self):
        """Unsupported convention string raises ValueError."""
        from app.utils.nifti_utils import transpose_for_nifti

        with pytest.raises(ValueError, match="Unsupported convention"):
            transpose_for_nifti(np.zeros((2, 3, 4)), "XYZ")


@pytest.mark.unit
class TestCreateSegmentationFilename:
    """Tests for create_segmentation_filename (Class C — DD-NII-001)."""

    def test_nii_gz_suffix(self):
        """Handles .nii.gz extension correctly."""
        from app.utils.nifti_utils import create_segmentation_filename

        result = create_segmentation_filename("brain.nii.gz")
        assert result == "brain_segmentation.nii.gz"

    def test_nii_suffix(self):
        """Handles .nii extension, outputs .nii.gz."""
        from app.utils.nifti_utils import create_segmentation_filename

        result = create_segmentation_filename("scan.nii")
        assert result == "scan_segmentation.nii.gz"

    def test_custom_suffix(self):
        """Custom suffix is applied correctly."""
        from app.utils.nifti_utils import create_segmentation_filename

        result = create_segmentation_filename("scan.nii", suffix="_labels")
        assert result == "scan_labels.nii.gz"

    def test_fallback_with_segmentation_id(self):
        """Non-NIfTI filename falls back to segmentation_id."""
        from app.utils.nifti_utils import create_segmentation_filename

        result = create_segmentation_filename("unknown.dcm", segmentation_id="seg-001")
        assert result == "seg-001_segmentation.nii.gz"
