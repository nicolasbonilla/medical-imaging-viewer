#!/usr/bin/env python3
"""Lesion-detector v3.1 — POST-HOC adversarial checks (NOT pre-registered; written after the v3.1
pre-registered evaluation was seen, to try to break its positive primary result).

P1  "Is it just the ensemble?"  The pre-registered candidates come from the FLAMeS fold-0 map, so the
    fold-disagreement family may mostly clean up fold-0-specific false positives that the deployed
    5-fold ensemble would never produce. Here candidates are re-defined on the 5-fold MEAN map (how
    FLAMeS is actually used); the raw score becomes the ensemble mean probability. Does GR-LR still
    beat it? (cache: build_features.py --candidate-map mean5 --no-images)
P2  Candidate counts / false rates with fold-0 vs 5-fold-mean candidates (how many false candidates
    the ensemble itself removes).
P3  External conformal selection with 5-fold-mean candidates (RAW = ensemble mean vs GR-LR).

    python research/lesion_detector_v3/posthoc_checks_v31.py
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evaluate_v3 as ev                                                  # noqa: E402
import evaluate_v31 as e31                                                # noqa: E402

OUT = os.path.join(ev.RECORDS, "2026-10-21_lesion_detector_v31_posthoc_checks.json")


def main():
    t0 = time.time()
    D0 = e31.Data31(os.path.join(HERE, ".cache", "features_v31.npz"))
    D = e31.Data31(os.path.join(HERE, ".cache", "features_v31_mean5.npz"))
    y0, y = D0.labels["lenient"], D.labels["lenient"]
    rec = {"status": "POST-HOC (not pre-registered); can only weaken claims", "seed": ev.SEED}
    log = []

    def say(m):
        print(m, flush=True)
        log.append(m)

    # P2 descriptives
    p2 = {}
    for nm in ("M", "L10") + e31.SITES:
        p2[nm] = {"fold0": {"candidates": int(D0.sets[nm].sum()), "false": int((D0.sets[nm] & ~y0).sum()),
                            "true": int((D0.sets[nm] & y0).sum())},
                  "mean5": {"candidates": int(D.sets[nm].sum()), "false": int((D.sets[nm] & ~y).sum()),
                            "true": int((D.sets[nm] & y).sum())}}
    rec["P2_candidates_fold0_vs_mean5"] = p2
    say(f"P2 {json.dumps(p2)}")

    # P1 pooled external + per site, candidates from the 5-fold mean map
    assert np.allclose(D.raw, D.X[:, D.col["prob_mean"]])
    sc, idx = e31.ext_scores(D, y, ("GR-LR", "GR-noENS-LR", "ENS-only-LR"), D.sets["TRAIN"], D.sets["EXT"])
    sc.pop("ENS-RAW")          # identical to RAW up to uint8 rounding when candidates come from the mean map
    p1 = {"pooled_external": ev.auc_table(D, sc, idx, y, e31.site_strata(D), ref="RAW", ref2="GR-noENS-LR",
                                          seed=ev.SEED + 131)}
    for s in e31.SITES:
        keep = D.sets[s][idx]
        p1[s] = ev.auc_table(D, {k: v[keep] for k, v in sc.items()}, idx[keep], y, [D.sets[s]], ref="RAW",
                             seed=ev.SEED + 132)
    s_, i_ = e31.ext_scores(D, y, ("GR-LR",), D.sets["M"], D.sets["L10"])
    s_.pop("ENS-RAW")
    p1["M_to_L10"] = ev.auc_table(D, s_, i_, y, [D.sets["L10"]], ref="RAW", seed=ev.SEED + 133)
    rec["P1_mean5_candidates"] = p1
    for k, t in p1.items():
        say(f"P1 {k}: " + ", ".join(f"{m} {t[m]['auroc']} dRAW {t[m].get('delta_vs_RAW')} {t[m].get('delta_vs_RAW_ci95')}"
                                   for m in t if m != "_n") + f" | {t['_n']}")

    # P3 conformal, mean5 candidates
    say("P3 conformal external with 5-fold-mean candidates ...")
    conf = e31.conformal_external(D, y, ("GR-LR",))
    rec["P3_conformal_external_mean5"] = conf
    for s in e31.SITES:
        for a in ("0.1", "0.2"):
            r_ = conf[f"{s}|bh|alpha={a}"]
            say(f"  {s} bh a={a}: " + ", ".join(f"{m} power {v['power']} FDR {v['micro_fdr']} "
                                               f"exc {v['frac_scans_fdp_gt_alpha_per_draw']}"
                                               for m, v in r_.items() if m != "ENS-RAW"))
    rec["runtime_s"] = round(time.time() - t0, 1)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    with open(OUT.replace(".json", "_output.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(log) + "\n")
    say(f"wrote {OUT}")


if __name__ == "__main__":
    main()
