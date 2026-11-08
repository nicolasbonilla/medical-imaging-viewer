#!/usr/bin/env python3
"""Paper A v0.3 controls addendum — input inventory (gate C0). NO OUTCOME IS COMPUTED HERE.

Opens the 100 SibBMS healthy-control inputs (FLAMeS folds 0-4, all-zero lesion mask, HD-BET brain
mask), records SHA-256, grid, dtype and NIfTI scaling of every file, and checks:
  * every fold map and the brain mask share the lesion mask's grid; the lesion mask is all zero;
  * fold maps decode (scl_slope) into [0, 1] (boolean only: no maximum, no count of voxels >= 0.5
    is recorded for the 70 controls never analysed before);
  * the 30 controls analysed in v0.1-v0.3 (August fold-0 maps, sub-001..020, sub-031..040):
    new fold 0 vs August fold 0 (max |dp|, voxels changing side of 0.5) — a reproduction check on
    data whose fold-0 outcome is already known (v0.3 Table 7);
  * the grid passes the app's MNI-grid check (`looks_mni`, RC-032), so the app's atlas-based DIS
    code path can run; overlap of the MNI-space MSMask atlas with each HD-BET brain mask
    (template-alignment check);
  * FLAMeS training fingerprint (668 entries shipped with the weights): entries whose spacing and
    non-zero bounding box are compatible with a SibBMS control (supporting evidence for the
    contamination check; the primary evidence is the FLAMeS paper's Table 1).

    python research/paper_a/v03c_inventory.py --data <dir with cohort/, brainmask/, manifests/> \
        --fingerprint <dataset_fingerprint.json>

Must run with the offline environment if the app modules are imported (they are, for looks_mni and
the MSMask atlas): GOOGLE_APPLICATION_CREDENTIALS=<missing file>, CLOUDSDK_CONFIG=<empty dir>,
GOOGLE_CLOUD_PROJECT=mstool-offline-tests.
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import time

import nibabel as nib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from v03_data import CONTROLS_DIR, RECORDS, ROOT  # noqa: E402

OUT = os.path.join(RECORDS, "2026-10-24_paper_a_v03c_inventory.json")
CASES = [f"sub-{i:03d}" for i in range(1, 101)]
AUGUST = [f"sub-{i:03d}" for i in list(range(1, 21)) + list(range(31, 41))]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def same_grid(a, b, tol=1e-4):
    return a.shape[:3] == b.shape[:3] and np.allclose(a.affine, b.affine, atol=tol)


def bbox_shape(mask):
    idx = np.nonzero(mask)
    return [int(i.max() - i.min() + 1) for i in idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--fingerprint", required=True)
    a = ap.parse_args()
    t0 = time.time()
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    from app.services import ms_region_classifier as rc               # app code, read-only use

    coh, bm_dir = os.path.join(a.data, "cohort"), os.path.join(a.data, "brainmask")
    rows, fails = [], []
    grids = set()
    atlas_zone = None
    for case in CASES:
        r = {"case": case, "files": {}}
        gpath = os.path.join(coh, f"{case}_gt.nii.gz")
        gimg = nib.load(gpath)
        r["files"]["gt"] = sha256(gpath)
        gt = np.asarray(gimg.dataobj)
        r["gt_all_zero"] = bool(not np.any(gt))
        r["zooms"] = [float(z) for z in gimg.header.get_zooms()[:3]]
        r["shape"] = list(gimg.shape[:3])
        grids.add((tuple(gimg.shape[:3]), tuple(np.round(gimg.affine, 4).ravel())))
        if not r["gt_all_zero"]:
            fails.append(f"{case}: lesion mask not all zero")
        for k in range(5):
            p = os.path.join(coh, f"{case}_f{k}_prob.nii.gz")
            img = nib.load(p)
            r["files"][f"f{k}"] = sha256(p)
            if not same_grid(img, gimg):
                fails.append(f"{case} f{k}: grid differs from lesion mask")
            arr = np.asarray(img.get_fdata(dtype=np.float32))
            if k == 0:
                r["dtype_on_disk"] = str(img.get_data_dtype())
                r["scl_slope"] = None if img.dataobj.slope is None else float(img.dataobj.slope)
            in01 = bool(arr.min() >= -1e-6 and arr.max() <= 1 + 1e-6)
            if not in01:
                fails.append(f"{case} f{k}: values outside [0, 1]")
            r.setdefault("maps_in_0_1", []).append(in01)
            if k == 0 and case in AUGUST:
                ap_ = os.path.join(CONTROLS_DIR, f"{case}_prob.nii.gz")
                aimg = nib.load(ap_)
                aug = np.asarray(aimg.get_fdata(dtype=np.float32))
                r["fold0_vs_august"] = {
                    "august_sha256": sha256(ap_), "same_grid": same_grid(aimg, gimg),
                    "max_abs_diff": round(float(np.abs(aug - arr).max()), 5) if aug.shape == arr.shape else None,
                    "voxels_ge_0.5_disagree": int(((aug >= 0.5) != (arr >= 0.5)).sum()) if aug.shape == arr.shape else None}
            del arr
        bpath = os.path.join(bm_dir, f"{case}_brainmask.nii.gz")
        bimg = nib.load(bpath)
        r["files"]["brainmask"] = sha256(bpath)
        if not same_grid(bimg, gimg):
            fails.append(f"{case}: brain mask grid differs")
        bm = np.asarray(bimg.dataobj) > 0
        vox = float(np.prod(r["zooms"]))
        r["brain_ml"] = round(float(bm.sum()) * vox / 1000.0, 1)
        r["brain_bbox_nifti"] = bbox_shape(bm)
        r["looks_mni"] = bool(rc.looks_mni(gimg.affine, gimg.shape[:3]))
        if atlas_zone is None and r["looks_mni"]:
            zr = rc.generate_zone_map_atlas(gimg, tuple(r["zooms"]))
            atlas_zone = np.asarray(zr["zone_mask"])           # NIfTI (a0, a1, k) order
            atlas_brain = _atlas_brain(rc, gimg)
        if atlas_zone is not None:
            inter = float((atlas_brain & bm).sum())
            r["atlas_vs_brainmask"] = {"dice": round(2 * inter / (atlas_brain.sum() + bm.sum()), 4),
                                       "brainmask_covered_by_atlas": round(inter / bm.sum(), 4),
                                       "atlas_covered_by_brainmask": round(inter / atlas_brain.sum(), 4),
                                       "wm_zones_covered_by_brainmask": round(float((bm & (atlas_zone > 0)).sum()) /
                                                                              float((atlas_zone > 0).sum()), 4)}
        rows.append(r)
        print(case, "ok" if not any(f.startswith(case) for f in fails) else "FAIL", flush=True)

    # FLAMeS training fingerprint: entries compatible with a SibBMS control?
    fp = json.load(open(a.fingerprint, encoding="utf-8"))
    sp = np.array(fp["spacings"], float)
    sh = np.array(fp["shapes_after_crop"], int)
    grid_shape = list(rows[0]["shape"])
    zo = rows[0]["zooms"]
    iso = np.all(np.abs(sp - np.array(zo[::-1])) < 1e-3, axis=1)
    # axis order differs between training datasets -> compare SORTED box dimensions
    sh_sorted = np.sort(sh, axis=1)
    full_grid_like = [int(i) for i in np.nonzero(iso & np.all(np.abs(sh_sorted - np.sort(grid_shape)) <= 10, axis=1))[0]]
    near = []
    for r in rows:
        bb = np.sort(np.array(r["brain_bbox_nifti"]))
        d = np.abs(sh_sorted - bb).max(axis=1)
        hits = np.nonzero(iso & (d <= 2))[0]
        near.append({"case": r["case"], "entries_within_2_voxels_any_axis_order": [int(h) for h in hits]})
    ctrl_bb = np.array([r["brain_bbox_nifti"][::-1] for r in rows])
    fp_iso_bb = sh[iso]
    rec = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "purpose": "PROTOCOL-v0.3 controls addendum, gate C0 (inventory; no outcome computed)",
        "data_dir_layout": "cohort/sub-XXX_{gt,f0..f4_prob}.nii.gz (gs://mstool-research-data/flames-ensemble/cohort), "
                           "brainmask/sub-XXX_brainmask.nii.gz (gs://mstool-research-data/controls/sibbms)",
        "manifests_sha256": {os.path.relpath(p, a.data).replace("\\", "/"): sha256(p)
                             for p in sorted(glob.glob(os.path.join(a.data, "manifests", "*", "*.json")))},
        "n_controls": len(rows), "distinct_grids": len(grids),
        "grid": {"shape": grid_shape, "zooms": zo, "affine": np.round(nib.load(os.path.join(coh, "sub-001_gt.nii.gz")).affine, 4).tolist()},
        "looks_mni_all": all(r["looks_mni"] for r in rows),
        "brain_ml": {"min": min(r["brain_ml"] for r in rows), "median": float(np.median([r["brain_ml"] for r in rows])),
                     "max": max(r["brain_ml"] for r in rows)},
        "atlas_vs_brainmask_dice": None if atlas_zone is None else {
            "min": min(r["atlas_vs_brainmask"]["dice"] for r in rows),
            "median": float(np.median([r["atlas_vs_brainmask"]["dice"] for r in rows])),
            "max": max(r["atlas_vs_brainmask"]["dice"] for r in rows)},
        "wm_zones_covered_by_brainmask": None if atlas_zone is None else {
            "min": min(r["atlas_vs_brainmask"]["wm_zones_covered_by_brainmask"] for r in rows),
            "median": float(np.median([r["atlas_vs_brainmask"]["wm_zones_covered_by_brainmask"] for r in rows]))},
        "fold0_vs_august_30": {
            "n": sum(1 for r in rows if "fold0_vs_august" in r),
            "max_abs_diff": max(r["fold0_vs_august"]["max_abs_diff"] for r in rows if "fold0_vs_august" in r),
            "scans_with_voxels_crossing_0.5": [r["case"] for r in rows if r.get("fold0_vs_august", {}).get("voxels_ge_0.5_disagree")],
            "total_voxels_crossing_0.5": sum(r["fold0_vs_august"]["voxels_ge_0.5_disagree"] for r in rows if "fold0_vs_august" in r)},
        "flames_fingerprint": {
            "file_sha256": sha256(a.fingerprint), "entries": int(len(sp)),
            "entries_with_control_spacing": int(iso.sum()),
            "entries_with_crop_close_to_full_control_grid(+-10 vox)": full_grid_like,
            "controls_with_an_entry_within_2_voxels_of_brain_bbox_any_axis_order": sum(1 for x in near if x["entries_within_2_voxels_any_axis_order"]),
            "control_brain_bbox_sorted_median": np.median(np.sort(ctrl_bb, axis=1), axis=0).tolist(),
            "fingerprint_1mm_crop_sorted_median": np.median(np.sort(fp_iso_bb, axis=1), axis=0).tolist() if fp_iso_bb.size else None,
            "fingerprint_1mm_crop_sorted_max": np.sort(fp_iso_bb, axis=1).max(axis=0).tolist() if fp_iso_bb.size else None,
            "per_control": near,
            "note": "Supporting evidence only: SibBMS Output/Norm is distributed with skull, so a FLAMeS crop of a "
                    "SibBMS image would be either ~the full template grid (unstripped) or a brain box from the "
                    "authors' own stripping; HD-BET boxes need not match exactly."},
        "fails": fails, "passed": not fails, "cases": rows, "runtime_s": round(time.time() - t0, 1)}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    summary = {k: v for k, v in rec.items() if k not in ("cases",)}
    summary["flames_fingerprint"] = {k: v for k, v in rec["flames_fingerprint"].items() if k != "per_control"}
    print(json.dumps(summary, indent=1))


def _atlas_brain(rc, target_img):
    """MSMask atlas brain (labels 1-5) resampled to the target grid, nearest neighbour (same
    reference-affine rule as generate_zone_map_atlas for an MNI-like grid)."""
    from nilearn.image import resample_to_img
    from pathlib import Path
    path = Path(rc.__file__).resolve().parent.parent.parent / "data" / "msmask" / "sub-mni152_space-mni_msmask.nii.gz"
    at = nib.load(str(path))
    lab = nib.Nifti1Image((np.asarray(at.dataobj) > 0).astype(np.uint8), at.affine)
    ref = nib.Nifti1Image(np.zeros(target_img.shape[:3], np.uint8), target_img.affine)
    out = resample_to_img(lab, ref, interpolation="nearest", force_resample=True, copy_header=True)
    return np.asarray(out.dataobj) > 0


if __name__ == "__main__":
    main()
