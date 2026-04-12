# MSTool-AI: Corrective and Preventive Action (CAPA) Procedure

**Document ID**: QP-002 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: ISO 13485:2016 — Clause 8.5

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Purpose

This procedure establishes a systematic process for identifying, investigating, and
resolving nonconformities through corrective and preventive actions. It ensures that
root causes are identified, effective actions are implemented, and recurrence is
prevented.

## 2. Scope

This procedure applies to all quality-related nonconformities affecting MSTool-AI,
including software defects, process deviations, and regulatory findings.

## 3. CAPA Triggers

A CAPA may be initiated from any of the following sources:

- **Customer complaints** — Reports received through QP-007 Complaints Handling.
- **Internal/external audit findings** — Nonconformities from QP-004 Internal Audit.
- **Nonconformance reports (NCRs)** — Product or process failures detected during
  development, testing, or deployment.
- **Trend analysis** — Patterns identified from software problem reports (SPR-001),
  support tickets, or monitoring dashboards.
- **Post-market surveillance (PMS)** — Field performance data, vigilance reports, or
  regulatory authority communications.
- **Management review outputs** — Actions identified during QP-003 reviews.

## 4. Process Flow

### 4.1 Detection and Initiation

Any team member may initiate a CAPA by filing an entry in the CAPA Register with:
CAPA ID, date opened, source/trigger, description of the nonconformity, and initial
severity classification.

### 4.2 Investigation

The assigned investigator gathers evidence including: affected software versions,
logs, user reports, test results, and relevant code changes. The investigation scope
must be sufficient to identify the true root cause.

### 4.3 Root Cause Analysis

Root cause analysis must use at least one structured method:

- **5 Whys** — For straightforward causal chains.
- **Fishbone (Ishikawa) diagram** — For multi-factor analysis.
- **Fault tree analysis** — For safety-critical issues in Class C modules.

The root cause must be documented with supporting evidence.

### 4.4 Action Planning

Define corrective actions (address root cause) and/or preventive actions (prevent
occurrence). Each action must have an owner, target date, and acceptance criteria.

### 4.5 Implementation

Actions follow standard change control. Software changes require code review,
testing per VVP-001, and release per REL-001.

### 4.6 Effectiveness Verification

The CAPA owner verifies the nonconformity has not recurred, acceptance criteria are
met, and no new risks introduced (RMF-001). Verification occurs after minimum 30
days or one release cycle.

## 5. Timelines

| Severity | Investigation Complete | Action Plan Approved | Implementation | Verification |
|----------|----------------------|---------------------|----------------|-------------|
| Critical | 3 days | 7 days | 7 days | 30 days |
| Major | 10 days | 30 days | 30 days | 60 days |
| Minor | 30 days | 90 days | 90 days | 90 days |

**Critical** CAPAs involve patient safety risk or regulatory non-compliance.
**Major** CAPAs involve significant quality system deviations.
**Minor** CAPAs involve isolated process improvements.

## 6. CAPA Register

The CAPA Register is maintained in `docs/iec62304/records/capa_register.md` and
contains: CAPA ID, date opened, source, severity, description, root cause, actions,
owner, target dates, status, effectiveness result, and date closed.

## 7. Regulatory Reporting

CAPAs related to patient safety events must be assessed for regulatory reporting
obligations under EU MDR Article 87 (vigilance). If a field safety corrective action
(FSCA) is required, it must be coordinated with QP-007 Complaints Handling and
reported to the competent authority within mandated timelines.

## 8. Links to Software Problem Reports

Software defects tracked via SPR-001 may escalate to CAPA when:

- The defect affects patient safety or clinical accuracy.
- The defect recurs across multiple releases.
- Trend analysis reveals a systemic issue in the development process.

## 9. References

- ISO 13485:2016, Clause 8.5.2 — Corrective Action
- ISO 13485:2016, Clause 8.5.3 — Preventive Action
- EU MDR 2017/745, Article 87 — Vigilance Reporting
- QP-004 Internal Audit, QP-007 Complaints Handling
- SPR-001 Software Problem Report, RMF-001 Risk Management File
