"""CALM-MS Phase 2: does a learned lesion score beat the base score under the
same conformal FDR guarantee?

Phase 1 established the guarantee (realized FDR <= alpha) but at a steep
sensitivity cost, because the base segmenter's pooled probability barely
separates true from false candidates. Phase 2 replaces that scalar with a
CalibratedLesionScorer trained on per-lesion features, and asks — on held-out
cases — whether the sensitivity-at-fixed-FDR operating point improves while the
guarantee is preserved.

Validity is the whole point, so the protocol is SPLIT conformal, not a naive
retrain-on-the-null. For each held-out test case the other cases are split into
two disjoint groups:

  * TRAIN — fits the scorer;
  * CALIB — supplies the conformal null (its false-candidate scores).

Because the scorer never sees CALIB or the test case, the CALIB scores and the
test scores are both out-of-sample for a FIXED scorer, so they stay exchangeable
and the conformal guarantee holds. Training the null on the same cases that fit
the scorer would make the calibration scores in-sample (artificially separated)
while the test case is out-of-sample — anti-conservative, breaking the guarantee.
Both the raw-score curve (Phase 1) and the learned-score curve (Phase 2) use the
SAME CALIB set and the SAME test case per fold, so they are paired on identical
candidates and the only difference is the score.

Pure NumPy/SciPy; consumes any probabilistic segmenter's output plus, optionally,
a second model's mask per case (deep-ensemble agreement feature).
"""
from __future__ import annotations

import numpy as np

from app.services.lesion_metrics import label_lesions, MIN_LESION_VOLUME_MM3
from app.services.calm_ms_inference import extract_lesion_candidates
from app.services.lesion_features import feature_matrix
from app.services.calibrated_lesion_scorer import CalibratedLesionScorer
from app.services.conformal_lesion_fdr import select_by_fdr
from app.services.segmentation_benchmark import bootstrap_ci_mean


def build_case_table(
    prob_map, gt_mask, threshold, voxel_spacing,
    min_volume_mm3: float = MIN_LESION_VOLUME_MM3, score: str = "mean",
    min_overlap: float = 0.0, second_mask=None,
) -> dict:
    """Per-candidate features, raw scores, TP flags and GT hits for one case."""
    labeled, cands = extract_lesion_candidates(
        prob_map, threshold, voxel_spacing, min_volume_mm3, score)
    gt_labeled, n_gt = label_lesions((gt_mask > 0).astype(np.uint8))

    X, _ = feature_matrix(prob_map, labeled, cands, voxel_spacing, second_mask)
    raw, tp_flags, gt_hits = [], [], []
    for c in cands:
        comp = (labeled == c.label)
        hit = set(int(x) for x in np.unique(gt_labeled[comp]) if x != 0)
        overlap_frac = (np.logical_and(comp, gt_mask > 0).sum() / c.n_voxels) if c.n_voxels else 0.0
        is_tp = overlap_frac > min_overlap and len(hit) > 0
        raw.append(c.score)
        tp_flags.append(is_tp)
        gt_hits.append(hit if is_tp else set())
    return {
        "X": X,
        "raw": np.asarray(raw, dtype=float),
        "tp": np.asarray(tp_flags, dtype=bool),
        "gt_hits": gt_hits,
        "n_gt": int(n_gt),
    }


def _fdr_and_sens(table, selected):
    sel = np.asarray(selected, dtype=bool)
    n_sel = int(sel.sum())
    fp = int(np.logical_and(sel, ~table["tp"]).sum())
    fdp = fp / n_sel if n_sel else 0.0
    detected = set()
    for i, keep in enumerate(sel):
        if keep:
            detected |= table["gt_hits"][i]
    sens = (len(detected) / table["n_gt"]) if table["n_gt"] else 1.0
    return fdp, sens, n_sel


def _split_others(n, i):
    """Disjoint (train, calib) index lists over all cases except i. A fixed parity
    split keeps the experiment deterministic and reproducible for the record."""
    others = [j for j in range(n) if j != i]
    calib = others[0::2]
    train = others[1::2]
    return train, calib


def _select_on_case(test_scores, calib_null, alpha):
    if calib_null.size == 0:
        return np.ones(test_scores.size, dtype=bool) if test_scores.size else np.zeros(0, bool)
    if test_scores.size == 0:
        return np.zeros(0, dtype=bool)
    sel, _ = select_by_fdr(test_scores, calib_null, alpha)
    return sel


def _fit_fold_scorer(tables, train_idx, l2, lr, n_iter):
    """Scorer fit on the TRAIN split only, or None if the split is unusable."""
    X_tr = [tables[j]["X"] for j in train_idx if tables[j]["X"].shape[0]]
    y_tr = [tables[j]["tp"].astype(float) for j in train_idx if tables[j]["X"].shape[0]]
    if not X_tr:
        return None
    X_tr = np.vstack(X_tr)
    y_tr = np.concatenate(y_tr)
    if len(np.unique(y_tr)) < 2:      # need both TP and FP to learn a ranking
        return None
    return CalibratedLesionScorer(l2=l2, lr=lr, n_iter=n_iter).fit(X_tr, y_tr)


def run_loo_rescoring_experiment(
    cases, alpha_grid, threshold, voxel_spacing,
    min_volume_mm3: float = MIN_LESION_VOLUME_MM3, score: str = "mean",
    min_overlap: float = 0.0, second_masks=None,
    l2: float = 1.0, lr: float = 0.5, n_iter: int = 800, boot_seed: int = 0,
) -> dict:
    """Paired split-conformal leave-one-case-out: raw base score vs learned score.

    cases: iterable of (prob_map, expert_mask). second_masks (optional): a parallel
    list of second-model masks for the agreement feature. Returns the uncontrolled
    baseline and two curves — `curve_raw` (Phase 1) and `curve_learned` (Phase 2) —
    computed on the SAME per-fold calibration set and test case, so the sensitivity
    lift at matched FDR is attributable to the score alone.
    """
    cases = list(cases)
    second_masks = second_masks if second_masks is not None else [None] * len(cases)
    tables = [build_case_table(p, g, threshold, voxel_spacing, min_volume_mm3,
                               score, min_overlap, sm)
              for (p, g), sm in zip(cases, second_masks)]
    n = len(tables)
    if n < 2:
        raise ValueError("need >= 2 cases for leave-one-out")

    # Uncontrolled baseline (keep every candidate above threshold).
    base_fdr, base_sens, base_nsel = [], [], []
    for t in tables:
        keep_all = np.ones(t["raw"].size, dtype=bool)
        f, s, k = _fdr_and_sens(t, keep_all)
        base_fdr.append(f); base_sens.append(s); base_nsel.append(k)

    # Per fold: split TRAIN/CALIB, fit a scorer on TRAIN, and precompute the
    # learned scores for the CALIB cases and the test case (all out-of-sample).
    folds = []
    for i in range(n):
        train_idx, calib_idx = _split_others(n, i)
        scorer = _fit_fold_scorer(tables, train_idx, l2, lr, n_iter)
        learned = None
        if scorer is not None:
            learned = {j: (scorer.score(tables[j]["X"]) if tables[j]["X"].shape[0] else np.zeros(0))
                       for j in calib_idx + [i]}
        folds.append((calib_idx, scorer, learned))

    def _curve(use_learned):
        curve = []
        for alpha in alpha_grid:
            fdrs, senss, nsels = [], [], []
            for i, (calib_idx, scorer, learned) in enumerate(folds):
                table = tables[i]
                if use_learned and scorer is None:
                    # No usable scorer this fold -> fall back to raw so the curve
                    # stays defined and the comparison stays paired.
                    src = {j: tables[j]["raw"] for j in calib_idx + [i]}
                elif use_learned:
                    src = learned
                else:
                    src = {j: tables[j]["raw"] for j in calib_idx + [i]}
                null = np.concatenate([src[j][~tables[j]["tp"]]
                                       for j in calib_idx if tables[j]["raw"].size]) \
                    if calib_idx else np.zeros(0)
                sel = _select_on_case(src[i], null, alpha)
                f, s, k = _fdr_and_sens(table, sel)
                fdrs.append(f); senss.append(s); nsels.append(k)
            lo, hi = bootstrap_ci_mean(fdrs, seed=boot_seed)
            curve.append({
                "alpha": float(alpha),
                "realized_fdr_mean": float(np.mean(fdrs)),
                "realized_fdr_ci95": [lo, hi],
                "sensitivity_mean": float(np.mean(senss)),
                "n_selected_mean": float(np.mean(nsels)),
            })
        return curve

    return {
        "n_cases": n,
        "baseline": {
            "fdr_mean": float(np.mean(base_fdr)),
            "sensitivity_mean": float(np.mean(base_sens)),
            "n_selected_mean": float(np.mean(base_nsel)),
        },
        "curve_raw": _curve(False),
        "curve_learned": _curve(True),
    }
