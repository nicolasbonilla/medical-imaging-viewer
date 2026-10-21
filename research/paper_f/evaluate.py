"""Paper F — LOCAL evaluation (no cloud calls). Implements docs/research/paper-f/PROTOCOL.md.

Two sub-commands:

  check    structural pass/fail of tool outputs downloaded from the bucket (pilot and full run):
           every {case}_{tool}_seg.nii.gz must sit on the exact FLAMeS grid ({case}_gt.nii.gz), be
           binary, and any {case}_{tool}_prob.nii.gz must be on the same grid with values in [0, 1].
  run      per-scan metrics for every tool and every pre-stated sensitivity variant, then the
           pre-stated comparisons (primary family with Holm, secondary family with Holm, descriptive
           per-cohort tables, exploratory second-opinion analyses).

    python research/paper_f/evaluate.py check --tool-dir <D>/toolbench/cohort \
        --flames-dir data/cohorts/cloud-2026-10/flames --cases mslesseg_P10_T1 ms3seg_001 pedims_P1_T1
    python research/paper_f/evaluate.py run --flames-dir data/cohorts/cloud-2026-10/flames \
        --lstai-dir data/cohorts/cloud-2026-10/lstai --tool-dir data/cohorts/cloud-2026-10/toolbench \
        --manifests data/cohorts/cloud-2026-10/toolbench-manifests --out <results dir>

Predictions (binary, on the FLAMeS grid):
  flames       mean of the five fold probabilities ({case}_f{k}_prob.nii.gz) > 0.5   (reference tool)
  lstai        LST-AI ensemble probability ({case}_lstai_prob.nii.gz) > 0.5 (= LST-AI's own binarisation)
  mindglide, wmhsynthseg, samseg   the tool's own hard mask ({case}_{tool}_seg.nii.gz) > 0.5
Ground truth: {case}_gt.nii.gz (binarised expert mask, same grid).
"""
import argparse
import csv
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import metrics as M  # noqa: E402

NEW_TOOLS = ("mindglide", "wmhsynthseg", "samseg")
RAW_ARM = ("mindglide-raw",)            # secondary arm 7.6: MindGlide on the FLAIR before skull stripping
TOOLS = ("flames", "lstai") + NEW_TOOLS + RAW_ARM
GRID_ATOL = 1e-4

# Contamination (PROTOCOL.md section 3): (tool, case) cells excluded from every comparison involving
# that tool and reported apart. FLAMeS was trained on Ljubljana except patients 16-20 and 26-30
# (research/cloud/ensemble_quality_check.py; FLAMeS ref. 13 = Lesjak 2018).
LJ_CLEAN_FOR_FLAMES = {f"openms_patient{i:02d}" for i in list(range(16, 21)) + list(range(26, 31))}


def contaminated(tool, case):
    """Reason string when `case` was (possibly) seen in training by `tool`, else None."""
    if tool == "flames" and case.startswith("openms_") and case not in LJ_CLEAN_FOR_FLAMES:
        return "FLAMeS training set (Ljubljana, FLAMeS ref. 13)"
    # LST-AI: trained on 491 in-house TUM scans; Ljubljana is one of its published TEST sets (kept).
    # MindGlide, WMH-SynthSeg, SAMSEG: none of the five cohorts appears in their training data
    # (PROTOCOL.md section 3, with sources). Any later finding is added here BEFORE unblinding.
    return None


# ----------------------------------------------------------------------------- loading
def _load(path):
    import nibabel as nib
    img = nib.load(path)
    return img, np.asarray(img.get_fdata(dtype=np.float32))


def same_grid(a, b):
    return tuple(a.shape[:3]) == tuple(b.shape[:3]) and np.allclose(a.affine, b.affine, atol=GRID_ATOL)


def list_cases(flames_dir):
    return sorted(os.path.basename(p)[:-len("_gt.nii.gz")] for p in glob.glob(os.path.join(flames_dir, "*_gt.nii.gz")))


def tool_paths(tool, case, dirs):
    if tool == "flames":
        return [os.path.join(dirs["flames"], f"{case}_f{k}_prob.nii.gz") for k in range(5)]
    if tool == "lstai":
        return [os.path.join(dirs["lstai"], f"{case}_lstai_prob.nii.gz")] if dirs.get("lstai") else []
    return [os.path.join(dirs["tool"], f"{case}_{tool}_seg.nii.gz")] if dirs.get("tool") else []


def load_prediction(tool, case, dirs, ref_img):
    """(binary mask or None, status). status: ok | missing | grid-mismatch."""
    paths = tool_paths(tool, case, dirs)
    if not paths or not all(os.path.exists(p) for p in paths):
        return None, "missing"
    arrs = []
    for p in paths:
        img, arr = _load(p)
        if not same_grid(img, ref_img):
            return None, "grid-mismatch"
        arrs.append(arr)
    return (np.mean(arrs, axis=0) if len(arrs) > 1 else arrs[0]) > 0.5, "ok"


def manifest_outcomes(manifest_dir):
    """{(case, tool): "ok" | "failed"} from toolbench run manifests (ok wins over an earlier failure)."""
    out = {}
    for p in sorted(glob.glob(os.path.join(manifest_dir or "", "*.json"))):
        m = json.load(open(p))
        for e in m.get("errors", []):
            out.setdefault((e.get("case"), e.get("tool")), "failed")
        for c in m.get("cases", []):
            if c.get("ok"):
                out[(c.get("case"), c.get("tool"))] = "ok"
    return out


# ----------------------------------------------------------------------------- check
def check_case(case, tool_dir, flames_dir, tools=NEW_TOOLS):
    fails, warns, info = [], [], {"case": case}
    gt_path = os.path.join(flames_dir, f"{case}_gt.nii.gz")
    if not os.path.exists(gt_path):
        return {**info, "fails": [f"no reference {gt_path}"], "warns": [], "pass": False}
    gimg, gt = _load(gt_path)
    for tool in tools:
        seg_p = os.path.join(tool_dir, f"{case}_{tool}_seg.nii.gz")
        prob_p = os.path.join(tool_dir, f"{case}_{tool}_prob.nii.gz")
        if not os.path.exists(seg_p):
            fails.append(f"{tool}: segmentation missing")
            continue
        simg, seg = _load(seg_p)
        if not same_grid(simg, gimg):
            fails.append(f"{tool}: segmentation grid differs from the FLAMeS grid")
            continue
        if not set(np.unique(seg).tolist()).issubset({0.0, 1.0}):
            fails.append(f"{tool}: segmentation is not binary 0/1")
        if os.path.exists(prob_p):
            pimg, prob = _load(prob_p)
            if not same_grid(pimg, gimg):
                fails.append(f"{tool}: probability grid differs from the FLAMeS grid")
            elif prob.min() < -1e-6 or prob.max() > 1 + 1e-6:
                fails.append(f"{tool}: probability outside [0, 1]")
            else:
                info[f"{tool}_prob_vs_seg_dice"] = M.dice(prob > 0.5, seg > 0.5)
        z = gimg.header.get_zooms()[:3]
        r = M.lesion_metrics(seg > 0.5, gt > 0.5, z)
        info[f"{tool}_dice"] = None if r["dice"] is None else round(r["dice"], 3)
        info[f"{tool}_lesion_f1"] = None if r["f1"] is None else round(r["f1"], 3)
        info[f"{tool}_lesion_ml"] = round(r["vol_pred_ml"], 2)
        if r["dice"] is not None and r["dice"] < 0.1:
            warns.append(f"{tool}: Dice vs expert {r['dice']:.3f} < 0.1 (orientation, label or grid?)")
        if r["vol_pred_ml"] > 10 * max(r["vol_ref_ml"], 1.0):
            warns.append(f"{tool}: {r['vol_pred_ml']:.1f} mL predicted vs {r['vol_ref_ml']:.1f} mL expert (>10x)")
    return {**info, "fails": fails, "warns": warns, "pass": not fails}


# ----------------------------------------------------------------------------- per-scan table
VARIANTS = {"primary": (M.MIN_LESION_MM3, 26), "S1_no_size_filter": (0.0, 26),
            "S2_min_3mm3": (3.0, 26), "S3_inplane_8conn": (M.MIN_LESION_MM3, 8)}
ROW_KEYS = ("n_ref", "n_pred", "tp_ref", "tp_pred", "false_lesions", "missed_lesions",
            "precision", "recall", "f1", "dice", "vol_pred_ml", "vol_ref_ml")


def per_scan_rows(cases, dirs, outcomes, tools=TOOLS, variants=VARIANTS):
    rows = []
    for case in cases:
        gimg, gt = _load(os.path.join(dirs["flames"], f"{case}_gt.nii.gz"))
        gt = gt > 0.5
        z = gimg.header.get_zooms()[:3]
        base = {"case": case, "cohort": M.cohort_of(case), "patient": M.patient_of(case),
                "band": M.band(z), "sub_band": M.sub_band(z), "slice_mm": round(M.slice_spacing(z), 3)}
        preds = {}
        for tool in tools:
            pred, status = load_prediction(tool, case, dirs, gimg)
            if status == "missing" and outcomes.get((case, tool)) == "failed":
                pred, status = np.zeros(gt.shape, bool), "failed-as-empty"        # intention to segment
            preds[tool] = (pred, status)
        for vname, (min_mm3, conn) in variants.items():
            if vname == "S3_inplane_8conn" and base["band"] != "thick":
                continue
            for tool, (pred, status) in preds.items():
                row = {**base, "variant": vname, "tool": tool, "status": status,
                       "contaminated": contaminated(tool, case) or ""}
                if pred is not None:
                    r = M.lesion_metrics(pred, gt, z, min_mm3, conn)
                    row.update({k: r[k] for k in ROW_KEYS})
                    for b, (n, d) in r["size_bins"].items():
                        row[f"ref_{b}"], row[f"det_{b}"] = n, d
                    if tool != "flames" and preds["flames"][0] is not None:
                        fl = preds["flames"][0]
                        a = M.lesion_metrics(pred, fl, z, min_mm3, conn)          # agreement with FLAMeS
                        row["agree_f1_vs_flames"] = a["f1"]
                        if vname == "primary":
                            c = M.lesion_metrics(M.confirmed(fl, pred, z, min_mm3, conn), gt, z, min_mm3, conn)
                            row.update({f"confirmed_{k}": c[k] for k in ("f1", "false_lesions", "recall", "dice")})
                rows.append(row)
    return rows


# ----------------------------------------------------------------------------- comparisons
def _num(v):
    return float(v) if v not in (None, "") else float("nan")


def paired(rows, tool, ref_tool, outcome, variant="primary", band=None, cohorts=None, complete_case=False,
           allow_contaminated=False, exclude_cohorts=()):
    """Aligned per-scan differences tool - ref_tool (both usable, neither contaminated by default).

    complete_case=True drops failed runs instead of scoring them as empty (sensitivity S4);
    allow_contaminated=True keeps training-set cases (S5); exclude_cohorts drops cohorts (S6)."""
    usable = ("ok",) if complete_case else ("ok", "failed-as-empty")
    by = {}
    for r in rows:
        if r["variant"] != variant or (band and r["band"] != band) or (cohorts and r["cohort"] not in cohorts):
            continue
        if r["cohort"] in exclude_cohorts:
            continue
        by.setdefault(r["case"], {})[r["tool"]] = r
    diffs, strata, clusters = [], [], []
    for case, d in sorted(by.items()):
        a, b = d.get(tool), d.get(ref_tool)
        if not a or not b or a["status"] not in usable or b["status"] not in usable:
            continue
        if (a["contaminated"] or b["contaminated"]) and not allow_contaminated:
            continue
        x, y = _num(a.get(outcome)), _num(b.get(outcome))
        if np.isfinite(x) and np.isfinite(y):
            diffs.append(x - y)
            strata.append(a["cohort"])
            clusters.append(a["patient"])
    return diffs, strata, clusters


def compare(rows, tool, ref_tool, outcome, band, margin=None, variant="primary", n_boot=M.BOOT_N, weighting="cohort",
            label="", **kw):
    d, s, c = paired(rows, tool, ref_tool, outcome, variant, band, **kw)
    return {"tool": tool, "vs": ref_tool, "outcome": outcome, "band": band, "variant": variant, "weighting": weighting,
            "analysis": label or variant, **M.stratified_cluster_bootstrap(d, s, c, n_boot=n_boot, weighting=weighting,
                                                                           margin=margin)}


def sensitivity(rows, n_boot=M.BOOT_N):
    """PROTOCOL.md section 7.4: the primary family re-run under each pre-stated variation (no Holm)."""
    out = []
    for tool in NEW_TOOLS:
        for outcome, margin in (("f1", M.EQUIV_MARGIN_F1), ("false_lesions", M.EQUIV_MARGIN_FP)):
            for v in ("S1_no_size_filter", "S2_min_3mm3", "S3_inplane_8conn"):
                out.append(compare(rows, tool, "flames", outcome, "thick", margin, variant=v, n_boot=n_boot))
            out.append(compare(rows, tool, "flames", outcome, "thick", margin, n_boot=n_boot,
                               label="S4_complete_case", complete_case=True))
            out.append(compare(rows, tool, "flames", outcome, "thick", margin, n_boot=n_boot,
                               label="S6_thick_without_muslim", exclude_cohorts=("muslim",)))
            out.append(compare(rows, tool, "flames", outcome, "thick", margin, n_boot=n_boot, weighting="scan",
                               label="S7_scan_weighted"))
    for tool in NEW_TOOLS + ("lstai",):
        out.append(compare(rows, tool, "flames", "f1", "iso", M.EQUIV_MARGIN_F1, n_boot=n_boot,
                           label="S5_iso_with_flames_training_cases", allow_contaminated=True))
    return out


def degradation(rows, tool, ref_tool, outcome, n_boot=M.BOOT_N):
    """Difference-in-differences: (tool - ref) on thick minus (tool - ref) on iso. Bands share no patient,
    so the two bootstraps are independent (different seeds)."""
    pt, bt, nt, kt = M.bootstrap_distribution(*paired(rows, tool, ref_tool, outcome, band="thick"), n_boot=n_boot)
    pi, bi, ni, ki = M.bootstrap_distribution(*paired(rows, tool, ref_tool, outcome, band="iso"), n_boot=n_boot,
                                              seed=M.BOOT_SEED + 1)
    if pt is None or pi is None:
        return {"tool": tool, "vs": ref_tool, "outcome": outcome, "contrast": "thick minus iso", "estimate": None}
    return {"tool": tool, "vs": ref_tool, "outcome": outcome, "contrast": "(tool-ref)_thick - (tool-ref)_iso",
            **M.summarize(pt - pi, bt - bi, nt + ni, kt + ki)}


def prestated(rows, n_boot=M.BOOT_N):
    """All comparisons fixed in PROTOCOL.md section 7, in protocol order."""
    out = {"primary": [], "secondary": [], "secondary_raw_arm": [], "sensitivity": [], "descriptive": [],
           "exploratory": []}
    for tool in NEW_TOOLS:                                       # P1-P6
        out["primary"].append(compare(rows, tool, "flames", "f1", "thick", M.EQUIV_MARGIN_F1, n_boot=n_boot))
        out["primary"].append(compare(rows, tool, "flames", "false_lesions", "thick", M.EQUIV_MARGIN_FP, n_boot=n_boot))
    for r, p in zip(out["primary"], M.holm([r["p_two_sided"] for r in out["primary"]])):
        r["p_holm"] = p
    sec = []
    for tool in NEW_TOOLS + ("lstai",):                          # S1-S8: iso band, incl. LST-AI
        sec.append(compare(rows, tool, "flames", "f1", "iso", M.EQUIV_MARGIN_F1, n_boot=n_boot))
        sec.append(compare(rows, tool, "flames", "false_lesions", "iso", M.EQUIV_MARGIN_FP, n_boot=n_boot))
    for tool in NEW_TOOLS:                                       # S9-S11: degradation with thickness
        sec.append(degradation(rows, tool, "flames", "f1", n_boot=n_boot))
    for r, p in zip(sec, M.holm([r.get("p_two_sided") for r in sec])):
        r["p_holm"] = p
    out["secondary"] = sec
    raw = []                                                     # R1-R4: raw-input arm, thick band (7.6)
    for ref in ("flames", "mindglide"):
        raw.append(compare(rows, "mindglide-raw", ref, "f1", "thick", M.EQUIV_MARGIN_F1, n_boot=n_boot))
        raw.append(compare(rows, "mindglide-raw", ref, "false_lesions", "thick", M.EQUIV_MARGIN_FP, n_boot=n_boot))
    for r, p in zip(raw, M.holm([r["p_two_sided"] for r in raw])):
        r["p_holm"] = p
    out["secondary_raw_arm"] = raw
    out["sensitivity"] = sensitivity(rows, n_boot)
    for tool in TOOLS:                                           # D: per cohort / band, every outcome
        for cohort in ("mslesseg", "openms", "ms3seg", "muslim", "pedims"):
            for outcome in ("f1", "false_lesions", "dice", "recall", "precision", "vol_pred_ml"):
                vals = [r for r in rows if r["variant"] == "primary" and r["tool"] == tool and r["cohort"] == cohort
                        and r["status"] in ("ok", "failed-as-empty") and not r["contaminated"]]
                v = [_num(r.get(outcome)) for r in vals]
                out["descriptive"].append({"tool": tool, "cohort": cohort, "outcome": outcome,
                                           **M.stratified_cluster_bootstrap(v, [cohort] * len(v),
                                                                            [r["patient"] for r in vals], n_boot=n_boot)})
    for tool in NEW_TOOLS + ("lstai",):                          # E: second opinion
        for band in ("iso", "thick"):
            sel = {r["case"]: r for r in rows if r["variant"] == "primary" and r["tool"] == tool and r["band"] == band
                   and r["status"] == "ok" and not r["contaminated"] and r.get("agree_f1_vs_flames") not in (None, "")}
            fl = {r["case"]: r for r in rows if r["variant"] == "primary" and r["tool"] == "flames" and r["status"] == "ok"
                  and not r["contaminated"] and r.get("f1") is not None}
            both = sorted(set(sel) & set(fl))
            score = [1.0 - float(sel[c]["agree_f1_vs_flames"]) for c in both]
            poor = [float(fl[c]["f1"]) < 0.5 for c in both]
            out["exploratory"].append({"analysis": "disagreement flags FLAMeS lesion F1 < 0.5", "tool": tool,
                                       "band": band, "n_scans": len(both), "n_poor": int(sum(poor)),
                                       "auroc": M.auroc(score, poor)})
            out["exploratory"].append({"analysis": "FLAMeS lesions confirmed by tool vs FLAMeS alone", "tool": tool,
                                       "band": band, "f1": compare_confirmed(rows, tool, "f1", band, n_boot),
                                       "false_lesions": compare_confirmed(rows, tool, "false_lesions", band, n_boot)})
    return out


def compare_confirmed(rows, tool, outcome, band, n_boot):
    d, s, c = [], [], []
    fl = {r["case"]: r for r in rows if r["variant"] == "primary" and r["tool"] == "flames"}
    for r in rows:
        if (r["variant"] != "primary" or r["tool"] != tool or r["band"] != band or r["status"] != "ok"
                or r["contaminated"] or r["case"] not in fl or fl[r["case"]]["contaminated"]):
            continue
        x, y = _num(r.get(f"confirmed_{outcome}")), _num(fl[r["case"]].get(outcome))
        if np.isfinite(x) and np.isfinite(y):
            d.append(x - y)
            s.append(r["cohort"])
            c.append(r["patient"])
    return M.stratified_cluster_bootstrap(d, s, c, n_boot=n_boot)


def write_csv(rows, path):
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--tool-dir", required=True)
    c.add_argument("--flames-dir", required=True)
    c.add_argument("--cases", nargs="+", required=True)
    c.add_argument("--tools", nargs="+", default=list(NEW_TOOLS))
    c.add_argument("--out")
    r = sub.add_parser("run")
    r.add_argument("--flames-dir", required=True)
    r.add_argument("--lstai-dir")
    r.add_argument("--tool-dir")
    r.add_argument("--manifests")
    r.add_argument("--cases", nargs="*")
    r.add_argument("--n-boot", type=int, default=M.BOOT_N)
    r.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "check":
        res = [check_case(x, a.tool_dir, a.flames_dir, a.tools) for x in a.cases]
        for x in res:
            extra = {k: v for k, v in x.items() if k not in ("case", "fails", "warns", "pass")}
            print(f"{'PASS' if x['pass'] else 'FAIL'} {x['case']}  {json.dumps(extra)}")
            for f in x["fails"]:
                print(f"    FAIL: {f}")
            for w in x["warns"]:
                print(f"    WARN: {w}")
        if a.out:
            json.dump(res, open(a.out, "w"), indent=1)
        sys.exit(0 if all(x["pass"] for x in res) else 1)
    dirs = {"flames": a.flames_dir, "lstai": a.lstai_dir, "tool": a.tool_dir}
    cases = a.cases or list_cases(a.flames_dir)
    rows = per_scan_rows(cases, dirs, manifest_outcomes(a.manifests))
    os.makedirs(a.out, exist_ok=True)
    write_csv(rows, os.path.join(a.out, "per_scan.csv"))
    res = prestated(rows, n_boot=a.n_boot)
    json.dump(res, open(os.path.join(a.out, "comparisons.json"), "w"), indent=1)
    for r in res["primary"]:
        print(f"PRIMARY {r['tool']:12s} {r['outcome']:14s} thick  est {r['estimate']}  95% CI {r['ci95']}  p_holm {r['p_holm']}")
    print(f"{len(rows)} per-scan rows -> {a.out}")


if __name__ == "__main__":
    main()
