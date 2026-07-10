"""
Fix ISBI MS Dataset: Re-upload segmentations + Upload preprocessed images.

Problem 1: 0 segmentations in Firestore — re-create from existing expert/outmask instances
Problem 2: Preprocessed images not uploaded — extract from ZIPs and upload

Usage:
    python scripts/fix_data.py [--segmentations] [--preprocessed] [--all]
"""

import hashlib
import os
import struct
import sys
import tempfile
import time
import zipfile

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

ZIP_FILES = [
    "C:/Users/Nicolas/Downloads/ISBI-20251117T213912Z-1-001.zip",
    "C:/Users/Nicolas/Downloads/ISBI-20251117T213912Z-1-002.zip",
    "C:/Users/Nicolas/Downloads/ISBI-20251117T213912Z-1-003.zip",
    "C:/Users/Nicolas/Downloads/ISBI-20251117T213912Z-1-004.zip",
]

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

# Preprocessed series number
PP_SERIES = {"flair": 11, "mprage": 12, "pd": 13, "t2": 14}


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
    """Upload binary mask in (depth, height, width) format."""
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
# NIfTI helpers
# ---------------------------------------------------------------------------

def nifti_to_binary_mask(filepath, threshold=0.5):
    """Load NIfTI, binarize, return mask in (slices, rows, columns) format."""
    img = nib.load(filepath)
    data = img.get_fdata()
    binary = (data > threshold).astype(np.uint8)
    rows, columns, slices = data.shape[0], data.shape[1], data.shape[2]
    mask = np.transpose(binary, (2, 0, 1)).copy()
    return mask, rows, columns, slices


# ---------------------------------------------------------------------------
# Part 1: Re-upload segmentations
# ---------------------------------------------------------------------------

def reupload_segmentations(token):
    """Find existing expert/outmask instances and create segmentations for them."""
    print("\n" + "=" * 60)
    print("PART 1: Re-uploading segmentations")
    print("=" * 60)

    stats = {"expert": 0, "outmask": 0, "brain": 0, "failed": 0}

    for p in PATIENTS:
        folder = p["folder"]
        mrn = f"ISBI-MS-{p['num']:03d}"
        patient_dir = os.path.join(EXTRACT_DIR, folder)

        if not os.path.isdir(patient_dir):
            continue

        patient_id = get_patient_id(token, mrn)
        if not patient_id:
            print(f"\n[WARN] Patient {mrn} not found")
            continue

        studies = get_studies(token, patient_id)
        if not studies:
            print(f"\n[WARN] No studies for {mrn}")
            continue

        # Find existing expert/outmask instances in the first study
        first_study = studies[0]
        study_id = first_study["id"]
        all_series = get_series(token, study_id)

        # Build map: original_filename -> gcs_object_name
        filename_to_gcs = {}
        for s in all_series:
            instances = get_instances(token, s["id"])
            for inst in instances:
                fname = inst.get("original_filename", "")
                gcs = inst.get("gcs_object_name", "")
                if fname and gcs:
                    filename_to_gcs[fname] = gcs

        # Collect mask files from disk
        all_files = os.listdir(patient_dir)
        expert_files = sorted([f for f in all_files if "Expert" in f and f.endswith(".nii.gz")])
        outmask_files = sorted([f for f in all_files if "out_mask" in f and f.endswith(".nii.gz")])
        brain_files = [f for f in all_files if f.startswith("patient") and f.endswith(".nii.gz")]

        mask_count = len(expert_files) + len(outmask_files) + len(brain_files)
        if mask_count == 0:
            continue

        print(f"\n{'='*50}")
        print(f"Patient {p['num']} ({mrn}): {len(expert_files)} experts, {len(outmask_files)} out_masks, {len(brain_files)} brain masks")
        print(f"  Available instances: {list(filename_to_gcs.keys())}")
        print(f"{'='*50}")

        # --- Expert Annotations ---
        for ef in expert_files:
            expert_path = os.path.join(patient_dir, ef)
            gcs_name = filename_to_gcs.get(ef)

            if not gcs_name:
                # Need to upload the image first
                print(f"      [INFO] Expert image {ef} not found as instance, uploading...")
                series_num = 7 + expert_files.index(ef)
                parts = ef.replace(".nii.gz", "").split("_")
                rater = parts[-1] if len(parts) >= 2 else "1"
                try:
                    gcs_name = upload_file(token, study_id, series_num, expert_path, ef)
                except Exception as e:
                    print(f"      [ERROR] Upload failed for {ef}: {e}")
                    stats["failed"] += 1
                    continue

            # Create segmentation
            mask, rows, cols, slices = nifti_to_binary_mask(expert_path)
            nonzero = int(np.sum(mask > 0))
            parts = ef.replace(".nii.gz", "").split("_")
            rater = parts[-1] if len(parts) >= 2 else "1"
            description = f"Expert Rater {rater} - MS Lesion Annotation"

            try:
                seg_id = create_segmentation(token, gcs_name, rows, cols, slices, description, LESION_LABELS)
                upload_mask_binary(token, seg_id, mask)
                save_segmentation(token, seg_id)
                print(f"      [SEG] {description} ({nonzero} voxels)")
                stats["expert"] += 1
            except Exception as e:
                print(f"      [ERROR] Segmentation for {ef}: {e}")
                stats["failed"] += 1

        # --- Out Masks ---
        for of_ in outmask_files:
            out_path = os.path.join(patient_dir, of_)
            gcs_name = filename_to_gcs.get(of_)

            if not gcs_name:
                print(f"      [INFO] Out mask {of_} not found as instance, uploading...")
                series_num = 9 + outmask_files.index(of_)
                try:
                    gcs_name = upload_file(token, study_id, series_num, out_path, of_)
                except Exception as e:
                    print(f"      [ERROR] Upload failed for {of_}: {e}")
                    stats["failed"] += 1
                    continue

            mask, rows, cols, slices = nifti_to_binary_mask(out_path)
            nonzero = int(np.sum(mask > 0))
            mask_label = of_.replace("out_mask", "").replace(".nii.gz", "") or "1"
            description = f"Output Mask {mask_label} - Lesion Prediction"

            try:
                seg_id = create_segmentation(token, gcs_name, rows, cols, slices, description, OUTPUT_LABELS)
                upload_mask_binary(token, seg_id, mask)
                save_segmentation(token, seg_id)
                print(f"      [SEG] {description} ({nonzero} voxels)")
                stats["outmask"] += 1
            except Exception as e:
                print(f"      [ERROR] Segmentation for {of_}: {e}")
                stats["failed"] += 1

        # --- Brain Masks (associate with FLAIR in first timepoint) ---
        for bf in brain_files:
            brain_path = os.path.join(patient_dir, bf)
            img = nib.load(brain_path)
            rows, cols, slices = img.shape[0], img.shape[1], img.shape[2]

            # Find FLAIR image in first timepoint
            flair_gcs = None
            for s in all_series:
                if s.get("series_number") == 1:  # FLAIR series
                    instances = get_instances(token, s["id"])
                    if instances:
                        flair_gcs = instances[0]["gcs_object_name"]
                        break

            if not flair_gcs:
                print(f"      [SKIP] No FLAIR found for brain mask")
                continue

            mask, rows, cols, slices = nifti_to_binary_mask(brain_path)
            nonzero = int(np.sum(mask > 0))

            try:
                seg_id = create_segmentation(
                    token, flair_gcs, rows, cols, slices,
                    "Brain Extraction Mask", BRAIN_LABELS,
                )
                upload_mask_binary(token, seg_id, mask)
                save_segmentation(token, seg_id)
                print(f"      [SEG] Brain Extraction Mask ({nonzero} voxels)")
                stats["brain"] += 1
            except Exception as e:
                print(f"      [ERROR] Brain mask {bf}: {e}")
                stats["failed"] += 1

    total = stats["expert"] + stats["outmask"] + stats["brain"]
    print(f"\n{'='*60}")
    print(f"SEGMENTATION UPLOAD COMPLETE")
    print(f"  Expert annotations: {stats['expert']}")
    print(f"  Output masks:       {stats['outmask']}")
    print(f"  Brain masks:        {stats['brain']}")
    print(f"  Total:              {total}")
    print(f"  Failed:             {stats['failed']}")
    print(f"{'='*60}")
    return total


# ---------------------------------------------------------------------------
# Part 2: Extract and upload preprocessed images
# ---------------------------------------------------------------------------

def extract_preprocessed(zip_files, output_dir):
    """Extract preprocessed .nii files from ZIP archives."""
    print("\n[EXTRACT] Extracting preprocessed files from ZIPs...")
    pp_dir = os.path.join(output_dir, "preprocessed_extracted")
    os.makedirs(pp_dir, exist_ok=True)

    count = 0
    for zf_path in zip_files:
        if not os.path.exists(zf_path):
            print(f"  [WARN] ZIP not found: {zf_path}")
            continue

        with zipfile.ZipFile(zf_path, 'r') as zf:
            for name in zf.namelist():
                if '/preprocessed/' in name and name.endswith('_pp.nii') and not name.endswith('/'):
                    # Parse patient folder from path: ISBI/testing/test08/preprocessed/test08_01_flair_pp.nii
                    parts = name.split('/')
                    # Find the patient folder (training01, test08, etc.)
                    patient_folder = None
                    for i, part in enumerate(parts):
                        if part in ('training', 'testing') and i + 1 < len(parts):
                            patient_folder = f"{part}/{parts[i+1]}"
                            break

                    if not patient_folder:
                        continue

                    # Create patient-specific output directory
                    patient_pp_dir = os.path.join(pp_dir, patient_folder)
                    os.makedirs(patient_pp_dir, exist_ok=True)

                    # Extract file
                    filename = os.path.basename(name)
                    output_path = os.path.join(patient_pp_dir, filename)

                    if not os.path.exists(output_path):
                        with zf.open(name) as src, open(output_path, 'wb') as dst:
                            dst.write(src.read())
                        count += 1

    print(f"  [EXTRACT] Extracted {count} preprocessed files to {pp_dir}")
    return pp_dir


def upload_preprocessed(token, pp_dir):
    """Upload preprocessed images to existing studies."""
    print("\n" + "=" * 60)
    print("PART 2: Uploading preprocessed images")
    print("=" * 60)

    stats = {"uploaded": 0, "skipped": 0, "failed": 0}

    for p in PATIENTS:
        folder = p["folder"]
        mrn = f"ISBI-MS-{p['num']:03d}"
        patient_pp_dir = os.path.join(pp_dir, folder)

        if not os.path.isdir(patient_pp_dir):
            continue

        patient_id = get_patient_id(token, mrn)
        if not patient_id:
            continue

        studies = get_studies(token, patient_id)
        if not studies:
            continue

        # Get all preprocessed files for this patient
        pp_files = sorted([f for f in os.listdir(patient_pp_dir) if f.endswith("_pp.nii")])
        if not pp_files:
            continue

        print(f"\nPatient {p['num']} ({mrn}): {len(pp_files)} preprocessed files, {len(studies)} studies")

        # Group by timepoint: training01_01_flair_pp.nii -> tp=01
        tp_files = {}
        for f in pp_files:
            # Parse: folder_TP_seq_pp.nii
            base = f.replace("_pp.nii", "")
            parts = base.split("_")
            if len(parts) >= 3:
                tp = parts[-2]  # timepoint number
                seq = parts[-1]  # sequence (flair, mprage, pd, t2)
                if tp not in tp_files:
                    tp_files[tp] = []
                tp_files[tp].append((f, seq))

        # Match timepoints to studies (both sorted chronologically)
        tp_keys = sorted(tp_files.keys())
        for i, tp_key in enumerate(tp_keys):
            if i >= len(studies):
                print(f"  [WARN] More timepoints ({len(tp_keys)}) than studies ({len(studies)})")
                break

            study = studies[i]
            study_id = study["id"]

            # Check if preprocessed images already exist in this study
            existing_series = get_series(token, study_id)
            existing_series_nums = {s.get("series_number") for s in existing_series}

            for filename, seq in tp_files[tp_key]:
                series_num = PP_SERIES.get(seq)
                if not series_num:
                    continue

                if series_num in existing_series_nums:
                    # Check if instances already exist
                    for s in existing_series:
                        if s.get("series_number") == series_num:
                            insts = get_instances(token, s["id"])
                            if insts:
                                stats["skipped"] += 1
                                continue

                filepath = os.path.join(patient_pp_dir, filename)
                try:
                    upload_file(token, study_id, series_num, filepath, filename)
                    stats["uploaded"] += 1
                except Exception as e:
                    print(f"      [ERROR] {filename}: {e}")
                    stats["failed"] += 1

    print(f"\n{'='*60}")
    print(f"PREPROCESSED UPLOAD COMPLETE")
    print(f"  Uploaded: {stats['uploaded']}")
    print(f"  Skipped:  {stats['skipped']}")
    print(f"  Failed:   {stats['failed']}")
    print(f"{'='*60}")
    return stats["uploaded"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:] if len(sys.argv) > 1 else ["--all"]

    do_seg = "--segmentations" in args or "--all" in args
    do_pp = "--preprocessed" in args or "--all" in args

    print("=" * 60)
    print("ISBI MS Dataset — Data Fix Script")
    print(f"  Segmentations: {'YES' if do_seg else 'NO'}")
    print(f"  Preprocessed:  {'YES' if do_pp else 'NO'}")
    print(f"API: {API_BASE}")
    print("=" * 60)

    token = login()
    start_time = time.time()

    if do_seg:
        reupload_segmentations(token)

    if do_pp:
        pp_dir = extract_preprocessed(ZIP_FILES, EXTRACT_DIR)
        upload_preprocessed(token, pp_dir)

    elapsed = time.time() - start_time
    print(f"\nTotal time: {elapsed/60:.1f} minutes")


if __name__ == "__main__":
    main()
