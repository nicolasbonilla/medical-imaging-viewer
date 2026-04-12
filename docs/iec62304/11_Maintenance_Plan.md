# MSTool-AI: Software Maintenance Plan

## IEC 62304 Section 6 — Post-Release Software Maintenance

**Document ID**: SMP-001
**Version**: 1.0
**Effective Date**: April 12, 2026

---

## 1. Scope

This plan defines the process for maintaining MSTool-AI after initial release, including problem resolution, change management, SOUP monitoring, and post-market surveillance activities.

---

## 2. Maintenance Activities

### 2.1 Problem Resolution

All software problems are handled per SPR-001 (Problem Resolution Procedure). Key activities:

| Activity | Trigger | Frequency | Responsible |
|----------|---------|-----------|-------------|
| Problem triage | New issue reported | Within 24 hours | Developer |
| Safety impact assessment | Each problem | Per problem | Risk Management Authority |
| Root cause analysis | Critical/Major problems | Per problem | Developer |
| Fix verification | Each fix | Per fix | Reviewer |
| Regression testing | Each fix | Per fix | CI pipeline |

### 2.2 Change Management

All modifications follow the change control process defined in CMP-001:

1. Change request documented (GitHub Issue)
2. Impact analysis (affected requirements, design, risk controls)
3. If safety-impacted → update RMF-001 before implementation
4. Implementation via Git PR with code review
5. Verification (unit + integration + system tests as applicable)
6. Release per REL-001

### 2.3 SOUP Monitoring (IEC 62304 A1:2015, IEC 81001-5-1:2021)

| Activity | Frequency | Method | Responsible |
|----------|-----------|--------|-------------|
| npm audit (frontend) | Monthly + per release | `npm audit --audit-level=high` | Developer |
| pip-audit (backend) | Monthly + per release | `pip-audit --strict` | Developer |
| NVD CVE review | Monthly | Manual check for Class C SOUP | Developer |
| SOUP vendor releases | Monthly | Check changelogs for security patches | Developer |
| SOUP update assessment | Per finding | Impact analysis + regression test | Developer + QA |

**Class C SOUP items requiring priority monitoring**:
- ONNX Runtime Web (SOUP-FE-008) — AI inference engine
- nibabel (SOUP-BE-004) — NIfTI parsing
- pydicom (SOUP-BE-005) — DICOM parsing
- NumPy (SOUP-BE-007) — Computational foundation
- SciPy (SOUP-BE-008) — EDT, connected components
- Anthropic SDK (SOUP-BE-011) — Report generation API
- Google Cloud AI Platform (SOUP-BE-012) — AI inference proxy

### 2.4 Post-Market Surveillance

Per EU MDR Article 83 and MDCG 2019-16 Rev.1:

| Activity | Frequency | Method | Output |
|----------|-----------|--------|--------|
| User feedback collection | Continuous | Structured reporting form | Trend analysis |
| Clinical performance review | Quarterly | Compare AI metrics to baseline | Performance report |
| Regulatory landscape monitoring | Quarterly | MDCG guidance, standard updates | Compliance update |
| Risk management file review | Annually | Formal review meeting | Updated RMF-001 |
| Periodic Safety Update Report (PSUR) | Per EU MDR schedule | Comprehensive safety review | PSUR document |

### 2.5 AI Model Performance Monitoring

| Metric | Baseline | Monitoring Frequency | Alert Threshold |
|--------|----------|---------------------|----------------|
| Segmentation Dice score | Established at validation | Quarterly | Decline > 5% from baseline |
| Volumetry correlation | Established at validation | Quarterly | r < 0.90 |
| Report quality score | Established at validation | Quarterly | Clinical reviewer score < 7/10 |
| Edge AI sensitivity | Established at validation | Quarterly | Decline > 10% from baseline |

---

## 3. Vigilance and Reporting

### 3.1 Serious Incident Reporting (EU MDR Article 87)

If a problem is assessed as a serious incident (contributed to or could contribute to death or serious deterioration of health):

1. **Immediate** (within 24 hours): Report to competent authority (BfArM in Germany)
2. **Within 15 days**: Submit initial report via EUDAMED
3. **Ongoing**: Follow-up reports as investigation progresses
4. **Final**: Trend report if applicable

### 3.2 Field Safety Corrective Action (FSCA)

If a corrective action is needed to reduce risk of serious incident:
1. Document FSCA scope and rationale
2. Implement correction (software update, usage restriction, or device recall)
3. Issue Field Safety Notice to affected users
4. Report FSCA to competent authority

---

## 4. End of Support

When MSTool-AI reaches end of support:
1. Notify all users 12 months in advance
2. Provide migration path for clinical data
3. Archive all regulatory documentation
4. Submit final PSUR
5. Maintain archived records per retention schedule

---

### References

[1] IEC 62304:2006+AMD1:2015, Section 6 (Software maintenance process)
[2] IEC 81001-5-1:2021, Clause 5.3.12 (Vulnerability management)
[3] EU MDR 2017/745, Articles 83–86 (Post-market surveillance), Article 87 (Vigilance)
[4] MDCG 2019-16 Rev.1, Cybersecurity for medical devices
[5] MDCG 2020-7, Post-market clinical follow-up plan template
