"""
Fix two data issues across all 19 ISBI-MS patients:

1. Duplicate preprocessed images (patients 001-004): delete extra copies
2. Segmentation timepoint mismatches (all patients): move "02" segmentations to Timepoint 2

The "02" segmentations (Expert Rater 02, Output Mask 2) are currently in Timepoint 1
but should be in Timepoint 2. This script:
  - Downloads the mask data from the old segmentation
  - Finds the preprocessed FLAIR image in TP2
  - Creates a new segmentation on the TP2 image
  - Uploads the mask data
  - Saves and deletes the old segmentation

Usage:
    python scripts/fix_timepoints_and_duplicates.py --dry-run     # preview changes
    python scripts/fix_timepoints_and_duplicates.py --fix          # apply fixes
"""

import argparse
import struct
import sys
import time
from collections import defaultdict

import numpy as np
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "https://brain-mri-209356685171.us-central1.run.app/api/v1"
USERNAME = "admin"
PASSWORD = "Admin123!@2024"


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
    print(f"[AUTH] Logged in")
    return token


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def get_all_patients(token):
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
    items = data.get("items", data) if isinstance(data, dict) else data
    return sorted(items, key=lambda s: s.get("study_date", ""))


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
    all_segs = []
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


def download_mask_binary(token, seg_id):
    """Download binary mask data. Returns (depth, height, width, mask_bytes)."""
    resp = requests.get(
        f"{API_BASE}/segmentation/{seg_id}/mask/binary",
        headers=auth_headers(token),
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.content
    depth, height, width = struct.unpack("<III", data[:12])
    mask_bytes = data[12:]
    return depth, height, width, mask_bytes


def create_segmentation(token, file_id, rows, columns, slices, description, labels):
    resp = requests.post(
        f"{API_BASE}/segmentation/create",
        json={
            "file_id": file_id,
            "image_shape": {"rows": rows, "columns": columns, "slices": slices},
            "description": description,
            "labels": labels,
        },
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["segmentation_id"]


def upload_mask_binary(token, seg_id, binary_data):
    """Upload binary mask (with header already included)."""
    resp = requests.put(
        f"{API_BASE}/segmentation/{seg_id}/mask/binary",
        data=binary_data,
        headers={**auth_headers(token), "Content-Type": "application/octet-stream"},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def save_segmentation(token, seg_id):
    resp = requests.post(
        f"{API_BASE}/segmentation/{seg_id}/save",
        headers=auth_headers(token),
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def delete_segmentation(token, seg_id):
    resp = requests.delete(
        f"{API_BASE}/segmentation/{seg_id}",
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()


def delete_instance(token, instance_id):
    resp = requests.delete(
        f"{API_BASE}/studies/instances/{instance_id}",
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Label definitions (same as upload script)
# ---------------------------------------------------------------------------

LESION_LABELS = [
    {"id": 0, "name": "Background", "color": "#000000", "opacity": 0.0, "visible": False},
    {"id": 1, "name": "MS Lesion", "color": "#FF4444", "opacity": 0.6, "visible": True},
]

OUTPUT_LABELS = [
    {"id": 0, "name": "Background", "color": "#000000", "opacity": 0.0, "visible": False},
    {"id": 1, "name": "Detected Lesion", "color": "#44FF44", "opacity": 0.6, "visible": True},
]

BRAIN_LABELS = [
    {"id": 0, "name": "Background", "color": "#000000", "opacity": 0.0, "visible": False},
    {"id": 1, "name": "Brain Tissue", "color": "#4488FF", "opacity": 0.4, "visible": True},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_preprocessed(filename):
    lower = filename.lower()
    return lower.endswith("_pp.nii") or lower.endswith("_pp.nii.gz")


def is_mask_instance(filename):
    lower = filename.lower()
    return "expert" in lower or "out_mask" in lower or lower.startswith("patient")


def get_seg_description(seg):
    """Get description from segmentation (nested under metadata)."""
    meta = seg.get("metadata", {})
    if isinstance(meta, dict):
        return meta.get("description", "") or ""
    return seg.get("description", "") or ""


def is_tp2_segmentation(description):
    """Check if segmentation description indicates timepoint 2."""
    if not description:
        return False
    desc_lower = description.lower()
    # "Expert Rater 02" → timepoint 2
    if "rater 02" in desc_lower or "rater 2 " in desc_lower:
        return True
    # "Output Mask 2" → timepoint 2
    if "mask 2" in desc_lower:
        return True
    return False


def get_labels_for_description(description):
    if not description:
        return LESION_LABELS
    desc_lower = description.lower()
    if "expert" in desc_lower:
        return LESION_LABELS
    if "output mask" in desc_lower:
        return OUTPUT_LABELS
    if "brain" in desc_lower:
        return BRAIN_LABELS
    return LESION_LABELS


def get_study_instances_map(token, studies):
    """
    Returns dict: study_id -> {
        "study": study_dict,
        "instances": [instance_dicts with series info],
        "file_ids": [gcs_object_names],
    }
    """
    result = {}
    for study in studies:
        sid = study["id"]
        instances = []
        file_ids = []
        series_list = get_series(token, sid)
        for s in series_list:
            for inst in get_instances(token, s["id"]):
                inst["_series_number"] = s.get("series_number")
                instances.append(inst)
                gcs = inst.get("gcs_object_name")
                if gcs:
                    file_ids.append(gcs)
        result[sid] = {
            "study": study,
            "instances": instances,
            "file_ids": file_ids,
        }
    return result


# ---------------------------------------------------------------------------
# Fix 1: Delete duplicate preprocessed images
# ---------------------------------------------------------------------------

def fix_duplicate_preprocessed(token, studies_map, dry_run=True):
    """Delete duplicate preprocessed instances within each study."""
    deleted = 0
    for sid, info in studies_map.items():
        # Group preprocessed instances by filename
        pp_groups = defaultdict(list)
        for inst in info["instances"]:
            fname = inst.get("original_filename", "")
            if is_preprocessed(fname):
                pp_groups[fname].append(inst)

        for fname, instances in pp_groups.items():
            if len(instances) <= 1:
                continue
            # Keep first, delete rest
            keep = instances[0]
            for dup in instances[1:]:
                if dry_run:
                    print(f"    [DRY] Would delete duplicate: {fname} (id={dup['id'][:8]}...)")
                else:
                    try:
                        delete_instance(token, dup["id"])
                        print(f"    [DEL] {fname} (id={dup['id'][:8]}...)")
                    except Exception as e:
                        print(f"    [ERR] Failed to delete {dup['id']}: {e}")
                deleted += 1
    return deleted


# ---------------------------------------------------------------------------
# Fix 2: Move TP2 segmentations to correct timepoint
# ---------------------------------------------------------------------------

def fix_segmentation_timepoints(token, studies, studies_map, dry_run=True):
    """
    Move "02" segmentations from TP1 to TP2.

    Strategy:
    - Download mask from old segmentation
    - Find a preprocessed FLAIR image in TP2
    - Create new segmentation pointing to TP2 image
    - Upload mask data
    - Delete old segmentation
    """
    moved = 0

    if len(studies) < 2:
        return 0

    tp1_study = studies[0]
    tp2_study = studies[1]
    tp1_id = tp1_study["id"]
    tp2_id = tp2_study["id"]

    tp1_info = studies_map[tp1_id]
    tp2_info = studies_map[tp2_id]

    # Find preprocessed FLAIR in TP2 (for the segmentation target)
    tp2_flair_pp = None
    for inst in tp2_info["instances"]:
        fname = inst.get("original_filename", "").lower()
        if "flair" in fname and is_preprocessed(fname):
            tp2_flair_pp = inst
            break

    # Fallback: any preprocessed image in TP2
    if not tp2_flair_pp:
        for inst in tp2_info["instances"]:
            fname = inst.get("original_filename", "")
            if is_preprocessed(fname):
                tp2_flair_pp = inst
                break

    if not tp2_flair_pp:
        print("    [WARN] No preprocessed image found in TP2, skipping segmentation fix")
        return 0

    tp2_target_file_id = tp2_flair_pp["gcs_object_name"]

    # Get all segmentations from TP1
    if not tp1_info["file_ids"]:
        return 0

    segs = get_segmentations(token, tp1_info["file_ids"])

    for seg in segs:
        desc = get_seg_description(seg)
        seg_id = seg.get("segmentation_id", "")

        if not is_tp2_segmentation(desc):
            continue

        if dry_run:
            print(f"    [DRY] Would move '{desc}' from TP1 to TP2 (-> {tp2_flair_pp['original_filename']})")
            moved += 1
            continue

        try:
            # Step 1: Download mask
            depth, height, width = 0, 0, 0
            mask_binary = None
            try:
                depth, height, width, mask_bytes = download_mask_binary(token, seg_id)
                # Reconstruct full binary (header + data)
                mask_binary = struct.pack("<III", depth, height, width) + mask_bytes
            except Exception as e:
                print(f"    [WARN] Could not download mask for {seg_id}: {e}")
                # Try to get dimensions from segmentation metadata
                continue

            # Step 2: Delete old segmentation
            delete_segmentation(token, seg_id)

            # Step 3: Create new segmentation on TP2 image
            # Note: image_shape is (rows, columns, slices) but mask is (depth=slices, height=rows, width=columns)
            labels = get_labels_for_description(desc)
            new_seg_id = create_segmentation(
                token, tp2_target_file_id,
                height, width, depth,  # rows=height, columns=width, slices=depth
                desc, labels,
            )

            # Step 4: Upload mask
            if mask_binary:
                upload_mask_binary(token, new_seg_id, mask_binary)

            # Step 5: Save
            save_segmentation(token, new_seg_id)

            print(f"    [MOV] '{desc}' -> TP2 (new_id={new_seg_id[:8]}...)")
            moved += 1

        except Exception as e:
            print(f"    [ERR] Failed to move '{desc}': {e}")

    return moved


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fix timepoint mismatches and duplicate preprocessed images")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    group.add_argument("--fix", action="store_true", help="Apply fixes")
    args = parser.parse_args()

    dry_run = args.dry_run

    print("=" * 60)
    print("Fix Timepoints & Duplicate Preprocessed Images")
    if dry_run:
        print("*** DRY RUN — add --fix to apply changes ***")
    print(f"API: {API_BASE}")
    print("=" * 60)

    token = login()
    start = time.time()

    patients = get_all_patients(token)
    # Filter to ISBI-MS patients only
    isbi_patients = [p for p in patients if (p.get("mrn", "") or "").startswith("ISBI-MS-")]
    isbi_patients.sort(key=lambda p: p.get("mrn", ""))
    print(f"\nFound {len(isbi_patients)} ISBI-MS patients\n")

    total_pp_deleted = 0
    total_seg_moved = 0

    for patient in isbi_patients:
        mrn = patient.get("mrn", "?")
        name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()
        patient_id = patient["id"]

        studies = get_studies(token, patient_id)
        if not studies:
            continue

        print(f"\n[{mrn}] {name} ({len(studies)} timepoints)")

        # Build instance map for all studies
        studies_map = get_study_instances_map(token, studies)

        # Fix 1: Duplicate preprocessed
        pp_deleted = fix_duplicate_preprocessed(token, studies_map, dry_run)
        if pp_deleted > 0:
            total_pp_deleted += pp_deleted
            print(f"  Preprocessed duplicates: {pp_deleted}")

        # Fix 2: Segmentation timepoints
        seg_moved = fix_segmentation_timepoints(token, studies, studies_map, dry_run)
        if seg_moved > 0:
            total_seg_moved += seg_moved
            print(f"  Segmentations moved to TP2: {seg_moved}")

        if pp_deleted == 0 and seg_moved == 0:
            print(f"  OK - no issues")

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"  Preprocessed duplicates {'would be ' if dry_run else ''}deleted: {total_pp_deleted}")
    print(f"  Segmentations {'would be ' if dry_run else ''}moved to TP2: {total_seg_moved}")
    print(f"  Time: {elapsed:.0f}s")
    if dry_run:
        print("  *** DRY RUN — run with --fix to apply ***")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
