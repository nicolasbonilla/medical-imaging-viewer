# Lesion-level false-positive detector v3.1 — results (2026-10-21)

**Status:** research only, investigational, not wired to any product path. Pre-registered in
[`PROTOCOL-v3.1.md`](PROTOCOL-v3.1.md) (commit 129d2ff, before any v3.1 feature was computed);
evaluation code committed before it was run (0d339b1; dry run on a synthetic random-feature cache only).
No deviation from the pre-registered analyses. Records: `docs/research/records/2026-10-21_lesion_detector_v31_evaluation.json`
(+ `_output.txt`), `..._v31_posthoc_checks.json` (post-hoc, labelled), `..._v31_feature_cache_meta.json`.

## Verdict

* **Pre-registered primary criterion: MET.** Pooled external AUROC on three never-analysed sites
  (MS3SEG, Muslim, PediMS; 6493 candidates, 160 patients), GR-LR trained on MSLesSeg + clean
  Ljubljana: **0.832 [0.818, 0.846] vs raw fold-0 probability 0.721 [0.703, 0.740], Δ +0.111
  [+0.096, +0.125]**. H2 (beats the plain 5-fold ensemble score, 0.789): Δ +0.044 [+0.037, +0.051],
  met. H3 (fold disagreement adds): Δ +0.074 [+0.060, +0.087], met. Consistent on every site.
* **H4 met for fold disagreement, not for LST-AI.** Cohort identity (MSLesSeg vs Ljubljana) from the
  fold-disagreement family: AUROC **0.502** (no site signature) vs 0.70–0.85 for the FLAIR families.
  LST-AI agreement: 0.637, not reliably below FLAIR contrast.
* **But the post-hoc check shows most of the gain is "use the 5-fold ensemble", not the learned
  detector.** With candidates defined on the 5-fold **mean** map (how FLAMeS is actually deployed),
  the ensemble mean probability already reaches **0.796**, and GR-LR adds only **+0.013 [+0.008,
  +0.018]** (statistically positive, practically small; below the 0.05 threshold the protocol uses).
  On clean Ljubljana-10 the learned model does not beat the ensemble at all (+0.011 [−0.019,
  +0.055] with fold-0 candidates; +0.017 [−0.016, +0.042] with mean candidates).

## 1. Data (gate passed)

| Set | Scans / patients | Candidates (fold-0) | False rate | 5-fold-mean candidates (false) |
|---|---|---|---|---|
| MSLesSeg (train) | 115 / 75 | 3866 | 0.349 | 3788 (1257) |
| Ljubljana-10 (train) | 10 / 10 | 534 | 0.176 | 517 (82) |
| MS3SEG (external) | 100 / 100 | 3635 | 0.384 | 3402 (1162) |
| Muslim (external) | 51 / 51 | 1649 | 0.414 | 1540 (568) |
| PediMS (external) | 28 / 9 children | 1209 | 0.334 | 1110 (321) |

MSLesSeg / Ljubljana-10 candidates identical to v3. Fold-0 parity with the August maps ≤ 0.00224.
FLAMeS training fingerprint has no case with spacing ≥ 3 mm or an axis < 40 voxels, so the external
sites are not FLAMeS training data. Single-voxel candidates: 4.4 % (MS3SEG), 4.0 % (Muslim), 0 %
(PediMS).

## 2. Primary and key secondaries (pooled external, AUROC [95 % CI])

| Score | Pooled | MS3SEG | Muslim | PediMS |
|---|---|---|---|---|
| Raw fold-0 probability | 0.721 [0.703, 0.740] | 0.720 | 0.746 | 0.698 |
| Plain 5-fold ensemble (ENS-RAW) | 0.789 [0.774, 0.802] | 0.798 | 0.763 | 0.795 |
| **GR-LR (primary)** | **0.832 [0.818, 0.846]** | 0.839 | 0.823 | 0.825 |
| GR without fold disagreement | 0.759 [0.739, 0.780] | 0.760 | 0.776 | 0.741 |
| Fold disagreement only (LR) | 0.816 [0.802, 0.828] | 0.826 | 0.792 | 0.815 |
| GR-GB | 0.821 [0.807, 0.835] | 0.820 | 0.820 | 0.824 |

Per-site Δ (GR-LR − raw): MS3SEG +0.119 [+0.103, +0.136], Muslim +0.077 [+0.052, +0.102], PediMS
+0.127 [+0.062, +0.149]; Δ vs ensemble: +0.041, +0.060, +0.031 (all CIs > 0).

## 3. Site signature (H4 / H4b)

Cohort-identity AUROC, MSLesSeg vs Ljubljana-10 (0.5 = no site signature): fold disagreement
**0.502**; LST-AI agreement 0.637; grid-robust probability/size features 0.638; FLAIR contrast 0.700,
texture 0.756, boundary 0.855. Paired separability differences: fold disagreement minus each FLAIR
family −0.20 / −0.25 / −0.35, all CIs < 0 (**H4 met for F8**); LST-AI minus FLAIR contrast −0.063
[−0.154, +0.019] (**H4 not met for F9**). MSLesSeg vs each new site: fold disagreement less site-specific
than the other grid-robust features for MS3SEG (0.524 vs 0.699) and Muslim (0.577 vs 0.665), not for
PediMS, which is strongly identifiable by every family (children, 3.9 mm slices; AUROC 0.22–0.29).

## 4. Other secondaries

* **External conformal selection** (20 splits, MSLesSeg null), α = 0.2, BH: power raw 0.40 / 0.14 /
  0.15 → GR-LR 0.60 / 0.41 / 0.41 (MS3SEG / Muslim / PediMS). Realised FDR with raw probability
  **exceeds α** at α = 0.1 on all three sites (0.22 / 0.16 / 0.19) and at 0.2 on MS3SEG (0.22); with
  GR-LR it stays below α at every level (≤ 0.15). Per-scan exceedance remains high on MS3SEG (0.27 at
  α = 0.1).
* **MSLesSeg ↔ Ljubljana-10 (re-uses v3 data; not confirmatory):** pooled leave-one-cohort-out raw
  0.728, ensemble 0.770, GR-LR 0.786, prob-only + fold disagreement + LST-AI 0.799, V3 + new families
  0.760 (FLAIR families still hurt across cohorts). Within MSLesSeg, adding fold disagreement + LST-AI
  to the probability-only set: +0.070 [+0.053, +0.087].

## 5. Adversarial self-check

| Check | Result |
|---|---|
| B1 shuffle-label null | mean 0.506 (0.32–0.64): no leakage signature |
| B2 integrity | no external candidate in any training/calibration set (asserted) |
| B3 per site | gain present on all three sites (above) |
| B4 labels | IoU > 0.10: Δ +0.109 [+0.095, +0.123]; any-voxel: Δ +0.128 [+0.107, +0.145] |
| B5 refits (50) | 0.831 [0.828, 0.832], none below raw |
| B6 contamination | trained on MSLesSeg: Ljubljana-10 0.791, FLAMeS-trained Ljubljana 0.720 (raw 0.635) |
| B8 resolution | candidates ≥ 3 voxels: Δ +0.122 |
| **Post-hoc P1: 5-fold-mean candidates** | ensemble mean 0.796 → GR-LR 0.809, **Δ +0.013 [+0.008, +0.018]**; per site +0.011 / +0.016 / +0.019; fold disagreement alone adds +0.003 |
| Post-hoc P3: conformal, mean candidates | α = 0.2 power ensemble 0.60 / 0.43 / 0.48 → GR-LR 0.65 / 0.52 / 0.56, FDR ≈ 0.09–0.13 for both |

## 6. Honest interpretation

1. The registered success is real but mostly explained by **ensembling FLAMeS**: fold-0 false
   positives that the other folds disagree with are the bulk of what v3.1 removes. Deploying the
   5-fold ensemble (FLAMeS' default) captures most of it with no learned model.
2. On top of the ensemble, the learned grid-robust detector gives a small, consistent gain (+0.01 to
   +0.02 AUROC; conformal power +0.05 to +0.09 at α = 0.2). Whether that justifies a learned component
   in a Class C path is an open question.
3. Fold disagreement is the first family with no measurable site signature; LST-AI agreement is not
   site-free.
4. The SibBMS healthy controls could not be tested (no 5-fold maps, no FLAIR); the v3 finding — FLAMeS
   false positives on healthy brains look like real lesions — remains open.

## 7. Next inputs needed

5-fold maps and HD-BET FLAIR for the 100 SibBMS controls (pending the dataset access form); a
v3.2 protocol should pre-register **5-fold-mean candidates** as the primary candidate definition and
the ensemble mean probability as the comparator.
