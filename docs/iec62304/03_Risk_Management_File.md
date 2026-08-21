# MSTool-AI: Risk Management File

> ## ⚠️ RESIDUAL RISK DETERMINATIONS WITHDRAWN — 2026-07-18
>
> Adversarial re-verification of all 22 risk controls against the source code
> (CAPA-001 action CA-3) found **4 verified, 5 partial, and 12 overstated or not
> implemented**. Four controls recorded as VERIFIED were absent from the codebase
> in every form.
>
> **Six residual-risk determinations are withdrawn** (HAZ-002, HAZ-004, HAZ-005,
> HAZ-006, HAZ-009, HAZ-010) because the controls that discharged them do not
> exist. They must be **re-derived, not amended**. Section 6 must not be relied on.
>
> **No Declaration of Conformity may be executed, and no clinical use may proceed**,
> while CAPA-001, CAPA-002, CAPA-004 and CAPA-005 are open.
>
> The Verification column in §5.1 now records the true state of each control as of
> 2026-07-18. The **Implementation column has deliberately not been edited** — it
> shows the original claim, so the discrepancy between what was cited and what
> exists remains visible in the record.
>
> Evidence: [`RCV-SUMMARY_2026-07-18.md`](records/risk_verification/RCV-SUMMARY_2026-07-18.md).
> The prior verification record (2026-04-12) is retained and marked withdrawn.

## ISO 14971:2019 Compliant Risk Management Documentation

**Document ID**: RMF-001
**Version**: 1.1 (2026-07-18 — verification column corrected under CAPA-001 CA-3)
**Effective Date**: April 12, 2026
**Standard**: ISO 14971:2019 — Medical devices — Application of risk management to medical devices
**Software Safety Class**: IEC 62304 Class C
**Confidentiality**: Restricted — Regulatory Audit Use Only

---

## Document Control

| Version | Date | Author | Changes | Approved By |
|---------|------|--------|---------|-------------|
| 1.0 | 2026-04-12 | Development Team | Initial release | — |

---

## Table of Contents

1. [Risk Management Plan](#1-risk-management-plan)
2. [Intended Use and Reasonably Foreseeable Misuse](#2-intended-use)
3. [Hazard Identification](#3-hazard-identification)
4. [Risk Estimation and Evaluation](#4-risk-estimation-and-evaluation)
5. [Risk Control](#5-risk-control)
6. [Overall Residual Risk Evaluation](#6-overall-residual-risk-evaluation)
7. [Risk Management Report](#7-risk-management-report)
8. [Post-Production Monitoring](#8-post-production-monitoring)

---

## 1. Risk Management Plan

### 1.1 Scope

This Risk Management File covers all software components of MSTool-AI that can contribute to hazardous situations as identified in IEC 62304 Clause 4.3. The scope includes:

- AI-assisted lesion segmentation (Vertex AI, ONNX Runtime Web)
- Brain volumetry computation
- MAGNIMS region classification
- McDonald 2024 DIS assessment
- Longitudinal lesion tracking
- AI-powered clinical report generation
- DICOM/NIfTI image handling (orientation, coordinate systems)
- User authentication and access control
- DICOMweb PACS integration and DICOM-SEG export

### 1.2 Risk Management Responsibilities

| Role | Responsibility | Assigned To |
|------|---------------|-------------|
| Risk Management Authority | Overall risk management process ownership | Project Lead |
| Risk Analyst | Hazard identification, risk estimation | Development Team |
| Clinical Expert | Clinical harm assessment, acceptability | Clinical Advisor (TBD) |
| Software Developer | Risk control implementation | Development Team |
| Quality Assurance | Risk control verification | QA (TBD) |

### 1.3 Risk Acceptability Criteria

#### Severity Scale

| Level | Severity | Description | Examples |
|-------|----------|-------------|----------|
| S1 | Negligible | Inconvenience or temporary discomfort | UI error with no clinical impact |
| S2 | Minor | Temporary minor injury not requiring intervention | Incorrect non-critical metadata display |
| S3 | Moderate | Injury requiring medical intervention | Delayed diagnosis by days (non-urgent) |
| S4 | Serious | Permanent impairment or life-threatening | Significant delayed diagnosis, wrong treatment |
| S5 | Catastrophic | Death or permanent life-altering injury | Missed critical diagnosis leading to death |

#### Probability of Occurrence Scale

| Level | Probability | Frequency | Description |
|-------|------------|-----------|-------------|
| P1 | Improbable | < 1 in 1,000,000 uses | Extremely unlikely under any conditions |
| P2 | Remote | 1 in 100,000 to 1 in 1,000,000 | Could occur over product lifetime |
| P3 | Occasional | 1 in 10,000 to 1 in 100,000 | May occur several times over lifetime |
| P4 | Probable | 1 in 1,000 to 1 in 10,000 | Likely to occur |
| P5 | Frequent | > 1 in 1,000 | Expected to occur regularly |

#### Risk Acceptability Matrix

| | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| **S5** | ALARP | UNACCEPTABLE | UNACCEPTABLE | UNACCEPTABLE | UNACCEPTABLE |
| **S4** | ACCEPTABLE | ALARP | UNACCEPTABLE | UNACCEPTABLE | UNACCEPTABLE |
| **S3** | ACCEPTABLE | ACCEPTABLE | ALARP | UNACCEPTABLE | UNACCEPTABLE |
| **S2** | ACCEPTABLE | ACCEPTABLE | ACCEPTABLE | ALARP | UNACCEPTABLE |
| **S1** | ACCEPTABLE | ACCEPTABLE | ACCEPTABLE | ACCEPTABLE | ALARP |

- **ACCEPTABLE**: Risk is acceptable without additional controls
- **ALARP**: Risk must be reduced As Low As Reasonably Practicable
- **UNACCEPTABLE**: Risk must be reduced; if not possible, benefit-risk analysis required

### 1.4 Risk Management Activities

| Activity | Trigger | Output |
|----------|---------|--------|
| Hazard identification | New feature, change, incident | Updated hazard list |
| Risk estimation | New hazard, changed conditions | Risk evaluation worksheet |
| Risk control implementation | Unacceptable/ALARP risk | Software requirement + implementation |
| Risk control verification | Control implemented | Verification test result |
| Residual risk evaluation | After all controls applied | Residual risk assessment |
| Post-production monitoring | Continuous | Trend analysis, updated risk file |

---

## 2. Intended Use and Reasonably Foreseeable Misuse

### 2.1 Intended Use Statement

MSTool-AI is intended to be used by qualified healthcare professionals (neuroradiologists, neurologists) as a **decision-support tool** for the visualization, quantification, and monitoring of brain MRI findings in patients with suspected or confirmed Multiple Sclerosis. The software provides automated lesion volume measurement, anatomical region classification, longitudinal change detection, and AI-assisted structured report generation.

**MSTool-AI is intended as an assistive tool and does NOT replace clinical judgment. All outputs require review and confirmation by a qualified physician before any clinical action is taken.**

### 2.2 Intended Users

| User Group | Role | Training Required |
|-----------|------|------------------|
| Neuroradiologist | Primary image interpretation, segmentation review | Board-certified, product training |
| Neurologist | Clinical correlation, treatment decisions | Board-certified, product training |
| Radiology Resident | Supervised image analysis | Under attending supervision, product training |
| IT Administrator | System configuration, PACS integration | Technical training |

### 2.3 Intended Patient Population

- Adults (18+) with suspected or confirmed Multiple Sclerosis
- Brain MRI studies acquired on 1.5T or 3T MRI scanners
- Sequences: T1, T2-FLAIR, T1-Gd (optional: SWI/QSM for CVS/PRL)

### 2.4 Intended Environment

- Hospital or clinic with internet access
- Modern web browser (Chrome, Firefox, Edge — last 2 versions)
- Connected to hospital PACS via DICOMweb (optional)
- Radiologist workstation with medical-grade display (recommended)

### 2.5 Reasonably Foreseeable Misuse

| Misuse Scenario | Risk | Mitigation |
|----------------|------|-----------|
| Using AI results without physician review | Incorrect treatment decision | Disclaimer on all AI outputs, Viewing/Edit mode separation |
| Using software for non-MS diagnoses | AI not trained/validated for other pathologies | Intended use documentation, UI clearly states "MS Analysis" |
| Using software on pediatric patients | AI models not validated for pediatric brains | Intended use limits to adults (18+) |
| IT administrator changes AI model without validation | Model performance degradation | Model version logging, SOUP change control |
| Using on MRI sequences not supported | Incorrect analysis results | Input validation, documented sequence requirements |

---

## 3. Hazard Identification

### 3.1 Hazard Analysis Method

Hazard identification was performed using **Software Failure Modes and Effects Analysis (SFMEA)** applied to each Class C software item identified in the safety classification (IEC 62304 Clause 4.3).

### 3.2 Hazard Register

| HAZ ID | Software Item | Failure Mode | Hazardous Situation | Foreseeable Sequence of Events | Potential Harm |
|--------|--------------|-------------|--------------------|---------------------------------|---------------|
| HAZ-001 | AI Segmentation (Vertex AI; **FLAMeS single-FLAIR GPU worker**, REQ-FUNC-034) | Incorrect lesion boundary delineation (over-/under-segmentation) | Clinician relies on AI segmentation for surgical/treatment planning | AI misses lesion → clinician does not treat → disease progression; OR AI creates false lesion → unnecessary treatment | Death / Serious injury |
| HAZ-002 | Brain Volumetry | Incorrect volume calculation | Clinician uses incorrect volumes for diagnosis | Atrophy missed → neurodegenerative disease untreated → permanent impairment | Serious injury |
| HAZ-003 | AI Report Generation | Misleading or hallucinated clinical text | Clinician acts on AI-generated clinical recommendation without verification | Wrong treatment initiated based on AI text | Death / Serious injury |
| HAZ-004 | Edge AI Screening | False negative (abnormal classified as normal) | Screening badge shows "Normal" for abnormal brain | Patient with pathology dismissed from further evaluation | Death / Serious injury |
| HAZ-005 | MAGNIMS Classifier | Wrong region assignment | Lesion classified as periventricular when actually infratentorial (or vice versa) | Incorrect MS staging → inappropriate disease-modifying therapy selection | Serious injury |
| HAZ-006 | NIfTI/DICOM Handler | Orientation/laterality error | 3D rendering shows brain in wrong orientation | Surgeon uses wrong laterality information → operates on wrong side | Death / Serious injury |
| HAZ-007 | Longitudinal Tracking | Lesion mismatch across timepoints — under-call ("stable" when progressed) AND over-call (**mis-registration → FALSE new/enlarging lesions**: two timepoints with equal array dimensions are not voxel-aligned, so an IoU diff on unregistered volumes manufactures false "new" lesions) | System reports "stable" when lesions progressed, OR reports false new/enlarging lesions and (before RC-014b) fed those raw counts into DIT report language | Missed escalation → progression; OR false disease-activity → over-diagnosis / unnecessary treatment escalation | Serious injury |
| HAZ-008 | DIS Assessment | Incorrect McDonald criteria evaluation | System falsely reports DIS met (or not met) | False positive → unnecessary treatment; False negative → missed diagnosis | Serious injury |
| HAZ-009 | Patient Data Management | Wrong patient data displayed | Clinical decisions made on wrong patient's imaging | Misdiagnosis and wrong treatment for wrong patient | Death / Serious injury |
| HAZ-010 | Authentication System | Unauthorized access | Unauthorized person modifies segmentations or reports | Corrupted clinical data leads to wrong decisions | Serious injury |
| HAZ-011 | DICOM-SEG Export | Corrupted segmentation data sent to PACS | Clinician views incorrect segmentation in PACS viewer | Treatment decisions based on corrupted data | Serious injury |
| HAZ-012 | DICOMweb Import | Import from wrong patient/study | Images imported and associated with wrong patient record | Misdiagnosis | Death / Serious injury |
| HAZ-013 | Claude API Integration | API failure during report generation | System hangs or returns incomplete/garbled report | Clinician receives unusable or misleading partial report | Moderate injury (S3) |
| HAZ-014 | Voxel Spacing | Hardcoded 1mm assumption violated | Volumes calculated with wrong voxel dimensions | Volumes off by factor of 2-10x → wrong atrophy assessment | Serious injury |

---

## 4. Risk Estimation and Evaluation

### 4.1 Pre-Control Risk Assessment

| HAZ ID | Severity | Probability (pre-control) | Risk Level (pre-control) |
|--------|----------|--------------------------|-------------------------|
| HAZ-001 | S5 (Catastrophic) | P3 (Occasional) | **UNACCEPTABLE** |
| HAZ-002 | S4 (Serious) | P3 (Occasional) | **UNACCEPTABLE** |
| HAZ-003 | S5 (Catastrophic) | P3 (Occasional) | **UNACCEPTABLE** |
| HAZ-004 | S5 (Catastrophic) | P3 (Occasional) | **UNACCEPTABLE** |
| HAZ-005 | S4 (Serious) | P3 (Occasional) | **UNACCEPTABLE** |
| HAZ-006 | S5 (Catastrophic) | P2 (Remote) | **UNACCEPTABLE** |
| HAZ-007 | S4 (Serious) | P3 (Occasional) | **UNACCEPTABLE** |
| HAZ-008 | S4 (Serious) | P3 (Occasional) | **UNACCEPTABLE** |
| HAZ-009 | S5 (Catastrophic) | P2 (Remote) | **UNACCEPTABLE** |
| HAZ-010 | S4 (Serious) | P2 (Remote) | **ALARP** |
| HAZ-011 | S4 (Serious) | P2 (Remote) | **ALARP** |
| HAZ-012 | S5 (Catastrophic) | P2 (Remote) | **UNACCEPTABLE** |
| HAZ-013 | S3 (Moderate) | P3 (Occasional) | **ALARP** |
| HAZ-014 | S4 (Serious) | P2 (Remote) | **ALARP** |

---

## 5. Risk Control

### 5.1 Risk Control Measures

| HAZ ID | Risk Control Measure | Type | Requirement ID | Implementation | Verification |
|--------|---------------------|------|---------------|----------------|-------------|
| HAZ-001 | RC-001: All AI segmentation results labeled "assistive — requires physician review" | Inherent safety (warning) | REQ-SAFE-001 | `QuickScreenBadge.tsx` disclaimer text, `brain_report_service.py` system prompt | **NOT IMPLEMENTED** (2026-07-18) — the phrase appears nowhere in the codebase; `SegmentationPanel.tsx` carries no disclaimer; AI masks are indistinguishable from hand-drawn ones. Cited `QuickScreenBadge.tsx` is a different feature. See RCV-SUMMARY_2026-07-18 §3.3. |
| HAZ-001 | RC-002: Viewing/Edit mode separation — AI results are read-only until clinician activates edit | Design control | REQ-SAFE-002 | `ViewerApp.tsx` Viewing/Edit mode toggle, `useSegmentationStore.ts` isPaintMode flag | **PARTIAL** (2026-07-18) — control is real and effective, but the cited file is wrong: the toggle is in `ImageViewer2D.tsx`, not `ViewerApp.tsx`. UI-layer only; no server-side enforcement. Not bound to a test. |
| HAZ-001 | RC-003: Manual segmentation tools always available as override | Design control | REQ-SAFE-003 | `SegmentationPanel.tsx` brush/eraser/fill tools always rendered in edit mode | **OVERSTATED** (2026-07-18) — rendered under two conditions (`!is3D && activeSegmentation`); in 3D view there is no manual override at all. "Always" is false. |
| HAZ-002 | RC-004: Volumetry displays percentile ranges with normative reference | Information for safety | REQ-SAFE-004 | `BrainVolumetryPanel.tsx` percentile bar chart with color coding | **NOT IMPLEMENTED** (2026-07-18) — normative table has no provenance; 11/32 structures covered; `patient_sex` accepted and never used; the sole call site omits `patientAge`, so no percentile is ever computed. See CAPA-005. |
| HAZ-002 | RC-005: Abnormality flags show threshold criteria used | Information for safety | REQ-SAFE-005 | `brain_volumetry_service.py` — percentile < 10 (atrophy) or > 90 (enlargement) flagged | **NOT IMPLEMENTED** (2026-07-18) — thresholds exist only in Python comments and never reach the UI; the flag can never fire (same dead path as RC-004). See CAPA-005. |
| HAZ-003 | RC-006: Report header states "AI-Generated — Requires Physician Review Before Clinical Action" | Inherent safety (warning) | REQ-SAFE-006 | `brain_report_service.py` REPORT_TEMPLATES system prompt includes mandatory disclaimer | **VERIFIED** (2026-07-18) — `brain_report_service.py::_apply_disclaimer`, bound to `tests/unit/test_rc006_report_disclaimer.py`; negative control: removing the enforcement line → 8 failed. Implemented under CAPA-001 CA-1; was **absent** when previously recorded VERIFIED. |
| HAZ-003 | RC-007: Report cannot be auto-committed to clinical record without clinician confirmation | Design control | REQ-SAFE-007 | `AIReportPanel.tsx` — report displayed in viewer with copy button; no auto-save to FHIR or PACS | **IMPLEMENTED BY ABSENCE OF FEATURE, NOT BY A CONTROL** (2026-07-18) — exhaustive search found no persistence path (FHIR is GET-only, DICOMweb inbound-only), but there is no confirmation gate, no export function and no test to turn CI red if auto-save were added. Note: the withdrawn RCV-SUMMARY defines RC-007 as de-identification, which is **not implemented** (CAPA-001 CA-4). |
| HAZ-004 | RC-008: Edge AI badge displays confidence and an **unconditional** assistive-only disclaimer | Information for safety | REQ-SAFE-008 | `QuickScreenBadge.tsx` — the disclaimer shares the result's visibility condition; the toggle is removed | **VERIFIED** (2026-07-18) — bound to `frontend/src/components/QuickScreenBadge.test.tsx`; negative control: toggle restored → 2 failed. Repaired under CAPA-004 CA-4.4. The previous VERIFIED record was reached by grepping for the string, which cannot distinguish a displayed control from one hidden behind `useState(false)`. |
| HAZ-004 | RC-009: Edge AI model file must be explicitly supplied by administrator; hidden when unavailable | Design control | REQ-SAFE-009 | `useEdgeAI.ts` — HEAD request checks model file availability; component hidden if 404 | **VERIFIED** (2026-07-18) — HEAD check also rejects `text/html`, defeating the SPA-rewrite false positive; broader than claimed. Residual: brief pre-resolution window where the button is clickable (fails to an error, not a wrong answer). Not bound to a test. **ID conflict**: the withdrawn RCV-SUMMARY defines RC-009 differently. |
| HAZ-005 | RC-010: Classification confidence scores displayed per lesion | Information for safety | REQ-SAFE-010 | `LesionDashboard.tsx` — confidence column in lesion table, color-coded badges | **DELIBERATELY ABSENT** (2026-07-18) — the geometric path sets `confidence = None` on purpose, having no calibrated confidence. The code is more honest than this document was. The row was wrong, not the code. |
| HAZ-005 | RC-011: Classification method displayed (EDT/Atlas/Geometric) | Information for safety | REQ-SAFE-011 | `LesionDashboard.tsx` — method selector dropdown and method label in results | **PARTIAL** (2026-07-18) — method is displayed and honestly resolves the effective method, but the backend has five methods and the UI exposes three; "EDT" and "Atlas" are not selectable method names. The control's wording cannot be mapped to the screen. |
| HAZ-006 | RC-012: Auto-transpose detection for axis mismatch in 2D rendering | Design control | REQ-SAFE-012 | `SegmentationCanvasLocal.tsx` transposeSlice() function with needsTranspose detection | **PARTIAL** (2026-07-18) — the detector is purely dimensional and is a **no-op on square (256×256) volumes**, the standard brain-MRI matrix. Blind in the geometry it most needs to cover. Overlay-only, 2D-only. See CAPA-004 §2.3. |
| HAZ-006 | RC-013: NIfTI orientation validation on upload | Design control | REQ-SAFE-013 | `nifti_utils.py` load_nifti_from_bytes() validates file via nibabel | **NOT IMPLEMENTED** (2026-07-18) — overstated even as PARTIAL. `load_nifti_from_bytes()` checks size and parseability only; it never reads the affine. **No orientation logic exists anywhere in the product**, and there are no L/R laterality labels on any viewport. See CAPA-004 §2. |
| HAZ-007 | RC-014: Longitudinal comparison displays tri-color overlay (TP1/TP2/overlap) for visual verification | Information for safety | REQ-SAFE-014 | `SegmentationCanvasLocal.tsx` — longitudinal overlay renders blue (TP1), red (TP2), green (overlap) | **VERIFIED** (2026-07-18) — blue/red/green confirmed; the overlap branch is correctly tested first; bounds-guarded and fails closed on dimension mismatch. The one control found implemented exactly as written. Not bound to a test. |
| HAZ-007 | RC-014b: Longitudinal counts are UNADJUDICATED CANDIDATES (no spatial registration performed); the compare response carries `registration_verified=false`/`adjudication_required=true`/FP caveat, and `brain_report_service` labels them as candidates requiring review + instructs the generator NOT to assert them as DIT evidence. Non-comparable grids are refused (HTTP 400, `_require_comparable_grid`), never silently re-aligned. | Inherent safety (truthful framing) + information for safety | REQ-FUNC-055a | `segmentation_analysis.py` compare_longitudinal (candidate framing), `brain_report_service.py` (report firewall), `_require_comparable_grid` (A-3 refuse) | **IMPLEMENTED (2026-08-20)** — also fixed a latent defect: compare_timepoints was called without its required `voxel_spacing` arg → TypeError → 500 for every request; the "obvious" arg-only fix would have turned a dead endpoint into a live false-new-lesion→DIT path, which the candidate framing + report firewall now prevent. Adversarial-reviewed. |
| HAZ-008 | RC-015: DIS assessment displays per-region details with qualifying lesion counts | Information for safety | REQ-SAFE-015 | `LesionDashboard.tsx` DIS section with per-region presence indicators and counts | **PARTIAL** (2026-07-18) — implements 3 of 5 McDonald 2024 DIS regions, correctly and honestly disclosed in both payload and UI. However the **qualifying lesion counts are not displayed**: the field is returned and typed but read by no component. |
| HAZ-009 | RC-016: Patient name and MRN rendered in the image viewport itself | Information for safety | REQ-SAFE-016 | `ViewportSafetyOverlay.tsx`, rendered unconditionally by `ImageViewer2D.tsx`; `ImageMetadata.anatomical_orientation` from the backend | **VERIFIED — 2D ONLY** (2026-07-18) — bound to `frontend/src/components/ViewportSafetyOverlay.test.tsx`; three negative-control vectors (identity removed → 1 failed; overlay unwired → 1 failed; orientation warning silenced → 2 failed). Tests assert what is RENDERED, not what is passed. Implemented under CAPA-004 CA-4.2; the previous VERIFIED record was false — `patientName` was a dead prop and MRN appeared nowhere. **3D and multi-panel views remain unannotated** (CA-4.2 open). |
| HAZ-010 | RC-017: JWT authentication on ALL 103 API endpoints (100% coverage) with token expiry (1 hour) + WebAuthn/Passkeys | Design control | REQ-SEC-001 | `authentication.py` JWT creation with exp claim; `webauthn_service.py` FIDO2 flow; all route files import `get_current_active_user` | **VERIFIED — AUTHENTICATION ONLY** (2026-07-18) — `websocket.py::_authenticate_websocket`, bound to `tests/unit/test_rc017_websocket_auth.py`; two negative-control vectors. Implemented under CAPA-001 CA-2; the WebSocket transport was **entirely unauthenticated** when previously recorded as 100% coverage. **Object-level authorization is absent — see CAPA-002.** |
| HAZ-010 | RC-029: Object-level authorization on segmentation routes; create authorizes the target image; list is file-scoped | Design control | REQ-SEC-001 | `resource_access.py::resolve_segmentation_patient_id` + `segmentation.py` (12 object routes + create + list) | **VERIFIED** (2026-07-19) — bound to `tests/unit/test_rc029_segmentation_access.py`; 2 isolated negative-control vectors (resolver invents a patient -> 2 failed; unscoped non-admin listing -> 1 failed). **NEW control, CAPA-002 CA-2.1.** Resolves via the segmented image's patient-scoped file_id; non-patient file_ids fail closed. **Completes object-level authorization across all data surfaces (patient, imaging, study, document, segmentation).** |
| HAZ-010 | RC-028: Object-level authorization on study, series, instance and document routes; list routes are patient-scoped | Design control | REQ-SEC-001 | `resource_access.py` (resolve object -> patient_id, reuse RC-026) + `studies.py` (12 routes) + `documents.py` (6 routes) | **VERIFIED** (2026-07-19) — bound to `tests/unit/test_rc028_resource_access.py`; 3 isolated negative-control vectors (guard grants on unresolved patient -> 1 failed; resolver raises instead of None -> 2 failed; unscoped non-admin listing -> 1 failed). **NEW control, CAPA-002 CA-2.1.** Unresolved objects and unauthorized patients both return an identical 404. Segmentation objects and result-level list filtering remain open. |
| HAZ-010 | RC-027: Imaging storage references are parsed against a positive grammar and patient-authorized; raw client paths are never used as bucket keys | Design control (inherent safety, ISO 14971 §7.1) | REQ-SEC-001 | `storage_access.py::parse_patient_storage_ref` + `patient_access_dependency.py::authorize_storage_ref` + `imaging.py` (8 handlers) | **VERIFIED** (2026-07-19) — bound to `tests/unit/test_rc027_storage_access.py`; 3 negative-control vectors (prefix removed -> 1 failed; UUID check skipped -> 2 failed; object_path echoes raw -> 2 failed), each re-measured in isolation after a chained run gave a spurious pass. **NEW control, CAPA-002 CA-2.3.** Closes the imaging half of CAPA-002; studies/documents/segmentations remain open. |
| HAZ-010 | RC-025: Role-level authorization enforced on every patient-record route | Design control | REQ-SEC-002 | `models.py` (4 `PATIENT_*` permissions), `rbac.py` (role map), `patients.py` (10/10 routes) | **VERIFIED — ROLE LEVEL ONLY** (2026-07-18) — bound to `tests/unit/test_rc025_patient_authorization.py`; three negative-control vectors (route reverted to auth-only → 3 failed; VIEWER granted delete → 4 failed; `created_by` capture removed → 1 failed). **NEW control added by CAPA-004 CA-4.5.** Ten route docstrings previously promised `PATIENT_*` permissions that did not exist in the enum and were enforced nowhere. **Does NOT close CAPA-002**: object-level authorization is still absent — an authenticated VIEWER reaches every patient in the system. |
| HAZ-010 | RC-018: RBAC with 4 roles and 15 granular permissions | Design control | REQ-SEC-002 | `rbac.py` RBACManager with role hierarchy VIEWER→TECHNICIAN→RADIOLOGIST→ADMIN | **OVERSTATED** (2026-07-18) — the model is correct (4 roles, 15 permissions) but of **124 route decorators, 7 enforce a permission and 0 enforce a role**, all in `auth.py`. Every clinical route gates on authentication only; a VIEWER can delete studies and generate reports. 10 of 15 permissions are never checked. See CAPA-004 §4. |
| HAZ-011 | RC-019: DICOM-SEG generated with standard SOP Class UID and proper header | Design control | REQ-SAFE-017 | `dicom_utils.py` create_dicom_seg() — SOP Class UID 1.2.840.10008.5.1.4.1.1.66.4 | **PARTIAL** (2026-07-18) — code is correct (SOP Class UID set in both file meta and SOP Common). **The test count is false: there are 7, not 8**, with no parametrisation to expand it. |
| HAZ-012 | RC-020: DICOMweb import displays study/patient metadata for user confirmation before import | Design control | REQ-SAFE-018 | `PACSBrowserPage.tsx` — study search results show patient name, ID, modality before import | **VERIFIED** (2026-07-18) — source metadata is displayed before an explicit import action. **New finding**: the destination is a raw `prompt()` free-text patient ID with no validation and no display of the destination patient's name, so a typo files one patient's series into another's record. Not covered by any control. |
| HAZ-013 | RC-021: Report generation timeout (30s) with error message if API fails | Design control | REQ-SAFE-019 | `brain_report_service.py` — httpx client with configurable timeout; error caught and returned | **NOT IMPLEMENTED** (2026-07-18) — **no timeout exists anywhere** in the report path; there is no `CLAUDE_TIMEOUT` setting. The cited "httpx client" is not used (the Anthropic SDK is). Additionally the `async def` handler calls the **synchronous** client without a threadpool, so a hung upstream call blocks the whole worker. |
| HAZ-006 | RC-023: Anatomical orientation is determinable from the NIfTI affine, and is **never guessed** when indeterminate | Design control | REQ-SAFE-013 | `nifti_utils.py` — `get_orientation_codes()`, `is_orientation_determinate()`, `describe_orientation()`, `canonicalize_orientation()` | **VERIFIED** (2026-07-18) — bound to `tests/unit/test_rc023_orientation.py`; negative control: fixed-RAS return → 9 failed, canonicalisation neutralised → 2 failed. **NEW control added by CAPA-004 CA-4.1.** Provides the primitives only; canonicalisation is deliberately opt-in because image and mask load through separate calls and transforming one without the other would misalign them. Wiring it into the load path (RC-013) and rendering L/R viewport labels (CA-4.2) remain open. |
| HAZ-014 | RC-024: Voxel spacing is **required** for every quantitative measurement and is never assumed | Inherent safety (design) | REQ-SAFE-020 | `spacing_utils.py` — `resolve_voxel_spacing()` / `require_spacing()`; applied at 4 route sites; the 14 `= (1.0, 1.0, 1.0)` defaults removed from Class C service signatures | **VERIFIED** (2026-07-18) — bound to `tests/unit/test_rc024_voxel_spacing.py` (26 assertions); negative control: helper restores the 1 mm default → 17 failed; a route restores it → 1 failed. **NEW control added by CAPA-001 CA-5.** Refuses with HTTP 422 `VOXEL_SPACING_UNAVAILABLE` rather than measuring against an assumed geometry. |
| HAZ-014 | RC-022: All images preprocessed to MNI 1mm template before analysis (voxel spacing guaranteed 1mm isotropic) | Inherent safety (design) | REQ-SAFE-020 | Preprocessing pipeline produces MNI 1mm registered NIfTI files before segmentation | **NOT VERIFIED** (2026-07-18) — recollection is not objective evidence under ISO 14971. The code does not depend on the assumption: it silently defaults `voxel_spacing` to 1 mm, which is the harm HAZ-014 describes. Tracked as CAPA-001 CA-5. |

### 5.2 Post-Control Risk Assessment

| HAZ ID | Severity | Probability (post-control) | Residual Risk | Acceptable? |
|--------|----------|---------------------------|---------------|-------------|
| HAZ-001 | S5 | P1 (Improbable) — physician review mandatory | ALARP | Yes — benefit outweighs residual risk |
| HAZ-002 | S4 | ~~P1 — percentile display provides context~~ **WITHDRAWN 2026-07-18** — no percentile is ever computed or displayed (CAPA-005) | **UNDETERMINED** | **No — re-assessment required** |
| HAZ-003 | S5 | P1 — disclaimer now implemented and test-bound (RC-006, CAPA-001 CA-1). Note it was **absent** when this ALARP was first recorded. De-identification (RC-007′) still absent. | ALARP **pending CA-4** | Provisional |
| HAZ-004 | S5 | ~~P1 — disclaimer~~ **WITHDRAWN** — the Edge AI disclaimer renders only after a user click (CAPA-004 §4). Model-availability gating (RC-009) does hold. | **UNDETERMINED** | **No — re-assessment required** |
| HAZ-005 | S4 | ~~P2 — confidence scores~~ **WITHDRAWN** — the geometric path deliberately emits no confidence (RC-010). The control cannot discharge this hazard on that path. | **UNDETERMINED** | **No — re-assessment required** |
| HAZ-006 | S5 | ~~P1 — auto-transpose + orientation validation~~ **WITHDRAWN** — orientation validation does not exist; auto-transpose is a no-op on square volumes (CAPA-004 §2). | **UNDETERMINED** | **No — re-assessment required** |
| HAZ-007 | S4 | P2 — visual overlay enables verification | ACCEPTABLE | Yes |
| HAZ-008 | S4 | P2 — per-region presence displayed; **qualifying lesion counts are not** (RC-015) | ACCEPTABLE **pending** | Provisional |
| HAZ-009 | S5 | ~~P1 — prominent patient identification~~ **WITHDRAWN** — no patient identifier is rendered in the image viewport in any view mode; MRN is displayed nowhere (CAPA-004 §3). | **UNDETERMINED** | **No — re-assessment required** |
| HAZ-010 | S4 | ~~P1 — multi-factor auth + RBAC~~ **WITHDRAWN** — 7 of 124 routes enforce a permission, 0 enforce a role; there is no object-level authorization at all (CAPA-002, CAPA-004 §4). | **UNDETERMINED** | **No — re-assessment required** |
| HAZ-011 | S4 | P1 — standard DICOM format | ACCEPTABLE | Yes |
| HAZ-012 | S5 | P1 — user confirmation before import | ALARP | Yes |
| HAZ-013 | S3 | P2 — timeout handling + error message | ACCEPTABLE | Yes |
| HAZ-014 | S4 | P1 — MNI template preprocessing | ACCEPTABLE | Yes |

---

## 6. Overall Residual Risk Evaluation

### 6.1 Summary

After application of all risk control measures:

| Risk Level | Count | Percentage |
|-----------|-------|-----------|
| ACCEPTABLE | 8 | 57% |
| ALARP (benefit outweighs) | 6 | 43% |
| UNACCEPTABLE | 0 | 0% |

### 6.2 Benefit-Risk Analysis for ALARP Residual Risks

For the 6 hazards with ALARP residual risk (HAZ-001, HAZ-003, HAZ-004, HAZ-006, HAZ-009, HAZ-012), the benefit-risk analysis concludes:

**Benefits**:
- Faster MS lesion analysis (30 min → 5 min per study)
- Standardized MAGNIMS 2024 region classification
- Objective longitudinal tracking (eliminates inter-reader variability)
- Comprehensive quantitative volumetry
- AI-assisted structured reporting
- Alignment with latest McDonald 2024 diagnostic criteria

**Residual risks** are limited by:
- Mandatory physician review before any clinical action
- Prominent disclaimers on all AI-generated outputs
- Tool is assistive, never autonomous — clinician has full override
- Multiple independent risk controls per hazard (defense in depth)

**Conclusion**: The clinical benefits of MSTool-AI substantially outweigh the residual risks. All ALARP residual risks have been reduced as far as reasonably practicable through multiple layers of risk control.

### 6.3 Acceptability Statement

All identified risks have been evaluated and are either ACCEPTABLE or ALARP with documented benefit-risk justification. The overall residual risk of MSTool-AI is **ACCEPTABLE** per the risk acceptability criteria defined in Section 1.3.

---

## 7. Risk Management Report

### 7.1 Summary of Risk Management Activities

| Activity | Status | Evidence |
|----------|--------|----------|
| Risk Management Plan established | DONE | This document, Section 1 |
| Intended use defined | DONE | This document, Section 2 |
| Hazard identification (SFMEA) | DONE | This document, Section 3 (14 hazards) |
| Risk estimation | DONE | This document, Section 4 |
| Risk evaluation | DONE | This document, Section 4 |
| Risk control measures defined | DONE | This document, Section 5 (22 controls) |
| Risk control implementation | **NOT DONE** | **4/22 implemented as written** (RC-006, RC-009, RC-014, RC-017); 5 partial; 12 overstated or absent. Re-verified 2026-07-18 under CAPA-001 CA-3. |
| Risk control verification | **NOT DONE** | Only RC-006 and RC-017 are bound to automated tests. The remaining 20 rest on inspection, which CAPA-001 PA-1 records as insufficient. The 2026-04-12 verification record is **withdrawn**; see RCV-SUMMARY_2026-07-18. |
| Overall residual risk acceptable | **WITHDRAWN** | Section 6 rests on controls now known absent. HAZ-006's ALARP cites orientation validation that does not exist; HAZ-009's cites patient identification that is never rendered. Must be re-derived, not amended. |
| Post-production plan | DONE | This document, Section 8; SMP-001 |

### 7.2 Open Items

| Item | Action Required | Priority | Target Date |
|------|----------------|----------|-------------|
| RC-013 / laterality (CAPA-004) | Canonicalise orientation on load; render persistent L/R labels and patient identity in every viewport. **No orientation logic exists today.** | **CRITICAL** | Before any clinical use |
| Clinical expert review | Independent clinical review of risk analysis by board-certified neuroradiologist | HIGH | Before CE submission |
| Automated verification tests | Bind every risk control to a test whose removal turns CI red. 2 of 22 done (RC-006, RC-017). Manifest + CI gate in place (CAPA-001 PA-2). | **HIGH** | Per CAPA-001 |

---

## 8. Post-Production Monitoring

### 8.1 Monitoring Plan

| Activity | Frequency | Responsible | Method |
|----------|-----------|-------------|--------|
| User problem reports | Continuous | QA | GitHub Issues + structured form |
| SOUP vulnerability monitoring | Monthly | Development | npm audit + pip-audit + NVD review |
| AI model performance monitoring | Quarterly | Clinical + Dev | Performance metrics on new data |
| Risk file review | Annually or after significant change | Risk Management Authority | Formal review meeting |
| Regulatory landscape monitoring | Quarterly | Regulatory Affairs | MDCG guidance, standard updates |

### 8.2 Trigger for Risk File Update

The risk management file must be updated when:
- A new hazard is identified (from field use, literature, or similar devices)
- A significant software change is made
- A SOUP vulnerability is discovered that affects safety
- Regulatory requirements change
- Post-market surveillance data indicates a trend

---

## Addendum A — CALM-MS Conformal Second-Reader Hazards (INVESTIGATIONAL)

Traces to REQ-FUNC-CALM-001..006. The feature is gated OFF (`CALM_MS_RESEARCH_ENABLED`)
and investigational; these hazards were derived from a 4-angle adversarial design
review (Class C/regulatory, clinical-UX, SOTA, engineering/security). Each has an
IMPLEMENTED design-level risk control; residual acceptability is **PENDING** the
listed V&V (mimic-cohort validation + summative usability study) before any clinical
enablement.

| Hazard | Failure mode | Harm | Risk control (implemented) | V&V still required |
|---|---|---|---|---|
| HAZ-CALM-1 | Sensitivity-spending suppression drops a true lesion from the mask/counts → missed lesion → wrong DMT / missed diagnosis | Serious | RC-CALM-1: feature is ADDITIVE-only (`conformal_review` never mutates the base mask; returns all candidates); downstream reads the full mask (REQ-FUNC-CALM-002) | Verify no downstream (DIS/volumetry/report) consumes a filtered mask |
| HAZ-CALM-2 | Per-lesion "confidence %" read as P(lesion real) → over/under-trust | Serious | RC-CALM-2: no probability/confidence surfaced; ordinal tier only (REQ-FUNC-CALM-003); enforced by test | IEC 62366-1 summative usability study |
| HAZ-CALM-3 | Per-scan FDR number read as this-scan precision (guarantee is marginal) | Serious | RC-CALM-3: only the preset α (input target) returned, labelled population-level scope; no realized-FDP; enforced by test | Summative usability study proving no per-scan inference |
| HAZ-CALM-4 | Free α/threshold → un-validated operating point (PCCP violation) | Serious | RC-CALM-4: preset enum only; server maps to frozen (α, threshold); raw values rejected | Per-preset clinical validation + PCCP change-control plan |
| HAZ-CALM-5 | Probability map from a different base model/grid/regime scored against the FLAMeS null → mathematically VOID guarantee shown | Serious | RC-CALM-5: (a) provenance stamp + `assert_compatible` fail-closed grid/spacing refusal; (b) **gross-marginal-shift backstop** (`conformal_ood.assess_ood`) — flags a gross shift of the mixed candidate-score marginal and WITHHOLDS the guarantee (`guarantee_applicable=False`, WITHHELD_SCOPE), fail-closed on no/malformed reference and non-finite scores. **NECESSARY, NOT SUFFICIENT** (see residual below): it cannot detect the label-conditional false-positive shift that actually breaks the guarantee | **BLOCKING for clinical enablement:** class-conditional null re-estimation on a per-site labelled slice (or covariate/embedding-space check); base-model stamp on prob maps; validate on real scanner-shift + mimic cohorts |
| HAZ-CALM-6 | Missing/empty/degenerate null asset or unauthenticated access → void guarantee / PHI exposure | Serious | RC-CALM-6: fail-closed asset load (`ConformalAssetError`) on missing/empty **and now on wrong `base_model` value or degenerate (low-dispersion) null**; endpoint behind auth + object-level PHI authz | Integration tests for the endpoint auth + asset-missing paths |
| HAZ-CALM-7 | Non-finite (NaN/inf) or out-of-range probability voxel bypasses the input gate (min/max propagate NaN) → guarantee served on a corrupt/failed-inference map | Serious | RC-CALM-7: explicit `np.isfinite` rejection added in `conformal_review`, `extract_lesion_candidates`, and `conformal_pvalues` (found & fixed in adversarial verification 2026-08-17) | — (covered by regression tests) |
| HAZ-CALM-8 | A TRUE lesion de-prioritized to a low tier → a hurried reader treats the ordinal tier as a filter and skips a real lesion | Serious | RC-CALM-1 (ADDITIVE): the full base mask is always shown; tiers are review-PRIORITY ordering, never inclusion/exclusion — nothing is hidden or removed. The UI must present tiers as priority, never as a filter | IEC 62366-1 summative usability study must verify low-tier lesions are still reviewed (surfaced by the 2026-08-21 adversarial design review) |

### Adversarial verification (2026-08-17)

Five adversarial agents wrote and executed probes against the conformal components.
**Confirmed sound:** the core lesion-FDR control holds empirically (E[FDP] ≤ preset α)
in every in-distribution regime including high-count clustered dependence (PRDS
holds; BH step-up 0/20000 mismatches vs reference); no labeling-hazard leak on the
served path; `status_mask` integrity; presets-only. **Fixed:** the non-finite input
fail-open (HAZ-CALM-7), the unvalidated `base_model` value and degenerate-null gaps
(HAZ-CALM-6). **Residual, documented limitation (feature stays dark):** the
grid/spacing check (RC-CALM-5) is necessary but **not sufficient** for
exchangeability — an on-grid out-of-distribution map cannot be detected from
geometry alone and empirically voids the guarantee (realized FDR up to ~8× target).
A v1 OOD monitor (`conformal_ood.assess_ood`) was added to withhold the guarantee on
gross candidate-score-distribution shift, with a Mahalanobis statistic and a threshold
(5.0) set from a validation sweep. **It is retained ONLY as a gross-marginal-shift
disclosure backstop.**

### Adversarial verification — round 2 (2026-08-17): the OOD monitor is necessary, not sufficient

A second, deeper adversarial round (4 agents: statistical-methodology, conformal-theory,
code-correctness, evasion) ran runnable probes against the OOD monitor and the guarantee.
Its central result **downgrades the claim above** and is recorded honestly here because,
for a Class C device, an overstated safety claim is itself the hazard:

- **CRITICAL (2 independent confirmations) — the monitor audits the wrong distribution.**
  It summarises the MIXED (true+false) candidate-score marginal, but the conformal FDR
  guarantee depends on the FALSE-candidate scores being exchangeable with the frozen null
  — a *label-conditional* property the marginal is blind to (a label-shift, not a
  covariate-shift; Podkopaev & Ramdas 2021). Confirmed with the real code + asset: a case
  whose 5-number summary sits *inside* the calibration envelope (Mahalanobis ≈ 0.75–3.1,
  more "in-distribution" than the median legit case) realises **FDP up to 1.0** — the
  monitor fails OPEN exactly where it must fail closed, and this false-positive-inflation
  regime is the clinically *likely* scanner shift, not a contrived one. **No label-free
  score statistic can close this**; it needs class-conditional null re-estimation on a
  per-site labelled slice, or a covariate/embedding-space check (weighted / Mondrian
  conformal — Tibshirani 2019; conformal-OOD on embeddings — Bates 2023). **This blocks
  clinical enablement.**
- **HIGH — frozen-null resolution overstated ~10×.** The 1,390 nulls are 145 scan clusters
  (~9.6 each); the honest p-value resolution and conditional-FDR band scale with the
  *cluster* count (~145), not 1,390. The advertised `1/1391` is corrected to ~`1/n_clusters`.
- **MEDIUM — within-scan dependence.** BH still controls the *marginal* FDR under the
  positive dependence (PRDS holds — the "needs Benjamini–Yekutieli" worry was *refuted* by
  simulation), but the per-scan FDP disperses: P(FDP > α) ≈ 25% at α=0.30. The marginal
  guarantee is honest but the *per-scan* experience a clinician reads is not controlled;
  disclosed, not hidden.
- **MEDIUM — v1 statistic weaknesses.** `n_candidates` (a skewed count) forced into a
  Gaussian ellipsoid preferentially flags high-burden (sickest) patients; the 5 moments are
  blind to shape/count evasions a full-distribution KS/energy/MMD test would catch; the
  reported "~2% false-OOD" is an in-sample point estimate (held-out p90 ≈ 7%). Planned v2:
  a KS two-sample test on the full candidate-score distribution (upgrades the backstop but
  does **not** address the CRITICAL label-shift above).

**Fixed this round:** the non-finite-score fail-open and malformed-reference crash in
`assess_ood` (now fail-closed, regression-tested); the per-lesion `confidence = 1 - p`
field removed from the inference layer (RC-CALM-2 hardening).

**Bottom line:** the feature stays DARK (investigational). The lesion-FDR core is sound
*when its exchangeability premise holds*; the premise cannot be certified at inference by
any score-only monitor, so clinical enablement is gated on class-conditional / site-level
recalibration, a base-model-bound probability producer, and the IEC 62366-1 summative
usability study (SRS Addendum A).

### F1 fix investigation (2026-08-18): site recalibration is necessary but NOT sufficient

The proposed F1 fix — site-conditional (Mondrian) recalibration of the null — was tested
on real data (`scripts/calm-ms/site_recalibration_experiment.py`, record
`assets/site_recalibration_record.json`; write-up `docs/calm-ms/F1-site-shift-investigation.md`).
Findings: (a) real cross-site FP shift exists (KS D=0.150, p=4.7e-4) but is mild between the
two academic cohorts, so the pooled null stays near target there; (b) a **severe confident-FP
shift** (a scanner emitting confident false positives) voids the pooled guarantee (realized
FDR 0.43–0.63, up to ~6× target) and the OOD monitor is blind to it (0/115 flagged) —
confirming F1 with a realistic construction; (c) **site-conditional recalibration does not
rescue it**: it restores a valid null but power collapses (1 of 2692 true lesions recovered),
because when FPs are as confident as TPs the raw-probability score is anti-informative. **The
true F1 fix is two-part: a scanner-robust LEARNED lesion score (TP/FP separability beyond raw
probability — the CALM-MS v2 scorer, now shown load-bearing, not optional) PLUS cluster-aware
site-conditional calibration.** Clinical enablement is gated on BOTH, validated on real
mimic/scanner-shift cohorts. This is a scoping result, recorded honestly: it delimits what the
conformal layer alone can deliver under acquisition shift.

**v2 learned scorer — claim CORRECTED after adversarial round 3 (2026-08-18)**
(`scripts/calm-ms/evaluate_lesion_scorer.py` [authoritative], record `assets/lesion_scorer_record.json`,
write-up `docs/calm-ms/v2-learned-scorer-result.md`). An earlier entry claimed the learned score
"survives the F1 shift where raw probability collapses" and was "F1 fix part 1, validated". **That is
RETRACTED.** Two independent adversarial audits (reproduced) found the load-bearing test was RIGGED
(it inflated only the FALSE candidates' probability features — physically impossible — and was
constructed to invert raw probability) and was run on a gradient-boosting model, not the shipped
logistic regression. Honest result on the shipped model: the learned score is a real WITHIN-DOMAIN
improvement (patient-grouped AUC 0.796 vs 0.701 raw, ECE 0.032, no overfit, location/morphology are
legitimate signal), but it does NOT solve cross-site non-exchangeability (pooled leave-one-site-out
AUC 0.624), its within-domain conformal power is modest (~0.47 of true lesions at α=0.20), and under
a FAIR monotone shift it does NOT beat raw probability (AUC 0.663 vs 0.736). **Neither a better null
nor a better score alone is the F1 fix** — that requires domain-conditional calibration + cross-site
score harmonisation + ≥3–5 sites, on real cohorts. Also fixed this round: two scorer fail-opens (an
empty-coefficient asset scored every lesion as a constant; non-integer powers were silently
truncated) — both now fail closed with regression tests. The scorer is NOT wired to the guarantee
and must not be until the above holds.

*End of Risk Management File*

*This document is maintained under configuration management. The latest version is always the one in the Git repository at `docs/iec62304/03_Risk_Management_File.md`.*
