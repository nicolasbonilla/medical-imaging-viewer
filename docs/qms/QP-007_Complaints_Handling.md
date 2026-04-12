# MSTool-AI: Complaints Handling Procedure

**Document ID**: QP-007 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: ISO 13485:2016 — Clause 8.2.1

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Purpose

This procedure defines how complaints related to MSTool-AI are received, recorded,
assessed for safety impact, investigated, and resolved. It ensures timely handling
of all customer feedback and compliance with regulatory reporting obligations.

## 2. Scope

This procedure applies to all complaints received about MSTool-AI, including reports
of software defects, clinical accuracy concerns, usability issues, data integrity
problems, and any communication alleging product inadequacy.

## 3. Complaint Channels

Complaints may be received through any of the following channels:

| Channel | Monitored By | Response SLA |
|---------|-------------|-------------|
| Email (support@mstool-ai.com) | Quality Engineer | 1 business day acknowledgment |
| In-app feedback form | Quality Engineer | 1 business day acknowledgment |
| Phone/video call | Project Lead | Immediate logging, 1 day follow-up |
| Regulatory authority notice | Regulatory Affairs | Same business day |
| Clinical site report | Clinical Advisor | 1 business day acknowledgment |

All channels are monitored during business hours.

## 4. Intake and Recording

Every complaint is recorded in `docs/iec62304/records/complaint_register.md` with:
Complaint ID (CMP-YYYY-NNN), date received, source/channel, product version,
description, initial classification (safety/non-safety + severity), and assignee.

## 5. Safety Assessment

A safety assessment is **mandatory** for every complaint, regardless of apparent
severity. The assessment determines whether the complaint involves:

- Actual or potential harm to a patient or user.
- Misdiagnosis risk due to incorrect segmentation, volumetry, or reporting.
- Data integrity loss affecting clinical decisions.
- Security breach exposing patient health information.

The safety assessment must be completed within **2 business days** of receipt. If
the complaint is determined to be safety-related, it is escalated immediately to
the QMS Manager and Regulatory Affairs.

## 6. Investigation

### 6.1 Non-Safety Complaints

The assigned investigator determines root cause using available evidence (logs,
screenshots, version history, user environment details). Investigation should be
completed within 30 days.

### 6.2 Safety-Related Complaints

Safety complaints require an expedited investigation:

- **Immediate containment** — Assess whether the affected software version should
  be restricted or a user advisory issued.
- **Root cause analysis** — Using structured methods per QP-002 Section 4.3.
- **Risk reassessment** — Update RMF-001 if a new hazard is identified or an
  existing risk control has failed.
- Investigation must be completed within **15 days**.

## 7. Regulatory Reporting

### 7.1 EU MDR Article 87 — Vigilance

The following reporting timelines apply under EU MDR vigilance requirements:

| Event Type | Reporting Deadline | Reported To |
|-----------|-------------------|------------|
| Serious incident — death or serious deterioration | Immediately, no later than 10 days | Competent authority via EUDAMED |
| Serious incident — other | Within 15 days | Competent authority via EUDAMED |
| Trend of non-serious incidents | Within 15 days of trend identification | Competent authority |
| Field safety corrective action (FSCA) | Before or concurrent with FSCA implementation | Competent authority + affected users |

### 7.2 FSCA Triggers

An FSCA is initiated when a complaint reveals a systematic safety defect, the
risk/benefit analysis no longer supports continued use, or a competent authority
requests corrective measures. Actions include software updates, user notification,
feature restriction, or recall. All FSCA communications require Regulatory Affairs
review.

## 8. Resolution and Closure

Resolution options: software fix (REL-001), user guidance, configuration adjustment,
or no action with documented rationale. Complaints close only after investigation is
complete, corrective actions verified, complainant notified, and safety assessment
recorded.

## 9. Trend Analysis

The Quality Engineer performs **quarterly** trend analysis to identify recurring
failure modes, patterns by version/site/user group, and emerging safety signals.
Findings are reported to Management Review (QP-003) and may trigger CAPA per
QP-002. Safety-related trends are escalated to Regulatory Affairs.

## 10. References

- ISO 13485:2016, Clause 8.2.1 — Feedback (Complaints)
- EU MDR 2017/745, Article 87 — Vigilance Reporting
- EU MDR 2017/745, Article 89 — Trend Reporting
- QP-002 CAPA Procedure, QP-003 Management Review
- RMF-001 Risk Management File, REL-001 Release Record
