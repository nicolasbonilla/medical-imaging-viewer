"""Convert pooled public MS-lesion datasets into nnU-Net v2 raw dataset format.

Target (nnU-Net v2 raw layout):

    $nnUNet_raw/Dataset<ID>_<NAME>/
        imagesTr/<case>_0000.nii.gz     # channel 0 = FLAIR (always)
        imagesTr/<case>_0001.nii.gz     # channel 1 = T1     (only if --with-t1)
        labelsTr/<case>.nii.gz          # binary lesion mask {0,1}
        dataset.json                    # channel_names, labels, numTraining, file_ending

FLAIR (+ optional T1) -> a BINARY whole-lesion mask (foreground = any annotated lesion).
This is the base segmenter's supervised target; the CALM-MS conformal layer sits on top of
its probability output and needs no change to the label.

Supported inputs
----------------
* A pooled root produced by `research/data_pipeline` (see README) whose per-case folders
  each contain a FLAIR, an optional T1, and a lesion mask, OR
* A standalone public dataset in its own on-disk convention. Known layouts are registered
  in LAYOUTS (MSLesSeg / ISBI-2015 / MSSEG-2016 / Ljubljana), and `--layout generic`
  matches any folder-per-case tree by filename keywords.

Only the non-GPU conversion is done here; it is pure nibabel + numpy and importable. A
tiny synthetic case is exercised by test_pipeline.py on CPU.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np
import nibabel as nib


# ---------------------------------------------------------------------------
# Layout registry: how to find (FLAIR, T1, mask) inside one case folder.
# Patterns are lowercase substrings; the first NIfTI matching wins. `t1` is optional.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Layout:
    name: str
    flair_keys: tuple = ("flair",)
    t1_keys: tuple = ("t1",)
    mask_keys: tuple = ("mask", "lesion", "consensus", "seg", "gt", "label")
    # exclude any file whose name contains one of these (e.g. a T1 "t1c"/"t1ce" we don't want)
    exclude_keys: tuple = ()


LAYOUTS = {
    # Generic folder-per-case: FLAIR + optional T1 + a mask, matched by keyword.
    "generic": Layout("generic"),
    # MSLesSeg (ICPR-2024): P<k>/T<j>/ with *_FLAIR.nii.gz, *_T1.nii.gz, *_MASK.nii.gz
    "mslesseg": Layout("mslesseg", flair_keys=("flair",), t1_keys=("t1",),
                       mask_keys=("mask",)),
    # ISBI-2015: *_flair_pp.nii, T1 *_mprage_pp.nii, masks *_mask1/_mask2 (rater consensus)
    "isbi": Layout("isbi", flair_keys=("flair",), t1_keys=("mprage", "t1"),
                   mask_keys=("mask1", "mask", "lesion")),
    # MSSEG-2016: Preprocessed/FLAIR_preprocessed.nii.gz, T1; masks Consensus.nii.gz
    "msseg": Layout("msseg", flair_keys=("flair",), t1_keys=("t1",),
                    mask_keys=("consensus", "mask", "lesion"),
                    exclude_keys=("gado", "t1c", "t1ce")),
    # Ljubljana (3D FLAIR MS lesion): flair + t1 + lesion/consensus mask
    "ljubljana": Layout("ljubljana", flair_keys=("flair",), t1_keys=("t1",),
                        mask_keys=("lesion", "consensus", "mask")),
}

_NIFTI_EXT = (".nii.gz", ".nii")


@dataclass
class Case:
    case_id: str
    flair: str
    mask: str
    t1: Optional[str] = None


def _list_niftis(folder: str) -> list[str]:
    out: list[str] = []
    for ext in _NIFTI_EXT:
        out.extend(glob.glob(os.path.join(folder, "**", "*" + ext), recursive=True))
    # dedupe (*.nii.gz also matches *.nii glob on some shells) and stabilise order
    return sorted(set(out))


def _first_match(files: list[str], keys: tuple, exclude: tuple = ()) -> Optional[str]:
    for f in files:
        low = os.path.basename(f).lower()
        if any(x in low for x in exclude):
            continue
        if any(k in low for k in keys):
            return f
    return None


def discover_cases(root: str, layout: str = "generic") -> list[Case]:
    """Find (FLAIR, optional T1, mask) triples under `root`.

    A "case" is a leaf folder that contains at least one FLAIR and one mask NIfTI. Case IDs
    are derived from the relative path (path separators -> '_') so longitudinal timepoints
    stay distinct (e.g. 'P12/T3' -> 'P12_T3').
    """
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout '{layout}'; known: {sorted(LAYOUTS)}")
    lay = LAYOUTS[layout]
    root = os.path.abspath(root)
    cases: list[Case] = []
    seen_ids: set[str] = set()

    # Every directory that directly holds NIfTI files is a candidate case folder.
    case_dirs: set[str] = set()
    for dirpath, _dirs, filenames in os.walk(root):
        if any(fn.lower().endswith(_NIFTI_EXT) for fn in filenames):
            case_dirs.add(dirpath)

    for d in sorted(case_dirs):
        files = _list_niftis(d)
        flair = _first_match(files, lay.flair_keys, lay.exclude_keys)
        mask = _first_match(files, lay.mask_keys, lay.exclude_keys)
        if not flair or not mask:
            continue
        t1 = _first_match(files, lay.t1_keys, lay.exclude_keys + lay.flair_keys)
        rel = os.path.relpath(d, root)
        cid = re.sub(r"[^A-Za-z0-9]+", "_", rel).strip("_") or "case"
        # de-duplicate collisions deterministically
        base = cid
        k = 1
        while cid in seen_ids:
            k += 1
            cid = f"{base}_{k}"
        seen_ids.add(cid)
        cases.append(Case(case_id=cid, flair=flair, mask=mask, t1=t1))
    return cases


def _load_nifti(path: str):
    img = nib.load(path)
    return np.asanyarray(img.dataobj), img.affine, img.header


def binarize_mask(mask_data: np.ndarray) -> np.ndarray:
    """Any positive label -> 1 (whole-lesion foreground). uint8."""
    return (np.asarray(mask_data) > 0).astype(np.uint8)


def convert_case(case: Case, out_dir: str, case_name: str, with_t1: bool) -> dict:
    """Write one case into imagesTr/labelsTr. Returns a small provenance record.

    Geometry check: the mask must share the FLAIR's grid shape (nnU-Net requires image and
    label on the same voxel grid). A mismatch raises rather than silently mis-aligning a
    Class-C training label.
    """
    images_dir = os.path.join(out_dir, "imagesTr")
    labels_dir = os.path.join(out_dir, "labelsTr")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(labels_dir, exist_ok=True)

    flair_data, flair_aff, flair_hdr = _load_nifti(case.flair)
    mask_data, _mask_aff, _mask_hdr = _load_nifti(case.mask)
    if mask_data.shape != flair_data.shape:
        raise ValueError(
            f"[{case.case_id}] mask shape {mask_data.shape} != FLAIR shape "
            f"{flair_data.shape}; resample to a common grid before conversion")

    nib.save(nib.Nifti1Image(np.asarray(flair_data, dtype=np.float32), flair_aff, flair_hdr),
             os.path.join(images_dir, f"{case_name}_0000.nii.gz"))
    channels = ["FLAIR"]
    if with_t1:
        if not case.t1:
            raise ValueError(f"[{case.case_id}] --with-t1 set but no T1 found")
        t1_data, _t1_aff, _t1_hdr = _load_nifti(case.t1)
        if t1_data.shape != flair_data.shape:
            raise ValueError(
                f"[{case.case_id}] T1 shape {t1_data.shape} != FLAIR shape {flair_data.shape}")
        nib.save(nib.Nifti1Image(np.asarray(t1_data, dtype=np.float32), flair_aff, flair_hdr),
                 os.path.join(images_dir, f"{case_name}_0001.nii.gz"))
        channels.append("T1")

    binm = binarize_mask(mask_data)
    nib.save(nib.Nifti1Image(binm, flair_aff, flair_hdr),
             os.path.join(labels_dir, f"{case_name}.nii.gz"))
    return {"case_id": case.case_id, "nnunet_name": case_name,
            "channels": channels, "lesion_voxels": int(binm.sum())}


def write_dataset_json(out_dir: str, n_training: int, with_t1: bool,
                       dataset_name: str, description: str = "") -> dict:
    """Write the nnU-Net v2 dataset.json (the v2 schema, not v1's numTest/training list)."""
    channel_names = {"0": "FLAIR"}
    if with_t1:
        channel_names["1"] = "T1"
    meta = {
        "name": dataset_name,
        "description": description or "Pooled public MS FLAIR lesion segmentation",
        "reference": "MSLesSeg / ISBI-2015 / MSSEG-2016 / Ljubljana (see README)",
        "channel_names": channel_names,
        "labels": {"background": 0, "lesion": 1},
        "numTraining": int(n_training),
        "file_ending": ".nii.gz",
    }
    with open(os.path.join(out_dir, "dataset.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    return meta


def convert_dataset(root: str, out_dir: str, dataset_name: str, layout: str = "generic",
                    with_t1: bool = False, case_prefix: str = "MSLES",
                    limit: Optional[int] = None, verbose: bool = True) -> dict:
    """Convert a whole dataset root into an nnU-Net v2 raw dataset directory.

    Returns a manifest dict (also written to <out_dir>/conversion_manifest.json).
    nnU-Net-safe case names are `<case_prefix>_<0001..>`; the mapping back to the source
    case id is kept in the manifest for traceability (IEC 62304).
    """
    cases = discover_cases(root, layout=layout)
    if limit is not None:
        cases = cases[:limit]
    if not cases:
        raise ValueError(f"no (FLAIR, mask) cases found under {root} with layout '{layout}'")
    os.makedirs(out_dir, exist_ok=True)

    records = []
    for i, case in enumerate(cases, start=1):
        case_name = f"{case_prefix}_{i:04d}"
        rec = convert_case(case, out_dir, case_name, with_t1=with_t1)
        rec["source_flair"] = os.path.abspath(case.flair)
        rec["source_mask"] = os.path.abspath(case.mask)
        rec["source_t1"] = os.path.abspath(case.t1) if case.t1 else None
        records.append(rec)
        if verbose:
            print(f"  [{i}/{len(cases)}] {case.case_id} -> {case_name} "
                  f"({rec['lesion_voxels']} lesion vox)")

    meta = write_dataset_json(out_dir, n_training=len(records), with_t1=with_t1,
                              dataset_name=dataset_name)
    manifest = {"dataset_json": meta, "layout": layout, "with_t1": with_t1,
                "root": os.path.abspath(root), "cases": records}
    with open(os.path.join(out_dir, "conversion_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    if verbose:
        print(f"Wrote nnU-Net v2 dataset: {out_dir}  ({len(records)} cases, "
              f"channels={list(meta['channel_names'].values())})")
    return manifest


def _default_out_dir(dataset_id: int, dataset_name: str) -> str:
    """<nnUNet_raw>/Dataset<ID>_<NAME> if nnUNet_raw is set, else ./ under CWD."""
    raw = os.environ.get("nnUNet_raw")
    folder = f"Dataset{dataset_id:03d}_{dataset_name}"
    return os.path.join(raw, folder) if raw else os.path.join(os.getcwd(), folder)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="dataset root (folder-per-case tree)")
    ap.add_argument("--layout", default="generic", choices=sorted(LAYOUTS),
                    help="on-disk convention of the source dataset")
    ap.add_argument("--dataset-id", type=int, default=501, help="nnU-Net dataset integer id")
    ap.add_argument("--dataset-name", default="MSLesionFLAIR", help="nnU-Net dataset name")
    ap.add_argument("--out", default=None,
                    help="output dir (default: $nnUNet_raw/Dataset<ID>_<NAME>)")
    ap.add_argument("--with-t1", action="store_true", help="include T1 as channel 1")
    ap.add_argument("--case-prefix", default="MSLES")
    ap.add_argument("--limit", type=int, default=None, help="convert only first N cases")
    args = ap.parse_args(argv)

    out_dir = args.out or _default_out_dir(args.dataset_id, args.dataset_name)
    convert_dataset(args.root, out_dir, dataset_name=args.dataset_name, layout=args.layout,
                    with_t1=args.with_t1, case_prefix=args.case_prefix, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
