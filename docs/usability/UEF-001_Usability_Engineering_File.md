# MSTool-AI: Usability Engineering File

**Document ID**: UEF-001 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: IEC 62366-1:2015+A1:2020

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Purpose

This Usability Engineering File documents the application of usability engineering
to MSTool-AI in accordance with IEC 62366-1:2015+A1:2020. It defines the use
specification, user profiles, use scenarios, hazard-related use scenarios, usability
goals, and evaluation plans for both formative and summative testing.

## 2. Use Specification

### 2.1 Intended Use

MSTool-AI is intended to assist qualified medical professionals in the quantitative
analysis of brain MRI for patients with known or suspected Multiple Sclerosis.
The device provides AI-assisted lesion segmentation, brain volumetry, MAGNIMS
region classification, and clinical report generation as decision support.

### 2.2 Intended Users

| Profile | Description |
|---|---|
| Primary | Neuroradiologists with 5+ years of brain MRI experience |
| Secondary | Neurologists specializing in MS or neuroimmunology |
| Tertiary | Radiology residents and research fellows (supervised use only) |

All intended users are expected to have:
- Medical degree and relevant board certification (or in training for tertiary users)
- Familiarity with brain MRI interpretation
- Knowledge of MS diagnostic criteria (McDonald 2024)
- Basic computer literacy and experience with PACS/medical imaging software

### 2.3 Use Environment

| Environment | Characteristics |
|---|---|
| Hospital radiology reading room | Dimmed lighting, diagnostic-grade monitors (minimum 2MP), PACS workstation, network access |
| Outpatient neurology clinic | Standard office lighting, clinical-grade display, EHR workstation, network access |
| Remote reading station | Home office, diagnostic-grade monitor required, VPN access |

**Environmental considerations**:
- Display calibration per DICOM GSDF is assumed
- Minimum screen resolution: 1920x1080
- Stable internet connection required (cloud-based device)
- Browser: Chrome 100+, Firefox 100+, or Edge 100+

### 2.4 Patient Population

- Adults aged 18 years and older
- Known or suspected Multiple Sclerosis
- Brain MRI acquired per standard MS protocols (MAGNIMS-CMSC-NAIMS 2024)
- All sexes and ethnicities

## 3. User Profiles

### 3.1 Primary User: Neuroradiologist

- **Education**: MD + radiology residency + neuroradiology fellowship
- **Experience**: 5+ years interpreting brain MRI, 100+ MS cases per year
- **Tasks**: Review AI segmentation overlays, validate volumetry results, confirm MAGNIMS classification, approve generated reports
- **Expectations**: High accuracy, fast workflow integration, minimal additional clicks
- **Limitations**: Time-constrained (5-10 minutes per case in high-volume practice)

### 3.2 Secondary User: Neurologist

- **Education**: MD + neurology residency, MS specialization
- **Experience**: 3+ years managing MS patients, familiar with MRI but not primary reader
- **Tasks**: Review reports, compare longitudinal studies, assess DIS criteria, clinical decision-making
- **Expectations**: Clear summary information, trend visualization, printable reports
- **Limitations**: May have less MRI interpretation expertise than radiologist

### 3.3 Tertiary User: Research Fellow / Resident

- **Education**: MD, in training
- **Experience**: Variable (1-3 years), supervised by primary or secondary user
- **Tasks**: Preliminary review, data entry, research data collection
- **Expectations**: Educational value, clear labeling, undo capability
- **Limitations**: Less experience with MS imaging, requires supervision for clinical decisions

## 4. Use Scenarios

### 4.1 Scenario 1: Routine MS Follow-Up

**User**: Neuroradiologist
**Context**: Annual follow-up MRI for established MS patient on disease-modifying therapy.

1. User opens patient study from PACS/worklist
2. MSTool-AI loads FLAIR and T1w sequences automatically
3. AI segmentation runs, overlay displayed on FLAIR
4. User reviews segmentation, corrects any errors using brush/eraser tools
5. User requests volumetry comparison with prior study
6. Brain volumetry panel shows volume changes with normative percentiles
7. Longitudinal comparison shows new/enlarged/resolved lesions
8. User generates structured report
9. Report is reviewed, approved, and exported to EHR

### 4.2 Scenario 2: New MS Diagnosis Workup

**User**: Neurologist reviewing with neuroradiologist
**Context**: Young adult presenting with optic neuritis, first brain MRI.

1. MRI loaded into MSTool-AI
2. AI segmentation identifies white matter lesions
3. MAGNIMS classification assigns regions (PV, JC, IT, DWM)
4. DIS assessment badge shows whether McDonald 2024 spatial criteria are met
5. Users review each lesion location against MAGNIMS classification
6. Volumetry baseline established
7. Report generated with DIS assessment summary
8. Clinical team uses report to support diagnostic discussion

### 4.3 Scenario 3: Longitudinal Comparison

**User**: Neuroradiologist
**Context**: Comparing current MRI with study from 12 months prior.

1. User loads current and prior studies
2. AI segments both timepoints
3. Longitudinal tracking matches lesions across timepoints
4. Change table shows NEW, ENLARGED, SHRUNK, RESOLVED, STABLE lesions
5. Lesion burden delta displayed
6. User reviews flagged changes
7. Report includes longitudinal summary

### 4.4 Scenario 4: AI-Assisted Segmentation Review

**User**: Research fellow (supervised)
**Context**: Research protocol requiring manual validation of AI segmentations.

1. Fellow loads study batch
2. AI segmentation displayed with confidence indicators
3. Fellow reviews each lesion, using MAGNIMS label presets
4. Brush and eraser tools used to refine segmentation boundaries
5. Undo/redo available for corrections
6. Contour overlay mode used for boundary verification
7. Supervisor reviews and approves final segmentation
8. Segmentation saved with audit trail

## 5. Hazard-Related Use Scenarios

The following 15 hazard-related use scenarios have been identified through task analysis
and risk assessment. Each scenario describes a use error or foreseeable misuse that
could lead to harm.

### H-01: Misinterpretation of AI Segmentation Overlay

**Scenario**: User interprets the AI segmentation overlay as definitive diagnosis rather
than a suggestion requiring validation.
**Hazard**: Incorrect clinical decision based on unvalidated AI output.
**Severity**: Serious
**Mitigation**: Prominent disclaimer banner ("AI-assisted — requires clinical validation");
overlay labeled "Draft" until user explicitly approves.

### H-02: Failure to Notice Disclaimers

**Scenario**: User dismisses or ignores safety disclaimers due to alert fatigue.
**Hazard**: Clinical decisions made without understanding AI limitations.
**Severity**: Serious
**Mitigation**: Disclaimers are non-dismissible for first 5 seconds; disclaimer
acknowledgment logged; critical disclaimers use distinct visual design (red border).

### H-03: Wrong Patient Loaded

**Scenario**: User loads the wrong patient's MRI study and reviews AI results for
the incorrect patient.
**Hazard**: Clinical decisions applied to wrong patient.
**Severity**: Critical
**Mitigation**: Patient name, DOB, and MRN displayed prominently in viewer header;
DICOM header verification against worklist; confirmation prompt when switching patients.

### H-04: Reliance on AI Volumetry Without Clinical Correlation

**Scenario**: User relies solely on AI volumetry percentile to diagnose brain atrophy
without considering patient-specific factors (age, hydrocephalus, prior surgery).
**Hazard**: Incorrect atrophy diagnosis leading to inappropriate treatment decisions.
**Severity**: Serious
**Mitigation**: Volumetry panel includes disclaimer "Correlate with clinical findings";
outlier values flagged for review; normative ranges shown with confidence intervals.

### H-05: Misreading DIS Criteria Badge

**Scenario**: User misinterprets a "DIS Met" badge as confirming MS diagnosis rather
than indicating spatial dissemination criteria alone.
**Hazard**: Premature or incorrect MS diagnosis.
**Severity**: Serious
**Mitigation**: Badge tooltip explains "Spatial criteria only — does not confirm MS
diagnosis"; badge labeled "DIS (spatial only)"; report template includes full criteria context.

### H-06: Confusion Between Heatmap and Segmentation

**Scenario**: User confuses the volumetric heatmap overlay with lesion segmentation,
interpreting heatmap intensity as lesion probability.
**Hazard**: Incorrect lesion identification.
**Severity**: Moderate
**Mitigation**: Distinct color schemes (segmentation: categorical colors; heatmap:
continuous hot colormap); clear mode indicator in toolbar; mode label on canvas.

### H-07: False Negative — AI Misses Lesion

**Scenario**: AI fails to segment a clinically significant lesion, and user does not
independently identify it.
**Hazard**: Missed lesion affecting diagnosis or treatment decision.
**Severity**: Serious
**Mitigation**: AI explicitly labeled as assistive; training materials emphasize
independent review; sensitivity metrics displayed; small lesion warning when low
confidence.

### H-08: False Positive — AI Marks Non-Lesion

**Scenario**: AI incorrectly segments an artifact or normal variant as a lesion.
**Hazard**: Unnecessary clinical concern, additional testing, or treatment.
**Severity**: Moderate
**Mitigation**: Confidence score displayed per lesion; low-confidence lesions highlighted
differently; user can delete false positives with single click.

### H-09: Incorrect MAGNIMS Region Assignment

**Scenario**: AI assigns a periventricular lesion as juxtacortical, affecting DIS assessment.
**Hazard**: Incorrect DIS assessment may affect diagnosis.
**Severity**: Serious
**Mitigation**: Classification confidence displayed; distance to anatomical boundary
shown; user can override region assignment; two-tier classification with fallback.

### H-10: Longitudinal Mismatch — Wrong Timepoint Comparison

**Scenario**: User inadvertently compares studies from incorrect timepoints or different patients.
**Hazard**: Incorrect assessment of disease progression.
**Severity**: Serious
**Mitigation**: Study dates prominently displayed; patient identity verification across
timepoints; warning if study date gap exceeds expected interval.

### H-11: Report Generated With Incorrect Data

**Scenario**: AI report includes data from a different analysis or outdated segmentation
that the user has since modified.
**Hazard**: Clinical report does not reflect current findings.
**Severity**: Serious
**Mitigation**: Report generation uses current in-memory data only; warning if
segmentation has been modified since last save; report timestamped and version-tracked.

### H-12: User Accidentally Modifies Approved Segmentation

**Scenario**: User inadvertently paints over an approved segmentation while reviewing.
**Hazard**: Corrupted segmentation data affecting downstream analysis.
**Severity**: Moderate
**Mitigation**: Undo/redo (Ctrl+Z/Ctrl+Y) available; segmentation lock after approval;
modification warning on locked segmentations; slice-level undo snapshots.

### H-13: Inadequate Display Calibration

**Scenario**: User reviews segmentation on an uncalibrated or low-resolution display,
missing subtle overlay details.
**Hazard**: Missed findings due to display limitations.
**Severity**: Moderate
**Mitigation**: Minimum display requirements documented; warning if browser window
below minimum resolution; high-contrast overlay colors; adjustable overlay opacity.

### H-14: Network Interruption During Analysis

**Scenario**: Network connection drops during AI processing, and user is unaware
results are incomplete.
**Hazard**: Incomplete analysis presented as complete.
**Severity**: Serious
**Mitigation**: Processing status indicator with error states; incomplete analyses
clearly marked; auto-save of local edits; retry mechanism with user notification.

### H-15: Expert Mask Overlay Confused With AI Segmentation

**Scenario**: User loads an expert annotation overlay and confuses it with the AI
segmentation, or vice versa.
**Hazard**: Clinical decisions based on wrong data source.
**Severity**: Moderate
**Mitigation**: Expert overlays use distinct colors (EXPERT_COLORS palette); overlay
source label displayed in toolbar; toggle buttons clearly separated in panel.

## 6. Usability Goals

### 6.1 Effectiveness Goals

| Goal | Metric | Target |
|---|---|---|
| Task completion rate | Percentage of tasks completed without critical error | >= 95% |
| Critical use errors | Use errors that could lead to harm (H-01 through H-15) | 0 in summative evaluation |
| Segmentation review accuracy | Proportion of AI errors identified by user during review | >= 90% |

### 6.2 Efficiency Goals

| Goal | Metric | Target |
|---|---|---|
| MS assessment time | Time to complete full MS follow-up assessment | <= 15 minutes |
| Segmentation review time | Time to review and approve AI segmentation | <= 5 minutes |
| Report generation time | Time from request to approved report | <= 3 minutes |

### 6.3 Satisfaction Goals

| Goal | Metric | Target |
|---|---|---|
| System Usability Scale (SUS) | Standardized SUS score | >= 70 (acceptable) |
| Clinician satisfaction | Custom satisfaction questionnaire | >= 80% satisfactory |
| Willingness to recommend | Net Promoter Score | >= 30 |

## 7. Formative Evaluation Plan

### 7.1 Overview

Three rounds of formative evaluation shall be conducted during development to identify
and correct usability issues before summative testing.

### 7.2 Round 1 — Early Prototype

- **Participants**: 3 neuroradiologists
- **Method**: Think-aloud protocol with low-fidelity prototype
- **Focus**: Navigation flow, segmentation review workflow, overlay comprehension
- **Duration**: 60 minutes per participant
- **Output**: Usability findings report, design recommendations

### 7.3 Round 2 — Functional Prototype

- **Participants**: 5 users (3 neuroradiologists, 2 neurologists)
- **Method**: Think-aloud protocol with functional prototype (real MRI data)
- **Focus**: Segmentation editing tools, volumetry interpretation, MAGNIMS classification, report generation
- **Duration**: 90 minutes per participant
- **Output**: Updated usability findings, hazard-related use scenario validation

### 7.4 Round 3 — Pre-Release

- **Participants**: 4 users (2 neuroradiologists, 1 neurologist, 1 research fellow)
- **Method**: Simulated clinical workflow with realistic scenarios
- **Focus**: End-to-end workflow, error recovery, disclaimer comprehension, longitudinal comparison
- **Duration**: 90 minutes per participant
- **Output**: Final formative findings, go/no-go recommendation for summative evaluation

## 8. Summative Evaluation Plan

### 8.1 Study Design

A summative usability evaluation shall be conducted to validate that MSTool-AI can
be used safely and effectively by the intended users in the intended use environment.

### 8.2 Participants

- **Total**: 15 representative users
- **Composition**: 8 neuroradiologists, 5 neurologists, 2 research fellows
- **Inclusion criteria**: Meets intended user profile (Section 3); no prior exposure to MSTool-AI
- **Exclusion criteria**: Involvement in device development

### 8.3 Test Environment

- Clinical simulation room with diagnostic-grade monitor (minimum 2MP)
- Calibrated display per DICOM GSDF
- Realistic network conditions (cloud-based deployment)
- Observer station with screen recording and eye tracking (optional)

### 8.4 Test Scenarios

| Scenario | Description | Hazard-Related Scenarios Tested |
|---|---|---|
| S1 | Routine MS follow-up with AI segmentation review | H-01, H-02, H-07, H-08 |
| S2 | New diagnosis workup with DIS assessment | H-05, H-09 |
| S3 | Longitudinal comparison (2 timepoints) | H-10, H-12 |
| S4 | Report generation and review | H-04, H-11 |
| S5 | Error recovery (network interruption simulation) | H-14 |
| S6 | Expert overlay vs AI segmentation distinction | H-06, H-15 |
| S7 | Wrong patient detection task | H-03 |

### 8.5 Data Collection

- Task completion (success/failure/partial)
- Task time
- Use errors (critical and non-critical) with root cause classification
- Subjective ratings: SUS questionnaire, custom satisfaction questionnaire, NASA-TLX workload
- Post-task interviews (structured)
- Screen recordings with audio for retrospective analysis

### 8.6 Standardized Evaluation Questionnaire

A standardized post-session questionnaire shall include:

1. System Usability Scale (SUS) — 10 items, 5-point Likert
2. Custom MSTool-AI satisfaction questions (15 items):
   - Segmentation overlay clarity
   - Volumetry display comprehension
   - MAGNIMS classification understandability
   - Report quality and completeness
   - Disclaimer visibility and comprehension
   - Confidence in AI output
   - Workflow integration
3. NASA-TLX workload assessment (6 dimensions)
4. Open-ended feedback questions

### 8.7 Pass/Fail Criteria

The summative evaluation passes if ALL of the following are met:
- Task completion rate >= 95% across all participants and scenarios
- Zero critical use errors (use errors that could lead to harm per hazard analysis)
- SUS score >= 70 (mean across participants)
- All 15 hazard-related use scenarios adequately mitigated (no unmitigated hazardous situations observed)

## 9. Known Use Problems With Similar Devices

From published usability literature on medical imaging AI tools:

| Problem | Source | Relevance to MSTool-AI |
|---|---|---|
| Automation bias — over-trust in AI output | Goddard et al. 2012, Cabitza et al. 2017 | High — addressed by H-01, H-07 |
| Alert fatigue with excessive warnings | Ancker et al. 2017 | Moderate — disclaimer design balances visibility and fatigue |
| Difficulty interpreting probability/confidence | Reyna et al. 2009 | High — confidence indicators must be intuitive |
| Inconsistent overlay rendering across displays | AAPM TG-270 | Moderate — minimum display requirements specified |
| Confusion between different overlay types | Defined et al. 2019 | High — addressed by H-06, H-15 |

## 10. UI Design Principles

### 10.1 MAGNIMS Color Coding

- **Periventricular (PV)**: Blue (#3B82F6)
- **Juxtacortical (JC)**: Green (#22C55E)
- **Infratentorial (IT)**: Orange (#F97316)
- **Deep White Matter (DWM)**: Purple (#A855F7)
- Colors chosen for distinguishability under color vision deficiency (tested with Sim Daltonism)

### 10.2 Disclaimers

- AI output disclaimers visible without scrolling
- Critical disclaimers use red border and warning icon
- Non-dismissible for minimum 5 seconds on first display
- Disclaimer text reviewed by clinical advisory board

### 10.3 Confidence Indicators

- Per-lesion confidence score (0-100%) displayed on hover
- Low confidence (< 60%) shown with dashed outline
- Medium confidence (60-80%) shown with solid outline
- High confidence (> 80%) shown with bold outline
- Classification confidence badge in lesion table

### 10.4 General Principles

- Progressive disclosure: summary first, details on demand
- Consistent layout across all analysis modes
- Keyboard shortcuts for expert users (documented in ? modal)
- Undo/redo for all destructive actions
- Clear mode indicators (segmentation vs heatmap vs expert overlay)
- Responsive design with minimum resolution enforcement

## 11. References

1. IEC 62366-1:2015+A1:2020. Medical devices — Application of usability engineering to medical devices.
2. IEC/TR 62366-2:2016. Medical devices — Guidance on the application of usability engineering to medical devices.
3. FDA Guidance. Applying Human Factors and Usability Engineering to Medical Devices. February 2016.
4. AAMI HE75:2009/(R)2018. Human factors engineering — Design of medical devices.
5. Goddard K, et al. Automation bias in medicine. *J Am Med Inform Assoc*. 2012;19(1):121-127.
6. Cabitza F, et al. Unintended consequences of machine learning in medicine. *JAMA*. 2017;318(6):517-518.
7. CEP-001 Clinical Evaluation Plan, MSTool-AI.
8. RMF-001 Risk Management File, MSTool-AI.
