#!/usr/bin/env python3
"""Paper A v0.2 — §5.6 real-data CALM-FDX results re-analysed on DISTINCT scans, with
contamination-clean pools and the FLAMeS-held-out openms subset.

Why: v0.1 reported "0/200 healthy scans certified as DIS (95 % CI <= 1.8 %)". The 200 are 20
repeated random splits x 10 test scans drawn from only 30 distinct healthy scans; repeated splits
re-use the same scans, so 200 is not the number of independent observations. The binomial interval
must be computed on the number of DISTINCT scans (here: ever falsely certified in any split, i.e.
the per-scan worst case), and per-draw rates need a CI that resamples scans, not draws.

Runs (template "hc" = the pre-registered primary; gamma = 0.2, delta = 0.1; seeds as pre-registered):
  A  the three pre-registered Layer-2 runs, recomputed with the committed code
     (scripts/calm-ms/calm_fdx_realdata.py: layer2/eval_scan) -> must reproduce v0.1 counts;
     then aggregated per distinct scan.
  B  healthy controls with a CLEAN pool (MSLesSeg false candidates only; v0.1 pooled openms, which
     is FLAMeS training data): Layer 1 (patient null) and Layer 2 on the SAME 20 splits.
  C  openms restricted to the 10 scans no FLAMeS fold trained on (patients 16-20, 26-30), pool =
     MSLesSeg: Layer 1, and Layer 2 by rotation (each held-out scan is the test scan once, the other
     9 are the labelled scans; ceil((9+1)(1-0.1)) = 9 <= 9 -> theta = max of the 9 safe values).
     Same rotation on clean12 (adds 04, 07; not seen by the fold-0 weights) and, as an
     in-distribution reference, on trained20.
  D  exact permutation test of candidate-level exchangeability (A1) on the clean openms subset.

    python research/paper_a/fdx_distinct_scans_v02.py
"""
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import (RECORDS, ROOT, clopper_pearson, cluster_bootstrap,   # noqa: E402
                    cp_upper_one_sided, flames_split, load_cache, openms_patient)

# the committed, pre-registered evaluation code (imported by name so worker processes can unpickle
# its functions); nothing in it is modified
sys.path.insert(0, os.path.join(ROOT, "scripts", "calm-ms"))
import calm_fdx_realdata as rd                                            # noqa: E402
cf = rd.cf

OUT_JSON = os.path.join(RECORDS, "2026-10-17_paper_a_v02_fdx_distinct_scans.json")
N_BOOT = 2000
SEED = 20261017
GAMMA, DELTA = rd.GAMMA, rd.DELTA


def distinct(rows, rng):
    """Aggregate per-draw rows (one per (split, test scan)) onto DISTINCT scans."""
    by = {}
    for r in rows:
        by.setdefault(r["case"], []).append(r)
    N = len(by)
    fdx = lambda r: r["sel"] > 0 and r["fdp"] > GAMMA                     # noqa: E731
    bhx = lambda r: r["bh_sel"] > 0 and r["bh_fp"] / r["bh_sel"] > GAMMA  # noqa: E731
    ever = lambda f: sum(any(f(r) for r in v) for v in by.values())       # noqa: E731
    out = {"draws": len(rows), "distinct_scans": N,
           "appearances_per_scan": {"min": min(map(len, by.values())), "max": max(map(len, by.values())),
                                    "mean": round(len(rows) / N, 2)}}
    for name, f in [("curve_violated", lambda r: r["curve_fail"]), ("fdp_gt_gamma", fdx),
                    ("false_certified_dis", lambda r: r["dis_cert_false"]),
                    ("certified_area_wrong", lambda r: r["cert_area_wrong"]),
                    ("raw_seg_false_dis", lambda r: r["dis_raw_false"]),
                    ("bh_selection_false_dis", lambda r: r["dis_bh_false"]),
                    ("bh_at_gamma_fdp_gt_gamma", bhx)]:
        x_draw = sum(bool(f(r)) for r in rows)
        x = ever(f)
        out[name] = {"draws_with_event": x_draw, "draw_rate": round(x_draw / len(rows), 4),
                     "draw_rate_ci95_scan_cluster": cluster_bootstrap(
                         by, lambda it, f=f: float(np.mean([bool(f(r)) for r in it])), N_BOOT, rng),
                     "distinct_scans_ever": x, "distinct_rate": round(x / N, 4),
                     "distinct_ci95_exact": clopper_pearson(x, N),
                     "distinct_upper95_one_sided": cp_upper_one_sided(x, N)}
    gd = {k: v for k, v in by.items() if v[0]["gt_dis"]}
    out["certified_on_gt_dis"] = {"gt_dis_distinct_scans": len(gd),
                                  "distinct_ever_certified": sum(any(r["dis_cert"] for r in v) for v in gd.values()),
                                  "draws_gt_dis": sum(len(v) for v in gd.values()),
                                  "draws_certified": sum(r["dis_cert"] for v in gd.values() for r in v)}
    # "at risk" denominator: scans where a false DIS was possible at all (raw segmentation shows
    # >= 1 candidate in >= 2 of PV/JC/IT), for controls = scans whose raw DIS reading is false.
    risk = {k: v for k, v in by.items() if v[0]["dis_raw"]}
    xr = sum(any(r["dis_cert_false"] for r in v) for v in risk.values())
    out["at_risk_scans"] = {"n": len(risk), "ever_false_certified": xr,
                            "ci95_exact": clopper_pearson(xr, len(risk)) if risk else None,
                            "upper95_one_sided": cp_upper_one_sided(xr, len(risk)) if risk else None}
    ntrue = sum(r["n_true"] for r in rows)
    out["power_per_draw"] = round(sum(r["tp"] for r in rows) / ntrue, 4) if ntrue else None
    out["abstain_draw_rate"] = round(sum(r["sel"] == 0 for r in rows) / len(rows), 4)
    return out


def rotation(cases, keep, pool_false, pool, template="hc"):
    """Layer 2 with each scan of `keep` as the test scan once and the others as labelled scans."""
    tgt = [c for c in cases if c["site"] == "openms" and openms_patient(c["case"]) in keep]
    fam = cf.EnvelopeFamily(DELTA, template)
    safe = {}
    for c in tgt:
        if c["scores"].size == 0:
            safe[c["case"]] = 0
            continue
        k, n = cf.conformal_ranks(c["scores"], pool_false)
        safe[c["case"]] = cf.scan_safe_inflation_simultaneous(k, n, rd._isf(c), fam)
    jobs, thetas = [], {}
    for c in tgt:
        th = cf.scan_level_theta([safe[o["case"]] for o in tgt if o["case"] != c["case"]], DELTA)
        thetas[c["case"]] = th
        jobs.append((c, pool_false, template, 10 ** 6 if th is None else th))
    rows = pool.map(rd.eval_scan, jobs)
    return rows, {"safe_values": {k: int(v) for k, v in safe.items()},
                  "theta_per_test_scan": {k: (None if v is None else int(v)) for k, v in thetas.items()}}


def per_scan_table(rows):
    return [{"case": r["case"], "m": r["m"], "n_true": r["n_true"], "sel": r["sel"], "fp": r["fp"],
             "curve_violated": bool(r["curve_fail"]), "fdp_gt_gamma": bool(r["sel"] > 0 and r["fdp"] > GAMMA),
             "gt_dis": r["gt_dis"], "dis_certified": r["dis_cert"], "false_certified": r["dis_cert_false"],
             "raw_dis_false": r["dis_raw_false"]} for r in rows]


def main():
    t0 = time.time()
    cases, meta = load_cache(".region_cache.npz")
    rng = np.random.RandomState(SEED)
    rec = {"inputs": [meta], "gamma": GAMMA, "delta": DELTA, "template": "hc (pre-registered primary)",
           "flames_split": flames_split(), "runs": {}}
    sp = flames_split()
    ms_false = np.concatenate([c["scores"][rd._isf(c)] for c in cases if c["site"] == "mslesseg"])
    with Pool(max(1, (os.cpu_count() or 2) - 2)) as pool:
        # ---- A: pre-registered Layer-2 runs, re-aggregated on distinct scans
        for site, kw in [("openms", dict(pool_from=["mslesseg"], K=20, T=10)),
                         ("mslesseg", dict(n_pool_subj=35, K=29, T=11)),
                         ("sibbms", dict(pool_from=["openms", "mslesseg"], K=20, T=10))]:
            rows, splits, _ = rd.layer2(cases, site, "hc", pool, **kw)
            d = distinct(rows, rng)
            d["v01_style_counts"] = {"curve_violated": sum(r["curve_fail"] for r in rows),
                                     "fdp_gt_gamma": sum(r["sel"] > 0 and r["fdp"] > GAMMA for r in rows),
                                     "false_certified_dis": sum(r["dis_cert_false"] for r in rows),
                                     "draws": len(rows)}
            d["theta_hat_per_split"] = [s["theta_hat"] for s in splits]
            rec["runs"][f"A_preregistered_layer2|{site}"] = d
            print(f"A {site}: draws {len(rows)} distinct {d['distinct_scans']} | v0.1-style {d['v01_style_counts']}"
                  f" | false-cert distinct {d['false_certified_dis']['distinct_scans_ever']}/{d['distinct_scans']}"
                  f" upper95 {d['false_certified_dis']['distinct_upper95_one_sided']}")
        # ---- B: controls, clean pool (MSLesSeg only), same 20 splits
        rows = pool.map(rd.eval_scan, rd.loso_jobs(cases, "sibbms", "hc", calib_from=["mslesseg"]))
        s = rd.summarize(rows, "L1 controls, MSLesSeg-only null")
        rec["runs"]["B_layer1_controls_mslesseg_null"] = {"summary": s, "distinct": distinct(rows, rng)}
        rows, splits, _ = rd.layer2(cases, "sibbms", "hc", pool, pool_from=["mslesseg"], K=20, T=10)
        d = distinct(rows, rng)
        d["theta_hat_per_split"] = [x["theta_hat"] for x in splits]
        rec["runs"]["B_layer2_controls_mslesseg_pool"] = d
        print(f"B controls clean pool: false-cert distinct {d['false_certified_dis']['distinct_scans_ever']}/"
              f"{d['distinct_scans']} | curve-violated draws {d['curve_violated']['draws_with_event']}/{d['draws']}"
              f" distinct {d['curve_violated']['distinct_scans_ever']}")
        # ---- C: openms subsets by FLAMeS training status, pool = MSLesSeg
        for name in ("heldout10", "clean12", "trained20"):
            keep = set(sp[name])
            tgt = [c for c in cases if c["site"] == "openms" and openms_patient(c["case"]) in keep]
            l1 = pool.map(rd.eval_scan, [(c, ms_false, "hc", 0) for c in tgt])
            rows, info = rotation(cases, keep, ms_false, pool)
            rec["runs"][f"C_openms_{name}"] = {
                "layer1_mslesseg_pool": {"distinct": distinct(l1, rng), "per_scan": per_scan_table(l1)},
                "layer2_rotation": {"distinct": distinct(rows, rng), "per_scan": per_scan_table(rows), **info}}
            dd = rec["runs"][f"C_openms_{name}"]["layer2_rotation"]["distinct"]
            print(f"C {name}: L2 rotation n={dd['distinct_scans']} curve-violated {dd['curve_violated']['distinct_scans_ever']}"
                  f" FDP>g {dd['fdp_gt_gamma']['distinct_scans_ever']} false-cert {dd['false_certified_dis']['distinct_scans_ever']}"
                  f" | certified on GT-DIS {dd['certified_on_gt_dis']} | power {dd['power_per_draw']} abstain {dd['abstain_draw_rate']}")
    # ---- D: A1 test on the clean subset
    ho = [c for c in cases if c["site"] == "openms" and openms_patient(c["case"]) in set(sp["heldout10"])]
    rec["runs"]["D_a1_permutation_openms_heldout10"] = rd.a1_permutation_test(ho, "openms")
    print("D A1 heldout10:", rec["runs"]["D_a1_permutation_openms_heldout10"])
    rec["runtime_s"] = round(time.time() - t0, 1)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print(f"wrote {OUT_JSON} in {rec['runtime_s']} s")


if __name__ == "__main__":
    main()
