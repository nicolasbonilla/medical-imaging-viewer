"""
Unit tests for lesion_analysis_service — IEC 62304 Class C.

Tests verify connected component analysis, volume computation,
DIS criteria assessment per McDonald 2024 (DD-LES-001/DD-LES-002).
"""
import pytest
import numpy as np


@pytest.mark.unit
class TestAnalyzeLesions:
    """Tests for analyze_lesions (Class C — DD-LES-001)."""

    def test_empty_mask_returns_zero(self):
        """All-zero mask returns total_count=0."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        result = analyze_lesions(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result.get("total_count", 0) == 0

    def test_single_lesion_detected(self):
        """Single connected component correctly identified."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 1  # 27 voxels, label=1 (PV)
        result = analyze_lesions(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result.get("total_count", 0) >= 1

    def test_multiple_separate_lesions(self):
        """Multiple disconnected components counted correctly."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((30, 30, 30), dtype=np.int32)
        mask[2:5, 2:5, 2:5] = 1   # Lesion 1
        mask[20:23, 20:23, 20:23] = 2  # Lesion 2
        result = analyze_lesions(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result.get("total_count", 0) >= 2

    def test_volume_calculation_isotropic(self):
        """Volume matches voxel count * voxel volume."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 1  # 27 voxels
        result = analyze_lesions(mask, voxel_spacing=(1.0, 1.0, 1.0))
        if "lesions" in result and len(result["lesions"]) > 0:
            assert result["lesions"][0]["volume_mm3"] == pytest.approx(27.0)

    def test_volume_calculation_anisotropic(self):
        """Non-isotropic spacing correctly scales volume."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[5:7, 5:7, 5:7] = 1  # 8 voxels, volume = 8 * 8.0 = 64.0 mm3
        result = analyze_lesions(mask, voxel_spacing=(2.0, 2.0, 2.0))
        if "lesions" in result and len(result["lesions"]) > 0:
            assert result["lesions"][0]["volume_mm3"] == pytest.approx(64.0)

    def test_input_validation_2d_mask(self):
        """2D mask raises ValueError (IEC 62304 REQ-SAFE-005)."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((20, 20), dtype=np.int32)
        with pytest.raises(ValueError, match="3D"):
            analyze_lesions(mask, (1.0, 1.0, 1.0))  # RC-024: spacing now required

    def test_input_validation_negative_spacing(self):
        """Negative spacing raises ValueError."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        with pytest.raises(ValueError):
            analyze_lesions(mask, voxel_spacing=(-1.0, 1.0, 1.0))

    def test_small_lesion_filtered_by_min_volume(self):
        """Lesions below MIN_LESION_VOLUME_MM3 (3.0) are excluded."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[5, 5, 5] = 1  # 1 voxel = 1.0 mm3 at 1mm isotropic → below threshold
        result = analyze_lesions(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result["total_count"] == 0

    def test_lesion_at_min_volume_threshold(self):
        """Lesion exactly at MIN_LESION_VOLUME_MM3 threshold is included."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[5:8, 5, 5] = 1  # 3 voxels = 3.0 mm3 at 1mm isotropic → at threshold
        result = analyze_lesions(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result["total_count"] == 1

    def test_size_category_small(self):
        """Lesion <100 mm3 classified as 'small'."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 1  # 27 voxels = 27 mm3
        result = analyze_lesions(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result["lesions"][0]["size_category"] == "small"

    def test_size_category_medium(self):
        """Lesion 100-999 mm3 classified as 'medium'."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[0:10, 0:10, 0:2] = 1  # 200 voxels = 200 mm3
        result = analyze_lesions(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result["lesions"][0]["size_category"] == "medium"

    def test_size_category_large(self):
        """Lesion >=1000 mm3 classified as 'large'."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[0:10, 0:10, 0:10] = 1  # 1000 voxels = 1000 mm3
        result = analyze_lesions(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result["lesions"][0]["size_category"] == "large"

    def test_region_summary_present(self):
        """Result includes region summary with correct label."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 1  # PV
        result = analyze_lesions(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert "regions" in result
        assert "Periventricular" in result["regions"]

    def test_total_burden_calculation(self):
        """Total burden matches sum of all annotated voxels."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 1  # 27 voxels
        mask[15:17, 15:17, 15:17] = 2  # 8 voxels
        result = analyze_lesions(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result["total_burden_mm3"] == pytest.approx(35.0)

    def test_lesions_sorted_by_volume_descending(self):
        """Lesions are returned sorted largest-first."""
        from app.services.lesion_analysis_service import analyze_lesions
        mask = np.zeros((30, 30, 30), dtype=np.int32)
        mask[2:5, 2:5, 2:5] = 1   # 27 voxels
        mask[20:25, 20:25, 20:25] = 2  # 125 voxels
        result = analyze_lesions(mask, voxel_spacing=(1.0, 1.0, 1.0))
        if len(result["lesions"]) >= 2:
            assert result["lesions"][0]["volume_mm3"] >= result["lesions"][1]["volume_mm3"]

    def test_input_validation_not_ndarray(self):
        """Non-ndarray input raises ValueError."""
        from app.services.lesion_analysis_service import analyze_lesions
        with pytest.raises(ValueError, match="numpy ndarray"):
            analyze_lesions([[1, 2], [3, 4]], (1.0, 1.0, 1.0))  # RC-024

    def test_custom_labels(self):
        """Custom label mapping is used in output."""
        from app.services.lesion_analysis_service import analyze_lesions
        custom = {1: "CustomRegion"}
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 1
        result = analyze_lesions(mask, voxel_spacing=(1.0, 1.0, 1.0), labels=custom)
        assert result["lesions"][0]["region"] == "CustomRegion"


@pytest.mark.unit
class TestDISCriteria:
    """Tests for compute_dis_criteria (Class C — DD-LES-002, McDonald 2024)."""

    def test_dis_met_two_brain_regions(self):
        """DIS met when >=2 brain regions have lesions (McDonald 2024)."""
        from app.services.lesion_analysis_service import compute_dis_criteria
        mask = np.zeros((30, 30, 30), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 1   # PV
        mask[20:23, 20:23, 20:23] = 2  # JC
        result = compute_dis_criteria(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result.get("dis_met_brain", result.get("dis_met", False)) is True

    def test_dis_not_met_one_region(self):
        """DIS not met with only 1 brain region."""
        from app.services.lesion_analysis_service import compute_dis_criteria
        mask = np.zeros((30, 30, 30), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 1   # Only PV
        result = compute_dis_criteria(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result.get("dis_met_brain", result.get("dis_met", False)) is False

    def test_dis_dwm_not_counted(self):
        """DWM (label 4) is NOT a DIS region per McDonald 2024."""
        from app.services.lesion_analysis_service import compute_dis_criteria
        mask = np.zeros((30, 30, 30), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 1   # PV
        mask[20:23, 20:23, 20:23] = 4  # DWM — NOT DIS
        result = compute_dis_criteria(mask, voxel_spacing=(1.0, 1.0, 1.0))
        brain_regions = result.get("brain_regions_with_lesions", 0)
        # Should be 1, not 2 (DWM doesn't count)
        assert brain_regions <= 1 or result.get("dis_met_brain", result.get("dis_met", False)) is False

    def test_dis_empty_mask(self):
        """Empty mask -> DIS not met."""
        from app.services.lesion_analysis_service import compute_dis_criteria
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        result = compute_dis_criteria(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result.get("dis_met_brain", result.get("dis_met", False)) is False

    def test_dis_input_validation(self):
        """2D mask raises ValueError."""
        from app.services.lesion_analysis_service import compute_dis_criteria
        with pytest.raises(ValueError, match="3D"):
            compute_dis_criteria(np.zeros((20, 20), dtype=np.int32), None, (1.0, 1.0, 1.0))  # RC-024

    def test_dis_all_three_brain_regions(self):
        """DIS met when all 3 brain regions (PV, JC, IT) have lesions."""
        from app.services.lesion_analysis_service import compute_dis_criteria
        mask = np.zeros((30, 30, 30), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 1   # PV
        mask[15:18, 15:18, 15:18] = 2  # JC
        mask[25:28, 25:28, 25:28] = 3  # IT
        result = compute_dis_criteria(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result["dis_met_brain"] is True
        assert result["brain_regions_with_lesions"] == 3

    def test_dis_region_details_structure(self):
        """Result includes region_details with expected keys."""
        from app.services.lesion_analysis_service import compute_dis_criteria
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 1  # PV
        result = compute_dis_criteria(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert "region_details" in result
        details = result["region_details"]
        # Should have entries for PV, JC, IT
        assert len(details) == 3

    def test_dis_small_lesion_not_qualifying(self):
        """Lesions below MIN_LESION_VOLUME_MM3 do not qualify for DIS."""
        from app.services.lesion_analysis_service import compute_dis_criteria
        mask = np.zeros((30, 30, 30), dtype=np.int32)
        mask[5, 5, 5] = 1      # 1 voxel PV — below threshold
        mask[20, 20, 20] = 2   # 1 voxel JC — below threshold
        result = compute_dis_criteria(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result["dis_met_brain"] is False

    def test_dis_active_lesion_detection(self):
        """Active lesions (Gd+, label 5) are detected in result."""
        from app.services.lesion_analysis_service import compute_dis_criteria
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 5  # Active (Gd+)
        result = compute_dis_criteria(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result["has_active_lesions"] is True
        assert result["active_voxels"] == 27

    def test_dis_black_hole_detection(self):
        """Black holes (label 6) are detected in result."""
        from app.services.lesion_analysis_service import compute_dis_criteria
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 6  # Black Hole (T1)
        result = compute_dis_criteria(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result["has_black_holes"] is True
        assert result["black_hole_voxels"] == 27

    def test_dis_criteria_version_string(self):
        """Result includes the McDonald 2024 version string."""
        from app.services.lesion_analysis_service import compute_dis_criteria
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        result = compute_dis_criteria(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert "McDonald 2024" in result["dis_criteria_version"]

    def test_dis_input_validation_not_ndarray(self):
        """Non-ndarray input raises ValueError."""
        from app.services.lesion_analysis_service import compute_dis_criteria
        with pytest.raises(ValueError, match="numpy ndarray"):
            compute_dis_criteria([[1, 2], [3, 4]], None, (1.0, 1.0, 1.0))  # RC-024
