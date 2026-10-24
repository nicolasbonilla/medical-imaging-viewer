# PRB-002 — Local Backend Test Runs Wrote Test Accounts Into the Production User Store

*Software problem report per SPR-001 (`docs/iec62304/08_Problem_Resolution_Procedure.md` §1), kept
under `docs/iec62304/records/problem_reports/` like PRB-001. A GitHub Issue citing this ID is to be
raised by the owner; the agent did not raise one.*

**Problem ID**: PRB-002 (GitHub Issue: not raised — owner action)
**Reporter**: found during CAPA-015 development (PR #65) by the AI coding agent; scope established by
the coordinating agent from the local application logs of every working copy on the development
machine (read-only; no cloud service was queried)
**Date**: 2026-10-24
**Version**: `main` @ `70cc5c7`. The behaviour exists since the user store moved to Firestore
(`backend/app/security/user_storage.py`, "Prefer Firestore; fall back to disk when unavailable")
**Severity**: **Major** (proposed): integrity of production data and separation of the test
environment from production; no clinical data, no patient data and no clinical output involved
(§5). **PENDING owner approval.**
**Status**: OPEN — DRAFT. Corrective action implemented on branch `fix/test-cloud-isolation-prb002`
(test configuration only, no application code changed); clean-up of production records pending an
owner decision (§4).

**Description**: When the backend test suite runs on a computer that has gcloud application-default
credentials (ADC), nothing in `backend/tests/conftest.py` hid those credentials. At import time the
test configuration loads the application, the application creates `SecureUserStorage`, and the
store "prefers Firestore when a client is available": `app.core.firebase.get_firebase_app()` falls
back to `credentials.ApplicationDefault()` and to the project `brain-mri-476110` when
`GOOGLE_CLOUD_PROJECT` is unset. The test run therefore used the **production** Firestore:

- it listed the `auth_users` collection (encrypted records) at import and on each user lookup;
- it wrote test accounts into `auth_users`, encrypted with the public test key from `conftest.py`:
  the default `admin` the authentication service seeds when it finds no readable admin, the accounts
  the lock-out tests create (`lock_<hex>`), `durable_user`, and updates of their failed-login
  counters.

The CI pipeline has no cloud credentials, so CI never showed the problem; it only happens on a
developer computer.

**Steps to Reproduce** (do NOT run: it writes to production):
1. On a computer with gcloud ADC for an account that can write to `brain-mri-476110`, with
   `GOOGLE_CLOUD_PROJECT` and `GOOGLE_APPLICATION_CREDENTIALS` unset, go to `backend/`.
2. Run `python -m pytest tests/integration/test_auth_endpoints.py`.
3. `backend/logs/app.log` shows `SecureUserStorage initialized` with `"backend": "firestore"` and
   `User saved securely` with `"backend": "firestore"`.

**Expected Behavior**: a test run never reaches a cloud service; every store uses its local or
in-memory backend (as in CI).

**Actual Behavior**: see Description. Evidence below.

## 1. Evidence and scope (from local logs only)

Local logs rotate (`app.log` + 2 backups of 10 MB each per working copy), so the surviving logs are a
lower bound: runs before the oldest surviving entry cannot be counted or excluded.

| Working copy (`backend/logs/`) | Real-store initialisations | Writes to `auth_users` | Period in surviving logs |
|---|---|---|---|
| main checkout | 7 | 69 | 2026-07-12 to 2026-08-18 |
| `agent-ab0f9245…` | 5 | 18 | 2026-10-22 to 2026-10-23 |
| `agent-a3b629dd…` | 1 | 6 | 2026-10-23 |
| `agent-a8847e46…` | 1 | 5 | 2026-10-21 |
| `agent-a05ff56d…` (CAPA-014) | 1 | 5 | 2026-10-24 |
| `agent-a87532be…` | — | 7 | 2026-10-17 to 2026-10-18 |
| `agent-a5e3a9f1…` (CAPA-015) | — | 2 | 2026-10-24 |
| **Total** | | **112** | |

- **Accounts written**: 62 distinct test accounts — 4 different `admin` records, 57 `lock_<hex>`
  accounts, 1 `durable_user` — between 2026-07-12 (oldest surviving entry) and 2026-10-24.
  "Real-store initialisations" is lower than the number of runs because the store is created once
  per test process and the oldest initialisation lines have rotated out. All are encrypted with the test key; the production service cannot
  decrypt them, so **they cannot be used to log in to production**.
- **Reads**: the runs listed `auth_users` and read production records in encrypted form; production
  records could not be decrypted with the test key (`Key mismatch` in the logs), so no account
  content was exposed in clear.
- **Other collections**: the other Firestore/GCS messages in the logs (segmentation save/load, tool
  runner) come from tests that install fake clients (fixture ids such as `seg-gcs`, file ids
  `patients/1111…/studies/4444…`, 3–7 ms per "save"). No evidence that a real client wrote any
  other collection; this cannot be fully excluded for runs older than the surviving logs.
- **Credentials and quota**: the ADC on the machine is the owner's personal account with quota
  project `daita-9f4f6` (an unrelated product). The calls therefore carried that quota project
  *(inference: they were counted against its API quota)*; **no Daita data was read or written** —
  the database used was `brain-mri-476110`.

## 2. Triage (SPR-001 §3.1)

- **Reproducible**: yes (by construction; the logs show it on five working copies).
- **Severity**: proposed Major (§5).
- **Assigned to**: corrective action by the AI coding agent (this branch); production clean-up:
  owner decision.

## 3. Root Cause (SPR-001 §3.2)

1. **Test environment not separated from production.** `conftest.py` set the test JWT and
   encryption keys but did not hide cloud credentials or the project, so local runs inherited the
   developer's ADC.
2. **Production as the silent default.** `get_firebase_app()` defaults the project to
   `brain-mri-476110`, and `SecureUserStorage` uses Firestore whenever a client can be built, with no
   check that the process is the production service.
3. **Not visible in CI.** CI has no credentials, so the store always fell back to disk there; the
   suite was green and the defect could only be seen in local logs.

## 4. Corrective and preventive actions

**Done on this branch (test configuration only):** `backend/tests/conftest.py` sets four
independent layers before any application import:
1. `GOOGLE_APPLICATION_CREDENTIALS` is **forced** (not `setdefault`) to a file that does not exist,
   and `GCS_CREDENTIALS_FILE` is emptied (a `.env` cannot point the storage service at a key file);
2. `CLOUDSDK_CONFIG` points at an empty folder (`backend/tests/.no-cloud/gcloud`, git-ignored), so
   the gcloud ADC file is never found;
3. `GOOGLE_CLOUD_PROJECT` is forced to `mstool-offline-tests` (not a real project) and
   `GCLOUD_PROJECT` is removed;
4. `google.auth.default` (public and internal) is replaced by a function that raises
   `DefaultCredentialsError`, so any client that slips past 1–3 fails exactly as on a computer without
   credentials; only a **local** Firestore emulator (opt-in `requires_firestore` tests) gets
   anonymous credentials.

**Verification:** `backend/tests/unit/test_prb002_no_cloud_in_tests.py` (9 tests: each layer, a
remote emulator host refused, and the end result for the user store, the Firestore client, the
segmentation service and the storage service). Negative controls
`scripts/safety/prb002_negative_controls.py`: 9 mutations, each removing or weakening one layer —
**9/9 detected** (`records/risk_verification/PRB-002_negative_controls_2026-10-24.json`). The
controls run with an outer environment that already hides credentials, so no control can reach the
cloud. The base without the guard was deliberately **not** run "failing first": on this computer it
writes to production, which is the defect. Full backend suite with the guard: see the PR.

**Pending — owner decisions:**
- **(a) Remove the test records from production `auth_users`.** They are inert (not decryptable by
  production) but they are test data in a production collection, and every login reads them
  (`_find_user_by` scans and decrypts the whole collection, logging an error per unreadable
  record). The list of the 62 document ids is kept in a local file for the owner, not in this public
  repository. Deleting production records is a production change: owner decision and owner action
  (or written authorisation for a scripted deletion of exactly those ids, with a dry run first).
- **(b) Preventive, application side (follow-up, not in this branch):** outside Cloud Run, the
  backend should not default to the production project (e.g. require an explicit
  `GOOGLE_CLOUD_PROJECT` when `K_SERVICE` is absent), so a locally started server cannot write to
  production either. It changes start-up of the production service, so it needs its own change
  record, tests and a careful deployment.
- **(c)** Agents and developers keep running tests only through the suite's `conftest.py` (which now
  guards every run); for open branches created before this fix, run tests with the same variables
  set outside (`GOOGLE_APPLICATION_CREDENTIALS` to a missing file, `CLOUDSDK_CONFIG` to an empty
  folder, `GOOGLE_CLOUD_PROJECT=mstool-offline-tests`) until they are rebased.

## 5. Safety and severity rationale

- [ ] Could contribute to a hazardous situation — no: no clinical data, measurement, segmentation or
  report was read or changed; the written records cannot authenticate in production.
- [ ] Affects a Class C software item — no (test configuration only; no application module changed).
- [ ] Requires regulatory notification (EU MDR Article 87) — no: the device is not CE-marked and not
  in clinical use, and no patient data was involved.
- Proposed **Major** rather than Minor: a verification activity changed production data, for weeks,
  without being detected by any control, and test runs read the production user collection (in
  encrypted form). Under ISO 27001 A.8.31 / A.8.33 (separation of environments, test information)
  this is a nonconformity of the development process.

## 6. Approval

| Role | Name | Decision | Date |
|---|---|---|---|
| Owner / management representative | N. G. Bonilla Vargas | PENDING owner approval | |
