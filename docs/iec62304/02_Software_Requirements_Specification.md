# MSTool-AI: Software Requirements Specification

## IEC 62304 Clause 5.2 Compliant Requirements Document

**Document ID**: SRS-001
**Version**: 1.0
**Effective Date**: April 12, 2026
**Standard**: IEC 62304:2006+A1:2015 Clause 5.2
**Software Safety Class**: IEC 62304 Class C
**Confidentiality**: Restricted — Regulatory Audit Use Only

---

## Document Control

| Version | Date | Author | Changes | Approved By |
|---------|------|--------|---------|-------------|
| 1.0 | 2026-04-12 | Development Team | Initial release | — |

---

## 1. Introduction

### 1.1 Purpose

This Software Requirements Specification (SRS) defines the functional, performance, safety, security, and interface requirements for MSTool-AI. Each requirement is uniquely identified, traceable to risk analysis (RMF-001) and system-level needs, and verifiable through defined test methods.

### 1.2 Scope

This SRS covers all software requirements for MSTool-AI version 2.0, including frontend (React/TypeScript), backend (FastAPI/Python), and external service integrations (Vertex AI, Claude API, DICOMweb).

### 1.3 Definitions

| Term | Definition |
|------|-----------|
| Shall | Mandatory requirement |
| Should | Recommended but not mandatory |
| May | Optional |
| User | Any authenticated user of the system |
| Clinician | Physician using the system for clinical decisions |
| Administrator | User with ADMIN role |

---

## 2. Functional Requirements

### 2.1 Medical Image Loading and Display

| ID | Requirement | Priority | Safety Class | Verification | Risk Ref |
|----|-------------|----------|-------------|-------------|----------|
| REQ-FUNC-001 | The system shall load NIfTI (.nii, .nii.gz) files and display them as navigable 2D slices. | Must | B | Test | — |
| REQ-FUNC-002 | The system shall load DICOM files and display them as navigable 2D slices. | Must | B | Test | — |
| REQ-FUNC-003 | The system shall provide 3D volume rendering of loaded NIfTI files using WebGL2. | Must | B | Test | — |
| REQ-FUNC-004 | The system shall provide multiplanar reconstruction (axial, coronal, sagittal) with synchronized crosshairs. | Must | B | Test | — |
| REQ-FUNC-005 | The system shall support windowing (brightness/contrast) adjustment for 2D slices. | Must | B | Test | — |
| REQ-FUNC-005a | The system shall provide true DICOM window/level (VOI-LUT applied to raw stored intensities server-side, not a cosmetic post-render filter) for 2D slices, seeded from the per-series DICOM WindowCenter/WindowWidth tag with a reset to full-range auto. This is display-fidelity for lesion conspicuity (esp. FLAIR); it operates on the same slice grid the segmentation overlay uses and does not alter mask geometry. | Must | B | Test | HAZ-001 |
| REQ-FUNC-006 | The system shall support zoom (0.25x to 20x) and pan in 2D view. | Should | A | Test | — |
| REQ-FUNC-007 | The system shall provide a clip plane tool for 3D volume slicing with axial/coronal/sagittal options. | Should | B | Test | — |
| REQ-FUNC-008 | The system shall support multiple colormaps (Gray, Hot, Bone, Viridis, Inferno, etc.). | Should | A | Test | — |
| REQ-FUNC-009 | The system shall detect MRI sequence type from BIDS filename (FLAIR, T1, T2, PD). | Should | A | Test | — |
| REQ-FUNC-010 | The system shall display patient name, MRN, and study information in the viewer header. | Must | B | Test | HAZ-009 |

### 2.2 Segmentation

| ID | Requirement | Priority | Safety Class | Verification | Risk Ref |
|----|-------------|----------|-------------|-------------|----------|
| REQ-FUNC-020 | The system shall provide brush painting tools (circle/square) with configurable size (1-50 voxels). | Must | B | Test | — |
| REQ-FUNC-021 | The system shall provide an eraser tool that sets voxels to background (label 0). | Must | B | Test | — |
| REQ-FUNC-022 | The system shall provide flood fill (BFS, 4-connectivity) and threshold-based region growing. | Should | B | Test | — |
| REQ-FUNC-023 | The system shall support undo/redo for segmentation operations with slice-level snapshots. | Must | B | Test | — |
| REQ-FUNC-024 | The system shall store segmentation masks as 3D Uint8Array in browser memory (local-first architecture). | Must | B | Test | — |
| REQ-FUNC-025 | The system shall save segmentation masks to server storage on explicit user action only. | Must | B | Test | — |
| REQ-FUNC-026 | The system shall support two label presets: Default (4 labels) and MAGNIMS Regional (6 labels). | Must | B | Test | — |
| REQ-FUNC-027 | The system shall allow per-label visibility toggling in both viewing and editing modes. | Should | A | Test | — |
| REQ-FUNC-028 | The system shall support overlay rendering with configurable opacity (0-100%). | Should | A | Test | — |

### 2.3 AI Segmentation

| ID | Requirement | Priority | Safety Class | Verification | Risk Ref |
|----|-------------|----------|-------------|-------------|----------|
| REQ-FUNC-030 | The system shall provide automatic brain parcellation via SynthSeg on Vertex AI. | Must | C | Test | HAZ-001 |
| REQ-FUNC-031 | The system shall provide interactive click-based segmentation (positive/negative points). | Should | C | Test | HAZ-001 |
| REQ-FUNC-032 | The system shall display AI segmentation results as an overlay on the medical image. | Must | C | Test | HAZ-001 |
| REQ-FUNC-033 | The system shall provide edge AI screening via ONNX Runtime Web in browser. | Should | C | Test | HAZ-004 |
| REQ-FUNC-034 | The system shall provide automatic MS-lesion segmentation from a single FLAIR volume using an externally-validated deep-learning model (FLAMeS, nnU-Net v2, Dataset004_WML), executed on an isolated GPU inference worker. | Should | C | Test | HAZ-001 |
| REQ-FUNC-035 | An auto-segmentation result shall be stored and surfaced as a reviewable DRAFT that is additive (it shall never overwrite or hide a clinician's own segmentation), shall record its provenance (model, version, citation, `validation_source`), and shall carry the "assistive — requires physician review" risk control (RC-001). | Must | C | Test + usability | HAZ-001 |
| REQ-FUNC-036 | The auto-segmentation feature shall fail closed: it shall be selectable only when its inference worker is configured and reported available, and an all-zero (empty) result shall be recorded with its annotated-voxel count so a true negative is distinguishable from a silent model/worker failure. | Must | C | Test | HAZ-001 |

### 2.4 Brain Volumetry

| ID | Requirement | Priority | Safety Class | Verification | Risk Ref |
|----|-------------|----------|-------------|-------------|----------|
| REQ-FUNC-040 | The system shall compute volumes (mm³ and mL) for each segmented brain structure. | Must | C | Test | HAZ-002 |
| REQ-FUNC-041 | The system shall compute normative percentiles using z-score against age-matched reference distributions. | Must | C | Test | HAZ-002 |
| REQ-FUNC-042 | The system shall flag structures with percentile < 10 (atrophy) or > 90 (enlargement). | Must | C | Test | HAZ-002 |

### 2.5 MS-Specific Analysis

| ID | Requirement | Priority | Safety Class | Verification | Risk Ref |
|----|-------------|----------|-------------|-------------|----------|
| REQ-FUNC-050 | The system shall perform connected component analysis to identify individual lesions. | Must | C | Test | HAZ-005 |
| REQ-FUNC-051 | The system shall compute per-lesion volume, centroid, and bounding box. | Must | C | Test | — |
| REQ-FUNC-052 | The system shall evaluate McDonald 2024 DIS criteria across PV, JC, IT regions. | Must | C | Test | HAZ-008 |
| REQ-FUNC-053 | The system shall classify lesions into MAGNIMS regions using SynthSeg parcellation + EDT (Tier 2) with MSMask atlas fallback (Tier 1). | Must | C | Test | HAZ-005 |
| REQ-FUNC-054 | The system shall provide longitudinal tracking with IoU-based lesion matching (threshold >= 0.3). | Must | C | Test | HAZ-007 |
| REQ-FUNC-055 | The system shall classify longitudinal lesion status: NEW, RESOLVED, ENLARGED (>20%), SHRUNK (<-20%), STABLE. | Must | C | Test | HAZ-007 |
| REQ-FUNC-055a | Longitudinal new/enlarging counts shall be presented as UNADJUDICATED CANDIDATES, not confirmed findings: the comparison performs NO spatial registration (equal array shape is not voxel alignment), so the response shall carry `registration_verified=false` + `adjudication_required=true` + a false-positive caveat, and reports shall label them as candidates requiring radiologist review and shall NOT assert them as dissemination-in-time (DIT) evidence without reader adjudication. The comparison shall refuse (HTTP 400) non-comparable grids rather than silently re-aligning them. | Must | C | Test | HAZ-007 |
| REQ-FUNC-056 | The system shall display longitudinal comparison as tri-color overlay (blue=TP1, red=TP2, green=overlap). | Must | B | Test | — |

### 2.6 AI Report Generation

| ID | Requirement | Priority | Safety Class | Verification | Risk Ref |
|----|-------------|----------|-------------|-------------|----------|
| REQ-FUNC-060 | The system shall generate structured clinical reports using the Claude API. | Must | C | Test | HAZ-003 |
| REQ-FUNC-061 | The system shall support report templates: General MS, Activity, Lesion Burden, Comprehensive, Longitudinal. | Must | C | Test | — |
| REQ-FUNC-062 | The system shall generate reports in English, Spanish, and German. | Should | A | Test | — |
| REQ-FUNC-063 | The system shall integrate volumetry, DIS assessment, and longitudinal data into report prompts. | Must | C | Test | HAZ-003 |

### 2.7 Hospital Integration

| ID | Requirement | Priority | Safety Class | Verification | Risk Ref |
|----|-------------|----------|-------------|-------------|----------|
| REQ-FUNC-070 | The system shall support QIDO-RS queries to search studies on remote PACS. | Must | B | Test | — |
| REQ-FUNC-071 | The system shall support WADO-RS retrieval of DICOM series from PACS with automatic DICOM-to-NIfTI conversion. | Must | B | Test | HAZ-012 |
| REQ-FUNC-072 | The system shall export segmentation masks as DICOM-SEG (SOP Class 1.2.840.10008.5.1.4.1.1.66.4). | Must | B | Test | HAZ-011 |
| REQ-FUNC-073 | The system shall generate HL7 FHIR R4 ImagingStudy, DiagnosticReport, and Patient resources. | Should | B | Test | — |

### 2.8 Patient and Study Management

| ID | Requirement | Priority | Safety Class | Verification | Risk Ref |
|----|-------------|----------|-------------|-------------|----------|
| REQ-FUNC-080 | The system shall support patient CRUD operations with demographic data. | Must | A | Test | — |
| REQ-FUNC-081 | The system shall organize studies by patient with timepoint timeline. | Must | A | Test | — |
| REQ-FUNC-082 | The system shall support NIfTI and DICOM file upload with SHA-256 checksum verification. | Must | B | Test | — |

### 2.9 Measurement Tools

| ID | Requirement | Priority | Safety Class | Verification | Risk Ref |
|----|-------------|----------|-------------|-------------|----------|
| REQ-FUNC-090 | The system shall provide a ruler tool measuring distance in millimeters. | Should | B | Test | — |
| REQ-FUNC-091 | The system shall provide an angle measurement tool (3-point, degrees). | Should | B | Test | — |
| REQ-FUNC-092 | The system shall provide an elliptical ROI tool measuring area in mm². | Should | B | Test | — |

---

## 3. Safety Requirements

*Derived from Risk Management File (RMF-001)*

| ID | Requirement | Risk Ref | Priority | Verification |
|----|-------------|----------|----------|-------------|
| REQ-SAFE-001 | All AI-generated segmentation results shall be labeled "Assistive tool — requires physician review". | HAZ-001 | Must | Test + Inspection |
| REQ-SAFE-002 | AI results shall be presented in read-only Viewing mode; clinician must explicitly switch to Edit mode to modify. | HAZ-001 | Must | Test |
| REQ-SAFE-003 | Manual segmentation tools shall always be available as override to any AI result. | HAZ-001 | Must | Test |
| REQ-SAFE-004 | Volumetry results shall display normative percentile range with reference distribution source. | HAZ-002 | Must | Test |
| REQ-SAFE-005 | Abnormality flags shall display the threshold criteria used (percentile < 10 or > 90). | HAZ-002 | Must | Test |
| REQ-SAFE-006 | AI-generated reports shall include header: "AI-Generated — Requires Physician Review Before Clinical Action". | HAZ-003 | Must | Test + Inspection |
| REQ-SAFE-007 | AI reports shall not be auto-committed to clinical record; clinician confirmation required for any export. | HAZ-003 | Must | Test |
| REQ-SAFE-008 | Edge AI screening badge shall display confidence percentage and "assistive tool only, not diagnostic" disclaimer. | HAZ-004 | Must | Test + Inspection |
| REQ-SAFE-009 | Edge AI screening shall be hidden when model file is not available (graceful degradation). | HAZ-004 | Must | Test |
| REQ-SAFE-010 | MAGNIMS classification shall display per-lesion confidence scores. | HAZ-005 | Must | Test |
| REQ-SAFE-011 | Classification method (EDT/Atlas/Geometric) shall be displayed to the user. | HAZ-005 | Should | Inspection |
| REQ-SAFE-012 | The system shall auto-detect and transpose axis mismatches between mask and image dimensions. | HAZ-006 | Must | Test |
| REQ-SAFE-013 | The system shall validate NIfTI orientation headers on file upload and warn if non-standard. | HAZ-006 | Must | Test |
| REQ-SAFE-014 | Longitudinal comparison shall display tri-color overlay for visual verification of lesion matching. | HAZ-007 | Must | Test |
| REQ-SAFE-015 | DIS assessment shall display per-region detail with qualifying lesion counts. | HAZ-008 | Must | Test |
| REQ-SAFE-016 | Patient name and MRN shall be prominently displayed in the viewer header at all times. | HAZ-009 | Must | Inspection |
| REQ-SAFE-017 | DICOM-SEG export shall use standard SOP Class UID and proper DICOM header structure. | HAZ-011 | Must | Test |
| REQ-SAFE-018 | DICOMweb import shall display study/patient metadata for user confirmation before import. | HAZ-012 | Must | Test |
| REQ-SAFE-019 | Report generation shall timeout after 30 seconds with user-visible error message if API fails. | HAZ-013 | Must | Test |
| REQ-SAFE-020 | All images shall be preprocessed to MNI 1mm isotropic template before quantitative analysis. | HAZ-014 | Must | Inspection |

---

## 4. Security Requirements

*Per IEC 62304 Amendment 1 (2015)*

| ID | Requirement | Priority | Verification |
|----|-------------|----------|-------------|
| REQ-SEC-001 | All API communications shall use TLS 1.2 or higher. | Must | Test |
| REQ-SEC-002 | Authentication shall be required for all non-public endpoints. | Must | Test |
| REQ-SEC-003 | JWT access tokens shall expire within 60 minutes. | Must | Test |
| REQ-SEC-004 | The system shall support WebAuthn/Passkeys (FIDO2) for biometric authentication. | Should | Test |
| REQ-SEC-005 | The system shall implement RBAC with 4 roles (Viewer, Technician, Radiologist, Admin) and 19 permissions (incl. 4 patient-record permissions added under CAPA-004 CA-4.5). | Must | Test |
| REQ-SEC-006 | Patient data shall be encrypted at rest using AES-256-GCM. | Must | Inspection |
| REQ-SEC-007 | No PHI (patient name, DOB, MRN) shall be transmitted to external AI APIs (Claude, Vertex AI). | Must | Test + Inspection |
| REQ-SEC-008 | The system shall enforce rate limiting (100 requests/minute per IP) on all API endpoints. | Must | Test |
| REQ-SEC-009 | The system shall log all data access events with user ID, action, resource, and timestamp. | Must | Inspection |
| REQ-SEC-010 | Secrets (API keys, JWT signing keys) shall not be stored in version control. | Must | Inspection |
| REQ-SEC-011 | Password policy shall enforce minimum 12 characters with uppercase, lowercase, digit, and special character. | Must | Test |
| REQ-SEC-012 | Account shall lock after 5 consecutive failed login attempts for 30 minutes. | Must | Test |
| REQ-SEC-013 | DICOM/NIfTI file parsing shall validate input headers and reject malformed files. | Must | Test |
| REQ-SEC-014 | The system shall enforce **object-level authorization** on every data-returning endpoint: a user may access a patient's records — and the imaging, study, series, instance, document and segmentation objects belonging to that patient — only if the user is an administrator or holds an active care-team assignment to that patient. Authentication and role permission alone shall not grant access to a specific patient's data. | Must | Test | HAZ-010 |
| REQ-SEC-015 | Denial of object-level access shall be **indistinguishable from non-existence**: the system shall respond with HTTP 404 and an identical response body whether the requested object does not exist or the caller is not entitled to it, so that object and patient identifiers cannot be enumerated. The true reason shall be recorded only in the server-side audit log. | Must | Test | HAZ-010 |
| REQ-SEC-016 | The system shall not accept a **raw storage path** as caller input for retrieving patient data. Imaging references shall be parsed against a fixed grammar and re-authorized to their owning patient; the storage key used shall be reconstructed server-side from validated components, never echoed from client input. | Must | Test | HAZ-010 |
| REQ-SEC-017 | The system shall record the **creating user (provenance)** on every patient record at creation. Provenance shall not be inferred or backfilled. | Must | Test | HAZ-010 |
| REQ-SEC-018 | Patient records lacking provenance and any care-team assignment (e.g. records created before REQ-SEC-017 was enforced) shall be **quarantined**: accessible only to an administrator for explicit triage, never auto-attributed to any user. | Must | Test | HAZ-010 |

**Note on REQ-SEC-014…018 (added 2026-07-19 under CAPA-002 CA-2.2).** These
requirements did not exist in the 2026-04-12 baseline. CAPA-002 found that the
software authenticated callers and checked roles but never verified that a caller
was entitled to a *specific* patient's data — a requirements gap that manifested
as OWASP API1:2023 (Broken Object Level Authorization). The requirements are
recorded here because the controls that satisfy them (RC-026 patient, RC-027
imaging, RC-028 study/document, RC-029 segmentation) were implemented ahead of the
specification, and a control without a stated requirement is not traceable under
IEC 62304 §5.2. The entitlement model chosen is **care-team assignment** (explicit
user↔patient links), decided by the product owner; alternatives (creator-scoped,
institution/tenant, role-graded) are recorded in CAPA-002 §8.4.

---

## 5. Performance Requirements

| ID | Requirement | Priority | Verification |
|----|-------------|----------|-------------|
| REQ-PERF-001 | 2D slice rendering shall complete within 500ms after data is loaded. | Must | Test |
| REQ-PERF-002 | 3D volume rendering shall initialize within 5 seconds for a standard brain MRI (~27MB NIfTI). | Must | Test |
| REQ-PERF-003 | Segmentation painting shall respond within 16ms (60fps) for brush strokes. | Must | Test |
| REQ-PERF-004 | API responses shall return within 3 seconds for standard operations. | Must | Test |
| REQ-PERF-005 | AI report generation shall complete within 30 seconds. | Must | Test |
| REQ-PERF-006 | The system shall support at least 10 concurrent users. | Should | Test |
| REQ-PERF-007 | DICOMweb import of a single MRI series shall complete within 5 minutes. | Should | Test |

---

## 6. Interface Requirements

### 6.1 User Interface

| ID | Requirement | Priority | Verification |
|----|-------------|----------|-------------|
| REQ-UI-001 | The system shall be accessible via modern web browsers (Chrome, Firefox, Edge — last 2 versions). | Must | Test |
| REQ-UI-002 | The system shall provide internationalization in English, Spanish, and German. | Must | Test |
| REQ-UI-003 | The system shall be responsive across desktop screen sizes (minimum 1280x720). | Should | Test |
| REQ-UI-004 | The system shall support dark mode (default) and light mode with persistent preference. | Should | Test |

### 6.2 External System Interfaces

| ID | Requirement | Priority | Verification |
|----|-------------|----------|-------------|
| REQ-IF-001 | The system shall interface with hospital PACS via DICOMweb (QIDO-RS, WADO-RS). | Must | Test |
| REQ-IF-002 | The system shall generate HL7 FHIR R4 resources (ImagingStudy, DiagnosticReport, Patient). | Should | Test |
| REQ-IF-003 | The system shall interface with Vertex AI for AI segmentation inference. | Must | Test |
| REQ-IF-004 | The system shall interface with Anthropic Claude API for report generation. | Must | Test |
| REQ-IF-005 | The system shall store data in Google Cloud Firestore and Google Cloud Storage. | Must | Inspection |

---

## 7. Data Requirements

| ID | Requirement | Priority | Verification |
|----|-------------|----------|-------------|
| REQ-DATA-001 | The system shall support NIfTI-1 format (.nii, .nii.gz) for medical image storage. | Must | Test |
| REQ-DATA-002 | The system shall support DICOM format for medical image import. | Must | Test |
| REQ-DATA-003 | Segmentation masks shall be stored as 3D Uint8Array with label values 0-255. | Must | Inspection |
| REQ-DATA-004 | Patient records shall include: name, MRN, date of birth, gender, contact information. | Must | Inspection |
| REQ-DATA-005 | Segmentation metadata shall include: labels (id, name, color), creation date, description. | Must | Inspection |

---

## 8. Regulatory Requirements

| ID | Requirement | Priority | Verification |
|----|-------------|----------|-------------|
| REQ-REG-001 | The system shall comply with EU MDR 2017/745 Annex I General Safety and Performance Requirements. | Must | Analysis |
| REQ-REG-002 | The system shall comply with GDPR requirements for medical data processing. | Must | Analysis |
| REQ-REG-003 | The system shall comply with IEC 62304:2006+A1:2015 Class C software lifecycle requirements. | Must | Analysis |
| REQ-REG-004 | The system shall comply with ISO 14971:2019 risk management requirements. | Must | Analysis |
| REQ-REG-005 | The system shall comply with EU AI Act high-risk AI requirements (when applicable). | Should | Analysis |

---

## 9. Requirements Summary

| Category | Count |
|----------|-------|
| Functional Requirements (REQ-FUNC) | 32 |
| Safety Requirements (REQ-SAFE) | 20 |
| Security Requirements (REQ-SEC) | 13 |
| Performance Requirements (REQ-PERF) | 7 |
| Interface Requirements (REQ-UI + REQ-IF) | 9 |
| Data Requirements (REQ-DATA) | 5 |
| Regulatory Requirements (REQ-REG) | 5 |
| **Total** | **91** |

| Priority | Count | Percentage |
|----------|-------|-----------|
| Must | 72 | 79% |
| Should | 19 | 21% |

| Safety Class | Count |
|-------------|-------|
| Class C | 25 |
| Class B | 38 |
| Class A | 9 |
| N/A (safety/security/performance) | 19 |

---

## 10. Requirements Verification Cross-Reference

*Full traceability to tests will be documented in the Traceability Matrix (TM-001).*

| Verification Method | Count | Description |
|-------------------|-------|-------------|
| Test | 72 | Verified by automated or manual test |
| Inspection | 12 | Verified by code/document review |
| Analysis | 5 | Verified by regulatory analysis |
| Demonstration | 2 | Verified by user demonstration |

---

## Addendum A — CALM-MS Conformal Second-Reader (INVESTIGATIONAL)

**Status:** Investigational / research-only. Gated behind `CALM_MS_RESEARCH_ENABLED`
(default OFF). NOT cleared for clinical use; full V&V (intended-use / mimic-cohort
validation, IEC 62366-1 summative usability study, per-preset validation, PCCP) is
pending. Requirements below define the safe behaviour the feature MUST exhibit even
in the investigational state.

| ID | Requirement | Priority | Class | Verification | Hazard |
|---|---|---|---|---|---|
| REQ-FUNC-CALM-001 | The system shall annotate lesion candidates from a probabilistic MS segmenter with a distribution-free, **population-level** lesion false-discovery-rate control (conformal p-values + Benjamini-Hochberg), exposing an ordinal per-lesion **review-priority tier** (high/medium/low). | Should | C | Test | HAZ-CALM-1..6 |
| REQ-FUNC-CALM-002 | The feature shall be **additive**: it shall never remove, hide, or alter the base segmenter's lesion mask, and all downstream consumers (volumetry, DIS/MAGNIMS, reports) shall continue to read the full base mask. | Must | C | Test | HAZ-CALM-1 |
| REQ-FUNC-CALM-003 | The system shall NOT present a per-lesion probability or "confidence" percentage, and shall NOT present a per-scan realized FDR; it shall present only the ordinal tier and the preset's target α, labelled as population-level scope. | Must | C | Test + usability | HAZ-CALM-2, HAZ-CALM-3 |
| REQ-FUNC-CALM-004 | The system shall accept only a **validated preset** (high_sensitivity[default]/balanced/high_precision), each mapped server-side to a frozen (α, threshold); it shall reject raw α/threshold. | Must | C | Test | HAZ-CALM-4 |
| REQ-FUNC-CALM-005 | The system shall **fail closed on exchangeability**: it shall refuse (4xx) any probability map whose base-model/grid/spacing does not match the frozen calibration null asset's provenance stamp. | Must | C | Test | HAZ-CALM-5 |
| REQ-FUNC-CALM-006 | The system shall fail closed if the calibration null asset is missing or empty (no void guarantee shall be served), and shall enforce authentication + object-level PHI authorization on the endpoint. | Must | C | Test | HAZ-CALM-6 |
| REQ-FUNC-CALM-007 | The system shall accept a probability map only from a producer that stamps `base_model=FLAMeS` + grid provenance the endpoint verifies; bring-your-own-prob is research-only and shall not be enabled clinically (closes the "non-FLAMeS map on the right grid" hole). | Must | C | Test | HAZ-CALM-5 |
| REQ-FUNC-CALM-008 | Every enabled preset's α shall satisfy α ≥ 1/(n_scans+1) of the shipped null (heuristic effective resolution, scan-clustered); the build shall reject any preset finer than the calibration can resolve. | Should | C | Test | HAZ-CALM-4 |
| REQ-FUNC-CALM-009 | The population-level scope text shall state that validity assumes cross-site exchangeability of the **false-candidate** distribution, which is not certified at inference (the OOD monitor sees only the mixed marginal). | Must | C | Test + usability | HAZ-CALM-5 |
| REQ-FUNC-CALM-010 | The feature shall remain disabled (`CALM_MS_RESEARCH_ENABLED=false`) until every gate in the V&V dossier (`docs/calm-ms/vv_gate_status.json`) is `pass`; a CI test shall fail the build if the flag is enabled while any gate is not green. | Must | C | Test | HAZ-CALM-1..8 |

*End of Software Requirements Specification*

*This document is maintained under configuration management. The latest version is always the one in the Git repository at `docs/iec62304/02_Software_Requirements_Specification.md`.*
