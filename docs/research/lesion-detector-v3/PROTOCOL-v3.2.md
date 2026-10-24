# Lesion-level false-positive detector v3.2 — PRE-REGISTERED PROTOCOL EXTENSION (healthy controls)

**Status:** pre-registration, written and committed on 2026-10-24 **before** any v3.2 feature was
computed on the control scans and before any learned score, fold-disagreement or LST-AI value was
computed for a control candidate. Extends [`PROTOCOL.md`](PROTOCOL.md) (v3) and
[`PROTOCOL-v3.1.md`](PROTOCOL-v3.1.md); everything not changed here is inherited (one-to-one
Hungarian labels, LR / GB specifications, seed 20261017, B = 2000 cluster bootstrap, no calibration
double use). Research only; no `backend/app` code is changed. Deviations go to §11.

## 1. Why v3.2

v3.1 met its criterion on three unseen sites, but the post-hoc check showed that most of the gain is
the 5-fold FLAMeS ensemble: with candidates taken from the 5-fold **mean** map, the ensemble mean
probability reaches 0.796 and the learned grid-robust detector adds only +0.013 [+0.008, +0.018].
Decision taken: the app ships the 5-fold ensemble plus fold disagreement, **not** the learned
detector. Open since v3: FLAMeS false positives on healthy brains look like real lesions. Paper A
v0.3c (branch `research/paper-a-v0.3`, record `2026-10-24_paper_a_v03c_controls.json`) has since
measured the raw ensemble on 100 SibBMS controls: ≥ 1 candidate in 85/100, 2.63 per scan, 63 % of
them periventricular. v3.2 asks whether a **candidate-level** score — beyond the ensemble mean and
fold disagreement — separates those healthy false candidates from real lesions, whether using
controls for training or calibration helps on unseen MS sites, and whether any such gain is real
lesion-ness or just recognition of the control cohort (controls are template-normalised, one site).
Paper A's claims (healthy false-alarm rates of the conformal selections calibrated on patients, the
app's dissemination-in-space rule on healthy scans, false-lesion locations) are **not** re-made here;
v3.2 reuses only its candidate definition (as a reproduction gate) and its per-candidate region
labels (descriptive breakdown).

## 2. What had been seen when this was written (honesty statement)

1. All v3 / v3.1 results, including post-hoc P1–P3 on the 5-fold-mean candidates of MSLesSeg (M),
   Ljubljana-10 (L10) and the three external sites. **Nothing on the MS side is blind.**
2. v3 S5: on 30 controls (sub-001…020, 031…040) with **fold-0** candidates, AUROC (L10 true vs
   control candidates) raw 0.371, V3P-LR 0.429.
3. Paper A v0.3c on all 100 controls, **ensemble arm**: 263 candidates in 85 scans, per-scan
   distribution, candidate score quantiles (median 0.738, 90th percentile 0.93), volumes, regions
   (165 PV / 33 JC / 4 IT / 61 DWM), and patient-calibrated selection counts. Hence the ensemble mean
   probability (ENS-RAW) of the control candidates is **not blind**. No learned score, no
   fold-disagreement value and no LST-AI value of any control candidate has been computed or seen.
4. Gate V0 (`inventory_v32.py` → `docs/research/records/2026-10-24_lesion_detector_v32_inventory.json`),
   integrity only: 100 controls × (5 FLAMeS fold maps + all-zero mask + LST-AI ensemble + 3 LST-AI
   U-Net maps) = 1000 files, SHA-256 recorded (combined `d68ef6d4…`); one grid for all
   (197 × 233 × 189, 1 mm); masks all zero; every map decodes into [0, 1] (yes/no only); LST-AI
   hashes equal the `lstai-ctl` manifest; 0 problems.
5. Accidentally displayed while reading the `lstai-ctl` manifest's structure: the per-case summary of
   **sub-001** (LST-AI ensemble maximum 0.575, 7 voxels ≥ 0.5). No other control's summary was looked at.

Controls: SibBMS, CC BY-NC-SA 3.0 (research only), one site, `Output/Norm` = spatially normalised to
a template (HD-BET brain ≈ 2.0 L). FLAMeS did not train on SibBMS (paper A addendum §1: 668 training
scans from 11 MS sources; fingerprint check). LST-AI v1.2.0 run `lstai-ctl` (100 cases, 0 errors),
same image digest and command as the MS run `lstai-full-a`.

## 3. Data and candidates

| Set | Scans / units | 5-fold-mean candidates (false) | Role |
|---|---|---|---|
| M = MSLesSeg | 115 / 75 patients | 3788 (1257) | 1-mm MS, cross-fitted train/test |
| L10 = clean Ljubljana-10 | 10 / 10 | 517 (82) | 1-mm MS, cross-fitted train/test |
| **C = SibBMS controls** | **100 / 100 subjects** | expected 263 (all false) | cross-fitted train/calibration/test |
| MS3SEG, Muslim, PediMS | 100 / 51 / 28 (9 children) | 3402 (1162) / 1540 (568) / 1110 (321) | external, **never trained or calibrated on** |

* **Candidates (primary, as recommended by v3.1 §7):** 18-connected components of the **5-fold mean**
  FLAMeS map ≥ 0.5 with physical volume ≥ 3 mm³ (`build_features.py --candidate-map mean5`, which
  uses the shipped `extract_lesion_candidates`, identical rule to paper A's `v03_candidates`). FLAIR
  and T1 are **not** used (no FLAIR families in v3.2; §5).
* Labels: one-to-one Hungarian, IoU > 0 (primary). Every control candidate is FALSE.
* **Gate V1 (reproduction; stop if failed):** (a) M / L10 / external candidate and false counts equal
  the v3.1 mean5 cache (table above) and their GR features equal it within 1e-6; (b) the control
  candidates equal paper A's ensemble arm: same count in each of the 100 controls (total 263, 85
  scans with ≥ 1) and, matched within a scan by score order, |Δ score| ≤ 0.003 and equal volume.
* LST-AI maps: M (P49_T2 has none: empty T1 → F9 imputed), L10, C. None for the external sites.

## 4. Splits (subject-disjoint everywhere)

* **1-mm cross-fit (K = 5):** M patients → 5 folds (seeded permutation, round-robin, seed
  SEED + 200), L10 patients → 5 folds (SEED + 201), the 100 controls → 5 folds of 20 subjects
  (SEED + 202). Fold k: test = MS patients of fold k ∪ controls of fold k; train = everything else in
  the 1-mm pool. Every 1-mm candidate gets one out-of-fold score; MS-only models use the same MS folds
  (they ignore controls), so all comparisons are paired.
* **External:** models trained on **all** of M ∪ L10 (∪ all 100 controls for "+C" models) score the
  three external sites, exactly as v3.1 held them out.
* **Healthy calibration rotation (S-CAL):** for test control fold k, calibration = control folds
  k+1, k+2 (40 subjects), training controls = folds k+3, k+4 (40), MS training = MS folds ≠ k.
* Assertions in code: no patient / subject in two roles of any split; no external candidate in any
  training or calibration set.

## 5. Features and models

* `GR` (v3.1 grid-robust set, 14): `prob_mean, prob_max, prob_std, prob_q90, log_volume_mm3,
  ps_surv_075, ps_surv_090, ps_log_merge_025, ps_log_merge_010` + **F8 fold disagreement**
  `ens_mean, ens_std, ens_frac_detect, ens_voxvar_mean, ens_mi`, all on the mean5 candidate.
* `GR-noVOL` = GR without `log_volume_mm3` (the only physically scaled feature; control volumes are
  template-space) — confound sensitivity K4.
* `GRL` = GR + **F9 LST-AI agreement** (`lst_mean, lst_max, lst_frac_ge05, lst_detect,
  lst_local_dice`, `lst_mstd`). **Flag: LST-AI agreement leaks site** (v3.1 H4: cohort identity
  0.637, not below FLAIR contrast). GRL models are secondary, 1-mm only (no external LST-AI maps), and
  **never enter a decision rule**.
* FLAIR families F1/F3/F4/F6 are **excluded** (v3 site signature 0.70–0.98; control FLAIR is
  template-normalised and differently pre-processed).
* Scores: **ENS-RAW** = `prob_mean` on the mean5 candidate (the shipped ensemble score, no model);
  **DIS-RAW** = −`ens_std` (no model; a priori direction: more fold disagreement = less lesion-like);
  **GR-LR** (MS-only training, = the v3.1 detector); **GR+C-LR** (MS + control training; **primary
  model**); GR+C-GB; GR+C-noVOL-LR; GRL-LR (MS-only) and GRL+C-LR; **GR-Conly-LR** (trained on MS TRUE
  vs control candidates only, no MS false candidates; confound test K3). LR / GB specifications
  exactly as v3 (L2 C = 0.1 with median imputation, train 1st/99th winsorisation, standardisation; GB
  depth 3, lr 0.05, 300 iterations, min leaf 30, l2 1.0). No class or cohort weights. No tuning.

## 6. Questions, endpoints and success criterion

**Q1 / primary (H1).** Does a candidate-level score trained with healthy controls separate real
lesions from healthy-control false candidates better than the ensemble mean probability?
Endpoint: lesion-level AUROC, positives = TRUE candidates of the 1-mm MS pool (M ∪ L10), negatives =
control candidates, all scores out-of-fold (§4); **GR+C-LR vs ENS-RAW** on the same candidates.
**Criterion: Δ ≥ +0.05 AND paired 95 % CI lower bound > 0.** Positive CI with Δ < 0.05 = "statistically
positive, below the practical threshold" = not met.

**Key secondaries (each decided by its paired 95 % CI):**
* **H2 — beyond the MS-trained detector:** Δ(GR+C-LR − GR-LR) on the H1 endpoint; met if CI lower > 0.
* **H3 — healthy false candidates at fixed sensitivity:** for each score, τ = 10th percentile
  (`numpy` method "lower") of its out-of-fold scores over the 1-mm MS TRUE candidates (≥ 90 % of real
  lesions kept); FPS = mean over the **100** controls of the number of candidates with score ≥ τ
  (controls without candidates count as 0); also the share of controls with ≥ 1. Met if
  FPS(GR+C-LR) / FPS(ENS-RAW) ≤ 0.75 AND the CI upper bound of FPS(GR+C-LR) − FPS(ENS-RAW) < 0.
  τ and FPS are recomputed inside every bootstrap resample.
* **H4 — no loss on unseen MS sites:** pooled external AUROC (TRUE vs FALSE), GR+C-LR (trained on
  M ∪ L10 ∪ C) vs GR-LR (M ∪ L10): non-inferior if the CI lower bound of Δ > −0.01. Also vs ENS-RAW.
  Descriptive companion (Q2, "fewer false candidates without losing sensitivity"): at the deployable
  threshold τ_dep = 10th percentile ("lower") of the model's in-sample scores over all 1-mm MS TRUE
  candidates, external candidate sensitivity and external false candidates per scan, paired Δ vs
  GR-LR and ENS-RAW (bootstrap over external patients, τ_dep fixed).

**Secondary (descriptive, no multiplicity correction):**
* S1 H1 endpoint per MS cohort (M-true vs C; L10-true vs C) and for every score of §5 (incl. DIS-RAW,
  GB, GRL models — the latter flagged).
* S2 1-mm MS-only out-of-fold AUROC (TRUE vs MS FALSE) and "all negatives" (TRUE vs MS FALSE ∪ C):
  does training with controls cost anything within the 1-mm MS data?
* S3 per external site AUROC for ENS-RAW, GR-LR, GR+C-LR, GR-Conly-LR.
* **S-CAL — healthy-calibrated threshold (Q2, "controls for calibration"):** in the rotation of §4,
  per calibration control i, M_i = its maximum candidate score (−∞ if none); n = 40; τ_α = the
  ⌈(n + 1)(1 − α)⌉-th smallest M_i (+∞ if that exceeds n); a test scan is flagged if any candidate
  scores > τ_α. For exchangeable healthy scans this guarantees P(flagged) ≤ α. For α ∈ {0.1, 0.2} and
  ENS-RAW, GR-LR, GR+C-LR: realised share of the 100 held-out controls flagged (exact CP interval),
  false candidates per control scan, and the price in sensitivity: share of out-of-fold 1-mm MS TRUE
  candidates and of external TRUE candidates (averaged over the 5 rotations) scoring > τ_α, external
  false candidates per scan.
* S-REG region breakdown: H1 AUROC with the control candidates restricted to paper A's
  periventricular (PV) vs non-PV labels (matched by scan, score within 0.003, equal volume).

## 7. Confound and leakage checks (pre-registered; K3 is decisive for the app)

The controls differ from the MS training scans in three ways at once — healthy, one site (SibBMS),
template-normalised geometry — and every control candidate is a negative. A model trained with
controls can therefore score them low by **recognising the cohort** (resampling smoothness of the
FLAMeS map, template-scaled volumes, site) rather than by judging lesion-ness, and the H1 endpoint
(positives all MS, negatives all controls) would reward that. Checks:

* **K1 integrity:** subject / patient disjointness asserted in every split; control subjects never
  in train and test of the same fold; external candidates never in training / calibration; feature
  code takes no ground truth (existing unit tests).
* **K2 cohort-identity probe (the confound, measured):** out-of-fold LR (the §4 folds) separating
  **control candidates from MS FALSE candidates** (M ∪ L10) — both are false, so lesion status cannot
  help — per family: GR, GR-noENS (`prob_*`, persistence, volume), F8, F9 (+`lst_mstd`),
  `log_volume_mm3` alone, `prob_mean` alone. AUROC with stratified cluster-bootstrap CI. Geometry
  dose: the same probe for M-false vs C (MSLesSeg is MNI-affine-scaled, like the template) and L10-false
  vs C (Ljubljana is rigidly placed, native size), and the within-MS reference M-false vs L10-false.
  Reading fixed now: identity AUROC ≤ 0.70 = "controls no more identifiable than a second MS site"
  (v3.1 M vs L10: F8 0.502, GR-noENS 0.638); > 0.70 = "controls identifiable — confound possible".
* **K3 transfer test (decisive):** GR-Conly-LR never sees an MS false candidate. Scored out-of-fold
  on the held-out 1-mm MS candidates (TRUE vs MS FALSE), and (trained on all 1-mm data) on the
  external sites. If what controls teach is lesion-ness, it must also reject MS false candidates:
  **transfer = Δ AUROC(GR-Conly-LR − ENS-RAW) on held-out 1-mm MS with CI lower bound > 0.**
  K3b (upper bound of what cohort recognition alone can do): the K2 GR probe (trained on MS FALSE vs
  controls, never on a true lesion), scored out-of-fold on the H1 endpoint (MS TRUE vs controls).
* **K4 geometry sensitivity:** H1 with GR+C-noVOL-LR.
* **K5 shuffle-label null:** 20 permutations of the training labels within each cross-fit training
  set, GR+C-LR, H1 AUROC; flagged if the mean exceeds 0.55.
* **K6 independent re-implementation (before any write-up):** a separate short script
  (`check_v32_independent.py`) recomputes (a) the control candidates from the raw fold maps with its
  own labelling and volume rule and its own mean-probability and across-fold-SD values; (b) the H1
  AUROC of ENS-RAW and GR+C-LR with its own pairwise Mann–Whitney count and its own refit of GR+C-LR
  (scikit-learn pipeline written independently) on the same folds; (c) H3 FPS. Candidates and
  counts must match exactly, AUROC within 0.002, FPS within 0.02. Any mismatch stops the write-up and
  goes to §11.
* **K7** bootstrap seed stability of the H1 Δ (3 seeds). **K8** blindness split: H1 on the 30 August
  controls vs the 70 others (ENS-RAW is not blind on any of them; learned scores are). **K9** H1 and
  H3 without sub-075 (paper A QC flag: HD-BET mask with extra-cerebral tissue).

## 8. Decision rules for the app (research input; no app code is changed by v3.2)

* **A learned, healthy-aware re-scorer (GR+C-LR) may be proposed** — only as a future, dark research
  feature behind a new SRS requirement, RMF hazard review and code review (Class C) — **only if** H1
  is met AND H3 is met AND H4 is non-inferior AND the confound gate passes: K3 transfer positive (or
  K2 identity ≤ 0.70 for GR). Even then it is evidence from one site, template-normalised images and
  a non-commercial licence: no product claim until replicated on native-space controls from another
  site and the licence is clarified.
* **H1 met but gate failed:** not shippable; the result is reported as (at least partly) cohort
  recognition, and the app keeps the v3.1 decision.
* **H1 not met:** no learned model; the app keeps the 5-fold ensemble + fold disagreement.
* **Fold disagreement display:** the app may describe disagreement as "also higher on false marks in
  healthy brains (research, one site)" only if DIS-RAW's AUROC on the H1 endpoint has a CI lower bound
  > 0.5; otherwise no healthy-brain statement about disagreement.
* **Healthy-calibrated operating point (S-CAL):** may be described in the app research spec (not the
  product) only if its realised held-out false-alarm share is ≤ α + 0.05 at both α, and always together
  with its measured sensitivity cost on MS lesions and the one-site / template / non-commercial caveats.
* **LST-AI agreement:** never a decision input (site leak); reported only.
* Paper A's healthy false-alarm and DIS numbers stay the source for any app statement on those topics.

## 9. Statistics

AUROC = Mann–Whitney (ties averaged). CIs: 95 % percentile, cluster bootstrap B = 2000, clusters =
MS patients (M patients, L10 patients; PediMS children) and control subjects, stratified by cohort /
site; paired differences on the same resamples; for H3 the resampling covers all 100 controls
(including those without candidates) and the MS patients, with τ recomputed per resample. Exact
Clopper–Pearson intervals for shares of 100 controls. Bootstrap seeds SEED + 300 + analysis offset.
Model refit variance is not in the CIs (stated limitation; v3.1 B5 showed it small for GR-LR).

## 10. Outputs

Code: `research/lesion_detector_v3/` — `inventory_v32.py` (gate V0, this commit),
`build_features.py --candidate-map mean5 --no-flair --controls-root R` (feature cache with the 100
controls; options added after this commit, before any control feature is computed), `evaluate_v32.py`
(this protocol), `check_v32_independent.py` (K6). Records: `docs/research/records/2026-10-24_lesion_detector_v32_*.json`
(+ `_output.txt`) with input and cache SHA-256. Report: `docs/research/lesion-detector-v3/RESULTS-v3.2.md`.
Data stay outside the repository (scratch; deleted after the run).

## 11. Deviations log

(none at pre-registration, commit 3c24977)

* **D1 (2026-10-24, BEFORE any control feature or outcome; found in the dry run on a synthetic
  random-feature cache).** Pooling the out-of-fold scores of 5 different models adds fold-specific
  offsets, which biases a pooled AUROC **below 0.5** when the signal is weak (the v3 D4 mechanism,
  still present with cohort-stratified folds because candidates per patient vary). On 12 synthetic
  random-feature caches the K2 probe gave pooled AUROC 0.470 (GR), 0.440 (F8), 0.419 (`prob_mean`),
  versus 0.502 / 0.492 / 0.498 for the **mean of the within-fold AUROCs**. A downward bias makes the
  K2 reading "≤ 0.70 = no more identifiable than a site" too easy to pass, so **the K2 decision uses
  the fold-wise mean AUROC** (cluster bootstrap, clusters keep their fold); the pooled value is
  reported next to it. For H1 and K3 the same bias works *against* the learned models (conservative),
  so the pre-registered pooled endpoints are kept unchanged and the fold-wise versions are added as
  sensitivity analyses (K10 for H1; K3 fold-wise). No other change.
* **Execution (2026-10-24, after the run):** the feature cache was built once and `evaluate_v32.py`
  ran once, unchanged from commit 6606cc6; gate V1 passed; the K6 independent check matched exactly.
  No deviation from the registered analyses beyond D1.
* **Post-hoc additions, made AFTER the outcomes were seen, labelled as such:** `posthoc_checks_v32.py`
  (fold disagreement of control vs MS candidates within probability and size bands; healthy false
  candidates per scan at 80 / 95 / 100 % sensitivity). Descriptive only; no decision uses them.
