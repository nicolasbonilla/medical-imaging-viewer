"""
Rename all instance files to BIDS (Brain Imaging Data Structure) format.

Mapping:
  test{NN}_{TT}_flair.nii.gz      -> sub-MS{NNN}_ses-{TT}_FLAIR.nii.gz
  test{NN}_{TT}_mprage.nii.gz     -> sub-MS{NNN}_ses-{TT}_acq-MPRAGE_T1w.nii.gz
  test{NN}_{TT}_pd.nii.gz         -> sub-MS{NNN}_ses-{TT}_PDw.nii.gz
  test{NN}_{TT}_t2.nii.gz         -> sub-MS{NNN}_ses-{TT}_T2w.nii.gz
  test{NN}_{TT}_flair_pp.nii      -> sub-MS{NNN}_ses-{TT}_acq-orig_desc-preproc_FLAIR.nii.gz
  test{NN}_{TT}_mprage_pp.nii     -> sub-MS{NNN}_ses-{TT}_acq-MPRAGE_desc-preproc_T1w.nii.gz
  test{NN}_{TT}_pd_pp.nii         -> sub-MS{NNN}_ses-{TT}_desc-preproc_PDw.nii.gz
  test{NN}_{TT}_t2_pp.nii         -> sub-MS{NNN}_ses-{TT}_desc-preproc_T2w.nii.gz
  Expert{NN}_{TT}.nii.gz          -> sub-MS{NNN}_ses-{TT}_label-lesion_desc-expert{N}_dseg.nii.gz
  Experto{NN}_{TT}.nii.gz         -> sub-MS{NNN}_ses-{TT}_label-lesion_desc-experto{N}_dseg.nii.gz
  out_mask.nii.gz / out_mask2...   -> sub-MS{NNN}_ses-{TT}_label-lesion_dseg.nii.gz

Uses the new PATCH /api/v1/studies/instances/{id} endpoint to update original_filename.

Usage:
    python scripts/rename_bids.py --dry-run   # preview changes
    python scripts/rename_bids.py --apply      # apply changes
"""

import argparse
import re
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "https://brain-mri-209356685171.us-central1.run.app/api/v1"
USERNAME = "admin"
PASSWORD = "Admin123!@2024"

# Sequence -> BIDS suffix mapping
SEQUENCE_MAP = {
    "flair":  "FLAIR",
    "mprage": "acq-MPRAGE_T1w",
    "pd":     "PDw",
    "t2":     "T2w",
}

# Preprocessed sequence -> BIDS suffix (desc-preproc added)
SEQUENCE_MAP_PP = {
    "flair":  "acq-orig_desc-preproc_FLAIR",
    "mprage": "acq-MPRAGE_desc-preproc_T1w",
    "pd":     "desc-preproc_PDw",
    "t2":     "desc-preproc_T2w",
}


# ---------------------------------------------------------------------------
# BIDS filename conversion
# ---------------------------------------------------------------------------

def to_bids_name(original: str, subject_num: int) -> str | None:
    """
    Convert an original filename to BIDS format.
    Returns None if the filename doesn't match any known pattern.
    """
    sub = f"sub-MS{subject_num:03d}"

    # Pattern 0: test{NN}_{TT}_{sequence}_pp_segmentation.nii.gz (segmentation from preprocessed)
    m = re.match(r"(?:test|training)(\d+)_(\d+)_(\w+)_pp_segmentation\.nii\.gz$", original)
    if m:
        tp = m.group(2)
        seq = m.group(3).lower()
        if seq in SEQUENCE_MAP:
            return f"{sub}_ses-{tp}_desc-segFromPreproc_{SEQUENCE_MAP[seq]}.nii.gz"
        return None

    # Pattern 1: test{NN}_{TT}_{sequence}_pp.nii (preprocessed)
    m = re.match(r"(?:test|training)(\d+)_(\d+)_(\w+)_pp\.nii$", original)
    if m:
        tp = m.group(2)
        seq = m.group(3).lower()
        if seq in SEQUENCE_MAP_PP:
            return f"{sub}_ses-{tp}_{SEQUENCE_MAP_PP[seq]}.nii.gz"
        return None

    # Pattern 2: test{NN}_{TT}_{sequence}.nii.gz (original)
    m = re.match(r"(?:test|training)(\d+)_(\d+)_(\w+)\.nii\.gz$", original)
    if m:
        tp = m.group(2)
        seq = m.group(3).lower()
        if seq in SEQUENCE_MAP:
            return f"{sub}_ses-{tp}_{SEQUENCE_MAP[seq]}.nii.gz"
        return None

    # Pattern 3a: Expert_{NN}_{TT}.nii.gz (underscore variant)
    m = re.match(r"Expert_(\d+)_(\d+)\.nii\.gz$", original)
    if m:
        expert_num = m.group(1)
        tp = m.group(2)
        return f"{sub}_ses-{tp}_label-lesion_desc-expert{expert_num}_dseg.nii.gz"

    # Pattern 3: Expert{NN}_{TT}.nii.gz
    m = re.match(r"Expert(\d+)_(\d+)\.nii\.gz$", original)
    if m:
        expert_num = m.group(1)
        tp = m.group(2)
        return f"{sub}_ses-{tp}_label-lesion_desc-expert{expert_num}_dseg.nii.gz"

    # Pattern 4: Experto{NN}_{TT}.nii.gz (Spanish variant)
    m = re.match(r"Experto(\d+)_(\d+)\.nii\.gz$", original)
    if m:
        expert_num = m.group(1)
        tp = m.group(2)
        return f"{sub}_ses-{tp}_label-lesion_desc-experto{expert_num}_dseg.nii.gz"

    # Pattern 5: out_mask*.nii.gz
    m = re.match(r"out_mask(\d*)\.nii\.gz$", original)
    if m:
        suffix = m.group(1)
        desc = f"_desc-mask{suffix}" if suffix else ""
        return f"{sub}_ses-01_label-lesion{desc}_dseg.nii.gz"

    # Pattern 6: Already BIDS-like (sub-MS*)
    if original.startswith("sub-MS"):
        return None  # Already renamed

    return None


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
    resp = requests.get(
        f"{API_BASE}/studies",
        headers=auth_headers(token),
        params={"patient_id": patient_id, "page_size": 50},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("items", [])


def get_study_series(token, study_id):
    resp = requests.get(
        f"{API_BASE}/studies/{study_id}/series",
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_series_instances(token, series_id):
    resp = requests.get(
        f"{API_BASE}/studies/series/{series_id}/instances",
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def rename_instance(token, instance_id, new_filename):
    resp = requests.patch(
        f"{API_BASE}/studies/instances/{instance_id}",
        headers=auth_headers(token),
        json={"original_filename": new_filename},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Rename instance files to BIDS format")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview changes")
    group.add_argument("--apply", action="store_true", help="Apply changes")
    args = parser.parse_args()

    dry_run = args.dry_run

    print("=" * 70)
    print("Rename Instance Files to BIDS Format")
    if dry_run:
        print("*** DRY RUN ***")
    print(f"API: {API_BASE}")
    print("=" * 70)

    token = login()

    # Get all ISBI-MS patients
    patients = get_all_patients(token)
    isbi_patients = [p for p in patients if (p.get("mrn", "") or "").startswith("ISBI-MS-")]
    isbi_patients.sort(key=lambda p: p.get("mrn", ""))

    print(f"\nFound {len(isbi_patients)} ISBI-MS patients\n")

    total_renamed = 0
    total_skipped = 0
    total_unmatched = 0

    for patient in isbi_patients:
        mrn = patient.get("mrn", "?")
        patient_id = patient["id"]
        name = f"{patient.get('given_name', '')} {patient.get('family_name', '')}".strip()

        # Extract subject number from MRN: ISBI-MS-001 -> 1
        m = re.match(r"ISBI-MS-(\d+)", mrn)
        if not m:
            print(f"  [SKIP] Cannot parse MRN: {mrn}")
            continue
        subject_num = int(m.group(1))

        print(f"\n[{mrn}] {name} (sub-MS{subject_num:03d})")

        studies = get_patient_studies(token, patient_id)

        for study in studies:
            study_id = study["id"]
            study_desc = study.get("study_description", "?")
            series_list = get_study_series(token, study_id)

            for series in series_list:
                series_id = series["id"]
                instances = get_series_instances(token, series_id)

                for inst in instances:
                    old_name = inst["original_filename"]
                    instance_id = inst["id"]

                    new_name = to_bids_name(old_name, subject_num)

                    if new_name is None:
                        if old_name.startswith("sub-MS"):
                            total_skipped += 1
                        else:
                            print(f"  [???] {old_name} (no BIDS mapping)")
                            total_unmatched += 1
                        continue

                    if old_name == new_name:
                        total_skipped += 1
                        continue

                    if dry_run:
                        print(f"  {old_name}")
                        print(f"    -> {new_name}")
                    else:
                        try:
                            rename_instance(token, instance_id, new_name)
                            print(f"  {old_name} -> {new_name}")
                            total_renamed += 1
                        except Exception as e:
                            print(f"  [ERR] {old_name}: {e}")

                    if dry_run:
                        total_renamed += 1

    print(f"\n{'=' * 70}")
    if dry_run:
        print(f"Would rename: {total_renamed} files")
        print(f"Already BIDS: {total_skipped} files")
        print(f"No mapping:   {total_unmatched} files")
        print("*** Run with --apply to apply changes ***")
    else:
        print(f"Renamed:      {total_renamed} files")
        print(f"Skipped:      {total_skipped} files")
        print(f"No mapping:   {total_unmatched} files")
    print("=" * 70)


if __name__ == "__main__":
    main()
