"""Paper F — tables from evaluate.py outputs (per_scan.csv + comparisons.json). LOCAL, no cloud calls.

Adds nothing to the protocol: it only formats the pre-registered outputs and, for an INTERIM report
(some tools not run yet), replaces Holm in an incomplete family by its conservative Bonferroni bound
(p x family size, capped at 1), which Holm can never exceed once the family is complete.

    python research/paper_f/summarize.py --results <dir with per_scan.csv, comparisons.json> --out <tables.md>
"""
import argparse
import csv
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import metrics as M  # noqa: E402

FAMILY_SIZE = {"primary": 6, "secondary": 11, "secondary_raw_arm": 4}
COHORTS = ("mslesseg", "openms", "ms3seg", "muslim", "pedims")
NAMES = {"flames": "FLAMeS (5 folds)", "lstai": "LST-AI", "mindglide": "MindGlide", "mindglide-raw": "MindGlide raw input",
         "wmhsynthseg": "WMH-SynthSeg", "samseg": "SAMSEG"}
USABLE = ("ok", "failed-as-empty")


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def load_rows(path):
    return list(csv.DictReader(open(path, encoding="utf-8")))


def fmt(x, d=3):
    return "—" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.{d}f}"


def ci(r, d=3):
    lo, hi = r.get("ci95", [None, None])
    return f"{fmt(r.get('estimate'), d)} ({fmt(lo, d)} to {fmt(hi, d)})"


def pfmt(p):
    return "—" if p is None else ("< 0.0001" if p < 1e-4 else f"{p:.4f}")


def usable(rows, tool, variant="primary", band=None, cohort=None, sub_band=None):
    return [r for r in rows if r["variant"] == variant and r["tool"] == tool and r["status"] in USABLE
            and not r["contaminated"] and (band is None or r["band"] == band)
            and (cohort is None or r["cohort"] == cohort) and (sub_band is None or r["sub_band"] == sub_band)]


def boot_mean(rs, key, n_boot):
    v = [num(r.get(key)) for r in rs]
    return M.stratified_cluster_bootstrap(v, [r["cohort"] for r in rs], [r["patient"] for r in rs], n_boot=n_boot)


def boot_ratio(rs, num_keys, den_keys, n_boot, seed=M.BOOT_SEED):
    """Pooled proportion sum(num)/sum(den) with the patient-cluster bootstrap stratified by cohort."""
    by = {}
    for r in rs:
        a = sum(num(r.get(k)) for k in num_keys)
        b = sum(num(r.get(k)) for k in den_keys)
        if math.isfinite(a) and math.isfinite(b):
            by.setdefault(r["cohort"], {}).setdefault(r["patient"], [0.0, 0.0])
            by[r["cohort"]][r["patient"]][0] += a
            by[r["cohort"]][r["patient"]][1] += b
    arr = {c: np.array(list(p.values())) for c, p in by.items()}
    tot = sum(a[:, 1].sum() for a in arr.values()) if arr else 0
    if not tot:
        return {"estimate": None, "ci95": [None, None], "n_ref": 0}
    point = sum(a[:, 0].sum() for a in arr.values()) / tot
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        s = np.zeros(2)
        for a in arr.values():
            s += a[rng.integers(0, len(a), len(a))].sum(axis=0)
        boots.append(s[0] / s[1] if s[1] else np.nan)
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return {"estimate": float(point), "ci95": [float(lo), float(hi)], "n_ref": int(tot)}


def tables(rows, comp, n_boot=M.BOOT_N):
    tools = [t for t in NAMES if any(r["tool"] == t and r["status"] in USABLE for r in rows)]
    L, out = [], {"tools_with_outputs": tools}
    L.append("### Table 1 — per cohort (primary definitions; mean over scans, 95% patient-cluster bootstrap CI)\n")
    L.append("| Cohort | Tool | Scans | Lesion F1 | False lesions / scan | Dice | Lesion recall | Predicted mL | Expert mL |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    out["per_cohort"] = []
    for c in COHORTS:
        for t in tools:
            rs = usable(rows, t, cohort=c)
            if not rs:
                continue
            res = {k: boot_mean(rs, k, n_boot) for k in ("f1", "false_lesions", "dice", "recall", "vol_pred_ml", "vol_ref_ml")}
            out["per_cohort"].append({"cohort": c, "tool": t, "n": len(rs), **res})
            L.append(f"| {c} | {NAMES[t]} | {len(rs)} | {ci(res['f1'])} | {ci(res['false_lesions'], 1)} | {ci(res['dice'])} "
                     f"| {ci(res['recall'])} | {fmt(res['vol_pred_ml']['estimate'], 2)} | {fmt(res['vol_ref_ml']['estimate'], 2)} |")
    L.append("\n### Table 2 — per band (cohort-weighted mean, each cohort counts once; 95% CI)\n")
    L.append("| Band | Tool | Scans | Lesion F1 | False lesions / scan | Dice |")
    L.append("|---|---|---|---|---|---|")
    out["per_band"] = []
    for band, sub in (("iso", None), ("thick", None), ("thick", "thick_3-5.5"), ("thick", "thick_>5.5")):
        for t in tools:
            rs = usable(rows, t, band=band, sub_band=sub)
            if not rs:
                continue
            res = {k: boot_mean(rs, k, n_boot) for k in ("f1", "false_lesions", "dice")}
            label = sub or band
            out["per_band"].append({"band": label, "tool": t, "n": len(rs), **res})
            L.append(f"| {label} | {NAMES[t]} | {len(rs)} | {ci(res['f1'])} | {ci(res['false_lesions'], 1)} | {ci(res['dice'])} |")
    L.append("\n### Table 3 — pre-stated comparisons available now (difference = tool minus reference)\n")
    L.append("| Family | Tool vs | Band | Outcome | Scans / patients | Difference (95% CI) | 90% CI | p | Multiplicity-adjusted p | Equivalent? |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    out["comparisons"] = []
    for fam in ("primary", "secondary", "secondary_raw_arm"):
        avail = [r for r in comp.get(fam, []) if r.get("estimate") is not None]
        complete = len(avail) == FAMILY_SIZE[fam]
        for r in avail:
            adj = r.get("p_holm") if complete else (None if r.get("p_two_sided") is None
                                                    else min(1.0, FAMILY_SIZE[fam] * r["p_two_sided"]))
            how = "Holm" if complete else f"Bonferroni bound x{FAMILY_SIZE[fam]} (family incomplete)"
            band = r.get("band") or r.get("contrast", "")
            eq = r.get("equivalent_within_margin")
            out["comparisons"].append({**r, "family": fam, "p_adjusted": adj, "adjustment": how})
            L.append(f"| {fam} | {NAMES.get(r['tool'], r['tool'])} vs {NAMES.get(r['vs'], r['vs'])} | {band} | {r['outcome']} "
                     f"| {r.get('n_scans')} / {r.get('n_clusters')} | {ci(r, 3)} | {fmt(r.get('ci90', [None])[0])} to "
                     f"{fmt(r.get('ci90', [None, None])[1])} | {pfmt(r.get('p_two_sided'))} | {pfmt(adj)} ({how}) "
                     f"| {'—' if eq is None else ('yes' if eq else 'no')} |")
    L.append("\n### Table 4 — expert lesions detected, by lesion size (pooled over scans; 95% CI)\n")
    bins = M.SIZE_BIN_LABELS
    L.append("| Band | Tool | " + " | ".join(f"{b} mm³" for b in bins) + " |")
    L.append("|---|---|" + "---|" * len(bins))
    out["size_bins"] = []
    for band in ("iso", "thick"):
        for t in tools:
            rs = usable(rows, t, band=band)
            if not rs:
                continue
            cells = []
            for b in bins:
                r = boot_ratio(rs, [f"det_{b}"], [f"ref_{b}"], n_boot)
                out["size_bins"].append({"band": band, "tool": t, "bin": b, **r})
                cells.append(f"{fmt(r['estimate'], 2)} ({fmt(r['ci95'][0], 2)}–{fmt(r['ci95'][1], 2)}; n={r['n_ref']})")
            L.append(f"| {band} | {NAMES[t]} | " + " | ".join(cells) + " |")
    L.append("\n### Table 5 — sensitivity analyses of the primary comparisons (no multiplicity adjustment)\n")
    L.append("| Analysis | Tool | Outcome | Scans | Difference vs FLAMeS (95% CI) |")
    L.append("|---|---|---|---|---|")
    for r in comp.get("sensitivity", []):
        if r.get("estimate") is not None:
            L.append(f"| {r['analysis']} | {NAMES.get(r['tool'], r['tool'])} | {r['outcome']} | {r['n_scans']} | {ci(r)} |")
    L.append("\n### Table 6 — exploratory second-opinion analyses (7.5)\n")
    L.append("| Analysis | Tool | Band | Result |")
    L.append("|---|---|---|---|")
    for r in comp.get("exploratory", []):
        if r["analysis"].startswith("disagreement") and r.get("auroc") is not None:
            L.append(f"| E1 AUROC: disagreement flags FLAMeS lesion F1 < 0.5 | {NAMES[r['tool']]} | {r['band']} "
                     f"| {fmt(r['auroc'])} ({r['n_poor']} poor of {r['n_scans']} scans) |")
        elif r["analysis"].startswith("FLAMeS lesions confirmed") and r["f1"].get("estimate") is not None:
            L.append(f"| E2 confirmed-lesions filter minus FLAMeS alone | {NAMES[r['tool']]} | {r['band']} "
                     f"| F1 {ci(r['f1'])}; false lesions {ci(r['false_lesions'], 1)} |")
    status = {}
    for r in rows:
        if r["variant"] == "primary":
            status.setdefault(r["tool"], {}).setdefault(r["status"], 0)
            status[r["tool"]][r["status"]] += 1
    out["status_counts"] = status
    L.append("\n### Table 7 — what each tool contributed (primary variant rows)\n")
    L.append("| Tool | " + " | ".join(sorted({s for v in status.values() for s in v})) + " |")
    keys = sorted({s for v in status.values() for s in v})
    L.append("|---|" + "---|" * len(keys))
    for t, v in status.items():
        L.append(f"| {NAMES.get(t, t)} | " + " | ".join(str(v.get(k, 0)) for k in keys) + " |")
    return "\n".join(L) + "\n", out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--json-out")
    ap.add_argument("--n-boot", type=int, default=M.BOOT_N)
    a = ap.parse_args()
    rows = load_rows(os.path.join(a.results, "per_scan.csv"))
    comp = json.load(open(os.path.join(a.results, "comparisons.json")))
    md, data = tables(rows, comp, a.n_boot)
    open(a.out, "w", encoding="utf-8", newline="\n").write(md)
    if a.json_out:
        json.dump(data, open(a.json_out, "w"), indent=1)
    print(md)


if __name__ == "__main__":
    main()
