# MSTool-AI: AI Act Compliance Document

**Document ID**: AIA-001 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: EU AI Act — Regulation (EU) 2024/1689

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Purpose

This document demonstrates MSTool-AI's compliance with the European Union Artificial Intelligence Act (Regulation (EU) 2024/1689), which entered into force on August 1, 2024. MSTool-AI incorporates multiple AI/ML components and, as a medical device with AI functionality, is classified as a high-risk AI system.

---

## 2. AI System Description

### 2.1 AI/ML Components in MSTool-AI

MSTool-AI integrates four distinct AI/ML components:

| Component | Type | Deployment | Function |
|-----------|------|-----------|----------|
| **SynthSeg Brain Segmentation** | Deep learning (CNN) | Vertex AI (cloud) | Automated parcellation of 33 brain structures from MRI |
| **ONNX Edge AI Screening** | Neural network (binary classifier) | Browser (ONNX Runtime Web) | Rapid normal/abnormal triage of brain MRI slices |
| **Claude API Report Generation** | Large language model (LLM) | Anthropic Cloud API | Generation of structured clinical reports from findings |
| **EDT-based MAGNIMS Classification** | Algorithmic (distance transform + rules) | Backend (Python/NumPy/SciPy) | Region classification of MS lesions per McDonald 2024 |

### 2.2 AI Component Details

**SynthSeg Brain Segmentation**
- Architecture: Convolutional Neural Network (SynthSeg variant)
- Training: Synthetic data augmentation approach (domain-randomized training)
- Inference: Vertex AI endpoint (Google Cloud)
- Output: 3D segmentation mask with 33 FreeSurfer structure labels

**ONNX Edge AI Screening**
- Architecture: Lightweight CNN for binary classification
- Input: 224x224 bilinear-interpolated grayscale brain MRI slice
- Inference: Browser-based via ONNX Runtime Web (WebGPU/WASM)
- Output: Normal/abnormal classification with confidence score

**Claude API Report Generation**
- Model: Anthropic Claude (large language model)
- Input: De-identified volumetry data, lesion analysis findings, clinical context (HIPAA-compliant)
- Output: Structured clinical report text (general, stroke, tumor, dementia, MS longitudinal templates)
- Safety: No patient identifiers transmitted; de-identified findings only

**EDT-based MAGNIMS Classification**
- Method: Euclidean Distance Transform with rule-based thresholds
- Tier 2: SynthSeg parcellation + EDT (PV<=3mm ventricle, JC<=4mm cortex, IT<=3mm infratentorial)
- Tier 1 fallback: Geometric heuristics (z-coordinate, center distance, surface distance)
- Output: Per-lesion region label, confidence score, distance metadata

---

## 3. Risk Classification

### 3.1 High-Risk AI System Determination

MSTool-AI is classified as a **High-Risk AI System** under the EU AI Act:

- **Article 6(1)**: MSTool-AI is a medical device covered by Regulation (EU) 2017/745 (MDR) and subject to third-party conformity assessment (Class IIa, Annex IX).
- **Annex I, Section A, Point 11**: Medical devices regulated under Regulation (EU) 2017/745 are listed as products whose AI components are high-risk when the device itself requires third-party conformity assessment.

### 3.2 Prohibited Practices Assessment (Article 5)

None of the prohibited AI practices under Article 5 apply to MSTool-AI. The system does not:
- Deploy subliminal techniques to manipulate behavior
- Exploit vulnerabilities of specific groups
- Perform social scoring
- Use real-time remote biometric identification in public spaces

---

## 4. Compliance with Chapter 3, Section 2 — Requirements for High-Risk AI Systems

### 4.1 Article 9: Risk Management System

**Requirement**: Establish, implement, document, and maintain a risk management system throughout the AI system's lifecycle.

**MSTool-AI Compliance**:
- Risk management per ISO 14971:2019 is documented in RMF-001 (Risk Management File)
- AI-specific risks identified and controlled:
  - Segmentation false negatives (missed lesions) — mitigated by radiologist review requirement
  - Volumetric measurement errors — mitigated by validation against reference datasets
  - MAGNIMS misclassification — mitigated by confidence scoring and Tier 1/Tier 2 transparency
  - LLM hallucination in reports — mitigated by mandatory clinician review, disclaimer text
  - Edge AI false negatives — mitigated by "assistive only" labeling and disclaimer
- Risk controls verified through VVP-001 (Verification & Validation Plan)
- Residual risk evaluation documented in RMF-001 Section 7

**Mapped Document**: RMF-001

### 4.2 Article 10: Data and Data Governance

**Requirement**: Training, validation, and testing data sets shall be subject to appropriate data governance and management practices.

**MSTool-AI Compliance**:

| Component | Training Data Governance |
|-----------|------------------------|
| SynthSeg | Trained on synthetic data (domain-randomized). Published methodology with known limitations. Validation on multi-site, multi-scanner datasets in peer-reviewed literature. |
| ONNX Edge AI | Training dataset documentation maintained. Bias assessment for demographic representation (age, sex, scanner manufacturer). |
| Claude API | Foundation model trained by Anthropic. MSTool-AI uses prompt engineering only (no fine-tuning). De-identified clinical data in prompts. |
| MAGNIMS Classification | Rule-based system using published distance thresholds from McDonald 2024 criteria. No training data required. |

**Data Quality Measures**:
- Input validation for DICOM/NIfTI files (format, dimensions, metadata integrity)
- DICOM anonymization checks before AI processing
- Known limitations documented: performance may vary across MRI scanner manufacturers, field strengths, and acquisition protocols

**Bias Assessment**:
- SynthSeg validated across diverse scanner types and acquisition parameters
- Volumetric normative databases stratified by age and sex
- Known limitation: normative data primarily from adult Western populations; applicability to other demographics requires clinical judgment

**Mapped Document**: SRS-001 (data requirements), VVP-001 (validation datasets)

### 4.3 Article 11: Technical Documentation

**Requirement**: Technical documentation shall be drawn up before the AI system is placed on the market and kept up to date.

**MSTool-AI Compliance**:
- Complete technical documentation per EU MDR Annex II maintained in TD-001
- AI-specific documentation includes:
  - Algorithm descriptions for all four AI components (Section 2 of this document)
  - Key design parameters and choices (model architectures, distance thresholds, confidence scoring)
  - Performance metrics and validation results (VVP-001)
  - Training data descriptions and governance (Section 4.2 above)
  - Known limitations and intended operating conditions

**Mapped Document**: TD-001, DD-001, SAD-001

### 4.4 Article 12: Record-Keeping

**Requirement**: High-risk AI systems shall technically allow for the automatic recording of events (logs) throughout the system's lifetime.

**MSTool-AI Compliance**:
- **Backend Logging**: All API requests logged with timestamps, user IDs, request parameters, and response status (FastAPI middleware)
- **AI Inference Logging**: Segmentation requests, volumetry computations, classification results, and report generation events logged with execution time and model version
- **Audit Trail**: User actions (upload, segment, classify, report generation) recorded with timestamps
- **Error Logging**: All exceptions and failures logged with stack traces and context
- **Retention**: Logs retained per data retention policy (minimum 10 years per MDR Article 10(8))
- **Edge AI**: Browser-based inference results logged locally; classification results with confidence scores available for review

**Mapped Document**: SDP-001 (logging standards), SAD-001 (logging architecture)

### 4.5 Article 13: Transparency and Provision of Information to Deployers

**Requirement**: High-risk AI systems shall be designed and developed to ensure their operation is sufficiently transparent to enable deployers to interpret output and use it appropriately.

**MSTool-AI Compliance**:
- **User Notification**: All AI-assisted results are clearly labeled as AI-generated in the user interface
- **Disclaimers**:
  - "AI-generated results require clinical verification" displayed with every AI output
  - Edge AI badge: "assistive tool only, not diagnostic"
  - Report generation: "AI-generated report — must be reviewed and edited by qualified radiologist"
- **Confidence Indicators**:
  - MAGNIMS classification includes per-lesion confidence scores and distance metadata
  - Edge AI screening displays confidence percentage and inference time
- **Limitations Documentation**: IFU-001 documents all known limitations, contraindications, and appropriate use conditions
- **Classification Method Transparency**: MAGNIMS dashboard shows classification tier (Tier 1/Tier 2) and method used

**Mapped Document**: IFU-001, i18n files (en.json, es.json, de.json)

### 4.6 Article 14: Human Oversight

**Requirement**: High-risk AI systems shall be designed and developed to be effectively overseen by natural persons during use.

**MSTool-AI Compliance**:
- **Radiologist-in-the-Loop**: MSTool-AI is designed as a decision-support tool. No clinical action is taken autonomously. All AI outputs require clinician review and approval.
- **Manual Override**:
  - Segmentation masks can be manually edited (brush/eraser tools) after AI generation
  - MAGNIMS classifications can be manually corrected
  - AI-generated reports are editable text — clinician modifies before use
  - Labels and regions can be manually reassigned
- **Rejection Capability**: Users can discard any AI output and perform manual analysis
- **No Autonomous Decisions**: The system never initiates clinical actions, sends results to patients, or modifies EHR records without explicit clinician action
- **Intervention Points**: Every step of the workflow (segment, classify, volumetry, report) has a review and approval gate

**Mapped Document**: SRS-001 (human oversight requirements), IFU-001 (workflow instructions)

### 4.7 Article 15: Accuracy, Robustness, and Cybersecurity

**Requirement**: High-risk AI systems shall be designed and developed to achieve appropriate levels of accuracy, robustness, and cybersecurity.

**Accuracy**:
- Segmentation accuracy validated per VVP-001 (Dice coefficient against expert annotations)
- Volumetric measurement accuracy validated against known phantoms
- MAGNIMS classification validated against expert consensus
- Performance metrics documented and monitored post-market (PMS-001)

**Robustness**:
- Graceful degradation when AI services unavailable (Vertex AI, Claude API)
- Edge AI automatic fallback from WebGPU to WASM execution
- Input validation for corrupted or malformed image data
- Error boundary components prevent UI crashes from propagating
- Multi-tier MAGNIMS classification (Tier 2 primary, Tier 1 fallback)

**Cybersecurity**:
- Authentication: Firebase JWT tokens with automatic refresh
- Transport: HTTPS/TLS 1.2+ for all communications
- API Security: CORS policies, rate limiting, input sanitization
- SOUP Monitoring: Continuous vulnerability scanning (PMS-001 Section 3.4)
- Data Protection: HIPAA-compliant de-identification for AI report generation
- Access Control: Role-based access to patient data and AI features

**Mapped Document**: VVP-001, CYB-001, RMF-001, PMS-001

---

## 5. Article 17: Quality Management System

**Requirement**: Providers of high-risk AI systems shall put a quality management system in place.

**MSTool-AI Compliance**:

The QMS (QM-001) covers all elements required by Article 17(1):
- (a) Regulatory compliance strategy — documented in TD-001, this document
- (b) Design, design control, and design verification — SDP-001, VVP-001
- (c) Testing and validation — VVP-001, test records
- (d) Technical specifications and standards — GSPR-001
- (e) Risk management — RMF-001 (ISO 14971)
- (f) Post-market monitoring — PMS-001
- (g) Incident reporting and FSCA — PMS-001 Section 4
- (h) Communication with competent authorities and notified bodies — Regulatory Affairs procedures
- (i) Record management — Document control per QM-001
- (j) Resource management — SDP-001
- (k) Accountability framework — QM-001 organizational chart
- (l) Assessment of changes and change management — CMP-001

**Mapped Document**: QM-001, ISO 13485:2016 certification (planned)

---

## 6. Article 72: Post-Market Monitoring

**Requirement**: Providers shall establish and document a post-market monitoring system proportionate to the nature and risks of the AI system.

**MSTool-AI Compliance**:
- Post-market monitoring system established per PMS-001
- AI-specific monitoring includes:
  - Model performance drift detection (quarterly)
  - SOUP/dependency vulnerability scanning (weekly automated, monthly manual)
  - User feedback on AI output quality (semi-annual surveys)
  - Clinical literature monitoring for validation of underlying algorithms (quarterly)
- Post-market monitoring plan updated based on findings
- Integration with EU MDR PSUR process (annually for Class IIa)

**Mapped Document**: PMS-001

---

## 7. Conformity Assessment Pathway

### 7.1 Assessment Route

Per Article 43(1) of the AI Act, for high-risk AI systems that are safety components of medical devices covered by Regulation (EU) 2017/745, the conformity assessment is carried out **through the existing MDR conformity assessment procedure**.

| Aspect | Approach |
|--------|----------|
| **Primary Pathway** | EU MDR Annex IX (Quality Management System and Technical Documentation Assessment) |
| **Notified Body** | MDR Notified Body performs integrated assessment covering both MDR and AI Act requirements |
| **AI-Specific Assessment** | AI Act requirements integrated into MDR technical documentation review |
| **No Separate AI Act Certification** | Single conformity assessment via MDR Notified Body |

### 7.2 Standards Applied

| Standard | Scope |
|----------|-------|
| IEC 62304:2006+A1:2015 | Software lifecycle (MDR + AI Act Article 9, 11) |
| ISO 14971:2019 | Risk management (MDR + AI Act Article 9) |
| IEC 81001-5-1:2021 | Cybersecurity (MDR + AI Act Article 15) |
| IEC 62366-1:2015+A1:2020 | Usability (MDR + AI Act Article 14) |
| ISO/IEC 23894:2023 | AI risk management guidance |
| ISO/IEC 42001:2023 | AI management system (reference) |

---

## 8. Compliance Timeline

| Milestone | Date | Status |
|-----------|------|--------|
| AI Act entered into force | August 1, 2024 | -- |
| Prohibited practices effective | February 2, 2025 | Not applicable (no prohibited practices) |
| GPAI model obligations effective | August 2, 2025 | Not applicable (not a GPAI provider) |
| **High-risk AI system obligations effective** | **August 2, 2027** | In preparation |
| MSTool-AI AI Act compliance target | Q2 2027 | Planned |

---

## 9. Gap Analysis Summary

| AI Act Requirement | Current Status | Gap | Remediation Plan |
|-------------------|----------------|-----|-----------------|
| Article 9: Risk Management | Compliant (ISO 14971) | AI-specific risk taxonomy to formalize | Extend RMF-001 with AI-specific annex by Q4 2026 |
| Article 10: Data Governance | Partial | Formal bias assessment needed for edge AI model | Complete bias assessment by Q1 2027 |
| Article 11: Technical Documentation | Compliant | AI algorithm detail level to enhance | Update DD-001 with detailed AI specs by Q4 2026 |
| Article 12: Record-Keeping | Compliant | Log retention automation to verify | Audit log infrastructure by Q3 2026 |
| Article 13: Transparency | Compliant | None | Maintain current disclaimers and labeling |
| Article 14: Human Oversight | Compliant | None | Maintain radiologist-in-the-loop design |
| Article 15: Accuracy/Robustness | Partial | Formal accuracy benchmarks to publish | Complete validation study by Q1 2027 |
| Article 17: QMS | In Progress | ISO 13485 certification pending | Certification target Q2 2027 |
| Article 72: Post-Market Monitoring | Compliant | AI drift monitoring to operationalize | Deploy monitoring pipeline by Q4 2026 |

---

## 10. Referenced Documents

| ID | Title |
|----|-------|
| TD-001 | Technical Documentation |
| GSPR-001 | General Safety and Performance Requirements |
| RMF-001 | Risk Management File |
| SDP-001 | Software Development Plan |
| SRS-001 | Software Requirements Specification |
| SAD-001 | Software Architecture Design |
| DD-001 | Detailed Design Specification |
| VVP-001 | Verification & Validation Plan |
| CMP-001 | Configuration Management Plan |
| SOUP-001 | SOUP Bill of Materials |
| CYB-001 | Cybersecurity Assessment |
| CER-001 | Clinical Evaluation Report |
| IFU-001 | Instructions for Use |
| PMS-001 | Post-Market Surveillance Plan |
| QM-001 | Quality Management System |

---

*End of Document*
