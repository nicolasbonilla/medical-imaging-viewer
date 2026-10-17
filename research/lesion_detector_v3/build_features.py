#!/usr/bin/env python3
"""Lesion-detector v3 — build the per-candidate feature/label cache (PROTOCOL.md §3-§5).

Reads (read-only) the FLAMeS fold-0 probability maps + expert masks in <data-root>/cohorts and the
co-registered FLAIR/T1 in <data-root>/external, extracts candidates exactly as paper A does, labels
them (lenient + strict one-to-one Hungarian, any-voxel), and computes the v2 features (shipped
module) and every v3 family whose inputs exist. Ground truth is used ONLY for labels.

Optional cloud-run inputs plug in without code changes (PROTOCOL.md §5 placeholders):
  --folds-dir D   D/{case}_prob_f{k}.nii.gz, k = 0..4  -> F8 ensemble disagreement
                  (fold 0 must reproduce the existing {case}_prob.nii.gz: provenance check)
  --lstai-dir D   D/{case}_lstai_prob.nii.gz             -> F9 LST-AI agreement
  --control-flair-dir D  D/{case}_FLAIR.nii.gz (skull-stripped, prob grid) -> F1/F3/F4/F6 on controls

    python research/lesion_detector_v3/build_features.py --data-root C:/Users/Nicolas/medical-imaging-viewer/data

Writes research/lesion_detector_v3/.cache/features_v3.npz (gitignored) + features_v3_meta.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from multiprocessing import Pool

import numpy as np
import nibabel as nib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for p in (os.path.join(ROOT, "backend"), os.path.join(ROOT, "scripts", "calm-ms"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.services.calm_ms_inference import extract_lesion_candidates, label_candidates_tp   # noqa: E402
from app.services.calm_ms_lesion_features import (FEATURE_NAMES as V2_NAMES,                  # noqa: E402
                                                  candidate_feature_matrix)
from app.services.lesion_metrics import label_lesions, meets_min_volume                       # noqa: E402
import multisite_conformal_advanced as msa                                                    # noqa: E402
import features_v3 as fv                                                                      # noqa: E402

THRESHOLD, MIN_VOL, SCORE, SPACING = 0.5, 3.0, "mean", (1.0, 1.0, 1.0)
assert (THRESHOLD, MIN_VOL, SCORE) == (msa.THRESHOLD, msa.MIN_VOL, msa.SCORE), "paper-A candidate definition drifted"
CLINICAL_VOL_MM3 = 14.14
CACHE_DIR = os.path.join(HERE, ".cache")
N_FOLDS = 5

# FLAMeS training overlap of the 30 Ljubljana scans (docs/research/records/
# 2026-10-17_flames_fold_membership.json, branch research/paper-a-v0.2 @ 87e998d)
LJ_HELDOUT10 = (16, 17, 18, 19, 20, 26, 27, 28, 29, 30)     # never trained on by any FLAMeS fold
LJ_FOLD0_VALIDATION = (4, 7)                                 # clean for the fold-0 weights only


def ljubljana_status(pid: int) -> str:
    if pid in LJ_HELDOUT10:
        return "heldout10"
    if pid in LJ_FOLD0_VALIDATION:
        return "fold0_validation"
    return "flames_trained"


def enumerate_scans(data_root: str, control_flair_dir: str | None = None):
    coh = os.path.join(data_root, "cohorts")
    ms_root = os.path.join(data_root, "external", "mslesseg", "MSLesSeg Dataset")
    lj_root = os.path.join(data_root, "external", "open_ms_data", "cross_sectional", "MNI")
    scans = []
    for f in sorted(os.listdir(os.path.join(coh, "mslesseg-flames"))):
        if not f.endswith("_prob.nii.gz"):
            continue
        case = f[:-len("_prob.nii.gz")]
        m = re.fullmatch(r"mslesseg_P(\d+)(?:_T(\d+))?", case)
        if not m:
            raise ValueError(f"unparseable MSLesSeg case {case}")
        p, t = m.group(1), m.group(2)
        base = (os.path.join(ms_root, "train", f"P{p}", f"T{t}", f"P{p}_T{t}") if t
                else os.path.join(ms_root, "test", f"P{p}", f"P{p}"))
        scans.append({"case": case, "cohort": "mslesseg", "patient": f"mslesseg_P{p}", "status": "clean",
                      "prob": os.path.join(coh, "mslesseg-flames", f), "gt": os.path.join(coh, "mslesseg-flames", case + "_gt.nii.gz"),
                      "flair": base + "_FLAIR.nii.gz", "t1": base + "_T1.nii.gz"})
    for f in sorted(os.listdir(os.path.join(coh, "openms-flames"))):
        if not f.endswith("_prob.nii.gz"):
            continue
        case = f[:-len("_prob.nii.gz")]
        pid = int(re.fullmatch(r"openms_patient(\d+)", case).group(1))
        d = os.path.join(lj_root, f"patient{pid:02d}")
        scans.append({"case": case, "cohort": "openms", "patient": case, "status": ljubljana_status(pid),
                      "prob": os.path.join(coh, "openms-flames", f), "gt": os.path.join(coh, "openms-flames", case + "_gt.nii.gz"),
                      "flair": os.path.join(d, "FLAIR_N4_noneck_reduced_winsor_regtoFLAIR_brain_N4_regtoMNI.nii.gz"),
                      "t1": os.path.join(d, "T1_N4_noneck_reduced_winsor_regtoFLAIR_brain_N4_regtoMNI.nii.gz")})
    for f in sorted(os.listdir(os.path.join(coh, "sibbms-controls-flames"))):
        if not f.endswith("_prob.nii.gz"):
            continue
        case = f[:-len("_prob.nii.gz")]
        fl = os.path.join(control_flair_dir, case + "_FLAIR.nii.gz") if control_flair_dir else None
        scans.append({"case": case, "cohort": "sibbms", "patient": "sibbms_" + case, "status": "control",
                      "prob": os.path.join(coh, "sibbms-controls-flames", f),
                      "gt": os.path.join(coh, "sibbms-controls-flames", case + "_gt.nii.gz"),
                      "flair": fl if fl and os.path.exists(fl) else None, "t1": None})
    for s in scans:
        for k in ("prob", "gt", "flair", "t1"):
            if s[k] is not None and not os.path.exists(s[k]):
                if s["cohort"] == "sibbms":
                    s[k] = None
                else:
                    raise FileNotFoundError(f"{s['case']}: missing {k} {s[k]}")
    return scans


def _load(path, ref_img=None):
    img = nib.load(path)
    if ref_img is not None:
        if img.shape != ref_img.shape or not np.allclose(img.affine, ref_img.affine, atol=1e-3):
            raise ValueError(f"{path}: grid/affine differs from the probability map")
    return img, np.asarray(img.get_fdata(dtype=np.float32))


def _code_digest():
    """Per-scan results are cached under a digest of the feature/build code, so any code change
    invalidates them (no stale features can leak into a run)."""
    h = hashlib.sha256()
    for f in ("features_v3.py", "build_features.py"):
        h.update(open(os.path.join(HERE, f), "rb").read())
    return h.hexdigest()[:16]


def process(job):
    """Cached wrapper around _process (own derived data, local, gitignored)."""
    import pickle
    s, opts = job
    d = os.path.join(CACHE_DIR, "scans_" + opts["code_digest"] + ("_folds" if opts.get("folds_dir") else "")
                     + ("_lstai" if opts.get("lstai_dir") else "") + ("_cflair" if opts.get("control_flair_dir") else ""))
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, s["case"] + ".pkl")
    if os.path.exists(f):
        with open(f, "rb") as fh:
            return pickle.load(fh)
    res = _process(job)
    with open(f + ".tmp", "wb") as fh:
        pickle.dump(res, fh)
    os.replace(f + ".tmp", f)
    return res


def _process(job):
    s, opts = job
    t0 = time.time()
    pimg, P = _load(s["prob"])
    zooms = pimg.header.get_zooms()[:3]
    if not np.allclose(zooms, 1.0, atol=1e-3):
        raise ValueError(f"{s['case']}: non-1mm voxels {zooms}")
    if not np.isfinite(P).all():
        raise ValueError(f"{s['case']}: non-finite probability")
    _, G = _load(s["gt"], pimg)
    gt = G > 0
    del G
    flair = _load(s["flair"], pimg)[1] if s["flair"] else None
    t1 = _load(s["t1"], pimg)[1] if s["t1"] else None

    labeled, cands = extract_lesion_candidates(P, THRESHOLD, SPACING, min_volume_mm3=MIN_VOL, score=SCORE)
    gt_labeled, n_gt_raw = label_lesions(gt.astype(np.uint8))
    gt_counts = np.bincount(gt_labeled.ravel())
    valid_gt = {g for g in range(1, n_gt_raw + 1) if g < len(gt_counts) and meets_min_volume(int(gt_counts[g]), 1.0)}
    clin_gt = {g for g in valid_gt if int(gt_counts[g]) >= CLINICAL_VOL_MM3}
    res = {"case": s["case"], "cohort": s["cohort"], "patient": s["patient"], "status": s["status"],
           "n_cand": len(cands), "n_gt": len(valid_gt), "n_gt_clin": len(clin_gt)}
    if not cands:
        res.update({"feats": {}, "X_v2": np.zeros((0, len(V2_NAMES))), "score": np.zeros(0),
                    "mg0": np.zeros(0, int), "mg1": np.zeros(0, int), "anyvox": np.zeros(0, bool),
                    "mg0_clin": np.zeros(0, bool), "ctx": {}, "families": [], "seconds": round(time.time() - t0, 1)})
        return res
    m0 = msa._hungarian(labeled, cands, gt_labeled, gt_counts, valid_gt, 0.0)
    m1 = msa._hungarian(labeled, cands, gt_labeled, gt_counts, valid_gt, 0.10)
    anyv = label_candidates_tp(labeled, cands, gt, 0.0)
    del gt_labeled, gt

    fold_maps = None
    if opts.get("folds_dir"):
        paths = [os.path.join(opts["folds_dir"], f"{s['case']}_prob_f{k}.nii.gz") for k in range(N_FOLDS)]
        if all(os.path.exists(p) for p in paths):
            fold_maps = [_load(p, pimg)[1] for p in paths]
            dev = float(np.abs(fold_maps[0] - P).max())
            if dev > 1e-3:
                raise ValueError(f"{s['case']}: fold-0 map deviates from the cohort prob map by {dev}")
    lst = None
    if opts.get("lstai_dir"):
        p = os.path.join(opts["lstai_dir"], f"{s['case']}_lstai_prob.nii.gz")
        if os.path.exists(p):
            lst = _load(p, pimg)[1]
            if lst.min() < -1e-4 or lst.max() > 1 + 1e-4:
                raise ValueError(f"{s['case']}: LST-AI map outside [0, 1]")

    X_v2 = candidate_feature_matrix(P, labeled, cands)
    ctx = fv.ScanContext(P, flair, t1)
    feats = fv.candidate_features_v3(P, labeled, cands, ctx, fold_maps=fold_maps, lstai=lst)
    fams = [f for f, names in fv.FAMILIES.items() if names[0] in feats]
    res.update({"feats": feats, "X_v2": X_v2, "score": np.array([c.score for c in cands]),
                "mg0": np.array([m0[c.label][0] for c in cands], int),
                "mg1": np.array([m1[c.label][0] for c in cands], int),
                "anyvox": np.array([bool(anyv[c.label]) for c in cands]),
                "mg0_clin": np.array([m0[c.label][0] in clin_gt for c in cands]),
                "ctx": ctx.summary(), "families": fams, "seconds": round(time.time() - t0, 1)})
    return res


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=os.environ.get("CALM_DATA_ROOT", os.path.join(ROOT, "data")))
    ap.add_argument("--folds-dir", default=None)
    ap.add_argument("--lstai-dir", default=None)
    ap.add_argument("--control-flair-dir", default=None)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="debug: first N scans per cohort")
    ap.add_argument("--out", default=os.path.join(CACHE_DIR, "features_v3.npz"))
    a = ap.parse_args()

    scans = enumerate_scans(a.data_root, a.control_flair_dir)
    if a.limit:
        by = {}
        for s in scans:
            by.setdefault(s["cohort"], []).append(s)
        scans = [s for v in by.values() for s in v[:a.limit]]
    print(f"{len(scans)} scans: " + ", ".join(f"{c} {sum(s['cohort'] == c for s in scans)}" for c in ("mslesseg", "openms", "sibbms")))
    opts = {"folds_dir": a.folds_dir, "lstai_dir": a.lstai_dir, "control_flair_dir": a.control_flair_dir,
            "code_digest": _code_digest()}
    t0 = time.time()
    results = []
    with Pool(a.workers) as pool:
        for r in pool.imap(process, [(s, opts) for s in scans], chunksize=1):
            results.append(r)
            print(f"  [{len(results):3d}/{len(scans)}] {r['case']:24s} cand {r['n_cand']:4d} gt {r['n_gt']:4d} "
                  f"fam {','.join(r['families'])} {r['seconds']}s", flush=True)

    names_new = [k for k in fv.NEW_FEATURE_NAMES if any(k in r["feats"] for r in results)]
    names = list(V2_NAMES) + names_new
    rows, idx = [], []
    for si, r in enumerate(results):
        n = r["n_cand"]
        if not n:
            continue
        block = np.full((n, len(names)), np.nan)
        block[:, :len(V2_NAMES)] = r["X_v2"]
        for j, k in enumerate(names_new):
            if k in r["feats"]:
                block[:, len(V2_NAMES) + j] = r["feats"][k]
        rows.append(block)
        idx.append(np.full(n, si))
    X = np.vstack(rows)
    scan_idx = np.concatenate(idx)
    cat = lambda k: np.concatenate([r[k] for r in results if r["n_cand"]])   # noqa: E731
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    np.savez_compressed(
        a.out, X=X, names=np.array(names), scan_idx=scan_idx, score=cat("score"),
        mg0=cat("mg0"), mg1=cat("mg1"), anyvox=cat("anyvox"), mg0_clin=cat("mg0_clin"),
        scan_case=np.array([r["case"] for r in results]), scan_cohort=np.array([r["cohort"] for r in results]),
        scan_patient=np.array([r["patient"] for r in results]), scan_status=np.array([r["status"] for r in results]),
        scan_ncand=np.array([r["n_cand"] for r in results]), scan_ngt=np.array([r["n_gt"] for r in results]),
        scan_ngt_clin=np.array([r["n_gt_clin"] for r in results]))
    print(f"hashing inputs ...")
    hashes = {}
    for s in scans:
        for k in ("prob", "gt", "flair", "t1"):
            if s[k]:
                hashes[f"{s['case']}:{k}"] = sha256(s[k])
    digest = hashlib.sha256("".join(f"{k}={v};" for k, v in sorted(hashes.items())).encode()).hexdigest()
    meta = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "data_root": a.data_root, "n_scans": len(results),
            "n_candidates": int(X.shape[0]), "feature_names": names,
            "options": {"folds_dir": a.folds_dir, "lstai_dir": a.lstai_dir, "control_flair_dir": a.control_flair_dir},
            "candidate_definition": {"threshold": THRESHOLD, "min_volume_mm3": MIN_VOL, "score": SCORE,
                                     "connectivity": 18, "labels": "Hungarian one-to-one IoU>0 (mg0), IoU>0.10 (mg1), any-voxel"},
            "inputs_combined_sha256": digest, "inputs_sha256": hashes,
            "scan_context": {r["case"]: r["ctx"] for r in results},
            "families_per_scan": {r["case"]: r["families"] for r in results},
            "cache_sha256": sha256(a.out), "runtime_s": round(time.time() - t0, 1)}
    with open(a.out.replace(".npz", "_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    print(f"wrote {a.out} ({X.shape[0]} candidates x {X.shape[1]} features) in {meta['runtime_s']} s")


if __name__ == "__main__":
    main()
