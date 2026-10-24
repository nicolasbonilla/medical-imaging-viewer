# Lesion-level false-positive detector v3 — PRE-REGISTERED PROTOCOL

**Status:** pre-registration, written and committed **before** any v3 feature was computed and
before any v3 model was trained or evaluated. Date: 2026-10-17. Branch `research/lesion-detector-v3`.
**Scope:** research only (CALM-MS "precision dial", investigational, dark). No `backend/app` code
is changed. Not a clinical claim.

Every change made after this commit is logged in §11 (Deviations) with the reason and whether it
was made before or after any outcome (AUROC / conformal metric) was seen.

---

## 1. Why v3, and what v2 taught us

The conformal lesion-selection guarantee (Jin & Candès conformal p-values + BH, and the per-scan
FDX layer in `research/conformal_fdx/calm_fdx.py`) is valid but has little power because the
score that separates true from false candidate lesions is weak: raw mean FLAMeS probability,
lesion-level AUROC 0.735 (MSLesSeg) / 0.698 (clean Ljubljana-10) in the paper-A v0.2 record.

v2 (August 2026) is documented and partly **retracted** (`docs/calm-ms/v2-learned-scorer-result.md`,
`scripts/calm-ms/evaluate_lesion_scorer.py` is the authoritative honest evaluation). Honest v2:
within-domain patient-grouped AUROC 0.796 vs 0.701 raw; **pooled leave-one-site-out AUROC 0.624**
(below raw). Retracted: a "load-bearing" shift test that inflated only the false candidates
(rigged), and a calibration double-use leak (scorer trained on the calibration site whose false
candidates were the conformal null) that manufactured power. v2 also pooled the 20 Ljubljana
scans FLAMeS was trained on.

Rules this protocol adopts from those failures:

1. No test or calibration patient ever contributes to training a scorer (three-way patient split).
2. No synthetic shift that touches labels; only real cohort-to-cohort transfer.
3. FLAMeS training overlap is respected: only FLAMeS-clean scans are used for training and testing
   in the primary analysis (§3).
4. The success criterion, models, hyper-parameters, seeds and resampling are fixed here, before
   results. One primary endpoint; everything else is labelled secondary or exploratory.
5. An adversarial self-check (§9) is part of the protocol, not an afterthought.

## 2. Data integrity observations made BEFORE pre-registration (no labels used)

Checked only grids, intensities and masks (no candidate/label relationship was looked at):

* MSLesSeg and Ljubljana FLAMeS maps (`*_prob.nii.gz`) share shape (182, 218, 182) and the exact
  affine of their FLAIR images → voxelwise aligned. Controls (SibBMS) are native-space
  (e.g. 197×233×189, 1 mm) and **have no FLAIR locally** (only prob + empty GT).
* Ljubljana "regtoMNI" brains are **not size-normalised**: brain volume ≈ 1.18–1.37 L and maximum
  depth ≈ 39–42 mm, vs MSLesSeg ≈ 1.84–1.95 L and 55–60 mm (MSLesSeg looks affine-scaled to MNI;
  Ljubljana looks rigidly placed, top/bottom trimmed). Consequences: (a) v2's MNI-normalised
  location features are not comparable across these cohorts — a plausible contributor to v2's
  LOSO collapse; (b) every v3 distance/depth/volume-location feature is **normalised by a
  scan-specific brain scale** (§5 F6).
* Ljubljana FLAIR is N4-corrected and **winsorised** (upper tail clipped; 99.9th brain percentile
  z ≈ 3.0–3.2 vs ≈ 3.9–5.0 MSLesSeg) and has a few negative interpolation values. This is a
  site-specific preprocessing difference that can shift intensity features (checked in §9 A8).
* Background is exactly 0 in both cohorts' FLAIR → brain mask = largest component of
  fill_holes(FLAIR > 0).

## 3. Cohorts and FLAMeS-contamination rules

| Set | Scans / patients | Role | FLAMeS status (fold-0 maps) |
|---|---|---|---|
| **M** = MSLesSeg | 115 / 75 (longitudinal) | train + test | clean (0/115 fingerprint matches; record `2026-10-17_mslesseg_flames_overlap_check`) |
| **L10** = Ljubljana patients 16–20, 26–30 | 10 / 10 | train + test | never trained on by any FLAMeS fold (also clean for a future 5-fold ensemble) |
| L12 = L10 + patients 04, 07 | 12 / 12 | sensitivity test only | 04, 07 are fold-0 validation → clean for fold-0 only |
| Ltr = Ljubljana 01–15, 21–25 | 20 / 20 | contamination reference (test only) + exploratory E1 | in FLAMeS training (18 of them in fold-0 training) |
| **C** = SibBMS healthy controls | 30 / 30 (local) | pure-false test only | not in FLAMeS' cited training sources; **not fingerprint-verified** |
| ISBI-19 (LST-AI maps) | 19 | **excluded** | different base model; patient identity across the 19 scans unknown |

Split source: `docs/research/records/2026-10-17_flames_fold_membership.json` (branch
`research/paper-a-v0.2`, commit 87e998d) — hard-coded in the v3 code with this reference.

## 4. Candidates and labels

* **Candidate** = 18-connected component of `FLAMeS fold-0 prob ≥ 0.5` with ≥ 3 voxels (3 mm³ at
  1 mm), extracted with the shared `app.services.calm_ms_inference.extract_lesion_candidates`
  (identical to paper A). Raw score = mean probability over the component.
* **GT lesions** = 18-connected components of the expert mask with ≥ 3 voxels.
* **Primary label (lenient one-to-one):** Hungarian maximum-IoU assignment of candidates to GT
  lesions, a pair allowed only if IoU > 0; a matched candidate is TRUE, every other candidate is
  FALSE (surplus fragments of one GT lesion are FALSE). Same function as paper A
  (`scripts/calm-ms/multisite_conformal_advanced._hungarian`).
* Sensitivity labels (§9 A4): strict one-to-one (IoU > 0.10); any-voxel (candidate overlaps any GT
  voxel — the v2 convention).
* **Reproduction gate:** candidate and FALSE counts must equal the paper-A cohort table
  (M 3866 / 1348; L10 534 / 94; controls 83 candidates). If not, stop and explain before modelling.

## 5. Features (all computed WITHOUT ground truth; GT only produces labels)

Per scan: `P` = FLAMeS prob map; `F` = FLAIR on the same grid; brain mask `B` (§2); robust per-scan
z-score `z = (F − median(F[R])) / (1.4826·MAD(F[R]))`, reference `R = B ∩ {P < 0.05}`. Ring
notation: `Dk` = k iterations of 18-connected dilation of the candidate `C`.

**Carried from v2 (NOT new):** `prob_mean, prob_max, prob_std, prob_q90` (prob moments) and
`log_volume, sphericity, surf_to_vol, elongation, extent` (morphology) — the 9 grid-invariant v2
features, computed with the shipped module `app.services.calm_ms_lesion_features`; and the 5 v2
MNI location features `z_norm, y_norm, x_norm, laterality, radial` (v2 comparator only).

**NEW in v3:**

* **F1 FLAIR contrast vs NAWM shell** — shell = `D4 \ D1` ∩ B, excluding `P ≥ 0.1` and CSF-like
  voxels (`z < −2`); if < 10 voxels, `D6 \ D1` with the same exclusions; else NaN.
  `fl_z_mean, fl_z_median, fl_shell_z_mean, fl_shell_z_std, fl_contrast (= fl_z_mean −
  fl_shell_z_mean), fl_cnr (= contrast / max(shell_std, 0.25)), fl_frac_hyper (fraction of C with
  z > shell_mean + 2·max(shell_std, 0.25)), fl_shell_valid_frac`.
* **F3 FLAIR texture** (candidate voxels, z units): `fl_tex_std, fl_tex_iqr, fl_tex_skew,
  fl_tex_kurt, fl_tex_entropy (histogram entropy, bin 0.5 z), fl_tex_grad_interior (mean |∇z| over
  the eroded candidate; NaN if empty)`.
* **F4 boundary sharpness:** FLAIR — `fl_grad_boundary (mean |∇z| on inner surface ∪ D1\C),
  fl_grad_ratio (= fl_grad_boundary / (fl_tex_grad_interior + 0.1)), fl_edge_step (mean z of inner
  surface − mean z of D1\C)`; prob-map — `pm_grad_boundary (mean |∇P| on the same band),
  pm_ring1_mean (mean P on D1\C), pm_ring3_mean (mean P on D3\D1)`.
* **F5 multi-threshold persistence (prob-map only):** `ps_surv_075, ps_surv_090` (fraction of C with
  P ≥ 0.75 / 0.90), `ps_nsplit_075, ps_nsplit_090` (number of 18-components of C ∩ {P ≥ t}),
  `ps_log_merge_025, ps_log_merge_010` (log of [volume of the {P ≥ t} component containing C /
  volume of C]), `ps_nmerge_025` (number of other candidates inside the same 0.25-component).
* **F6 scale-normalised location proxies, MNI-free:** depth `d` = Euclidean distance to the outside
  of B (cortex/surface proxy), `dmax = max d`; brain radius `r_b = (3|B|/4π)^(1/3)`; ventricle proxy
  = 18-components of `{z < −2} ∩ {d ≥ 0.25·dmax}` whose size ≥ 25 % of the largest such component.
  `loc_depth_min_rel, loc_depth_mean_rel (d/dmax over C), loc_dvent_min_rel (min distance to the
  ventricle proxy / r_b), loc_csf_contact (fraction of D2\C ∩ B that is CSF-like),
  loc_outside_contact (fraction of D2\C outside B), loc_log_rel_volume (log(|C| / |B|))`.
  Heuristic proxies, not validated against an atlas (stated as a limitation).
* **Exploratory only (not in the primary model):** F2 T1 contrast `t1_contrast, t1_frac_hypo`
  (same shell; FLAMeS is single-FLAIR so the primary detector stays FLAIR-only); F7 scan context
  `ctx_log_ncand, ctx_log_totvol, ctx_rank_prob`.
* **Placeholders (code + unit tests now; evaluated only under a future amendment v3.1):**
  F8 ensemble disagreement from the 5 FLAMeS folds — `ens_mean, ens_std (across-fold std of the
  candidate mean), ens_frac_detect (fraction of folds with ≥ 50 % of C at P_k ≥ 0.5),
  ens_voxvar_mean, ens_mi (mean mutual information = epistemic uncertainty)`; F9 independent-model
  agreement with LST-AI — `lst_mean, lst_max, lst_frac_ge05, lst_detect, lst_local_dice`.
  Candidates stay defined on the fold-0 map unless v3.1 pre-registers otherwise.

**Feature sets.** `RAW` = prob_mean (no model). `V2` = 14 v2 features. `V3P` (prob-map only, usable
on controls) = 9 v2 grid-invariant + pm_* (F4) + F5. **`V3` (primary)** = 9 v2 grid-invariant + F1 +
F3 + F4 + F5 + F6. Exploratory: V3+F2, V3+F7, V3+MNI, new-families-only.

## 6. Models (hyper-parameters fixed now; no tuning on any test data)

* **LR (primary):** per-feature median imputation and winsorisation at the training 1st/99th
  percentiles, standardisation, L2 `LogisticRegression(C=0.1, lbfgs, max_iter=5000)`. Output
  P(true lesion) = the score (higher = more lesion-like).
* **GB (secondary):** `HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05,
  max_iter=300, min_samples_leaf=30, l2_regularization=1.0, random_state=0)`, no early stopping,
  same imputation.
* **V2 comparator "as shipped":** degree-2 polynomial LR, C = 0.5, standardised (the
  `evaluate_lesion_scorer.py` specification) on the 14 V2 features. V2 with the v3 LR spec is
  also reported.
* Seed for everything: 20261017.

## 7. Evaluation designs

* **Within-cohort (S1):** M — 5 patient folds (seeded permutation of the 75 patients, round-robin);
  L10 — leave-one-patient-out. Out-of-fold scores.
* **Leave-one-cohort-out (primary):** direction A = train on all M → score L10; direction B = train
  on L10 → score M. **Pooled LOCO** = the union of the out-of-cohort scores (4400 candidates), as in
  v2's 0.624. Raw probability is scored on the same union.
* **Healthy controls (S5):** pure-false test set, never used for training; only V3P and RAW can be
  applied (no local FLAIR).
* **Conformal, no calibration double use (S3, S4, S5):** within M, three-way patient cross-fit —
  for test fold k the scorer is trained on the 3 folds ≠ k, k+1 and the conformal null is the FALSE
  candidates of fold k+1 scored by that scorer; rotating k covers every patient once. Cross-cohort:
  20 seeded random 50/50 splits of the M patients into (train, calibration); test = L10 (and the
  controls). Raw probability uses the identical calibration patients (paired). Conformal p-values
  from `calm_fdx.conformal_ranks` (k/(n+1)); **BH within each scan** at α ∈ {0.1, 0.2, 0.3}; per-scan
  FDX Layer 1 via `calm_fdx.select_fdx` (γ = α, δ = 0.1, template "hc").
* **Resampling:** all CIs are 95 % percentile **patient-clustered bootstrap** (for L10 and controls
  patient = scan), stratified by cohort for pooled statistics, B = 2000, seed 20261017; paired
  differences use the same resamples. Bootstrap is over test units with fixed predictions (model
  re-fitting variance is not included — stated limitation).

## 8. Endpoints and success criterion

**Primary endpoint:** lesion-level AUROC (TRUE vs FALSE, primary labels) of the pooled
leave-one-cohort-out scores, model **V3-LR**, compared with **RAW** on the same 4400 candidates.

**Pre-registered success criterion (primary):** Δ = AUROC(V3-LR) − AUROC(RAW) on pooled LOCO is
**≥ +0.05 AND the lower bound of its paired 95 % bootstrap CI is > 0**. A positive CI with
Δ < 0.05 is reported as "statistically positive but below the pre-registered practical threshold"
— **not met**. Anything else — **not met**.

**Key secondary (H2):** Δ(V3-LR − V2 as shipped) on pooled LOCO, CI lower bound > 0.

**Secondary (descriptive, no multiplicity correction):** S1 within-cohort AUROC; S2 per-direction
and per-cohort LOCO AUROC; S3 within-M conformal power (selection recall), micro-FDR, mean per-scan
FDP, per-scan FDP exceedance P(FDP > α), scans selecting nothing, for RAW / V2 / V3-LR / V3-GB at
α = 0.1/0.2/0.3, BH and FDX; S4 the same M → L10 (FDR realised, not guaranteed — no exchangeability
across cohorts); S5 controls: false detections per 100 control scans and fraction of control scans
with ≥ 1 detection (V3P-LR vs RAW), and AUROC(L10 TRUE vs control candidates); V3-GB everywhere.

**Exploratory:** E1 train on all 30 Ljubljana (incl. FLAMeS-trained maps; not a leak for M) → test
M; E2 V3+F2 (T1), V3+F7 (scan context), V3+MNI; E3 new-families-only.

## 9. Pre-registered adversarial self-check

* **A1 shuffle-label null:** 20 permutations of the training labels (within the training cohort),
  re-fit, evaluate with true labels — pooled LOCO and within-M; flag if the null mean is > 0.53.
* **A2 leakage / integrity:** assertions that no patient is in two roles of any split; feature code
  takes no GT argument (unit test); conformal null never contains a training or test patient.
* **A3 site confound:** cohort-identity AUROC (M vs L10) from each family (patient-grouped CV); the
  v3 gain must be present **within each cohort** of the LOCO predictions, not only pooled.
* **A4 label shift:** base rates per cohort; primary re-run with strict and any-voxel labels; share
  of FALSE candidates that overlap GT (fragments).
* **A5 small-n optimism:** within M, train V3-LR on 10 random patients (20 draws), test on the other
  M patients — how much does a 10-patient training set (direction B) lose? Events-per-variable.
* **A6 contamination:** direction-A model on L12 and Ltr vs L10.
* **A7 drop-one-family ablation** on pooled LOCO.
* **A8 intensity-preprocessing confound:** KS distance M vs L10 of every FLAIR feature, separately
  among TRUE and among FALSE candidates.
* **A9 model choice:** GB vs LR on every endpoint.

## 10. Outputs

Scripts: `research/lesion_detector_v3/` (`features_v3.py`, `build_features.py`, `evaluate_v3.py`,
tests). Feature cache (derived from gitignored data): `research/lesion_detector_v3/.cache/`
(gitignored), its SHA-256 written into the records. Records: `docs/research/records/2026-10-17_
lesion_detector_v3_*.json` + `_output.txt`. Report: `docs/research/lesion-detector-v3/RESULTS.md`.

## 11. Deviations log

(none at pre-registration)

* **D1 (2026-10-17, added BEFORE any outcome was seen; feature cache still building).** Extra
  adversarial check A4b: under one-to-one labels, surplus fragments of a real lesion are FALSE, so a
  detector could "win" by flagging fragments (e.g. via `ps_nmerge_025`) without removing any false
  lesion. The primary pooled-LOCO predictions are re-scored with fragment-false candidates (FALSE but
  overlapping GT) removed — TRUE vs pure-false only. Does not change the primary endpoint.
* **D2 (2026-10-17, added BEFORE any outcome was seen).** Extra check A5b: the bootstrap CIs hold
  the fitted model fixed (§7); direction B trains on 10 patients, so V3-LR is refitted on 50
  patient-bootstrap resamples of L10 and scored on M to expose model-refit variance.
* **D3 (2026-10-17, data integrity, BEFORE any outcome).** The public MSLesSeg T1 of P49_T2 is
  essentially empty (6994 non-zero voxels, none inside the FLAIR brain), which aborted the feature
  build. T1 feeds only the exploratory family F2, so a T1 covering < 50 % of the FLAIR brain (or with
  a degenerate intensity spread) now disables F2 for that scan (NaN, imputed) instead of aborting;
  the FLAIR path stays fail-closed. Primary analysis unaffected.
* **D4 (2026-10-17, BEFORE any outcome; found in a dry run on a synthetic random-feature cache).**
  A3 (site-identity probe) used patient folds not stratified by cohort; pooled out-of-fold AUROC with
  fold-varying class balance is biased below 0.5 for uninformative features (0.31 on random data).
  A3 folds are now assigned per cohort (M patients and L10 patients each split into 5 folds) so
  every fold has the same cohort mix. The same mechanism makes the pre-registered pooled-LOCO
  endpoint penalise any learned model whose two directions are calibrated to different base rates
  (RAW has no training and is immune); the endpoint is kept as pre-registered and the per-direction
  AUROCs (S2) are reported alongside.
