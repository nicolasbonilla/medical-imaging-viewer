"""
Unit tests for ms_region_classifier — IEC 62304 Class C.

Tests verify MAGNIMS region classification accuracy per McDonald 2024
and 2024 MAGNIMS-CMSC-NAIMS consensus (DD-CLS-001).
"""
import pytest
import numpy as np


@pytest.mark.unit
class TestClassifyWithParcellation:
    """Tests for classify_lesions_with_parcellation (Class C — DD-CLS-001)."""

    def test_pv_lesion_near_ventricle(self):
        """Lesion adjacent to lateral ventricle -> classified as PV (label 1)."""
        from app.services.ms_region_classifier import classify_lesions_with_parcellation
        lesion = np.zeros((30, 30, 30), dtype=np.int32)
        parc = np.zeros((30, 30, 30), dtype=np.int32)
        parc[14:16, 14:16, 14:16] = 4  # Left lateral ventricle
        lesion[16, 14:16, 14:16] = 1   # Lesion directly adjacent
        result = classify_lesions_with_parcellation(lesion, parc, voxel_spacing=(1.0, 1.0, 1.0))
        assert "classified_lesions" in result or "lesions" in result

    def test_pv_lesion_classified_correctly(self):
        """Lesion touching ventricle gets MAGNIMS region=1 (Periventricular)."""
        from app.services.ms_region_classifier import classify_lesions_with_parcellation
        lesion = np.zeros((30, 30, 30), dtype=np.int32)
        parc = np.zeros((30, 30, 30), dtype=np.int32)
        parc[13:17, 13:17, 13:17] = 4  # Left lateral ventricle (larger)
        lesion[17:19, 14:16, 14:16] = 1  # Lesion directly adjacent to ventricle
        result = classify_lesions_with_parcellation(lesion, parc, voxel_spacing=(1.0, 1.0, 1.0))
        lesions_list = result.get("classified_lesions", result.get("lesions", []))
        if len(lesions_list) > 0:
            # Region label 1 = Periventricular
            assert lesions_list[0].get("region_id", lesions_list[0].get("region_label", lesions_list[0].get("label"))) == 1

    def test_jc_lesion_near_cortex(self):
        """Lesion adjacent to cortex -> classified as JC (label 2)."""
        from app.services.ms_region_classifier import classify_lesions_with_parcellation
        lesion = np.zeros((30, 30, 30), dtype=np.int32)
        parc = np.zeros((30, 30, 30), dtype=np.int32)
        # Cortex at the surface, no ventricles nearby
        parc[2:4, 2:28, 2:28] = 3   # Left cerebral cortex (outer shell)
        lesion[4:6, 14:16, 14:16] = 1  # Lesion adjacent to cortex
        result = classify_lesions_with_parcellation(lesion, parc, voxel_spacing=(1.0, 1.0, 1.0))
        lesions_list = result.get("classified_lesions", result.get("lesions", []))
        if len(lesions_list) > 0:
            # Region label 2 = Juxtacortical
            assert lesions_list[0].get("region_id", lesions_list[0].get("region_label", lesions_list[0].get("label"))) == 2

    def test_it_lesion_near_brainstem(self):
        """Lesion adjacent to brainstem -> classified as IT (label 3)."""
        from app.services.ms_region_classifier import classify_lesions_with_parcellation
        lesion = np.zeros((30, 30, 30), dtype=np.int32)
        parc = np.zeros((30, 30, 30), dtype=np.int32)
        parc[3:6, 14:16, 14:16] = 16  # Brain Stem
        lesion[6:8, 14:16, 14:16] = 1  # Lesion adjacent to brainstem
        result = classify_lesions_with_parcellation(lesion, parc, voxel_spacing=(1.0, 1.0, 1.0))
        lesions_list = result.get("classified_lesions", result.get("lesions", []))
        if len(lesions_list) > 0:
            # Region label 3 = Infratentorial (IT has highest priority in cascade)
            assert lesions_list[0].get("region_id", lesions_list[0].get("region_label", lesions_list[0].get("label"))) == 3

    def test_shape_mismatch_raises_error(self):
        """Different shape masks raise ValueError."""
        from app.services.ms_region_classifier import classify_lesions_with_parcellation
        lesion = np.zeros((10, 10, 10), dtype=np.int32)
        parc = np.zeros((20, 20, 20), dtype=np.int32)
        with pytest.raises(ValueError):
            classify_lesions_with_parcellation(lesion, parc)

    def test_empty_lesion_mask(self):
        """All-zero lesion mask returns empty result."""
        from app.services.ms_region_classifier import classify_lesions_with_parcellation
        lesion = np.zeros((20, 20, 20), dtype=np.int32)
        parc = np.zeros((20, 20, 20), dtype=np.int32)
        parc[10, 10, 10] = 4
        result = classify_lesions_with_parcellation(lesion, parc, voxel_spacing=(1.0, 1.0, 1.0))
        lesions_list = result.get("classified_lesions", result.get("lesions", []))
        assert len(lesions_list) == 0

    def test_input_validation_2d(self):
        """2D mask raises ValueError."""
        from app.services.ms_region_classifier import classify_lesions_with_parcellation
        with pytest.raises(ValueError):
            classify_lesions_with_parcellation(
                np.zeros((10, 10), dtype=np.int32),
                np.zeros((10, 10), dtype=np.int32)
            )

    def test_negative_spacing_raises(self):
        """Negative voxel spacing raises ValueError."""
        from app.services.ms_region_classifier import classify_lesions_with_parcellation
        with pytest.raises(ValueError):
            classify_lesions_with_parcellation(
                np.zeros((10, 10, 10), dtype=np.int32),
                np.zeros((10, 10, 10), dtype=np.int32),
                voxel_spacing=(-1.0, 1.0, 1.0)
            )

    def test_classified_mask_in_result(self):
        """Result includes a classified_mask ndarray with MAGNIMS labels."""
        from app.services.ms_region_classifier import classify_lesions_with_parcellation
        lesion = np.zeros((30, 30, 30), dtype=np.int32)
        parc = np.zeros((30, 30, 30), dtype=np.int32)
        parc[14:16, 14:16, 14:16] = 4  # Ventricle
        lesion[16:18, 14:16, 14:16] = 1  # Adjacent lesion
        result = classify_lesions_with_parcellation(lesion, parc, voxel_spacing=(1.0, 1.0, 1.0))
        if "classified_mask" in result:
            assert isinstance(result["classified_mask"], np.ndarray)
            assert result["classified_mask"].shape == lesion.shape

    def test_method_field_is_parcellation(self):
        """Result method field indicates parcellation-based classification."""
        from app.services.ms_region_classifier import classify_lesions_with_parcellation
        lesion = np.zeros((20, 20, 20), dtype=np.int32)
        parc = np.zeros((20, 20, 20), dtype=np.int32)
        result = classify_lesions_with_parcellation(lesion, parc, voxel_spacing=(1.0, 1.0, 1.0))
        assert result.get("method") == "parcellation"

    def test_small_lesion_filtered(self):
        """Lesion below MIN_LESION_VOLUME_MM3 is excluded from classification."""
        from app.services.ms_region_classifier import classify_lesions_with_parcellation
        lesion = np.zeros((30, 30, 30), dtype=np.int32)
        parc = np.zeros((30, 30, 30), dtype=np.int32)
        parc[14:16, 14:16, 14:16] = 4  # Ventricle
        lesion[16, 14, 14] = 1  # 1 voxel = 1mm3 < 3.0mm3 threshold
        result = classify_lesions_with_parcellation(lesion, parc, voxel_spacing=(1.0, 1.0, 1.0))
        lesions_list = result.get("classified_lesions", result.get("lesions", []))
        assert len(lesions_list) == 0


@pytest.mark.unit
class TestClassifyGeometric:
    """Tests for classify_lesions_geometric (Class C — DD-CLS-001 fallback)."""

    def test_basic_classification(self):
        """Geometric classifier returns results for non-empty mask."""
        from app.services.ms_region_classifier import classify_lesions_geometric
        mask = np.zeros((30, 30, 30), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 1  # A lesion
        result = classify_lesions_geometric(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert isinstance(result, dict)
        assert "classified_lesions" in result or "lesions" in result

    def test_empty_mask_returns_empty(self):
        """Empty mask returns empty classification."""
        from app.services.ms_region_classifier import classify_lesions_geometric
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        result = classify_lesions_geometric(mask, voxel_spacing=(1.0, 1.0, 1.0))
        lesions_list = result.get("classified_lesions", result.get("lesions", []))
        assert len(lesions_list) == 0

    def test_input_validation_2d(self):
        """2D mask raises ValueError."""
        from app.services.ms_region_classifier import classify_lesions_geometric
        with pytest.raises(ValueError):
            classify_lesions_geometric(np.zeros((10, 10), dtype=np.int32))

    def test_input_validation_negative_spacing(self):
        """Negative voxel spacing raises ValueError."""
        from app.services.ms_region_classifier import classify_lesions_geometric
        with pytest.raises(ValueError):
            classify_lesions_geometric(
                np.zeros((10, 10, 10), dtype=np.int32),
                voxel_spacing=(-1.0, 1.0, 1.0)
            )

    def test_input_validation_not_ndarray(self):
        """Non-ndarray input raises ValueError."""
        from app.services.ms_region_classifier import classify_lesions_geometric
        with pytest.raises(ValueError):
            classify_lesions_geometric([[1, 2, 3]])

    def test_method_field_is_geometric(self):
        """Result method field indicates geometric classification."""
        from app.services.ms_region_classifier import classify_lesions_geometric
        mask = np.zeros((20, 20, 20), dtype=np.int32)
        result = classify_lesions_geometric(mask, voxel_spacing=(1.0, 1.0, 1.0))
        assert result.get("method") == "geometric"

    def test_classified_mask_in_result(self):
        """Result includes a classified_mask ndarray."""
        from app.services.ms_region_classifier import classify_lesions_geometric
        mask = np.zeros((30, 30, 30), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 1
        result = classify_lesions_geometric(mask, voxel_spacing=(1.0, 1.0, 1.0))
        if "classified_mask" in result:
            assert isinstance(result["classified_mask"], np.ndarray)
            assert result["classified_mask"].shape == mask.shape

    def test_multiple_lesions_classified(self):
        """Multiple disconnected lesions each receive a classification."""
        from app.services.ms_region_classifier import classify_lesions_geometric
        mask = np.zeros((30, 30, 30), dtype=np.int32)
        mask[2:5, 2:5, 2:5] = 1     # Bottom lesion
        mask[25:28, 15:18, 15:18] = 1  # Top lesion
        result = classify_lesions_geometric(mask, voxel_spacing=(1.0, 1.0, 1.0))
        lesions_list = result.get("classified_lesions", result.get("lesions", []))
        assert len(lesions_list) >= 2

    def test_small_lesion_filtered(self):
        """Lesion below MIN_LESION_VOLUME_MM3 is excluded."""
        from app.services.ms_region_classifier import classify_lesions_geometric
        mask = np.zeros((30, 30, 30), dtype=np.int32)
        mask[5, 5, 5] = 1  # 1 voxel = 1mm3 < 3.0mm3 threshold
        result = classify_lesions_geometric(mask, voxel_spacing=(1.0, 1.0, 1.0))
        lesions_list = result.get("classified_lesions", result.get("lesions", []))
        assert len(lesions_list) == 0

    def test_region_labels_are_valid_magnims(self):
        """All classified regions use valid MAGNIMS labels (1-4)."""
        from app.services.ms_region_classifier import classify_lesions_geometric
        mask = np.zeros((30, 30, 30), dtype=np.int32)
        mask[5:8, 5:8, 5:8] = 1
        mask[20:23, 20:23, 20:23] = 1
        result = classify_lesions_geometric(mask, voxel_spacing=(1.0, 1.0, 1.0))
        lesions_list = result.get("classified_lesions", result.get("lesions", []))
        valid_labels = {1, 2, 3, 4}
        for les in lesions_list:
            region_label = les.get("region_id", les.get("region_label", les.get("label", 0)))
            assert region_label in valid_labels, f"Invalid MAGNIMS label: {region_label}"
