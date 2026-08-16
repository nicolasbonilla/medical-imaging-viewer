"""Multi-case benchmark aggregation for MS lesion segmentation (CALM-MS C4).

Turns a list of per-case metric dicts (each from compare_two_masks) into a
publishable summary: mean/median/std/IQR, bootstrap 95% CIs, and both MICRO
(pool TP/FP/FN across the cohort) and MACRO (mean of per-case F1) lesion-detection
scores — the standardized reporting the field's "rethinking evaluation" work asks
for. Pure NumPy, deterministic, unit-testable.
"""
from __future__ import annotations

import numpy as np


def _clean(values):
    a = np.asarray([v for v in values if isinstance(v, (int, float)) and np.isfinite(v)], dtype=float)
    return a


def summary_stats(values) -> dict:
    """mean/median/std/IQR/min/max/n over the finite values."""
    a = _clean(values)
    if a.size == 0:
        return {"n": 0, "mean": None, "median": None, "std": None,
                "iqr": None, "min": None, "max": None}
    q1, q3 = np.percentile(a, [25, 75])
    return {
        "n": int(a.size),
        "mean": float(a.mean()),
        "median": float(np.median(a)),
        "std": float(a.std(ddof=1)) if a.size > 1 else 0.0,
        "iqr": float(q3 - q1),
        "min": float(a.min()),
        "max": float(a.max()),
    }


def bootstrap_ci_mean(values, n_boot: int = 2000, conf: float = 0.95, seed: int = 0):
    """Percentile bootstrap CI for the MEAN. Returns (lo, hi) or (None, None)."""
    a = _clean(values)
    if a.size == 0:
        return (None, None)
    if a.size == 1:
        return (float(a[0]), float(a[0]))
    rng = np.random.RandomState(seed)
    idx = rng.randint(0, a.size, size=(n_boot, a.size))
    means = a[idx].mean(axis=1)
    lo_q = (1.0 - conf) / 2.0
    lo, hi = np.percentile(means, [100 * lo_q, 100 * (1.0 - lo_q)])
    return (float(lo), float(hi))


def aggregate_metrics(per_case: list[dict], metric_keys, seed: int = 0) -> dict:
    """For each metric key, summary stats + bootstrap 95% CI of the mean."""
    out = {}
    for k in metric_keys:
        vals = [row.get(k) for row in per_case]
        s = summary_stats(vals)
        lo, hi = bootstrap_ci_mean(vals, seed=seed)
        s["ci95_low"], s["ci95_high"] = lo, hi
        out[k] = s
    return out


def micro_macro_lesion_f1(per_case_counts: list[dict]) -> dict:
    """Aggregate lesion-detection counts.

    per_case_counts: dicts with true_positives / false_positives / false_negatives
    (as compute_lesion_detection_metrics emits). Reports:
      - MICRO: pool TP/FP/FN over the whole cohort, then P/R/F1 (large lesions and
        lesion-heavy cases dominate).
      - MACRO: mean of each case's own F1 (every patient weighs equally).
    """
    tp = sum(int(c.get("true_positives", 0)) for c in per_case_counts)
    fp = sum(int(c.get("false_positives", 0)) for c in per_case_counts)
    fn = sum(int(c.get("false_negatives", 0)) for c in per_case_counts)

    def _prf(tp, fp, fn):
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        return prec, rec, f1

    micro_p, micro_r, micro_f1 = _prf(tp, fp, fn)

    per_case_f1 = []
    for c in per_case_counts:
        _, _, f1 = _prf(int(c.get("true_positives", 0)),
                        int(c.get("false_positives", 0)),
                        int(c.get("false_negatives", 0)))
        per_case_f1.append(f1)
    macro_f1 = float(np.mean(per_case_f1)) if per_case_f1 else 0.0

    return {
        "micro_precision": micro_p, "micro_recall": micro_r, "micro_f1": micro_f1,
        "macro_f1": macro_f1,
        "pooled_tp": tp, "pooled_fp": fp, "pooled_fn": fn,
        "n_cases": len(per_case_counts),
    }
