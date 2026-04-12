# MSTool-AI: Quality Manual

**Document ID**: QM-001 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: ISO 13485:2016 — Medical devices — Quality management systems

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Quality Policy

MSTool-AI is committed to developing safe, effective, and reliable AI-powered medical imaging software that meets or exceeds regulatory requirements and customer expectations. We achieve this through:

1. **Patient Safety First**: Every software decision prioritizes patient safety per IEC 62304 Class C requirements
2. **Regulatory Compliance**: Full compliance with EU MDR 2017/745, IEC 62304:2006+A1:2015, ISO 14971:2019, IEC 81001-5-1:2021, and EU AI Act 2024/1689
3. **Continuous Improvement**: Systematic monitoring, measurement, and improvement of quality processes
4. **Evidence-Based Development**: All clinical claims supported by validated clinical evidence
5. **Transparency**: Clear communication of software capabilities and limitations to users

## 2. Scope

### 2.1 QMS Scope

This Quality Management System applies to the design, development, deployment, and maintenance of **MSTool-AI**, a cloud-native Software as a Medical Device (SaMD) for:
- AI-assisted brain MRI segmentation for Multiple Sclerosis
- Brain volumetry and normative comparison
- MAGNIMS region classification per McDonald 2024 criteria
- Clinical report generation
- Longitudinal lesion tracking

### 2.2 Regulatory Classification

| Attribute | Classification |
|-----------|---------------|
| EU MDR Classification | Class IIa (Rule 11 — diagnostic software) |
| IEC 62304 Safety Class | Class C (highest — could contribute to death or serious injury) |
| EU AI Act | High-Risk AI System (Annex I, Section A) |
| IMDRF SaMD Category | Category III (serious condition, treat/diagnose) |
| Intended Users | Neuroradiologists, neurologists, MS specialists |
| Patient Population | Adults with suspected or confirmed Multiple Sclerosis |

### 2.3 Exclusions

ISO 13485 Clause 7.5.2 (Cleanliness of product) and Clause 7.5.5 (Particular requirements for sterile medical devices) are excluded as not applicable to software-only medical devices.

## 3. Organizational Structure

### 3.1 Key Roles and Responsibilities

| Role | Responsibility | Authority |
|------|---------------|-----------|
| **Project Lead / QMS Manager** | Overall QMS effectiveness, management review, regulatory submissions | Final approval on all QMS decisions |
| **Software Developer** | Code implementation per SDP-001, unit testing, code reviews | Commit to feature branches |
| **QA Engineer** | Test execution, verification records, SOUP monitoring | Accept/reject test results |
| **Clinical Advisor** | Clinical requirement review, risk analysis review, CER review | Clinical sign-off on risk acceptability |
| **Regulatory Affairs** | Regulatory strategy, Notified Body liaison, GSPR compliance | Regulatory submission approval |

### 3.2 Organizational Independence

Per ISO 14971 and IEC 62304, the following independence requirements are maintained:
- Code reviewers must not be the code author
- Risk analysis reviewed by a clinician independent of development
- QA verification performed by personnel not involved in implementation
- Internal audits conducted by personnel independent of the audited area

## 4. QMS Process Interactions

```
                    ┌──────────────────┐
                    │ Management Review │ ◄── Internal Audit
                    │     (QP-003)      │ ◄── CAPA Trends
                    └────────┬─────────┘ ◄── PMS Data
                             │
            ┌────────────────┼────────────────┐
            ▼                ▼                 ▼
    ┌───────────┐   ┌──────────────┐   ┌──────────────┐
    │  Design    │   │  Document    │   │  Supplier    │
    │  Control   │   │  Control     │   │  Evaluation  │
    │  (QP-006)  │   │  (QP-001)   │   │  (QP-005)    │
    └─────┬─────┘   └──────────────┘   └──────────────┘
          │
    ┌─────┴─────────────────────────────────┐
    │        Software Lifecycle              │
    │  (IEC 62304 — SDP-001)                │
    │                                        │
    │  Requirements → Architecture → Design  │
    │  → Implementation → V&V → Release     │
    └─────┬──────────────────────────┬──────┘
          │                          │
    ┌─────▼─────┐            ┌──────▼───────┐
    │ Complaints │            │    CAPA      │
    │ (QP-007)   │ ──────►   │  (QP-002)    │
    └────────────┘            └──────────────┘
```

## 5. Management Commitment

Top management ensures:
- The Quality Policy is communicated and understood at all levels
- Quality objectives are established and measurable
- Resources are available for QMS activities
- Management Reviews are conducted per QP-003
- Customer and regulatory requirements are determined and met
- Risk-based thinking is applied throughout product realization

## 6. Resource Management

### 6.1 Personnel Competence

All personnel performing work affecting product quality must be competent based on:
- Education and training records
- Relevant experience in medical device software
- Awareness of IEC 62304 Class C requirements
- Acknowledgment of reading GUIDE-001 (Team Operating Guide)

### 6.2 Infrastructure

| Component | Purpose | Provider |
|-----------|---------|----------|
| GitHub | Source code management, CI/CD, issue tracking | Microsoft |
| Google Cloud Run | Backend deployment | Google Cloud |
| Firebase Hosting | Frontend deployment | Google/Firebase |
| Firebase Firestore | Patient/study data storage | Google/Firebase |
| Google Cloud Storage | NIfTI/DICOM file storage | Google Cloud |
| Vertex AI | AI model inference | Google Cloud |
| Anthropic Claude API | Clinical report generation | Anthropic |

## 7. Document Control

All QMS documents are controlled per **QP-001 Document Control Procedure**. The document hierarchy is:

| Level | Type | Examples |
|-------|------|---------|
| 1 | Quality Manual | QM-001 |
| 2 | Quality Procedures | QP-001 through QP-007 |
| 3 | IEC 62304 Lifecycle Documents | SDP-001, SRS-001, RMF-001, etc. |
| 4 | Work Instructions & Templates | TPL-01 through TPL-11 |
| 5 | Records & Evidence | Code reviews, test results, risk verifications |

## 8. Referenced Documents

| Document | ID | Standard |
|----------|----|----------|
| Document Control Procedure | QP-001 | ISO 13485 Clause 4.2.4 |
| CAPA Procedure | QP-002 | ISO 13485 Clause 8.5 |
| Management Review Procedure | QP-003 | ISO 13485 Clause 5.6 |
| Internal Audit Procedure | QP-004 | ISO 13485 Clause 8.2.2 |
| Supplier Evaluation Procedure | QP-005 | ISO 13485 Clause 7.4 |
| Design Control Procedure | QP-006 | ISO 13485 Clause 7.3 |
| Complaints Handling Procedure | QP-007 | ISO 13485 Clause 8.2.1 |

---

*This Quality Manual is maintained under document control in the Git repository.*
