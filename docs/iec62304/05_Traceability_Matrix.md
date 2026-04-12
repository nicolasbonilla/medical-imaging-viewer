# MSTool-AI: Requirements Traceability Matrix

## IEC 62304 Clause 5.1.1(e) — Bidirectional Traceability

**Document ID**: TM-001 | **Version**: 1.0 | **Date**: April 12, 2026

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
| REQ-FUNC-053 | MAGNIMS classification | SAD 3.5 | DD-CLS-001 | `ms_region_classifier.py` | UT-CLS-001 | IT-CLS-001 | ST-FUNC-053 | HAZ-005 |
| REQ-FUNC-054 | Longitudinal tracking | SAD 3.5 | — | `longitudinal_tracking_service.py` | UT-LONG-001 | IT-LONG-001 | ST-FUNC-054 | HAZ-007 |
| REQ-FUNC-060 | AI report generation | SAD 3.6 | DD-RPT-001 | `brain_report_service.py` | UT-RPT-001 | IT-RPT-001 | ST-FUNC-060 | HAZ-003 |
| REQ-FUNC-070 | QIDO-RS search | SAD 3.7 | — | `dicomweb_service.py` | — | IT-PACS-001 | ST-FUNC-070 | — |
| REQ-FUNC-071 | WADO-RS import | SAD 3.7 | — | `dicomweb_service.py` | — | IT-PACS-002 | ST-FUNC-071 | HAZ-012 |
| REQ-FUNC-072 | DICOM-SEG export | SAD 3.7 | — | `dicom_utils.py` | UT-SEG-001 | — | ST-FUNC-072 | HAZ-011 |
| REQ-FUNC-073 | FHIR resources | SAD 3.7 | — | `fhir.py` | — | IT-FHIR-001 | ST-FUNC-073 | — |

---

## Safety Requirements Traceability

| Req ID | Safety Requirement | Risk Control | HAZ ID | Design (DD) | Implementation | Test ID | Verified? |
|--------|-------------------|-------------|--------|-------------|----------------|---------|-----------|
| REQ-SAFE-001 | AI disclaimer label | RC-001 | HAZ-001 | DD-AI-001 | `QuickScreenBadge.tsx` | TST-SAFE-001 | TO DO |
| REQ-SAFE-002 | Viewing/Edit mode separation | RC-002 | HAZ-001 | DD-AI-001 | `ViewerApp.tsx` | TST-SAFE-002 | TO DO |
| REQ-SAFE-003 | Manual override available | RC-003 | HAZ-001 | DD-AI-001 | `SegmentationPanel.tsx` | TST-SAFE-003 | TO DO |
| REQ-SAFE-004 | Volumetry percentile display | RC-004 | HAZ-002 | DD-VOL-001 | `BrainVolumetryPanel.tsx` | TST-SAFE-004 | TO DO |
| REQ-SAFE-005 | Abnormality threshold display | RC-005 | HAZ-002 | DD-VOL-001 | `BrainVolumetryPanel.tsx` | TST-SAFE-005 | TO DO |
| REQ-SAFE-006 | Report disclaimer header | RC-006 | HAZ-003 | DD-RPT-001 | `brain_report_service.py` | TST-SAFE-006 | TO DO |
| REQ-SAFE-007 | Report no auto-commit | RC-007 | HAZ-003 | DD-RPT-001 | `AIReportPanel.tsx` | TST-SAFE-007 | TO DO |
| REQ-SAFE-008 | Edge AI confidence + disclaimer | RC-008 | HAZ-004 | DD-EDGE-003 | `QuickScreenBadge.tsx` | TST-SAFE-008 | TO DO |
| REQ-SAFE-009 | Edge AI hidden when no model | RC-009 | HAZ-004 | DD-EDGE-002 | `useEdgeAI.ts` | TST-SAFE-009 | TO DO |
| REQ-SAFE-010 | Classification confidence scores | RC-010 | HAZ-005 | DD-CLS-001 | `LesionDashboard.tsx` | TST-SAFE-010 | TO DO |
| REQ-SAFE-012 | Auto-transpose axis mismatch | RC-012 | HAZ-006 | DD-NII-002 | `SegmentationCanvasLocal.tsx` | TST-SAFE-012 | TO DO |
| REQ-SAFE-014 | Longitudinal tri-color overlay | RC-014 | HAZ-007 | — | `LongitudinalCompare.tsx` | TST-SAFE-014 | TO DO |
| REQ-SAFE-015 | DIS per-region details | RC-015 | HAZ-008 | DD-LES-002 | `LesionDashboard.tsx` | TST-SAFE-015 | TO DO |
| REQ-SAFE-016 | Patient ID prominent | RC-016 | HAZ-009 | — | `ViewerApp.tsx` | TST-SAFE-016 | TO DO |
| REQ-SAFE-018 | DICOMweb import confirmation | RC-020 | HAZ-012 | — | `PACSBrowserPage.tsx` | TST-SAFE-018 | TO DO |
| REQ-SAFE-020 | MNI 1mm template preprocessing | RC-022 | HAZ-014 | — | Preprocessing pipeline | TST-SAFE-020 | TO DO |

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

---

## Traceability Completeness Summary

| Chain | Total Links | Complete | Incomplete | Percentage |
|-------|-----------|----------|------------|-----------|
| Requirement → Architecture | 91 | 91 | 0 | 100% |
| Requirement → Design (Class C) | 25 | 25 | 0 | 100% |
| Requirement → Code | 91 | 91 | 0 | 100% |
| Requirement → Test | 91 | 23 | 68 | **25%** |
| Safety Req → Risk Control | 20 | 20 | 0 | 100% |
| Risk Control → Verification | 22 | 0 | 22 | **0%** |

**Key Gap**: 68 requirements lack formal test traceability. 22 risk controls lack verification evidence. These are the highest priority items for audit remediation.

---

*This matrix must be updated with each requirement change, design change, or new test.*
