#!/usr/bin/env python3
"""Paper A revision — PROTOCOL-v0.3 §13 entry 11 (i), post hoc: share of first scans (per site, ensemble
arm) whose safe threshold lies above the scan's top false candidate, at gamma 0.1 and 0.2. Full precision.

    python research/paper_a/v03r_revision_extra.py
"""
import json
import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v03_analysis as A                                   # noqa: E402
from v03_candidates import CACHE, sha256                   # noqa: E402
from v03_data import RECORDS, SITES                        # noqa: E402

OUT = os.path.join(RECORDS, "2026-10-31_paper_a_revision_extra.json")


def main():
    cache = pickle.load(open(CACHE, "rb"))
    ens = A.build(cache, "ens")
    rec = {"status": "POST HOC (revision, PROTOCOL-v0.3 §13 entry 11 (i))", "cache_sha256": sha256(CACHE), "sites": {}}
    for site in SITES:
        fs = A.first_scans([s for s in ens if s["site"] == site])
        row = {"first_scans": len(fs)}
        for g in (0.1, 0.2):
            above = 0
            for s in fs:
                f = s["scores"][s["isf"]]
                top = f.max() if f.size else -np.inf
                above += A.safe(s, g) > top
            row[f"safe_above_top_false_gamma_{g}"] = above / len(fs)
        rec["sites"][site] = row
        print(site, row)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, indent=1)


if __name__ == "__main__":
    main()
