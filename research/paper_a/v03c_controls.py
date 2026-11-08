#!/usr/bin/env python3
"""Paper A v0.3 controls addendum — healthy-control analysis (PROTOCOL-v0.3-addendum-controls.md,
pre-registered in commit caa47e7). CPU only; local files only.

  1. Candidate extraction on the 100 SibBMS controls with the v0.3 code
     (v03_candidates.candidates: 18-connected {p >= 0.5}, >= 3 mm^3, mean score): ensemble (mean of
     5 folds, + per-fold candidate means) and folds 0-4. Cache: research/paper_a/.cache/v03c_controls.pkl
  2. Calibration from the v0.3 patient cache with v03_analysis.select (re-checked against the frozen
     record 2026-10-24_paper_a_v03c_calibration.json: thresholds and null SHA-256 must be equal).
  3. Primary (§5), S1-S8 (§6). S3 uses the app's own region / DIS functions (read-only import).

    python research/paper_a/v03c_controls.py --data <scratch dir with cohort/ and brainmask/> [--workers 4]

Run with the offline environment (the app modules are imported):
  GOOGLE_APPLICATION_CREDENTIALS=<missing file> CLOUDSDK_CONFIG=<empty dir> GOOGLE_CLOUD_PROJECT=mstool-offline-tests
"""
import argparse
import json
import os
import pickle
import sys
import time
from multiprocessing import Pool

import nibabel as nib
import numpy as np
from scipy import ndimage as ndi
from scipy.stats import binom

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v03_analysis as A                                                # noqa: E402
import v03_metrics as M                                                 # noqa: E402
from v03_candidates import (CACHE, MIN_VOL_MM3, STRUCT, THRESHOLD, candidates,   # noqa: E402
                            expert_lesions, load, sha256)
from v03_data import RECORDS, ROOT                                      # noqa: E402
from v03c_calibration import null_sha, pools_for                        # noqa: E402

SEED = 20261024
N_BOOT = 2000
CASES = [f"sub-{i:03d}" for i in range(1, 101)]
AUGUST = {f"sub-{i:03d}" for i in list(range(1, 21)) + list(range(31, 41))}
QC_FLAG = {"sub-075"}
PRIMARY_POOL = "1-mm sites"
PRIMARY = [("P1", 0.1), ("P1", 0.2), ("P2", 0.1), ("P2", 0.2)]
CTL_CACHE = os.path.join(HERE, ".cache", "v03c_controls.pkl")
OUT = os.path.join(RECORDS, "2026-10-24_paper_a_v03c_controls.json")
CALIB = os.path.join(RECORDS, "2026-10-24_paper_a_v03c_calibration.json")
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)


def rnd(x, k=4):
    if x is None:
        return None
    if isinstance(x, np.ndarray):
        x = x.tolist()
    if isinstance(x, (list, tuple)):
        return [rnd(v, k) for v in x]
    return round(float(x), k)


# ------------------------------------------------------------------ 1. extraction (v0.3 rule)
def _cand_voxels(prob, vox):
    """Same labelling as v03_candidates.candidates: flat voxel indices of each kept component,
    in the same order as its outputs."""
    lab, n = ndi.label(prob >= THRESHOLD, structure=STRUCT)
    counts = np.bincount(lab.ravel(), minlength=n + 1)
    ids = [i for i in range(1, n + 1) if counts[i] * vox >= MIN_VOL_MM3 - 1e-9]
    if not ids:
        return []
    objs = ndi.find_objects(lab)
    out = []
    for i in ids:
        sl = objs[i - 1]
        sub = lab[sl] == i
        idx = np.nonzero(sub)
        full = tuple(idx[d] + sl[d].start for d in range(3))
        out.append(np.ravel_multi_index(full, lab.shape).astype(np.int64))
    return out


def one_control(args):
    data, case = args
    t0 = time.time()
    coh = os.path.join(data, "cohort")
    gimg = nib.load(os.path.join(coh, f"{case}_gt.nii.gz"))
    zooms = [float(z) for z in gimg.header.get_zooms()[:3]]
    vox = float(np.prod(zooms))
    gt = np.asarray(gimg.dataobj) > 0
    gt_lab, gt_counts, valid, _ = expert_lesions(gt, vox)
    assert valid.size == 0, case
    bm = np.asarray(nib.load(os.path.join(data, "brainmask", f"{case}_brainmask.nii.gz")).dataobj) > 0
    edt = ndi.distance_transform_edt(bm, sampling=zooms)               # mm to the nearest non-brain voxel
    folds = [load(os.path.join(coh, f"{case}_f{k}_prob.nii.gz")) for k in range(5)]
    ens = np.mean(folds, axis=0)
    rec = {"case": case, "zooms": zooms, "vox_mm3": vox, "shape": list(gt.shape), "arms": {}}
    maps = {"ens": ens, **{f"f{k}": folds[k] for k in range(5)}}
    for arm, m in maps.items():
        c = candidates(m, vox, gt_lab, gt_counts, valid, extra_maps=folds if arm == "ens" else None)
        vlist = _cand_voxels(m, vox)
        assert len(vlist) == c["n"], (case, arm)
        c["voxels"] = vlist
        c["min_edt_mm"] = np.array([float(edt.ravel()[v].min()) for v in vlist])
        c["outside_mask_vox"] = np.array([int((~bm.ravel()[v]).sum()) for v in vlist])
        c["centroid_vox"] = np.array([np.mean(np.unravel_index(v, gt.shape), axis=1) for v in vlist]) if vlist else np.zeros((0, 3))
        rec["arms"][arm] = c
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


# ------------------------------------------------------------------ helpers
def ctrl_scans(crecs, arm, exclude=()):
    out = []
    for r in crecs:
        if r["case"] in exclude:
            continue
        a = r["arms"][arm]
        out.append({"case": r["case"], "site": "sibbms", "patient": r["case"], "scores": np.asarray(a["score"], float),
                    "isf": np.ones(a["n"], bool), "mg": np.zeros(a["n"], int), "gt_ids": np.zeros(0, int),
                    "gt_vol": np.zeros(0), "_safe": {}, "slice_mm": 1.0, "band": "B1"})
    return out


def cell(sel, ctr, nominal=None, guarantee=True):
    x = sum(int(sel[c["case"]].any()) for c in ctr)
    F = np.array([int(sel[c["case"]].sum()) for c in ctr])
    n = len(ctr)
    ci = M.clopper_pearson(x, n)
    res = {"n": n, "scans_with_any": x, "rate": rnd(x / n), "ci95_exact": rnd(ci),
           "false_lesions_total": int(F.sum()), "per_100_scans": rnd(100.0 * F.sum() / n, 1),
           "false_per_scan_mean": rnd(F.mean()), "false_per_scan_sd": rnd(F.std(ddof=1) if n > 1 else 0.0),
           "false_per_scan_median": rnd(np.median(F)), "false_per_scan_max": int(F.max()) if n else 0,
           "distribution_0_1_2_ge3": [int((F == 0).sum()), int((F == 1).sum()), int((F == 2).sum()), int((F >= 3).sum())]}
    if x == 0:
        res["one_sided_95_upper"] = rnd(1 - 0.05 ** (1.0 / n))
    if nominal is not None:
        res["nominal"] = nominal
        res["class"] = M.classify(ci, nominal, A.MARGIN) if guarantee else "no guarantee (descriptive)"
    return res


def nominal_of(proc, target):
    if proc == "P2":
        return A.DELTA, True
    if proc == "B1":
        return target, False
    return target, True


def mcnemar_exact(a, b):
    """a, b boolean arrays (paired). Two-sided exact test on discordant pairs."""
    n10 = int((a & ~b).sum())
    n01 = int((~a & b).sum())
    k = n10 + n01
    p = 1.0 if k == 0 else min(1.0, 2 * binom.cdf(min(n10, n01), k, 0.5))
    return {"ens_only": n10, "f0_only": n01, "p_two_sided": rnd(p, 5)}


def paired_boot(a, b, seed=SEED):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    rng = np.random.RandomState(seed)
    idx = rng.randint(0, a.size, size=(N_BOOT, a.size))
    d = a[idx].mean(1) - b[idx].mean(1)
    return {"diff": rnd(a.mean() - b.mean()), "ci95_boot": rnd([np.quantile(d, 0.025), np.quantile(d, 0.975)])}


# ------------------------------------------------------------------ S3 app DIS
class AppDIS:
    def __init__(self, gimg):
        sys.path.insert(0, os.path.join(ROOT, "backend"))
        from app.services import lesion_analysis_service as las     # read-only use of app code
        from app.services import ms_region_classifier as rc
        self.rc, self.las = rc, las
        if not rc.looks_mni(gimg.affine, gimg.shape[:3]):
            raise RuntimeError("grid not MNI-like: the app would refuse (NotMNISpaceError)")
        zooms = [float(z) for z in gimg.header.get_zooms()[:3]]
        self.spacing = (zooms[2], zooms[0], zooms[1])                   # app internal (D, H, W) = (k, a0, a1)
        zr = rc.generate_zone_map_atlas(gimg, self.spacing)
        self.zone = np.ascontiguousarray(np.transpose(np.asarray(zr["zone_mask"]), (2, 0, 1)))
        self.shape = tuple(gimg.shape[:3])
        self.affine = gimg.affine.copy()

    def run(self, voxel_lists):
        """voxel_lists: flat NIfTI indices of each lesion of the set. Returns (dis dict, classified NIfTI)."""
        if not voxel_lists:
            return {"dis_met_brain": False, "regions": {}, "any_dis_region": False}, None
        m = np.zeros(int(np.prod(self.shape)), np.uint8)
        for v in voxel_lists:
            m[v] = 1
        m = np.transpose(m.reshape(self.shape), (2, 0, 1)).copy()
        cl = self.rc.classify_from_zone_mask(m, self.zone, self.spacing)
        dis = self.las.compute_dis_criteria(cl["classified_mask"], voxel_spacing=self.spacing)
        pres = {k: bool(v["present"]) for k, v in dis["region_details"].items()}
        return ({"dis_met_brain": bool(dis["dis_met_brain"]), "regions": pres, "any_dis_region": any(pres.values())},
                np.transpose(cl["classified_mask"], (1, 2, 0)))


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--reuse-cache", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    frozen = json.load(open(CALIB, encoding="utf-8"))
    pcache = pickle.load(open(CACHE, "rb"))
    assert sha256(CACHE) == frozen["patient_cache"]["sha256"]

    # ---- 1. extraction
    if a.reuse_cache and os.path.exists(CTL_CACHE):
        crecs = pickle.load(open(CTL_CACHE, "rb"))
    else:
        with Pool(a.workers) as pool:
            crecs = pool.map(one_control, [(a.data, c) for c in CASES], chunksize=1)
        os.makedirs(os.path.dirname(CTL_CACHE), exist_ok=True)
        with open(CTL_CACHE, "wb") as fh:
            pickle.dump(crecs, fh, protocol=4)
    log(f"extraction done: {len(crecs)} controls ({time.time() - t0:.0f} s)")
    rec = {"created": time.strftime("%Y-%m-%d %H:%M:%S"),
           "protocol": "docs/research/paper/PROTOCOL-v0.3-addendum-controls.md (commit caa47e7)",
           "inventory_record": "2026-10-24_paper_a_v03c_inventory.json",
           "inventory_record_sha256": sha256(os.path.join(RECORDS, "2026-10-24_paper_a_v03c_inventory.json")),
           "calibration_record_sha256": sha256(CALIB),
           "patient_cache_sha256": frozen["patient_cache"]["sha256"],
           "control_cache": {"file": "research/paper_a/.cache/v03c_controls.pkl", "sha256": sha256(CTL_CACHE)},
           "code_sha256": {f: sha256(os.path.join(HERE, f)) for f in
                           ("v03c_controls.py", "v03c_calibration.py", "v03_analysis.py", "v03_metrics.py", "v03_candidates.py")},
           "seed": SEED, "n_boot": N_BOOT}

    # ---- 2. calibration (re-checked against the frozen record)
    check = []
    pools = {}
    for arm in ("ens", "f0"):
        pools[arm] = pools_for(pcache, arm)
        for pname, pool in pools[arm].items():
            fz = frozen["arms"][arm][pname]
            ok = null_sha(A.null_of(pool)) == fz["null_sha256"]
            for p in A.PROCS:
                if p[0] != "P1":
                    lam = A.select(pool, [], *p)[1]
                    lam = None if not np.isfinite(lam) else round(float(lam), 4)
                    ok &= lam == fz["thresholds"][f"{p[0]}|{p[1]}"]
            check.append(ok)
    assert all(check), "calibration differs from the frozen record"
    rec["calibration_matches_frozen_record"] = True

    # ---- raw candidates (no selection)
    raw = {}
    for arm in ("ens", "f0", "f1", "f2", "f3", "f4"):
        C = np.array([r["arms"][arm]["n"] for r in crecs])
        allsc = np.concatenate([r["arms"][arm]["score"] for r in crecs]) if C.sum() else np.zeros(0)
        allv = np.concatenate([r["arms"][arm]["vol_mm3"] for r in crecs]) if C.sum() else np.zeros(0)
        x = int((C > 0).sum())
        raw[arm] = {"scans_with_any_candidate": x, "ci95_exact": rnd(M.clopper_pearson(x, len(C))),
                    "candidates_total": int(C.sum()), "per_scan_mean": rnd(C.mean()), "per_scan_sd": rnd(C.std(ddof=1)),
                    "per_scan_median": rnd(np.median(C)), "per_scan_max": int(C.max()),
                    "distribution_0_1_2_ge3": [int((C == 0).sum()), int((C == 1).sum()), int((C == 2).sum()), int((C >= 3).sum())],
                    "score_quantiles_50_90_max": rnd(np.quantile(allsc, [0.5, 0.9, 1.0])) if allsc.size else None,
                    "volume_mm3_quantiles_50_90_max": rnd(np.quantile(allv, [0.5, 0.9, 1.0]), 1) if allv.size else None}
    rec["raw_candidates"] = raw
    log("raw candidates:", json.dumps({k: {kk: v[kk] for kk in ("scans_with_any_candidate", "candidates_total", "per_scan_mean")} for k, v in raw.items()}))

    # ---- primary + S1 (all operating points), S6 and S5 subsets
    subsets = {"all100": (), "without_sub-075": tuple(QC_FLAG),
               "new70": tuple(sorted(AUGUST)), "august30": tuple(c for c in CASES if c not in AUGUST)}
    S1 = {}
    sels = {}
    for arm in ("ens", "f0"):
        ctr_all = ctrl_scans(crecs, arm)
        for pname, pool in pools[arm].items():
            for p in A.PROCS:
                sel, lam = A.select(pool, ctr_all, *p)
                sels[(arm, pname, p)] = sel
                nom, g = nominal_of(*p)
                for sname, excl in subsets.items():
                    ctr = [c for c in ctr_all if c["case"] not in excl]
                    S1[f"{arm}|{pname}|{p[0]}|{p[1]}|{sname}"] = dict(cell(sel, ctr, nom, g),
                                                                       threshold=None if lam is None or not np.isfinite(lam) else rnd(lam))
        for al in A.ALPHAS:                                       # own-null floor
            sel = {}
            for c in ctr_all:
                null = A.null_of([x for x in ctr_all if x["patient"] != c["patient"]])
                sel[c["case"]] = M.bh(M.conformal_pvalues(c["scores"], null), al) if c["scores"].size else np.zeros(0, bool)
            sels[(arm, "own-null floor", ("P1", al))] = sel
            S1[f"{arm}|own-null floor (leave-one-control-out)|P1|{al}|all100"] = cell(sel, ctr_all, al, True)
    rec["operating_points"] = S1

    prim = {}
    z_bonf = 1 - 0.05 / len(PRIMARY)
    for p in PRIMARY:
        c = S1[f"ens|{PRIMARY_POOL}|{p[0]}|{p[1]}|all100"]
        c = dict(c, ci_bonferroni=rnd(M.clopper_pearson(c["scans_with_any"], c["n"], conf=z_bonf)))
        c["class_bonferroni"] = M.classify(c["ci_bonferroni"], c["nominal"], A.MARGIN)
        prim[f"P{p[0][1]}|{p[1]}"] = c
        log(f"PRIMARY ens | {PRIMARY_POOL} | {p[0]} {p[1]}: {c['scans_with_any']}/100 {c['ci95_exact']} -> {c['class']}; "
            f"false lesions/scan {c['false_per_scan_mean']}; Bonferroni {c['ci_bonferroni']} -> {c['class_bonferroni']}")
    rec["primary"] = prim

    # ---- S4 ensemble vs fold 0 (paired)
    s4 = {}
    for pname in pools["ens"]:
        for p in PRIMARY + [("P1", 0.3)]:
            se, sf = sels[("ens", pname, p)], sels[("f0", pname, p)]
            ae = np.array([se[c].any() for c in CASES])
            af = np.array([sf[c].any() for c in CASES])
            fe = np.array([se[c].sum() for c in CASES])
            ff = np.array([sf[c].sum() for c in CASES])
            s4[f"{pname}|{p[0]}|{p[1]}"] = {"ens_scans_with_any": int(ae.sum()), "f0_scans_with_any": int(af.sum()),
                                            "rate_diff": paired_boot(ae, af), "mcnemar": mcnemar_exact(ae, af),
                                            "false_per_scan_diff": paired_boot(fe, ff)}
    ae = np.array([r["arms"]["ens"]["n"] > 0 for r in crecs])
    af = np.array([r["arms"]["f0"]["n"] > 0 for r in crecs])
    s4["raw|any candidate"] = {"rate_diff": paired_boot(ae, af), "mcnemar": mcnemar_exact(ae, af),
                               "candidates_per_scan_diff": paired_boot([r["arms"]["ens"]["n"] for r in crecs],
                                                                       [r["arms"]["f0"]["n"] for r in crecs])}
    rec["ensemble_vs_fold0"] = s4

    # ---- S8 reproduction of the 30 August fold-0 controls vs the v0.3 cache
    v03c = {r["case"].replace("sibbms_", ""): r for r in pcache["controls"]}
    rep = {"compared": 0, "same_count": 0, "max_score_diff": 0.0, "mismatches": []}
    for r in crecs:
        if r["case"] not in v03c:
            continue
        o = v03c[r["case"]]["arms"]["f0"]
        n = r["arms"]["f0"]
        rep["compared"] += 1
        if o["n"] == n["n"]:
            rep["same_count"] += 1
            if n["n"]:
                rep["max_score_diff"] = max(rep["max_score_diff"], float(np.abs(np.asarray(o["score"]) - n["score"]).max()))
        else:
            rep["mismatches"].append({"case": r["case"], "v03": int(o["n"]), "new": int(n["n"])})
    rep["max_score_diff"] = rnd(rep["max_score_diff"], 5)
    rep["passed"] = rep["compared"] == 30 and rep["same_count"] == 30 and rep["max_score_diff"] <= 0.003
    rec["reproduction_august30"] = rep
    log("S8 reproduction:", rep)

    # ---- S3 app DIS + S7 location
    gimg = nib.load(os.path.join(a.data, "cohort", "sub-001_gt.nii.gz"))
    app = AppDIS(gimg)
    region_name = {1: "PV", 2: "JC", 3: "IT", 4: "DWM"}
    lesion_sets = {"raw ens": ("ens", None), "raw f0": ("f0", None)}
    for p in PRIMARY:
        lesion_sets[f"ens|{PRIMARY_POOL}|{p[0]}|{p[1]}"] = ("ens", (PRIMARY_POOL, p))
    for al in (0.1, 0.2):
        lesion_sets[f"ens|all five patient sites|P1|{al}"] = ("ens", ("all five patient sites", ("P1", al)))
    dis = {k: [] for k in lesion_sets}
    loc = {"ens": [], "f0": []}
    for r in crecs:
        regions = {}
        for arm in ("ens", "f0"):
            vl = r["arms"][arm]["voxels"]
            d, cls = app.run(vl)
            dis[f"raw {arm}"].append(dict(d, case=r["case"]))
            reg = [region_name.get(int(cls.ravel()[v[0]]), "none") for v in vl] if cls is not None else []
            regions[arm] = reg
            for j, v in enumerate(vl):
                loc[arm].append({"case": r["case"], "score": float(r["arms"][arm]["score"][j]),
                                 "vol_mm3": float(r["arms"][arm]["vol_mm3"][j]), "min_edt_mm": float(r["arms"][arm]["min_edt_mm"][j]),
                                 "outside_mask_vox": int(r["arms"][arm]["outside_mask_vox"][j]), "region": reg[j],
                                 "selected": {}})
        for name, (arm, spec) in lesion_sets.items():
            if spec is None:
                continue
            pname, p = spec
            s = sels[(arm, pname, p)][r["case"]]
            vl = [v for v, keep in zip(r["arms"][arm]["voxels"], s) if keep]
            d, _ = app.run(vl)
            dis[name].append(dict(d, case=r["case"]))
    # mark selections on location rows (ensemble, primary pool)
    idx = 0
    for r in crecs:
        n = r["arms"]["ens"]["n"]
        for p in PRIMARY:
            s = sels[("ens", PRIMARY_POOL, p)][r["case"]]
            for j in range(n):
                loc["ens"][idx + j]["selected"][f"{p[0]}|{p[1]}"] = bool(s[j])
        idx += n
    s3 = {}
    for name, rows in dis.items():
        for sname, excl in (("all100", ()), ("without_sub-075", tuple(QC_FLAG))):
            rr = [x for x in rows if x["case"] not in excl]
            k = sum(x["dis_met_brain"] for x in rr)
            k2 = sum(x["any_dis_region"] for x in rr)
            e = {"n": len(rr), "dis_met_brain": k, "ci95_exact": rnd(M.clopper_pearson(k, len(rr))),
                 "any_dis_region": k2, "any_dis_region_ci95": rnd(M.clopper_pearson(k2, len(rr))),
                 "cases_dis_met": [x["case"] for x in rr if x["dis_met_brain"]]}
            if k == 0:
                e["one_sided_95_upper"] = rnd(1 - 0.05 ** (1.0 / len(rr)))
            s3[f"{name}|{sname}"] = e
        log(f"S3 DIS {name}: {s3[name + '|all100']['dis_met_brain']}/100 {s3[name + '|all100']['ci95_exact']}; "
            f"any DIS region {s3[name + '|all100']['any_dis_region']}")
    rec["app_dis"] = {"code_path": "ms_region_classifier.generate_zone_map_atlas -> classify_from_zone_mask -> "
                                   "lesion_analysis_service.compute_dis_criteria (dis_met_brain); spinal cord / optic nerve None",
                      "app_files_sha256": {f: sha256(os.path.join(ROOT, "backend", "app", "services", f))
                                           for f in ("ms_region_classifier.py", "lesion_analysis_service.py", "lesion_metrics.py")},
                      "results": s3}

    def loc_summary(rows):
        if not rows:
            return {"n": 0}
        e = np.array([x["min_edt_mm"] for x in rows])
        regs = [x["region"] for x in rows]
        return {"n": len(rows), "within_3mm_of_brainmask_edge": int((e <= 3.0).sum()),
                "share_within_3mm": rnd((e <= 3.0).mean()), "touching_outside_mask": int(sum(x["outside_mask_vox"] > 0 for x in rows)),
                "min_edt_mm_quantiles_10_50_90": rnd(np.quantile(e, [0.1, 0.5, 0.9]), 2),
                "regions": {k: regs.count(k) for k in ("PV", "JC", "IT", "DWM", "none")},
                "vol_mm3_quantiles_50_90": rnd(np.quantile([x["vol_mm3"] for x in rows], [0.5, 0.9]), 1),
                "score_quantiles_50_90": rnd(np.quantile([x["score"] for x in rows], [0.5, 0.9]))}
    s7 = {"raw ens": loc_summary(loc["ens"]), "raw f0": loc_summary(loc["f0"])}
    for p in PRIMARY:
        s7[f"ens|{PRIMARY_POOL}|{p[0]}|{p[1]} selected"] = loc_summary([x for x in loc["ens"] if x["selected"][f"{p[0]}|{p[1]}"]])
    s7["raw ens, top-scoring 20"] = loc_summary(sorted(loc["ens"], key=lambda x: -x["score"])[:20])
    rec["location"] = s7
    rec["location_rows_ens"] = loc["ens"]
    log("S7 location raw ens:", s7["raw ens"])
    rec["per_control"] = [{"case": r["case"], "ens_candidates": int(r["arms"]["ens"]["n"]), "f0_candidates": int(r["arms"]["f0"]["n"]),
                           "ens_max_score": rnd(r["arms"]["ens"]["score"].max()) if r["arms"]["ens"]["n"] else None,
                           "f0_max_score": rnd(r["arms"]["f0"]["score"].max()) if r["arms"]["f0"]["n"] else None,
                           "selected_primary": {f"{p[0]}|{p[1]}": int(sels[("ens", PRIMARY_POOL, p)][r["case"]].sum()) for p in PRIMARY},
                           "august30": r["case"] in AUGUST} for r in crecs]
    rec["runtime_s"] = round(time.time() - t0, 1)
    rec["log"] = LOG
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    log(f"wrote {OUT} in {rec['runtime_s']} s")


if __name__ == "__main__":
    main()
