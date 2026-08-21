"""Lesion-WISE detection metrics (TPR / PPV / F1) — the ISBI-2015 / MSSEG-2016
challenge standard, complementing voxel-overlap Dice.

Dice cannot tell whether the right DISCRETE lesions were found. These tests pin
the detection metric on synthetic masks with KNOWN true/false positives and
negatives, and lock two properties that make it trustworthy:
  - discrete lesions are counted with the SAME 18-connectivity as everywhere
    else in the app (RC-030), so detection and the reported lesion count agree;
  - the overlap gate and the empty-mask conventions behave as documented.
"""
import numpy as np
import pytest

from app.services.segmentation_comparison_service import (
    compute_lesion_detection_metrics,
    compare_two_masks,
)


def _mask(shape, voxels):
    m = np.zeros(shape, dtype=np.uint8)
    for v in voxels:
        m[v] = 1
    return m


SHAPE = (10, 10, 10)
# Three well-separated single-voxel lesions (>= 4 apart → distinct components).
L1, L2, L3 = (1, 1, 1), (1, 1, 5), (5, 5, 5)

# These fixtures exercise detection LOGIC (counting, matching, overlap gating,
# connectivity), not the sub-noise-floor filter. compute_lesion_detection_metrics
# floors sub-3mm3 PREDICTIONS as noise, so a single voxel at 1 mm iso (1 mm3)
# would be dropped from the prediction side. Score them at 1.5 mm iso where one
# voxel is 3.375 mm3 (> the 3 mm3 floor), so a single-voxel prediction survives
# and the tests measure the logic rather than the floor.
SPACING = (1.5, 1.5, 1.5)


class TestDetectionCounts:
    def test_perfect_match_is_f1_one(self):
        ref = _mask(SHAPE, [L1, L2, L3])
        pred = _mask(SHAPE, [L1, L2, L3])
        m = compute_lesion_detection_metrics(pred, ref, voxel_spacing=SPACING)
        assert (m["ref_lesion_count"], m["pred_lesion_count"]) == (3, 3)
        assert (m["true_positives"], m["false_positives"], m["false_negatives"]) == (3, 0, 0)
        assert m["sensitivity_ltpr"] == 1.0 and m["precision_lppv"] == 1.0 and m["lesion_f1"] == 1.0

    def test_missed_lesion_lowers_sensitivity_only(self):
        ref = _mask(SHAPE, [L1, L2, L3])   # 3 reference lesions
        pred = _mask(SHAPE, [L1, L2])      # found 2, missed 1
        m = compute_lesion_detection_metrics(pred, ref, voxel_spacing=SPACING)
        assert m["true_positives"] == 2 and m["false_negatives"] == 1 and m["false_positives"] == 0
        assert m["sensitivity_ltpr"] == round(2 / 3, 4)
        assert m["precision_lppv"] == 1.0  # every prediction was real

    def test_false_positive_lowers_precision_only(self):
        ref = _mask(SHAPE, [L1, L2])            # 2 reference lesions
        pred = _mask(SHAPE, [L1, L2, L3])       # 2 real + 1 spurious
        m = compute_lesion_detection_metrics(pred, ref, voxel_spacing=SPACING)
        assert m["true_positives"] == 2 and m["false_positives"] == 1 and m["false_negatives"] == 0
        assert m["sensitivity_ltpr"] == 1.0
        assert m["precision_lppv"] == round(2 / 3, 4)


class TestEmptyMaskConventions:
    def test_both_empty_agree_f1_one(self):
        z = _mask(SHAPE, [])
        m = compute_lesion_detection_metrics(z, z, voxel_spacing=SPACING)
        assert m["ref_lesion_count"] == 0 and m["pred_lesion_count"] == 0
        assert m["lesion_f1"] == 1.0  # they agree: no lesions

    def test_ref_empty_pred_populated_is_f1_zero(self):
        ref = _mask(SHAPE, [])
        pred = _mask(SHAPE, [L1])
        m = compute_lesion_detection_metrics(pred, ref, voxel_spacing=SPACING)
        assert m["false_positives"] == 1
        assert m["precision_lppv"] == 0.0 and m["lesion_f1"] == 0.0

    def test_ref_populated_pred_empty_is_f1_zero(self):
        ref = _mask(SHAPE, [L1])
        pred = _mask(SHAPE, [])
        m = compute_lesion_detection_metrics(pred, ref, voxel_spacing=SPACING)
        assert m["false_negatives"] == 1
        assert m["sensitivity_ltpr"] == 0.0 and m["lesion_f1"] == 0.0


class TestConnectivityConsistencyWithRC030:
    def test_edge_touching_voxels_are_one_lesion(self):
        """(1,1,1) and (2,2,1) differ in 2 axes (edge neighbour) → ONE 18-connected
        lesion, exactly as RC-030 counts them. If detection silently used a
        different connectivity, the count here would be 2."""
        ref = _mask(SHAPE, [(1, 1, 1), (2, 2, 1)])
        pred = _mask(SHAPE, [(1, 1, 1), (2, 2, 1)])
        m = compute_lesion_detection_metrics(pred, ref, voxel_spacing=SPACING)
        assert m["ref_lesion_count"] == 1 and m["pred_lesion_count"] == 1
        assert m["connectivity"] == 18
        assert m["lesion_f1"] == 1.0


class TestOverlapGate:
    def _partial(self):
        # One reference lesion of 4 face-connected voxels; prediction touches
        # only 1 of them → 25% coverage of the reference lesion.
        ref = _mask(SHAPE, [(1, 1, 1), (1, 1, 2), (1, 1, 3), (1, 1, 4)])
        pred = _mask(SHAPE, [(1, 1, 1)])
        return pred, ref

    def test_any_overlap_counts_as_detected_by_default(self):
        pred, ref = self._partial()
        m = compute_lesion_detection_metrics(pred, ref, voxel_spacing=SPACING)  # min_overlap_ratio=0.0
        assert m["ref_lesion_count"] == 1 and m["true_positives"] == 1
        assert m["sensitivity_ltpr"] == 1.0

    def test_strict_overlap_ratio_rejects_a_grazing_hit(self):
        pred, ref = self._partial()  # 25% coverage
        m = compute_lesion_detection_metrics(pred, ref, min_overlap_ratio=0.5, voxel_spacing=SPACING)
        assert m["true_positives"] == 0 and m["false_negatives"] == 1
        assert m["sensitivity_ltpr"] == 0.0


class TestWiredIntoCompareTwoMasks:
    def test_compare_two_masks_reports_lesion_detection(self):
        ref = _mask(SHAPE, [L1, L2, L3])
        pred = _mask(SHAPE, [L1, L2])
        out = compare_two_masks(pred, ref, voxel_spacing=SPACING)
        assert "lesion_detection" in out, "compare must surface detection metrics alongside Dice"
        ld = out["lesion_detection"]
        # B (ref) has 3, A (pred) has 2 → one missed.
        assert ld["ref_lesion_count"] == 3 and ld["pred_lesion_count"] == 2
        assert ld["sensitivity_ltpr"] == round(2 / 3, 4)
        # Dice (overlap) and F1 (detection) are DISTINCT axes, both present.
        assert "dice" in out and "lesion_f1" in ld
