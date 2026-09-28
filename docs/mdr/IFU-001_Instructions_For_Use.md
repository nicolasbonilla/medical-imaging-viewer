# MSTool-AI: Instructions for Use

**Document ID**: IFU-001 | **Version**: 1.3 | **Date**: September 28, 2026
**Standard**: EU MDR 2017/745 Annex I Chapter III, EN ISO 20417:2021

---

| Version | Date | Author | Approved By | Change |
|---------|------|--------|-------------|--------|
| 1.0 | 2026-04-12 | Development Team | — | Initial release |
| 1.1 | 2026-09-28 | Development Team | — | MAGNIMS region classification: no per-lesion confidence is reported; region evidence and the "No WM zone — DWM by default" warning described (HAZ-005, REQ-SAFE-010 amended, RC-010 (amended)) |
| 1.2 | 2026-09-28 | Development Team | — | CAPA-006, HAZ-005: Section 10.3 method description corrected. Versions 1.0–1.1 stated distance thresholds of 3 mm (PV), 4 mm (JC) and 3 mm (IT) and a two-tier cascade (parcellation, geometric fallback). ~~These described an earlier software version (commit cf780f4, February 2026); the software has since used 1.5 mm (direct contact) and added the MSMask atlas path, but this document was not updated.~~ *Correction (review 2026-09-28)*: that explanation was inaccurate. The code applied 3.0/4.0/3.0 mm only in commit cf780f4 (2026-02-22, with a Harvard-Oxford zone map); commit 67fa336 (2026-02-28) changed it to 1.5 mm and added the MSMask atlas, and the four-path order dates from commit a637cdf (2026-03-14). Version 1.0 of this document was issued on 2026-04-12 (commit 9ac536d) already stating 3/4/3 mm, six weeks after the code had moved to 1.5 mm and on the day the DDS was issued stating 1.5 mm: the labelling was wrong when issued and had not been reviewed against the code or the DDS. The 3/4/3 mm values were never published MAGNIMS thresholds and are withdrawn. Section 10.3 now gives the MAGNIMS contact criterion, the four classification paths in the order used, and the requirement that atlas-based regions are applied only to MNI-space images. MNI and LST-AI added to Section 11 |
| 1.3 | 2026-09-28 | Development Team | — | CAPA-006 review, HAZ-005: Section 10.3 path table and MNI paragraph rewritten to the code: LST-AI path copies LST-AI's zones voxel by voxel with no contact rule and no priority; exact FreeSurfer-parcellation test and the limits of the 1.5 mm rule stated; the five MNI grid conditions stated, and the atlas path described as used only for images already registered to MNI152 ("This is the usual path" withdrawn: native clinical scans normally fail the check and are classified by path 4); geometric path preconditions and refusal stated, replacing the v1.2 "Known limitation … Correction pending (CA-6.6)"; priority stated per path; refusal when no path applies stated. Misalignment figures corrected to the product-rule run (27.5 % / 43.0 % / 55.2 %; v1.2 quoted the superseded run: 28 % / 62 %). Spinal cord and optic nerve: "not evaluated from the images". Section 6.1: replaced v1.2 sentence marked; MNI bullet aligned. Sections 9.3 and 10.1: "disabled by default (not enabled by the deployment pipeline)"; "Segmentation model hosted on Google Vertex AI" withdrawn. Version 1.2 row corrected (history) |

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
- **MAGNIMS classification accuracy depends on segmentation quality.** ~~Region classification results are directly dependent on the accuracy of the underlying brain parcellation and lesion segmentation.~~ *(Replaced v1.2, CAPA-006: a parcellation is only one of the anatomical references used.)* Region classification results are directly dependent on the accuracy of the lesion segmentation and of the anatomical reference used (LST-AI zones, parcellation, MNI atlas or geometric heuristics — see §10.3).
- **Atlas-based regions require an MNI-registered image.** The MSMask atlas is in MNI152 space and MSTool-AI performs no registration. It is used only for images already registered to MNI152 whose grid passes the MNI grid check (§10.3); native clinical scans normally fail the check. Otherwise the atlas is refused and, in automatic mode, the least accurate geometric heuristics are used (if their own preconditions hold) with an amber warning on screen; if they cannot be applied either, no regions are assigned. The grid check cannot prove that an image is truly normalized (§10.3).
- **No per-lesion confidence for region classification.** Lesion regions are assigned by a deterministic MAGNIMS rule; MSTool-AI does not report a per-lesion confidence or probability for the assigned region. The accuracy of region assignment has not yet been measured against expert region labels (HAZ-005, residual risk undetermined). Verify the location of every lesion that contributes to Dissemination in Space (DIS) before using the DIS assessment.

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
   - **Auto mode**: Automated brain parcellation using SynthSeg model — *available only when the SynthSeg integration is enabled; it is disabled by default (not enabled by the deployment pipeline) (CAPA-006)*
   - **Interactive mode**: Click-based segmentation with positive/negative points
   - **Manual mode**: Brush/eraser painting tools with label presets
3. Review and refine the segmentation mask
4. Save the segmentation when satisfied

### 9.4 Step 3: Lesion Analysis and Classification

1. Open the Lesion Dashboard
2. Click "Analyze Lesions" to run connected-component analysis
3. Click "Auto-Classify Regions" to apply MAGNIMS region classification
4. Review the region assigned to each lesion and its evidence (see Section 10.3). Any lesion marked **"No WM zone — DWM by default"** must have its location verified on the images.
5. Review DIS (Dissemination in Space) assessment only after the lesion locations it depends on have been verified
6. For longitudinal studies: select baseline and follow-up segmentations for comparison

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

- Brain parcellation: 33 FreeSurfer structures (SynthSeg-based) — *available only when the SynthSeg integration is enabled; it is disabled by default (not enabled by the deployment pipeline). When enabled, SynthSeg runs as a separate service at a configured endpoint (CAPA-006)*
- ~~Segmentation model hosted on Google Vertex AI~~ *(Withdrawn v1.3, CAPA-006: no segmentation model is hosted on Google Vertex AI; the Vertex AI endpoints were never deployed and SynthSeg, when enabled, does not run on Vertex AI.)*

### 10.2 Brain Volumetry

- Voxel-counting method with known voxel dimensions
- Normative comparison against age- and sex-adjusted reference data
- Volume reported in mL and mm3

### 10.3 MAGNIMS Region Classification

**Criterion** (MAGNIMS consensus, Filippi et al. 2019; McDonald 2024 criteria):

| Region | Abbreviation | A lesion is assigned to this region when it |
|--------|-------------|---------------------------------------------|
| Infratentorial | IT | lies in or touches the brainstem or cerebellum |
| Periventricular | PV | abuts (is in contact with) the lateral ventricles |
| Juxtacortical | JC | abuts the cortex |
| Deep White Matter | DWM | meets none of the above |

On the parcellation, MSMask and geometric paths the priority is IT > PV > JC > DWM; the LST-AI path copies LST-AI's zones voxel by voxel (see the table below). Only PV, JC and IT count towards Dissemination in Space (DIS) in the brain. MSTool-AI does not evaluate the spinal cord or the optic nerve from the images; evidence for these regions entered by the clinician is accepted by the DIS assessment.

**Classification paths**: in automatic mode ("Auto"), MSTool-AI tries the paths in the order below and uses the first one that applies. The result states which path was used. **If no path can be applied validly, the request is refused and the reasons are shown; no regions are assigned.**

| Order | Path | Used when | How "abutting" is implemented |
|-------|------|-----------|-------------------------------|
| 1 | LST-AI zones | Another segmentation of the same image was produced by LST-AI (its validation source contains "lst-ai"). The LST-AI integration is disabled by default (not enabled by the deployment pipeline). | Voxel by voxel: each lesion voxel takes the zone that LST-AI assigned at that voxel. No contact rule and no priority are applied, so one lesion can receive more than one region. Lesion voxels outside LST-AI's zones become DWM without a warning |
| 2 | Parcellation + Euclidean distance transform | A parcellation is given explicitly, or another segmentation of the same image looks like a FreeSurfer parcellation: at least 3 of the labels {2, 3, 4, 7, 8, 10, 16, 41, 42, 43} and at least one of {16, 41, 42, 43}, and it is not a MAGNIMS zone map. An explicitly given parcellation that fails this test is refused (HTTP 422). The SynthSeg integration is disabled by default (not enabled by the deployment pipeline). | Minimum distance between the lesion voxel centres and the lateral-ventricle (4, 43), cortex (3, 42) or brainstem/cerebellum (7, 8, 16, 46, 47) labels of 1.5 mm or less (direct contact). Limits: with slices thicker than 1.5 mm, contact through the slice direction is not detected; at 1 mm voxels, diagonal (corner) neighbours at 1.73 mm are missed |
| 3 | MSMask atlas (LST-AI MSMask, Wiltgen et al. 2024; used here in an adapted form that has not been validated) | Used only for images already registered to MNI152: MSTool-AI performs no registration, and the image must pass all five grid conditions below. ~~This is the usual path.~~ *(Withdrawn v1.3, CAPA-006: native clinical scans normally fail the grid check and are classified by path 4, or refused if path 4 cannot be applied.)* | The zone map is generated fresh for every classification; a stored zone map is never reused. Zones: the atlas ventricle, cortex and infratentorial structures dilated by one voxel (3 x 3 x 3 cube on the 1 mm atlas, adapted from LST-AI) and intersected with atlas white matter, plus the infratentorial structures themselves; zone precedence IT > PV > JC; the remaining atlas white matter is the DWM zone. A lesion is assigned the highest-priority zone that any of its voxels lies in (IT > PV > JC > DWM). A lesion with no voxel in any zone is DWM by default and flagged "No WM zone — DWM by default" |
| 4 | Geometric heuristics (least accurate; coordinate rules, not anatomical landmarks) | None of the paths above applies, and all of these hold: the source image can be read; its orientation can be determined; its slice axis runs from inferior to superior (axial acquisition); it is 3-D; it is on the same grid as the lesion mask; it is not blank. Otherwise this path is refused: sagittal or coronal acquisitions, or slices ordered from superior to inferior, are not classified by it. | Brain outline = Otsu threshold (x 0.3) of the image intensities, holes filled (this is the head outline if the image is not skull-stripped). IT = lesion centroid in the lowest 25 % of the outline's extent along the slice axis; PV = mean distance of the lesion's voxels from the brain centre (midpoint of the outline's slice extent and the in-plane array centre) below 35 % of the largest such distance in the image array; JC = lesion within min(8 mm, 15 % of the maximum depth of the outline) of the outline surface; otherwise DWM. Priority IT > PV > JC > DWM. Whenever regions come from this path, an amber warning is shown: "Geometric heuristics: the least accurate method (coordinate rules, not anatomical landmarks). Verify every region before using it for DIS." (or the atlas warning below, when the atlas was refused). *CAPA-006 CA-6.6 (v1.3)*: version 1.2 of this row stated a known limitation — the IT rule read the slice axis without the image orientation, so IT assignments on sagittal, coronal or superior-to-inferior acquisitions could not be relied on. This is corrected: such images are now refused by this path |

**Atlas-based regions require an MNI-registered image.** The MSMask atlas is in MNI152 space, and MSTool-AI does **not** register your image to it. The atlas path is therefore used only for images already registered to MNI152, and only when the image grid meets all of these conditions:

1. isotropic voxels (largest / smallest voxel spacing at most 1.05);
2. axes aligned with, and not permuted relative to, the world axes (within about 2.5°);
3. field of view within 25 % of 181 x 217 x 181 mm on each axis;
4. grid centre within 10 mm of the MNI template centre (0, -18, 18) mm;
5. a spatial transform in the image header (sform or qform code not 0).

Native clinical scans normally fail these conditions; they are then classified by path 4, if its preconditions hold. For any image that fails, the atlas is not used:

- If the MSMask method was requested explicitly, the request is refused (HTTP 422) and no regions are assigned.
- In automatic mode, the geometric heuristics (path 4) are used and an amber warning is shown: "Atlas regions not used: this image is not in MNI space, so the least accurate geometric fallback was applied. Verify every region before using it for DIS." If path 4 is refused as well, the request is refused with both reasons and no regions are assigned.

This check looks only at the image grid. It cannot confirm that an image which passes it has actually been normalized to MNI152: an image resampled onto an MNI grid without being registered to it, or an imperfectly normalized one, passes. Use atlas-based regions only on images you know were registered to MNI152. Small misalignments matter: in a controlled experiment on 30 MNI-registered scans with expert-annotated lesions (MSLesSeg), moving the anatomy inside the MNI grid by up to 3°, 3 % and 5 mm changed the region of 216 of 786 lesions (27.5 %); by up to 8°, 7 % and 10 mm, 338 of 786 (43.0 %); by up to 15°, 10 % and 20 mm, 433 of 785 (55.2 %). The brain DIS result changed in 4, 1 and 3 of the 30 scans respectively (up to 13 %).

> **Withdrawn (CAPA-006, 2026-09-28)**: versions 1.0–1.1 of this section stated distance thresholds of 3 mm (PV), 4 mm (JC) and 3 mm (IT) and a two-tier classification (parcellation with a geometric fallback). ~~These described an earlier software version.~~ *Correction (review 2026-09-28)*: they were wrong when this document was issued on 2026-04-12 — the code had applied 1.5 mm since 2026-02-28 (commit 67fa336) and the four-path order since 2026-03-14 (commit a637cdf); 3/4/3 mm had been applied only in commit cf780f4 (2026-02-22). They are withdrawn. The 3/4/3 mm values are not published thresholds: MAGNIMS defines these regions by contact.

**Output (per lesion)**: the assigned region together with the evidence produced by the classification path that was used. No confidence score or probability is reported, because region assignment is a deterministic rule and no path has a calibrated per-lesion probability.

| Classification path | Evidence shown |
|---------------------|----------------|
| Parcellation (distance transform) | Distances in mm to the ventricle, cortex and infratentorial landmarks ("-" when a landmark is absent) |
| MSMask zone map | "Lesion % in zone" — fraction of all lesion voxels inside the assigned zone (e.g. "8% in PV"). Descriptive, not a probability; a low value is normal under the MAGNIMS contact rule |
| Geometric (fallback) | Distance columns in mm, which here are heuristic proxies (e.g. distance from the brain centre), not distances to anatomical landmarks |

The lesion table states: "Regions follow a deterministic MAGNIMS rule; no per-lesion confidence is reported."

**"No WM zone — DWM by default" (amber warning)**: shown when no voxel of the lesion lies in any MSMask white-matter zone (the lesion may be cortical or intraventricular, or the atlas may be misaligned). Deep White Matter was then assigned **by default, not by the MAGNIMS rule**. If the atlas is misaligned, the lesion may in fact be periventricular, juxtacortical or infratentorial, which could lead to a false-negative DIS result. Verify its location on the images before using it for DIS.

The accuracy of region assignment (any path) has not been measured against expert region labels; see Section 6.1.

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
| LST-AI | Lesion Segmentation Tool - AI (Wiltgen et al. 2024), source of the MSMask atlas |
| MAGNIMS | Magnetic Resonance Imaging in MS |
| MNI152 | Standard brain space of the Montreal Neurological Institute (MNI) |
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
