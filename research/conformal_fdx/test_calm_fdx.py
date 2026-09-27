"""Tests for CALM-FDX (CPU, synthetic, seconds-to-minutes).

    backend/venv/Scripts/python -m pytest research/conformal_fdx -q
"""
import itertools
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calm_fdx as cf  # noqa: E402


def _brute_cross(n, r, G):
    """Enumerate all C(n+r, r) interleavings; V_k = #tests before the k-th calibration point."""
    bad = tot = 0
    for pos in itertools.combinations(range(n + r), r):
        pos = np.array(pos)
        # rank of test i among descending pooled order -> #calib before it = pos[i] - i
        k = 1 + (pos - np.arange(r))                       # conformal rank in 1..n+1
        V = np.cumsum(np.bincount(k, minlength=n + 2))[1:n + 2]
        bad += bool(np.any(V > G))
        tot += 1
    return bad / tot


@pytest.mark.parametrize("n,r", [(6, 3), (8, 4), (10, 2), (5, 5)])
def test_crossing_prob_equals_brute_force(n, r):
    rng = np.random.default_rng(n * 10 + r)
    for _ in range(6):
        G = np.sort(rng.integers(0, r + 1, size=n + 1))
        assert abs(cf.crossing_prob(n, r, G)[0] - _brute_cross(n, r, G)) < 1e-12


def test_crossing_prob_matches_monte_carlo():
    n, r = 120, 30
    G = cf.env_hc(n, r, [2.0])[0]
    exact = cf.crossing_prob(n, r, G)[0]
    rng = np.random.default_rng(1)
    hits, reps = 0, 20000
    for _ in range(reps):
        k, _ = cf.conformal_ranks(rng.random(r), rng.random(n))
        V = np.cumsum(np.bincount(k, minlength=n + 2))[1:n + 2]
        hits += np.any(V > G)
    se = math.sqrt(exact * (1 - exact) / reps)
    assert abs(hits / reps - exact) < 4 * se + 1e-3


@pytest.mark.parametrize("template", ["hc", "simes", "hybrid"])
def test_calibrated_envelope_is_certified(template):
    for n, r in [(200, 10), (200, 80), (600, 40)]:
        G, cp = cf.calibrate(n, r, 0.1, template)
        assert cp <= 0.1 and (np.diff(G) >= 0).all() and G.max() <= r
        assert abs(cf.crossing_prob(n, r, G)[0] - cp) < 1e-12


def test_completion_coupling_fewer_nulls_cross_less():
    n, r = 200, 40
    G, cp = cf.calibrate(n, r, 0.1, "hc")
    for m0 in (5, 20, 39):
        Gm = np.minimum(G, G)  # same envelope, fewer nulls
        assert cf.crossing_prob(n, m0, Gm)[0] <= cp + 1e-12


def test_kr_closed_form_constant_is_invalid_under_conformal_dependence():
    """Positive control: Katsevich-Ramdas' closed-form constant assumes independence."""
    delta = 0.1
    L = math.log(1 / delta)
    c = L / math.log(1 + L)
    n, r = 200, 100
    t = np.arange(1, n + 2) / (n + 1)
    G = np.minimum(np.floor(c * (1 + r * t)).astype(np.int64), r)
    assert cf.crossing_prob(n, r, G)[0] > delta


def _sim_scan(rng, n, m0, m1, mu):
    cal = rng.standard_normal(n)
    s = np.r_[rng.standard_normal(m0), rng.standard_normal(m1) + mu]
    isf = np.r_[np.ones(m0, bool), np.zeros(m1, bool)]
    k, _ = cf.conformal_ranks(s, cal)
    return k, isf


@pytest.mark.parametrize("template", ["hc", "hybrid"])
@pytest.mark.parametrize("n,m0,m1,mu", [(200, 10, 0, 0.0), (200, 7, 3, 4.0), (300, 20, 20, 2.5),
                                         (150, 3, 7, 6.0)])
def test_fdx_validity_exchangeable(template, n, m0, m1, mu):
    fam = cf.EnvelopeFamily(0.1, template)
    rng = np.random.default_rng(n * 1000 + m0 * 10 + m1 + (0 if template == "hc" else 7))
    reps, exceed = 1500, 0
    for _ in range(reps):
        k, isf = _sim_scan(rng, n, m0, m1, mu)
        sel, _ = cf.select_fdx(k, n, 0.2, fam)
        ns = sel.sum()
        exceed += ns > 0 and (sel & isf).sum() / ns > 0.2
    p = exceed / reps
    assert p <= 0.1 + 3 * math.sqrt(0.1 * 0.9 / reps), p


def test_region_bounds_valid_and_dis_rarely_false_on_all_null():
    """All candidates null: any certified DIS is false; must happen <= delta."""
    fam = cf.EnvelopeFamily(0.1, "hybrid")
    rng = np.random.default_rng(7)
    reps, false_dis, bound_violations = 1500, 0, 0
    n = 250
    for _ in range(reps):
        m = int(rng.integers(5, 40))
        k, _ = cf.conformal_ranks(rng.standard_normal(m), rng.standard_normal(n))
        Bstar, R, _ = cf.simultaneous_bound(k, n, fam)
        regions = rng.integers(1, 5, size=m)
        dis, lb = cf.certify_dis(regions, k, Bstar)
        false_dis += dis
        bound_violations += any(v > 0 for v in lb.values())   # any certified true lesion is wrong
    se = math.sqrt(0.1 * 0.9 / reps)
    assert false_dis / reps <= 0.1 + 3 * se
    assert bound_violations / reps <= 0.1 + 3 * se


def test_null_upper_bound_invariant_on_good_event():
    """Whenever V_k <= B*_k for all k (event E), the subset bound holds for every subset."""
    fam = cf.EnvelopeFamily(0.1, "hc")
    rng = np.random.default_rng(3)
    n = 200
    for _ in range(300):
        k, isf = _sim_scan(rng, n, int(rng.integers(1, 30)), int(rng.integers(0, 20)), 3.0)
        Bstar, R, _ = cf.simultaneous_bound(k, n, fam)
        V = np.cumsum(np.bincount(k[isf], minlength=n + 2))[1:n + 2]
        if np.all(V <= Bstar):
            for _ in range(5):
                S = rng.random(k.size) < 0.5
                assert (S & isf).sum() <= cf.null_upper_bound(S, k, Bstar)


def test_selection_is_nested_in_inflation():
    fam = cf.EnvelopeFamily(0.1, "hc")
    rng = np.random.default_rng(11)
    k, _ = _sim_scan(rng, 300, 15, 25, 3.0)
    sizes = [cf.select_fdx(k, 300, 0.2, fam, inflate=c)[0].sum() for c in range(0, 12)]
    assert all(a >= b for a, b in zip(sizes, sizes[1:]))


def test_scan_level_quantile():
    assert cf.scan_level_theta(list(range(9)), 0.1) == 8          # K=9 -> max
    assert cf.scan_level_theta(list(range(8)), 0.1) is None       # K<9 -> abstain
    assert cf.scan_level_theta([0] * 29, 0.1) == 0


def test_bstar_is_monotone_in_inflation():
    fam = cf.EnvelopeFamily(0.1, "hc")
    rng = np.random.default_rng(21)
    for _ in range(40):
        k, _ = _sim_scan(rng, 250, int(rng.integers(1, 25)), int(rng.integers(0, 25)), 3.0)
        prev = None
        for c in range(0, 8):
            B = cf.simultaneous_bound(k, 250, fam, inflate=c)[0]
            if prev is not None:
                assert np.all(B >= prev)
            prev = B


def _clustered_scan(rng, n_fp, n_tp, tau, mu):
    u = rng.normal(0, tau)                       # scan random intercept (violates A1)
    s = np.r_[rng.normal(u, 1, n_fp), rng.normal(u + mu, 1, n_tp)]
    return s, np.r_[np.ones(n_fp, bool), np.zeros(n_tp, bool)]


def test_layer2_simultaneous_restores_curve_validity_under_scan_random_effect():
    """Worlds with ICC 0.5 (tau=1): the pool is clustered, K=29 labelled scans + 1 test scan,
    all exchangeable AT THE SCAN LEVEL only. Layer 2 calibrated on the simultaneous event must
    keep P(exists k: V_k > B*_k(theta_hat)) <= delta on the test scan."""
    rng = np.random.default_rng(2026)
    fam = cf.EnvelopeFamily(0.1, "hc")
    tau, mu, W, K = 1.0, 3.0, 400, 29
    fails = abstain = 0
    for _ in range(W):
        pool = np.concatenate([_clustered_scan(rng, 10, 0, tau, mu)[0] for _ in range(30)])  # n=300
        safes = []
        scans = [_clustered_scan(rng, int(rng.integers(2, 9)), int(rng.integers(2, 12)), tau, mu)
                 for _ in range(K + 1)]
        for s, isf in scans[:K]:
            k, n = cf.conformal_ranks(s, pool)
            safes.append(cf.scan_safe_inflation_simultaneous(k, n, isf, fam))
        theta = cf.scan_level_theta(safes, 0.1)
        s, isf = scans[K]
        k, n = cf.conformal_ranks(s, pool)
        if theta is None:
            abstain += 1
            continue
        B = cf.simultaneous_bound(k, n, fam, inflate=theta)[0]
        V = np.cumsum(np.bincount(k[isf], minlength=n + 2))[1:n + 2]
        fails += bool(np.any(V > B))
    assert fails / W <= 0.1 + 3 * math.sqrt(0.09 / W), (fails, abstain)


def test_scan_level_pac_quantile():
    assert cf.scan_level_theta_pac(list(range(29)), 0.1, 0.05) == 28     # K=29 -> max
    assert cf.scan_level_theta_pac(list(range(20)), 0.1, 0.05) is None   # K=20 infeasible
    v = list(range(60))
    assert cf.scan_level_theta_pac(v, 0.1, 0.05) >= cf.scan_level_theta(v, 0.1)  # PAC is stricter
