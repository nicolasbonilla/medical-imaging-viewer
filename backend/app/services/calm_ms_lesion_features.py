"""CALM-MS v2 — per-candidate feature extraction (the scanner-robust lesion scorer's input).

The F1 investigation (docs/calm-ms/F1-site-shift-investigation.md) showed the conformal
guarantee collapses when raw probability is the score, because a scanner can inflate the
confidence of false positives. This module computes, at INFERENCE and WITHOUT ground
truth, the per-candidate features a learned score leans on instead — the ones a scanner
cannot trivially inflate (morphology, anatomical location) alongside the probability
moments — exactly what lesion-wise false-positive-reduction models use.

SINGLE SOURCE OF TRUTH: both the frozen-asset trainer (scripts/calm-ms) and the
production scorer (`calm_ms_scorer`) import FEATURE_NAMES and `candidate_feature_matrix`
from here, so training and inference can never diverge (a defect an earlier adversarial
review flagged as a whole class of hazard).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi

# Feature layout — order is CONTRACTUAL (the frozen scorer asset stores coefficients in
# this order). PROB_* are scanner-inflatable; MORPH_*/LOC_* are the robust signal.
PROB_FEATURES = ("prob_mean", "prob_max", "prob_std", "prob_q90")
MORPH_FEATURES = ("log_volume", "sphericity", "surf_to_vol", "elongation", "extent")
LOC_FEATURES = ("z_norm", "y_norm", "x_norm", "laterality", "radial")
FEATURE_NAMES = PROB_FEATURES + MORPH_FEATURES + LOC_FEATURES


def _morphology(mask_bbox: np.ndarray, probs: np.ndarray) -> dict:
    """Morphology + probability summary of one candidate, from its cropped binary mask
    and the posterior probabilities of its voxels."""
    n = int(mask_bbox.sum())
    vol = float(max(n, 1))                                   # 1 mm^3 isotropic voxels
    surf = float((mask_bbox & ~ndi.binary_erosion(mask_bbox)).sum())
    surf = max(surf, 1.0)
    s2v = surf / vol
    sphericity = (np.pi ** (1 / 3) * (6 * vol) ** (2 / 3)) / surf   # 1.0 for a sphere
    coords = np.argwhere(mask_bbox).astype(float)
    if len(coords) >= 3:
        centred = coords - coords.mean(0)
        ev = np.sort(np.linalg.eigvalsh(np.cov(centred.T)))[::-1]
        ev = np.clip(ev, 1e-6, None)
        elongation = float(np.sqrt(ev[0] / ev[-1]))
    else:
        elongation = 1.0
    extent = vol / float(max(np.prod(mask_bbox.shape), 1))
    return {
        "prob_mean": float(probs.mean()), "prob_max": float(probs.max()),
        "prob_std": float(probs.std()), "prob_q90": float(np.quantile(probs, 0.9)),
        "log_volume": float(np.log(vol)), "sphericity": float(sphericity),
        "surf_to_vol": float(s2v), "elongation": elongation, "extent": float(extent),
    }


def _location(centroid, grid_shape) -> dict:
    """Anatomical location features from an MNI-space centroid (z, y, x)."""
    gz, gy, gx = (float(g) for g in grid_shape)
    cz, cy, cx = (float(c) for c in centroid)
    centre = np.array([gz / 2.0, gy / 2.0, gx / 2.0])
    radial = float(np.linalg.norm(np.array([cz, cy, cx]) - centre) / (np.linalg.norm(centre) + 1e-9))
    return {"z_norm": cz / gz, "y_norm": cy / gy, "x_norm": cx / gx,
            "laterality": abs(cx / gx - 0.5), "radial": radial}


def candidate_feature_matrix(prob_map, labeled, cands, voxel_spacing=(1.0, 1.0, 1.0)):
    """(n_candidates, len(FEATURE_NAMES)) feature matrix, rows aligned to `cands` order.

    `labeled`/`cands` are the outputs of `extract_lesion_candidates`. Uses only the
    probability map + the labelling (no ground truth), so it is inference-safe.
    """
    objs = ndi.find_objects(labeled)
    rows = []
    for c in cands:
        sl = objs[c.label - 1]
        m = (labeled[sl] == c.label)
        feats = _morphology(m, np.asarray(prob_map[sl])[m])
        feats.update(_location(c.centroid, prob_map.shape))
        rows.append([feats[k] for k in FEATURE_NAMES])
    return np.asarray(rows, dtype=float).reshape(-1, len(FEATURE_NAMES))
