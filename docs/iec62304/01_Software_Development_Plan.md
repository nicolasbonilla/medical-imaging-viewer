# MSTool-AI: Software Development Plan

## IEC 62304 Clause 5.1 Compliant Development Lifecycle

**Document ID**: SDP-001
**Version**: 1.1 (2026-10-17 — AI coding agent declared as a development tool, §4.2, §4.4, §9)
**Effective Date**: April 12, 2026
**Software Safety Class**: IEC 62304 Class C

---

## 1. Purpose and Scope

### 1.1 Product Description

MSTool-AI is a cloud-native web application for AI-assisted Multiple Sclerosis brain MRI analysis. See SRS-001 for complete requirements specification.

### 1.2 Intended Purpose

As defined in RMF-001 Section 2.1: MSTool-AI is intended as a decision-support tool for qualified healthcare professionals, providing visualization, quantification, and monitoring of brain MRI findings in MS patients. All outputs require physician review before clinical action.

### 1.3 Safety Classification

IEC 62304 Software Safety Class C per RMF-001 Section 3 (death or serious injury possible). Amendment 1 software item-level decomposition applied (see Master Compliance Document Section 3.4).

---

## 2. References

| Document | ID | Description |
|----------|-----|-------------|
| Software Requirements Specification | SRS-001 | Requirements (106 items) |
| Risk Management File | RMF-001 | ISO 14971 risk analysis (14 hazards, 22 controls) |
| Master Compliance Document | IEC62304-MASTER-001 | Clause-by-clause assessment |
| Technical Documentation | TD-001 | Architecture and algorithms |
| **QMS Platform** | **QMS-001** | **AI-powered compliance automation ([mstool-ai-qms.web.app](https://mstool-ai-qms.web.app))** |

---

## 3. Development Lifecycle Model

### 3.1 Model: Iterative Incremental with Quality Gates

MSTool-AI follows an **iterative incremental** development model with quality gates at each iteration boundary. Each iteration produces a potentially deployable increment.

```
Iteration N:
  [Requirements] → [Design] → [Implementation] → [Verification] → [Release]
      ↑                                                                ↓
      └────────────── Feedback / Risk Update ──────────────────────────┘
```

### 3.2 Phase Definitions

| Phase | Entry Criteria | Activities | Exit Criteria | Deliverables |
|-------|---------------|------------|---------------|-------------|
| **Planning** | New feature request or change | Requirements analysis, risk assessment, design | Requirements reviewed and approved | Updated SRS, risk assessment |
| **Design** | Approved requirements | Architecture/detailed design for affected items | Design review passed | Updated SAD/DD |
| **Implementation** | Approved design | Coding, unit testing, code review | All unit tests pass, code review approved | Source code, test results |
| **Integration** | All units implemented | Integration testing | Integration tests pass | Integration test results |
| **System Test** | Integration verified | System testing against requirements | All requirement tests pass | System test results |
| **Release** | System test passed | Release package, deployment | Deploy verified, anomalies documented | Release notes, deployment record |

### 3.3 Quality Gates

| Gate | Condition | Authority |
|------|-----------|-----------|
| G1: Requirements Approved | SRS requirements reviewed, risk assessment complete | Project Lead |
| G2: Design Approved | Architecture/detailed design reviewed | Project Lead + Reviewer |
| G3: Implementation Complete | Code review passed, unit tests pass, CI green | Reviewer |
| G4: Integration Verified | Integration tests pass, endpoint verification | QA |
| G5: Release Approved | System tests pass, known anomalies acceptable, risk controls verified | Project Lead |

---

## 4. Standards, Methods, and Tools

### 4.1 Coding Standards

| Language | Standard | Enforcement |
|----------|----------|-------------|
| TypeScript | ESLint + TypeScript strict mode | CI pipeline (GitHub Actions) |
| Python | PEP 8 + type annotations | CI pipeline (syntax check) |

### 4.2 Development Tools

| Tool | Purpose | Version |
|------|---------|---------|
| VS Code | IDE | Latest |
| Git | Version control | Latest |
| GitHub | Repository, PR workflow, CI/CD | Cloud |
| Vite | Frontend build | 5.4.8 |
| Docker | Backend containerization | Latest |
| Cloud Build | Backend CI/CD | Google Cloud |
| Firebase CLI | Frontend deployment | Latest |
| Claude Code (Anthropic) — AI coding agent | Drafts code, tests, lifecycle documents and CAPA records under the owner's direction (§4.4). Holds no approval authority | Model recorded per commit in the `Co-Authored-By` trailer (e.g. Claude Opus 5.5) |

### 4.3 Programming Languages

| Language | Rationale |
|----------|-----------|
| TypeScript 5.6 | Type safety, React ecosystem, WebGL/WebGPU access |
| Python 3.11 | Scientific computing ecosystem (NumPy, SciPy, nibabel), FastAPI async performance |

### 4.4 AI-Assisted Development (declared 2026-10-17)

**Why this section exists.** IEC 62304 §5.1.4 requires the plan to state the methods and tools used
to develop Class C software. An AI coding agent has written most of this repository: on
2026-10-17, 327 of 388 commits carried its `Co-Authored-By` trailer. Until v1.1 the plan did not
say so.

**Scope.** The agent drafts source code, tests, negative-control scripts, design and lifecycle
documents, and CAPA records. It does not approve, merge or release anything.

**Controls applied to agent output:**
1. **Human approval.** No change reaches `main` or production without the owner's explicit
   approval, recorded in the controlled documents with the PR number. Class C modules are flagged
   in every PR.
2. **Verification that can fail.** Every risk control is bound to tests that exercise behaviour,
   preferably real requests. Negative controls (deliberate mutations, one at a time, with every
   anchor asserted unique) must show that the tests detect the removal of each sub-control. The
   records are kept under `records/risk_verification/`.
3. **Adversarial review.** Separate review agents try to refute each change before the owner
   decides. Their findings are recorded, including withdrawn claims.
4. **Operational guards.**
   - The backend is deployed only through `scripts/deploy_backend.sh`, which always targets the
     `brain-mri-476110` project; `cloudbuild.yaml` refuses any other project (PR #44).
   - The agent never changes the global cloud configuration.
5. **Attribution.** Each commit carries the agent's trailer, so its contribution can be measured.

**Failure modes observed, and the control that now catches each:**
- Verification that read source text instead of observing behaviour (CAPA-001, -006, -007, -009).
  It let an inert authorization dependency pass as VERIFIED. Control 2 now catches this.
- Inaccurate self-reports in drafted records. Caught by controls 2 and 3.
- A deployment to the wrong cloud project (2026-10-17). Caught by control 4.

**Known limitation.** Review agents are not independent of the authoring agent, in the sense of
IEC 62304 §5.5.x and ISO 13485 §7.3.5. An **independent human reviewer for Class C changes**
remains a gap; it must be closed before any regulatory submission.

---

## 5. Verification Plan

### 5.1 Unit Verification (Class C)

- **Scope**: All Class C software units (7 units identified)
- **Method**: Automated pytest (backend) and vitest (frontend)
- **Acceptance criteria**: Per SRS-001 requirements + boundary conditions + invalid input robustness
- **Evidence**: Test reports archived in CI artifacts

### 5.2 Integration Verification

- **Scope**: Frontend ↔ Backend API, Backend ↔ External Services
- **Method**: `test_endpoints.sh` (9-point verification) + integration test suite
- **Evidence**: CI pipeline results

### 5.3 System Verification

- **Scope**: All SRS-001 requirements
- **Method**: Traceability matrix (TM-001) linking each requirement to test
- **Evidence**: System test report with pass/fail per requirement

---

## 6. Risk Management Activities

Per RMF-001:
- Hazard identification at each iteration (new features assessed)
- Risk control measures implemented as safety requirements (REQ-SAFE-xxx)
- Risk control verification through dedicated tests (TEST-SAFE-xxx)
- Risk file updated with each release

---

## 7. Configuration Management

### 7.1 Repository

- **Platform**: GitHub (https://github.com/nicolasbonilla/medical-imaging-viewer)
- **Branching**: `main` branch protected, all changes via pull requests
- **Releases**: Git tags with semantic versioning

### 7.2 Change Control

1. All changes submitted as pull requests
2. PR requires: description, impact analysis, CI pipeline pass
3. Code review required before merge
4. `test_endpoints.sh` verification before and after backend deployment

### 7.3 SOUP Management

- Dependencies pinned in `package.json` and `requirements.txt`
- SOUP inventory maintained in SOUP-001 document
- Vulnerability scanning: `npm audit` + `pip-audit` (to be added to CI)

---

## 8. Documentation Plan

| Document | Owner | Review Frequency |
|----------|-------|-----------------|
| SDP-001 (this document) | Project Lead | Per release |
| SRS-001 | Development Team | Per feature change |
| RMF-001 | Risk Management Authority | Per release + incident |
| SAD (Technical Documentation) | Development Team | Per architecture change |
| DD-001 (Detailed Design) | Development Team | Per Class C unit change |
| TM-001 (Traceability Matrix) | QA | Per release |
| SOUP-001 | Development Team | Monthly (vulnerability check) |

---

## 9. Roles and Responsibilities

| Role | Responsibilities |
|------|-----------------|
| **Project Lead** | SDP ownership, quality gate approval, risk management authority |
| **Developer** | Implementation, unit testing, code documentation |
| **Reviewer** | Code review, design review, independence from author |
| **QA** | Integration/system testing, traceability verification |
| **Clinical Advisor** | Clinical risk assessment, intended use validation |
| **Regulatory Affairs** | Standard compliance, audit preparation |
| *AI coding agent (tool, §4.4)* | *Drafts code, tests and documents. Not a role holder: no review independence, no approval authority* |

---

## 10. Maintenance Plan

### 10.1 Problem Resolution

Per SPR-001: All problems reported via GitHub Issues, evaluated for safety impact, resolved through change control process.

### 10.2 SOUP Monitoring

Monthly review of:
- NVD (National Vulnerability Database) for known CVEs in SOUP items
- npm audit / pip-audit automated reports
- SOUP vendor release notes for security patches

### 10.3 Post-Market Surveillance

- User feedback collection through structured reporting
- AI model performance monitoring (quarterly)
- Risk file review (annually or after significant change)

---

*End of Software Development Plan*
