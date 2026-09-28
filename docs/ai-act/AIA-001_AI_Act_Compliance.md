# MSTool-AI: AI Act Compliance Document

**Document ID**: AIA-001 | **Version**: 1.3 | **Date**: September 28, 2026
**Standard**: EU AI Act — Regulation (EU) 2024/1689

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |
| 1.1 | 2026-09-28 | Development Team | — |
| 1.2 | 2026-09-28 | Development Team | — |
| 1.3 | 2026-09-28 | Development Team | — |

*Version 1.2 (CAPA-006, HAZ-005)*: MAGNIMS classification description corrected (Sections 2.1, 2.2, 4.1, 4.2, 4.3, 4.5, 4.7). Version 1.1 stated distance thresholds of 3 mm (PV), 4 mm (JC) and 3 mm (IT), called them "published", and described a two-tier cascade (parcellation, geometric fallback). ~~These described an earlier software version (commit cf780f4, February 2026) and are withdrawn.~~ *Correction (review 2026-09-28)*: they did not describe the software at issue. The code applied 3.0/4.0/3.0 mm only in commit cf780f4 (2026-02-22, with a Harvard-Oxford zone map); commit 67fa336 (2026-02-28) changed it to 1.5 mm and added the MSMask atlas; the four-path order dates from commit a637cdf (2026-03-14). Version 1.0 was issued on 2026-04-12 (commit 9ac536d) already stating 3/4/3 mm, six weeks after the code had moved to 1.5 mm and on the day the DDS was issued stating 1.5 mm: this document was wrong when issued and had not been reviewed against the code or the DDS. The values are withdrawn. The current software uses the MAGNIMS contact criterion (1.5 mm on the parcellation path) and a four-path order in which the MSMask atlas is applied only to MNI-space images.

*Version 1.3 (CAPA-006 review, HAZ-005)*: Sections 2.1, 2.2, 4.1, 4.2, 4.3, 4.5 and 4.7 aligned with the code, correcting v1.2 text: the LST-AI path copies LST-AI's zones voxel by voxel with no contact rule and no priority; the parcellation test and the limits of the 1.5 mm rule are stated; the MSMask path was called "the usual path" (withdrawn: native clinical scans normally fail the MNI grid check and are classified by the geometric path), described as "lesion voxels touching the atlas zones … as in LST-AI" (corrected: lesion voxels lying in an atlas zone, adapted from LST-AI, not validated) and with two of the five MNI grid conditions (all five now stated); the geometric path's refusal preconditions and warning, and the refusal when no path applies, are added; misalignment figures corrected to the product-rule run (27.5 % of lesions; v1.2 quoted 28 % from a superseded run); "Vertex AI" corrected in Sections 2.1, 2.2 and 4.7 (SynthSeg, disabled by default, runs as a separate service at SYNTHSEG_ENDPOINT when enabled; no Vertex AI endpoint is deployed); tier wording replaced in v1.2 is kept struck through; region-assignment accuracy has not been measured for any path.

---

## 1. Purpose

This document demonstrates MSTool-AI's compliance with the European Union Artificial Intelligence Act (Regulation (EU) 2024/1689), which entered into force on August 1, 2024. MSTool-AI incorporates multiple AI/ML components and, as a medical device with AI functionality, is classified as a high-risk AI system.

---

## 2. AI System Description

### 2.1 AI/ML Components in MSTool-AI

MSTool-AI integrates four distinct AI/ML components:

| Component | Type | Deployment | Function |
|-----------|------|-----------|----------|
| **SynthSeg Brain Segmentation** | Deep learning (CNN) | ~~Vertex AI (cloud)~~ Separate service at the configured `SYNTHSEG_ENDPOINT`, not Google Vertex AI *(corrected v1.3, CAPA-006)* | Automated parcellation of 33 brain structures from MRI — *disabled by default (`SYNTHSEG_ENABLED=false`; not enabled by the deployment pipeline)* |
| **ONNX Edge AI Screening** | Neural network (binary classifier) | Browser (ONNX Runtime Web) | Rapid normal/abnormal triage of brain MRI slices |
| **Claude API Report Generation** | Large language model (LLM) | Anthropic Cloud API | Generation of structured clinical reports from findings |
| **EDT-based MAGNIMS Classification** | Algorithmic (distance transform + rules) | Backend (Python/NumPy/SciPy) | Region classification of MS lesions per McDonald 2024 |

### 2.2 AI Component Details

**SynthSeg Brain Segmentation**
- Architecture: Convolutional Neural Network (SynthSeg variant)
- Training: Synthetic data augmentation approach (domain-randomized training)
- Inference: ~~Vertex AI endpoint (Google Cloud)~~ separate SynthSeg service at `SYNTHSEG_ENDPOINT` when enabled; disabled by default *(corrected v1.3, CAPA-006: no Vertex AI endpoint is deployed)*
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
- ~~Method: Euclidean Distance Transform with rule-based thresholds~~ / ~~Tier 2: SynthSeg parcellation + EDT (PV<=3mm ventricle, JC<=4mm cortex, IT<=3mm infratentorial)~~ / ~~Tier 1 fallback: Geometric heuristics (z-coordinate, center distance, surface distance)~~ — *v1.1 text, replaced in v1.2 (CAPA-006): the 3/4/3 mm values and the two-level cascade did not describe the software at issue (see the version notes)*
- Criterion (MAGNIMS / McDonald 2024; Filippi et al. 2019): periventricular (PV) = abutting the lateral ventricles; juxtacortical (JC) = abutting the cortex; infratentorial (IT) = in or touching the brainstem or cerebellum; otherwise deep white matter (DWM). On the parcellation, MSMask and geometric paths the priority is IT > PV > JC > DWM; the LST-AI path copies LST-AI's zones voxel by voxel. Only PV, JC and IT count towards brain DIS (spinal cord and optic nerve are not evaluated from the images; clinician-entered evidence for them is accepted by the DIS assessment).
- Method: deterministic rules, no trained model. In `auto` mode the paths are tried in this order, the first that applies is used, and the path used is reported. If no path can be applied validly, the request is refused (HTTP 422) with the reasons; no regions are assigned:
  1. LST-AI zones — only if another segmentation of the same image was produced by LST-AI (`validation_source` contains "lst-ai"); LST-AI integration disabled by default (`LSTAI_ENABLED=false`; not enabled by the deployment pipeline). Copies, voxel by voxel, the zone LST-AI assigned: no contact rule and no priority, so one lesion can receive more than one region; lesion voxels outside LST-AI's zones become DWM without a warning
  2. Parcellation + Euclidean Distance Transform — with an explicit `parcellation_id`, or when another segmentation of the same image looks like a FreeSurfer parcellation (at least 3 of the labels {2,3,4,7,8,10,16,41,42,43} and at least one of {16,41,42,43}, and not a MAGNIMS zone map; an explicit `parcellation_id` that fails this test is refused with HTTP 422). SynthSeg integration disabled by default (`SYNTHSEG_ENABLED=false`; not enabled by the deployment pipeline). "Abutting" = minimum distance <= 1.5 mm between lesion voxel centres and the lateral-ventricle (4, 43), cortex (3, 42) or brainstem/cerebellum (7, 8, 16, 46, 47) labels (PV/JC/IT_DISTANCE_THRESHOLD_MM = 1.5). With slices thicker than 1.5 mm, contact through the slice direction is not detected; at 1 mm voxels, diagonal (corner) neighbours at 1.73 mm are missed
  3. MSMask atlas (LST-AI MSMask, Wiltgen et al. 2024, used here in an adapted form that has not been validated) — only for images already registered to MNI152; no registration is performed. The image must meet all of: isotropic voxels (max/min spacing <= 1.05); axes aligned with and not permuted relative to the world axes (within ~2.5°); field of view within 25 % of 181x217x181 mm on each axis; grid centre within 10 mm of the MNI template centre (0, -18, 18) mm; a spatial transform in the header (sform or qform code not 0). Native clinical scans normally fail these conditions. The zone map is generated fresh for every classification (a stored zone map is never reused). Zones: the atlas ventricle, cortex and infratentorial structures dilated by one voxel (3x3x3 cube on the 1 mm atlas, adapted from LST-AI) and intersected with atlas white matter, plus the infratentorial structures themselves; zone precedence IT > PV > JC. A lesion is assigned the highest-priority zone that any of its voxels lies in (IT > PV > JC > DWM, the DWM zone being the remaining atlas white matter); a lesion with no voxel in any zone is DWM by default and flagged "No WM zone — DWM by default". If the conditions fail: HTTP 422 if MSMask was requested explicitly; in `auto` the geometric path is tried and the user sees an amber "Atlas regions not used: this image is not in MNI space..." warning. The grid check cannot certify that an image is truly normalized (an image resampled onto an MNI grid without registration passes)
  4. Geometric heuristics — least accurate; coordinate rules, not anatomical landmarks. Refused unless the source image can be read, its orientation can be determined, its slice axis runs from inferior to superior (axial acquisition; sagittal, coronal or superior-to-inferior slice order is refused), it is 3-D, it is on the same grid as the lesion mask and it is not blank. Brain outline = Otsu threshold (x0.3) of the image intensities, holes filled (the head outline if the image is not skull-stripped); IT = lesion centroid in the lowest 25 % of the outline's extent along the slice axis; PV = mean distance of the lesion's voxels from the brain centre below 35 % of the largest such distance in the image array; JC = lesion within min(8 mm, 15 % of the maximum depth of the outline) of the outline surface; otherwise DWM. Whenever regions come from this path the UI shows an amber warning ("Geometric heuristics: the least accurate method (coordinate rules, not anatomical landmarks). Verify every region before using it for DIS."), or the atlas warning when the atlas was refused
- Region-assignment accuracy has not been measured for any path (HAZ-005 residual risk undetermined).
- Output: Per-lesion region label, ~~confidence score~~, distance metadata
- *Amended 2026-09-28 (REQ-SAFE-010 amended, RC-010 (amended), HAZ-005)*: no classification path emits or displays a per-lesion confidence (always null); region assignment is a deterministic rule with no calibrated per-lesion probability. Evidence is exposed under its own name: `distances_mm` (parcellation; each distance is null when its landmark is absent) or, for the MSMask zone-map path, `region_overlap_fraction`, `zone_coverage_fraction` and `atlas_coverage` (false = no white-matter zone, Deep White Matter assigned by default, shown as the warning "No WM zone — DWM by default"). Region-assignment logic unchanged by that amendment (CAPA-006 then added path preconditions — §2.2).

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
  - MAGNIMS misclassification — mitigated by ~~confidence scoring and~~ ~~Tier 1/Tier 2 transparency~~ classification-path transparency (the path used is reported) *(v1.2, CAPA-006: the tier wording did not describe the software)*. *v1.2 (CAPA-006)*: the MNI-space MSMask atlas is refused on images whose grid is not MNI-like, because without registration a misalignment by up to 3°, 3 % and 5 mm inside an MNI grid changed the region of 27.5 % (216/786) of expert-annotated lesions on 30 MNI-registered scans (43.0 % and 55.2 % at larger misalignments) and changed brain DIS in up to 13 % of scans in a controlled experiment; in `auto` the geometric heuristics are then used, with an on-screen warning, only if their own preconditions hold (axial inferior-to-superior 3-D image on the lesion-mask grid); otherwise the request is refused with the reasons. *2026-09-28*: confidence scoring removed as a mitigation (it was not a calibrated probability); replaced by per-lesion evidence display and the "No WM zone — DWM by default" warning (RC-010 (amended)), which are information-for-safety only. Region-assignment accuracy has not been measured against expert region labels; HAZ-005 residual risk is **undetermined** and requires re-assessment (RMF-001)
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
| MAGNIMS Classification | ~~Rule-based system using published distance thresholds from McDonald 2024 criteria.~~ *(v1.1 text, replaced in v1.2, CAPA-006: McDonald 2024 / MAGNIMS publish no distance thresholds.)* Rule-based system implementing the MAGNIMS / McDonald 2024 contact criterion (lesion abutting the lateral ventricles or cortex, or in or touching the brainstem/cerebellum). MAGNIMS defines contact, not distance thresholds; the parcellation path implements contact as a distance <= 1.5 mm, the MSMask path (adapted from LST-AI, not validated) as lesion voxels lying in an atlas zone (atlas white matter within the one-voxel dilation of the structure) (see Section 2.2). No training data required. Region-assignment accuracy has not been measured for any path. |

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
  - Key design parameters and choices (model architectures, ~~distance thresholds~~ contact criterion and its implementation per classification path — ~~confidence scoring~~ withdrawn: no path reports a per-lesion confidence, REQ-SAFE-010) *(v1.2, CAPA-006: "distance thresholds" replaced — MAGNIMS defines contact; a distance is its implementation on the parcellation path only)*
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
  - ~~MAGNIMS classification includes per-lesion confidence scores and distance metadata~~ — *superseded 2026-09-28*: MAGNIMS classification reports no per-lesion confidence; it shows each lesion's region with its evidence (distances in mm, or "Lesion % in zone"), an amber "No WM zone — DWM by default" warning, and the statement "Regions follow a deterministic MAGNIMS rule; no per-lesion confidence is reported." (REQ-SAFE-010 amended; verified by UT-CLS-002, UI-RC010)
  - Edge AI screening displays confidence percentage and inference time
- **Limitations Documentation**: IFU-001 documents all known limitations, contraindications, and appropriate use conditions
- **Classification Method Transparency**: ~~MAGNIMS dashboard shows classification tier (Tier 1/Tier 2) and method used~~ *(v1.1 text, replaced in v1.2, CAPA-006: the software has no tiers)*. MAGNIMS dashboard shows the classification path used (LST-AI zones, parcellation, MSMask atlas or geometric). When regions come from the geometric heuristics it shows an amber warning: "Geometric heuristics: the least accurate method (coordinate rules, not anatomical landmarks). Verify every region before using it for DIS." — or, when the atlas was not applied because the image is not in MNI space, the amber warning that the least accurate geometric fallback was applied. When no path can be applied validly, the reasons are shown and no regions are assigned

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
- Validation of MAGNIMS classification against expert consensus — *status 2026-09-28: NOT yet performed*; region-assignment accuracy (any path) has not been measured against expert region labels (HAZ-005 residual undetermined)
- Performance metrics documented and monitored post-market (PMS-001)

**Robustness**:
- Graceful degradation when AI services unavailable (~~Vertex AI~~ SynthSeg / LST-AI services when enabled, Claude API) *(v1.3, CAPA-006: no Vertex AI endpoint is deployed)*
- Edge AI automatic fallback from WebGPU to WASM execution
- Input validation for corrupted or malformed image data
- Error boundary components prevent UI crashes from propagating
- ~~Multi-tier MAGNIMS classification (Tier 2 primary, Tier 1 fallback)~~ *(v1.1 text, replaced in v1.2, CAPA-006)*. MAGNIMS classification with an ordered set of paths (LST-AI zones, parcellation, MSMask atlas, geometric heuristics); the MNI-space atlas is refused on non-MNI image grids rather than applied without registration, the geometric heuristics are refused unless the image is an axial, inferior-to-superior 3-D image on the lesion-mask grid, and when no path applies validly the request is refused with the reasons rather than regions being guessed (HAZ-005). These refusals are fail-closed controls, not evidence of accuracy: region-assignment accuracy has not been measured for any path

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
