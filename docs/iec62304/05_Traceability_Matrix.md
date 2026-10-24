# MSTool-AI: Requirements Traceability Matrix

## IEC 62304 Clause 5.1.1(e) — Bidirectional Traceability

**Document ID**: TM-001 | **Version**: 1.10 DRAFT (2026-10-24 — CAPA-014: REQ-SEC-021..023 → RC-064..RC-066, updated after the second review; PENDING owner approval) — last approved: 1.9 (versions 1.4 to 1.9 approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63), merged to `main` with PR #64) | **Date**: October 24, 2026 (v1.6 to v1.9: October 17–22, 2026; v1.2 to v1.5: October 17, 2026; v1.1: September 28, 2026; v1.0: April 12, 2026)

| Version | Date | Author | Change | Approved By |
|---------|------|--------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | Initial release | — |
| 1.1 | 2026-09-28 | Development Team | CAPA-006 (HAZ-005). (a) REQ-FUNC-053 row corrected in place. It was "MAGNIMS classification", tested by UT-CLS-001 only. It now reflects the corrected SRS text: contact criterion, four paths, MNI-only atlas. It adds UT-CLS-002/003 and UI-RC032, and the architecture reference, which was "SAD 3.5", a section that does not exist. (b) Addendum added for REQ-SAFE-021 → RC-032 and for the CAPA-006 PA-6.1 labelling gate. (c) REQ-SAFE-020 / RC-022 row: "VERIFIED (code inspection)" struck through. It is NOT IMPLEMENTED / NOT VERIFIED: no MNI preprocessing or registration to a template exists in the code. (d) New tests added to the backward and unit-test traceability tables. The 2026-09-28 RC-010 addendum below was entered without a version change; it is covered by this version | N. G. Bonilla Vargas — approved 2026-10-17 (PR #43) |
| 1.2 | 2026-10-17 | Development Team | CAPA-008: REQ-SAFE-022/023/024 → RC-033/034/035 → UT-CAPA008, UT-LONG-RULES (addendum below; test rows added) | N. G. Bonilla Vargas — approved 2026-10-17 (PR #46) |
| 1.3 | 2026-10-17 | Development Team | CAPA-009: REQ-SEC-014/015/016/019/020 → RC-036 → UT-CAPA009 | N. G. Bonilla Vargas — approved 2026-10-17 (PR #47) |
| 1.4 | 2026-10-17 | Development Team | CAPA-010: REQ-SAFE-016 (amended), REQ-SAFE-025/026/027 → RC-016, RC-023, RC-037, RC-038 → UI-CAPA010-3D, UI-CAPA010-MPV, UI-CAPA010-APP, UI-RC038 (addendum below; test rows added) | N. G. Bonilla Vargas — approved 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
| 1.5 | 2026-10-17 | Development Team | CAPA-011: REQ-SAFE-028 → RC-039 → UT-RC039 (addendum below; test rows added) | approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
| 1.6 (draft) | 2026-10-17/18 | Development Team | CP-FLAMES-BROWSER-001 (in-browser FLAMeS, flag OFF). Re-review 2 (2026-10-18): REQ-SAFE-030 / RC-047 and REQ-SAFE-033 / RC-049 rows updated; UI-FLAMES-BANNER added. Original entry: REQ-FUNC-034/036 (amended), REQ-FUNC-093..097, REQ-SAFE-029..033 → RC-040..RC-051 (RC-052/053 not implemented) → UT-FLAMES-*, UI-FLAMES-*, UT-RC047, VAL-FLAMES-* (addendum below; test rows added). Versions 1.4 and 1.5 are reserved by open PRs #52 and #51 | N. G. Bonilla Vargas — approved 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
| 1.7 (draft) | 2026-10-21 | Development Team | CP-SLICE-THICKNESS-001 (reliability by slice thickness, flag OFF): REQ-FUNC-098/099, REQ-SAFE-034/035/036 → RC-054..RC-058 → UT-RC054, UT-STC-LOGIC, UI-STC-CARD, UT-STC-FLAG (addendum below; test rows added). Versions 1.4, 1.5 and 1.6 are reserved by open PRs #52, #51 and #53. Amended 2026-10-23 after the independent review of PR #59: RC-054 row and UT-RC054 (spacing without thickness); RC-056/RC-057 rows, UT-STC-LOGIC and UI-STC-CARD (evidence asset v2, pre-registered bands only) | N. G. Bonilla Vargas — approved 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
| 1.8 (draft) | 2026-10-22 | Development Team | RMF-OBS-001 and PRB-001: REQ-FUNC-053 row annotated with the known nonconformity of the MSMask and LST-AI zones paths (PRB-001 → RC-059, proposed); REQ-FUNC-054 row annotated (RMF-OBS-001); REQ-SAFE-037 (proposed) → RC-060, RC-061, RC-062 (proposed); RC-059..RC-062 NOT IMPLEMENTED, no test (addendum below). Version 1.7 is reserved by open PR #59 | N. G. Bonilla Vargas — approved 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
| 1.9 (draft) | 2026-10-22 | Development Team | CAPA-013: REQ-SAFE-037 → RC-060/RC-061/RC-062 implemented on branch → UT-CAPA013, UI-CAPA013 (addendum below supersedes the three REQ-SAFE-037 rows of the 1.8 addendum; test rows added; REQ-FUNC-054 row annotated). Versions 1.4 to 1.8 are held by open PRs #52, #51, #53, #59 and #62 | N. G. Bonilla Vargas — approved 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
| 1.10 (draft) | 2026-10-24 | Development Team | CAPA-014 (redesigned after the review of PR #67): REQ-SEC-021/022/023 → RC-064/RC-065/RC-066 (HAZ-016) → UT-CAPA014, UI-CAPA014, UT-CAPA009 (route classified) (security addendum and test rows below). Header line corrected: on `main` it still read "1.9 DRAFT … merge after … — last approved: 1.3", although versions 1.4 to 1.9 were approved on 2026-10-23 and merged with PR #64 (approval entries of those rows unchanged). Updated after the second independent review (N1–N10): UT-CAPA014 220 cases, UI-CAPA014 11 cases, negative controls 73 mutations. Version 1.11 is reserved by the parallel CAPA-015 PR | PENDING owner approval |

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
| REQ-FUNC-053 | MAGNIMS classification by the contact criterion via four paths (LST-AI zones, parcellation + EDT <= 1.5 mm, MSMask atlas on MNI-space images only, geometric fallback); path reported *(corrected 2026-09-28, CAPA-006; was "MAGNIMS classification", SAD 3.5, UT-CLS-001 only)* | SAD 3.2 (BE-CLS) | DD-CLS-001 | `ms_region_classifier.py`, `segmentation_regions.py` | UT-CLS-001, UT-CLS-002, UT-CLS-003, UI-RC032, UT-LBL-001 | IT-CLS-001 | ST-FUNC-053 | HAZ-005 (RC-010 (amended), RC-032). *Known nonconformity (2026-10-22, draft): the MSMask path, and the LST-AI zones path by inheritance, use the third ventricle as a PV landmark — PRB-001, RC-059 proposed, NOT IMPLEMENTED, no test* |
| REQ-FUNC-054 | Longitudinal tracking | SAD 3.5 | — | `longitudinal_tracking_service.py` | UT-LONG-001 | IT-LONG-001 | ST-FUNC-054 | HAZ-007 *(2026-10-22, draft: RMF-OBS-001 — on automatic masks >= 1 false new/enlarging candidate in 20/20 patients against expert change masks, about 9 per patient; REQ-SAFE-037, RC-060..RC-062 proposed; implemented on branch by CAPA-013, UT-CAPA013, UI-CAPA013 — approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63))* |
| REQ-FUNC-060 | AI report generation | SAD 3.6 | DD-RPT-001 | `brain_report_service.py` | UT-RPT-001 | IT-RPT-001 | ST-FUNC-060 | HAZ-003 |
| REQ-FUNC-070 | QIDO-RS search | SAD 3.7 | — | `dicomweb_service.py` | — | IT-PACS-001 | ST-FUNC-070 | — |
| REQ-FUNC-071 | WADO-RS import | SAD 3.7 | — | `dicomweb_service.py` | — | IT-PACS-002 | ST-FUNC-071 | HAZ-012 |
| REQ-FUNC-072 | DICOM-SEG export | SAD 3.7 | — | `dicom_utils.py` | UT-SEG-001 | — | ST-FUNC-072 | HAZ-011 |
| REQ-FUNC-073 | FHIR resources | SAD 3.7 | — | `fhir.py` | — | IT-FHIR-001 | ST-FUNC-073 | — |
| REQ-FUNC-034 (amended, draft) | FLAMeS auto-segmentation: GPU worker (not deployed) or in-browser (flag OFF) | — | DESIGN.md (flames-in-browser) | `tool_runner_service.py`; `services/flames/*`, `flamesInBrowser.worker.ts` | UT-FLAMES-PORT | — | VAL-FLAMES-PARITY | HAZ-001 |
| REQ-FUNC-036 (amended, draft) | Fail closed; empty result explicit (browser: warning + acknowledgement) | — | DESIGN.md §8 | `BrowserFlamesCard.tsx`, `draft.ts` | UI-FLAMES-CARD | — | — | HAZ-001 (RC-051) |
| REQ-FUNC-093 (draft) | FLAMeS computed in the browser (flag OFF) | — | DESIGN.md §2 | `services/flames/*`, `flamesInBrowser.worker.ts`, `useBrowserFlames.ts` | UT-FLAMES-PORT | — | VAL-FLAMES-PARITY | HAZ-001, HAZ-006 (RC-048) |
| REQ-FUNC-094 (draft) | nnU-Net parity (Dice >= 0.99) | — | DESIGN.md §3 | `preprocess.ts`, `slidingWindow.ts`, `pipeline.ts` | UT-FLAMES-PORT | — | VAL-FLAMES-PARITY | HAZ-001 (RC-041) |
| REQ-FUNC-095 (draft) | Result on the FLAIR's grid in RC-031 order; opened only over the same file/grid | — | DESIGN.md §3.1, §9 | `axes.ts`, `draft.ts`, `useSegmentationMask.ts` | UT-FLAMES-PORT, UT-FLAMES-MODEL | — | — | HAZ-006 (RC-042, RC-046) |
| REQ-FUNC-096 (draft) | Expected duration, elapsed time, cancel without touching the open segmentation | — | COOP-COEP-IMPACT.md | `runtimeEstimate.ts`, `BrowserFlamesCard.tsx`, `useBrowserFlames.ts` | UI-FLAMES-CANCEL, UI-FLAMES-CARD | — | — | — |
| REQ-FUNC-097 (draft) | Licence/attribution notices reachable in the app | — | DESIGN.md §11 | `notices.ts`, `BrowserFlamesCard.tsx`, `public/licenses/*` | UI-FLAMES-CARD | — | — | — |
| REQ-FUNC-098 (draft) | Reliability-by-slice-thickness card next to the lesion results (flag OFF) | — | spec `APP-FEATURE-slice-thickness-reliability.md` (PR #54, research input) | `SliceThicknessReliabilityCard.tsx`, `utils/sliceThicknessReliability.ts`, `config/sliceThicknessReliability.v2.json`, `LesionDashboard.tsx`, `ViewerApp.tsx`, `config/features.ts` | UT-STC-LOGIC, UI-STC-CARD, UT-STC-FLAG | — | — | HAZ-015, HAZ-001 (RC-055..RC-058) |
| REQ-FUNC-099 (draft) | Acquisition geometry per image (state, effective mm, source, reason), Class C utilities wrapped | — | `acquisition_geometry.py` module docstring | `acquisition_geometry.py`, `imaging_service.py`, `schemas.py` | UT-RC054 | — | — | HAZ-015 (RC-054) |

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
> | REQ-SAFE-021 (added 2026-09-28) | Each region-classification path only under its precondition: atlas only on MNI-like grids; FreeSurfer parcellation check; geometric preconditions; zone map in the lesion mask's axis order, generated fresh, shape-checked; parcellation of the same image with the full landmark set; spacing from the source image; 422 with reasons when every applicable path refused, 500 / `atlas_error` on a fault; atomic zone-map replacement; same gate in the longitudinal compare route | RC-032 | HAZ-005 | DD-CLS-001 | `ms_region_classifier.py` (`looks_mni`, `NotMNISpaceError`, `looks_like_freesurfer_parcellation`, `prepare_geometric_image`, `GeometricPreconditionError`, shape checks), `segmentation_regions.py` (classify-regions, generate-zone-map), `LesionDashboard.tsx` (amber atlas-unavailable and geometric alerts) | UT-CLS-003 (`backend/tests/unit/test_rc032_region_atlas_guard.py`, 36 `test_rc032_*`), UI-RC032 (`frontend/src/components/LesionDashboard.rc032.test.ts`, 6 `rc032`), UT-LBL-001 (labelling) | TEST-BOUND (negative controls executed: `docs/iec62304/records/risk_verification/RC-032_negative_controls_2026-09-28.json`) |
> | CAPA-006 PA-6.1 (preventive) | The MAGNIMS method in the labelling and design documents is bound to the code: IFU §10.3 states each `*_DISTANCE_THRESHOLD_MM` and the MNI requirement. Withdrawn 3/4/3 mm values, a "two-tier" cascade and unsupported accuracy/validation claims appear only next to a CAPA-006 note | — (preventive action for HAZ-005 labelling) | HAZ-005 | DD-CLS-001 | IFU-001, AIA-001, CER-001, GSPR-001, SRS-001, SAD-001, DD-001, UEF-001, master and technical documents, README, Class C code comments | UT-LBL-001 (`backend/tests/unit/test_capa006_labelling_bound_to_code.py`, 48 tests) | TEST-BOUND (negative controls executed: same record, section PA-6.1) |
>
> RC-032 does not establish region-assignment accuracy, and the grid gate cannot certify true normalisation. The **HAZ-005 residual risk remains UNDETERMINED** (RMF-001).
>
> **Addendum 2026-10-17: REQ-SAFE-022/023/024 added, RC-033/034/035 (CAPA-008).**
>
> | Req ID | Safety Requirement | Risk Control | HAZ ID | Implementation | Test ID | Verified? |
> |--------|-------------------|-------------|--------|----------------|---------|-----------|
> | REQ-SAFE-022 | AI-assistant (MCP) layer read-only, STDIO only, identifiers removed, intended-use wording | RC-033 | HAZ-003, HAZ-010 | `app/mcp/_backend.py`, `imaging_server.py`, `ms_clinical_server.py`, `run_all.py` | UT-CAPA008 | VERIFIED 2026-10-17 (negative controls A1–A9 9/9) |
> | REQ-SAFE-023 | No AI report draft without a device measurement; reason shown | RC-034 | HAZ-003 | `ai_report.py`, `AIReportPanel.tsx` | UT-CAPA008 | VERIFIED 2026-10-17 (R1–R2 2/2) |
> | REQ-SAFE-024 | CVS/PRL readings attributed and counted per McDonald 2024; activity candidate per MAGNIMS 2021 | RC-035 | HAZ-007, HAZ-008 | `segmentation_analysis.py`, `LesionDashboard.tsx`, `longitudinal_tracking_service.py` | UT-CAPA008, UT-LONG-RULES | VERIFIED 2026-10-17 (C1–C6 6/6) |
>
> **Addendum 2026-10-17: REQ-SAFE-016 amended, REQ-SAFE-025/026/027 added, RC-016/RC-023 extended, RC-037/RC-038 added (CAPA-010, approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63)).**
>
> | Req ID | Safety Requirement | Risk Control | HAZ ID | Implementation | Test ID | Verified? |
> |--------|-------------------|-------------|--------|----------------|---------|-----------|
> | REQ-SAFE-016 (amended) | Identity in the image viewport in every view mode (2D, every multi-panel cell, 3D volume and multiplanar); "not identified" warning when absent | RC-016 (extended) | HAZ-009 | `ViewportSafetyOverlay.tsx`; `ImageViewer2D.tsx`, `ImageViewer3D.tsx`, `MultiPanelViewer.tsx`; identity passed by `ViewerApp.tsx` | UI-RC016-023 (existing), UI-CAPA010-3D, UI-CAPA010-MPV, UI-CAPA010-APP | TEST-BOUND on branch (negative controls I1–I5) — approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
> | REQ-SAFE-025 | No laterality glyph in any viewport; orientation of each viewport's own image reported; standing caveat fully visible on the page | RC-023 (extended) | HAZ-006 | `ImageViewer3D.tsx` (niivue `isOrientCube: false`, `isOrientationTextVisible: false`), `MultiPanelViewer.tsx` + `useMultiViewerStore.ts` (per-panel orientation), `ViewerApp.tsx` (flex centre column) | UI-CAPA010-3D, UI-CAPA010-MPV, UI-CAPA010-APP (real-browser layout) | TEST-BOUND on branch (O1–O4, G1–G2, L1, L3 detected; L2 equivalent by design) — approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
> | REQ-SAFE-026 | Selected-lesion crosshair and box at the reported voxel in 3D: (z, y, x) → (i, j, k) = (y, x, z) | RC-037 | HAZ-006 | `utils/boundingBoxMesh.ts::lesionVoxelToNifti`, `ImageViewer3D.tsx` | UI-CAPA010-3D | TEST-BOUND on branch (M1–M3) — approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
> | REQ-SAFE-027 | Distance, area and angle tools zoom/pan invariant, in millimetres per axis, attached to the anatomy | RC-038 | HAZ-014 (HAZ-008) | `MeasurementOverlay.tsx` | UI-RC038 | TEST-BOUND on branch (R1–R9) — approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
>
> Negative-control record: `records/risk_verification/CAPA-010_negative_controls_2026-10-17.json`. Tests on the `main` sources (25 of 27 fail for the stated reason; the 2 that pass are expected to): `records/risk_verification/CAPA-010_tests_on_main_2026-10-17.json`.
>
> **REQ-SAFE-020 / RC-022 (HAZ-014)**: the row in the table above said "VERIFIED (code inspection)". It is struck through in place. Nothing in the code preprocesses images to the MNI 1 mm template or registers them to it; the only registration is longitudinal, intra-subject and rigid. Images are therefore **not** in MNI space by construction, which is why RC-032 must gate the MNI-space atlas. RMF-001 already records RC-022 as NOT VERIFIED (2026-07-18).
>
> **Addendum 2026-10-17: REQ-SAFE-028 added, RC-039 (CAPA-011).**
>
> | Req ID | Safety Requirement | Risk Control | HAZ ID | Implementation | Test ID | Verified? |
> |--------|-------------------|-------------|--------|----------------|---------|-----------|
> | REQ-SAFE-028 | A clinical-tool mask (FLAMeS, LST-AI, SynthSeg, mindGlide) loads back at the voxel and scanner position where the tool placed it; the orientation marker only on files in the image's own voxel order; not stored (stated error) when that position cannot be established, incl. a mask not on the image's own grid | RC-039 | HAZ-006, HAZ-001, HAZ-005 | `tool_runner_service.py` (`_orient_mask_for_storage`, `_store_nifti_as_segmentation`) | UT-RC039 | VERIFIED BY ITS AUTHOR 2026-10-17 (round-trip cases fail on `main`, fail-closed cases on the first fix, grid cases before CA-11.5; negative controls D0–D4, D6, F1–F5, G1–G4, M1, L1, T1–T5 22/22); owner approval PENDING |
>
> **Addendum 2026-10-17 (DRAFT, approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63)): REQ-SAFE-029..033, RC-040..RC-053 (CP-FLAMES-BROWSER-001, in-browser FLAMeS, flag OFF).**
> Negative controls: `records/risk_verification/CP-FLAMES-BROWSER-001_negative_controls_2026-10-17.json` (and the 2026-10-17 prototype set M1-M12, `docs/research/flames-in-browser/evidence/negative-controls.json`).
>
> | Req ID | Safety Requirement | Risk Control | HAZ ID | Implementation | Test ID | Verified? |
> |--------|-------------------|-------------|--------|----------------|---------|-----------|
> | REQ-SAFE-031 | Only the pinned model runs (download and cache) | RC-040 | HAZ-001 | `modelStore.ts`, `plan.ts` | UT-FLAMES-MODEL | TEST-BOUND on branch (I1, I2 detected; the pre-fix tests missed both) |
> | REQ-FUNC-094 | nnU-Net-faithful port | RC-041 | HAZ-001 | `preprocess.ts`, `slidingWindow.ts`, `pipeline.ts` | UT-FLAMES-PORT, VAL-FLAMES-PARITY | TEST-BOUND on branch (M1, M3, M5-M8) |
> | REQ-FUNC-095 | Axis order NIfTI → nnU-Net → app (RC-031) | RC-042 | HAZ-006 | `axes.ts` | UT-FLAMES-PORT | TEST-BOUND on branch (M2, M4, M10) |
> | REQ-SAFE-033 (a) | Skull-stripped gate incl. skull clue (zero-background heads) | RC-043 | HAZ-001 | `pipeline.ts`, `contrastGate.ts` | UT-FLAMES-GATE, VAL-FLAMES-GATE | TEST-BOUND on branch (G5, G5b, M11); with-skull FLAIRs refused 12/12 (6 subjects only) |
> | REQ-SAFE-029 | Fail closed: numerical/output guard | RC-044 | HAZ-001 | `slidingWindow.ts`, `pipeline.ts`, worker | UT-FLAMES-PORT | TEST-BOUND on branch (G9) |
> | REQ-SAFE-029 | One terminal message, worker terminated on cancel | RC-045 | HAZ-001 | `protocol.ts`, `useBrowserFlames.ts` | UI-FLAMES-CANCEL | TEST-BOUND on branch (H10) |
> | REQ-FUNC-095 | Draft only over the same file and grid | RC-046 | HAZ-006 | `draft.ts`, `useSegmentationMask.importMask` | UT-FLAMES-MODEL | TEST-BOUND on branch (M9) |
> | REQ-SAFE-030 | AI draft labelled, never autosaved, saved only with an exact provenance echo, unreviewed until a radiologist confirms the exact stored mask (SHA-256), reset on any mask change, no confirmation with unsaved corrections | RC-047 | HAZ-001 | `useSegmentationData.ts`, `AiDraftBanner.tsx`, `SegmentationPanel.tsx`, `draft.ts`; backend `schemas.py`, `segmentation_service.py`, `segmentation.py` | UT-FLAMES-HANDOFF, UI-FLAMES-CARD, UI-FLAMES-BANNER, UT-FLAMES-MODEL, UT-RC047 | TEST-BOUND on branch (H1-H4, B1-B9, U1-U5, P1-P2; BEFORE-R2a/R2b/R3 fail); usability not evaluated |
> | REQ-FUNC-093 | Feature flag OFF by default | RC-048 | HAZ-001 | `features.ts`, `ClinicalToolsPanel.tsx` | UT-FLAMES-FLAG | TEST-BOUND on branch (F1) |
> | REQ-SAFE-033 (b)(c) | FLAIR gate `flair-gate/2`: header and content refusal-only; positive evidence required (clinician's per-file confirmation recorded with who confirmed, or a FLAIR inversion time) — fail closed | RC-049 | HAZ-001 | `headerEvidence.ts`, `contrastGate.ts`, `nifti.ts`, `pipeline.ts`, worker, `BrowserFlamesCard.tsx`, `useBrowserFlames.ts`; backend `create_segmentation` | UT-FLAMES-GATE, UI-FLAMES-CARD, UI-FLAMES-CANCEL, UT-RC047, VAL-FLAMES-GATE | TEST-BOUND on branch (G1-G4, G7, G8, E1-E6, B10; G6 not detected; BEFORE-R1 fails); leave-one-dataset-out sensitivity/specificity in FLAIR-GATE-VALIDATION.md |
> | REQ-SAFE-032 | Never discard unsaved work when opening a draft | RC-050 | HAZ-001 | `useSegmentationData.ts`, `BrowserFlamesCard.tsx` | UT-FLAMES-HANDOFF, UI-FLAMES-CARD | TEST-BOUND on branch (H5, H6; the reviewed code fails these tests) |
> | REQ-FUNC-036 | Empty result explicit | RC-051 | HAZ-001 | `BrowserFlamesCard.tsx`, `draft.ts` | UI-FLAMES-CARD | TEST-BOUND on branch (H7, H8) |
> | — | 5-fold ensemble default before clinical use | RC-052 | HAZ-001 | — | — | **NOT IMPLEMENTED** (CA-FLAMES-1) |
> | — | Device gate / cross-origin isolation | RC-053 | HAZ-001 | — | — | **NOT IMPLEMENTED** (CA-FLAMES-2) |
>
> **Addendum 2026-10-21 (DRAFT, approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63)): REQ-SAFE-034/035/036, RC-054..RC-058 (CP-SLICE-THICKNESS-001, reliability by slice thickness, flag OFF).**
> Negative controls and provenance re-derivation: `records/risk_verification/CP-SLICE-THICKNESS-001_negative_controls_2026-10-21.json`. Re-executed 2026-10-23 after the independent review of PR #59 (B13, D10, D11 added, D5 redefined): `records/risk_verification/CP-SLICE-THICKNESS-001_negative_controls_2026-10-23.json` — 38/38 detected, provenance re-derived.
>
> | Req ID | Safety Requirement | Risk Control | HAZ ID | Implementation | Test ID | Verified? |
> |--------|-------------------|-------------|--------|----------------|---------|-----------|
> | REQ-SAFE-034, REQ-FUNC-099 | Acquisition thickness read from the file, never assumed (native only from an ORIGINAL DICOM with a recorded thickness and spacing or 3D; spacing without thickness not determinable; NIfTI at most a lower bound > 1.5 mm; otherwise not determinable with a reason; total) | RC-054 | HAZ-015, HAZ-001 | `acquisition_geometry.py`, `imaging_service.py`, `schemas.py` | UT-RC054 | TEST-BOUND on branch (B1-B13; B13 added 2026-10-23) |
> | REQ-SAFE-034 | Strict parse; the segmentation's own image or the single original FLAIR of a processed image, named; thicker source wins; legacy `slice_thickness` never read | RC-055 | HAZ-015 | `sliceThicknessReliability.ts`, `SliceThicknessReliabilityCard.tsx`, `LesionDashboard.tsx`, `ViewerApp.tsx` | UT-STC-LOGIC, UI-STC-CARD | TEST-BOUND on branch (P1-P8) |
> | REQ-SAFE-035 | No false-lesion rate at any thickness in this version; asset with a site calibration refused | RC-056 | HAZ-015 | `sliceThicknessReliability.ts`, `sliceThicknessReliability.v2.json`, card | UT-STC-LOGIC, UI-STC-CARD | TEST-BOUND on branch (R1-R3) |
> | REQ-SAFE-036, REQ-FUNC-098 | Detection note from the versioned, source-bound asset (v2.0.0); evidence size; pre-registered thickness bands only, post-hoc row or record refused (amended 2026-10-23 after the independent review of PR #59); worst case; empty-list warning; 3D FLAIR recommendation | RC-057 | HAZ-001, HAZ-015 | `sliceThicknessReliability.v2.json`, `sliceThicknessReliability.ts`, card | UT-STC-LOGIC, UI-STC-CARD | TEST-BOUND on branch (D1-D11; every asset figure re-derived from the record at `cabb99d`) |
> | REQ-FUNC-098 | Feature flag OFF by default; card lazy and only behind the flag | RC-058 | HAZ-015 | `features.ts`, `LesionDashboard.tsx` | UT-STC-FLAG | TEST-BOUND on branch (F1-F3); production build checked with the flag absent |
>
> **Addendum 2026-10-22 (DRAFT, approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63)): RC-059 (PRB-001), REQ-SAFE-037 → RC-060/RC-061/RC-062 (RMF-OBS-001).** All four controls are proposed and NOT IMPLEMENTED; no test exists. Records: `records/problem_reports/PRB-001_MSMask_Third_Ventricle_Counted_Periventricular.md`; RMF-001 §3.5. RC-054..RC-058 and REQ-SAFE-034..036 are reserved by open PR #59.
>
> | Req ID | Safety Requirement | Risk Control | HAZ ID | Implementation | Test ID | Verified? |
> |--------|-------------------|-------------|--------|----------------|---------|-----------|
> | REQ-FUNC-053 | MSMask path: PV landmark = lateral ventricles only (derived, versioned, hash-checked mask; fail closed); LST-AI zones path recomputed with the same rule or deviation stated | RC-059 | HAZ-005 (HAZ-008) | — | — (proposed: `test_rc059_*`, PRB-001 §6 V1–V7) | **NOT IMPLEMENTED** (proposed CAPA-006 CA-6.14) |
> | REQ-SAFE-037 (a)–(c) (proposed) | Unconfirmed candidates never presented as activity (interim, first); no activity/DIT flag to reports or the assistant; per-candidate confirmation by the reader; activity from confirmed candidates only | RC-060 | HAZ-007 | — | — | **NOT IMPLEMENTED** (proposed CAPA-008 CA-8.11) |
> | REQ-SAFE-037 (d) (proposed) | Measured false-candidate rate stated to the reader in the user's language; subtraction never worded as confirmation; longitudinal safety texts in every shipped locale | RC-061 | HAZ-007 | — | — | **NOT IMPLEMENTED** (proposed CAPA-008 CA-8.12) |
> | REQ-SAFE-037 (e) (proposed) | No new/enlarging counts when the acquisition differs between visits or cannot be established; reason stated; overlay kept | RC-062 | HAZ-007 | — | — | **NOT IMPLEMENTED** (proposed CAPA-008 CA-8.13) |
>
> **Addendum 2026-10-22 (CAPA-013, DRAFT, approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63)): REQ-SAFE-037 → RC-060/RC-061/RC-062 implemented on branch `fix/longitudinal-activity-display-capa013`.** Supersedes the three REQ-SAFE-037 rows above. Record: `records/capa/CAPA-013_Longitudinal_Candidates_Presented_As_Activity.md`; tests on PR #62: `records/risk_verification/CAPA-013_tests_on_base_2026-10-22.json`; negative controls: `records/risk_verification/CAPA-013_negative_controls_2026-10-22.json`.
>
> | Req ID | Safety Requirement | Risk Control | HAZ ID | Implementation | Test ID | Verified? |
> |--------|-------------------|-------------|--------|----------------|---------|-----------|
> | REQ-SAFE-037 (a)–(c) | Unconfirmed candidates never activity (no flag to view, report or assistant; fixed report notice); radiologist confirm/reject recorded with reader and time, bound to both masks; activity statement from confirmed candidates only | RC-060 | HAZ-007 (HAZ-003) | `longitudinal_candidate_safety.py`, `segmentation_analysis.py` (compare, `/longitudinal/review`), `LongitudinalResultPanel.tsx`, `mcp/_backend.py`, `brain_report_service.py`, `ai_report.py` | UT-CAPA013 (`test_rc060_*`), UI-CAPA013 (`rc060`) | TEST-BOUND on branch (fail on PR #62 and, for the review findings, on `ad144ba`; negative controls B1–B11, B13–B20, F1–F5, F20; B12 retired with the code it mutated); owner approval PENDING |
> | REQ-SAFE-037 (d) | Measured false-candidate rate from a versioned asset bound to the rule, with source and date, in the reader's language; subtraction a signal; every text of the view in en/es/de | RC-061 | HAZ-007 | `longitudinal_candidate_safety.py`, `assets/longitudinal_false_candidate_evidence.json`, `LongitudinalResultPanel.tsx`, `LongitudinalCompare.tsx`, locale files | UT-CAPA013 (`test_rc061_*`), UI-CAPA013 (`rc061`) | TEST-BOUND on branch (negative controls E1–E9, F6–F12, F15, F21); owner approval PENDING |
> | REQ-SAFE-037 (e) | Abstain when the acquisition differs or cannot be established; reason and metadata compared stated; overlay kept; acquisition record stored at PACS import | RC-062 | HAZ-007 | `longitudinal_candidate_safety.py`, `segmentation_analysis.py`, `dicomweb_service.py`, `LongitudinalResultPanel.tsx` | UT-CAPA013 (`test_rc062_*`), UI-CAPA013 (`rc062`) | TEST-BOUND on branch (negative controls A1–A16, F13–F14, F16–F19, F22); owner approval PENDING |

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

> **Addendum 2026-10-24 (CAPA-014, DRAFT — PENDING owner approval): data sent to the AI report provider.** Branch `fix/ai-report-deidentification-capa014`. REQ-SEC-007 is refined for the report path by REQ-SEC-021..023.
>
> | Req ID | Requirement | Risk Control | HAZ ID | Implementation | Test | Verified? |
> |--------|-------------|-------------|--------|----------------|------|-----------|
> | REQ-SEC-021 | Structured payload only (measurements — "not available" never 0, out-of-range numbers refused; fixed labels incl. the application's label names, other labels numbered and named in the draft only; sex M/F; 5-year age band, "90 or older"; DIS evaluation state kept, not evaluated never "NOT MET"); no free text; typed text merged locally, quoted and closed, the model's text under a fixed heading; fixed system prompt | RC-064 | HAZ-016 | `report_payload_guard.py`, `brain_report_service.py` (Class C), `ai_report.py` | UT-CAPA014 (`test_rc064_*` incl. `test_rc064_dis_*`, `test_n1_*`–`test_n4_*`), UI-CAPA014 | TEST-BOUND on branch (negative controls CAPA-014, P1–P17, M4–M7, U8) |
> | REQ-SEC-022 | Fail closed (400 / 404 / 503) and a detection-only tripwire on the final prompt (patient's own identifiers — all-digit record numbers and the digits of a prefixed one as whole numbers; generic patterns; never on the device's words of the user prompt alone or two of them in the device's order; capped, linear) | RC-065 | HAZ-016 | `ai_report.py`, `resource_access.py::authorize_segmentation_id`, `brain_report_service.py`, `report_payload_guard.py`, `AIReportPanel.tsx`, `mcp/ms_clinical_server.py` | UT-CAPA014 (`test_rc065_*`, `test_n5_*`, `test_n8_*`), UT-CAPA009, UI-CAPA014 | TEST-BOUND on branch (T1–T27, F1–F6, U5) |
> | REQ-SEC-023 | Count log, never the payload; true panel note and viewer footer in en/es/de; no false claim (repository test); data categories recorded (CAPA-014 §6) | RC-066 | HAZ-016 | `brain_report_service.py`, `ai_report.py`, `AIReportPanel.tsx`, `ReportViewerModal.tsx`, locales | UT-CAPA014 (`test_rc066_*`, `test_n6_*`, `test_n9_*`), UI-CAPA014; inspection of CAPA-014 §6 | TEST-BOUND on branch (M1–M3, M8, L1–L3, C1–C4, U1–U4, U6, U7); §6 owner to confirm |

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
| UT-CLS-003 | RC-032 path preconditions (36 `test_rc032_*`, 22 through the real app, added 2026-09-28). MNI gate accepts MNI grids and rejects oblique, clinical, permuted, off-centre, transform-less and non-MNI-FOV grids (the FOV condition tested on its own); the longitudinal compare route uses the same gate. Atlas zone map matches the orientation-consistent reference per lesion, including on a cubic grid; a zone map of another grid is refused; zone volumes use the voxel volume. Region routes alive with spacing from the source image. `msmask` off-MNI → 422; `auto` → fallback with reason. Persisted zone map never reused. generate-zone-map refuses non-MNI images, keeps existing zone maps on a refusal or a persist failure, and makes no raw upload. Parcellation: a zone map, an instance-labelled mask or another image's parcellation is never used; a genuine same-image parcellation is. Geometric path uses the brain outline and refuses sagittal, reversed, > 30° tilted, mismatched or blank images. An atlas fault is reported (`atlas_error`); a geometric fault is a 500. Object-level authorization: a caller without access to the patient gets 404 on both routes (RC-029) | REQ-SAFE-021, REQ-FUNC-053 (RC-032, HAZ-005); REQ-SEC-001 (RC-029, HAZ-010) for the two authorization tests |
| UI-RC032 | LesionDashboard shows an amber alert whenever `atlas_unavailable_reason` is present, translated in every shipped locale and naming MNI space. An atlas fault has its own alert. Geometric regions always carry a warning, and no warning claims an unmeasured comparative accuracy. The panel no longer promises SynthSeg or a "best" automatic method (6 `rc032`, added 2026-09-28) | REQ-SAFE-021, REQ-FUNC-053 (RC-032) |
| UT-LBL-001 | CAPA-006 PA-6.1 labelling gate (60 tests, added 2026-09-28). IFU §10.3 states each `*_DISTANCE_THRESHOLD_MM` and the MNI requirement. Withdrawn 3/4/3 mm values, a "two-tier" cascade, validation, "exact methodology" and MAGNIMS accuracy-% claims appear only next to a CAPA-006 withdrawal note in 19 listed documents, Class C source files, the MCP server and the UI locales. A missing listed file fails | REQ-FUNC-053, REQ-SAFE-021 (CAPA-006 PA-6.1) |
| UT-CAPA008 | `test_capa008_assistant_read_only.py` (39 tests, added 2026-10-17): MCP layer read-only (exact server and tool sets, no direct HTTP client, POST only to compute-only routes, every GET mounted and object-authorized, compute-only routes store nothing, every field sent is read by its route), intended-use phrase ban, identifier removal; report route refuses requests without a measurement; CVS/PRL readings validated, attributed to the authenticated reader, counted without the 40 % rule; UI sources | REQ-SAFE-022, REQ-SAFE-023, REQ-SAFE-024 |
| UT-LONG-RULES | `test_longitudinal_clinical_rules.py`: activity candidate raised by >=1 new or enlarging candidate (MAGNIMS 2021; CAPA-008 CA-8.10) | REQ-SAFE-024, REQ-FUNC-055a |
| UT-CAPA009 | `test_capa009_object_authorization_everywhere.py` (47 tests, added 2026-10-17): every mounted route referencing an object classified and re-derived; path dependencies match the path; no dependency can skip itself (async guards); 33 requests by an unentitled user → 404 before any data service; 4 administrator-only routes → 403; positive controls; overlay/reference-image authorization; tool inputs from one patient; initiator registry | REQ-SEC-014, REQ-SEC-015, REQ-SEC-016, REQ-SEC-019, REQ-SEC-020 |
| UI-RC016-023 | `frontend/src/components/ViewportSafetyOverlay.test.tsx` (CAPA-004): the overlay renders identity, missing-identity warning, orientation, UNKNOWN alert, no L/R glyph, caveat | REQ-SAFE-016, REQ-SAFE-013 (RC-016, RC-023) |
| UI-CAPA010-3D | `frontend/src/components/ImageViewer3D.capa010.test.tsx` (10 tests, added 2026-10-17): the real 3D viewer with a recording niivue stand-in — identity and missing-identity warning in volume and multiplanar mode; the effective options of every 3D niivue instance fed to the REAL niivue drawing routines draw no orientation cube and no slice letters; orientation and caveat on the 3D viewport; lesion crosshair (volume, four multiplanar panels) and box at affine · (y, x, z) | REQ-SAFE-016, REQ-SAFE-025, REQ-SAFE-026 (RC-016, RC-023, RC-037) |
| UI-CAPA010-MPV | `frontend/src/components/MultiPanelViewer.capa010.test.tsx` (6 tests, added 2026-10-17): identity and missing-identity warning on every panel; each panel shows its own image's orientation, keeps it on slice change and clears it on reassignment; caveat on every panel | REQ-SAFE-016, REQ-SAFE-025 (RC-016, RC-023) |
| UI-CAPA010-APP | `frontend/src/ViewerApp.capa010.test.tsx` (5 tests, added 2026-10-17): the REAL viewer page (mocked backend) puts the loaded identity on 2D, multi-panel, 3D volume and 3D multiplanar; the rendered page with the app's real CSS, measured in a real headless browser at 1366x768, 1600x900, 1920x1080, shows every caveat in full (fails in CI if no browser) | REQ-SAFE-016, REQ-SAFE-025 (RC-016, RC-023) |
| UI-RC038 | `frontend/src/components/MeasurementOverlay.rc038.test.tsx` (10 tests, added 2026-10-17/18): simulated clicks on the real component — ruler true length at zoom 2, same length at zoom 1/2/4 with pan, ROI true area at zoom 2, ruler follows the anatomy on zoom and on pan, angle in millimetres on 2 mm x 1 mm pixels; on a non-square image and canvas with 3 mm x 0.9 mm pixels at zoom 1/2/4: ruler, ROI area, angle, and the ruler redrawn where the canvas draws its end points | REQ-SAFE-027, REQ-FUNC-090/091/092 (RC-038) |
| UT-RC039 | `test_rc039_tool_runner_mask_axes.py` (28 test cases, added 2026-10-17, grid and record cases 2026-10-18): a clinical-tool mask goes through the real store path and the real load path (`SegmentationService.get_mask`) and comes back at the same voxel (a0, a1, k), the same scanner position and the same slice layout, and the stored file served to viewers places it at the same position; non-cubic asymmetric volume with a flipped anisotropic affine; cubic silent case; tool output in another voxel order; LST-AI types mask; marker/order contract; every tool end to end (FLAMeS, LST-AI, SynthSeg, mindGlide lesion and structure masks); fail closed (no / missing / unreadable reference, indeterminate affine → nothing stored; each tool's run with an unreadable reference → FAILED, nothing stored); same grid required (other shape, 0.5 mm shift, SynthSeg-like 1 mm output, SynthSeg run end to end → refused, nothing stored; float rounding accepted); stored record dimensions agree with the image and the loaded mask | REQ-SAFE-028, REQ-FUNC-034, REQ-FUNC-035 |
| UT-FLAMES-PORT (draft) | `frontend/src/services/flames/__tests__/{preprocess,slidingWindow,axes-nifti,pipeline}.test.ts`: nnU-Net arithmetic vs nnunetv2/scipy/skimage/SimpleITK fixtures, axis order, blob localisation, fail-closed output guards (`rc041`, `rc042`, `rc043`, `rc044`, `rc049`) | REQ-FUNC-093/094/095, REQ-SAFE-029 (RC-041, RC-042, RC-044) |
| UT-FLAMES-MODEL (draft) | `modelStore.test.ts` (download and Cache Storage paths, `rc040`), `draft-model.test.ts` (pin, CM pin = committed manifest, grid gate `rc046`, sequence evidence recorded and exact unreviewed provenance echo `rc047`/`rc049`) | REQ-SAFE-031, REQ-FUNC-095, REQ-SAFE-030 (RC-040, RC-046, RC-047) |
| UT-FLAMES-GATE (draft) | `inputGates.test.ts` (synthetic FLAIR/T1/T2 phantoms, bias field, no positive evidence → refused, header with a FLAIR inversion time → accepted, a FLAIR label alone → refused, T1/T2 refused even when confirmed, grey-class rule, skull with zero background, `rc043`/`rc049`), `niftiHeader.test.ts` (descrip, extensions, DICOM InversionTime), `pipeline.test.ts` (T1 refused before any network call) | REQ-SAFE-033 (RC-043, RC-049) |
| UT-FLAMES-HANDOFF (draft) | `useSegmentationData.flamesDraft.test.tsx`: no save-on-unload for AI drafts, provenance sent and echo-checked exactly (another hash / fold / a confirmed echo refused), automatic not manual, unsaved work never discarded, provenance re-read after saving corrections (fail safe unreviewed), unsaved flag and mask SHA-256 published (`rc047`, `rc050`) | REQ-SAFE-030, REQ-SAFE-032 (RC-047, RC-050) |
| UI-FLAMES-CARD (draft) | `BrowserFlamesCard.test.tsx`: empty-result warning + acknowledgement (`rc051`), unsaved-work question (`rc050`), provenance hand-over incl. sequence evidence (`rc047`), run disabled until the clinician confirms the sequence of this file, cleared on a file change (`rc049`), duration text, licence panel and shipped licence texts | REQ-FUNC-036, REQ-SAFE-030, REQ-SAFE-032, REQ-SAFE-033, REQ-FUNC-096, REQ-FUNC-097 |
| UT-CAPA013 (draft) | `test_capa013_longitudinal_candidates.py` (52 cases, added 2026-10-22, 11 more 2026-10-23 after the independent review of PR #63; written before each fix): through the real routes — no activity/DIT flag or activity word in the comparison, radiologist-only decisions bound to both masks, reader and time stored, rejected or voided decisions never raise activity, unknown decisions refused; report prompt and template without an activity class from candidates, radiologist confirmation stated, localised notice on the draft; assistant client drops the flags and cannot record a decision; evidence asset bound to rule and source, served from the asset, withheld when the rule changes or the asset is incomplete; acquisition comparison (same, each field differing, missing, voxel size), abstention without counts or any quantity, DICOM header read as plain values, PACS import records it; review of PR #63: forged confirmation never reaches the report (real route and prompt builder), decision history appended, read errors reported, visit order, SEL gated, rate share as measured, assistant rate from the asset | REQ-SAFE-037, REQ-FUNC-055a |
| UI-CAPA013 (draft) | `frontend/src/components/LongitudinalCompare.capa013.test.tsx` (18 cases, added 2026-10-22, 5 more 2026-10-23 after the review; written before each fix): the real panel with mocked API — no activity/DIT/NEDA text from unconfirmed candidates (legacy flags in the fixture), activity only in the radiologist-confirmed box with who and when, decision sent with the mask binding then the comparison refreshed, refusal shown; measured rate rendered from the response (other figures render as given), missing rate stated; subtraction a signal; every key in en/es/de and safety texts translated; Spanish and German rendering with no English phrase; abstention with reason, fields and no counts or lesion load; SEL not offered when abstaining; Compare disabled for the same visit or a visit 2 not later; unknown visit dates stated; unreadable decisions reported | REQ-SAFE-037 |
| UT-CAPA014 (draft) | `test_capa014_report_provider_payload.py` (220 cases, added 2026-10-24 for the redesign after the review of PR #67; the behavioural cases written before the redesign fail on the PR #67 head `4bfdd7e`): through the real route and report service with a mocked provider client — markers in every text field never sent, measurements and labels unchanged, age bands incl. "90 or older", sex M/F only, fixed system prompt; label-collision patients (White, Black, Small, Pons, Blanca, May, Do, Le …) change nothing and are never blocked; the tripwire refuses each leak form of the review and generic patterns, never edits text, caps, runs in linear time; fail closed; typed text merged locally after the disclaimer; count log without payload; no false claim in the repository; second review (written first, failing on `5314af7`): typed text quoted and closed, the model's text under a fixed heading (en/es/de), every label name the application ships in the vocabulary, one number per unlisted label in groups and rows and named in the draft only, "not available" never 0, implausible numbers refused, exempt words of the user prompt only, the instruction only when something was typed, all-digit record numbers not found inside measurements, the digits of a prefixed record number found, pairs of device words not a name, no RC-007 statement generated, the configured model named | REQ-SEC-021, REQ-SEC-022, REQ-SEC-023 (RC-064, RC-065, RC-066) |
| UI-CAPA014 (draft) | `frontend/src/components/AIReportPanel.capa014.test.tsx` (11 cases, added 2026-10-24, rewritten for the redesign): the panel sends the analysed segmentation; the note directly above the draft button in en/es/de states measurements only and that the typed text stays in the application; the report viewer footer is true in en/es/de (no HIPAA claim; old key removed); no HIPAA claim in the API client or the viewer source; typed Markdown shown as text and no image loaded by the report viewer (second review) | REQ-SEC-022, REQ-SEC-023 (RC-065, RC-066) |
| UI-FLAMES-BANNER (draft) | `AiDraftBanner.test.tsx`: no confirm button with unsaved corrections; the SHA-256 of the mask on screen is sent; nothing sent if it cannot be computed; server refusal shown; a confirmed review names its mask (`rc047`) | REQ-SAFE-030 (RC-047) |
| UI-FLAMES-CANCEL (draft) | `useBrowserFlames.cancel.test.tsx`: cancel terminates the worker, ignores late results, never touches the open segmentation (`rc045`); the sequence confirmation reaches the worker only when given (`rc049`); duration estimate | REQ-FUNC-096, REQ-SAFE-029, REQ-SAFE-033 (RC-045, RC-049) |
| UT-FLAMES-FLAG (draft) | `features.flames.test.ts`: flag OFF unless 'true'/'1'; card only behind the flag, lazy (`rc048`) | REQ-FUNC-093 (RC-048) |
| UT-RC047 (draft) | `backend/tests/unit/test_rc047_ai_draft_provenance.py`: provenance schema (sequence evidence required), service forces 'unreviewed' + automatic and records who confirmed the sequence, create route passes provenance, confirm route (radiologist only, 409 for manual work, binds the SHA-256 of the stored mask, 409 on a different mask), any mask change after a confirmation resets it (mask upload and every persist path), identical re-upload keeps it | REQ-SAFE-030, REQ-SAFE-033 (RC-047, RC-049) |
| VAL-FLAMES-GATE (draft) | `gateValidation.flames.test.ts` + `gateReplay.flames.test.ts` (opt-in) on public MSLesSeg / open_ms_data / ISBI-2015 volumes incl. with-skull FLAIRs; leave-one-dataset-out by `research/flames_in_browser/gate_lodo.py`; results in `docs/research/flames-in-browser/evidence/gate-*.json`, FLAIR-GATE-VALIDATION.md | REQ-SAFE-033 (RC-043, RC-049) |
| VAL-FLAMES-PARITY (draft) | `parity.flames.test.ts` (opt-in) vs `nnUNetv2_predict` on public FLAIR (DESIGN.md §0) | REQ-FUNC-094 (RC-041) |
| UT-RC054 (draft) | `backend/tests/unit/test_rc054_acquisition_geometry.py` (`test_rc054_*`, added 2026-10-21): DICOM native/lower-bound/not-determinable rules (ORIGINAL + spacing or 3D, gap counted, derived/untyped never native, missing/invalid never defaulted, spacing without thickness not determinable — added 2026-10-23 after the independent review, also through the real loader — enhanced multi-frame), NIfTI never native (thick grid = lower bound on any axis and rotated affine; fine and MNI grids not determinable; pixdim/affine contradiction; units), totality on garbage, exposure by the image loaders and the process response, legacy default never leaks, Class C utilities untouched, every reason has a card message | REQ-FUNC-099, REQ-SAFE-034 (RC-054) |
| UT-STC-LOGIC (draft) | `frontend/src/utils/sliceThicknessReliability.test.ts` (`rc055`, `rc056`, `rc057`): strict parse, source image and original-FLAIR location, thicker source wins, MSLesSeg-like grid never thin; no false-lesion figure in any state, calibrated asset refused; asset equals the paper, bound to its record, worst-case sizes per band, band edges, lower bound over thicker bands; pre-registered bands only, post-hoc row or record refused, 2 mm gives no "8 in 10" size (added 2026-10-23) | REQ-SAFE-034, REQ-SAFE-035, REQ-SAFE-036 (RC-055, RC-056, RC-057) |
| UI-STC-CARD (draft) | `frontend/src/components/SliceThicknessReliabilityCard.test.tsx` (`rc055`, `rc056`, `rc057`): rendered card — image binding, legacy value never shown, original FLAIR named, request failure not determinable; no percentage next to the false-lesion statement; figures with evidence size, no post-hoc row (at 2 mm: band 1.5-4.5 mm, no "8 in 10" size — added 2026-10-23), empty-list warning, 3D FLAIR recommendation, provenance; Spanish wording | REQ-FUNC-098, REQ-SAFE-034, REQ-SAFE-035, REQ-SAFE-036 |
| UT-STC-FLAG (draft) | `frontend/src/config/features.sliceThickness.test.ts` (`rc058`): flag OFF unless 'true'/'1'; card only behind the flag, lazy; nothing else imports the card, its logic or its asset | REQ-FUNC-098 (RC-058) |

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
| `test_capa008_assistant_read_only.py` | UT-CAPA008 | REQ-SAFE-022, REQ-SAFE-023, REQ-SAFE-024 (RC-033/034/035, HAZ-003/007/008/010; added 2026-10-17) |
| `test_longitudinal_clinical_rules.py` | UT-LONG-RULES | REQ-SAFE-024, REQ-FUNC-055a (RC-035, HAZ-007) |
| `test_capa009_object_authorization_everywhere.py` | UT-CAPA009 | REQ-SEC-014/015/016/019/020 (RC-036, HAZ-010; added 2026-10-17) |
| `test_rc039_tool_runner_mask_axes.py` | UT-RC039 | REQ-SAFE-028, REQ-FUNC-034, REQ-FUNC-035 (RC-039, HAZ-006/001/005; added 2026-10-17) |
| `test_capa013_longitudinal_candidates.py` (draft) | UT-CAPA013 | REQ-SAFE-037 (RC-060/061/062, HAZ-007; added 2026-10-22, CAPA-013; exercises the Class C `brain_report_service.py` prompt) |
| `test_capa014_report_provider_payload.py` (draft) | UT-CAPA014 | REQ-SEC-021/022/023 (RC-064/065/066, HAZ-016; added 2026-10-24, CAPA-014, redesign; exercises the Class C `brain_report_service.py` and `report_payload_guard.py`) |
| `test_rc047_ai_draft_provenance.py` (draft) | UT-RC047 | REQ-SAFE-030 (RC-047, HAZ-001; added 2026-10-17, CP-FLAMES-BROWSER-001) |
| `test_rc054_acquisition_geometry.py` | UT-RC054 | REQ-FUNC-099, REQ-SAFE-034 (RC-054, HAZ-015; added 2026-10-21, draft) |
| `test_nifti_utils.py` | UT-NII-001 | REQ-FUNC-001 |
| `test_dicom_seg.py` | UT-SEG-001..008 | REQ-FUNC-072 |
| `test_dicom_utils.py` | UT-DICOM-001..007 | REQ-FUNC-072, REQ-SAFE-013 | RC-016 | VERIFIED |

---

*This matrix must be updated with each requirement change, design change, or new test.*
