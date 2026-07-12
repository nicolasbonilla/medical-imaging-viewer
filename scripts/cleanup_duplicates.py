"""
Cleanup duplicate segmentations across all patients.

The segmentation upload was run multiple times, creating duplicate records.
This script keeps only the earliest segmentation for each (file_id, description) pair
and deletes the rest.

Usage:
    python scripts/cleanup_duplicates.py           # dry run (shows what would be deleted)
    python scripts/cleanup_duplicates.py --delete   # actually delete duplicates
"""

import argparse
import sys
import time
from collections import defaultdict

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "https://brain-mri-209356685171.us-central1.run.app/api/v1"
USERNAME = "admin"
import os
PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD")
assert PASSWORD, "Set ADMIN_DEFAULT_PASSWORD env var; do not hardcode the admin password"
# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def login():
    resp = requests.post(
        f"{API_BASE}/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()["token"]["access_token"]
    print(f"[AUTH] Logged in as {USERNAME}")
    return token


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def get_all_patients(token):
    """Get all patients (paginated)."""
    patients = []
    page = 1
    while True:
        resp = requests.get(
            f"{API_BASE}/patients",
            headers=auth_headers(token),
            params={"page": page, "page_size": 50},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        if not items:
            break
        patients.extend(items)
        if isinstance(data, dict) and data.get("total_pages", 1) <= page:
            break
        page += 1
    return patients


def get_studies(token, patient_id):
    resp = requests.get(
        f"{API_BASE}/studies",
        headers=auth_headers(token),
        params={"patient_id": patient_id},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("items", data) if isinstance(data, dict) else data


def get_series(token, study_id):
    resp = requests.get(
        f"{API_BASE}/studies/{study_id}/series",
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_instances(token, series_id):
    resp = requests.get(
        f"{API_BASE}/studies/series/{series_id}/instances",
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_segmentations(token, file_ids):
    """Get segmentations for a list of file_ids (max 30 per Firestore `in` query)."""
    all_segs = []
    # Split into chunks of 30 for Firestore `in` operator limit
    for i in range(0, len(file_ids), 30):
        chunk = file_ids[i : i + 30]
        resp = requests.get(
            f"{API_BASE}/segmentation/list",
            headers=auth_headers(token),
            params={"file_ids": ",".join(chunk)},
            timeout=30,
        )
        resp.raise_for_status()
        all_segs.extend(resp.json())
    return all_segs


def delete_segmentation(token, seg_id):
    resp = requests.delete(
        f"{API_BASE}/segmentation/{seg_id}",
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Cleanup duplicate segmentations")
    parser.add_argument("--delete", action="store_true", help="Actually delete duplicates (default: dry run)")
    args = parser.parse_args()

    print("=" * 60)
    print("Segmentation Duplicate Cleanup")
    if not args.delete:
        print("*** DRY RUN — add --delete to actually remove duplicates ***")
    print(f"API: {API_BASE}")
    print("=" * 60)

    token = login()

    # Get all patients
    patients = get_all_patients(token)
    print(f"\nFound {len(patients)} patients")

    total_duplicates = 0
    total_kept = 0
    total_deleted = 0

    for patient in patients:
        mrn = patient.get("mrn", "?")
        name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}"
        patient_id = patient["id"]

        studies = get_studies(token, patient_id)
        if not studies:
            continue

        patient_dups = 0

        for study in studies:
            study_id = study["id"]

            # Get all file_ids for this study
            file_ids = []
            series_list = get_series(token, study_id)
            for s in series_list:
                instances = get_instances(token, s["id"])
                for inst in instances:
                    gcs = inst.get("gcs_object_name")
                    if gcs:
                        file_ids.append(gcs)

            if not file_ids:
                continue

            # Get all segmentations
            segs = get_segmentations(token, file_ids)
            if not segs:
                continue

            # Group by (file_id, description) to find duplicates
            groups = defaultdict(list)
            for seg in segs:
                key = (seg.get("file_id", ""), seg.get("description", ""))
                groups[key].append(seg)

            # Process each group
            for (file_id, desc), group_segs in groups.items():
                if len(group_segs) <= 1:
                    total_kept += 1
                    continue

                # Sort by created_at — keep earliest
                group_segs.sort(key=lambda s: s.get("created_at", ""))
                keep = group_segs[0]
                duplicates = group_segs[1:]

                total_kept += 1
                patient_dups += len(duplicates)

                for dup in duplicates:
                    total_duplicates += 1
                    if args.delete:
                        try:
                            delete_segmentation(token, dup["segmentation_id"])
                            total_deleted += 1
                            print(f"  [DEL] {desc} (id={dup['segmentation_id'][:8]}...)")
                        except Exception as e:
                            print(f"  [ERR] Failed to delete {dup['segmentation_id']}: {e}")
                    else:
                        print(f"  [DUP] {desc} (id={dup['segmentation_id'][:8]}... created={dup.get('created_at', '?')})")

        if patient_dups > 0:
            print(f"\n[{mrn}] {name}: {patient_dups} duplicates found")

    # Summary
    print(f"\n{'=' * 60}")
    print("CLEANUP SUMMARY")
    print(f"  Unique segmentations kept: {total_kept}")
    print(f"  Duplicates found:          {total_duplicates}")
    if args.delete:
        print(f"  Duplicates deleted:        {total_deleted}")
    else:
        print("  *** DRY RUN — no deletions performed ***")
        print("  Run with --delete to remove duplicates")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
