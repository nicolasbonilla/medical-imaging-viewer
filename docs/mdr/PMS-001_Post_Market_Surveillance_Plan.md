# MSTool-AI: Post-Market Surveillance Plan

**Document ID**: PMS-001 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: EU MDR 2017/745 Articles 83-85, Annex III

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Purpose and Scope

This Post-Market Surveillance (PMS) Plan establishes a systematic process for proactively collecting and evaluating data on the quality, performance, and safety of MSTool-AI throughout its post-market lifecycle, in accordance with EU MDR 2017/745 Articles 83-85 and Annex III.

### 1.1 Device Identification

| Field | Value |
|-------|-------|
| **Device Name** | MSTool-AI |
| **Classification** | Class IIa (Rule 11) |
| **UDI-DI** | To be assigned |
| **Software Type** | SaMD — AI-assisted brain MRI analysis |

### 1.2 PMS Objectives

- Confirm continued safety and performance of MSTool-AI in clinical use
- Detect emerging risks, systematic misuse, or off-label use
- Monitor AI/ML model performance and detect performance drift
- Identify trends in complaints, incidents, and user feedback
- Provide data for PSUR, risk management updates, and clinical evaluation updates
- Monitor SOUP components for security vulnerabilities

---

## 2. PMS System Description

The PMS system integrates proactive and reactive data collection, analysis, and action processes. Data flows into a centralized PMS database, is analyzed per defined schedules, and triggers corrective actions through the CAPA system (QP-002) when thresholds are met.

### 2.1 Responsible Personnel

| Role | Responsibility |
|------|---------------|
| **PMS Manager** | Overall PMS system management, PSUR preparation |
| **Quality Manager** | CAPA oversight, QMS integration |
| **Clinical Affairs** | Clinical literature monitoring, CER updates |
| **Software Development** | SOUP monitoring, defect resolution, AI performance tracking |
| **Regulatory Affairs** | Incident reporting, regulatory intelligence, EUDAMED updates |

---

## 3. Proactive Data Collection

### 3.1 Complaint Monitoring

- **Source**: User-reported issues via support channels, in-app feedback
- **Process**: All complaints logged in complaint database, triaged within 24 hours, assessed for reportability within 48 hours
- **Frequency**: Continuous
- **Metrics**: Complaint rate per active user, complaint categorization (safety/performance/usability)

### 3.2 User Feedback Surveys

- **Method**: Structured satisfaction surveys distributed to active users
- **Frequency**: Semi-annually
- **Content**: Usability satisfaction, clinical utility assessment, feature requests, perceived accuracy of AI outputs
- **Target Response Rate**: >30% of active users

### 3.3 Clinical Literature Monitoring

- **Databases**: PubMed, Cochrane Library, Embase
- **Search Terms**: SynthSeg validation, brain volumetry SaMD, MAGNIMS classification software, MS lesion segmentation AI, McDonald criteria automation
- **Frequency**: Quarterly
- **Output**: Literature review summary, relevance assessment, CER-001 update triggers

### 3.4 SOUP Vulnerability Monitoring

- **Components Monitored**: All SOUP listed in SOUP-001, including ONNX Runtime Web, SciPy, NumPy, FastAPI, React, Firebase SDK, Anthropic SDK
- **Sources**: CVE databases (NVD), GitHub Security Advisories, vendor notifications
- **Frequency**: Weekly automated scans, monthly manual review
- **Response**: Critical vulnerabilities assessed within 48 hours; patches deployed per severity per CYB-001

### 3.5 AI/ML Model Performance Monitoring

- **Metrics Tracked**: Segmentation accuracy (Dice coefficient), volumetry measurement consistency, MAGNIMS classification agreement with expert annotation, edge AI screening sensitivity/specificity
- **Method**: Periodic validation against curated test datasets, analysis of user correction frequency
- **Frequency**: Quarterly
- **Drift Detection**: Statistical comparison of current performance against baseline validation metrics; >5% degradation triggers investigation

### 3.6 Regulatory Intelligence

- **Scope**: EU MDR implementing acts, MDCG guidance documents, harmonized standard updates, EU AI Act implementation updates, competent authority advisories
- **Frequency**: Monthly
- **Sources**: European Commission, MDCG publications, notified body communications, IMDRF documents

---

## 4. Reactive Surveillance

### 4.1 Serious Incident Reporting (Article 87)

A serious incident is reported to the competent authority without delay, and no later than:
- **15 days** for incidents involving death or serious deterioration of health
- **10 days** for imminent serious public health threats
- **2 days** for death or unanticipated serious deterioration

**Reportability Assessment Criteria**:
- Incorrect AI segmentation leading to misdiagnosis
- Volumetric measurement errors exceeding clinically significant thresholds
- MAGNIMS misclassification affecting DIS assessment
- System failure during critical clinical workflow
- Data breach involving patient health information

### 4.2 Field Safety Corrective Actions (Article 89)

FSCA procedures include:
- Device recall (software update withdrawal)
- Software update deployment (forced or recommended)
- Field Safety Notice (FSN) distribution to affected users
- EUDAMED notification

### 4.3 Trend Reporting (Article 88)

Statistically significant increases in non-serious incidents or expected side-effects that could have a significant impact on benefit-risk are reported to competent authorities.

**Trend Detection Thresholds**:
- Complaint rate increase >50% over 6-month baseline
- Recurring identical failure mode reported by >3 independent users
- AI classification error pattern detected in >2% of analyzed cases

---

## 5. Periodic Safety Update Report (PSUR)

### 5.1 PSUR Frequency

Per EU MDR Article 86: **Annually** for Class IIa devices.

### 5.2 PSUR Content

Each PSUR includes:

1. **Summary of PMS data** collected during the reporting period
2. **Conclusions of the benefit-risk determination** with updated analysis
3. **Volume of sales** and estimated number of users
4. **Complaint and incident summary** with categorization and trend analysis
5. **FSCA summary** (if any were initiated)
6. **AI performance monitoring results** including drift analysis
7. **SOUP vulnerability summary** and remediation status
8. **Clinical literature review update**
9. **Risk management file update** triggers and actions taken
10. **Conclusions and actions** planned for the next period

### 5.3 PSUR Submission

- Submitted via EUDAMED
- Made available to the Notified Body
- PSUR kept as part of the technical documentation (TD-001)

---

## 6. PMS Data Analysis

### 6.1 Statistical Methods

- Trend analysis using control charts for complaint rates and incident frequency
- Performance metric comparison using paired statistical tests (Wilcoxon signed-rank for Dice coefficients, t-tests for volumetric measurements)
- Root cause analysis (Ishikawa, 5-Why) for recurring issues

### 6.2 Trend Detection Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Complaint rate | >50% increase over 6-month baseline | CAPA investigation |
| AI segmentation Dice score | >5% decrease from validation baseline | Model revalidation |
| Volumetry measurement CV | >10% coefficient of variation | Algorithm review |
| MAGNIMS classification disagreement | >15% disagreement with expert review | Classification algorithm audit |
| Critical SOUP vulnerability | CVSS >= 9.0 | Emergency patch within 72 hours |
| Edge AI false negative rate | >10% for abnormal cases | Model update or withdrawal |

### 6.3 Analysis Schedule

| Activity | Frequency |
|----------|-----------|
| Complaint trend review | Monthly |
| AI performance metrics review | Quarterly |
| SOUP vulnerability review | Monthly |
| Clinical literature review | Quarterly |
| Comprehensive PMS data review | Semi-annually |
| PSUR preparation | Annually |

---

## 7. Integration with Other Quality Processes

### 7.1 CAPA (QP-002)

PMS findings exceeding defined thresholds trigger CAPA investigations per QP-002. CAPA effectiveness is tracked and reported in the PSUR.

### 7.2 Risk Management (RMF-001)

PMS data feeds into periodic risk management file reviews per ISO 14971:2019. New hazards identified through PMS are added to the hazard analysis. Risk-benefit assessment is updated based on real-world data.

### 7.3 Clinical Evaluation (CER-001)

PMS data, including clinical performance data and literature review findings, feeds into CER-001 updates. The clinical evaluation is updated at least annually, synchronized with the PSUR cycle.

### 7.4 Post-Market Clinical Follow-Up (PMCF-001)

PMCF activities complement this PMS plan with structured clinical data collection to confirm long-term safety and performance. PMCF plan defined in a separate document (PMCF-001).

---

## 8. Record Keeping

All PMS records are maintained in the PMS database for a minimum of 10 years after the last device is placed on the market, per EU MDR Article 10(8). Records include:
- Complaint records and investigation reports
- Incident reports and FSCA documentation
- PSURs
- Trend analysis reports
- AI performance monitoring data
- SOUP vulnerability assessments
- Literature review summaries

---

## 9. Referenced Documents

| ID | Title |
|----|-------|
| TD-001 | Technical Documentation |
| RMF-001 | Risk Management File |
| CER-001 | Clinical Evaluation Report |
| PMCF-001 | Post-Market Clinical Follow-Up Plan |
| QP-002 | CAPA Procedure |
| QM-001 | Quality Management System |
| SOUP-001 | SOUP Bill of Materials |
| CYB-001 | Cybersecurity Assessment |
| MP-001 | Maintenance Plan |
| VVP-001 | Verification & Validation Plan |
| AIA-001 | AI Act Compliance Document |

---

*End of Document*
