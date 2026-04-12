# MSTool-AI: General Safety and Performance Requirements

**Document ID**: GSPR-001 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: EU MDR 2017/745 Annex I

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## Purpose

This document demonstrates compliance of MSTool-AI with the General Safety and Performance Requirements (GSPRs) set out in EU MDR 2017/745, Annex I. For each requirement, the applicability, applied standards, evidence references, and compliance status are provided.

---

## Chapter I — General Requirements

### GSPR 1: Safety and Performance Under Normal Conditions

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Requirement** | Devices shall achieve intended performance and shall be designed and manufactured to be safe during normal conditions of use. |
| **Standard Applied** | IEC 62304:2006+A1:2015, ISO 14971:2019 |
| **Evidence** | RMF-001 (Risk Management File), VVP-001 (Verification & Validation Plan), SDP-001 (Software Development Plan) |
| **Compliance Status** | Compliant |
| **Notes** | Software lifecycle processes ensure performance. Risk analysis covers all foreseeable use conditions. |

### GSPR 2: Risk Management

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Requirement** | Manufacturers shall establish, implement, document, and maintain a risk management system. |
| **Standard Applied** | ISO 14971:2019 |
| **Evidence** | RMF-001 (Risk Management File), including hazard analysis, risk evaluation, risk controls, and residual risk assessment |
| **Compliance Status** | Compliant |
| **Notes** | Risk management covers all AI/ML components. Hazard analysis includes misclassification, false negatives, data corruption. |

### GSPR 3: Risk Control Measures

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Requirement** | Risks shall be reduced as far as possible through inherent safety by design, protective measures, and information for safety. |
| **Standard Applied** | ISO 14971:2019 |
| **Evidence** | RMF-001 Sections 5-6 (risk control measures and verification), IFU-001 (warnings and precautions) |
| **Compliance Status** | Compliant |
| **Notes** | Three-tier hierarchy applied: (1) inherently safe design (radiologist-in-the-loop), (2) protective measures (input validation, graceful degradation), (3) information (disclaimers, IFU warnings). |

### GSPR 4: Risk-Benefit Analysis

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Requirement** | Risk control measures shall not adversely affect the benefit-risk ratio. |
| **Standard Applied** | ISO 14971:2019 |
| **Evidence** | RMF-001 Section 7 (overall residual risk), CER-001 (Clinical Evaluation Report) |
| **Compliance Status** | Compliant |

### GSPR 5: Devices for Non-Expert Users

| Field | Value |
|-------|-------|
| **Applicable** | No |
| **Notes** | MSTool-AI is intended exclusively for use by qualified healthcare professionals (radiologists, neurologists). Not a consumer device. |

### GSPR 6: Usability

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Requirement** | Usability and ergonomic principles shall be considered to minimize use error risks. |
| **Standard Applied** | IEC 62366-1:2015+A1:2020 |
| **Evidence** | Usability Engineering File (planned), SRS-001 (usability requirements), keyboard shortcuts documentation |
| **Compliance Status** | In Progress |
| **Notes** | Formative usability evaluation planned. UI follows established radiology viewer conventions. Keyboard shortcuts (?, Ctrl+Z, E, B, S) for efficient workflow. |

### GSPR 7: Product Lifecycle Risk Management

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Requirement** | Risk management and product lifecycle processes shall be systematic and iterative. |
| **Standard Applied** | ISO 14971:2019, IEC 62304:2006+A1:2015 |
| **Evidence** | SDP-001, RMF-001, PMS-001 (Post-Market Surveillance Plan), MP-001 (Maintenance Plan) |
| **Compliance Status** | Compliant |

### GSPR 8: Interaction with Other Devices

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Requirement** | Risks arising from interaction with other devices and substances shall be minimized. |
| **Standard Applied** | ISO 14971:2019 |
| **Evidence** | RMF-001 (interface hazard analysis), SAD-001 (architecture, API contracts) |
| **Compliance Status** | Compliant |
| **Notes** | Software interacts with PACS (DICOM import), Vertex AI, Claude API. All interfaces validated. Graceful degradation when external services unavailable. |

### GSPR 9: Devices with Diagnostic or Measuring Function (General)

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Requirement** | Devices designed with a measuring or diagnostic function shall provide sufficient accuracy and stability. |
| **Standard Applied** | IEC 62304:2006+A1:2015, ISO 14971:2019 |
| **Evidence** | VVP-001 (performance validation), SRS-001 (accuracy requirements) |
| **Compliance Status** | Compliant |
| **Notes** | Volumetric measurements use voxel counting with known voxel dimensions. MAGNIMS classification validated against expert annotations. |

---

## Chapter II — Requirements Regarding Design and Manufacture

### GSPR 10: Chemical, Physical, and Biological Properties

| Field | Value |
|-------|-------|
| **Applicable** | No |
| **Notes** | MSTool-AI is a pure software device with no physical components, materials, or substances in contact with the human body. |

### GSPR 11: Infection and Microbial Contamination

| Field | Value |
|-------|-------|
| **Applicable** | No |
| **Notes** | Pure software device. No physical contact with patients. |

### GSPR 12: Devices Incorporating Substances

| Field | Value |
|-------|-------|
| **Applicable** | No |
| **Notes** | Pure software device. No substances incorporated. |

### GSPR 13: Devices Incorporating Materials of Biological Origin

| Field | Value |
|-------|-------|
| **Applicable** | No |
| **Notes** | Pure software device. No biological materials. |

### GSPR 14: Devices Incorporating Software — Construction of Devices

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Requirement** | Software shall be developed and manufactured in accordance with the state of the art taking into account the principles of development lifecycle, risk management, verification, and validation. |
| **Standard Applied** | IEC 62304:2006+A1:2015 |
| **Evidence** | SDP-001, SRS-001, SAD-001, DD-001, VVP-001, CMP-001, TM-001 |
| **Compliance Status** | Compliant |
| **Notes** | Full IEC 62304 Class C lifecycle implemented. 14 lifecycle documents maintained. All Class C modules identified and subject to mandatory code review. |

### GSPR 14.1: Software Repeatability, Reliability, and Performance

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Evidence** | VVP-001 (test suite including endpoint tests), SDP-001 (coding standards, CI pipeline) |
| **Compliance Status** | Compliant |
| **Notes** | Deterministic algorithms for volumetry and lesion analysis. AI model outputs are reproducible for same inputs. 9-check endpoint test suite run per deployment. |

### GSPR 14.2: Software with Intended Measuring Function

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Evidence** | SRS-001 (accuracy requirements for volumetry), VVP-001 (measurement validation) |
| **Compliance Status** | Compliant |
| **Notes** | Brain volumetry provides quantitative measurements (mm3/mL) with normative percentile comparison. |

### GSPR 15: Devices with Energy Source

| Field | Value |
|-------|-------|
| **Applicable** | No |
| **Notes** | Pure software. No direct energy emission or control. |

### GSPR 16: Protection Against Mechanical and Thermal Risks

| Field | Value |
|-------|-------|
| **Applicable** | No |
| **Notes** | Pure software device. |

### GSPR 17: Electronic Programmable Systems — Devices Incorporating Electronic Programmable Systems

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Requirement** | Devices shall be designed to ensure repeatability, reliability, and performance. Cybersecurity risks shall be addressed. |
| **Standard Applied** | IEC 62304:2006+A1:2015, IEC 81001-5-1:2021 |
| **Evidence** | SDP-001, CYB-001 (Cybersecurity Assessment), SAD-001, VVP-001 |
| **Compliance Status** | Compliant |
| **Notes** | Cybersecurity assessment per IEC 81001-5-1 covers: authentication (Firebase JWT), transport encryption (TLS 1.2+), input validation, SOUP vulnerability monitoring, access control. Single-fault safety analysis in RMF-001. |

### GSPR 17.1: IT Security

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Evidence** | CYB-001, SAD-001 (security architecture), SOUP-001 (vulnerability tracking) |
| **Compliance Status** | Compliant |
| **Notes** | JWT authentication, HTTPS-only communication, CORS policies, rate limiting, input sanitization for DICOM/NIfTI uploads. SOUP vulnerability monitoring included in PMS-001. |

### GSPR 18: Protection Against Radiation Risks

| Field | Value |
|-------|-------|
| **Applicable** | No |
| **Notes** | MSTool-AI does not emit, control, or generate radiation. It processes existing MRI images. |

### GSPR 19: Active Implantable Devices

| Field | Value |
|-------|-------|
| **Applicable** | No |
| **Notes** | Not an implantable device. |

### GSPR 20: Protection Against Mechanical and Thermal Risks (Specific)

| Field | Value |
|-------|-------|
| **Applicable** | No |
| **Notes** | Pure software device. |

### GSPR 21: Protection Against Specific Environmental Risks

| Field | Value |
|-------|-------|
| **Applicable** | No |
| **Notes** | Cloud-hosted software. No specific environmental exposure risks. System requirements (browser, display) documented in IFU-001. |

### GSPR 22: Devices with Diagnostic or Measuring Function (Specific)

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Requirement** | Devices designed to measure shall provide sufficient accuracy and stability for their intended purpose. Measurement units shall be expressed in legal units of measurement. |
| **Standard Applied** | ISO 14971:2019, IEC 62304:2006+A1:2015 |
| **Evidence** | SRS-001 (volumetry accuracy requirements), VVP-001 (measurement validation), DD-001 (algorithm specifications) |
| **Compliance Status** | Compliant |
| **Notes** | Brain volumetry reports volumes in mL and mm3. MAGNIMS classification uses published distance thresholds (PV<=3mm, JC<=4mm, IT<=3mm) per McDonald 2024 criteria. Measurement uncertainty documented. |

### GSPR 23: Protection Against Risks Posed by the Device to the Patient and User

| Field | Value |
|-------|-------|
| **Applicable** | No |
| **Notes** | Pure software device. No direct physical risks to patient or user. Information risks addressed under GSPR 1-3 and GSPR 22. |

---

## Chapter III — Requirements Regarding Information Supplied with the Device

### GSPR 23: Information Supplied by the Manufacturer

| Field | Value |
|-------|-------|
| **Applicable** | Yes |
| **Requirement** | The manufacturer shall supply information together with the device, including intended purpose, user information, residual risks, and instructions for use. |
| **Standard Applied** | EN ISO 20417:2021 |
| **Evidence** | IFU-001 (Instructions for Use), in-app labels and disclaimers, TD-001 Section 2 |
| **Compliance Status** | Compliant |
| **Notes** | IFU-001 covers all required elements per MDR Annex I Chapter III and EN ISO 20417:2021, including: intended purpose, contraindications, warnings, system requirements, operating instructions, performance characteristics, manufacturer contact, UDI references. Multi-language support (EN/ES/DE). |

---

## Summary Compliance Matrix

| GSPR | Title | Applicable | Status |
|------|-------|:----------:|--------|
| 1 | Safety and Performance | Yes | Compliant |
| 2 | Risk Management | Yes | Compliant |
| 3 | Risk Control Measures | Yes | Compliant |
| 4 | Risk-Benefit Analysis | Yes | Compliant |
| 5 | Non-Expert Users | No | N/A |
| 6 | Usability | Yes | In Progress |
| 7 | Lifecycle Risk Management | Yes | Compliant |
| 8 | Interaction with Other Devices | Yes | Compliant |
| 9 | Diagnostic/Measuring (General) | Yes | Compliant |
| 10 | Chemical/Physical/Biological | No | N/A |
| 11 | Infection/Microbial | No | N/A |
| 12 | Substances | No | N/A |
| 13 | Biological Materials | No | N/A |
| 14 | Software (IEC 62304) | Yes | Compliant |
| 15 | Energy Source | No | N/A |
| 16 | Mechanical/Thermal | No | N/A |
| 17 | Electronic Programmable Systems | Yes | Compliant |
| 18 | Radiation | No | N/A |
| 19 | Active Implantable | No | N/A |
| 20 | Mechanical/Thermal (Specific) | No | N/A |
| 21 | Environmental | No | N/A |
| 22 | Diagnostic/Measuring (Specific) | Yes | Compliant |
| 23 | Information Supplied | Yes | Compliant |

---

## Referenced Documents

| ID | Title | Standard |
|----|-------|----------|
| RMF-001 | Risk Management File | ISO 14971:2019 |
| SDP-001 | Software Development Plan | IEC 62304:2006+A1:2015 |
| SRS-001 | Software Requirements Specification | IEC 62304:2006+A1:2015 |
| SAD-001 | Software Architecture Design | IEC 62304:2006+A1:2015 |
| DD-001 | Detailed Design Specification | IEC 62304:2006+A1:2015 |
| VVP-001 | Verification & Validation Plan | IEC 62304:2006+A1:2015 |
| CMP-001 | Configuration Management Plan | IEC 62304:2006+A1:2015 |
| TM-001 | Traceability Matrix | IEC 62304:2006+A1:2015 |
| SOUP-001 | SOUP Bill of Materials | IEC 62304:2006+A1:2015 |
| CYB-001 | Cybersecurity Assessment | IEC 81001-5-1:2021 |
| CER-001 | Clinical Evaluation Report | EU MDR 2017/745 |
| IFU-001 | Instructions for Use | EN ISO 20417:2021 |
| PMS-001 | Post-Market Surveillance Plan | EU MDR 2017/745 |
| QM-001 | Quality Management System | ISO 13485:2016 |

---

*End of Document*
