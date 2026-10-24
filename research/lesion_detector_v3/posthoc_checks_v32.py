#!/usr/bin/env python3
"""Lesion-detector v3.2 — POST-HOC checks (NOT pre-registered; written after the v3.2 pre-registered
evaluation was seen, to understand it and to try to break its one positive secondary).

Q1  Fold disagreement (ens_std) separates real lesions from healthy-control candidates (DIS-RAW,
    H1 AUROC 0.852) and the K2 probe identifies control candidates among false ones mostly through F8.
    Is that just because control candidates have a lower mean probability or a smaller volume?
    -> ens_std of MS TRUE / MS FALSE / control candidates within bins of the ensemble mean
       probability and within volume bins (medians), and the H1 AUROC of DIS-RAW within each
       probability bin.
Q2  Healthy false candidates per control scan at other sensitivity levels (0.80 / 0.95 / 1.00) for
    ENS-RAW, DIS-RAW, GR-LR, GR+C-LR (out-of-fold scores of the evaluation), to show the trade-off.

    python research/lesion_detector_v3/posthoc_checks_v32.py
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evaluate_v3 as ev                                                  # noqa: E402
import evaluate_v32 as e32                                                # noqa: E402

OUT = os.path.join(ev.RECORDS, "2026-10-24_lesion_detector_v32_posthoc_checks.json")


def main():
    D = e32.Data32(os.path.join(HERE, ".cache", "features_v32.npz"))
    y = D.labels["lenient"]
    z = np.load(e32.OOF_OUT, allow_pickle=False)
    names = [str(n) for n in z["names"]]
    S = {n: z[f"s{i}"] for i, n in enumerate(names)}
    assert (z["y"] == y).all() and (z["fold"] == D.fold).all()
    import hashlib
    rec = {"status": "POST-HOC (not pre-registered); descriptive",
           "oof_scores_sha256": hashlib.sha256(open(e32.OOF_OUT, "rb").read()).hexdigest()}
    log = []

    def say(m):
        print(m, flush=True)
        log.append(m)

    groups = {"MS_true": D.sets["MS1"] & y, "MS_false": D.sets["MS1"] & ~y, "controls": D.sets["C"]}
    pm = D.X[:, D.col["prob_mean"]]
    sd = D.X[:, D.col["ens_std"]]
    vol = D.X[:, D.col["log_volume_mm3"]]
    q1 = {"by_mean_probability": {}, "by_volume_mm3": {}}
    for lo, hi in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)):
        b = (pm >= lo) & (pm < hi)
        row = {g: {"n": int((m & b).sum()), "median_ens_std": ev._r(float(np.median(sd[m & b]))) if (m & b).any() else None}
               for g, m in groups.items()}
        ii = np.nonzero(b & (groups["MS_true"] | groups["controls"]))[0]
        row["DIS_RAW_auroc_true_vs_controls"] = ev._r(ev.auroc(-sd[ii], y[ii])) if ii.size else None
        row["ENS_RAW_auroc_true_vs_controls"] = ev._r(ev.auroc(pm[ii], y[ii])) if ii.size else None
        q1["by_mean_probability"][f"{lo:.1f}-{min(hi, 1.0):.1f}"] = row
        say(f"Q1 prob {lo:.1f}-{min(hi, 1):.1f}: " + ", ".join(f"{g} n={row[g]['n']} sd~{row[g]['median_ens_std']}" for g in groups)
            + f" | DIS-RAW AUROC {row['DIS_RAW_auroc_true_vs_controls']}")
    for lo, hi in ((3, 10), (10, 30), (30, 100), (100, 1e9)):
        b = (np.exp(vol) >= lo) & (np.exp(vol) < hi)
        row = {g: {"n": int((m & b).sum()), "median_ens_std": ev._r(float(np.median(sd[m & b]))) if (m & b).any() else None}
               for g, m in groups.items()}
        q1["by_volume_mm3"][f"{lo}-{hi:g}"] = row
        say(f"Q1 vol {lo}-{hi:g} mm3: " + ", ".join(f"{g} n={row[g]['n']} sd~{row[g]['median_ens_std']}" for g in groups))
    rec["Q1_disagreement_vs_probability_and_size"] = q1

    q2 = {}
    pos = D.sets["MS1"] & y
    ctl = [D.scan_cands(s) for s in D.ctl_scans]
    for sens in (0.80, 0.90, 0.95, 1.00):
        row = {}
        for n in ("ENS-RAW", "DIS-RAW", "GR-LR", "GR+C-LR"):
            tau = np.quantile(S[n][pos], 1 - sens, method="lower") if sens < 1 else -np.inf
            c = np.array([int((S[n][ii] >= tau).sum()) for ii in ctl])
            row[n] = {"false_per_control_scan": ev._r(c.mean()), "share_controls_with_any": ev._r((c > 0).mean())}
        q2[f"sensitivity_{sens:.2f}"] = row
        say(f"Q2 sens {sens:.2f}: " + ", ".join(f"{n} {v['false_per_control_scan']}/{v['share_controls_with_any']}" for n, v in row.items()))
    rec["Q2_healthy_false_per_scan_vs_sensitivity"] = q2
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    with open(OUT.replace(".json", "_output.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(log) + "\n")
    say(f"wrote {OUT}")


if __name__ == "__main__":
    main()
