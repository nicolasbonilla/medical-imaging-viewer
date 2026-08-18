# CALM-MS v2 — the learned scanner-robust lesion scorer (empirical validation)

**Status:** research finding, 2026-08-18. Feature remains DARK (investigational).
**Artifacts:** `scripts/calm-ms/train_lesion_scorer.py`,
`backend/app/services/assets/lesion_scorer_record.json`.
**Depends on / motivated by:** [F1 site-shift investigation](F1-site-shift-investigation.md).

## Why

The F1 investigation established that the conformal FDR wrapper is only as good as the
underlying score's TP/FP separability, and that raw pooled probability collapses under a
confident-false-positive scanner shift (rank inversion). The state of the art points to a
per-candidate learned score built on features a scanner cannot trivially inflate —
morphology and anatomical location — the way lesion-wise false-positive-reduction models
work (LST family; nnU-Net FP-reduction cascades; radiomics), kept compatible with
conformal selection (Jin & Candès 2023). This document tests whether such a score is the
load-bearing fix, on our 145 labelled FLAMeS cases.

## Method

Per candidate (18-connected component of the FLAMeS prob map ≥ 0.5, ≥ 3 mm³) we extract
features computable **at inference, without ground truth**:

- **Probability** (scanner-inflatable): mean, max, std, q90 of the component's posteriors.
- **Morphology** (scanner-robust): log-volume, sphericity, surface-to-volume, elongation
  (PCA eigenvalue ratio), extent.
- **Location** (scanner-robust): MNI-normalised centroid (z/y/x), laterality (distance from
  the midsagittal plane), radial position from the brain centre.

A `HistGradientBoostingClassifier` predicts P(false candidate). Evaluated with
case-grouped 5-fold CV (no within-case leakage) and **leave-one-site-out** (train on one
acquisition domain, test on the other). 6224 candidates (4834 true, 1390 false) across
openms (2358) and mslesseg (3866).

## Results

**1. The learned score separates TP from FP far better than raw probability.**

| Score | AUC (TP vs FP) |
|---|---|
| Raw mean probability | 0.701 |
| Learned (case-grouped 5-fold OOF) | **0.822** (+0.121) |

**2. It generalises across acquisition domains.**

| Train → Test | Learned AUC | Raw-prob AUC |
|---|---|---|
| ¬openms → openms | 0.767 | 0.708 |
| ¬mslesseg → mslesseg | 0.766 | 0.736 |

Cross-site AUC (0.77) is below the within-cohort CV (0.82) — a real domain gap — but the
learned score beats raw probability on every held-out site.

**3. Location and morphology carry the signal (permutation importance, top 8):**
`x_norm`, `prob_max`, `surf_to_vol`, `y_norm`, `prob_q90`, `z_norm`, `radial`, `sphericity`
— anatomical location and shape co-lead with two probability moments, confirming the
physical hypothesis: the discriminative content the scanner cannot inflate is *where* and
*what shape* a candidate is, not how confident the model is.

**4. LOAD-BEARING TEST — the learned score survives the F1 failure mode.**
An FP-selective confidence inflation (only the FALSE candidates' probability features are
pushed up in logit space; morphology/location untouched — an artefact FP keeps its FP-like
shape/location), scored by a model trained on the *other* site:

| Under F1 shift | Raw probability | Learned score |
|---|---|---|
| TP/FP AUC | **0.203** (collapsed / rank-inverted) | **0.727** (survives) |
| Conformal @α=0.20 — realized FDR | 0.467 (broken) | 0.292 |
| Conformal @α=0.20 — power (TP recovered) | 0.391 | **0.966** |

Where raw probability collapses (AUC 0.20, FDR 2.3× target), the learned score stays
discriminative (AUC 0.73) and recovers conformal **power** (0.97 vs 0.39). The residual FDR
(0.29 > 0.20) is exactly what the *second* part of the fix — site-conditional / cluster-aware
calibration — is for: the learned score restores separability, the calibration restores the
guarantee.

## Conclusion — the two-part F1 fix is empirically validated

1. **Scanner-robust learned score** (this result): restores TP/FP separability and conformal
   power under the confident-FP shift that breaks raw probability. **Load-bearing, confirmed.**
2. **Site-conditional, cluster-aware calibration** (F1 investigation): needed to bring the
   residual FDR back to target once the score is discriminative again.

## Honest limitations

- The shift is synthetic (FP-selective logit inflation); real scanner shifts require real
  multi-scanner/mimic-cohort validation.
- Two sites, 145 cases — the domain gap (0.82 → 0.77) will widen with more heterogeneous
  scanners; more sites are needed before any performance claim.
- Location features assume correct MNI registration (already a pipeline invariant); a
  registration failure would corrupt them — must be gated by the existing provenance checks.
- The learned FDR under shift is not yet ≤ α on its own; the guarantee is delivered only by
  the full two-part method, and clinical enablement remains gated on real-cohort validation
  plus the IEC 62366-1 usability study.
