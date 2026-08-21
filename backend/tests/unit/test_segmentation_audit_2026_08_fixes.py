"""Regression tests for the 2026-08-21 adversarial segmentation audit fixes (findings #2, #5).

Each pins a fix so the Class C defect cannot return:
  #2 DIS zone classification must use the MAGNIMS CONTACT criterion (priority IT>PV>JC), not
     majority vote — else a periventricular lesion that is bulk deep-WM is undercalled and DIS
     can flip met->not-met (false-negative MS diagnosis).
  #5 lesion-detection metrics must apply the same 3mm3 noise floor as the clinical count — else
     sub-floor specks inflate the predicted lesion count and the false-positive rate.
"""
import numpy as np


def test_zone_classification_uses_contact_priority_not_majority():
    from app.services.ms_region_classifier import classify_from_zone_mask
    shape = (12, 12, 12)
    lesion = np.zeros(shape, np.uint8)
    zone = np.zeros(shape, np.uint8)
    # one contiguous lesion (5x5x2 = 50 voxels); bulk in deep white matter (zone 4) with a
    # small periventricular CONTACT corner (zone 1). Majority -> DWM; contact -> PV.
    lesion[3:8, 3:8, 4:6] = 1
    zone[lesion > 0] = 4                 # bulk = deep white matter
    zone[3:5, 3:5, 4] = 1               # 4-voxel periventricular contact (inside the lesion)
    res = classify_from_zone_mask(lesion, zone, (1.0, 1.0, 1.0))
    dets = res["lesions"]
    assert len(dets) == 1
    assert dets[0]["region_id"] == 1, f"expected Periventricular (contact), got {dets[0]['region']}"


def test_lesion_detection_applies_the_3mm3_noise_floor():
    from app.services.segmentation_comparison_service import compute_lesion_detection_metrics
    shape = (24, 24, 24)
    ref = np.zeros(shape, np.uint8)
    pred = np.zeros(shape, np.uint8)
    # one real, matched lesion (4x4x4 = 64 voxels >= floor)
    ref[5:9, 5:9, 5:9] = 1
    pred[5:9, 5:9, 5:9] = 1
    # a sub-3mm3 speck (2 voxels) only in pred -> must be DROPPED, not counted as a false positive
    pred[18, 18, 18] = 1
    pred[18, 18, 19] = 1
    m = compute_lesion_detection_metrics(pred, ref, voxel_spacing=(1.0, 1.0, 1.0))
    assert m["pred_lesion_count"] == 1, m           # speck floored out
    assert m["false_positives"] == 0
    assert m["ref_lesion_count"] == 1
