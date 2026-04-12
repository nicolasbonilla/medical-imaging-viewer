# MSTool-AI: Supplier Evaluation and Monitoring Procedure

**Document ID**: QP-005 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: ISO 13485:2016 — Clause 7.4

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Purpose

This procedure defines how suppliers of products, services, and software components
used in MSTool-AI are evaluated, approved, and monitored. It ensures that externally
provided items meet specified requirements and do not compromise product quality or
patient safety.

## 2. Scope

This procedure applies to all external suppliers including:

- **SOUP (Software of Unknown Provenance)** — Open-source libraries and frameworks.
- **Cloud service providers** — Hosting, compute, storage, and AI inference services.
- **AI model providers** — Pre-trained models and inference APIs.
- **Development tools** — Compilers, CI/CD platforms, and testing frameworks.

## 3. Supplier Classification

Suppliers are classified based on their impact on product quality and patient safety:

| Classification | Definition | Examples |
|---------------|-----------|----------|
| Critical | Directly affects clinical output, patient data, or safety-critical functions | Vertex AI (inference), ONNX Runtime (edge AI), NIfTI/DICOM libraries, Anthropic Claude API |
| Standard | Affects product functionality but not directly safety-critical | React, Vite, FastAPI, Zustand, Firebase Auth |
| Infrastructure | Supports development or deployment but does not affect product output | GitHub, Google Cloud Run, Firebase Hosting, CI/CD tools |

## 4. Initial Evaluation Criteria

Before approving a new supplier, the following criteria are assessed:

### 4.1 Critical Suppliers
- Published security vulnerability history and response times.
- Compliance certifications (SOC 2, ISO 27001, HIPAA BAA where applicable).
- Software release cadence and long-term support commitment.
- License compatibility with medical device distribution.
- Known anomalous behavior or failure modes documented in SOUP-001.

### 4.2 Standard Suppliers
- Active maintenance status (commits within last 6 months).
- Community size and issue response metrics.
- License compatibility (MIT, Apache 2.0, BSD preferred).
- Dependency tree depth and transitive risk assessment.

### 4.3 Infrastructure Suppliers
- Service level agreement (SLA) terms.
- Data residency and GDPR compliance.
- Disaster recovery and backup capabilities.

## 5. Approval Process

1. **Requestor** submits Supplier Evaluation Form with classification and assessment.
2. **Quality Engineer** reviews for completeness.
3. **QMS Manager** approves (Critical suppliers require Project Lead co-review).
4. Approved suppliers added to `docs/iec62304/records/approved_supplier_list.md`.

## 6. Ongoing Monitoring

### 6.1 Critical Suppliers — Monthly

- CVE database scan for known vulnerabilities affecting supplier components.
- Review of security advisories and patch releases.
- Verification that deployed versions are within supported ranges.
- Automated dependency scanning via CI pipeline (`npm audit`, `pip-audit`).

### 6.2 Standard Suppliers — Quarterly

- CVE scan and advisory review.
- Check for deprecated status or maintainer abandonment.
- Evaluate if newer versions address known issues.
- Review dependency tree for newly introduced transitive risks.

### 6.3 Infrastructure Suppliers — Semi-Annually

- SLA compliance review (uptime, response times).
- Security certification renewal status.
- Service change notifications and impact assessment.

## 7. Non-Conforming Suppliers

When a supplier fails to meet requirements:

1. The issue is documented in the supplier record.
2. For Critical suppliers, a risk assessment is performed immediately.
3. A CAPA is initiated per QP-002 if the issue affects product quality or safety.
4. The supplier is placed on probation or removed from the Approved Supplier List.
5. Alternative suppliers are evaluated if removal is necessary.

## 8. SOUP Management

SOUP components are documented in SOUP-001 (Software of Unknown Provenance List)
which records for each component:

- Name, version, and license.
- Supplier classification (Critical/Standard/Infrastructure).
- Known anomalous behavior and risk mitigation measures.
- Minimum acceptable version and end-of-life date.

SOUP-001 is reviewed and updated with each product release and during quarterly
supplier monitoring cycles.

## 9. References

- ISO 13485:2016, Clause 7.4 — Purchasing
- IEC 62304:2006+A1:2015, Clause 8 — Software Maintenance (SOUP monitoring)
- SOUP-001 Software of Unknown Provenance List
- QP-002 CAPA Procedure
- RMF-001 Risk Management File
