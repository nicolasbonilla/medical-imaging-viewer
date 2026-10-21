#!/usr/bin/env python3
"""Paper C — independent re-computation of the 4 primary cells (different code path).

Reads the per-unit cache directly (not run_pilot.units_for), recomputes leave-one-patient-out
conformal thresholds with an explicit rank rule (p-value form: a held-out patient makes a false
call iff its largest false score is strictly above the k-th smallest calibration value), and
compares the false-call counts and true-detection counts with the pilot record.

    python research/paper_c/verify_primary.py
"""
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C  # noqa: E402

REC = os.path.join(C.RECORDS, "2026-10-21_paper_c_pilot.json")


def load(kind):
    out = []
    for f in sorted(glob.glob(os.path.join(HERE, ".cache", "units", f"{kind}_*.json"))):
        out.append(json.load(open(f)))
    return out


def cell(units, get_cands, key, alpha):
    fc = tf = 0
    for u in units:
        cal = []
        for v in units:
            if v["patient"] == u["patient"]:
                continue
            fs = [c[key] for c in get_cands(v) if not c["true"] and c[key] not in (None,) and math.isfinite(c[key])]
            cal.append(max(fs) if fs else -math.inf)
        n = len(cal)
        k = math.ceil((n + 1) * (1 - alpha) - 1e-12)
        lam = sorted(cal)[k - 1] if k <= n else math.inf
        mine = [c for c in get_cands(u) if math.isfinite(c[key]) and c[key] > lam]
        fc += any(not c["true"] for c in mine)
        tf += any(c["true"] for c in mine) and u["active"]
    return fc, tf


def main():
    rec = json.load(open(REC))
    oms = load("oms")
    msl = [u for u in load("msl") if u["first_pair"]]
    ok = True
    for arm, units, get, key in (("A1", oms, lambda u: u["dsub"]["1.5"], "score"),
                                 ("A2", msl, lambda u: u["dseg"], "score_sub")):
        for alpha in (0.1, 0.2):
            fc, tf = cell(units, get, key, alpha)
            r = rec["arms"][arm]["loo"][f"marginal_a{alpha}"]
            same = (fc == r["fwer_x"] and tf == r["true_flag_x"])
            ok &= same
            print(f"{arm} a={alpha}: independent false-call {fc}/{len(units)}, true-flag {tf} | "
                  f"record {r['fwer_x']}/{r['units']}, {r['true_flag_x']} -> {'MATCH' if same else 'MISMATCH'}")
    print("ALL PRIMARY CELLS REPRODUCED" if ok else "MISMATCH FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
