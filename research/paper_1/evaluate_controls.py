#!/usr/bin/env python3
"""Paper 1 healthy-control arm — evaluation (docs/research/paper-1/PREREG-healthy-controls.md, commit 1e62f5c).

LOCAL, CPU only, no cloud calls. The app's region / DIS functions are imported read-only (hc_core.AppDIS),
so run it in the offline environment:
    GOOGLE_APPLICATION_CREDENTIALS=<missing file> CLOUDSDK_CONFIG=<empty dir> GOOGLE_CLOUD_PROJECT=mstool-offline-tests

Subcommands
  check   G3 structural check of new tool outputs (FLAMeS grid, binary uint8, SHA-256 and voxel count equal
          to the run manifest). Prints PASS/FAIL per (control, tool); prints no lesion count.
  run     all pre-registered quantities (sections 5-7) for the arms whose files exist:
            flames_ens  mean of the 5 FLAMeS fold maps >= 0.5      {flames-dir}/sub-XXX_f{0..4}_prob.nii.gz
            flames_f0   FLAMeS fold 0 >= 0.5                       {flames-dir}/sub-XXX_f0_prob.nii.gz
            lstai       LST-AI ensemble probability >= 0.5         {lstai-dir}/sub-XXX_lstai_prob.nii.gz
            mindglide / wmhsynthseg / samseg   tool hard label on the FLAMeS grid
                                                                   {tool-dir}/sub-XXX_{tool}_seg.nii.gz
          lesion = 18-connected component >= 3 mm^3 (paper A); DIS = the app's dis_met_brain (paper A S3 path).
          Writes {out}/summary.json, per_control.csv, lesions.csv, tables.md, run_info.json.

    python research/paper_1/evaluate_controls.py run --flames-dir D/flames --lstai-dir D/lstai \
        --tool-dir D/toolbench --brainmask-dir D/brainmask --manifests D/manifests --out research/paper_1/results
    python research/paper_1/evaluate_controls.py check --tool-dir D/toolbench --manifests D/manifests \
        --tools wmhsynthseg mindglide samseg --cases sub-001 sub-021
"""
import argparse
import csv
import glob
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from multiprocessing import Pool

import nibabel as nib
import numpy as np
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "research", "paper_f"))
import hc_core as H                                                    # noqa: E402
import metrics as PF                                                   # noqa: E402  (paper F lesion rule, S5)

INPUTS = os.path.join(HERE, "controls_inputs.json")
PAPER_A_RECORD = os.path.join(ROOT, "docs", "research", "records", "2026-10-24_paper_a_v03c_controls.json")
ARMS = ("flames_ens", "flames_f0", "lstai", "mindglide", "wmhsynthseg", "samseg")
REFERENCE = "flames_ens"
COMPARED = ARMS[1:]                                                    # the five paired comparisons
DISTINCT = ("flames_ens", "lstai", "mindglide", "wmhsynthseg", "samseg")   # E1 (one FLAMeS arm)
TOOLS = ("mindglide", "wmhsynthseg", "samseg")
TOOL_LABEL = {"mindglide": 18, "wmhsynthseg": 77, "samseg": 99}
REGION = {1: "PV", 2: "JC", 3: "IT", 4: "DWM"}
SIZE_EDGES = (H.MIN_VOL_MM3, PF.SPHERE_3MM_MM3, 50.0, 200.0, 1000.0, math.inf)
SIZE_LABELS = ("3-14", "14-50", "50-200", "200-1000", ">=1000")
QC_FLAG = "sub-075"
SEED, N_BOOT = 20261108, 10000
EDGE_MM = 3.0
MISSING_FLAG = 5                                                        # > 5 missing controls -> "incomplete"

_APP = None                                                             # one AppDIS per worker process


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def rnd(x, k=4):
    if x is None:
        return None
    if isinstance(x, np.ndarray):
        x = x.tolist()
    if isinstance(x, (list, tuple)):
        return [rnd(v, k) for v in x]
    return round(float(x), k)


def frozen_inputs():
    return json.load(open(INPUTS))


# ------------------------------------------------------------------ arm maps
def arm_paths(arm, case, d):
    if arm == "flames_ens":
        return [os.path.join(d["flames"], f"{case}_f{k}_prob.nii.gz") for k in range(5)]
    if arm == "flames_f0":
        return [os.path.join(d["flames"], f"{case}_f0_prob.nii.gz")]
    if arm == "lstai":
        return [os.path.join(d["lstai"], f"{case}_lstai_prob.nii.gz")] if d.get("lstai") else []
    return [os.path.join(d["tool"], f"{case}_{arm}_seg.nii.gz")] if d.get("tool") else []


def arm_map(arm, case, d, ref_img):
    """Float map whose >= 0.5 voxels are the arm's unreviewed lesion mask, or None if the arm is missing."""
    paths = arm_paths(arm, case, d)
    if not paths or not all(os.path.exists(p) for p in paths):
        return None, {"missing": [p for p in paths if not os.path.exists(p)] or "no directory given"}
    for p in paths:
        img = nib.load(p)
        if tuple(img.shape[:3]) != tuple(ref_img.shape[:3]) or not np.allclose(img.affine, ref_img.affine, atol=1e-4):
            raise ValueError(f"{p}: not on the FLAMeS grid")
    info = {"files": [os.path.basename(p) for p in paths]}
    if arm == "flames_ens":
        folds = [H.load(p) for p in paths]
        return np.mean(folds, axis=0), info                             # paper A: ens = np.mean(folds, axis=0)
    if arm in ("flames_f0", "lstai"):
        m = H.load(paths[0])
        if arm == "lstai":
            info["voxels_equal_0.5"] = int((m == 0.5).sum())
        return m, info
    data = np.asarray(nib.load(paths[0]).dataobj)
    vals = np.unique(data)
    if not set(vals.tolist()) <= {0, 1}:
        raise ValueError(f"{paths[0]}: not binary ({vals[:10]})")
    return data.astype(np.float32), info


def voxel_lists_from_labels(lab, n):
    if n == 0:
        return []
    objs = ndi.find_objects(lab)
    out = []
    for i in range(1, n + 1):
        sl = objs[i - 1]
        idx = np.nonzero(lab[sl] == i)
        out.append(np.ravel_multi_index(tuple(idx[k] + sl[k].start for k in range(3)), lab.shape).astype(np.int64))
    return out


def _init_worker():
    global _APP
    _APP = None


def app_for(ref_img):
    global _APP
    if _APP is None:
        _APP = H.AppDIS(ref_img)
    return _APP


def lesion_rows(vl, vox, edt_flat, bm_flat, cls, zone_flat):
    rows = []
    for v in vl:
        z = zone_flat[v]
        rows.append({"vol_mm3": float(v.size * vox), "min_edt_mm": float(edt_flat[v].min()),
                     "outside_mask_vox": int((~bm_flat[v]).sum()),
                     "region": REGION.get(int(cls.ravel()[v[0]]), "none") if cls is not None else "none",
                     "outside_atlas": bool((z == 0).all())})
    return rows


def one_control(args):
    case, d, arms = args
    t0 = time.time()
    gimg = nib.load(os.path.join(d["flames"], f"{case}_gt.nii.gz"))
    zooms = [float(z) for z in gimg.header.get_zooms()[:3]]
    vox = float(np.prod(zooms))
    if np.asarray(gimg.dataobj).any():
        raise ValueError(f"{case}: lesion mask not empty")
    bm = np.asarray(nib.load(os.path.join(d["brainmask"], f"{case}_brainmask.nii.gz")).dataobj) > 0
    edt = ndi.distance_transform_edt(bm, sampling=zooms)               # paper A S7
    app = app_for(gimg)
    zone_nifti = np.transpose(app.zone, (1, 2, 0)).ravel()
    rec = {"case": case, "brain_ml": float(bm.sum() * vox / 1000.0), "arms": {}}
    unions = {}
    for arm in arms:
        m, info = arm_map(arm, case, d, gimg)
        if m is None:
            rec["arms"][arm] = {"available": False, **info}
            continue
        vl = H.cand_voxels(m, vox)                                      # 18-conn, >= 3 mm^3, map >= 0.5
        dis, cls = app.run(vl)
        rows = lesion_rows(vl, vox, edt.ravel(), bm.ravel(), cls, zone_nifti)
        lab_pf, n_pf, _ = PF.components(m >= H.THRESHOLD, zooms)      # S5: 26-conn, >= 14.137 mm^3
        dis_pf, _ = app.run(voxel_lists_from_labels(lab_pf, n_pf))
        a = {"available": True, **info, "n": len(vl), "lesions": rows, "dis_met_brain": dis["dis_met_brain"],
             "any_dis_region": dis["any_dis_region"], "regions_present": dis["regions"],
             "n_pf": int(n_pf), "dis_met_brain_pf": dis_pf["dis_met_brain"]}
        if info.get("voxels_equal_0.5"):                                # LST-AI '> 0.5' sensitivity, only if needed
            vg = H.cand_voxels(np.where(m == 0.5, 0.0, m), vox)
            a["gt_half"] = {"n": len(vg), "dis_met_brain": app.run(vg)[0]["dis_met_brain"]}
        rec["arms"][arm] = a
        if arm in DISTINCT:
            unions[arm] = (vl, np.concatenate(vl) if vl else np.zeros(0, np.int64))
    # E1: overlap of each tool's false lesions with the other tools' false lesions
    e1 = {}
    for x, (vlx, _) in unions.items():
        others = {y: u for y, (_, u) in unions.items() if y != x}
        tools_hit = []
        for v in vlx:
            hit = [y for y, u in others.items() if u.size and np.isin(v, u, assume_unique=False).any()]
            tools_hit.append(hit)
        e1[x] = {"overlaps": {y: sum(y in h for h in tools_hit) for y in others}, "n": len(vlx),
                 "consensus_ge3": sum(len(h) + 1 >= 3 for h in tools_hit), "tools_available": len(unions)}
        for j, h in enumerate(tools_hit):
            rec["arms"][x]["lesions"][j]["n_tools_overlapping"] = len(h) + 1
    rec["e1"] = e1
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


# ------------------------------------------------------------------ statistics
def binom_cell(x, n):
    c = {"x": int(x), "n": int(n), "rate": rnd(x / n) if n else None, "ci95_exact": rnd(H.clopper_pearson(x, n))}
    if n and x == 0:
        c["one_sided_95_upper"] = rnd(1 - 0.05 ** (1.0 / n))
    return c


def boot_diff(a, b, seed=SEED, n_boot=N_BOOT):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.size == 0:
        return {"diff": None, "ci95_boot": [None, None]}
    rng = np.random.RandomState(seed)
    idx = rng.randint(0, a.size, size=(n_boot, a.size))
    d = a[idx].mean(1) - b[idx].mean(1)
    return {"diff": rnd(a.mean() - b.mean()), "ci95_boot": rnd([np.quantile(d, 0.025), np.quantile(d, 0.975)])}


def dist(v):
    v = np.asarray(v, float)
    if v.size == 0:
        return {"n": 0}
    return {"n": int(v.size), "mean": rnd(v.mean()), "sd": rnd(v.std(ddof=1)) if v.size > 1 else 0.0,
            "median": rnd(np.median(v)), "iqr": rnd(np.quantile(v, [0.25, 0.75])), "max": rnd(v.max())}


def per_arm_vectors(recs, arm):
    """Controls with an output for the arm, in case order: dict of arrays."""
    rows = [(r["case"], r["arms"][arm], r["brain_ml"]) for r in recs if r["arms"].get(arm, {}).get("available")]
    cases = [c for c, _, _ in rows]
    a = [x for _, x, _ in rows]
    vol = np.array([sum(l["vol_mm3"] for l in x["lesions"]) for x in a])
    return {"cases": cases,
            "R": np.array([x["n"] > 0 for x in a], bool), "F": np.array([x["n"] for x in a], float),
            "D": np.array([x["dis_met_brain"] for x in a], bool),
            "anyDIS": np.array([x["any_dis_region"] for x in a], bool),
            "V_ml": vol / 1000.0, "ppm": vol / 1000.0 / np.array([b for _, _, b in rows]) * 1e6 if rows else np.zeros(0),
            "R_pf": np.array([x["n_pf"] > 0 for x in a], bool), "D_pf": np.array([x["dis_met_brain_pf"] for x in a], bool),
            "lesions": [l for x in a for l in x["lesions"]],
            "per_case_lesions": {c: x["lesions"] for c, x in zip(cases, a)}}


def paired(va, vr, key):
    common = [c for c in va["cases"] if c in set(vr["cases"])]
    ia = {c: i for i, c in enumerate(va["cases"])}
    ir = {c: i for i, c in enumerate(vr["cases"])}
    a = np.array([va[key][ia[c]] for c in common])
    b = np.array([vr[key][ir[c]] for c in common])
    return common, a, b


def analyse(recs, arms, paper_a=None):
    vec = {arm: per_arm_vectors(recs, arm) for arm in arms}
    n_all = len(recs)
    out = {"arms": {}, "comparisons": {}, "secondary": {}}
    for arm in arms:
        v = vec[arm]
        n = len(v["cases"])
        e = {"n": n, "missing": n_all - n, "incomplete": (n_all - n) > MISSING_FLAG,
             "a_false_alarm_scans": binom_cell(int(v["R"].sum()), n),
             "b_dis_met_brain": binom_cell(int(v["D"].sum()), n),
             "any_dis_region": binom_cell(int(v["anyDIS"].sum()), n)}
        out["arms"][arm] = e
    # primary paired comparisons, Holm per endpoint over the registered family of 5
    ref = vec.get(REFERENCE)
    for ep, key in (("a", "R"), ("b", "D")):
        fam = {}
        for arm in COMPARED:
            if arm not in vec or ref is None or not vec[arm]["cases"]:
                fam[arm] = {"run": False, "p_two_sided": None}
                continue
            common, a, b = paired(vec[arm], ref, key)
            mc = H.mcnemar_exact(a, b)
            fam[arm] = {"run": True, "n_paired": len(common), "arm_x": int(a.sum()), "reference_x": int(b.sum()),
                        **mc, "rate_diff": boot_diff(a, b)}
        adj = H.holm([fam[x]["p_two_sided"] for x in COMPARED])
        for x, p in zip(COMPARED, adj):
            fam[x]["p_holm_family"] = rnd(p, 6)
            fam[x]["established_holm_lt_0.05"] = bool(fam[x]["run"] and p < 0.05)
        out["comparisons"][ep] = fam
    allp = [out["comparisons"][ep][x]["p_two_sided"] for ep in ("a", "b") for x in COMPARED]
    adj10 = H.holm(allp)
    k = 0
    for ep in ("a", "b"):
        for x in COMPARED:
            out["comparisons"][ep][x]["p_holm_all10"] = rnd(adj10[k], 6)
            k += 1
    # secondary
    S = out["secondary"]
    for arm in arms:
        v = vec[arm]
        les = v["lesions"]
        F = v["F"]
        s1 = {"false_lesions_per_scan": dist(F), "per_100_scans": rnd(100.0 * F.sum() / max(1, F.size), 1),
              "distribution_0_1_2_ge3": [int((F == 0).sum()), int((F == 1).sum()), int((F == 2).sum()), int((F >= 3).sum())],
              "total": int(F.sum())}
        if ref is not None and arm != REFERENCE and v["cases"]:
            _, a, b = paired(v, ref, "F")
            s1["paired_mean_diff_vs_ens"] = boot_diff(a, b)
        s2 = {"false_volume_ml": dist(v["V_ml"]), "ppm_of_brain_mask": dist(v["ppm"]),
              "controls_gt_0.1_ml": int((v["V_ml"] > 0.1).sum())}
        regs = [l["region"] for l in les]
        s3 = {"lesions_by_region": {r: regs.count(r) for r in ("PV", "JC", "IT", "DWM", "none")},
              "outside_atlas_coverage": int(sum(l["outside_atlas"] for l in les)),
              "controls_with_region": {r: int(sum(any(l["region"] == r for l in ls) for ls in v["per_case_lesions"].values()))
                                       for r in ("PV", "JC", "IT", "DWM")},
              "controls_any_dis_region": int(v["anyDIS"].sum())}
        vols = np.array([l["vol_mm3"] for l in les])
        bins = np.digitize(vols, SIZE_EDGES[1:-1], right=False) if vols.size else np.zeros(0, int)
        s4 = {lab: int((bins == i).sum()) for i, lab in enumerate(SIZE_LABELS)}
        s4_per_scan = {lab: rnd(s4[lab] / max(1, len(v["cases"]))) for lab in SIZE_LABELS}
        n = len(v["cases"])
        s5 = {"a_paper_f_rule": binom_cell(int(v["R_pf"].sum()), n), "b_paper_f_rule": binom_cell(int(v["D_pf"].sum()), n)}
        keep = [i for i, c in enumerate(v["cases"]) if c != QC_FLAG]
        s6 = {"a_without_sub-075": binom_cell(int(v["R"][keep].sum()), len(keep)),
              "b_without_sub-075": binom_cell(int(v["D"][keep].sum()), len(keep))}
        e = np.array([l["min_edt_mm"] for l in les])
        s7 = {"lesions": int(e.size), "within_3mm_of_brainmask_edge": int((e <= EDGE_MM).sum()),
              "share_within_3mm": rnd((e <= EDGE_MM).mean()) if e.size else None,
              "min_edt_mm_quantiles_10_50_90": rnd(np.quantile(e, [0.1, 0.5, 0.9]), 2) if e.size else None,
              "touching_outside_mask": int(sum(l["outside_mask_vox"] > 0 for l in les))}
        miss = len(recs) - n
        s8 = None
        if miss:
            s8 = {"missing": miss,
                  "a_worst_case": binom_cell(int(v["R"].sum()) + miss, len(recs)),
                  "a_best_case": binom_cell(int(v["R"].sum()), len(recs)),
                  "b_worst_case": binom_cell(int(v["D"].sum()) + miss, len(recs)),
                  "b_best_case": binom_cell(int(v["D"].sum()), len(recs))}
        S[arm] = {"S1": s1, "S2": s2, "S3": s3, "S4": {"lesions": s4, "per_scan": s4_per_scan}, "S5": s5, "S6": s6,
                  "S7": s7, "S8_missing": s8}
    # LST-AI '>= 0.5' vs '> 0.5'
    if "lstai" in arms:
        eq = [r["arms"]["lstai"].get("voxels_equal_0.5", 0) for r in recs if r["arms"]["lstai"].get("available")]
        S["lstai_threshold_check"] = {"voxels_exactly_0.5_total": int(sum(eq)), "controls_with_any": int(sum(e > 0 for e in eq))}
        gh = [r["arms"]["lstai"]["gt_half"] for r in recs if "gt_half" in r["arms"]["lstai"]]
        if gh:
            S["lstai_threshold_check"]["gt_0.5_variant_controls_changed"] = len(gh)
    # E1 (exploratory)
    e1 = {}
    for x in DISTINCT:
        rows = [r["e1"][x] for r in recs if x in r.get("e1", {})]
        if not rows:
            continue
        tot = sum(r["n"] for r in rows)
        ov = {}
        for y in DISTINCT:
            if y != x and all(y in r["overlaps"] for r in rows):
                k = sum(r["overlaps"][y] for r in rows)
                ov[y] = {"lesions_overlapping": k, "share": rnd(k / tot) if tot else None}
        e1[x] = {"false_lesions": tot, "overlap_with": ov, "consensus_ge3_tools": sum(r["consensus_ge3"] for r in rows),
                 "controls_with_consensus_ge3": sum(r["consensus_ge3"] > 0 for r in rows),
                 "tools_available": max(r["tools_available"] for r in rows)}
    S["E1_exploratory_cross_tool"] = e1
    out["gate_G1_paper_a"] = gate_g1(recs, paper_a) if paper_a else None
    return out, vec


def gate_g1(recs, rec_a):
    """FLAMeS-ens / fold-0 numbers must equal the paper A record exactly (PREREG section 7)."""
    got, want, ok = {}, {}, True
    have = {arm: all(r["arms"].get(arm, {}).get("available") for r in recs) for arm in ("flames_ens", "flames_f0")}
    if not all(have.values()) or len(recs) != 100:
        return {"run": False, "reason": "needs both FLAMeS arms on all 100 controls"}
    pa = {p["case"]: p for p in rec_a["per_control"]}
    for arm, short in (("flames_ens", "ens"), ("flames_f0", "f0")):
        n = [r["arms"][arm]["n"] for r in recs]
        got[arm] = {"scans_with_any_candidate": int(sum(x > 0 for x in n)), "candidates_total": int(sum(n)),
                    "dis_met_brain": int(sum(r["arms"][arm]["dis_met_brain"] for r in recs)),
                    "any_dis_region": int(sum(r["arms"][arm]["any_dis_region"] for r in recs))}
        ra = rec_a["raw_candidates"][short]
        da = rec_a["app_dis"]["results"][f"raw {short}|all100"]
        want[arm] = {"scans_with_any_candidate": ra["scans_with_any_candidate"], "candidates_total": ra["candidates_total"],
                     "dis_met_brain": da["dis_met_brain"], "any_dis_region": da["any_dis_region"]}
        per_case = sum(r["arms"][arm]["n"] == pa[r["case"]][f"{short}_candidates"] for r in recs)
        got[arm]["per_control_counts_equal"] = int(per_case)
        want[arm]["per_control_counts_equal"] = 100
        dis_cases = sorted(r["case"] for r in recs if r["arms"][arm]["dis_met_brain"])
        got[arm]["dis_cases_equal"] = dis_cases == sorted(da["cases_dis_met"])
        want[arm]["dis_cases_equal"] = True
    regs = [l["region"] for r in recs for l in r["arms"]["flames_ens"]["lesions"]]
    got["regions_raw_ens"] = {k: regs.count(k) for k in ("PV", "JC", "IT", "DWM", "none")}
    want["regions_raw_ens"] = rec_a["location"]["raw ens"]["regions"]
    ok = got == want
    return {"run": True, "passed": bool(ok), "got": got, "expected_paper_a": want}


# ------------------------------------------------------------------ outputs
def write_tables(res, out_dir, arms, interim):
    L = [f"# Paper 1 healthy controls — {'INTERIM (only ' + ', '.join(arms) + ')' if interim else 'final'} results", "",
         "Pre-registration: `docs/research/paper-1/PREREG-healthy-controls.md` (commit 1e62f5c). "
         "Generated by `research/paper_1/evaluate_controls.py`; numbers from `summary.json`.", "",
         "## Primary endpoints (exact 95 % Clopper–Pearson)", "",
         "| Arm | n | (a) controls with ≥ 1 false lesion | (b) app DIS rule met (`dis_met_brain`) | ≥ 1 lesion in a DIS region |",
         "|---|---|---|---|---|"]

    def fmt(c):
        if not c["n"]:
            return "no output"
        lo, hi = c["ci95_exact"]
        return f"{c['x']}/{c['n']} ({100 * c['rate']:.0f} %; {100 * lo:.1f}–{100 * hi:.1f})"
    for arm in arms:
        e = res["arms"][arm]
        L.append(f"| {arm}{' (incomplete)' if e['incomplete'] else ''} | {e['n']} | {fmt(e['a_false_alarm_scans'])} | "
                 f"{fmt(e['b_dis_met_brain'])} | {fmt(e['any_dis_region'])} |")
    L += ["", "## Paired comparisons with the FLAMeS 5-fold mean (exact McNemar; Holm over the registered family of 5)", "",
          "| Endpoint | Arm | n paired | arm / ref | arm only / ref only | Δ rate (95 % bootstrap) | p | Holm p (family) | Holm p (all 10) |",
          "|---|---|---|---|---|---|---|---|---|"]
    for ep in ("a", "b"):
        for x in COMPARED:
            c = res["comparisons"][ep][x]
            if not c["run"]:
                L.append(f"| {ep} | {x} | — | not run | — | — | (1) | {c['p_holm_family']} | {c['p_holm_all10']} |")
                continue
            d = c["rate_diff"]
            L.append(f"| {ep} | {x} | {c['n_paired']} | {c['arm_x']} / {c['reference_x']} | {c['arm_only']} / {c['reference_only']} | "
                     f"{d['diff']:+.2f} ({d['ci95_boot'][0]:+.2f}, {d['ci95_boot'][1]:+.2f}) | {c['p_two_sided']:.4g} | "
                     f"{c['p_holm_family']:.4g} | {c['p_holm_all10']:.4g} |")
    L += ["", "## Secondary (descriptive)", "",
          "| Arm | false lesions / scan, mean (median, max) | distribution 0/1/2/≥3 | false volume mL, median (IQR) | "
          "PV / JC / IT / DWM (outside atlas) | size 3–14 / 14–50 / 50–200 / 200–1000 / ≥1000 mm³ | ≤ 3 mm from mask edge | "
          "(a), (b) paper F rule | (a), (b) without sub-075 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for arm in arms:
        s = res["secondary"][arm]
        f = s["S1"]["false_lesions_per_scan"]
        v = s["S2"]["false_volume_ml"]
        r = s["S3"]["lesions_by_region"]
        z = s["S4"]["lesions"]
        if f.get("n", 0) == 0:
            L.append(f"| {arm} | no output | | | | | | | |")
            continue
        L.append(f"| {arm} | {f['mean']:.2f} ({f['median']:.0f}, {f['max']:.0f}) | {'/'.join(map(str, s['S1']['distribution_0_1_2_ge3']))} | "
                 f"{v['median']:.3f} ({v['iqr'][0]:.3f}–{v['iqr'][1]:.3f}) | {r['PV']} / {r['JC']} / {r['IT']} / {r['DWM']} "
                 f"({s['S3']['outside_atlas_coverage']}) | {' / '.join(str(z[k]) for k in SIZE_LABELS)} | "
                 f"{s['S7']['within_3mm_of_brainmask_edge']}/{s['S7']['lesions']} | "
                 f"{s['S5']['a_paper_f_rule']['x']}, {s['S5']['b_paper_f_rule']['x']} | "
                 f"{s['S6']['a_without_sub-075']['x']}/{s['S6']['a_without_sub-075']['n']}, {s['S6']['b_without_sub-075']['x']} |")
    g = res.get("gate_G1_paper_a")
    L += ["", f"Gate G1 (FLAMeS reproduces paper A exactly): **{'PASS' if g and g.get('passed') else ('not run' if not g or not g.get('run') else 'FAIL')}**."]
    if "lstai_threshold_check" in res["secondary"]:
        L.append(f"LST-AI voxels exactly at 0.5: {res['secondary']['lstai_threshold_check']['voxels_exactly_0.5_total']}.")
    open(os.path.join(out_dir, "tables.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")


def write_csvs(recs, arms, out_dir):
    with open(os.path.join(out_dir, "per_control.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case", "arm", "available", "n_false_lesions", "any_false_lesion", "dis_met_brain", "any_dis_region",
                    "false_volume_mm3", "n_paper_f_rule", "dis_met_brain_paper_f_rule", "brain_ml"])
        for r in recs:
            for arm in arms:
                a = r["arms"][arm]
                if not a.get("available"):
                    w.writerow([r["case"], arm, 0, "", "", "", "", "", "", "", rnd(r["brain_ml"], 1)])
                    continue
                w.writerow([r["case"], arm, 1, a["n"], int(a["n"] > 0), int(a["dis_met_brain"]), int(a["any_dis_region"]),
                            rnd(sum(l["vol_mm3"] for l in a["lesions"]), 3), a["n_pf"], int(a["dis_met_brain_pf"]),
                            rnd(r["brain_ml"], 1)])
    with open(os.path.join(out_dir, "lesions.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case", "arm", "lesion", "vol_mm3", "size_bin", "region", "outside_atlas", "min_edt_mm",
                    "outside_mask_vox", "n_tools_overlapping"])
        for r in recs:
            for arm in arms:
                a = r["arms"][arm]
                for j, l in enumerate(a.get("lesions", []) if a.get("available") else []):
                    b = SIZE_LABELS[int(np.digitize([l["vol_mm3"]], SIZE_EDGES[1:-1])[0])]
                    w.writerow([r["case"], arm, j + 1, rnd(l["vol_mm3"], 3), b, l["region"], int(l["outside_atlas"]),
                                rnd(l["min_edt_mm"], 2), l["outside_mask_vox"], l.get("n_tools_overlapping", "")])


def git_commit():
    r = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True)
    s = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "--", "research/paper_1"], capture_output=True, text=True)
    return {"commit": r.stdout.strip() or None, "paper_1_code_dirty": bool(s.stdout.strip())}


def runtime_table(manifest_dir, cases):
    """S9: seconds and peak memory per tool from the toolbench and LST-AI manifests (control records only)."""
    if not manifest_dir or not os.path.isdir(manifest_dir):
        return None
    out = {}
    for p in sorted(glob.glob(os.path.join(manifest_dir, "*.json"))):
        try:
            m = json.load(open(p))
        except (OSError, ValueError):
            continue
        for c in m.get("cases", []):
            if c.get("case") not in cases:
                continue
            tool = c.get("tool") or ("lstai" if "seconds_lstai" in c else None)
            if tool is None:
                continue
            out.setdefault(tool, {"seconds": [], "peak_mem_gb": [], "runs": set(), "machines": set()})
            out[tool]["seconds"].append(c.get("seconds_tool") or c.get("seconds_lstai") or c.get("seconds"))
            if c.get("peak_mem_used_gb") is not None:
                out[tool]["peak_mem_gb"].append(c["peak_mem_used_gb"])
            out[tool]["runs"].add(m.get("run_id"))
    return {t: {"n": len(v["seconds"]), "seconds": dist([s for s in v["seconds"] if s is not None]),
                "peak_mem_gb_max": rnd(max(v["peak_mem_gb"]), 2) if v["peak_mem_gb"] else None,
                "runs": sorted(x for x in v["runs"] if x)} for t, v in out.items()}


def cmd_run(a):
    t0 = time.time()
    inputs = frozen_inputs()
    cases = sorted(inputs) if not a.cases else a.cases
    d = {"flames": a.flames_dir, "lstai": a.lstai_dir, "tool": a.tool_dir, "brainmask": a.brainmask_dir}
    arms = list(a.arms)
    for x in arms:
        if x not in ARMS:
            raise SystemExit(f"unknown arm {x}")
    if REFERENCE not in arms:
        raise SystemExit("the reference arm flames_ens is required")
    for c in cases:
        g = nib.load(os.path.join(a.flames_dir, f"{c}_gt.nii.gz"))
        f = inputs[c]
        if list(g.shape[:3]) != f["shape"] or not np.allclose(g.affine, np.asarray(f["affine"]), atol=1e-4):
            raise SystemExit(f"{c}: lesion-mask grid differs from the frozen control grid")
    with Pool(a.workers, initializer=_init_worker) as pool:
        recs = pool.map(one_control, [(c, d, arms) for c in cases], chunksize=1)
    paper_a = json.load(open(PAPER_A_RECORD, encoding="utf-8")) if os.path.exists(PAPER_A_RECORD) else None
    res, _ = analyse(recs, arms, paper_a)
    os.makedirs(a.out, exist_ok=True)
    files = sorted({p for c in cases for arm in arms for p in arm_paths(arm, c, d) if os.path.exists(p)} |
                   {os.path.join(a.flames_dir, f"{c}_gt.nii.gz") for c in cases} |
                   {os.path.join(a.brainmask_dir, f"{c}_brainmask.nii.gz") for c in cases})
    hashes = {os.path.basename(p): sha256(p) for p in files}
    digest = hashlib.sha256("".join(f"{k} {v}\n" for k, v in sorted(hashes.items())).encode()).hexdigest()
    info = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "interim": bool(a.interim), "arms": arms, "n_controls": len(cases),
            "prereg": "docs/research/paper-1/PREREG-healthy-controls.md (commit 1e62f5c)", "code": git_commit(),
            "code_sha256": {f: sha256(os.path.join(HERE, f)) for f in ("evaluate_controls.py", "hc_core.py", "controls_inputs.json")},
            "paper_f_metrics_sha256": sha256(os.path.join(ROOT, "research", "paper_f", "metrics.py")),
            "app_files_sha256": {f: sha256(os.path.join(ROOT, "backend", "app", "services", f))
                                 for f in ("ms_region_classifier.py", "lesion_analysis_service.py", "lesion_metrics.py")},
            "atlas_sha256": sha256(os.path.join(ROOT, "backend", "data", "msmask", "sub-mni152_space-mni_msmask.nii.gz")),
            "inputs": {"files": len(hashes), "digest_sha256_of_sorted_list": digest},
            "versions": {"python": sys.version.split()[0], "executable": sys.executable, "numpy": np.__version__,
                         "nibabel": nib.__version__, "scipy": __import__("scipy").__version__},
            "seed": SEED, "n_boot": N_BOOT, "runtime_s": round(time.time() - t0, 1)}
    res["run_info"] = info
    res["S9_runtime"] = runtime_table(a.manifests, set(cases))
    json.dump(res, open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8"), indent=1,
              default=lambda o: o.item() if hasattr(o, "item") else (sorted(o) if isinstance(o, set) else str(o)))
    json.dump({"info": info, "input_sha256": hashes}, open(os.path.join(a.out, "run_info.json"), "w"), indent=1)
    write_csvs(recs, arms, a.out)
    write_tables(res, a.out, arms, a.interim)
    for arm in arms:
        e = res["arms"][arm]
        print(f"{arm}: (a) {e['a_false_alarm_scans']['x']}/{e['n']} {e['a_false_alarm_scans']['ci95_exact']}  "
              f"(b) {e['b_dis_met_brain']['x']}/{e['n']} {e['b_dis_met_brain']['ci95_exact']}", flush=True)
    g = res["gate_G1_paper_a"]
    print("G1 paper A reproduction:", "PASS" if g and g.get("passed") else g, flush=True)
    print(f"wrote {a.out} in {info['runtime_s']} s", flush=True)
    return 0


# ------------------------------------------------------------------ G3 structural check
def cmd_check(a):
    inputs = frozen_inputs()
    recs = {}
    for p in sorted(glob.glob(os.path.join(a.manifests, "*.json"))) if a.manifests else []:
        try:
            m = json.load(open(p))
        except (OSError, ValueError):
            continue
        for c in m.get("cases", []):
            if c.get("case") in inputs and "seg_sha256" in c:
                recs[(c["case"], c["tool"])] = c
    bad = 0
    for case in a.cases:
        f = inputs[case]
        for tool in a.tools:
            p = os.path.join(a.tool_dir, f"{case}_{tool}_seg.nii.gz")
            why = []
            if not os.path.exists(p):
                why.append("missing")
            else:
                img = nib.load(p)
                data = np.asarray(img.dataobj)
                if list(img.shape[:3]) != f["shape"] or not np.allclose(img.affine, np.asarray(f["affine"]), atol=1e-4):
                    why.append("not on the FLAMeS grid")
                if img.get_data_dtype() != np.uint8:
                    why.append(f"dtype {img.get_data_dtype()}")
                if not set(np.unique(data).tolist()) <= {0, 1}:
                    why.append("not binary")
                r = recs.get((case, tool))
                if r is None:
                    why.append("no manifest record")
                else:
                    if r["seg_sha256"] != sha256(p):
                        why.append("SHA-256 differs from the manifest")
                    if int(data.sum()) != int(r.get("lesion_voxels", -1)):
                        why.append("voxel count differs from the manifest")
                    labels = r.get("native_seg", {}).get("labels_found")
                    if not labels:
                        why.append("no native label list recorded")
                    tr = r.get("seg_transform", {}).get("kind")
                    why += [] if tr else ["no grid transform recorded"]
            ok = not why
            bad += not ok
            extra = "" if ok else ": " + "; ".join(why)
            tr = recs.get((case, tool), {}).get("seg_transform", {}).get("kind", "?")
            print(f"{'PASS' if ok else 'FAIL'} {case} {tool} (transform {tr}){extra}", flush=True)
    print(f"G3: {len(a.cases) * len(a.tools) - bad} PASS, {bad} FAIL", flush=True)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--flames-dir", required=True)
    r.add_argument("--lstai-dir", default="")
    r.add_argument("--tool-dir", default="")
    r.add_argument("--brainmask-dir", required=True)
    r.add_argument("--manifests", default="")
    r.add_argument("--out", required=True)
    r.add_argument("--arms", nargs="+", default=list(ARMS))
    r.add_argument("--cases", nargs="*", default=[])
    r.add_argument("--workers", type=int, default=3)
    r.add_argument("--interim", action="store_true", help="label the outputs as interim (not all arms)")
    c = sub.add_parser("check")
    c.add_argument("--tool-dir", required=True)
    c.add_argument("--manifests", required=True)
    c.add_argument("--tools", nargs="+", default=list(TOOLS))
    c.add_argument("--cases", nargs="+", required=True)
    a = ap.parse_args()
    sys.exit(cmd_run(a) if a.cmd == "run" else cmd_check(a))


if __name__ == "__main__":
    main()
