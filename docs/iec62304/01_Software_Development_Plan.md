# MSTool-AI: Software Development Plan

## IEC 62304 Clause 5.1 Compliant Development Lifecycle

**Document ID**: SDP-001
**Version**: 1.2 DRAFT (2026-10-22 — CAPA-012: who records an approval, a review record per PR, `main` protection stated as it is; §3.3, §4.4, §7.1, §7.2, new §7.4, §9; **PENDING owner approval**; v1.1 is in open PR #49, merge after #49) — v1.1 (2026-10-17 — AI coding agent declared as a development tool, §4.2, §4.4, §9; PENDING owner approval in PR #49)
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

*(v1.2 DRAFT, CAPA-012 — PENDING owner approval.)* A gate is passed only when its approval is recorded as §7.4 requires: by an action of the approver himself, never by the AI coding agent. The reviewer's part of G2 and G3 is the review record of §7.4 (b).

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
   approval. *(v1.2 DRAFT, CAPA-012 — PENDING owner approval; v1.1 said "recorded in the
   controlled documents with the PR number" and did not say who writes the record.)* The approval
   is recorded **by the owner himself**, as §7.4 (a) requires. The agent writes
   `PENDING owner approval` and never writes an approval line, an "Approved By" value, a signature
   or a sign-off date. Class C modules are flagged in every PR.
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
- *(v1.2 DRAFT, CAPA-012.)* Approval lines written by the agent: all 31 lines recording the
  owner's approval in 19 controlled documents (2026-09-28 and 2026-10-17) were written by the agent
  from approvals the owner gave in chat; no formal review on any of 56 pull requests. Caught by
  the agent harness refusing to write such lines (2026-10-17 to 2026-10-21; a tool behaviour, not
  a control of this plan) and by the paper H case study. Controls now: §7.4 and CAPA-012 PA-12.1
  (proposed). The 31 historical lines are kept unchanged and read as agent-transcribed
  (CAPA-012 §6).

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
- **Branching**: all changes via pull requests. *(v1.2 DRAFT, CAPA-012 — PENDING owner approval.
  v1.0 and v1.1 said "`main` branch protected". On 2026-10-22 `main` was **not** protected: the
  GitHub API returned "Branch not protected" and the repository had no rulesets. Required by
  CAPA-012 CA-12.3: pull request required, one approving review, code-owner review on Class C
  paths and regulatory documents, the CI jobs as required checks, signed commits, no direct
  pushes, administrators not exempt.)*
- **Releases**: Git tags with semantic versioning

### 7.2 Change Control

1. All changes submitted as pull requests
2. PR requires: description, impact analysis, CI pipeline pass
3. Code review required before merge — *(v1.2 DRAFT, CAPA-012)* evidenced by the review record
   and the owner's decision of §7.4 (b)
4. `test_endpoints.sh` verification before and after backend deployment

### 7.3 SOUP Management

- Dependencies pinned in `package.json` and `requirements.txt`
- SOUP inventory maintained in SOUP-001 document
- Vulnerability scanning: `npm audit` + `pip-audit` (to be added to CI)

### 7.4 Approval and Review Records (v1.2 DRAFT, CAPA-012 — PENDING owner approval)

**(a) Who records an approval.** An approval, sign-off, gate decision or release decision is
valid only when its record is created by an action of the approver that the AI coding agent
cannot perform:
1. an **owner-executed sign-off commit**: made by the owner in his own session, without the
   agent's `Co-Authored-By` trailer and without the Claude Code footer, signed with a key the agent
   cannot use (hardware security key, or a passphrase-protected key never loaded into the agent's
   environment) and shown as "Verified" by GitHub; it replaces `PENDING owner approval` by the
   approval line(s) for the pull request it names; or
2. a **formal GitHub review** (state APPROVED) given in the GitHub web interface, with two-factor
   authentication, from the owner's account on a pull request authored by the agent's own,
   separate identity (CAPA-012 CA-12.3).

Until the separate agent identity and branch protection exist, only (a) 1 produces a valid
approval. The agent may draft any document but never writes an approval line, an "Approved By"
value, a signature or a sign-off date; where an approval is pending it writes
`PENDING owner approval`.

**(b) Review record per pull request.** Before merge, every pull request has:
1. at least one adversarial review report by a reviewer session that did not author the change —
   scope, findings, verdict (approve / block), the author's responses — stored as
   `docs/iec62304/records/code_reviews/CR-PR<N>_<date>.md` (structure of TPL-03) and linked from the
   pull request; and
2. the owner's decision (approve / approve with conditions / reject), recorded as (a) requires.

For a pull request that touches a Class C module, the review record states that the review
sessions are not independent of the authoring agent in the sense of IEC 62304 and
ISO 13485 §7.3.5, until an independent human reviewer is appointed (§9; CAPA-012 CA-12.5).

**(c) Check in CI** (CAPA-012 PA-12.1, proposed, not yet implemented): a job fails when a line
recording an approval is added to a controlled document by a commit that carries the agent's
trailer or footer, or — once (a) 1 is in force — by a commit not signed by the owner's key.

**(d) Historical approvals.** The 31 lines recording the owner's approval that were written
between 2026-09-28 and 2026-10-17 were written by the agent from approvals the owner gave in chat
(CAPA-012 §6). They are not invalidated and not rewritten; they are read as agent-transcribed.
Retrospective confirmation by the owner: PENDING owner approval (CAPA-012 D-3).

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
| **Reviewer** | Code review, design review, independence from author. *(v1.2 DRAFT, CAPA-012: no person holds this role today; the review sessions of §4.4 control 3 are not independent of the author. To be appointed before any regulatory submission — CA-12.5)* |
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
