# PRB-021 — Every Signed-In User Could List the Whole Patient Registry

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: see PRB-020 (PRB-004..009 used by the concurrent
display work, PRB-010..019 left free for it). GitHub Issue: not raised — owner action.*

**Problem ID**: PRB-021
**Reporter**: found by the AI coding agent while reproducing PRB-020 (F21) on `main`; the capture notes (F21) said
"patient data still needs a care-team assignment", which is true for the record routes but **not for the list**
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7` (also on the release branch). The list and search routes have been unscoped since they
were written; CAPA-002/CAPA-009 scoped every route that names an object, and these two name none
**Severity**: **Critical** (proposed; disclosure of patient identifiers to any account — HAZ-010, REQ-SEC-014 not met).
**PENDING owner approval.**
**Status**: OPEN — DRAFT. Fix on branch `fix/platform-security-findings-prb020`; not merged, not deployed.

**Description**: `GET /api/v1/patients` (`patients.py:77-108`) and `GET /api/v1/patients/search` (`:112-163`) need only
`PATIENT_VIEW`, which every role holds (VIEWER included, `rbac.py:42-47`), and call the service with no user and no
care-team check (`patient_service_firestore.py` `list_patients`, `search_patients`). Each item carries the patient's
full name, record number (MRN), birth date, sex and study/document counts (`patient_schemas.py:270-283`). REQ-SEC-014
requires object-level authorization on **every** data-returning endpoint; the record routes (`/patients/{id}`) enforce
it (RC-026, RC-036) but the list does not, so the list reveals what the record routes hide. With open
self-registration (PRB-020) this was anyone on the internet.

**Steps to Reproduce**: sign in as any user without a care-team assignment (a VIEWER, technician or radiologist) and
call `GET /api/v1/patients` or `/patients/search?gender=male`: every patient is returned.
(Tests `test_rc082_prb021_*`, §5; on `70cc5c7` every scoped test fails — the list returns all four test patients.)

**Expected Behavior**: an administrator lists every record (as on every object route: GRANTED_ADMIN); every other user
lists only the patients of their **active** care-team assignments; a revoked assignment no longer lists the patient;
filters, ordering and pages behave as before within that set; if the care-team store cannot be read, the list is
refused (503), never returned unfiltered or silently empty.

**Root Cause**: the CAPA-009 enumeration of routes (`test_capa009_object_authorization_everywhere.py`) classified
every route that *references* an object (path parameter, query or body id); a list with no id was out of its scope,
and `authorize_list_scope` (RC-028) was applied to the study and document lists but never to the patient list. No
test sent a list request as a user without assignments.

**Fix** (on branch): `patients.py` — `get_care_team_service` moved before the routes; `_listing_scope()` returns `None`
for an administrator, else the ids of the caller's active assignments (503 if the store cannot be read);
`list_patients` and `search_patients` pass it as `allowed_ids`. `patient_service_firestore.py` — with `allowed_ids`,
the documents of those ids are read one by one (never a query over the registry), filtered in memory with the same
rules (status; exact MRN, family-name prefix, gender), ordered and paged as the unscoped query; counts per page.
Requirement **REQ-SEC-032** (new; makes REQ-SEC-014 explicit for lists); risk control **RC-082** (HAZ-010).

**Verification**: `backend/tests/unit/test_prb021_patient_scope_creator_counts.py` — `test_rc082_prb021_*` (6 tests,
one over three roles): no assignment → empty list for viewer, technician, radiologist; one assignment → that patient
only; search scoped; revoked assignment → not listed; administrator → all (positive control, passes on the base);
status filter and pages within the scoped set. Negative controls P1–P7 (`prb020_negative_controls.py`).

**Limits**: a user with many assignments is read patient by patient (one read each); fine for a care team, not for
thousands of assignments (then a query on the assignment ids would be needed). The `query`, `given_name` and `city`
parameters of the search are accepted but have never been applied (no full-text search exists) — the route's
docstring claimed one and is corrected. The quarantined-records triage route (`/patients/quarantined`) stays
administrator-only.

**Owner decisions / actions (PENDING)**: severity Critical; together with PRB-020 §7 items 2–3 (production account
review; whether the registry was read by self-registered accounts — production access logs, owner/DPO only;
production was not contacted); whether CAPA-009's route enumeration is extended to list routes (proposed: yes —
a test that sends every mounted GET without an id as an unentitled user and expects no record of another patient).

## Deployment effect and review of PR #70 (2026-10-28) *(review of PR #70, 2026-10-28 — DRAFT, PENDING owner approval)*

**Deployment effect**: after this change a clinician sees only the patients of their active care-team assignments; a
clinician who created patients before PRB-023 (records with `created_by` but no assignment) or who treats patients created
by someone else will see **no patients** until an administrator assigns them — run the owner backfill
`scripts/owner/prb021_backfill_creator_care_team.py` (PRB-023) **before** deploying the backend, then assign the remaining
treating clinicians (`POST /api/v1/patients/{id}/care-team`), as listed in `DEPLOYMENT_CHECKLIST.md`.

**Empty state (review of PR #70, M3)**: a non-administrator with no listed patient read "No patients registered — Start by
registering your first patient" and the tile "Patients 0 in registry" — false, and an invitation to register again a
patient who already exists (same MRN → 409; a different spelling of the MRN → a **duplicate record** whose earlier scans are
then missing from comparisons, HAZ-009). Now: "No patients are assigned to you yet. An administrator can add you to a
patient's care team." — no create invitation in the empty state (the header's New Patient button stays) — and the tile
says "assigned to you" (en/es/de; `PatientsPage.tsx`, `PatientsOverview.tsx`). An administrator keeps the registry wording.
Tests: `frontend/src/pages/PatientsPage.prb021.test.tsx` — `rc082 prb021 *` (2); the clinician test fails at `7de9334`
(`records/risk_verification/PRB-020_review1_tests_on_7de9334_2026-10-28.json`); the administrator test is the positive control. Negative controls VF1–VF4 (`records/risk_verification/PRB-020_negative_controls_2026-10-28.json`).

**Limits added by the review (m9)**: `POST /patients` answers 409 "Patient with MRN '…' already exists" to any role that
may create patients — an MRN-existence signal the scoped list no longer gives. Kept on purpose (it prevents duplicate
records, HAZ-009) and recorded with a proposed mitigation in **PRB-027**, which also restricts the PACS patient search.
