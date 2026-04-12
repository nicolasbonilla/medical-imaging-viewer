"""
Unit tests for BrainVolumetryService — IEC 62304 Class C.

Tests verify correctness of brain volume computation, normative comparison,
and abnormality detection per DD-VOL-001/DD-VOL-002.

Requirement traceability:
  - REQ-FUNC-040: Brain volumetry computation
  - REQ-SAFE-005: Input validation for safety-critical parameters
  - DD-VOL-001: Volume calculation from voxel counts
  - DD-VOL-002: Normative comparison and abnormality detection
"""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch


@pytest.mark.unit
class TestBrainVolumetryService:
    """Tests for BrainVolumetryService (Class C — DD-VOL-001)."""

    def setup_method(self):
        from app.services.brain_volumetry_service import BrainVolumetryService
        self.service = BrainVolumetryService()

    # =========================================================================
    # Volume computation — basic correctness
    # =========================================================================

    def test_compute_volumes_basic(self):
        """Verify volume computation with known label and isotropic 1mm spacing."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        mask[2:5, 2:5, 2:5] = 17  # Left hippocampus, 3*3*3 = 27 voxels
        result = self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="seg-001")

        assert result.total_brain_volume_ml > 0
        structures = result.structures
        assert any(s.label_id == 17 for s in structures)
        hippo = next(s for s in structures if s.label_id == 17)
        assert hippo.volume_mm3 == 27.0
        assert hippo.volume_ml == 0.027
        assert hippo.structure_name == "Left Hippocampus"

    def test_compute_volumes_spacing_scaling(self):
        """Verify volumes scale correctly with non-isotropic spacing (DD-VOL-001)."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        mask[0, 0, 0] = 17  # 1 voxel

        result_1mm = self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="seg-1mm")
        result_2mm = self.service.compute_volumes(mask, (2.0, 2.0, 2.0), segmentation_id="seg-2mm")

        v1 = next(s for s in result_1mm.structures if s.label_id == 17).volume_mm3
        v2 = next(s for s in result_2mm.structures if s.label_id == 17).volume_mm3
        assert v2 == v1 * 8.0  # 2^3 = 8x volume

    def test_compute_volumes_anisotropic_spacing(self):
        """Verify volume computation with anisotropic voxel spacing."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        mask[0:2, 0:2, 0:2] = 10  # 8 voxels, Left Thalamus
        # Spacing: z=3mm, y=1mm, x=0.5mm => voxel vol = 1.5 mm3
        result = self.service.compute_volumes(mask, (3.0, 1.0, 0.5), segmentation_id="seg-aniso")
        thal = next(s for s in result.structures if s.label_id == 10)
        assert thal.volume_mm3 == pytest.approx(8 * 1.5, abs=0.01)

    def test_compute_volumes_empty_mask(self):
        """Empty mask returns empty structures list and zero volumes."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        result = self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="seg-empty")
        assert result.structures == []
        assert result.total_brain_volume_ml == 0.0
        assert result.intracranial_volume_ml == 0.0

    def test_compute_volumes_multiple_labels(self):
        """Multiple labels each get their own volume entry."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        mask[0:2, 0:2, 0:2] = 17  # 8 voxels — Left Hippocampus
        mask[5:7, 5:7, 5:7] = 4   # 8 voxels — Left Lateral Ventricle
        result = self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="seg-multi")

        label_ids = [s.label_id for s in result.structures]
        assert 17 in label_ids
        assert 4 in label_ids
        assert len(result.structures) == 2

    def test_compute_volumes_unknown_label(self):
        """Unknown label IDs produce 'Structure N' fallback name."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        mask[0, 0, 0] = 999  # Not in STRUCTURE_NAMES
        result = self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="seg-unk")
        s = result.structures[0]
        assert s.label_id == 999
        assert s.structure_name == "Structure 999"

    def test_compute_volumes_background_excluded(self):
        """Label 0 (background) is excluded from structures."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)  # All zeros
        mask[0, 0, 0] = 17
        result = self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="seg-bg")
        label_ids = [s.label_id for s in result.structures]
        assert 0 not in label_ids

    def test_compute_volumes_segmentation_id_propagated(self):
        """Segmentation ID is included in the result."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        result = self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="test-id-42")
        assert result.segmentation_id == "test-id-42"

    def test_compute_volumes_processing_time(self):
        """Processing time is recorded as non-negative integer milliseconds."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        result = self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="seg-time")
        assert isinstance(result.processing_time_ms, int)
        assert result.processing_time_ms >= 0

    # =========================================================================
    # Brain volume vs intracranial volume accounting
    # =========================================================================

    def test_ventricular_label_excluded_from_brain_volume(self):
        """Ventricular structures count toward ICV but NOT brain volume."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        mask[0:5, 0:5, 0:5] = 4  # 125 voxels — Left Lateral Ventricle
        result = self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="seg-vent")

        assert result.intracranial_volume_ml == pytest.approx(0.125, abs=0.001)
        assert result.total_brain_volume_ml == 0.0  # Ventricles excluded

    def test_csf_excluded_from_brain_volume(self):
        """CSF (label 24) counts toward ICV but NOT brain volume."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        mask[0:10, 0:10, 0:1] = 24  # 100 voxels — CSF
        result = self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="seg-csf")

        assert result.intracranial_volume_ml > 0
        assert result.total_brain_volume_ml == 0.0

    def test_parenchyma_in_brain_volume(self):
        """Non-ventricular, non-CSF structures contribute to brain volume."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        mask[0:5, 0:5, 0:5] = 17  # 125 voxels — Left Hippocampus
        result = self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="seg-paren")

        expected_ml = 125.0 / 1000.0
        assert result.total_brain_volume_ml == pytest.approx(expected_ml, abs=0.01)
        assert result.intracranial_volume_ml == pytest.approx(expected_ml, abs=0.01)

    # =========================================================================
    # Normative comparison and abnormality detection (DD-VOL-002)
    # =========================================================================

    def test_compute_volumes_with_age_provides_percentile(self):
        """Patient age triggers normative percentile computation."""
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[5:10, 5:10, 5:10] = 17  # 125 voxels = 0.125 mL
        result = self.service.compute_volumes(
            mask, (1.0, 1.0, 1.0), segmentation_id="seg-age", patient_age=40
        )
        hippo = next(s for s in result.structures if s.label_id == 17)
        assert hippo.normative_percentile is not None
        assert 0.0 <= hippo.normative_percentile <= 100.0

    def test_no_percentile_without_age(self):
        """No normative percentile when patient_age is None."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        mask[0, 0, 0] = 17
        result = self.service.compute_volumes(
            mask, (1.0, 1.0, 1.0), segmentation_id="seg-noage"
        )
        hippo = next(s for s in result.structures if s.label_id == 17)
        assert hippo.normative_percentile is None

    def test_no_percentile_for_unknown_label(self):
        """No normative percentile for labels not in NORMATIVE_VOLUMES."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        mask[0, 0, 0] = 2  # Left Cerebral White Matter — not in NORMATIVE_VOLUMES
        result = self.service.compute_volumes(
            mask, (1.0, 1.0, 1.0), segmentation_id="seg-noref", patient_age=50
        )
        s = next(s for s in result.structures if s.label_id == 2)
        assert s.normative_percentile is None

    def test_hippocampal_atrophy_detected(self):
        """Very small hippocampus flags atrophy (percentile < 10)."""
        # Normative for 20-40: mean=4.2mL, std=0.5mL
        # Volume = 0.001 mL => z = (0.001 - 4.2) / 0.5 => extreme low => percentile ~ 0
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        mask[0, 0, 0] = 17  # 1 voxel = 0.001 mL at 1mm spacing
        result = self.service.compute_volumes(
            mask, (1.0, 1.0, 1.0), segmentation_id="seg-atrophy", patient_age=30
        )
        hippo = next(s for s in result.structures if s.label_id == 17)
        assert hippo.is_abnormal is True
        assert hippo.abnormality_type == "atrophy"

    def test_ventricular_enlargement_detected(self):
        """Very large ventricle flags enlargement (percentile > 90)."""
        # Normative for 20-40: mean=7.5mL, std=3.5mL
        # Need volume > ~12mL for 90th+ percentile
        # 15000 voxels at 1mm = 15.0 mL
        mask = np.zeros((30, 30, 30), dtype=np.int32)
        mask[0:15, 0:10, 0:100] = 4  # Many voxels
        voxel_count = int(np.sum(mask == 4))
        volume_ml = voxel_count / 1000.0
        # Use enough voxels to get above 90th percentile
        mask2 = np.zeros((50, 50, 50), dtype=np.int32)
        mask2[:, :, :] = 4  # 125000 voxels = 125 mL — well above 90th
        result = self.service.compute_volumes(
            mask2, (1.0, 1.0, 1.0), segmentation_id="seg-enlarge", patient_age=25
        )
        vent = next(s for s in result.structures if s.label_id == 4)
        assert vent.is_abnormal is True
        assert vent.abnormality_type == "enlargement"

    def test_normal_volume_not_flagged(self):
        """Volume near normative mean is NOT flagged as abnormal."""
        # Normative for Left Thalamus 20-40: mean=8.0mL, std=0.8mL
        # 8000 voxels at 1mm = 8.0 mL (exactly at mean)
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[:, :, :] = 0
        # Place exactly 8000 voxels of label 10
        flat = mask.ravel()
        flat[:8000] = 10
        mask = flat.reshape(20, 20, 20)

        result = self.service.compute_volumes(
            mask, (1.0, 1.0, 1.0), segmentation_id="seg-normal", patient_age=30
        )
        thal = next(s for s in result.structures if s.label_id == 10)
        assert thal.is_abnormal is False
        assert thal.normative_percentile is not None
        # Near 50th percentile (mean)
        assert 20.0 <= thal.normative_percentile <= 80.0

    # =========================================================================
    # Age group mapping
    # =========================================================================

    def test_age_group_young(self):
        """Age < 40 maps to '20-40'."""
        assert self.service._get_age_group(25) == "20-40"
        assert self.service._get_age_group(39) == "20-40"

    def test_age_group_middle(self):
        """Age 40-59 maps to '40-60'."""
        assert self.service._get_age_group(40) == "40-60"
        assert self.service._get_age_group(59) == "40-60"

    def test_age_group_senior(self):
        """Age 60-79 maps to '60-80'."""
        assert self.service._get_age_group(60) == "60-80"
        assert self.service._get_age_group(79) == "60-80"

    def test_age_group_elderly(self):
        """Age 80+ maps to '80+'."""
        assert self.service._get_age_group(80) == "80+"
        assert self.service._get_age_group(95) == "80+"

    # =========================================================================
    # Percentile computation
    # =========================================================================

    def test_percentile_at_mean_is_50(self):
        """Volume equal to normative mean yields ~50th percentile."""
        # Left Hippocampus, 20-40: mean=4.2, std=0.5
        pct = self.service._compute_percentile(4.2, 17, "20-40")
        assert pct == pytest.approx(50.0, abs=1.0)

    def test_percentile_high_volume(self):
        """Volume 2 SD above mean yields ~97.7th percentile."""
        # mean=4.2, std=0.5 => mean+2*std=5.2
        pct = self.service._compute_percentile(5.2, 17, "20-40")
        assert pct is not None
        assert pct > 95.0

    def test_percentile_low_volume(self):
        """Volume 2 SD below mean yields ~2.3rd percentile."""
        # mean=4.2, std=0.5 => mean-2*std=3.2
        pct = self.service._compute_percentile(3.2, 17, "20-40")
        assert pct is not None
        assert pct < 5.0

    def test_percentile_clamped_0_100(self):
        """Extreme volumes clamp percentile to [0, 100]."""
        pct_low = self.service._compute_percentile(0.0, 17, "20-40")
        pct_high = self.service._compute_percentile(100.0, 17, "20-40")
        assert pct_low >= 0.0
        assert pct_high <= 100.0

    def test_percentile_unknown_label(self):
        """Unknown label returns None percentile."""
        pct = self.service._compute_percentile(5.0, 999, "20-40")
        assert pct is None

    def test_percentile_unknown_age_group(self):
        """Unknown age group returns None percentile."""
        pct = self.service._compute_percentile(5.0, 17, "0-10")
        assert pct is None

    # =========================================================================
    # Input validation — IEC 62304 REQ-SAFE-005
    # =========================================================================

    def test_input_validation_non_ndarray(self):
        """Non-ndarray mask raises ValueError."""
        with pytest.raises(ValueError, match="numpy ndarray"):
            self.service.compute_volumes([[0, 0], [0, 0]], (1.0, 1.0, 1.0), segmentation_id="x")

    def test_input_validation_2d_mask(self):
        """2D mask raises ValueError (REQ-SAFE-005)."""
        mask = np.zeros((10, 10), dtype=np.int32)
        with pytest.raises(ValueError, match="3D"):
            self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="x")

    def test_input_validation_1d_mask(self):
        """1D mask raises ValueError."""
        mask = np.zeros((100,), dtype=np.int32)
        with pytest.raises(ValueError, match="3D"):
            self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="x")

    def test_input_validation_4d_mask(self):
        """4D mask raises ValueError."""
        mask = np.zeros((5, 5, 5, 3), dtype=np.int32)
        with pytest.raises(ValueError, match="3D"):
            self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="x")

    def test_input_validation_negative_spacing(self):
        """Negative voxel spacing raises ValueError (REQ-SAFE-005)."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        with pytest.raises(ValueError):
            self.service.compute_volumes(mask, (-1.0, 1.0, 1.0), segmentation_id="x")

    def test_input_validation_zero_spacing(self):
        """Zero voxel spacing raises ValueError."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        with pytest.raises(ValueError):
            self.service.compute_volumes(mask, (0.0, 1.0, 1.0), segmentation_id="x")

    def test_input_validation_excessive_spacing(self):
        """Spacing > 10mm raises ValueError (physically implausible)."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        with pytest.raises(ValueError):
            self.service.compute_volumes(mask, (1.0, 1.0, 11.0), segmentation_id="x")

    def test_input_validation_boundary_spacing_low(self):
        """Spacing at lower boundary (0.1mm) is accepted."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        mask[0, 0, 0] = 17
        result = self.service.compute_volumes(
            mask, (0.1, 0.1, 0.1), segmentation_id="seg-boundary"
        )
        assert len(result.structures) == 1

    def test_input_validation_boundary_spacing_high(self):
        """Spacing at upper boundary (10.0mm) is accepted."""
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        mask[0, 0, 0] = 17
        result = self.service.compute_volumes(
            mask, (10.0, 10.0, 10.0), segmentation_id="seg-boundary-hi"
        )
        assert len(result.structures) == 1

    # =========================================================================
    # Longitudinal comparison — compare_timepoints
    # =========================================================================

    def test_compare_timepoints_basic(self):
        """Two timepoints with known volumes produce change percentages."""
        tp1 = {
            "study_id": "s1",
            "date": "2025-01-01",
            "structures": [
                {"label_id": 17, "volume_ml": 3.0},
            ],
        }
        tp2 = {
            "study_id": "s2",
            "date": "2025-06-01",
            "structures": [
                {"label_id": 17, "volume_ml": 2.7},
            ],
        }
        result = self.service.compare_timepoints("patient1", [tp1, tp2])
        assert result.patient_id == "patient1"
        assert len(result.changes) == 1
        change = result.changes[0]
        assert change["label_id"] == 17
        assert change["change_percent"] == pytest.approx(-10.0, abs=0.01)
        assert change["trend"] == "decreasing"

    def test_compare_timepoints_increasing_trend(self):
        """Volume increase > 2% classified as 'increasing'."""
        tp1 = {"study_id": "s1", "date": "2025-01-01",
               "structures": [{"label_id": 4, "volume_ml": 10.0}]}
        tp2 = {"study_id": "s2", "date": "2025-12-01",
               "structures": [{"label_id": 4, "volume_ml": 12.0}]}
        result = self.service.compare_timepoints("p1", [tp1, tp2])
        change = result.changes[0]
        assert change["trend"] == "increasing"
        assert change["change_percent"] == pytest.approx(20.0, abs=0.01)

    def test_compare_timepoints_stable_trend(self):
        """Volume change < 2% classified as 'stable'."""
        tp1 = {"study_id": "s1", "date": "2025-01-01",
               "structures": [{"label_id": 17, "volume_ml": 4.0}]}
        tp2 = {"study_id": "s2", "date": "2025-06-01",
               "structures": [{"label_id": 17, "volume_ml": 4.05}]}
        result = self.service.compare_timepoints("p1", [tp1, tp2])
        change = result.changes[0]
        assert change["trend"] == "stable"

    def test_compare_timepoints_sorts_by_date(self):
        """Timepoints are sorted by date; first vs last comparison used."""
        tp_early = {"study_id": "s1", "date": "2024-01-01",
                    "structures": [{"label_id": 17, "volume_ml": 4.0}]}
        tp_late = {"study_id": "s3", "date": "2026-01-01",
                   "structures": [{"label_id": 17, "volume_ml": 3.0}]}
        tp_mid = {"study_id": "s2", "date": "2025-01-01",
                  "structures": [{"label_id": 17, "volume_ml": 3.5}]}
        # Pass in unsorted order
        result = self.service.compare_timepoints("p1", [tp_late, tp_early, tp_mid])
        assert len(result.timepoints) == 3
        # Should compare first (2024) vs last (2026)
        change = next(c for c in result.changes if c["label_id"] == 17)
        assert change["change_percent"] == pytest.approx(-25.0, abs=0.01)

    def test_compare_timepoints_multiple_structures(self):
        """Multiple structures are compared independently."""
        tp1 = {"study_id": "s1", "date": "2025-01-01", "structures": [
            {"label_id": 17, "volume_ml": 4.0},
            {"label_id": 4, "volume_ml": 8.0},
        ]}
        tp2 = {"study_id": "s2", "date": "2025-06-01", "structures": [
            {"label_id": 17, "volume_ml": 3.6},
            {"label_id": 4, "volume_ml": 10.0},
        ]}
        result = self.service.compare_timepoints("p1", [tp1, tp2])
        assert len(result.changes) == 2
        hippo = next(c for c in result.changes if c["label_id"] == 17)
        vent = next(c for c in result.changes if c["label_id"] == 4)
        assert hippo["trend"] == "decreasing"
        assert vent["trend"] == "increasing"

    def test_compare_timepoints_structure_only_in_one(self):
        """Structure present in only one timepoint is excluded from changes."""
        tp1 = {"study_id": "s1", "date": "2025-01-01",
               "structures": [{"label_id": 17, "volume_ml": 4.0}]}
        tp2 = {"study_id": "s2", "date": "2025-06-01",
               "structures": [{"label_id": 53, "volume_ml": 4.0}]}
        result = self.service.compare_timepoints("p1", [tp1, tp2])
        assert len(result.changes) == 0

    def test_compare_timepoints_zero_first_volume_skipped(self):
        """Structure with zero volume at first timepoint is skipped (division by zero)."""
        tp1 = {"study_id": "s1", "date": "2025-01-01",
               "structures": [{"label_id": 17, "volume_ml": 0.0}]}
        tp2 = {"study_id": "s2", "date": "2025-06-01",
               "structures": [{"label_id": 17, "volume_ml": 3.0}]}
        result = self.service.compare_timepoints("p1", [tp1, tp2])
        assert len(result.changes) == 0

    def test_compare_timepoints_single_timepoint(self):
        """Single timepoint returns empty changes (need >= 2 for comparison)."""
        tp1 = {"study_id": "s1", "date": "2025-01-01",
               "structures": [{"label_id": 17, "volume_ml": 4.0}]}
        result = self.service.compare_timepoints("p1", [tp1])
        assert result.changes == []

    def test_compare_timepoints_empty_list(self):
        """Empty timepoints list returns empty changes."""
        result = self.service.compare_timepoints("p1", [])
        assert result.changes == []

    # =========================================================================
    # Input validation — compare_timepoints
    # =========================================================================

    def test_compare_timepoints_empty_patient_id(self):
        """Empty patient_id raises ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            self.service.compare_timepoints("", [])

    def test_compare_timepoints_whitespace_patient_id(self):
        """Whitespace-only patient_id raises ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            self.service.compare_timepoints("   ", [])

    def test_compare_timepoints_non_list(self):
        """Non-list timepoints raises ValueError."""
        with pytest.raises(ValueError, match="list"):
            self.service.compare_timepoints("p1", "not a list")

    # =========================================================================
    # Return type verification
    # =========================================================================

    def test_result_is_volumetry_result_model(self):
        """compute_volumes returns a VolumetryResult Pydantic model."""
        from app.core.interfaces.ai_interface import VolumetryResult
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        result = self.service.compute_volumes(mask, (1.0, 1.0, 1.0), segmentation_id="seg-type")
        assert isinstance(result, VolumetryResult)

    def test_comparison_result_is_model(self):
        """compare_timepoints returns a VolumetryComparisonResult Pydantic model."""
        from app.core.interfaces.ai_interface import VolumetryComparisonResult
        result = self.service.compare_timepoints("p1", [])
        assert isinstance(result, VolumetryComparisonResult)
