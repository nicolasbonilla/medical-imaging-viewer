# MSTool-AI: Design Control Procedure

**Document ID**: QP-006 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: ISO 13485:2016 — Clause 7.3

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Purpose

This procedure defines how design and development activities for MSTool-AI are
planned, controlled, reviewed, verified, and validated. It maps ISO 13485 design
control requirements to the IEC 62304 software lifecycle framework used by the
project.

## 2. Scope

This procedure applies to all design and development activities for MSTool-AI,
including new features, architectural changes, AI model integration, and
safety-critical modifications to Class C modules.

## 3. Design Control Mapping to IEC 62304

The following table maps ISO 13485 Clause 7.3 sub-clauses to MSTool-AI project
documents and IEC 62304 activities:

| ISO 13485 Activity | IEC 62304 Activity | MSTool-AI Document |
|--------------------|--------------------|-------------------|
| Design Input | Software Requirements Analysis | SRS-001 Software Requirements Specification |
| Design Output | Software Architecture, Detailed Design | SAD-001 Architecture Description, DD-001 Detailed Design |
| Design Review | Quality Gate Reviews | Gates G1 through G5 (see Section 5) |
| Design Verification | Software Verification | VVP-001 Verification & Validation Plan |
| Design Validation | Clinical/User Evaluation | CEP-001 Clinical Evaluation Plan, UEF-001 Usability Evaluation |
| Design Transfer | Software Release | REL-001 Release Record |
| Design Changes | Change Management | CMP-001 Change Management Plan |

## 4. Design and Development Planning

Each design activity is planned in the Software Development Plan (SDP-001) which
defines:

- Development phases and milestones.
- Roles and responsibilities for each phase.
- Required reviews, verifications, and validations.
- Risk management activities per ISO 14971 and RMF-001.
- SOUP evaluation requirements per QP-005.

The plan is updated when scope, schedule, or resources change materially.

## 5. Quality Gates

Five quality gates govern the progression of design activities:

### G1 — Requirements Review
- **Entry**: Draft SRS-001 complete.
- **Criteria**: Requirements are unambiguous, testable, traceable, and risk-assessed.
- **Output**: Approved SRS-001 baseline.

### G2 — Architecture Review
- **Entry**: SAD-001 complete, risk controls identified in RMF-001.
- **Criteria**: Architecture addresses all requirements, safety-critical interfaces
  identified, SOUP components evaluated.
- **Output**: Approved SAD-001 baseline.

### G3 — Implementation Review
- **Entry**: Code complete for the release scope.
- **Criteria**: Code reviews passed for all changes (mandatory for Class C modules),
  static analysis clean, unit tests passing.
- **Output**: Code baseline tagged in Git.

### G4 — Verification Review
- **Entry**: VVP-001 test execution complete.
- **Criteria**: All test cases passed or deviations justified, requirement traceability
  matrix complete, no unresolved Critical/Major defects.
- **Output**: Verification report approved.

### G5 — Validation and Release Review
- **Entry**: Clinical evaluation (CEP-001) and usability evaluation (UEF-001) complete.
- **Criteria**: Validation evidence demonstrates fitness for intended use, risk/benefit
  analysis acceptable, regulatory submission materials ready.
- **Output**: REL-001 Release Record approved, deployment authorized.

## 6. Design Input, Output, Verification, and Validation

- **Design Input** (SRS-001): Functional, performance, safety, regulatory, and
  interface requirements. Reviewed at Gate G1.
- **Design Output** (SAD-001, DD-001, code, tests): Must be traceable to inputs,
  meet acceptance criteria, and identify safety-essential characteristics.
- **Verification** (VVP-001): Unit tests, integration tests (`test_endpoints.sh`),
  static analysis, code review, and requirements traceability matrix.
- **Validation** (CEP-001, UEF-001): Clinical evaluation with representative data,
  usability testing with radiologists/neurologists, performance validation.

## 7. Design Changes

All changes follow CMP-001 and are assessed for impact on requirements, risk
controls, regression risk, and re-verification needs. Class C module changes
require mandatory code review per CLAUDE.md.

## 8. References

- ISO 13485:2016, Clause 7.3 — Design and Development
- IEC 62304:2006+A1:2015, Clauses 5.1-5.8
- ISO 14971:2019 — Risk Management
- SRS-001, SAD-001, DD-001, VVP-001, CEP-001, UEF-001, REL-001, CMP-001, RMF-001
