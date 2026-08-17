"""CALM-MS Phase 2 — the calibrated lesion scorer (pure-NumPy learned score).

Covers the three pieces the conformal layer relies on: standardisation that
survives a degenerate feature, an L2 logistic that separates and respects class
imbalance, and a monotone isotonic calibration that preserves ranking while
producing probabilities.
"""
import numpy as np

from app.services.calibrated_lesion_scorer import (
    StandardScaler,
    LogisticRegressionL2,
    IsotonicCalibrator,
    CalibratedLesionScorer,
)


def test_standard_scaler_passes_zero_variance_column():
    X = np.array([[1.0, 5.0], [3.0, 5.0], [5.0, 5.0]])  # 2nd col constant
    sc = StandardScaler().fit(X)
    Z = sc.transform(X)
    assert np.isfinite(Z).all()            # constant column must not blow up
    assert np.allclose(Z[:, 1], 0.0)       # centered to zero, scale forced to 1
    assert abs(Z[:, 0].std() - 1.0) < 1e-9


def test_logistic_separates_linearly_separable():
    rng = np.random.default_rng(0)
    pos = rng.normal(2.0, 0.4, size=(60, 2))
    neg = rng.normal(-2.0, 0.4, size=(60, 2))
    X = np.vstack([pos, neg])
    y = np.concatenate([np.ones(60), np.zeros(60)])
    clf = LogisticRegressionL2(l2=0.01, n_iter=1000).fit(X, y)
    acc = ((clf.predict_proba(X) >= 0.5) == (y == 1)).mean()
    assert acc == 1.0


def test_logistic_balanced_weights_learn_minority():
    rng = np.random.default_rng(1)
    neg = rng.normal(-1.5, 0.5, size=(180, 1))     # 90% negatives
    pos = rng.normal(1.5, 0.5, size=(20, 1))       # 10% positives
    X = np.vstack([neg, pos])
    y = np.concatenate([np.zeros(180), np.ones(20)])
    clf = LogisticRegressionL2(l2=0.01, n_iter=1000, class_weight="balanced").fit(X, y)
    # A clearly-positive point is still called positive despite the imbalance.
    assert clf.predict_proba(np.array([[2.0]]))[0] > 0.5


def test_isotonic_is_monotone_and_calibrates():
    rng = np.random.default_rng(2)
    s = np.linspace(0, 1, 200)
    y = (rng.uniform(size=200) < s).astype(float)   # P(y=1) increases with s
    iso = IsotonicCalibrator().fit(s, y)
    grid = np.linspace(0, 1, 50)
    out = iso.transform(grid)
    assert np.all(np.diff(out) >= -1e-9)            # non-decreasing
    assert out.min() >= 0.0 and out.max() <= 1.0
    assert out[-1] > out[0]                          # actually rises


def test_calibrated_scorer_ranks_and_bounds():
    rng = np.random.default_rng(3)
    Xpos = rng.normal(1.5, 0.5, size=(80, 3))
    Xneg = rng.normal(-1.5, 0.5, size=(80, 3))
    X = np.vstack([Xpos, Xneg])
    y = np.concatenate([np.ones(80), np.zeros(80)])
    scorer = CalibratedLesionScorer(l2=0.05, n_iter=1000).fit(X, y)
    s = scorer.score(X)
    assert s.min() >= 0.0 and s.max() <= 1.0
    assert s[:80].mean() > s[80:].mean()            # positives rank above negatives
