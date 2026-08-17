"""CALM-MS out-of-distribution monitor (RC-CALM-5, second control axis).

The adversarial verification proved that the grid/spacing provenance check is
necessary but NOT sufficient for exchangeability: a probability map on the correct
grid but from a different scanner/regime (an "on-grid OOD" case) silently voids the
conformal FDR guarantee (realized FDR up to ~8x the target). This module adds the
missing distribution check.

Approach (v1, deliberately simple + auditable): summarise the incoming case by
features computable at inference WITHOUT ground truth — the candidate-score
distribution [n_candidates, mean, q10, q50, q90] — and measure a MAHALANOBIS distance
to the calibration cohort's envelope of the same features. If the case is far outside
the envelope, it is OOD and the endpoint WITHHOLDS the FDR guarantee (fail closed)
while still showing the tiers as an unguaranteed second look.

Statistic + threshold are chosen from EVIDENCE, not guessed
(scripts/calm-ms/validate_ood_monitor.py, record in assets/ood_validation_record.json):
a naive max-robust-z statistic was found inadequate (to catch a +6SD score-regime
shift it had to flag ~9% of legitimate cases). Mahalanobis — which accounts for the
strong correlation among the mean/quantile features — separates far better: at
threshold 5.0 it withholds the guarantee on only ~2% of legitimate in-distribution
cases (a fail-closed, utility-only cost) while catching a +6SD shift ~100% of the time.

SCOPE / residual limitation (documented in RMF Addendum A): this is a GROSS-shift
backstop. A gross score-regime shift — the documented ~8x-FDR failure mode — is
caught reliably; a SUBTLE shift (~+3SD) is NOT reliably caught (detection ~25%). The
monitor's sensitivity/specificity on real mimic/scanner-shift cohorts remains a V&V
prerequisite for clinical enablement.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Mahalanobis distance beyond which a case is declared out of the validated
# distribution. Chosen from the validation sweep (validate_ood_monitor.py): the
# lowest threshold with <=3% false-OOD on the 145 legit cases AND >=95% detection of
# a +6SD score-regime shift. See assets/ood_validation_record.json.
OOD_THRESHOLD = 5.0
# Ridge added to the whitened covariance before inversion — the mean/quantile
# features are near-collinear, so a small ridge keeps the inverse well-conditioned
# (must match the value used in the validation script).
_COV_RIDGE = 1e-3


@dataclass
class OODVerdict:
    is_ood: bool
    distance: float           # Mahalanobis distance to the calibration envelope
    threshold: float
    detail: str

    def as_dict(self) -> dict:
        return {
            "is_ood": bool(self.is_ood),
            "distance": round(float(self.distance), 2),
            "threshold": float(self.threshold),
            "detail": self.detail,
        }


def case_features(scores) -> np.ndarray | None:
    """[n_candidates, mean, q10, q50, q90] for a case's candidate scores, or None
    if there are no candidates (nothing to place in-distribution)."""
    s = np.asarray(scores, dtype=float).ravel()
    if s.size == 0:
        return None
    q10, q50, q90 = np.quantile(s, [0.1, 0.5, 0.9])
    return np.array([float(s.size), float(s.mean()), float(q10), float(q50), float(q90)], dtype=float)


def _robust_center_scale(ref: np.ndarray):
    med = np.median(ref, axis=0)
    mad = np.median(np.abs(ref - med), axis=0) * 1.4826   # ~SD under normality
    mad = np.where(mad < 1e-6, 1e-6, mad)
    return med, mad


def _mahalanobis(feat: np.ndarray, ref: np.ndarray) -> float:
    """Mahalanobis distance of `feat` to the `ref` envelope. Features are first
    standardized per-column by robust scale (n_candidates and scores live on very
    different scales), then covariance-whitened so a coherent score-regime shift —
    which moves the correlated mean/quantile features together — registers as one
    large distance instead of being diluted across per-feature z-scores. Ridge keeps
    the near-collinear quantile block invertible. Mirrors validate_ood_monitor.py."""
    mu = np.median(ref, axis=0)
    _, sc = _robust_center_scale(ref)
    R = (ref - mu) / sc
    C = np.cov(R, rowvar=False) + _COV_RIDGE * np.eye(ref.shape[1])
    Ci = np.linalg.pinv(C)
    v = (feat - mu) / sc
    return float(np.sqrt(max(0.0, v @ Ci @ v)))


def assess_ood(scores, ood_reference, threshold: float = OOD_THRESHOLD) -> OODVerdict:
    """Assess whether a case's candidate-score distribution is out of the calibration
    envelope. Fail-safe: if no OOD reference is available, treat as OOD-unknown and
    return is_ood=True (fail closed — never claim in-distribution without evidence)."""
    if ood_reference is None or np.asarray(ood_reference).ndim != 2 or np.asarray(ood_reference).shape[0] < 5:
        return OODVerdict(True, float("inf"), threshold,
                          "no OOD reference available — guarantee withheld (fail closed)")
    feat = case_features(scores)
    if feat is None:
        # No candidates on the map -> nothing flagged; guarantee trivially applies.
        return OODVerdict(False, 0.0, threshold, "no candidates")
    dist = _mahalanobis(feat, np.asarray(ood_reference, dtype=float))
    is_ood = dist > threshold
    detail = ("in validated distribution" if not is_ood
              else f"case is {dist:.1f} Mahalanobis-SD from the calibration envelope (> {threshold})")
    return OODVerdict(is_ood, dist, threshold, detail)
