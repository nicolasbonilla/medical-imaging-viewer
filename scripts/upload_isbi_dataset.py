"""
Upload ISBI 2015 MS Longitudinal Lesion Segmentation Challenge dataset.

Creates 19 patients with longitudinal brain MRI studies (FLAIR, MPRAGE, PD, T2)
plus lesion masks and expert annotations.

Usage:
    python scripts/upload_isbi_dataset.py

Requires: requests (pip install requests)
"""

import hashlib
import os
import sys
import tempfile
import time
import zipfile
from datetime import date, datetime, timedelta

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "https://brain-mri-209356685171.us-central1.run.app/api/v1"
USERNAME = "admin"
import os
PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD")
assert PASSWORD, "Set ADMIN_DEFAULT_PASSWORD env var; do not hardcode the admin password"
ZIP_FILES = [
    "C:/Users/Nicolas/Downloads/ISBI-20251117T213912Z-1-001.zip",
    "C:/Users/Nicolas/Downloads/ISBI-20251117T213912Z-1-002.zip",
    "C:/Users/Nicolas/Downloads/ISBI-20251117T213912Z-1-003.zip",
    "C:/Users/Nicolas/Downloads/ISBI-20251117T213912Z-1-004.zip",
]

# Series number mapping
SEQ_SERIES = {"flair": 1, "mprage": 2, "pd": 3, "t2": 4}
LESION_SERIES = 5
EXPERT_SERIES = 6

# Patient demographics (fictional, MS-epidemiology realistic)
# ~65% female, ages 25-55, Colombian names
PATIENTS = [
    # Training set: Patient 1-5
    {"num": 1, "folder": "training/training01", "given": "Maria", "family": "Rodriguez", "gender": "female", "age": 32},
    {"num": 2, "folder": "training/training02", "given": "Carlos", "family": "Martinez", "gender": "male", "age": 41},
    {"num": 3, "folder": "training/training03", "given": "Laura", "family": "Garcia", "gender": "female", "age": 28},
    {"num": 4, "folder": "training/training04", "given": "Andres", "family": "Lopez", "gender": "male", "age": 37},
    {"num": 5, "folder": "training/training05", "given": "Sofia", "family": "Hernandez", "gender": "female", "age": 45},
    # Testing set: Patient 6-19
    {"num": 6, "folder": "testing/test01", "given": "Valentina", "family": "Gonzalez", "gender": "female", "age": 30},
    {"num": 7, "folder": "testing/test02", "given": "Diego", "family": "Ramirez", "gender": "male", "age": 35},
    {"num": 8, "folder": "testing/test03", "given": "Camila", "family": "Torres", "gender": "female", "age": 29},
    {"num": 9, "folder": "testing/test04", "given": "Santiago", "family": "Flores", "gender": "male", "age": 43},
    {"num": 10, "folder": "testing/test05", "given": "Isabella", "family": "Rivera", "gender": "female", "age": 38},
    {"num": 11, "folder": "testing/test06", "given": "Gabriela", "family": "Morales", "gender": "female", "age": 33},
    {"num": 12, "folder": "testing/test07", "given": "Daniel", "family": "Jimenez", "gender": "male", "age": 47},
    {"num": 13, "folder": "testing/test08", "given": "Natalia", "family": "Castillo", "gender": "female", "age": 26},
    {"num": 14, "folder": "testing/test09", "given": "Sebastian", "family": "Vargas", "gender": "male", "age": 51},
    {"num": 15, "folder": "testing/test10", "given": "Paula", "family": "Rojas", "gender": "female", "age": 34},
    {"num": 16, "folder": "testing/test11", "given": "Andrea", "family": "Mendoza", "gender": "female", "age": 40},
    {"num": 17, "folder": "testing/test12", "given": "Felipe", "family": "Guerrero", "gender": "male", "age": 36},
    {"num": 18, "folder": "testing/test13", "given": "Daniela", "family": "Ortiz", "gender": "female", "age": 31},
    {"num": 19, "folder": "testing/test14", "given": "Alejandro", "family": "Perez", "gender": "male", "age": 44},
]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def login():
    """Authenticate and return access token."""
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


def create_patient(token, patient_info):
    """Create a patient and return its ID."""
    birth_date = date.today() - timedelta(days=patient_info["age"] * 365)
    phone = f"+5730{patient_info['num']:07d}"

    data = {
        "mrn": f"ISBI-MS-{patient_info['num']:03d}",
        "given_name": patient_info["given"],
        "family_name": patient_info["family"],
        "birth_date": birth_date.isoformat(),
        "gender": patient_info["gender"],
        "phone_mobile": phone,
        "country": "COL",
        "city": "Bogota",
    }

    resp = requests.post(
        f"{API_BASE}/patients",
        json=data,
        headers=auth_headers(token),
        timeout=30,
    )

    if resp.status_code == 409:
        # Patient already exists — find by MRN
        print(f"  [SKIP] Patient {data['mrn']} already exists")
        list_resp = requests.get(
            f"{API_BASE}/patients",
            headers=auth_headers(token),
            params={"search": data["mrn"]},
            timeout=30,
        )
        list_resp.raise_for_status()
        patients = list_resp.json()
        if isinstance(patients, dict) and "items" in patients:
            patients = patients["items"]
        for p in patients:
            if p.get("mrn") == data["mrn"]:
                return p["id"]
        raise RuntimeError(f"Patient {data['mrn']} exists but not found in list")

    resp.raise_for_status()
    patient_id = resp.json()["id"]
    name = f"{patient_info['given']} {patient_info['family']}"
    print(f"  [OK] Created patient {data['mrn']}: {name} ({patient_id[:8]}...)")
    return patient_id


def create_study(token, patient_id, tp_number, patient_num):
    """Create a study for a timepoint and return its ID."""
    # Stagger study dates ~6 months apart, starting from 2020
    base_date = datetime(2020, 1, 15, 9, 0, 0)
    study_date = base_date + timedelta(days=tp_number * 180)

    data = {
        "patient_id": patient_id,
        "modality": "MR",
        "study_date": study_date.isoformat(),
        "study_description": f"Brain MRI MS Protocol - Timepoint {tp_number + 1}",
        "body_site": "BRAIN",
        "reason_for_study": "Multiple Sclerosis evaluation and monitoring",
        "institution_name": "ISBI MS Lesion Challenge",
    }

    resp = requests.post(
        f"{API_BASE}/studies",
        json=data,
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    study_id = resp.json()["id"]
    print(f"    [OK] Study TP{tp_number + 1} ({study_id[:8]}...)")
    return study_id


def sha256_file(filepath):
    """Calculate SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def upload_file(token, study_id, series_number, filepath, filename):
    """Upload a single NIfTI file via the signed URL flow."""
    file_size = os.path.getsize(filepath)
    checksum = sha256_file(filepath)

    # Step 1: Init upload
    init_data = {
        "study_id": study_id,
        "series_number": series_number,
        "filename": filename,
        "content_type": "application/gzip",
        "file_size_bytes": file_size,
        "checksum_sha256": checksum,
    }

    resp = requests.post(
        f"{API_BASE}/studies/upload/init",
        json=init_data,
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    init_resp = resp.json()
    signed_url = init_resp["signed_url"]
    upload_id = init_resp["upload_id"]

    # Step 2: PUT file to GCS
    with open(filepath, "rb") as f:
        file_data = f.read()

    gcs_headers = init_resp.get("headers", {"Content-Type": "application/gzip"})
    resp = requests.put(signed_url, data=file_data, headers=gcs_headers, timeout=120)
    resp.raise_for_status()

    # Step 3: Complete upload
    complete_data = {
        "upload_id": upload_id,
        "checksum_sha256": checksum,
    }
    resp = requests.post(
        f"{API_BASE}/studies/upload/complete",
        json=complete_data,
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    size_mb = file_size / (1024 * 1024)
    print(f"      [UP] {filename} ({size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# Dataset extraction
# ---------------------------------------------------------------------------

def extract_dataset(tmp_dir):
    """
    Extract all NIfTI files from ZIPs organized by patient folder.

    Returns:
        dict: {folder: {tp_num: {seq: filepath, ...}, "lesions": [paths], "experts": [paths]}}
    """
    dataset = {}

    for zip_path in ZIP_FILES:
        if not os.path.exists(zip_path):
            print(f"[WARN] ZIP not found: {zip_path}")
            continue

        print(f"[EXTRACT] {os.path.basename(zip_path)}...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                if not member.endswith(".nii.gz"):
                    continue
                if ".ipynb_checkpoints" in member:
                    continue

                parts = member.split("/")
                if len(parts) < 3:
                    continue

                folder = f"{parts[1]}/{parts[2]}"  # e.g., training/training01
                fname = parts[-1]

                if folder not in dataset:
                    dataset[folder] = {"timepoints": {}, "lesions": [], "experts": []}

                # Extract to temp dir
                out_dir = os.path.join(tmp_dir, folder)
                os.makedirs(out_dir, exist_ok=True)
                out_path = os.path.join(out_dir, fname)

                # Extract if not already on disk
                if not os.path.exists(out_path):
                    with zf.open(member) as src, open(out_path, "wb") as dst:
                        dst.write(src.read())

                # Classify file (always, even if already extracted)
                if "Lesion" in fname:
                    dataset[folder]["lesions"].append(out_path)
                elif "Expert" in fname:
                    dataset[folder]["experts"].append(out_path)
                elif "out_mask" in fname or "surrounding_mask" in fname:
                    pass  # Skip derived masks
                else:
                    # MRI sequence: training01_01_flair.nii.gz
                    base = fname.replace(".nii.gz", "")
                    parts_f = base.split("_")
                    if len(parts_f) >= 3:
                        tp = int(parts_f[1])  # 01 -> 1
                        seq = parts_f[2]  # flair, mprage, pd, t2
                        if tp not in dataset[folder]["timepoints"]:
                            dataset[folder]["timepoints"][tp] = {}
                        dataset[folder]["timepoints"][tp][seq] = out_path

    return dataset


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("ISBI MS Dataset Upload")
    print(f"API: {API_BASE}")
    print(f"Patients: {len(PATIENTS)}")
    print("=" * 60)

    # Login
    token = login()

    # Extract dataset to temp directory
    tmp_dir = os.path.join(tempfile.gettempdir(), "isbi_ms_extract")
    os.makedirs(tmp_dir, exist_ok=True)
    print(f"\n[EXTRACT] Extracting to {tmp_dir}")
    dataset = extract_dataset(tmp_dir)
    print(f"[EXTRACT] Found {len(dataset)} patient folders\n")

    # Stats
    total_files = 0
    uploaded_files = 0
    failed_files = 0
    start_time = time.time()

    for p in PATIENTS:
        folder = p["folder"]
        if folder not in dataset:
            print(f"\n[WARN] No data for Patient {p['num']} ({folder})")
            continue

        data = dataset[folder]
        tp_count = len(data["timepoints"])
        seq_count = sum(len(seqs) for seqs in data["timepoints"].values())
        lesion_count = len(data["lesions"])
        expert_count = len(data["experts"])
        total_files += seq_count + lesion_count + expert_count

        print(f"\n{'='*50}")
        print(f"Patient {p['num']}: {p['given']} {p['family']}")
        print(f"  {tp_count} timepoints, {seq_count} MRIs, {lesion_count} lesions, {expert_count} experts")
        print(f"{'='*50}")

        # Create patient
        try:
            patient_id = create_patient(token, p)
        except Exception as e:
            print(f"  [ERROR] Failed to create patient: {e}")
            continue

        # Create studies and upload per timepoint
        for tp_num in sorted(data["timepoints"].keys()):
            seqs = data["timepoints"][tp_num]

            try:
                study_id = create_study(token, patient_id, tp_num - 1, p["num"])
            except Exception as e:
                print(f"    [ERROR] Failed to create study TP{tp_num}: {e}")
                continue

            # Upload MRI sequences
            for seq_name in ["flair", "mprage", "pd", "t2"]:
                if seq_name not in seqs:
                    continue
                filepath = seqs[seq_name]
                fname = os.path.basename(filepath)
                try:
                    upload_file(token, study_id, SEQ_SERIES[seq_name], filepath, fname)
                    uploaded_files += 1
                except Exception as e:
                    print(f"      [ERROR] {fname}: {e}")
                    failed_files += 1

        # Upload lesion masks (all into first study's series 5)
        if data["lesions"] and data["timepoints"]:
            first_tp = min(data["timepoints"].keys())
            try:
                # We need the study_id of the first timepoint
                # Re-create would fail, so we create a dedicated study for masks
                lesion_study_id = create_study(token, patient_id, 99, p["num"])
                for lpath in sorted(data["lesions"]):
                    fname = os.path.basename(lpath)
                    try:
                        upload_file(token, lesion_study_id, LESION_SERIES, lpath, fname)
                        uploaded_files += 1
                    except Exception as e:
                        print(f"      [ERROR] {fname}: {e}")
                        failed_files += 1
            except Exception as e:
                print(f"    [ERROR] Failed to create lesion study: {e}")

        # Upload expert annotations
        if data["experts"]:
            try:
                expert_study_id = create_study(token, patient_id, 98, p["num"])
                for epath in sorted(data["experts"]):
                    fname = os.path.basename(epath)
                    try:
                        upload_file(token, expert_study_id, EXPERT_SERIES, epath, fname)
                        uploaded_files += 1
                    except Exception as e:
                        print(f"      [ERROR] {fname}: {e}")
                        failed_files += 1
            except Exception as e:
                print(f"    [ERROR] Failed to create expert study: {e}")

    # Summary
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print("UPLOAD COMPLETE")
    print(f"  Uploaded: {uploaded_files}/{total_files} files")
    print(f"  Failed:   {failed_files}")
    print(f"  Time:     {elapsed/60:.1f} minutes")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
