"""
Rename mask files for clearer labeling in the viewer.

Changes:
  - label-lesion_dseg.nii.gz → label-lesion_desc-output1_dseg.nii.gz
    (was showing as "Consensus" — actually an algorithm output)
  - label-lesion_desc-mask2_dseg.nii.gz → label-lesion_desc-output2_dseg.nii.gz
    (was showing as "Auto Mask" — actually a second algorithm output)
  - desc-experto12 → desc-expert12
    (typo fix in ISBI-MS-017)

Uses PATCH /api/v1/studies/instances/{id} to update original_filename.

Usage:
    python scripts/rename_mask_labels.py --dry-run
    python scripts/rename_mask_labels.py --apply
"""

import argparse
import re
import requests

API_BASE = "https://brain-mri-209356685171.us-central1.run.app/api/v1"
USERNAME = "admin"
import os
PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD")
assert PASSWORD, "Set ADMIN_DEFAULT_PASSWORD env var; do not hardcode the admin password"
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


def get_studies(token, patient_id):
    resp = requests.get(
        f"{API_BASE}/studies",
        headers=auth_headers(token),
        params={"patient_id": patient_id, "page_size": 50},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("items", [])


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


def rename_instance(token, instance_id, new_filename):
    resp = requests.patch(
        f"{API_BASE}/studies/instances/{instance_id}",
        headers=auth_headers(token),
        json={"original_filename": new_filename},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def compute_new_name(filename):
    """
    Compute a new filename if rename is needed, or return None.

    Rules:
    1. label-lesion_dseg.nii.gz → label-lesion_desc-output1_dseg.nii.gz
    2. label-lesion_desc-mask2_dseg.nii.gz → label-lesion_desc-output2_dseg.nii.gz
    3. desc-experto → desc-expert (typo fix)
    """
    new = filename

    # Rule 1: bare label-lesion_dseg → add desc-output1
    # Match: ends with label-lesion_dseg.nii.gz (no desc- before dseg)
    new = re.sub(
        r"_label-lesion_dseg\.nii\.gz$",
        "_label-lesion_desc-output1_dseg.nii.gz",
        new,
    )

    # Rule 2: desc-mask2 → desc-output2
    new = new.replace("_desc-mask2_", "_desc-output2_")

    # Rule 3: desc-experto → desc-expert (typo fix, preserving the number)
    new = re.sub(r"_desc-experto(\d+)_", r"_desc-expert\1_", new)

    return new if new != filename else None


def main():
    parser = argparse.ArgumentParser(description="Rename mask files for clearer viewer labels")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    dry_run = args.dry_run

    print("=" * 70)
    print("Rename Mask Labels for Clearer Viewer Display")
    if dry_run:
        print("*** DRY RUN ***")
    print(f"API: {API_BASE}")
    print("=" * 70)

    token = login()

    patients = get_all_patients(token)
    isbi = [p for p in patients if (p.get("mrn") or "").startswith("ISBI-MS-")]
    isbi.sort(key=lambda p: p.get("mrn", ""))

    print(f"\nFound {len(isbi)} ISBI-MS patients\n")

    stats = {"renamed": 0, "skipped": 0, "errors": 0}

    for patient in isbi:
        mrn = patient.get("mrn", "?")
        studies = get_studies(token, patient["id"])

        for study in studies:
            series_list = get_series(token, study["id"])
            for series in series_list:
                instances = get_instances(token, series["id"])
                for inst in instances:
                    old_name = inst["original_filename"]
                    instance_id = inst["id"]

                    new_name = compute_new_name(old_name)
                    if new_name is None:
                        continue

                    if dry_run:
                        print(f"  [{mrn}] {old_name}")
                        print(f"       -> {new_name}")
                        stats["renamed"] += 1
                    else:
                        try:
                            rename_instance(token, instance_id, new_name)
                            print(f"  [{mrn}] {old_name} -> {new_name}")
                            stats["renamed"] += 1
                        except Exception as e:
                            print(f"  [{mrn}] ERROR {old_name}: {e}")
                            stats["errors"] += 1

    print(f"\n{'=' * 70}")
    if dry_run:
        print(f"Would rename: {stats['renamed']} files")
        print("*** Run with --apply to execute ***")
    else:
        print(f"Renamed: {stats['renamed']} files")
        print(f"Errors:  {stats['errors']} files")
    print("=" * 70)


if __name__ == "__main__":
    main()
