"""OWNER-RUN ONLY — put each patient's creator on that patient's care team (PRB-021 / PRB-023, review of PR #70, M3).

WHY
---
After PRB-021 a non-administrator sees only the patients of their active care-team assignments. Until PRB-023 the
clinician who created a patient was never assigned to it, so records created by clinicians carry `created_by` but no
assignment: after the backend deployment their creators would see "No patients are assigned to you yet". This script
records, for each such record, the assignment PRB-023 now records at creation (role "attending").

WHAT IT DOES — AND DOES NOT DO
------------------------------
* Reads the `patients` and `patient_assignments` collections of the Firestore project you name, and the account list
  you exported from the application (`GET /api/v1/auth/users` as an administrator, saved as JSON).
* For each patient with a `created_by`, it plans one assignment (patient, creator, "attending") — unless:
  - the record has no provenance (legacy, "quarantined": an administrator triages it, REQ-SEC-018);
  - the creator is an administrator (administrators are not put on care teams, RC-083);
  - the creator's account is unknown or inactive;
  - ANY care-team row already exists for that creator and patient, active OR revoked (a revocation is a decision;
    it is never undone here). This also makes the script idempotent: a second run plans nothing.
* Default is a DRY RUN: it prints the plan (patient ids and creator usernames — no patient names) and writes nothing.
* `--apply` asks you to type the word ASSIGN; then it writes a backup file (every existing assignment row and the plan)
  under a name no other run can take (time to the microsecond plus a random part; the file is created exclusively) and
  stops if the backup cannot be written. Then, for each assignment: re-check it, put its id in the backup
  (`attempted_assignment_ids`, written to disk BEFORE the row is written), write the row, and add the id to
  `created_assignment_ids`. A crash at any point leaves every written row's id in the backup.
* Each new row: role_in_care "attending", granted_by = the administrator you name (`--granted-by`, must be an active
  administrator in the account list), basis "prb021_backfill_created_by".
* UNDO: revoke exactly the ids in the backup's `created_assignment_ids` (an id in `attempted_assignment_ids` only was not
  written; revoking it answers 404) with `DELETE /api/v1/patients/{patient_id}/care-team/{assignment_id}`, which stamps
  them revoked. If a backup is lost, the rows are still findable: revoke every row whose basis is
  "prb021_backfill_created_by" and whose granted_by is the administrator who ran the script. At start-up the script
  prints how many rows earlier runs left, so a resumed run is obvious.

HOW TO RUN (owner only, BEFORE deploying the backend of PR #70; see DEPLOYMENT_CHECKLIST.md)
------------------------------------------------------------------------------------------
    python scripts/owner/prb021_backfill_creator_care_team.py --project brain-mri-476110 \
        --users-json users.json --granted-by <your administrator user id>            # dry run
    ... the same with --apply                                                           # after reading the plan
It acts ONLY on the MSTool-AI production project brain-mri-476110: any other --project (another project, a typo, an
empty value, the Daita project daita-9f4f6) is refused before the account list is read or any client is built. It uses
your Google application-default credentials with the quota project forced to that project. Accounts count as active
only when the account list says `"is_active": true`. Never run it from an automated agent.
"""
import argparse
import datetime
import json
import os
import sys
import uuid

# Re-review of PR #70, R1: an allow-list — the one project this tool was written for — checked before anything is read
# or any client is built; the Daita deny-list stays as a second check.
ALLOWED_PROJECTS = frozenset({"brain-mri-476110"})
FORBIDDEN_PROJECTS = frozenset({"daita-9f4f6"})
CONFIRMATION_WORD = "ASSIGN"
PATIENTS = "patients"
ASSIGNMENTS = "patient_assignments"
ROLE_IN_CARE = "attending"
BASIS = "prb021_backfill_created_by"


def _parse(argv):
    ap = argparse.ArgumentParser(description="Owner-run: assign each patient's creator to its care team (PRB-021).")
    ap.add_argument("--project", required=True, help="Firestore project id (required; no default)")
    ap.add_argument("--users-json", required=True, help="JSON list saved from GET /api/v1/auth/users (administrator)")
    ap.add_argument("--granted-by", required=True, help="user id of the active administrator recorded as granter")
    ap.add_argument("--apply", action="store_true", help="write the assignments (asks for the word ASSIGN)")
    ap.add_argument("--backup-dir", default="prb021_backfill_backups", help="where the backup file is written")
    return ap.parse_args(argv)


def _client(project):
    """The real Firestore client — only for the owner's run; never built in tests."""
    import google.auth
    from google.cloud import firestore
    credentials, _ = google.auth.default(quota_project_id=project)   # never bill another project's quota
    return firestore.Client(project=project, credentials=credentials)


def _rows(db, collection):
    return {snap.id: (snap.to_dict() or {}) for snap in db.collection(collection).stream()}


def build_plan(patients, assignments, users):
    """Pure: (patients {id: doc}, assignments {id: row}, users {id: account}) -> (plan, skipped {reason: [...]})."""
    existing = {(r.get("patient_id"), r.get("user_id")) for r in assignments.values()}
    plan, skipped = [], {}

    def skip(reason, pid, creator=None):
        skipped.setdefault(reason, []).append({"patient_id": pid, "created_by": creator})

    for pid in sorted(patients):
        creator = patients[pid].get("created_by")
        if not creator:
            skip("no provenance (legacy record: administrator triage)", pid)
            continue
        creator = str(creator)
        account = users.get(creator)
        if account is None:
            skip("unknown account", pid, creator)
        elif account.get("is_active") is not True:          # fail closed (re-review of PR #70, R2)
            skip("inactive account", pid, creator)
        elif str(account.get("role", "")).lower() == "admin":
            skip("creator is an administrator (not put on care teams)", pid, creator)
        elif (pid, creator) in existing:
            skip("already has a care-team row for the creator (active or revoked)", pid, creator)
        else:
            plan.append({"patient_id": pid, "user_id": creator, "username": account.get("username", "")})
    return plan, skipped


def main(argv=None, *, db=None, input_fn=input, out=None, now=None):
    out = out or sys.stdout
    args = _parse(sys.argv[1:] if argv is None else argv)

    def say(*parts):
        print(*parts, file=out)

    project = args.project.strip()
    if project not in ALLOWED_PROJECTS or project in FORBIDDEN_PROJECTS:
        say(f"REFUSED: project {project!r} — this script acts only on {', '.join(sorted(ALLOWED_PROJECTS))}.")
        return 2
    try:
        with open(args.users_json, encoding="utf-8") as fh:
            users = {str(u["id"]): u for u in json.load(fh)}
    except (OSError, ValueError, KeyError, TypeError) as e:
        say(f"REFUSED: the account list could not be read ({type(e).__name__}).")
        return 2
    granter = users.get(str(args.granted_by))
    if not granter or str(granter.get("role", "")).lower() != "admin" or granter.get("is_active") is not True:
        say("REFUSED: --granted-by must be the id of an ACTIVE administrator in the account list.")
        return 2

    db = db if db is not None else _client(project)
    patients, assignments = _rows(db, PATIENTS), _rows(db, ASSIGNMENTS)
    plan, skipped = build_plan(patients, assignments, users)

    say(f"Project: {project}   mode: {'APPLY' if args.apply else 'DRY RUN'}")
    say(f"Patients read: {len(patients)}   existing care-team rows: {len(assignments)}")
    earlier = sum(1 for r in assignments.values() if r.get("basis") == BASIS)
    say(f"rows from earlier backfill runs (basis {BASIS}): {earlier}")
    for item in plan:
        say(f"  would assign: patient {item['patient_id']}  <-  creator {item['username']} ({item['user_id']})")
    for reason, items in sorted(skipped.items()):
        say(f"  skipped, {reason}: {len(items)}")
    say(f"would assign: {len(plan)}")
    if not plan:
        say("Nothing to assign.")
        return 0
    if not args.apply:
        say("DRY RUN: nothing was written. Re-run with --apply to write these assignments.")
        return 0

    answer = input_fn(f"Type {CONFIRMATION_WORD} to write {len(plan)} assignment(s) to project {project}: ")
    if (answer or "").strip() != CONFIRMATION_WORD:
        say("Not confirmed: nothing was written.")
        return 1

    stamp = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = os.path.join(args.backup_dir, f"prb021_backfill_{project}_{stamp}_{uuid.uuid4().hex[:8]}.json")
    record = {"project": project, "taken_at": stamp, "granted_by": str(args.granted_by),
              "assignments_before": assignments, "plan": plan, "skipped": skipped,
              "attempted_assignment_ids": [], "created_assignment_ids": []}

    def save_backup(mode="w"):
        with open(backup_path, mode, encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())

    try:
        os.makedirs(args.backup_dir, exist_ok=True)
        save_backup("x")          # exclusive: never overwrites another run's backup
    except OSError as e:
        say(f"STOPPED: the backup could not be written ({type(e).__name__}); nothing was written to {project}.")
        return 3
    say(f"Backup written: {backup_path}")

    created = []
    try:
        for item in plan:
            # Re-check just before writing (another administrator may have assigned or revoked meanwhile).
            rows = db.collection(ASSIGNMENTS).where("patient_id", "==", item["patient_id"]).stream()
            if any((snap.to_dict() or {}).get("user_id") == item["user_id"] for snap in rows):
                say(f"  skipped at write time (row appeared): patient {item['patient_id']}")
                continue
            ref = db.collection(ASSIGNMENTS).document()
            record["attempted_assignment_ids"].append(ref.id)
            save_backup()             # the id is on disk before the row exists (re-review of PR #70, R3)
            ref.set({
                "patient_id": item["patient_id"], "user_id": item["user_id"], "role_in_care": ROLE_IN_CARE,
                "granted_by": str(args.granted_by),
                "granted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "revoked_at": None, "revoked_by": None, "basis": BASIS,
            })
            created.append(ref.id)
            record["created_assignment_ids"] = list(created)
            save_backup()
    finally:
        record["created_assignment_ids"] = list(created)
        save_backup()
    say(f"Assignments written: {len(created)} (ids in {backup_path}; to undo, revoke exactly those ids).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
