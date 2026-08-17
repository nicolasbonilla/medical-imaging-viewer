"""CALM-MS second-reader review core — the hazard-free, testable heart of the
conformal-confidence feature (REQ-FUNC-CALM-001).

Shaped directly by the 4-angle adversarial Class C review. Every design choice
here is a risk control:

  * ADDITIVE, never a suppressor (RC-CALM-1): all base-model lesion candidates are
    returned and painted; nothing is ever removed. The conformal layer only
    ANNOTATES a review-priority tier. Downstream consumers (volumetry, DIS,
    reports) must keep reading the full base mask.
  * NO per-lesion probability (RC-CALM-2): a conformal p-value is NOT P(lesion is
    real). We expose an ORDINAL review-priority tier (high/medium/low), never a
    percentage or a "confidence".
  * NO per-scan realized FDR (RC-CALM-3): the guarantee is MARGINAL (population).
    We return only the preset's target alpha, labelled as population-level scope.
  * VALIDATED PRESETS only (RC-CALM-4): alpha + candidate threshold are frozen per
    preset; callers pass a preset name, never raw alpha/threshold.
  * FAIL-CLOSED exchangeability (RC-CALM-5): the probability map must match the
    null asset's base model + grid; a mismatch raises ProvenanceMismatch and the
    endpoint refuses — the guarantee is never shown when it is void.

This module is pure NumPy/SciPy + the frozen null asset; it does no I/O, no auth,
no persistence, so it is unit-testable end to end.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.services.calm_ms_inference import extract_lesion_candidates
from app.services.conformal_lesion_fdr import conformal_pvalues, benjamini_hochberg
from app.services.conformal_null_asset import get_null_asset, resolve_preset, PRESETS, DEFAULT_PRESET

GUARANTEE_SCOPE = (
    "Population-level lesion false-discovery control (marginal over an exchangeable "
    "cohort). NOT a per-scan or per-lesion probability. Tiers rank review priority; "
    "they are not a probability that a lesion is real."
)

# Ordinal review-priority tiers, keyed off the conformal p-value relative to the
# preset alpha. Low p = stronger conformal evidence the candidate is a real lesion.
TIER_HIGH = "high"      # p <= alpha  -> inside the FDR-controlled set at this preset
TIER_MEDIUM = "medium"  # alpha < p <= min(2*alpha, 0.5)
TIER_LOW = "low"        # weakest evidence


@dataclass
class LesionReview:
    label: int
    centroid: tuple            # (z, y, x)
    volume_mm3: float
    n_voxels: int
    review_priority: str       # high | medium | low  (ordinal; NOT a probability)
    in_fdr_set: bool           # covered by the population FDR guarantee at this preset

    def as_dict(self) -> dict:
        return {
            "centroid": [round(float(c), 1) for c in self.centroid],
            "volume_mm3": round(float(self.volume_mm3), 2),
            "n_voxels": int(self.n_voxels),
            "review_priority": self.review_priority,
            "in_fdr_set": bool(self.in_fdr_set),
        }


@dataclass
class ConformalReview:
    preset: str
    fdr_target: float                  # the preset's alpha (INPUT target; never a realized FDP)
    guarantee_scope: str
    lesions: list[LesionReview]
    status_mask: np.ndarray            # uint8: 1=high,2=medium,3=low per candidate (additive overlay)
    provenance: dict

    def summary(self) -> dict:
        counts = {TIER_HIGH: 0, TIER_MEDIUM: 0, TIER_LOW: 0}
        for r in self.lesions:
            counts[r.review_priority] += 1
        return {
            "preset": self.preset,
            "fdr_target": self.fdr_target,
            "guarantee_scope": self.guarantee_scope,
            "n_candidates": len(self.lesions),
            "n_in_fdr_set": sum(1 for r in self.lesions if r.in_fdr_set),
            "tier_counts": counts,
            "base_model": self.provenance.get("base_model"),
            "null_version": self.provenance.get("version"),
            "lesions": [r.as_dict() for r in self.lesions],
        }


def _tier(pval: float, alpha: float) -> str:
    if pval <= alpha:
        return TIER_HIGH
    if pval <= min(2.0 * alpha, 0.5):
        return TIER_MEDIUM
    return TIER_LOW


def conformal_review(prob_map: np.ndarray, voxel_spacing, preset: str = DEFAULT_PRESET) -> ConformalReview:
    """Second-reader review of a FLAMeS probability map at a validated preset.

    Fails closed: raises KeyError for an unknown preset, ProvenanceMismatch if the
    map is off the calibration grid, and ValueError if the map is not a valid
    probability volume. Returns every candidate (additive) with an ordinal tier.
    """
    if preset not in PRESETS:
        raise KeyError(preset)
    prob_map = np.asarray(prob_map, dtype=np.float32)
    if prob_map.ndim != 3:
        raise ValueError(f"prob_map must be 3D, got {prob_map.ndim}D")
    pmin, pmax = float(prob_map.min()), float(prob_map.max())
    if pmin < 0.0 or pmax > 1.001:
        raise ValueError(f"prob_map must be in [0,1], got [{pmin:.3f},{pmax:.3f}]")

    asset = get_null_asset()
    asset.assert_compatible(prob_map.shape, voxel_spacing)   # FAIL-CLOSED exchangeability
    alpha, threshold = resolve_preset(preset)

    labeled, cands = extract_lesion_candidates(
        prob_map, threshold, tuple(float(s) for s in voxel_spacing),
        min_volume_mm3=asset.min_volume_mm3, score=asset.score_pooling)

    status = np.zeros(prob_map.shape, dtype=np.uint8)
    lesions: list[LesionReview] = []
    if cands:
        scores = np.array([c.score for c in cands], dtype=float)
        pvals = conformal_pvalues(scores, asset.null_scores)
        in_set = benjamini_hochberg(pvals, alpha)
        tier_label = {TIER_HIGH: 1, TIER_MEDIUM: 2, TIER_LOW: 3}
        for c, p, sel in zip(cands, pvals, in_set):
            t = _tier(float(p), alpha)
            status[labeled == c.label] = tier_label[t]
            lesions.append(LesionReview(
                label=c.label, centroid=c.centroid, volume_mm3=c.volume_mm3,
                n_voxels=c.n_voxels, review_priority=t, in_fdr_set=bool(sel)))

    return ConformalReview(
        preset=preset, fdr_target=float(alpha), guarantee_scope=GUARANTEE_SCOPE,
        lesions=lesions, status_mask=status, provenance=asset.provenance)
