#!/usr/bin/env python3
"""Paper A v0.2 — small numbers quoted in the draft that had no committed script, recomputed.

  * fraction of scans whose TOP-scored candidate is false (one-to-one labels), per cohort
    (v0.1 quoted 16.5 % for MSLesSeg without a script);
  * exact binomial bounds quoted in the text (0/30, 0/10, 0/5, ...), so every interval in the
    draft is reproducible; and the v0.1 "0/200 -> <= 1.8 %" bound, to show where it came from.

    python research/paper_a/misc_checks_v02.py
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (RECORDS, clopper_pearson, cp_upper_one_sided, flames_split,  # noqa: E402
                    load_cache, openms_patient)

OUT = os.path.join(RECORDS, "2026-10-17_paper_a_v02_misc_checks.json")


def main():
    cases, meta = load_cache(".multisite_adv_cache.npz")
    sp = flames_split()
    groups = {"mslesseg": [c for c in cases if c["site"] == "mslesseg"],
              "openms_all": [c for c in cases if c["site"] == "openms"]}
    for k in ("heldout10", "trained20"):
        groups[k] = [c for c in cases if c["site"] == "openms" and openms_patient(c["case"]) in set(sp[k])]
    rec = {"inputs": [meta], "top_candidate_false": {}, "binomial_bounds": {}}
    for k, cs in groups.items():
        x = sum(int(np.asarray(c["mg0"])[int(np.argmax(c["scores"]))] == 0) for c in cs if len(c["scores"]))
        n = sum(1 for c in cs if len(c["scores"]))
        rec["top_candidate_false"][k] = {"scans": n, "top_false": x, "rate": round(x / n, 4),
                                         "ci95_exact": clopper_pearson(x, n)}
        print(f"top-scored candidate is false: {k:10s} {x}/{n} = {x / n:.3f}")
    for x, n in [(0, 200), (0, 30), (0, 27), (0, 10), (0, 5), (5, 30), (2, 30), (40, 200), (17, 200)]:
        rec["binomial_bounds"][f"{x}/{n}"] = {"two_sided_95": clopper_pearson(x, n),
                                              "one_sided_95_upper": cp_upper_one_sided(x, n)}
        print(f"{x}/{n}: two-sided 95% {clopper_pearson(x, n)}  one-sided 95% upper {cp_upper_one_sided(x, n)}")
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
