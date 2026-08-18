"""CALM-MS v2 — the frozen, transparent learned lesion scorer.

Loads a versioned, provenance-stamped asset (built by
scripts/calm-ms/build_lesion_scorer_asset.py) and turns a per-candidate feature matrix
into a learned score in [0, 1] (higher = more likely a TRUE lesion). The score replaces
raw pooled probability as the conformal statistic, restoring TP/FP separability under the
confident-false-positive scanner shift that breaks raw probability
(docs/calm-ms/v2-learned-scorer-result.md).

DELIBERATELY TRANSPARENT for a Class C device: the model is a degree-2 polynomial
logistic regression whose parameters are stored as PLAIN ARRAYS (feature means/stds, a
monomial-exponent matrix, coefficients, intercept) — NOT a pickled estimator. The forward
pass here is pure NumPy and re-derivable by hand; there is no third-party model runtime to
trust or version-match, and no arbitrary-code-execution surface from unpickling.

Fails closed: if the asset is missing/malformed, `load_lesion_scorer()` raises and the
caller must withhold the learned-score path (never silently fall back to a different
statistic than the null was built against).
"""
from __future__ import annotations

import os
import json
from dataclasses import dataclass

import numpy as np

from app.services.calm_ms_lesion_features import FEATURE_NAMES

_ASSET = os.path.join(os.path.dirname(__file__), "assets", "calm_ms_lesion_scorer_v1.npz")


class LesionScorerError(RuntimeError):
    """Raised when the scorer asset is missing, malformed, or provenance-inconsistent."""


@dataclass(frozen=True)
class LesionScorer:
    feature_names: tuple
    mean: np.ndarray          # (d,)
    std: np.ndarray           # (d,)
    powers: np.ndarray        # (n_terms, d) non-negative integer exponents
    coef: np.ndarray          # (n_terms,)
    intercept: float
    provenance: dict

    def score(self, feature_matrix: np.ndarray) -> np.ndarray:
        """Learned score in [0, 1] per candidate (higher = more likely TRUE lesion).

        Pure-NumPy replica of PolynomialFeatures(degree=2) + LogisticRegression on
        standardized features: standardize -> monomial expansion via `powers` ->
        linear -> sigmoid -> 1 - P(false). Fails closed on non-finite input."""
        X = np.asarray(feature_matrix, dtype=float)
        if X.ndim != 2 or X.shape[1] != len(self.feature_names):
            raise LesionScorerError(
                f"feature matrix has shape {X.shape}, expected (*, {len(self.feature_names)})")
        if X.size and not np.isfinite(X).all():
            raise LesionScorerError("non-finite features — refusing to score (fail closed)")
        z = (X - self.mean) / self.std                       # (n, d)
        # monomial terms: for each term t, prod_j z[:, j] ** powers[t, j]
        terms = np.prod(z[:, None, :] ** self.powers[None, :, :], axis=2)   # (n, n_terms)
        logit = terms @ self.coef + self.intercept
        p_false = 1.0 / (1.0 + np.exp(-logit))
        return 1.0 - p_false


def load_lesion_scorer(path: str = _ASSET) -> LesionScorer:
    if not os.path.exists(path):
        raise LesionScorerError(f"lesion scorer asset not found: {path}")
    try:
        d = np.load(path, allow_pickle=False)
        prov = json.loads(str(d["provenance"]))
        mean, std = np.asarray(d["mean"], float), np.asarray(d["std"], float)
        powers_raw = np.asarray(d["powers"])
        coef = np.asarray(d["coef"], float)
        intercept = float(d["intercept"])
        names = tuple(prov.get("feature_names", []))
    except Exception as e:                                    # malformed asset
        raise LesionScorerError(f"malformed lesion scorer asset: {e}") from e
    # powers must be genuinely integer exponents — a silent float->int truncation
    # (e.g. 1.9 -> 1) would corrupt the monomial expansion.
    if not np.allclose(powers_raw, np.round(powers_raw)):
        raise LesionScorerError("scorer powers are not integer exponents")
    powers = np.round(powers_raw).astype(int)
    # provenance + shape invariants (fail closed on any mismatch)
    if names != tuple(FEATURE_NAMES):
        raise LesionScorerError("scorer feature_names do not match the code's FEATURE_NAMES")
    d_feat = len(FEATURE_NAMES)
    if mean.shape != (d_feat,) or std.shape != (d_feat,) or powers.shape[1] != d_feat:
        raise LesionScorerError("scorer parameter shapes inconsistent with feature layout")
    if powers.shape[0] != coef.shape[0] or coef.ndim != 1:
        raise LesionScorerError("scorer coef/powers length mismatch")
    if coef.shape[0] == 0 or powers.shape[0] == 0:
        # An empty coefficient block passes every shape check but degrades the scorer to a
        # constant 1 - sigmoid(intercept) for EVERY candidate — a silent total loss of
        # TP/FP separation. Refuse it (fail closed).
        raise LesionScorerError("empty scorer model (no terms) — refusing to load")
    if not (np.isfinite(mean).all() and np.isfinite(std).all()
            and np.isfinite(coef).all() and np.isfinite(intercept) and (std > 0).all()):
        raise LesionScorerError("scorer parameters non-finite or degenerate")
    return LesionScorer(tuple(FEATURE_NAMES), mean, std, powers, coef, intercept, prov)
