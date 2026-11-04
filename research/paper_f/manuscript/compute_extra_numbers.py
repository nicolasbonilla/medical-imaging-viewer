"""Paper F manuscript - extra numbers computed OFFLINE from the stored results (no cloud, no images).

Everything here is derived from files already committed with the pre-registered analysis:
  ../results/per_scan.csv.gz      per-scan metrics (evaluate.py run, commit 7a9a24e)
  ../results/comparisons.json     pre-registered comparisons
  data/compute_ledger_c8b4239.csv compute ledger snapshot (branch research/cloud-compute-ledger, commit c8b4239)

Nothing in this file changes a pre-registered result. Items marked "post hoc" were NOT in the protocol
(docs/research/paper-f/PROTOCOL.md) and are labelled as such wherever the manuscript uses them.

    python -I research/paper_f/manuscript/compute_extra_numbers.py
writes research/paper_f/manuscript/data/extra_numbers.json
"""
import csv
import gzip
import io
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PF = os.path.dirname(HERE)
sys.path.insert(0, PF)
import metrics as M  # noqa: E402  (the pre-registered metric and bootstrap code)

RES = os.path.join(PF, "results")
USABLE = ("ok", "failed-as-empty")
COHORTS = ("mslesseg", "openms", "ms3seg", "muslim", "pedims")
TOOLS = ("flames", "lstai", "mindglide", "mindglide-raw", "wmhsynthseg", "samseg")


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def load_rows():
    with gzip.open(os.path.join(RES, "per_scan.csv.gz"), "rb") as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8")))


def usable(rows, tool, band=None, cohort=None, cases=None):
    return [r for r in rows if r["variant"] == "primary" and r["tool"] == tool and r["status"] in USABLE
            and not r["contaminated"] and (band is None or r["band"] == band)
            and (cohort is None or r["cohort"] == cohort) and (cases is None or r["case"] in cases)]


def boot(rs, key, seed=M.BOOT_SEED):
    v = [num(r[key]) for r in rs]
    return M.stratified_cluster_bootstrap(v, [r["cohort"] for r in rs], [r["patient"] for r in rs], seed=seed)


def auroc_parts(scores, labels):
    s, y = np.asarray(scores, float), np.asarray(labels, bool)
    pos, neg = s[y], s[~y]
    if pos.size == 0 or neg.size == 0:
        return 0.0, 0
    gt = (pos[:, None] > neg[None, :]).sum()
    eq = (pos[:, None] == neg[None, :]).sum()
    return float(gt + 0.5 * eq), int(pos.size * neg.size)


def e1_table(rows, tool, band):
    """Reproduces evaluate.py's E1 inputs: per scan, disagreement score and 'FLAMeS poor' label."""
    sel = {r["case"]: r for r in rows if r["variant"] == "primary" and r["tool"] == tool and r["band"] == band
           and r["status"] == "ok" and not r["contaminated"] and r.get("agree_f1_vs_flames") not in (None, "")}
    fl = {r["case"]: r for r in rows if r["variant"] == "primary" and r["tool"] == "flames" and r["status"] == "ok"
          and not r["contaminated"] and r.get("f1") not in (None, "")}
    both = sorted(set(sel) & set(fl))
    return [{"case": c, "cohort": sel[c]["cohort"], "patient": sel[c]["patient"],
             "score": 1.0 - float(sel[c]["agree_f1_vs_flames"]), "poor": float(fl[c]["f1"]) < 0.5} for c in both]


def e1_posthoc(rows, tool, band, n_boot=M.BOOT_N, seed=M.BOOT_SEED):
    """POST HOC (not pre-registered): bootstrap CI of the E1 AUROC and a cohort-stratified AUROC."""
    t = e1_table(rows, tool, band)
    a = M.auroc([x["score"] for x in t], [x["poor"] for x in t])
    poor_by_cohort = defaultdict(int)
    n_by_cohort = defaultdict(int)
    for x in t:
        n_by_cohort[x["cohort"]] += 1
        poor_by_cohort[x["cohort"]] += int(x["poor"])
    # cohort-stratified AUROC: only poor-vs-not-poor pairs from the SAME cohort are compared
    num_, den_ = 0.0, 0
    for c in n_by_cohort:
        sub = [x for x in t if x["cohort"] == c]
        g, d = auroc_parts([x["score"] for x in sub], [x["poor"] for x in sub])
        num_, den_ = num_ + g, den_ + d
    strat = num_ / den_ if den_ else None
    # patient-cluster bootstrap stratified by cohort (same scheme as the protocol), percentile 95% CI
    by = defaultdict(lambda: defaultdict(list))
    for x in t:
        by[x["cohort"]][x["patient"]].append(x)
    clusters = {c: list(p.values()) for c, p in by.items()}
    rng = np.random.default_rng(seed)
    reps = []
    for _ in range(n_boot):
        s, y = [], []
        for c, cl in clusters.items():
            for i in rng.integers(0, len(cl), len(cl)):
                for x in cl[i]:
                    s.append(x["score"])
                    y.append(x["poor"])
        v = M.auroc(s, y)
        if v is not None:
            reps.append(v)
    lo, hi = (np.percentile(reps, [2.5, 97.5]).tolist() if reps else [None, None])
    return {"tool": tool, "band": band, "n_scans": len(t), "n_poor": int(sum(x["poor"] for x in t)),
            "auroc_reproduced": a, "auroc_ci95_posthoc": [lo, hi], "n_boot_valid": len(reps),
            "auroc_cohort_stratified_posthoc": strat,
            "poor_by_cohort": dict(poor_by_cohort), "scans_by_cohort": dict(n_by_cohort)}


def auroc_block(t, key, n_boot=M.BOOT_N, seed=M.BOOT_SEED):
    """Pooled AUROC, cohort-stratified AUROC and patient-cluster bootstrap CI of a score `key` in table `t`
    (rows with cohort, patient, poor, and the score) for identifying poor FLAMeS scans."""
    a = M.auroc([x[key] for x in t], [x["poor"] for x in t])
    num_, den_ = 0.0, 0
    for c in sorted({x["cohort"] for x in t}):
        sub = [x for x in t if x["cohort"] == c]
        g, d = auroc_parts([x[key] for x in sub], [x["poor"] for x in sub])
        num_, den_ = num_ + g, den_ + d
    by = defaultdict(lambda: defaultdict(list))
    for x in t:
        by[x["cohort"]][x["patient"]].append(x)
    clusters = {c: list(p.values()) for c, p in by.items()}
    rng = np.random.default_rng(seed)
    reps = []
    for _ in range(n_boot):
        s, y = [], []
        for c, cl in clusters.items():
            for i in rng.integers(0, len(cl), len(cl)):
                for x in cl[i]:
                    s.append(x[key])
                    y.append(x["poor"])
        v = M.auroc(s, y)
        if v is not None:
            reps.append(v)
    return {"auroc": a, "auroc_ci95": np.percentile(reps, [2.5, 97.5]).tolist(),
            "auroc_cohort_stratified": num_ / den_ if den_ else None, "n_scans": len(t), "n_poor": int(sum(x["poor"] for x in t))}


def micro_f1(rs):
    tp_p = sum(num(r["tp_pred"]) for r in rs)
    n_p = sum(num(r["n_pred"]) for r in rs)
    tp_r = sum(num(r["tp_ref"]) for r in rs)
    n_r = sum(num(r["n_ref"]) for r in rs)
    p, r = tp_p / n_p, tp_r / n_r
    return 2 * p * r / (p + r)


def micro_paired(rows, tool, band, n_boot=M.BOOT_N, seed=M.BOOT_SEED):
    """Scan-pooled (micro) lesion-wise F1 of tool and FLAMeS on their paired scans; bootstrap of the difference."""
    t = {r["case"]: r for r in usable(rows, tool, band=band)}
    f = {r["case"]: r for r in usable(rows, "flames", band=band)}
    cases = sorted(set(t) & set(f))
    pairs = [(t[c], f[c]) for c in cases]
    by = defaultdict(lambda: defaultdict(list))
    for a, b in pairs:
        by[a["cohort"]][a["patient"]].append((a, b))
    clusters = {c: list(p.values()) for c, p in by.items()}
    point = (micro_f1([a for a, _ in pairs]), micro_f1([b for _, b in pairs]))
    rng = np.random.default_rng(seed)
    reps = []
    for _ in range(n_boot):
        sel = []
        for c, cl in clusters.items():
            for i in rng.integers(0, len(cl), len(cl)):
                sel.extend(cl[i])
        reps.append(micro_f1([a for a, _ in sel]) - micro_f1([b for _, b in sel]))
    lo, hi = np.percentile(reps, [2.5, 97.5])
    return {"n_scans": len(pairs), "tool_micro_f1": point[0], "flames_micro_f1": point[1],
            "difference": point[0] - point[1], "ci95": [float(lo), float(hi)]}


def revision_numbers(rows, comp, tier_c):
    rev = {}
    # (a) M2: absolute cohort-weighted F1 on the PAIRED sets used by the degradation contrast
    deg = {}
    for tool in ("mindglide", "wmhsynthseg", "lstai", "samseg", "mindglide-raw"):
        for band in ("iso", "thick"):
            t = {r["case"]: r for r in usable(rows, tool, band=band)}
            f = {r["case"]: r for r in usable(rows, "flames", band=band)}
            cases = set(t) & set(f)
            if not cases:
                continue
            deg[f"{tool}|{band}"] = {"n_scans": len(cases),
                                     "tool_f1": boot([t[c] for c in sorted(cases)], "f1"),
                                     "flames_f1": boot([f[c] for c in sorted(cases)], "f1")}
    rev["paired_set_absolute_f1"] = deg
    # (b) M2 / m10: per-cohort paired differences (tool - FLAMeS), single-cohort patient bootstrap
    pc = {}
    for tool in ("mindglide", "wmhsynthseg", "samseg", "lstai", "mindglide-raw"):
        for cohort in COHORTS:
            t = {r["case"]: r for r in usable(rows, tool, cohort=cohort)}
            f = {r["case"]: r for r in usable(rows, "flames", cohort=cohort)}
            cases = sorted(set(t) & set(f))
            if not cases:
                continue
            res = {"n_scans": len(cases)}
            for k in ("f1", "false_lesions"):
                d = [num(t[c][k]) - num(f[c][k]) for c in cases]
                res[k] = M.stratified_cluster_bootstrap(d, [cohort] * len(cases), [t[c]["patient"] for c in cases])
            pc[f"{tool}|{cohort}"] = res
    rev["per_cohort_paired_differences"] = pc
    rev["iso_band_cohorts"] = sorted({r["cohort"] for r in usable(rows, "flames", band="iso")})
    rev["iso_flames_scans_by_cohort"] = {c: len(usable(rows, "flames", band="iso", cohort=c)) for c in rev["iso_band_cohorts"]}
    # (c) M3: FLAMeS-only baselines for flagging poor FLAMeS scans (same 179 thick scans as the MindGlide E1)
    t = e1_table(rows, "mindglide", "thick")
    fl = {r["case"]: r for r in usable(rows, "flames", band="thick")}
    for x in t:
        x["fewer_flames_lesions"] = -num(fl[x["case"]]["n_pred"])
        x["smaller_flames_volume"] = -num(fl[x["case"]]["vol_pred_ml"])
        x["cohort_is_muslim"] = 1.0 if x["cohort"] == "muslim" else 0.0
    r1 = np.argsort(np.argsort([x["fewer_flames_lesions"] for x in t]))
    r2 = np.argsort(np.argsort([x["score"] for x in t]))
    for i, x in enumerate(t):
        x["rank_sum"] = float(r1[i] + r2[i])
    rev["e1_baselines_posthoc"] = {
        "mindglide_disagreement": auroc_block(t, "score"),
        "fewer_flames_lesions": auroc_block(t, "fewer_flames_lesions"),
        "smaller_flames_volume": auroc_block(t, "smaller_flames_volume"),
        "cohort_is_muslim": {"auroc": M.auroc([x["cohort_is_muslim"] for x in t], [x["poor"] for x in t])},
        "rank_sum_fewer_lesions_and_disagreement": {"auroc": M.auroc([x["rank_sum"] for x in t], [x["poor"] for x in t])},
    }
    poor = [x for x in t if x["poor"]]
    rev["poor_scans"] = [{"case": x["case"], "cohort": x["cohort"], "n_ref": int(num(fl[x["case"]]["n_ref"])),
                          "flames_f1": num(fl[x["case"]]["f1"])} for x in poor]
    thick_fl = usable(rows, "flames", band="thick")
    rev["thick_scans_with_fewer_than_5_ref_lesions"] = sum(int(num(r["n_ref"])) < 5 for r in thick_fl)
    rev["thick_scans_with_at_most_2_ref_lesions"] = sum(int(num(r["n_ref"])) <= 2 for r in thick_fl)
    rev["ms3seg_poor_scans_with_at_most_4_ref_lesions"] = sum(1 for p in rev["poor_scans"] if p["cohort"] == "ms3seg" and p["n_ref"] <= 4)
    # (d) m7: scan-pooled (micro) lesion-wise F1, tool - FLAMeS, on paired scans
    rev["micro_f1_posthoc"] = {f"{tool}|{band}": micro_paired(rows, tool, band)
                               for tool, band in (("mindglide", "thick"), ("wmhsynthseg", "thick"), ("samseg", "thick"),
                                                  ("mindglide-raw", "thick"), ("mindglide", "iso"), ("wmhsynthseg", "iso"),
                                                  ("lstai", "iso"))}
    # (e) m5: precision on the paired tier-C set (FLAMeS vs SAMSEG)
    fl_c = usable(rows, "flames", band="thick", cases=tier_c)
    sm_c = usable(rows, "samseg", band="thick", cases=tier_c)
    defined = {r["case"] for r in sm_c if r["precision"] not in ("", None)}
    rev["tier_c_precision"] = {"flames_all_129": boot(fl_c, "precision"),
                               "flames_on_samseg_defined": boot([r for r in fl_c if r["case"] in defined], "precision"),
                               "samseg": boot(sm_c, "precision"), "n_samseg_defined": len(defined)}
    # (f) m1: Monte Carlo SE of a two-sided bootstrap p near 0.45 with 10,000 replicates
    p = [r for r in comp["primary"] if r["tool"] == "mindglide" and r["outcome"] == "false_lesions"][0]["p_two_sided"]
    q = p / 2
    rev["mc_se_of_p_at_mindglide_fp"] = {"p": p, "se": 2 * math.sqrt(q * (1 - q) / M.BOOT_N)}
    return rev


def main():
    rows = load_rows()
    out = {"_provenance": {"per_scan_rows": len(rows), "inputs": ["results/per_scan.csv.gz", "results/comparisons.json",
                                                                  "manuscript/data/compute_ledger_c8b4239.csv"],
                           "bootstrap": f"{M.BOOT_N} replicates, seed {M.BOOT_SEED}, patient clusters within cohort"}}

    # 1. cohort geometry and counts (FLAMeS rows = every scan of the study)
    geo = {}
    for c in COHORTS:
        rs = [r for r in rows if r["variant"] == "primary" and r["tool"] == "flames" and r["cohort"] == c]
        sl = [num(r["slice_mm"]) for r in rs]
        geo[c] = {"scans": len(rs), "patients": len({r["patient"] for r in rs}),
                  "slice_mm_min": min(sl), "slice_mm_max": max(sl), "slice_mm_median": float(np.median(sl)),
                  "bands": sorted({r["band"] for r in rs}),
                  "flames_contaminated_scans": sum(1 for r in rs if r["contaminated"])}
    out["cohorts"] = geo
    for b in ("iso", "thick"):
        rs = [r for r in rows if r["variant"] == "primary" and r["tool"] == "flames" and r["band"] == b]
        out.setdefault("bands", {})[b] = {"scans": len(rs), "patients": len({r["patient"] for r in rs})}
    out["n_scans_total"] = len({r["case"] for r in rows})
    out["n_patients_total"] = len({r["patient"] for r in rows})

    # 2. expert lesions after the 14.137 mm^3 filter, by band (scans usable for FLAMeS comparisons)
    for b in ("iso", "thick"):
        rs = usable(rows, "flames", band=b)
        n_ref = sum(int(num(r["n_ref"])) for r in rs)
        small = sum(int(num(r["ref_14-50"])) for r in rs)
        out["bands"][b].update({"expert_lesions_flames_set": n_ref, "expert_lesions_14_50": small,
                                "share_14_50": small / n_ref if n_ref else None,
                                "scans_flames_set": len(rs),
                                "scans_with_empty_reference": sum(1 for r in rs if int(num(r["n_ref"])) == 0)})

    # 3. scans with no predicted lesion after the size filter (per tool and band; descriptive, post hoc)
    zero = {}
    for t in TOOLS:
        for b in ("iso", "thick"):
            rs = usable(rows, t, band=b)
            if rs:
                zero[f"{t}|{b}"] = {"scans": len(rs), "no_predicted_lesion": sum(1 for r in rs if int(num(r["n_pred"])) == 0)}
    out["zero_prediction_scans_posthoc"] = zero

    # 4. FLAMeS on the SAMSEG tier-C scans (descriptive; same estimator as Table 2)
    tier_c = set(open(os.path.join(RES, "samseg_tier_c_ids.txt")).read().split())
    fl_c = usable(rows, "flames", band="thick", cases=tier_c)
    sm_c = usable(rows, "samseg", band="thick", cases=tier_c)
    out["tier_c"] = {"n_ids": len(tier_c), "flames_scans": len(fl_c), "samseg_scans": len(sm_c),
                     "flames_f1": boot(fl_c, "f1"), "flames_false_lesions": boot(fl_c, "false_lesions"),
                     "samseg_f1": boot(sm_c, "f1"), "samseg_false_lesions": boot(sm_c, "false_lesions")}

    # 5. lesion-wise precision per band (cohort-weighted, descriptive; per cohort is in comparisons.json)
    prec = {}
    for t in TOOLS:
        for b in ("iso", "thick"):
            rs = usable(rows, t, band=b)
            if rs:
                prec[f"{t}|{b}"] = boot(rs, "precision")
    out["precision_by_band_descriptive"] = prec
    rec = {}
    for t in TOOLS:
        for b in ("iso", "thick"):
            rs = usable(rows, t, band=b)
            if rs:
                rec[f"{t}|{b}"] = boot(rs, "recall")
    out["recall_by_band_descriptive"] = rec

    # 6. exploratory E1 - post hoc CI and cohort-stratified AUROC
    out["e1_posthoc"] = [e1_posthoc(rows, t, "thick") for t in ("mindglide", "wmhsynthseg", "samseg")]
    comp = json.load(open(os.path.join(RES, "comparisons.json")))
    for e in out["e1_posthoc"]:
        reg = [x for x in comp["exploratory"] if x.get("auroc") is not None and x["tool"] == e["tool"]
               and x["band"] == e["band"]][0]
        e["auroc_registered"] = reg["auroc"]
        assert abs(reg["auroc"] - e["auroc_reproduced"]) < 1e-12, "E1 AUROC not reproduced"

    # 7. compute and cost (ledger snapshot)
    led = list(csv.DictReader(open(os.path.join(HERE, "data", "compute_ledger_c8b4239.csv"), encoding="utf-8")))
    f = [r for r in led if r["run_id"].startswith("toolbench")]
    groups = {"pilots": ("toolbench-pilot-mindglide", "toolbench-pilot-mindglide-2", "toolbench-pilot-mindglide-3",
                         "toolbench-pilot-fs", "toolbench-pilot-fs-2"),
              "mindglide_primary": ("toolbench-mindglide-a", "toolbench-mindglide-b"),
              "mindglide_raw_arm": ("toolbench-mgraw", "toolbench-mgraw-2"),
              "wmhsynthseg": ("toolbench-wmh", "toolbench-wmh-crop"),
              "samseg_tier_c": ("toolbench-samseg-a", "toolbench-samseg-b", "toolbench-samseg-c")}
    cost = {"runs": len(f), "vm_hours": sum(float(r["vm_hours"]) for r in f),
            "usd_list": sum(float(r["cost_usd_list"]) for r in f), "by_group": {}}
    for g, ids in groups.items():
        rs = [r for r in f if r["run_id"] in ids]
        cost["by_group"][g] = {"runs": len(rs), "vm_hours": sum(float(r["vm_hours"]) for r in rs),
                               "usd_list": sum(float(r["cost_usd_list"]) for r in rs)}
    assert sum(len(v) for v in groups.values()) == len(f)
    upstream_ids = {"flames_iso_maps": ("flames-full-a", "flames-full-b", "flames-full-c"),
                    "flames_thick_maps_incl_hdbet": ("flames-extra-a", "flames-extra-b"),
                    "lstai_maps": ("lstai-full-a",)}
    cost["upstream_not_paper_f"] = {}
    for g, ids in upstream_ids.items():
        rs = [r for r in led if r["run_id"] in ids]
        cost["upstream_not_paper_f"][g] = {"runs": len(rs), "vm_hours": sum(float(r["vm_hours"]) for r in rs),
                                           "usd_list": sum(float(r["cost_usd_list"]) for r in rs)}
    out["compute"] = cost
    up = sum(g["usd_list"] for g in cost["upstream_not_paper_f"].values())
    cost["usd_list_including_reused_runs"] = cost["usd_list"] + up
    cost["vm_hours_including_reused_runs"] = cost["vm_hours"] + sum(g["vm_hours"] for g in cost["upstream_not_paper_f"].values())

    # 8. REVISION (2026-10-31, after the internal review; all POST HOC and labelled as such in the manuscript)
    out["revision"] = revision_numbers(rows, comp, tier_c)

    path = os.path.join(HERE, "data", "extra_numbers.json")
    json.dump(out, open(path, "w", encoding="utf-8"), indent=1, default=float)
    print("wrote", path)
    for e in out["e1_posthoc"]:
        print("E1", e["tool"], round(e["auroc_reproduced"], 3), [None if v is None else round(v, 3) for v in e["auroc_ci95_posthoc"]],
              "strat", None if e["auroc_cohort_stratified_posthoc"] is None else round(e["auroc_cohort_stratified_posthoc"], 3),
              e["poor_by_cohort"], e["scans_by_cohort"])


if __name__ == "__main__":
    main()
