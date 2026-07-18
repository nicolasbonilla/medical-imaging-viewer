# CAPA-001 — Risk Control Verification Integrity

**CAPA ID**: CAPA-001
**Date Opened**: 2026-07-16
**Source**: Internal audit finding (code inspection of the Class C codebase against
`docs/iec62304/03_Risk_Management_File.md` and
`docs/iec62304/records/risk_verification/RCV-SUMMARY_2026-04-12.md`)
**Severity**: **CRITICAL** — regulatory non-compliance affecting records that
substantiate patient-safety risk controls (QP-002 §5)
**Owner**: *(to be assigned — Software Safety Officer / QMS Manager)*
**Status**: OPEN — investigation complete, corrective actions in progress
**Procedure**: QP-002 Corrective and Preventive Action

---

## 1. Detection and Initiation (QP-002 §4.1)

During an internal review of the Class C codebase, four risk controls recorded as
**VERIFIED** in the Risk Management File (RMF) and in the Risk Control Verification
Summary (RCV-SUMMARY-2026-04-12) were found **not to be implemented as described**.

RCV-SUMMARY-2026-04-12 states: *Total Risk Controls 22 · Verified 21 (95.5%) ·
Partial 1 · **Failed 0***. That summary is not accurate.

The nonconformity is **not primarily a software defect**. It is a failure of the
verification record itself: the QMS asserts, in a controlled document, that safety
controls exist which cannot be found in the code they cite.

---

## 2. Investigation (QP-002 §4.2)

Each finding below was confirmed by direct inspection of the cited source file.

### 2.1 RC-006 — report disclaimer — **NOT IMPLEMENTED**

| | |
|---|---|
| RMF record (`03_Risk_Management_File.md:213`) | RC-006: Report header states "AI-Generated — Requires Physician Review Before Clinical Action" … **VERIFIED — System prompt reviewed, disclaimer present in all 5 templates** |
| RCV-SUMMARY record | RC-006 … `brain_report_service.py` FORMAT_INSTRUCTIONS mandate disclaimer in every report … **VERIFIED** |
| **Actual state** | `backend/app/services/brain_report_service.py` contains **zero** occurrences of `disclaimer`, `limitation`, `physician review`, `not for clinical`, or `assistive` (case-insensitive). The control is absent in every form, not merely differently worded. |

Hazard **HAZ-003** (AI report hallucination, severity S5 — Catastrophic) is reduced to
ALARP on the strength of this control.

### 2.2 RC-017 — authentication coverage — **PARTIALLY IMPLEMENTED**

| | |
|---|---|
| RMF record (`03_Risk_Management_File.md:224`) | RC-017: JWT authentication on **ALL 103 API endpoints (100% coverage)** … **VERIFIED — All 103 API endpoints require JWT authentication** |
| **Actual state** | `backend/app/api/routes/websocket.py:24-30` — `@router.websocket("/imaging")` accepts `websocket`, `compression` and an injected `imaging_service`. There is **no token parameter, no `get_current_active_user` dependency and no handshake authentication**. The client subsequently requests slices by `file_id` and receives pixel data. `get_websocket_stats` and `get_connection_stats` are likewise unauthenticated. |

The REST surface **is** protected — the clinical route modules do carry
`get_current_active_user`. The defect is confined to the WebSocket transport, but the
record claims 100 % coverage, which is false, and the exposed data is patient imaging.

Hazard **HAZ-010** (unauthorized access, S4) is affected.

### 2.3 RC-007 — de-identification before third-party API — **NOT IMPLEMENTED**

| | |
|---|---|
| RCV-SUMMARY record | RC-007: De-identified data only sent to Claude API (HIPAA Safe Harbor) — `brain_report_service.py` `_build_findings_prompt` **strips PHI** … **VERIFIED** |
| **Actual state** | `_build_findings_prompt` exists (`brain_report_service.py:387`) but performs **no de-identification**; it composes a prompt. No de-identification routine exists anywhere under `backend/app/` (no `deident*`, `anonym*`, `scrub*` or `strip_phi*` definition). Free-text fields supplied by the caller are interpolated verbatim. |

### 2.4 RC-010 — per-lesion confidence — **RECORD OVERSTATES THE CODE**

| | |
|---|---|
| RMF/RCV record | RC-010: Classification confidence scores displayed per lesion … **VERIFIED** |
| **Actual state** | `backend/app/services/ms_region_classifier.py:404` sets `confidence = None` on the **geometric** classification path, correctly annotated at `:386-387` as *"Geometric method has no empirically calibrated confidence scores … use parcellation or MSMask for validated results"*. |

**Note — this one is different in kind, and it matters for the root cause.** The code
is *more honest than its documentation*. The engineering judgement was correct
(refusing to emit an uncalibrated confidence); the verification record failed to
capture that the control is deliberately absent on the least reliable path.

### 2.5 Related observation — RC-022 verification method

`03_Risk_Management_File.md:230` records RC-022 (all images preprocessed to MNI 1 mm)
as *"VERIFIED — Confirmed by user: … documented in project memory"*. Recollection is
not objective verification evidence under ISO 14971. Separately, the code does not
depend on the assumption — it **silently defaults** `voxel_spacing` to `(1.0, 1.0, 1.0)`
when metadata is absent (e.g. `segmentation_regions.py:92`), which is the harm
described by HAZ-014. Tracked as a separate action (CA-5).

### 2.6 Procedural gap

QP-002 §6 requires a CAPA Register at `docs/iec62304/records/capa_register.md`.
**It did not exist** at the time of this finding. Created under CA-6.

---

## 3. Root Cause Analysis (QP-002 §4.3 — 5 Whys)

**Problem statement:** Four risk controls were recorded as VERIFIED without being
implemented as described, and the verification summary reported 0 failures.

1. **Why were controls recorded as VERIFIED when absent?**
   Verification was performed as *"code inspection"* and recorded as prose describing
   the intended design, rather than as an executed check against the code.

2. **Why did prose descriptions pass as verification evidence?**
   The RCV record's "Verification Method" column permits free-text assertions
   (e.g. *"Code inspection: grep for 'assistive' in …"*) with **no requirement to
   record the command, its output, the commit SHA, or a linked test ID**. A claimed
   grep and a performed grep are indistinguishable in the record.

3. **Why was there no objective, re-runnable evidence requirement?**
   No acceptance criterion in the verification process obliges a control to be
   demonstrated by an automated, failing-capable test. The RMF cites source files, but
   nothing binds a control to an executable assertion.

4. **Why was the absence not caught by the test suite or CI?**
   No test asserts the presence of any risk control. CI does not gate on risk-control
   verification, and coverage enforcement is disabled (`backend/pytest.ini:43` —
   `--cov-fail-under` commented out). A missing control produces a green build.

5. **Why did the same author both implement and verify, with no independent check?**
   Verification was recorded as *"Development Team (code inspection)"* — the same party
   that wrote the design documents. ISO 14971 expects verification of risk control
   implementation to be objective; single-party self-attestation on a document that
   reduces an S5 hazard to ALARP is not sufficient.

**Root cause:**
> The verification process accepts *unexecuted, unreproducible, self-attested prose* as
> objective evidence for risk-control implementation, and nothing in the build pipeline
> can contradict it. The controls were documented as designed rather than verified as
> built.

**Contributing factor:** the RMF and the RCV-SUMMARY describe RC-006 with *different*
wording (a header string vs. a "limitations section"), so neither is a testable
specification — there was no unambiguous statement of what "implemented" means.

---

## 4. Action Plan (QP-002 §4.4)

Timelines per QP-002 §5 for **Critical**: investigation 3 days · action plan 7 days ·
implementation 7 days · effectiveness verification 30 days.

| ID | Type | Action | Acceptance criteria | Status |
|----|------|--------|--------------------|--------|
| **CA-1** | Corrective | Implement RC-006: mandatory, non-removable AI/physician-review disclaimer in `brain_report_service.py` output **and** in the report UI. | Automated test asserts the disclaimer string is present in every generated report for all 5 templates and all 3 languages. | **BACKEND DONE** (see §5.1) — UI pending |
| **CA-2** | Corrective | Implement RC-017: authenticate all WebSocket endpoints; authorize `file_id` against the caller. | Automated test asserts an unauthenticated WS connection is rejected (close code 1008). | **AUTH DONE** (see §5.3) — authorization split to CAPA-002 |
| **CA-3** | Corrective | Correct RC-006, RC-007, RC-010, RC-017, RC-022 rows in the RMF and RCV-SUMMARY to their true status, with linked evidence. Re-verify the remaining 17 controls by the same standard. | No row reads VERIFIED without a linked, executable test ID. | PENDING |
| **CA-4** | Corrective | Implement RC-007 (de-identification) or restate the control to match reality and re-assess HAZ-003 residual risk. | De-identifier with an allow-list, tested with PHI present in the input. | PENDING |
| **CA-5** | Corrective | Make `voxel_spacing` a required input; remove the silent 1 mm default (HAZ-014). | Raises when spacing is unavailable; test with 3 mm slice thickness. | **DONE** — new control RC-024. 4 route fallbacks and 14 Class C service defaults removed; refuses with HTTP 422 rather than assuming. 26 assertions incl. the 3 mm case; negative controls 17 failed / 1 failed. |
| **PA-1** | Preventive | Require every risk control to be bound to an **automated test** (`RC-xxx` referenced in the test name/docstring). Verification records must cite the test ID and commit SHA, not prose. | Verification template updated; no VERIFIED row without a test ID. | PENDING |
| **PA-2** | Preventive | Add a CI gate that fails the build when any RC lacks a linked passing test; enable `--cov-fail-under`; run `tests/security/` in CI. | CI red on a deliberately removed control (see §5). | PENDING |
| **PA-3** | Preventive | Require independent verification: the author of a risk control may not record its verification. | QP updated; RCV records name a verifier distinct from the implementer. | PENDING |
| **CA-6** | Corrective | Create the CAPA Register required by QP-002 §6. | File exists and lists CAPA-001. | **DONE** |

---

## 5. Effectiveness Verification (QP-002 §4.6)

To be performed no later than **2026-08-15** (30 days).

The check is a **negative control**, because the failure mode being corrected is
"absence goes unnoticed":

1. Remove the RC-006 disclaimer string in a scratch branch → the RC-006 test **must
   fail** and CI **must go red**.
2. Remove WebSocket authentication in a scratch branch → the RC-017 test **must fail**.
3. Re-run the full RC verification; every VERIFIED row must resolve to a passing test
   ID at a named commit.

If any of the above passes while the control is absent, the CAPA is **not** effective
and must be re-opened.

### 5.1 Result — RC-006 negative control (executed)

**Implementation**: `backend/app/services/brain_report_service.py` —
`REPORT_DISCLAIMERS` (en/es/de) applied by `_apply_disclaimer()` at the single
generation return point, unconditionally, template-independent. Applied in code
rather than requested of the model: a control an LLM may decline to emit is not a
control, and its omission would be invisible.

**Test**: `backend/tests/unit/test_rc006_report_disclaimer.py` — 14 assertions
covering all 3 languages, all templates, empty/failed generation, unknown-language
fallback, idempotency, and absence of fabricated-citation instructions.

| Codebase state | Expected | Observed |
|---|---|---|
| Control present | all pass | **14 passed** |
| Enforcement line replaced with `return body` | must fail | **8 failed, 6 passed** |

The control is therefore bound to executable evidence: its removal turns the suite red.

### 5.2 Result — RC-017 negative control (executed)

**Implementation**: `backend/app/api/routes/websocket.py` — `_extract_token()` /
`_authenticate_websocket()`, invoked before the socket is accepted and before any
service capable of reading patient data is constructed. Credentials accepted via
`Authorization: Bearer`, the `bearer` subprotocol (the only way a browser can send
a credential without putting it in the URL), or `?token=` (accepted for
compatibility, logged as a warning — query strings are recorded by proxies and
access logs, so such a token should be treated as disclosed). All failure modes
close with **1008** and an identical reason, so a caller cannot distinguish
"no token" from "bad token" from "expired token". The two `/ws/stats` and
`/ws/connections/{id}` GET endpoints, also unauthenticated, now require
`get_current_active_user`.

**Test**: `backend/tests/unit/test_rc017_websocket_auth.py` — 14 assertions. Uses
a WebSocket double rather than a live server, deliberately: a risk-control test
that cannot run in CI without Redis, GCS and a DI container is not a risk control.

Two independent sabotage vectors were exercised, because a control can disappear
either by being unwired or by being neutralised in place:

| Codebase state | Expected | Observed |
|---|---|---|
| Control present | all pass | **14 passed** |
| Enforcement call removed from the endpoint (unwired) | must fail | **1 failed, 13 passed** |
| `_authenticate_websocket` returns a token unconditionally (neutralised) | must fail | **5 failed, 9 passed** |

Full backend unit suite after the change: **264 passed, 0 failed**.

**Observation — the endpoint has no consumers.** A repository-wide search found
no client of `/ws/imaging`: the router is registered in `app/main.py:281` and
served in production, but nothing in the frontend or elsewhere connects to it.
It was therefore live, unauthenticated attack surface streaming patient imaging,
with zero functional benefit. ISO 14971 §7.1 ranks *inherently safe design* above
*protective measures*: **removing** the endpoint would eliminate the hazard rather
than mitigate it. That is a product decision, not a unilateral one, so the
endpoint has been authenticated as CA-2 specifies and the removal option is
raised here for the Software Safety Officer to decide.

### 5.3 Process observation — the first negative control was invalid

The RC-006 negative control was first attempted with a string-substitution patch
that **silently did not match**. The suite reported 14 passed, which would have
been recorded as "negative control performed, control confirmed" — when in fact
the control had never been challenged.

This is the **same failure mode as the finding that opened this CAPA**: an
unverified action recorded as a completed verification. It was caught only because
the sabotage was independently re-checked (`grep` for the marker) before the result
was trusted. Every negative control in §5.1 and §5.2 was subsequently confirmed
applied before its result was accepted.

**Consequence for PA-1**: a negative control is only evidence if the record shows
*both* that the sabotage was applied and that the suite failed. Adding to PA-1's
acceptance criteria: verification records citing a negative control must include the
observed failure output, not merely the assertion that one was run. A negative
control that reports "all passed" is an inconclusive result, never a passing one.

---

## 6. Regulatory Assessment (QP-002 §7)

- The device is **not CE-marked, not FDA-cleared and not in clinical use**; there is no
  marketed product and therefore **no vigilance/field-safety reporting obligation** at
  this time.
- No Declaration of Conformity may be signed while this CAPA is open. Note that
  `docs/mdr/DoC-001_Declaration_of_Conformity.md` exists in the repository as a template
  and must not be executed until CA-1…CA-5 are closed and the clinical evaluation report
  is populated.
- This CAPA and its evidence should be presented proactively at the next notified-body
  interaction. A CAPA that a manufacturer raises and closes itself demonstrates a
  functioning QMS; the same finding raised by an auditor does not.

---

## 7. Links

- QP-002 Corrective and Preventive Action Procedure
- `docs/iec62304/03_Risk_Management_File.md` (HAZ-003, HAZ-006, HAZ-010, HAZ-014)
- `docs/iec62304/records/risk_verification/RCV-SUMMARY_2026-04-12.md`
- `docs/iec62304/08_Problem_Resolution_Procedure.md`
- `docs/iec62304/10_Verification_Validation_Plan.md`

---

**Prepared by**: Internal code audit
**Requires**: review and sign-off by the Software Safety Officer before closure.
