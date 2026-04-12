# MSTool-AI: Management Review Procedure

**Document ID**: QP-003 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: ISO 13485:2016 — Clause 5.6

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Purpose

This procedure defines how top management reviews the quality management system at
planned intervals to ensure its continuing suitability, adequacy, and effectiveness.
Management review ensures the QMS remains aligned with organizational objectives,
regulatory requirements, and patient safety goals.

## 2. Scope

This procedure covers the planning, execution, documentation, and follow-up of
management reviews for the MSTool-AI quality management system.

## 3. Frequency

Management reviews are conducted at least **annually**. Additional reviews may be
convened when:

- Significant regulatory changes occur (e.g., new EU MDR implementing acts).
- Critical CAPA trends are identified.
- Major product releases or architectural changes are planned.
- External audit findings require management attention.

## 4. Attendees

The following roles are required attendees:

| Role | Responsibility |
|------|---------------|
| QMS Manager | Chairs the review, prepares the agenda |
| Project Lead | Reports on development status and technical risks |
| Regulatory Affairs | Reports on regulatory changes and compliance status |
| Quality Engineer | Presents CAPA, audit, and metrics data |
| Clinical Advisor | Provides clinical feedback and user perspective |

Additional participants may be invited based on the agenda. A quorum requires the
QMS Manager and at least two other required attendees.

## 5. Review Inputs

The QMS Manager ensures the following inputs are prepared and distributed at least
5 business days before the review:

1. **Audit Results** — Internal audit summaries (QP-004), external findings, open NCRs.
2. **Customer Feedback** — Complaint summaries (QP-007), usability feedback, feature requests.
3. **CAPA Status** — Open count by severity, closure rate, effectiveness results, themes.
4. **Quality Metrics** — Defect density, Class C test coverage, deployment success rate.
5. **PMS Data** — Field performance, vigilance reports (EU MDR Art 87), PSUR status.
6. **Regulatory Changes** — New/revised standards, EU MDR guidance, authority communications.
7. **Improvements** — Previous review recommendations, team proposals, technology updates.

## 6. Review Outputs

The management review must produce documented decisions regarding:

- **Improvement actions** — Specific changes to the QMS, processes, or product.
- **Resource allocation** — Staffing, tooling, or infrastructure needs.
- **Risk reassessment** — Updates to the risk management file (RMF-001).
- **Quality objectives** — Revised targets for the next review period.
- **Regulatory actions** — Steps to address compliance gaps.

Each output item must have an assigned owner and target completion date.

## 7. Meeting Minutes Template

Management review minutes are recorded using the following structure and stored in
`docs/iec62304/records/management_review_YYYY-MM-DD.md`:

```
# Management Review — [Date]
## Attendees: [Name, Role]
## Agenda Items Reviewed: [Input topic] — Summary
## Decisions Made: [Decision] — Owner: [Name], Due: [Date]
## Action Items: [#, Action, Owner, Due Date, Priority]
## Next Review Date: [Date]
```

## 8. Follow-Up

Action items from the management review are tracked in the CAPA Register (QP-002)
if they relate to nonconformities, or in the project task tracker for improvement
initiatives. Status of all action items is reported at the next management review.

## 9. References

- ISO 13485:2016, Clause 5.6 — Management Review
- ISO 13485:2016, Clause 5.6.2 — Review Input
- ISO 13485:2016, Clause 5.6.3 — Review Output
- QP-002 CAPA Procedure, QP-004 Internal Audit
- RMF-001 Risk Management File
