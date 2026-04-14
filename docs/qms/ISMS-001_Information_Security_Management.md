# MSTool-AI: Information Security Management System (ISMS)

## ISO 27001:2022 Annex A Controls — Mapping to Medical Device Security Requirements

**Document ID**: ISMS-001
**Version**: 1.0
**Effective Date**: April 14, 2026
**Standards**: ISO/IEC 27001:2022, IEC 81001-5-1:2021, IEC 62304:2006+A1:2015, EU MDR 2017/745 Annex I Section 17.2
**Classification**: Confidential — Regulatory Audit Use

---

| Version | Date | Author | Changes | Approved By |
|---------|------|--------|---------|-------------|
| 1.0 | 2026-04-14 | Development Team | Initial release — ISO 27001 Annex A control mapping | — |

---

## 1. Purpose and Regulatory Context

### 1.1 Purpose

This document establishes the Information Security Management System (ISMS) framework for MSTool-AI, mapping implemented security controls to ISO/IEC 27001:2022 Annex A. It serves as evidence of a systematic approach to managing sensitive medical imaging data and ensuring the security of a Class C medical device software.

### 1.2 Regulatory Hierarchy

The security requirements for MSTool-AI flow from multiple regulatory sources. The relationship between standards is critical for CE Marking:

```
┌─────────────────────────────────────────────────────────────────┐
│                    CE MARKING (EU MDR 2017/745)                  │
│                                                                  │
│  Annex I, Section 17.2: "IT security measures, including        │
│  protection against unauthorized access, shall be designed       │
│  according to the state of the art."                            │
│                                                                  │
│  → The "state of the art" for medical device cybersecurity:     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
┌──────────────────────┐  ┌──────────────────────────────┐
│ IEC 81001-5-1:2021   │  │ MDCG 2019-16 Rev.1          │
│ Health software       │  │ Guidance on Cybersecurity    │
│ cybersecurity         │  │ for Medical Devices          │
│ (MANDATORY for EU MDR)│  │                              │
│                       │  │ References ISO 27001 as      │
│ Clauses 5.3.1-5.3.13 │  │ "recognized framework"       │
└──────────┬────────────┘  └──────────────┬───────────────┘
           │                              │
           │    ┌─────────────────────────┘
           │    │
           ▼    ▼
┌──────────────────────────────────────────┐
│ ISO/IEC 27001:2022                        │
│ Information Security Management Systems   │
│                                           │
│ Provides the CONTROL FRAMEWORK            │
│ that IEC 81001-5-1 builds upon.           │
│                                           │
│ 93 controls in Annex A, organized in:     │
│ A.5  Organizational (37 controls)         │
│ A.6  People (8 controls)                  │
│ A.7  Physical (14 controls)               │
│ A.8  Technological (34 controls)          │
│                                           │
│ NOT mandatory for CE Marking, but         │
│ STRONGLY recommended by MDCG 2019-16     │
│ and provides evidence for IEC 81001-5-1   │
└──────────────────────────────────────────┘
```

### 1.3 Key Insight for Auditors

**ISO 27001 is not a direct CE Marking requirement.** The mandatory standard is **IEC 81001-5-1:2021**. However:

1. MDCG 2019-16 Rev.1 explicitly references ISO 27001 as a "recognized cybersecurity framework"
2. Notified Bodies increasingly expect ISO 27001 alignment as evidence of "state of the art" security
3. IEC 81001-5-1 clauses 5.3.1–5.3.13 map directly to ISO 27001 Annex A controls
4. Demonstrating ISO 27001 alignment strengthens the CE Marking Technical Documentation

**Our approach**: Implement IEC 81001-5-1 as the primary obligation, with ISO 27001 Annex A as the control framework, documented here.

---

## 2. Scope

### 2.1 ISMS Scope

This ISMS covers:
- **MSTool-AI application** (frontend + backend + infrastructure)
- **Medical imaging data** processed by the application (brain MRI, NIfTI, DICOM)
- **Patient data** stored in Firestore (demographics, study records)
- **AI model interactions** (Claude API, Vertex AI, ONNX models)
- **Third-party services** (Firebase, Cloud Run, Cloud Storage, GitHub)
- **QMS platform** (MSTool-AI-QMS — compliance automation)

### 2.2 Out of Scope

- Physical security of end-user devices (hospital responsibility)
- Network security of hospital infrastructure (covered by hospital ISMS)
- Clinical validation of AI model accuracy (covered by Clinical Evaluation Report)

---

## 3. ISO 27001:2022 Annex A Control Mapping

### 3.1 Organizational Controls (A.5)

| Control | Title | Implementation | IEC 81001-5-1 | Status |
|---------|-------|---------------|---------------|--------|
| A.5.1 | Policies for information security | Quality Manual (QM-001), CLAUDE.md development guidelines, this ISMS document | 5.3.1 | IMPLEMENTED |
| A.5.2 | Information security roles | RBAC: 4 roles (Viewer, Technician, Radiologist, Admin) with 15 permissions | 5.3.3 | IMPLEMENTED |
| A.5.3 | Segregation of duties | QMS Manager approves forms, Developer cannot self-approve Class C changes | 5.3.3 | IMPLEMENTED |
| A.5.7 | Threat intelligence | NVD CVE monitoring via QMS SOUP Monitor, npm audit + pip-audit in CI | 5.3.12 | IMPLEMENTED |
| A.5.8 | Information security in project management | IEC 62304 lifecycle with security gates, CLAUDE.md rules for all contributors | 5.3.1 | IMPLEMENTED |
| A.5.9 | Inventory of information | SOUP Bill of Materials (SOUP-001), CycloneDX SBOM, QMS dependency tracking | 5.3.11 | IMPLEMENTED |
| A.5.10 | Acceptable use | RBAC enforces acceptable use, audit trail logs all actions | 5.3.7 | IMPLEMENTED |
| A.5.14 | Information transfer | TLS 1.3 for all data in transit, HIPAA de-identification for AI API calls | 5.3.5 | IMPLEMENTED |
| A.5.23 | Information security for cloud services | Cloud Run (Google-managed TLS), Firebase (Google SOC 2/3), Firestore encryption | 5.3.5 | IMPLEMENTED |
| A.5.24 | Incident management planning | TPL-08 Serious Incident Report, QP-007 Complaints Handling | 5.3.1 | IMPLEMENTED |
| A.5.28 | Collection of evidence | Immutable audit trail in Firestore (QMS), structured JSON logs | 5.3.7 | IMPLEMENTED |
| A.5.29 | Information security during disruption | Cloud Run auto-scaling, multi-zone Firestore, GCS versioning | 5.3.8 | PARTIAL |
| A.5.30 | ICT readiness for business continuity | Cloud Run 0→N auto-scaling, no single points of failure | 5.3.8 | IMPLEMENTED |
| A.5.36 | Compliance with policies | QMS automated compliance scoring (97.1% IEC 62304, 93.9% Cybersecurity) | 5.3.1 | IMPLEMENTED |

### 3.2 People Controls (A.6)

| Control | Title | Implementation | IEC 81001-5-1 | Status |
|---------|-------|---------------|---------------|--------|
| A.6.1 | Screening | GitHub account verification, Firebase Auth identity verification | — | IMPLEMENTED |
| A.6.3 | Information security awareness | QMS Operational Guide (QMS-OPG-001), CLAUDE.md mandatory reading | — | IMPLEMENTED |
| A.6.5 | Responsibilities after termination | Firebase Auth account deactivation, QMS role revocation | 5.3.2 | IMPLEMENTED |
| A.6.8 | Information security event reporting | TPL-01 Problem Report, TPL-08 Incident Report, QMS audit trail | 5.3.7 | IMPLEMENTED |

### 3.3 Physical Controls (A.7)

| Control | Title | Implementation | IEC 81001-5-1 | Status |
|---------|-------|---------------|---------------|--------|
| A.7.9 | Security of assets off-premises | Cloud-only deployment — no on-premises assets. All data in Google Cloud. | — | N/A (Cloud) |
| A.7.10 | Storage media | No local storage of PHI. All data in Firestore/GCS with encryption at rest. | 5.3.5 | IMPLEMENTED |
| A.7.14 | Secure disposal or re-use of equipment | Firestore document deletion, GCS object deletion with lifecycle policies | 5.3.5 | IMPLEMENTED |

### 3.4 Technological Controls (A.8)

| Control | Title | Implementation | IEC 81001-5-1 | Status |
|---------|-------|---------------|---------------|--------|
| A.8.1 | User endpoint devices | Browser-based SPA — no installation required, no local data persistence | — | IMPLEMENTED |
| A.8.2 | Privileged access rights | Admin role requires explicit assignment, CODEOWNERS for Class C modules | 5.3.3 | IMPLEMENTED |
| A.8.3 | Information access restriction | RBAC with 15 permissions, API endpoint auth on 100% of mutating endpoints | 5.3.3 | IMPLEMENTED |
| A.8.4 | Access to source code | Private GitHub repository, CODEOWNERS for Class C, branch protection | 5.3.3 | IMPLEMENTED |
| A.8.5 | Secure authentication | Firebase Auth + JWT + WebAuthn/Passkeys (FIDO2), Argon2id password hashing | 5.3.2 | IMPLEMENTED |
| A.8.7 | Protection against malware | Pydantic input validation, file type verification (NIfTI/DICOM only) | 5.3.10 | IMPLEMENTED |
| A.8.8 | Management of technical vulnerabilities | npm audit + pip-audit in CI, QMS SOUP Monitor with NVD CVE scanning | 5.3.12 | IMPLEMENTED |
| A.8.9 | Configuration management | IEC 62304 Configuration Management Plan (CMP-001), Git version control | 5.3.11 | IMPLEMENTED |
| A.8.10 | Information deletion | Firestore document TTL, patient data deletion API, GDPR right to erasure | 5.3.5 | IMPLEMENTED |
| A.8.12 | Data leakage prevention | PHI de-identification before AI API calls, no PHI in logs, CORS allowlist | 5.3.6 | IMPLEMENTED |
| A.8.15 | Logging | Structured JSON audit logs, Cloud Run request logs, Firebase Auth logs | 5.3.7 | IMPLEMENTED |
| A.8.16 | Monitoring activities | QMS Compliance Dashboard (real-time), GitHub Actions CI on every commit | 5.3.7 | IMPLEMENTED |
| A.8.20 | Networks security | TLS 1.3 enforced, CORS configuration, API rate limiting (100/min) | 5.3.9 | IMPLEMENTED |
| A.8.24 | Use of cryptography | AES-256-GCM (user data), TLS 1.3 (transit), JWT RS256 (tokens) | 5.3.5 | IMPLEMENTED |
| A.8.25 | Secure development lifecycle | IEC 62304 Class C lifecycle, code review required for Class C, QMS monitoring | 5.3.1 | IMPLEMENTED |
| A.8.26 | Application security requirements | SRS-001 with REQ-SAFE-XXX and REQ-SEC-XXX requirements | 5.3.1 | IMPLEMENTED |
| A.8.27 | Secure system architecture | Decoupled frontend/backend, container isolation, principle of least privilege | 5.3.9 | IMPLEMENTED |
| A.8.28 | Secure coding | CLAUDE.md coding standards, Pydantic validation, no eval/exec, OWASP Top 10 | 5.3.10 | IMPLEMENTED |
| A.8.29 | Security testing | npm audit + pip-audit in CI, QMS AI code review capability | 5.3.13 | PARTIAL |
| A.8.31 | Separation of environments | Production (Cloud Run) isolated from development (local), separate .env files | 5.3.9 | IMPLEMENTED |
| A.8.33 | Test information | No real patient data in tests, synthetic test data only | 5.3.6 | IMPLEMENTED |

---

## 4. Control Implementation Summary

| Category | Total Controls Assessed | Implemented | Partial | N/A | Gap |
|----------|----------------------|-------------|---------|-----|-----|
| A.5 Organizational | 14 | 13 | 1 | 0 | 0 |
| A.6 People | 4 | 4 | 0 | 0 | 0 |
| A.7 Physical | 3 | 2 | 0 | 1 | 0 |
| A.8 Technological | 21 | 20 | 1 | 0 | 0 |
| **Total** | **42** | **39** | **2** | **1** | **0** |

### Overall ISO 27001 Annex A Alignment: **95%** (39 implemented + 1 N/A of 42 assessed)

### Partial Controls Requiring Action

| Control | Gap | Remediation | Priority | Target Date |
|---------|-----|-------------|----------|-------------|
| A.5.29 | Formal disaster recovery procedure not documented | Create DR procedure with RTO/RPO targets | MEDIUM | Q3 2026 |
| A.8.29 | No external penetration testing performed | Engage external security firm for pentest | HIGH | Q2 2026 |

---

## 5. Cross-Reference: ISO 27001 → IEC 81001-5-1 → CE Marking

This table demonstrates how ISO 27001 controls provide evidence for IEC 81001-5-1 compliance, which in turn satisfies EU MDR Annex I cybersecurity requirements:

| EU MDR Annex I | IEC 81001-5-1 Clause | ISO 27001 Controls | MSTool-AI Evidence |
|----------------|---------------------|--------------------|--------------------|
| 17.2(a) Cybersecurity measures | 5.3.1 Security risk management | A.5.1, A.5.8, A.8.25, A.8.26 | RMF-001, CSA-001, this document |
| 17.2(b) Protection against unauthorized access | 5.3.2 Authentication | A.8.5 | Firebase Auth + WebAuthn + JWT |
| 17.2(b) Protection against unauthorized access | 5.3.3 Access control | A.5.2, A.8.2, A.8.3, A.8.4 | RBAC (4 roles, 15 permissions) |
| 17.2(c) Data integrity | 5.3.5 Data protection | A.5.14, A.8.24 | TLS 1.3 + AES-256-GCM |
| 17.2(d) Confidentiality | 5.3.6 De-identification | A.8.12, A.8.33 | PHI stripped before AI calls |
| 17.4 Audit trails | 5.3.7 Audit and accountability | A.5.28, A.8.15, A.8.16 | Firestore audit trail, QMS monitoring |
| 17.2(e) Resilience | 5.3.8 Backup and recovery | A.5.29, A.5.30 | Cloud Run auto-scaling, GCS versioning |
| 17.2(a) State of the art | 5.3.9 Network security | A.8.20, A.8.27, A.8.31 | TLS 1.3, CORS, container isolation |
| 17.2(a) State of the art | 5.3.10 Input validation | A.8.7, A.8.28 | Pydantic schemas, OWASP Top 10 |
| 17.2(a) State of the art | 5.3.11 SOUP management | A.5.9, A.8.9 | SOUP-001, SBOM, version pinning |
| 17.2(a) State of the art | 5.3.12 Vulnerability management | A.5.7, A.8.8 | QMS SOUP Monitor, CI scanning |
| 17.2(a) State of the art | 5.3.13 Security testing | A.8.29 | npm/pip audit in CI (pentest pending) |

---

## 6. Continuous Monitoring

Security controls are continuously monitored by the **MSTool-AI-QMS** platform ([mstool-ai-qms.web.app](https://mstool-ai-qms.web.app)):

| QMS Feature | ISO 27001 Controls Monitored |
|-------------|------------------------------|
| Compliance Dashboard → Cybersecurity Score | A.8.3 (auth coverage), A.8.7 (input validation), A.8.8 (SOUP vulnerability) |
| SOUP Monitor → CVE Scanning | A.5.7, A.5.9, A.8.8 |
| AI Code Review → OWASP Analysis | A.8.28, A.8.29 |
| AI Risk Detection → Class C Change Monitoring | A.8.25, A.8.26 |
| Audit Trail → Action Logging | A.5.28, A.8.15 |
| Auth Coverage → Endpoint Protection | A.8.3, A.8.5 |

Current QMS cybersecurity compliance score: **93.9%**

---

## 7. Statement of Applicability (SoA)

Of the 93 controls in ISO 27001:2022 Annex A, **42 are applicable** to MSTool-AI as a cloud-deployed SaMD. The remaining 51 controls relate to physical premises, HR processes, and organizational governance that are outside the scope of the software product ISMS (they would be covered by the manufacturer's organizational ISMS).

This product-level ISMS demonstrates that the **technical and operational security controls** required by IEC 81001-5-1 are implemented and aligned with the internationally recognized ISO 27001 framework.

---

*Document generated as part of MSTool-AI Technical Documentation for CE Marking under EU MDR 2017/745.*
*Monitored by [MSTool-AI-QMS](https://mstool-ai-qms.web.app) — AI-powered regulatory compliance automation.*
