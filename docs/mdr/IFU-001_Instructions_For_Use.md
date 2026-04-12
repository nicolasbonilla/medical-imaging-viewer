# MSTool-AI: Instructions for Use

**Document ID**: IFU-001 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: EU MDR 2017/745 Annex I Chapter III, EN ISO 20417:2021

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Intended Purpose

MSTool-AI is a cloud-native Software as a Medical Device (SaMD) intended to assist qualified healthcare professionals in the analysis and interpretation of brain MRI images. The software provides AI-assisted segmentation, quantitative brain volumetry, MAGNIMS lesion region classification per McDonald 2024 criteria, longitudinal lesion tracking, and AI-generated structured clinical reports.

MSTool-AI is an **assistive tool only**. It does not provide standalone diagnoses. All AI-generated results, measurements, classifications, and reports require review and verification by a qualified clinician before any clinical decision is made.

---

## 2. Intended Users

MSTool-AI is intended for use by the following qualified healthcare professionals:

- **Radiologists and neuroradiologists** — for image analysis and report generation
- **Neurologists** — for MS lesion monitoring and longitudinal assessment
- **Clinical researchers** — for quantitative neuroimaging analysis

Users must be trained in brain MRI interpretation and familiar with MAGNIMS guidelines and McDonald diagnostic criteria. MSTool-AI is not intended for use by patients or non-clinical personnel.

---

## 3. Patient Population

- Adult patients (18 years and older)
- Patients undergoing brain MRI for suspected or confirmed neurological conditions
- Primary application: Multiple Sclerosis patients requiring longitudinal monitoring

---

## 4. Indications for Use

MSTool-AI is indicated for the following clinical applications:

1. Assisted identification and segmentation of brain structures in T1-weighted, FLAIR, T2-weighted, and PD-weighted brain MRI sequences
2. Quantitative brain volumetry with normative comparison (age- and sex-adjusted percentiles)
3. MS lesion detection, counting, and volume measurement
4. MAGNIMS region classification of white matter lesions (periventricular, juxtacortical, infratentorial, deep white matter) per McDonald 2024 criteria
5. Assessment of Dissemination in Space (DIS) criteria
6. Longitudinal comparison of lesion burden across serial MRI examinations
7. Generation of AI-assisted structured clinical reports

---

## 5. Contraindications

MSTool-AI is **NOT** indicated for use in the following scenarios:

- **Acute stroke triage** — The software is not validated for time-critical stroke assessment. Do not use for acute stroke decision-making.
- **Pediatric patients** — The software and its normative volumetric databases are validated for adult patients (18+) only. Brain volumetry percentiles are not applicable to pediatric populations.
- **Non-brain MRI** — The software is designed and validated exclusively for brain MRI. Do not use with spinal cord, cardiac, abdominal, or other body region MRI data.
- **Standalone diagnostic use** — The software must not be used as the sole basis for clinical diagnosis or treatment decisions.
- **Emergency or life-threatening conditions** — The software is not designed for use in emergency settings where immediate clinical action is required.

---

## 6. Warnings and Precautions

### 6.1 Warnings

- **AI-generated results require clinical verification.** All segmentation masks, volumetric measurements, lesion classifications, and generated reports are AI-assisted outputs and may contain errors. A qualified clinician must verify all results before clinical use.
- **Not for standalone diagnosis.** MSTool-AI is a clinical decision-support tool. It does not replace professional medical judgment.
- **Edge AI screening is assistive only.** The browser-based normal/abnormal triage classification is a rapid screening aid. It is not a diagnostic test and must not be used as the sole basis for clinical decisions.
- **Report generation uses AI language models.** Generated reports may contain inaccuracies, hallucinations, or inappropriate conclusions. All generated reports must be reviewed and edited by a qualified radiologist before clinical use.
- **MAGNIMS classification accuracy depends on segmentation quality.** Region classification results are directly dependent on the accuracy of the underlying brain parcellation and lesion segmentation.

### 6.2 Precautions

- Ensure uploaded DICOM/NIfTI files are from the correct patient before analysis.
- Verify image orientation and slice ordering before interpreting segmentation results.
- Volumetric measurements assume correct voxel dimension metadata in the image files. Incorrect DICOM/NIfTI headers will produce inaccurate measurements.
- Longitudinal comparisons require consistent MRI acquisition protocols across timepoints.
- The software requires a stable internet connection for cloud-based AI features (segmentation, volumetry, report generation). Edge AI screening functions offline after initial model download.

---

## 7. System Requirements

### 7.1 Client (Browser)

| Component | Minimum Requirement |
|-----------|-------------------|
| Browser | Chrome 100+, Firefox 100+, Edge 100+, Safari 16+ |
| Display Resolution | 1920 x 1080 (Full HD) minimum; 2560 x 1440 recommended |
| Memory (RAM) | 8 GB minimum; 16 GB recommended for large datasets |
| Network | Broadband internet connection (10 Mbps+ recommended) |
| WebGPU | Recommended for Edge AI features (automatic WASM fallback available) |

### 7.2 Server

MSTool-AI backend is deployed as a managed cloud service on Google Cloud Run. No server installation is required by the user.

### 7.3 Supported Image Formats

| Format | Extensions | Notes |
|--------|-----------|-------|
| DICOM | `.dcm`, `.dicom` | Single files or multi-frame series |
| NIfTI | `.nii`, `.nii.gz` | 3D volumetric data |

---

## 8. Installation and Configuration

### 8.1 Access

MSTool-AI is accessed via web browser at the designated URL. No local software installation is required.

### 8.2 Authentication

Users must authenticate with valid credentials (email/password or institutional SSO) via Firebase Authentication. Access is restricted to authorized healthcare professionals.

### 8.3 Initial Configuration

1. Navigate to the MSTool-AI URL in a supported browser
2. Log in with authorized credentials
3. Verify display calibration per institutional standards
4. Create or select a study/patient record

---

## 9. Operating Instructions

### 9.1 Clinical Workflow Overview

The standard clinical workflow follows these steps:

**Upload** --> **Segment** --> **Classify** --> **Report**

### 9.2 Step 1: Upload Images

1. Select "New Study" or open an existing study
2. Upload DICOM or NIfTI brain MRI files
3. Verify image metadata (patient, sequence type, orientation)
4. The system automatically detects sequence type (FLAIR, T1, T2, PD) from BIDS filenames

### 9.3 Step 2: AI Segmentation

1. Open the Segmentation Panel (sidebar)
2. Select segmentation mode:
   - **Auto mode**: Automated brain parcellation using SynthSeg model
   - **Interactive mode**: Click-based segmentation with positive/negative points
   - **Manual mode**: Brush/eraser painting tools with label presets
3. Review and refine the segmentation mask
4. Save the segmentation when satisfied

### 9.4 Step 3: Lesion Analysis and Classification

1. Open the Lesion Dashboard
2. Click "Analyze Lesions" to run connected-component analysis
3. Click "Auto-Classify Regions" to apply MAGNIMS region classification
4. Review DIS (Dissemination in Space) assessment
5. For longitudinal studies: select baseline and follow-up segmentations for comparison

### 9.5 Step 4: Brain Volumetry

1. Open the Brain Volumetry Panel
2. Click "Compute Volumetry" to calculate structure volumes
3. Review bar chart, sort by volume/name/percentile
4. Note abnormality badges for structures outside normative range

### 9.6 Step 5: Report Generation

1. Open the AI Report Panel
2. Select report template (general, stroke, tumor, dementia, MS longitudinal)
3. Enter clinical context and relevant history
4. Click "Generate Report"
5. **Review and edit the generated report before clinical use**
6. Copy or export the final report

### 9.7 Keyboard Shortcuts

Press `?` to display the keyboard shortcuts modal. Key shortcuts include:

| Shortcut | Action |
|----------|--------|
| `?` | Toggle shortcuts modal |
| `B` | Select brush tool |
| `E` | Select eraser tool |
| `S` | Toggle segmentation overlay |
| `+` / `-` | Increase/decrease brush size |
| `1`-`9` | Select label |
| `Ctrl+Z` | Undo last paint stroke |

---

## 10. Performance Characteristics

### 10.1 AI Segmentation

- Brain parcellation: 33 FreeSurfer structures (SynthSeg-based)
- Segmentation model hosted on Google Vertex AI

### 10.2 Brain Volumetry

- Voxel-counting method with known voxel dimensions
- Normative comparison against age- and sex-adjusted reference data
- Volume reported in mL and mm3

### 10.3 MAGNIMS Region Classification

Classification thresholds per McDonald 2024 criteria:

| Region | Abbreviation | Distance Threshold |
|--------|-------------|-------------------|
| Periventricular | PV | <= 3 mm from ventricle |
| Juxtacortical | JC | <= 4 mm from cortex |
| Infratentorial | IT | <= 3 mm from infratentorial structures |
| Deep White Matter | DWM | Default (none of the above) |

Two-tier classification: Tier 2 (SynthSeg parcellation + EDT distance transform) with Tier 1 (geometric heuristic) fallback. Priority cascade: IT > PV > JC > DWM.

### 10.4 Edge AI Screening

- Model: ONNX Runtime Web, binary classification (normal/abnormal)
- Input: 224x224 bilinear-interpolated grayscale slice
- Output: Classification with confidence percentage
- Execution: WebGPU preferred, automatic WASM fallback

---

## 11. Symbols and Abbreviations

| Abbreviation | Meaning |
|-------------|---------|
| DIS | Dissemination in Space (McDonald criteria) |
| DIT | Dissemination in Time (McDonald criteria) |
| DWM | Deep White Matter |
| EDT | Euclidean Distance Transform |
| FLAIR | Fluid-Attenuated Inversion Recovery |
| IT | Infratentorial |
| JC | Juxtacortical |
| MAGNIMS | Magnetic Resonance Imaging in MS |
| MRI | Magnetic Resonance Imaging |
| MS | Multiple Sclerosis |
| NIfTI | Neuroimaging Informatics Technology Initiative |
| ONNX | Open Neural Network Exchange |
| PV | Periventricular |
| SaMD | Software as a Medical Device |
| SynthSeg | Synthetic Segmentation (FreeSurfer) |

---

## 12. Maintenance and Updates

Software updates are deployed automatically via the cloud infrastructure. Users are notified of significant version changes. Update release notes are maintained in the version history.

SOUP components are monitored for security vulnerabilities as described in PMS-001.

---

## 13. Manufacturer Information

| Field | Value |
|-------|-------|
| **Manufacturer** | [Manufacturer Legal Name] |
| **Address** | [Registered Address] |
| **Contact Email** | [regulatory@manufacturer.com] |
| **Contact Phone** | [+XX XXX XXX XXXX] |
| **Website** | [https://www.manufacturer.com] |
| **EU Authorized Representative** | [If applicable — name and address] |

---

## 14. Regulatory Identification

| Field | Value |
|-------|-------|
| **UDI-DI** | To be assigned |
| **Basic UDI-DI** | To be assigned |
| **SRN** | To be assigned upon EU registration |
| **Device Classification** | Class IIa (EU MDR Rule 11) |
| **Notified Body** | To be designated |

---

## 15. Reporting Incidents

If you experience or become aware of any serious incident related to MSTool-AI, please report it immediately to the manufacturer at the contact information above and to the competent authority of the Member State in which you are established.

A serious incident is any incident that directly or indirectly led, might have led, or might lead to the death of a patient, user, or other person, or to a temporary or permanent serious deterioration of health.

---

*End of Document*
