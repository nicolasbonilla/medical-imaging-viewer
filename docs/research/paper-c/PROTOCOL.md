# Paper C pilot — pre-registered protocol: a per-patient guarantee on FALSE new-lesion activity calls

*Research code, not the medical device. Written 2026-10-21 and committed **before** any detector
output (candidate, score, label, threshold, flag, false-call rate or sensitivity) was computed.
Deviations after this commit go to §12 with a reason, before the affected result is looked at.*

**What had been seen when this was written.**
(i) The novelty re-check (`NOVELTY-CHECK.md`). (ii) The FLAMeS training-overlap check for the
longitudinal open_ms scans (`research/paper_c/flames_overlap_longitudinal.py`, record
`docs/research/records/2026-10-21_paper_c_flames_overlap_longitudinal.json`). (iii) The **truth-only**
inventory (`research/paper_c/inventory.py`, record `…_paper_c_inventory.json`): grids, intervals,
scanners, and the ground-truth change counts per patient / pair, including the sign of the mean
FLAIR subtraction inside each expert change component (a property of the truth, used by rule §2.1).
Nothing else: no candidate of any detector has been extracted on real data.

**Inventory result that shapes this protocol.** There are essentially **no stable patients** in the
public longitudinal data we can use: open_ms longitudinal 20/20 patients have expert-marked change
(8–133 components each; 500 of 835 components brighter at follow-up), and MSLesSeg has 39/40
consecutive pairs (25/25 first pairs) "active" under the approximate truth of §2.2. The quantity the
paper is ultimately about — P(false activity | stable patient) — therefore **cannot be measured
directly in this pilot**. The pilot measures the closest quantity that *is* identifiable on active
patients (the per-patient family-wise error of new-lesion calls, §4) and states the assumption
under which it transfers to stable patients (§5). MSSEG-2 (28 stable patients, access pending) is
where the transfer is to be tested.

---

## 1. Questions

- **Q1 (validity).** Does a conformal threshold calibrated on the *largest false candidate score per
  patient* keep the per-patient probability of **≥ 1 false new/enlarging-lesion call** at or below
  α on held-out patients?
- **Q2 (cost).** At that threshold, how many active patients are still flagged *by a true change*,
  and what fraction of true new/enlarging lesions is kept?
- **Q3 (the app).** How often does the app's current rule (`compare_timepoints`:
  `activity_candidate`) produce ≥ 1 false new/enlarging candidate per patient, with and without the
  app's subtraction confirmation?
- **Q4 (transfer, indirect).** Is the largest false score larger in patients with more true change
  (which would make the guarantee conservative for stable patients)?

## 2. Data, truth and eligibility

### 2.1 open_ms_data longitudinal (Lesjak et al., Neuroinformatics 2016) — expert change truth

20 patients × 2 studies (interval 81–723 days), 2D FLAIR, in-plane 0.57–0.90 mm, slices 3.0–3.3 mm,
co-registered by the providers into a common space and N4-corrected; brain mask and **expert
lesion-change mask** supplied (one label; the direction of change is not encoded). Licence CC-BY.
*FLAMeS overlap:* no FLAMeS training case has the raw spacing of any of these 40 FLAIRs, and the
FLAMeS paper lists only the cross-sectional Ljubljana set (Lesjak 2018, "PubMRI"); the residual
risk is that some of the same people appear in that cross-sectional set (same centre, different
scans) — unknowable from public data, stated as a limitation. Only D-sub (model-free) runs on these
data now; the FLAMeS arm needs the cloud job (§10).

**Truth rule.** Expert change components = 18-connected components of the change mask ≥ 3 mm³.
Each is *positive* (new/enlarging) if the mean normalised subtraction (follow-up − baseline, §3)
inside it is > 0, otherwise *negative* (shrinking/resolving). A candidate is **true** if it overlaps
any expert change component (primary; sensitivity analysis: positive components only), otherwise
**false**. Truth lesions for sensitivity = positive components ≥ 14.14 mm³. All 20 patients are
active.

### 2.2 MSLesSeg (Rondinella et al., Sci Data 2025) — APPROXIMATE truth

25 patients with ≥ 2 timepoints (40 consecutive pairs; interval 0.09–3.89 years), MNI 1 mm as
delivered (native 2D FLAIR 2–5 mm; 18/40 pairs — 13/25 first pairs — differ in scanner model or
vendor string between timepoints, and 4 pairs have an unknown acquisition), FLAMeS-clean
(external test set of FLAMeS). FLAMeS 5-fold maps exist locally. **Primary unit: the first pair of
each patient (25 pairs).** All 40 pairs: sensitivity analysis.

**Truth rule (approximate, because MSLesSeg has per-timepoint lesion masks, not a change
annotation):** components of the follow-up mask ≥ 3 mm³ are *new* if no voxel lies within one voxel
(18-dilation) of the baseline mask; *enlarging* if they touch it and their volume is ≥ 1.5 × the
summed volume of the baseline components they touch **and** they add ≥ 14.14 mm³; otherwise
*persistent*. Change region = new components + the growth voxels of enlarging components.
A candidate is **true** if it overlaps the change region. A pair is *active* if it has ≥ 1 new
component ≥ 14.14 mm³ or ≥ 1 enlarging component. Annotation differences between timepoints create
spurious "new" lesions and can hide real ones; both directions of error are discussed in RESULTS.

### 2.3 Not used

The app's patient data (never). ISBI-2015 (FLAMeS training data, 5 patients). PediMS (longitudinal
but would need our own registration; future). MSSEG-2 (access agreement pending; the target study).

## 3. Candidates and scores (fixed before any candidate was extracted)

Normalised subtraction, both detectors: the app's own functions — z-score each FLAIR within the
brain domain (`normalize_intensity`), d = z_follow-up − z_baseline (`subtraction_map`). Brain domain:
open_ms = supplied brain mask; MSLesSeg = voxels non-zero at both timepoints. Interior = domain eroded
by one voxel (the app's border rule). No further registration: open_ms uses the providers'
co-registration, MSLesSeg its MNI alignment (the app's rigid registration is not exercised).

- **D-sub (model-free subtraction detector).** Candidate voxels: d ≥ 1.5 **and** z_follow-up ≥ 1.0
  inside the interior; candidates = 18-connected components ≥ 14.14 mm³ (MAGNIMS 3-mm size).
  Score **S_sub** = mean d over the component. Thresholds 1.5 / 1.0 SD were chosen a priori
  (sensitivity: 1.0 and 2.0 SD).
- **D-seg (the app's current rule on FLAMeS).** Masks = 5-fold-mean FLAMeS probability ≥ 0.5 at each
  timepoint; the app's `compare_timepoints` (18-conn, ≥ 3 mm³, mutual-best IoU ≥ 0.3). Candidates =
  its *new* components ≥ 14.14 mm³ (`clinically_significant`) and its *enlarged* matches (> 20 %);
  change region R = whole component (new) or component minus the baseline mask (enlarged).
  **Primary score S_sub** = mean d over R ∩ domain (= the app's `subtraction_signal`); secondary
  **S_dp** = mean (p_follow-up − p_baseline) over R.

Gate **G1** (before outcomes): the reconstructed D-seg candidates must reproduce the app's
`new_clinically_significant_count` and `enlarging_count` for every pair (asserted in code).

## 4. Estimand and procedures

For patient i: M_i^F = largest score among its **false** candidates (−∞ if none). Selecting every
candidate with score > λ makes a false call in patient i iff M_i^F > λ. The **per-patient
family-wise error** FWER(λ) = P(M^F > λ) is the probability that a follow-up report contains at
least one false new/enlarging lesion. In a stable patient every candidate is false, so the same
event is exactly a false activity call.

- **CF-M (primary; conformal, marginal).** On n calibration patients, λ̂ = the k-th smallest M^F,
  k = ⌈(n+1)(1−α)⌉; λ̂ = +∞ (abstain: no activity call can be guaranteed) if k > n. Flag candidates
  with score **strictly** > λ̂. Guarantee: P(M_test^F > λ̂) ≤ α for a patient exchangeable with the
  calibration patients (ties included). This is a split-conformal quantile of a max statistic
  (equivalently conformal risk control with the binary loss "≥ 1 false call"); not a new method.
- **CF-PAC (secondary; calibration-conditional).** k = smallest k with P(Bin(n, 1−α) ≥ k) ≤ δ = 0.1
  (Neyman–Pearson umbrella order statistic); abstain if none. Guarantee:
  P_cal[ P(M_test^F > λ̂ | cal) > α ] ≤ δ.
- **Stable-conditional conformal (the ideal procedure).** Calibrate on stable patients' largest
  score. *Not estimable in this pilot* (0 stable patients in open_ms, 0/25 MSLesSeg first pairs).
  Reported as such; it is the primary procedure for MSSEG-2.
- **Baselines.** B-all: every candidate (no threshold) — for D-seg this *is* the app's rule
  (`activity_candidate` counts every one of these candidates); B-app-sub: the app's rule with new
  lesions counted only if S_sub ≥ 0.5 SD (app default) and enlarged lesions always counted;
  B-plug-in: the empirical (1−α) quantile, k = ⌈n(1−α)⌉ (no finite-sample correction);
  B-fixed: S_sub > 0.5 SD for D-seg (the app's confirmation bar used as a threshold for all
  candidates).

Targets α ∈ {0.1, 0.2}; δ = 0.1.

## 5. Transfer to stable patients (assumption, stated not proved)

If the largest score of a stable patient's candidates is stochastically no larger than the largest
false score of the calibration patients (assumption **A-dom**), CF-M's guarantee transfers:
P(false activity | stable) ≤ P(M^F > λ̂) ≤ α. A-dom is plausible (more disease → more perilesional
change and registration-sensitive tissue → more false candidates) but can fail (e.g. stable patients
scanned on a different scanner). The pilot cannot test it directly; it reports the proxy Q4:
Spearman ρ between M^F and the number of truth change components, with a 10 000-permutation p-value.
ρ ≥ 0 is *consistent* with A-dom; ρ < 0 with p < 0.05 is a warning. A 2026 audit of Conformal
Triage (arXiv 2605.20956) shows why pooled validity need not hold in a low-prevalence subgroup —
the reason the stable-conditional procedure is primary on MSSEG-2.

## 6. Arms

| arm | data | detector / score | truth | status |
|---|---|---|---|---|
| **A1** | open_ms longitudinal, 20 patients | D-sub / S_sub | expert change | now (primary) |
| **A2** | MSLesSeg first pairs, 25 patients | D-seg (FLAMeS, app rule) / S_sub | approximate | now (primary) |
| A2b | same | D-seg / S_dp | approximate | now (secondary) |
| A3 | MSLesSeg first pairs | D-sub / S_sub | approximate | now (secondary) |
| **A4** | open_ms longitudinal | D-seg (FLAMeS 5-fold, app rule) / S_sub, S_dp | expert change | **pending cloud job (§10)** — analysed exactly as A2 |

## 7. Evaluation design

**Leave-one-patient-out cross-fitting** within each arm: for each test patient, calibrate on all
other patients of the arm (n = 19 for A1/A4, 24 for A2/A3), test on the held-out one. Every patient
is tested once. Exploratory transport (D-sub only): calibrate on all of open_ms, test on MSLesSeg
first pairs, and the reverse.

## 8. Outcomes

**Primary (4 cells):** realised FWER = fraction of test patients with ≥ 1 false call, CF-M,
α ∈ {0.1, 0.2}, arms A1 and A2, with exact Clopper–Pearson 95 % intervals.

**Secondary.** (1) Patient-level true detection = fraction of test patients flagged by ≥ 1 *true*
candidate; any-flag rate; abstention rate (λ̂ = +∞). (2) Lesion-level sensitivity = truth lesions
(§2) overlapped by a selected true candidate / all truth lesions, patient-cluster bootstrap 95 %
(2000 resamples, seed 20261021). (3) Mean false calls per patient (bootstrap CI). (4) The same for
CF-PAC, B-plug-in, B-all, B-app-sub, B-fixed. (5) Candidate-level AUROC of the score (true vs false),
patient-cluster bootstrap. (6) Q4 Spearman ρ. (7) Number of candidates per patient (descriptive).

## 9. Success criteria (decided now)

- A primary cell is **violated** if the Clopper–Pearson lower bound of the realised FWER exceeds α;
  otherwise **"no violation detected"**. With 20–25 patients the intervals are ±0.15–0.2 wide: the
  pilot can only detect gross failures, and "no violation detected" is not "holds".
- A cell is **informative** if patient-level true detection ≥ 0.5 at that α; **bought by
  abstention** if < 0.2 (including λ̂ = +∞).
- **Q3** "the app's rule over-calls" if the lower bound of its per-patient FWER (B-all on D-seg)
  exceeds 0.2 (the upper end of the false-activity range of the MSSEG-2 systems in Valencia 2022).
- **Go/no-go for the MSSEG-2 study:** *go* if no primary cell is violated and at least one primary
  cell at α = 0.2 is informative; otherwise *redesign the score* (e.g. learned change score,
  FLAMeS-based score on open_ms) before requesting MSSEG-2 time.
- **Q4:** reported, no pass/fail.

## 10. Cloud job (prepared, not launched)

FLAMeS 5 folds on the 40 co-registered open_ms longitudinal FLAIRs (skull-stripped with the
supplied brain mask; no HD-BET) → A4. Spec and launch commands: `CLOUD-JOB.md` (project
`mstool-research` only, isolated gcloud configuration; the owner launches it).

## 11. Sensitivity analyses (pre-specified)

open_ms truth = positive components only; D-sub thresholds d ≥ 1.0 and ≥ 2.0 (z_follow-up ≥ 1.0
unchanged); MSLesSeg all 40 pairs (LOO by patient: a held-out patient's pairs are all tested, the
other patients' pairs are all used for calibration); MSLesSeg same-scanner first pairs only
(descriptive); MSLesSeg "lenient stable" (any new ≥ 3 mm³ counts) — only for counting stable pairs.

## 12. Deviations log

*(empty at the protocol commit 6233b4b)*

**2026-10-21, entry 1 — implementation clarifications, written before any detector output had
been displayed.** (a) Truth lesions for sensitivity get contiguous ids (an implementation detail of
`common.py`; the truth rules of §2 are unchanged). (b) The app's functions are imported read-only
from `backend/app/services/` (`compare_timepoints`, `_extract_components`, `_match_components`,
`normalize_intensity`, `subtraction_map`); Python must not run in isolated mode (`-I`) because the
backend's logging import needs user site-packages. (c) Arm A2b (score S_dp) has no B-fixed
baseline (the 0.5 SD bar is defined on S_sub only).

**2026-10-21, entry 2 — run disclosures and post-hoc material (after the results).** (a) Two
candidate-extraction runs stopped on out-of-memory errors caused by other jobs on the machine; the
extractor was made resumable per unit (`.cache/units/`) and finished in-process; units are
deterministic, so no number depends on this. (b) Drive C: fell below 3 GB free; the 40 open_ms
FLAIRs (0.29 GB) were deleted after the candidates were cached; `extract_candidates.py --stream`
re-fetches one patient at a time for arm A4. (c) `posthoc.py` (score/volume by label, per-patient
ranking ceiling, tail of the largest false scores) was written after the results and is labelled
post hoc in RESULTS.md. (d) `verify_primary.py` recomputes the 4 primary cells by a separate code
path (identical). No pre-registered analysis was changed.

## 13. Compute and records

Local CPU only. Code: `research/paper_c/*.py`; tests `research/paper_c/test_paper_c.py`.
Derived candidate caches go to the git-ignored `research/paper_c/.cache/`; the record
(`docs/research/records/2026-10-21_paper_c_pilot.json` + `_output.txt`) stores input SHA-256s,
per-patient candidate summaries (no voxels), every number in RESULTS.md, and the code commit.
