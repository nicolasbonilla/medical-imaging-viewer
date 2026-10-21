#!/usr/bin/env python3
"""Tests for the Paper A v0.3 metric and selection functions (research/paper_a/v03_metrics.py).

Brute-force equivalences (p-values, BH, FDP curve, safe threshold), agreement with the committed
v0.2 implementations (CRC, LTT, naive threshold, Clopper-Pearson, AUROC), the classification
rule, and two Monte-Carlo validity checks: P1 (conformal BH) on exchangeable candidates and P2
(scan-conformal FDX threshold) on scans with a scan random effect.

    python -m pytest research/paper_a/test_v03_metrics.py -q
"""
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import baselines as bl          # noqa: E402  (v0.2)
import common as cm             # noqa: E402  (v0.2)
import v03_metrics as m         # noqa: E402


def test_conformal_pvalues_bruteforce():
    rng = np.random.RandomState(0)
    null = np.round(rng.rand(57), 2)            # ties on purpose
    s = np.round(rng.rand(30), 2)
    brute = np.array([(1 + (null >= x).sum()) / (null.size + 1) for x in s])
    assert np.allclose(m.conformal_pvalues(s, null), brute)


def _bh_brute(p, a):
    m_ = p.size
    ks = [k for k in range(1, m_ + 1) if np.sort(p)[k - 1] <= a * k / m_]
    if not ks:
        return np.zeros(m_, bool)
    return p <= np.sort(p)[max(ks) - 1]


@pytest.mark.parametrize("seed", range(20))
def test_bh_bruteforce(seed):
    rng = np.random.RandomState(seed)
    p = np.round(rng.beta(0.5, 2, size=rng.randint(1, 25)), 3)
    for a in (0.05, 0.1, 0.2, 0.3):
        assert (m.bh(p, a) == _bh_brute(p, a)).all()
        assert (m.bh(p, a) == bl._bh(p, a)).all()


def test_fdp_curve_and_safe_threshold_bruteforce():
    rng = np.random.RandomState(1)
    for _ in range(50):
        n = rng.randint(0, 30)
        s = np.round(rng.rand(n), 3)
        f = rng.rand(n) < 0.4
        curve = m.fdp_curve(s, f)
        for i in rng.randint(0, m.GRID.size, 40):
            lam = m.GRID[i]
            sel = s >= lam
            want = (sel & f).sum() / sel.sum() if sel.sum() else 0.0
            assert abs(curve[i] - want) < 1e-12
        for g in (0.1, 0.2):
            t = m.safe_threshold(s, f, g)
            j = int(np.nonzero(m.GRID == t)[0][0])
            assert (curve[j:] <= g + 1e-12).all()
            if j > 0:
                assert curve[j - 1] > g


def test_fdx_threshold_index_and_abstention():
    assert m.fdx_threshold(np.arange(8) / 10.0, 0.1) == float("inf")      # K=8: ceil(8.1)=9 > 8
    assert m.fdx_threshold(np.arange(9) / 10.0, 0.1) == 0.8                # K=9: 9th smallest
    t = np.random.RandomState(2).rand(99)
    assert m.fdx_threshold(t, 0.1) == np.sort(t)[math.ceil(100 * 0.9) - 1]


def test_crc_ltt_match_v02_on_v02_grid():
    rng = np.random.RandomState(3)
    cal = []
    for _ in range(40):
        n = rng.randint(1, 15)
        s = 0.5 + 0.5 * rng.rand(n)
        cal.append((s, rng.rand(n) < 0.35))
    v02 = [{"scores": s, "isf": f} for s, f in cal]
    for a in (0.1, 0.2, 0.3):
        assert m.crc_threshold(cal, a, grid=bl.LAMBDAS) == bl.crc_threshold(v02, a)
        assert m.ltt_threshold(cal, a, 0.1, grid=bl.LAMBDAS) == bl.ltt_threshold(v02, a, 0.1)


def test_naive_threshold_matches_v02():
    rng = np.random.RandomState(4)
    s = rng.rand(300)
    f = rng.rand(300) < (1 - s)
    import reanalysis_v02 as rv
    for a in (0.1, 0.2, 0.3):
        assert m.naive_threshold(s, f, a) == rv.naive_tau([{"scores": s, "isf": f}], a)


def test_scan_row_counts():
    sel = np.array([1, 1, 0, 1, 1], bool)
    isf = np.array([0, 1, 0, 0, 0], bool)
    mg = np.array([3, 0, 5, 3, 7])                      # two candidates hit lesion 3 (not possible
    r = m.scan_row(sel, isf, mg, [3, 5, 7, 9], [20.0, 5.0, 100.0, 4.0])   # 1:1, but count by id)
    assert (r["ns"], r["nf"], r["hits"], r["n_gt"], r["det"]) == (4, 1, 2, 4, 3)
    assert r["fdp"] == 0.25 and r["hits_clin"] == 2 and r["n_clin"] == 2
    e = m.scan_row(np.zeros(0, bool), np.zeros(0, bool), np.zeros(0, int), [1], [10.0])
    assert e["fdp"] == 0.0 and e["ns"] == 0


def test_bootstrap_weights_and_ratio_ci():
    rng = np.random.RandomState(5)
    W = m.bootstrap_weights(7, 300, rng)
    assert W.shape == (300, 7) and (W.sum(1) == 7).all()
    lo, hi = m.ratio_ci(np.full(7, 2.0), np.full(7, 4.0), W)
    assert abs(lo - 0.5) < 1e-12 and abs(hi - 0.5) < 1e-12


def test_clopper_pearson_and_auroc_match_v02():
    for x, n in ((0, 30), (3, 10), (10, 10), (17, 30)):
        assert np.allclose(m.clopper_pearson(x, n), cm.clopper_pearson(x, n), atol=1e-4)
    rng = np.random.RandomState(6)
    s = rng.rand(200)
    y = rng.rand(200) < s
    assert abs(m.auroc(s, y) - cm.auroc(s, y)) < 1e-12


def test_classify():
    assert m.classify([0.12, 0.2], 0.1) == "violated"
    assert m.classify([0.0, 0.15], 0.1) == "holds"
    assert m.classify([0.05, 0.16], 0.1) == "inconclusive"
    assert m.classify([None, None], 0.1) == "undefined"


def test_icc1():
    rng = np.random.RandomState(7)
    iid = [rng.randn(10) for _ in range(200)]
    clus = [rng.randn() + rng.randn(10) for _ in range(200)]
    assert abs(m.icc1(iid)) < 0.05
    assert 0.35 < m.icc1(clus) < 0.65


def test_min_reliable_size():
    edges = [3, 14.14, 50, 150, 500]
    assert m.min_reliable_size(edges, [0.2, 0.6, 0.85, 0.9, 0.95], [50] * 5) == (50.0, "ok")
    assert m.min_reliable_size(edges, [0.2, 0.9, 0.7, 0.9, 0.95], [50] * 5) == (150.0, "ok")
    assert m.min_reliable_size(edges, [0.2, 0.6, 0.7, 0.7, 0.5], [50] * 5) == (None, "ok")
    assert m.min_reliable_size(edges, [0.2, 0.6, 0.85, 0.9, 0.95], [50, 50, 50, 50, 4]) == (50.0, "insufficient")


def _scan(rng, tau, mu=1.5):
    u = rng.normal(0, tau)
    n0, n1 = rng.poisson(5) + 1, rng.poisson(8)
    s = np.r_[rng.normal(u, 1, n0), rng.normal(u + mu, 1, n1)]
    return 1 / (1 + np.exp(-s)), np.r_[np.ones(n0, bool), np.zeros(n1, bool)]


def test_p1_conformal_bh_valid_on_exchangeable_candidates():
    rng = np.random.RandomState(8)
    fdps = []
    for _ in range(1500):
        null = 1 / (1 + np.exp(-rng.normal(0, 1, 200)))
        s, f = _scan(rng, 0.0)
        sel = m.conformal_bh([s], null, 0.2)[0]
        fdps.append((sel & f).sum() / sel.sum() if sel.sum() else 0.0)
    fdps = np.array(fdps)
    assert fdps.mean() <= 0.2 + 3 * fdps.std() / np.sqrt(fdps.size)


def test_p2_fdx_threshold_valid_with_scan_random_effect():
    rng = np.random.RandomState(9)
    bad = []
    for _ in range(1500):
        cal = [_scan(rng, 0.8) for _ in range(29)]
        lam = m.fdx_threshold([m.safe_threshold(s, f, 0.2) for s, f in cal], 0.1)
        s, f = _scan(rng, 0.8)
        sel = s >= lam
        bad.append(sel.sum() > 0 and (sel & f).sum() / sel.sum() > 0.2)
    bad = np.array(bad, float)
    assert bad.mean() <= 0.1 + 3 * np.sqrt(0.1 * 0.9 / bad.size)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
