"""CALM-MS out-of-distribution monitor (RC-CALM-5, second control axis).

The adversarial verification proved that the grid/spacing provenance check is
necessary but NOT sufficient for exchangeability: a probability map on the correct
grid but from a different scanner/regime (an "on-grid OOD" case) silently voids the
conformal FDR guarantee (realized FDR up to ~8x the target). This module adds the
missing distribution check.

Approach (v1, deliberately simple + auditable): summarise the incoming case by
features computable at inference WITHOUT ground truth — the candidate-score
distribution [n_candidates, mean, q10, q50, q90] — and measure a robust distance to
the calibration cohort's envelope of the same features (median + MAD). If the case
is far outside the envelope, it is OOD and the endpoint WITHHOLDS the FDR guarantee
(fail closed) while still showing the tiers as an unguaranteed second look.

This is a FIRST monitor: it catches gross distribution shift (different scanner /
score regime / candidate load), which is the documented failure mode. Its own
sensitivity/specificity on real mimic/scanner-shift cohorts remains a V&V
prerequisite for clinical enablement (SRS/RMF Addendum A).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Robust-SD distance beyond which a case is declared out of the validated
# distribution. Conservative: flags only gross shifts, not normal case-to-case
# variation (validated by test against the calibration cohort's own spread).
OOD_THRESHOLD = 8.0


@dataclass
class OODVerdict:
    is_ood: bool
    distance: float           # max robust-SD deviation across features
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
    med, mad = _robust_center_scale(np.asarray(ood_reference, dtype=float))
    z = np.abs((feat - med) / mad)
    dist = float(np.max(z))
    is_ood = dist > threshold
    detail = ("in validated distribution" if not is_ood
              else f"case is {dist:.1f} robust-SD from the calibration envelope (> {threshold})")
    return OODVerdict(is_ood, dist, threshold, detail)
