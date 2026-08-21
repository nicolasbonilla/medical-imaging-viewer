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
threshold 5.0 it withholds the guarantee on ~2.6% of the 115 legitimate
in-distribution cases (a fail-closed, utility-only cost) while catching a +6SD
score-regime shift ~92% of the time — the best +6SD detection among thresholds that
meet the <=3% false-OOD budget (t=4 detects ~98% but false-flags 4.3%). Numbers are
the shipped validation record (115 MSLesSeg cases; assets/ood_validation_record.json).

SCOPE / FUNDAMENTAL limitation — read before trusting this (RMF HAZ-CALM-5).
Adversarial verification (2 independent reviews, runnable repros) proved this monitor
is NECESSARY BUT NOT SUFFICIENT for the FDR guarantee, and cannot be made sufficient:

  * It audits the MIXED (true+false) candidate-score MARGINAL. The conformal FDR
    guarantee depends on the FALSE-candidate scores being exchangeable with the frozen
    null — a LABEL-conditional property (P(score | candidate is false)) that the
    marginal is blind to (a label-shift, not a covariate-shift; cf. Podkopaev &
    Ramdas 2021). A case whose 5-number summary sits INSIDE this envelope can still
    realize FDP ~1.0 (confirmed: false candidates parked in the null's upper tail get
    small conformal p-values, are BH-selected, and the mixture still looks normal
    because legitimate cases carry high scores from their TRUE lesions).
  * It is therefore, at best, a GROSS-MARGINAL-SHIFT disclosure backstop — it flags
    obvious whole-distribution shifts, NOT the clinically-likely false-positive
    inflation that actually breaks the guarantee. No label-free score statistic can
    close that hole; doing so needs class-conditional null re-estimation on a per-site
    labelled slice, or a covariate/embedding-space check (weighted / Mondrian
    conformal — Tibshirani 2019, Barber 2023). This is a BLOCKING prerequisite for
    clinical enablement, tracked in the RMF.

Known statistical weaknesses of the v1 statistic (see ood_validation_record.json):
`n_candidates` is a skewed count forced into a Gaussian ellipsoid — it conflates
lesion burden with score regime, so high-burden (sickest) patients are preferentially
flagged; the 5 moments are also blind to shape/count evasions a full-distribution
two-sample test (KS/energy/MMD) would catch. A KS-based v2 is the planned upgrade.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Feature layout of both the per-case summary and the calibration reference. Order
# and definition MUST match build_null_bundle.py (verified in test).
OOD_FEATURES = ("n_candidates", "mean", "q10", "q50", "q90")

# Mahalanobis distance beyond which a case is declared out of the validated
# distribution. Chosen from the validation sweep (validate_ood_monitor.py): the lowest
# threshold whose false-OOD rate on the 115 legit cases is <=3% (2.6% at t=5; t=4 is
# 4.3%). At that threshold, +6SD score-regime-shift detection is ~92% (t=4 reaches ~98%
# but breaks the false-OOD budget). See assets/ood_validation_record.json.
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
    the near-collinear quantile block invertible. Mirrors validate_ood_monitor.py.

    Fails closed numerically: a non-finite quadratic form (e.g. a NaN feature slipped
    past the callers) returns +inf, not a spurious 0.0 that would read as
    in-distribution."""
    mu = np.median(ref, axis=0)
    _, sc = _robust_center_scale(ref)
    R = (ref - mu) / sc
    C = np.cov(R, rowvar=False) + _COV_RIDGE * np.eye(ref.shape[1])
    Ci = np.linalg.pinv(C)
    v = (feat - mu) / sc
    q = float(v @ Ci @ v)
    if not np.isfinite(q):
        return float("inf")
    return float(np.sqrt(max(0.0, q)))


def assess_ood(scores, ood_reference, threshold: float = OOD_THRESHOLD) -> OODVerdict:
    """Assess whether a case's candidate-score distribution is out of the calibration
    envelope. Fail-safe: if no OOD reference is available, or the case features are
    non-finite, treat as OOD-unknown and return is_ood=True (fail closed — never claim
    in-distribution without evidence).

    SCOPE (see module docstring + RMF HAZ-CALM-5): this detects only a GROSS shift of
    the *mixed* candidate-score marginal. It CANNOT certify exchangeability of the
    *false*-candidate null the FDR guarantee actually depends on (a label-shift the
    marginal is blind to); an in-distribution verdict here is necessary, not
    sufficient, for the guarantee. Adversarially confirmed: a case matched to this
    envelope can still realize FDP ~1.0."""
    ref = np.asarray(ood_reference, dtype=float) if ood_reference is not None else None
    if ref is None or ref.ndim != 2 or ref.shape[0] < 5 or ref.shape[1] != len(OOD_FEATURES):
        return OODVerdict(True, float("inf"), threshold,
                          "no valid OOD reference available — guarantee withheld (fail closed)")
    s = np.asarray(scores, dtype=float).ravel()
    if s.size and not np.isfinite(s).all():
        return OODVerdict(True, float("inf"), threshold,
                          "non-finite candidate scores — guarantee withheld (fail closed)")
    feat = case_features(s)
    if feat is None:
        # No candidates on the map -> empty FDR set -> nothing to guarantee (vacuous).
        return OODVerdict(False, 0.0, threshold, "no candidates")
    dist = _mahalanobis(feat, ref)
    is_ood = dist > threshold
    detail = ("in validated distribution (marginal only — see scope)" if not is_ood
              else f"case is {dist:.1f} Mahalanobis-SD from the calibration envelope (> {threshold})")
    return OODVerdict(is_ood, dist, threshold, detail)
