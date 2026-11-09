#!/usr/bin/env python3
"""Paper 1 addendum — the frozen final evaluation (docs/research/paper-1/PREREG-mimics-thickness.md sections 4-8,
amendment 1 section 15). Committed before it is run on any new output; run ONCE, on the evaluation VM
(research/cloud/vm_mimics_eval.sh, started by research/paper_1/mimics/run_final_mimics.sh), with no cloud
credentials in the Python environment. The app's region / DIS functions are imported read-only (hc_core.AppDIS).

Subcommands (in this order; each writes into --out):
  register  A and B only: greedy affine (12 dof, NMI) of each HD-BET FLAIR to the MSMask atlas T1 brain; the HD-BET
            mask warped the same way must reach Dice >= 0.85 with the atlas brain (gate GR). Prints GR counts only.
  check     G3: every expected output exists, on its input grid, binary uint8 where required, SHA-256 = manifest.
  run       every registered quantity -> summary.json, tables.md, per_unit.csv, lesions.csv, run_info.json.

Definitions (unchanged from the healthy arm and paper F):
  arm map     flames_ens = mean of the 5 fold maps, flames_f0 = fold 0, lstai = ensemble map, tools = hard label 0/1
  DIS path    map >= 0.5 -> 18-connected components >= 3 mm^3 (hc_core.cand_voxels) -> hc_core.AppDIS (app code);
              A and B: the binary mask is first warped to the atlas grid (linear, >= 0.5)
  accuracy    map > 0.5 vs the expert mask with research/paper_f/metrics.lesion_metrics (26-conn, >= 14.137 mm^3)
"""
import argparse
import csv
import glob
import gzip
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "research", "paper_1"))
sys.path.insert(0, os.path.join(ROOT, "research", "paper_f"))
import hc_core as H                     # noqa: E402  (paper A definitions + AppDIS, healthy arm)
import metrics as PF                    # noqa: E402  (paper F lesion-wise metrics and bootstrap)
import thick_slice as TS                # noqa: E402
import simulate_thick as ST             # noqa: E402

SETS = os.path.join(HERE, "analysis_sets.json")
ARMS = ("flames_ens", "flames_f0", "lstai", "mindglide", "wmhsynthseg", "samseg")
REF = "flames_ens"
OTHERS = ARMS[1:]
TOOLS = ("mindglide", "wmhsynthseg", "samseg")
REGION = {1: "PV", 2: "JC", 3: "IT", 4: "DWM"}
DIS_REGIONS = ("PV", "JC", "IT")
SEED, N_BOOT = 20261109, 10000
T_GRID = tuple(round(0.50 + 0.05 * i, 2) for i in range(10))
M_GRID = (3.0, PF.SPHERE_3MM_MM3, 25.0, 50.0, 100.0)
GR_MIN_DICE = 0.85
GREEDY_AFFINE = "-d 3 -a -dof 12 -m NMI -ia-image-centers -n 100x50x10 -i {fixed} {moving} -o {mat} -threads {t}"
GREEDY_RESLICE = "-d 3 -rf {fixed} -ri LINEAR -rm {moving} {out} -r {mat} -threads {t}"
PAPER_D_REF_MET = 118                                           # paper D results v1: 0.9516 x 124 scans
_CACHE = {}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def rnd(x, k=4):
    if x is None:
        return None
    if isinstance(x, (list, tuple, np.ndarray)):
        return [rnd(v, k) for v in x]
    return round(float(x), k)


# ====================================================================== units
def units(sets, d):
    """Every evaluated input: id, block, base case, thickness, DIS grid, sources of the arm maps, expert."""
    out = []
    A, B = sets["A_wmh2017"], sets["B1_sample"]["ids"]
    if os.path.exists(os.path.join(d["out"], "variant.json")):
        var = json.load(open(os.path.join(d["out"], "variant.json")))
    else:
        var = {}
    if var.get("dlbs_n") == 75:
        B = sets["B1_sample"]["reduced_75"]["ids"]
    thick = tuple(var.get("c1_thick", (3, 5, 7)))
    with_c2 = var.get("with_c2", True)
    sub = set(sets["C1_samseg_subset"]["ids"])
    for i, v in sorted(A.items()):
        arms = [a for a in ARMS if a != "wmhsynthseg" or v["split"] == "test"]
        out.append({"id": i, "block": "A", "base": i, "T": 3.0, "warp": True, "src": "mimics", "arms": arms,
                    "site": v["site"], "split": v["split"], "wmh": v["wmh"], "observers": v["extra_observers"]})
    for i in B:
        v = sets["B_dlbs"][i]
        out.append({"id": i, "block": "B", "base": i, "T": 2.5, "warp": True, "src": "mimics", "arms": list(ARMS),
                    "age": v["age_mri_w1"], "cohort": v["recruitment_cohort"]})
    for c, v in sorted(sets["C1_ms_iso"].items()):
        clean = not v["flames_contaminated"]
        base_arms = [a for a in ARMS if (clean or not a.startswith("flames")) and not (a == "lstai" and v["lstai_missing"])]
        out.append({"id": c, "block": "C1", "base": c, "T": 1.0, "warp": False, "src": "pf",
                    "arms": [a for a in base_arms if a != "samseg"] + (["samseg"] if c in sub else []), "clean": clean,
                    "samseg_id": f"{c}_th1"})
        for t in thick:
            out.append({"id": f"{c}_th{t}", "block": "C1", "base": c, "T": float(t), "warp": False, "src": "mimics",
                        "arms": [a for a in base_arms if a != "samseg"] + (["samseg"] if c in sub else []), "clean": clean})
    for s in sets["C2_sibbms"]:
        out.append({"id": s, "block": "C2", "base": s, "T": 1.0, "warp": False, "src": "pf", "arms": list(ARMS)})
        if with_c2:
            out.append({"id": f"{s}_th7", "block": "C2", "base": s, "T": 7.0, "warp": False, "src": "mimics",
                        "arms": list(ARMS)})
    return out


def arm_paths(u, arm, d):
    src = d["pf"] if u["src"] == "pf" else d["mimics"]
    iid = u["id"]
    if arm == "flames_ens":
        return [os.path.join(src, "flames", f"{iid}_f{k}_prob.nii.gz") for k in range(5)]
    if arm == "flames_f0":
        return [os.path.join(src, "flames", f"{iid}_f0_prob.nii.gz")]
    if arm == "lstai":
        return [os.path.join(src, "lstai", f"{iid}_lstai_prob.nii.gz")]
    if arm == "samseg" and u["src"] == "pf" and u["block"] == "C1":
        return [os.path.join(d["mimics"], "toolbench", f"{u['samseg_id']}_samseg_seg.nii.gz")]
    return [os.path.join(src, "toolbench", f"{iid}_{arm}_seg.nii.gz")]


def arm_map(u, arm, d, ref_img):
    """Float map (exactly as the healthy arm / paper F read it), or None if missing."""
    paths = arm_paths(u, arm, d)
    if not all(os.path.exists(p) for p in paths):
        return None
    for p in paths:
        img = nib.load(p)
        if tuple(img.shape[:3]) != tuple(ref_img.shape[:3]) or not np.allclose(img.affine, ref_img.affine, atol=1e-3):
            raise ValueError(f"{p}: not on the input grid")
    if arm == "flames_ens":
        return np.mean([H.load(p) for p in paths], axis=0)
    if arm in ("flames_f0", "lstai"):
        return H.load(paths[0])
    data = np.asarray(nib.load(paths[0]).dataobj)
    if not set(np.unique(data).tolist()) <= {0, 1}:
        raise ValueError(f"{paths[0]}: not binary")
    return data.astype(np.float32)


def ref_image(u, d):
    if u["block"] == "C1":
        return nib.load(os.path.join(d["pf"], "flames", f"{u['base']}_gt.nii.gz"))
    if u["block"] == "C2":
        return nib.load(os.path.join(d["pf"], "flames", f"{u['base']}_gt.nii.gz"))
    return nib.load(os.path.join(d["mimics"], "inputs", f"{u['base']}_FLAIR.nii.gz"))


# ====================================================================== registration (A, B)
def greedy(cmd):
    """Run one greedy command (picsl_greedy 1.4.0.3). On the evaluation VM greedy lives in its own venv
    (GREEDY_PYTHON), so the analysis environment keeps the healthy arm's pinned numpy/scipy/nibabel."""
    gp = os.environ.get("GREEDY_PYTHON")
    if gp:
        r = subprocess.run([gp, "-c", "import sys; from picsl_greedy import Greedy3D; Greedy3D().execute(sys.argv[1])", cmd],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"greedy failed: {cmd[:200]} :: {r.stderr[-800:]}")
        return
    from picsl_greedy import Greedy3D
    Greedy3D().execute(cmd)


def warp_float(arr, ref_img, base, d, tag):
    """Warp a native float/binary array to the atlas grid (greedy, linear); returns float32 on the atlas grid."""
    w = os.path.join(d["out"], "tmp_warp")
    os.makedirs(w, exist_ok=True)
    src = os.path.join(w, f"{base}_{tag}_{os.getpid()}.nii.gz")
    dst = src.replace(".nii.gz", "_w.nii.gz")
    nib.save(nib.Nifti1Image(np.asarray(arr, np.float32), ref_img.affine), src)
    greedy(GREEDY_RESLICE.format(fixed=d["atlas_t1"], moving=src, out=dst, mat=os.path.join(d["reg"], f"{base}.mat"), t=1))
    out = np.asarray(nib.load(dst).get_fdata(dtype=np.float32))
    os.remove(src)
    os.remove(dst)
    return out


def cmd_register(a, d, sets):
    os.makedirs(d["reg"], exist_ok=True)
    atlas = nib.load(d["msmask"])
    brain = np.asarray(atlas.dataobj) > 0
    t1 = nib.load(d["atlas_t1_raw"])
    if sha256(d["atlas_t1_raw"]) != "d4104bbda56ad46c898135c805b394856993aea239b942f3a705136cd2b4476b":
        raise SystemExit("atlas T1 differs from the LST-AI v1.1.0 file used by paper D")
    nib.save(nib.Nifti1Image(np.where(brain, np.asarray(t1.get_fdata(dtype=np.float32)), 0.0), t1.affine), d["atlas_t1"])
    ids = [u["base"] for u in units(sets, d) if u["warp"]]
    rec = {}
    for i in ids:
        mat = os.path.join(d["reg"], f"{i}.mat")
        fl = os.path.join(d["mimics"], "inputs", f"{i}_FLAIR.nii.gz")
        t0 = time.time()
        if not os.path.exists(mat):
            greedy(GREEDY_AFFINE.format(fixed=d["atlas_t1"], moving=fl, mat=mat, t=a.threads))
        ref = nib.load(fl)
        m = np.asarray(nib.load(os.path.join(d["mimics"], "inputs", f"{i}_brainmask.nii.gz")).dataobj) > 0
        wm = warp_float(m, ref, i, d, "brainmask") >= 0.5
        dice = float(2 * (wm & brain).sum() / max(1, wm.sum() + brain.sum()))
        rec[i] = {"dice_brain": round(dice, 4), "pass": dice >= GR_MIN_DICE, "seconds": round(time.time() - t0, 1),
                  "mat_sha256": sha256(mat)}
    json.dump({"rule": f"Dice(warped HD-BET brain, MSMask > 0) >= {GR_MIN_DICE}", "command": GREEDY_AFFINE,
               "records": rec}, open(os.path.join(d["out"], "registration.json"), "w"), indent=1)
    by = {}
    for u in units(sets, d):
        if u["warp"]:
            by.setdefault(u["block"], []).append(rec[u["base"]]["pass"])
    for b, v in by.items():
        print(f"GR {b}: {sum(v)}/{len(v)} pass", flush=True)
    stop = {b: (len(v) - sum(v)) / len(v) > 0.10 for b, v in by.items()}
    print("GR stop rule (> 10 % fail):", stop, flush=True)
    return 0


# ====================================================================== per-unit evaluation
def app_for(img):
    key = (tuple(img.shape[:3]), np.round(img.affine, 4).tobytes())
    if key not in _CACHE:
        _CACHE[key] = H.AppDIS(img)
    return _CACHE[key]


def lesion_set(mask_float, img):
    vox = float(np.prod(img.header.get_zooms()[:3]))
    vl = H.cand_voxels(mask_float, vox)
    return vl, vox


def dis_from_lesions(lesions, min_vol, pv_min=1):
    cnt = {r: 0 for r in DIS_REGIONS}
    for vol, reg in lesions:
        if vol >= min_vol - 1e-9 and reg in cnt:
            cnt[reg] += 1
    met = sum(1 for r in DIS_REGIONS if cnt[r] >= (pv_min if r == "PV" else 1))
    return met >= 2


def dis_block(mask_float, img, app):
    """App DIS of one binary mask on img's grid: dict + per-lesion (volume, region)."""
    vl, vox = lesion_set(mask_float, img)
    dis, cls = app.run(vl)
    les = [(float(v.size * vox), REGION.get(int(cls.ravel()[v[0]]), "none") if cls is not None else "none") for v in vl]
    out = {"n": len(vl), "dis": bool(dis["dis_met_brain"]), "any_dis_region": bool(dis["any_dis_region"]),
           "dis_pv3": dis_from_lesions(les, 3.0, pv_min=3), "recount_equal": dis_from_lesions(les, 3.0) == bool(dis["dis_met_brain"]),
           "regions": {r: sum(1 for _, g in les if g == r) for r in ("PV", "JC", "IT", "DWM", "none")},
           "vol_mm3": float(sum(v for v, _ in les))}
    return out, les


def grid_d(m, u, img, app, d, ref_acc=None, warp_ref=None):
    """Part D: for each threshold t one app classification; DIS for every minimum size from the per-lesion regions
    (falls back to one app call per size when the recount disagrees with the app at the default)."""
    out = {}
    for t in T_GRID:
        mt = (m >= t).astype(np.float32)
        if u["warp"]:
            mt = (warp_float(mt, warp_ref, u["base"], d, f"d{int(t * 100)}") >= 0.5).astype(np.float32)
        vl, vox = lesion_set(mt, img)
        dis, cls = app.run(vl)
        les = [(float(v.size * vox), REGION.get(int(cls.ravel()[v[0]]), "none") if cls is not None else "none") for v in vl]
        ok = dis_from_lesions(les, 3.0) == bool(dis["dis_met_brain"])
        row = {}
        for mm in M_GRID:
            if ok:
                row[f"{mm:.3f}"] = dis_from_lesions(les, mm)
            else:
                keep = [v for v in vl if v.size * vox >= mm - 1e-9]
                row[f"{mm:.3f}"] = bool(app.run(keep)[0]["dis_met_brain"])
        rec = {"dis": row, "recount_equal": ok}
        if ref_acc is not None:                                  # MS: lesion-wise recall at (t, m), native grid
            lr, n_r, _ = PF.components(ref_acc, img.header.get_zooms()[:3])
            rec["recall"] = {}
            for mm in M_GRID:
                lp, n_p, _ = PF.components(m >= t, img.header.get_zooms()[:3], min_mm3=mm, connectivity=18)
                hit = len(set(np.unique(lr[lp > 0]).tolist()) - {0})
                rec["recall"][f"{mm:.3f}"] = (hit / n_r) if n_r else None
        out[f"{t:.2f}"] = rec
    return out


def one_unit(args):
    u, d = args
    t0 = time.time()
    img = ref_image(u, d)
    zooms = img.header.get_zooms()[:3]
    rec = {k: u.get(k) for k in ("id", "block", "base", "T", "site", "split", "age", "cohort", "clean")}
    rec["arms"] = {}
    if u["warp"]:
        reg = json.load(open(os.path.join(d["out"], "registration.json")))["records"][u["base"]]
        rec["gr_pass"], rec["gr_dice"] = reg["pass"], reg["dice_brain"]
        dis_img = nib.load(d["msmask"])
    else:
        rec["gr_pass"], dis_img = True, img
    app = app_for(dis_img)
    expert = expert2 = None
    if u["block"] == "A":
        lab = np.rint(np.asarray(nib.load(os.path.join(d["wmh"], u["wmh"])).dataobj)).astype(np.int16)
        expert, other = lab == 1, lab == 2
        expert2 = (lab == 1) | (lab == 2)
    elif u["block"] == "C1":
        expert, other = np.asarray(img.get_fdata(dtype=np.float32)) > 0.5, None
    resolvable = None
    if u["block"] == "C1" and u["T"] > 1:
        thick = TS.thicken(expert.astype(np.float32), 2, float(zooms[2]), u["T"], 0.0, 0.0, "box", "linear")
        resolvable = thick
    # expert DIS (and observers)
    if expert is not None and rec["gr_pass"]:
        def edis(mask):
            mm = mask.astype(np.float32)
            if u["warp"]:
                mm = (warp_float(mm, img, u["base"], d, "expert") >= 0.5).astype(np.float32)
            return dis_block(mm, dis_img, app)[0]
        rec["expert"] = edis(expert)
        if expert2 is not None:
            rec["expert_l12"] = edis(expert2)
            for k, p in enumerate(u.get("observers") or []):
                lab_o = np.rint(np.asarray(nib.load(os.path.join(d["wmh"], p)).dataobj)).astype(np.int16)
                rec[f"expert_o{k + 3}"] = edis(lab_o == 1)
    for arm in u["arms"]:
        m = arm_map(u, arm, d, img)
        if m is None:
            rec["arms"][arm] = {"available": False}
            continue
        a = {"available": True, "n_native": len(lesion_set((m >= 0.5).astype(np.float32), img)[0])}
        if rec["gr_pass"]:
            dm = (m >= 0.5).astype(np.float32)
            if u["warp"]:
                dm = (warp_float(dm, img, u["base"], d, arm) >= 0.5).astype(np.float32)
            blk, les = dis_block(dm, dis_img, app)
            a.update(blk)
            a["lesions"] = [[round(v, 3), r] for v, r in les]
        if expert is not None:
            pred = m > 0.5
            if u["block"] == "A":
                pred = pred & ~other
            lm = PF.lesion_metrics(pred, expert, zooms)
            a["acc"] = {k: lm[k] for k in ("n_ref", "n_pred", "tp_ref", "tp_pred", "false_lesions", "precision",
                                            "recall", "f1", "dice", "vol_pred_ml", "vol_ref_ml")}
            a["acc"]["size_bins"] = lm["size_bins"]
            if resolvable is not None:
                lr, n_r, _ = PF.components(expert, zooms)
                lp, _, _ = PF.components(pred, zooms)
                res_ids = [k for k in range(1, n_r + 1) if float(resolvable[lr == k].max()) >= 0.5]
                hit = set(np.unique(lr[lp > 0]).tolist()) - {0}
                a["acc"]["n_resolvable"] = len(res_ids)
                a["acc"]["recall_resolvable"] = (sum(k in hit for k in res_ids) / len(res_ids)) if res_ids else None
        if arm in ("flames_ens", "flames_f0") and rec["gr_pass"] and d_set(u):
            a["grid"] = grid_d(m, u, dis_img, app, d, ref_acc=expert if u["block"] == "C1" else None, warp_ref=img)
        rec["arms"][arm] = a
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


def d_set(u):
    """Units used by part D (selection or validation)."""
    if u["block"] in ("A", "B", "C2"):
        return True
    return bool(u.get("clean"))


# ====================================================================== statistics
def binom(x, n):
    c = {"x": int(x), "n": int(n), "rate": rnd(x / n) if n else None, "ci95_exact": rnd(H.clopper_pearson(x, n))}
    if n and x == 0:
        c["one_sided_95_upper"] = rnd(1 - 0.05 ** (1.0 / n))
    if n:
        from scipy.stats import beta
        c["one_sided_95_upper_exact"] = rnd(1.0 if x == n else float(beta.ppf(0.95, x + 1, n - x)))
    return c


def boot_diff(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.size == 0:
        return {"diff": None, "ci95_boot": [None, None]}
    rng = np.random.RandomState(SEED)
    idx = rng.randint(0, a.size, size=(N_BOOT, a.size))
    dd = a[idx].mean(1) - b[idx].mean(1)
    return {"diff": rnd(a.mean() - b.mean()), "ci95_boot": rnd([np.quantile(dd, 0.025), np.quantile(dd, 0.975)])}


def mcnemar(a, b):
    r = H.mcnemar_exact(a, b)
    return {**r, "n_paired": int(len(a)), "arm_x": int(np.sum(a)), "reference_x": int(np.sum(b)), "rate_diff": boot_diff(a, b)}


def newcombe(x1, n1, x2, n2):
    """Newcombe (1998) method 10: difference of two independent proportions with Wilson score limits."""
    def wilson(x, n, z=1.959964):
        p = x / n
        c = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
        den = 1 + z * z / n
        return ((p + z * z / (2 * n) - c) / den, (p + z * z / (2 * n) + c) / den)
    p1, p2 = x1 / n1, x2 / n2
    l1, u1 = wilson(x1, n1)
    l2, u2 = wilson(x2, n2)
    d = p1 - p2
    return {"diff": rnd(d), "ci95": rnd([d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2),
                                         d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)])}


def logistic_per_decade(age, y):
    """Odds ratio of DIS per 10 years of age (IRLS); None when y is constant."""
    y = np.asarray(y, float)
    if y.min() == y.max():
        return None
    X = np.column_stack([np.ones(len(age)), (np.asarray(age, float) - 70.0) / 10.0])
    beta = np.zeros(2)
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ beta))
        W = p * (1 - p)
        hess = X.T @ (X * W[:, None])
        step = np.linalg.solve(hess, X.T @ (y - p))
        beta += step
        if np.abs(step).max() < 1e-10:
            break
    se = math.sqrt(np.linalg.inv(hess)[1, 1])
    return {"or_per_decade": rnd(math.exp(beta[1])), "ci95_wald": rnd([math.exp(beta[1] - 1.96 * se), math.exp(beta[1] + 1.96 * se)])}


def fleiss(ratings):
    """Fleiss kappa for binary ratings (subjects x raters)."""
    r = np.asarray(ratings, float)
    n, k = r.shape
    p1 = r.sum(1)
    P = (p1 * (p1 - 1) + (k - p1) * (k - p1 - 1)) / (k * (k - 1))
    pj = np.array([p1.sum(), (k - p1).sum()]) / (n * k)
    pe = (pj ** 2).sum()
    return rnd((P.mean() - pe) / (1 - pe)) if pe < 1 else None


def cluster_boot(values, units_):
    strata = [PF.cohort_of(u) for u in units_]
    clusters = [PF.patient_of(u) for u in units_]
    out = PF.stratified_cluster_bootstrap(values, strata, clusters, N_BOOT, SEED, "scan")
    out["cohort_weighted"] = PF.stratified_cluster_bootstrap(values, strata, clusters, N_BOOT, SEED, "cohort")
    return out


def vec(recs, block, arm, key, T=None, pred=None):
    """{unit id or base: value} for available arms (DIS endpoints need the GR pass)."""
    out = {}
    for r in recs:
        if r["block"] != block or (T is not None and r["T"] != T) or (pred and not pred(r)):
            continue
        a = r["arms"].get(arm, {})
        if not a.get("available") or key not in a:
            continue
        out[r["base"]] = a[key]
    return out


def paired_bool(x, y):
    common = sorted(set(x) & set(y))
    return common, np.array([bool(x[c]) for c in common]), np.array([bool(y[c]) for c in common])


def family(entries):
    """Holm within a registered family (missing tests keep their place with p = 1)."""
    ps = [e.get("p_two_sided") if e.get("run", True) else None for e in entries]
    adj = H.holm([1.0 if p is None else p for p in ps])
    for e, p in zip(entries, adj):
        e["p_holm_family"] = rnd(p, 6)
        e["established_holm_lt_0.05"] = bool(e.get("run", True) and p < 0.05)
    return entries


def analyse(recs, sets, d):
    S = {"A": {}, "B": {}, "C1": {}, "C2": {}, "D": {}, "families": {}}
    # ---------------- A
    gr = lambda r: r["gr_pass"]  # noqa: E731
    A = [r for r in recs if r["block"] == "A"]
    dE = {r["base"]: r["expert"]["dis"] for r in A if "expert" in r}
    S["A"]["A0_expert_dis"] = binom(sum(dE.values()), len(dE))
    S["A"]["A0_expert_dis_labels_1_2"] = binom(sum(r["expert_l12"]["dis"] for r in A if "expert_l12" in r),
                                              sum(1 for r in A if "expert_l12" in r))
    S["A"]["A0_lower_bound_exceeds_5pct"] = bool(S["A"]["A0_expert_dis"]["ci95_exact"][0] is not None and
                                                 S["A"]["A0_expert_dis"]["ci95_exact"][0] > 0.05)
    S["A"]["by_site"] = {s: binom(sum(dE[r["base"]] for r in A if r["site"] == s and r["base"] in dE),
                                  sum(1 for r in A if r["site"] == s and r["base"] in dE)) for s in sorted({r["site"] for r in A})}
    obs = [r for r in A if all(k in r for k in ("expert", "expert_o3", "expert_o4"))]
    S["A"]["observers_training"] = {"n": len(obs), "O1": sum(r["expert"]["dis"] for r in obs),
                                    "O3": sum(r["expert_o3"]["dis"] for r in obs), "O4": sum(r["expert_o4"]["dis"] for r in obs),
                                    "fleiss_kappa": fleiss([[r["expert"]["dis"], r["expert_o3"]["dis"], r["expert_o4"]["dis"]] for r in obs]) if obs else None}
    S["A"]["arms"] = {}
    fam1, fam2 = [], []
    ref = vec(recs, "A", REF, "dis", pred=gr)
    for arm in ARMS:
        v = vec(recs, "A", arm, "dis", pred=gr)
        S["A"]["arms"][arm] = {"dis": binom(sum(v.values()), len(v)),
                               "dis_pv3": binom(sum(vec(recs, "A", arm, "dis_pv3", pred=gr).values()), len(v)),
                               "any_dis_region": binom(sum(vec(recs, "A", arm, "any_dis_region", pred=gr).values()), len(v))}
        c, x, y = paired_bool(v, dE)
        fam1.append({"arm": arm, "run": bool(c), **(mcnemar(x, y) if c else {"p_two_sided": None})})
        if arm != REF:
            c, x, y = paired_bool(v, ref)
            fam2.append({"arm": arm, "run": bool(c), **(mcnemar(x, y) if c else {"p_two_sided": None})})
        acc = [r["arms"][arm]["acc"] for r in A if r["arms"].get(arm, {}).get("acc")]
        S["A"]["arms"][arm]["accuracy"] = summarise_acc(acc)
    S["A"]["dE_pv3"] = binom(sum(r["expert"]["dis_pv3"] for r in A if "expert" in r), len(dE))
    S["families"]["A-1"] = family(fam1)
    S["families"]["A-2"] = family(fam2)
    # ---------------- B
    B = [r for r in recs if r["block"] == "B"]
    ref_a = vec(recs, "B", REF, "n_native")
    ref_b = vec(recs, "B", REF, "dis", pred=gr)
    fa, fb = [], []
    S["B"]["arms"] = {}
    sib = {r["base"]: r for r in recs if r["block"] == "C2" and r["T"] == 1.0}
    for arm in ARMS:
        n_ = vec(recs, "B", arm, "n_native")
        dd = vec(recs, "B", arm, "dis", pred=gr)
        e = {"a_any_lesion": binom(sum(v > 0 for v in n_.values()), len(n_)), "b_dis": binom(sum(dd.values()), len(dd)),
             "dis_pv3": binom(sum(vec(recs, "B", arm, "dis_pv3", pred=gr).values()), len(dd)),
             "by_decade": {dec: binom(sum(dd[r["base"]] for r in B if r["base"] in dd and dec <= r["age"] < dec + 10),
                                      sum(1 for r in B if r["base"] in dd and dec <= r["age"] < dec + 10)) for dec in (50, 60, 70, 80)},
             "by_cohort": {c: binom(sum(dd[r["base"]] for r in B if r["base"] in dd and r["cohort"] == c),
                                    sum(1 for r in B if r["base"] in dd and r["cohort"] == c)) for c in (1, 2)},
             "age_logistic": logistic_per_decade([r["age"] for r in B if r["base"] in dd], [dd[r["base"]] for r in B if r["base"] in dd]),
             "lesions_per_scan": dist([v for v in n_.values()])}
        sx = sum(sib[c]["arms"][arm]["dis"] for c in sib if sib[c]["arms"].get(arm, {}).get("available"))
        sn = sum(1 for c in sib if sib[c]["arms"].get(arm, {}).get("available"))
        if dd and sn:
            e["replication_minus_sibbms"] = newcombe(sum(dd.values()), len(dd), sx, sn)
        S["B"]["arms"][arm] = e
        if arm != REF:
            c, x, y = paired_bool({k: v > 0 for k, v in n_.items()}, {k: v > 0 for k, v in ref_a.items()})
            fa.append({"arm": arm, "run": bool(c), **(mcnemar(x, y) if c else {"p_two_sided": None})})
            c, x, y = paired_bool(dd, ref_b)
            fb.append({"arm": arm, "run": bool(c), **(mcnemar(x, y) if c else {"p_two_sided": None})})
    S["families"]["B-a"] = family(fa)
    S["families"]["B-b"] = family(fb)
    # ---------------- C1
    C1 = [r for r in recs if r["block"] == "C1"]
    thicks = sorted({r["T"] for r in C1})
    S["C1"]["thicknesses"] = thicks
    dEc = {(r["base"], r["T"]): r["expert"]["dis"] for r in C1 if "expert" in r}
    S["C1"]["arms"] = {}
    f1_delta = {}
    for arm in ARMS:
        e = {}
        for t in thicks:
            rows = [r for r in C1 if r["T"] == t and r["arms"].get(arm, {}).get("available")]
            acc = [r["arms"][arm]["acc"] for r in rows if r["arms"][arm].get("acc")]
            dis = [(r["arms"][arm]["dis"], dEc.get((r["base"], t))) for r in rows if "dis" in r["arms"][arm]]
            e[f"T{t:g}"] = {"n": len(rows), "accuracy": summarise_acc(acc),
                            "dis_agree": binom(sum(a == b for a, b in dis), len(dis)),
                            "false_dis": binom(sum(a and not b for a, b in dis), sum(not b for _, b in dis)),
                            "missed_dis": binom(sum(b and not a for a, b in dis), sum(bool(b) for _, b in dis)),
                            "by_native_stratum": by_stratum(rows, arm, sets)}
        base_rows = {r["base"]: r["arms"][arm]["acc"]["f1"] for r in C1 if r["T"] == 1.0
                     and r["arms"].get(arm, {}).get("acc") and r["arms"][arm]["acc"]["f1"] is not None}
        for t in [x for x in thicks if x > 1]:
            tr = {r["base"]: r["arms"][arm]["acc"]["f1"] for r in C1 if r["T"] == t
                  and r["arms"].get(arm, {}).get("acc") and r["arms"][arm]["acc"]["f1"] is not None}
            common = sorted(set(base_rows) & set(tr))
            e[f"delta_f1_T{t:g}_minus_T1"] = cluster_boot([tr[c] - base_rows[c] for c in common], common)
            if t == max(thicks):
                f1_delta[arm] = {c: tr[c] - base_rows[c] for c in common}
        e["slope_f1_per_mm"] = slope_f1(C1, arm)
        S["C1"]["arms"][arm] = e
    S["C1"]["expert_dis"] = binom(sum(v for (b, t), v in dEc.items() if t == 1.0), sum(1 for (b, t) in dEc if t == 1.0))
    S["families"]["C-1"] = family([{"arm": arm, "run": arm in f1_delta and bool(f1_delta[arm]),
                                    **(S["C1"]["arms"][arm][f"delta_f1_T{max(thicks):g}_minus_T1"] if arm in f1_delta else {"p_two_sided": None})}
                                   for arm in ARMS])
    c2f = []
    for arm in OTHERS:
        common = sorted(set(f1_delta.get(arm, {})) & set(f1_delta.get(REF, {})))
        c2f.append({"arm": arm, "run": bool(common), **(cluster_boot([f1_delta[arm][c] - f1_delta[REF][c] for c in common], common)
                                                       if common else {"p_two_sided": None})})
    S["families"]["C-2"] = family(c2f)
    # ---------------- C2
    C2 = [r for r in recs if r["block"] == "C2"]
    S["C2"]["arms"] = {}
    c3 = []
    for arm in ARMS:
        one = vec(recs, "C2", arm, "dis", T=1.0)
        sev = vec(recs, "C2", arm, "dis", T=7.0)
        n1 = vec(recs, "C2", arm, "n", T=1.0)
        n7 = vec(recs, "C2", arm, "n", T=7.0)
        S["C2"]["arms"][arm] = {"T1": {"a": binom(sum(v > 0 for v in n1.values()), len(n1)), "b": binom(sum(one.values()), len(one))},
                                "T7": {"a": binom(sum(v > 0 for v in n7.values()), len(n7)), "b": binom(sum(sev.values()), len(sev))}}
        c, x, y = paired_bool(sev, one)
        c3.append({"arm": arm, "run": bool(c), **(mcnemar(x, y) if c else {"p_two_sided": None})})
    S["families"]["C-3"] = family(c3)
    # ---------------- D
    S["D"], fam_d = part_d(recs)
    S["families"]["D-1"] = family(fam_d)
    # ---------------- strictest reading
    allp = [(f, e) for f, es in S["families"].items() for e in es]
    adj = H.holm([1.0 if e.get("p_two_sided") is None else e["p_two_sided"] for _, e in allp])
    for (f, e), p in zip(allp, adj):
        e["p_holm_all_40"] = rnd(p, 6)
    S["n_primary_tests"] = len(allp)
    S["consistency_recount_vs_app"] = int(sum(1 for r in recs for a in r["arms"].values() if a.get("recount_equal") is False))
    return S


def dist(v):
    v = np.asarray(v, float)
    if v.size == 0:
        return {"n": 0}
    return {"n": int(v.size), "mean": rnd(v.mean()), "median": rnd(np.median(v)), "iqr": rnd(np.quantile(v, [0.25, 0.75])),
            "max": rnd(v.max())}


def summarise_acc(acc):
    if not acc:
        return {"n": 0}
    f1 = [x["f1"] for x in acc if x["f1"] is not None]
    rec_ = [x["recall"] for x in acc if x["recall"] is not None]
    pre = [x["precision"] for x in acc if x["precision"] is not None]
    rr = [x.get("recall_resolvable") for x in acc if x.get("recall_resolvable") is not None]
    return {"n": len(acc), "f1": dist(f1), "recall": dist(rec_), "precision": dist(pre),
            "false_lesions_per_scan": dist([x["false_lesions"] for x in acc]),
            "dice": dist([x["dice"] for x in acc if x["dice"] is not None]),
            "vol_pred_ml": dist([x["vol_pred_ml"] for x in acc]), "vol_ref_ml": dist([x["vol_ref_ml"] for x in acc]),
            "recall_resolvable": dist(rr) if rr else None}


def by_stratum(rows, arm, sets):
    st = sets["C1_native_thickness"]["stratum"]
    out = {}
    for s in ("<=2.3mm", "3mm", "4-5mm", "unknown"):
        f1 = [r["arms"][arm]["acc"]["f1"] for r in rows if st.get(r["base"]) == s and r["arms"][arm].get("acc")
              and r["arms"][arm]["acc"]["f1"] is not None]
        out[s] = dist(f1)
    return out


def slope_f1(C1, arm):
    per = {}
    for r in C1:
        a = r["arms"].get(arm, {})
        if a.get("acc") and a["acc"]["f1"] is not None:
            per.setdefault(r["base"], {})[r["T"]] = a["acc"]["f1"]
    vals, ids = [], []
    for b, d_ in per.items():
        if len(d_) >= 3:
            t = np.array(sorted(d_))
            y = np.array([d_[k] for k in t])
            vals.append(float(np.polyfit(t, y, 1)[0]))
            ids.append(b)
    return cluster_boot(vals, ids) if vals else None


def part_d(recs):
    out, fam = {}, []
    for arm in ("flames_ens", "flames_f0"):
        def rates(pred, key="dis"):
            rows = [r for r in recs if pred(r) and r["arms"].get(arm, {}).get("grid")]
            return rows
        sel_ctl = rates(lambda r: r["block"] == "C2" and r["T"] == 1.0)
        sel_ms = rates(lambda r: r["block"] == "C1" and r["T"] == 1.0 and r.get("clean") and "expert" in r and r["expert"]["dis"])
        grid = []
        for t in T_GRID:
            for mm in M_GRID:
                kt, km = f"{t:.2f}", f"{mm:.3f}"
                fd = sum(r["arms"][arm]["grid"][kt]["dis"][km] for r in sel_ctl)
                sens = sum(r["arms"][arm]["grid"][kt]["dis"][km] for r in sel_ms)
                rec_ = [r["arms"][arm]["grid"][kt]["recall"][km] for r in sel_ms
                        if r["arms"][arm]["grid"][kt].get("recall", {}).get(km) is not None]
                grid.append({"t": t, "m": mm, "sibbms_dis": fd, "sibbms_n": len(sel_ctl), "ms_dis_sens": sens,
                             "ms_n": len(sel_ms), "ms_recall_mean": rnd(np.mean(rec_)) if rec_ else None})
        default = next(g for g in grid if g["t"] == 0.5 and g["m"] == 3.0)

        def pick(feasible):
            f = [g for g in grid if feasible(g)]
            if not f:
                return None
            return sorted(f, key=lambda g: (-g["ms_dis_sens"], -(g["ms_recall_mean"] or 0), g["t"], g["m"]))[0]
        selected = pick(lambda g: g["sibbms_dis"] <= 0.05 * g["sibbms_n"])
        strict = pick(lambda g: g["sibbms_dis"] <= 1)
        e = {"grid": grid, "default": default, "selected": selected, "strict": strict}
        for name, g in (("selected", selected), ("strict", strict)):
            if g is None:
                continue
            kt, km = f"{g['t']:.2f}", f"{g['m']:.3f}"
            val = {}
            for lab, pred in (("dlbs", lambda r: r["block"] == "B"), ("wmh2017", lambda r: r["block"] == "A"),
                              ("sibbms_7mm", lambda r: r["block"] == "C2" and r["T"] == 7.0)):
                rows = rates(pred)
                x = sum(r["arms"][arm]["grid"][kt]["dis"][km] for r in rows)
                val[lab] = binom(x, len(rows))
                if lab == "wmh2017":
                    val["wmh2017_excess_over_expert"] = binom(sum(r["arms"][arm]["grid"][kt]["dis"][km] and not r["expert"]["dis"]
                                                                  for r in rows if "expert" in r), len(rows))
            for t_ in (3.0, 5.0, 7.0):
                rows = rates(lambda r: r["block"] == "C1" and r["T"] == t_ and r.get("clean") and "expert" in r and r["expert"]["dis"])
                if rows:
                    val[f"ms_dis_sens_T{t_:g}"] = binom(sum(r["arms"][arm]["grid"][kt]["dis"][km] for r in rows), len(rows))
                    val[f"ms_dis_sens_T{t_:g}_default"] = binom(sum(r["arms"][arm]["grid"]["0.50"]["dis"]["3.000"] for r in rows), len(rows))
            dl = rates(lambda r: r["block"] == "B")
            if dl:
                b = val["dlbs"]
                ub = b.get("one_sided_95_upper_exact")
                val["transfer_reading"] = ("holds" if b["rate"] is not None and b["rate"] <= 0.05 and ub is not None and ub <= 0.10
                                           else "fails" if b["ci95_exact"][0] is not None and b["ci95_exact"][0] > 0.05 else "inconclusive")
            e[f"validation_{name}"] = val
        if selected:
            kt, km = f"{selected['t']:.2f}", f"{selected['m']:.3f}"
            dl = rates(lambda r: r["block"] == "B")
            x = np.array([r["arms"][arm]["grid"][kt]["dis"][km] for r in dl], bool)
            y = np.array([r["arms"][arm]["grid"]["0.50"]["dis"]["3.000"] for r in dl], bool)
            fam.append({"arm": arm, "run": bool(len(dl)), **(mcnemar(x, y) if len(dl) else {"p_two_sided": None})})
        else:
            fam.append({"arm": arm, "run": False, "p_two_sided": None})
        out[arm] = e
    return out, fam


# ====================================================================== gates
def gate_g1(recs, d):
    g = {}
    # (i) healthy arm, per control and arm: number of false lesions and DIS
    hc = {}
    for row in csv.DictReader(open(os.path.join(ROOT, "research", "paper_1", "results", "per_control.csv"))):
        if row["available"] == "1":
            hc[(row["case"], row["arm"])] = (int(row["n_false_lesions"]), int(row["dis_met_brain"]))
    got = {(r["base"], arm): (a["n"], int(a["dis"])) for r in recs if r["block"] == "C2" and r["T"] == 1.0
           for arm, a in r["arms"].items() if a.get("available")}
    g["healthy_arm"] = {"compared": len(hc), "equal": sum(got.get(k) == v for k, v in hc.items()), "passed": got == hc}
    # (ii) paper F iso band, per scan: n_ref, n_pred, tp_ref, tp_pred
    pf = {}
    for row in csv.DictReader(gzip.open(os.path.join(ROOT, "research", "paper_f", "results", "per_scan.csv.gz"), "rt")):
        if row["variant"] == "primary" and row["band"] == "iso" and row["status"] == "ok" and row["tool"] in ("flames", "lstai", "mindglide", "wmhsynthseg"):
            pf[(row["case"], row["tool"])] = tuple(int(row[k]) for k in ("n_ref", "n_pred", "tp_ref", "tp_pred"))
    mine = {}
    for r in recs:
        if r["block"] == "C1" and r["T"] == 1.0:
            for arm, tool in (("flames_ens", "flames"), ("lstai", "lstai"), ("mindglide", "mindglide"), ("wmhsynthseg", "wmhsynthseg")):
                a = r["arms"].get(arm, {})
                if a.get("acc"):
                    mine[(r["base"], tool)] = tuple(a["acc"][k] for k in ("n_ref", "n_pred", "tp_ref", "tp_pred"))
    keys = [k for k in pf if k in mine]
    g["paper_f_iso"] = {"compared": len(keys), "equal": sum(pf[k] == mine[k] for k in keys),
                        "passed": bool(keys) and all(pf[k] == mine[k] for k in keys)}
    # (iii) paper D reference decision on its 124 clean scans
    dset = [r for r in recs if r["block"] == "C1" and r["T"] == 1.0 and r.get("clean") and r["base"] != "mslesseg_P49_T2" and "expert" in r]
    met = sum(r["expert"]["dis"] for r in dset)
    g["paper_d_reference"] = {"n": len(dset), "dis_met": met, "expected": PAPER_D_REF_MET, "passed": len(dset) == 124 and met == PAPER_D_REF_MET}
    g["passed"] = all(v["passed"] for v in g.values() if isinstance(v, dict))
    return g


def cmd_check(a, d, sets):
    recs = {}
    for p in glob.glob(os.path.join(d["manifests"], "*.json")):
        m = json.load(open(p))
        for c in m.get("cases", []):
            if "seg_sha256" in c:
                recs[(c["case"], c["tool"])] = c
    bad = n = 0
    for u in units(sets, d):
        if u["src"] != "mimics":
            continue
        img = ref_image(u, d)
        for arm in u["arms"]:
            for p in arm_paths(u, arm, d):
                n += 1
                why = []
                if not os.path.exists(p):
                    why.append("missing")
                else:
                    im = nib.load(p)
                    if tuple(im.shape[:3]) != tuple(img.shape[:3]) or not np.allclose(im.affine, img.affine, atol=1e-3):
                        why.append("not on the input grid")
                    if p.endswith("_seg.nii.gz"):
                        tool = arm
                        data = np.asarray(im.dataobj)
                        if im.get_data_dtype() != np.uint8 or not set(np.unique(data).tolist()) <= {0, 1}:
                            why.append("not binary uint8")
                        key = os.path.basename(p)[:-len(f"_{tool}_seg.nii.gz")]
                        if recs.get((key, tool), {}).get("seg_sha256") != sha256(p):
                            why.append("SHA-256 differs from the manifest")
                if why:
                    bad += 1
                    print(f"FAIL {os.path.basename(p)}: {'; '.join(why)}", flush=True)
    print(f"G3: {n - bad} PASS, {bad} FAIL", flush=True)
    return 1 if bad else 0


# ====================================================================== run
def cmd_run(a, d, sets):
    t0 = time.time()
    us = units(sets, d)
    with Pool(a.workers) as pool:
        recs = pool.map(one_unit, [(u, d) for u in us], chunksize=1)
    S = analyse(recs, sets, d)
    S["gate_G1"] = gate_g1(recs, d)
    S["gate_GR"] = json.load(open(os.path.join(d["out"], "registration.json")))
    S["gate_GR"].pop("records", None)
    S["gate_GR"]["by_block"] = {b: {"pass": sum(bool(r["gr_pass"]) for r in recs if r["block"] == b),
                                    "n": sum(1 for r in recs if r["block"] == b)} for b in ("A", "B")}
    info = {"created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "units": len(recs),
            "prereg": "docs/research/paper-1/PREREG-mimics-thickness.md (effa3a9; amendment 1 d0fdee6)",
            "code_sha256": {f: sha256(os.path.join(HERE, f)) for f in ("evaluate_mimics.py", "analysis_sets.json",
                                                                        "simulate_thick.py", "thick_slice.py")},
            "app_files_sha256": {f: sha256(os.path.join(ROOT, "backend", "app", "services", f))
                                 for f in ("ms_region_classifier.py", "lesion_analysis_service.py", "lesion_metrics.py")},
            "atlas_sha256": sha256(d["msmask"]), "versions": {"python": sys.version.split()[0], "numpy": np.__version__,
                                                              "nibabel": nib.__version__, "scipy": __import__("scipy").__version__},
            "seed": SEED, "n_boot": N_BOOT, "runtime_s": round(time.time() - t0, 1),
            "code_commit": os.environ.get("MIMICS_CODE_COMMIT")}
    S["run_info"] = info
    os.makedirs(a.results, exist_ok=True)
    json.dump(S, open(os.path.join(a.results, "summary.json"), "w"), indent=1,
              default=lambda o: o.item() if hasattr(o, "item") else str(o))
    json.dump(recs, open(os.path.join(d["out"], "records.json"), "w"), default=lambda o: o.item() if hasattr(o, "item") else str(o))
    write_tables(S, a.results)
    write_csvs(recs, a.results)
    print("G1:", json.dumps(S["gate_G1"]), flush=True)
    print(f"wrote {a.results} in {info['runtime_s']} s", flush=True)
    return 0


def write_csvs(recs, out):
    with open(os.path.join(out, "per_unit.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "block", "base", "T", "arm", "available", "gr_pass", "n_lesions", "dis", "dis_pv3", "any_dis_region",
                    "vol_mm3", "f1", "recall", "precision", "false_lesions", "n_ref", "expert_dis"])
        for r in recs:
            for arm, a in r["arms"].items():
                acc = a.get("acc") or {}
                w.writerow([r["id"], r["block"], r["base"], r["T"], arm, int(a.get("available", False)), int(r["gr_pass"]),
                            a.get("n", ""), int(a["dis"]) if "dis" in a else "", int(a["dis_pv3"]) if "dis_pv3" in a else "",
                            int(a["any_dis_region"]) if "any_dis_region" in a else "", rnd(a.get("vol_mm3"), 1),
                            rnd(acc.get("f1")), rnd(acc.get("recall")), rnd(acc.get("precision")), acc.get("false_lesions", ""),
                            acc.get("n_ref", ""), int(r["expert"]["dis"]) if "expert" in r else ""])
    with open(os.path.join(out, "lesions.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "block", "arm", "lesion", "vol_mm3", "region"])
        for r in recs:
            for arm, a in r["arms"].items():
                for j, (v, g) in enumerate(a.get("lesions", []), 1):
                    w.writerow([r["id"], r["block"], arm, j, v, g])


def fmt(c):
    if not c or not c.get("n"):
        return "—"
    lo, hi = c["ci95_exact"]
    return f"{c['x']}/{c['n']} ({100 * c['rate']:.0f} %; {100 * lo:.1f}–{100 * hi:.1f})"


def write_tables(S, out):
    L = ["# Paper 1 addendum — final results (MS mimic, second cohort, controlled thickness, safeguard)", "",
         "Pre-registration: `docs/research/paper-1/PREREG-mimics-thickness.md` (effa3a9, amendment 1 d0fdee6). "
         "Generated by `research/paper_1/mimics/evaluate_mimics.py`; numbers from `summary.json`.", "",
         f"Gates: G1 {'PASS' if S['gate_G1']['passed'] else 'FAIL'} · GR {json.dumps(S['gate_GR']['by_block'])}", "",
         "## A — WMH 2017 (vascular WMH, no MS)", "",
         f"Expert WMH masks meet the app's DIS rule: **{fmt(S['A']['A0_expert_dis'])}** (labels 1 ∪ 2: {fmt(S['A']['A0_expert_dis_labels_1_2'])}; "
         f"PV ≥ 3: {fmt(S['A']['dE_pv3'])}).", "", "| Arm | DIS met | PV ≥ 3 variant | lesion F1 median |", "|---|---|---|---|"]
    for arm, e in S["A"]["arms"].items():
        f1 = e["accuracy"].get("f1", {}).get("median") if e["accuracy"].get("n") else None
        L.append(f"| {arm} | {fmt(e['dis'])} | {fmt(e['dis_pv3'])} | {f1} |")
    L += ["", "## B — DLBS, 100 adults aged 50–89 without MS", "", "| Arm | ≥ 1 lesion | DIS met | DIS by decade 50s/60s/70s/80s |", "|---|---|---|---|"]
    for arm, e in S["B"]["arms"].items():
        dec = " / ".join(f"{v['x']}/{v['n']}" if v.get("n") else "—" for v in e["by_decade"].values())
        L.append(f"| {arm} | {fmt(e['a_any_lesion'])} | {fmt(e['b_dis'])} | {dec} |")
    L += ["", "## C1 — controlled thickness (MS), lesion-wise F1 median by thickness", ""]
    th = S["C1"]["thicknesses"]
    L += ["| Arm | " + " | ".join(f"{t:g} mm" for t in th) + " | ΔF1 max − 1 mm (95 % CI) |", "|---" * (len(th) + 2) + "|"]
    for arm, e in S["C1"]["arms"].items():
        cells = [str(e[f"T{t:g}"]["accuracy"].get("f1", {}).get("median")) if e[f"T{t:g}"]["accuracy"].get("n") else "—" for t in th]
        dd = e.get(f"delta_f1_T{max(th):g}_minus_T1") or {}
        ci = dd.get("ci95") or [None, None]
        L.append(f"| {arm} | " + " | ".join(cells) + f" | {rnd(dd.get('estimate'))} ({rnd(ci[0])}, {rnd(ci[1])}) |")
    L += ["", "## C2 — SibBMS controls, DIS at 1 mm and 7 mm", "", "| Arm | 1 mm | 7 mm |", "|---|---|---|"]
    for arm, e in S["C2"]["arms"].items():
        L.append(f"| {arm} | {fmt(e['T1']['b'])} | {fmt(e['T7']['b'])} |")
    L += ["", "## D — safeguard", ""]
    for arm, e in S["D"].items():
        sel = e.get("selected")
        L.append(f"- {arm}: selected {('t = %.2f, m = %.3f mm³' % (sel['t'], sel['m'])) if sel else 'none feasible'}; "
                 f"DLBS {fmt(e.get('validation_selected', {}).get('dlbs'))}; transfer: {e.get('validation_selected', {}).get('transfer_reading')}")
    L += ["", "## Registered families (Holm within family; strictest = Holm over all 40)", "",
          "| Family | Arm | estimate | p | Holm (family) | Holm (all) |", "|---|---|---|---|---|---|"]
    for f, es in S["families"].items():
        for e in es:
            est = e.get("estimate", (e.get("rate_diff") or {}).get("diff"))
            L.append(f"| {f} | {e['arm']} | {rnd(est)} | {rnd(e.get('p_two_sided'), 6)} | {e.get('p_holm_family')} | {e.get('p_holm_all_40')} |")
    open(os.path.join(out, "tables.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")


def dirs(a):
    return {"pf": a.pf, "mimics": a.mimics, "wmh": a.wmh, "out": a.work, "reg": os.path.join(a.work, "registration"),
            "manifests": a.manifests, "msmask": os.path.join(ROOT, "backend", "data", "msmask", "sub-mni152_space-mni_msmask.nii.gz"),
            "atlas_t1_raw": a.atlas_t1, "atlas_t1": os.path.join(a.work, "atlas_t1_brain.nii.gz")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("register", "check", "run"))
    ap.add_argument("--pf", required=True, help="dir with flames/, lstai/, toolbench/ of paper F and the healthy arm")
    ap.add_argument("--mimics", required=True, help="dir with flames/, lstai/, toolbench/, inputs/ of the addendum")
    ap.add_argument("--wmh", required=True, help="the wmh2017 mirror folder")
    ap.add_argument("--manifests", required=True)
    ap.add_argument("--atlas-t1", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--results", default=os.path.join(HERE, "results"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    d = dirs(a)
    os.makedirs(a.work, exist_ok=True)
    sets = json.load(open(SETS))
    sys.exit({"register": cmd_register, "check": cmd_check, "run": cmd_run}[a.cmd](a, d, sets))


if __name__ == "__main__":
    main()
