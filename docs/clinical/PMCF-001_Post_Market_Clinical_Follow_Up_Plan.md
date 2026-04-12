# MSTool-AI: Post-Market Clinical Follow-Up Plan

**Document ID**: PMCF-001 | **Version**: 1.0 | **Date**: April 12, 2026
**Standard**: EU MDR 2017/745 Annex XIV Part B, MDCG 2020-7

---

| Version | Date | Author | Approved By |
|---------|------|--------|-------------|
| 1.0 | 2026-04-12 | Development Team | — |

---

## 1. Purpose

This Post-Market Clinical Follow-Up (PMCF) Plan defines the proactive activities
to collect and evaluate clinical data on MSTool-AI after market placement, in accordance
with EU MDR 2017/745 Annex XIV Part B and MDCG 2020-7 guidance.

PMCF activities shall confirm the clinical safety and performance of the device
throughout its intended lifetime and identify previously unknown risks or emerging
clinical concerns.

## 2. Device and Scope

- **Device**: MSTool-AI (SaMD, Class IIa, IEC 62304 Class C)
- **Intended purpose**: AI-assisted MS lesion segmentation, brain volumetry, MAGNIMS classification, report generation
- **Scope**: All clinical sites using MSTool-AI in routine MS clinical workflow
- **Related documents**: CEP-001, CER-001, UEF-001

## 3. PMCF Objectives

### 3.1 Primary Objectives

1. **Confirm clinical safety**: Verify that MSTool-AI does not introduce unacceptable risks when used in routine clinical practice
2. **Confirm clinical performance**: Validate that clinical claims (CEP-001 Section 3) are maintained under real-world conditions
3. **Detect emerging risks**: Identify adverse events, near-misses, or use patterns not anticipated during pre-market evaluation

### 3.2 Secondary Objectives

4. **Monitor state of the art**: Track evolving diagnostic criteria (McDonald criteria revisions, MAGNIMS updates), new AI benchmarks, and competing device performance
5. **Validate residual risk acceptability**: Confirm that residual risks identified in the risk management file remain acceptable
6. **Support CER updates**: Generate clinical data for periodic CER updates (minimum annually per MDR Article 61(11))
7. **Identify subpopulation performance**: Assess performance across different scanner types, field strengths, clinical sites, and patient demographics

## 4. PMCF Methods

### 4.1 User Surveys (Annual)

**Objective**: Assess ongoing user satisfaction, identify use problems, and evaluate
clinical utility.

| Parameter | Details |
|---|---|
| Frequency | Annual (Q4 each year) |
| Target respondents | All active clinical users (minimum 20 responses per cycle) |
| Method | Standardized online questionnaire (validated Likert scales) |
| Topics | Overall satisfaction, segmentation accuracy perception, report quality, workflow integration, training adequacy, feature requests |
| Analysis | Descriptive statistics, trend analysis year-over-year |
| Acceptance criterion | Overall satisfaction >= 80% "satisfactory" or above |

### 4.2 Clinical Performance Registry

**Objective**: Collect real-world performance data on segmentation accuracy, volumetry
consistency, and classification agreement.

| Parameter | Details |
|---|---|
| Frequency | Continuous collection, quarterly analysis |
| Method | Automated logging of anonymized performance metrics (with user consent) |
| Metrics | Cases processed, segmentation confidence scores, volumetry outlier flags, classification distribution, user edits to AI output |
| Sample size | Minimum 500 cases per year |
| Analysis | Performance trend monitoring, site-level comparison, drift detection |
| Acceptance criteria | Mean segmentation confidence stable within 5% of baseline; user edit rate stable or declining |

### 4.3 Literature Monitoring (Quarterly)

**Objective**: Track the evolving state of the art and identify new safety signals
from the published literature.

| Parameter | Details |
|---|---|
| Frequency | Quarterly literature search |
| Databases | PubMed, Cochrane, Embase, FDA MAUDE |
| Search terms | Per CEP-001 Section 5.2, plus device-specific terms |
| Scope | New MS diagnostic criteria, AI segmentation benchmarks, competing device publications, adverse events with similar devices |
| Output | Quarterly literature summary report, annual state-of-the-art update for CER |

### 4.4 Complaint and Vigilance Analysis

**Objective**: Systematically analyze all complaints, adverse events, and near-misses
for clinical safety signals.

| Parameter | Details |
|---|---|
| Frequency | Continuous monitoring, monthly review |
| Sources | Customer complaints, vigilance reports, field safety corrective actions |
| Classification | Severity (serious/non-serious), relatedness, root cause |
| Escalation | Serious adverse events reported within 15 days per MDR Article 87 |
| Trend analysis | Quarterly trend review, annual summary for CER |

### 4.5 PMCF Study — Observational Multi-Center

**Objective**: Prospective collection of clinical outcome data in routine clinical use.

| Parameter | Details |
|---|---|
| Design | Prospective, observational, multi-center |
| Target sites | 3-5 clinical sites (academic hospitals and community neurology practices) |
| Sample size | 200 patients over 24 months |
| Inclusion | Adults with known or suspected MS, brain MRI analyzed with MSTool-AI |
| Endpoints | Segmentation accuracy (expert review of subset), diagnostic concordance, reading time impact, clinical decision changes |
| Ethics | Ethics committee approval required per site; informed consent for data collection |
| Data management | Anonymized, centralized database with audit trail |

## 5. Acceptance Criteria for Continued Safety and Performance

The following criteria must be met for continued market placement without corrective action:

| Criterion | Threshold | Action if Not Met |
|---|---|---|
| Serious adverse events related to device | 0 per year | Immediate investigation, FSCA if required |
| User satisfaction (annual survey) | >= 80% satisfactory | Root cause analysis, corrective action plan |
| Segmentation performance drift | < 5% decline from baseline | Algorithm review, retraining assessment |
| User edit rate to AI output | Stable or declining trend | Usability investigation |
| Complaint rate | < 2% of active user base per quarter | Trend analysis, design review |
| Literature-identified new risks | None unaddressed within 90 days | Risk management file update, CER amendment |

## 6. Reporting

### 6.1 PMCF Evaluation Report

A PMCF Evaluation Report shall be produced annually summarizing all PMCF activities,
findings, and conclusions. This report feeds directly into the CER update cycle.

**Contents**:
- Summary of all data collected during the reporting period
- Performance trend analysis
- New literature findings and state-of-the-art assessment
- Adverse event and complaint summary
- Conclusions on continued safety and performance
- Recommendations for design changes, labeling updates, or additional studies

### 6.2 CER Update Cycle

Per MDR Article 61(11), the CER (CER-001) shall be updated:
- **Annually** for Class IIa devices
- **Ad hoc** if a significant safety signal is identified through PMCF

### 6.3 Periodic Safety Update Report (PSUR)

PMCF data shall be integrated into the PSUR as required by MDR Article 86.

## 7. Timeline and Milestones

| Milestone | Target Date | Responsible |
|---|---|---|
| PMCF Plan finalized | Q2 2026 | Clinical Affairs |
| Ethics submissions for PMCF study | Q3 2026 | Clinical Affairs |
| First site activated (PMCF study) | Q4 2026 | Clinical Affairs |
| First user survey deployed | Q4 2026 (post-launch) | Quality |
| Performance registry operational | At product launch | Engineering |
| First quarterly literature review | Q1 2027 | Clinical Affairs |
| First PMCF Evaluation Report | Q2 2027 | Clinical Affairs |
| PMCF study interim analysis (N=100) | Q4 2027 | Clinical Affairs |
| PMCF study final analysis (N=200) | Q4 2028 | Clinical Affairs |
| First CER update incorporating PMCF data | Q2 2027 | Clinical Affairs |

## 8. Roles and Responsibilities

| Role | Responsibility |
|---|---|
| Clinical Affairs Manager | PMCF Plan execution, study oversight, CER updates |
| Quality Manager | Complaint monitoring, vigilance reporting, survey deployment |
| Engineering Lead | Performance registry implementation, drift monitoring |
| Medical Advisor | Literature review, clinical significance assessment |
| Data Protection Officer | GDPR compliance for all PMCF data collection |

## 9. References

1. EU MDR 2017/745, Annex XIV Part B — Post-Market Clinical Follow-Up.
2. MDCG 2020-7. Post-market clinical follow-up (PMCF) Plan Template. April 2020.
3. MDCG 2020-8. Post-market clinical follow-up (PMCF) Evaluation Report Template. April 2020.
4. CEP-001 Clinical Evaluation Plan, MSTool-AI.
5. CER-001 Clinical Evaluation Report, MSTool-AI.
