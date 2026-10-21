#!/usr/bin/env python3
"""Paper A v0.3 — candidate extraction and one-to-one lesion matching for every arm
(PROTOCOL-v0.3 §3-§4). Writes the git-ignored cache research/paper_a/.cache/v03_candidates.pkl
and a small record with its SHA-256 plus gate G1 (fold-0 arm reproduces v0.2's cached candidates
on MSLesSeg and the 10 FLAMeS-clean Ljubljana scans).

Arms per case:
  ens          voxelwise mean of the 5 FLAMeS folds (primary); also per-fold candidate means
  f0 .. f4     single FLAMeS folds (f0 = the v0.2 pipeline)
  lstai, lstai_m1   LST-AI ensemble / sub-model 1 (MSLesSeg, Ljubljana only)
Controls (SibBMS): f0 only (August fold-0 maps).

Candidate = 18-connected component of {p >= 0.5} with physical volume >= 3 mm^3; score = mean
probability. Expert lesions = 18-connected components of the mask, detectable if >= 3 mm^3,
clinical if >= 14.14 mm^3. Matching = Hungarian maximum IoU, lenient IoU > 0 (mg0) and strict
IoU >= 0.10 (mg1, implemented as v0.2: IoU > 0.10).

    python research/paper_a/v03_candidates.py [--workers 8]
"""
import argparse
import glob
import hashlib
import json
import os
import pickle
import sys
import time
from multiprocessing import Pool

import nibabel as nib
import numpy as np
from scipy import ndimage as ndi
from scipy.optimize import linear_sum_assignment

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from v03_data import (CLOUD, CONTROLS_DIR, RECORDS, ROOT, case_cohort, flames_clean,   # noqa: E402
                      patient_of)

THRESHOLD, MIN_VOL_MM3, CLIN_MM3 = 0.5, 3.0, 14.14
STRUCT = ndi.generate_binary_structure(3, 2)            # 18-connectivity
CACHE_DIR = os.path.join(HERE, ".cache")
CACHE = os.path.join(CACHE_DIR, "v03_candidates.pkl")
OUT = os.path.join(RECORDS, "2026-10-21_paper_a_v03_candidates.json")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load(path):
    return np.asarray(nib.load(path).get_fdata(dtype=np.float32))


def expert_lesions(gt, vox_mm3):
    lab, n = ndi.label(gt > 0, structure=STRUCT)
    counts = np.bincount(lab.ravel(), minlength=n + 1)
    vol = counts * vox_mm3
    valid = np.array([g for g in range(1, n + 1) if vol[g] >= MIN_VOL_MM3 - 1e-9], int)
    return lab, counts, valid, vol


def match(cand_lab, cand_ids, cand_counts, gt_lab, gt_counts, valid_gt, thr):
    """One-to-one Hungarian max-IoU matching; returns matched expert-lesion id per candidate (0 = false)."""
    out = np.zeros(len(cand_ids), int)
    if len(cand_ids) == 0 or valid_gt.size == 0:
        return out
    both = (cand_lab > 0) & (gt_lab > 0)
    c, g = cand_lab[both], gt_lab[both]
    if c.size == 0:
        return out
    key = c.astype(np.int64) * (int(gt_lab.max()) + 1) + g
    uk, inter = np.unique(key, return_counts=True)
    cc, gg = uk // (int(gt_lab.max()) + 1), uk % (int(gt_lab.max()) + 1)
    cidx = {int(x): i for i, x in enumerate(cand_ids)}
    gidx = {int(x): j for j, x in enumerate(valid_gt)}
    iou = np.zeros((len(cand_ids), valid_gt.size))
    for a, b, k in zip(cc, gg, inter):
        a, b = int(a), int(b)
        if a not in cidx or b not in gidx:
            continue
        v = k / (cand_counts[a] + gt_counts[b] - k)
        if v > thr:
            iou[cidx[a], gidx[b]] = v
    ri, ci = linear_sum_assignment(-iou)
    for i, j in zip(ri, ci):
        if iou[i, j] > thr:
            out[i] = int(valid_gt[j])
    return out


def candidates(prob, vox_mm3, gt_lab, gt_counts, valid_gt, extra_maps=None):
    lab, n = ndi.label(prob >= THRESHOLD, structure=STRUCT)
    counts = np.bincount(lab.ravel(), minlength=n + 1)
    ids = np.array([i for i in range(1, n + 1) if counts[i] * vox_mm3 >= MIN_VOL_MM3 - 1e-9], int)
    res = {"n": int(ids.size), "vol_mm3": (counts[ids] * vox_mm3).astype(np.float32) if ids.size else np.zeros(0, np.float32)}
    res["score"] = np.asarray(ndi.mean(prob, lab, ids), float) if ids.size else np.zeros(0)
    res["max"] = np.asarray(ndi.maximum(prob, lab, ids), float) if ids.size else np.zeros(0)
    if extra_maps is not None:
        res["fold_means"] = (np.stack([np.asarray(ndi.mean(m, lab, ids), float) for m in extra_maps], 1)
                             if ids.size else np.zeros((0, len(extra_maps))))
    res["mg0"] = match(lab, ids, counts, gt_lab, gt_counts, valid_gt, 0.0)
    res["mg1"] = match(lab, ids, counts, gt_lab, gt_counts, valid_gt, 0.10)
    return res


def one_case(case):
    t0 = time.time()
    fl = os.path.join(CLOUD, "flames")
    gimg = nib.load(os.path.join(fl, f"{case}_gt.nii.gz"))
    zooms = [float(z) for z in gimg.header.get_zooms()[:3]]
    vox = float(np.prod(zooms))
    gt = np.asarray(gimg.dataobj) > 0
    gt_lab, gt_counts, valid, vol = expert_lesions(gt, vox)
    rec = {"case": case, "cohort": case_cohort(case), "patient": patient_of(case),
           "flames_clean": flames_clean(case), "zooms": zooms, "slice_mm": max(zooms), "vox_mm3": vox,
           "gt_ids": valid, "gt_vol_mm3": vol[valid].astype(np.float32), "arms": {}}
    folds = [load(os.path.join(fl, f"{case}_f{k}_prob.nii.gz")) for k in range(5)]
    ens = np.mean(folds, axis=0)
    rec["arms"]["ens"] = candidates(ens, vox, gt_lab, gt_counts, valid, extra_maps=folds)
    for k in range(5):
        rec["arms"][f"f{k}"] = candidates(folds[k], vox, gt_lab, gt_counts, valid)
    del folds, ens
    for arm, suf in (("lstai", ""), ("lstai_m1", "_m1")):
        p = os.path.join(CLOUD, "lstai", f"{case}_lstai_prob{suf}.nii.gz")
        if os.path.exists(p):
            rec["arms"][arm] = candidates(load(p), vox, gt_lab, gt_counts, valid)
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


def one_control(prefix):
    case = os.path.basename(prefix)
    img = nib.load(prefix + "_prob.nii.gz")
    zooms = [float(z) for z in img.header.get_zooms()[:3]]
    vox = float(np.prod(zooms))
    gt = np.asarray(nib.load(prefix + "_gt.nii.gz").dataobj) > 0
    gt_lab, gt_counts, valid, vol = expert_lesions(gt, vox)
    assert valid.size == 0
    rec = {"case": "sibbms_" + case, "cohort": "sibbms", "patient": "sibbms_" + case, "flames_clean": True,
           "zooms": zooms, "slice_mm": max(zooms), "vox_mm3": vox, "gt_ids": valid,
           "gt_vol_mm3": np.zeros(0, np.float32), "arms": {}}
    rec["arms"]["f0"] = candidates(load(prefix + "_prob.nii.gz"), vox, gt_lab, gt_counts, valid)
    return rec


def gate_g1(cases):
    """Fold-0 arm vs the v0.2 cache (.multisite_adv_cache.npz) on MSLesSeg + clean Ljubljana."""
    cdir = os.environ.get("PAPER_A_CACHE_DIR", os.path.join(ROOT, "scripts", "calm-ms"))
    path = os.path.join(cdir, ".multisite_adv_cache.npz")
    if not os.path.exists(path):
        path = os.path.abspath(os.path.join(ROOT, "..", "..", "..", "scripts", "calm-ms", ".multisite_adv_cache.npz"))
    old = {c["case"]: c for c in np.load(path, allow_pickle=True)["cases"]}
    by = {c["case"]: c for c in cases}
    n_scans = same_n = 0
    n_cand = same_lab0 = same_lab1 = 0
    max_dscore = 0.0
    max_dscore_outside = 0.0
    diffs = []
    inv0 = json.load(open(os.path.join(RECORDS, "2026-10-21_paper_a_v03_inventory.json"), encoding="utf-8"))
    allowed0 = {r["case"] for r in inv0["cases"] if r.get("fold0_vs_august", {}).get("voxels_ge_0.5_disagree", 0) > 0}
    gt_same = 0
    bad = []
    for case, o in old.items():
        if case not in by or not by[case]["flames_clean"]:
            continue
        a = by[case]["arms"]["f0"]
        n_scans += 1
        gt_same += int(len(by[case]["gt_ids"]) == int(o["n_gt"]))
        if a["n"] != len(o["scores"]):
            bad.append({"case": case, "n_new": a["n"], "n_v02": len(o["scores"])})
            continue
        same_n += 1
        n_cand += a["n"]
        if a["n"]:
            dd = np.abs(a["score"] - np.asarray(o["scores"]))
            diffs.append(dd)
            max_dscore = max(max_dscore, float(dd.max()))
            if case not in allowed0:
                max_dscore_outside = max(max_dscore_outside, float(dd.max()))
            same_lab0 += int(((a["mg0"] > 0) == (np.asarray(o["mg0"]) > 0)).sum())
            same_lab1 += int(((a["mg1"] > 0) == (np.asarray(o["mg1"]) > 0)).sum())
    res = {"v02_cache": os.path.basename(path), "v02_cache_sha256": sha256(path), "scans_compared": n_scans,
           "scans_same_candidate_count": same_n, "scans_same_detectable_gt_count": gt_same,
           "candidates_compared": n_cand,
           "lenient_label_agreement": round(same_lab0 / n_cand, 5) if n_cand else None,
           "strict_label_agreement": round(same_lab1 / n_cand, 5) if n_cand else None,
           "max_abs_score_diff": round(max_dscore, 5),
           "max_abs_score_diff_outside_threshold_voxel_scans": round(max_dscore_outside, 5),
           "score_diff_quantiles_50_99_99.9_100": [round(float(q), 5) for q in
                                                    np.quantile(np.concatenate(diffs), [0.5, 0.99, 0.999, 1.0])] if diffs else None,
           "candidates_score_diff_gt_0.003": int(sum((d > 0.003).sum() for d in diffs)),
           "count_mismatches": bad}
    # PROTOCOL-v0.3 §13 entry 4: count mismatches allowed only in scans where the inventory found
    # voxels crossing 0.5 between the August and the new fold-0 maps.
    inv = json.load(open(os.path.join(RECORDS, "2026-10-21_paper_a_v03_inventory.json"), encoding="utf-8"))
    allowed = sorted(r["case"] for r in inv["cases"]
                     if r.get("fold0_vs_august", {}).get("voxels_ge_0.5_disagree", 0) > 0)
    res["scans_with_threshold_voxel_disagreement"] = allowed
    res["passed_as_preregistered"] = bool(n_scans and all(b["case"] in allowed for b in bad)
                                          and (res["lenient_label_agreement"] or 0) >= 0.99 and max_dscore <= 0.003)
    # PROTOCOL-v0.3 §13 entry 5: criterion (c) applied outside the 5 threshold-voxel scans
    res["passed_with_deviation_5"] = bool(n_scans and all(b["case"] in allowed for b in bad)
                                          and (res["lenient_label_agreement"] or 0) >= 0.99
                                          and max_dscore_outside <= 0.003)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--gate-only", action="store_true", help="re-evaluate G1 from the existing cache")
    args = ap.parse_args()
    t0 = time.time()
    if args.gate_only:
        d = pickle.load(open(CACHE, "rb"))
        recs, crecs = d["cases"], d["controls"]
    else:
        cases = sorted({os.path.basename(p)[:-len("_gt.nii.gz")]
                        for p in glob.glob(os.path.join(CLOUD, "flames", "*_gt.nii.gz"))})
        ctrls = sorted({p[:-len("_prob.nii.gz")] for p in glob.glob(os.path.join(CONTROLS_DIR, "*_prob.nii.gz"))})
        with Pool(args.workers) as pool:
            recs = pool.map(one_case, cases, chunksize=1)
            crecs = pool.map(one_control, ctrls, chunksize=1)
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE, "wb") as fh:
            pickle.dump({"cases": recs, "controls": crecs}, fh, protocol=4)
    g1 = gate_g1(recs)
    summary = {}
    for r in recs + crecs:
        s = summary.setdefault(r["cohort"], {"scans": 0, "scans_flames_clean": 0})
        s["scans"] += 1
        s["scans_flames_clean"] += int(r["flames_clean"])
    rec = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "protocol": "docs/research/paper/PROTOCOL-v0.3.md",
           "cache": os.path.relpath(CACHE, ROOT).replace("\\", "/"), "cache_sha256": sha256(CACHE),
           "rule": {"threshold": THRESHOLD, "min_vol_mm3": MIN_VOL_MM3, "clinical_mm3": CLIN_MM3,
                    "connectivity": 18, "match": "Hungarian max-IoU; lenient IoU>0, strict IoU>0.10"},
           "scans_by_cohort": summary, "gate_G1": g1, "runtime_s": round(time.time() - t0, 1)}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
