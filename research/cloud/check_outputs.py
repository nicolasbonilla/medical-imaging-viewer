"""LOCAL ONLY (no cloud calls): pass/fail checks on pilot outputs downloaded from the bucket.

    python research/cloud/check_outputs.py controls --controls-dir <D>/controls/sibbms \
        --folds-dir <D>/flames-ensemble/cohort --august-dir data/cohorts/sibbms-controls-flames \
        --cases sub-001 sub-021
    python research/cloud/check_outputs.py lstai --lstai-dir <D>/lstai/cohort \
        --ref-dirs data/cohorts/mslesseg-flames data/cohorts/openms-flames <D>/flames-ensemble/cohort \
        --cases mslesseg_P10_T1 sub-001

FAIL = structural (missing file, grid/affine mismatch, values outside [0, 1], non-binary mask,
image outside the mask, August parity broken). WARN = plausibility for a human to look at.
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import job_common as jc  # noqa: E402

UINT8_TOL = 1.0 / 510.0 + 1e-6


def _load(path):
    import nibabel as nib
    img = nib.load(path)
    return img, np.asarray(img.get_fdata(dtype=np.float32))


def _first(paths):
    return next((p for p in paths if os.path.exists(p)), None)


def check_control(case, controls_dir, folds_dir, august_dir=None, folds=(0, 1, 2, 3, 4)):
    fails, warns, info = [], [], {"case": case}
    p = {k: os.path.join(controls_dir, f"{case}_{k}.nii.gz") for k in ("FLAIR", "T1", "brainmask")}
    missing = [k for k, v in p.items() if not os.path.exists(v)]
    if missing:
        return {**info, "fails": [f"missing {missing}"], "warns": [], "pass": False}
    fl_img, fl = _load(p["FLAIR"])
    t1_img, t1 = _load(p["T1"])
    m_img, m = _load(p["brainmask"])
    for k, img in (("T1", t1_img), ("brainmask", m_img)):
        if not jc.same_grid(img.shape, img.affine, fl_img.shape, fl_img.affine):
            fails.append(f"{k} grid differs from FLAIR")
    if fails:
        return {**info, "fails": fails, "warns": warns, "pass": False}
    if not set(np.unique(m)).issubset({0.0, 1.0}):
        fails.append("brain mask is not binary")
    mask = m > 0
    info["brain_ml"] = round(float(mask.sum()) * float(np.prod(fl_img.header.get_zooms()[:3])) / 1000.0, 1)
    if not 900 <= info["brain_ml"] <= 2000:
        warns.append(f"brain volume {info['brain_ml']} mL outside 900-2000")
    for k, arr in (("FLAIR", fl), ("T1", t1)):
        if np.count_nonzero(arr[~mask]):
            fails.append(f"{k} has non-zero voxels outside the brain mask")
    info["zooms"] = [float(z) for z in fl_img.header.get_zooms()[:3]]
    for k in folds:
        fp = os.path.join(folds_dir, f"{case}_f{k}_prob.nii.gz")
        if not os.path.exists(fp):
            fails.append(f"fold {k} map missing")
            continue
        img, pr = _load(fp)
        if not jc.same_grid(img.shape, img.affine, fl_img.shape, fl_img.affine):
            fails.append(f"fold {k} grid differs from FLAIR")
        elif pr.min() < -1e-6 or pr.max() > 1 + 1e-6:
            fails.append(f"fold {k} values outside [0,1]")
        if k == 0 and august_dir:
            ap = os.path.join(august_dir, f"{case}_prob.nii.gz")
            if os.path.exists(ap):
                aimg, aug = _load(ap)
                if aug.shape != pr.shape:
                    fails.append("fold 0 shape differs from the August map")
                else:
                    info["august_max_abs_diff"] = round(float(np.abs(aug - pr).max()), 5)
                    info["august_dice_0.5"] = round(jc.dice(aug > 0.5, pr > 0.5), 4)
                    if info["august_dice_0.5"] < 0.95:
                        fails.append(f"fold 0 vs August Dice {info['august_dice_0.5']} < 0.95")
                    elif info["august_max_abs_diff"] > 0.0025:
                        warns.append(f"fold 0 vs August max diff {info['august_max_abs_diff']} > 0.0025 "
                                     "(beyond uint8 rounding: HD-BET mask or software differs)")
            else:
                info["august"] = "not an August control"
    return {**info, "fails": fails, "warns": warns, "pass": not fails}


def check_lstai(case, lstai_dir, ref_dirs):
    fails, warns, info = [], [], {"case": case}
    names = {"ens": f"{case}_lstai_prob.nii.gz", **{j: f"{case}_lstai_prob_m{j}.nii.gz" for j in (1, 2, 3)}}
    paths = {k: os.path.join(lstai_dir, v) for k, v in names.items()}
    missing = [names[k] for k, v in paths.items() if not os.path.exists(v)]
    if missing:
        return {**info, "fails": [f"missing {missing}"], "warns": [], "pass": False}
    ref = _first([os.path.join(d, f) for d in ref_dirs
                  for f in (f"{case}_prob.nii.gz", f"{case}_f0_prob.nii.gz", f"{case}_prob_f0.nii.gz")])
    if not ref:
        return {**info, "fails": ["no FLAMeS reference map found in --ref-dirs"], "warns": [], "pass": False}
    rimg, _ = _load(ref)
    info["reference"] = ref
    arrs = {}
    for k, p in paths.items():
        img, arr = _load(p)
        if not jc.same_grid(img.shape, img.affine, rimg.shape, rimg.affine):
            fails.append(f"{names[k]}: grid differs from the FLAMeS map")
            continue
        if arr.min() < -1e-6 or arr.max() > 1 + 1e-6:
            fails.append(f"{names[k]}: values outside [0,1]")
        arrs[k] = arr
    if len(arrs) == 4:
        dev = float(np.abs(arrs["ens"] - (arrs[1] + arrs[2] + arrs[3]) / 3.0).max())
        info["ensemble_minus_mean3_max_abs"] = round(dev, 5)
        if dev > 4 * UINT8_TOL:
            fails.append(f"ensemble != mean of the 3 U-Nets (max diff {dev:.4f})")
        les = arrs["ens"] > 0.5
        info["lesion_ml_at_0.5"] = round(float(les.sum()) * float(np.prod(rimg.header.get_zooms()[:3])) / 1000.0, 2)
        gt = _first([os.path.join(os.path.dirname(ref), f"{case}_gt.nii.gz")]
                    + [os.path.join(d, f"{case}_gt.nii.gz") for d in ref_dirs])
        if gt:
            _, g = _load(gt)
            if g.shape == les.shape and g.any():
                info["dice_vs_gt_0.5"] = round(jc.dice(les, g > 0), 4)
                if info["dice_vs_gt_0.5"] < 0.2:
                    warns.append(f"Dice vs expert mask {info['dice_vs_gt_0.5']} < 0.2 (orientation?)")
            elif g.shape == les.shape and info["lesion_ml_at_0.5"] > 5:
                warns.append(f"healthy control with {info['lesion_ml_at_0.5']} mL above 0.5")
    return {**info, "fails": fails, "warns": warns, "pass": not fails}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="what", required=True)
    c = sub.add_parser("controls")
    c.add_argument("--controls-dir", required=True)
    c.add_argument("--folds-dir", required=True)
    c.add_argument("--august-dir", default=None)
    c.add_argument("--cases", nargs="+", required=True)
    s = sub.add_parser("lstai")
    s.add_argument("--lstai-dir", required=True)
    s.add_argument("--ref-dirs", nargs="+", required=True)
    s.add_argument("--cases", nargs="+", required=True)
    for p in (c, s):
        p.add_argument("--out", default=None, help="write the full report as JSON")
    a = ap.parse_args()
    if a.what == "controls":
        rows = [check_control(x, a.controls_dir, a.folds_dir, a.august_dir) for x in a.cases]
    else:
        rows = [check_lstai(x, a.lstai_dir, a.ref_dirs) for x in a.cases]
    for r in rows:
        extra = {k: v for k, v in r.items() if k not in ("case", "fails", "warns", "pass")}
        print(f"{'PASS' if r['pass'] else 'FAIL'} {r['case']}  {json.dumps(extra)}")
        for f in r["fails"]:
            print(f"    FAIL: {f}")
        for w in r["warns"]:
            print(f"    WARN: {w}")
    if a.out:
        json.dump(rows, open(a.out, "w"), indent=1)
    sys.exit(0 if all(r["pass"] for r in rows) else 1)


if __name__ == "__main__":
    main()
