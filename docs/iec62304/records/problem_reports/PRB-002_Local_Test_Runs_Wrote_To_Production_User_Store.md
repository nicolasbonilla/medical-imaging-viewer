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
**Severity**: **Critical** (proposed, conservative mapping of SPR-001 §2 "data corruption": the
production authentication collection was contaminated with test records by an uncontrolled process).
Mitigating facts: no existing record was changed or deleted, no function was lost, no clinical or
patient data was involved (§5). **PENDING owner approval** — the owner may classify it Major if he
reads "data corruption" as alteration of existing data only.
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

Local logs rotate at 10 MB (the main checkout keeps 6 backups, back to 2025-11-23; agent working
copies keep 2), so the surviving logs are a lower bound: runs before the oldest surviving entry
cannot be counted or excluded. No write was found before 2026-07-12. One later `"backend":
"firestore"` line in the `prb002` working copy (2026-10-24 12:53:52) was the independent reviewer's
own probe of a client pointed at `localhost:8081`, with no cloud contact; it is not part of the scope.

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
  accounts, 1 `durable_user` — between 2026-07-12 (oldest write found) and 2026-10-24.
  Each record has a new random id (`backend/app/security/auth.py:190`), so no existing production
  record was overwritten.
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
- **Severity**: proposed Critical (§5).
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

**Done on this branch (test configuration only):** `backend/tests/conftest.py` sets five
independent layers before any application import (tests check that no app module was imported
before the guard, before the environment layers took effect, or before the credential and socket
guards were installed):
1. `GOOGLE_APPLICATION_CREDENTIALS` is **forced** (not `setdefault`) to a file that does not exist,
   and `GCS_CREDENTIALS_FILE` is emptied (a `.env` cannot point the storage service at a key file);
   this also stops `google.oauth2.id_token.fetch_id_token`, which does not use `google.auth.default`;
2. `CLOUDSDK_CONFIG` points at an empty folder (`backend/tests/.no-cloud/gcloud`, git-ignored), so
   the gcloud ADC file is never found;
3. `GOOGLE_CLOUD_PROJECT` is forced to `mstool-offline-tests` (not a real project), and keys and
   endpoints of other external services inherited from the environment are removed
   (`GCLOUD_PROJECT`, `ANTHROPIC_API_KEY`, `API_SERVICE_TOKEN`, `API_BASE_URL`, the FLAMeS / LST-AI /
   SynthSeg / MindGlide / Vertex endpoints, Redis and PACS settings). On this computer
   `ANTHROPIC_API_KEY` is set in the user environment; every test that touches the provider mocks its
   client, so no evidence of real provider calls from tests was found;
4. `google.auth.default` (public and internal) **always** raises `DefaultCredentialsError`, also when
   `FIRESTORE_EMULATOR_HOST` is set (CI sets it without running an emulator), so every Google client
   fails exactly as on a computer without credentials;
5. Python sockets, and on Windows asyncio's default IOCP proactor, may only connect to the loopback
   address, and HTTP proxies are switched off (`NO_PROXY=*`, proxy variables removed, which also
   overrides a Windows system proxy), so a local proxy cannot relay requests out. Covers requests,
   urllib3 and httpx (sync and async). **Limits:** gRPC does not use Python sockets (covered by 1–4);
   UDP datagrams and DNS lookups are not blocked (they can leak a host name, no data); a service
   listening on loopback is not necessarily local (a tunnel or port-forward, e.g. on the Redis port
   the rate limiter pings at import; production runs no Redis today).

**Verification:** `backend/tests/unit/test_prb002_no_cloud_in_tests.py` (19 tests: no app module
imported before the guard, the environment layers or the credential guard; each layer; credentials
refused also with CI's emulator variable, and a GCS client failing at once under it; HTTP proxies
off; outbound `connect`, `connect_ex`, a host name and an asyncio connection refused, a loopback
connection allowed;
the end result for the **start-up user store singleton** and the `AuthService` that uses it (the
object that wrote to production), a new user store, the Firestore client, the segmentation service
and the storage service). Negative controls `scripts/safety/prb002_negative_controls.py`: 19
mutations, each removing or weakening one layer or re-introducing a defect the independent review
found (§6); result in `records/risk_verification/PRB-002_negative_controls_2026-10-24.json`. The
controls refuse to start if `conftest.py` has uncommitted changes, restore it on exit or signal, and
run with an outer environment that already hides credentials and carries dummy service variables,
so no control can reach the cloud. The base without the guard was deliberately **not** run "failing
first": on this computer it writes to production, which is the defect. Full backend suite with the
guard, and the integration step run the way CI runs it: see the PR.

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
  production either. Checked 2026-10-24 by the coordinating agent with a read-only
  `gcloud run services describe brain-mri --project=brain-mri-476110` (setting names and non-secret
  values only; separate from the log-based scope above): the production Cloud Run service sets
  `GOOGLE_CLOUD_PROJECT` explicitly, so this would not change production behaviour. It changes
  start-up code, so it needs its own change record, tests and a careful deployment.
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
- Mapping to SPR-001 §2: **Critical** lists "safety impact, data corruption, complete system
  failure"; **Major** "significant functional loss, no workaround". There was no safety impact and no
  functional loss. Test records were added to a production collection by an uncontrolled process for
  months without any control noticing; read conservatively, that is contamination ("data
  corruption") of production data, so **Critical is proposed**. Read narrowly (no existing record
  altered or lost), it is Major. The owner decides. Response: same day (this branch), as Critical
  requires.
- Under ISO 27001 A.8.31 / A.8.33 (separation of environments, test information) it is in any case a
  nonconformity of the development process.

## 6. Independent review before merge (2026-10-24) and changes made

An independent reviewer (AI agent, read-only, with a local proxy that logged and refused every
outbound connection: zero attempts during the test runs) found, in the first version of this
branch (`1bd6d69`):

1. **CI regression.** CI sets `FIRESTORE_EMULATOR_HOST=localhost:8081` without an emulator; the first
   version then gave *anonymous* credentials to every Google client, so routes that fell back via
   try/except hung on gRPC (4 to 5 min per request in a local CI simulation) and an unmocked GCS call
   retried towards storage.googleapis.com. **Changed:** layer 4 always refuses; mutation M9 re-creates
   the old branch, and tests run with CI's variable.
2. **The tests did not check the object that wrote to production** (the start-up singleton), and
   moving the guard below the app import went undetected. **Changed:** tests on the singleton and on
   `AuthService`, a test that no app module was imported before the guard, mutation M10.
3. A cached Firestore client could keep a guard state: moot now that no client can be built.
4. Other inherited secrets. **Changed:** layer 3 removes them; layer 5 added; mutations M11 to M13.
5. Emulator host parsing: moot (branch removed).
6. Negative-control script safety. **Changed:** refuses an uncommitted `conftest.py`, restores on
   signal.
7. Record accuracy (emulator and CI claims, log rotation, severity mapping, marker docs).
   **Changed:** this record and the marker comments in `conftest.py`.

**Re-review of `8bd7fe4`** (same reviewer): findings 1 to 8 closed or moot (CI simulation: the FHIR and
DICOMweb requests that hung for 4 to 5 minutes now take 0.05 s; zero outbound attempts at the
proxy). New findings, all addressed in the next commit:
- N1: on Windows, asyncio's default proactor connected through IOCP `ConnectEx`, bypassing the
  socket guard (`httpx.AsyncClient`, `redis.asyncio`, MCP client). **Changed:** the proactor's
  `connect` is guarded; test with `asyncio.open_connection`; mutation M16.
- N2: a proxy on loopback could relay requests out. **Changed:** proxies off (`NO_PROXY=*`); test;
  mutation M17. The Redis-port ping at import is documented as a limit.
- N3: `connect_ex` unpatched and host names treated as loopback went undetected; UDP and DNS not
  guarded. **Changed:** tests and mutations M18, M19; UDP and DNS documented as limits.
- N4: the opt-in Firestore emulator tests cannot run under the guard. **Changed:** marker text says
  so (CI deselects them).
- N5: record nits (section reference, layer-5 wording, ordering claim, how the Cloud Run setting was
  checked). **Changed:** this record. Single-layer reordering is now tested (M14, M15).

## 7. Approval

| Role | Name | Decision | Date |
|---|---|---|---|
| Owner / management representative | N. G. Bonilla Vargas | PENDING owner approval | |
