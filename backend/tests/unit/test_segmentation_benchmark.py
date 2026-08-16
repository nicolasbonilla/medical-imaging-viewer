"""Multi-case benchmark aggregation (CALM-MS C4) + Jaccard/AVD metrics."""
import numpy as np
import pytest

from app.services.segmentation_benchmark import (
    summary_stats,
    bootstrap_ci_mean,
    aggregate_metrics,
    micro_macro_lesion_f1,
)
from app.services.segmentation_comparison_service import compute_jaccard, compute_avd


# --- summary / bootstrap ----------------------------------------------------

def test_summary_stats_basic():
    s = summary_stats([1, 2, 3, 4, 5])
    assert s["n"] == 5
    assert s["mean"] == pytest.approx(3.0)
    assert s["median"] == pytest.approx(3.0)
    assert s["min"] == 1 and s["max"] == 5
    assert s["iqr"] == pytest.approx(2.0)


def test_summary_ignores_non_finite():
    s = summary_stats([1.0, float("inf"), None, 3.0, float("nan")])
    assert s["n"] == 2
    assert s["mean"] == pytest.approx(2.0)


def test_summary_empty():
    s = summary_stats([])
    assert s["n"] == 0 and s["mean"] is None


def test_bootstrap_ci_contains_mean_and_is_ordered():
    rng = np.random.RandomState(0)
    vals = rng.normal(0.5, 0.1, size=200).tolist()
    lo, hi = bootstrap_ci_mean(vals, seed=0)
    assert lo < np.mean(vals) < hi
    # narrow-ish for n=200
    assert (hi - lo) < 0.06


def test_bootstrap_is_deterministic():
    vals = [0.1, 0.5, 0.9, 0.3, 0.7]
    assert bootstrap_ci_mean(vals, seed=1) == bootstrap_ci_mean(vals, seed=1)


def test_bootstrap_singleton():
    assert bootstrap_ci_mean([0.42]) == (0.42, 0.42)


def test_aggregate_metrics_shape():
    per_case = [{"dice": 0.5, "hd95": 10.0}, {"dice": 0.7, "hd95": 5.0}, {"dice": 0.6, "hd95": float("inf")}]
    agg = aggregate_metrics(per_case, ["dice", "hd95"])
    assert agg["dice"]["n"] == 3
    assert agg["dice"]["mean"] == pytest.approx(0.6)
    assert "ci95_low" in agg["dice"] and "ci95_high" in agg["dice"]
    # hd95 inf is dropped
    assert agg["hd95"]["n"] == 2


# --- micro / macro ----------------------------------------------------------

def test_micro_vs_macro_differ_with_imbalance():
    # Case 1: tiny, perfect. Case 2: huge, poor. Micro (pooled) is dominated by
    # the big case; macro weighs both equally.
    counts = [
        {"true_positives": 1, "false_positives": 0, "false_negatives": 0},   # F1=1.0
        {"true_positives": 10, "false_positives": 90, "false_negatives": 10}, # F1 low
    ]
    r = micro_macro_lesion_f1(counts)
    assert r["pooled_tp"] == 11 and r["pooled_fp"] == 90 and r["pooled_fn"] == 10
    # macro averages 1.0 and the low one -> clearly above micro
    assert r["macro_f1"] > r["micro_f1"]
    assert 0.0 <= r["micro_f1"] <= 1.0


def test_micro_macro_empty():
    r = micro_macro_lesion_f1([])
    assert r["micro_f1"] == 0.0 and r["macro_f1"] == 0.0 and r["n_cases"] == 0


# --- Jaccard / AVD ----------------------------------------------------------

def _cube(shape, sl):
    m = np.zeros(shape, np.uint8); m[sl] = 1; return m


def test_jaccard_identity_and_disjoint():
    a = _cube((10, 10, 10), np.s_[2:6, 2:6, 2:6])
    assert compute_jaccard(a, a.copy()) == pytest.approx(1.0)
    b = _cube((10, 10, 10), np.s_[7:9, 7:9, 7:9])
    assert compute_jaccard(a, b) == pytest.approx(0.0)


def test_jaccard_half_overlap():
    a = np.zeros((1, 1, 4), np.uint8); a[0, 0, :2] = 1  # {0,1}
    b = np.zeros((1, 1, 4), np.uint8); b[0, 0, 1:3] = 1  # {1,2}
    # inter={1}=1, union={0,1,2}=3 -> 1/3
    assert compute_jaccard(a, b) == pytest.approx(1 / 3)


def test_jaccard_empty_conventions():
    z = np.zeros((4, 4, 4), np.uint8)
    a = z.copy(); a[0, 0, 0] = 1
    assert compute_jaccard(z, z) == 1.0
    assert compute_jaccard(a, z) == 0.0


def test_avd_normalized_unsigned():
    sp = (1.0, 1.0, 1.0)
    # pred 8 vox, ref 10 vox -> |8-10|/10 = 0.2
    pred = _cube((4, 4, 4), np.s_[0:2, 0:2, 0:2])   # 8
    ref = np.zeros((4, 4, 4), np.uint8); ref.reshape(-1)[:10] = 1  # 10
    assert compute_avd(pred, ref, sp) == pytest.approx(0.2)
    # symmetric in magnitude (unsigned): swapping direction changes denominator only
    assert compute_avd(ref, pred, sp) == pytest.approx(2 / 8)


def test_avd_empty_ref():
    sp = (1.0, 1.0, 1.0)
    z = np.zeros((3, 3, 3), np.uint8)
    a = z.copy(); a[0, 0, 0] = 1
    assert compute_avd(z, z, sp) == 0.0
    assert compute_avd(a, z, sp) == 1.0
