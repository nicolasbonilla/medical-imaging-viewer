# MSTool-AI: Technical Documentation

**Document ID**: TD-001 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: EU MDR 2017/745 Annex II

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Device Description and Specification (Annex II, Section 1)

### 1.1 Device Name and Identification

- **Trade Name**: MSTool-AI
- **Device Type**: Software as a Medical Device (SaMD)
- **GMDN Code**: 62518 — Software for image analysis and interpretation
- **UDI-DI**: To be assigned upon registration
- **Basic UDI-DI**: To be assigned upon registration
- **Software Version**: See release notes (current: v3.x)

### 1.2 Intended Purpose

MSTool-AI is a cloud-native Software as a Medical Device (SaMD) intended to assist qualified healthcare professionals (radiologists, neurologists) in the analysis of brain MRI images. The software provides:

1. **AI-assisted brain segmentation** — Automated parcellation of brain structures using SynthSeg-based models via Vertex AI
2. **Brain volumetry** — Quantitative measurement of brain structure volumes with normative comparison (age/sex-adjusted percentiles)
3. **MS lesion analysis** — Connected-component lesion detection, MAGNIMS region classification (periventricular, juxtacortical, infratentorial, deep white matter), and DIS (Dissemination in Space) assessment per McDonald 2024 criteria
4. **Longitudinal tracking** — Comparison of lesion burden across timepoints (NEW, RESOLVED, ENLARGED, SHRUNK, STABLE)
5. **AI-generated clinical reports** — Structured radiology reports using Claude API with HIPAA-compliant de-identified findings
6. **Edge AI screening** — Browser-based ONNX Runtime Web classification for rapid normal/abnormal triage

The software is an assistive tool only. It does not provide standalone diagnoses and all results require verification by a qualified clinician.

### 1.3 Intended Users

- Radiologists and neuroradiologists
- Neurologists specializing in multiple sclerosis and demyelinating diseases
- Clinical researchers in neuroimaging

### 1.4 Patient Population

- Adult patients (18+ years) undergoing brain MRI for suspected or confirmed neurological conditions
- Primary focus: Multiple Sclerosis (MS) patients requiring longitudinal monitoring

### 1.5 Technical Architecture

- **Frontend**: React 18 + Vite + TypeScript, deployed on Firebase Hosting
- **Backend**: FastAPI (Python 3.11+), deployed on Google Cloud Run
- **AI Services**: Vertex AI (SynthSeg segmentation), Anthropic Claude API (report generation), ONNX Runtime Web (edge screening)
- **Data Storage**: Google Cloud Storage (DICOM/NIfTI files), Cloud Firestore (metadata)
- **Authentication**: Firebase Authentication with JWT tokens
- **Communication**: REST API over HTTPS (TLS 1.2+)

### 1.6 Medical Device Software Safety Classification

- **IEC 62304 Safety Class**: Class C (highest)
- **IEC 82304-1 Health Software**: Applicable
- **IMDRF SaMD Classification**: Category II (Inform clinical management, Serious condition)

### 1.7 Accessories and SOUP Components

No physical accessories. Software Of Unknown Provenance (SOUP) components are documented in SOUP-001 (IEC 62304 Section 8). Key SOUP includes:
- ONNX Runtime Web (edge inference)
- SynthSeg model (brain parcellation)
- Anthropic Claude API (report generation)
- SciPy (connected-component analysis)
- NumPy (volumetric computation)

---

## 2. Information Supplied by the Manufacturer (Annex II, Section 2)

### 2.1 Labelling and Instructions for Use

All labelling complies with EU MDR Annex I Chapter III and EN ISO 20417:2021.

| Document | ID | Description |
|----------|----|-------------|
| Instructions for Use | IFU-001 | Complete usage instructions, warnings, contraindications |
| Quick Start Guide | — | Abbreviated setup and workflow guide |
| In-app Disclaimers | — | AI-assisted result warnings displayed at point of use |

### 2.2 Languages

User interface and documentation available in English, Spanish, and German (i18n keys: `en.json`, `es.json`, `de.json`).

---

## 3. Design and Manufacturing Information (Annex II, Section 3)

### 3.1 Software Development Lifecycle

MSTool-AI is developed under a controlled software development lifecycle compliant with IEC 62304:2006+A1:2015 for Class C medical device software.

| Phase | Document | ID |
|-------|----------|----|
| Development Planning | Software Development Plan | SDP-001 |
| Requirements Analysis | Software Requirements Specification | SRS-001 |
| Architectural Design | Software Architecture Design | SAD-001 |
| Detailed Design | Detailed Design Specification | DD-001 |
| Implementation | Coding Standards (within SDP-001) | — |
| Integration & Testing | Verification & Validation Plan | VVP-001 |
| Configuration Management | Configuration Management Plan | CMP-001 |
| Problem Resolution | Problem Resolution Procedure | PRP-001 |
| SOUP Management | SOUP Bill of Materials | SOUP-001 |
| Maintenance | Maintenance Plan | MP-001 |
| Traceability | Traceability Matrix | TM-001 |
| Release | Release Procedure | RP-001 |

### 3.2 Quality Management System

The QMS is described in QM-001 and covers design controls, document control, CAPA, supplier management, and post-market activities per ISO 13485:2016.

### 3.3 Design and Development Controls

All design changes follow the change control process defined in CMP-001. Each change is traced from requirement (SRS-001) through design (SAD-001, DD-001) to verification (VVP-001) via TM-001.

---

## 4. General Safety and Performance Requirements (Annex II, Section 4)

Compliance with EU MDR Annex I General Safety and Performance Requirements is documented in GSPR-001.

The GSPR checklist demonstrates compliance with all 23 requirements, including:
- GSPR 14: Software lifecycle per IEC 62304
- GSPR 17: Electronic programmable systems validation and cybersecurity per IEC 81001-5-1
- GSPR 22: Diagnostic and measuring function accuracy

Applied harmonized standards:
- IEC 62304:2006+A1:2015 — Medical device software lifecycle
- ISO 14971:2019 — Risk management
- IEC 62366-1:2015+A1:2020 — Usability engineering
- IEC 81001-5-1:2021 — Health software cybersecurity
- EN ISO 20417:2021 — Information supplied by manufacturer

---

## 5. Benefit-Risk Analysis (Annex II, Section 5)

### 5.1 Clinical Evaluation

The Clinical Evaluation Report (CER-001) demonstrates that clinical benefits outweigh residual risks through:
- Literature review of SynthSeg validation studies
- Equivalence analysis with predicate SaMD devices
- Performance data from verification and validation activities (VVP-001)

### 5.2 Risk Management

Risk management is conducted per ISO 14971:2019 and documented in RMF-001. Key risk controls include:
- All AI outputs marked as "assistive — requires clinical verification"
- Radiologist-in-the-loop design (no autonomous decisions)
- Input validation for DICOM/NIfTI data integrity
- Graceful degradation when AI services unavailable
- Edge AI disclaimer: "assistive tool only, not diagnostic"

### 5.3 Residual Risk Acceptability

Residual risks are documented in RMF-001 Section 7. The overall residual risk is acceptable when weighed against the clinical benefits of:
- Reduced inter-reader variability in lesion counting
- Quantitative volumetric tracking over time
- Standardized MAGNIMS region classification
- Time savings in structured report generation

---

## 6. Product Verification and Validation (Annex II, Section 6)

### 6.1 Verification Activities

| Activity | Document | Status |
|----------|----------|--------|
| Unit Testing | VVP-001 Section 4 | Per release |
| Integration Testing | VVP-001 Section 5 | Per release |
| API Endpoint Testing | `test_endpoints.sh` (9 checks) | Per deployment |
| Static Analysis | SDP-001 coding standards | Continuous |
| SOUP Verification | SOUP-001 | Per update |

### 6.2 Validation Activities

| Activity | Document | Status |
|----------|----------|--------|
| Usability Validation | IEC 62366-1 Usability File | Planned |
| Clinical Validation | CER-001 | Planned |
| Performance Validation | VVP-001 Section 6 | Per release |

### 6.3 Test Records

Test execution records are maintained in `docs/iec62304/records/` per the Verification & Validation Plan (VVP-001).

---

## 7. UDI Information

| Field | Value |
|-------|-------|
| UDI-DI | To be assigned |
| Basic UDI-DI | To be assigned |
| UDI Database | EUDAMED |
| Issuing Entity | GS1 (planned) |
| SRN | To be assigned upon EU registration |

---

## 8. Device Classification Justification

### 8.1 Applicable Classification Rule

**EU MDR Annex VIII, Rule 11**: Software intended to provide information used to take decisions with diagnosis or therapeutic purposes is classified as Class IIa.

### 8.2 Rationale

MSTool-AI provides information (AI-assisted segmentation, volumetry, lesion classification, reports) that is used by clinicians to inform diagnostic decisions regarding neurological conditions (serious conditions). The software:
- Does not directly control or monitor patient treatment
- Provides decision-support information to qualified clinicians
- Addresses serious but non-immediately-life-threatening conditions (MS monitoring)

Per Rule 11: Software intended to provide information used for diagnosis or therapeutic decisions regarding serious conditions is classified as **Class IIa**.

> Note: The IEC 62304 safety classification of Class C reflects the highest software safety class to ensure maximum rigor in the development process, independent of the EU MDR device classification.

---

## 9. Referenced Documents

| ID | Title |
|----|-------|
| SDP-001 | Software Development Plan |
| SRS-001 | Software Requirements Specification |
| SAD-001 | Software Architecture Design |
| DD-001 | Detailed Design Specification |
| CMP-001 | Configuration Management Plan |
| VVP-001 | Verification & Validation Plan |
| RMF-001 | Risk Management File |
| SOUP-001 | SOUP Bill of Materials |
| QM-001 | Quality Management System Manual |
| CER-001 | Clinical Evaluation Report |
| GSPR-001 | General Safety and Performance Requirements |
| IFU-001 | Instructions for Use |
| PMS-001 | Post-Market Surveillance Plan |
| AIA-001 | AI Act Compliance Document |

---

*End of Document*
