# Lesion-level false-positive detector v3.1 — PRE-REGISTERED PROTOCOL EXTENSION

**Status:** pre-registration, written and committed on 2026-10-21 **before** any v3.1 feature was
computed and before any candidate on the new sites was labelled or scored. Extends
[`PROTOCOL.md`](PROTOCOL.md) (v3); everything not changed here is inherited from v3 (candidate rule,
one-to-one labels, LR/GB specifications, seed 20261017, B = 2000 patient-clustered bootstrap,
no calibration double use). Deviations go to §10.

## 1. Why v3.1, and what v3 taught us

v3 did not meet its criterion (pooled leave-one-cohort-out Δ +0.014 [−0.012, +0.041]). Its main
failure was the **site signature** of the FLAIR families (cohort-identity AUROC 0.98). v3.1 adds the
two families designed to be site-independent — **disagreement between the 5 FLAMeS folds** and
**agreement with an independent model (LST-AI)** — and, for the first time, **sites never touched by
any lesion-level analysis**: MS3SEG, Muslim, PediMS.

Honesty constraint: MSLesSeg and Ljubljana-10 were already examined in v3, so any v3.1 analysis
restricted to them is **not confirmatory** (same data, new hypothesis). The confirmatory test is on
the three new sites, which is why the v3.1 primary endpoint lives there.

## 2. Data and integrity checks done BEFORE pre-registration (no labels used)

Source: `data/cohorts/cloud-2026-10/` (manifests with checkpoint SHA-256, versions, commands).

* FLAMeS folds 0–4 run separately, no TTA, stored as uint8 (maximum storage error 0.002).
  Fold-0 parity with the August float maps over all 145 MSLesSeg + Ljubljana scans: maximum
  absolute difference **0.00224** (tolerance 0.0025); ground-truth masks identical (0 mismatches).
* LST-AI v1.2.0 (image digest in the manifest) ensemble + 3 U-Net maps on the FLAMeS grid for 114
  MSLesSeg (P49_T2 skipped: empty T1) and 30 Ljubljana scans; grids match (0 mismatches).
  LST-AI was trained on 491 in-house TUM scans (Wiltgen et al., NeuroImage: Clinical 2024; medRxiv
  10.1101/2023.11.23.23298966); public cohorts were used by its authors only as test data. Not
  independently fingerprint-verified.
* New sites (FLAMeS maps + ground truth only; **no FLAIR locally**):
  * MS3SEG — 100 scans / 100 patients, 2D axial, 0.898 × 0.898 × 6.4–7.6 mm;
  * Muslim — 51 scans / 51 patients, 2D, in-plane pixel size **estimated** (not published);
  * PediMS — 28 scans / 9 children (longitudinal), 0.75 × 0.75 × 3.9 mm.
* FLAMeS-training overlap: the released fingerprint (668 training cases, fetched from the Zenodo
  archive by HTTP range) contains **no case with any spacing ≥ 3 mm and no case with any axis < 40
  voxels**, so none of the three new sites (thick slices; Muslim's raw arrays have 18–33 slices) can
  be in FLAMeS training. MSLesSeg clean (v3); Ljubljana: with all 5 folds only patients 16–20, 26–30
  (L10) are clean.
* The SibBMS controls have only the August fold-0 maps (no 5-fold maps, no FLAIR): they cannot be
  scored by any v3.1 model and are not re-analysed (v3 S5 stands).

## 3. Candidates and labels (inherited, made grid-aware)

* MSLesSeg / Ljubljana: candidates from the **August fold-0 float maps** (identical candidate set to
  v3; reproduction gate M 3866/1348, L10 534/94).
* New sites: candidates from the **cloud fold-0 map** (uint8-stored; a voxel within 0.002 of the 0.5
  threshold may flip — disclosed).
* Volumes are **physical**: candidate and GT-lesion floor = 3 mm³ computed with the true voxel size
  (on thick slices a single voxel passes); 18-connectivity in voxel index space.
* Labels: one-to-one Hungarian, IoU > 0 (primary); IoU > 0.10 and any-voxel as sensitivity.

## 4. Features

Inherited v3 families (F1–F7, v2 features). **New in v3.1:**

* **F8 fold disagreement** (5 cloud fold maps): `ens_mean` (mean over folds of the candidate's mean
  probability), `ens_std` (across-fold SD of that mean), `ens_frac_detect` (fraction of folds with
  ≥ 50 % of the candidate at P ≥ 0.5), `ens_voxvar_mean` (mean voxelwise across-fold variance),
  `ens_mi` (mean mutual information = epistemic uncertainty).
* **F9 LST-AI agreement**: `lst_mean, lst_max, lst_frac_ge05, lst_detect, lst_local_dice` on the
  ensemble map, plus **`lst_mstd`** (across-model SD of the candidate mean over LST-AI's 3 U-Nets).
* **`log_volume_mm3`** = log(physical volume) (equals v2 `log_volume` on 1 mm grids).

**Feature sets.**
* `RAW` = fold-0 `prob_mean` (no model). `ENS-RAW` = `ens_mean` (no model; the plain 5-fold
  ensemble score).
* **`GR` (grid-robust, primary model's set; computable on every site):** `prob_mean, prob_max,
  prob_std, prob_q90, log_volume_mm3, ps_surv_075, ps_surv_090, ps_log_merge_025,
  ps_log_merge_010` + F8 (14 features). `GR-noENS` = GR without F8 (9). `ENS-only` = F8 (5).
* M/L10-only sets (FLAIR and LST-AI exist only there): `V3` (v3 primary, 42), **`V31` = V3 + F8 +
  F9** (53), `V3P+ENS+LST` = V3P + F8 + F9.

## 5. Models

As v3: LR (median imputation, train 1st/99th winsorisation, standardisation, L2 C = 0.1) primary;
GB (depth 3, lr 0.05, 300 iterations, min leaf 30, l2 1.0) secondary. No tuning.

## 6. Designs

* **External (confirmatory):** train on **all candidates of M ∪ L10** (125 scans, 85 patients);
  score MS3SEG, Muslim, PediMS. Nothing from the new sites is used for training, calibration or any
  choice. Pooled external = union of the three sites' candidates.
* **M ↔ L10 (not confirmatory, re-uses v3 data):** v3 designs (pooled LOCO, per direction,
  within-M 5-fold CV) for RAW, ENS-RAW, V3-LR, V31-LR, V3P+ENS+LST-LR, GR-LR.
* **Conformal, external:** 20 seeded splits of the M patients into train / calibration halves;
  scorer trained on M-train ∪ L10; null = FALSE candidates of M-calibration scored by that scorer;
  test = each new site. BH per scan at α ∈ {0.1, 0.2, 0.3} and FDX layer 1 (γ = α, δ = 0.1, "hc").
  RAW, ENS-RAW and GR-LR use identical calibration patients. FDR is realised, not guaranteed (no
  cross-site exchangeability).
* CIs: patient-clustered bootstrap, stratified by site for pooled statistics, B = 2000; paired
  differences on the same resamples. PediMS clusters = children.

## 7. Endpoints and success criterion

**Primary endpoint:** pooled external lesion-level AUROC (MS3SEG + Muslim + PediMS), **GR-LR**
trained on M ∪ L10, vs **RAW** on the same candidates.

**Pre-registered success criterion (primary):** Δ = AUROC(GR-LR) − AUROC(RAW) **≥ +0.05 AND the
paired 95 % CI lower bound > 0.** Positive CI with Δ < 0.05 = "statistically positive, below the
practical threshold" = not met.

**Key secondaries (each: paired 95 % CI lower bound > 0):**
* H2 — GR-LR beats the plain ensemble score: Δ(GR-LR − ENS-RAW) on pooled external.
* H3 — fold disagreement adds: Δ(GR-LR − GR-noENS-LR) on pooled external.
* H4 — the new families are less site-specific than FLAIR: site-identity separability
  |AUROC − 0.5| (M vs L10, cohort-stratified patient folds as v3 A3) of F8, and of F9, is lower than
  that of each FLAIR family (F1, F3, F4_FLAIR): paired bootstrap CI of the difference entirely < 0.
* H4b — for each new site s, separability (M vs s) of F8 is lower than that of GR-noENS.

**Secondary (descriptive):** per-site external AUROC for RAW, ENS-RAW, GR-LR, GR-noENS-LR, GR-GB,
ENS-only-LR; M ↔ L10 analyses of §6 (incl. Δ V31-LR − V3-LR, Δ V3P+ENS+LST − V3P); external
conformal power / FDR / per-scan exceedance.

## 8. Adversarial self-check (pre-registered)

* B1 shuffle-label null for the external model (20 permutations of the training labels).
* B2 integrity: no new-site candidate in any training / calibration set (assertions); features
  GT-free (unit tests).
* B3 site signature (H4/H4b) + per-site breakdown: the pooled gain must not come from one site only.
* B4 label definitions (IoU > 0.10, any-voxel) on pooled external.
* B5 model-refit variance: 50 patient-bootstrap refits of the training set, scored on pooled
  external; fraction of refits below RAW.
* B6 contamination reference: GR-LR (trained on M only) on FLAMeS-trained Ljubljana vs L10.
* B7 KS distance M vs each new site for every GR feature, among TRUE and among FALSE candidates.
* B8 resolution confound: on thick-slice sites, report the share of single-voxel candidates and the
  AUROC restricted to candidates ≥ 3 voxels (descriptive).

## 9. Outputs

Code: `research/lesion_detector_v3/` (`build_features.py --cloud-root`, `features_v3.py`,
`evaluate_v31.py`). Records: `docs/research/records/2026-10-21_lesion_detector_v31_*.json` + `.txt`.
Report: `docs/research/lesion-detector-v3/RESULTS-v3.1.md`.

## 10. Deviations log

(none at pre-registration)
