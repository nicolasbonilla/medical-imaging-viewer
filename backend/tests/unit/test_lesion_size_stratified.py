"""Size-stratified detection sensitivity + explicit LFPR.

A single lesion-wise LTPR averages over lesion sizes and hides that SMALL lesions are
systematically missed — the clinically important gap (FLAMeS 2025: ~35% detection for
3-10 mm³ vs ~81% for >10 mm³). compute_lesion_detection_metrics now reports LTPR per
reference-lesion size band, plus LFPR (fraction of predicted lesions that are false
positives) explicitly.
"""
import numpy as np

from app.services.segmentation_comparison_service import compute_lesion_detection_metrics


def _place(vol, z, y, x, shape):
    """Place a contiguous (18-connected) block of the given shape → one lesion."""
    dz, dy, dx = shape
    vol[z:z + dz, y:y + dy, x:x + dx] = 1
    return vol


def _masks():
    """ref has 3 well-separated lesions of distinct sizes; pred detects the two larger
    ones and MISSES the smallest — the small-lesion failure the stratification must expose."""
    ref = np.zeros((32, 32, 32), np.uint8)
    _place(ref, 2, 2, 2, (1, 1, 2))    # 2 voxels  -> <3
    _place(ref, 10, 10, 10, (1, 1, 5)) # 5 voxels  -> 3-10
    _place(ref, 20, 20, 20, (5, 5, 2)) # 50 voxels -> 30-100
    pred = np.zeros((32, 32, 32), np.uint8)
    _place(pred, 10, 10, 10, (1, 1, 5))  # detects the 3-10 lesion
    _place(pred, 20, 20, 20, (5, 5, 2))  # detects the 30-100 lesion
    _place(pred, 28, 28, 28, (1, 1, 4))  # a FALSE POSITIVE (no ref lesion here)
    return pred, ref


def test_size_stratified_sensitivity_exposes_missed_small_lesion():
    pred, ref = _masks()
    m = compute_lesion_detection_metrics(pred, ref, voxel_spacing=(1.0, 1.0, 1.0))
    sss = m["size_stratified_sensitivity"]
    assert sss["unit"] == "mm3"
    by = {b["bucket"]: b for b in sss["buckets"]}
    # smallest lesion missed → 0% detection in its band; larger bands 100%
    assert by["<3mm3 (sub-floor)"]["n_ref"] == 1 and by["<3mm3 (sub-floor)"]["detected"] == 0
    assert by["<3mm3 (sub-floor)"]["sensitivity_ltpr"] == 0.0
    assert by["3-10mm3"]["sensitivity_ltpr"] == 1.0
    assert by["30-100mm3"]["sensitivity_ltpr"] == 1.0
    # empty band → LTPR is None (not a misleading 0 or 1)
    assert by["10-30mm3"]["n_ref"] == 0 and by["10-30mm3"]["sensitivity_ltpr"] is None
    # overall LTPR is the average that hides the small-lesion miss (2/3); the metric
    # rounds to 4 dp, so compare at that precision.
    assert m["sensitivity_ltpr"] == round(2 / 3, 4)


def test_lfpr_reported_explicitly():
    pred, ref = _masks()
    m = compute_lesion_detection_metrics(pred, ref)
    # 3 predicted lesions, 1 is a false positive → LFPR = 1/3
    assert m["pred_lesion_count"] == 3
    assert m["false_positives"] == 1
    assert abs(m["false_positive_rate_lfpr"] - 1 / 3) < 1e-4
    # LFPR == 1 - precision (LPPV)
    assert abs(m["false_positive_rate_lfpr"] - (1 - m["precision_lppv"])) < 1e-4


def test_no_spacing_reports_voxel_units_not_mm3():
    pred, ref = _masks()
    m = compute_lesion_detection_metrics(pred, ref)  # no voxel_spacing
    assert m["size_stratified_sensitivity"]["unit"] == "voxels"
    assert all("vox" in b["bucket"] for b in m["size_stratified_sensitivity"]["buckets"])


def test_lfpr_zero_when_nothing_predicted():
    ref = _place(np.zeros((16, 16, 16), np.uint8), 4, 4, 4, (2, 2, 2))
    empty = np.zeros((16, 16, 16), np.uint8)
    m = compute_lesion_detection_metrics(empty, ref)
    assert m["false_positive_rate_lfpr"] == 0.0
