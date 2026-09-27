#!/usr/bin/env python3
"""CALM-FDX synthetic study: does per-scan FDX survive a SCAN RANDOM EFFECT?

World model (the minimal A1 violation measured on real MS data): every false-candidate score of
scan i is N(u_i, 1) and every true one N(u_i + mu, 1), with a scan intercept u_i ~ N(0, tau^2);
ICC = tau^2 / (1 + tau^2). The calibration pool is itself clustered (P pool scans x 10 false
candidates each). Marginal score laws are identical in pool and test — only the clustering
differs, so any failure is due to the violated CANDIDATE-level exchangeability alone.

For each world we report, on one test scan:
  Layer 1 (candidate-level exact envelope):  P(curve violated), P(FDP > gamma), power
  Layer 2 (scan-level split-conformal on the simultaneous event, K labelled scans):
                                             P(curve violated), P(FDP > gamma), power, abstain
Regimes follow the real cohorts (MSLesSeg median: n ~ 1160, m0 ~ 8, m1 ~ 19; openms-like
n ~ 210) plus a few-false-candidate tight regime where Layer 1 has no slack.

    python research/conformal_fdx/synthetic_icc_study.py            (~10-20 min, all CPUs)
"""
import json
import math
import os
import sys
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calm_fdx as cf  # noqa: E402

GAMMA, DELTA, K = 0.2, 0.1, 29
ICCS = (0.0, 0.09, 0.23, 0.5)
REGIMES = {
    "mslesseg_like": dict(pool_scans=116, m0=8, m1=19, mu=3.0),     # n ~ 1160
    "tight_few_fp":  dict(pool_scans=116, m0=2, m1=6,  mu=4.0),
    "openms_like":   dict(pool_scans=21,  m0=5, m1=10, mu=3.0),     # n ~ 210
}
WORLDS = 1500
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synthetic_icc_record.json")


def _scan(rng, tau, m0, m1, mu):
    u = rng.normal(0, tau)
    s = np.r_[rng.normal(u, 1, m0), rng.normal(u + mu, 1, m1)]
    return s, np.r_[np.ones(m0, bool), np.zeros(m1, bool)]


def _eval(k, n, isf, fam, inflate):
    sel, info = cf.select_fdx(k, n, GAMMA, fam, inflate=inflate)
    V = np.cumsum(np.bincount(k[isf], minlength=n + 2))[1:n + 2]
    ns = int(sel.sum())
    return (bool(np.any(V > info["Bstar"])),
            bool(ns and (sel & isf).sum() / ns > GAMMA),
            int((sel & ~isf).sum()), int((~isf).sum()))


def run_config(args):
    regime, icc, seed = args
    cfg = REGIMES[regime]
    tau = math.sqrt(icc / (1 - icc)) if icc > 0 else 0.0
    rng = np.random.default_rng(seed)
    fam = cf.EnvelopeFamily(DELTA, "hc")
    L1 = np.zeros(4); L2 = np.zeros(4); abstain = 0
    for _ in range(WORLDS):
        pool = np.concatenate([rng.normal(rng.normal(0, tau), 1, 10) for _ in range(cfg["pool_scans"])])
        # K labelled scans AND the test scan drawn from the SAME law (scan sizes vary as in
        # reality) — Layer 2's guarantee needs the K+1 scans to be exchangeable.
        draws = [_scan(rng, tau, max(1, int(rng.poisson(cfg["m0"]))), int(rng.poisson(cfg["m1"])), cfg["mu"])
                 for _ in range(K + 1)]
        scans, test = draws[:K], draws[K]
        kt, n = cf.conformal_ranks(test[0], pool)
        L1 += _eval(kt, n, test[1], fam, 0)
        safe = []
        for s, isf in scans:
            if s.size == 0:
                safe.append(0)
                continue
            k, _ = cf.conformal_ranks(s, pool)
            safe.append(cf.scan_safe_inflation_simultaneous(k, n, isf, fam))
        theta = cf.scan_level_theta(safe, DELTA)
        if theta is None:
            abstain += 1
            L2 += (False, False, 0, int((~test[1]).sum()))
        else:
            L2 += _eval(kt, n, test[1], fam, theta)
    se = lambda p: round(math.sqrt(max(p * (1 - p), 1e-12) / WORLDS), 4)   # noqa: E731
    res = {"regime": regime, "icc": icc, "worlds": WORLDS, "n": int(10 * cfg["pool_scans"])}
    for name, A in (("layer1", L1), ("layer2", L2)):
        cfail, fdx = A[0] / WORLDS, A[1] / WORLDS
        res[name] = {"curve_fail": round(cfail, 4), "curve_fail_se": se(cfail),
                     "fdx": round(fdx, 4), "fdx_se": se(fdx),
                     "power": round(A[2] / max(A[3], 1), 4)}
    res["layer2"]["abstain"] = round(abstain / WORLDS, 4)
    return res


def main():
    jobs = [(r, icc, 1000 * i + j) for i, r in enumerate(REGIMES) for j, icc in enumerate(ICCS)]
    with Pool(max(1, (os.cpu_count() or 2) - 2)) as p:
        results = p.map(run_config, jobs)
    for r in results:
        a, b = r["layer1"], r["layer2"]
        flag = lambda x: "  <-- exceeds delta" if x["curve_fail"] - 2 * x["curve_fail_se"] > DELTA else ""  # noqa: E731
        print(f"{r['regime']:14s} ICC={r['icc']:.2f} n={r['n']:5d} | L1 curve-fail {a['curve_fail']:.3f}"
              f"+-{a['curve_fail_se']:.3f} FDX {a['fdx']:.3f} pow {a['power']:.3f}{flag(a)}"
              f" | L2 curve-fail {b['curve_fail']:.3f}+-{b['curve_fail_se']:.3f} FDX {b['fdx']:.3f}"
              f" pow {b['power']:.3f} abst {b['abstain']:.3f}{flag(b)}")
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"gamma": GAMMA, "delta": DELTA, "K": K, "results": results}, fh, indent=2)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
