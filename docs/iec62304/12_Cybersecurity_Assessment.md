# MSTool-AI: Cybersecurity Assessment

## IEC 81001-5-1:2021 + ISO 27001:2022 + IEC 62304 Amendment 1 (2015) Compliance

**Document ID**: CSA-001
**Version**: 1.1
**Effective Date**: April 14, 2026
**Standards**: IEC 81001-5-1:2021 (Health software cybersecurity — primary), ISO/IEC 27001:2022 (ISMS control framework), IEC 62304:2006+A1:2015 (cybersecurity requirements)
**Related Documents**: ISMS-001 (ISO 27001 Annex A Control Mapping)

---

## 1. Scope

This assessment covers the cybersecurity posture of MSTool-AI as a cloud-deployed medical device software (SaMD) processing sensitive medical imaging data. The assessment addresses requirements from IEC 81001-5-1:2021 (primary obligation for CE Marking) and uses ISO/IEC 27001:2022 Annex A as the control framework, as recommended by MDCG 2019-16 Rev.1.

### 1.1 Regulatory Hierarchy for Cybersecurity

For CE Marking under EU MDR 2017/745:
- **EU MDR Annex I, Section 17.2** requires cybersecurity measures "according to the state of the art"
- **IEC 81001-5-1:2021** is the harmonized standard satisfying this requirement (mandatory)
- **ISO/IEC 27001:2022** provides the recognized control framework referenced by MDCG 2019-16
- **IEC 62304 Amendment 1 (2015)** adds software-specific cybersecurity requirements

The complete ISO 27001 Annex A control mapping is documented in **ISMS-001** (42 controls assessed, 95% alignment).

---

## 2. System Security Architecture

```
Internet
    │ TLS 1.3
    ▼
┌─────────────────┐     ┌──────────────────────┐
│ Firebase Hosting │     │ Google Cloud Run      │
│ (Frontend SPA)   │────▶│ (Backend API)         │
│ HTTPS only       │     │ Container isolation   │
└─────────────────┘     │ Auto-scaling 0→N      │
                        └──────┬───────────────┘
                               │ TLS
                    ┌──────────┼──────────┐
                    ▼          ▼          ▼
              Firestore   Cloud Storage  External APIs
              (Encrypted)  (Encrypted)   (TLS + API keys)
```

---

## 3. Security Controls Inventory

### 3.1 Authentication and Access Control

| Control | Implementation | IEC 81001-5-1 | ISO 27001 | Status |
|---------|---------------|---------------|-----------|--------|
| User authentication | Firebase Auth + JWT — 103 API endpoints, 100% coverage | 5.3.2 | A.8.5 | IMPLEMENTED |
| Biometric auth (WebAuthn/Passkeys) | FIDO2 protocol, credentials in Firestore | 5.3.2 | A.8.5 | IMPLEMENTED |
| Role-based access control (RBAC) | 4 roles, 15 granular permissions | 5.3.3 | A.5.2, A.8.3 | IMPLEMENTED |
| Token expiration | JWT expires in 60 minutes | 5.3.2 | A.8.5 | IMPLEMENTED |
| Account lockout | After 5 failed attempts, 30 min lock | 5.3.2 | A.8.5 | IMPLEMENTED |
| Password policy | Argon2id, 12+ chars, complexity, history | 5.3.2 | A.8.5 | IMPLEMENTED |
| Session management | Configurable idle timeout with warning | 5.3.4 | A.8.5 | IMPLEMENTED |
| CAPTCHA | Numeric challenge after failed attempts | 5.3.2 | A.8.5 | IMPLEMENTED |

### 3.2 Data Protection

| Control | Implementation | IEC 81001-5-1 | ISO 27001 | Status |
|---------|---------------|---------------|-----------|--------|
| Encryption in transit | TLS 1.3 (Cloud Run enforced) | 5.3.5 | A.8.24 | IMPLEMENTED |
| Encryption at rest (user data) | AES-256-GCM | 5.3.5 | A.8.24 | IMPLEMENTED |
| Encryption at rest (storage) | GCS server-side encryption | 5.3.5 | A.8.24 | IMPLEMENTED |
| PHI de-identification | Stripped before AI API calls | 5.3.6 | A.8.12 | IMPLEMENTED |
| Audit logging | Structured JSON per access event | 5.3.7 | A.8.15 | IMPLEMENTED |
| Data backup | GCS versioning + Firestore export | 5.3.8 | A.5.29 | PARTIAL |

### 3.3 Network Security

| Control | Implementation | IEC 81001-5-1 Clause | Status |
|---------|---------------|---------------------|--------|
| HTTPS only | Firebase + Cloud Run enforce HTTPS | 5.3.5 | IMPLEMENTED |
| API rate limiting | Token bucket (100 req/min per IP) | 5.3.9 | IMPLEMENTED |
| CORS configuration | Explicit allowlist of origins | 5.3.9 | IMPLEMENTED |
| Input validation | Pydantic schemas on all API endpoints | 5.3.10 | IMPLEMENTED |
| Content Security Policy | Not implemented | 5.3.9 | GAP |

### 3.4 Software Supply Chain

| Control | Implementation | IEC 81001-5-1 Clause | Status |
|---------|---------------|---------------------|--------|
| SOUP inventory | 37 items documented (SOUP-001) | 5.3.11 | IMPLEMENTED |
| SOUP version pinning | package.json + requirements.txt | 5.3.11 | IMPLEMENTED |
| Vulnerability scanning (npm) | npm audit in GitHub Actions CI | 5.3.12 | IMPLEMENTED |
| Vulnerability scanning (pip) | pip-audit in GitHub Actions CI | 5.3.12 | IMPLEMENTED |
| Container base image | Python 3.11 slim (Docker) | 5.3.11 | IMPLEMENTED |

### 3.5 Secrets Management

| Control | Implementation | IEC 81001-5-1 Clause | Status |
|---------|---------------|---------------------|--------|
| Secrets not in code | env.yaml in .gitignore | 5.3.5 | IMPLEMENTED |
| API key rotation | Manual (no automated rotation) | 5.3.5 | PARTIAL |
| JWT signing key | Environment variable, not hardcoded | 5.3.5 | IMPLEMENTED |

---

## 4. Threat Analysis

### 4.1 STRIDE Analysis

| Threat Category | Threat | Mitigation | Residual Risk |
|----------------|--------|-----------|---------------|
| **Spoofing** | Attacker impersonates user | JWT auth + WebAuthn/Passkeys | Low |
| **Tampering** | Modification of segmentation data in transit | TLS 1.3 encryption | Low |
| **Repudiation** | User denies performing action | Audit logging with timestamps | Low |
| **Information Disclosure** | PHI leaked to AI APIs | De-identification pipeline | Low |
| **Information Disclosure** | Patient data in error messages | Pydantic validation, no PHI in logs | Medium |
| **Denial of Service** | API overwhelmed | Rate limiting (100/min), Cloud Run auto-scaling | Low |
| **Elevation of Privilege** | User gains admin access | RBAC with 15 granular permissions | Low |
| **Supply Chain** | Compromised SOUP component | Version pinning + vulnerability scanning | Medium |

### 4.2 Medical Device Specific Threats

| Threat | Scenario | Mitigation | Status |
|--------|----------|-----------|--------|
| Model poisoning | Malicious ONNX model supplied | Administrator-only model upload | MITIGATED |
| DICOM exploit | Malformed DICOM triggers buffer overflow | pydicom parsing with error handling | MITIGATED |
| NIfTI exploit | Malformed NIfTI triggers crash | nibabel parsing with temp file isolation | MITIGATED |
| Report manipulation | Attacker modifies AI-generated report | Reports are read-only, clinician must copy/export | MITIGATED |
| Cross-patient data | Wrong patient data displayed | Patient ID verification in viewer header | MITIGATED |

---

## 5. Vulnerability Management

### 5.1 Current Process

| Activity | Frequency | Tool | Status |
|----------|-----------|------|--------|
| SOUP anomaly review | Monthly | Manual NVD check | PARTIAL |
| npm audit | Per build (CI) | npm audit | IMPLEMENTED (`.github/workflows/ci.yml`) |
| pip-audit | Per build (CI) | pip-audit | IMPLEMENTED (`.github/workflows/ci.yml`) |
| Container scanning | Not implemented | — | GAP |
| Penetration testing | Not performed | — | GAP |

### 5.2 SOUP Vulnerability Scanning in CI (Implemented)

npm audit and pip-audit are already integrated in `.github/workflows/ci.yml` and run on every build. No further action required for SOUP scanning.

```yaml
# Already in .github/workflows/ci.yml
- name: npm audit
  run: npm audit --audit-level=high
  working-directory: frontend

- name: pip audit
  run: pip-audit --strict
  working-directory: backend
```

---

## 6. Compliance Summary

### IEC 81001-5-1:2021 Clause Coverage

| Clause | Requirement | Status |
|--------|-------------|--------|
| 5.3.1 | Security risk management | PARTIAL (integrated in RMF-001) |
| 5.3.2 | Authentication and authorization | IMPLEMENTED |
| 5.3.3 | Access control | IMPLEMENTED |
| 5.3.4 | Session management | IMPLEMENTED |
| 5.3.5 | Data protection (confidentiality, integrity) | IMPLEMENTED |
| 5.3.6 | Data de-identification | IMPLEMENTED |
| 5.3.7 | Audit and accountability | IMPLEMENTED |
| 5.3.8 | Backup and recovery | PARTIAL |
| 5.3.9 | Network security | PARTIAL (CSP missing) |
| 5.3.10 | Input validation | IMPLEMENTED |
| 5.3.11 | SOUP security management | IMPLEMENTED (37 items inventoried in SOUP-001, CI scanning active) |
| 5.3.12 | Vulnerability management | IMPLEMENTED (npm audit + pip-audit in GitHub Actions CI) |
| 5.3.13 | Security testing | GAP (no penetration test) |

### Overall Cybersecurity Compliance: **87%**

### Critical Actions Required

| Action | Priority | Effort |
|--------|----------|--------|
| ~~Add npm audit + pip-audit to CI~~ | ~~HIGH~~ | COMPLETED (2026-04-12) |
| Add Content Security Policy headers | MEDIUM | 1 day |
| Schedule penetration test (external firm) | HIGH | 2 weeks + report |
| Implement automated SOUP CVE monitoring | MEDIUM | 2 days |
| Document backup/recovery procedures | MEDIUM | 1 day |

---

---

## 7. ISO 27001:2022 Alignment

A comprehensive mapping of all applicable ISO 27001:2022 Annex A controls is documented in **ISMS-001_Information_Security_Management.md**.

**Summary**: 42 of 93 Annex A controls are applicable to MSTool-AI as a cloud-deployed SaMD. Of these, **39 are fully implemented**, **2 are partial** (disaster recovery procedure, penetration testing), and **1 is N/A** (physical premises — cloud only).

**Overall ISO 27001 Annex A Alignment: 95%**

This alignment provides strong evidence for EU MDR Annex I Section 17.2 compliance ("state of the art" cybersecurity measures) and satisfies MDCG 2019-16 Rev.1 recommendations for recognized cybersecurity frameworks.

---

## 8. Continuous Monitoring

All cybersecurity controls are continuously monitored by the **MSTool-AI-QMS** platform ([mstool-ai-qms.web.app](https://mstool-ai-qms.web.app)):

- **Cybersecurity compliance score**: 93.9% (real-time, computed from auth coverage + input validation + SOUP vulnerability + CODEOWNERS)
- **SOUP CVE scanning**: NVD API 2.0 integration with safety classification per IEC 62304
- **AI code review**: Automated OWASP Top 10 analysis of Class C modules
- **Auth coverage tracking**: 100% of API endpoints verified as protected

---

*End of Cybersecurity Assessment — CSA-001 v1.1*
*Monitored by [MSTool-AI-QMS](https://mstool-ai-qms.web.app)*
