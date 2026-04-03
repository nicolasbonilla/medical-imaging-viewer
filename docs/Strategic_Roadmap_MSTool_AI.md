# MSTool-AI: Strategic Roadmap to Clinical-Grade Production

## From Research Prototype to Hospital-Deployed Medical Device

**Version**: 1.0
**Date**: April 2026
**Target**: TUM Klinikum rechts der Isar — Department of Neuroradiology
**Timeline**: 18 months to CE-marked clinical pilot

---

## Vision Statement

Transform MSTool-AI from a feature-complete research prototype (82,400 LOC, 210+ files) into a **CE-marked Class IIa medical device** deployed in German university hospitals, leveraging its unique CVS/PRL biomarker support and MAGNIMS two-tier classification as first-mover advantages aligned with the 2024 revised McDonald criteria.

---

## Current State Assessment

### Strengths (Leverage)
- CVS/PRL biomarker support — **unique globally**, no competitor offers this
- MAGNIMS two-tier region classification with SynthSeg parcellation
- Full-stack platform (viewer + segmentation + analysis + AI reporting + edge AI + MCP)
- NIfTI-native support enables direct research pipeline integration (FreeSurfer, FSL, LST-AI)
- WebAuthn/Passkeys biometric authentication
- Multi-language (EN/ES/DE)
- Claude API report generation with HIPAA de-identification

### Weaknesses (Fix)
- No DICOMweb/PACS integration
- Authentication architecture has critical bugs
- Secrets exposed in version control
- < 10% test coverage
- No clinical validation studies
- No regulatory documentation (IEC 62304, ISO 14971)
- Voxel spacing hardcoded in some analysis paths

### Opportunities (Capture)
- McDonald 2024 criteria just published — market timing is perfect for CVS/PRL
- LST-AI developed at TUM/CompImg — natural collaboration partner
- EU AI Act creates barrier to entry for new competitors (benefits first movers)
- German Medical Informatics Initiative (MII) funding for FHIR-based imaging tools
- CPT reimbursement codes active (0865T, 0866T) for AI-assisted MS analysis

### Threats (Mitigate)
- NeuroQuant, icometrix, Pixyl all CE-marked and deployed
- OHIF is free, open-source, DICOMweb-native with 26/29 feature score
- EU MDR + AI Act + NIS2 regulatory stack is complex and expensive
- LLM hallucination risk (8-15%) requires careful clinical positioning

---

## 6-Phase Roadmap

```
Phase 1 ──── Phase 2 ──── Phase 3 ──── Phase 4 ──── Phase 5 ──── Phase 6
Security    Hospital     Testing &    Clinical     Regulatory   Pilot
& Stability Integration  Quality      Validation   (CE Mark)    Deployment

Weeks 1-4   Weeks 5-12   Weeks 8-20   Months 6-12  Months 9-18  Months 18-24
```

---

## Phase 1: Security & Stability Foundation
**Timeline**: Weeks 1-4
**Goal**: Eliminate all known bugs and security vulnerabilities

### 1.1 Authentication Refactor (Week 1-2)

**Problem**: Dual auth modules (`auth.py` + `authentication.py`) with duplicate endpoints, missing methods, and `full_name=""` Pydantic validation bug.

**Actions**:
| Task | Priority | Effort |
|------|----------|--------|
| Merge `authentication.py` into `auth.py` — single auth module | CRITICAL | 2 days |
| Implement 5 missing AuthService methods (logout, update_user, get_user_by_id, delete_user, get_audit_logs) | CRITICAL | 2 days |
| Remove duplicate `/auth/login`, `/auth/register`, `/auth/me` endpoints | CRITICAL | 1 day |
| Use singleton `get_token_manager()` everywhere — remove local TokenManager in `auth.py` | HIGH | 1 day |
| Remove hardcoded admin credentials from `main.py` — use CLI seed script | HIGH | 0.5 day |
| Fix typo in `auth.py:221` (`username` → `user.username`) | LOW | 0.5 hour |

### 1.2 Secrets Management (Week 1)

**Problem**: `JWT_SECRET_KEY` and `ANTHROPIC_API_KEY` committed to `env.yaml` in version control.

**Actions**:
| Task | Priority | Effort |
|------|----------|--------|
| Migrate secrets to Google Cloud Secret Manager | CRITICAL | 1 day |
| Update `cloudbuild.yaml` to use `--set-secrets` flag | CRITICAL | 0.5 day |
| Remove `env.yaml` from repository, add to `.gitignore` | CRITICAL | 0.5 hour |
| Rotate all exposed credentials (JWT key, Anthropic key) | CRITICAL | 1 hour |
| Document secret management procedure | HIGH | 0.5 day |

### 1.3 Data Accuracy (Week 2-3)

**Problem**: Voxel spacing hardcoded to (1,1,1) mm in longitudinal tracking and some volumetry paths.

**Actions**:
| Task | Priority | Effort |
|------|----------|--------|
| Extract real voxel spacing from NIfTI headers in all analysis services | CRITICAL | 2 days |
| Validate voxel spacing propagation through entire pipeline (upload → analysis → report) | HIGH | 1 day |
| Add NIfTI orientation validation on upload (prevent future axis mismatch bugs) | HIGH | 1 day |
| Fix `_save_masks_to_gcs` to always preserve original affine | HIGH | 1 day |

### 1.4 Error Handling Audit (Week 3-4)

**Problem**: Silent `except Exception` blocks hide real errors (the `full_name` bug was hidden for weeks).

**Actions**:
| Task | Priority | Effort |
|------|----------|--------|
| Audit all `except Exception` blocks — add specific error logging | HIGH | 2 days |
| Replace generic 401/500 responses with descriptive error messages (dev mode) | HIGH | 1 day |
| Add structured error response format across all endpoints | MEDIUM | 1 day |
| Implement global exception handler with correlation IDs | MEDIUM | 1 day |

### Phase 1 Deliverables
- [ ] Single unified auth module with all methods implemented
- [ ] All secrets in Cloud Secret Manager, rotated credentials
- [ ] Accurate voxel spacing in all quantitative analysis
- [ ] No silent exception swallowing anywhere in codebase
- [ ] Auth architecture document

---

## Phase 2: Hospital Integration
**Timeline**: Weeks 5-12
**Goal**: Enable MSTool-AI to connect to hospital PACS infrastructure

### 2.1 DICOMweb Implementation (Week 5-8)

**Why**: Without DICOMweb, MSTool-AI cannot receive studies from or return results to hospital PACS. This is the #1 blocker for clinical deployment.

**Architecture**:
```
Hospital PACS (dcm4chee / Sectra / Philips)
        │
        ▼ DICOMweb (HTTPS)
   ┌────────────────┐
   │ MSTool-AI      │
   │ DICOMweb Proxy │
   │ (FastAPI)      │
   └────┬───────────┘
        │
        ▼
   Existing NIfTI pipeline
   (auto-convert DICOM→NIfTI on ingest)
```

**Actions**:
| Task | Priority | Effort |
|------|----------|--------|
| **QIDO-RS**: Query studies/series/instances from external PACS | CRITICAL | 1 week |
| **WADO-RS**: Retrieve pixel data and metadata | CRITICAL | 1 week |
| **STOW-RS**: Store DICOM-SEG results back to PACS | CRITICAL | 1 week |
| DICOM→NIfTI auto-conversion on ingest (for internal processing) | HIGH | 3 days |
| PACS configuration UI (endpoint, AE title, credentials) | MEDIUM | 2 days |
| Connection health check and retry logic | MEDIUM | 1 day |

**Reference**: Use `pynetdicom` for DIMSE fallback, `httpx` for DICOMweb REST calls. Study OHIF's DICOMweb data source architecture.

### 2.2 DICOM-SEG & DICOM-SR Export (Week 8-10)

**Why**: Segmentation results and reports must be stored as DICOM objects for clinical archival.

**Actions**:
| Task | Priority | Effort |
|------|----------|--------|
| Resolve pydicom 2.4.4 → 3.0+ upgrade (highdicom dependency) | HIGH | 2 days |
| DICOM-SEG: Export segmentation masks as DICOM Segmentation objects | HIGH | 1 week |
| DICOM-SR: Export AI reports as DICOM Structured Reports | HIGH | 1 week |
| DICOM Secondary Capture: Export 2D/3D screenshots | MEDIUM | 2 days |

### 2.3 HL7 FHIR Integration (Week 10-12)

**Why**: Bridge imaging data to the hospital's Electronic Health Record.

**Actions**:
| Task | Priority | Effort |
|------|----------|--------|
| FHIR ImagingStudy resource generation from DICOM metadata | HIGH | 3 days |
| FHIR DiagnosticReport for AI-generated reports | HIGH | 3 days |
| FHIR Patient resource mapping | MEDIUM | 2 days |
| FHIR Bundle for complete study + report submission | MEDIUM | 2 days |

### Phase 2 Deliverables
- [ ] DICOMweb proxy with QIDO-RS, WADO-RS, STOW-RS
- [ ] DICOM-SEG export for all segmentation masks
- [ ] DICOM-SR export for AI reports
- [ ] FHIR ImagingStudy + DiagnosticReport generation
- [ ] Hospital PACS integration test with Orthanc/dcm4chee

---

## Phase 3: Testing & Quality Assurance
**Timeline**: Weeks 8-20 (overlaps with Phase 2)
**Goal**: Achieve IEC 62304-compliant test coverage

### 3.1 Test Infrastructure (Week 8-10)

| Task | Effort |
|------|--------|
| Backend: pytest fixtures for all services (mock Firestore, GCS, Vertex AI) | 3 days |
| Frontend: Vitest + React Testing Library setup for all components | 3 days |
| E2E: Playwright setup with hospital workflow scenarios | 3 days |
| CI/CD: GitHub Actions for automated test + lint on every PR | 2 days |
| Code coverage reporting (Codecov or similar) | 1 day |

### 3.2 Test Implementation (Week 10-18)

| Category | Target Coverage | Test Count (est.) | Effort |
|----------|----------------|------------------|--------|
| Backend unit tests | > 85% | ~400 tests | 3 weeks |
| Frontend unit tests | > 80% | ~200 tests | 2 weeks |
| API integration tests | All 60 endpoints | ~120 tests | 2 weeks |
| E2E clinical workflows | 10 critical paths | ~30 tests | 1 week |
| Golden dataset regression | ISBI 2015 + MSLesSeg | ~20 tests | 1 week |
| Performance/load tests | 10 concurrent users | ~10 scenarios | 3 days |

### 3.3 Clinical Workflow E2E Tests

| Workflow | Steps | Priority |
|----------|-------|----------|
| Login → PACS query → Open study → View 2D/3D | 8 steps | CRITICAL |
| Segmentation: Create → Paint → Save → Reload | 6 steps | CRITICAL |
| Longitudinal: Select TP1 → Select TP2 → Compare → View overlay | 7 steps | HIGH |
| AI Report: Select template → Generate → Review → Export DICOM-SR | 5 steps | HIGH |
| MAGNIMS Classification: Load seg → Auto-classify → Review regions | 4 steps | HIGH |
| Brain Volumetry: Run → Compare normative → Flag abnormalities | 4 steps | HIGH |
| DIS Assessment: Load seg → Compute DIS → View criteria | 3 steps | HIGH |
| Passkey: Register → Logout → Login with passkey | 4 steps | MEDIUM |
| Multi-panel: Open → Sync slices → Compare sequences | 4 steps | MEDIUM |
| Edge AI: Load → Screen → View badge | 3 steps | MEDIUM |

### 3.4 Security Testing (Week 18-20)

| Task | Effort |
|------|--------|
| External penetration test (accredited firm) | 2 weeks + report |
| OWASP Top 10 vulnerability scan | 1 day |
| Dependency vulnerability audit (Snyk/Dependabot) | 1 day |
| Authentication bypass testing | 2 days |
| Data leakage testing (PHI in logs, responses, errors) | 2 days |

### Phase 3 Deliverables
- [ ] > 80% code coverage (backend + frontend)
- [ ] All 60 API endpoints with integration tests
- [ ] 10 E2E clinical workflow tests
- [ ] Golden dataset regression suite
- [ ] Penetration test report
- [ ] CI/CD pipeline with automated testing

---

## Phase 4: Clinical Validation Study
**Timeline**: Months 6-12
**Goal**: Generate clinical evidence per CLAIM 2024 guidelines

### 4.1 Study Design

**Title**: "Clinical Validation of MSTool-AI for Automated MS Lesion Classification and Longitudinal Tracking Using MAGNIMS 2024 Criteria: A Multi-Center Study"

**Design**: Prospective, multi-center, cross-sectional + longitudinal

**Primary Endpoints**:
1. Agreement between MSTool-AI MAGNIMS classification and expert neuroradiologist consensus (Cohen's kappa)
2. Dice similarity between MSTool-AI-assisted segmentation and expert manual segmentation

**Secondary Endpoints**:
1. DIS assessment concordance (MSTool-AI vs. expert clinical judgment)
2. Longitudinal tracking accuracy (IoU-matched lesion status vs. expert)
3. Time efficiency (MSTool-AI-assisted workflow vs. standard workflow)
4. System Usability Scale (SUS) score

### 4.2 Study Protocol

| Parameter | Specification |
|-----------|--------------|
| **Sites** | 3 minimum: TUM Klinikum, Charité Berlin, LMU München |
| **Patients** | 150 (50 per site): confirmed MS, ≥ 2 MRI timepoints |
| **Subtypes** | RRMS (60%), SPMS (20%), PPMS (10%), CIS (10%) |
| **Scanners** | Siemens (minimum 2 models), Philips, GE — 1.5T and 3T |
| **Sequences** | T1, T2-FLAIR, T1-Gd (mandatory); SWI/QSM (CVS/PRL subset) |
| **Expert raters** | 3 board-certified neuroradiologists per site |
| **Reference standard** | Majority consensus (2/3 experts) |
| **Inter-rater reliability** | Fleiss' kappa, measured independently |

### 4.3 Validation Metrics

| Metric | Formula | Acceptable Threshold |
|--------|---------|---------------------|
| Lesion-wise Dice | DSC per connected component | > 0.60 (ISBI 2015 benchmark) |
| Volume correlation | Pearson r (total lesion volume) | > 0.90 |
| MAGNIMS classification | Cohen's kappa (weighted) | > 0.70 (substantial agreement) |
| DIS concordance | Sensitivity + Specificity | Sensitivity > 0.85, Specificity > 0.80 |
| Longitudinal tracking | F1-score (status classification) | > 0.75 |
| CVS detection | Sensitivity (per-lesion) | > 0.80 (if validated subset available) |
| Usability (SUS) | Questionnaire score | > 70 (acceptable) |
| Time efficiency | Minutes per study | < 50% of manual workflow |

### 4.4 Ethics and Regulatory

| Requirement | Action | Timeline |
|------------|--------|----------|
| IRB/Ethics approval (TUM) | Submit protocol to Ethikkommission | Month 6 |
| Data processing agreement | GDPR-compliant DPA with each site | Month 6-7 |
| Patient consent | Informed consent for AI-assisted analysis | Month 7+ |
| Data anonymization | Full DICOM de-identification before multi-site sharing | Month 7 |
| ClinicalTrials.gov registration | Register observational study | Month 7 |

### 4.5 Publication Strategy

| Manuscript | Target Journal | Impact Factor | Timeline |
|-----------|---------------|---------------|----------|
| Validation study (primary) | *Radiology: AI* or *NeuroImage: Clinical* | 8.1 / 4.2 | Month 14 |
| MAGNIMS classification method | *Multiple Sclerosis Journal* | 6.4 | Month 12 |
| LLM reporting evaluation | *European Radiology* | 5.9 | Month 16 |
| Platform architecture | *Journal of Medical Internet Research* | 7.4 | Month 10 |
| CVS/PRL tool (if validated) | *Brain* | 14.5 | Month 18 |

### Phase 4 Deliverables
- [ ] IRB-approved multi-center study protocol
- [ ] 150-patient validated dataset
- [ ] CLAIM 2024-compliant validation results
- [ ] 2-3 peer-reviewed publications submitted
- [ ] Clinical evidence report for CE submission

---

## Phase 5: Regulatory Pathway (CE Marking)
**Timeline**: Months 9-18
**Goal**: Achieve EU MDR CE marking as Class IIa medical device

### 5.1 Intended Purpose Statement (Draft)

> MSTool-AI is a software-as-a-medical-device (SaMD) intended to assist qualified healthcare professionals in the visualization, quantification, and monitoring of brain MRI findings in patients with suspected or confirmed Multiple Sclerosis. The software provides automated lesion volume measurement, anatomical region classification per MAGNIMS guidelines, longitudinal change detection, and AI-assisted structured report generation. MSTool-AI is intended as a decision-support tool and does not replace clinical judgment. All outputs require review and confirmation by a qualified physician before clinical action.

### 5.2 QMS Implementation (ISO 13485)

| QMS Element | Document | Effort |
|------------|----------|--------|
| Quality manual | Top-level QMS policy document | 1 week |
| Design controls | Design history file, design input/output, V&V | 3 weeks |
| Risk management | ISO 14971 risk management file | 3 weeks |
| Software lifecycle | IEC 62304 documentation (retroactive) | 4 weeks |
| Usability engineering | IEC 62366 usability file | 2 weeks |
| SOUP management | List of all third-party components with risk assessment | 1 week |
| Post-market surveillance | PMS plan, PSUR template | 1 week |
| Change management | ECO/ECN procedures | 1 week |
| CAPA procedures | Corrective and preventive action process | 1 week |
| Training records | Developer and user training documentation | 1 week |

### 5.3 Technical Documentation (MDR Annex II/III)

| Document | Content | Effort |
|----------|---------|--------|
| Device description | Architecture, features, intended purpose, contraindications | 2 weeks |
| Label and IFU | Instructions for use in EN, DE | 2 weeks |
| Design verification | Test reports, traceability matrix | 3 weeks |
| Clinical evaluation | CER per MEDDEV 2.7/1 rev 4, clinical data from Phase 4 | 4 weeks |
| Biocompatibility | N/A (software only) | — |
| Cybersecurity | MDCG 2019-16 compliance | 2 weeks |
| AI-specific | Training data, model validation, demographic performance (EU AI Act) | 3 weeks |

### 5.4 Notified Body Engagement

**Recommended Notified Bodies for SaMD in Germany**:
- TÜV SÜD (Munich — geographically convenient for TUM)
- BSI Group (Netherlands, but active in Germany)
- DEKRA (Stuttgart)

**Process**:
1. Pre-submission meeting to discuss classification and documentation scope
2. Technical documentation review
3. QMS audit (on-site or remote)
4. Certificate issuance (valid 5 years with annual surveillance)

**Estimated cost**: EUR 50,000-80,000 (Notified Body fees) + EUR 150,000-400,000 (consultant, QMS implementation, clinical evaluation).

### Phase 5 Deliverables
- [ ] ISO 13485 QMS implemented and documented
- [ ] IEC 62304 software lifecycle documentation
- [ ] ISO 14971 risk management file
- [ ] IEC 62366 usability engineering file
- [ ] Clinical evaluation report (CER)
- [ ] Technical documentation per MDR Annex II/III
- [ ] Notified Body submission
- [ ] EU Declaration of Conformity + CE mark

---

## Phase 6: Pilot Deployment
**Timeline**: Months 18-24
**Goal**: Monitored clinical use at TUM Klinikum

### 6.1 Infrastructure

| Component | Specification |
|-----------|--------------|
| Hosting | Google Cloud region: europe-west3 (Frankfurt) for GDPR compliance |
| Network | VPN or IP-whitelisted access from hospital network |
| PACS connection | DICOMweb to hospital PACS (Sectra/Syngo) via TLS |
| Backup | Daily automated backups with 30-day retention, geo-redundant |
| Monitoring | Google Cloud Monitoring + PagerDuty alerting |
| SLA | 99.5% uptime, < 3s study loading, < 5min analysis pipeline |

### 6.2 Training Program

| Audience | Content | Format | Duration |
|----------|---------|--------|----------|
| Neuroradiologists | Clinical workflow, segmentation tools, AI reports, longitudinal tracking | In-person workshop | 2 hours |
| Radiology residents | Same as above + hands-on practice | Workshop + supervised use | 4 hours |
| IT administrators | System configuration, PACS integration, user management, monitoring | Technical training | 3 hours |
| Data protection officer | GDPR compliance, audit logs, incident response | Compliance briefing | 1 hour |

### 6.3 Pilot Protocol

| Week | Activity |
|------|----------|
| 1-2 | System deployment, PACS integration, user account setup |
| 3-4 | Supervised use: neuroradiologists use MSTool-AI alongside standard workflow |
| 5-8 | Independent use: MSTool-AI as primary MS analysis tool with mandatory expert review |
| 9-12 | Evaluation: collect usability data, error reports, time savings |
| 13+ | Ongoing use with post-market surveillance |

### 6.4 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| System uptime | > 99.5% | Cloud Monitoring |
| Study loading time | < 3 seconds | APM traces |
| Analysis pipeline time | < 5 minutes | Server logs |
| User satisfaction (SUS) | > 75 | Quarterly survey |
| Error rate | < 1% critical errors | Error tracking |
| Adoption rate | > 80% of MS cases analyzed | Usage analytics |
| Time savings | > 30% vs manual workflow | Time comparison study |

### Phase 6 Deliverables
- [ ] Production deployment in eu-west3
- [ ] PACS integration with TUM hospital
- [ ] Trained clinical staff
- [ ] Post-market surveillance system active
- [ ] Quarterly performance reports
- [ ] User feedback collection system

---

## Resource Requirements

### Team

| Role | FTE | Phase | Responsibility |
|------|-----|-------|---------------|
| Lead developer (full-stack) | 1.0 | All | Architecture, implementation, deployment |
| Backend developer | 0.5 | 1-3 | DICOMweb, FHIR, testing |
| Frontend developer | 0.5 | 1-3 | Clinical UX, testing |
| Regulatory affairs specialist | 0.5 | 4-5 | QMS, IEC 62304, ISO 14971, Notified Body |
| Clinical scientist (neuroradiology) | 0.3 | 4-6 | Study design, clinical validation, CER |
| Data protection officer | 0.1 | 1-6 | GDPR, DPIA, NIS2 compliance |
| QA engineer | 0.5 | 3 | Test infrastructure and coverage |

### Budget

| Category | Estimate (EUR) |
|----------|---------------|
| Development (6 months, 2 FTE) | 120,000 |
| Testing & QA (3 months, 1.5 FTE) | 45,000 |
| Clinical validation study (multi-center) | 80,000 |
| Regulatory affairs consultant | 60,000 |
| Notified Body fees (TÜV SÜD) | 60,000 |
| ISO 13485 QMS implementation | 40,000 |
| Penetration testing (external) | 15,000 |
| Cloud infrastructure (18 months) | 18,000 |
| Contingency (15%) | 65,000 |
| **Total** | **~503,000** |

### Funding Opportunities

| Source | Program | Relevance | Amount |
|--------|---------|-----------|--------|
| BMBF | Medical Informatics Initiative (MII) | FHIR integration, multi-center data sharing | EUR 200-500K |
| DFG | Individual Research Grant | Clinical validation study | EUR 100-300K |
| EU Horizon Europe | AI for Health cluster | AI-assisted diagnosis | EUR 500K-2M |
| BfArM | DiGA Fast-Track | Digital health application pathway | Regulatory support |
| TUM | Innovation Fund | Medical device development | EUR 50-100K |
| Bavaria | Hightech Agenda | AI in medicine | Variable |

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Notified Body delays (MDR backlog) | HIGH | HIGH | Engage TÜV SÜD early, pre-submission meeting by Month 9 |
| Clinical study recruitment delays | MEDIUM | HIGH | Multi-center design, leverage TUM MS patient registry |
| Key developer departure | LOW | CRITICAL | Document architecture, code review practices, knowledge sharing |
| PACS integration compatibility issues | MEDIUM | HIGH | Test with Orthanc first, then hospital PACS in staging |
| AI model drift / hallucination | MEDIUM | HIGH | Mandatory physician review, confidence thresholds, monitoring |
| Competitor ships CVS/PRL first | LOW | HIGH | Accelerate CVS/PRL validation, publish early |
| EU AI Act requirements change | LOW | MEDIUM | Monitor regulatory updates, build flexible compliance framework |
| Data breach during pilot | LOW | CRITICAL | Penetration test, DPIA, incident response plan, insurance |

---

## Key Milestones

| Month | Milestone | Gate |
|-------|-----------|------|
| 1 | Auth refactored, secrets secured | Security audit pass |
| 3 | DICOMweb integration complete | Successful PACS retrieval + store |
| 5 | > 80% test coverage | CI/CD green on all tests |
| 6 | Clinical study protocol approved (IRB) | Ethics approval letter |
| 9 | 150 patients enrolled | Recruitment complete |
| 12 | Validation results analyzed | CLAIM 2024 compliance verified |
| 12 | First manuscript submitted | Target: Radiology: AI |
| 15 | ISO 13485 QMS audited | External audit pass |
| 18 | CE marking obtained | Notified Body certificate |
| 20 | TUM pilot launch | First clinical patient |
| 24 | Pilot evaluation complete | Success metrics met |

---

## Conclusion

MSTool-AI has a realistic 18-24 month path to clinical deployment. The platform's unique CVS/PRL biomarker support, combined with its MAGNIMS two-tier classification and LLM-powered reporting, positions it as a differentiated entry in the MS imaging AI market at a critical moment — the 2024 McDonald criteria revision has created demand for tools that no commercial competitor yet satisfies.

The primary challenges are regulatory (CE marking) and clinical validation (multi-center study). Both are addressable with the proposed resource allocation and TUM's clinical and academic infrastructure.

The strategic recommendation is to proceed immediately with Phase 1 (security hardening) while simultaneously initiating Phase 5 regulatory groundwork (intended purpose definition, Notified Body pre-submission meeting). This parallel approach minimizes time-to-market while maintaining regulatory compliance.

---

*This roadmap is a living document subject to revision based on regulatory guidance, clinical feedback, and competitive landscape changes.*
