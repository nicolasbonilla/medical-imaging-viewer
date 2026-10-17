#!/usr/bin/env python3
"""Paper A v0.2 — the pre-registered PAC (training-conditional, device) Layer-2 quantile on
MSLesSeg, re-aggregated on DISTINCT scans (complements fdx_distinct_scans_v02.py, which re-ran the
marginal quantile; same pre-registered splits and seeds).

    python research/paper_a/pac_distinct_v02.py
"""
import json
import os
import sys
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fdx_distinct_scans_v02 as fx                                       # noqa: E402
from common import RECORDS, load_cache                                    # noqa: E402

OUT = os.path.join(RECORDS, "2026-10-17_paper_a_v02_pac_distinct_scans.json")


def main():
    cases, meta = load_cache(".region_cache.npz")
    rng = np.random.RandomState(fx.SEED + 7)
    with Pool(max(1, (os.cpu_count() or 2) - 2)) as pool:
        rows, splits, pacrows = fx.rd.layer2(cases, "mslesseg", "hc", pool, n_pool_subj=35, K=29, T=11)
    d = fx.distinct(pacrows, rng)
    d["v01_style_counts"] = {"curve_violated": sum(r["curve_fail"] for r in pacrows),
                             "fdp_gt_gamma": sum(r["sel"] > 0 and r["fdp"] > fx.GAMMA for r in pacrows),
                             "false_certified_dis": sum(r["dis_cert_false"] for r in pacrows),
                             "draws": len(pacrows)}
    d["theta_pac_per_split"] = [s["theta_pac"] for s in splits]
    print(f"PAC mslesseg: draws {d['draws']} distinct {d['distinct_scans']} | v0.1-style {d['v01_style_counts']}"
          f" | curve-violated distinct {d['curve_violated']['distinct_scans_ever']}"
          f" | certified on GT-DIS {d['certified_on_gt_dis']} | power {d['power_per_draw']} abstain {d['abstain_draw_rate']}")
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"inputs": [meta], "pac_mslesseg": d}, fh, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
