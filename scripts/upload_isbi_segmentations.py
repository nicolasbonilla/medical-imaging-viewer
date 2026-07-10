"""
Upload ISBI 2015 MS segmentation masks as proper segmentations.

Uploads expert annotations, out_masks, and brain masks so they appear
in the "Segmentations" panel of the viewer.

- Expert annotations (MNI space) → uploaded as images + segmentations
- Out masks (MNI space) → uploaded as images + segmentations
- Brain masks (native space) → segmentations on matching FLAIR images

Usage:
    python scripts/upload_isbi_segmentations.py
"""

import hashlib
import os
import struct
import sys
import time

import nibabel as nib
import numpy as np
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "https://brain-mri-209356685171.us-central1.run.app/api/v1"
USERNAME = "admin"
import os
PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD")
assert PASSWORD, "Set ADMIN_DEFAULT_PASSWORD env var; do not hardcode the admin password"
EXTRACT_DIR = "C:/Users/Nicolas/AppData/Local/Temp/isbi_ms_extract"

# Same patient mapping from upload_isbi_dataset.py
PATIENTS = [
    {"num": 1, "folder": "training/training01"},
    {"num": 2, "folder": "training/training02"},
    {"num": 3, "folder": "training/training03"},
    {"num": 4, "folder": "training/training04"},
    {"num": 5, "folder": "training/training05"},
    {"num": 6, "folder": "testing/test01"},
    {"num": 7, "folder": "testing/test02"},
    {"num": 8, "folder": "testing/test03"},
    {"num": 9, "folder": "testing/test04"},
    {"num": 10, "folder": "testing/test05"},
    {"num": 11, "folder": "testing/test06"},
    {"num": 12, "folder": "testing/test07"},
    {"num": 13, "folder": "testing/test08"},
    {"num": 14, "folder": "testing/test09"},
    {"num": 15, "folder": "testing/test10"},
    {"num": 16, "folder": "testing/test11"},
    {"num": 17, "folder": "testing/test12"},
    {"num": 18, "folder": "testing/test13"},
    {"num": 19, "folder": "testing/test14"},
]

# Series numbers for new uploads (avoid conflict with MRI series 1-4)
SERIES_EXPERT_1 = 7
SERIES_EXPERT_2 = 8
SERIES_OUTMASK_1 = 9
SERIES_OUTMASK_2 = 10

# Label definitions
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


def get_patient_id(token, mrn):
    resp = requests.get(
        f"{API_BASE}/patients",
        headers=auth_headers(token),
        params={"search": mrn},
        timeout=30,
    )
    resp.raise_for_status()
    patients = resp.json()
    if isinstance(patients, dict) and "items" in patients:
        patients = patients["items"]
    for p in patients:
        if p.get("mrn") == mrn:
            return p["id"]
    return None


def get_studies(token, patient_id):
    resp = requests.get(
        f"{API_BASE}/studies",
        headers=auth_headers(token),
        params={"patient_id": patient_id},
        timeout=30,
    )
    resp.raise_for_status()
    studies = resp.json()
    if isinstance(studies, dict) and "items" in studies:
        studies = studies["items"]
    return sorted(studies, key=lambda s: s.get("study_date", ""))


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


def sha256_file(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def upload_file(token, study_id, series_number, filepath, filename):
    """Upload a NIfTI file as an image, return gcs_object_name."""
    file_size = os.path.getsize(filepath)
    checksum = sha256_file(filepath)

    # Init
    resp = requests.post(
        f"{API_BASE}/studies/upload/init",
        json={
            "study_id": study_id,
            "series_number": series_number,
            "filename": filename,
            "content_type": "application/gzip",
            "file_size_bytes": file_size,
            "checksum_sha256": checksum,
        },
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    init = resp.json()

    # PUT to GCS
    with open(filepath, "rb") as f:
        file_data = f.read()
    gcs_headers = init.get("headers", {"Content-Type": "application/gzip"})
    resp = requests.put(init["signed_url"], data=file_data, headers=gcs_headers, timeout=120)
    resp.raise_for_status()

    # Complete
    resp = requests.post(
        f"{API_BASE}/studies/upload/complete",
        json={"upload_id": init["upload_id"], "checksum_sha256": checksum},
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()
    size_mb = file_size / (1024 * 1024)
    print(f"      [UP] {filename} ({size_mb:.1f} MB)")
    return result["gcs_object_name"]


def create_segmentation(token, file_id, rows, columns, slices, description, labels):
    """Create a segmentation record, return segmentation_id."""
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


def upload_mask_binary(token, seg_id, mask_3d):
    """Upload binary mask in (depth, height, width) = (slices, rows, columns) format."""
    depth, height, width = mask_3d.shape
    header = struct.pack("<III", depth, height, width)
    binary_data = header + mask_3d.astype(np.uint8).tobytes()

    resp = requests.put(
        f"{API_BASE}/segmentation/{seg_id}/mask/binary",
        data=binary_data,
        headers={**auth_headers(token), "Content-Type": "application/octet-stream"},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def save_segmentation(token, seg_id):
    """Persist segmentation to cloud storage."""
    resp = requests.post(
        f"{API_BASE}/segmentation/{seg_id}/save",
        headers=auth_headers(token),
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# NIfTI → mask conversion
# ---------------------------------------------------------------------------

def nifti_to_binary_mask(filepath, threshold=0.5):
    """
    Load NIfTI, binarize, and return mask in segmentation format.

    NIfTI shape: (rows, columns, slices)
    Mask format: (slices, rows, columns) = (depth, height, width)

    Returns: (mask_3d, rows, columns, slices)
    """
    img = nib.load(filepath)
    data = img.get_fdata()

    binary = (data > threshold).astype(np.uint8)

    rows, columns, slices = data.shape[0], data.shape[1], data.shape[2]
    # Transpose to (slices, rows, columns)
    mask = np.transpose(binary, (2, 0, 1)).copy()

    return mask, rows, columns, slices


def find_flair_gcs_for_shape(token, studies, target_rows, target_cols, target_slices):
    """
    Find a FLAIR image (series_number=1) whose dimensions match the target.
    Returns gcs_object_name or None.
    """
    for study in studies:
        series_list = get_series(token, study["id"])
        for s in series_list:
            if s.get("series_number") == 1:  # FLAIR
                instances = get_instances(token, s["id"])
                if instances:
                    return instances[0]["gcs_object_name"]
    return None


# ---------------------------------------------------------------------------
# Upload logic per mask type
# ---------------------------------------------------------------------------

def upload_expert_or_outmask(token, study_id, filepath, filename, series_num, description, labels):
    """Upload a MNI-space mask as image + create segmentation on it."""
    # Step 1: Upload NIfTI as an image file
    gcs_name = upload_file(token, study_id, series_num, filepath, filename)

    # Step 2: Load mask data
    mask, rows, cols, slices = nifti_to_binary_mask(filepath)
    nonzero = int(np.sum(mask > 0))

    # Step 3: Create segmentation associated with this image
    seg_id = create_segmentation(token, gcs_name, rows, cols, slices, description, labels)

    # Step 4: Upload binary mask
    upload_mask_binary(token, seg_id, mask)

    # Step 5: Save to cloud
    save_segmentation(token, seg_id)

    print(f"      [SEG] {description} ({nonzero} voxels)")
    return seg_id


def upload_brain_mask(token, studies, filepath, filename):
    """Upload brain mask as segmentation on matching FLAIR image."""
    img = nib.load(filepath)
    rows, cols, slices = img.shape[0], img.shape[1], img.shape[2]

    # Find a FLAIR with matching dimensions
    flair_gcs = find_flair_gcs_for_shape(token, studies, rows, cols, slices)
    if not flair_gcs:
        print(f"      [SKIP] No matching FLAIR found for brain mask ({rows}x{cols}x{slices})")
        return None

    mask, rows, cols, slices = nifti_to_binary_mask(filepath)
    nonzero = int(np.sum(mask > 0))

    seg_id = create_segmentation(
        token, flair_gcs, rows, cols, slices,
        "Brain Extraction Mask", BRAIN_LABELS,
    )
    upload_mask_binary(token, seg_id, mask)
    save_segmentation(token, seg_id)

    print(f"      [SEG] Brain Extraction Mask ({nonzero} voxels) -> FLAIR")
    return seg_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("ISBI MS Dataset — Segmentation Upload")
    print(f"API: {API_BASE}")
    print("=" * 60)

    token = login()
    start_time = time.time()

    stats = {"expert": 0, "outmask": 0, "brain": 0, "failed": 0}

    for p in PATIENTS:
        folder = p["folder"]
        mrn = f"ISBI-MS-{p['num']:03d}"
        patient_dir = os.path.join(EXTRACT_DIR, folder)

        if not os.path.isdir(patient_dir):
            print(f"\n[WARN] Folder not found: {patient_dir}")
            continue

        # Get patient
        patient_id = get_patient_id(token, mrn)
        if not patient_id:
            print(f"\n[WARN] Patient {mrn} not found in API")
            continue

        # Get studies (sorted chronologically)
        studies = get_studies(token, patient_id)
        if not studies:
            print(f"\n[WARN] No studies for {mrn}")
            continue

        first_study_id = studies[0]["id"]

        # Collect mask files
        all_files = os.listdir(patient_dir)
        expert_files = sorted([f for f in all_files if "Expert" in f and f.endswith(".nii.gz")])
        outmask_files = sorted([f for f in all_files if "out_mask" in f and f.endswith(".nii.gz")])
        brain_files = [f for f in all_files if f.startswith("patient") and f.endswith(".nii.gz")]

        mask_count = len(expert_files) + len(outmask_files) + len(brain_files)
        if mask_count == 0:
            continue

        print(f"\n{'='*50}")
        print(f"Patient {p['num']} ({mrn}): {len(expert_files)} experts, {len(outmask_files)} out_masks, {len(brain_files)} brain masks")
        print(f"{'='*50}")

        # --- Expert Annotations ---
        series_map = {}  # filename -> series_number (to avoid duplicates)
        for i, ef in enumerate(expert_files):
            expert_path = os.path.join(patient_dir, ef)
            series_num = SERIES_EXPERT_1 + i

            # Parse rater number from filename (Expert01_01 → Rater 1, Expert01_02 → Rater 2)
            parts = ef.replace(".nii.gz", "").split("_")
            rater = parts[-1] if len(parts) >= 2 else str(i + 1)
            description = f"Expert Rater {rater} - MS Lesion Annotation"

            try:
                upload_expert_or_outmask(
                    token, first_study_id, expert_path, ef,
                    series_num, description, LESION_LABELS,
                )
                stats["expert"] += 1
            except Exception as e:
                print(f"      [ERROR] {ef}: {e}")
                stats["failed"] += 1

        # --- Out Masks ---
        for i, of in enumerate(outmask_files):
            out_path = os.path.join(patient_dir, of)
            series_num = SERIES_OUTMASK_1 + i

            mask_label = of.replace("out_mask", "").replace(".nii.gz", "") or "1"
            description = f"Output Mask {mask_label} - Lesion Prediction"

            try:
                upload_expert_or_outmask(
                    token, first_study_id, out_path, of,
                    series_num, description, OUTPUT_LABELS,
                )
                stats["outmask"] += 1
            except Exception as e:
                print(f"      [ERROR] {of}: {e}")
                stats["failed"] += 1

        # --- Brain Masks ---
        for bf in brain_files:
            brain_path = os.path.join(patient_dir, bf)
            try:
                upload_brain_mask(token, studies, brain_path, bf)
                stats["brain"] += 1
            except Exception as e:
                print(f"      [ERROR] {bf}: {e}")
                stats["failed"] += 1

    # Summary
    elapsed = time.time() - start_time
    total = stats["expert"] + stats["outmask"] + stats["brain"]
    print(f"\n{'='*60}")
    print("SEGMENTATION UPLOAD COMPLETE")
    print(f"  Expert annotations: {stats['expert']}")
    print(f"  Output masks:       {stats['outmask']}")
    print(f"  Brain masks:        {stats['brain']}")
    print(f"  Total:              {total}")
    print(f"  Failed:             {stats['failed']}")
    print(f"  Time:               {elapsed/60:.1f} minutes")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
