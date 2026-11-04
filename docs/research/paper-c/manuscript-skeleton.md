# A per-patient guarantee on false "new lesion" calls in longitudinal MS MRI — manuscript skeleton (pilot)

> **Superseded 2026-10-31 by `manuscript/manuscript.md` (v0.2).** Kept for the record.

*Research draft, not the medical device. Skeleton written 2026-10-21 from the pilot; numbers are
from `RESULTS.md` (record `docs/research/records/2026-10-21_paper_c_pilot.json`). The confirmatory
study is planned on MSSEG-2 (access pending); this pilot is the methods and feasibility part.*

**Working title.** "Guaranteeing how often an automated follow-up report invents disease activity:
conformal control of false new-lesion calls in multiple sclerosis."

**Target.** MELBA or a MICCAI-2027 workshop (UNSURE / BrainLes) for the pilot + MSSEG-2 study;
clinical companion note later.

## Abstract (structure)

- *Background.* MAGNIMS-CMSC-NAIMS 2021: one new or enlarging T2 lesion = MRI activity. Automated
  tools call false new lesions in 14–36 % of stable MSSEG-2 patients (Valencia 2022) versus 0–11 %
  for experts; no tool states a bound on that rate.
- *Method.* Patient-level split-conformal threshold on the largest false-candidate score
  (equivalently conformal risk control with the loss "≥ 1 false call"), plus its Neyman–Pearson
  (PAC) version; the transfer assumption to stable patients made explicit.
- *Pilot data.* open_ms longitudinal (20 patients, expert change masks, model-free subtraction
  detector); MSLesSeg (25 patients, approximate truth, the app's rule on FLAMeS).
- *Results (pilot).* No stable patients were available. Realised per-patient false-call rates
  matched the targets (open_ms 0.10 [0.01, 0.32] and 0.20 [0.06, 0.44]; MSLesSeg 0.08
  [0.01, 0.26] and 0.20 [0.07, 0.41] at α = 0.1 / 0.2), but at α = 0.2 only 0/20 and 5/25
  patients were flagged by a true change (lesion sensitivity ≤ 0.07). With a deployed rule (the
  MSTool-AI `activity_candidate` on FLAMeS 5-fold masks) and expert change masks (open_ms, n = 20)
  the same threshold kept the rate at 0.10 [0.01, 0.32] / 0.20 [0.06, 0.44] while all 20 patients
  remained flagged by a true change and 28 % [18, 38] of expert lesions were kept; the rule itself
  produced ≥ 1 false new/enlarging candidate in 20/20 (expert truth, 8.9 per patient) and 25/25
  (approximate truth, 8.2 per patient) patients.
- *Conclusion.* The distribution-free bound is attainable and cheap. Whether it is useful depends
  on the change score and on acquisition consistency: informative with the segmenter-based rule on
  consistent co-registered follow-ups, bought by abstention with a model-free score or across
  scanner changes. Stable patients (MSSEG-2) are required to test the clinical claim.

## 1. Introduction

1. Clinical stake: a false "active" call changes treatment (escalation, NEDA status, trial
   endpoints). Patient-level, not voxel- or lesion-level, error is what the clinician acts on.
2. Prior measurement without guarantees: McKinley 2020 (stable time points called progressive),
   Homssi 2023 (SDC, voxel-wise Neyman–Pearson, subject specificity 0.67), MSSEG-2 papers
   (Valencia 2022, Andresen 2022, Masson 2026), commercial validations (Peters 2025, Hindsholm
   2025/26).
3. Distribution-free tools exist (conformal prediction, conformal risk control, Learn-then-Test,
   Neyman–Pearson umbrella; Conformal Triage 2024 for patient-level PPV/NPV) but none has been
   used to bound false activity calls in MS follow-up. Contribution = estimand + honest evaluation
   + comparison with a deployed rule; the statistics are not new.

## 2. Methods

2.1 Estimand: per-patient family-wise error of new/enlarging calls; equals false activity in a
stable patient. 2.2 Procedures CF-M, CF-PAC, baselines (PROTOCOL §4). 2.3 Transfer assumption
A-dom and the subgroup-validity caveat (arXiv 2605.20956). 2.4 Detectors: model-free subtraction
(D-sub) and the app's rule on FLAMeS (D-seg), scores S_sub / S_dp. 2.5 Data and truth (expert
change vs approximate). 2.6 Leave-one-patient-out evaluation, exact intervals, success criteria
(pre-registered, PROTOCOL commit 6233b4b).

## 3. Results (to fill from RESULTS.md)

- Table 1: cohorts, candidates per patient, candidate AUROC.
- Table 2 (primary): realised per-patient false-call rate, CF-M at α = 0.1 / 0.2, A1 and A2, with
  Clopper–Pearson intervals; true-detection rate; lesion sensitivity; abstentions.
- Table 3: baselines — every candidate (= the app's rule for D-seg), app rule + subtraction
  confirmation, fixed 0.5 SD, plug-in quantile.
- Table 4: the deployed rule against expert change masks (A4, RESULTS §2b) — likely the paper's
  central clinical table; Figure 2: largest false score per patient, open_ms vs MSLesSeg (the two
  outlier patients that set the MSLesSeg threshold).
- Figure 1: per-patient largest false score vs truth burden (Q4).
- Sensitivity analyses: thresholds, truth definitions, all MSLesSeg pairs, transport.

## 4. Discussion (points to make)

- What the guarantee buys and costs at this detector quality.
- Why the stable-patient rate could not be measured on public data and what MSSEG-2 adds
  (28 stable patients; stable-conditional calibration becomes possible).
- Calibration must match segmenter, acquisition and registration (paper A: guarantees break when
  the segmenter changes or slices thicken).
- Product implication: an "activity" flag should come with a stated false-activity bound or
  abstain (APP-FEATURE.md).

## 5. Limitations (pilot)

See RESULTS.md §6; at minimum: no stable patients; small n (intervals ±0.15–0.2); approximate truth
in MSLesSeg; supplied co-registration (the app's registration not exercised); 2D 3-mm FLAIR in
open_ms; possible identity overlap of open_ms longitudinal patients with FLAMeS's cross-sectional
Ljubljana training scans; the informative arm (A4) is a pre-registered secondary arm on 20 highly
active patients, so the primary NO-GO stands until MSSEG-2.

## 6. Data and code availability

Public data only (open_ms_data CC-BY; MSLesSeg CC-BY-4.0). Code `research/paper_c/`, records in
`docs/research/records/2026-10-21_paper_c_*`.
