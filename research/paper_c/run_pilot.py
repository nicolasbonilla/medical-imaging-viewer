#!/usr/bin/env python3
"""Paper C pilot — pre-registered analysis (docs/research/paper-c/PROTOCOL.md §4–§11).

Reads research/paper_c/.cache/candidates.json (extract_candidates.py) and writes
docs/research/records/2026-10-21_paper_c_pilot.json; prints the tables used in RESULTS.md.

    python research/paper_c/run_pilot.py
"""
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import conformal as K  # noqa: E402

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "candidates.json")
OUT = os.path.join(C.RECORDS, "2026-10-21_paper_c_pilot.json")
ALPHAS = (0.1, 0.2)
DELTA = 0.1
METHODS = ("marginal", "pac", "plugin")


def units_for(arm, cache):
    """List of analysis units {id, patient, active, burden, n_truth_lesions, cands[score,true,hits]}."""
    oms, msl = cache["open_ms"], cache["mslesseg"]
    spec = {
        "A1": (oms, "dsub", "1.5", "score", "true", False),
        "A1_truthpos": (oms, "dsub", "1.5", "score", "true_pos", False),
        "A1_t1.0": (oms, "dsub", "1.0", "score", "true", False),
        "A1_t2.0": (oms, "dsub", "2.0", "score", "true", False),
        "A2": (msl, "dseg", None, "score_sub", "true", True),
        "A2b": (msl, "dseg", None, "score_dp", "true", True),
        "A3": (msl, "dsub", "1.5", "score", "true", True),
        "A3_t1.0": (msl, "dsub", "1.0", "score", "true", True),
        "A3_t2.0": (msl, "dsub", "2.0", "score", "true", True),
        "A2_allpairs": (msl, "dseg", None, "score_sub", "true", False),
        "A2b_allpairs": (msl, "dseg", None, "score_dp", "true", False),
        "A3_allpairs": (msl, "dsub", "1.5", "score", "true", False),
        "A4": (oms, "dseg", None, "score_sub", "true", False),
        "A4b": (oms, "dseg", None, "score_dp", "true", False),
    }[arm]
    src, det, thr, key, lab, first_only = spec
    out = []
    for u in src:
        if first_only and not u["first_pair"]:
            continue
        if det == "dseg" and "dseg" not in u:
            return None                                    # A4 pending (no FLAMeS maps yet)
        raw = u["dsub"][thr] if det == "dsub" else u["dseg"]
        cands = [{"score": c[key], "true": bool(c[lab]), "hits": c["hits"], "kind": c.get("kind", "sub"),
                  "score_sub": c.get("score_sub", c.get("score"))} for c in raw]
        out.append({"id": u["unit"], "patient": u["patient"], "active": u["active"], "burden": u["burden"],
                    "n_truth_lesions": u["n_truth_lesions"], "cands": cands, "app_flags": u.get("app_flags")})
    return out


def summarize(units, outcomes, alpha=None):
    """Aggregate per-unit outcomes (same order as units)."""
    n = len(units)
    fc = sum(o["false_call"] for o in outcomes)
    act = [i for i, u in enumerate(units) if u["active"]]
    tf = sum(outcomes[i]["true_flag"] for i in act)
    af = sum(o["any_flag"] for o in outcomes)
    ab = sum(o.get("abstained", False) for o in outcomes)
    # patient-cluster bootstrap for ratios
    by_p = defaultdict(lambda: [0, 0, 0, 0, 0])        # false_call, units, lesions_hit, lesions, n_false
    for u, o in zip(units, outcomes):
        b = by_p[u["patient"]]
        b[0] += o["false_call"]
        b[1] += 1
        b[2] += len(o["lesions_hit"])
        b[3] += u["n_truth_lesions"]
        b[4] += o["n_false"]
    P = list(by_p.values())
    fwer_bs = K.cluster_bootstrap([p[0] for p in P], [p[1] for p in P])
    sens = K.cluster_bootstrap([p[2] for p in P], [p[3] for p in P])
    nfalse = K.cluster_bootstrap([p[4] for p in P], [p[1] for p in P])
    r = {"units": n, "patients": len(P),
         "fwer": fc / n if n else float("nan"), "fwer_x": fc, "fwer_cp95": K.clopper_pearson(fc, n),
         "fwer_cluster_boot95": [fwer_bs[1], fwer_bs[2]],
         "true_flag_active": tf / len(act) if act else float("nan"), "true_flag_x": tf, "n_active": len(act),
         "true_flag_cp95": K.clopper_pearson(tf, len(act)),
         "any_flag": af / n if n else float("nan"), "abstained": ab,
         "lesion_sensitivity": sens[0], "lesion_sensitivity_boot95": [sens[1], sens[2]],
         "lesions_total": int(sum(p[3] for p in P)),
         "false_calls_per_unit": nfalse[0], "false_calls_per_unit_boot95": [nfalse[1], nfalse[2]]}
    if alpha is not None:
        lo = r["fwer_cp95"][0]
        r["classification"] = "violated" if lo > alpha else "no violation detected"
        r["informative"] = ("informative" if r["true_flag_active"] >= 0.5 else
                            "bought by abstention" if r["true_flag_active"] < 0.2 else "intermediate")
    return r


def loo(units, alpha, method, calib_units=None):
    """Leave-one-patient-out: calibrate on the other patients' units (or on calib_units if given)."""
    outs, lams = [], []
    for u in units:
        cal = calib_units if calib_units is not None else [v for v in units if v["patient"] != u["patient"]]
        lam = K.threshold([K.max_false(v["cands"]) for v in cal], alpha, method=method, delta=DELTA)
        o = K.evaluate_patient(u["cands"], lam)
        o["abstained"] = not np.isfinite(lam)
        outs.append(o)
        lams.append(lam)
    return outs, lams


def fixed(units, lam=float("-inf"), rule=None):
    outs = []
    for u in units:
        if rule == "app_sub":                  # new counted only if subtraction-confirmed (>= 0.5 SD)
            keep = [c for c in u["cands"] if c["kind"] == "enlarged" or c["score_sub"] >= 0.5]
            o = K.evaluate_patient(keep, float("-inf"))
        else:
            o = K.evaluate_patient(u["cands"], lam)
        outs.append(o)
    return outs


def describe(units):
    nc = [len(u["cands"]) for u in units]
    nf = [sum(not c["true"] for c in u["cands"]) for u in units]
    mf = [K.max_false(u["cands"]) for u in units]
    auc = K.auroc_cluster(units)
    rho, p = K.spearman_perm(mf, [u["burden"] for u in units])
    fin = [m for m in mf if np.isfinite(m)]
    return {"candidates_per_unit_median": float(np.median(nc)), "candidates_per_unit_iqr": [float(np.percentile(nc, 25)), float(np.percentile(nc, 75))],
            "candidates_total": int(sum(nc)), "false_candidates_total": int(sum(nf)),
            "true_candidates_total": int(sum(nc) - sum(nf)),
            "units_with_false_candidate": int(sum(1 for x in nf if x > 0)),
            "max_false_score_quartiles": [float(np.percentile(fin, q)) for q in (25, 50, 75)] if fin else None,
            "auroc": auc[0], "auroc_boot95": [auc[1], auc[2]],
            "q4_spearman_maxfalse_vs_burden": rho, "q4_perm_p": p,
            "stable_units": int(sum(not u["active"] for u in units))}


def fmt(r):
    return (f"FWER {r['fwer']:.2f} ({r['fwer_x']}/{r['units']}) CP[{r['fwer_cp95'][0]:.2f},{r['fwer_cp95'][1]:.2f}] | "
            f"true-flag {r['true_flag_active']:.2f} ({r['true_flag_x']}/{r['n_active']}) | "
            f"lesion sens {r['lesion_sensitivity']:.3f} [{r['lesion_sensitivity_boot95'][0]:.3f},{r['lesion_sensitivity_boot95'][1]:.3f}] | "
            f"false/unit {r['false_calls_per_unit']:.2f} | abstain {r['abstained']}")


def main():
    cache = json.load(open(CACHE))
    rec = {"cache_sha256": hashlib.sha256(open(CACHE, "rb").read()).hexdigest(), "params": cache["params"],
           "code_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                         cwd=C.ROOT).stdout.strip(), "arms": {}}
    arms = ["A1", "A2", "A2b", "A3", "A1_truthpos", "A1_t1.0", "A1_t2.0", "A3_t1.0", "A3_t2.0",
            "A2_allpairs", "A2b_allpairs", "A3_allpairs", "A4", "A4b"]
    for arm in arms:
        units = units_for(arm, cache)
        if units is None:
            rec["arms"][arm] = {"status": "pending: FLAMeS maps for open_ms longitudinal not present (CLOUD-JOB.md)"}
            print(f"\n=== {arm}: PENDING (cloud job)")
            continue
        a = {"describe": describe(units), "fixed": {}, "loo": {}}
        a["fixed"]["B_all"] = summarize(units, fixed(units))
        if arm.startswith(("A2", "A4")):
            a["fixed"]["B_app_sub"] = summarize(units, fixed(units, rule="app_sub"))
            a["fixed"]["B_fixed_0.5SD"] = summarize(units, fixed(units, lam=0.5)) if arm in ("A2", "A4", "A2_allpairs") else None
            a["app_activity_rate"] = float(np.mean([u["app_flags"]["app_activity"] for u in units]))
            a["app_subconfirmed_activity_rate"] = float(np.mean([u["app_flags"]["app_activity_subconfirmed"] for u in units]))
        for alpha in ALPHAS:
            for m in METHODS:
                outs, lams = loo(units, alpha, m)
                s = summarize(units, outs, alpha)
                fin = [x for x in lams if np.isfinite(x)]
                s["threshold_median"] = float(np.median(fin)) if fin else None
                a["loo"][f"{m}_a{alpha}"] = s
        rec["arms"][arm] = a
        d = a["describe"]
        print(f"\n=== {arm}: {len(units)} units, {d['candidates_total']} candidates ({d['true_candidates_total']} true), "
              f"median {d['candidates_per_unit_median']:.0f}/unit, units with >=1 false cand {d['units_with_false_candidate']}, "
              f"stable units {d['stable_units']}")
        print(f"   AUROC {d['auroc']:.3f} [{d['auroc_boot95'][0]:.3f},{d['auroc_boot95'][1]:.3f}] | "
              f"Q4 rho(maxfalse, burden) {d['q4_spearman_maxfalse_vs_burden']:.2f} p={d['q4_perm_p']:.3f}")
        for k, v in a["fixed"].items():
            if v:
                print(f"   {k:14s} {fmt(v)}")
        if "app_activity_rate" in a:
            print(f"   app activity_candidate rate {a['app_activity_rate']:.2f}; subtraction-confirmed {a['app_subconfirmed_activity_rate']:.2f}")
        for k, v in a["loo"].items():
            print(f"   {k:14s} {fmt(v)} | {v['classification']}, {v['informative']} | thr~{v['threshold_median']}")

    # exploratory transport, D-sub (A1 <-> A3)
    a1, a3 = units_for("A1", cache), units_for("A3", cache)
    tr = {}
    for name, cal, test in (("open_ms->MSLesSeg", a1, a3), ("MSLesSeg->open_ms", a3, a1)):
        for alpha in ALPHAS:
            lam = K.threshold([K.max_false(v["cands"]) for v in cal], alpha)
            outs = []
            for u in test:
                o = K.evaluate_patient(u["cands"], lam)
                o["abstained"] = not np.isfinite(lam)
                outs.append(o)
            s = summarize(test, outs, alpha)
            s["threshold"] = lam
            tr[f"{name}_a{alpha}"] = s
            print(f"   transport {name} a={alpha}: thr {lam:.3f} {fmt(s)} | {s['classification']}")
    rec["transport_dsub"] = tr
    json.dump(rec, open(OUT, "w"), indent=1, default=float)
    print("\nwrote", os.path.relpath(OUT, C.ROOT))


if __name__ == "__main__":
    main()
