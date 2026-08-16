"""The CALM-MS headline experiment: leave-one-case-out conformal FDR coverage.

Given a cohort of (probability map, expert mask) pairs, this answers the paper's
central question: when the clinician asks for a target lesion-level FDR alpha,
does the conformal layer actually deliver it — and at what cost in sensitivity —
on HELD-OUT cases?

For each target alpha we run leave-one-case-out: calibrate the conformal null on
every other case, select on the held-out case, and record realized FDR and
lesion sensitivity. Aggregating over the cohort yields the FDR-coverage curve
(target vs realized) with bootstrap CIs — the plot that is the paper — alongside
the uncontrolled baseline (select everything at the threshold), which is where
today's ~0.22 precision lives.

Pure NumPy/SciPy; consumes any probabilistic segmenter's output. Unit-testable on
synthetic cohorts.
"""
from __future__ import annotations

import numpy as np

from app.services.lesion_metrics import label_lesions, MIN_LESION_VOLUME_MM3
from app.services.calm_ms_inference import extract_lesion_candidates
from app.services.conformal_lesion_fdr import select_by_fdr
from app.services.segmentation_benchmark import bootstrap_ci_mean


def _prep_case(prob_map, gt_mask, threshold, voxel_spacing, min_volume_mm3, score, min_overlap):
    """Per-case candidate scores, TP flags, and which GT lesion each hits."""
    labeled, cands = extract_lesion_candidates(
        prob_map, threshold, voxel_spacing, min_volume_mm3, score)
    gt_labeled, n_gt = label_lesions((gt_mask > 0).astype(np.uint8))

    scores, tp_flags, gt_hits = [], [], []
    for c in cands:
        comp = (labeled == c.label)
        hit = set(int(x) for x in np.unique(gt_labeled[comp]) if x != 0)
        overlap_frac = (np.logical_and(comp, gt_mask > 0).sum() / c.n_voxels) if c.n_voxels else 0.0
        is_tp = overlap_frac > min_overlap and len(hit) > 0
        scores.append(c.score)
        tp_flags.append(is_tp)
        gt_hits.append(hit if is_tp else set())
    return {
        "scores": np.asarray(scores, dtype=float),
        "tp": np.asarray(tp_flags, dtype=bool),
        "gt_hits": gt_hits,
        "n_gt": int(n_gt),
    }


def _fdr_and_sens(prep, selected):
    """(realized FDR, lesion sensitivity, n_selected) for a boolean selection."""
    sel = np.asarray(selected, dtype=bool)
    n_sel = int(sel.sum())
    fp = int(np.logical_and(sel, ~prep["tp"]).sum())
    fdp = fp / n_sel if n_sel else 0.0
    detected = set()
    for i, keep in enumerate(sel):
        if keep:
            detected |= prep["gt_hits"][i]
    sens = (len(detected) / prep["n_gt"]) if prep["n_gt"] else 1.0
    return fdp, sens, n_sel


def run_loo_fdr_experiment(
    cases,
    alpha_grid,
    threshold: float,
    voxel_spacing,
    min_volume_mm3: float = MIN_LESION_VOLUME_MM3,
    score: str = "mean",
    min_overlap: float = 0.0,
    boot_seed: int = 0,
) -> dict:
    """Leave-one-case-out conformal FDR-coverage over a cohort.

    cases: iterable of (prob_map, expert_mask). Returns the baseline (uncontrolled)
    operating point and, per target alpha, the mean realized FDR (+95% CI) and
    mean sensitivity across held-out cases.
    """
    preps = [_prep_case(p, g, threshold, voxel_spacing, min_volume_mm3, score, min_overlap)
             for (p, g) in cases]
    n = len(preps)
    if n < 2:
        raise ValueError("need >= 2 cases for leave-one-out")

    # Baseline: keep every candidate above threshold (no conformal control).
    base_fdr, base_sens, base_nsel = [], [], []
    for prep in preps:
        keep_all = np.ones(prep["scores"].size, dtype=bool)
        f, s, k = _fdr_and_sens(prep, keep_all)
        base_fdr.append(f); base_sens.append(s); base_nsel.append(k)

    curve = []
    for alpha in alpha_grid:
        fdrs, senss, nsels = [], [], []
        for i, prep in enumerate(preps):
            null = np.concatenate([preps[j]["scores"][~preps[j]["tp"]]
                                   for j in range(n) if j != i]) if n > 1 else np.array([])
            if null.size == 0:
                # no false candidates anywhere else -> nothing to calibrate against
                sel = np.ones(prep["scores"].size, dtype=bool) if prep["scores"].size else np.zeros(0, bool)
            elif prep["scores"].size == 0:
                sel = np.zeros(0, dtype=bool)
            else:
                sel, _ = select_by_fdr(prep["scores"], null, alpha)
            f, s, k = _fdr_and_sens(prep, sel)
            fdrs.append(f); senss.append(s); nsels.append(k)
        lo, hi = bootstrap_ci_mean(fdrs, seed=boot_seed)
        curve.append({
            "alpha": float(alpha),
            "realized_fdr_mean": float(np.mean(fdrs)),
            "realized_fdr_ci95": [lo, hi],
            "sensitivity_mean": float(np.mean(senss)),
            "n_selected_mean": float(np.mean(nsels)),
        })

    return {
        "n_cases": n,
        "baseline": {
            "fdr_mean": float(np.mean(base_fdr)),
            "sensitivity_mean": float(np.mean(base_sens)),
            "n_selected_mean": float(np.mean(base_nsel)),
        },
        "curve": curve,
    }
