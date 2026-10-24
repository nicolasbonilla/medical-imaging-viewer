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
  --cloud-root R  (v3.1, PROTOCOL-v3.1.md) the Oct-2026 cloud layout read in place:
                  R/flames/{case}_f{k}_prob.nii.gz + {case}_gt.nii.gz, R/lstai/{case}_lstai_prob[_m1..3].nii.gz;
                  adds the new held-out sites (ms3seg_, muslim_, pedims_) with their true voxel size.
                  Fold-0 parity tolerance 0.0025 (uint8 storage, max error 0.002).

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
FOLD0_TOL = 0.0025          # v3.1: cloud maps are uint8-stored (max error 0.002)
EXTERNAL_SITES = ("ms3seg", "muslim", "pedims")

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


def _external_patient(case: str) -> str:
    m = re.fullmatch(r"pedims_(P\d+)_T\d+", case)
    if m:
        return "pedims_" + m.group(1)                # longitudinal children: cluster by child
    if re.fullmatch(r"(ms3seg_\d+|muslim_\d+)", case):
        return case                                  # one scan per patient
    raise ValueError(f"unparseable external case {case}")


def attach_inputs(scans, folds_dir=None, lstai_dir=None, cloud_root=None):
    """Resolve the optional fold / LST-AI map paths of every scan (None when absent)."""
    for s in scans:
        c = s["case"]
        folds = None
        if s.get("ctl_root"):                       # v3.2: the 100 SibBMS controls (own folder)
            folds = [os.path.join(s["ctl_root"], "flames", f"{c}_f{k}_prob.nii.gz") for k in range(N_FOLDS)]
        elif cloud_root:
            folds = [os.path.join(cloud_root, "flames", f"{c}_f{k}_prob.nii.gz") for k in range(N_FOLDS)]
        elif folds_dir:
            folds = [os.path.join(folds_dir, f"{c}_prob_f{k}.nii.gz") for k in range(N_FOLDS)]
        s["folds"] = folds if folds and all(os.path.exists(p) for p in folds) else None
        if s.get("ctl_root") and s["folds"] is None:
            raise FileNotFoundError(f"{c}: missing control fold maps")
        if s.get("ctl_root"):
            ldir = os.path.join(s["ctl_root"], "lstai")
        else:
            ldir = os.path.join(cloud_root, "lstai") if cloud_root else lstai_dir
        s["lstai"], s["lstai_models"] = None, None
        if ldir:
            p = os.path.join(ldir, f"{c}_lstai_prob.nii.gz")
            if os.path.exists(p):
                s["lstai"] = p
                ms = [os.path.join(ldir, f"{c}_lstai_prob_m{j}.nii.gz") for j in (1, 2, 3)]
                s["lstai_models"] = ms if all(os.path.exists(q) for q in ms) else None
    return scans


def enumerate_external(cloud_root: str):
    d = os.path.join(cloud_root, "flames")
    out = []
    for f in sorted(os.listdir(d)):
        m = re.fullmatch(r"(.+)_f0_prob\.nii\.gz", f)
        if not m or not m.group(1).startswith(EXTERNAL_SITES):
            continue
        case = m.group(1)
        out.append({"case": case, "cohort": case.split("_")[0], "patient": _external_patient(case),
                    "status": "external", "prob": os.path.join(d, f), "gt": os.path.join(d, case + "_gt.nii.gz"),
                    "flair": None, "t1": None})
    for s in out:
        if not os.path.exists(s["gt"]):
            raise FileNotFoundError(f"{s['case']}: missing ground truth")
    return out


def enumerate_controls_v32(controls_root: str):
    """v3.2 (PROTOCOL-v3.2.md): the 100 SibBMS controls, R/flames/sub-XXX_f{k}_prob.nii.gz +
    sub-XXX_gt.nii.gz (all-zero) and R/lstai/sub-XXX_lstai_prob[_m1..3].nii.gz. Fail-closed."""
    fd = os.path.join(controls_root, "flames")
    out = []
    for f in sorted(os.listdir(fd)):
        m = re.fullmatch(r"(sub-\d{3})_f0_prob\.nii\.gz", f)
        if not m:
            continue
        case = m.group(1)
        s = {"case": case, "cohort": "sibbms", "patient": "sibbms_" + case, "status": "control",
             "prob": os.path.join(fd, f), "gt": os.path.join(fd, case + "_gt.nii.gz"),
             "flair": None, "t1": None, "ctl_root": controls_root}
        for k in ("prob", "gt"):
            if not os.path.exists(s[k]):
                raise FileNotFoundError(f"{case}: missing {k}")
        out.append(s)
    return out


def enumerate_scans(data_root: str, control_flair_dir: str | None = None, controls_root: str | None = None):
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
    if controls_root:          # v3.2: the 100 cloud controls replace the 30 August fold-0 controls
        scans += enumerate_controls_v32(controls_root)
    for f in sorted(os.listdir(os.path.join(coh, "sibbms-controls-flames"))) if not controls_root else []:
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
                     + ("_lstai" if opts.get("lstai_dir") else "") + ("_cflair" if opts.get("control_flair_dir") else "")
                     + ("_cloud" if opts.get("cloud_root") else "")
                     + ("_mean5" if opts.get("candidate_map") == "mean5" else "")
                     + ("_noimg" if opts.get("no_images") else "")
                     + ("_noflair" if opts.get("no_flair") else "") + ("_ctl100" if opts.get("controls_root") else ""))
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
    mean5 = opts.get("candidate_map") == "mean5"
    if mean5:
        # POST-HOC (v3.1 RESULTS P1): candidates from the 5-fold MEAN map, as FLAMeS is deployed
        if not s.get("folds"):
            raise ValueError(f"{s['case']}: --candidate-map mean5 needs the 5 fold maps")
        P = np.mean([_load(p, pimg)[1] for p in s["folds"]], axis=0).astype(np.float32)
    zooms = tuple(float(z) for z in pimg.header.get_zooms()[:3])
    if s["status"] != "external" and not np.allclose(zooms, 1.0, atol=1e-3):
        raise ValueError(f"{s['case']}: non-1mm voxels {zooms}")
    spacing = zooms if s["status"] == "external" else SPACING        # v3.1: physical volumes
    vox = float(np.prod(spacing))
    if not np.isfinite(P).all():
        raise ValueError(f"{s['case']}: non-finite probability")
    _, G = _load(s["gt"], pimg)
    gt = G > 0
    del G
    no_img = bool(opts.get("no_images"))
    flair = _load(s["flair"], pimg)[1] if s["flair"] and not no_img else None
    t1 = _load(s["t1"], pimg)[1] if s["t1"] and not no_img else None

    labeled, cands = extract_lesion_candidates(P, THRESHOLD, spacing, min_volume_mm3=MIN_VOL, score=SCORE)
    gt_labeled, n_gt_raw = label_lesions(gt.astype(np.uint8))
    gt_counts = np.bincount(gt_labeled.ravel())
    valid_gt = {g for g in range(1, n_gt_raw + 1) if g < len(gt_counts) and meets_min_volume(int(gt_counts[g]), vox)}
    clin_gt = {g for g in valid_gt if int(gt_counts[g]) * vox >= CLINICAL_VOL_MM3}
    res = {"case": s["case"], "cohort": s["cohort"], "patient": s["patient"], "status": s["status"],
           "n_cand": len(cands), "n_gt": len(valid_gt), "n_gt_clin": len(clin_gt), "spacing": spacing}
    if not cands:
        res.update({"feats": {}, "X_v2": np.zeros((0, len(V2_NAMES))), "score": np.zeros(0),
                    "mg0": np.zeros(0, int), "mg1": np.zeros(0, int), "anyvox": np.zeros(0, bool),
                    "mg0_clin": np.zeros(0, bool), "ctx": {}, "families": [], "seconds": round(time.time() - t0, 1)})
        return res
    m0 = msa._hungarian(labeled, cands, gt_labeled, gt_counts, valid_gt, 0.0)
    m1 = msa._hungarian(labeled, cands, gt_labeled, gt_counts, valid_gt, 0.10)
    anyv = label_candidates_tp(labeled, cands, gt, 0.0)
    del gt_labeled, gt

    fold_maps, fold0_dev = None, None
    if s.get("folds"):
        fold_maps = [_load(p, pimg)[1] for p in s["folds"]]
        if not mean5:
            fold0_dev = float(np.abs(fold_maps[0] - P).max())
            if fold0_dev > FOLD0_TOL:
                raise ValueError(f"{s['case']}: fold-0 map deviates from the cohort prob map by {fold0_dev}")
    lst, lst_models = None, None
    if s.get("lstai") and not no_img:
        lst = _load(s["lstai"], pimg)[1]
        if lst.min() < -1e-4 or lst.max() > 1 + 1e-4:
            raise ValueError(f"{s['case']}: LST-AI map outside [0, 1]")
        if s.get("lstai_models"):
            lst_models = [_load(p, pimg)[1] for p in s["lstai_models"]]

    X_v2 = candidate_feature_matrix(P, labeled, cands)
    ctx = fv.ScanContext(P, flair, t1)
    feats = fv.candidate_features_v3(P, labeled, cands, ctx, fold_maps=fold_maps, lstai=lst,
                                     lstai_models=lst_models, voxel_volume=vox)
    fams = [f for f, names in fv.FAMILIES.items() if names[0] in feats]
    res.update({"feats": feats, "X_v2": X_v2, "score": np.array([c.score for c in cands]),
                "mg0": np.array([m0[c.label][0] for c in cands], int),
                "mg1": np.array([m1[c.label][0] for c in cands], int),
                "anyvox": np.array([bool(anyv[c.label]) for c in cands]),
                "mg0_clin": np.array([m0[c.label][0] in clin_gt for c in cands]),
                "ctx": {**ctx.summary(), "fold0_parity_max_abs": fold0_dev}, "families": fams,
                "seconds": round(time.time() - t0, 1)})
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
    ap.add_argument("--cloud-root", default=None)
    ap.add_argument("--candidate-map", choices=("fold0", "mean5"), default="fold0",
                    help="post-hoc: define candidates on the 5-fold mean map (needs fold maps)")
    ap.add_argument("--no-images", action="store_true", help="skip FLAIR/T1/LST-AI (probability-map families only)")
    ap.add_argument("--no-flair", action="store_true",
                    help="v3.2: skip FLAIR/T1 (no FLAIR families) but keep LST-AI and fold maps")
    ap.add_argument("--controls-root", default=None,
                    help="v3.2: folder with flames/ and lstai/ of the 100 SibBMS controls (replaces the August 30)")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="debug: first N scans per cohort")
    ap.add_argument("--out", default=os.path.join(CACHE_DIR, "features_v3.npz"))
    a = ap.parse_args()

    scans = enumerate_scans(a.data_root, a.control_flair_dir, a.controls_root)
    if a.controls_root and sum(s["cohort"] == "sibbms" for s in scans) != 100:
        raise SystemExit("v3.2 needs exactly 100 controls")
    if a.no_flair:
        for s in scans:
            s["flair"], s["t1"] = None, None
    if a.cloud_root:
        scans += enumerate_external(a.cloud_root)
    attach_inputs(scans, a.folds_dir, a.lstai_dir, a.cloud_root)
    if a.limit:
        by = {}
        for s in scans:
            by.setdefault(s["cohort"], []).append(s)
        scans = [s for v in by.values() for s in v[:a.limit]]
    cohorts = sorted({s["cohort"] for s in scans})
    print(f"{len(scans)} scans: " + ", ".join(f"{c} {sum(s['cohort'] == c for s in scans)}" for c in cohorts))
    opts = {"folds_dir": a.folds_dir, "lstai_dir": a.lstai_dir, "control_flair_dir": a.control_flair_dir,
            "cloud_root": a.cloud_root, "candidate_map": a.candidate_map, "no_images": a.no_images,
            "no_flair": a.no_flair, "controls_root": a.controls_root, "code_digest": _code_digest()}
    if a.candidate_map == "mean5":
        scans = [s for s in scans if s.get("folds")]          # controls have no fold maps
        print(f"mean5: {len(scans)} scans with 5 fold maps")
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
        scan_ngt_clin=np.array([r["n_gt_clin"] for r in results]),
        scan_spacing=np.array([r.get("spacing", SPACING) for r in results], float))
    print(f"hashing inputs ...")
    hashes = {}
    for s in scans:
        for k in ("prob", "gt", "flair", "t1", "lstai"):
            if s.get(k):
                hashes[f"{s['case']}:{k}"] = sha256(s[k])
        for j, p in enumerate(s.get("folds") or []):
            hashes[f"{s['case']}:fold{j}"] = sha256(p)
        for j, p in enumerate(s.get("lstai_models") or []):
            hashes[f"{s['case']}:lstai_m{j + 1}"] = sha256(p)
    digest = hashlib.sha256("".join(f"{k}={v};" for k, v in sorted(hashes.items())).encode()).hexdigest()
    meta = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "data_root": a.data_root, "n_scans": len(results),
            "n_candidates": int(X.shape[0]), "feature_names": names,
            "options": {"folds_dir": a.folds_dir, "lstai_dir": a.lstai_dir, "control_flair_dir": a.control_flair_dir,
                        "cloud_root": a.cloud_root, "fold0_tolerance": FOLD0_TOL,
                        "candidate_map": a.candidate_map, "no_images": a.no_images,
                        "no_flair": a.no_flair, "controls_root": a.controls_root},
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
