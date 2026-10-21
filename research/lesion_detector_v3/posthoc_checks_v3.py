#!/usr/bin/env python3
"""Lesion-detector v3 — POST-HOC adversarial checks (NOT pre-registered; written after the
pre-registered evaluation was seen, to try to break its favourable secondary findings).

Every check here can only weaken a claim; none is used to pick features, models or endpoints.
  P1  What do the NEW families add over v2's features with the SAME model? Paired bootstrap of
      V3-LR - V2-LR (pooled LOCO, each direction, within-MSLesSeg CV). The pre-registered H2 compared
      against "V2 as shipped" (degree-2 polynomial LR + MNI location), which mixes a model effect
      with a feature effect.
  P2  Model-refit variance of direction A (train MSLesSeg -> test Ljubljana-10), mirroring A5b.
  P3  Why the pooled LOCO AUROC is below both per-direction AUROCs: mean score each direction's
      model assigns to its test cohort (base-rate calibration mismatch between the two models).
  P4  Seed stability of the primary paired bootstrap (3 other seeds).
  P5  Descriptive: univariate AUROC per feature and cohort; control vs Ljubljana candidate medians.

    python research/lesion_detector_v3/posthoc_checks_v3.py
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evaluate_v3 as ev                                                  # noqa: E402

OUT = os.path.join(ev.RECORDS, "2026-10-17_lesion_detector_v3_posthoc_checks.json")


def main():
    t0 = time.time()
    D = ev.Data(os.path.join(HERE, ".cache", "features_v3.npz"))
    y = D.labels["lenient"]
    rec = {"status": "POST-HOC (not pre-registered); can only weaken claims", "seed": ev.SEED}
    log = []

    def say(m):
        print(m, flush=True)
        log.append(m)

    # P1 ------------------------------------------------------------------
    sc, idx = ev.loco(D, ("V3-LR", "V2-LR"), y)
    nA = int(D.sets["L10"].sum())
    p1 = {"pooled": ev.auc_table(D, sc, idx, y, [D.sets["M"], D.sets["L10"]], ref="V2-LR", seed=ev.SEED + 21)}
    for nm, sl, mk in (("A_M_to_L10", slice(0, nA), D.sets["L10"]), ("B_L10_to_M", slice(nA, None), D.sets["M"])):
        p1[nm] = ev.auc_table(D, {k: v[sl] for k, v in sc.items()}, idx[sl], y, [mk], ref="V2-LR", seed=ev.SEED + 22)
    scw, idw = ev.within_cohort(D, ("V3-LR", "V2-LR"), y, "M", 5)
    p1["within_M_cv"] = ev.auc_table(D, scw, idw, y, [D.sets["M"]], ref="V2-LR", seed=ev.SEED + 23)
    rec["P1_v3_minus_v2_same_model"] = {k: {"V3-LR": v["V3-LR"]["auroc"], "V2-LR": v["V2-LR"]["auroc"],
                                            "delta": v["V3-LR"]["delta_vs_V2-LR"],
                                            "delta_ci95": v["V3-LR"]["delta_vs_V2-LR_ci95"]} for k, v in p1.items()}
    say(f"P1 V3-LR minus V2-LR (same LR spec): {json.dumps(rec['P1_v3_minus_v2_same_model'])}")

    # P2 ------------------------------------------------------------------
    Mp = np.array(sorted(set(D.patient[D.sets["M"]])))
    te = D.sets["L10"]
    fset, fitter = ev.MODELS["V3-LR"]
    cols = [D.col[c] for c in ev.FEATURE_SETS[fset]]
    refit = []
    for r in range(50):
        rng = np.random.RandomState(ev.SEED + 900 + r)
        pick = rng.choice(Mp, len(Mp), replace=True)
        rows = np.concatenate([np.nonzero(D.sets["M"] & (D.patient == p))[0] for p in pick])
        f = fitter(D.X[rows][:, cols], y[rows].astype(int))
        refit.append(ev.auroc(f(D.F(fset, te)), y[te]))
    raw = ev.auroc(D.raw[te], y[te])
    rec["P2_direction_A_refit_variance"] = {"n_refits": 50, "auroc_mean": ev._r(np.mean(refit)),
                                            "auroc_p2.5_p97.5": ev.ci(refit), "raw_auroc_on_L10": ev._r(raw),
                                            "frac_refits_below_raw": ev._r(np.mean(np.array(refit) < raw))}
    say(f"P2 {rec['P2_direction_A_refit_variance']}")

    # P3 ------------------------------------------------------------------
    sc3, idx3 = ev.loco(D, ("V3-LR",), y)
    p3 = {}
    for nm, sl in (("A_scores_on_L10", slice(0, nA)), ("B_scores_on_M", slice(nA, None))):
        ii = idx3[sl]
        p3[nm] = {"mean_score_V3-LR": ev._r(float(np.mean(sc3["V3-LR"][sl]))),
                  "mean_score_RAW": ev._r(float(np.mean(sc3["RAW"][sl]))),
                  "false_rate": ev._r(float((~y[ii]).mean()))}
    p3["note"] = ("pooled AUROC also ranks candidates ACROSS the two directions; if the model used on the "
                  "cohort with MORE false candidates outputs HIGHER scores on average, the pooled AUROC falls "
                  "below both per-direction AUROCs. RAW has no training and is not affected this way.")
    rec["P3_pooled_calibration_mismatch"] = p3
    say(f"P3 {json.dumps(p3)}")

    # P4 ------------------------------------------------------------------
    sc4, idx4 = ev.loco(D, ("V3-LR",), y)
    p4 = {}
    for s in (1, 2, 3):
        t = ev.auc_table(D, sc4, idx4, y, [D.sets["M"], D.sets["L10"]], seed=ev.SEED + 1000 * s)
        p4[f"seed+{1000 * s}"] = {"delta": t["V3-LR"]["delta_vs_RAW"], "ci95": t["V3-LR"]["delta_vs_RAW_ci95"]}
    rec["P4_bootstrap_seed_stability"] = p4
    say(f"P4 {json.dumps(p4)}")

    # P5 descriptive: univariate AUROC of every V3 feature per cohort (NaN rows dropped), and
    # medians of control candidates vs L10 true / false candidates for prob-map features
    p5 = {"univariate_auroc": {}, "medians": {}}
    for c in ev.FEATURE_SETS["V3"]:
        j = D.col[c]
        row = {}
        for nm in ("M", "L10"):
            m = D.sets[nm] & np.isfinite(D.X[:, j])
            row[nm] = ev._r(ev.auroc(D.X[m, j], y[m]), 3)
        p5["univariate_auroc"][c] = row
    for c in ("prob_mean", "log_volume", "sphericity", "pm_grad_boundary", "pm_ring1_mean", "ps_surv_090",
              "ps_log_merge_010"):
        j = D.col[c]
        p5["medians"][c] = {k: ev._r(float(np.nanmedian(D.X[m, j])), 3) for k, m in
                            (("controls", D.sets["C"]), ("L10_true", D.sets["L10"] & y),
                             ("L10_false", D.sets["L10"] & ~y), ("M_false", D.sets["M"] & ~y))}
    rec["P5_descriptive"] = p5
    say(f"P5 {json.dumps(p5)}")

    rec["runtime_s"] = round(time.time() - t0, 1)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    with open(OUT.replace(".json", "_output.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(log) + "\n")
    say(f"wrote {OUT}")


if __name__ == "__main__":
    main()
