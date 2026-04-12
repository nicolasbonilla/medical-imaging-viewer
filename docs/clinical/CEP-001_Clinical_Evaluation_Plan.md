# MSTool-AI: Clinical Evaluation Plan

**Document ID**: CEP-001 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: EU MDR 2017/745 Article 61, MEDDEV 2.7/1 Rev 4

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Scope

This Clinical Evaluation Plan (CEP) defines the methodology for evaluating the clinical
safety and performance of MSTool-AI, a Software as a Medical Device (SaMD) intended
for AI-assisted analysis of brain MRI in patients with Multiple Sclerosis (MS).

This plan covers all clinical claims, the literature search strategy, equivalence
assessment, and acceptance criteria required under EU MDR Article 61 and MEDDEV 2.7/1
Revision 4.

## 2. Device Description

### 2.1 Device Identification

- **Device Name**: MSTool-AI
- **Classification**: Class IIa (EU MDR Rule 11 — software intended to provide information used for diagnostic purposes)
- **Software Safety Class**: IEC 62304 Class C
- **UDI-DI**: To be assigned upon notified body submission
- **GMDN Code**: 64463 — Software, medical image analysis

### 2.2 Device Overview

MSTool-AI is a cloud-deployed SaMD platform for quantitative analysis of brain MRI
studies. The system processes NIfTI and DICOM brain MRI volumes (primarily FLAIR, T1w,
T2w sequences) and provides:

1. **AI-assisted MS lesion segmentation** — automated detection and delineation of white matter lesions
2. **Brain volumetry with normative comparison** — quantitative volume measurement of 33 FreeSurfer-derived brain structures with percentile ranking against normative data
3. **MAGNIMS region classification** — automated classification of lesions into periventricular (PV), juxtacortical (JC), infratentorial (IT), and deep white matter (DWM) regions per MAGNIMS-CMSC-NAIMS 2024 consensus criteria
4. **Dissemination in Space (DIS) assessment** — automated evaluation of McDonald 2024 DIS criteria
5. **Clinical report generation** — AI-generated structured reports integrating volumetric and lesion data
6. **Longitudinal tracking** — lesion-level change detection across timepoints

### 2.3 Intended Purpose

MSTool-AI is intended to assist neuroradiologists and neurologists in the quantitative
analysis of brain MRI studies for patients with known or suspected Multiple Sclerosis.
The device provides automated lesion segmentation, brain volumetry, and MAGNIMS region
classification to support clinical decision-making.

**MSTool-AI is a clinical decision support tool. It does not provide autonomous diagnosis
and all outputs require validation by a qualified medical professional.**

### 2.4 Intended Users

| User Profile | Qualification | Role |
|---|---|---|
| Neuroradiologist | Board-certified, 5+ years MRI experience | Primary: reviews segmentation, validates volumetry |
| Neurologist | Board-certified, MS specialist | Reviews reports, longitudinal comparison |
| Radiology resident / research fellow | In training, supervised | Assisted reading under supervision |

### 2.5 Target Patient Population

- Adults (age 18+) with known or suspected Multiple Sclerosis
- Brain MRI studies acquired per standard MS protocols (MAGNIMS-CMSC-NAIMS 2024 recommendations)
- Sequences: FLAIR (primary), T1w, T2w, PD

### 2.6 Indications and Contraindications

**Indications**: Quantitative analysis of brain MRI in MS clinical workflow.

**Contraindications**:
- Pediatric populations (under 18 years)
- Non-brain MRI studies
- Studies with severe motion artifacts or incomplete acquisitions
- Emergency/acute stroke triage (device not validated for this use)

## 3. Clinical Claims

The following clinical claims shall be evaluated:

### Claim 1: Lesion Detection Accuracy

MSTool-AI achieves a Dice similarity coefficient of 0.70 or greater when compared
against expert manual segmentation for MS white matter lesion delineation on FLAIR MRI.

- **Metric**: Dice similarity coefficient (DSC)
- **Acceptance threshold**: DSC >= 0.70 (mean across test dataset)
- **Comparator**: Manual segmentation by two independent neuroradiologists (consensus)
- **Justification**: DSC >= 0.70 is the accepted threshold in MS lesion segmentation literature (Carass et al., NeuroImage 2017) and aligns with inter-rater variability.

### Claim 2: Volumetry Accuracy

MSTool-AI brain structure volumetry measurements are within 5% of FreeSurfer 7.x
reference measurements.

- **Metric**: Mean absolute percentage error (MAPE)
- **Acceptance threshold**: MAPE <= 5% for each of the 33 measured structures
- **Comparator**: FreeSurfer 7.4.1 cross-sectional pipeline
- **Justification**: 5% tolerance accounts for known inter-method variability while ensuring clinical relevance for atrophy monitoring.

### Claim 3: MAGNIMS Region Classification Agreement

MSTool-AI automated MAGNIMS region classification achieves substantial agreement
with expert neuroradiologist classification.

- **Metric**: Cohen's kappa coefficient
- **Acceptance threshold**: kappa >= 0.80 (almost perfect agreement)
- **Comparator**: Consensus classification by two MS-specialist neuroradiologists
- **Justification**: kappa >= 0.80 represents almost perfect agreement (Landis & Koch 1977), required given the clinical significance of DIS assessment.

### Claim 4: Report Quality

AI-generated clinical reports meet clinician expectations for completeness, accuracy,
and clinical utility.

- **Metric**: Clinician satisfaction on validated Likert scale questionnaire
- **Acceptance threshold**: >= 80% of evaluators rate reports as "satisfactory" or above
- **Comparator**: Blinded comparison with standard dictated reports
- **Justification**: User acceptance is critical for adoption; 80% threshold reflects meaningful clinical utility.

## 4. Equivalence Analysis

### 4.1 Predicate Device

**icobrain ms** (icometrix NV, Leuven, Belgium) is identified as the primary equivalent
device for comparison.

- CE-marked Class IIa SaMD
- FDA 510(k) cleared (K193351)
- Intended for MS lesion and brain volumetry analysis
- Established clinical evidence base

### 4.2 Equivalence Assessment

| Characteristic | MSTool-AI | icobrain ms | Equivalent? |
|---|---|---|---|
| Intended purpose | MS lesion + volumetry + reports | MS lesion + volumetry + reports | Yes |
| Target population | Adults with MS | Adults with MS | Yes |
| Anatomical site | Brain | Brain | Yes |
| Input modality | Brain MRI (FLAIR, T1w) | Brain MRI (FLAIR, T1w, T2w) | Similar |
| AI architecture | Deep learning (SynthSeg-based) | Proprietary deep learning | **Difference noted** |
| Training data | Open datasets + proprietary | Proprietary clinical datasets | **Difference noted** |
| Deployment | Cloud (GCP Cloud Run) | Cloud (icometrix platform) | Similar |
| Region classification | MAGNIMS 2024 criteria | MAGNIMS criteria | Yes |
| Regulatory status | Pending | CE marked, FDA cleared | N/A |

### 4.3 Equivalence Conclusion

Full equivalence cannot be claimed due to differences in AI architecture and training
data. MSTool-AI uses a SynthSeg-based parcellation approach while icobrain ms uses a
proprietary architecture. Therefore, clinical data from icobrain ms can support the
state of the art analysis but **cannot substitute for device-specific clinical evidence**.

Own clinical data collection is required (see Section 7).

## 5. Literature Search Strategy

### 5.1 Databases

- PubMed / MEDLINE
- Cochrane Library
- Embase
- IEEE Xplore (for technical validation studies)
- MAGNIMS consortium publications

### 5.2 Search Terms

Primary: `("multiple sclerosis" OR "MS") AND ("MRI" OR "magnetic resonance") AND ("lesion segmentation" OR "volumetry" OR "brain atrophy")`

Secondary: `("AI" OR "deep learning" OR "machine learning") AND ("white matter lesion") AND ("FLAIR")`

Tertiary: `("MAGNIMS" OR "McDonald criteria" OR "dissemination in space") AND ("automated" OR "software")`

### 5.3 Inclusion Criteria

- Published 2019-2026 (last 7 years)
- English language
- Peer-reviewed journals or major conference proceedings
- Studies involving adult MS patients
- Studies evaluating automated or semi-automated lesion segmentation, volumetry, or region classification

### 5.4 Exclusion Criteria

- Pediatric populations
- Non-brain MRI studies
- Case reports with fewer than 10 subjects
- Studies without quantitative performance metrics
- Non-peer-reviewed preprints (unless from established consortia)

### 5.5 Data Extraction

For each included study, the following data shall be extracted: study design, sample
size, MRI protocol, AI method, performance metrics (Dice, sensitivity, specificity,
kappa), comparator method, and reported limitations.

## 6. State of the Art

### 6.1 MS Diagnosis

MS diagnosis follows the McDonald 2024 criteria (Montalban et al., Lancet Neurology
2025), which revised the 2017 criteria with updated MRI requirements for dissemination
in space (DIS) and dissemination in time (DIT). Key changes include recognition of
the central vein sign and paramagnetic rim lesions as supportive criteria.

### 6.2 MRI in MS — MAGNIMS-CMSC-NAIMS 2024 Consensus

The MAGNIMS-CMSC-NAIMS 2024 consensus guidelines (Barkhof et al.) standardize MRI
acquisition and reporting for MS. Key recommendations include:

- Standardized FLAIR and T1w acquisition protocols
- Region-based lesion classification: periventricular, juxtacortical/cortical, infratentorial, deep white matter
- Quantitative volumetry for atrophy monitoring
- Structured reporting with lesion counts per region

### 6.3 AI in MS Lesion Segmentation

Current state of the art for automated MS lesion segmentation:

- **LST-AI** (Wiltgen et al., NeuroImage Clinical 2024): ensemble deep learning, DSC 0.62-0.76 on multi-center data
- **icobrain ms**: commercial, DSC ~0.63-0.72 (reported in validation studies)
- **SAMSEG** (FreeSurfer): Bayesian segmentation, DSC ~0.55-0.65
- **Inter-rater variability**: DSC 0.55-0.75 between expert raters (Defined as benchmark)

### 6.4 Brain Volumetry

FreeSurfer remains the de facto reference standard for brain volumetry. SynthSeg
(Billot et al., 2023) provides contrast-agnostic parcellation suitable for clinical
deployment.

## 7. Clinical Investigation Needs Assessment

Given the inability to claim full equivalence with icobrain ms (Section 4.3), the
following clinical data is required:

### 7.1 Required Clinical Evidence

1. **Retrospective validation study**: Lesion segmentation and volumetry accuracy on a multi-center dataset (minimum N=100 MS patients)
2. **Region classification validation**: MAGNIMS classification accuracy on an annotated dataset (minimum N=200 lesions from 50 patients)
3. **Usability study**: Summative usability evaluation with 15 representative users (see UEF-001)
4. **Clinical utility study**: Impact on reading time and diagnostic confidence (prospective, N=30 cases)

### 7.2 Clinical Investigation Decision

A formal clinical investigation under MDR Article 62 is **not required** at this time,
provided that:
- Sufficient retrospective clinical data can be collected from existing annotated datasets
- The device is positioned as a clinical decision support tool (not autonomous)
- Post-market clinical follow-up (PMCF-001) will collect prospective real-world data

## 8. Data Analysis Plan

### 8.1 Statistical Methods

| Claim | Primary Metric | Statistical Test | Sample Size Justification |
|---|---|---|---|
| Lesion detection | Dice coefficient | One-sample t-test (H0: DSC < 0.70) | N=100 (power 0.90, alpha 0.05) |
| Volumetry | MAPE | Paired t-test vs FreeSurfer | N=100 (power 0.90, alpha 0.05) |
| Region classification | Cohen's kappa | Bootstrap 95% CI | N=200 lesions (50 patients) |
| Report quality | Satisfaction rate | Exact binomial test (H0: rate < 0.80) | N=15 evaluators |

### 8.2 Additional Metrics

- **Sensitivity** (lesion-level): proportion of expert-identified lesions detected
- **Specificity**: proportion of non-lesion regions correctly identified
- **Positive Predictive Value (PPV)**: proportion of detected lesions that are true lesions
- **Negative Predictive Value (NPV)**: proportion of undetected regions that are truly lesion-free
- **Hausdorff Distance (HD95)**: 95th percentile boundary distance for segmentation accuracy

### 8.3 Acceptance Criteria Summary

| Claim | Metric | Threshold | Status |
|---|---|---|---|
| Lesion detection | Dice coefficient | >= 0.70 | Pending validation |
| Volumetry accuracy | MAPE | <= 5% | Pending validation |
| MAGNIMS classification | Cohen's kappa | >= 0.80 | Pending validation |
| Report quality | Clinician satisfaction | >= 80% | Pending validation |

## 9. Evaluation Timeline

| Phase | Activity | Timeline |
|---|---|---|
| Phase 1 | Literature search and state of the art review | Q2 2026 |
| Phase 2 | Retrospective validation dataset collection | Q3 2026 |
| Phase 3 | Segmentation and volumetry validation | Q3-Q4 2026 |
| Phase 4 | MAGNIMS classification validation | Q4 2026 |
| Phase 5 | Usability study (UEF-001) | Q4 2026 |
| Phase 6 | Clinical Evaluation Report (CER-001) | Q1 2027 |

## 10. References

1. Montalban X, et al. McDonald criteria revision 2024. *Lancet Neurology*. 2025.
2. Barkhof F, et al. MAGNIMS-CMSC-NAIMS 2024 consensus guidelines for MRI in MS. 2024.
3. Wiltgen T, et al. LST-AI: A deep learning ensemble for MS lesion segmentation. *NeuroImage: Clinical*. 2024;41:103565.
4. Filippi M, et al. MRI criteria for the diagnosis of multiple sclerosis: MAGNIMS consensus guidelines. *Lancet Neurology*. 2016;15(3):292-303.
5. Billot B, et al. SynthSeg: Segmentation of brain MRI scans of any contrast and resolution without retraining. *Medical Image Analysis*. 2023;86:102789.
6. Carass A, et al. Longitudinal multiple sclerosis lesion segmentation: Resource and challenge. *NeuroImage*. 2017;148:77-102.
7. Landis JR, Koch GG. The measurement of observer agreement for categorical data. *Biometrics*. 1977;33(1):159-174.
8. MEDDEV 2.7/1 Rev 4. Clinical Evaluation: A Guide for Manufacturers and Notified Bodies. European Commission. 2016.
9. EU MDR 2017/745, Article 61 — Clinical Evaluation.
