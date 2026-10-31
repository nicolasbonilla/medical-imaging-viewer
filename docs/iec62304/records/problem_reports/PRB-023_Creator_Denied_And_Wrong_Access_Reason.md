# PRB-023 — A Clinician Who Creates a Patient Gets "Patient not found"; the Access Log Gives the Wrong Reason

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: see PRB-020. GitHub Issue: not raised.*

**Problem ID**: PRB-023
**Reporter**: browser capture of the release candidate, 2026-10-28 (F18; backend log `backend_console_181016`);
reproduced on `main` by the AI coding agent
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7`
**Severity**: **Major** (proposed; loss of function with no workaround but an administrator, and an audit record that
states a false reason — HAZ-010 accountability). **N. G. Bonilla Vargas — approved 2026-10-30 (PR #70).**
**Status**: OPEN — DRAFT. Fix on branch `fix/platform-security-findings-prb020`.

**Description**: A radiologist or technician creates a patient (`POST /api/v1/patients`, `patients.py:50-74`); the record
stores `created_by` (`:73`), but nobody is put on its care team, so the creator's next request (`GET /patients/{id}`,
uploads) is refused with 404 "Patient not found" (RC-026: access needs an explicit assignment). The access log then
records `denied:record_unattributed_pending_review` ("quarantined") although `created_by` was stored.

**Root Cause**:
1. No assignment is recorded at creation. The care-team model (CAPA-002) requires a positive, recorded fact and forbids
   inferring access from `created_by`; the record of that fact at creation was simply never written.
2. The wrong reason has two causes. (a) The access check reads `created_by` from the object the patient service returns
   (`patient_access_dependency.py:93`, `_created_by_of` `:193`), and that object (`PatientResponse`,
   `patient_schemas.py:210-266`) has no `created_by` field — so every record looked like a legacy record without
   provenance. (b) "Quarantined" was decided on the **caller's** assignments (`patient_access.py:138`:
   `patient_created_by is None and not assignments`, where `assignments` are the user's entitlements): a user with no
   assignment anywhere was told "quarantined" for any patient, and a user with an assignment elsewhere was told "not
   assigned" for a true quarantined record. REQ-SEC-018 defines quarantine by the **record** ("lacking provenance and
   any care-team assignment").

**Fix** (on branch):
- `patients.py` `create_patient`: a non-administrator creator is recorded on the care team (`role_in_care = attending`,
  `granted_by` = the creator) right after the record is stored. An administrator is not (administrator access is its own
  audited grant, GRANTED_ADMIN; an IT administrator does not treat the patient). If the assignment cannot be stored, the
  request answers 500 with a plain message — the record exists (its id is given), the creator must ask an administrator
  and must not create it again — instead of a success the creator cannot use.
- `patient_schemas.py`: `PatientResponse.created_by` with `exclude=True` (read by the server's own check, never
  serialised); `patient_service_firestore.py` fills it.
- `patient_access.py`: `decide_patient_access(..., patient_assignments=None)` — when given, quarantine is decided on the
  record's assignment rows; `patient_access_dependency.py` reads them only on the denial path of a record without
  provenance (one extra read); the outcome is a denial in every case — only the recorded reason changes.
- Requirement **REQ-SEC-033** (new); risk control **RC-083** (HAZ-010). REQ-SEC-017/018 unchanged.

**Verification**: `test_prb021_patient_scope_creator_counts.py` — `test_rc083_prb023_*` (7): the creator is assigned
and can open the patient and see it in the list; an administrator creator is not assigned (positive control);
a failed assignment is reported and the record kept with its provenance; `created_by` read but absent from the JSON;
reasons: attributed patient → `denied:no_care_team_assignment`; legacy patient assigned to someone else →
`no_care_team_assignment`; legacy patient with no assignment → `denied:record_unattributed_pending_review`. On
`70cc5c7` six fail (the administrator test passes). Negative controls C1–C7.

**What the fix does not do**: patients created before this change by a non-administrator still have no assignment;
their creators keep getting 404 until an administrator assigns them (`POST /patients/{id}/care-team`). Records are not
backfilled (REQ-SEC-017: provenance is never inferred) — the owner may decide to assign each creator explicitly.

**Owner decisions (PENDING)**: severity Major; the rule "the non-administrator creator is recorded on the care team at
creation" (it changes the access model of CAPA-002 by adding an automatic, attributable assignment; proposed: accept);
whether to assign the creators of existing records (a production action; production was not contacted).

## Owner backfill of creator assignments — review of PR #70 (2026-10-28) *(review of PR #70, 2026-10-28 — DRAFT, N. G. Bonilla Vargas — approved 2026-10-30 (PR #70))*

The fix assigns creators from now on; records created by clinicians before it have `created_by` and no assignment, so
their creators would see no patients after the deployment (PRB-021). `scripts/owner/prb021_backfill_creator_care_team.py`
— **run by the owner only, before the backend deployment** — records for each such record the assignment the fix now
records at creation (attending, granted by the administrator who runs it, basis `prb021_backfill_created_by`):
- dry run by default (prints patient ids and creator usernames, no patient names; writes nothing);
- `--apply` asks for the typed word `ASSIGN`, then writes a backup (every existing assignment row and the plan) and stops if
  it cannot; each assignment is re-checked just before writing; the created ids are added to the backup (undo = revoke
  exactly those ids);
- idempotent; never re-grants an assignment that exists in any state (a revocation is a decision); skips records without
  provenance (administrator triage), administrator creators, unknown and inactive accounts;
- explicit `--project` (no default), refuses the Daita project; quota project forced to the named project.
Tests (offline, in-memory stand-in only — the script was **not** run against anything):
`backend/tests/unit/test_prb021_backfill_creator_care_team.py` — `test_rc083_prb023_backfill_*` (6); all fail at `7de9334`
(the script did not exist). Negative controls V6–V11 (`records/risk_verification/PRB-020_negative_controls_2026-10-28.json`).

## Re-review of PR #70 (2026-10-28) *(re-review of PR #70, 2026-10-28 — DRAFT, N. G. Bonilla Vargas — approved 2026-10-30 (PR #70))*

- **R1 (major)**: the backfill refused only the Daita project and an empty value; any other project id (another project,
  a typo such as `brain-mri-47611`) passed, and a real run would have read — and with `--apply` written to — that
  project. It now acts **only on `brain-mri-476110`** (allow-list), checked before the account list is read or any client
  is built; the Daita deny-list stays as a second check.
- **R2**: an account without an `is_active` field counted as active (creator and granter). Now active only when the list
  says `"is_active": true`.
- **R3**: the backup was rewritten only at the end and named to the second (a run in the same second overwrote the previous
  run's backup). Now the name carries microseconds and a random part and is created exclusively; each row's id is written
  and flushed to the backup (`attempted_assignment_ids`) **before** the row is written, and `created_assignment_ids` after;
  at start-up the script prints how many rows earlier runs left; the docstring states the fallback undo — revoke every row
  whose `basis` is `prb021_backfill_created_by` and whose `granted_by` is the administrator who ran it.
Tests `test_rc083_prb023_r2_*` in `backend/tests/unit/test_prb020_review2_findings.py` (12 cases: 7 project values refused
with no read; the production project accepted — positive control; no-field accounts; id in the backup before each write;
no overwrite; earlier rows counted and the undo documented); all but the positive control fail at `570d78f` (`records/risk_verification/PRB-020_review2_tests_on_570d78f_2026-10-28.json`).
Negative controls V10 (re-anchored), W1–W7 (`records/risk_verification/PRB-020_negative_controls_2026-10-28.json`). The script was still never run against anything.
