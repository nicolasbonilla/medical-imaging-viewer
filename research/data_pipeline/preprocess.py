#!/usr/bin/env python3
"""Common preprocessing entry point: raw multi-site NIfTI -> standardized cases.

REUSES the repo's frozen utilities rather than re-implementing them:

* ``app.utils.nifti_utils`` — load/save, orientation inspection + canonicalisation
  (RC-013), metadata.
* ``app.services.registration_service`` — SimpleITK N4/rigid registration to a
  reference (the same ``_to_sitk`` / ``_brain_mask`` / ``register_rigid`` the
  longitudinal pipeline uses), so preprocessing here matches production geometry.
* ``app.services.dataset_inventory`` — ``detect_sequence`` sequence classification.

The steps below are the standard MS-lesion preprocessing chain. Each is OPTIONAL
and degrades gracefully (records a status in ``case.meta`` instead of crashing)
because the heavy dependency (SimpleITK, and ideally HD-BET/ANTs for real
skull-stripping) may not be installed on every box:

  orient   -> canonicalise voxel axes (nibabel; always available)
  bias     -> N4 bias-field correction            [needs SimpleITK]
  strip    -> brain extraction (Otsu fallback)    [needs SimpleITK; HD-BET better]
  register -> rigid align to a reference image    [needs SimpleITK]
  normalize-> z-score intensities within brain    [numpy; always available]

The output of ``build_cohort`` is the on-disk format the LST-AI runner + conformal
experiment consume: preprocessed NIfTIs plus a ``cohort.csv`` whose rows carry
``case,t1_path,flair_path,expert_path`` (+ ``dataset,site,edss``), and a
``cases.json`` with the full :class:`StandardizedCase` records.

WHAT EACH STEP NEEDS (documented, not silently assumed):
  * SimpleITK:  pip install SimpleITK           (bias / strip / register)
  * HD-BET:     pip install hd-bet   (GPU-lean, far better strip than Otsu)
  * A reference: an MNI-1mm template NIfTI for `register`; datasets already in
    MNI_1mm (mslesseg, open_ms_data) can SKIP register entirely.

Usage
-----
    python -m research.data_pipeline.preprocess --dataset open_ms_data \\
        --raw ./raw/open_ms_data --out ./cohorts/open_ms_data \\
        --steps orient,normalize
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np

try:
    from .common import (ensure_backend_on_path, load_manifest, StandardizedCase,
                         COHORT_CSV_FIELDS, KNOWN_SEQUENCES, SEQ_T1, SEQ_FLAIR,
                         SEQ_T2, SPACE_MNI_1MM, SPACE_NATIVE)
except ImportError:  # pragma: no cover - direct-script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import (ensure_backend_on_path, load_manifest, StandardizedCase,  # type: ignore
                        COHORT_CSV_FIELDS, KNOWN_SEQUENCES, SEQ_T1, SEQ_FLAIR,
                        SEQ_T2, SPACE_MNI_1MM, SPACE_NATIVE)

DEFAULT_STEPS = ("orient", "normalize")
ALL_STEPS = ("orient", "bias", "strip", "register", "normalize")


# ---------------------------------------------------------------------------
# per-image preprocessing steps (each returns (array, status_str))
# ---------------------------------------------------------------------------
def step_orient(img):
    """Canonicalise voxel axes via the repo's RC-013 orientation util.

    Returns a nibabel image in canonical (RAS+) orientation, or the input
    unchanged if the affine is non-determinate (documented RC-013 refusal)."""
    ensure_backend_on_path()
    from app.utils.nifti_utils import canonicalize_orientation, is_orientation_determinate
    if not is_orientation_determinate(img):
        return img, "orient:skipped(non-determinate affine)"
    return canonicalize_orientation(img), "orient:ok"


def step_bias(arr: np.ndarray, spacing) -> tuple[np.ndarray, str]:
    """N4 bias-field correction (SimpleITK). No-op with a status if SITK absent."""
    try:
        import SimpleITK as sitk
    except Exception:
        return arr, "bias:skipped(no SimpleITK)"
    from app.services.registration_service import _to_sitk, _brain_mask
    ensure_backend_on_path()
    img = _to_sitk(arr, spacing)
    mask = _brain_mask(img)
    corrected = sitk.N4BiasFieldCorrection(sitk.Cast(img, sitk.sitkFloat32), mask)
    return sitk.GetArrayFromImage(corrected), "bias:ok"


def step_strip(arr: np.ndarray, spacing) -> tuple[np.ndarray, str]:
    """Brain extraction. Uses the repo's Otsu ``_brain_mask`` fallback (leaky — HD-BET
    strongly preferred for real runs) to zero non-brain voxels."""
    try:
        import SimpleITK as sitk
    except Exception:
        return arr, "strip:skipped(no SimpleITK; install hd-bet for real strip)"
    ensure_backend_on_path()
    from app.services.registration_service import _to_sitk, _brain_mask
    img = _to_sitk(arr, spacing)
    mask = sitk.GetArrayFromImage(_brain_mask(img)) > 0
    out = np.where(mask, arr, 0.0)
    return out, "strip:ok(otsu-fallback)"


def step_register(arr: np.ndarray, spacing, reference: Optional[tuple]):
    """Rigid-align ``arr`` to a reference (ref_array, ref_spacing) via the repo's
    ``register_rigid``, resampling into the reference grid. No reference -> skip."""
    if reference is None:
        return arr, spacing, "register:skipped(no --reference)"
    try:
        import SimpleITK as sitk
    except Exception:
        return arr, spacing, "register:skipped(no SimpleITK)"
    ensure_backend_on_path()
    from app.services.registration_service import _to_sitk, _brain_mask, register_rigid
    ref_arr, ref_sp = reference
    fixed = _to_sitk(np.asarray(ref_arr, np.float32), ref_sp)
    moving = _to_sitk(np.asarray(arr, np.float32), spacing)
    tx, _metric, _stop = register_rigid(fixed, moving, _brain_mask(fixed), _brain_mask(moving))
    resampled = sitk.Resample(moving, fixed, tx, sitk.sitkLinear, 0.0, moving.GetPixelID())
    out = sitk.GetArrayFromImage(resampled)
    return out, tuple(float(s) for s in ref_sp), "register:ok"


def step_normalize(arr: np.ndarray) -> tuple[np.ndarray, str]:
    """Z-score intensities over the non-zero (brain) region. Pure numpy."""
    arr = np.asarray(arr, dtype=np.float32)
    brain = arr[arr != 0]
    if brain.size == 0:
        return arr, "normalize:skipped(empty)"
    mu, sd = float(brain.mean()), float(brain.std())
    if sd <= 0:
        return arr, "normalize:skipped(zero-variance)"
    out = np.where(arr != 0, (arr - mu) / sd, 0.0).astype(np.float32)
    return out, "normalize:ok"


def preprocess_image(path: str, steps: Iterable[str],
                     reference: Optional[tuple] = None):
    """Run the requested step chain on one NIfTI. Returns (array, spacing, status_list)."""
    ensure_backend_on_path()
    import nibabel as nib
    img = nib.load(str(path))
    statuses: List[str] = []

    if "orient" in steps:
        img, s = step_orient(img)
        statuses.append(s)
    arr = np.asarray(img.get_fdata(), dtype=np.float32)
    spacing = tuple(float(z) for z in img.header.get_zooms()[:3])

    if "bias" in steps:
        arr, s = step_bias(arr, spacing); statuses.append(s)
    if "strip" in steps:
        arr, s = step_strip(arr, spacing); statuses.append(s)
    if "register" in steps:
        arr, spacing, s = step_register(arr, spacing, reference); statuses.append(s)
    if "normalize" in steps:
        arr, s = step_normalize(arr); statuses.append(s)
    return arr, spacing, statuses


# ---------------------------------------------------------------------------
# raw-dataset discovery -> StandardizedCase records
# ---------------------------------------------------------------------------
def _classify(name: str) -> Optional[str]:
    """Map a filename to a canonical sequence key using the repo's detector."""
    ensure_backend_on_path()
    try:
        from app.services.dataset_inventory import detect_sequence
        seq = detect_sequence("", name)
        # dataset_inventory returns its own SEQ_* constants (strings); normalise.
        s = (seq or "").lower()
    except Exception:
        s = ""
    low = name.lower()
    if "flair" in low or "flair" in s:
        return SEQ_FLAIR
    if "t2" in low or "t2" in s:
        return SEQ_T2
    if "t1" in low or "t1" in s:
        return SEQ_T1
    return None


def _is_mask(name: str, entry: dict) -> bool:
    low = name.lower()
    suffix = (entry.get("layout") or {}).get("mask_suffix", "")
    globpat = (entry.get("layout") or {}).get("mask_glob", "")
    if suffix and suffix.lower() in low:
        return True
    if globpat and globpat.strip("*").lower() in low:
        return True
    return any(k in low for k in ("mask", "lesion", "consensus", "seg", "_gt"))


def discover_cases(dataset_name: str, raw_dir: str, manifest: dict) -> List[StandardizedCase]:
    """Group a downloaded dataset's NIfTIs into per-case :class:`StandardizedCase`.

    Generic best-effort grouper: a *case* is a leaf directory that contains at
    least one classifiable image; masks are matched by the manifest's layout hints
    or common name tokens. Real per-dataset quirks (BIDS, timepoint folders) can be
    handled by extending this function; it never guesses a mask onto the wrong case
    because grouping is per-directory.
    """
    entry = (manifest.get("datasets") or {}).get(dataset_name, {})
    site = entry.get("site", dataset_name)
    space = entry.get("space", SPACE_NATIVE)
    root = Path(raw_dir)
    if not root.exists():
        raise FileNotFoundError(f"raw dir not found: {root} (run download.py first)")

    # bucket every nifti by its parent directory
    by_dir: dict[Path, list[Path]] = {}
    for p in root.rglob("*.nii*"):
        by_dir.setdefault(p.parent, []).append(p)

    cases: List[StandardizedCase] = []
    for d in sorted(by_dir):
        files = by_dir[d]
        images: dict[str, str] = {}
        mask: Optional[str] = None
        for f in files:
            if _is_mask(f.name, entry):
                mask = str(f)
                continue
            seq = _classify(f.name)
            if seq:
                images.setdefault(seq, str(f))
        if not images:
            continue
        case_id = f"{dataset_name}_{d.relative_to(root).as_posix().replace('/', '_') or d.name}"
        cases.append(StandardizedCase(
            case_id=case_id, dataset=dataset_name, site=site,
            images=images, lesion_mask=mask, space=space,
            meta={"source_dir": str(d)},
        ))
    return cases


def run_preprocess(cases: List[StandardizedCase], out_dir: str, steps: Iterable[str],
                   reference: Optional[tuple] = None) -> List[StandardizedCase]:
    """Preprocess every image of every case, writing results into ``out_dir``.

    Returns updated records whose ``images``/``lesion_mask`` point at the written
    preprocessed NIfTIs (masks are copied through unchanged — never intensity-
    normalised). Records preprocessing statuses in ``case.meta['preprocess']``.
    """
    ensure_backend_on_path()
    import nibabel as nib
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    steps = list(steps)
    updated: List[StandardizedCase] = []

    for case in cases:
        new_images: dict[str, str] = {}
        statuses: dict[str, list] = {}
        for seq, path in case.images.items():
            arr, spacing, st = preprocess_image(path, steps, reference)
            dst = out / f"{case.case_id}_{seq}.nii.gz"
            nib.save(nib.Nifti1Image(arr, np.eye(4)), str(dst))
            new_images[seq] = str(dst)
            statuses[seq] = st
            case.spacing = spacing
        # copy mask through unchanged (nearest-neighbour geometry preserved as-is)
        new_mask = None
        if case.lesion_mask:
            m = nib.load(case.lesion_mask)
            new_mask = str(out / f"{case.case_id}_gt.nii.gz")
            nib.save(nib.Nifti1Image((np.asarray(m.get_fdata()) > 0).astype(np.uint8),
                                     m.affine), new_mask)
        meta = dict(case.meta); meta["preprocess"] = statuses
        updated.append(StandardizedCase(
            case_id=case.case_id, dataset=case.dataset, site=case.site,
            images=new_images, lesion_mask=new_mask, space=case.space,
            spacing=case.spacing, edss=case.edss, meta=meta))
    return updated


def write_cohort(cases: List[StandardizedCase], out_dir: str) -> tuple[str, str]:
    """Write ``cohort.csv`` (LST-AI schema) + ``cases.json`` (full records)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "cohort.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COHORT_CSV_FIELDS)
        w.writeheader()
        for c in cases:
            w.writerow(c.cohort_row())
    json_path = out / "cases.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([c.to_dict() for c in cases], f, indent=2)
    return str(csv_path), str(json_path)


def build_cohort(dataset_name: str, raw_dir: str, out_dir: str,
                 steps: Iterable[str] = DEFAULT_STEPS,
                 reference: Optional[tuple] = None) -> List[StandardizedCase]:
    """End-to-end: discover -> preprocess -> write cohort.csv/cases.json."""
    manifest = load_manifest()
    cases = discover_cases(dataset_name, raw_dir, manifest)
    if not cases:
        print(f"[{dataset_name}] no cases discovered under {raw_dir}")
        return []
    print(f"[{dataset_name}] discovered {len(cases)} case(s); preprocessing "
          f"(steps={list(steps)}) ...")
    done = run_preprocess(cases, out_dir, steps, reference)
    csv_path, json_path = write_cohort(done, out_dir)
    print(f"[{dataset_name}] wrote {csv_path} and {json_path}")
    return done


def _load_reference(path: Optional[str]):
    if not path:
        return None
    import nibabel as nib
    img = nib.load(path)
    return np.asarray(img.get_fdata(), np.float32), tuple(float(z) for z in img.header.get_zooms()[:3])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, help="manifest key (see datasets.yaml)")
    ap.add_argument("--raw", required=True, help="raw dataset dir (download.py output)")
    ap.add_argument("--out", required=True, help="cohort output dir")
    ap.add_argument("--steps", default=",".join(DEFAULT_STEPS),
                    help=f"comma list from {ALL_STEPS}")
    ap.add_argument("--reference", help="MNI-1mm template NIfTI for the `register` step")
    args = ap.parse_args(argv)

    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    bad = set(steps) - set(ALL_STEPS)
    if bad:
        ap.error(f"unknown steps {bad}; choose from {ALL_STEPS}")
    reference = _load_reference(args.reference)
    build_cohort(args.dataset, args.raw, args.out, steps, reference)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
