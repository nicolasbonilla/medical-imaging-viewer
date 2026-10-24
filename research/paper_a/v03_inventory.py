#!/usr/bin/env python3
"""Paper A v0.3 — input inventory (run BEFORE any outcome is computed).

For every input file of the v0.3 analysis this script records the SHA-256, shape, voxel size,
orientation, dtype and value range, and checks that
  * every file opens;
  * each probability map (5 FLAMeS folds, LST-AI ensemble + 3 sub-models) has the same shape and
    affine as its expert mask;
  * expert masks are binary;
  * the uint8 maps decode (NIfTI scl_slope/scl_inter, applied by nibabel) to probabilities in [0, 1];
  * the new fold-0 maps of MSLesSeg / Ljubljana reproduce the August fold-0 maps used by v0.1/v0.2
    (same inputs and weights, TTA off) up to the uint8 storage error (1/510).
No candidate, score or lesion match is computed here; GT lesion VOXEL counts are descriptive.

    python research/paper_a/v03_inventory.py
"""
import glob
import hashlib
import json
import os
import re
import sys
import time
from multiprocessing import Pool

import nibabel as nib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from v03_data import (CLOUD, CONTROLS_DIR, OLD_DIRS, RECORDS, case_cohort, patient_of,   # noqa: E402
                      openms_clean_ids)

OUT = os.path.join(RECORDS, "2026-10-21_paper_a_v03_inventory.json")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def info(path, want_values=True):
    im = nib.load(path)
    d = {"file": os.path.relpath(path, os.path.dirname(CLOUD)).replace("\\", "/"),
         "sha256": sha256(path), "shape": list(im.shape),
         "zooms": [round(float(z), 5) for z in im.header.get_zooms()[:3]],
         "axcodes": "".join(nib.aff2axcodes(im.affine)), "dtype": str(im.get_data_dtype())}
    if want_values:
        a = np.asarray(im.get_fdata(dtype=np.float32))          # scaled values (probabilities)
        d["min"], d["max"] = float(a.min()), float(a.max())
        d["nonzero"] = int(np.count_nonzero(a))
    return d, im


def one_case(case):
    out = {"case": case, "cohort": case_cohort(case), "patient": patient_of(case), "problems": []}
    gt_path = os.path.join(CLOUD, "flames", f"{case}_gt.nii.gz")
    g, gim = info(gt_path)
    ga = np.asanyarray(gim.dataobj)
    vals = np.unique(ga)
    g["unique_values"] = [float(v) for v in vals[:5]]
    if not set(vals.tolist()) <= {0, 1}:
        out["problems"].append("gt not binary")
    out["gt"] = g
    out["gt_lesion_voxels"] = int((ga > 0).sum())
    out["voxel_volume_mm3"] = round(float(np.prod(g["zooms"])), 4)
    out["slice_spacing_mm"] = round(float(max(g["zooms"])), 4)
    maps = {f"f{k}": os.path.join(CLOUD, "flames", f"{case}_f{k}_prob.nii.gz") for k in range(5)}
    for m in ("", "_m1", "_m2", "_m3"):
        p = os.path.join(CLOUD, "lstai", f"{case}_lstai_prob{m}.nii.gz")
        if os.path.exists(p):
            maps["lstai" + m] = p
    out["maps"] = {}
    for k, p in maps.items():
        if not os.path.exists(p):
            out["problems"].append(f"missing {k}")
            continue
        d, im = info(p)
        if tuple(im.shape) != tuple(gim.shape):
            out["problems"].append(f"{k} shape {im.shape} != gt {gim.shape}")
        if not np.allclose(im.affine, gim.affine, atol=1e-4):
            out["problems"].append(f"{k} affine differs from gt")
        if d["dtype"] != "uint8":
            out["problems"].append(f"{k} dtype {d['dtype']}")
        if not (d["min"] >= 0.0 and d["max"] <= 1.0 + 1e-6):
            out["problems"].append(f"{k} values outside [0, 1]")
        out["maps"][k] = d
    # reproduction of the August fold-0 maps (MSLesSeg, Ljubljana)
    for coh, old_dir in OLD_DIRS.items():
        if out["cohort"] == coh:
            old = os.path.join(old_dir, f"{case}_prob.nii.gz")
            if os.path.exists(old):
                a_old = np.asarray(nib.load(old).dataobj, dtype=np.float32)
                a_new = np.asarray(nib.load(maps["f0"]).get_fdata(dtype=np.float32))   # scl_slope applied
                if a_old.shape == a_new.shape:
                    diff = np.abs(a_old - a_new)
                    out["fold0_vs_august"] = {
                        "max_abs_diff": round(float(diff.max()), 5),
                        "frac_voxels_diff_gt_0.01": float((diff > 0.01).mean()),
                        "voxels_ge_0.5_old": int((a_old >= 0.5).sum()),
                        "voxels_ge_0.5_new": int((a_new >= 0.5).sum()),
                        "voxels_ge_0.5_disagree": int(((a_old >= 0.5) != (a_new >= 0.5)).sum())}
                else:
                    out["fold0_vs_august"] = {"shape_mismatch": [list(a_old.shape), list(a_new.shape)]}
    return out


def one_control(prefix):
    out = {"case": os.path.basename(prefix), "problems": []}
    p, g = prefix + "_prob.nii.gz", prefix + "_gt.nii.gz"
    d, im = info(p)
    dg, gim = info(g)
    out["prob"], out["gt"] = d, dg
    if tuple(im.shape) != tuple(gim.shape) or not np.allclose(im.affine, gim.affine, atol=1e-4):
        out["problems"].append("prob/gt grid mismatch")
    if dg["nonzero"] != 0:
        out["problems"].append("control gt has lesion voxels")
    return out


def main():
    t0 = time.time()
    cases = sorted({re.sub(r"_(f[0-4]_prob|gt)\.nii\.gz$", "", os.path.basename(p))
                    for p in glob.glob(os.path.join(CLOUD, "flames", "*.nii.gz"))})
    with Pool(8) as pool:
        rows = pool.map(one_case, cases)
        ctrl = pool.map(one_control, sorted({p[:-len("_prob.nii.gz")] for p in
                                             glob.glob(os.path.join(CONTROLS_DIR, "*_prob.nii.gz"))}))
    manifests = {os.path.basename(p): sha256(p) for p in sorted(glob.glob(os.path.join(CLOUD, "manifests", "*.json")))}
    # cohort summary
    summ = {}
    for r in rows:
        s = summ.setdefault(r["cohort"], {"scans": 0, "patients": set(), "slice_spacing_mm": [],
                                         "voxel_volume_mm3": [], "with_lstai": 0, "problems": 0})
        s["scans"] += 1
        s["patients"].add(r["patient"])
        s["slice_spacing_mm"].append(r["slice_spacing_mm"])
        s["voxel_volume_mm3"].append(r["voxel_volume_mm3"])
        s["with_lstai"] += int("lstai" in r["maps"])
        s["problems"] += int(bool(r["problems"]))
    for k, s in summ.items():
        s["patients"] = len(s["patients"])
        z = np.array(s["slice_spacing_mm"]); v = np.array(s["voxel_volume_mm3"])
        s["slice_spacing_mm"] = {"min": float(z.min()), "median": float(np.median(z)), "max": float(z.max())}
        s["voxel_volume_mm3"] = {"min": float(v.min()), "median": float(np.median(v)), "max": float(v.max())}
    rep = [r["fold0_vs_august"] for r in rows if "fold0_vs_august" in r]
    reproduction = {"scans_compared": len(rep),
                    "max_abs_diff_max": max(x.get("max_abs_diff", np.nan) for x in rep) if rep else None,
                    "scans_with_any_threshold_disagreement": sum(x.get("voxels_ge_0.5_disagree", 1) > 0 for x in rep),
                    "total_threshold_disagree_voxels": int(sum(x.get("voxels_ge_0.5_disagree", 0) for x in rep))}
    rec = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "cloud_dir": "data/cohorts/cloud-2026-10",
           "controls_dir": "data/cohorts/sibbms-controls-flames",
           "openms_flames_clean_patients": openms_clean_ids(),
           "cohort_summary": summ, "fold0_reproduction_vs_august": reproduction,
           "manifests_sha256": manifests,
           "scans_with_problems": [{"case": r["case"], "problems": r["problems"]} for r in rows if r["problems"]],
           "controls_with_problems": [{"case": c["case"], "problems": c["problems"]} for c in ctrl if c["problems"]],
           "cases": rows, "controls": ctrl, "runtime_s": round(time.time() - t0, 1)}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    print(json.dumps({k: rec[k] for k in ("cohort_summary", "fold0_reproduction_vs_august",
                                         "scans_with_problems", "controls_with_problems", "runtime_s")}, indent=1))
    print(f"controls: {len(ctrl)}; wrote {OUT}")


if __name__ == "__main__":
    main()
