#!/usr/bin/env python3
"""Paper A v0.3 — POST-HOC explanatory checks (NOT pre-registered; written after the
pre-registered results were seen, to explain them). Nothing here changes a primary or secondary
result of PROTOCOL-v0.3.

  1. Why the FDX threshold P2 is identical at gamma = 0.1 and 0.2: share of calibration scans
     whose safe threshold sits above their highest-scoring false candidate (P2 then reduces to
     "no false candidate above the threshold in 90 % of patients").
  2. Upper tail of false-candidate scores per site (ensemble vs fold 0): share of scans with a
     false candidate above the 1-mm-calibrated P2 threshold; share of false candidates >= 0.95.
  3. Expert-lesion counts and sizes per site (context for power).
  4. Within-site slice-thickness gradient (MS3SEG, Muslim): per-scan FDP of P1 (alpha = 0.2,
     leave-one-site-out calibration) vs slice spacing, Spearman rho and a patient-permutation p.
  5. (added after an independent review) P1 realised FDR on thick-slice scans with many false
     candidates (share false >= 0.4 / 0.5), 1-mm vs within-site calibration, and alpha * pi0.

    python research/paper_a/v03_posthoc.py
"""
import json
import os
import pickle
import sys

import numpy as np
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v03_analysis as A                                   # noqa: E402
import v03_metrics as M                                    # noqa: E402
from v03_candidates import CACHE, sha256                   # noqa: E402
from v03_data import ONE_MM_SITES, RECORDS, SITES          # noqa: E402

OUT = os.path.join(RECORDS, "2026-10-21_paper_a_v03_posthoc.json")


def main():
    cache = pickle.load(open(CACHE, "rb"))
    rec = {"status": "POST-HOC, not pre-registered", "cache_sha256": sha256(CACHE)}
    arms = {"ens": A.build(cache, "ens"), "f0": A.build(cache, "f0")}
    # 1 + 2
    for arm, scans in arms.items():
        one = [s for s in scans if s["site"] in ONE_MM_SITES]
        lam = M.fdx_threshold([A.safe(s, 0.1) for s in A.first_scans(one)], A.DELTA)
        rec[f"{arm}|P2_threshold_1mm_calibrated"] = lam
        for site in SITES:
            ss = [s for s in scans if s["site"] == site]
            fs = A.first_scans(ss)
            same = above = 0
            for s in fs:
                t1, t2 = A.safe(s, 0.1), A.safe(s, 0.2)
                same += t1 == t2
                mf = s["scores"][s["isf"]].max() if s["isf"].any() else -1
                above += t2 > mf
            f = np.concatenate([s["scores"][s["isf"]] for s in ss])
            maxf = np.array([s["scores"][s["isf"]].max() if s["isf"].any() else 0.0 for s in ss])
            rec[f"{arm}|{site}"] = {
                "first_scans": len(fs), "safe_threshold_equal_at_gamma_0.1_and_0.2": round(same / len(fs), 3),
                "safe_threshold_above_top_false_candidate_gamma_0.2": round(above / len(fs), 3),
                "scans_with_false_candidate_above_1mm_P2_threshold": round(float((maxf >= lam).mean()), 3),
                "patient_q90_of_max_false_score": round(float(np.quantile([maxf[i] for i in range(len(ss))], 0.9)), 4),
                "false_candidates_score_ge_0.95": round(float((f >= 0.95).mean()), 4),
                "false_candidates": int(f.size)}
    # 3
    for site in SITES:
        ss = [s for s in arms["ens"] if s["site"] == site]
        vols = np.concatenate([s["gt_vol"] for s in ss])
        rec[f"lesions|{site}"] = {"per_scan_median": float(np.median([s["gt_ids"].size for s in ss])),
                                  "volume_mm3_median": round(float(np.median(vols)), 1),
                                  "volume_mm3_q25_q75": [round(float(x), 1) for x in np.quantile(vols, [0.25, 0.75])]}
    # 4
    sels, _ = A.run_design(arms["ens"], "D2", [("P1", 0.2)])
    sel = sels[("P1", 0.2)]
    rng = np.random.RandomState(A.SEED + 99)
    for site in ("ms3seg", "muslim"):
        ss = [s for s in arms["ens"] if s["site"] == site]
        z = np.array([s["slice_mm"] for s in ss])
        fdp = np.array([M.scan_row(sel[s["case"]], s["isf"], s["mg"], s["gt_ids"], s["gt_vol"])["fdp"] for s in ss])
        rho = spearmanr(z, fdp).correlation
        perm = [spearmanr(rng.permutation(z), fdp).correlation for _ in range(5000)]
        p = (np.sum(np.abs(perm) >= abs(rho)) + 1) / 5001
        rec[f"thickness_gradient|{site}|D2|P1|0.2"] = {
            "spearman_rho_slice_vs_scan_fdp": round(float(rho), 3), "perm_p_two_sided": round(float(p), 4),
            "mean_fdp_slice_le_6.5": round(float(fdp[z <= 6.5].mean()), 4) if (z <= 6.5).any() else None,
            "mean_fdp_slice_gt_6.5": round(float(fdp[z > 6.5].mean()), 4) if (z > 6.5).any() else None,
            "scans_le_6.5": int((z <= 6.5).sum()), "scans_gt_6.5": int((z > 6.5).sum())}
    # 5 (added 2026-10-21 after the independent review): realised FDR of P1 on thick-slice scans
    #   with a high share of false candidates (pi0 = false / candidates), 1-mm calibration (D3) vs
    #   within-site calibration (D1); alpha * pi0 is the value conformal BH attains under
    #   exchangeability (Benjamini-Hochberg: FDR = alpha * m0 / m).
    sel_d3, _ = A.run_design(arms["ens"], "D3", [("P1", 0.1), ("P1", 0.2)])
    sel_d1, _ = A.run_design(arms["ens"], "D1", [("P1", 0.1), ("P1", 0.2)])
    thick = [s for s in arms["ens"] if s["site"] in ("ms3seg", "muslim")]
    pi0 = {s["case"]: (s["isf"].mean() if s["isf"].size else 0.0) for s in thick}
    for site in ("ms3seg", "muslim", "pedims"):
        ss = [s for s in arms["ens"] if s["site"] == site]
        rec[f"alpha_pi0|{site}"] = {"mean_pi0": round(float(np.mean([s["isf"].mean() for s in ss if s["isf"].size])), 4)}
    for a in (0.1, 0.2):
        for lo in (0.0, 0.4, 0.5):
            sub = [s for s in thick if s["isf"].size and pi0[s["case"]] >= lo]
            cell = {"scans": len(sub), "mean_pi0": round(float(np.mean([pi0[s["case"]] for s in sub])), 3),
                    "alpha_times_mean_pi0": round(a * float(np.mean([pi0[s["case"]] for s in sub])), 4)}
            for dname, sels in (("D3_1mm_calibrated", sel_d3), ("D1_within_site", sel_d1)):
                sm = A.summarize(sub, sels[("P1", a)])
                cell[dname] = {"realised_fdr": sm["mean_fdp"], "ci95": sm["mean_fdp_ci"], "sens_e2e": sm["sens_e2e"]}
            rec[f"pi0_subset|ms3seg+muslim|P1|{a}|pi0>={lo}"] = cell
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1, default=float)
    print(json.dumps(rec, indent=1, default=float))


if __name__ == "__main__":
    main()
