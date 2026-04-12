# MSTool-AI: Document Control Procedure

**Document ID**: QP-001 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: ISO 13485:2016 — Clause 4.2.4

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Purpose

This procedure defines how quality management system documents are created, reviewed,
approved, distributed, and maintained for MSTool-AI. It ensures that only current,
approved documents are available at points of use and that obsolete documents are
promptly removed or clearly identified.

## 2. Scope

This procedure applies to all QMS documents including quality manuals, procedures,
specifications, plans, records, and templates used in the design, development, and
maintenance of MSTool-AI.

## 3. Document Numbering Convention

All controlled documents follow a structured identifier:

| Prefix | Category | Example |
|--------|----------|---------|
| QM | Quality Manual | QM-001 Quality Manual |
| QP | Quality Procedure | QP-001 Document Control |
| SDP | Software Development Plan | SDP-001 |
| SRS | Software Requirements Specification | SRS-001 |
| RMF | Risk Management File | RMF-001 |
| TPL | Template | TPL-001 CAPA Form |
| SAD | Software Architecture Description | SAD-001 |
| DD | Detailed Design | DD-001 |
| VVP | Verification & Validation Plan | VVP-001 |
| REL | Release Record | REL-001 |
| CMP | Change Management Plan | CMP-001 |
| SPR | Software Problem Report | SPR-001 |

Each document version follows semantic numbering: Major.Minor (e.g., 1.0, 1.1, 2.0).
Major increments indicate significant changes; minor increments indicate corrections or
clarifications.

## 4. Approval Workflow

All documents pass through a three-stage approval process:

1. **Author** — Drafts or revises the document and submits for review.
2. **Reviewer** — Performs technical review for accuracy and completeness. At least one
   reviewer with domain expertise is required.
3. **QMS Manager** — Grants final approval. Only the QMS Manager (or delegate) can mark
   a document as "Approved."

Documents must not be distributed or referenced until they reach "Approved" status.

## 5. Version Control via Git

All QMS documents are stored in the project Git repository under `docs/`. Git provides:

- Full change history with author, date, and commit message for every revision.
- Pull request reviews serve as the Reviewer approval step.
- Merge to `main` by the QMS Manager constitutes final approval.
- Tags (e.g., `qms-v1.0`) mark formal QMS baselines.

Every commit that modifies a controlled document must reference the document ID in the
commit message (e.g., "Update QP-001 v1.1 — clarify review cycle").

## 6. Review Cycle

All QMS documents must be reviewed at least **annually** to ensure continued suitability.
The QMS Manager maintains a review schedule. Reviews assess:

- Alignment with current regulatory requirements (EU MDR, ISO 13485, IEC 62304).
- Consistency with actual practices.
- Incorporation of lessons learned from audits and CAPAs.

Review outcomes are recorded in the Management Review minutes (see QP-003).

## 7. Obsolete Document Handling

When a document is superseded or withdrawn:

1. The file is moved to a `docs/archive/` directory with an `_OBSOLETE` suffix.
2. The Git history preserves the original content for traceability.
3. References to the obsolete document in other procedures are updated within 30 days.
4. The document register is updated to reflect "Obsolete" status.

Obsolete documents must never be used for active work.

## 8. Electronic Records

Formal quality records (audit reports, CAPA evidence, test results, review minutes) are
stored in `docs/iec62304/records/`. Each record file includes:

- Record ID and title.
- Date of creation.
- Author or responsible party.
- Associated document or process reference.

Records are retained for the lifetime of the product plus 5 years, consistent with
EU MDR Article 10(8). Records must not be altered after approval; corrections require
a new record referencing the original.

## 9. References

- ISO 13485:2016, Clause 4.2.4 — Control of Documents
- ISO 13485:2016, Clause 4.2.5 — Control of Records
- EU MDR 2017/745, Article 10(8) — Documentation retention
- IEC 62304:2006+A1:2015, Clause 5.1.1 — Software development plan
