# MSTool-AI: Production Readiness Analysis for Clinical Deployment

## State-of-the-Art Assessment, Regulatory Pathway, and Technical Gap Analysis

**Prepared for**: Technical University of Munich (TUM) — Department of Artificial Intelligence in Medicine
**Audience**: Director of AI, Neurosurgeons (PhD), MS Specialists, MRI Specialists, Software Engineering & AI Reviewers
**Date**: April 2026
**Classification**: Confidential — Pre-Regulatory Assessment

---

## Executive Summary

This document provides a comprehensive analysis of MSTool-AI's readiness for clinical deployment in a German university hospital environment, benchmarked against FDA-cleared and CE-marked competitors, current EU regulatory requirements (MDR, AI Act, NIS2), and the MAGNIMS-CMSC-NAIMS 2024 consensus guidelines. The analysis identifies MSTool-AI's unique differentiators — particularly its alignment with the revised McDonald 2024 diagnostic criteria including CVS/PRL biomarker support — while mapping the precise regulatory, technical, and clinical validation gaps that must be addressed for production deployment.

---

## 1. Competitive Landscape

### 1.1 FDA-Cleared / CE-Marked Commercial Platforms

| Platform | Origin | Regulatory Status | Key Capabilities | Processing Time |
|----------|--------|------------------|-------------------|-----------------|
| **Neurophet AQUA** | South Korea | FDA 510(k) (Nov 2024) | MS lesion quantification on T2-FLAIR, brain volumetry without 3D T1 | < 5 minutes |
| **NeuroQuant MS / LesionQuant** | USA (Cortechs.ai) | FDA 510(k), CE | 75 brain structures, lesion dynamics (NEW/STABLE/SHRINKING/ENLARGING), configurable region thresholds | < 6 minutes |
| **icometrix MSmetrix** | Belgium | CE + FDA | Scanner-independent MS volumetry, intercontinental multi-center validation | < 10 minutes |
| **Pixyl.Neuro.MS** | France | CE Class IIa MDR, FDA Class II | AI-powered neuroinflammatory/neurodegenerative analysis | < 5 minutes |
| **Quantib ND** | Netherlands | CE + FDA | Brain atrophy monitoring, WMH tracking, single + longitudinal analysis | < 5 minutes |

**CPT Reimbursement**: NeuroQuant MS has active CPT codes (0865T, 0866T) since January 2024, establishing a reimbursement pathway for AI-assisted MS analysis in the US market.

### 1.2 Research / Open-Source Platforms

| Platform | Affiliation | Status | Key Feature |
|----------|------------|--------|-------------|
| **OHIF Viewer** | Harvard/MGH | Open-source | DICOMweb-native, 26/29 feature score, 0.72s 2D loading (Pereira et al., JIIM 2025) |
| **Brainlife.io** | Indiana University | Research (Nature Methods 2024) | 400+ processing apps, reproducibility via DOI-addressed workflows |
| **LST-AI** | CompImg / TUM-affiliated | Research only | 3D U-Net ensemble, 491 T1/FLAIR training pairs, explicitly "not validated for clinical usage" |
| **volBrain / DeepLesionBrain** | Spain | Research only | Hierarchical 3D U-Net, free web service |
| **SynthSeg** | FreeSurfer / Harvard | Research (v7.3.2+) | Contrast-agnostic brain segmentation, multi-center validation on 260 paired CT/MRI |

### 1.3 Feature Comparison Matrix

| Feature | MSTool-AI | NeuroQuant MS | icometrix | Pixyl | OHIF |
|---------|:---------:|:------------:|:---------:|:-----:|:----:|
| Web-based viewer (2D + 3D) | **Yes** | Cloud+PACS | Cloud | Cloud | **Yes** |
| MS lesion segmentation | **Yes** (manual + AI) | **Yes** (auto) | **Yes** (auto) | **Yes** (auto) | No |
| Brain volumetry | **Yes** (SynthSeg) | **Yes** (75 structures) | **Yes** | Limited | No |
| Longitudinal tracking | **Yes** (IoU matching) | **Yes** (dynamics) | **Yes** | **Yes** | Partial |
| MAGNIMS region classification | **Yes** (2-tier EDT + atlas) | **Yes** (configurable) | Limited | Unknown | No |
| McDonald 2024 DIS assessment | **Yes** | Partial | Partial | Unknown | No |
| **CVS/PRL biomarker support** | **Yes** | **No** | **No** | **No** | **No** |
| AI report generation (LLM) | **Yes** (Claude) | PDF reports | PDF reports | Unknown | No |
| Edge AI (browser inference) | **Yes** (ONNX) | No | No | No | No |
| MCP server architecture | **Yes** | No | No | No | No |
| WebAuthn / Passkeys | **Yes** | No | No | No | No |
| DICOMweb / PACS integration | **No** | **Yes** | **Yes** | **Yes** | **Yes** |
| FDA / CE clearance | **No** | **Yes** | **Yes** | **Yes** | N/A |
| HL7 FHIR support | **No** | Partial | Partial | Unknown | **Yes** |
| DICOM-SEG export | **No** | **Yes** | **Yes** | Unknown | **Yes** |

### 1.4 Key Differentiators of MSTool-AI

1. **CVS/PRL biomarker support** — aligned with the 2024 revised McDonald criteria. No commercial competitor currently offers this. This represents a significant first-mover advantage as the criteria gain clinical adoption.

2. **MAGNIMS two-tier region classification** — combining SynthSeg parcellation with EDT distance transforms and MSMask atlas fallback. More methodologically rigorous than geometric heuristics used by most competitors.

3. **Full-stack research platform** — viewer + segmentation + analysis + AI reporting + edge AI + MCP in a single application, vs. single-purpose commercial tools that require integration of multiple products.

4. **NIfTI-native support** — enables direct integration with research pipelines (FreeSurfer, FSL, ANTs, LST-AI), bridging the research-clinical gap that DICOM-only tools cannot.

5. **LLM-powered clinical reporting** — Claude API integration with MAGNIMS-compliant formatting guidelines, multi-language support, and HIPAA-compliant de-identification pipeline.

6. **Model Context Protocol** — 22 MCP tools enabling Claude-native agentic workflows for MS analysis, positioning the platform for the emerging AI agent paradigm in clinical imaging.

---

## 2. Regulatory Requirements for Hospital Deployment in Germany

### 2.1 EU Medical Device Regulation (MDR) Classification

Under MDR Annex VIII Rule 11, MSTool-AI's classification depends on its **intended purpose**:

| Intended Purpose | MDR Class | Rationale | Implications |
|-----------------|-----------|-----------|-------------|
| Visualization-only (no diagnostic claims) | Class I | Software not intended for diagnostic purposes | Self-certification, no Notified Body |
| Monitoring aid (lesion tracking, volumetry trends) | **Class IIa** | Provides information used for monitoring serious conditions | Notified Body audit required |
| Diagnostic support (DIS assessment, lesion classification) | **Class IIb** | Supports diagnosis of MS, errors could cause significant harm | Full Notified Body conformity assessment |

**Recommendation**: Define intended purpose as **Class IIa monitoring/quantification aid** initially, with a roadmap to Class IIb diagnostic support. This balances regulatory burden with clinical utility.

### 2.2 Required Standards and Certifications

| Standard | Purpose | Timeline | Status in MSTool-AI |
|----------|---------|----------|-------------------|
| **ISO 13485** | Quality Management System | Must be in place before CE submission | **Not implemented** |
| **IEC 62304** | Software lifecycle processes | Mandatory (harmonized standard) | **Not documented** (retroactive documentation possible) |
| **ISO 14971** | Risk management | Mandatory | **Not formalized** |
| **IEC 62366** | Usability engineering | Mandatory | **Not documented** |
| **IEC 82304-1** | Health software product safety | Mandatory for standalone SaMD | **Not implemented** |
| **ISO 27001** | Information security | Required for DiGA; strongly recommended | **Partially implemented** (controls exist, no certification) |
| **BSI IT-Grundschutz** | Germany-specific security | Required for KRITIS hospitals | **Not assessed** |
| **GDPR / BDSG** | Data protection | Mandatory | **Partially implemented** (de-identification, audit logging) |

### 2.3 EU AI Act (Effective August 2026)

MSTool-AI's AI components (SynthSeg proxy, lesion classification, Claude report generation, edge AI screening) fall under the **high-risk AI** classification when used with medical devices. Additional requirements:

- **Training data governance**: Documentation of datasets, preprocessing, bias assessment
- **Transparency**: Clinically interpretable outputs, uncertainty quantification
- **Robustness**: Testing across demographic subgroups, scanner manufacturers, field strengths
- **Human oversight**: Physician review must be mandatory (cannot be autonomous)
- **Conformity assessment**: Integrated with MDR process

**Full compliance deadline: August 2027.**

### 2.4 Germany-Specific Requirements

**NIS2 Directive** (transposed December 6, 2025):
- Hospitals are **"essential entities"** — immediate compliance required
- 24-hour incident reporting to BSI (Bundesamt für Sicherheit in der Informationstechnik)
- Risk-based cybersecurity management
- Supply chain security (includes cloud providers: Google Cloud, Firebase)
- **Personal sanctions for senior management** non-compliance

**BSI C5** (Cloud Computing Compliance Criteria Catalogue):
- Required for cloud-hosted medical software in German hospitals
- Google Cloud Platform has BSI C5 Type 2 attestation — MSTool-AI benefits from this, but application-level controls must still be demonstrated

**Medical Professional Secrecy** (StGB §203):
- Criminal liability for disclosure of patient information
- Extends beyond GDPR — includes all persons involved in data processing
- Cloud processing requires explicit patient consent or legal basis

### 2.5 Estimated CE Marking Timeline

```
Months 1-3:   Define intended purpose, gap analysis, QMS planning
Months 3-9:   Implement ISO 13485 QMS, begin IEC 62304 documentation
Months 6-12:  Risk management file (ISO 14971), usability study (IEC 62366)
Months 9-15:  Clinical evaluation (literature review + clinical investigation plan)
Months 12-18: Technical documentation compilation, Notified Body engagement
Months 18-24: Notified Body audit, conformity assessment, CE marking
Months 24+:   Post-market surveillance, periodic safety updates
```

**Estimated cost**: EUR 200,000 – 500,000 for Class IIa (including Notified Body fees, consultant support, clinical evaluation).

---

## 3. Clinical Validation Requirements

### 3.1 CLAIM 2024 Checklist

The Checklist for Artificial Intelligence in Medical Imaging (CLAIM 2024 Update), developed through a 72-member expert Delphi panel, is the reporting standard expected by reviewers. Key requirements for MSTool-AI:

| CLAIM Category | Requirement | MSTool-AI Status |
|---------------|-------------|-----------------|
| Study Design | Clear definition of clinical task and AI role | **Not documented** |
| Data | Dataset demographics, acquisition parameters, inclusion/exclusion | **Not documented** |
| Reference Standard | Expert annotation protocol, inter-rater reliability | **Not assessed** |
| Model | Architecture description, training methodology | **Documented** (SynthSeg, Claude) |
| Evaluation | Metrics with confidence intervals, statistical tests | **Not performed** |
| External Validation | Independent dataset from different institution/scanner | **Not performed** |
| Subgroup Analysis | Performance by age, sex, scanner, disease severity | **Not performed** |
| Failure Mode Analysis | Systematic characterization of failure cases | **Not performed** |

### 3.2 Validation Study Design Recommendations

**Phase 1 — Technical Validation** (internal):
- Benchmark lesion segmentation against ISBI 2015, MSLesSeg (2025) datasets
- Measure Dice, HD95, volume correlation against expert annotations
- Compare MAGNIMS classification against manual expert classification
- Test across multiple scanner manufacturers (Siemens, GE, Philips) and field strengths (1.5T, 3T)

**Phase 2 — Clinical Validation** (external):
- Multi-center study (minimum 3 sites) with independent expert neuroradiologists
- Minimum 100 patients with confirmed MS diagnosis
- Inter-rater reliability assessment (expert vs. MSTool-AI vs. expert)
- Subgroup analysis: RRMS vs. PPMS, pediatric vs. adult, high vs. low lesion burden

**Phase 3 — Usability Validation**:
- System Usability Scale (SUS) with practicing neuroradiologists
- Task completion time comparison: MSTool-AI vs. standard workflow
- Error rate analysis in clinical scenarios

### 3.3 Reference Datasets

| Dataset | Size | Annotations | Availability |
|---------|------|-------------|-------------|
| **ISBI 2015 MS Lesion** | 21 cases (5 training, 14 test) | Expert consensus | Public |
| **MSLesSeg (2025)** | 115 scans, 75 patients | T1 + T2 + FLAIR, expert-validated | Public (Nature Scientific Data) |
| **MSSEG-2 (MICCAI)** | 15 patients, multi-expert | Multiple raters | By request |
| **LST-AI Training Set** | 491 T1/FLAIR pairs, 3T | Expert neuroradiologist annotations | Not public (TUM/CompImg) |

### 3.4 McDonald 2024 / MAGNIMS 2024 Alignment

The 2024 revised McDonald criteria and MAGNIMS consensus represent the most significant update to MS diagnostic criteria in a decade. Key changes relevant to MSTool-AI:

| Criterion Change | MSTool-AI Support | Competitor Support |
|-----------------|------------------|-------------------|
| Optic nerve as 5th DIS location | **Not implemented** (requires dedicated imaging) | Not implemented |
| CVS incorporated as diagnostic biomarker | **Implemented** | **Not available** in any commercial tool |
| PRL incorporated as diagnostic biomarker | **Implemented** | **Not available** in any commercial tool |
| Susceptibility-sensitive sequences required | NIfTI support (SWI/QSM) | DICOM only |
| Stricter criteria for patients >50 years | **Not implemented** (age-adjusted thresholds) | Partial (NeuroQuant) |

**Strategic implication**: MSTool-AI's CVS/PRL support positions it ahead of all commercial competitors in alignment with the latest diagnostic criteria. This is a compelling differentiator for the TUM evaluation committee.

---

## 4. Technical Gap Analysis for Hospital Integration

### 4.1 Critical Gaps (Blocking Hospital Deployment)

#### 4.1.1 DICOMweb Integration

**Current state**: MSTool-AI uses custom REST endpoints for NIfTI/DICOM file transfer.
**Required**: DICOMweb (WADO-RS, STOW-RS, QIDO-RS) for PACS connectivity.

**Impact**: Without DICOMweb, the platform cannot:
- Receive studies directly from hospital PACS
- Return segmentation results as DICOM-SEG objects
- Integrate into the radiology reading workflow

**Reference implementation**: OHIF Viewer is built entirely on DICOMweb. Orthanc and dcm4chee-arc-light provide open-source DICOMweb-compliant servers.

**Effort estimate**: 3-4 weeks for basic WADO-RS retrieval; 6-8 weeks for full bidirectional integration.

#### 4.1.2 DICOM Structured Reporting (DICOM-SR / DICOM-SEG)

**Current state**: Reports generated as text/PDF. Segmentation masks stored as NIfTI.
**Required**: DICOM-SEG for segmentation masks, DICOM-SR for structured reports.

**Impact**: Without DICOM-SEG/SR, results cannot be archived in the hospital PACS alongside the original study, breaking the clinical audit trail.

**Effort estimate**: 2-3 weeks using highdicom library (requires pydicom >= 3.0, currently blocked by dependency conflict with pydicom 2.4.4).

#### 4.1.3 HL7 FHIR ImagingStudy

**Current state**: No FHIR support.
**Required**: FHIR ImagingStudy resource for EHR/HIS integration.

**Impact**: Cannot link imaging findings to the patient's electronic health record, limiting clinical utility.

**Effort estimate**: 2-3 weeks for basic ImagingStudy resource generation and DiagnosticReport creation.

#### 4.1.4 Authentication Architecture

**Current state**: Multiple auth modules with known bugs (dual TokenManager, missing AuthService methods, duplicate endpoints, secrets in version control).
**Required**: Unified, tested, auditable authentication system.

**Impact**: Current state would fail any security audit. Specifically:
- `JWT_SECRET_KEY` and `ANTHROPIC_API_KEY` committed to `env.yaml`
- 5 missing AuthService methods causing runtime crashes
- Duplicate `/auth/login`, `/auth/register`, `/auth/me` endpoints
- Hardcoded admin credentials in `main.py`

**Effort estimate**: 1-2 weeks for complete auth refactor.

### 4.2 High Priority Gaps

#### 4.2.1 Test Coverage

**Current state**: ~5,300 lines of tests (< 10% coverage estimated).
**Required for IEC 62304**: Comprehensive test suite with documented traceability to requirements.

| Test Type | Current | Required |
|-----------|---------|----------|
| Unit tests | Partial (hooks, services) | > 80% coverage |
| Integration tests | None | API endpoint coverage |
| End-to-end tests | None | Critical user workflows |
| Regression tests | None | Golden dataset validation |
| Performance tests | None | Load testing under concurrent users |

**Effort estimate**: 4-6 weeks for comprehensive test suite.

#### 4.2.2 Voxel Spacing Accuracy

**Current state**: Longitudinal tracking and volumetry use hardcoded voxel spacing (1,1,1) mm when metadata unavailable.
**Required**: Accurate voxel spacing from NIfTI/DICOM headers for all quantitative measurements.

**Impact**: Volume measurements may be inaccurate by factors of 2-10x if voxel spacing differs from 1mm isotropic. This is unacceptable for clinical volumetry.

**Effort estimate**: 1 week.

#### 4.2.3 Monitoring and Observability

**Current state**: Console logging only.
**Required**: Structured logging, APM (Application Performance Monitoring), health checks, alerting.

**Recommended stack**: Google Cloud Monitoring + Cloud Logging (already in GCP ecosystem), or Grafana + Prometheus.

**Effort estimate**: 1-2 weeks.

### 4.3 Medium Priority Gaps

| Gap | Description | Effort |
|-----|-------------|--------|
| Hanging protocols | Auto-configure viewer layout by study type | 2 weeks |
| Measurement tools | Ruler, angle, ROI ellipse/circle | 2 weeks |
| Text annotations | Free-text overlays on images | 1 week |
| DICOM GSDF | Grayscale Standard Display Function for calibrated monitors | 1 week |
| Offline mode | Service worker for intermittent connectivity | 2 weeks |
| Worklist | Pending studies queue for reading workflow | 2 weeks |
| Export to PDF | Print views as clinical-quality PDF | 1 week |
| Database migration | PostgreSQL for relational data (alongside Firestore) | 2 weeks |
| Backup & DR | Automated backups with disaster recovery plan | 1 week |

---

## 5. Security Assessment

### 5.1 Current Security Posture

| Control | Status | Gap |
|---------|--------|-----|
| Authentication (Firebase + WebAuthn) | **Implemented** | Auth architecture needs refactoring |
| Encryption at rest (AES-256-GCM) | **Implemented** | — |
| Encryption in transit (TLS) | **Implemented** (Cloud Run default) | — |
| RBAC (4 roles, 15 permissions) | **Implemented** | — |
| Audit logging | **Implemented** | Not HIPAA-certified |
| De-identification (AI reports) | **Implemented** | Not formally validated |
| Rate limiting | **Implemented** | — |
| Input validation (Pydantic) | **Implemented** | — |
| Secrets management | **CRITICAL GAP** | JWT_SECRET_KEY and ANTHROPIC_API_KEY in env.yaml |
| Penetration testing | **Not performed** | Required before go-live |
| DPIA (Data Protection Impact Assessment) | **Not performed** | Mandatory under GDPR |
| BSI IT-Grundschutz assessment | **Not performed** | Required for KRITIS hospitals |
| NIS2 compliance | **Not assessed** | Immediate requirement |
| Vulnerability scanning | **Not performed** | Required for IEC 62304 |

### 5.2 Critical Security Actions

1. **Immediately**: Remove secrets from `env.yaml`, migrate to Cloud Secret Manager
2. **Before pilot**: External penetration test by accredited firm
3. **Before go-live**: DPIA, BSI IT-Grundschutz self-assessment, NIS2 compliance documentation

---

## 6. AI/ML Production Readiness

### 6.1 AI Components Assessment

| Component | Model | Validation Status | Production Readiness |
|-----------|-------|------------------|---------------------|
| Brain parcellation | SynthSeg (FreeSurfer) | Multi-center validated (260 CT/MRI) | **Research only** — not independently FDA/CE cleared |
| Lesion segmentation | Vertex AI proxy | Depends on deployed model | **Not validated** — model not specified |
| Region classification | EDT + MSMask atlas | No formal validation | **Research only** — needs clinical study |
| Report generation | Claude API | No clinical validation | **Assistive only** — physician review mandatory |
| Edge screening | ONNX (user-supplied) | No validation | **Research only** — model not included |

### 6.2 AI Hallucination Risk

Current literature reports LLM hallucination rates of 8-15% in radiology report generation. MSTool-AI must:
- Clearly label AI-generated reports as "AI-assisted, requires physician review"
- Implement confidence scoring or uncertainty indicators
- Maintain audit trail of all AI-generated content
- Provide mechanism for physician to flag/correct AI errors

### 6.3 Regulatory Classification of AI Components

Under the EU AI Act (effective August 2026), all AI components in MSTool-AI are **high-risk AI systems** when used in conjunction with a medical device. Requirements include:
- Technical documentation of all AI models
- Data governance for training datasets
- Transparency and explainability
- Human oversight mechanisms
- Post-market monitoring of AI performance

---

## 7. Performance Benchmarks

### 7.1 Industry Reference (Pereira et al., JIIM 2025)

The definitive benchmark for web-based DICOM viewers (16 viewers evaluated):

| Metric | OHIF (best) | Clinical Acceptable | MSTool-AI Target |
|--------|------------|-------------------|-----------------|
| 2D rendering | 0.72-2.56s | < 3s | < 2s |
| 3D rendering | 0.93-3.70s | < 5s | < 4s |
| Feature completeness | 26/29 | 20+/29 | 24+/29 |

### 7.2 MS-Specific Processing Benchmarks

| Operation | Industry Standard | Target |
|-----------|------------------|--------|
| Full MS analysis pipeline | < 5-6 min (Neurophet, Pixyl) | < 5 min |
| Lesion segmentation | < 2 min (LST-AI) | < 3 min |
| Brain volumetry | < 3 min (NeuroQuant) | < 3 min |
| Report generation | < 30s (Claude API) | < 30s |
| Study loading | < 3s (cloud viewer) | < 3s |

---

## 8. Recommended Roadmap

### Phase 1: Security & Stability (Weeks 1-4)

- [ ] Remove secrets from version control, migrate to Cloud Secret Manager
- [ ] Refactor auth system (eliminate duplicates, implement missing methods)
- [ ] Fix voxel spacing accuracy in volumetry and longitudinal tracking
- [ ] Comprehensive error handling audit (no silent `except Exception`)
- [ ] Automated backup configuration

### Phase 2: Hospital Integration (Weeks 5-12)

- [ ] DICOMweb (WADO-RS) retrieval from PACS
- [ ] DICOM-SEG export for segmentation masks
- [ ] HL7 FHIR ImagingStudy resource generation
- [ ] DICOMweb (STOW-RS) for returning results to PACS
- [ ] Performance benchmarking against JIIM 2025 methodology

### Phase 3: Testing & Validation (Weeks 8-16)

- [ ] Unit test suite (> 80% coverage)
- [ ] Integration test suite (all API endpoints)
- [ ] End-to-end test suite (critical clinical workflows)
- [ ] External penetration test
- [ ] DPIA documentation

### Phase 4: Clinical Validation Study (Weeks 12-24)

- [ ] IRB/ethics approval
- [ ] Multi-center protocol design (minimum 3 sites, 100 patients)
- [ ] Inter-rater reliability study (MSTool-AI vs. expert neuroradiologists)
- [ ] MAGNIMS classification validation against manual expert consensus
- [ ] Longitudinal tracking validation on serial MS cohort
- [ ] CLAIM 2024 checklist compliance

### Phase 5: Regulatory Preparation (Months 6-18)

- [ ] Define intended purpose (Class IIa monitoring aid)
- [ ] ISO 13485 QMS implementation
- [ ] IEC 62304 software lifecycle documentation
- [ ] ISO 14971 risk management file
- [ ] IEC 62366 usability engineering file
- [ ] Notified Body engagement
- [ ] CE marking conformity assessment

### Phase 6: Pilot Deployment (Months 18-24)

- [ ] Hospital IT infrastructure integration
- [ ] Staff training program
- [ ] Monitored clinical pilot (supervised use)
- [ ] Post-market surveillance system
- [ ] Feedback collection and iteration

---

## 9. Strategic Positioning for TUM

### 9.1 Research Contribution

MSTool-AI represents a contribution at the intersection of:
- **Medical image computing**: Novel two-tier MAGNIMS classification with SynthSeg parcellation
- **Clinical AI**: LLM-powered structured reporting with HIPAA-compliant de-identification
- **Software engineering**: Full-stack cloud-native architecture (82,400 LOC) with edge AI and MCP integration
- **Clinical neuroscience**: McDonald 2024 compliance including CVS/PRL biomarkers

### 9.2 Publication Opportunities

| Venue | Focus | Type |
|-------|-------|------|
| NeuroImage: Clinical | MAGNIMS classification validation study | Original research |
| Radiology: AI | LLM-assisted MS reporting with clinical validation | Original research |
| MICCAI Workshop | Edge AI + MCP architecture for clinical imaging | Workshop paper |
| Journal of Medical Internet Research | Web-based MS monitoring platform usability study | Original research |
| Frontiers in Neurology | Longitudinal tracking with McDonald 2024 criteria | Original research |

### 9.3 Collaboration Potential

MSTool-AI's NIfTI-native architecture enables direct integration with:
- **LST-AI** (CompImg/TUM): Replace Vertex AI proxy with locally-deployed LST-AI for validated MS lesion segmentation
- **FreeSurfer/SynthSeg**: Already integrated; validation studies possible
- **MAGNIMS consortium**: MAGNIMS classification module could be validated on consortium data
- **German MS Registry (DMSG)**: Longitudinal tracking module applicable to registry data

---

## References

1. Montalban, X., et al. (2025). Revised McDonald criteria for the diagnosis of multiple sclerosis. *Lancet Neurology*, 24(10), 850–865.
2. Barkhof, F., et al. (2025). MAGNIMS-CMSC-NAIMS 2024 consensus guidelines on the use of MRI in patients with multiple sclerosis. *Lancet Neurology*, 24(10), 866–879.
3. Wiltgen, T., et al. (2024). LST-AI: A deep learning ensemble for accurate MS lesion segmentation. *NeuroImage: Clinical*, 42, 103611.
4. Pereira, S., et al. (2025). Web-based DICOM viewers: A survey and performance classification. *Journal of Imaging Informatics in Medicine*.
5. Billot, B., et al. (2023). SynthSeg: Segmentation of brain MRI scans of any contrast and resolution without retraining. *Medical Image Analysis*, 86, 102789.
6. CLAIM Working Group (2024). Checklist for Artificial Intelligence in Medical Imaging — 2024 Update. *Radiology: AI*, 6(5).
7. EU Regulation 2017/745 (MDR). Medical Device Regulation, Annex VIII Rule 11.
8. EU Regulation 2024/1689 (AI Act). Artificial Intelligence Act, Chapter III (High-Risk AI Systems).
9. BSI (2025). IT-Grundschutz Compendium — Healthcare Module. Bundesamt für Sicherheit in der Informationstechnik.
10. NIS2 Directive 2022/2555, transposed via BSI-Gesetz (Germany), effective December 6, 2025.

---

*This document is intended for internal evaluation purposes. Clinical claims are subject to regulatory validation.*
