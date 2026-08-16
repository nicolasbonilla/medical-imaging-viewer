"""Conformal, distribution-free lesion-level false-discovery control.

CALM-MS core contribution (C1). Given a base segmenter that emits lesion
CANDIDATES, each with a confidence score (higher = more likely a true lesion),
this turns the score into a GUARANTEED operating point: it selects a subset of
candidates whose expected false-discovery proportion is <= alpha, with NO
distributional assumption on the scores.

This is what converts today's uncontrolled over-segmentation (measured on our own
data: lesion precision ~0.22) into a clinician-set, provable dial.

Method — conformal selection (Jin & Candes 2023; Bates et al. 2023):
  1. Calibrate on held-out cases where every candidate is known true (TP) or
     false (FP). Keep the scores of the FALSE candidates -> the null calibration
     set {c_1, ..., c_n}.
  2. For a test candidate with score s, the conformal p-value
         p = (1 + #{i : c_i >= s}) / (n + 1)
     is super-uniform under the null (the candidate is truly false), by
     exchangeability of the null scores.
  3. Benjamini-Hochberg on the test p-values at level alpha selects a subset with
     FDR <= alpha.

Model-agnostic: it wraps LST-AI, nnU-Net, a foundation model, or the legacy AI
identically — the calibration set is the only thing it needs. It is both the
product's "false-positive tolerance" slider and the paper's statistical
guarantee.

Pure NumPy, no I/O, no app imports -> unit-testable in isolation and reusable by
the benchmark and the serving path.
"""
from __future__ import annotations

import numpy as np


def conformal_pvalues(test_scores, calib_null_scores) -> np.ndarray:
    """Conformal p-values for each test candidate against the null calibration set.

    p_j = (1 + #{c_i >= s_j}) / (n + 1). Super-uniform under the null, so small p
    means "unlikely to be a false positive" (i.e. likely a real lesion).
    """
    test = np.asarray(test_scores, dtype=float).ravel()
    calib = np.asarray(calib_null_scores, dtype=float).ravel()
    n = calib.size
    if n == 0:
        raise ValueError("conformal calibration null set is empty")
    calib_sorted = np.sort(calib)
    # #{c_i >= s} = n - #{c_i < s} = n - searchsorted(sorted_calib, s, 'left')
    ge = n - np.searchsorted(calib_sorted, test, side="left")
    return (1.0 + ge) / (n + 1.0)


def benjamini_hochberg(pvalues, alpha: float) -> np.ndarray:
    """Boolean selection mask from the Benjamini-Hochberg procedure at level alpha.

    Selects every p-value <= p_(k*), where k* is the largest rank k with
    p_(k) <= alpha * k / m. Controls FDR under independence / PRDS — which the
    shared-calibration conformal p-values satisfy.
    """
    p = np.asarray(pvalues, dtype=float).ravel()
    m = p.size
    if m == 0:
        return np.zeros(0, dtype=bool)
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    order = np.argsort(p, kind="mergesort")
    ranked = p[order]
    thresh = alpha * (np.arange(1, m + 1) / m)
    below = np.nonzero(ranked <= thresh)[0]
    if below.size == 0:
        return np.zeros(m, dtype=bool)
    cutoff = ranked[below.max()]
    return p <= cutoff


def select_by_fdr(test_scores, calib_null_scores, alpha: float):
    """Select lesion candidates at a guaranteed lesion-level FDR <= alpha.

    Returns (selected_mask: bool[m], pvalues: float[m]). `selected_mask[j]` True
    means candidate j is kept as a real lesion at the chosen operating point.
    """
    pv = conformal_pvalues(test_scores, calib_null_scores)
    sel = benjamini_hochberg(pv, alpha)
    return sel, pv


def effective_score_cutoff(test_scores, selected_mask) -> float | None:
    """The lowest score among selected candidates — the equivalent hard threshold
    of the (adaptive) selection, useful for UI display / audit. None if empty."""
    test = np.asarray(test_scores, dtype=float).ravel()
    sel = np.asarray(selected_mask, dtype=bool).ravel()
    if not sel.any():
        return None
    return float(test[sel].min())
