# MSTool-AI: Internal Audit Procedure

**Document ID**: QP-004 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: ISO 13485:2016 — Clause 8.2.2

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Purpose

This procedure defines the process for planning, conducting, and following up on
internal audits of the quality management system. Internal audits verify that QMS
processes conform to planned arrangements, applicable standards, and regulatory
requirements.

## 2. Scope

This procedure applies to all processes within the MSTool-AI quality management
system, including software development, risk management, CAPA, supplier management,
and post-market activities.

## 3. Annual Audit Program

The QMS Manager establishes an annual audit program that covers all QMS processes
over a 12-month cycle. The program considers:

- **Risk-based prioritization** — Higher-risk processes (Class C modules, AI
  segmentation, clinical reporting) are audited more frequently.
- **Previous audit results** — Processes with open findings receive priority.
- **Regulatory changes** — New or revised requirements trigger focused audits.
- **Process maturity** — Newly implemented processes are audited within 6 months.

The audit program is documented in `docs/iec62304/records/audit_program_YYYY.md`
and approved by the QMS Manager before the start of each calendar year.

## 4. Auditor Qualification

Internal auditors must meet the following requirements:

| Criterion | Requirement |
|-----------|------------|
| Independence | Must not audit their own work or direct area of responsibility |
| Training | Completed internal audit training (ISO 19011 principles) |
| Knowledge | Familiarity with ISO 13485, IEC 62304, and ISO 14971 |
| Experience | Participated in at least one audit as an observer before leading |

The QMS Manager maintains a register of qualified auditors. External auditors may
be engaged for specialized areas (e.g., cybersecurity, AI/ML validation).

## 5. Audit Criteria

Each audit is conducted against one or more of the following standards:

- **ISO 13485:2016** — Quality management system requirements.
- **IEC 62304:2006+A1:2015** — Software lifecycle processes.
- **ISO 14971:2019** — Risk management for medical devices.
- **EU MDR 2017/745** — Regulatory requirements, as applicable.
- **Internal procedures** — QP-001 through QP-007 and referenced documents.

## 6. Audit Process

### 6.1 Planning

The lead auditor prepares an audit plan including: scope, criteria, schedule,
auditee contacts, and document review checklist. The plan is communicated to
auditees at least 10 business days before the audit.

### 6.2 Document Review

Before the on-site (or remote) audit, the auditor reviews relevant documentation:
procedures, records, previous audit reports, and open CAPA items related to the
audit scope.

### 6.3 Execution

The audit sequence: (1) Opening meeting, (2) Evidence gathering (interviews,
document review, Git history, test results, deployment logs), (3) Finding
classification per Section 7, (4) Closing meeting with preliminary findings.

### 6.4 Reporting

The audit report is issued within 10 business days, including scope, criteria,
findings, evidence, and recommendations. Stored in
`docs/iec62304/records/audit_report_YYYY-MM-DD.md`.

### 6.5 Follow-Up

Findings requiring corrective action are tracked through QP-002 CAPA Procedure.
The auditor verifies closure of all findings before the next scheduled audit of the
same process area.

## 7. Finding Classification

| Classification | Definition | Action Required |
|---------------|-----------|-----------------|
| Major NCR | Absence or total breakdown of a required process; direct impact on product quality or safety | CAPA required, Critical or Major severity per QP-002 |
| Minor NCR | Isolated lapse in following a defined process; limited impact | CAPA required, Minor severity per QP-002 |
| Observation | Opportunity for improvement; no nonconformity identified | Noted in audit report; no CAPA required but may be tracked |

## 8. Records

Records maintained per audit cycle: annual program, audit plans, audit reports,
CAPA records for NCRs, and auditor qualifications. Retained per QP-001.

## 9. References

- ISO 13485:2016, Clause 8.2.2 — Internal Audit
- ISO 19011:2018 — Guidelines for Auditing Management Systems
- QP-001 Document Control, QP-002 CAPA Procedure
- QP-003 Management Review (audit results as review input)
