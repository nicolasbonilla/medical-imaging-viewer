#!/usr/bin/env python3
"""Paper A v0.2 — scan-clustered permutation test of false-candidate score laws (one-to-one
labels), re-run with the FLAMeS-training-aware openms subsets.

Statistic: two-sample KS distance D between the pooled false-candidate scores of two scan sets;
null distribution: permute WHOLE SCANS between the two sets (sizes fixed), so within-scan
clustering is respected (same test as scripts/calm-ms/multisite_conformal_advanced.py §1.5).

Pairs: openms_all vs MSLesSeg (reproduces v0.1: D = 0.048, p = 0.71), heldout10 vs MSLesSeg
(the clean comparison), trained20 vs MSLesSeg, and trained20 vs heldout10 (same site, same
annotation protocol, differing only in FLAMeS training membership -> a direct probe of the
in-sample effect on the false-candidate law).

    python research/paper_a/exchangeability_v02.py
"""
import json
import os
import sys

import numpy as np
from scipy.stats import ks_2samp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RECORDS, flames_split, load_cache, openms_patient  # noqa: E402

N_PERM, SEED = 2000, 20261017
OUT = os.path.join(RECORDS, "2026-10-17_paper_a_v02_exchangeability.json")


def main():
    cases, meta = load_cache(".multisite_adv_cache.npz")
    sp = flames_split()
    fp = lambda c: np.asarray(c["scores"])[np.asarray(c["mg0"]) == 0]    # noqa: E731
    sets = {"mslesseg": [c for c in cases if c["site"] == "mslesseg"],
            "openms_all": [c for c in cases if c["site"] == "openms"]}
    for k in ("heldout10", "trained20"):
        sets[k] = [c for c in cases if c["site"] == "openms" and openms_patient(c["case"]) in set(sp[k])]
    rng = np.random.RandomState(SEED)
    rec = {"inputs": [meta], "n_perm": N_PERM, "pairs": {}}
    for a, b in [("openms_all", "mslesseg"), ("heldout10", "mslesseg"), ("trained20", "mslesseg"),
                 ("trained20", "heldout10")]:
        A, B = sets[a], sets[b]
        obs = ks_2samp(np.concatenate([fp(c) for c in A]), np.concatenate([fp(c) for c in B])).statistic
        pooled = [fp(c) for c in A + B]
        perm = []
        for _ in range(N_PERM):
            idx = rng.permutation(len(pooled))
            ga = np.concatenate([pooled[i] for i in idx[:len(A)]])
            gb = np.concatenate([pooled[i] for i in idx[len(A):]])
            if ga.size >= 3 and gb.size >= 3:
                perm.append(ks_2samp(ga, gb).statistic)
        p = (np.sum(np.array(perm) >= obs) + 1) / (len(perm) + 1)
        rec["pairs"][f"{a}|{b}"] = {"scans": [len(A), len(B)],
                                    "false_candidates": [int(sum(fp(c).size for c in A)), int(sum(fp(c).size for c in B))],
                                    "ks_D": round(float(obs), 4), "perm_p": round(float(p), 4)}
        print(f"{a:11s} vs {b:9s}: D={obs:.3f}  scan-permutation p={p:.3f}  scans {len(A)}/{len(B)}")
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
