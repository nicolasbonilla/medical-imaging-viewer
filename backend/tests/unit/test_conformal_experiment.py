"""The CALM-MS headline experiment (leave-one-case-out FDR coverage).

Verifies the plot that is the paper: across held-out cases, realized FDR tracks
at or below the target alpha, while the uncontrolled baseline sits far higher —
exactly the over-segmentation the conformal dial removes.
"""
import numpy as np
import pytest

from app.services.conformal_experiment import run_loo_fdr_experiment

SP = (1.0, 1.0, 1.0)
THR = 0.5


def _synthetic_case(rng, n_true=6, n_false=10, shape=(20, 60, 60),
                    true_p=0.86, false_p=0.62, sigma=0.03):
    prob = rng.uniform(0.0, 0.12, size=shape)
    gt = np.zeros(shape, np.uint8)
    positions = [(z, y, x)
                 for z in range(2, shape[0] - 3, 5)
                 for y in range(2, shape[1] - 4, 8)
                 for x in range(2, shape[2] - 4, 8)]
    rng.shuffle(positions)
    for i, (z, y, x) in enumerate(positions[:n_true + n_false]):
        base = true_p if i < n_true else false_p
        block = np.clip(base + rng.normal(0, sigma, size=(3, 3, 3)), 0, 1)
        prob[z:z + 3, y:y + 3, x:x + 3] = block
        if i < n_true:
            gt[z:z + 3, y:y + 3, x:x + 3] = 1
    return prob, gt


def _cohort(seed, n_cases=12):
    rng = np.random.RandomState(seed)
    return [_synthetic_case(rng) for _ in range(n_cases)]


def test_loo_controls_fdr_and_beats_baseline():
    res = run_loo_fdr_experiment(_cohort(0), [0.05, 0.1, 0.2], THR, SP)
    assert res["n_cases"] == 12
    # Uncontrolled baseline over-segments: many false candidates kept.
    assert res["baseline"]["fdr_mean"] > 0.3
    for row in res["curve"]:
        # realized FDR at or below target (small MC slack), and strictly better
        # than the uncontrolled baseline.
        assert row["realized_fdr_mean"] <= row["alpha"] + 0.05, row
        assert row["realized_fdr_mean"] < res["baseline"]["fdr_mean"], row
        assert len(row["realized_fdr_ci95"]) == 2


def test_curve_is_a_tradeoff():
    res = run_loo_fdr_experiment(_cohort(1), [0.02, 0.05, 0.1, 0.2, 0.4], THR, SP)
    fdrs = [r["realized_fdr_mean"] for r in res["curve"]]
    sens = [r["sensitivity_mean"] for r in res["curve"]]
    # Loosening alpha admits more -> realized FDR and sensitivity both rise
    # (monotone non-decreasing).
    assert fdrs == sorted(fdrs), fdrs
    assert sens == sorted(sens), sens
    # Baseline recovers ~all true lesions (its problem is precision, not recall).
    assert res["baseline"]["sensitivity_mean"] > 0.95


def test_requires_two_cases():
    rng = np.random.RandomState(3)
    with pytest.raises(ValueError):
        run_loo_fdr_experiment([_synthetic_case(rng)], [0.1], THR, SP)
