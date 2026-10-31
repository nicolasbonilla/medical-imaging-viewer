# Pre-registration — Paper C, confirmatory study on MSSEG-2

**A per-patient, distribution-free bound on false new-lesion activity calls in longitudinal MS MRI**

*Ready to post on OSF (template: "OSF Preregistration"). Written 2026-10-31 on branch
`research/paper-c-pilot`, **before any MSSEG-2 data were requested, downloaded or seen** by anyone on
the team. Research, not the medical device. Section numbers follow the OSF template; every choice
below was fixed before access. Changes after posting go to §7 (deviations) with date and reason,
and are reported in the paper.*

---

## 1. Study information

**1.1 Title.** A per-patient, distribution-free bound on false new-lesion activity calls in
longitudinal multiple sclerosis MRI: a pre-registered evaluation on MSSEG-2.

**1.2 Authors.** Nicolas G. Bonilla Vargas (MSTool-AI). Contributor statement and any further
authors are added before submission; a change of authors is not a deviation.

**1.3 Description.** The 2021 MAGNIMS–CMSC–NAIMS recommendations treat one new or enlarging T2
lesion on follow-up MRI as disease activity (Wattjes et al., Lancet Neurol 2021). Automated tools
detect new lesions but do not state how often they call activity in a patient who has none. On the
MSSEG-2 test set, the best expert raters produced few false new lesions, the automated methods many
more (Masson et al., Sci Rep 2026). We test whether a split-conformal threshold on a change score —
calibrated on patients without new lesions — bounds the per-patient probability of a false
new-lesion call at a chosen level α, and what fraction of patients with true new lesions are still
flagged. The candidate generator is the rule of an existing software (MSTool-AI
`compare_timepoints`, new lesion ≥ 3 mm diameter) applied to an open segmentation model (FLAMeS
5-fold ensemble). A pilot on two other public datasets (20 + 25 patients, no stable patient) found
the bound held but was informative only with this segmenter-based configuration and consistent
acquisitions (`RESULTS.md`, arm A4).

**1.4 Hypotheses.** Unit: patient. "Stable" = no expert-confirmed new lesion. α ∈ {0.1, 0.2}.

- **H1 (validity; falsification check, both α).** Among stable patients, the realised rate of
  ≥ 1 false new-lesion call with the stable-conditional conformal threshold (primary procedure,
  §5.1) does not exceed α. *Declared violated* if the exact Clopper–Pearson 95 % lower bound
  exceeds α. With 11 stable patients this can only detect gross violations; "no violation
  detected" is not proof of validity.
- **H2 (utility; primary test, α = 0.2).** With the primary procedure at α = 0.2, the proportion of
  active patients flagged by ≥ 1 *true* new-lesion candidate exceeds 0.25. One-sided exact
  binomial test against 0.25.
- **H3 (the current rule over-calls in stable patients).** The software's current new-lesion rule
  (every new candidate ≥ 3 mm diameter counts) produces ≥ 1 new-lesion call in more than 20 % of
  stable patients. One-sided exact binomial test against 0.20. (0.20 lies above every expert and
  inside the range of the challenge systems for "stable test patients with ≥ 1 false positive" in
  Valencia et al., Front Neurosci 2022, Table 3: experts 0–11 %, systems 11–36 % of 28 patients.)
- **H4 (improvement).** The rate of false new-lesion calls in stable patients is lower with the
  primary procedure at α = 0.2 than with the current rule. Exact one-sided McNemar test (paired by
  patient).
- H2–H4 are one family: **Holm** correction at a family-wise 0.05. H1 is a validity check,
  reported at both α, not part of the family.

## 2. Design plan

**2.1 Study type.** Observational; secondary analysis of an existing, de-identified public dataset;
methods evaluation.

**2.2 Blinding.** No image, mask or derived number of MSSEG-2 has been seen. After download, the only
look before the pre-specified pipeline runs is the truth-only inventory (§4.2). Scripts print and
commit group-level results only (also a data-use-agreement requirement, §4.4).

**2.3 Study design.** Each patient contributes one pair of 3D FLAIR scans (baseline, follow-up) and
the expert consensus mask of new lesions. Leave-one-patient-out evaluation within the dataset (§5).

**2.4 Randomisation.** None. Bootstrap seed 20261031.

## 3. Sampling plan

**3.1 Existing data.** *Registration prior to accessing the data.* The data exist (MSSEG-2, 2021);
no team member has accessed them. Known before registration, from publications only: dataset size
and split (100 patients; 40 training distributed, 60 test not distributed), 36 of 100 patients
without new lesions overall and 25 of 60 in the revised test set (Masson et al. 2026), case-wise
test results of the challenge methods and experts (Zenodo record 5552675, not opened by us), and our
own pilot on other datasets (`RESULTS.md`, `stage0` and `power` records).

**3.2 Data collection procedure.** Access through Shanoir under the OFSEP data use agreement
(`MSSEG2_ACCESS_REQUEST.md`). Two pre-specified scenarios, decided by what OFSEP grants, **not by any
result**:

- **S1 (default) — training set only:** 40 patients; expected 11 stable and 29 active (inferred
  36 − 25; confirmed by the inventory).
- **S2 — training + test set:** 100 patients (36 stable, 64 active, revised ground truth), only if
  OFSEP/Inria grant the test set with its revised ground truth. In S2 every analysis uses all
  100 patients; S1 results are not reported separately except as a sensitivity analysis.

**3.3 Sample size.** Fixed by the dataset (S1: 40; S2: 100). No patient is added or removed after
results are seen.

**3.4 Sample size rationale (power from the pilot).** Monte Carlo simulation
(`research/paper_c/power_msseg2.py`, 2,000 runs per setting, seed 20261031; record
`docs/research/records/2026-10-31_paper_c_power_msseg2.json`). Per-patient largest false scores and
true-candidate scores are resampled from the pilot (arm A4 = open_ms, expert change masks; arm A2 =
MSLesSeg, heavier tail); new-lesion counts follow MSSEG-2 (17 of 64 active patients with exactly
one new lesion); each lesion becomes a candidate with the pilot's lesion-level recall (0.354, or a
pessimistic 0.6 × 0.354 with scores lowered by 0.25 SD). Power of H2 (Holm-adjusted) with the
primary procedure at α = 0.2:

| Pilot-based scenario | S1 (11 / 29) | S2 (36 / 64) | Expected share of active patients flagged (S1) |
|---|---|---|---|
| Consistent acquisitions (A4 tail) | **0.995** | 1.000 | 0.64 |
| Consistent, pessimistic detection | 0.62 | 0.90 | 0.43 |
| Mixed tail (half A4, half A2) | 0.80 | 0.99 | 0.50 |
| Heterogeneous (A2 tail) | 0.49 | 0.81 | 0.32 |
| Mixed tail, pessimistic detection | 0.39 | 0.73 | 0.32 |

At α = 0.1 the power of an H2-type test is 0.99 (consistent) but falls to 0.14–0.17 with the heavy
tail — the reason α = 0.2 carries the primary test. H3 (analytic, Holm worst case, S1): power 0.75
if the current rule's true false-activity rate in stable patients is 0.6, 0.97 if 0.75 (pilot: ≥ 1
false new candidate in 20/20 and 25/25 patients). H4: power ≥ 0.96 in every setting. **Honest
reading:** S1 is well powered only if MSSEG-2 behaves like the consistent pilot arm; under heavy
tails or weak detection its power is 0.4–0.6, which is why the test set is requested (S2).

**3.5 Stopping rule.** None (fixed dataset).

## 4. Variables

**4.1 Pipeline (fixed).**

1. *Preprocessing:* the MSSEG-2 organisers' published preprocessing (Anima-based brain extraction and
   bias correction; **no** template normalisation; mask = union of both time points' brain masks),
   version and SHA-256 recorded. Both time points are delivered in a common middle space; no further
   registration (the software's own rigid registration is not exercised).
2. *Segmenter:* FLAMeS (nnU-Net `Dataset004_WML`) folds 0–4 on each preprocessed FLAIR, no
   test-time augmentation; lesion mask = mean probability ≥ 0.5. Weights SHA-256 recorded (the same
   frozen weights and environment as the pilot cloud job). Before analysis we re-check the FLAMeS
   paper's dataset list; any MSSEG-2 case in FLAMeS *training* is excluded (expected none: FLAMeS used
   MSSEG-2 cases as test data only).
3. *Candidate rule:* the software's `compare_timepoints` (18-connected components ≥ 3 mm³,
   mutual-best IoU ≥ 0.3 matching), imported read-only from `backend/app/services/`. **Primary
   candidates = its new components ≥ 14.14 mm³** (3-mm-diameter sphere; `clinically_significant`).
   Enlarged matches are reported descriptively only (§6.3) because MSSEG-2 does not annotate growth.
4. *Score:* **S_sub** = mean normalised FLAIR subtraction over the candidate inside the domain
   interior (domain eroded by one voxel) — the software's `subtraction_signal` (z-score within the
   domain, follow-up minus baseline). Secondary scores: S_dp (mean FLAMeS probability change) and
   S_v2 (frozen logistic combination, §4.3).
5. *Gate G1:* the research reconstruction must reproduce the software's own new-lesion count for
   every pair (asserted in code; a failure stops the run and is fixed before any outcome is looked
   at).

**4.2 Truth.** MSSEG-2 consensus new-lesion mask (lesions < 3 mm already removed by the organisers).
Truth lesions = 18-connected components. A candidate is **true** if it overlaps any truth voxel,
otherwise **false**. A patient is **stable** if the truth mask is empty, **active** otherwise.
*Truth-only inventory* (the first look after download): number of patients, stable/active counts,
truth lesions per patient — no image intensity, no candidate.

**4.3 Frozen secondary score S_v2 (Stage 0, before access).** Logistic score on standardised
features [S_sub, S_dp, log10 volume], L2, C = 1, fitted on the pilot arm A4 new-lesion candidates:
coefficients [1.2176, −0.0369, 1.1686], intercept 0.8799, means [0.8190, 0.6497, 1.8453], SDs
[0.8297, 0.3569, 0.5656]; SHA-256 of the frozen JSON `92faf442…364f013e`
(record `docs/research/records/2026-10-31_paper_c_stage0_score_v2.json`). Stage 0 showed no gain over
S_sub on the pilot (nested cross-fitted CF-M at α = 0.1: 15/20 vs 18/20 patients flagged by a true
change; worse when transported to MSLesSeg); S_v2 is therefore secondary only and is never re-fitted.

**4.4 Data-use constraints that shape the variables.** OFSEP DUA clause 4: only group-level
results leave the owner's machine. Clause 8: nothing derived from MSSEG-2 is used in any product.

## 5. Analysis plan

**5.1 Procedures.** For patient i, M_i = largest score among its false candidates (−∞ if none; in a
stable patient every candidate is false). Selecting candidates with score > λ calls a false new lesion
in i iff M_i > λ.

- **Primary — stable-conditional CF-M.** λ̂ = k-th smallest M among n calibration *stable*
  patients, k = ⌈(n + 1)(1 − α)⌉; λ̂ = +∞ (abstain) if k > n. Stable test patient: calibration =
  the other stable patients (leave-one-out; n = 10 in S1, 35 in S2). Active test patient:
  calibration = all stable patients. Guarantee: P(M_test > λ̂) ≤ α for a stable patient exchangeable
  with the calibration stable patients (finite-sample, distribution-free; ties included).
- **Secondary — pooled CF-M** (the pilot's primary): calibration on the largest *false* score of all
  other patients; valid for stable patients only under the dominance assumption A-dom (pilot
  protocol §5).
- **Secondary — CF-PAC** (δ = 0.1), **plug-in quantile**, **every candidate** (= the current rule),
  **current rule + its subtraction confirmation** (S_sub ≥ 0.5 SD), **fixed bar** S_sub > 0.5 SD.

**5.2 Outcomes.**

- Primary: false-activity rate in stable patients (H1, H3, H4); proportion of active patients
  flagged by ≥ 1 true candidate (H2). Exact Clopper–Pearson 95 % intervals.
- Secondary: lesion-level sensitivity (truth lesions overlapped by a selected true candidate / all
  truth lesions; patient-bootstrap 95 %, B = 2,000); false calls per patient; abstention; per-patient
  family-wise false-call rate over all patients; candidate-level AUROC (patient bootstrap);
  three-class patient accuracy (0, 1–2, ≥ 3 new lesions) as in Masson 2026.

**5.3 Inference criteria.** H2–H4: Holm at 0.05 (one-sided tests as stated). H1: violation if CP
lower bound > α. **Informative** if the point estimate of H2's proportion is ≥ 0.5; **bought by
abstention** if < 0.2 (pilot rule). All pre-specified outcomes are reported whatever their
direction.

**5.4 Data exclusion.** A pair is excluded only if preprocessing or FLAMeS fails (listed with the
reason) or if the patient was in FLAMeS training. No outlier removal. Gate G1 failures are fixed in
code, never by exclusion.

**5.5 Missing data.** None expected; a failed pair is excluded (complete case) and reported.

**5.6 Sensitivity analyses (pre-specified).** (a) α = 0.1 for H2 (reported, not tested in the
family); (b) primary procedure with S_dp and with S_v2; (c) pooled CF-M; (d) in S2, training set only;
(e) by vendor, only if the release states it (descriptive); (f) truth = lesions ≥ 14.14 mm³ only
(candidate size floor matched).

**5.7 Exploratory (labelled as such).** (1) Dominance check: one-sided Mann–Whitney of stable
patients' M vs active patients' largest false score (A-dom; pilot Q4). (2) Transport: threshold
calibrated on the pilot's open_ms arm A4 applied unchanged to MSSEG-2. (3) Enlarged candidates in
stable patients: count per patient (no truth). (4) S2 only: false-activity rate of our procedure
next to the four experts' and the methods' case-wise results published on Zenodo 5552675.

## 6. Other

**6.1 What a positive result would and would not mean.** A bound on false *new-lesion* calls in
patients without new lesions, for this segmenter, rule and acquisition class (3D FLAIR, co-registered
pairs). It says nothing about missed lesions (the threshold increases them), about enlarging
lesions, or about other scanners, registrations or segmenters.

**6.2 Products.** No threshold, table or model computed on MSSEG-2 is used in any software (DUA
clause 8). The paper's results inform a separately calibrated feature (`APP_FEATURE_SPEC.md`).

**6.3 Code and records.** `research/paper_c/` (pilot pipeline reused unchanged). The MSSEG-2
loader does not exist yet: it is written, unit-tested on synthetic files and committed **before** the
data are opened, and it only reads files and checks grids — any analysis choice stays as written here. Records: group-level JSON in `docs/research/records/`. Per-patient caches git-ignored
and deleted with the data (DUA clause 7).

## 7. Deviations (after posting)

*(empty)*
