# CAPA-009 — Object-Level Authorization Missing or Not Executing Across the API

**CAPA ID**: CAPA-009
**Date Opened**: 2026-10-17
**Source**: CAPA-008 inspection of the `/ai` routes, followed by an enumeration of every mounted route that references an object (CAPA-007 PA-7.2) and an in-process request probe
**Severity**: **CRITICAL**. Any authenticated user could read or change other patients' records and imaging (HAZ-010; OWASP API1:2023 Broken Object Level Authorization, API5:2023 Broken Function Level Authorization, API7:2023 Server-Side Request Forgery; GDPR Art. 32; MDR Annex I §17.4). QP-002 §5.
**Owner**: *(to be assigned: Software Safety Officer / QMS Manager)*
**Status**: OPEN.
- Implemented on branch `fix/object-authorization-everywhere-capa009` (stacked on CAPA-008, PR #46): CA-9.1 to CA-9.8, PA-9.1, PA-9.2. **Awaiting human approval** (PR).
- Pending: PA-9.3, PA-9.4 and the access-log review (owner decisions).
- Effectiveness is not verified.

**Procedure**: QP-002 (`docs/qms/QP-002_CAPA_Procedure.md`) · SPR-001
**Related**: HAZ-010 · HAZ-012 · REQ-SEC-014/015/016 · new REQ-SEC-019/020 · RC-026 (finding) · RC-027 · RC-028 · RC-029 · new RC-036 · CAPA-002 · CAPA-007 (PA-7.2) · CAPA-008 (CA-8.8)

---

## 1. Findings

### Finding 1 — The patient check never executed (RC-026)

`require_patient_access` was a plain `def` that **returned** the coroutine of the real check.
FastAPI runs a plain-def dependency in a thread pool and uses its return value without awaiting
it, so the check never ran. Every caller holding the role permission reached every patient
through these routes:
- `GET/PUT/DELETE /patients/{id}`;
- care-team list, assign and revoke;
- medical-history list and add;
- `GET /documents/patient/{id}`.

**Evidence.** A request probe as a radiologist with no care-team entitlement reached the data
service, and the authorization function ran **0 times**. With the fix it runs once and answers
404.

RC-026 had been recorded VERIFIED. Its tests checked the decision function directly and checked
that the text `Depends(require_patient_access)` appears in the route source. No test sent a
request, so nothing could observe that the dependency was inert.

### Finding 2 — Routes that never authorized the object they reference

All confirmed by reading each handler, and by the request tests in §5.

| Area | Routes | Exposure |
|---|---|---|
| Studies | `instances/{id}/download-url`, `{study_id}/download-urls`, `instances/{id}/mask-data`, `patient/{patient_id}`, `accession/{n}`, `POST /studies`, `upload/init`, `upload/complete` | Signed download links for any instance or study; any expert mask; any patient's study list; lookup by accession; creating studies and uploading into any patient |
| Documents | `{id}/download-url`, `patient/{id}/download-urls`, `study/{study_id}`, `versions/{version_id}`, `upload/init`, `upload/complete`, `versions/upload/init`, `versions/upload/complete` | Signed links to any patient's documents; uploads into any patient or document |
| FHIR | `Patient/{id}`, `ImagingStudy/{id}` | Any patient's demographics and studies |
| Patients | `by-mrn/{mrn}` | Enumeration of patients by (often sequential) MRN |
| AI | `segment/interactive`, `segment/auto`, `anomaly/detect`, `volumetry/compute`, `volumetry/compare`, `segment/{task_id}/status` | Jobs on any image or segmentation; anyone's task |
| Clinical tools | `lst-ai`, `flames`, `synthseg`, `task/{id}`, `task/{id}/result` | Jobs on any image; anyone's task |
| PACS (DICOMweb) | `import`, `import/{job_id}`, `imports` | Import into any patient (HAZ-012); anyone's jobs |
| Imaging | `matplotlib-2d?segmentation_id=` | Another patient's mask drawn onto an authorized image |
| Segmentation | `{id}/nifti?ref_file_id=` | A raw client storage path used as a bucket key (RC-027 class) |
| Conformal (research, off) | `select`, `status-mask` | Authorized the path, then downloaded the raw client string |

Several handlers state "Requires STUDY_VIEW permission"; no permission was checked.

### Finding 3 — Server-side request forgery through PACS connections

Any authenticated user could create a PACS connection to any URL and "test" it. Testing makes
the server send a request to that URL. Users could also delete any connection.

### Finding 4 — Live websocket connection statistics

`/ws/connections/{id}`: any user could read the statistics of any other user's live connection.

### Finding 5 — Why nothing caught it

The CAPA-007 route enumeration covered `/segmentation` only. PA-7.2 (all routers) was pending.

### Finding 6 — A dead route

`PATCH /patients/history/{history_id}` depends on `require_patient_access` but has no
`{patient_id}` in its path. It always fails validation (422), and its service raises
`NotImplementedError`. The UI still offers it. It is a broken feature, not a leak.

### Mitigating factors

- Identifiers are random UUIDs, except MRN and accession numbers.
- Every route requires authentication.
- The device is not in clinical use.

These reduce likelihood, not severity.

## 2. Corrective Actions

| ID | Action | Status |
|----|--------|--------|
| **CA-9.1** | `require_patient_access` and `require_imaging_access` are `async def` and await the check; the root cause is documented in the code | **DONE** (branch) |
| **CA-9.2** | Studies: path dependencies (`require_instance_access`, `require_study_access`, `require_patient_access`) on download links, mask data and the patient list; body checks (`authorize_patient_id`, `authorize_study_id`) on create, accession lookup and upload init | **DONE** (branch) |
| **CA-9.3** | Documents: `require_study_access`, new `require_version_access`, `require_document_access`, `require_patient_access`; upload init authorizes the patient and checks that a linked study belongs to the same patient (400 otherwise); version upload authorizes the document | **DONE** (branch) |
| **CA-9.4** | FHIR Patient / ImagingStudy and MRN lookup authorize the resolved patient (404) | **DONE** (branch) |
| **CA-9.5** | AI and clinical-tool routes authorize every input image (and an AI refinement mask), require all inputs to belong to one patient matching any given `patient_id` / `study_id` (400 otherwise), and pass the parsed, authorized storage path to the service instead of the raw client string; volumetry authorizes its segmentation or patient | **DONE** (branch) |
| **CA-9.6** | New `app/security/ownership.py` initiator registry. Task, upload and import handles are usable only by their initiator or an administrator; unknown handles get 404 (fail closed). Applied to AI tasks, clinical-tool tasks, study and document uploads, version uploads and PACS import jobs (the job list is filtered to the caller's own jobs) | **DONE** (branch) |
| **CA-9.7** | PACS connections: create, delete and test require ADMIN (`require_role`); listing and reading stay open with credentials masked, so users can pick one. Websocket connection statistics require ADMIN | **DONE** (branch) |
| **CA-9.8** | The overlay segmentation (`matplotlib-2d`) is authorized; the NIfTI reference image and the conformal routes use the parsed, authorized path (RC-027) | **DONE** (branch) |

## 3. Preventive Actions

| ID | Action | Status |
|----|--------|--------|
| **PA-9.1** | `test_capa009_object_authorization_everywhere.py` (47 tests). It completes CAPA-007 PA-7.2. **Structure:** enumerates every mounted route that references an object (path parameter, query or body `*_id`, raw request body); each must be classified with its mechanism (dependency, call, initiator, admin, permission, self) or exempted with a written reason, and the mechanism is re-derived from the code; a `require_X_access` dependency must match a `{X_id}` in the path. **Root cause:** the authorization dependencies are coroutine functions, and no plain-def function used in `Depends()` anywhere returns a coroutine. **Behaviour:** 33 real requests as an unentitled radiologist get 404 before any data service is touched; 4 administrator-only routes get 403; positive controls show that an entitled caller passes and that the AI service receives the authorized path; tests cover overlay and reference-image authorization, mixed-patient tool inputs and the accession lookup; test file paths are checked against the RC-027 grammar, so a 404 cannot come from a malformed path | **DONE** (branch) |
| **PA-9.2** | Negative controls: `scripts/safety/capa009_negative_controls.py`, 32 mutations, one at a time, every anchor asserted unique | **DONE** (branch) |
| **PA-9.3** | Re-verify every risk control whose evidence is source-text matching rather than an executed behaviour (RC-026 is the proven example). Owner to prioritise | **PENDING** |
| **PA-9.4** | Access-log review for the exposure window (owner decision; Firestore and production logs not accessed by the audit) | **PENDING** — owner decision |

## 4. Root Cause

1. **Verification that could not observe the failure.** This is the third occurrence, after
   CAPA-006 and CAPA-007. RC-026 was "verified" by matching source text, and a
   dependency that silently never ran passed it.
2. **Authorization written per route by hand.** A route added later (download links, mask data,
   FHIR, AI, tools, PACS import) needed someone to remember the check. Nothing failed when they
   did not.
3. **Handles treated as secrets.** Task, upload and import identifiers were assumed unguessable,
   and therefore authorization-free.

## 5. Verification Evidence (executed 2026-10-17)

- Request probe, recorded in this CAPA's PR:
  - before the fix: authorization ran 0 times and the handler reached the data service;
  - after the fix: it ran once and the response was 404.
- `backend/tests/unit/test_capa009_object_authorization_everywhere.py`: 47 passed.
- Full backend unit suite with CAPA-008 + CAPA-009: **1200 passed**, without cloud credentials as in CI.
- Adapted test: `test_conformal_route.py`. Its fake image check now returns a reference, as the
  real one does, because the route downloads `ref.object_path`.
- **Negative controls** (`docs/iec62304/records/risk_verification/CAPA-009_negative_controls_2026-10-17.json`):
  - 32 of 32 detected;
  - restored suite green.

**Not verified.** Production behaviour after deployment. The effectiveness check needs two real
accounts:
- each route answers 404 to the user without access;
- an entitled clinician's normal workflow (viewer, uploads, PACS import, AI jobs) still works.

The UI handling of the new 403 for non-administrators creating PACS connections has not been
tested.

## 6. Regulatory Assessment

- The device is not CE-marked and not in clinical use, so there is no vigilance reporting
  obligation.
- No real-world exploitation is known.
- On a marketed device this would be a personal-data breach risk assessed under GDPR Art. 33.
  Whether production access logs are reviewed is the owner's decision (PA-9.4).

---

**Prepared by**: internal audit, 2026-10-17.
**Requires**: human approval before merge and deployment.
