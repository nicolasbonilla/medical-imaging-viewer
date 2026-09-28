# MSTool-AI: Requirements Traceability Matrix

## IEC 62304 Clause 5.1.1(e) — Bidirectional Traceability

**Document ID**: TM-001 | **Version**: 1.1 | **Date**: September 28, 2026 (v1.0: April 12, 2026)

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0 | 2026-04-12 | Development Team | Initial release |
| 1.1 | 2026-09-28 | Development Team | CAPA-006 (HAZ-005). (a) REQ-FUNC-053 row corrected in place. It was "MAGNIMS classification", tested by UT-CLS-001 only. It now reflects the corrected SRS text: contact criterion, four paths, MNI-only atlas. It adds UT-CLS-002/003 and UI-RC032, and the architecture reference, which was "SAD 3.5", a section that does not exist. (b) Addendum added for REQ-SAFE-021 → RC-032 and for the CAPA-006 PA-6.1 labelling gate. (c) REQ-SAFE-020 / RC-022 row: "VERIFIED (code inspection)" struck through. It is NOT IMPLEMENTED / NOT VERIFIED: no MNI preprocessing or registration to a template exists in the code. (d) New tests added to the backward and unit-test traceability tables. The 2026-09-28 RC-010 addendum below was entered without a version change; it is covered by this version |

---

## Forward Traceability: Requirement → Design → Code → Test

| Req ID | Requirement | Arch (SAD) | Design (DD) | Code Module | Unit Test | Integration Test | System Test | Risk Ref |
|--------|-------------|-----------|-------------|-------------|-----------|-----------------|------------|----------|
| REQ-FUNC-001 | Load NIfTI files | SAD 3.1 | — | `imaging_service.py` | — | IT-API-001 | ST-FUNC-001 | — |
| REQ-FUNC-002 | Load DICOM files | SAD 3.1 | — | `imaging_service.py` | — | IT-API-001 | ST-FUNC-002 | — |
| REQ-FUNC-003 | 3D volume rendering | SAD 3.1 | — | `ImageViewer3D.tsx` | — | — | ST-FUNC-003 | — |
| REQ-FUNC-010 | Display patient info | SAD 3.1 | — | `ViewerApp.tsx` | — | — | ST-FUNC-010 | HAZ-009 |
| REQ-FUNC-030 | Auto brain parcellation | SAD 3.3 | DD-AI-001 | `ai_segmentation_service.py` | UT-AI-001 | IT-AI-001 | ST-FUNC-030 | HAZ-001 |
| REQ-FUNC-033 | Edge AI screening | SAD 3.3 | DD-EDGE-001/002/003 | `edgeAI.worker.ts` | UT-EDGE-001 | — | ST-FUNC-033 | HAZ-004 |
| REQ-FUNC-040 | Compute volumes | SAD 3.4 | DD-VOL-001 | `brain_volumetry_service.py` | UT-VOL-001 | IT-VOL-001 | ST-FUNC-040 | HAZ-002 |
| REQ-FUNC-041 | Normative percentiles | SAD 3.4 | DD-VOL-001 | `brain_volumetry_service.py` | UT-VOL-002 | — | ST-FUNC-041 | HAZ-002 |
| REQ-FUNC-042 | Abnormality flags | SAD 3.4 | DD-VOL-001 | `brain_volumetry_service.py` | UT-VOL-003 | — | ST-FUNC-042 | HAZ-002 |
| REQ-FUNC-050 | Connected component analysis | SAD 3.5 | DD-LES-001 | `lesion_analysis_service.py` | UT-LES-001 | IT-LES-001 | ST-FUNC-050 | HAZ-005 |
| REQ-FUNC-052 | McDonald 2024 DIS | SAD 3.5 | DD-LES-002 | `lesion_analysis_service.py` | UT-DIS-001 | — | ST-FUNC-052 | HAZ-008 |
| REQ-FUNC-053 | MAGNIMS classification by the contact criterion via four paths (LST-AI zones, parcellation + EDT <= 1.5 mm, MSMask atlas on MNI-space images only, geometric fallback); path reported *(corrected 2026-09-28, CAPA-006; was "MAGNIMS classification", SAD 3.5, UT-CLS-001 only)* | SAD 3.2 (BE-CLS) | DD-CLS-001 | `ms_region_classifier.py`, `segmentation_regions.py` | UT-CLS-001, UT-CLS-002, UT-CLS-003, UI-RC032 | IT-CLS-001 | ST-FUNC-053 | HAZ-005 (RC-010 (amended), RC-032) |
| REQ-FUNC-054 | Longitudinal tracking | SAD 3.5 | — | `longitudinal_tracking_service.py` | UT-LONG-001 | IT-LONG-001 | ST-FUNC-054 | HAZ-007 |
| REQ-FUNC-060 | AI report generation | SAD 3.6 | DD-RPT-001 | `brain_report_service.py` | UT-RPT-001 | IT-RPT-001 | ST-FUNC-060 | HAZ-003 |
| REQ-FUNC-070 | QIDO-RS search | SAD 3.7 | — | `dicomweb_service.py` | — | IT-PACS-001 | ST-FUNC-070 | — |
| REQ-FUNC-071 | WADO-RS import | SAD 3.7 | — | `dicomweb_service.py` | — | IT-PACS-002 | ST-FUNC-071 | HAZ-012 |
| REQ-FUNC-072 | DICOM-SEG export | SAD 3.7 | — | `dicom_utils.py` | UT-SEG-001 | — | ST-FUNC-072 | HAZ-011 |
| REQ-FUNC-073 | FHIR resources | SAD 3.7 | — | `fhir.py` | — | IT-FHIR-001 | ST-FUNC-073 | — |

---

## Safety Requirements Traceability

> ## ⚠️ VERIFICATION STATUS IN THIS TABLE IS WITHDRAWN — 2026-07-18/19
>
> The "VERIFIED (code inspection)" entries below were **not updated** when the
> Risk Management File's verification column was corrected under CAPA-001 CA-3.
> Adversarial re-verification found **4 of 22 controls verified, 12 overstated or
> absent** — for example RC-001, RC-004, RC-005, RC-016 and RC-022 are **not
> implemented as described**, and RC-007's row here (`no auto-commit`) does not
> match the RCV-SUMMARY's RC-007 (`de-identification`, also absent).
>
> **Do not rely on the "Verified?" column below.** The authoritative status is
> [`RCV-SUMMARY_2026-07-18.md`](records/risk_verification/RCV-SUMMARY_2026-07-18.md)
> and the RMF §5.1 verification column. This table's rows are retained unedited as
> evidence of the same records-disagreement documented in CAPA-001; per-row
> correction is tracked there.

| Req ID | Safety Requirement | Risk Control | HAZ ID | Design (DD) | Implementation | Test ID | Verified? |
|--------|-------------------|-------------|--------|-------------|----------------|---------|-----------|
| REQ-SAFE-001 | AI disclaimer label | RC-001 | HAZ-001 | DD-AI-001 | `QuickScreenBadge.tsx` | TST-SAFE-001 | VERIFIED (code inspection) |
| REQ-SAFE-002 | Viewing/Edit mode separation | RC-002 | HAZ-001 | DD-AI-001 | `ViewerApp.tsx` | TST-SAFE-002 | VERIFIED (code inspection) |
| REQ-SAFE-003 | Manual override available | RC-003 | HAZ-001 | DD-AI-001 | `SegmentationPanel.tsx` | TST-SAFE-003 | VERIFIED (code inspection) |
| REQ-SAFE-004 | Volumetry percentile display | RC-004 | HAZ-002 | DD-VOL-001 | `BrainVolumetryPanel.tsx` | TST-SAFE-004 | VERIFIED (code inspection) |
| REQ-SAFE-005 | Abnormality threshold display | RC-005 | HAZ-002 | DD-VOL-001 | `BrainVolumetryPanel.tsx` | TST-SAFE-005 | VERIFIED (code inspection) |
| REQ-SAFE-006 | Report disclaimer header | RC-006 | HAZ-003 | DD-RPT-001 | `brain_report_service.py` | TST-SAFE-006 | VERIFIED (code inspection) |
| REQ-SAFE-007 | Report no auto-commit | RC-007 | HAZ-003 | DD-RPT-001 | `AIReportPanel.tsx` | TST-SAFE-007 | VERIFIED (code inspection) |
| REQ-SAFE-008 | Edge AI confidence + disclaimer | RC-008 | HAZ-004 | DD-EDGE-003 | `QuickScreenBadge.tsx` | TST-SAFE-008 | VERIFIED (code inspection) |
| REQ-SAFE-009 | Edge AI hidden when no model | RC-009 | HAZ-004 | DD-EDGE-002 | `useEdgeAI.ts` | TST-SAFE-009 | VERIFIED (code inspection) |
| REQ-SAFE-010 | Classification confidence scores | RC-010 | HAZ-005 | DD-CLS-001 | `LesionDashboard.tsx` | TST-SAFE-010 | VERIFIED (code inspection) |
| REQ-SAFE-012 | Auto-transpose axis mismatch | RC-012 | HAZ-006 | DD-NII-002 | `SegmentationCanvasLocal.tsx` | TST-SAFE-012 | VERIFIED (code inspection) |
| REQ-SAFE-014 | Longitudinal tri-color overlay | RC-014 | HAZ-007 | — | `LongitudinalCompare.tsx` | TST-SAFE-014 | VERIFIED (code inspection) |
| REQ-SAFE-015 | DIS per-region details | RC-015 | HAZ-008 | DD-LES-002 | `LesionDashboard.tsx` | TST-SAFE-015 | VERIFIED (code inspection) |
| REQ-SAFE-016 | Patient ID prominent | RC-016 | HAZ-009 | — | `ViewerApp.tsx` | TST-SAFE-016 | VERIFIED (code inspection) |
| REQ-SAFE-018 | DICOMweb import confirmation | RC-020 | HAZ-012 | — | `PACSBrowserPage.tsx` | TST-SAFE-018 | VERIFIED (code inspection) |
| REQ-SAFE-020 | MNI 1mm template preprocessing | RC-022 | HAZ-014 | — | ~~Preprocessing pipeline~~ none: no MNI preprocessing or template registration exists | TST-SAFE-020 | ~~VERIFIED (code inspection)~~ **NOT IMPLEMENTED / NOT VERIFIED** (2026-09-28, CAPA-006; see addendum below) |

> **Note**: The original claim "All safety requirements verified by code
> inspection per RMF-001 (April 2026)" is **withdrawn** — see the banner above.
> Code inspection recorded as prose, with no executed check, is precisely the
> nonconformity CAPA-001 was raised for.

> **Addendum 2026-09-28: REQ-SAFE-010 amended (audit #8, HAZ-005).** The REQ-SAFE-010 row above ("Classification confidence scores") is kept unedited as history but is **superseded**. Problems with the original control have been found:
> - the parcellation path produced its "confidence" by mapping distance linearly onto 0.70–0.95 (0.60–0.90 for DWM);
> - the MSMask path reported the in-zone fraction as its "confidence", and used a fixed 0.50 for lesions outside every zone.
>
> None of these values was calibrated. The amended control, RC-010 (amended), removes per-lesion confidence from every classification path, from the API, from MCP and from the UI, and shows each path's own evidence instead. It is bound to executed tests:
>
> | Req ID | Safety Requirement | Risk Control | HAZ ID | Design (DD) | Implementation | Test ID | Verified? |
> |--------|-------------------|-------------|--------|-------------|----------------|---------|-----------|
> | REQ-SAFE-010 (amended 2026-09-28) | Region evidence displayed; never a per-lesion confidence | RC-010 (amended) | HAZ-005 | DD-CLS-001 | `ms_region_classifier.py`, `region_evidence.py`, `LesionDashboard.tsx`, `utils/regionEvidence.ts`, `mcp/ms_clinical_server.py` | UT-CLS-002, UI-RC010 | TEST-BOUND (neg. control UT-CLS-002: 2/5, 1/6, 1/6, 1/6; UI-RC010: 1/6, 1/6) |
>
> This control provides information for safety only. The accuracy of region assignment has **not** been measured against expert region labels on any path, so the **HAZ-005 residual risk is UNDETERMINED** and must be re-assessed (RMF-001).

> **Addendum 2026-09-28: REQ-SAFE-021 added, RC-032 (CAPA-006, HAZ-005).** Each MAGNIMS classification path is valid only under a precondition, and none of them was enforced:
> - the MNI152 MSMask atlas was applied to any image, with no registration;
> - the atlas zone map was combined with the lesion mask in a different axis order, and a persisted zone map came back transposed after a reload;
> - a MAGNIMS zone map was accepted as a FreeSurfer parcellation;
> - the geometric heuristics received the image in the wrong axis order and never checked the slice direction;
> - the region routes resolved voxel spacing from metadata that never carries it (HTTP 500).
>
> RC-032 makes every precondition checkable and fails closed. It is bound to executed tests:
>
> | Req ID | Safety Requirement | Risk Control | HAZ ID | Design (DD) | Implementation | Test ID | Verified? |
> |--------|-------------------|-------------|--------|-------------|----------------|---------|-----------|
> | REQ-SAFE-021 (added 2026-09-28) | Each region-classification path only under its precondition: atlas only on MNI-like grids; FreeSurfer parcellation check; geometric preconditions; zone map in the lesion mask's axis order, generated fresh, shape-checked; spacing from the source image; 422 with reasons when no path applies | RC-032 | HAZ-005 | DD-CLS-001 | `ms_region_classifier.py` (`looks_mni`, `NotMNISpaceError`, `looks_like_freesurfer_parcellation`, `prepare_geometric_image`, `GeometricPreconditionError`, shape checks), `segmentation_regions.py` (classify-regions, generate-zone-map), `LesionDashboard.tsx` (amber atlas-unavailable and geometric alerts) | UT-CLS-003 (`backend/tests/unit/test_rc032_region_atlas_guard.py`, 23 `test_rc032_*`), UI-RC032 (`frontend/src/components/LesionDashboard.rc032.test.ts`, 4 `rc032`) | TEST-BOUND (negative controls executed: `docs/iec62304/records/risk_verification/RC-032_negative_controls_2026-09-28.json`) |
> | CAPA-006 PA-6.1 (preventive) | The MAGNIMS method in the labelling and design documents is bound to the code: IFU §10.3 states each `*_DISTANCE_THRESHOLD_MM` and the MNI requirement. Withdrawn 3/4/3 mm values, a "two-tier" cascade and unsupported accuracy/validation claims appear only next to a CAPA-006 note | — (preventive action for HAZ-005 labelling) | HAZ-005 | DD-CLS-001 | IFU-001, AIA-001, CER-001, GSPR-001, SRS-001, SAD-001, DD-001, UEF-001, master and technical documents, README, Class C code comments | UT-LBL-001 (`backend/tests/unit/test_capa006_labelling_bound_to_code.py`, 48 tests) | TEST-BOUND (negative controls executed: same record, section PA-6.1) |
>
> RC-032 does not establish region-assignment accuracy, and the grid gate cannot certify true normalisation. The **HAZ-005 residual risk remains UNDETERMINED** (RMF-001).
>
> **REQ-SAFE-020 / RC-022 (HAZ-014)**: the row in the table above said "VERIFIED (code inspection)". It is struck through in place. Nothing in the code preprocesses images to the MNI 1 mm template or registers them to it; the only registration is longitudinal, intra-subject and rigid. Images are therefore **not** in MNI space by construction, which is why RC-032 must gate the MNI-space atlas. RMF-001 already records RC-022 as NOT VERIFIED (2026-07-18).

---

## Security Requirements Traceability — Object-Level Authorization (CAPA-002)

Added 2026-07-19. Unlike the safety table above, every row here is bound to an
automated test whose removal turns CI red (the standard CAPA-001 established), and
each carries a recorded negative-control result. "Verified?" here means
*test-bound and negative-control-checked*, not *inspected*.

| Req ID | Requirement | Risk Control | HAZ ID | Implementation | Test | Verified? |
|--------|-------------|-------------|--------|----------------|------|-----------|
| REQ-SEC-014 | Object-level authorization (care-team) | RC-026 | HAZ-010 | `patient_access.py`, `patient_access_dependency.py`, `care_team_service.py` | `test_rc026_patient_access.py`, `test_rc026_access_enforcement.py` | TEST-BOUND (neg. control 7/2/1/7 + 1/7/1) |
| REQ-SEC-016 | No raw storage paths; parse + re-authorize | RC-027 | HAZ-010 | `storage_access.py`, `imaging.py` (8 routes) | `test_rc027_storage_access.py` | TEST-BOUND (neg. control 1/2/2) |
| REQ-SEC-014 | Object-level authz — study/series/instance/document | RC-028 | HAZ-010 | `resource_access.py`, `studies.py` (12), `documents.py` (6) | `test_rc028_resource_access.py` | TEST-BOUND (neg. control 1/2/1) |
| REQ-SEC-014 | Object-level authz — segmentation | RC-029 | HAZ-010 | `resource_access.py`, `segmentation.py` (12+2) | `test_rc029_segmentation_access.py` | TEST-BOUND (neg. control 2/1) |
| REQ-SEC-015 | Enumeration defence (404 not 403) | RC-026/027/028/029 | HAZ-010 | identical-404 in every guard | assertions in each test above | TEST-BOUND |
| REQ-SEC-017 | Provenance capture (created_by) | RC-025 | HAZ-010 | `patients.py` create route | `test_rc025_patient_authorization.py` | TEST-BOUND (neg. control 1) |
| REQ-SEC-018 | Quarantine of unattributable records | RC-026 | HAZ-010 | `patient_access.py` (DENIED_QUARANTINED) | `test_rc026_patient_access.py` | TEST-BOUND |

The full binding is machine-checked in
[`rc_test_manifest.json`](records/risk_verification/rc_test_manifest.json), enforced
by `backend/tests/unit/test_risk_control_manifest.py`.

---

## Backward Traceability: Test → Requirement

| Test ID | Test Description | Requirements Verified |
|---------|-----------------|---------------------|
| IT-AUTH-001 | Login returns valid JWT | REQ-SEC-002, REQ-SEC-003 |
| IT-AUTH-002 | Protected endpoint requires token | REQ-SEC-002 |
| IT-AUTH-003 | WebAuthn register/begin returns challenge | REQ-SEC-004 |
| IT-PACS-001 | DICOMweb connections CRUD | REQ-FUNC-070 |
| IT-FHIR-001 | FHIR DiagnosticReport structure | REQ-FUNC-073 |
| UT-SEG-001 | DICOM-SEG creation (single label) | REQ-FUNC-072 |
| UT-SEG-002 | DICOM-SEG creation (multi label) | REQ-FUNC-072 |
| UT-SEG-003 | DICOM-SEG creation (empty mask) | REQ-FUNC-072 |
| UT-CLS-002 | No classification path emits a per-lesion confidence; evidence fields are honest (distances None when a landmark is absent, full-lesion overlap denominator, default-DWM flagged); MCP strips persisted confidence; region thresholds unchanged (added 2026-09-28) | REQ-SAFE-010 (amended), REQ-FUNC-053 |
| UI-RC010 | LesionDashboard shows in-zone evidence and a default-DWM warning, never a confidence cell or average confidence; stale confidence values are ignored (added 2026-09-28) | REQ-SAFE-010 (amended) |
| UT-CLS-003 | RC-032 path preconditions (23 `test_rc032_*`, added 2026-09-28). MNI gate accepts MNI grids and rejects oblique, clinical and previously accepted grids. Atlas zone map matches the orientation-consistent reference, including on a cubic grid; a zone map of another grid is refused. Region routes alive with spacing from the source image. `msmask` off-MNI → 422; `auto` → fallback with reason. Persisted zone map never reused. generate-zone-map refuses non-MNI images and keeps existing zone maps. A zone map is neither read nor accepted as a parcellation. Geometric path uses the brain outline and refuses sagittal, reversed, mismatched or blank images | REQ-SAFE-021, REQ-FUNC-053 (RC-032, HAZ-005) |
| UI-RC032 | LesionDashboard shows an amber alert whenever `atlas_unavailable_reason` is present, translated in every shipped locale and naming MNI space. Geometric regions always carry a least-accurate warning. The panel no longer promises SynthSeg or a "best" automatic method (4 `rc032`, added 2026-09-28) | REQ-SAFE-021, REQ-FUNC-053 (RC-032) |
| UT-LBL-001 | CAPA-006 PA-6.1 labelling gate (48 tests, added 2026-09-28). IFU §10.3 states each `*_DISTANCE_THRESHOLD_MM` and the MNI requirement. Withdrawn 3/4/3 mm values, a "two-tier" cascade and unsupported accuracy/validation claims appear only next to a CAPA-006 note in 15 listed documents and Class C source files. A missing listed file fails | REQ-FUNC-053, REQ-SAFE-021 (CAPA-006 PA-6.1) |

---

## Traceability Completeness Summary

| Chain | Total Links | Complete | Incomplete | Percentage |
|-------|-----------|----------|------------|-----------|
| Requirement → Architecture | 91 | 91 | 0 | 100% |
| Requirement → Design (Class C) | 25 | 25 | 0 | 100% |
| Requirement → Code | 91 | 91 | 0 | 100% |
| Requirement → Test | 91 | 38 | 53 | **42%** |
| Safety Req → Risk Control | 20 | 20 | 0 | 100% |
| Risk Control → Verification | 22 | 21 | 1 | **95%** |

**Key Gap**: 53 requirements lack formal test traceability. 1 risk control lacks verification evidence. Unit tests for Class C services significantly improved coverage (April 2026). dicom_utils tests added ~4 additional requirements covered.

---

## Unit Test Traceability (Class C Services)

| Test File | Test IDs | Requirements Covered |
|-----------|---------|---------------------|
| `test_ai_segmentation_service.py` | UT-AI-001 | REQ-FUNC-030 |
| `test_brain_volumetry_service.py` | UT-VOL-001..003 | REQ-FUNC-040, REQ-FUNC-041, REQ-FUNC-042 |
| `test_brain_report_service.py` | UT-RPT-001 | REQ-FUNC-060 |
| `test_lesion_analysis_service.py` | UT-LES-001, UT-DIS-001 | REQ-FUNC-050, REQ-FUNC-052 |
| `test_ms_region_classifier.py` | UT-CLS-001 | REQ-FUNC-053 |
| `test_region_confidence_haz005.py` | UT-CLS-002 | REQ-SAFE-010 (amended 2026-09-28), REQ-FUNC-053 (RC-010 (amended), HAZ-005) |
| `test_rc032_region_atlas_guard.py` | UT-CLS-003 | REQ-SAFE-021, REQ-FUNC-053 (RC-032, HAZ-005; added 2026-09-28) |
| `test_capa006_labelling_bound_to_code.py` | UT-LBL-001 | REQ-FUNC-053, REQ-SAFE-021 (CAPA-006 PA-6.1; added 2026-09-28) |
| `test_nifti_utils.py` | UT-NII-001 | REQ-FUNC-001 |
| `test_dicom_seg.py` | UT-SEG-001..008 | REQ-FUNC-072 |
| `test_dicom_utils.py` | UT-DICOM-001..007 | REQ-FUNC-072, REQ-SAFE-013 | RC-016 | VERIFIED |

---

*This matrix must be updated with each requirement change, design change, or new test.*
