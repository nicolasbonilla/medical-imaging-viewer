"""
Rename all 19 ISBI-MS patients to German names.

Usage:
    python scripts/rename_patients_german.py --dry-run   # preview changes
    python scripts/rename_patients_german.py --apply      # apply changes
"""

import argparse
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "https://brain-mri-209356685171.us-central1.run.app/api/v1"
USERNAME = "admin"
import os
PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD")
assert PASSWORD, "Set ADMIN_DEFAULT_PASSWORD env var; do not hardcode the admin password"
# 19 German names (MS demographics: ~65% female, ages 25-55)
GERMAN_NAMES = [
    # (first_name, last_name, gender)
    ("Katharina", "Müller", "female"),
    ("Stefan", "Schmidt", "male"),
    ("Laura", "Schneider", "female"),
    ("Maximilian", "Fischer", "male"),
    ("Anna", "Weber", "female"),
    ("Thomas", "Wagner", "male"),
    ("Sophie", "Becker", "female"),
    ("Markus", "Hoffmann", "male"),
    ("Julia", "Schäfer", "female"),
    ("Christian", "Koch", "male"),
    ("Lena", "Bauer", "female"),
    ("Florian", "Richter", "male"),
    ("Marie", "Klein", "female"),
    ("Andreas", "Wolf", "male"),
    ("Hannah", "Schröder", "female"),
    ("Sebastian", "Neumann", "male"),
    ("Clara", "Braun", "female"),
    ("Daniel", "Zimmermann", "male"),
    ("Franziska", "Hartmann", "female"),
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


def update_patient(token, patient_id, given_name, family_name, gender):
    resp = requests.put(
        f"{API_BASE}/patients/{patient_id}",
        json={
            "given_name": given_name,
            "family_name": family_name,
            "gender": gender,
        },
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Rename ISBI-MS patients to German names")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview changes")
    group.add_argument("--apply", action="store_true", help="Apply changes")
    args = parser.parse_args()

    dry_run = args.dry_run

    print("=" * 60)
    print("Rename ISBI-MS Patients to German Names")
    if dry_run:
        print("*** DRY RUN ***")
    print(f"API: {API_BASE}")
    print("=" * 60)

    token = login()

    patients = get_all_patients(token)
    isbi_patients = [p for p in patients if (p.get("mrn", "") or "").startswith("ISBI-MS-")]
    isbi_patients.sort(key=lambda p: p.get("mrn", ""))

    print(f"\nFound {len(isbi_patients)} ISBI-MS patients\n")

    if len(isbi_patients) > len(GERMAN_NAMES):
        print(f"[WARN] More patients ({len(isbi_patients)}) than names ({len(GERMAN_NAMES)})")

    renamed = 0
    for i, patient in enumerate(isbi_patients):
        if i >= len(GERMAN_NAMES):
            print(f"  [SKIP] No more names available for {patient.get('mrn', '?')}")
            break

        mrn = patient.get("mrn", "?")
        old_name = f"{patient.get('given_name', '')} {patient.get('family_name', '')}".strip()
        new_given, new_family, gender = GERMAN_NAMES[i]
        new_name = f"{new_given} {new_family}"

        if dry_run:
            print(f"  [{mrn}] {old_name} -> {new_name} ({gender})")
        else:
            try:
                update_patient(token, patient["id"], new_given, new_family, gender)
                print(f"  [{mrn}] {old_name} -> {new_name} ({gender})")
                renamed += 1
            except Exception as e:
                print(f"  [ERR] {mrn}: {e}")

    print(f"\n{'=' * 60}")
    if dry_run:
        print(f"Would rename {min(len(isbi_patients), len(GERMAN_NAMES))} patients")
        print("*** Run with --apply to apply changes ***")
    else:
        print(f"Renamed {renamed} patients")
    print("=" * 60)


if __name__ == "__main__":
    main()
