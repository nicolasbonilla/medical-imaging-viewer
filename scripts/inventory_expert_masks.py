#!/usr/bin/env python3
"""Phase 0 — inventory ALL expert ground-truth masks for the validation pipeline.

Generalizes scripts/audit_expert_masks.py (which was hard-scoped to ISBI 001-005)
to the whole dataset, and enriches each case with:
  - conservative provenance (human_expert / algorithm / unknown) — see
    app/services/dataset_inventory.classify_provenance,
  - MRI sequence per study (heuristic from series_description / filename),
  - rater index, mask depth, study date,
and rolls up benchmark eligibility: multi-rater studies (Phase 2 inter-rater
baseline), longitudinal patients, and LST-AI-ready studies (T1+FLAIR, Phase 3).

Writes a JSON manifest and prints a human summary. NEVER hardcodes credentials.

Run (from the repo root or scripts/):
    # Option A — pre-minted admin bearer token (preferred; no password in shell)
    export MSTOOL_API_BASE="https://brain-mri-7bp6oqdu7a-uc.a.run.app/api/v1"
    export MSTOOL_ADMIN_TOKEN="<bearer>"
    python scripts/inventory_expert_masks.py --out inventory_manifest.json

    # Option B — username/password login (password from env, never inline)
    export ADMIN_DEFAULT_PASSWORD="<admin password>"
    python scripts/inventory_expert_masks.py
"""
import argparse
import json
import os
import sys

import requests

# Make the backend package importable so we can reuse the tested inventory logic.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.dataset_inventory import (  # noqa: E402
    build_manifest,
    detect_sequence,
    sequences_available,
    is_lst_ai_ready,
)

API = os.environ.get(
    "MSTOOL_API_BASE",
    "https://brain-mri-7bp6oqdu7a-uc.a.run.app/api/v1",
).rstrip("/")
SEP = "=" * 80
TIMEOUT = 60


# ---------------------------------------------------------------------------
# HTTP helpers (response-shape tolerant: some endpoints wrap in {"items": [...]})
# ---------------------------------------------------------------------------

def _auth_headers():
    token = os.environ.get("MSTOOL_ADMIN_TOKEN")
    if token:
        print("[OK] Using MSTOOL_ADMIN_TOKEN")
        return {"Authorization": "Bearer " + token}
    password = os.environ.get("ADMIN_DEFAULT_PASSWORD")
    if not password:
        sys.exit(
            "Provide MSTOOL_ADMIN_TOKEN (preferred) or ADMIN_DEFAULT_PASSWORD.\n"
            "Never hardcode the production admin password."
        )
    r = requests.post(API + "/auth/login",
                      json={"username": "admin", "password": password}, timeout=TIMEOUT)
    r.raise_for_status()
    token = r.json()["token"]["access_token"]
    print("[OK] Logged in via password")
    return {"Authorization": "Bearer " + token}


def _get(headers, path, **params):
    r = requests.get(API + path, headers=headers, params=params, timeout=TIMEOUT)
    if r.status_code != 200:
        return None
    return r.json()


def _items(payload):
    if isinstance(payload, dict) and "items" in payload:
        return payload["items"]
    if isinstance(payload, list):
        return payload
    if payload is None:
        return []
    return [payload]


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_patients(H):
    return _items(_get(H, "/patients", limit=500))


def fetch_studies(H, patient_id):
    data = _get(H, "/studies/patient/" + patient_id, limit=200)
    if data is None:
        data = _get(H, "/studies", patient_id=patient_id, limit=200)
    studies = _items(data)
    studies.sort(key=lambda s: s.get("study_date", "") or "")
    return studies


def fetch_study_instances(H, study_id):
    """Return list of instances enriched with their series_description."""
    out = []
    for ser in _items(_get(H, "/studies/" + study_id + "/series")):
        ser_id = ser.get("id", "")
        ser_desc = ser.get("series_description", "") or ""
        for inst in _items(_get(H, "/studies/series/" + ser_id + "/instances", limit=500)):
            inst["_series_description"] = ser_desc
            out.append(inst)
    return out


def fetch_segmentations(H, study_id):
    data = _get(H, "/segmentation/list", study_id=study_id, limit=200)
    return _items(data)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Inventory expert ground-truth masks (Phase 0).")
    ap.add_argument("--out", default="inventory_manifest.json", help="Manifest JSON output path.")
    args = ap.parse_args()

    H = _auth_headers()
    print(SEP)
    print("EXPERT MASK INVENTORY  (API: %s)" % API)
    print(SEP)

    patients = fetch_patients(H)
    print("Patients: %d\n" % len(patients))

    seg_records = []
    study_index = {}

    for p in patients:
        pid = p.get("id")
        mrn = p.get("mrn") or p.get("full_name") or pid
        if not pid:
            continue
        studies = fetch_studies(H, pid)
        for study in studies:
            sid = study.get("id")
            study_date = study.get("study_date") or ""
            instances = fetch_study_instances(H, sid)

            # Study-level sequence inventory (from every series in the study).
            series_texts = [
                "%s %s" % (i.get("_series_description", ""),
                           i.get("filename", "") or i.get("original_filename", ""))
                for i in instances
            ]
            seqs = sequences_available(series_texts)
            study_index[sid] = {
                "patient_mrn": mrn,
                "patient_id": pid,
                "study_date": study_date,
                "sequences": sorted(seqs),
                "lst_ai_ready": is_lst_ai_ready(seqs),
            }

            # Map each source image (file_id == gcs_object_name) -> descriptive text.
            file_text = {}
            for i in instances:
                fid = i.get("gcs_object_name") or i.get("file_id")
                if fid:
                    file_text[fid] = "%s %s" % (
                        i.get("_series_description", ""),
                        i.get("filename", "") or i.get("original_filename", ""),
                    )

            for seg in fetch_segmentations(H, sid):
                meta = seg.get("metadata", {}) or {}
                fid = seg.get("file_id") or meta.get("file_id")
                seg_records.append({
                    "seg_id": seg.get("segmentation_id") or seg.get("id"),
                    "file_id": fid,
                    "description": meta.get("description") or seg.get("description") or "",
                    "validation_source": meta.get("validation_source") or seg.get("validation_source"),
                    "segmentation_type": seg.get("segmentation_type"),
                    "created_by": seg.get("created_by"),
                    "mask_shape": seg.get("mask_shape") or [seg.get("total_slices")],
                    "patient_mrn": mrn,
                    "patient_id": pid,
                    "study_id": sid,
                    "study_date": study_date,
                    "source_text": file_text.get(fid, ""),
                })

    manifest = build_manifest(seg_records, study_index)

    # --- write + summarize ---
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"api": API, "study_index": study_index, "manifest": manifest}, f, indent=2, default=str)

    print(SEP)
    print("SUMMARY")
    print(SEP)
    print("Total segmentations:        %d" % manifest["total_segmentations"])
    print("  human_expert:             %d" % manifest["human_expert_count"])
    print("  algorithm:                %d" % manifest["algorithm_count"])
    print("  unknown:                  %d" % manifest["unknown_count"])
    print("Distinct patients:          %d" % len(manifest["distinct_patients"]))
    print("Multi-rater studies (>=2):  %d  %s" % (
        len(manifest["multi_rater_studies"]), manifest["multi_rater_studies"][:10]))
    print("Longitudinal patients:      %d  %s" % (
        len(manifest["longitudinal_patients"]), manifest["longitudinal_patients"][:10]))
    print("LST-AI-ready studies (T1+FLAIR): %d" % manifest["lst_ai_ready_study_count"])
    print()
    print("Caveats: provenance is BEST-EFFORT (no authoritative human/algorithm")
    print("flag exists); MRI sequence is HEURISTIC (parsed from free text). Review")
    print("'unknown' rows and any single-rater 'multi-rater' before Phase 2/3.")
    print()
    print("Manifest written to: %s" % os.path.abspath(args.out))


if __name__ == "__main__":
    main()
