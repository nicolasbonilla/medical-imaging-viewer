"""Per-lesion feature extraction for the CALM-MS learned re-scoring layer (Phase 2).

The Phase-1 experiment showed the guarantee holds but sensitivity collapses: the
base segmenter's pooled probability does not separate a true lesion from a false
candidate well, so controlling the false-discovery rate discards almost
everything. The literature is explicit about the fix — lesion-level uncertainty /
feature-based filtering lifts the lesion-wise TP rate at a fixed false-detection
rate (Nair et al.; MICCAI-2025 calibrated blending). This module builds the
feature vector that a calibrated scorer turns into a much better-separating score,
which then feeds the SAME conformal layer.

Every feature is computed from what a probabilistic segmenter already produces —
the soft map and the candidate's connected component — plus, when available, a
second model's mask (deep-ensemble agreement, the single strongest false-positive
filter). No new dependency: NumPy + SciPy ndimage only, matching the Class C
"pure NumPy/SciPy" modules around it. Unit-testable on synthetic volumes.

Feature vector (per candidate, in `FEATURE_NAMES` order):
  log_volume      log1p of physical volume (mm^3) — FPs skew small
  mean_prob       mean posterior over the lesion
  max_prob        peak posterior
  std_prob        posterior spread inside the lesion
  mean_entropy    mean binary entropy of the posterior — voxel-level uncertainty
  surface_to_vol  boundary voxels / total — thin/irregular blobs skew high (FP)
  boundary_contrast   mean interior posterior minus mean posterior in the 1-voxel
                      outer shell — a real lesion has a sharp edge (large drop)
  agreement       fraction of the lesion also positive in a second model's mask
                  (0.0 when no second model is supplied)
"""
from __future__ import annotations

import numpy as np

FEATURE_NAMES = (
    "log_volume",
    "mean_prob",
    "max_prob",
    "std_prob",
    "mean_entropy",
    "surface_to_vol",
    "boundary_contrast",
    "agreement",
)

_EPS = 1e-6


def _binary_entropy(p: np.ndarray) -> np.ndarray:
    """Per-voxel binary entropy in bits, safe at p in {0, 1}."""
    q = np.clip(p, _EPS, 1.0 - _EPS)
    return -(q * np.log2(q) + (1.0 - q) * np.log2(1.0 - q))


def _expand_slice(sl, shape, pad=1):
    """Grow a bounding-box slice tuple by `pad` voxels, clipped to `shape`."""
    out = []
    for s, n in zip(sl, shape):
        start = max(0, s.start - pad)
        stop = min(n, s.stop + pad)
        out.append(slice(start, stop))
    return tuple(out)


def candidate_feature_row(
    prob_map: np.ndarray,
    sub_lab: np.ndarray,
    label: int,
    sub_prob: np.ndarray,
    voxel_vol: float,
    sub_second=None,
) -> np.ndarray:
    """Feature row for one candidate, given its (padded) sub-volumes.

    `sub_lab`/`sub_prob` are the label and probability crops around the component;
    `sub_second` (optional) is the second model's binary crop for the agreement
    feature. Kept separate from the batch driver so it is trivially unit-testable.
    """
    from scipy import ndimage

    comp = (sub_lab == label)
    n = int(comp.sum())
    if n == 0:
        return np.zeros(len(FEATURE_NAMES), dtype=float)

    probs = sub_prob[comp]
    mean_p = float(probs.mean())
    max_p = float(probs.max())
    std_p = float(probs.std())
    mean_h = float(_binary_entropy(probs).mean())

    # Shape: boundary voxels (foreground with a background face-neighbour).
    eroded = ndimage.binary_erosion(comp, border_value=0)
    surface = np.logical_and(comp, np.logical_not(eroded))
    s2v = float(surface.sum()) / n

    # Edge sharpness: interior posterior minus the 1-voxel outer shell posterior.
    dil = ndimage.binary_dilation(comp, border_value=0)
    shell = np.logical_and(dil, np.logical_not(comp))
    shell_mean = float(sub_prob[shell].mean()) if bool(shell.any()) else 0.0
    boundary_contrast = mean_p - shell_mean

    agreement = 0.0
    if sub_second is not None:
        agreement = float(np.logical_and(comp, sub_second > 0).sum()) / n

    log_vol = float(np.log1p(n * voxel_vol))
    return np.array(
        [log_vol, mean_p, max_p, std_p, mean_h, s2v, boundary_contrast, agreement],
        dtype=float,
    )


def feature_matrix(
    prob_map: np.ndarray,
    labeled: np.ndarray,
    candidates,
    voxel_spacing: tuple[float, float, float],
    second_mask=None,
):
    """(X [n_candidates, n_features], FEATURE_NAMES) for a case's candidates.

    `labeled`/`candidates` come straight from `extract_lesion_candidates`. Each row
    is computed inside the candidate's padded bounding box, so cost scales with
    lesion size, not volume size. `second_mask` (any array; truthy = foreground)
    enables the deep-ensemble agreement feature.
    """
    from scipy import ndimage

    if not candidates:
        return np.zeros((0, len(FEATURE_NAMES)), dtype=float), FEATURE_NAMES
    voxel_vol = float(np.prod(voxel_spacing))
    # find_objects returns bounding boxes indexed by label-1.
    boxes = ndimage.find_objects(labeled)

    rows = []
    for c in candidates:
        box = boxes[c.label - 1]
        if box is None:
            rows.append(np.zeros(len(FEATURE_NAMES), dtype=float))
            continue
        esl = _expand_slice(box, labeled.shape, pad=1)
        sub_second = None if second_mask is None else second_mask[esl]
        rows.append(candidate_feature_row(
            prob_map, labeled[esl], c.label, prob_map[esl], voxel_vol, sub_second))
    return np.vstack(rows), FEATURE_NAMES
