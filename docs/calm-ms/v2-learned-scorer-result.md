# CALM-MS v2 — the learned lesion scorer (corrected after adversarial round 3)

> **CORRECTION (2026-08-18, adversarial round 3).** An earlier version of this document
> claimed the learned score "survives the confident-FP scanner shift where raw probability
> collapses" and was therefore "F1 fix part 1, validated". **That claim is RETRACTED.** Two
> independent adversarial audits showed (and I reproduced) that: (a) the load-bearing shift
> test was RIGGED — it inflated only the FALSE candidates' probability features (physically
> impossible; a scanner cannot know which candidates are false) and was constructed to invert
> raw probability; (b) the headline numbers were computed on a gradient-boosting model, not
> the logistic regression that ships; (c) under a FAIR monotone shift the learned score does
> NOT beat raw probability (AUC 0.66 vs 0.74), and cross-site it does NOT restore the
> guarantee. The honest result is below; the authoritative record is
> `assets/lesion_scorer_record.json` (regenerated on the shipped model with honest protocols
> by `scripts/calm-ms/evaluate_lesion_scorer.py`). The rigged experiment
> `scripts/calm-ms/train_lesion_scorer.py` is superseded and retained only for provenance.

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

*Leakage note (2026-08-18):* MSLesSeg contains multiple longitudinal timepoints per
patient. Grouping CV by patient (leak-free, 105 patients) rather than by scan (145) lowers
the transparent poly-LR estimate only marginally, **0.801 → 0.796**, so the improvement over
raw probability (0.70) is not an artefact of longitudinal leakage. The asset builder now
groups by patient.

**3. Location and morphology carry the signal (permutation importance, top 8):**
`x_norm`, `prob_max`, `surf_to_vol`, `y_norm`, `prob_q90`, `z_norm`, `radial`, `sphericity`
— anatomical location and shape co-lead with two probability moments, confirming the
physical hypothesis: the discriminative content the scanner cannot inflate is *where* and
*what shape* a candidate is, not how confident the model is.

**4. Shift robustness — the RETRACTED claim, and the honest result.**
The original "load-bearing test" inflated only the FALSE candidates' probability features.
That is a stacked deck (a scanner cannot know which candidates are false, and the
construction inverts raw probability by definition), so its result — raw AUC 0.203 vs
learned 0.727 — is meaningless. Under a **fair** shift (a monotone confidence inflation of
ALL candidates, on the shipped LR, trained openms → tested mslesseg):

| | Raw probability | Learned score |
|---|---|---|
| No shift — TP/FP AUC | 0.736 | 0.798 |
| **Fair shift (+1.5 all candidates) — TP/FP AUC** | **0.736** (unchanged) | **0.663** (worse) |
| Fair shift — conformal FDR @α=0.20 | 0.288 (violated) | 0.068 |
| Fair shift — conformal power @α=0.20 | 0.984 | 0.066 (collapses) |

Under a fair shift the learned score does **not** beat raw probability, and neither delivers
a controlled-and-powerful guarantee cross-site: raw keeps power but violates FDR; learned
keeps FDR but its power collapses. This is the same cross-site non-exchangeability the F1
investigation identified — **a better score does not fix it.**

## Conclusion (corrected)

- **What the learned score IS:** a genuine WITHIN-DOMAIN improvement in TP/FP separability
  (patient-grouped AUC ~0.80 vs 0.70 raw), well-calibrated (ECE 0.032), with no overfitting
  (label-shuffle AUC 0.499) and location/morphology as legitimate signal (not a site-identity
  confound). Worth keeping as a component.
- **What it is NOT:** the F1 fix. It does not solve cross-site non-exchangeability
  (pooled leave-one-site-out AUC ~0.62), and its conformal power even within-domain is modest
  (~0.47 of true lesions at α=0.20). Neither a better null (F1 investigation) nor a better
  score (this) alone restores the guarantee under acquisition shift.
- **What F1 actually needs:** domain-conditional calibration **and** cross-site score
  harmonisation (ComBat-style) **and** more sites (≥3–5), validated on real mimic/scanner-shift
  cohorts — not a single silver bullet.

## Honest limitations

- Two sites, 145 cases; pooled cross-domain AUC is only ~0.62 and will not improve without
  more heterogeneous scanners.
- Location features assume correct MNI registration (a pipeline invariant); off-grid maps
  score plausibly-but-wrong — gated in production by the conformal provenance check, with a
  defense-in-depth guard recommended in the scorer itself.
- The scorer is NOT wired into the guarantee path and must not be until the above holds.
  Clinical enablement remains gated on real-cohort validation + the IEC 62366-1 study.
