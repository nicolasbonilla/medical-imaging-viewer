# How often does an automated follow-up report invent disease activity? A distribution-free, per-patient bound on false new-lesion calls in multiple sclerosis MRI

*Manuscript skeleton v0.2, 2026-10-31 (branch `research/paper-c-pilot`). Research, not the medical
device. Pilot numbers are copied from `../RESULTS.md` and the records in `docs/research/records/`
(`2026-10-21_paper_c_pilot.json`, `2026-10-31_paper_c_stage0_score_v2.json`,
`2026-10-31_paper_c_power_msseg2.json`). Everything that depends on MSSEG-2 is marked **TODO** and
will be filled only by the analysis pre-registered in `../PREREGISTRATION_C.md`. Supersedes
`../manuscript-skeleton.md` (v0.1).*

**Authors.** Nicolás G. Bonilla Vargas¹ [+ co-authors TBD]
¹ MSTool-AI.
**Target.** Medical Image Analysis / MELBA (full paper; pre-registered confirmatory study); short
version for a MICCAI 2027 workshop (UNSURE). Reporting follows TRIPOD+AI where applicable (Collins et
al. 2024).

---

## Abstract

**Background.** Since 2021, one new or enlarging T2 lesion on follow-up MRI counts as disease
activity in multiple sclerosis (MS). Automated tools now propose new lesions between two scans, but
none states how often it calls activity in a patient who has none. In the MSSEG-2 challenge, expert
raters produced a false new lesion in 0–11 % of stable patients and the best automated methods in
11–36 %.

**Methods.** We bound the per-patient probability of at least one false new-lesion call with a
split-conformal threshold on a change score, calibrated on the largest score of patients without new
lesions (finite-sample, distribution-free; equivalent to conformal risk control with the loss
"≥ 1 false call"), and compare it with the rule of a deployed research software. A pre-registered
pilot used two public datasets without stable patients (open_ms longitudinal, 20 patients with expert
change masks; MSLesSeg, 25 patients with approximate change truth). The confirmatory study on
MSSEG-2 (pre-registered before data access; 40 patients of which about 11 stable, or 100 if the test
set is granted) uses the deployed rule on an open segmenter (FLAMeS 5-fold) and its FLAIR-subtraction
score.

**Results (pilot).** The realised per-patient false-call rate matched the target in all four primary
cells (0.10 [0.01, 0.32] and 0.20 [0.06, 0.44] on open_ms; 0.08 [0.01, 0.26] and 0.20 [0.07, 0.41] on
MSLesSeg at α = 0.1 / 0.2) but was bought by abstention: at α = 0.2 only 0/20 and 5/25 patients were
flagged by a true change. With the deployed rule on FLAMeS and expert change masks (pre-registered
secondary arm), the same procedure kept the rate at 0.10 [0.01, 0.32] while 20/20 patients remained
flagged by a true change and 28 % [18, 38] of expert-marked lesions were kept; the deployed rule itself
proposed at least one false new or enlarging lesion in 20/20 patients (8.9 per patient). **(MSSEG-2:
TODO.)**

**Conclusions.** A distribution-free per-patient bound on false activity calls is cheap to compute
and held in every pilot cell; whether it is informative depends on the change score and on
acquisition consistency. **(Confirmatory conclusion: TODO.)**

---

## 1. Introduction

1. **The clinical decision is per patient.** MAGNIMS–CMSC–NAIMS 2021 recommends treating one new or
   enlarging T2 lesion as MRI activity (Wattjes et al. 2021); new T2 lesions are a validated
   surrogate of relapses at trial level (Sormani & Bruzzi 2013) and part of "no evident disease
   activity" (NEDA-3; Giovannoni et al. 2015). A clinician acts on whether a patient is active, not on
   voxel or lesion counts. Human reads of activity are themselves variable: in 85 patients of an MS
   clinic, clinician raters classified MRI activity differently from a neuroradiologist or a
   computer program in 18–25 % of cases (Erbayat Altay et al. 2013), and subtraction images detected
   1.7 times more active lesions than side-by-side reading in a multicentre trial (Moraal et al. 2009).
2. **Automated tools are measured, not bounded.** Systems detect new lesions with deep learning
   (McKinley et al. 2020; MSSEG-2 methods: Andresen et al. 2022, Basaran et al. 2022, Schmidt-Mengin
   et al. 2022, Valencia et al. 2022) or statistical change detection (Homssi et al. 2023). Their
   false activity in stable patients is reported after the fact: in MSSEG-2, 0–11 % of 28 stable
   test patients received at least one false new lesion from the four experts and 11–36 % from the
   leading systems (Valencia et al. 2022, Table 3); Masson et al. (2026) report the revised test set.
   Clinical validations of commercial tools report patient-level specificity or positive predictive
   value without a guarantee (Barnett et al. 2023; Peters et al. 2025; Hindsholm et al. 2026). The
   statistical change-detection approach controls a voxel-wise false-positive rate, not the
   patient-level one (Homssi et al. 2023).
3. **Distribution-free tools exist.** Split-conformal prediction (Vovk et al. 2005; Lei et al. 2018;
   Angelopoulos & Bates 2023), risk-controlling prediction sets and conformal risk control (Bates et
   al. 2021; Angelopoulos et al. 2024), Learn-then-Test (Angelopoulos et al. 2025) and Neyman–Pearson
   order statistics (Tong et al. 2018) give finite-sample guarantees on user-chosen error rates. In
   medical imaging they have bounded triage error (Angelopoulos et al. 2024, Conformal Triage),
   lesion-level miss rates in lung CT (Hulsman et al. 2025), voxel-level errors (Tan et al. 2025;
   Davenport 2024) and detection precision (Blot et al. 2025). We found no application that bounds the
   per-patient false activity call in MS follow-up (novelty check, `../NOVELTY-CHECK.md`).
4. **Contribution.** (i) A clinically framed estimand — the probability that a follow-up report
   contains at least one false new-lesion call — and the matching conformal procedure, with its
   transfer assumption made explicit; (ii) an honest pilot showing validity everywhere and utility
   only under some conditions; (iii) the comparison with the rule of a deployed software, on expert
   change masks; (iv) a pre-registered confirmatory test on stable patients (MSSEG-2). The statistics
   are not new; the formulation and the evidence are.

## 2. Related work (short; full list in `../NOVELTY-CHECK.md`)

- *Stable/active decisions without guarantees:* McKinley et al. 2020 (stable time points called
  progressive); Homssi et al. 2023 (subject-level specificity 0.67 [0.59, 0.74] in 200 patients with a
  voxel-wise Neyman–Pearson argument).
- *MSSEG-2:* challenge proceedings (Commowick et al. 2021), dataset and results paper (Masson et al.
  2026), method papers reporting stable-patient false positives (Valencia et al. 2022; Andresen et al.
  2022; Schmidt-Mengin et al. 2022; Basaran et al. 2022).
- *Conformal guarantees in imaging:* Conformal Triage (Angelopoulos et al. 2024) and its audit under
  prevalence shift (Li et al. 2026: pooled validity need not hold in a low-prevalence subgroup — the
  reason our primary procedure calibrates on stable patients only); Hulsman et al. 2025; Tan et al.
  2025; Davenport 2024; Blot et al. 2025.
- *Shift:* conformal guarantees require exchangeability; under covariate or other shift they
  degrade (Tibshirani et al. 2019; Barber et al. 2023) — relevant to scanner changes between visits.

## 3. Methods

### 3.1 Estimand

For a patient i with candidate new lesions c = 1…m_i, scores s_ic and truth labels (true/false), let
M_i = max over false candidates of s_ic (−∞ if none). Calling every candidate with score > λ produces
at least one false call in patient i iff M_i > λ. The per-patient family-wise error
FWER(λ) = P(M > λ) is the probability that a follow-up report contains at least one false new-lesion
call. **In a stable patient every candidate is false, so the event is exactly a false activity
call** — the clinically relevant quantity.

### 3.2 Procedures

- **Stable-conditional CF-M (primary on MSSEG-2).** Calibrate on n stable patients:
  λ̂ = k-th smallest M, k = ⌈(n + 1)(1 − α)⌉, λ̂ = +∞ (abstain) if k > n. For a new stable patient
  exchangeable with the calibration patients, P(M_new > λ̂) ≤ α (Vovk et al. 2005; Lei et al. 2018),
  without assumptions on the score distribution.
- **Pooled CF-M (primary in the pilot, which had no stable patients).** Calibrate on the largest
  *false* score of all patients. It bounds the per-patient FWER over the calibration population; it
  bounds false activity in stable patients only under assumption **A-dom**: a stable patient's
  largest score is stochastically no larger than an active patient's largest false score (§3.3).
- **CF-PAC.** k = smallest k with P(Bin(n, 1 − α) ≥ k) ≤ δ (Neyman–Pearson umbrella order statistic,
  Tong et al. 2018; calibration-conditional validity, Vovk 2013); δ = 0.1.
- **Baselines.** Every candidate (= the deployed rule), the deployed rule with its subtraction
  confirmation (new candidates ≥ 0.5 SD), a fixed bar of 0.5 SD on all candidates, and the
  plug-in empirical quantile k = ⌈n(1 − α)⌉ (no finite-sample correction).

### 3.3 Transfer and subgroup validity

Pooled calibration on active patients transfers to stable patients only under A-dom. It is plausible
(more disease, more perilesional change and registration-sensitive tissue) but can fail, e.g. when
stable patients are scanned differently. A recent audit of Conformal Triage shows that marginal
validity over a population does not bound the risk in a low-prevalence subgroup (Li et al. 2026). The
pilot could only probe A-dom indirectly (Spearman ρ between M and disease burden); the confirmatory
study therefore calibrates on stable patients directly.

### 3.4 Candidate generators and scores — from the pilot design to the confirmatory design

All scores use the deployed software's own functions, imported read-only: each FLAIR is z-scored
within the brain domain, d = z_follow-up − z_baseline, interior = domain eroded by one voxel.

| | Pilot (pre-registered 2026-10-21) | Confirmatory, MSSEG-2 (pre-registered 2026-10-31) | Evidence for the change |
|---|---|---|---|
| Candidate generator | D-sub (model-free subtraction: d ≥ 1.5 SD, z_follow-up ≥ 1.0) and D-seg (deployed rule on FLAMeS) | **D-seg only**: `compare_timepoints` on FLAMeS 5-fold mean ≥ 0.5 | candidate AUROC 0.40 [0.34, 0.46] (D-sub) vs 0.84 [0.75, 0.90] (D-seg), same patients, expert truth (arms A1, A4) |
| Candidate type | new ≥ 14.14 mm³ and enlarged (> 20 %) | **new ≥ 14.14 mm³ only** | in A4, 72/108 "enlarged" candidates were false vs 106/282 "new"; MSSEG-2 annotates new lesions only |
| Score | S_sub (mean d over the change region); S_dp secondary | **S_sub** (the deployed `subtraction_signal`); S_dp and a frozen learned score S_v2 secondary | Stage 0 (§4.5): S_v2 did not beat S_sub on pilot data |
| Calibration | pooled CF-M (no stable patients available) | **stable-conditional CF-M**; pooled secondary | removes the dependence on A-dom (§3.3) |
| Acquisition | 2D 3-mm FLAIR (open_ms); MNI-resampled, 18/40 pairs changing scanner string (MSLesSeg) | 3D FLAIR pairs co-registered by the organisers | the two MSLesSeg patients with false candidates at 4.9 and 5.3 SD set the whole operating point (post hoc) |

The **power problem of the pilot** — guaranteed but nearly blind (0/20 and 5/25 patients flagged by a
true change at α = 0.2) — came from the candidate generator and the heavy tail of the largest false
score, not from the conformal step: with segmenter-based candidates and consistent acquisitions
(arm A4) the same step flagged 20/20 patients by a true change at α = 0.1.

### 3.5 Data

- **open_ms longitudinal** (Lesjak et al. 2016; CC-BY): 20 patients × 2 studies (81–723 days), 2D FLAIR
  (in-plane 0.57–0.90 mm, slices 3.0–3.3 mm), co-registered and N4-corrected by the providers, brain
  mask and an **expert lesion-change mask**. All 20 patients have expert-marked change (8–133
  components each).
- **MSLesSeg** (Guarnera et al. 2025; CC-BY-4.0): 25 patients with ≥ 2 time points (first pairs
  primary), MNI 1 mm as delivered, per-time-point expert masks (no change annotation); not in FLAMeS
  training (external test set of FLAMeS).
- **MSSEG-2** (Commowick et al. 2021; Masson et al. 2026): 100 patients, OFSEP registry, 15 scanners
  of 3 vendors, 3D FLAIR pairs (70–1,187 days) co-registered to a middle space; consensus of four
  neuroradiologists with senior adjudication; **new lesions only** (growth not annotated), lesions
  < 3 mm discarded. Distributed: the 40 training patients (≈ 11 without new lesions — inferred,
  confirmed at download). Test set (60; 25 without new lesions, revised ground truth): requested,
  not distributed by default. Access under the OFSEP data use agreement (research use, no commercial
  use of data or derivatives; `../MSSEG2_ACCESS_REQUEST.md`).
- **Segmenter:** FLAMeS (Dereskewicz et al. 2025; nnU-Net, Isensee et al. 2021), 5 folds, no
  test-time augmentation, weights CC BY-NC 4.0 (research use).

### 3.6 Truth

- open_ms: candidate true if it overlaps any expert change component (18-connected, ≥ 3 mm³);
  sensitivity on positive components ≥ 14.14 mm³ (sign from the subtraction).
- MSLesSeg (approximate): follow-up components ≥ 3 mm³ with no voxel within one voxel of the
  baseline mask are *new*; touching components ≥ 1.5 × the baseline volume and ≥ 14.14 mm³ larger are
  *enlarging*; a candidate is true if it overlaps the change region.
- MSSEG-2: candidate true if it overlaps the consensus new-lesion mask; stable = empty mask.

### 3.7 Evaluation (pilot)

Leave-one-patient-out within each arm (calibrate on the other patients, test on the held-out one).
Exact Clopper–Pearson 95 % intervals over patients; patient-cluster bootstrap (B = 2,000, seed
20261021) for lesion sensitivity and false calls per patient. Pre-registered success rules: a cell is
*violated* if the CP lower bound exceeds α; *informative* if ≥ 0.5 of patients are flagged by a true
change; *bought by abstention* if < 0.2. Go/no-go for the confirmatory study: go if no primary cell is
violated and one primary cell at α = 0.2 is informative.

### 3.8 Pre-registered confirmatory analysis on MSSEG-2

Full text: `../PREREGISTRATION_C.md` (to be time-stamped on OSF before data access).

- **Hypotheses.** H1 (validity check at α = 0.1 and 0.2): false-activity rate in stable patients
  ≤ α (violation if CP lower bound > α). H2 (primary test, α = 0.2): share of active patients flagged
  by ≥ 1 true new-lesion candidate > 0.25 (exact one-sided binomial). H3: the deployed rule calls a
  new lesion in > 20 % of stable patients. H4: the conformal procedure calls fewer false new lesions
  in stable patients than the deployed rule (exact McNemar). Holm over H2–H4 at 0.05.
- **Sample.** Fixed by the dataset: S1 = 40 training patients (≈ 11 stable / 29 active); S2 = 100
  patients (36 / 64) if the test set is granted. Scenario chosen by access, not by results.
- **Metrics.** Primary: false-activity rate in stable patients; share of active patients flagged by
  a true candidate. Secondary: lesion-level sensitivity, false calls per patient, abstention,
  per-patient FWER over all patients, AUROC, three-class patient accuracy (0 / 1–2 / ≥ 3 new
  lesions).
- **α.** Targets α ∈ {0.1, 0.2}; the hypothesis test uses α = 0.2 because the pilot-based simulation
  shows α = 0.1 is under-powered under heavy-tailed false scores.
- **Power (from the pilot, simulation; record `2026-10-31_paper_c_power_msseg2.json`).** Primary
  procedure, α = 0.2, power of H2 after Holm: 0.995 (S1) if MSSEG-2 behaves like the consistent pilot
  arm, 0.62 with pessimistic detection, 0.80 with a mixed tail, 0.49 with the heavy MSLesSeg tail; in
  S2: 1.00, 0.90, 0.99, 0.81. Expected share of active patients flagged by a true change in S1:
  0.64 (consistent) to 0.32 (heavy tail). H3 power 0.75–0.97 (S1) if the deployed rule's true
  false-activity rate is 0.6–0.75; H4 ≥ 0.96. If A-dom fails, pooled calibration would give a
  false-activity rate of 0.26–0.33 in stable patients (2.5 × α at α = 0.1), detected by the S1
  falsification check in only 9–32 % of simulated studies — the reason the primary procedure is
  stable-conditional.

### 3.9 Software, reproducibility, data use

Code `research/paper_c/` (pilot, Stage 0, power, and the MSSEG-2 loader written before access);
unit tests include validity simulations of the thresholds. Records with input SHA-256s in
`docs/research/records/`. MSSEG-2 results are committed and published at group level only (OFSEP
DUA clause 4); no threshold or model derived from MSSEG-2 is used in any product (clause 8).

## 4. Results

### 4.1 Pilot cohorts and candidates

**Table 1.** Candidates and their separability (pilot; RESULTS §1).

| Arm | Data | Detector / score | Candidates (true) | Per patient, median | Patients with ≥ 1 false candidate | Candidate AUROC [95 %] |
|---|---|---|---|---|---|---|
| A1 | open_ms, 20, expert change | D-sub / S_sub | 476 (185) | 23 | 19/20 | 0.40 [0.34, 0.46] |
| A2 | MSLesSeg first pairs, 25, approximate | deployed rule on FLAMeS / S_sub | 327 (119) | 11 | 25/25 | 0.70 [0.63, 0.78] |
| A2b | same | same / S_dp | 327 (119) | 11 | 25/25 | 0.72 [0.63, 0.80] |
| A3 | same | D-sub / S_sub | 1,264 (56) | 31 | 24/25 | 0.55 [0.40, 0.69] |
| A4 | open_ms, 20, expert change | deployed rule on FLAMeS / S_sub | 390 (212) | 14 | 20/20 | 0.84 [0.75, 0.90] |
| A4b | same | same / S_dp | 390 (212) | 14 | 20/20 | 0.76 [0.67, 0.82] |

No stable patient was available: all 20 open_ms patients have expert-marked change; all 25 MSLesSeg
first pairs are active under the approximate truth.

### 4.2 Pilot primary cells (pooled CF-M, leave-one-patient-out)

**Table 2.**

| Arm | α | Per-patient false-call rate [CP 95 %] | Verdict | Flagged by a true change | Lesion sensitivity | False calls / patient |
|---|---|---|---|---|---|---|
| A1 | 0.1 | 0.10 (2/20) [0.01, 0.32] | no violation detected | 0/20 | 0.000 | 0.20 |
| A1 | 0.2 | 0.20 (4/20) [0.06, 0.44] | no violation detected | 0/20 | 0.000 | 0.30 |
| A2 | 0.1 | 0.08 (2/25) [0.01, 0.26] | no violation detected | 1/25 | 0.004 [0.000, 0.012] | 0.16 |
| A2 | 0.2 | 0.20 (5/25) [0.07, 0.41] | no violation detected | 5/25 | 0.070 [0.012, 0.136] | 0.36 |

Pre-registered verdict: **no-go** (validity held; no primary cell informative).

### 4.3 The deployed rule against expert change masks (arm A4, pre-registered secondary)

**Table 3.** open_ms, 20 patients, FLAMeS 5-fold, deployed rule; gate G1 (reconstruction reproduces the
software's counts) passed for 20/20.

| Procedure | Per-patient false-call rate | Flagged by a true change | Lesion sensitivity | False calls / patient |
|---|---|---|---|---|
| Deployed rule, every candidate | 1.00 (20/20) [0.83, 1.00] | 20/20 | 0.52 [0.40, 0.61] | 8.90 [5.8, 12.6] |
| Deployed rule + subtraction confirmation | 0.95 (19/20) [0.75, 1.00] | 20/20 | 0.49 [0.38, 0.59] | 5.40 [3.5, 7.7] |
| Fixed bar S_sub > 0.5 SD | 0.85 (17/20) [0.62, 0.97] | 20/20 | 0.46 [0.34, 0.56] | 3.15 |
| **CF-M, α = 0.1** | **0.10 (2/20) [0.01, 0.32]** | **20/20 [0.83, 1.00]** | **0.28 [0.18, 0.38]** | 0.15 [0.0, 0.4] |
| CF-M, α = 0.2 | 0.20 (4/20) [0.06, 0.44] | 20/20 | 0.31 [0.19, 0.41] | 0.25 |
| CF-PAC, α = 0.2 | 0.10 (2/20) [0.01, 0.32] | 20/20 | 0.28 | 0.15 |

Median conformal threshold ≈ 1.1 SD on the deployed subtraction score (the software's own
confirmation bar is 0.5 SD). On MSLesSeg (approximate truth) the deployed rule likewise had ≥ 1 false
new or enlarging candidate in 25/25 patients (8.2 per patient [6.3, 10.4]).

### 4.4 Pilot secondary analyses

- Transfer proxy (Q4): ρ(M, number of truth change components) = 0.04 (p 0.87, A1), −0.03 (0.88, A2),
  0.15 (0.53, A4) — no evidence for or against A-dom.
- Transport (D-sub, exploratory): calibrated on open_ms and applied to MSLesSeg, 0.20 (5/25)
  [0.07, 0.41] at α = 0.1 — twice nominal, not a detected violation at this n.
- Sensitivity analyses (truth definitions, thresholds 1.0 / 2.0 SD, all 40 MSLesSeg pairs): no
  violated cell.
- Post hoc: two MSLesSeg patients with false candidates at 4.9 and 5.3 SD set the operating point at
  α = 0.1 (median patient 0.89 SD); scanner change and resampling plausible, not shown.

### 4.5 Stage 0 — development before MSSEG-2 (pilot data only; new-lesion candidates)

Record `2026-10-31_paper_c_stage0_score_v2.json`. On A4 new-lesion candidates (282; 176 true):
cross-fitted AUROC S_sub 0.845 [0.733, 0.917], S_dp 0.777, learned S_v2 0.846 [0.743, 0.907];
leave-one-patient-out CF-M at α = 0.1 / 0.2 — S_sub: 2/20 and 4/20 false-call patients, 18/20 and
18/20 flagged by a true change (lesion sensitivity 0.23 / 0.25); S_v2 (nested cross-fitting): 2/20
and 3/20, 15/20 and 18/20 (0.13 / 0.17). Fitted on A4 and transported to MSLesSeg, S_v2 did worse
than S_sub (AUROC 0.68 vs 0.75). S_sub is kept as the primary score.

### 4.6 Confirmatory study on MSSEG-2 — **TODO** (filled only by the pre-registered analysis)

- 4.6.1 Inventory: patients, stable / active, truth lesions per patient — **TODO**.
- 4.6.2 Gate G1 and candidates (Table 4: candidates per patient, AUROC) — **TODO**.
- 4.6.3 H1: false-activity rate in stable patients, stable-conditional CF-M, α = 0.1 / 0.2 — **TODO**.
- 4.6.4 H2: active patients flagged by a true new lesion, α = 0.2 (and 0.1) — **TODO**.
- 4.6.5 H3, H4: deployed rule vs conformal procedure in stable patients (Table 5) — **TODO**.
- 4.6.6 Secondary: pooled CF-M, CF-PAC, S_dp, S_v2, lesion sensitivity, three-class accuracy —
  **TODO**.
- 4.6.7 Exploratory: A-dom check, transport of the pilot threshold, enlarged candidates in stable
  patients, experts' case-wise results (S2 only) — **TODO**.

## 5. Discussion (points to develop after the confirmatory results)

1. *What the bound buys.* A stated, finite-sample bound on false activity per patient, at the cost of
   missed lesions (the threshold raises misses; the bound says nothing about them). **TODO: size of
   the cost on MSSEG-2.**
2. *Validity was never the problem; utility was.* The pilot's model-free score was blind; the
   segmenter-based candidates made the same conformal step informative on consistent acquisitions.
3. *Acquisition consistency decides the operating point.* A few patients with large false scores
   (plausibly scanner or protocol changes) set the threshold for everyone; deployment needs either
   matched calibration or abstention when the acquisition changes (the deployed software already
   abstains when the two visits' acquisitions differ).
4. *Calibrate on stable patients.* Pooled calibration relies on an untestable-in-practice assumption;
   subgroup validity fails under prevalence shift (Li et al. 2026).
5. *The deployed rule over-calls.* Against expert change masks the rule proposed about nine false new
   or enlarging candidates per patient, in every patient; presenting such candidates as "activity"
   would be unsafe (the software has since changed how they are presented). **TODO: the rate in
   stable patients.**
6. *Comparison with experts* (S2 only). **TODO.**

## 6. Limitations

1. Pilot: no stable patients; n = 20 and 25; intervals ±0.15–0.2; approximate truth in MSLesSeg;
   2D 3-mm FLAIR in open_ms; the informative arm (A4) is a pre-registered secondary arm, so the
   pre-registered pilot verdict is no-go.
2. MSSEG-2 training set: about 11 stable patients — H1 can only exclude gross violations; S2 requires
   the test set.
3. MSSEG-2 annotates new lesions only; the bound covers false *new*-lesion calls, not enlarging ones.
4. The software's own rigid registration is not exercised (providers' co-registration).
5. One segmenter (FLAMeS) and one rule; FLAMeS ran on 2D FLAIR in open_ms, outside most of its
   training data; possible identity overlap of open_ms longitudinal patients with FLAMeS's
   cross-sectional Ljubljana training scans (unknowable).
6. Expert change masks are themselves imperfect; a "false" candidate may be a real change.
7. Conflict of interest: the author develops the software whose rule is evaluated (Declarations).

## 7. Conclusion — **TODO** (after the confirmatory results)

---

## Declarations

- **Ethics.** Only public, de-identified datasets distributed under their own ethics approvals and
  licences (open_ms CC-BY; MSLesSeg CC-BY-4.0; MSSEG-2 under the OFSEP data use agreement — "All
  subjects gave written informed consent for their data to be used for research", Masson et al.
  2026). No new data were collected.
- **Methods text required by OFSEP (MSSEG-2).** "Data were generated by participating neurologists in
  the framework of Observatoire Français de la Sclérose en Plaques (OFSEP), the French MS registry
  (Vukusic et al. 2020). They collect clinical data prospectively in the European Database for
  Multiple Sclerosis (EDMUS) software (Confavreux et al. 1992). MRI of patients were provided as part
  of a care protocol. Nominative data are deleted from MRI before transfer and storage on the Shanoir
  platform (Sharing NeurOImaging Resources, shanoir.org)."
- **Acknowledgements.** "This work was carried out in collaboration with The Observatoire Français de
  la Sclérose en Plaques (OFSEP), who is supported by a grant provided by the French State and handled
  by the "Agence Nationale de la Recherche," within the framework of the "Investments for the Future"
  program, under the reference ANR-10-COHO-002, by the Eugène Devic EDMUS Foundation against multiple
  sclerosis and by the ARSEP Foundation." We thank the providers of open_ms_data, MSLesSeg and FLAMeS.
- **Competing interests.** N.G.B.V. develops MSTool-AI, software intended to become a commercial
  medical device; the longitudinal rule evaluated here is that software's rule. No data or result
  derived from MSSEG-2 is used in the software.
- **Pre-registration.** Pilot protocol: repository commit `6233b4b` (2026-10-21). Confirmatory study:
  OSF **TODO (DOI / time stamp)**, text identical to `PREREGISTRATION_C.md` at commit **TODO**.
- **Data availability.** open_ms_data and MSLesSeg are public. MSSEG-2 is available from Shanoir under
  the OFSEP agreement. Only group-level MSSEG-2 results are shared.
- **Code availability.** `research/paper_c/` (licence to be stated at submission).
- **Funding.** None. **TODO** confirm.

## References (each verified on 2026-10-31 against Crossref/OpenAlex, Europe PMC, arXiv or HAL)

1. Andresen J, Uzunova H, Ehrhardt J, Kepp T, Handels H. Image registration and appearance adaptation in non-correspondent image regions for new MS lesions detection. *Front Neurosci* 2022;16:981523. doi:10.3389/fnins.2022.981523
2. Angelopoulos AN, Bates S. Conformal prediction: a gentle introduction. *Found Trends Mach Learn* 2023;16(4):494–591. doi:10.1561/2200000101
3. Angelopoulos AN, Bates S, Fisch A, Lei L, Schuster T. Conformal risk control. ICLR 2024. arXiv:2208.02814
4. Angelopoulos AN, Bates S, Candès EJ, Jordan MI, Lei L. Learn then test: calibrating predictive algorithms to achieve risk control. *Ann Appl Stat* 2025;19(2):1641–1662. doi:10.1214/24-AOAS1998
5. Angelopoulos AN, et al. Conformal triage for medical imaging AI deployment. *medRxiv* 2024. doi:10.1101/2024.02.09.24302543
6. Barber RF, Candès EJ, Ramdas A, Tibshirani RJ. Conformal prediction beyond exchangeability. *Ann Stat* 2023;51(2):816–845. doi:10.1214/23-AOS2276
7. Barnett M, Wang D, Beadnall H, et al. A real-world clinical validation for AI-based MRI monitoring in multiple sclerosis. *NPJ Digit Med* 2023;6:196. doi:10.1038/s41746-023-00940-6
8. Basaran BD, Matthews PM, Bai W. New lesion segmentation for multiple sclerosis brain images with imaging and lesion-aware augmentation. *Front Neurosci* 2022;16:1007453. doi:10.3389/fnins.2022.1007453
9. Bates S, Angelopoulos A, Lei L, Malik J, Jordan M. Distribution-free, risk-controlling prediction sets. *J ACM* 2021;68(6):43. doi:10.1145/3478535
10. Blot V, Lorenzo de Brionne A, Sellami I, et al. Efficient precision control in object detection models for enhanced and reliable ovarian follicle counting. arXiv:2501.14036 (2025)
11. Clopper CJ, Pearson ES. The use of confidence or fiducial limits illustrated in the case of the binomial. *Biometrika* 1934;26(4):404–413. doi:10.1093/biomet/26.4.404
12. Collins GS, Moons KGM, Dhiman P, et al. TRIPOD+AI statement. *BMJ* 2024;385:e078378. doi:10.1136/bmj-2023-078378
13. Commowick O, Cervenansky F, Cotton F, Dojat M. MSSEG-2 challenge proceedings: multiple sclerosis new lesions segmentation challenge using a data management and processing infrastructure. MICCAI 2021. HAL hal-03358968
14. Confavreux C, Compston DAS, Hommes OR, McDonald WI, Thompson AJ. EDMUS, a European database for multiple sclerosis. *J Neurol Neurosurg Psychiatry* 1992;55(8):671–676. doi:10.1136/jnnp.55.8.671
15. Davenport S. Conformal confidence sets for biomedical image segmentation. arXiv:2410.03406 (2024)
16. Dereskewicz E, et al. A novel convolutional neural network for automated multiple sclerosis brain lesion segmentation (FLAMeS). *J Neuroimaging* 2025;35(5):e70085. doi:10.1111/jon.70085
17. Erbayat Altay E, Fisher E, Jones SE, Hara-Cleaver C, Lee JC, Rudick RA. Reliability of classifying multiple sclerosis disease activity using magnetic resonance imaging in a multiple sclerosis clinic. *JAMA Neurol* 2013;70(3):338–344. doi:10.1001/2013.jamaneurol.211
18. Giovannoni G, Turner B, Gnanapavan S, Offiah C, Schmierer K, Marta M. Is it time to target no evident disease activity (NEDA) in multiple sclerosis? *Mult Scler Relat Disord* 2015;4(4):329–333. doi:10.1016/j.msard.2015.04.006
19. Guarnera F, Rondinella A, Crispino E, et al. MSLesSeg: baseline and benchmarking of a new multiple sclerosis lesion segmentation dataset. *Sci Data* 2025;12:920. doi:10.1038/s41597-025-05250-y
20. Hindsholm AM, Langkilde AR, Frederiksen JL, et al. Longitudinal deep learning-based segmentation of multiple sclerosis lesions in a local clinical cohort. *Front Radiol* 2026;6:1758276. doi:10.3389/fradi.2026.1758276
21. Holm S. A simple sequentially rejective multiple test procedure. *Scand J Stat* 1979;6:65–70. doi:10.2307/4615733
22. Homssi M, Sweeney EM, Demmon E, et al. Evaluation of the statistical detection of change algorithm for screening patients with MS with new lesion activity on longitudinal brain MRI. *AJNR Am J Neuroradiol* 2023;44(6):649–655. doi:10.3174/ajnr.A7858
23. Hulsman R, Comte V, Bertolini L, et al. Conformal risk control for pulmonary nodule detection. *PMLR* 2025;266:445–463 (COPA 2025). arXiv:2412.20167
24. Isensee F, Jaeger PF, Kohl SAA, Petersen J, Maier-Hein KH. nnU-Net: a self-configuring method for deep learning-based biomedical image segmentation. *Nat Methods* 2021;18(2):203–211. doi:10.1038/s41592-020-01008-z
25. Lei J, G'Sell M, Rinaldo A, Tibshirani RJ, Wasserman L. Distribution-free predictive inference for regression. *J Am Stat Assoc* 2018;113(523):1094–1111. doi:10.1080/01621459.2017.1307116
26. Lesjak Ž, Pernuš F, Likar B, Špiclin Ž. Validation of white-matter lesion change detection methods on a novel publicly available MRI image database. *Neuroinformatics* 2016;14(4):403–420. doi:10.1007/s12021-016-9301-1
27. Li C, Liu X, Zhang H, et al. A deployment audit of release-side risk in conformal triage under prevalence shift. arXiv:2605.20956 (2026)
28. Masson A, Combès B, Kerbrat A, et al. Performances of experts and automated methods on new multiple sclerosis lesions detection: insights from the MSSeg2 challenge. *Sci Rep* 2026;16. doi:10.1038/s41598-026-52150-1
29. McKinley R, Wepfer R, Grunder L, et al. Automatic detection of lesion load change in multiple sclerosis using convolutional neural networks with segmentation confidence. *NeuroImage Clin* 2020;25:102104. doi:10.1016/j.nicl.2019.102104
30. Moraal B, Meier D, Poppe PA, et al. Subtraction MR images in a multiple sclerosis multicenter clinical trial setting. *Radiology* 2009;250(2):506–514. doi:10.1148/radiol.2501080480
31. Montalban X, Lebrun-Frénay C, Oh J, et al. Diagnosis of multiple sclerosis: 2024 revisions of the McDonald criteria. *Lancet Neurol* 2025;24(10):850–865. doi:10.1016/S1474-4422(25)00270-4
32. Nosek BA, Ebersole CR, DeHaven AC, Mellor DT. The preregistration revolution. *Proc Natl Acad Sci USA* 2018;115(11):2600–2606. doi:10.1073/pnas.1708274114
33. Peters S, Schmill L, Gless CA, Stürner K, Jansen O, Seehafer S. AI-based assessment of longitudinal multiple sclerosis MRI: strengths and weaknesses in clinical practice. *Eur J Radiol* 2025;183:111941. doi:10.1016/j.ejrad.2025.111941
34. Schmidt-Mengin M, Soulier T, Hamzaoui M, et al. Online hard example mining vs. fixed oversampling strategy for segmentation of new multiple sclerosis lesions from longitudinal FLAIR MRI. *Front Neurosci* 2022;16:1004050. doi:10.3389/fnins.2022.1004050
35. Sormani MP, Bruzzi P. MRI lesions as a surrogate for relapses in multiple sclerosis: a meta-analysis of randomised trials. *Lancet Neurol* 2013;12(7):669–676. doi:10.1016/S1474-4422(13)70103-0
36. Tan B, Wang Z, Duan J, et al. Conformal lesion segmentation for 3D medical images. arXiv:2510.17897 (2025)
37. Thompson AJ, Banwell BL, Barkhof F, et al. Diagnosis of multiple sclerosis: 2017 revisions of the McDonald criteria. *Lancet Neurol* 2018;17(2):162–173. doi:10.1016/S1474-4422(17)30470-2
38. Tibshirani RJ, Barber RF, Candès EJ, Ramdas A. Conformal prediction under covariate shift. NeurIPS 2019. arXiv:1904.06019
39. Tong X, Feng Y, Li JJ. Neyman–Pearson classification algorithms and NP receiver operating characteristics. *Sci Adv* 2018;4(2):eaao1659. doi:10.1126/sciadv.aao1659
40. Valencia L, Clèrigues A, Valverde S, et al. Evaluating the use of synthetic T1-w images in new T2 lesion detection in multiple sclerosis. *Front Neurosci* 2022;16:954662. doi:10.3389/fnins.2022.954662
41. Vovk V. Conditional validity of inductive conformal predictors. *Mach Learn* 2013;92(2–3):349–376. doi:10.1007/s10994-013-5355-6
42. Vovk V, Gammerman A, Shafer G. *Algorithmic Learning in a Random World.* Springer; 2005. doi:10.1007/b106715
43. Vukusic S, Casey R, Rollot F, et al. Observatoire Français de la Sclérose en Plaques (OFSEP): a unique multimodal nationwide MS registry in France. *Mult Scler* 2020;26(1):118–122. doi:10.1177/1352458518815602
44. Wattjes MP, Ciccarelli O, Reich DS, et al. 2021 MAGNIMS–CMSC–NAIMS consensus recommendations on the use of MRI in patients with multiple sclerosis. *Lancet Neurol* 2021;20(8):653–670. doi:10.1016/S1474-4422(21)00095-8

*Verification notes.* Metadata (authors, year, title, journal, volume, pages) were matched against
the DOI record (author lists checked against OpenAlex on 2026-10-31); first-author spellings and pages as in the record. The MSLesSeg dataset paper's first
author is **Guarnera**, not Rondinella as written in earlier pilot notes. Erbayat Altay et al. was
published online 2012, in print 2013. Vukusic et al. was published online 2018, in print 2020.
Hulsman et al. appear in PMLR 266 (COPA 2025). Conformal risk control appeared at ICLR 2024 (cited
via arXiv). Montalban et al. (ref. 31) and Thompson et al. (ref. 37) are cited for the
diagnostic-criteria context in the Discussion.
