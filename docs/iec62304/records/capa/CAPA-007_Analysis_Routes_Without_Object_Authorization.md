# CAPA-007 — Segmentation Analysis Routes Without Object-Level Authorization

**CAPA ID**: CAPA-007
**Date Opened**: 2026-10-17
**Source**: CAPA-006 review round 2 (code reviewer, finding "BLOCKER (deploy)"); enumeration of the routes the application actually mounts
**Severity**: **CRITICAL**. Any authenticated user could read another patient's lesion analysis, DIS assessment, comparisons and DICOM-SEG export, write lesion annotations, and read any stored object through a client-supplied storage path (HAZ-010; OWASP API1:2023 and API3:2023; GDPR Art. 32; MDR Annex I §17.4). QP-002 §5.
**Owner**: *(to be assigned: Software Safety Officer / QMS Manager)*
**Status**: OPEN.
- Implemented on branch `fix/analysis-routes-authorization-capa007`: CA-7.1 to CA-7.3 and PA-7.1. **Approved by N. G. Bonilla Vargas on 2026-10-17** (PR #45) and merged.
- Pending: CA-7.4. PA-7.2 is implemented by CAPA-009 (PA-9.1), which found the patient check (RC-026) not executing and ~40 routes without object-level authorization.
- Effectiveness is not verified.

**Procedure**: QP-002 (`docs/qms/QP-002_CAPA_Procedure.md`) · SPR-001
**Related**: HAZ-010 · REQ-SEC-001 · RC-029 (erratum) · RC-027 · CAPA-002 · CAPA-006 (Finding 10, PA-6.2)

---

## 1. Finding

The C3 refactor (`5ebe5f6`, 2026-07-10) moved ten routes from `segmentation.py` into
`segmentation_regions.py` and `segmentation_analysis.py`. CAPA-002 RC-029 was verified on
2026-07-19 by a test that read **only `segmentation.py`**, so the moved routes kept authentication
only.

CAPA-006 authorized the two region routes. The **eight analysis routes**, all live in production,
remained open:

| Route | Exposure |
|---|---|
| `GET /segmentation/{id}/lesion-analysis` | any patient's lesion counts and volumes |
| `GET /segmentation/{id}/dis-assessment` | any patient's DIS result |
| `POST /segmentation/{id}/lesion-annotations` | **write** of annotations on any patient's segmentation |
| `GET /segmentation/{id}/export/dicom-seg` | DICOM-SEG export of any patient's segmentation |
| `POST /segmentation/compare` | metrics between any segmentations or instances |
| `POST /segmentation/agreement-map` | agreement map of any masks |
| `POST /segmentation/longitudinal/compare` | longitudinal comparison of any two timepoints |
| `POST /segmentation/longitudinal/sel` | slowly-expanding-lesion analysis of any two timepoints |

**Read of any stored object.** In addition, `compare` used a **client-supplied `gcs_path`** as the
storage key for instance masks. Any authenticated caller could therefore read any object in the
imaging bucket. RC-027 forbids exactly this ("raw client paths are never used as bucket keys"). The
UI never sends `gcs_path`.

**Mitigating factors.**
- Identifiers are random UUIDs.
- All routes require authentication.
- The device is not in clinical use.

These factors reduce the likelihood of exploitation, not the severity.

## 2. Corrective Actions

| ID | Action | Status |
|----|--------|--------|
| **CA-7.1** | `lesion-analysis`, `dis-assessment`, `lesion-annotations` and `export/dicom-seg` now depend on `require_segmentation_access`, returning 404 to a caller not entitled to the patient | **DONE** (branch) |
| **CA-7.2** | New `authorize_mask_specs()` in `resource_access.py`: every `{type, id}` a request body references (segmentation or instance) must resolve to a patient the caller may access, or the request gets 404; an unknown type returns 400. It is used by `compare`, `agreement-map`, `longitudinal/compare` and `longitudinal/sel` | **DONE** (branch) |
| **CA-7.3** | `compare` no longer reads a client `gcs_path`; it uses only the authorized instance's own object path | **DONE** (branch) |
| **CA-7.4** | RC-024 deviation: `longitudinal/compare` and `longitudinal/sel` fall back to 1 mm spacing when the source image has none. This is flagged in the response (`spacing_resolved=false`) and the UI warns. **Decision for the owner:** keep the flagged fallback, or refuse (422) | **PENDING** (owner decision) |

## 3. Preventive Actions

| ID | Action | Status |
|----|--------|--------|
| **PA-7.1** | `test_rc029_analysis_routes_authorization.py` enumerates the routes the application **mounts**, not a file. Every `/segmentation` route with `{segmentation_id}` must depend on `require_segmentation_access`. Every other `/segmentation` route must be in a classified list, and its handler must call the matching scope authorization. A new, unclassified route fails the build. This implements the authorization half of CAPA-006 PA-6.2 | **DONE** (branch) |
| **PA-7.2** | Extend the same mounted-route enumeration to every router (imaging, studies, documents, patients, AI) | **DONE by CAPA-009** (PA-9.1, branch `fix/object-authorization-everywhere-capa009`): every mounted route that references an object is enumerated, classified and tested by request |

## 4. Root Cause

Verification checked **a file instead of the system**. The RC-029 wiring test read
`segmentation.py`, so a refactor that moved routes out of that file removed them from the
verification without any test failing. This is the same root cause as CAPA-006 (c): evidence that
could not observe the failure.

## 5. Verification Evidence (executed 2026-10-17)

- `backend/tests/unit/test_rc029_analysis_routes_authorization.py`: 12 tests.
  - 2 structural tests over the mounted routes.
  - 8 behavioural tests: a caller without access gets 404 from each analysis route, and the
    segmentation service and storage are never touched before authorization.
  - 1 test of the helper (entitled caller passes; foreign, empty, malformed or unknown references
    are refused).
  - 1 test that the client storage path is ignored.
- **Adapted tests.** `test_analysis_flow_ci_guard.py` and `test_instance_mask_orientation.py` now
  pass authorization through explicitly, and keep testing analysis and orientation. The orientation
  test had relied on the client `gcs_path`, the hole closed by CA-7.3.
- **Negative controls.** Script: `scripts/safety/rc029_negative_controls.py`. Record:
  `docs/iec62304/records/risk_verification/RC-029_analysis_negative_controls_2026-10-17.json`.
  - 11 mutations, each sub-control removed once: the four path dependencies, the four body
    authorizations, the `gcs_path` trust, the helper authorizing nothing, and an unknown type
    accepted.
  - 11 of 11 detected.
  - After restoring: 12 passed.
- **Run without cloud credentials**, as in CI.

**Effectiveness check (after deployment).** A user with no access to a patient gets 404 on each of
the eight routes. This needs two real accounts.

## 6. Regulatory Assessment

- The device is not CE-marked and not in clinical use, so there is no vigilance reporting
  obligation.
- No real-world exploitation is known. No access-log review has been performed; that is the
  owner's decision.
- On a marketed device, this would be a personal-data breach risk to assess under GDPR Art. 33.

---

**Prepared by**: internal audit, 2026-10-17.
**Requires**: human approval before merge and deployment.
