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
- MAGNIMS classification agreement with expert consensus
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
