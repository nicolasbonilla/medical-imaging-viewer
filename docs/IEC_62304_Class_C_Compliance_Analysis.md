# MSTool-AI: IEC 62304 Class C Compliance Analysis

## Gap Assessment for Regulatory Audit Preparation

**Standard**: IEC 62304:2006 + Amendment 1:2015 — Medical device software — Software life cycle processes
**Classification**: Class C (Death or serious injury possible)
**Date**: April 2026
**Status**: Pre-Audit Gap Assessment

---

## 1. Classification Justification

### Why Class C

MSTool-AI's AI-powered outputs can directly influence clinical decisions about Multiple Sclerosis diagnosis and treatment:

| Hazardous Situation | Potential Harm | Severity |
|-------------------|---------------|----------|
| AI segmentation produces incorrect lesion boundaries | Wrong surgical planning, missed lesions | Death / Serious injury |
| Volumetry calculates wrong brain volumes | Missed atrophy, delayed treatment | Serious injury |
| AI report generates misleading clinical text | Wrong treatment decision | Death / Serious injury |
| Edge AI screening shows "normal" for abnormal brain | Missed pathology, delayed diagnosis | Death / Serious injury |
| Incorrect MAGNIMS region classification | Wrong MS staging, inappropriate treatment | Serious injury |
| DICOM orientation error in 3D view | Surgeon operates on wrong location | Death / Serious injury |
| Longitudinal tracking mismatches lesions | Missed disease progression | Serious injury |

**Conclusion**: Class C is appropriate. The software can contribute to hazardous situations resulting in death or serious injury.

### Amendment 1 Decomposition Opportunity

Per Amendment 1 Clause 4.3, individual software items may be classified at lower levels if adequate segregation (5.3.5) is demonstrated:

| Software Item | Proposed Class | Rationale |
|--------------|---------------|-----------|
| AI Segmentation Pipeline (Vertex AI + ONNX) | **C** | Direct diagnostic impact |
| Brain Volumetry Service | **C** | Quantitative clinical measurements |
| AI Report Generation (Claude API) | **C** | Clinical text influencing decisions |
| Lesion Analysis / DIS Assessment | **C** | MS staging criteria |
| MAGNIMS Region Classifier | **C** | Treatment-affecting classification |
| DICOM/NIfTI Orientation Handling | **C** | Patient safety (laterality) |
| Longitudinal Tracking | **B** | Monitoring, not primary diagnosis |
| Image Viewer (2D/3D rendering) | **B** | Display only, no computation |
| Patient Management UI | **A** | Administrative, no clinical impact |
| Authentication / User Management | **B** | Access control, indirect safety |
| i18n / Styling / Layout | **A** | No clinical impact |

**Segregation requirement**: Must demonstrate that Class A/B items cannot corrupt Class C item behavior.

---

## 2. Section-by-Section Compliance Assessment

### Section 5: Software Development Process

#### 5.1 — Software Development Planning

| Clause | Requirement | Status | Evidence | Gap |
|--------|-------------|--------|----------|-----|
| 5.1.1 | Software Development Plan | **PARTIAL** | README.md, Strategic_Roadmap | No formal SDP document with lifecycle model |
| 5.1.2 | Keep plan updated | **PARTIAL** | Git history shows evolution | No formal version-controlled plan |
| 5.1.3 | Reference to system design | **PARTIAL** | Technical_Documentation.md | No formal system-level design document |
| 5.1.4 | Standards, methods, tools | **PARTIAL** | package.json, requirements.txt | Not formalized in a planning document |
| 5.1.5 | Integration testing planning | **PARTIAL** | test_endpoints.sh, CI/CD | No formal integration test plan |
| 5.1.6 | Verification planning | **PARTIAL** | GitHub Actions CI | No formal verification plan |
| 5.1.7 | Risk management planning | **NOT DONE** | — | No formal risk management plan |
| 5.1.8 | Documentation planning | **PARTIAL** | docs/ directory | No formal documentation plan |
| 5.1.9 | Configuration management planning | **PARTIAL** | Git, Cloud Build | No formal CM plan |
| 5.1.10 | Supporting items control | **PARTIAL** | Node 20, Python 3.11 documented | Not formalized |
| 5.1.11 | CI control before verification | **DONE** | GitHub Actions runs before merge | — |

#### 5.2 — Software Requirements Analysis

| Clause | Requirement | Status | Evidence | Gap |
|--------|-------------|--------|----------|-----|
| 5.2.1 | Define software requirements | **PARTIAL** | Features documented in README, Technical Docs | No formal SRS with unique requirement IDs |
| 5.2.2 | Requirements content (a-l) | **PARTIAL** | Functional reqs documented; security, usability partially | Missing: formal performance reqs, installation reqs, networking reqs |
| 5.2.3 | Risk control in requirements | **NOT DONE** | — | Risk controls not traced to requirements |
| 5.2.4 | Re-evaluate risk analysis | **NOT DONE** | — | No formal risk analysis exists |
| 5.2.5 | Update requirements | **PARTIAL** | Git history | No formal change tracking for requirements |
| 5.2.6 | Verify requirements | **NOT DONE** | — | No formal requirements review record |

#### 5.3 — Software Architectural Design

| Clause | Requirement | Status | Evidence | Gap |
|--------|-------------|--------|----------|-----|
| 5.3.1 | Architecture from requirements | **DONE** | Technical_Documentation.md Section 2 | Formalize as SAD |
| 5.3.2 | Interface architecture | **PARTIAL** | REST API documented, TypeScript types | Not all interfaces formally specified |
| 5.3.3 | SOUP functional requirements | **NOT DONE** | — | No SOUP requirements documentation |
| 5.3.4 | SOUP hardware/software requirements | **PARTIAL** | Node 20, Python 3.11, browser reqs | Not formalized per SOUP item |
| 5.3.5 | Segregation for risk control | **NOT DONE** | — | No formal segregation analysis |
| 5.3.6 | Verify architecture | **NOT DONE** | — | No formal architecture review record |

#### 5.4 — Software Detailed Design (CLASS C SPECIFIC)

| Clause | Requirement | Status | Evidence | Gap |
|--------|-------------|--------|----------|-----|
| 5.4.1 | Subdivide into software units | **PARTIAL** | Code is modular (services, hooks, stores) | No formal unit decomposition document |
| 5.4.2 | Detailed design per unit | **PARTIAL** | Code comments, JSDoc, docstrings | No formal detailed design specs for Class C units |
| 5.4.3 | Interface detailed design | **PARTIAL** | TypeScript types, Pydantic models | Not formally documented as design artifacts |
| 5.4.4 | Verify detailed design | **NOT DONE** | — | No formal design review records |

#### 5.5 — Software Unit Implementation and Verification

| Clause | Requirement | Status | Evidence | Gap |
|--------|-------------|--------|----------|-----|
| 5.5.1 | Implement units | **DONE** | 224+ files, ~84K LOC | — |
| 5.5.2 | Unit verification process | **PARTIAL** | 35+ tests, code reviews via PRs | No formal verification process document |
| 5.5.3 | Acceptance criteria (a-h) | **PARTIAL** | Error handling exists, boundary checks | Not formally documented per unit |
| 5.5.4 | Additional Class C criteria (a-e) | **PARTIAL** | Input validation (Pydantic), coding standards (ESLint/TypeScript) | No formal robustness testing with invalid inputs |
| 5.5.5 | Unit verification evidence | **PARTIAL** | Test results in CI | Not all Class C units have tests |

#### 5.6 — Software Integration and Integration Testing

| Clause | Requirement | Status | Evidence | Gap |
|--------|-------------|--------|----------|-----|
| 5.6.1 | Integrate per plan | **DONE** | CI/CD pipeline | — |
| 5.6.2 | Verify integration | **PARTIAL** | test_endpoints.sh (9 checks) | Limited coverage |
| 5.6.3 | Integration testing | **PARTIAL** | 35+ automated tests | No formal integration test procedures |
| 5.6.4 | Test interface compliance | **PARTIAL** | API tests exist | Not all interfaces tested |
| 5.6.5 | Verify against architecture | **NOT DONE** | — | No formal verification record |
| 5.6.6 | Test procedure evaluation | **NOT DONE** | — | Test procedures not formally reviewed |
| 5.6.7 | Regression testing | **PARTIAL** | CI runs on every push | No formal regression test strategy document |

#### 5.7 — Software System Testing

| Clause | Requirement | Status | Evidence | Gap |
|--------|-------------|--------|----------|-----|
| 5.7.1 | Tests for each requirement | **NOT DONE** | — | No requirement-to-test traceability |
| 5.7.2 | Requirements as test criteria | **NOT DONE** | — | No formal SRS to trace from |
| 5.7.3 | Re-test after changes | **DONE** | CI/CD runs automatically | — |
| 5.7.4 | Verify test content | **NOT DONE** | — | No formal test review |
| 5.7.5 | Evaluate anomalies | **PARTIAL** | Known anomaly list in audit report | Not formal |

#### 5.8 — Software Release

| Clause | Requirement | Status | Evidence | Gap |
|--------|-------------|--------|----------|-----|
| 5.8.1 | Verification completeness | **PARTIAL** | test_endpoints.sh pre/post deploy | No formal release checklist |
| 5.8.2 | Document known anomalies | **DONE** | Software_Audit_Report.md | — |
| 5.8.3 | Evaluate anomalies | **PARTIAL** | Documented in audit report | No formal risk assessment per anomaly |
| 5.8.4 | Document released versions | **DONE** | Git tags, COMMIT_SHA in Cloud Run | — |
| 5.8.5 | Release activities documented | **PARTIAL** | cloudbuild.yaml, deploy commands in README | No formal release procedure |
| 5.8.6 | Activities complete | **PARTIAL** | CI/CD checks | No formal release gate |
| 5.8.7 | Archive software | **DONE** | Git repository, Cloud Build artifacts | — |
| 5.8.8 | Reliable delivery | **DONE** | Firebase + Cloud Build reproducible | — |

### Section 6: Software Maintenance

| Clause | Requirement | Status | Gap |
|--------|-------------|--------|-----|
| 6.1 | Maintenance plan | **NOT DONE** | No formal maintenance plan |
| 6.2 | Problem and modification analysis | **PARTIAL** | GitHub issues used | No formal impact analysis process |
| 6.3 | Modification implementation | **PARTIAL** | Git PRs | No formal re-verification requirement |

### Section 7: Software Risk Management

| Clause | Requirement | Status | Gap |
|--------|-------------|--------|-----|
| 7.1 | Identify hazardous situations | **PARTIAL** | Listed in this document | No formal ISO 14971 risk analysis file |
| 7.2 | Risk control measures | **PARTIAL** | Disclaimers, validation exist | Not traced to requirements |
| 7.3 | Verify risk controls | **NOT DONE** | — | No verification evidence |
| 7.4 | Manage changes | **NOT DONE** | — | No formal change risk analysis |

### Section 8: Software Configuration Management

| Clause | Requirement | Status | Gap |
|--------|-------------|--------|-----|
| 8.1.1 | Configuration identification | **DONE** | Git SHAs, version pinning | — |
| 8.1.2 | Identify SOUP | **PARTIAL** | package.json, requirements.txt | No formal SOUP BOM with all required metadata |
| 8.1.3 | System configuration docs | **PARTIAL** | env.yaml, .env.production | — |
| 8.2 | Change control | **DONE** | Git PRs, CI/CD | — |
| 8.3 | Configuration status accounting | **DONE** | Git history | — |

### Section 9: Software Problem Resolution

| Clause | Requirement | Status | Gap |
|--------|-------------|--------|-----|
| 9.1 | Problem reports | **PARTIAL** | GitHub Issues | No formal problem report template |
| 9.2 | Investigate problems | **PARTIAL** | Done ad-hoc | No formal investigation process |
| 9.3 | Advise relevant parties | **NOT DONE** | — | No formal communication procedure |
| 9.4 | Use change control | **DONE** | Git PRs | — |
| 9.5 | Maintain records | **DONE** | Git history, commit messages | — |
| 9.6 | Analyze trends | **NOT DONE** | — | No trend analysis |
| 9.7 | Verify resolution | **PARTIAL** | CI/CD tests | Not formally documented |
| 9.8 | Test documentation content | **PARTIAL** | CI logs | Missing: tester identity, test environment details |

---

## 3. Compliance Summary

### Scorecard

| Section | Clauses | Compliant | Partial | Not Done | Compliance % |
|---------|---------|-----------|---------|----------|-------------|
| 5.1 Development Planning | 11 | 1 | 9 | 1 | 50% |
| 5.2 Requirements Analysis | 6 | 0 | 3 | 3 | 25% |
| 5.3 Architecture Design | 6 | 1 | 3 | 2 | 42% |
| 5.4 Detailed Design (Class C) | 4 | 0 | 3 | 1 | 38% |
| 5.5 Unit Implementation | 5 | 1 | 4 | 0 | 60% |
| 5.6 Integration Testing | 7 | 1 | 3 | 3 | 36% |
| 5.7 System Testing | 5 | 1 | 1 | 3 | 30% |
| 5.8 Release | 8 | 4 | 3 | 1 | 69% |
| 6 Maintenance | 3 | 0 | 2 | 1 | 33% |
| 7 Risk Management | 4 | 0 | 2 | 2 | 25% |
| 8 Configuration Management | 5 | 3 | 2 | 0 | 80% |
| 9 Problem Resolution | 8 | 2 | 4 | 2 | 50% |
| **TOTAL** | **72** | **14** | **39** | **19** | **47%** |

### Overall Status: **47% Compliant** — Significant work required for full Class C compliance.

---

## 4. Critical Gaps (Must Fix Before Audit)

### Priority 1 — Documents That Must Exist

| Document | IEC 62304 Clause | Status | Effort |
|----------|-----------------|--------|--------|
| **Software Development Plan (SDP)** | 5.1.1 | Missing | 2 weeks |
| **Software Requirements Specification (SRS)** | 5.2.1-5.2.6 | Missing | 3 weeks |
| **Risk Management File (ISO 14971)** | 7.1-7.4 | Missing | 3 weeks |
| **Software Architecture Description (SAD)** | 5.3.1-5.3.6 | Partial (Technical Docs exist) | 1 week |
| **Detailed Design Specification** | 5.4.1-5.4.4 | Missing for Class C units | 2 weeks |
| **SOUP Bill of Materials** | 8.1.2 | Missing formal BOM | 1 week |
| **Traceability Matrix** | 5.2.6, 5.7.1 | Missing | 2 weeks |
| **Software Maintenance Plan** | 6.1 | Missing | 1 week |

### Priority 2 — Processes That Must Be Documented

| Process | Clause | Status | Effort |
|---------|--------|--------|--------|
| **Change Control Procedure** | 8.2 | Informal (Git PRs) | 3 days |
| **Problem Resolution Procedure** | 9.1-9.7 | Informal (GitHub Issues) | 3 days |
| **Code Review Procedure** | 5.5.2 | Informal | 2 days |
| **Release Procedure** | 5.8.1-5.8.8 | Informal (deploy scripts) | 2 days |
| **Regression Test Strategy** | 5.6.7 | Informal (CI/CD) | 2 days |
| **SOUP Monitoring Process** | 6.2 (Amd 1) | Not done | 2 days |

### Priority 3 — Verification Evidence

| Evidence | Clause | Status | Effort |
|----------|--------|--------|--------|
| **Unit test coverage for Class C units** | 5.5.5 | ~35 tests, low coverage | 3 weeks |
| **Formal code review records** | 5.5.2, 5.5.4 | Not documented | Ongoing |
| **Architecture review record** | 5.3.6 | Not done | 2 days |
| **Detailed design review records** | 5.4.4 | Not done | 1 week |
| **Integration test procedures** | 5.6.3 | Informal | 1 week |
| **System test procedures (per requirement)** | 5.7.1 | Not done | 2 weeks |
| **Risk control verification** | 7.3 | Not done | 1 week |

---

## 5. Estimated Timeline to Full Compliance

| Phase | Duration | Activities |
|-------|----------|-----------|
| **Phase A** (Weeks 1-4) | 4 weeks | SDP, SRS, Risk Management File, SOUP BOM |
| **Phase B** (Weeks 5-8) | 4 weeks | SAD formalization, Detailed Design specs, Traceability Matrix |
| **Phase C** (Weeks 9-14) | 6 weeks | Unit tests for Class C units, Integration test procedures, System test procedures |
| **Phase D** (Weeks 15-18) | 4 weeks | Code review records, Verification evidence, Release procedures |
| **Phase E** (Weeks 19-20) | 2 weeks | Pre-audit review, gap closure, mock audit |

**Total estimated effort: 20 weeks (5 months) with 1 full-time regulatory/quality engineer**

---

## 6. SOUP Bill of Materials (Draft)

### Frontend Critical SOUP

| Name | Manufacturer | Version | Safety Class | Risk if Fails |
|------|-------------|---------|-------------|---------------|
| React | Meta Platforms | 18.3.1 | B | UI fails to render clinical data |
| TypeScript | Microsoft | 5.6.2 | A | Build-time only |
| Vite | Evan You / Vite Team | 5.4.8 | A | Build-time only |
| onnxruntime-web | Microsoft | 1.21.0 | **C** | Edge AI misclassification |
| zustand | Daishi Kato | 4.5.5 | B | State corruption affects overlay |
| @tanstack/react-query | Tanner Linsley | 5.56.2 | B | Stale data displayed |
| @niivue/niivue | NiiVue Team | 0.67.0 | B | 3D rendering errors |
| framer-motion | Framer | 12.23 | A | Animation only |
| i18next | i18next contributors | 25.6.3 | A | Translation only |
| lucide-react | Lucide contributors | 0.447.0 | A | Icons only |
| axios | Matt Zabriskie | 1.7.7 | B | API communication failure |

### Backend Critical SOUP

| Name | Manufacturer | Version | Safety Class | Risk if Fails |
|------|-------------|---------|-------------|---------------|
| FastAPI | Sebastian Ramirez | 0.115.0 | B | API unavailable |
| numpy | NumPy Team | 1.26.4 | **C** | Volumetry calculation errors |
| scipy | SciPy Team | 1.13.1 | **C** | EDT/connected component errors |
| nibabel | NiBabel Team | 5.3.0 | **C** | NIfTI parsing/orientation errors |
| pydicom | pydicom contributors | 2.4.4 | **C** | DICOM parsing errors |
| SimpleITK | Insight Software | 2.3.1 | B | Image processing errors |
| anthropic | Anthropic | 0.44.0 | **C** | Report generation errors |
| google-cloud-aiplatform | Google | 1.136.0 | **C** | AI inference errors |
| webauthn | Duo Labs | 2.7.1 | B | Authentication bypass |
| firebase-admin | Google | 7.1.0 | B | Storage/auth failures |
| scikit-image | scikit-image Team | 0.24.0 | B | Image analysis errors |
| python-jose | Michael Davis | 3.3.0 | B | Token validation errors |

---

## 7. Recommendations

### For the Audit

1. **Be transparent about current status**. The codebase is functionally complete and well-architected. The gaps are primarily in formal documentation, not in code quality.

2. **Use the decomposition strategy** (Amendment 1). Classify individual items, not the entire system. This reduces the scope of Class C documentation to ~6 critical services.

3. **Leverage existing artifacts**. The Technical Documentation, README, audit report, and Production Readiness Analysis contain substantial content that can be formalized into IEC 62304-compliant documents.

4. **Prioritize the Risk Management File**. This is the single most impactful document — it drives the safety classification, requirements, and testing strategy.

5. **Start with the traceability matrix**. This forces formalization of requirements, design, and test mapping.

---

*This analysis is based on IEC 62304:2006 + Amendment 1:2015. Consult with a regulatory affairs specialist for formal audit preparation.*
