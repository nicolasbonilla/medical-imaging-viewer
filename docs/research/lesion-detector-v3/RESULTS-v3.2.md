# Lesion-level false-positive detector v3.2 — results with 100 healthy controls (2026-10-24)

**Status:** research only, investigational, not wired to any product path. Pre-registered in
[`PROTOCOL-v3.2.md`](PROTOCOL-v3.2.md) (commit 3c24977, before any feature or score of a control
candidate existed); evaluation code and deviation D1 committed before the run (6606cc6, dry run on a
synthetic random-feature cache only). Records (`docs/research/records/2026-10-24_lesion_detector_v32_*`):
`_inventory.json` (gate V0), `_feature_cache_meta.json` (input SHA-256, combined `3110e6e9…`; cache
`a14d36ad…`), `_evaluation.json` + `_output.txt`, `_independent_check.json` (K6), `_posthoc_checks.json`
(post hoc, labelled). Candidates: 5-fold **mean** FLAMeS map (as deployed). Controls: SibBMS, one
site, template-normalised, CC BY-NC-SA 3.0 (research only).

## Verdict

* **Pre-registered primary criterion: NOT MET.** Real 1-mm MS lesions vs healthy-control candidates
  (out-of-fold, 2966 true vs 263 control candidates): grid-robust model trained with controls (GR+C-LR)
  **0.822 [0.787, 0.857]** vs the ensemble mean probability **0.805 [0.764, 0.846]**, **Δ +0.017
  [+0.005, +0.030]** — statistically positive, far below the 0.05 practical threshold.
* **Healthy false candidates at 90 % sensitivity: no reduction.** Ensemble mean: **1.02 false
  candidates per healthy scan [0.72, 1.35]**, 49 % of controls with ≥ 1; GR+C-LR 0.97 (ratio 0.95,
  Δ −0.05 [−0.13, +0.09]). H3 not met.
* **Unseen MS sites: no loss, no gain.** Pooled external AUROC GR+C-LR 0.810 vs GR-LR 0.809,
  Δ +0.001 [−0.002, +0.003] (non-inferior); fewer false candidates or more sensitivity: neither.
* **The confound is real and strong.** Among *false* candidates only, a classifier tells healthy-control
  candidates from MS-patient candidates with fold-wise AUROC **0.848 [0.806, 0.882]** (grid-robust
  features; 0.813 from fold disagreement alone) — versus 0.55 between the two MS sites. A model that
  learns from controls only (MS true vs control candidates) reaches 0.914 on controls but **0.650 on
  held-out MS false candidates (Δ −0.168 [−0.202, −0.134] vs the ensemble mean)** and 0.651 on the
  unseen sites: what the controls teach does **not** transfer to MS false positives. A pure
  "cohort detector" that never saw a true lesion separates MS lesions from control candidates with
  AUROC 0.833 — as well as any lesion model. **Confound gate: failed.**
* **The v3.1 learned detector is worse than the plain ensemble on healthy brains**: at 90 %
  sensitivity GR-LR (MS-trained) gives **1.31 false candidates per healthy scan vs 1.02**
  (Δ +0.29 [+0.13, +0.41]; 63 % vs 49 % of controls with ≥ 1). This independently supports the v3.1
  decision not to ship it.
* **One positive, pre-registered secondary:** fold disagreement alone (no model) separates real lesions
  from healthy-control candidates better than the ensemble mean (0.852 vs 0.805, Δ +0.047
  [+0.033, +0.062]) although it is *worse* on MS false candidates (0.800 vs 0.817). Whether this is a
  property of healthy-brain false positives or of the SibBMS site cannot be decided with one site.

## 1. Data and gates

| Set | Scans / units | Candidates (false) |
|---|---|---|
| MSLesSeg (M) | 115 / 75 patients | 3788 (1257) |
| Ljubljana-10 (L10) | 10 / 10 | 517 (82) |
| **SibBMS controls (C)** | **100 / 100 subjects** | **263 (263) in 85 scans** |
| MS3SEG / Muslim / PediMS (external) | 100 / 51 / 28 (9 children) | 3402 (1162) / 1540 (568) / 1110 (321) |

* Gate V0 (integrity, before pre-registration): 1000 control files, one grid, all-zero masks, LST-AI
  hashes = manifest, 0 problems.
* Gate V1a: MS and external candidates identical to the v3.1 mean5 cache, labels equal, GR features
  max |Δ| 3.5 × 10⁻⁷. Gate V1b: control candidates identical to paper A's ensemble arm (263 in 85 of
  100, per-scan counts equal, max |Δ score| 0.0, volumes equal). **Passed.**
* Folds: 5 × (15 M patients + 2 L10 patients + 20 controls); every split asserted subject-disjoint.

## 2. Primary and key secondaries (out-of-fold, AUROC [95 % CI])

**H1 — real 1-mm MS lesions vs healthy-control candidates** (Δ = paired difference):

| Score | AUROC | Δ vs ensemble mean | Δ vs GR-LR |
|---|---|---|---|
| Ensemble mean probability (ENS-RAW, shipped) | 0.805 [0.764, 0.846] | — | +0.010 [−0.001, +0.021] |
| Fold disagreement alone (DIS-RAW = −SD across folds) | 0.852 [0.821, 0.883] | +0.047 [+0.033, +0.062] | +0.057 |
| GR-LR (v3.1 detector, MS-trained) | 0.795 [0.757, 0.832] | −0.010 [−0.021, +0.001] | — |
| **GR+C-LR (primary, trained with controls)** | **0.822 [0.787, 0.857]** | **+0.017 [+0.005, +0.030]** | +0.027 [+0.022, +0.033] |
| GR+C-GB | 0.858 [0.831, 0.882] | +0.053 [+0.028, +0.077] | +0.063 |
| GR+C without volume (K4) | 0.808 [0.768, 0.848] | +0.003 [−0.004, +0.011] | +0.013 |
| GRL-LR (+ LST-AI, MS-trained) † | 0.846 [0.812, 0.879] | +0.041 [+0.024, +0.061] | +0.051 |
| GRL+C-LR (+ LST-AI, with controls) † | 0.871 [0.838, 0.902] | +0.066 [+0.047, +0.087] | +0.076 |
| GR-Conly-LR (controls as the only negatives; K3) | 0.914 [0.890, 0.935] | +0.110 [+0.081, +0.139] | +0.120 |

† LST-AI agreement leaks site (v3.1) and is excluded from every decision.
Criteria: **H1 not met** (Δ +0.017 < 0.05); **H2 met** (+0.027 [+0.022, +0.033]) but only because
the MS-trained detector is *below* the ensemble on controls; fold-wise version (K10): Δ +0.021
[+0.008, +0.032], same reading.

**H3 — false candidates per healthy scan, threshold keeping 90 % of real 1-mm MS lesions:**

| Score | False / healthy scan | Controls with ≥ 1 | Δ vs ensemble mean |
|---|---|---|---|
| Ensemble mean | 1.02 [0.72, 1.35] | 49 % [39, 61] | — |
| Fold disagreement alone | 0.93 [0.67, 1.21] | 48 % | −0.09 [−0.23, +0.02] |
| GR-LR (v3.1 detector) | **1.31 [0.95, 1.62]** | **63 %** | **+0.29 [+0.13, +0.41]** |
| **GR+C-LR** | **0.97 [0.70, 1.34]** | 49 % | **−0.05 [−0.13, +0.09]** (ratio 0.95) |
| GRL+C-LR † | 0.84 [0.57, 1.13] | 43 % | −0.18 [−0.32, −0.07] |

**H3 not met** (ratio 0.95 > 0.75; CI includes 0). For reference, with no threshold (every candidate
shown) the ensemble gives 2.63 per healthy scan (paper A); post hoc, at 80 / 95 % sensitivity 0.73 / 1.62.

**H4 — unseen MS sites (pooled MS3SEG + Muslim + PediMS, 6052 candidates, 160 patients):** ensemble
mean 0.796 [0.782, 0.812]; GR-LR 0.809 [0.795, 0.824]; **GR+C-LR 0.810 [0.797, 0.824], Δ vs GR-LR
+0.001 [−0.002, +0.003] → non-inferior**; GR-Conly-LR 0.651 [0.627, 0.677]. Per site the same
(GR+C-LR 0.813 / 0.799 / 0.821). Deployable threshold (10th percentile of training true lesions):
GR+C-LR vs GR-LR external sensitivity −0.006 [−0.013, +0.001], false candidates per scan −0.10
[−0.28, +0.11]: **adding controls to training neither removes false candidates nor costs sensitivity
on unseen MS sites.**

## 3. The confound — controls are recognisable (K2, K3, K4)

**K2 cohort-identity probe** (false candidates only, so lesion status cannot help; fold-wise AUROC per
D1, 0.5 = not recognisable):

| Family | MS false vs controls | M false vs controls | L10 false vs controls | M false vs L10 false (reference) |
|---|---|---|---|---|
| Grid-robust (GR) | **0.848 [0.806, 0.882]** | 0.844 | 0.855 | 0.550 [0.469, 0.656] |
| Without fold disagreement | 0.740 [0.700, 0.773] | 0.736 | 0.810 | 0.568 |
| Fold disagreement (F8) | **0.813 [0.767, 0.851]** | 0.806 | 0.811 | 0.535 |
| LST-AI agreement | 0.652 [0.608, 0.701] | 0.644 | 0.644 | 0.518 |
| Volume alone | 0.608 | 0.601 | 0.663 | 0.561 |
| Mean probability alone | 0.543 [0.485, 0.597] | 0.541 | 0.574 | 0.547 |

* Controls are far more identifiable (0.85) than a second MS site (0.55). Pre-registered reading:
  > 0.70 → **confound possible**.
* **No geometry "dose":** MSLesSeg (MNI-affine-scaled, like the template) and Ljubljana (rigid, native
  size) are equally separable from the controls (0.84 vs 0.86), so brain-size normalisation alone does
  not explain it; site (scanner, protocol, template resampling) and healthy status remain confounded.
* **K3 transfer test (decisive): failed.** GR-Conly-LR on held-out 1-mm MS: 0.650 vs 0.817, Δ −0.168
  [−0.202, −0.134] (fold-wise −0.150 [−0.180, −0.119]); on the unseen sites 0.651 vs 0.796.
* **K3b:** the K2 probe — trained only to tell MS false candidates from control candidates, never on a
  true lesion — scores the H1 endpoint at **0.833 [0.794, 0.866]**, above the ensemble (0.805) and
  equal to GR+C-LR (Δ +0.011 [−0.040, +0.058]). The H1 endpoint can be "won" by recognising the
  cohort.
* **K4:** without the template-scaled volume feature the GR+C-LR gain vanishes (+0.003 [−0.004,
  +0.011]).
* **Confound gate (§8): failed** (K2 0.848 > 0.70 and K3 negative). Even the learned scores that beat
  the 0.05 threshold on controls (GB, LST-AI with controls, controls-only) cannot be read as better
  lesion judgement.

## 4. Other secondaries

* **S1 per cohort:** M-true vs controls: ensemble 0.804, disagreement 0.849, GR+C-LR 0.826; L10-true vs
  controls: 0.810, 0.871, 0.801 (GR-LR 0.773, Δ −0.036 [−0.049, −0.023]).
* **S2 within 1-mm MS (true vs MS false):** ensemble 0.817 [0.797, 0.837], GR-LR 0.824, GR+C-LR 0.823
  (Δ +0.005 [−0.002, +0.013]) — training with controls costs nothing within MS data; fold disagreement
  alone 0.800 (Δ −0.017 [−0.026, −0.009]).
* **S-CAL — threshold calibrated on 40 healthy scans (rotation of 5; held-out 100):**

| α | Score | Held-out controls flagged | 1-mm MS lesions still shown | Unseen-site lesions shown | Unseen-site false / scan |
|---|---|---|---|---|---|
| 0.1 | Ensemble mean | 8/100 [3.5, 15.2] % | 0.156 [0.117, 0.198] | 0.234 | 0.51 |
| 0.1 | GR-LR | 8/100 | 0.217 [0.190, 0.248] | 0.317 | 0.45 |
| 0.1 | GR+C-LR | 8/100 | 0.233 [0.204, 0.267] | 0.344 | 0.52 |
| 0.2 | Ensemble mean | 17/100 [10.2, 25.8] % | 0.324 [0.278, 0.376] | 0.412 | 1.01 |
| 0.2 | GR-LR | 16/100 | 0.379 [0.342, 0.420] | 0.498 | 1.14 |
| 0.2 | GR+C-LR | 18/100 | 0.410 [0.373, 0.451] | 0.530 | 1.30 |

  The healthy false-alarm control works as designed (all within α + 0.05), but the price is severe:
  to keep ≤ 10 % of healthy scans free of any mark, only **16–23 % of real MS lesions** stay visible
  (thresholds ≈ 0.94–0.97 on the ensemble mean). The GR+C-LR advantage here is exposed to the same
  cohort confound (calibration and test controls share the site).
* **S-REG (paper A regions):** periventricular control candidates (165): ensemble 0.818, disagreement
  0.864, GR+C-LR 0.818; other regions (98): 0.783, 0.833, 0.829.

## 5. Adversarial self-check

| Check | Result |
|---|---|
| K1 integrity | subject / patient disjointness asserted in every split; external never trained or calibrated on |
| K5 shuffle-label null (20) | H1 mean 0.477 (0.33–0.60): not flagged |
| **K6 independent re-implementation** | own union-find labelling + float64 mean: 263 candidates in 85 controls, all sizes / scores / SDs equal; own folds + own scikit-learn refit + pairwise count: AUROC 0.8048 / 0.8220 (= record); H3 1.02 / 0.97 (= record). **Passed** |
| K7 bootstrap seeds | Δ +0.0172, CI [+0.005, +0.030] / [+0.005, +0.030] / [+0.005, +0.031] |
| K8 blindness split | 30 August controls: ensemble 0.838, GR+C-LR 0.852; 70 others: 0.793, 0.811 — same direction |
| K9 without sub-075 | H1 Δ +0.017 [+0.004, +0.031]; H3 0.97 vs 1.02 — unchanged |
| K10 fold-wise H1 (D1) | ensemble 0.808, GR+C-LR 0.828 (Δ +0.021 [+0.008, +0.032]), disagreement 0.856 |

## 6. Post-hoc checks (not pre-registered; `posthoc_checks_v32.py`)

* **Why does fold disagreement separate controls?** At equal *size*, healthy-control candidates have
  about twice the across-fold SD of MS false candidates (10–30 mm³: median 0.37 vs 0.20; > 100 mm³:
  0.26 vs 0.13) and far more than true lesions (0.08 / 0.03). At equal *mean probability* the gap is
  smaller (0.7–0.8: 0.37 vs 0.27 / 0.26) and disagreement alone still separates true lesions from
  control candidates with AUROC 0.70–0.80 inside each probability band. The 5 FLAMeS folds disagree
  more on these healthy-scan marks — but the same could come from the SibBMS site.
* Healthy false candidates per scan vs sensitivity (ensemble mean / fold disagreement / GR+C-LR):
  80 %: 0.73 / 0.61 / 0.69; 90 %: 1.02 / 0.93 / 0.97; 95 %: 1.62 / 1.26 / 1.61; all candidates: 2.63.

## 7. Honest interpretation

1. **v3.2 adds no usable detector.** Training with healthy controls improves the healthy-control
   endpoint only slightly (+0.017) and does not lower healthy false marks at a clinically relevant
   sensitivity; on unseen MS sites it changes nothing.
2. **Controls are recognisable, and the recognition does not transfer.** The extra separation that
   controls teach is cohort-specific (site / template / healthy status cannot be told apart with one
   site); applied to MS patients' false candidates it is harmful (0.65). Any future "healthy-aware"
   model needs controls from **another site in native space** and, ideally, MS patients from the
   **same** site.
3. **The v3.1 learned detector would have made healthy scans worse** (more false marks at 90 %
   sensitivity). Not shipping it was right.
4. **Fold disagreement is the only signal that helps on healthy brains without being trained on
   them** — but it is also what makes the controls recognisable (0.81), so its healthy-brain value is
   plausible, not established.
5. Calibrating a threshold on healthy scans controls the healthy false-alarm rate as promised, but at
   a cost (16–41 % of lesions kept) that rules it out as a lesion-display threshold.

## 8. App-feature consequence (no app code is changed by v3.2)

**Can ship (unchanged from v3.1):** the 5-fold FLAMeS ensemble (mean map, candidates ≥ 0.5) with the
per-lesion fold-disagreement indicator. Per the pre-registered rule (DIS-RAW CI lower bound > 0.5 on
the healthy endpoint: 0.821), the research spec **may describe** the disagreement indicator as:
"In one public dataset of 100 healthy adults (one site, template-normalised images, research licence),
marks with high disagreement between the 5 model versions were more often false marks than real
lesions." It must not claim that it removes false marks, must not give a healthy-brain specificity,
and must say it is unconfirmed on other sites.

**Cannot ship:**
* any learned re-scorer — the v3.1 GR-LR (worse on healthy brains), the v3.2 GR+C-LR (H1 / H3 not
  met, confound gate failed), the GB or LST-AI variants (confounded / site-leaky);
* a "healthy-calibrated" threshold as the lesion display threshold (keeps only 16–41 % of lesions);
  it may be described in the research spec only as a measured trade-off, with the one-site,
  template-space and non-commercial caveats;
* any healthy-brain false-alarm or specificity figure derived from v3.2 in the product or its
  labelling (SibBMS licence CC BY-NC-SA; one site). Healthy false-alarm statements stay with paper A's
  numbers and rules.

**Not changed:** no SRS requirement, no RMF hazard control, no Class C module. If a future version
meets its criteria, wiring it in needs a new requirement, hazard review and code review.

## 9. Open issues / next inputs

* **De-confounding test:** run the same 5-fold FLAMeS (and LST-AI) pipeline on SibBMS **MS patients**
  (same scanner and protocol; registry: 93 patients, 10 public lesion masks). If MS-patient false
  candidates from SibBMS look like the control candidates (probe ≈ 0.5), the separation is the site;
  if not, it is healthy status. Needs the dataset access and free CPU time (research project only).
* Healthy controls from a second site, in native space (e.g. the "controls" arms of public MS
  datasets), before any healthy-brain claim.
* LST-AI agreement on the external sites (maps not available) — it is the strongest learned family on
  the 1-mm data but leaks site.
* SibBMS licence wording (CC BY vs CC BY-NC-SA) to be clarified with the authors before any number
  reaches product documentation.
