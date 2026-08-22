"""Trained nnU-Net (or ANY probability map) -> CALM-MS lesion CANDIDATES + conformal mask.

This is the BRIDGE that makes "strong nnU-Net base + CALM-MS conformal precision control"
a single stack. It never re-implements the conformal layer; it feeds it, using the exact
repo functions the shipped guarantee is calibrated against (via `_bridge`):

    prob_map (0..1)  --extract_lesion_candidates-->  18-conn components + pooled score
                     --candidate_feature_matrix -->  14 contractual per-candidate features
                     --select_lesions_conformal -->  FDR<=alpha risk-controlled mask

Three outputs, each matching an existing repo consumer so nothing downstream changes:

  1. CANDIDATES JSON  — per-candidate {score, n_voxels, volume_mm3, centroid, features{}},
     the object the CALM-MS learned scorer / calibration path reads.
  2. CALM-MS COHORT   — `<case>_prob.nii.gz` (+ `<case>_gt.nii.gz` when GT is given), the
     directory format `scripts/calm-ms/build_null_bundle.py` and
     `build_lesion_scorer_asset.py` consume verbatim to build the calibration null.
  3. CONFORMAL MASK   — when a calibration null (.npy/.txt) is supplied, the selected,
     FDR-controlled binary lesion mask + a summary (calls `select_lesions_conformal`).

nnU-Net probability input: run `nnUNetv2_predict ... --save_probabilities`; each case gets
a `<CASE>.npz` with key `probabilities` shape (n_classes, *seg_grid), aligned to the saved
`<CASE>.nii.gz` segmentation geometry. `load_nnunet_probabilities` pulls the foreground
channel (index 1). You can also pass any `_prob.nii.gz` directly.

Conventions are pinned to the repo's CALM-MS defaults (calm_ms_inference / build_null_bundle):
THRESHOLD=0.5, MIN_VOLUME_MM3=3.0, SCORE="mean", SPACING=(1,1,1) for MNI-1mm probability maps.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Optional

import numpy as np
import nibabel as nib

from _bridge import (
    require_calm,
    extract_lesion_candidates,
    candidate_feature_matrix,
    select_lesions_conformal,
    FEATURE_NAMES,
    MIN_LESION_VOLUME_MM3,
    bridge_status,
)

# Repo CALM-MS defaults (calm_ms_inference.py / build_null_bundle.py).
DEFAULT_THRESHOLD = 0.5
DEFAULT_SCORE = "mean"
DEFAULT_SPACING = (1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# Probability-map loading.
# ---------------------------------------------------------------------------
def load_nnunet_probabilities(npz_path: str, foreground_index: int = 1) -> np.ndarray:
    """Foreground probability volume from an nnU-Net `--save_probabilities` .npz.

    nnU-Net stores `probabilities` shape (n_classes, *grid). For binary lesion vs
    background, class 1 is the lesion posterior. Returns a float32 3D array in [0,1].
    """
    with np.load(npz_path) as d:
        if "probabilities" not in d:
            raise KeyError(f"{npz_path} has no 'probabilities' key (keys: {list(d.keys())})")
        probs = np.asarray(d["probabilities"], dtype=np.float32)
    if probs.ndim != 4:
        raise ValueError(f"expected (n_classes, Z, Y, X), got shape {probs.shape}")
    if not (0 <= foreground_index < probs.shape[0]):
        raise ValueError(f"foreground_index {foreground_index} out of range {probs.shape[0]}")
    return probs[foreground_index]


def load_probmap(path: str, foreground_index: int = 1):
    """Load a probability map from `.npz` (nnU-Net) or `.nii.gz`/`.nii` (already a prob map).

    Returns (prob_map float32 [0,1] 3D, affine or None). NIfTI keeps its affine so the
    CALM-MS cohort export lands on the same grid as the reference; .npz has no affine.
    """
    lower = path.lower()
    if lower.endswith(".npz"):
        return load_nnunet_probabilities(path, foreground_index), None
    if lower.endswith((".nii.gz", ".nii")):
        img = nib.load(path)
        return np.asarray(img.dataobj, dtype=np.float32), img.affine
    raise ValueError(f"unsupported probability map extension: {path}")


def nnunet_npz_to_prob_nifti(npz_path: str, reference_nifti: str, out_path: str,
                             foreground_index: int = 1) -> str:
    """Write an nnU-Net probabilities .npz as a `_prob.nii.gz` on the reference grid.

    The reference is typically the case's saved segmentation (or the GT), which carries the
    correct affine. Shapes must match (raises otherwise) — an orientation/geometry mismatch
    must fail loudly, not silently mis-map a Class-C probability volume.
    """
    prob = load_nnunet_probabilities(npz_path, foreground_index)
    ref = nib.load(reference_nifti)
    if tuple(prob.shape) != tuple(ref.shape):
        raise ValueError(
            f"probabilities shape {prob.shape} != reference {ref.shape}; nnU-Net may store "
            "probabilities in a transposed axis order — verify orientation before bridging")
    nib.save(nib.Nifti1Image(prob.astype(np.float32), ref.affine, ref.header), out_path)
    return out_path


# ---------------------------------------------------------------------------
# prob map -> CALM-MS candidates + features.
# ---------------------------------------------------------------------------
def probmap_to_candidates(prob_map: np.ndarray, spacing=DEFAULT_SPACING,
                          threshold: float = DEFAULT_THRESHOLD,
                          min_volume_mm3: float = MIN_LESION_VOLUME_MM3,
                          score: str = DEFAULT_SCORE):
    """(labeled, candidates, feature_matrix) using the repo's exact CALM-MS extractor.

    feature_matrix rows align to `candidates` order, columns to FEATURE_NAMES.
    """
    require_calm()
    prob_map = np.asarray(prob_map, dtype=np.float32)
    labeled, cands = extract_lesion_candidates(
        prob_map, threshold, tuple(spacing), min_volume_mm3=min_volume_mm3, score=score)
    if not cands:
        return labeled, [], np.zeros((0, len(FEATURE_NAMES)), dtype=float)
    feats = candidate_feature_matrix(prob_map, labeled, cands, tuple(spacing))
    return labeled, cands, feats


def candidates_to_records(cands, feats) -> list[dict]:
    """Per-candidate dicts (score, geometry, and the 14 named CALM-MS features).

    This is the inference/calibration record the CALM-MS learned scorer consumes; the
    feature block is keyed by FEATURE_NAMES so training and inference cannot diverge.
    """
    records = []
    for i, c in enumerate(cands):
        records.append({
            "label": int(c.label),
            "score": round(float(c.score), 6),
            "n_voxels": int(c.n_voxels),
            "volume_mm3": round(float(c.volume_mm3), 3),
            "centroid": [round(float(x), 2) for x in c.centroid],
            "features": {name: float(feats[i, j]) for j, name in enumerate(FEATURE_NAMES)},
        })
    return records


def write_candidates_json(case: str, cands, feats, out_path: str,
                          threshold: float, spacing, score: str) -> dict:
    payload = {
        "case": case,
        "convention": {"threshold": threshold, "min_volume_mm3": MIN_LESION_VOLUME_MM3,
                       "score_pooling": score, "voxel_spacing": list(spacing),
                       "connectivity": 18},
        "feature_names": list(FEATURE_NAMES),
        "n_candidates": len(cands),
        "candidates": candidates_to_records(cands, feats),
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return payload


def write_calm_cohort(case: str, prob_map: np.ndarray, out_dir: str,
                      affine: Optional[np.ndarray] = None,
                      gt_mask: Optional[np.ndarray] = None) -> dict:
    """Write `<case>_prob.nii.gz` (+ `<case>_gt.nii.gz`) — the CALM-MS calibration format.

    This is exactly the directory `scripts/calm-ms/build_null_bundle.py` and
    `build_lesion_scorer_asset.py` glob for, so a converted nnU-Net cohort drops straight
    into the existing calibration pipeline with no code change.
    """
    os.makedirs(out_dir, exist_ok=True)
    aff = np.eye(4) if affine is None else affine
    prob = np.asarray(prob_map, dtype=np.float32)
    pmin, pmax = float(prob.min()), float(prob.max())
    if not (pmin >= -1e-6 and pmax <= 1.001):
        raise ValueError(f"[{case}] prob out of [0,1] (min {pmin}, max {pmax})")
    prob_path = os.path.join(out_dir, f"{case}_prob.nii.gz")
    nib.save(nib.Nifti1Image(prob, aff), prob_path)
    out = {"prob": prob_path}
    if gt_mask is not None:
        gt_path = os.path.join(out_dir, f"{case}_gt.nii.gz")
        nib.save(nib.Nifti1Image((np.asarray(gt_mask) > 0).astype(np.uint8), aff), gt_path)
        out["gt"] = gt_path
    return out


# ---------------------------------------------------------------------------
# Conformal selection (needs a calibration null).
# ---------------------------------------------------------------------------
def load_calibration_null(path: str) -> np.ndarray:
    """Load the conformal null (false-candidate scores) from .npy / .npz / .txt.

    Build one with `scripts/calm-ms/build_null_bundle.py` from a `_prob/_gt` cohort, or
    with `_bridge.build_calibration_nulls` over held-out cases.
    """
    lower = path.lower()
    if lower.endswith(".npy"):
        return np.asarray(np.load(path), dtype=float).ravel()
    if lower.endswith(".npz"):
        with np.load(path) as d:
            key = "null_scores" if "null_scores" in d else list(d.keys())[0]
            return np.asarray(d[key], dtype=float).ravel()
    return np.loadtxt(path, dtype=float).ravel()


def run_conformal(prob_map: np.ndarray, calib_null_scores, alpha: float,
                  spacing=DEFAULT_SPACING, threshold: float = DEFAULT_THRESHOLD,
                  min_volume_mm3: float = MIN_LESION_VOLUME_MM3, score: str = DEFAULT_SCORE):
    """Probability map -> FDR<=alpha risk-controlled mask (repo `select_lesions_conformal`)."""
    require_calm()
    return select_lesions_conformal(
        np.asarray(prob_map, dtype=np.float32), calib_null_scores, alpha, threshold,
        tuple(spacing), min_volume_mm3=min_volume_mm3, score=score)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prob", required=True, help="probability map (.npz nnU-Net or .nii.gz)")
    ap.add_argument("--case", default=None, help="case id (default: basename of --prob)")
    ap.add_argument("--gt", default=None, help="optional GT mask NIfTI (for cohort export)")
    ap.add_argument("--reference", default=None,
                    help="reference NIfTI for the affine when --prob is .npz")
    ap.add_argument("--spacing", type=float, nargs=3, default=list(DEFAULT_SPACING))
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--min-volume-mm3", type=float, default=MIN_LESION_VOLUME_MM3)
    ap.add_argument("--score", default=DEFAULT_SCORE, choices=("mean", "max"))
    ap.add_argument("--out-candidates", default=None, help="write candidates JSON here")
    ap.add_argument("--out-cohort", default=None,
                    help="dir to write <case>_prob.nii.gz (+ _gt) CALM-MS cohort format")
    ap.add_argument("--calib-null", default=None,
                    help="calibration null (.npy/.npz/.txt); enables conformal selection")
    ap.add_argument("--alpha", type=float, default=0.1, help="FDR target for conformal select")
    ap.add_argument("--out-mask", default=None, help="write conformal mask NIfTI here")
    args = ap.parse_args(argv)

    print("[bridge]", bridge_status())
    require_calm()
    case = args.case or os.path.basename(args.prob).split(".")[0]
    prob_map, affine = load_probmap(args.prob)
    if affine is None and args.reference:
        affine = nib.load(args.reference).affine

    labeled, cands, feats = probmap_to_candidates(
        prob_map, spacing=tuple(args.spacing), threshold=args.threshold,
        min_volume_mm3=args.min_volume_mm3, score=args.score)
    print(f"[{case}] {len(cands)} candidates (threshold={args.threshold}, score={args.score})")

    if args.out_candidates:
        write_candidates_json(case, cands, feats, args.out_candidates,
                              args.threshold, tuple(args.spacing), args.score)
        print(f"  wrote candidates -> {args.out_candidates}")

    if args.out_cohort:
        gt = (np.asarray(nib.load(args.gt).dataobj) if args.gt else None)
        paths = write_calm_cohort(case, prob_map, args.out_cohort, affine=affine, gt_mask=gt)
        print(f"  wrote CALM-MS cohort -> {paths}")

    if args.calib_null:
        null = load_calibration_null(args.calib_null)
        res = run_conformal(prob_map, null, args.alpha, spacing=tuple(args.spacing),
                            threshold=args.threshold, min_volume_mm3=args.min_volume_mm3,
                            score=args.score)
        print(f"  conformal @ alpha={args.alpha}: {res.n_selected}/{res.n_candidates} selected")
        if args.out_mask:
            nib.save(nib.Nifti1Image(res.mask, np.eye(4) if affine is None else affine),
                     args.out_mask)
            print(f"  wrote conformal mask -> {args.out_mask}")
        print(json.dumps(res.summary(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
