#!/usr/bin/env python3
"""Paper A v0.3 controls addendum — freeze the calibrated operating points BEFORE any control
outcome is computed. Uses ONLY the v0.3 patient candidate cache (no control data is read).

For every arm (FLAMeS 5-fold ensemble = primary, fold 0, LST-AI ensemble = deferred exploratory)
and calibration pool (1-mm sites = primary, all five patient sites, MSLesSeg only, thick-slice
sites) it records:
  P1 (conformal BH)  null size, SHA-256 of the sorted null, and the single-candidate cut
                     c(q) = largest null value that a score must EXCEED to get p <= q, for
                     q = alpha / m (m = 1..10): a candidate above c(alpha / m) is selected in any
                     scan with <= m candidates (BH step 1);
  P2, B1, B2, B3     the global score threshold (inf = abstain), exactly as v03_analysis.select.

    python research/paper_a/v03c_calibration.py
"""
import hashlib
import json
import os
import pickle
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v03_analysis as A                                       # noqa: E402  (reuses v0.3 code)
from v03_candidates import CACHE, sha256                       # noqa: E402
from v03_data import ONE_MM_SITES, RECORDS, THICK_SITES        # noqa: E402

OUT = os.path.join(RECORDS, "2026-10-24_paper_a_v03c_calibration.json")
EXPECTED_CACHE_SHA = json.load(open(os.path.join(RECORDS, "2026-10-21_paper_a_v03_candidates.json"),
                                    encoding="utf-8"))["cache_sha256"]


def pools_for(cache, arm):
    if arm == "lstai":
        pat = A.build(cache, "lstai", sites=ONE_MM_SITES, flames_only=False)   # LST-AI-clean, all 30 Ljubljana
        return {"1-mm sites": pat, "MSLesSeg only": [s for s in pat if s["site"] == "mslesseg"]}
    pat = A.build(cache, arm)                                  # FLAMeS-clean scans only (protocol §2)
    return {"1-mm sites": [s for s in pat if s["site"] in ONE_MM_SITES],
            "all five patient sites": pat,
            "MSLesSeg only": [s for s in pat if s["site"] == "mslesseg"],
            "thick-slice sites": [s for s in pat if s["site"] in THICK_SITES]}


def null_sha(null):
    return hashlib.sha256(np.sort(np.asarray(null, np.float64)).tobytes()).hexdigest()


def single_cut(null, q):
    """Score must be > returned value for p = (1 + #{null >= s}) / (n + 1) <= q (None: impossible)."""
    n = null.size
    k = int(np.floor(q * (n + 1) - 1 + 1e-12))                 # max admissible #{null >= s}
    if k < 0:
        return None
    desc = np.sort(null)[::-1]
    return float(desc[k]) if k < n else float("-inf")


def main():
    t0 = time.time()
    got = sha256(CACHE)
    assert got == EXPECTED_CACHE_SHA, f"patient cache changed: {got} != {EXPECTED_CACHE_SHA}"
    cache = pickle.load(open(CACHE, "rb"))
    rec = {"created": time.strftime("%Y-%m-%d %H:%M:%S"),
           "purpose": "PROTOCOL-v0.3 controls addendum: calibrated operating points frozen before any control outcome",
           "patient_cache": {"file": "research/paper_a/.cache/v03_candidates.pkl", "sha256": got},
           "code": {"v03c_calibration.py": sha256(os.path.abspath(__file__)),
                    "v03_analysis.py": sha256(os.path.join(HERE, "v03_analysis.py")),
                    "v03_metrics.py": sha256(os.path.join(HERE, "v03_metrics.py"))},
           "procedures": [list(p) for p in A.PROCS], "delta": A.DELTA, "arms": {}}
    for arm in ("ens", "f0", "lstai"):
        rec["arms"][arm] = {}
        for pname, pool in pools_for(cache, arm).items():
            null = A.null_of(pool)
            fs = A.first_scans(pool)
            entry = {"scans": len(pool), "patients": len({s["patient"] for s in pool}),
                     "sites": sorted({s["site"] for s in pool}), "first_scans_for_P2_B2_B3": len(fs),
                     "null_size": int(null.size), "null_sha256": null_sha(null),
                     "null_quantiles_50_90_95_99": [round(float(q), 4) for q in np.quantile(null, [0.5, 0.9, 0.95, 0.99])],
                     "P1": {}, "thresholds": {}}
            for a in A.ALPHAS:
                entry["P1"][str(a)] = {f"m={m}": single_cut(null, a / m) for m in range(1, 11)}
            for p in A.PROCS:
                if p[0] == "P1":
                    continue
                _, lam = A.select(pool, [], *p)
                entry["thresholds"][f"{p[0]}|{p[1]}"] = None if not np.isfinite(lam) else round(float(lam), 4)
            rec["arms"][arm][pname] = entry
            print(arm, pname, json.dumps({k: entry[k] for k in ("scans", "null_size", "thresholds")}), flush=True)
            print("   P1 single-candidate cuts (m=1):", {a: entry["P1"][a]["m=1"] for a in entry["P1"]}, flush=True)
    rec["runtime_s"] = round(time.time() - t0, 1)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
