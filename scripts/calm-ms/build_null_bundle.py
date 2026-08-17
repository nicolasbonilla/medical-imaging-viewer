#!/usr/bin/env python3
"""Build the FROZEN, versioned, provenance-stamped CALM-MS calibration-null asset.

The conformal endpoint loads this ONCE at startup and FAILS CLOSED if it is
missing/empty or if a request's probability map does not match its provenance
(same base model + same MNI grid/spacing). This is the enforced exchangeability
invariant the adversarial Class C review demanded — never a comment or a warning.

v1 uses the RAW pooled-probability null (the learned scorer is deferred to v2 to
keep the validation surface minimal). Built over the 145 FLAMeS-derived labeled
cases (open_ms_data 30 + MSLesSeg 115), all MNI 1mm.

    python scripts/calm-ms/build_null_bundle.py

Output: backend/app/services/assets/calm_ms_null_flames_v1.npz
"""
import os, sys, glob, json, datetime, hashlib
import numpy as np
import nibabel as nib

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.calm_ms_inference import extract_lesion_candidates, label_candidates_tp  # noqa: E402

OOD_FEATURES = ["n_candidates", "mean_score", "q10", "q50", "q90"]

THRESHOLD = 0.5
MIN_VOLUME_MM3 = 3.0
SCORE = "mean"
VOXEL_SPACING = (1.0, 1.0, 1.0)          # MNI 1mm
BASE_MODEL = "FLAMeS"
BASE_MODEL_VERSION = "Dataset004_WML (Zenodo 17955359)"
PREPROCESSING_SPACE = "MNI152 1mm"
VERSION = "v1"

COHORTS = {
    "openms-flames": "open_ms_data (Lesjak 2018, 3-rater consensus)",
    "mslesseg-flames": "MSLesSeg (ICPR-2024, multi-site)",
}


def _load_pairs(d):
    for prob in sorted(glob.glob(os.path.join(d, "*_prob.nii.gz"))):
        case = os.path.basename(prob)[:-len("_prob.nii.gz")]
        gt = os.path.join(d, case + "_gt.nii.gz")
        if os.path.exists(gt):
            p = nib.load(prob); g = nib.load(gt)
            yield case, np.asarray(p.get_fdata(), dtype=np.float32), (np.asarray(g.get_fdata()) > 0).astype(np.uint8), p.shape


def main():
    cases, grids = [], set()
    for sub, _ in COHORTS.items():
        d = os.path.join("data", "cohorts", sub)
        for case, prob, gt, shape in _load_pairs(d):
            if not (0.0 <= float(prob.min()) and float(prob.max()) <= 1.001):
                sys.exit(f"[{case}] prob out of [0,1] — refusing to build null from bad data")
            cases.append((prob, gt)); grids.add(tuple(int(x) for x in shape))
    if len(cases) < 2:
        sys.exit(f"need >= 2 cases, found {len(cases)}")
    if len(grids) != 1:
        sys.exit(f"cases span multiple grids {grids} — a single-grid null is required for exchangeability")
    grid = grids.pop()

    print(f"Building null + OOD reference over {len(cases)} FLAMeS cases on grid {grid} @ {VOXEL_SPACING} mm ...")
    null_list, ood_rows = [], []
    for prob, gt in cases:
        labeled, cands = extract_lesion_candidates(prob, THRESHOLD, VOXEL_SPACING,
                                                   min_volume_mm3=MIN_VOLUME_MM3, score=SCORE)
        if not cands:
            continue
        scores = np.array([c.score for c in cands], dtype=float)
        # Per-case OOD summary over ALL candidates (computable at inference — no GT).
        q10, q50, q90 = (float(q) for q in np.quantile(scores, [0.1, 0.5, 0.9]))
        ood_rows.append([float(len(cands)), float(scores.mean()), q10, q50, q90])
        # Null = FALSE-candidate scores (need GT here, at build time only).
        is_tp = label_candidates_tp(labeled, cands, gt, min_overlap=0.0)
        null_list.extend(c.score for c in cands if not is_tp[c.label])
    null = np.asarray(null_list, dtype=np.float32)
    ood_reference = np.asarray(ood_rows, dtype=np.float32)   # (n_cases, len(OOD_FEATURES))
    if null.size == 0:
        sys.exit("empty null — refusing to ship an unusable asset")

    provenance = {
        "asset": "calm_ms_null_flames_v1",
        "version": VERSION,
        "base_model": BASE_MODEL,
        "base_model_version": BASE_MODEL_VERSION,
        "preprocessing_space": PREPROCESSING_SPACE,
        "grid_shape": list(grid),
        "voxel_spacing": list(VOXEL_SPACING),
        "threshold": THRESHOLD,
        "min_volume_mm3": MIN_VOLUME_MM3,
        "score_pooling": SCORE,
        "null_kind": "raw_pooled_probability (v1; learned scorer deferred to v2)",
        "n_cases": len(cases),
        "n_null_scores": int(null.size),
        "ood_feature_names": OOD_FEATURES,
        "ood_n_cases": int(ood_reference.shape[0]),
        "cohorts": COHORTS,
        "built_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "requirement": "REQ-FUNC-CALM-001",
        "note": "Valid ONLY for FLAMeS-derived probability maps on this exact MNI grid. Endpoint MUST fail closed on any provenance mismatch.",
    }
    prov_json = json.dumps(provenance, indent=2, sort_keys=True)
    provenance["sha256"] = hashlib.sha256((prov_json + null.tobytes().hex()[:1024]).encode()).hexdigest()[:16]

    out_dir = os.path.join(_BACKEND, "app", "services", "assets")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "calm_ms_null_flames_v1.npz")
    np.savez_compressed(out, null_scores=null, ood_reference=ood_reference,
                        provenance=json.dumps(provenance))
    print(f"\nWROTE {out}")
    print(f"  null scores: {null.size}  (mean {null.mean():.3f}, min {null.min():.3f}, max {null.max():.3f})")
    print(f"  grid {grid} @ {VOXEL_SPACING}  base={BASE_MODEL}  sha={provenance['sha256']}")
    print(f"  -> min conformal p-value achievable = 1/(n+1) = {1.0/(null.size+1):.4f}")


if __name__ == "__main__":
    main()
