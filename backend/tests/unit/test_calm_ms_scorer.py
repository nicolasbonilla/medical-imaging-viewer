"""CALM-MS v2 learned lesion scorer + shared feature extractor.

Verifies: (1) the inference-time feature matrix is deterministic and shaped to the
contract; (2) the pure-NumPy scorer forward pass is mathematically correct and fails
closed on bad input/asset; (3) if the frozen asset is present, it loads, its provenance
matches the code's FEATURE_NAMES, and scores are valid probabilities.
"""
import json

import numpy as np
import pytest

from app.services.calm_ms_lesion_features import (
    FEATURE_NAMES, candidate_feature_matrix, PROB_FEATURES, MORPH_FEATURES, LOC_FEATURES,
)
from app.services.calm_ms_scorer import LesionScorer, LesionScorerError, load_lesion_scorer
from app.services.calm_ms_inference import extract_lesion_candidates


def _ball(shape, c, r):
    zz, yy, xx = np.ogrid[:shape[0], :shape[1], :shape[2]]
    return (zz - c[0]) ** 2 + (yy - c[1]) ** 2 + (xx - c[2]) ** 2 <= r ** 2


def test_feature_layout_is_contractual():
    assert FEATURE_NAMES == PROB_FEATURES + MORPH_FEATURES + LOC_FEATURES
    assert len(FEATURE_NAMES) == 14


def test_feature_matrix_shape_and_determinism():
    shape = (60, 60, 60)
    p = np.full(shape, 0.02, dtype=np.float32)
    for c in [(20, 20, 20), (40, 40, 40)]:
        p[_ball(shape, c, 3)] = 0.9
    labeled, cands = extract_lesion_candidates(p, 0.5, (1.0, 1.0, 1.0))
    fm1 = candidate_feature_matrix(p, labeled, cands)
    fm2 = candidate_feature_matrix(p, labeled, cands)
    assert fm1.shape == (len(cands), 14)
    assert np.array_equal(fm1, fm2)                 # deterministic
    assert np.isfinite(fm1).all()


def _toy_scorer(d=14):
    """A tiny linear (degree-1) scorer with known params for exact-math testing."""
    rng = np.random.RandomState(0)
    powers = np.eye(d, dtype=int)                   # one linear term per feature
    coef = rng.randn(d)
    mean = rng.randn(d); std = np.abs(rng.randn(d)) + 0.5
    return LesionScorer(tuple(FEATURE_NAMES), mean, std, powers, coef, 0.3, {"asset": "toy"})


def test_forward_pass_matches_hand_computation():
    s = _toy_scorer()
    X = np.random.RandomState(1).randn(5, 14)
    z = (X - s.mean) / s.std
    expected = 1.0 - 1.0 / (1.0 + np.exp(-(z @ s.coef + s.intercept)))
    assert np.allclose(s.score(X), expected, atol=1e-12)
    assert np.all((s.score(X) >= 0) & (s.score(X) <= 1))


def test_scorer_fails_closed_on_bad_input():
    s = _toy_scorer()
    with pytest.raises(LesionScorerError):
        s.score(np.zeros((3, 5)))                   # wrong feature count
    with pytest.raises(LesionScorerError):
        s.score(np.array([[np.nan] * 14]))          # non-finite -> fail closed


def test_missing_asset_fails_closed():
    with pytest.raises(LesionScorerError):
        load_lesion_scorer("does_not_exist_calm_scorer.npz")


# --- asset-dependent (skip cleanly if not built) ---
try:
    _SCORER = load_lesion_scorer()
except LesionScorerError:
    _SCORER = None


@pytest.mark.skipif(_SCORER is None, reason="frozen lesion-scorer asset not built")
def test_frozen_asset_provenance_and_scores():
    assert _SCORER.feature_names == tuple(FEATURE_NAMES)
    prov = _SCORER.provenance
    assert prov["base_model"] == "FLAMeS" and prov["degree"] == 2
    # score a couple of synthetic candidates -> valid probabilities
    shape = (60, 60, 60)
    p = np.full(shape, 0.02, dtype=np.float32)
    p[_ball(shape, (30, 30, 30), 4)] = 0.95
    labeled, cands = extract_lesion_candidates(p, 0.5, (1.0, 1.0, 1.0))
    sc = _SCORER.score(candidate_feature_matrix(p, labeled, cands))
    assert sc.shape == (len(cands),)
    assert np.all((sc >= 0) & (sc <= 1))
