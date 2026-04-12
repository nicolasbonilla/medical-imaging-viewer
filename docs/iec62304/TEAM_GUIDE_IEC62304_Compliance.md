# MSTool-AI: Team Operating Guide for IEC 62304 Class C Compliance

## Practical Step-by-Step Instructions for Every Team Member

**Document ID**: GUIDE-001
**Version**: 1.0
**Date**: April 12, 2026
**Audience**: ALL team members — developers, reviewers, QA, project lead, clinical advisor

---

## IMPORTANT — READ FIRST

MSTool-AI is classified as **IEC 62304 Software Safety Class C** — the highest safety class. This means a software failure could contribute to **death or serious injury**. Every person working on this software has a responsibility to follow these procedures. A government audit will verify that these procedures are followed for EVERY change.

**The auditor will:**
- Pick random Git commits and trace them to requirements, risk analysis, and tests
- Pick random requirements and trace them to code and verification evidence
- Ask to see signed review records, test results, and problem reports
- Check that templates (PDFs in `docs/iec62304/templates/`) are being used

---

## 1. FOR DEVELOPERS — Daily Workflow

### Step 1: Before Starting Any Work

```
□ Check GitHub Issues for assigned task
□ Identify which requirement(s) the task implements
  → Open docs/iec62304/02_Software_Requirements_Specification.md
  → Find the REQ-ID (e.g., REQ-FUNC-040)
  → If no requirement exists, STOP and create one first

□ Check if the task touches a Class C module:
  → If YES: read the risk analysis for that module in RMF-001
  → If YES: your PR will need extra scrutiny

□ Create a feature branch from main:
  git checkout -b feature/REQ-FUNC-040-description
```

### Step 2: While Writing Code

```
□ Follow coding standards:
  → TypeScript: ESLint rules + TypeScript strict mode
  → Python: PEP 8 + type annotations

□ For Class C modules:
  → Add input validation for ALL external inputs
  → Handle ALL error cases (no silent failures)
  → Add unit tests for the change
  → Document safety-related behavior in code comments

□ Write meaningful commit messages:
  git commit -m "feat(REQ-FUNC-040): Implement volume computation

  Implements voxel counting with normative percentile comparison.
  Risk control RC-004 (volumetry displays percentile ranges).
  Unit test: UT-VOL-001"
```

### Step 3: Submitting a Pull Request

```
□ PR Title: "[REQ-ID] Brief description"
  Example: "[REQ-FUNC-040] Brain volumetry computation"

□ PR Description MUST include:
  - What: description of the change
  - Why: which requirement it implements
  - Risk: which hazards are affected (if any)
  - Tests: which tests verify the change
  - SOUP: any new dependencies added?

□ Ensure CI pipeline is GREEN before requesting review:
  → TypeScript check
  → Frontend build
  → Backend tests
  → SOUP vulnerability scan
  → Python syntax check

□ Request review from at least 1 team member
□ For Class C changes: request review from 2 team members
```

### Step 4: Code Review (as Reviewer)

```
□ Use the Code Review Checklist: docs/iec62304/templates/TPL-03_Code_Review_Checklist.pdf
□ Print or fill digitally — this is AUDIT EVIDENCE

□ Check every item on the checklist:
  GENERAL:
  □ Code implements the detailed design (DD-001)
  □ Coding standards followed
  □ No commented-out code without issue link

  SAFETY (Class B/C):
  □ Input validation for all external inputs
  □ Error handling covers all failure modes
  □ No unhandled exceptions
  □ Risk controls correctly implemented

  CLASS C SPECIFIC:
  □ No unintended functionality
  □ Robustness with invalid inputs
  □ SOUP APIs used correctly

□ Document your review result:
  → APPROVED / APPROVED WITH COMMENTS / REJECTED

□ SAVE the filled checklist as evidence:
  → Name: CR-YYYY-NNN_[module_name].pdf
  → Store in: docs/iec62304/records/code_reviews/
```

### Step 5: After Merge and Deploy

```
□ For backend changes:
  → Deploy: gcloud builds submit --config=cloudbuild.yaml --substitutions=COMMIT_SHA=$(git rev-parse --short HEAD)
  → Wait for build SUCCESS
  → Run: bash test_endpoints.sh
  → ALL 9 checks must PASS

□ For frontend changes:
  → Build: cd frontend && npm run build
  → Deploy: npx firebase deploy --only hosting
  → Verify the app loads correctly

□ Fill the deployment section of the Release Checklist (TPL-02) if this is a release
```

---

## 2. FOR QA / TESTERS — Testing Workflow

### Testing a Requirement

```
□ Find the requirement in SRS-001 (docs/iec62304/02_Software_Requirements_Specification.md)

□ For each requirement, use the Test Execution Report template:
  → docs/iec62304/templates/TPL-06_Test_Execution_Report.pdf

□ Fill in ALL fields:
  → Test ID: ST-FUNC-[number matching requirement]
  → Requirement Verified: REQ-FUNC-XXX
  → Software Version: git rev-parse --short HEAD
  → Test Environment: Browser version, OS
  → Tester: Your name
  → Date: Today

□ Write clear test steps:
  → Preconditions (what must be set up)
  → Step-by-step instructions (anyone should be able to follow)
  → Expected result (specific, measurable)

□ Execute the test and document:
  → Actual result (what actually happened)
  → PASS or FAIL
  → Any anomalies discovered

□ SAVE the filled report:
  → Name: ST-FUNC-XXX_[date].pdf
  → Store in: docs/iec62304/records/test_results/
```

### Testing a Risk Control

```
□ Find the risk control in RMF-001 (docs/iec62304/03_Risk_Management_File.md, Section 5)

□ Use the Risk Control Verification template:
  → docs/iec62304/templates/TPL-04_Risk_Control_Verification.pdf

□ For each of the 22 risk controls (RC-001 through RC-022):
  → Verify the control is implemented in the code
  → Test that it works correctly
  → Document the verification method and result
  → Sign and date

□ SAVE: RCV-RC-XXX_[date].pdf
  → Store in: docs/iec62304/records/risk_verification/
```

---

## 3. FOR PROJECT LEAD — Management Workflow

### Release Process

```
□ Before every release:
  1. Fill the Pre-Release Checklist (TPL-02_Release_Checklist.pdf)
  2. All 11 checks must be marked YES
  3. Document any known anomalies with risk assessment
  4. Sign the approval section

□ Quality gates:
  → Use TPL-10_Quality_Gate_Approval.pdf for each gate
  → G1 (Requirements) → G2 (Design) → G3 (Implementation) → G4 (Integration) → G5 (Release)
```

### Monthly Tasks

```
□ SOUP Vulnerability Review (MONTHLY):
  → Use TPL-07_SOUP_Vulnerability_Review.pdf
  → Run npm audit and pip-audit
  → Check NVD for 7 Class C SOUP items
  → Document findings and actions
  → Sign and date
  → Store in: docs/iec62304/records/soup_reviews/

□ Risk Management File Review (QUARTERLY):
  → Review RMF-001 for new hazards
  → Check if any changes introduced new risks
  → Update if needed
  → Document review in RMF-001 Section 7
```

### When a Bug is Found

```
□ Create GitHub Issue using the problem report format
  → Use TPL-01_Problem_Report.pdf for formal documentation

□ CRITICAL: Always assess safety impact:
  → Does this affect a Class C module?
  → Could this contribute to a hazardous situation?
  → Does this require regulatory notification (EU MDR Article 87)?

□ If safety-impacted:
  → Use TPL-08_Serious_Incident_Report.pdf
  → Notify regulatory authority within 24 hours if serious
  → Update RMF-001 if new hazard identified
```

### Document Approval

```
□ Use TPL-11_Document_Approval.pdf
□ All 15 IEC 62304 documents need formal approval signatures
□ Each document needs: Reviewer name + Approver name + Date + Signature
□ Store signed original in: docs/iec62304/records/approvals/
```

---

## 4. FOR CLINICAL ADVISOR — Clinical Workflow

### Risk Analysis Review

```
□ Review docs/iec62304/03_Risk_Management_File.md (RMF-001):
  → Are all 14 hazardous situations clinically accurate?
  → Are severity ratings appropriate?
  → Are risk control measures clinically adequate?
  → Is the benefit-risk analysis justified?

□ Sign off on the risk management file
  → Use TPL-05_Design_Review_Record.pdf
  → Document your clinical assessment
```

### Requirements Review

```
□ Review safety requirements (REQ-SAFE-001 through REQ-SAFE-020):
  → Are disclaimers clinically appropriate?
  → Is the "assistive tool" positioning clear?
  → Are confidence thresholds clinically meaningful?

□ Review AI-related requirements:
  → Are AI performance thresholds appropriate?
  → Is the de-identification approach adequate for HIPAA?
```

---

## 5. RECORD KEEPING — Where to Store Everything

### Folder Structure

```
docs/iec62304/records/
├── code_reviews/           ← Filled TPL-03 for each PR
│   ├── CR-2026-001_volumetry_service.pdf
│   ├── CR-2026-002_report_generation.pdf
│   └── ...
├── test_results/           ← Filled TPL-06 for each test
│   ├── ST-FUNC-001_load_nifti.pdf
│   ├── ST-FUNC-040_compute_volumes.pdf
│   └── ...
├── risk_verification/      ← Filled TPL-04 for each risk control
│   ├── RCV-RC-001_ai_disclaimer.pdf
│   ├── RCV-RC-004_volumetry_percentile.pdf
│   └── ...
├── soup_reviews/           ← Filled TPL-07 monthly
│   ├── SOUP-2026-04.pdf
│   ├── SOUP-2026-05.pdf
│   └── ...
├── releases/               ← Filled TPL-02 per release
│   ├── REL-v2.0.0.pdf
│   └── ...
├── design_reviews/         ← Filled TPL-05 per review
│   ├── DR-SAD-001_architecture.pdf
│   ├── DR-DD-AI-001_segmentation.pdf
│   └── ...
├── incidents/              ← Filled TPL-08 if needed
├── changes/                ← Filled TPL-09 per significant change
├── gate_approvals/         ← Filled TPL-10 per gate
└── approvals/              ← Filled TPL-11 document sign-off
```

### Naming Convention

```
[Template Type]-[ID]_[Description]_[Date].pdf

Examples:
  CR-2026-001_brain_volumetry_service_2026-04-15.pdf
  ST-FUNC-040_compute_volumes_2026-04-16.pdf
  RCV-RC-004_volumetry_percentile_display_2026-04-17.pdf
  SOUP-2026-04_monthly_review.pdf
  REL-v2.0.0_release_checklist_2026-04-20.pdf
```

---

## 6. QUICK REFERENCE — What Template to Use When

| Situation | Template | File |
|-----------|----------|------|
| I'm reviewing someone's code | Code Review Checklist | TPL-03 |
| I'm deploying a new version | Release Checklist | TPL-02 |
| I found a bug | Problem Report | TPL-01 |
| I'm testing a requirement | Test Execution Report | TPL-06 |
| I'm verifying a risk control works | Risk Control Verification | TPL-04 |
| I'm reviewing architecture/design | Design Review Record | TPL-05 |
| Monthly SOUP vulnerability check | SOUP Vulnerability Review | TPL-07 |
| A serious safety incident occurred | Serious Incident Report | TPL-08 |
| Making a significant code change | Change Control Record | TPL-09 |
| Approving a development phase gate | Quality Gate Approval | TPL-10 |
| Formally approving all documents | Document Approval Record | TPL-11 |

---

## 7. AUDIT PREPARATION CHECKLIST

When the audit is announced, verify:

```
□ All 15 IEC 62304 documents exist and are current version
□ All 11 PDF templates have been used (filled records exist)
□ Document Approval Record (TPL-11) is signed by authority
□ At least 1 filled Code Review Checklist per Class C module change
□ At least 1 filled Test Execution Report per "Must" requirement
□ All 22 Risk Control Verification records filled and signed
□ Monthly SOUP Vulnerability Reviews exist for the past 6 months
□ Release Checklists exist for each deployed version
□ Git history shows PR reviews on all changes to main branch
□ CI pipeline results are available (GitHub Actions artifacts)
□ test_endpoints.sh results available for pre/post deploy
□ No critical/major open bugs without safety assessment
```

---

## 8. COMMON MISTAKES TO AVOID

| Mistake | Why It's a Problem | What To Do Instead |
|---------|-------------------|-------------------|
| Pushing directly to main | No review evidence = audit failure | Always use pull requests |
| "Fix typo" commit without PR | Uncontrolled change = audit finding | Every change needs a PR, even typos |
| No commit message references | Auditor can't trace changes | Include REQ-ID or issue # in every commit |
| Skipping test_endpoints.sh | Can't prove deployment was verified | Run BEFORE and AFTER every deploy |
| Not filling PDF templates | No audit evidence exists | Fill templates and save as records |
| Ignoring SOUP vulnerabilities | Cybersecurity non-compliance | Monthly review is MANDATORY |
| Changing Class C code without review | IEC 62304 5.5.4 violation | ALWAYS get a code review for Class C |
| Not assessing safety impact of bugs | ISO 14971 violation | Every bug report must assess safety |

---

## 9. CONTACT AND ESCALATION

| Issue | Contact | Escalation |
|-------|---------|-----------|
| Code review question | Assigned reviewer | Project Lead |
| Safety concern about a change | Project Lead | Clinical Advisor |
| Serious incident suspected | Project Lead + Clinical Advisor | Regulatory Authority (BfArM) within 24h |
| SOUP vulnerability (critical) | Developer | Project Lead for risk assessment |
| Audit preparation question | Project Lead | Regulatory Affairs |

---

## 10. REFERENCES

All IEC 62304 documentation is in: `docs/iec62304/`
All fillable templates are in: `docs/iec62304/templates/`
All filled records go in: `docs/iec62304/records/`

| Document | Purpose |
|----------|---------|
| `00_IEC_62304_Master_Compliance_Document.md` | Overall compliance status |
| `02_Software_Requirements_Specification.md` | All 91 requirements |
| `03_Risk_Management_File.md` | 14 hazards, 22 risk controls |
| `06_Detailed_Design_Specification.md` | Class C unit designs |
| `05_Traceability_Matrix.md` | Requirement ↔ test mapping |

---

*This guide must be read by every team member before contributing to MSTool-AI. Acknowledgment of reading this guide should be documented.*

*Last updated: April 12, 2026 | Version 1.0*
