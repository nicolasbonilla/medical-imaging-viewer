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
TIMEOUT = 30


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


def fetch_segmentations_all(H):
    """The whole segmentations collection (admin sees all; the study_id filter on
    /segmentation/list is not applied server-side). The endpoint hydrates every
    mask from GCS, so it is SLOW — use a long timeout and retry."""
    last = None
    for attempt in range(3):
        try:
            r = requests.get(API + "/segmentation/list", headers=H,
                             params={"limit": 5000}, timeout=180)
            if r.status_code == 200:
                return _items(r.json())
            last = "HTTP %s" % r.status_code
        except requests.exceptions.RequestException as e:
            last = str(e)
        print("  list attempt %d failed (%s), retrying..." % (attempt + 1, last), flush=True)
    sys.exit("Could not list segmentations after retries: %s" % last)


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

    # The list endpoint returns the WHOLE collection for an admin token (the
    # study_id filter is not applied) — so ONE call yields every distinct
    # segmentation. We then map each to its true case by PARSING its file_id
    # (patients/{pid}/studies/{sid}/series/{serid}/{file}), not by which study
    # loop it came from (the earlier bug that inflated counts 83x).
    try:
        from app.security.storage_access import parse_patient_storage_ref
    except Exception:
        parse_patient_storage_ref = None

    all_segs = fetch_segmentations_all(H)
    print("Distinct segmentations in system: %d\n" % len(all_segs), flush=True)

    # Lightweight lookup maps: patient_id -> MRN, study_id -> (date, patient_id).
    patients = fetch_patients(H)
    pid2mrn = {p.get("id"): (p.get("mrn") or p.get("full_name") or p.get("id")) for p in patients}
    study_meta = {}
    for p in patients:
        for s in fetch_studies(H, p.get("id")):
            study_meta[s.get("id")] = {"date": s.get("study_date") or "", "patient_id": p.get("id")}

    seg_records = []
    for seg in all_segs:
        meta = seg.get("metadata", {}) or {}
        fid = seg.get("file_id") or meta.get("file_id") or ""
        pid = sid = None
        if parse_patient_storage_ref and fid:
            try:
                ref = parse_patient_storage_ref(fid)
                pid, sid = ref.patient_id, ref.study_id
            except Exception:
                pid = sid = None
        smeta = study_meta.get(sid, {})
        seg_records.append({
            "seg_id": seg.get("segmentation_id") or seg.get("id"),
            "file_id": fid,
            "description": meta.get("description") or seg.get("description") or "",
            "validation_source": meta.get("validation_source") or seg.get("validation_source"),
            "segmentation_type": seg.get("segmentation_type"),
            "created_by": seg.get("created_by"),
            "mask_shape": seg.get("mask_shape") or [seg.get("total_slices")],
            "patient_mrn": pid2mrn.get(pid, pid),
            "patient_id": pid,
            "study_id": sid,
            "study_date": smeta.get("date", ""),
            "source_text": fid,
        })

    # Study index (sequences unknown here — filled only if needed later).
    study_index = {}
    for r in seg_records:
        if r["study_id"] and r["study_id"] not in study_index:
            study_index[r["study_id"]] = {
                "patient_mrn": r["patient_mrn"], "patient_id": r["patient_id"],
                "study_date": r["study_date"], "sequences": [], "lst_ai_ready": False,
            }

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
