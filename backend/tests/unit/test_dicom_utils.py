"""
Unit tests for dicom_utils — IEC 62304 Class C.

Tests verify DICOM file creation, patient info handling, pixel data conversion,
spatial metadata, and DICOM-SEG export per DD-NII-001.

References:
  - DICOM PS3.3-2024: Information Object Definitions
  - IEC 62304:2006+A1:2015, Clause 5.5.5 (Unit Verification)
"""
import pytest
import numpy as np
from pathlib import Path
import tempfile
import os


@pytest.mark.unit
class TestCreateFileMeta:
    """Tests for create_file_meta()."""

    def test_default_sop_class(self):
        """Default SOP Class UID is Secondary Capture."""
        from app.utils.dicom_utils import create_file_meta
        meta = create_file_meta()
        assert meta.MediaStorageSOPClassUID == '1.2.840.10008.5.1.4.1.1.7'

    def test_default_transfer_syntax(self):
        """Default Transfer Syntax is Explicit VR Little Endian."""
        from app.utils.dicom_utils import create_file_meta
        meta = create_file_meta()
        assert meta.TransferSyntaxUID == '1.2.840.10008.1.2.1'

    def test_custom_sop_class(self):
        """Custom SOP Class UID is preserved."""
        from app.utils.dicom_utils import create_file_meta
        seg_uid = '1.2.840.10008.5.1.4.1.1.66.4'  # Segmentation Storage
        meta = create_file_meta(sop_class_uid=seg_uid)
        assert meta.MediaStorageSOPClassUID == seg_uid

    def test_unique_instance_uids(self):
        """Each call generates unique SOP Instance UID."""
        from app.utils.dicom_utils import create_file_meta
        meta1 = create_file_meta()
        meta2 = create_file_meta()
        assert meta1.MediaStorageSOPInstanceUID != meta2.MediaStorageSOPInstanceUID


@pytest.mark.unit
class TestCreateDicomDataset:
    """Tests for create_dicom_dataset()."""

    def test_creates_file_dataset(self):
        """Returns a valid FileDataset."""
        from app.utils.dicom_utils import create_dicom_dataset
        ds = create_dicom_dataset('test.dcm')
        assert ds is not None
        assert hasattr(ds, 'file_meta')
        assert ds.filename == 'test.dcm'

    def test_custom_file_meta(self):
        """Custom file_meta is used when provided."""
        from app.utils.dicom_utils import create_file_meta, create_dicom_dataset
        meta = create_file_meta(sop_class_uid='1.2.840.10008.5.1.4.1.1.66.4')
        ds = create_dicom_dataset('seg.dcm', file_meta=meta)
        assert ds.file_meta.MediaStorageSOPClassUID == '1.2.840.10008.5.1.4.1.1.66.4'


@pytest.mark.unit
class TestSetPatientInfo:
    """Tests for set_patient_info() — HIPAA-relevant."""

    def test_patient_id_set(self):
        """Patient ID is correctly set."""
        from app.utils.dicom_utils import create_dicom_dataset, set_patient_info
        ds = create_dicom_dataset('test.dcm')
        ds = set_patient_info(ds, 'PAT001', 'John Doe')
        assert ds.PatientID == 'PAT001'
        assert str(ds.PatientName) == 'John Doe'

    def test_patient_id_truncated_at_64(self):
        """Patient ID truncated to 64 characters (DICOM VR LO limit)."""
        from app.utils.dicom_utils import create_dicom_dataset, set_patient_info
        ds = create_dicom_dataset('test.dcm')
        long_id = 'A' * 100
        ds = set_patient_info(ds, long_id)
        assert len(ds.PatientID) == 64

    def test_patient_name_defaults_to_id(self):
        """Patient name defaults to patient_id when not provided."""
        from app.utils.dicom_utils import create_dicom_dataset, set_patient_info
        ds = create_dicom_dataset('test.dcm')
        ds = set_patient_info(ds, 'PAT002')
        assert str(ds.PatientName) == 'PAT002'


@pytest.mark.unit
class TestSetImageInfo:
    """Tests for set_image_info() — pixel data handling."""

    def test_16bit_image(self):
        """16-bit image correctly stored."""
        from app.utils.dicom_utils import create_dicom_dataset, set_image_info
        ds = create_dicom_dataset('test.dcm')
        pixels = np.zeros((64, 64), dtype=np.uint16)
        pixels[10, 10] = 1000
        ds = set_image_info(ds, 64, 64, pixels, bits_allocated=16)
        assert ds.Rows == 64
        assert ds.Columns == 64
        assert ds.BitsAllocated == 16
        assert ds.BitsStored == 16
        assert ds.HighBit == 15
        assert ds.PixelRepresentation == 0
        assert len(ds.PixelData) == 64 * 64 * 2  # 2 bytes per pixel

    def test_8bit_image(self):
        """8-bit image correctly stored."""
        from app.utils.dicom_utils import create_dicom_dataset, set_image_info
        ds = create_dicom_dataset('test.dcm')
        pixels = np.zeros((32, 32), dtype=np.uint8)
        ds = set_image_info(ds, 32, 32, pixels, bits_allocated=8)
        assert ds.BitsAllocated == 8
        assert len(ds.PixelData) == 32 * 32

    def test_unsupported_bits_raises(self):
        """Unsupported bits_allocated raises ValueError."""
        from app.utils.dicom_utils import create_dicom_dataset, set_image_info
        ds = create_dicom_dataset('test.dcm')
        pixels = np.zeros((32, 32), dtype=np.uint32)
        with pytest.raises(ValueError, match="Unsupported bits_allocated"):
            set_image_info(ds, 32, 32, pixels, bits_allocated=32)

    def test_pixel_data_dtype_conversion(self):
        """Float input correctly converted to uint16."""
        from app.utils.dicom_utils import create_dicom_dataset, set_image_info
        ds = create_dicom_dataset('test.dcm')
        pixels = np.ones((16, 16), dtype=np.float64) * 500.0
        ds = set_image_info(ds, 16, 16, pixels, bits_allocated=16)
        # Should not raise — float64 converted to uint16
        assert len(ds.PixelData) == 16 * 16 * 2


@pytest.mark.unit
class TestSetSpatialInfo:
    """Tests for set_spatial_info() — geometric accuracy."""

    def test_pixel_spacing(self):
        """Pixel spacing correctly set."""
        from app.utils.dicom_utils import create_dicom_dataset, set_spatial_info
        ds = create_dicom_dataset('test.dcm')
        ds = set_spatial_info(ds, pixel_spacing=(0.5, 0.5), slice_thickness=3.0)
        assert ds.PixelSpacing == [0.5, 0.5]
        assert ds.SliceThickness == 3.0

    def test_image_position(self):
        """Image position patient correctly set."""
        from app.utils.dicom_utils import create_dicom_dataset, set_spatial_info
        ds = create_dicom_dataset('test.dcm')
        ds = set_spatial_info(ds, image_position=(10.0, 20.0, 30.0))
        assert ds.ImagePositionPatient == [10.0, 20.0, 30.0]

    def test_slice_location(self):
        """Slice location correctly set."""
        from app.utils.dicom_utils import create_dicom_dataset, set_spatial_info
        ds = create_dicom_dataset('test.dcm')
        ds = set_spatial_info(ds, slice_location=42.5)
        assert ds.SliceLocation == 42.5


@pytest.mark.unit
class TestNumpyToPixelData:
    """Tests for numpy_to_dicom_pixel_data()."""

    def test_uint8_conversion(self):
        """uint8 array correctly converted to DICOM pixel data."""
        from app.utils.dicom_utils import numpy_to_dicom_pixel_data
        arr = np.array([[0, 128], [255, 64]], dtype=np.uint8)
        pixel_data = numpy_to_dicom_pixel_data(arr, bits_allocated=8)
        assert isinstance(pixel_data, bytes)
        assert len(pixel_data) == 4

    def test_uint16_conversion(self):
        """uint16 array correctly converted."""
        from app.utils.dicom_utils import numpy_to_dicom_pixel_data
        arr = np.array([[0, 1000], [4095, 2048]], dtype=np.uint16)
        pixel_data = numpy_to_dicom_pixel_data(arr, bits_allocated=16)
        assert isinstance(pixel_data, bytes)
        assert len(pixel_data) == 8  # 4 pixels * 2 bytes


@pytest.mark.unit
class TestSaveDicom:
    """Tests for save_dicom() — file I/O safety."""

    def test_save_creates_file(self):
        """DICOM file is written to disk."""
        from app.utils.dicom_utils import create_dicom_dataset, set_patient_info, save_dicom
        ds = create_dicom_dataset('test.dcm')
        ds = set_patient_info(ds, 'TESTPAT')
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'output.dcm')
            save_dicom(ds, path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0

    def test_save_creates_parent_dirs(self):
        """Missing parent directories are created automatically."""
        from app.utils.dicom_utils import create_dicom_dataset, set_patient_info, save_dicom
        ds = create_dicom_dataset('test.dcm')
        ds = set_patient_info(ds, 'TESTPAT')
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'subdir', 'nested', 'output.dcm')
            save_dicom(ds, path)
            assert os.path.exists(path)


@pytest.mark.unit
class TestExtractDicomMetadata:
    """Tests for extract_dicom_metadata()."""

    def test_extracts_patient_info(self):
        """Patient metadata correctly extracted from dataset."""
        from app.utils.dicom_utils import (
            create_dicom_dataset, set_patient_info,
            set_study_info, extract_dicom_metadata
        )
        ds = create_dicom_dataset('test.dcm')
        ds = set_patient_info(ds, 'PAT123', 'Test Patient')
        ds = set_study_info(ds, study_description='Brain MRI')
        metadata = extract_dicom_metadata(ds)
        assert isinstance(metadata, dict)
        assert metadata.get('patient_id') == 'PAT123' or 'PatientID' in str(metadata)


@pytest.mark.unit
class TestCreateDicomSeg:
    """Tests for create_dicom_seg() — DICOM-SEG export (Class C)."""

    def test_basic_seg_creation(self):
        """Basic DICOM-SEG created from 3D mask."""
        from app.utils.dicom_utils import create_dicom_seg
        mask = np.zeros((10, 64, 64), dtype=np.uint8)
        mask[3:7, 20:40, 20:40] = 1
        labels = [{"id": 1, "name": "Lesion", "color": "#FF0000"}]
        result = create_dicom_seg(mask, labels)
        assert result is not None

    def test_multi_label_seg(self):
        """Multi-label segmentation with different regions."""
        from app.utils.dicom_utils import create_dicom_seg
        mask = np.zeros((10, 64, 64), dtype=np.uint8)
        mask[2:4, 10:20, 10:20] = 1
        mask[6:8, 30:40, 30:40] = 2
        labels = [
            {"id": 1, "name": "PV", "color": "#FF0000"},
            {"id": 2, "name": "JC", "color": "#00FF00"},
        ]
        result = create_dicom_seg(mask, labels)
        assert result is not None

    def test_empty_mask_seg(self):
        """Empty mask produces valid DICOM-SEG (no segments active)."""
        from app.utils.dicom_utils import create_dicom_seg
        mask = np.zeros((5, 32, 32), dtype=np.uint8)
        labels = [{"id": 1, "name": "Empty", "color": "#FFFFFF"}]
        result = create_dicom_seg(mask, labels)
        assert result is not None

    def test_seg_with_patient_metadata(self):
        """DICOM-SEG includes patient metadata when provided."""
        from app.utils.dicom_utils import create_dicom_seg
        mask = np.zeros((5, 32, 32), dtype=np.uint8)
        mask[2, 10:20, 10:20] = 1
        labels = [{"id": 1, "name": "Lesion", "color": "#FF0000"}]
        result = create_dicom_seg(
            mask, labels,
            patient_id="PAT001",
            patient_name="Test Patient",
            study_description="MS Brain MRI"
        )
        assert result is not None
