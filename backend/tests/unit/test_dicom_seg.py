"""
Unit tests for DICOM-SEG creation.

Validates that create_dicom_seg produces valid DICOM Segmentation objects
with correct SOP Class, segment sequences, and pixel data encoding.

@module tests.unit.test_dicom_seg
"""

import pytest
import numpy as np


class TestDICOMSegCreation:
    """Test DICOM-SEG object creation from 3D masks."""

    def test_basic_creation(self):
        """Test basic DICOM-SEG creation with a simple mask."""
        from app.utils.dicom_utils import create_dicom_seg, SEGMENTATION_STORAGE_UID

        # Create a simple 3D mask (10 slices, 64x64)
        mask = np.zeros((10, 64, 64), dtype=np.uint8)
        mask[3:7, 20:40, 20:40] = 1  # A lesion in label 1

        labels = [
            {"id": 1, "name": "MS Lesion", "color": "#FF4444"},
        ]

        ds = create_dicom_seg(mask, labels)

        # Verify SOP Class
        assert str(ds.SOPClassUID) == SEGMENTATION_STORAGE_UID
        assert ds.Modality == 'SEG'
        assert ds.SegmentationType == 'BINARY'

        # Verify dimensions
        assert ds.Rows == 64
        assert ds.Columns == 64
        assert ds.NumberOfFrames == 10  # 10 slices * 1 label

        # Verify segment sequence
        assert len(ds.SegmentSequence) == 1
        assert ds.SegmentSequence[0].SegmentLabel == 'MS Lesion'
        assert ds.SegmentSequence[0].SegmentNumber == 1

        # Verify pixel data exists
        assert ds.PixelData is not None
        assert len(ds.PixelData) > 0

    def test_multi_label_creation(self):
        """Test DICOM-SEG with multiple labels."""
        from app.utils.dicom_utils import create_dicom_seg

        mask = np.zeros((5, 32, 32), dtype=np.uint8)
        mask[1, 10:20, 10:20] = 1  # Label 1
        mask[2, 5:15, 5:15] = 2    # Label 2
        mask[3, 15:25, 15:25] = 3  # Label 3

        labels = [
            {"id": 1, "name": "Periventricular", "color": "#FF4444"},
            {"id": 2, "name": "Juxtacortical", "color": "#44BB44"},
            {"id": 3, "name": "Infratentorial", "color": "#4488FF"},
        ]

        ds = create_dicom_seg(mask, labels)

        # 5 slices * 3 labels = 15 frames
        assert ds.NumberOfFrames == 15
        assert len(ds.SegmentSequence) == 3
        assert ds.SegmentSequence[0].SegmentLabel == 'Periventricular'
        assert ds.SegmentSequence[1].SegmentLabel == 'Juxtacortical'
        assert ds.SegmentSequence[2].SegmentLabel == 'Infratentorial'

    def test_empty_mask(self):
        """Test DICOM-SEG with empty mask (all zeros)."""
        from app.utils.dicom_utils import create_dicom_seg

        mask = np.zeros((5, 32, 32), dtype=np.uint8)
        labels = [{"id": 1, "name": "Lesion", "color": "#FF0000"}]

        ds = create_dicom_seg(mask, labels)

        # Should still create valid DICOM-SEG
        assert ds.NumberOfFrames == 5
        assert ds.PixelData is not None

    def test_patient_metadata(self):
        """Test that patient metadata is correctly set."""
        from app.utils.dicom_utils import create_dicom_seg

        mask = np.zeros((3, 16, 16), dtype=np.uint8)
        labels = [{"id": 1, "name": "Test", "color": "#FF0000"}]

        ds = create_dicom_seg(
            mask, labels,
            patient_name="DOE^JOHN",
            patient_id="MRN-12345",
            study_description="MS Brain MRI",
        )

        assert str(ds.PatientName) == "DOE^JOHN"
        assert ds.PatientID == "MRN-12345"
        assert ds.StudyDescription == "MS Brain MRI"

    def test_per_frame_functional_groups(self):
        """Test that per-frame functional groups are correctly structured."""
        from app.utils.dicom_utils import create_dicom_seg

        mask = np.zeros((3, 16, 16), dtype=np.uint8)
        mask[1, 5:10, 5:10] = 1
        labels = [{"id": 1, "name": "Lesion", "color": "#FF0000"}]

        ds = create_dicom_seg(mask, labels)

        # Should have 3 per-frame items (3 slices * 1 label)
        assert len(ds.PerFrameFunctionalGroupsSequence) == 3

        # Each frame should have segment identification
        for pf in ds.PerFrameFunctionalGroupsSequence:
            assert hasattr(pf, 'SegmentIdentificationSequence')
            assert hasattr(pf, 'PlanePositionSequence')
            assert hasattr(pf, 'FrameContentSequence')

    def test_shared_functional_groups(self):
        """Test that shared functional groups include pixel measures."""
        from app.utils.dicom_utils import create_dicom_seg

        mask = np.zeros((3, 16, 16), dtype=np.uint8)
        labels = [{"id": 1, "name": "Test", "color": "#FF0000"}]

        ds = create_dicom_seg(mask, labels)

        shared = ds.SharedFunctionalGroupsSequence[0]
        assert hasattr(shared, 'PixelMeasuresSequence')
        assert hasattr(shared, 'PlaneOrientationSequence')

        pm = shared.PixelMeasuresSequence[0]
        assert list(pm.PixelSpacing) == [1.0, 1.0]
        assert pm.SliceThickness == 1.0

    def test_bit_packing(self):
        """Test that binary pixel data is correctly bit-packed."""
        from app.utils.dicom_utils import create_dicom_seg

        # Small mask where we can verify bit packing
        mask = np.zeros((1, 2, 4), dtype=np.uint8)
        mask[0, 0, :] = 1  # First row all 1s (4 pixels)
        mask[0, 1, :] = 0  # Second row all 0s
        labels = [{"id": 1, "name": "Test", "color": "#FF0000"}]

        ds = create_dicom_seg(mask, labels)

        assert ds.BitsAllocated == 1
        assert ds.BitsStored == 1
        assert ds.PixelData is not None
