"""Regression tests for the bugs found by the 2026-08-17 adversarial verification
of the CALM-MS conformal second-reader. Each test pins a fix so the bug cannot
return (HAZ-CALM-6, HAZ-CALM-7 + hardening).
"""
import json
import os
import tempfile

import numpy as np
import pytest

from app.services.conformal_lesion_fdr import conformal_pvalues
from app.services.calm_ms_inference import extract_lesion_candidates
from app.services.conformal_null_asset import (
    load_null_asset, ConformalAssetError, ProvenanceMismatch, get_null_asset,
    EXPECTED_BASE_MODEL,
)

SP = (1.0, 1.0, 1.0)


# ---- HAZ-CALM-7: non-finite inputs must fail closed everywhere -----------------

def test_extract_rejects_non_finite():
    p = np.full((10, 10, 10), 0.8, dtype=np.float32)
    p[0, 0, 0] = np.nan
    with pytest.raises(ValueError):
        extract_lesion_candidates(p, 0.5, SP, min_volume_mm3=3)
    p[0, 0, 0] = np.inf
    with pytest.raises(ValueError):
        extract_lesion_candidates(p, 0.5, SP, min_volume_mm3=3)


def test_conformal_pvalues_rejects_non_finite():
    calib = np.linspace(0.1, 0.9, 50)
    with pytest.raises(ValueError):
        conformal_pvalues(np.array([0.5, np.nan]), calib)
    with pytest.raises(ValueError):
        conformal_pvalues(np.array([0.5, np.inf]), calib)
    with pytest.raises(ValueError):
        conformal_pvalues(np.array([0.5]), np.array([0.1, np.nan, 0.3]))


def test_conformal_review_rejects_non_finite():
    """The HIGH fail-open: a NaN voxel must not slip past the [0,1] gate."""
    try:
        asset = get_null_asset()
    except ConformalAssetError:
        pytest.skip("null asset not built")
    from app.services.conformal_review_service import conformal_review
    p = np.full(asset.grid_shape, 0.02, dtype=np.float32)
    p[0, 0, 0] = np.nan
    with pytest.raises(ValueError):
        conformal_review(p, SP, "balanced")
    p[0, 0, 0] = np.inf
    with pytest.raises(ValueError):
        conformal_review(p, SP, "balanced")


# ---- HAZ-CALM-6: bad null asset must fail closed at load -----------------------

def _write_null(tmp, scores, base_model=EXPECTED_BASE_MODEL, grid=(182, 218, 182),
                base_model_independent=True):
    prov = {
        "base_model": base_model, "version": "test", "threshold": 0.5,
        "min_volume_mm3": 3.0, "voxel_spacing": [1.0, 1.0, 1.0], "grid_shape": list(grid),
        "base_model_independent": base_model_independent,
    }
    path = os.path.join(tmp, "null.npz")
    np.savez_compressed(path, null_scores=np.asarray(scores, dtype=np.float32),
                        provenance=json.dumps(prov))
    return path


def test_load_rejects_wrong_base_model():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_null(tmp, np.linspace(0.1, 0.9, 200), base_model="EvilNet-v9")
        with pytest.raises(ConformalAssetError):
            load_null_asset(path)


def test_load_rejects_degenerate_null():
    with tempfile.TemporaryDirectory() as tmp:
        # constant null -> every score maps to the same tiny p -> selects everything
        path = _write_null(tmp, np.full(200, 0.5, dtype=np.float32))
        with pytest.raises(ConformalAssetError):
            load_null_asset(path)


def test_load_rejects_empty_null():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_null(tmp, np.zeros(0, dtype=np.float32))
        with pytest.raises(ConformalAssetError):
            load_null_asset(path)


# ---- spacing-length hardening --------------------------------------------------

def test_assert_compatible_rejects_short_spacing():
    try:
        asset = get_null_asset()
    except ConformalAssetError:
        pytest.skip("null asset not built")
    with pytest.raises(ProvenanceMismatch):
        asset.assert_compatible(asset.grid_shape, (1.0, 1.0))   # only 2 spacings


def test_real_asset_still_loads():
    """The shipped v1 asset must pass all the new gates."""
    try:
        a = get_null_asset()
    except ConformalAssetError:
        pytest.skip("null asset not built")
    assert a.provenance["base_model"] == EXPECTED_BASE_MODEL
    assert np.unique(a.null_scores).size >= 20 and float(np.std(a.null_scores)) >= 1e-3


# ---- contamination gate: a null not stamped base_model_independent must fail closed --

def test_load_rejects_null_not_marked_base_model_independent():
    """A null whose cohorts might overlap the base model's training set (non-exchangeable
    false-candidate scores) must be refused unless explicitly stamped independent."""
    with tempfile.TemporaryDirectory() as tmp:
        good = np.linspace(0.1, 0.9, 200)
        # flag missing -> refuse
        path = _write_null(tmp, good, base_model_independent=None)
        # None serializes to JSON null; provenance.get(...) is not True -> ConformalAssetError
        with pytest.raises(ConformalAssetError):
            load_null_asset(path)
        # flag explicitly False -> refuse
        path2 = _write_null(tmp, good, base_model_independent=False)
        with pytest.raises(ConformalAssetError):
            load_null_asset(path2)


def test_shipped_provenance_is_honest_about_acquisition():
    """The shipped null must NOT claim single-site/1.5T (MSLesSeg is multi-center) and
    MUST be stamped base_model_independent. Pins the 2026-08-21 honesty correction."""
    try:
        a = get_null_asset()
    except ConformalAssetError:
        pytest.skip("null asset not built")
    prov = a.provenance
    assert prov.get("base_model_independent") is True
    # the false "single_site: Catania 1.5T" claim must be gone
    assert "single_site" not in prov
    blob = json.dumps(prov).lower()
    assert "single-site" not in blob and "1.5t" not in blob
    # and the honest multi-center scope must be recorded
    assert "multi-center" in prov.get("acquisition_scope", "").lower()
