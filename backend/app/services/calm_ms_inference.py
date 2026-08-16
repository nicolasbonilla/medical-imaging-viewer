"""CALM-MS inference layer — from a probability map to a risk-controlled mask.

This is the bridge between a probabilistic base segmenter (LST-AI, nnU-Net, a
foundation model) and the conformal guarantee in `conformal_lesion_fdr`. It:

  1. EXTRACTS lesion candidates from a soft probability map (threshold -> 18-conn
     components -> per-lesion confidence score);
  2. CALIBRATES on held-out cases with expert ground truth, collecting the scores
     of the FALSE candidates (the conformal null distribution);
  3. SELECTS, on a new case, the subset of candidates whose expected
     false-discovery proportion is <= a clinician-set alpha, painting them into a
     final mask and attaching a calibrated per-lesion confidence.

The result is the product's precision dial with a statistical guarantee, and the
data pipeline for the paper's FDR-coverage experiment. Model-agnostic: any
segmenter that emits a per-voxel probability plugs in.

Depends only on NumPy/SciPy and the app's shared 18-connectivity labelling
(RC-030) — unit-testable end to end on synthetic probability maps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from app.services.lesion_metrics import label_lesions, MIN_LESION_VOLUME_MM3
from app.services.conformal_lesion_fdr import select_by_fdr

# How a candidate's scalar confidence is pooled from its voxel probabilities.
SCORE_MEAN = "mean"      # average posterior over the lesion — stable, default
SCORE_MAX = "max"        # peak posterior — sensitive to a single confident voxel


@dataclass
class LesionCandidate:
    """One connected-component lesion candidate and its conformal verdict."""
    label: int
    score: float
    n_voxels: int
    volume_mm3: float
    centroid: tuple            # (z, y, x)
    pvalue: Optional[float] = None
    confidence: Optional[float] = None   # 1 - pvalue once calibrated
    selected: Optional[bool] = None

    def as_dict(self) -> dict:
        return {
            "score": round(float(self.score), 4),
            "n_voxels": int(self.n_voxels),
            "volume_mm3": round(float(self.volume_mm3), 2),
            "centroid": [round(float(c), 1) for c in self.centroid],
            "pvalue": None if self.pvalue is None else round(float(self.pvalue), 4),
            "confidence": None if self.confidence is None else round(float(self.confidence), 4),
            "selected": self.selected,
        }


def extract_lesion_candidates(
    prob_map: np.ndarray,
    threshold: float,
    voxel_spacing: tuple[float, float, float],
    min_volume_mm3: float = MIN_LESION_VOLUME_MM3,
    score: str = SCORE_MEAN,
):
    """(labeled_array, [LesionCandidate]) from a soft probability map.

    Candidates are 18-connected components of `prob_map >= threshold`, filtered by
    a minimum physical volume, each scored by pooling its voxel probabilities.
    """
    if prob_map.ndim != 3:
        raise ValueError(f"prob_map must be 3D, got {prob_map.ndim}D")
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(f"threshold must be in [0,1], got {threshold}")
    from scipy import ndimage

    binary = (prob_map >= threshold)
    labeled, n = label_lesions(binary.astype(np.uint8))
    voxel_vol = float(np.prod(voxel_spacing))
    if n == 0:
        return labeled, []

    index = np.arange(1, n + 1)
    sizes = np.bincount(labeled.ravel(), minlength=n + 1)[1:]          # per-label voxel counts
    if score == SCORE_MAX:
        pooled = ndimage.maximum(prob_map, labeled, index)
    else:
        pooled = ndimage.mean(prob_map, labeled, index)
    centroids = ndimage.center_of_mass(binary, labeled, index)
    # With an array `index`, SciPy returns a list of (z,y,x) tuples. Some versions
    # collapse a single label to a bare tuple of scalars — normalize that case.
    if n == 1 and len(centroids) == prob_map.ndim and np.isscalar(centroids[0]):
        centroids = [centroids]

    cands = []
    for i, lbl in enumerate(index):
        nv = int(sizes[i])
        vol = nv * voxel_vol
        if vol < min_volume_mm3:
            continue
        cands.append(LesionCandidate(
            label=int(lbl), score=float(pooled[i]), n_voxels=nv,
            volume_mm3=vol, centroid=tuple(float(c) for c in centroids[i]),
        ))
    return labeled, cands


def label_candidates_tp(
    labeled: np.ndarray,
    candidates: list[LesionCandidate],
    gt_mask: np.ndarray,
    min_overlap: float = 0.0,
) -> dict[int, bool]:
    """Mark each candidate TP/FP against expert GT by voxel overlap.

    A candidate is a true positive if predicted foreground covers more than
    `min_overlap` of its voxels within any expert lesion (ISBI any-voxel
    convention at the default 0.0). Returns {candidate.label: is_true_positive}.
    """
    gt = (gt_mask > 0)
    out = {}
    for c in candidates:
        comp = (labeled == c.label)
        overlap = int(np.logical_and(comp, gt).sum())
        out[c.label] = (overlap / c.n_voxels) > min_overlap if c.n_voxels else False
    return out


def build_calibration_nulls(
    calibration_cases,
    threshold: float,
    voxel_spacing: tuple[float, float, float],
    min_volume_mm3: float = MIN_LESION_VOLUME_MM3,
    score: str = SCORE_MEAN,
    min_overlap: float = 0.0,
) -> np.ndarray:
    """Collect the scores of FALSE candidates across calibration cases.

    calibration_cases: iterable of (prob_map, expert_mask). These null scores are
    the conformal reference distribution; a test candidate scoring higher than
    most of them earns a small p-value (i.e. is unlikely to be a false positive).
    """
    nulls: list[float] = []
    for prob_map, gt_mask in calibration_cases:
        labeled, cands = extract_lesion_candidates(
            prob_map, threshold, voxel_spacing, min_volume_mm3, score)
        if not cands:
            continue
        is_tp = label_candidates_tp(labeled, cands, gt_mask, min_overlap)
        nulls.extend(c.score for c in cands if not is_tp[c.label])
    return np.asarray(nulls, dtype=float)


@dataclass
class ConformalResult:
    mask: np.ndarray                       # uint8 final lesion mask (selected only)
    candidates: list[LesionCandidate]      # every candidate, with verdict
    alpha: float
    n_candidates: int = 0
    n_selected: int = 0
    fdr_target: float = field(default=0.0)

    def summary(self) -> dict:
        return {
            "alpha": self.alpha,
            "fdr_target": self.alpha,
            "n_candidates": self.n_candidates,
            "n_selected": self.n_selected,
            "lesions": [c.as_dict() for c in self.candidates],
        }


def select_lesions_conformal(
    prob_map: np.ndarray,
    calib_null_scores,
    alpha: float,
    threshold: float,
    voxel_spacing: tuple[float, float, float],
    min_volume_mm3: float = MIN_LESION_VOLUME_MM3,
    score: str = SCORE_MEAN,
) -> ConformalResult:
    """End to end: probability map -> risk-controlled lesion mask.

    Selects the candidate subset with expected lesion-level FDR <= alpha, paints
    it, and attaches a calibrated confidence (1 - conformal p-value) to every
    candidate. The clinician's "false-positive tolerance" is exactly `alpha`.
    """
    labeled, cands = extract_lesion_candidates(
        prob_map, threshold, voxel_spacing, min_volume_mm3, score)
    final = np.zeros(prob_map.shape, dtype=np.uint8)
    if not cands:
        return ConformalResult(mask=final, candidates=[], alpha=alpha,
                               n_candidates=0, n_selected=0)

    scores = np.array([c.score for c in cands], dtype=float)
    selected, pvals = select_by_fdr(scores, calib_null_scores, alpha)

    n_sel = 0
    for c, sel, p in zip(cands, selected, pvals):
        c.pvalue = float(p)
        c.confidence = float(1.0 - p)
        c.selected = bool(sel)
        if sel:
            final[labeled == c.label] = 1
            n_sel += 1

    return ConformalResult(mask=final, candidates=cands, alpha=alpha,
                           n_candidates=len(cands), n_selected=n_sel)
