#!/usr/bin/env python3
"""Paper A revision (2026-10-31) — full-precision re-run of the committed analyses.

The v0.3 records store values rounded to 3–4 decimals; the manuscript then rounded them again, which
produced eight off-by-0.001 double-rounding slips (independent review, §3). This wrapper re-runs the
SAME committed scripts on the SAME frozen candidate cache with the SAME seeds, but with every rounding
helper replaced by float(), and writes the results to new *_fullprec.json records. It then checks that
each full-precision value, rounded as the original script rounded it, equals the committed record —
i.e. that nothing but the rounding changed. The manuscript renders from the full-precision records and
rounds once (round-half-up), at printing.

Nothing here is a new analysis; no pre-registered number changes. Local CPU only.

    python research/paper_a/v03r_fullprecision.py
"""
import builtins
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v03_analysis as A                                   # noqa: E402
from v03_data import RECORDS                               # noqa: E402

_round = builtins.round


def full(x, k=4):
    if x is None:
        return None
    if isinstance(x, (list, tuple)):
        return [full(v, k) for v in x]
    return float(x)


def full_round(x, k=None):
    return _round(x) if k is None else float(x)


A.rnd = full

JOBS = [  # module, output attribute, new record, committed record
    ("v03_analysis", "OUT_JSON", "2026-10-31_paper_a_v03_results_fullprec.json", "2026-10-21_paper_a_v03_results.json"),
    ("v03_posthoc", "OUT", "2026-10-31_paper_a_v03_posthoc_fullprec.json", "2026-10-21_paper_a_v03_posthoc.json"),
    ("v03_mslesseg_native", "OUT", "2026-10-31_paper_a_v03_mslesseg_native_fullprec.json", "2026-10-21_paper_a_v03_mslesseg_native.json"),
    ("v03m_manuscript_posthoc", "OUT", "2026-10-31_paper_a_manuscript_posthoc_fullprec.json", "2026-10-31_paper_a_manuscript_posthoc.json"),
]
SKIP_KEYS = {"runtime_s", "log", "created"}


def decimals(v):
    s = repr(float(v))
    if "e" in s:
        return 12
    return len(s.split(".")[1]) if "." in s else 0


def compare(new, old, path="", out=None):
    """Every committed number must equal the full-precision value at the committed precision."""
    if out is None:
        out = {"numbers": 0, "mismatches": []}
    if isinstance(old, dict) and isinstance(new, dict):
        for k in old:
            if k in SKIP_KEYS:
                continue
            if k not in new:
                out["mismatches"].append(f"{path}/{k}: missing")
                continue
            compare(new[k], old[k], f"{path}/{k}", out)
    elif isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            out["mismatches"].append(f"{path}: length {len(new)} vs {len(old)}")
        for i, (a, b) in enumerate(zip(new, old)):
            compare(a, b, f"{path}[{i}]", out)
    elif isinstance(old, bool) or isinstance(new, bool) or old is None or isinstance(old, str):
        if old != new and not (isinstance(old, str) and isinstance(new, str) and path.endswith("note")):
            out["mismatches"].append(f"{path}: {new!r} vs {old!r}")
    elif isinstance(old, (int, float)) and isinstance(new, (int, float)):
        out["numbers"] += 1
        d = decimals(old)
        if not (math.isfinite(float(new)) and abs(float(new) - float(old)) <= 0.5 * 10 ** (-d) + 1e-9):
            out["mismatches"].append(f"{path}: full {new} vs committed {old}")
    return out


def main():
    summary = {"description": "Full-precision re-run of the committed v0.3 / manuscript analyses (rounding helpers "
                              "replaced by float()); each full value rounded to the committed precision must equal "
                              "the committed record.", "jobs": {}}
    for mod_name, attr, new_name, old_name in JOBS:
        t0 = time.time()
        mod = __import__(mod_name)
        mod.round = full_round           # module-level name shadows the builtin inside that module
        setattr(mod, attr, os.path.join(RECORDS, new_name))
        mod.main()
        new = json.load(open(os.path.join(RECORDS, new_name), encoding="utf-8"))
        old = json.load(open(os.path.join(RECORDS, old_name), encoding="utf-8"))
        cmp = compare(new, old)
        summary["jobs"][mod_name] = {"record": new_name, "compared_to": old_name, "numbers_compared": cmp["numbers"],
                                     "mismatches": cmp["mismatches"][:50], "n_mismatches": len(cmp["mismatches"]),
                                     "runtime_s": _round(time.time() - t0, 1)}
        print(f"[fullprec] {mod_name}: {cmp['numbers']} numbers compared, {len(cmp['mismatches'])} mismatches", flush=True)
    with open(os.path.join(RECORDS, "2026-10-31_paper_a_fullprec_check.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, indent=1)


if __name__ == "__main__":
    main()
