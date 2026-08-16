"""Conformal lesion-level FDR control (CALM-MS C1).

The headline test does what the paper must claim: over many simulated cohorts,
the REALIZED lesion-level false-discovery proportion stays at or below the target
alpha — the guarantee, verified by Monte Carlo, not asserted.
"""
import numpy as np
import pytest

from app.services.conformal_lesion_fdr import (
    conformal_pvalues,
    benjamini_hochberg,
    select_by_fdr,
    effective_score_cutoff,
)


# --- component correctness --------------------------------------------------

def test_conformal_pvalue_formula():
    calib = np.array([0.1, 0.2, 0.3, 0.4])  # n=4
    # s=0.35 -> #{c>=0.35}=1 (0.4) -> p=(1+1)/5=0.4
    assert conformal_pvalues([0.35], calib)[0] == pytest.approx(0.4)
    # s above all -> #{c>=s}=0 -> p=1/5=0.2 (smallest possible)
    assert conformal_pvalues([0.99], calib)[0] == pytest.approx(0.2)
    # s below all -> #{c>=s}=4 -> p=5/5=1.0
    assert conformal_pvalues([0.0], calib)[0] == pytest.approx(1.0)


def test_conformal_pvalue_empty_calib_raises():
    with pytest.raises(ValueError):
        conformal_pvalues([0.5], [])


def test_pvalue_monotone_in_score():
    calib = np.random.RandomState(0).beta(2, 5, size=100)
    scores = np.linspace(0, 1, 25)
    pv = conformal_pvalues(scores, calib)
    # higher score -> smaller (or equal) p-value
    assert np.all(np.diff(pv) <= 1e-12)


def test_bh_basic():
    # classic BH example
    p = np.array([0.01, 0.02, 0.03, 0.9])
    sel = benjamini_hochberg(p, 0.05)
    assert sel.tolist() == [True, True, True, False]


def test_bh_selects_none_when_all_large():
    assert benjamini_hochberg(np.array([0.5, 0.7, 0.9]), 0.1).sum() == 0


def test_bh_rejects_bad_alpha():
    with pytest.raises(ValueError):
        benjamini_hochberg(np.array([0.1]), 1.5)


def test_effective_cutoff():
    scores = np.array([0.9, 0.8, 0.2, 0.1])
    sel = np.array([True, True, False, False])
    assert effective_score_cutoff(scores, sel) == pytest.approx(0.8)
    assert effective_score_cutoff(scores, np.zeros(4, bool)) is None


# --- the guarantee: realized FDR <= alpha -----------------------------------

@pytest.mark.parametrize("alpha", [0.05, 0.10, 0.20])
def test_fdr_is_controlled_on_average(alpha):
    """Monte Carlo: mean realized false-discovery proportion <= alpha.

    True lesions score high (Beta(6,2)); false candidates score low (Beta(2,6)).
    Calibration nulls are drawn from the SAME false distribution (exchangeable),
    which is exactly the assumption the guarantee needs.
    """
    rng = np.random.RandomState(42)
    fdps = []
    n_trials = 400
    for _ in range(n_trials):
        calib_null = rng.beta(2, 6, size=300)
        n_true, n_false = 50, 100
        true_scores = rng.beta(6, 2, size=n_true)
        false_scores = rng.beta(2, 6, size=n_false)
        test = np.concatenate([true_scores, false_scores])
        is_false = np.concatenate([np.zeros(n_true, bool), np.ones(n_false, bool)])
        sel, _ = select_by_fdr(test, calib_null, alpha)
        if sel.sum() > 0:
            fdps.append((sel & is_false).sum() / sel.sum())
    mean_fdp = float(np.mean(fdps))
    # BH controls E[FDP] <= alpha * (m0/m) <= alpha; allow small MC slack.
    assert mean_fdp <= alpha + 0.02, (mean_fdp, alpha)


def test_dial_is_monotone():
    """Loosening the FDR target never selects FEWER lesions — the 'dial' behaves."""
    rng = np.random.RandomState(1)
    calib = rng.beta(2, 6, size=300)
    test = np.concatenate([rng.beta(6, 2, size=40), rng.beta(2, 6, size=80)])
    counts = [select_by_fdr(test, calib, a)[0].sum() for a in (0.01, 0.05, 0.1, 0.2, 0.4)]
    assert counts == sorted(counts), counts


def test_high_power_on_easy_case():
    """When true and false are well separated, most true lesions are recovered."""
    rng = np.random.RandomState(7)
    calib = rng.beta(1.5, 12, size=400)           # nulls very low
    true_scores = rng.beta(12, 1.5, size=60)      # trues very high
    false_scores = rng.beta(1.5, 12, size=90)
    test = np.concatenate([true_scores, false_scores])
    is_true = np.concatenate([np.ones(60, bool), np.zeros(90, bool)])
    sel, _ = select_by_fdr(test, calib, 0.1)
    recovered = (sel & is_true).sum() / is_true.sum()
    assert recovered > 0.8, recovered
