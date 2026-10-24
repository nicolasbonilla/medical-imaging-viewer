"""The pre-registered FLAMeS-thick evaluation set (PROTOCOL.md §7): 211 scans, fixed before any run.

    python eval_cases.py --cases /w/cases_all.json --out /w/cases.json      # on the evaluation VM

Selects, from the case list the v2 job builds, exactly: MSLesSeg TEST (P54-P75, 22), Ljubljana clean-10
(patients 16-20, 26-30), MS3SEG (100), Muslim 2022 axial (51), PediMS (28). Refuses to run when the
count differs from the protocol (a deviation must be decided and logged first: --allow-count C).
Also exports site / band / patient helpers shared with analysis.py.
"""
import argparse
import json
import re
import sys

OPENMS_CLEAN = (16, 17, 18, 19, 20, 26, 27, 28, 29, 30)
EXPECTED = {"mslesseg": 22, "openms": 10, "ms3seg": 100, "muslim": 51, "pedims": 28}
THICK_SITES = ("ms3seg", "muslim", "pedims")
ONE_MM_SITES = ("openms", "mslesseg")


def site_of(case):
    return case.split("_", 1)[0]


def patient_of(case):
    s = site_of(case)
    if s == "mslesseg":
        return "mslesseg_" + re.match(r"mslesseg_(P\d+)", case).group(1)
    if s == "pedims":
        return "pedims_" + re.match(r"pedims_(P\d+)", case).group(1)
    return case


def in_eval_set(case):
    s = site_of(case)
    if s == "mslesseg":
        m = re.fullmatch(r"mslesseg_P(\d+)", case)              # test scans have no timepoint
        return bool(m) and 54 <= int(m.group(1)) <= 75
    if s == "openms":
        m = re.fullmatch(r"openms_patient(\d+)", case)
        return bool(m) and int(m.group(1)) in OPENMS_CLEAN
    return s in THICK_SITES


def band(slice_mm):
    """Paper A v0.3 thickness bands by slice spacing (largest voxel side, mm)."""
    if slice_mm <= 1.5:
        return "B1"
    if slice_mm <= 4.5:
        return "B2"
    if slice_mm <= 6.5:
        return "B3"
    return "B4"


def select(case_ids, allow_count=None):
    sel = sorted(c for c in case_ids if in_eval_set(c))
    counts = {s: sum(site_of(c) == s for c in sel) for s in EXPECTED}
    total = sum(counts.values())
    if counts != EXPECTED and total != allow_count:
        raise SystemExit(f"evaluation set differs from PROTOCOL §7: {counts} (expected {EXPECTED}); "
                         f"log a deviation and pass --allow-count {total} to proceed")
    return sel, counts


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True, help="cases.json of every available case")
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow-count", type=int)
    ap.add_argument("--ids", nargs="*", default=[], help="pilot: explicit subset (each must be in the set)")
    a = ap.parse_args(argv)
    cases = json.load(open(a.cases))
    if a.ids:
        bad = [c for c in a.ids if not in_eval_set(c) or c not in cases]
        if bad:
            raise SystemExit(f"not in the evaluation set or not available: {bad}")
        sel = sorted(a.ids)
        counts = {s: sum(site_of(c) == s for c in sel) for s in EXPECTED}
    else:
        sel, counts = select(cases, a.allow_count)
    json.dump({c: cases[c] for c in sel}, open(a.out, "w"), indent=1)
    print("EVAL SET", len(sel), counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
