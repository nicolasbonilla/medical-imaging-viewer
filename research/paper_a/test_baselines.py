#!/usr/bin/env python3
"""Paper A v0.2 — sanity checks of the baseline implementations on synthetic CLUSTERED worlds
(scan random effect, group sizes independent of the scores so every method's assumptions hold).
Not a proof; it guards against implementation errors (a wrong sign, a missing +1) before the
methods are run on real data.

Checks (alpha = 0.2, delta = 0.1):
  * Lee & Ren hierarchical and subsampling e-values + e-BH: mean over worlds of the batch FDP
    <= alpha (+ 3 Monte-Carlo SE), in a SMALL world (40 calibration / 10 test scans, like our
    real designs) and a LARGE world (300 / 50); power is printed because the hierarchical variant
    has essentially no power with few groups (the "+1" terms dominate), which matters for the
    real-data comparison;
  * CRC global threshold: mean per-scan FDP on a fresh test scan <= alpha (+ 3 SE);
  * LTT: fraction of worlds whose TRUE expected per-scan FDP (estimated on 400 fresh scans)
    exceeds alpha is <= delta (+ 3 SE).

    python research/paper_a/test_baselines.py        (pytest-compatible too)
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import baselines as bl  # noqa: E402

ALPHA, DELTA = 0.2, 0.1


def _scan(rng, tau=0.5, m0=6, m1=10, mu=1.6):
    u = rng.normal(0, tau)
    n0, n1 = rng.poisson(m0) + 1, rng.poisson(m1)
    s = np.r_[rng.normal(u, 0.35, n0), rng.normal(u + mu * 0.35, 0.35, n1)]
    s = 0.5 + 0.5 / (1 + np.exp(-s))             # map to (0.5, 1) like a candidate's mean probability
    return {"scores": s, "isf": np.r_[np.ones(n0, bool), np.zeros(n1, bool)], "subject": None}


def _batch(test, sels):
    ns = sum(int(s.sum()) for s in sels)
    nf = sum(int((s & t["isf"]).sum()) for s, t in zip(sels, test))
    nt = sum(int((~t["isf"]).sum()) for t in test)
    return (nf / ns if ns else 0.0), (ns - nf) / max(nt, 1)


def run(seed=7):
    rng = np.random.default_rng(seed)
    r = np.random.RandomState(seed)
    out = {}
    for world, (K, M, W, mu) in {"small": (40, 10, 300, 1.6), "large": (300, 50, 100, 4.0)}.items():
        for v in ("hier", "sub"):
            out[f"leeren_{v}_{world}_fdp"], out[f"leeren_{v}_{world}_power"] = [], []
        for _ in range(W):
            cal = [_scan(rng, mu=mu) for _ in range(K)]
            test = [_scan(rng, mu=mu) for _ in range(M)]
            for v in ("hier", "sub"):
                fdp, pw = _batch(test, bl.leeren(cal, test, ALPHA, v, rng=r))
                out[f"leeren_{v}_{world}_fdp"].append(fdp)
                out[f"leeren_{v}_{world}_power"].append(pw)
    out["crc_fdp"], out["ltt_bad"] = [], []
    for _ in range(300):
        cal = [_scan(rng) for _ in range(40)]
        lam = bl.crc_threshold(cal, ALPHA)
        t = _scan(rng)
        sel = t["scores"] >= lam
        out["crc_fdp"].append(((sel & t["isf"]).sum() / sel.sum()) if sel.sum() else 0.0)
        lam = bl.ltt_threshold(cal, ALPHA, DELTA)
        fresh = [_scan(rng) for _ in range(400)]
        risk = np.mean([(((f["scores"] >= lam) & f["isf"]).sum() / max((f["scores"] >= lam).sum(), 1))
                        for f in fresh])
        out["ltt_bad"].append(risk > ALPHA)
    return {k: (float(np.mean(v)), float(np.std(v, ddof=1) / math.sqrt(len(v)))) for k, v in out.items()}


def test_baselines_valid():
    res = run()
    for k, (m, se) in res.items():
        if k.endswith("_fdp"):
            assert m <= ALPHA + 3 * se, (k, m, se)
    m, se = res["ltt_bad"]
    assert m <= DELTA + 3 * max(se, 0.01), ("ltt", m, se)
    assert res["leeren_hier_large_power"][0] > 0.1           # the implementation can select


if __name__ == "__main__":
    res = run()
    for k, (m, se) in res.items():
        print(f"{k:28s} mean {m:.4f}  (MC s.e. {se:.4f})")
    for k, (m, se) in res.items():
        if k.endswith("_fdp"):
            assert m <= ALPHA + 3 * se, (k, m, se)
    assert res["ltt_bad"][0] <= DELTA + 3 * max(res["ltt_bad"][1], 0.01)
    assert res["leeren_hier_large_power"][0] > 0.1
    print("all baseline sanity checks passed")
