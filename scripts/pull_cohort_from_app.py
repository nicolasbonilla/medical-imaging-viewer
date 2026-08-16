#!/usr/bin/env python3
"""Pull the CALM-MS cohort straight from the app (no external ISBI download).

The software already holds every case's T1w + FLAIR (as NIfTI instances in GCS)
and the expert 'Expert Rater' masks. This assembles them locally:

  - source images via  GET /imaging/nifti/{file_id}
  - expert masks   via  GET /segmentation/{seg_id}/mask/binary  (saved as NIfTI)

and writes cohort.csv (case,t1_path,flair_path,expert_path) for the LST-AI +
conformal-experiment chain. Credentials via MSTOOL_ADMIN_TOKEN, like the other
tools.

ORIENTATION NOTE: the expert mask is stored internal (k,a0,a1); we save it in
MRI-native order (a0,a1,k) via transpose(1,2,0) so it matches an MNI-native LST-AI
output. VERIFY alignment on one case (Dice of LST-AI binary vs expert should be
sane, not ~0) before trusting the full cohort.

    python scripts/pull_cohort_from_app.py --out-dir ./cohort --expert-idx 01
"""
import argparse
import csv
import os
import struct
import sys
import tempfile

import numpy as np
import nibabel as nib
import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.dataset_inventory import detect_sequence, SEQ_T1, SEQ_FLAIR  # noqa: E402
try:
    from app.security.storage_access import parse_patient_storage_ref
except Exception:
    parse_patient_storage_ref = None

API = os.environ.get("MSTOOL_API_BASE", "https://brain-mri-7bp6oqdu7a-uc.a.run.app/api/v1").rstrip("/")
TIMEOUT = 120


def _H():
    tok = os.environ.get("MSTOOL_ADMIN_TOKEN")
    if not tok:
        sys.exit("Set MSTOOL_ADMIN_TOKEN.")
    return {"Authorization": "Bearer " + tok}


def _items(p):
    if isinstance(p, dict) and "items" in p:
        return p["items"]
    return p if isinstance(p, list) else ([] if p is None else [p])


def _get(H, path, timeout=TIMEOUT, **params):
    r = requests.get(API + path, headers=H, params=params, timeout=timeout)
    return r.json() if r.status_code == 200 else None


def _download_nifti_bytes(H, file_id):
    r = requests.get(API + "/imaging/nifti/" + file_id, headers=H, timeout=TIMEOUT)
    return r.content if r.status_code == 200 else None


def _download_expert_mask(H, seg_id):
    r = requests.get(API + "/segmentation/" + seg_id + "/mask/binary", headers=H, timeout=TIMEOUT)
    if r.status_code != 200 or len(r.content) < 12:
        return None
    d, h, w = struct.unpack("<III", r.content[:12])
    body = r.content[12:12 + d * h * w]
    if len(body) != d * h * w:
        return None
    internal = np.frombuffer(body, dtype=np.uint8).reshape((d, h, w))  # (k,a0,a1)
    native = np.transpose(internal, (1, 2, 0)).astype(np.uint8)        # -> (a0,a1,k)
    return native


def _nifti_shape(nifti_bytes):
    with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as t:
        t.write(nifti_bytes); p = t.name
    try:
        return tuple(int(x) for x in nib.load(p).shape[:3])
    finally:
        os.unlink(p)


def _pick_template_image(H, candidates, target_dims):
    """From candidate (file_id, name) images, return (file_id, bytes) of the one
    whose voxel grid matches the 1mm template the expert mask lives on (sorted
    dims == target). Falls back to the first downloadable candidate."""
    fallback = None
    for fid, _name in candidates:
        b = _download_nifti_bytes(H, fid)
        if b is None:
            continue
        try:
            sh = _nifti_shape(b)
        except Exception:
            continue
        if sorted(sh) == list(target_dims):
            return fid, b
        if fallback is None:
            fallback = (fid, b)
    return fallback if fallback else (None, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--expert-idx", default="01")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    H = _H()
    exp_desc = "Expert Rater %s" % args.expert_idx

    print("Listing segmentations (hydrates masks, ~1-3 min)...", flush=True)
    segs = _items(requests.get(API + "/segmentation/list", headers=H,
                               params={"limit": 5000}, timeout=180).json())

    # case -> {expert_seg_id, study_id}
    cases = {}
    for s in segs:
        meta = s.get("metadata", {}) or {}
        if not (meta.get("description") or "").startswith(exp_desc):
            continue
        fid = s.get("file_id") or meta.get("file_id")
        sid = s.get("segmentation_id") or s.get("id")
        study_id = None
        if parse_patient_storage_ref and fid:
            try:
                study_id = parse_patient_storage_ref(fid).study_id
            except Exception:
                study_id = None
        key = study_id or fid
        cases.setdefault(key, {"expert_seg_id": sid, "study_id": study_id})
    print("Cases with %r: %d\n" % (exp_desc, len(cases)), flush=True)

    rows = []
    for i, (key, info) in enumerate(sorted(cases.items()), 1):
        case = "case%03d" % i
        study_id = info["study_id"]
        # Gather ALL T1 / FLAIR candidates (raw AND 1mm-template brain-only) in the study.
        t1_cands, flair_cands = [], []
        if study_id:
            for ser in _items(_get(H, "/studies/" + study_id + "/series")):
                desc = ser.get("series_description", "") or ""
                for inst in _items(_get(H, "/studies/series/" + ser.get("id", "") + "/instances", limit=200)):
                    fid = inst.get("gcs_object_name") or inst.get("file_id")
                    name = inst.get("original_filename", "") or inst.get("filename", "")
                    seq = detect_sequence(desc, name)
                    if seq == SEQ_T1:
                        t1_cands.append((fid, name))
                    elif seq == SEQ_FLAIR:
                        flair_cands.append((fid, name))

        expert = _download_expert_mask(H, info["expert_seg_id"])   # native (a0,a1,k), 1mm template
        if expert is None:
            print("[%2d] %s  expert download failed — skipped" % (i, case), flush=True)
            continue
        target = sorted(expert.shape)   # the 1mm-template dims (e.g. [181,181,217])

        # Pick the T1/FLAIR that live on the SAME 1mm template as the expert mask
        # (brain-only, preprocessed) — NOT the raw 256xN skull images.
        t1_fid, t1b = _pick_template_image(H, t1_cands, target)
        flair_fid, flb = _pick_template_image(H, flair_cands, target)
        if t1b is None or flb is None:
            print("[%2d] %s  no template-space T1/FLAIR (t1=%s flair=%s) — skipped"
                  % (i, case, bool(t1b), bool(flb)), flush=True)
            continue

        t1p = os.path.join(args.out_dir, case + "_t1.nii.gz")
        flp = os.path.join(args.out_dir, case + "_flair.nii.gz")
        gtp = os.path.join(args.out_dir, case + "_gt.nii.gz")
        open(t1p, "wb").write(t1b)
        open(flp, "wb").write(flb)
        nib.save(nib.Nifti1Image(expert, np.eye(4)), gtp)
        rows.append({"case": case, "t1_path": t1p, "flair_path": flp, "expert_path": gtp})
        print("[%2d] %s  ok  (gt %s)" % (i, case, expert.shape), flush=True)

    man = os.path.join(args.out_dir, "cohort.csv")
    with open(man, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["case", "t1_path", "flair_path", "expert_path"])
        w.writeheader(); w.writerows(rows)
    print("\n%d cases -> %s" % (len(rows), man))
    print("Next: run LST-AI, then the experiment:")
    print("  python scripts/run_lstai_cohort.py --manifest %s --out-dir %s --stripped" % (man, args.out_dir))
    print("  python scripts/run_conformal_experiment.py --data-dir %s" % args.out_dir)


if __name__ == "__main__":
    main()
