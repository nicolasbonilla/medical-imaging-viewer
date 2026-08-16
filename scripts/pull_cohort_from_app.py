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


def _pick_preproc(candidates):
    """Prefer the BIDS 'desc-preproc' (brain-only, template) image the expert masks
    were drawn on; fall back to the first candidate. candidates = [(file_id, name)]."""
    pre = [c for c in candidates if "preproc" in (c[1] or "").lower()]
    pool = pre if pre else candidates
    return pool[0] if pool else (None, None)


def _save_niigz(nifti_bytes, src_name, dst_path):
    """Persist downloaded bytes (source .nii or .nii.gz) normalized to .nii.gz."""
    ext = ".nii.gz" if str(src_name).lower().endswith(".gz") else ".nii"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as t:
        t.write(nifti_bytes); p = t.name
    try:
        nib.save(nib.load(p), dst_path)
    finally:
        os.unlink(p)


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

        # Pick the brain-only 'desc-preproc' T1/FLAIR the expert masks were drawn
        # on — NOT the raw 256xN skull images.
        (t1_fid, t1name) = _pick_preproc(t1_cands)
        (flair_fid, flname) = _pick_preproc(flair_cands)
        if not (t1_fid and flair_fid):
            print("[%2d] %s  missing preproc T1/FLAIR — skipped" % (i, case), flush=True)
            continue

        t1b = _download_nifti_bytes(H, t1_fid)
        flb = _download_nifti_bytes(H, flair_fid)
        expert = _download_expert_mask(H, info["expert_seg_id"])
        if t1b is None or flb is None or expert is None:
            print("[%2d] %s  download failed — skipped" % (i, case), flush=True)
            continue

        t1p = os.path.join(args.out_dir, case + "_t1.nii.gz")
        flp = os.path.join(args.out_dir, case + "_flair.nii.gz")
        gtp = os.path.join(args.out_dir, case + "_gt.nii.gz")
        _save_niigz(t1b, t1name, t1p)
        _save_niigz(flb, flname, flp)
        nib.save(nib.Nifti1Image(expert, np.eye(4)), gtp)
        rows.append({"case": case, "t1_path": t1p, "flair_path": flp, "expert_path": gtp})
        pre = "preproc" if "preproc" in (t1name or "").lower() else "RAW-fallback"
        print("[%2d] %s  ok  (%s; gt %s)" % (i, case, pre, expert.shape), flush=True)

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
