"""CALM-MS out-of-distribution monitor (RC-CALM-5, 2nd axis). Verifies the monitor
flags gross score-distribution shift and that conformal_review WITHHOLDS the
guarantee (fail closed) on an OOD case while still returning the additive tiers.
"""
import numpy as np
import pytest

from app.services.conformal_ood import assess_ood, case_features, _mahalanobis, OOD_THRESHOLD
from app.services.conformal_null_asset import get_null_asset, ConformalAssetError

try:
    _ASSET = get_null_asset()
    _REF = _ASSET.ood_reference
    _GRID = _ASSET.grid_shape
    _OK = _REF is not None
except ConformalAssetError:
    _OK = False

pytestmark = pytest.mark.skipif(not _OK, reason="null asset / OOD reference not built")


def test_center_is_in_distribution():
    # The calibration median feature vector is the envelope centre: distance ~0.
    med = np.median(_REF, axis=0)
    assert _mahalanobis(med, _REF) < OOD_THRESHOLD


def test_specificity_most_calibration_cases_in_distribution():
    # Leave-one-out: the validated statistic must NOT flag the bulk of the 145
    # legitimate in-distribution cases (validation measured ~2% false-OOD at thr 5).
    flagged = sum(
        _mahalanobis(_REF[i], np.delete(_REF, i, axis=0)) > OOD_THRESHOLD
        for i in range(_REF.shape[0])
    )
    assert flagged / _REF.shape[0] <= 0.05


def test_gross_score_shift_is_ood():
    # FP-shifted / wrong-regime: many candidates all near the 0.5 floor.
    v = assess_ood(np.full(60, 0.52), _REF)
    assert v.is_ood is True and v.distance > OOD_THRESHOLD


def test_no_reference_fails_closed():
    v = assess_ood(np.full(10, 0.9), None)
    assert v.is_ood is True   # never claim in-distribution without evidence


def test_no_candidates_guarantee_trivially_applies():
    v = assess_ood(np.array([]), _REF)
    assert v.is_ood is False


def _ball(shape, c, r):
    zz, yy, xx = np.ogrid[:shape[0], :shape[1], :shape[2]]
    return (zz - c[0]) ** 2 + (yy - c[1]) ** 2 + (xx - c[2]) ** 2 <= r ** 2


def test_conformal_review_withholds_guarantee_on_ood_but_keeps_tiers():
    from app.services.conformal_review_service import conformal_review, WITHHELD_SCOPE
    # ~30 low-score blobs (mean ~0.52) => grossly OOD vs FLAMeS calibration (~0.94).
    p = np.full(_GRID, 0.02, dtype=np.float32)
    n = 0
    for z in range(30, 150, 20):
        for y in range(30, 200, 30):
            core = _ball(_GRID, (z, y, 90), 3)
            p[core] = 0.52
            n += 1
            if n >= 30:
                break
        if n >= 30:
            break
    r = conformal_review(p, (1.0, 1.0, 1.0), "balanced")
    assert r.guarantee_applicable is False           # guarantee withheld
    assert r.guarantee_scope == WITHHELD_SCOPE
    assert r.ood is not None and r.ood.is_ood is True
    assert len(r.lesions) >= 1                        # additive: tiers still shown
    s = r.summary()
    assert s["guarantee_applicable"] is False and s["ood"]["is_ood"] is True
