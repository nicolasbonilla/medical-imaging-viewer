# MSTool-AI: Software Verification and Validation Plan

## IEC 62304 Clauses 5.1.6, 5.5, 5.6, 5.7 — Class C V&V Strategy

**Document ID**: VVP-001
**Version**: 1.0
**Effective Date**: April 12, 2026

---

## 1. Verification Activities (Did we build it right?)

### 1.1 Requirements Review

| Activity | Scope | Method | Acceptance Criteria | Evidence |
|----------|-------|--------|-------------------|----------|
| SRS Review | All 91 requirements (SRS-001) | Peer review | Each requirement is unambiguous, testable, traceable | Review record |
| Safety Requirements Review | 20 REQ-SAFE items | Peer review + clinical | Each traces to RMF-001 hazard | Review record |

### 1.2 Architecture Review

| Activity | Scope | Method | Acceptance Criteria | Evidence |
|----------|-------|--------|-------------------|----------|
| SAD Review | Technical Documentation Sec 2 | Peer review | Implements all requirements; interfaces complete | Review record |
| Segregation Review | SEG-001 | Peer review | All failure paths blocked | SEG-001 document |

### 1.3 Detailed Design Review (Class C Only)

| Activity | Scope | Method | Acceptance Criteria | Evidence |
|----------|-------|--------|-------------------|----------|
| DD Review | 12 Class C units (DD-001) | Peer review | Algorithms correct, interfaces complete, error handling specified | Review record |

### 1.4 Code Review (Class C)

| Activity | Scope | Method | Tool | Evidence |
|----------|-------|--------|------|----------|
| Static analysis (TS) | All frontend code | TypeScript strict + ESLint | GitHub Actions CI | CI pipeline logs |
| Static analysis (Py) | All backend code | Python syntax check | GitHub Actions CI | CI pipeline logs |
| Peer code review | All PRs to main | Pull request review | GitHub PRs | PR approval records |

### 1.5 Unit Verification (Class C)

| Unit | Test IDs | Method | Acceptance Criteria | Status |
|------|---------|--------|-------------------|--------|
| AI Segmentation | UT-AI-001 | pytest | Returns valid AITaskResult | DONE (test_ai_segmentation_service.py) |
| Volumetry | UT-VOL-001..003 | pytest | Volumes within ±1% of reference | DONE (test_brain_volumetry_service.py) |
| Report Generation | UT-RPT-001 | pytest | Returns valid report content | DONE (test_brain_report_service.py) |
| Lesion Analysis | UT-LES-001 | pytest | Component count matches reference | DONE (test_lesion_analysis_service.py) |
| DIS Criteria | UT-DIS-001 | pytest | DIS evaluation matches expert | DONE (test_lesion_analysis_service.py) |
| MAGNIMS Classifier | UT-CLS-001 | pytest | Region assignment matches reference | DONE (test_ms_region_classifier.py) |
| MAGNIMS Classifier — region evidence, no confidence (RC-010 (amended), HAZ-005, REQ-SAFE-010 amended 2026-09-28) | UT-CLS-002 | pytest | All 7 `test_rc010_*` tests pass: (1) the parcellation, MSMask and geometric paths all emit `confidence = None`, and the parcellation and MSMask paths also carry the matching `confidence_note`; (2) parcellation `distances_mm` are None, not 0.0, when a landmark is absent; (3) MSMask `region_overlap_fraction` uses all lesion voxels as the denominator, so a partially covered lesion is not reported as 1.0; (4) a lesion in no zone gets DWM with `atlas_coverage = false`, `region_overlap_fraction = None` and no fabricated 0.50; (5) the distance rule returns the region only and its 1.5 mm thresholds are unchanged; (6) MCP strips `confidence` from persisted classifications. Negative controls, executed: restoring numeric confidence gives 2 failed / 5 passed; restoring the 0.50 fallback gives 1/6; the old denominator gives 1/6; infinite distances give 1/6 | DONE 2026-09-28 (test_region_confidence_haz005.py) |
| LesionDashboard — region evidence display (RC-010 (amended), HAZ-005, REQ-SAFE-010 amended 2026-09-28) | UI-RC010 | vitest | All 7 `rc010` tests pass: (1) `regionEvidence()` maps the MSMask `region_overlap_fraction` to an overlap value; the table displays it as "Lesion % in zone", e.g. "8% in PV"; (2) a default-DWM lesion (`atlas_coverage = false`) maps to `outsideZones`, and the dashboard renders it with the translated `classify.outsideZones` label and tooltip ("No WM zone — DWM by default"); (3) paths without zone evidence show nothing in that column; (4) a `confidence` sent by a stale backend or a persisted result is ignored; (5) the table never reads a lesion confidence; (6) the summary says no per-lesion confidence is reported and computes no average. Negative controls, executed: restoring the confidence cell gives 1 failed / 6 passed; having regionEvidence return confidence gives 1/6 | DONE 2026-09-28 (frontend/src/components/LesionDashboard.haz005.test.ts) |
| MAGNIMS Classifier — path preconditions (RC-032, HAZ-005, REQ-SAFE-021, CAPA-006) | UT-CLS-003 | pytest (service + real FastAPI app) | All 23 `test_rc032_*` tests pass. (1) `looks_mni` accepts MNI152 grids (FSL 1 mm and 2 mm, ICBM 2009c, 4-D). It rejects oblique, anisotropic/clinical, permuted, off-centre (25 mm) and transform-less (sform and qform code 0) grids, including those the first version of the gate accepted. (2) `generate_zone_map_atlas` refuses a non-MNI image. (3) Atlas classification of internal-order lesions equals the orientation-consistent reference, including on a cubic grid; a zone map of another grid is refused. (4) classify-regions and generate-zone-map are alive, with spacing from the source image. (5) `msmask` on a non-MNI image gives 422; `auto` falls back with `atlas_unavailable_reason`; `msmask` on an MNI image classifies. (6) A persisted zone map is never reused, even on an MNI image. (7) generate-zone-map refuses a non-MNI image and keeps the existing zone maps, works on an MNI image, and refuses a zone map as the parcellation. (8) A zone map is neither auto-detected nor accepted as an explicit parcellation. (9) The geometric path uses the brain outline, is refused on sagittal and reversed slices, reorders and checks the image, and refuses a mismatched image instead of dropping it. Negative controls executed and recorded in `docs/iec62304/records/risk_verification/RC-032_negative_controls_2026-09-28.json` | DONE 2026-09-28 (backend/tests/unit/test_rc032_region_atlas_guard.py) |
| LesionDashboard — atlas-unavailable and geometric warnings (RC-032, HAZ-005, REQ-SAFE-021) | UI-RC032 | vitest | All 4 `rc032` tests pass. (1) An amber alert is rendered whenever the response carries `atlas_unavailable_reason`. (2) The warning is translated in every shipped locale (en, es, de) and names MNI space. (3) Geometric regions always carry a least-accurate warning. (4) The panel no longer promises SynthSeg or a "best" automatic method. Negative controls: same record | DONE 2026-09-28 (frontend/src/components/LesionDashboard.rc032.test.ts) |
| MAGNIMS labelling bound to code (CAPA-006 PA-6.1, HAZ-005) | UT-LBL-001 | pytest (document scan) | All 48 tests pass. (1) IFU-001 §10.3 states the value of each `PV/JC/IT_DISTANCE_THRESHOLD_MM` read from the code, and states that the atlas path is limited to MNI-space images with no registration. (2) In each of the 15 listed labelling/design documents and Class C source files, the withdrawn 3/4/3 mm thresholds, a "two-tier" MAGNIMS cascade, "only published, validated" and "~90 % / ~70 %" accuracy claims appear only within one line of a CAPA-006 note. (3) A listed file that is missing fails the test. (4) The patterns catch every phrasing actually issued. Negative controls: same record, section PA-6.1 | DONE 2026-09-28 (backend/tests/unit/test_capa006_labelling_bound_to_code.py) |
| DICOM-SEG | UT-SEG-001..008 | pytest | Valid DICOM-SEG structure | DONE (test_dicom_seg.py) |
| DICOM Utils | UT-DICOM-001..007 | pytest | File meta, patient info, image info, spatial, pixel data, save, extract metadata, DICOM-SEG creation | DONE (test_dicom_utils.py — 250 lines) |
| NIfTI Utils | UT-NII-001 | pytest | Load/transpose round-trip correct | DONE (test_nifti_utils.py) |
| Edge AI | UT-EDGE-001 | vitest | Preprocessing output correct shape | TO DO |

> **Note**: Class C unit test files added April 2026. All 8 Class C backend modules now have unit tests (dicom_utils covered separately by test_dicom_utils.py in addition to test_dicom_seg.py). Tests run in CI pipeline (`python -m pytest tests/unit/ -v --cov`). Coverage reports uploaded as GitHub Actions artifacts.

### 1.6 Integration Verification

| Integration Path | Test IDs | Method | Status |
|-----------------|---------|--------|--------|
| Auth endpoints | IT-AUTH-001..005 | pytest + httpx | DONE (5 tests) |
| DICOMweb endpoints | IT-PACS-001..005 | pytest + httpx | DONE (5 tests) |
| FHIR endpoints | IT-FHIR-001..004 | pytest + httpx | DONE (4 tests) |
| Segmentation pipeline | IT-SEG-001 | test_endpoints.sh | PARTIAL |
| AI pipeline end-to-end | IT-AI-001 | Manual | TO DO |

---

## 2. Validation Activities (Did we build the right thing?)

### 2.1 System Testing (Requirement Verification)

Each requirement in SRS-001 must have at least one system test demonstrating implementation. See Traceability Matrix (TM-001) for the complete mapping.

**Current coverage**: 23 of 91 requirements have formal tests (25%).
**Target**: 100% of "Must" requirements (72 items).

### 2.2 Usability Validation

Per IEC 62366-1:2015+A1:2020:
- Task completion for critical clinical workflows
- Error rate assessment
- System Usability Scale (SUS) questionnaire

**Status**: TO DO — requires clinical user participation.

### 2.3 Clinical Validation (AI Components)

Per MDCG 2020-1:
- AI segmentation performance on reference dataset
- Volumetry accuracy against manual measurement
- MAGNIMS classification agreement with expert consensus. This is required to re-assess HAZ-005. UT-CLS-002 and UI-RC010 only verify that no uncalibrated confidence is emitted or displayed. They do not measure region-assignment accuracy on any path, so the HAZ-005 residual risk remains UNDETERMINED until this study is done (added 2026-09-28).
- Report quality assessment by clinical reviewers

**Status**: TO DO — requires clinical study (see Strategic Roadmap Phase 4).

---

## 3. Test Environment

| Environment | Purpose | Configuration |
|-------------|---------|--------------|
| Local development | Unit testing | Node 20 + Python 3.11 + local Firestore emulator |
| CI (GitHub Actions) | Automated verification | Ubuntu latest, Node 18, Python 3.11 |
| Staging (Cloud Run) | Integration testing | Same as production, separate project |
| Production | System testing + validation | Cloud Run + Firebase Hosting |

---

## 4. Test Documentation Requirements

Per IEC 62304 Clause 9.8, test documentation shall include:
- Test ID and description
- Software version tested (Git SHA)
- Test environment configuration
- Expected result
- Actual result
- Pass/fail determination
- Date of execution
- Tester identification
- Any anomalies discovered

---

## 5. Pass/Fail Criteria

| Level | Criteria | Authority |
|-------|---------|-----------|
| Unit | 100% pass rate for Class C units | Developer |
| Integration | 100% of endpoint tests pass | QA |
| System | 100% of critical (Must) requirements verified | Project Lead |
| Validation | Clinical expert sign-off | Clinical Advisor |

---

### References

[1] IEC 62304:2006+AMD1:2015, Clauses 5.1.6, 5.5, 5.6, 5.7, 5.8
[2] IEC 62366-1:2015+AMD1:2020, Usability engineering
[3] MDCG 2020-1, Clinical evaluation of medical device software
