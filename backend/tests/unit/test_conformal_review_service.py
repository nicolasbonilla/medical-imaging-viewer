"""CALM-MS second-reader review core (REQ-FUNC-CALM-001) — the risk controls the
adversarial Class C review demanded, verified as behaviour.

Uses the shipped frozen null asset (backend/app/services/assets/…). Skips cleanly
if the asset has not been built, so CI without the asset does not hard-fail.
"""
import numpy as np
import pytest

from app.services.conformal_null_asset import (
    get_null_asset, ConformalAssetError, ProvenanceMismatch, PRESETS, DEFAULT_PRESET,
)

try:
    _ASSET = get_null_asset()
    _GRID = _ASSET.grid_shape
except ConformalAssetError:
    _ASSET = None

pytestmark = pytest.mark.skipif(_ASSET is None, reason="CALM-MS null asset not built")

from app.services.conformal_review_service import (  # noqa: E402
    conformal_review, GUARANTEE_SCOPE, TIER_HIGH, TIER_MEDIUM, TIER_LOW,
)


def _ball(shape, center, radius):
    zz, yy, xx = np.ogrid[:shape[0], :shape[1], :shape[2]]
    d2 = (zz - center[0]) ** 2 + (yy - center[1]) ** 2 + (xx - center[2]) ** 2
    return d2 <= radius ** 2


def _synthetic_prob():
    """A probability volume on the null's exact grid with a few confident blobs."""
    p = np.full(_GRID, 0.02, dtype=np.float32)
    for c, val in [((60, 90, 90), 0.95), ((60, 130, 90), 0.80), ((90, 90, 120), 0.62)]:
        core = _ball(_GRID, c, 3)
        p[core] = val
    return p


def test_asset_has_expected_provenance():
    prov = _ASSET.provenance
    assert prov["base_model"] == "FLAMeS"
    assert _ASSET.null_scores.size > 0
    assert _ASSET.threshold == 0.5
    assert tuple(_ASSET.voxel_spacing) == (1.0, 1.0, 1.0)


def test_review_is_additive_and_tiered():
    r = conformal_review(_synthetic_prob(), (1.0, 1.0, 1.0), preset="high_sensitivity")
    assert r.preset == "high_sensitivity"
    assert r.fdr_target == PRESETS["high_sensitivity"]
    # additive: every candidate is returned + painted (nothing removed)
    assert len(r.lesions) >= 1
    assert int((r.status_mask > 0).sum()) > 0
    assert set(np.unique(r.status_mask)).issubset({0, 1, 2, 3})
    # tiers are ordinal labels, never numbers
    for les in r.lesions:
        assert les.review_priority in (TIER_HIGH, TIER_MEDIUM, TIER_LOW)


def test_no_probability_or_realized_fdr_leaks_into_output():
    """RC-CALM-2/3: no per-lesion 'confidence' %, no per-scan realized FDR."""
    r = conformal_review(_synthetic_prob(), (1.0, 1.0, 1.0))
    s = r.summary()
    assert "guarantee_scope" in s and "population-level" in s["guarantee_scope"].lower()
    assert "realized" not in str(s).lower()          # no realized FDP anywhere
    for les in s["lesions"]:
        assert "confidence" not in les               # never a confidence field
        assert not any(isinstance(v, float) and 0.0 < v < 1.0 and k not in ("volume_mm3",)
                       for k, v in les.items())       # no bare 0..1 "probability" per lesion


def test_preset_monotonicity_fdr_set():
    """A stricter preset (lower alpha) selects a subset — and NOTHING is dropped
    from the candidate list (still additive)."""
    p = _synthetic_prob()
    hs = conformal_review(p, (1.0, 1.0, 1.0), "high_sensitivity")
    hp = conformal_review(p, (1.0, 1.0, 1.0), "high_precision")
    assert len(hs.lesions) == len(hp.lesions)        # same candidates shown (additive)
    n_hs = sum(1 for x in hs.lesions if x.in_fdr_set)
    n_hp = sum(1 for x in hp.lesions if x.in_fdr_set)
    assert n_hp <= n_hs                               # stricter -> not more in the FDR set


def test_fail_closed_provenance_mismatch():
    """RC-CALM-5: a map off the calibration grid is REFUSED, not scored."""
    bad = np.zeros((100, 100, 100), dtype=np.float32)
    with pytest.raises(ProvenanceMismatch):
        conformal_review(bad, (1.0, 1.0, 1.0))


def test_reject_unknown_preset_and_bad_prob():
    p = _synthetic_prob()
    with pytest.raises(KeyError):
        conformal_review(p, (1.0, 1.0, 1.0), preset="ultra")   # raw/unknown preset refused
    bad = p.copy(); bad[0, 0, 0] = 5.0
    with pytest.raises(ValueError):
        conformal_review(bad, (1.0, 1.0, 1.0))                 # out-of-range prob refused
