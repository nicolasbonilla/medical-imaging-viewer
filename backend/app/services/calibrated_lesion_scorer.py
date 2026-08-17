"""Calibrated lesion scorer — the learned score behind CALM-MS Phase 2.

The conformal FDR layer only needs a score that RANKS true lesions above false
candidates; it makes no distributional assumption. So the whole job here is to
turn the per-lesion feature vector (`lesion_features`) into a score that separates
TP from FP far better than the base segmenter's pooled probability — which is
exactly what lifts the sensitivity-at-fixed-FDR operating point.

Design choices, all in service of a Class C, auditable, dependency-light module:
  * Regularised logistic regression (L2, balanced class weights) — deterministic
    full-batch gradient descent, no randomness, interpretable coefficients. With
    ~10 features and ~1e3 candidates it is the right capacity: enough to combine
    features, too small to overfit. A heavy model is neither needed nor honest at
    this N — the deep-ensemble signal enters as the `agreement` FEATURE instead.
  * Isotonic calibration (Pool-Adjacent-Violators) maps the logistic output to a
    calibrated probability for the UI confidence readout. It is monotone, so it
    does NOT change the ranking — the conformal selection is identical whether it
    sees the logit or the calibrated probability. Calibration is for display; the
    guarantee comes from the conformal layer.

Pure NumPy. `scikit-learn` is a dev-only import in this repo, never a production
dependency, so nothing here relies on it.
"""
from __future__ import annotations

import numpy as np


class StandardScaler:
    """Zero-mean, unit-variance per feature. Degenerate (zero-variance) columns
    are scaled by 1.0 so they pass through unchanged instead of exploding."""

    def fit(self, X):
        X = np.asarray(X, dtype=float)
        self.mean_ = X.mean(axis=0)
        scale = X.std(axis=0)
        scale[scale < 1e-12] = 1.0
        self.scale_ = scale
        return self

    def transform(self, X):
        return (np.asarray(X, dtype=float) - self.mean_) / self.scale_

    def fit_transform(self, X):
        return self.fit(X).transform(X)


def _sigmoid(z):
    # Numerically stable logistic.
    out = np.empty_like(z, dtype=float)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


class LogisticRegressionL2:
    """L2-regularised logistic regression via deterministic gradient descent.

    Balanced class weights counter the FP-heavy candidate mix so the minority true
    lesions are not ignored. No intercept regularisation. Deterministic: identical
    inputs give identical coefficients (reproducible for a medical record)."""

    def __init__(self, l2: float = 1.0, lr: float = 0.5, n_iter: int = 800,
                 class_weight: str | None = "balanced"):
        self.l2 = float(l2)
        self.lr = float(lr)
        self.n_iter = int(n_iter)
        self.class_weight = class_weight

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        n, d = X.shape
        w = np.zeros(d, dtype=float)
        b = 0.0

        if self.class_weight == "balanced":
            n_pos = max(1.0, float((y == 1).sum()))
            n_neg = max(1.0, float((y == 0).sum()))
            sw = np.where(y == 1, n / (2.0 * n_pos), n / (2.0 * n_neg))
        else:
            sw = np.ones(n, dtype=float)
        sw_sum = float(sw.sum())

        for _ in range(self.n_iter):
            p = _sigmoid(X @ w + b)
            resid = sw * (p - y)
            grad_w = (X.T @ resid) / sw_sum + self.l2 * w / n
            grad_b = float(resid.sum()) / sw_sum
            w -= self.lr * grad_w
            b -= self.lr * grad_b
        self.coef_ = w
        self.intercept_ = b
        return self

    def decision_function(self, X):
        return np.asarray(X, dtype=float) @ self.coef_ + self.intercept_

    def predict_proba(self, X):
        return _sigmoid(self.decision_function(X))


class IsotonicCalibrator:
    """Monotone (non-decreasing) probability calibration via Pool-Adjacent-
    Violators. Fit on (raw score, label); `transform` interpolates. Monotone, so
    it preserves ranking — safe to feed the conformal layer."""

    def fit(self, scores, y):
        scores = np.asarray(scores, dtype=float).ravel()
        y = np.asarray(y, dtype=float).ravel()
        if scores.size == 0:
            self.x_ = np.array([0.0, 1.0])
            self.y_ = np.array([0.0, 1.0])
            return self
        order = np.argsort(scores, kind="mergesort")
        xs = scores[order]
        ys = y[order]

        # PAVA: maintain blocks of (weighted mean value, weight), merging any
        # block that violates monotonicity with its predecessor.
        vals = list(ys.astype(float))
        wts = [1.0] * len(vals)
        i = 0
        while i < len(vals) - 1:
            if vals[i] > vals[i + 1] + 1e-12:
                new_w = wts[i] + wts[i + 1]
                new_v = (vals[i] * wts[i] + vals[i + 1] * wts[i + 1]) / new_w
                vals[i] = new_v
                wts[i] = new_w
                del vals[i + 1]
                del wts[i + 1]
                # Also merge xs so block boundaries stay aligned.
                xs = np.delete(xs, i + 1)
                if i > 0:
                    i -= 1
            else:
                i += 1

        # Expand block values back to per-boundary knots for interpolation.
        self.x_ = xs
        self.y_ = np.clip(np.asarray(vals, dtype=float), 0.0, 1.0)
        return self

    def transform(self, scores):
        scores = np.asarray(scores, dtype=float).ravel()
        if self.x_.size == 1:
            return np.full(scores.shape, float(self.y_[0]))
        return np.interp(scores, self.x_, self.y_)


class CalibratedLesionScorer:
    """Standardise -> logistic -> isotonic. `score(X)` returns a calibrated
    probability that a candidate is a true lesion; because isotonic is monotone,
    that probability ranks candidates identically to the logistic decision
    function, so it is exactly what the conformal layer consumes."""

    def __init__(self, l2: float = 1.0, lr: float = 0.5, n_iter: int = 800):
        self.scaler = StandardScaler()
        self.logreg = LogisticRegressionL2(l2=l2, lr=lr, n_iter=n_iter)
        self.calibrator = IsotonicCalibrator()

    def fit(self, X, y):
        Xs = self.scaler.fit_transform(X)
        self.logreg.fit(Xs, y)
        raw = self.logreg.decision_function(Xs)
        self.calibrator.fit(raw, y)
        return self

    def decision_function(self, X):
        return self.logreg.decision_function(self.scaler.transform(X))

    def score(self, X):
        return self.calibrator.transform(self.decision_function(X))
