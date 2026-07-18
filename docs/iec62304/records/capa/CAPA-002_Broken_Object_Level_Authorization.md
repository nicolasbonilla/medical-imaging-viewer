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
| **CA-2.1** | Corrective | Define and implement object-level authorization for imaging, studies, patients and documents: every route resolves the requested object and verifies the caller's entitlement before returning data. | Automated test: user A receives 403/404 for user B's `file_id`, on every data-returning route. | PENDING |
| **CA-2.2** | Corrective | Add the missing requirement to the SRS (which users may access which records) and the corresponding hazard + risk control to the RMF. | REQ and RC exist, RC bound to the CA-2.1 test. | PENDING |
| **CA-2.3** | Corrective | Stop accepting raw storage paths as caller input; use opaque identifiers resolved server-side against the caller's entitlements. | No route takes a `{file_id:path}` that maps directly to a bucket key. | PENDING |
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
