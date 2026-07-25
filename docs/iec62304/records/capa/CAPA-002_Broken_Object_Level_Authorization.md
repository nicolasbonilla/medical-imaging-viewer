# CAPA-002 — Broken Object-Level Authorization on Patient Imaging

**CAPA ID**: CAPA-002
**Date Opened**: 2026-07-18
**Source**: Internal code audit, discovered while implementing CAPA-001 CA-2
**Severity**: **CRITICAL** — unauthorized access to patient data (QP-002 §5)
**Owner**: *(to be assigned — Software Safety Officer / QMS Manager)*
**Status**: OPEN — investigation complete, corrective action not started
**Procedure**: QP-002 Corrective and Preventive Action

---

## 1. Detection

While implementing WebSocket authentication (CAPA-001 CA-2), the REST imaging
routes were read to determine how they authorize access to a `file_id`. They do
not authorize it at all.

## 2. Finding

`backend/app/api/routes/imaging.py` injects the authenticated caller and never
uses it:

```python
@router.get("/process/{file_id:path}", response_model=ImageSeriesResponse)
async def process_image(
    file_id: str,
    ...
    current_user: User = Depends(get_current_active_user)   # injected
):
    file_data = await storage_service.download_file(
        settings.GCS_BUCKET_NAME, file_id                   # ... never consulted
    )
```

`file_id` is documented in the same function as *"the GCS object path (e.g.
`patients/{id}/studies/{id}/series/{id}/image.dcm`)"* — a caller-supplied,
guessable, enumerable path into the patient bucket.

A repository-wide search for an ownership or access check
(`owner`, `user_id ==`, `belongs_to`, `verify_access`, `check_access`) across
`app/api/routes/imaging.py` and `app/services/imaging_service.py` returned
**no matches**.

**Consequence**: any authenticated user — any clinician, any test account, any
compromised credential — can read **any patient's imaging** by supplying its
path. Authentication is enforced; authorization is not.

This is OWASP API Security Top 10 **API1:2023 Broken Object Level Authorization**,
applied to protected health information.

### 2.1 Distinction from CAPA-001

CAPA-001 concerns records asserting controls that do not exist. This is different
in kind: **the control was never claimed**. RC-017 speaks only of authentication
("JWT authentication on ALL 103 API endpoints"). No risk control in the RMF
addresses *authorization* — whether an authenticated caller may access *this*
object. The hazard analysis has a gap, not merely a verification gap.

HAZ-010 (unauthorized access, S4) is stated in terms of access to the system.
It does not consider a legitimate user reaching another patient's record.

## 3. Preliminary Root Cause

To be completed with the Safety Officer. Initial assessment:

The threat model assumed a trust boundary at the perimeter — once a caller holds a
valid token they are treated as entitled to the whole dataset. For a
single-institution research tool that assumption is survivable; for a clinical
device holding multiple patients' records under GDPR / HIPAA it is not. No
requirement in the SRS states *which* records a given user may read, so no
control could be designed, and no test could be written.

**This is a requirements gap manifesting as a security defect**, which is why it
warrants its own CAPA rather than an action under CAPA-001.

## 4. Immediate Containment

- The device is **not CE-marked, not FDA-cleared and not in clinical use**; there
  is no production patient data at risk and therefore no breach-notification
  obligation under GDPR Art. 33 at this time. **This must be re-assessed the
  moment real patient data is loaded.**
- No clinical deployment may proceed until CA-2.1 below is closed.

## 5. Action Plan (draft — requires Safety Officer approval)

| ID | Type | Action | Acceptance criteria | Status |
|----|------|--------|--------------------|--------|
| **CA-2.1** | Corrective | Define and implement object-level authorization for imaging, studies, patients and documents: every route resolves the requested object and verifies the caller's entitlement before returning data. | Automated test: user A receives 403/404 for user B's `file_id`, on every data-returning route. | **DONE (enforcement)** — RC-026/027/028/029 cover all data surfaces; each test-bound with a negative control (§9–§12). |
| **CA-2.2** | Corrective | Add the missing requirement to the SRS (which users may access which records) and the corresponding hazard + risk control to the RMF. | REQ and RC exist, RC bound to the CA-2.1 test. | **DONE** — REQ-SEC-014…018 added to the SRS; RC-026…029 added to RMF §5.1; traceability rows added to the matrix (§13). |
| **CA-2.3** | Corrective | Stop accepting raw storage paths as caller input; use opaque identifiers resolved server-side against the caller's entitlements. | No route takes a `{file_id:path}` that maps directly to a bucket key. | **DONE (imaging)** — RC-027 parses against a fixed grammar and rebuilds the key server-side; raw client bytes never reach storage (§10). |
| **PA-2.1** | Preventive | Add an authorization test to the route-review checklist: a new data-returning route may not merge without a cross-tenant denial test. | Checklist updated; CI enforces via `tests/security/`. | PENDING |

## 6. Note on CA-2.3

CA-2.3 is the structural fix and the others are mitigations. While `file_id` is a
storage path supplied by the client, every route must be trusted to validate it
correctly, forever, including routes not yet written. Replacing it with an opaque
identifier resolved server-side removes the class of defect rather than each
instance — the same reasoning ISO 14971 §7.1 applies in ranking inherently safe
design above protective measures.

---

**Prepared by**: Internal code audit
**Requires**: review, root-cause confirmation and sign-off by the Software Safety
Officer. The action plan above is a draft prepared by the finder and must not be
treated as approved.

---

## 8. Investigation update — 2026-07-18

Two findings while preparing CA-2.1 materially change the remediation.

### 8.1 There is no data to authorize against

`created_by` exists on the patient model and the Firestore service has accepted
a `created_by` argument all along — **and no caller ever supplied it**. The route
had `current_user` in scope and called `service.create_patient(data)`.

Every patient record therefore has `created_by = None`. Object-level
authorization needs an entitlement relation to evaluate, and provenance is the
minimum such relation. **It cannot be reconstructed retroactively**: for records
created before 2026-07-18 there is no record anywhere of who created them.

This inverts the sequencing. CA-2.1 cannot simply be "add checks to routes" —
the data those checks would read does not exist. Capturing provenance is now
landed ahead of the entitlement decision, because every day without it enlarges
the permanently un-attributable set. Existing records will need an explicit
disposition (grandfathered, reassigned, or quarantined) as part of CA-2.1.

### 8.2 The routes documented an access-control model that was never built

Ten route docstrings in `patients.py` state *"Required permissions:
PATIENT_CREATE"* (and VIEW / UPDATE / DELETE). **None of those four permissions
existed in the `Permission` enum**, and none was enforced. Every patient route
gated on authentication alone.

In a Class C device a docstring naming a required permission is a claim a
reviewer will believe. An auditor reading `patients.py` would reasonably
conclude the routes were access-controlled.

This is the same class as CAPA-001 — documentation asserting a control that does
not exist — but located in source comments rather than the QMS, so no QMS review
would ever have caught it.

### 8.3 What has been done, and what it does NOT close

Landed as **RC-025** (CAPA-004 CA-4.5):

- The four `PATIENT_*` permissions now exist and are mapped across the four
  roles, with `PATIENT_DELETE` restricted to ADMIN (destructive, and subject to
  regulatory retention).
- All **10 of 10** patient routes enforce a permission; none gates on
  authentication alone.
- `created_by` is captured at creation.
- A test asserts that **no route docstring anywhere promises a permission that
  does not exist** — this is the assertion that would have caught the original
  defect, and it now guards every future route.

**This does NOT close CAPA-002.** RC-025 answers *"may this role operate on
patient records"*. CAPA-002 asks *"may this user access THIS patient"*. An
authenticated VIEWER still reaches every patient in the system. The manifest
entry and the test suite both record that boundary explicitly, so the two
controls cannot be conflated in a future audit.

### 8.4 The open decision

CA-2.1 cannot proceed without an entitlement model, which is a product decision,
not an engineering one. The candidates:

| Model | Rule | Fits |
|---|---|---|
| Creator-scoped | a user sees the records they created | single-clinician research use; wrong for a shared clinic |
| Care-team | explicit user↔patient assignment | clinical reality; needs an assignment UI and workflow |
| Institution/tenant | a user sees their organisation's records | multi-site deployments; requires a tenant field that does not exist |
| Role-graded | RADIOLOGIST sees all, VIEWER sees assigned | common compromise; still needs assignment data |

Only the first is satisfiable with the data now being captured. The others each
require a new relation and a migration decision for existing records.


---

## 9. Enforcement update — 2026-07-19

The three-layer implementation of CA-2.1 under the care-team model is now
enforced on the **patient resource**.

| Layer | Module | Status |
|---|---|---|
| Decision (pure rule) | `app/security/patient_access.py` | Done — RC-026, 19 tests, 4 negative vectors |
| Store (Firestore) | `app/services/care_team_service.py` | Done — assignments never deleted, only revoked (GDPR Art. 5(2)) |
| HTTP guard | `app/security/patient_access_dependency.py` | Done — 11 tests, 3 negative vectors |
| Route wiring | `app/api/routes/patients.py` | Done — 6 patient-scoped routes + care-team management |

**Enumeration defence.** The guard denies with **404, never 403**, and returns an
identical body for "patient does not exist" and "you are not entitled to see it".
A 403 would confirm a record's existence to an unauthorised caller. The audit log
still records the true reason server-side, where it is safe.

**Bootstrap and delegation.** Care-team assignment and revocation themselves
require object-level access to the patient, so a clinician cannot add themselves
to a team they are not on. ADMIN bootstraps the first assignment on any patient,
including quarantined legacy records.

### 9.1 What remains OPEN

CA-2.1 is **not** complete and this CAPA stays **OPEN**:

- **imaging.py, studies.py, documents.py are not yet wired.** They identify the
  patient indirectly — via `file_id` (a raw GCS path) or `study_id` — so
  object-level enforcement there depends on **CA-2.3** (opaque identifiers
  resolved server-side) landing first. Wiring them against a caller-supplied path
  would authorize the path the attacker already controls.
- **CA-2.3** (stop accepting raw storage paths) — not started.
- **CA-2.2** (SRS requirement + RMF hazard/RC for authorization) — the RC now
  exists (RC-026); the SRS requirement is still to be written.
- **Existing-record disposition.** Quarantine is enforced (non-ADMIN denied on
  `created_by = None` with no assignment), but the operational triage — an ADMIN
  reviewing and reassigning legacy records — is a process, not yet a workflow.


---

## 10. CA-2.3 update — 2026-07-19 — imaging references parsed and authorized

The imaging half of the finding in §2 is closed. `imaging.py` no longer passes a
raw caller-supplied key to storage.

**Approach — a parser, not a blocklist.** The instinct is to reject bad paths
(strip `..`, block `config/`). Blocklists on storage keys lose: GCS names are
opaque byte strings, `..` does not traverse, encodings vary, every new prefix is
a new hole. Instead `parse_patient_storage_ref` accepts input *only* if it
matches `patients/{uuid}/studies/{uuid}/series/{uuid}/{safe-filename}` exactly.
Anything that parses has, by construction, a patient_id — which is then
authorized via RC-026. `object_path` is rebuilt from the parsed components, so no
unparsed caller byte reaches the bucket key (RC-027).

This is the CA-2.3 structural fix for imaging: the route no longer trusts the
raw key at all. It did not require a frontend change — the path shape the client
sends is unchanged; it is now validated and authorized rather than used verbatim.

**Enumeration defence preserved.** A malformed reference and a valid reference to
a patient the caller may not see both return an identical 404. During
implementation the two paths initially returned different 404 bodies ("Imaging
object not found" vs "Patient not found") — a genuine oracle, caught by a test
asserting the two are byte-identical, and fixed before commit.

### 10.1 What remains OPEN — CAPA-002 stays OPEN

- **studies.py, documents.py** are not yet wired. They identify the object by
  `study_id` / `document_id`, which need their own resolve-then-authorize path
  (look up the owning patient in Firestore, authorize via RC-026).
- **Segmentation objects** (`segmentations/{id}/...`) are outside the imaging
  grammar and are authorized via their Firestore patient link — not yet built.
- **CA-2.2** (SRS requirement for record-level access) — still to be written.
- **Quarantine triage workflow** for legacy `created_by = None` records.


---

## 11. Studies and documents update — 2026-07-19 (RC-028)

Object-level authorization now covers the **study, series, instance and document**
resources, not just patient and imaging objects.

**Uniform resolve-then-authorize.** Every such object belongs to one patient and
the datastore records the link (study.patient_id; series/instance via study_id;
document.patient_id). `resource_access.py` resolves the object to its owning
patient and reuses the RC-026 decision. A single chokepoint, wired as a
dependency — writing `if obj.patient_id == ...` inline in ~18 routes is how
CAPA-002 happened, and a hand-duplicated check is one that gets omitted from the
next route added. A wiring test asserts each data route depends on the guard.

**Wired**: studies.py — get/update/delete study, list/create series,
get/delete series, list instances, get/update/delete instance, list studies
(scoped). documents.py — get/update/delete document, list versions, list
documents (scoped), list-by-patient (reuses require_patient_access).

**List routes.** An archive-wide listing is the bulk form of this finding. Rule:
a patient_id scope is required for non-admins; with it, the scope is authorized;
admins may list archive-wide. This closes the bulk-metadata leak without needing
result-level entitlement filtering (which remains the fuller, not-yet-built
solution).

**Enumeration defence preserved.** An object that does not exist and one the
caller may not see both resolve to "no authorized patient" and raise an identical
404 — no id-enumeration oracle.

### 11.1 Still OPEN

- **Segmentation objects** (`segmentations/{id}/...`) — authorized via their
  Firestore patient link, not yet built.
- **Result-level list filtering** — the fuller alternative to requiring a
  patient scope, so a clinician could see all patients they are entitled to in
  one unscoped call. Not built.
- **series/instance resolution efficiency** — currently rides the study
  service's pre-existing full-collection scan (N+1). Correct but not efficient;
  a stored patient_id on series/instance docs, or a collectionGroup index, would
  fix it.
- **CA-2.2** (SRS requirement) and the quarantine-triage workflow.


---

## 12. Segmentation update — 2026-07-19 (RC-029) — all data surfaces covered

Object-level authorization now covers the segmentation resource, the last data
surface identified in this CAPA.

**Resolution.** A segmentation stores no patient_id; it stores the file_id of the
image it segments, which is patient-scoped
(`patients/{patient_id}/studies/.../image`). The owning patient is extracted from
that file_id via `extract_patient_id_from_path` — a lenient counterpart to
RC-027's strict download parser, appropriate because here the path is being read
for authorization, not dereferenced. A non-patient or malformed file_id fails
closed to a 404.

**Wired.** 12 object routes (`{segmentation_id}`: get, paint, slice mask, overlay,
segmentation-only, save, delete, labels, nifti, binary mask get/put, info) via
`require_segmentation_access`. `create_segmentation` authorizes `request.file_id`
through the imaging guard — a caller may only segment an image they can access.
`list_segmentations` requires a file_id scope for non-admins and authorizes every
referenced patient; one off-limits file denies the whole listing.

### 12.1 Coverage reached

| Data surface | Control | Status |
|---|---|---|
| Patient records | RC-026 | enforced |
| Imaging objects | RC-027 | enforced |
| Study / series / instance | RC-028 | enforced |
| Clinical documents | RC-028 | enforced |
| Segmentations | RC-029 | enforced |

Every data-returning route now resolves the requested object to an owning patient
and authorizes the caller against the care-team decision, denying with an
identical 404 that never reveals object or patient existence.

### 12.2 What remains before CAPA-002 can CLOSE

The enforcement is complete; the CAPA is not yet closable:

- **CA-2.2** — the SRS requirement stating which users may access which records is
  still to be written (the control RC-026…RC-029 exists; the specification it
  satisfies does not yet).
- **Quarantine-triage workflow** for legacy `created_by = None` records — the
  policy denies them to non-admins, but the operational ADMIN reassignment
  process is not built.
- **Result-level list filtering** — non-admins must currently scope listings to
  one patient; seeing all entitled patients in one call needs result filtering.
- **Efficiency** — series/instance and segmentation resolution ride pre-existing
  full-collection scans (N+1). Correct but not performant; storing patient_id on
  those documents would fix it.
- **Effectiveness verification** by the Safety Officer, per QP-002.


---

## 13. CA-2.2 update — 2026-07-19 — the specification now exists

The controls RC-026…RC-029 were implemented ahead of any requirement stating
*which users may access which records*. Under IEC 62304 §5.2 a control without a
stated requirement is not traceable, so the requirement has now been written:

- **SRS**: REQ-SEC-014 (object-level authorization / care-team), REQ-SEC-015
  (enumeration defence — 404 not 403), REQ-SEC-016 (no raw storage paths),
  REQ-SEC-017 (provenance capture), REQ-SEC-018 (quarantine). REQ-SEC-005's
  permission count corrected 15 → 19.
- **RMF §5.1**: RC-026, RC-027, RC-028, RC-029 rows added, each VERIFIED against a
  named test with a recorded negative control.
- **Traceability matrix §**: a new *Object-Level Authorization* section binds each
  REQ-SEC-014…018 to its control and test. While there, the matrix's stale
  "VERIFIED (code inspection)" safety rows — a THIRD document still asserting the
  status CAPA-001 CA-3 corrected in the RMF — were marked withdrawn, closing a
  records-disagreement that had survived the earlier correction.

### 13.1 Remaining before CAPA-002 can be CLOSED

Enforcement and specification are complete. Still open:

- ~~**Quarantine-triage workflow**~~ **DONE (2026-07-19)** — `GET /patients/quarantined`
  (ADMIN-only via `require_role`, the first use of that previously-dead
  dependency) lists records with no provenance. It scans and filters in memory
  because legacy records lack the `created_by` field entirely and a Firestore
  `== None` query would miss them; a capped scan reports `scan_capped` so a
  truncated view is never mistaken for the whole. Reassignment reuses the
  existing `POST /{patient_id}/care-team`, after which the record leaves
  quarantine.
- **Result-level list filtering** — non-admins must scope listings to one patient.
- **Resolution efficiency — DEFERRED with a recorded reason.** `get_series` is
  O(studies); `get_instance` is O(studies × series). The fix is to denormalise
  `patient_id` onto series/instance documents and resolve via a Firestore
  `collectionGroup` query (a slot in the existing `firestore.indexes.json`). It
  is deliberately not done in this pass: the study service's Firestore methods
  are not exercised against a live store or emulator in CI (the unit suite uses
  fakes), so a `collectionGroup` change would ship UNVERIFIED to a Class C data
  path — contradicting the discipline this effort established. It needs a
  Firestore-emulator integration test in CI first. Correctness and security are
  unaffected meanwhile; only latency on the series/instance authorization path.
- **Effectiveness verification** by the Software Safety Officer per QP-002 §4.6,
  including a negative-control demonstration that removing a guard turns CI red on
  a representative data route.
