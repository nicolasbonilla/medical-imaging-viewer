"""Paper F — pre-registered metrics (docs/research/paper-f/PROTOCOL.md, sections 5-7).

Pure numpy / scipy, no cloud calls, no I/O. Every definition the protocol fixes lives here so the
analysis cannot drift after the results are seen:

  * binarisation            prob > 0.5 (tool hard masks are used as delivered, see evaluate.py)
  * lesion                  3D connected component, 26-connectivity, on the reference (FLAMeS) grid
  * minimum lesion size     14.137 mm^3 (= sphere of 3 mm diameter), applied to prediction AND
                            reference before matching; sensitivity analyses use 0 and 3 mm^3
  * matching                any overlap (>= 1 voxel) between surviving components
  * lesion-wise precision   matched predicted components / predicted components
  * lesion-wise recall      matched reference components / reference components
  * lesion-wise F1          harmonic mean of the two; undefined (None) when the reference is empty
  * false lesions per scan  predicted components (after the size filter) that touch no reference lesion
  * Dice                    voxel-wise on the unfiltered masks; None when the reference is empty
  * detection by size       reference lesions per size bin (mm^3) and how many were matched
  * thickness band          from the slice spacing of the grid the tools received
  * inference               patient-cluster bootstrap stratified by cohort; Holm across a family
"""
import math

import numpy as np
from scipy import ndimage

SPHERE_3MM_MM3 = 4.0 / 3.0 * math.pi * 1.5 ** 3          # 14.137 mm^3
MIN_LESION_MM3 = SPHERE_3MM_MM3                          # primary
SENSITIVITY_MIN_MM3 = (0.0, 3.0)                         # S1 (no filter), S2 (MSSEG-2016-style 3 mm^3)
SIZE_BINS_MM3 = (SPHERE_3MM_MM3, 50.0, 200.0, 1000.0, math.inf)
SIZE_BIN_LABELS = ("14-50", "50-200", "200-1000", ">=1000")
ISO_MAX_MM = 1.5          # band "iso": slice spacing <= 1.5 mm
THICK_MIN_MM = 3.0        # band "thick": slice spacing > 3 mm
THICK_SPLIT_MM = 5.5      # exploratory sub-bands: (3, 5.5] and > 5.5 mm
BOOT_N = 10000
BOOT_SEED = 20261021
EQUIV_MARGIN_F1 = 0.05
EQUIV_MARGIN_FP = 1.0


def structure(connectivity=26, slice_axis=2):
    """3D structuring element: 26 (full), 18, 6, or 8 (= in-plane only: no link across `slice_axis`)."""
    if connectivity == 26:
        return np.ones((3, 3, 3), bool)
    if connectivity == 18:
        return ndimage.generate_binary_structure(3, 2)
    if connectivity == 6:
        return ndimage.generate_binary_structure(3, 1)
    if connectivity == 8:                                    # slice-wise components (3rd axis = slices)
        s = np.zeros((3, 3, 3), bool)
        sl = [slice(None)] * 3
        sl[slice_axis] = 1
        s[tuple(sl)] = True
        return s
    raise ValueError(f"unsupported connectivity {connectivity}")


def voxel_mm3(zooms):
    return float(np.prod([float(z) for z in zooms[:3]]))


def components(mask, zooms, min_mm3=MIN_LESION_MM3, connectivity=26):
    """(labels, n, volumes_mm3) of the components of `mask` with volume >= min_mm3, relabelled 1..n."""
    slice_axis = int(np.argmax([float(z) for z in zooms[:3]]))
    lab, n = ndimage.label(np.asarray(mask, bool), structure=structure(connectivity, slice_axis))
    if n == 0:
        return lab, 0, np.zeros(0)
    vox = np.bincount(lab.ravel(), minlength=n + 1)[1:] * voxel_mm3(zooms)
    keep = vox >= min_mm3 - 1e-9
    remap = np.zeros(n + 1, np.int32)
    remap[1:][keep] = np.arange(1, int(keep.sum()) + 1)
    return remap[lab], int(keep.sum()), vox[keep]


def dice(a, b):
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    s = int(a.sum()) + int(b.sum())
    return None if s == 0 else float(2.0 * np.logical_and(a, b).sum() / s)


def size_bin(v_mm3):
    for i in range(len(SIZE_BIN_LABELS)):
        if SIZE_BINS_MM3[i] - 1e-9 <= v_mm3 < SIZE_BINS_MM3[i + 1]:
            return SIZE_BIN_LABELS[i]
    return None                                              # below the smallest bin edge


def lesion_metrics(pred, ref, zooms, min_mm3=MIN_LESION_MM3, connectivity=26):
    """All per-scan outcomes of the protocol for one binary prediction against one reference."""
    pred, ref = np.asarray(pred, bool), np.asarray(ref, bool)
    if pred.shape != ref.shape:
        raise ValueError(f"shape mismatch {pred.shape} vs {ref.shape}")
    lp, n_p, _ = components(pred, zooms, min_mm3, connectivity)
    lr, n_r, vol_r = components(ref, zooms, min_mm3, connectivity)
    hit_p = set(np.unique(lp[lr > 0]).tolist()) - {0}        # predicted components touching a reference lesion
    hit_r = set(np.unique(lr[lp > 0]).tolist()) - {0}        # reference lesions touched by a prediction
    tp_p, tp_r = len(hit_p), len(hit_r)
    precision = tp_p / n_p if n_p else None
    recall = tp_r / n_r if n_r else None
    if n_r == 0:
        f1 = None
    elif n_p == 0 or tp_p + tp_r == 0:
        f1 = 0.0
    else:
        f1 = 2.0 * precision * recall / (precision + recall)
    v = voxel_mm3(zooms)
    bins = {b: [0, 0] for b in SIZE_BIN_LABELS}               # [reference lesions, detected]
    for idx, vol in enumerate(vol_r, start=1):
        b = size_bin(vol)
        if b:
            bins[b][0] += 1
            bins[b][1] += int(idx in hit_r)
    return {"n_ref": n_r, "n_pred": n_p, "tp_ref": tp_r, "tp_pred": tp_p,
            "false_lesions": n_p - tp_p, "missed_lesions": n_r - tp_r,
            "precision": precision, "recall": recall, "f1": f1,
            "dice": dice(pred, ref) if ref.any() else None,
            "vol_pred_ml": float(pred.sum()) * v / 1000.0, "vol_ref_ml": float(ref.sum()) * v / 1000.0,
            "size_bins": bins}


def confirmed(a, b, zooms, min_mm3=MIN_LESION_MM3, connectivity=26):
    """Exploratory 'second opinion': the lesions of `a` (after the size filter) that `b` also marks."""
    la, n, _ = components(a, zooms, min_mm3, connectivity)
    if n == 0:
        return np.zeros(np.shape(a), bool)
    keep = set(np.unique(la[np.asarray(b, bool)]).tolist()) - {0}
    return np.isin(la, sorted(keep)) if keep else np.zeros(np.shape(a), bool)


# ----------------------------------------------------------------------------- cohorts and bands
def slice_spacing(zooms):
    return float(max(float(z) for z in zooms[:3]))


def band(zooms):
    s = slice_spacing(zooms)
    if s <= ISO_MAX_MM:
        return "iso"
    if s > THICK_MIN_MM:
        return "thick"
    return "intermediate"


def sub_band(zooms):
    s = slice_spacing(zooms)
    if s <= ISO_MAX_MM:
        return "iso"
    if s <= THICK_MIN_MM:
        return "intermediate"
    return "thick_3-5.5" if s <= THICK_SPLIT_MM else "thick_>5.5"


def cohort_of(case):
    for c in ("mslesseg", "openms", "ms3seg", "muslim", "pedims"):
        if case.startswith(c + "_"):
            return c
    return "other"


def patient_of(case):
    """Cluster for the bootstrap: scans of the same person are not independent."""
    c = cohort_of(case)
    parts = case.split("_")
    if c in ("mslesseg", "pedims") and len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}"                      # mslesseg_P10_T1 -> mslesseg_P10; pedims_P1_T2 -> pedims_P1
    return case


# ----------------------------------------------------------------------------- inference
def bootstrap_distribution(values, strata, clusters, n_boot=BOOT_N, seed=BOOT_SEED, weighting="cohort"):
    """Point estimate and bootstrap replicates of a mean of per-scan values (e.g. tool - FLAMeS).

    Clusters (patients) are resampled with replacement inside each stratum (cohort). The statistic is
    the mean over strata of the per-stratum scan mean ("cohort": each cohort counts once) or the
    plain scan-weighted mean ("scan"). Non-finite values (undefined metric) are dropped first.
    Returns (point, replicates, n_scans, n_clusters); point is None when nothing is left.
    """
    values = np.asarray(values, float)
    strata, clusters = np.asarray(strata), np.asarray(clusters)
    ok = np.isfinite(values)
    values, strata, clusters = values[ok], strata[ok], clusters[ok]
    if values.size == 0:
        return None, np.zeros(0), 0, 0
    arrays = {}
    for s in sorted(set(strata.tolist())):
        cl = {}
        for i in np.where(strata == s)[0]:
            cl.setdefault(clusters[i], []).append(values[i])
        arrays[s] = (np.array([np.sum(v) for v in cl.values()]), np.array([len(v) for v in cl.values()]))

    def stat(picks):
        num = sum(arrays[s][0][p].sum() for s, p in picks.items())
        den = sum(arrays[s][1][p].sum() for s, p in picks.items())
        if weighting == "scan":
            return float(num / den)
        return float(np.mean([arrays[s][0][p].sum() / arrays[s][1][p].sum() for s, p in picks.items()]))

    point = stat({s: np.arange(len(a[0])) for s, a in arrays.items()})
    rng = np.random.default_rng(seed)
    boots = np.array([stat({s: rng.integers(0, len(a[0]), len(a[0])) for s, a in arrays.items()})
                      for _ in range(n_boot)])
    return point, boots, int(values.size), int(sum(len(a[0]) for a in arrays.values()))


def summarize(point, boots, n_scans=None, n_clusters=None, margin=None):
    """Estimate, 95% and 90% percentile intervals, two-sided bootstrap p (H0: 0), optional TOST."""
    if point is None or len(boots) == 0:
        return {"n_scans": n_scans or 0, "n_clusters": n_clusters or 0, "estimate": None,
                "ci95": [None, None], "ci90": [None, None], "p_two_sided": None}
    lo, hi = np.percentile(boots, [2.5, 97.5])
    lo90, hi90 = np.percentile(boots, [5, 95])
    p = min(1.0, 2.0 * min(float(np.mean(boots <= 0.0)), float(np.mean(boots >= 0.0))))
    out = {"n_scans": n_scans, "n_clusters": n_clusters, "estimate": float(point),
           "ci95": [float(lo), float(hi)], "ci90": [float(lo90), float(hi90)], "p_two_sided": float(p)}
    if margin is not None:
        out["equivalent_within_margin"] = bool(-margin < lo90 and hi90 < margin)
        out["margin"] = margin
    return out


def stratified_cluster_bootstrap(values, strata, clusters, n_boot=BOOT_N, seed=BOOT_SEED, weighting="cohort",
                                 margin=None):
    point, boots, n, k = bootstrap_distribution(values, strata, clusters, n_boot, seed, weighting)
    return summarize(point, boots, n, k, margin)


def holm(pvalues):
    """Holm-Bonferroni adjusted p-values (same order as the input); None stays None."""
    idx = [i for i, p in enumerate(pvalues) if p is not None]
    order = sorted(idx, key=lambda i: pvalues[i])
    adj, running = [None] * len(pvalues), 0.0
    m = len(order)
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adj[i] = running
    return adj


def auroc(scores, labels):
    """Mann-Whitney AUROC (ties count 1/2); None when one class is empty."""
    s, y = np.asarray(scores, float), np.asarray(labels, bool)
    pos, neg = s[y], s[~y]
    if pos.size == 0 or neg.size == 0:
        return None
    gt = (pos[:, None] > neg[None, :]).sum()
    eq = (pos[:, None] == neg[None, :]).sum()
    return float((gt + 0.5 * eq) / (pos.size * neg.size))
