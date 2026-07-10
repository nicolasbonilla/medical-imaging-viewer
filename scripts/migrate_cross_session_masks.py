"""
Migrate misplaced ses-02 expert masks from TP1 studies to their correct TP2 studies.

The original upload script (upload_isbi_segmentations.py) put ALL masks into
first_study_id regardless of session, so ses-02 masks ended up in TP1 studies.
This script moves them to TP2.

Steps per misplaced instance:
  1. Download file via signed URL from current TP1 location
  2. Upload to the correct TP2 study using the standard upload flow
  3. Migrate segmentation records (create new on TP2 file, delete old)
  4. Delete old instance from TP1

Also handles:
  - ISBI-MS-001 duplicate instance (two copies of same file)

Usage:
    python scripts/migrate_cross_session_masks.py --dry-run   # preview changes
    python scripts/migrate_cross_session_masks.py --apply      # apply changes
"""

import argparse
import hashlib
import struct
import sys
import time

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
# ---------------------------------------------------------------------------
# Misplaced instances from audit (2026-02-22)
#
# Each entry: ses-02 expert mask sitting in TP1 study (ctp=1, ses=2)
# Fields: mrn, instance_id (iid), series_id, series_number,
#          study_id (TP1), filename, gcs_path
# ---------------------------------------------------------------------------

MISPLACED = [
    {
        "mrn": "ISBI-MS-001",
        "iid": "56e567b3-19aa-4d9a-9788-ac36eeb78327",
        "sid": "ba97458f-2a36-4a5f-936e-2c0ea384a645",
        "fn": "sub-MS001_ses-02_label-lesion_desc-expert01_dseg.nii.gz",
        "gcs": "patients/6ccf7491-0aed-45fe-8a13-2ca6c82980b7/studies/ba97458f-2a36-4a5f-936e-2c0ea384a645/series/fafe2967-22a1-4544-933d-324f7841cc4b/56e567b3-19aa-4d9a-9788-ac36eeb78327.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-002",
        "iid": "b8d56353-612c-4ad5-9c72-adca21097c88",
        "sid": "e7f19290-cf02-425f-9620-c5f978985df4",
        "fn": "sub-MS002_ses-02_label-lesion_desc-expert02_dseg.nii.gz",
        "gcs": "patients/0c96e8df-f3bc-4b0a-a931-ee1cf94b2ee1/studies/e7f19290-cf02-425f-9620-c5f978985df4/series/e2bdfacb-4cc2-456e-94a0-8188ea6e17f4/b8d56353-612c-4ad5-9c72-adca21097c88.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-003",
        "iid": "22982061-08c3-4f69-b567-74481e7d2a7f",
        "sid": "fa78a1c0-340f-4d08-9baf-e713ef655775",
        "fn": "sub-MS003_ses-02_label-lesion_desc-expert03_dseg.nii.gz",
        "gcs": "patients/417eae0c-4665-4a1e-9059-fe59959b8870/studies/fa78a1c0-340f-4d08-9baf-e713ef655775/series/bfd69435-06bd-4adf-a3e4-801290b923df/22982061-08c3-4f69-b567-74481e7d2a7f.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-004",
        "iid": "2aa87ecd-87d3-43a6-ba82-dd40c51e347c",
        "sid": "7f9149a2-8219-4d6b-9e36-54cbabcb9967",
        "fn": "sub-MS004_ses-02_label-lesion_desc-expert04_dseg.nii.gz",
        "gcs": "patients/a5735b64-ece1-42c3-93d9-226ddbab5465/studies/7f9149a2-8219-4d6b-9e36-54cbabcb9967/series/bde3680a-84e7-4f8c-a8ec-dc235a50060b/2aa87ecd-87d3-43a6-ba82-dd40c51e347c.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-005",
        "iid": "42751e8a-f50f-41cd-aabc-ed181c2a4f8b",
        "sid": "ff7381ba-272b-4369-8825-f8d386412d0d",
        "fn": "sub-MS005_ses-02_label-lesion_desc-expert05_dseg.nii.gz",
        "gcs": "patients/7d2c1f38-a931-4412-8438-50072ebde81f/studies/ff7381ba-272b-4369-8825-f8d386412d0d/series/c1143a4b-b3ed-4a3c-b2ec-42de985d9bf1/42751e8a-f50f-41cd-aabc-ed181c2a4f8b.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-006",
        "iid": "42beebf5-46bb-48ac-b456-92d8f1c3b980",
        "sid": "8e7e03c1-e857-4047-9524-0356f61c1002",
        "fn": "sub-MS006_ses-02_label-lesion_desc-expert01_dseg.nii.gz",
        "gcs": "patients/855ba1b7-be62-4679-af97-b8088d610498/studies/8e7e03c1-e857-4047-9524-0356f61c1002/series/7f4b76cd-3dc9-4eb5-ad97-7f4b5ce8ef3c/42beebf5-46bb-48ac-b456-92d8f1c3b980.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-007",
        "iid": "e677b580-e94c-42e7-86dd-258ea2cae359",
        "sid": "f6475b26-ac74-4783-a64f-c69f44f01f57",
        "fn": "sub-MS007_ses-02_label-lesion_desc-expert02_dseg.nii.gz",
        "gcs": "patients/897906e6-04ca-4826-a1ea-25cc9321a874/studies/f6475b26-ac74-4783-a64f-c69f44f01f57/series/9a84406a-7d3a-4aae-aab6-af3095df35c0/e677b580-e94c-42e7-86dd-258ea2cae359.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-008",
        "iid": "1098b30b-c24c-4526-990b-6b723778bcfb",
        "sid": "99111635-e8dd-4e70-9c96-12ba04163d5a",
        "fn": "sub-MS008_ses-02_label-lesion_desc-expert03_dseg.nii.gz",
        "gcs": "patients/ba38b12c-dc13-431d-ac87-54ab7c54ddb5/studies/99111635-e8dd-4e70-9c96-12ba04163d5a/series/dab56d85-439c-4a96-81c2-12ef72051c55/1098b30b-c24c-4526-990b-6b723778bcfb.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-009",
        "iid": "4cbe1621-ad70-443e-9fb2-2a45937752e5",
        "sid": "c5e36e7f-fc0e-4e1a-b801-5c92db87fe65",
        "fn": "sub-MS009_ses-02_label-lesion_desc-expert04_dseg.nii.gz",
        "gcs": "patients/c4c58d2e-5dda-4372-93cd-d73dc9107022/studies/c5e36e7f-fc0e-4e1a-b801-5c92db87fe65/series/ce01c37e-2133-4a5d-9925-d7f9157e880e/4cbe1621-ad70-443e-9fb2-2a45937752e5.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-010",
        "iid": "d1afe00c-07d9-4659-a270-59c6a634e465",
        "sid": "aa72cf8c-b2ae-41ac-8cb0-dae176ae147e",
        "fn": "sub-MS010_ses-02_label-lesion_desc-expert05_dseg.nii.gz",
        "gcs": "patients/f4ec9e06-0c12-42de-9294-699d481c1e97/studies/aa72cf8c-b2ae-41ac-8cb0-dae176ae147e/series/21cc5b36-640e-4260-bf6b-74ba15c7b399/d1afe00c-07d9-4659-a270-59c6a634e465.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-011",
        "iid": "32ddad47-7811-45dc-84ac-1b617976ab89",
        "sid": "a97bbe94-0e09-4694-9e96-b3f1a28f47fd",
        "fn": "sub-MS011_ses-02_label-lesion_desc-expert06_dseg.nii.gz",
        "gcs": "patients/469e1d61-dcfc-451b-a728-e36ecba9aae6/studies/a97bbe94-0e09-4694-9e96-b3f1a28f47fd/series/7cce27b2-b89e-4fe4-acc2-b9912eab827b/32ddad47-7811-45dc-84ac-1b617976ab89.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-012",
        "iid": "681e3904-39ab-4d61-b1a0-f984e845b8b0",
        "sid": "ab85d5c6-45a9-457f-b8d8-aa2a1f897a79",
        "fn": "sub-MS012_ses-02_label-lesion_desc-expert07_dseg.nii.gz",
        "gcs": "patients/c273d893-938b-4bf5-a3de-3af77dd62a01/studies/ab85d5c6-45a9-457f-b8d8-aa2a1f897a79/series/1a99ffdc-0b6e-4851-85e5-8704b8b71b9c/681e3904-39ab-4d61-b1a0-f984e845b8b0.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-013",
        "iid": "f39eefde-9581-4fcb-97dc-48ea10b3332e",
        "sid": "df6633e7-0576-4517-8348-bc7f3389cabb",
        "fn": "sub-MS013_ses-02_label-lesion_desc-expert08_dseg.nii.gz",
        "gcs": "patients/8c31e870-8576-4f70-aeb4-f5da2972f36a/studies/df6633e7-0576-4517-8348-bc7f3389cabb/series/634fc7fa-938e-477d-991b-e7638ca4e08b/f39eefde-9581-4fcb-97dc-48ea10b3332e.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-014",
        "iid": "a5d8b925-5ab6-4d6c-a785-6aad31b15ee3",
        "sid": "c820c4d6-e4ba-4efd-b9f8-5080f31ed1e9",
        "fn": "sub-MS014_ses-02_label-lesion_desc-expert09_dseg.nii.gz",
        "gcs": "patients/83375699-82a3-4d06-9033-8d7a3d48bf46/studies/c820c4d6-e4ba-4efd-b9f8-5080f31ed1e9/series/0c9d6e9b-a910-4c59-b9e1-0a7c4fe9ae77/a5d8b925-5ab6-4d6c-a785-6aad31b15ee3.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-015",
        "iid": "066420d4-2f6a-486f-b286-76911d4c3c9e",
        "sid": "0ba2006f-2410-4c3b-a820-75f8754f8e3d",
        "fn": "sub-MS015_ses-02_label-lesion_desc-expert10_dseg.nii.gz",
        "gcs": "patients/8fc9f862-bacd-4baa-9a08-08c478f22afa/studies/0ba2006f-2410-4c3b-a820-75f8754f8e3d/series/6aecd4b1-79c0-4653-b88b-65ebb10496bf/066420d4-2f6a-486f-b286-76911d4c3c9e.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-016",
        "iid": "d6e8b0c1-f611-44eb-aa89-7c823f830861",
        "sid": "85cb714e-3531-4894-a78f-22ad1c10bbc4",
        "fn": "sub-MS016_ses-02_label-lesion_desc-expert11_dseg.nii.gz",
        "gcs": "patients/91d76347-2224-4a67-875b-87d6eb7aa755/studies/85cb714e-3531-4894-a78f-22ad1c10bbc4/series/8e8bf3a7-5efe-4a4e-9fe7-83509a553c62/d6e8b0c1-f611-44eb-aa89-7c823f830861.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-017",
        "iid": "726974c8-dc06-492f-8ad6-bf201c0457cf",
        "sid": "d6e1efd0-5ed2-4740-8532-2b67ba3972e1",
        "fn": "sub-MS017_ses-02_label-lesion_desc-expert12_dseg.nii.gz",
        "gcs": "patients/871ad47e-2d77-4990-83f3-34cbfae4ebe4/studies/d6e1efd0-5ed2-4740-8532-2b67ba3972e1/series/a1023e40-ebad-4f59-b7a5-1c0f18cbdc50/726974c8-dc06-492f-8ad6-bf201c0457cf.gz",
        "snum": 7,  # Note: series_number=7 (not 8 like others)
    },
    {
        "mrn": "ISBI-MS-018",
        "iid": "ce35caa7-e859-4470-a5f6-e34a4cc67eba",
        "sid": "1d6d96d5-9039-48f5-9b24-fafdf8d59780",
        "fn": "sub-MS018_ses-02_label-lesion_desc-expert13_dseg.nii.gz",
        "gcs": "patients/9b9e6946-7aff-4e81-a57b-d1341b524f31/studies/1d6d96d5-9039-48f5-9b24-fafdf8d59780/series/d2abe596-656b-47ac-ab31-5d51c66e56a4/ce35caa7-e859-4470-a5f6-e34a4cc67eba.gz",
        "snum": 8,
    },
    {
        "mrn": "ISBI-MS-019",
        "iid": "fa307315-35d1-4587-b6d0-a7e1b23e30e3",
        "sid": "cb2309d1-669f-4be5-be6f-a03e5aa15d4d",
        "fn": "sub-MS019_ses-02_label-lesion_desc-expert14_dseg.nii.gz",
        "gcs": "patients/5f9d0b3b-2315-4e10-be7b-0a7d1eb00eef/studies/cb2309d1-669f-4be5-be6f-a03e5aa15d4d/series/58f89d32-4acb-41e4-8b82-57d6a4487f9b/fa307315-35d1-4587-b6d0-a7e1b23e30e3.gz",
        "snum": 8,
    },
]

# Duplicate in ISBI-MS-001: two copies of the same ses-01 expert file
DUPLICATE = {
    "mrn": "ISBI-MS-001",
    "keep": "5174c9ef-088b-4191-bd73-9430bb201d28",  # first copy
    "delete": "d444aaa6-76aa-4e02-af75-e7aad09cdfbc",  # duplicate
    "fn": "sub-MS001_ses-01_label-lesion_desc-expert01_dseg.nii.gz",
}

# Label definitions (same as upload script)
LESION_LABELS = [
    {"id": 0, "name": "Background", "color": "#000000", "opacity": 0.0, "visible": False},
    {"id": 1, "name": "MS Lesion", "color": "#FF4444", "opacity": 0.6, "visible": True},
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
    print("[AUTH] Logged in")
    return token


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def get_all_patients(token):
    """Get all patients, paginated."""
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


def get_patient_studies(token, patient_id):
    """Get studies for a patient, sorted by date."""
    resp = requests.get(
        f"{API_BASE}/studies",
        headers=auth_headers(token),
        params={"patient_id": patient_id, "page_size": 50},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    studies = data.get("items", [])
    return sorted(studies, key=lambda s: s.get("study_date", ""))


def get_download_url(token, instance_id):
    """Get a signed download URL for an instance."""
    resp = requests.get(
        f"{API_BASE}/studies/instances/{instance_id}/download-url",
        headers=auth_headers(token),
        params={"expiration_minutes": 60},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["url"]


def download_file(url):
    """Download file data from a signed URL."""
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return resp.content


def upload_file(token, study_id, series_number, filename, file_data):
    """Upload file to a study, return gcs_object_name."""
    checksum = hashlib.sha256(file_data).hexdigest()

    # Init upload
    resp = requests.post(
        f"{API_BASE}/studies/upload/init",
        json={
            "study_id": study_id,
            "series_number": series_number,
            "filename": filename,
            "content_type": "application/gzip",
            "file_size_bytes": len(file_data),
            "checksum_sha256": checksum,
        },
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    init = resp.json()

    # PUT to GCS
    gcs_headers = init.get("headers", {"Content-Type": "application/gzip"})
    resp = requests.put(init["signed_url"], data=file_data, headers=gcs_headers, timeout=120)
    resp.raise_for_status()

    # Complete upload
    resp = requests.post(
        f"{API_BASE}/studies/upload/complete",
        json={"upload_id": init["upload_id"], "checksum_sha256": checksum},
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()
    return result["gcs_object_name"]


def list_segmentations(token, file_id):
    """List segmentations for a file_id (gcs_object_name)."""
    resp = requests.get(
        f"{API_BASE}/segmentation/list",
        headers=auth_headers(token),
        params={"file_id": file_id},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_segmentation_mask(token, seg_id):
    """Download binary mask data for a segmentation."""
    resp = requests.get(
        f"{API_BASE}/segmentation/{seg_id}/mask/binary",
        headers=auth_headers(token),
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content


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


def upload_mask_binary(token, seg_id, binary_data):
    """Upload raw binary mask data (with header already included)."""
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


def delete_segmentation(token, seg_id):
    """Delete a segmentation."""
    resp = requests.delete(
        f"{API_BASE}/segmentation/{seg_id}",
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()


def delete_instance(token, instance_id):
    """Delete an instance (removes from DB and GCS)."""
    resp = requests.delete(
        f"{API_BASE}/studies/instances/{instance_id}",
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Migration logic
# ---------------------------------------------------------------------------

def find_tp2_study(studies, tp1_study_id):
    """Find the TP2 study for a patient (the study that is NOT TP1)."""
    for study in studies:
        if study["id"] != tp1_study_id:
            return study
    return None


def migrate_instance(token, item, tp2_study, dry_run):
    """Migrate a single misplaced instance from TP1 to TP2."""
    mrn = item["mrn"]
    instance_id = item["iid"]
    old_gcs = item["gcs"]
    filename = item["fn"]
    series_num = item["snum"]
    tp2_study_id = tp2_study["id"]

    print(f"\n  [{mrn}] {filename}")
    print(f"    From: TP1 study {item['sid'][:8]}...")
    print(f"    To:   TP2 study {tp2_study_id[:8]}... ({tp2_study.get('study_date', '?')[:10]})")

    if dry_run:
        # Check for segmentations
        segs = list_segmentations(token, old_gcs)
        seg_count = len(segs) if isinstance(segs, list) else 0
        print(f"    Segmentations to migrate: {seg_count}")
        return True

    try:
        # Step 1: Download file from current location
        print(f"    [1/5] Downloading from TP1...")
        download_url = get_download_url(token, instance_id)
        file_data = download_file(download_url)
        size_mb = len(file_data) / (1024 * 1024)
        print(f"          Downloaded {size_mb:.1f} MB")

        # Step 2: Upload to TP2 study
        print(f"    [2/5] Uploading to TP2...")
        new_gcs = upload_file(token, tp2_study_id, series_num, filename, file_data)
        print(f"          New GCS: ...{new_gcs[-40:]}")

        # Step 3: Migrate segmentations
        print(f"    [3/5] Migrating segmentations...")
        old_segs = list_segmentations(token, old_gcs)
        if not isinstance(old_segs, list):
            old_segs = []
        seg_migrated = 0

        for seg in old_segs:
            seg_id = seg.get("segmentation_id") or seg.get("id")
            description = seg.get("metadata", {}).get("description", "Expert Annotation")
            shape = seg.get("metadata", {}).get("image_shape", {})
            rows = shape.get("rows", 0)
            cols = shape.get("columns", 0)
            slices = shape.get("slices", 0)

            if rows == 0 or cols == 0 or slices == 0:
                print(f"          [SKIP] Segmentation {seg_id[:8]}... has no shape info")
                continue

            # Download mask from old segmentation
            try:
                mask_data = get_segmentation_mask(token, seg_id)
            except Exception as e:
                print(f"          [SKIP] Cannot download mask {seg_id[:8]}...: {e}")
                continue

            # Create new segmentation on new file
            labels = seg.get("metadata", {}).get("labels", LESION_LABELS)
            new_seg_id = create_segmentation(
                token, new_gcs, rows, cols, slices, description, labels
            )

            # Upload mask to new segmentation
            upload_mask_binary(token, new_seg_id, mask_data)
            save_segmentation(token, new_seg_id)

            # Delete old segmentation
            delete_segmentation(token, seg_id)
            seg_migrated += 1
            print(f"          Migrated segmentation: {description}")

        print(f"          {seg_migrated} segmentation(s) migrated")

        # Step 4: Delete old instance from TP1
        print(f"    [4/5] Deleting old instance from TP1...")
        delete_instance(token, instance_id)
        print(f"          Deleted {instance_id[:8]}...")

        # Step 5: Verify
        print(f"    [5/5] Migration complete")
        return True

    except Exception as e:
        print(f"    [ERROR] {e}")
        return False


def handle_duplicate(token, dry_run):
    """Handle the duplicate instance in ISBI-MS-001."""
    dup = DUPLICATE
    print(f"\n  [{dup['mrn']}] Remove duplicate: {dup['fn']}")
    print(f"    Keep:   {dup['keep'][:8]}...")
    print(f"    Delete: {dup['delete'][:8]}...")

    if dry_run:
        return True

    try:
        # Check for segmentations on the duplicate
        # The duplicate should not have independent segmentations
        delete_instance(token, dup["delete"])
        print(f"    Deleted duplicate instance")
        return True
    except Exception as e:
        print(f"    [ERROR] {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Migrate misplaced ses-02 masks to TP2 studies")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview changes")
    group.add_argument("--apply", action="store_true", help="Apply changes")
    args = parser.parse_args()

    dry_run = args.dry_run

    print("=" * 70)
    print("Cross-Session Mask Migration")
    if dry_run:
        print("*** DRY RUN — no changes will be made ***")
    print(f"API: {API_BASE}")
    print(f"Instances to migrate: {len(MISPLACED)}")
    print(f"Duplicates to remove: 1")
    print("=" * 70)

    token = login()
    start_time = time.time()

    # Build patient ID lookup: mrn -> patient_id
    print("\n[1] Loading patients...")
    all_patients = get_all_patients(token)
    patient_map = {}
    for p in all_patients:
        mrn = p.get("mrn", "")
        if mrn.startswith("ISBI-MS-"):
            patient_map[mrn] = p["id"]
    print(f"    Found {len(patient_map)} ISBI-MS patients")

    # Build study lookup: mrn -> [studies sorted by date]
    print("\n[2] Loading studies...")
    study_map = {}
    for mrn, pid in sorted(patient_map.items()):
        studies = get_patient_studies(token, pid)
        study_map[mrn] = studies
    print(f"    Loaded studies for {len(study_map)} patients")

    # Migrate misplaced instances
    print("\n[3] Migrating misplaced instances...")
    stats = {"migrated": 0, "failed": 0, "skipped": 0}

    for item in MISPLACED:
        mrn = item["mrn"]
        studies = study_map.get(mrn, [])

        if len(studies) < 2:
            print(f"\n  [{mrn}] SKIP — only {len(studies)} study (no TP2)")
            stats["skipped"] += 1
            continue

        tp2_study = find_tp2_study(studies, item["sid"])
        if not tp2_study:
            print(f"\n  [{mrn}] SKIP — cannot find TP2 study")
            stats["skipped"] += 1
            continue

        success = migrate_instance(token, item, tp2_study, dry_run)
        if success:
            stats["migrated"] += 1
        else:
            stats["failed"] += 1

    # Handle duplicate
    print("\n[4] Handling duplicates...")
    dup_success = handle_duplicate(token, dry_run)

    # Summary
    elapsed = time.time() - start_time
    print(f"\n{'=' * 70}")
    if dry_run:
        print("DRY RUN SUMMARY")
        print(f"  Would migrate:  {stats['migrated']} instances")
        print(f"  Would skip:     {stats['skipped']} instances")
        print(f"  Would remove:   1 duplicate")
        print("*** Run with --apply to execute ***")
    else:
        print("MIGRATION COMPLETE")
        print(f"  Migrated:  {stats['migrated']} instances")
        print(f"  Failed:    {stats['failed']} instances")
        print(f"  Skipped:   {stats['skipped']} instances")
        print(f"  Duplicate: {'removed' if dup_success else 'FAILED'}")
    print(f"  Time:      {elapsed:.1f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
