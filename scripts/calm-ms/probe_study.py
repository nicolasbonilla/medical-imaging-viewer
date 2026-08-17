#!/usr/bin/env python3
"""List EVERY series + instance of one case's study (no sequence filtering).

Reveals how the preprocessed brain-only 1mm images are named/described in the
app, so the cohort pull can select them correctly. Cheap: metadata only, no NIfTI
downloads. Admin token via MSTOOL_ADMIN_TOKEN.

    python scripts/calm-ms/probe_study.py            # first Expert Rater 01 case
    python scripts/calm-ms/probe_study.py --study <study_id>
"""
import argparse
import os
import sys

import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
try:
    from app.security.storage_access import parse_patient_storage_ref
except Exception:
    parse_patient_storage_ref = None

API = os.environ.get("MSTOOL_API_BASE", "https://brain-mri-7bp6oqdu7a-uc.a.run.app/api/v1").rstrip("/")


def _H():
    tok = os.environ.get("MSTOOL_ADMIN_TOKEN")
    if not tok:
        sys.exit("Set MSTOOL_ADMIN_TOKEN.")
    return {"Authorization": "Bearer " + tok}


def _items(p):
    if isinstance(p, dict) and "items" in p:
        return p["items"]
    return p if isinstance(p, list) else ([] if p is None else [p])


def _get(H, path, timeout=60, **params):
    r = requests.get(API + path, headers=H, params=params, timeout=timeout)
    return r.json() if r.status_code == 200 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--study")
    args = ap.parse_args()
    H = _H()

    study_id = args.study
    if not study_id:
        print("Finding first 'Expert Rater 01' case...", flush=True)
        segs = _items(requests.get(API + "/segmentation/list", headers=H,
                                   params={"limit": 5000}, timeout=180).json())
        for s in segs:
            meta = s.get("metadata", {}) or {}
            if (meta.get("description") or "").startswith("Expert Rater 01"):
                fid = s.get("file_id") or meta.get("file_id")
                if parse_patient_storage_ref and fid:
                    try:
                        study_id = parse_patient_storage_ref(fid).study_id
                        break
                    except Exception:
                        pass
        if not study_id:
            sys.exit("could not resolve a study_id")

    print("STUDY %s\n" % study_id + "=" * 78)
    for ser in _items(_get(H, "/studies/" + study_id + "/series")):
        sid = ser.get("id", "")
        print("\nSERIES  desc=%r  number=%s  id=%s"
              % (ser.get("series_description", ""), ser.get("series_number", ""), sid[:8]))
        for inst in _items(_get(H, "/studies/series/" + sid + "/instances", limit=500)):
            fname = inst.get("original_filename") or inst.get("filename") or ""
            gcs = inst.get("gcs_object_name") or inst.get("file_id") or ""
            geom = ""
            for k in ("rows", "columns", "number_of_frames", "slice_thickness", "pixel_spacing"):
                if inst.get(k) is not None:
                    geom += " %s=%s" % (k, inst.get(k))
            print("    inst  file=%r%s" % (fname, geom))
            print("          gcs=%s" % gcs)


if __name__ == "__main__":
    main()
