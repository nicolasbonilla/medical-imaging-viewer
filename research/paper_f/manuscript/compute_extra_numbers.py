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

    path = os.path.join(HERE, "data", "extra_numbers.json")
    json.dump(out, open(path, "w", encoding="utf-8"), indent=1, default=float)
    print("wrote", path)
    for e in out["e1_posthoc"]:
        print("E1", e["tool"], round(e["auroc_reproduced"], 3), [None if v is None else round(v, 3) for v in e["auroc_ci95_posthoc"]],
              "strat", None if e["auroc_cohort_stratified_posthoc"] is None else round(e["auroc_cohort_stratified_posthoc"], 3),
              e["poor_by_cohort"], e["scans_by_cohort"])


if __name__ == "__main__":
    main()
