# Lesion-level false-positive detector v3 — results (2026-10-17)

**Status:** research only, investigational, not wired to any product path. Pre-registered in
[`PROTOCOL.md`](PROTOCOL.md) (commit 59cc796, before any feature or result existed); evaluation code
committed before it was run (6840ef3, ed3c858, b87f267, e5415e5). Deviations D1–D4 are logged in the
protocol, all made before any outcome was seen. Records:
`docs/research/records/2026-10-17_lesion_detector_v3_evaluation.json` (+ `_output.txt`),
`..._posthoc_checks.json` (post-hoc, labelled), `..._feature_cache_meta.json` (input SHA-256,
combined digest `d2727030…0b64b6`; cache SHA-256 `f8e85aac…bb085`).

## Verdict

* **Pre-registered primary criterion: NOT MET.** Pooled leave-one-cohort-out AUROC, V3-LR 0.742
  [0.716, 0.772] vs raw probability 0.728 [0.703, 0.754]: **Δ = +0.014 [−0.012, +0.041]** (needed
  Δ ≥ 0.05 with CI > 0).
* Key secondary H2 (vs v2 as shipped) met: Δ = +0.104 [+0.073, +0.140] — **but a post-hoc check shows
  this is mostly a model-specification effect**: against v2's features with the *same* LR the new
  families add only +0.020 [−0.004, +0.047] pooled.
* What is real: a **within-domain** gain (MSLesSeg patient-grouped CV 0.835 vs 0.735 raw; conformal
  power at α = 0.2 0.47 vs 0.14) and a **robust MSLesSeg → clean-Ljubljana transfer gain** (0.779 vs
  0.698, Δ +0.081 [+0.022, +0.142]; 50/50 model refits above raw). The reverse direction (train on 10
  Ljubljana scans) is not reliable (58 % of refits fall below raw).
* Healthy controls defeat every probability-map-only score: FLAMeS false positives on healthy brains
  are *more* confident and lesion-shaped than true lesions (AUROC true-lesion vs control-candidate
  0.37 raw, 0.43 v3-prob-only), and the conformal selection calibrated on MSLesSeg still flags ~1
  false lesion per healthy scan at α = 0.2.

## 1. Data actually used (reproduction gate passed exactly)

| Set | Scans / patients | Candidates | FALSE (one-to-one) | False rate | Fragment share of FALSE |
|---|---|---|---|---|---|
| MSLesSeg (M) | 115 / 75 | 3866 | 1348 | 0.349 | 0.129 |
| Ljubljana clean-10 (L10) | 10 / 10 | 534 | 94 | 0.176 | 0.287 |
| SibBMS controls (C) | 30 / 30 | 83 | 83 | 1.000 | — |

Counts match the paper-A v0.2 cohort table exactly (same candidate and label code).
Data notes found before modelling: MSLesSeg P49_T2 ships an empty T1 (D3; only the exploratory T1
family affected); the ventricle proxy found no CSF-like voxels in MSLesSeg P12_T2/T3/T4 (feature NaN,
imputed); controls have no local FLAIR, so only probability-map families apply to them.

## 2. Primary endpoint — pooled leave-one-cohort-out (4400 candidates, 85 patients)

| Score | AUROC [95 % CI] | Δ vs raw [95 % CI] | Δ vs v2 shipped |
|---|---|---|---|
| Raw mean probability | 0.728 [0.703, 0.754] | — | +0.090 [+0.054, +0.125] |
| **V3-LR (primary)** | **0.742 [0.716, 0.772]** | **+0.014 [−0.012, +0.041]** | +0.104 [+0.073, +0.140] |
| V3-GB | 0.689 [0.662, 0.718] | −0.040 [−0.072, −0.007] | +0.050 |
| V2 as shipped (poly-2 LR + MNI) | 0.639 [0.611, 0.668] | −0.090 [−0.125, −0.054] | — |
| V2 features, v3 LR spec | 0.722 [0.686, 0.759] | −0.006 [−0.041, +0.028] | +0.083 |
| V3 prob-map-only (V3P-LR) | 0.714 [0.685, 0.748] | −0.014 [−0.042, +0.012] | +0.076 |

v2's honest number is reproduced under the clean protocol (0.639 here vs 0.624 in the August
record). The pooled metric sits **below both per-direction AUROCs** for every learned model because
it also ranks candidates across two different models calibrated to different base rates: the
M-trained model gives L10 candidates (18 % false) a mean score of 0.63, the L10-trained model gives M
candidates (35 % false) 0.79 (post-hoc P3). Raw probability has no training and is immune. This is a
property of the pre-registered endpoint; it is kept and the criterion is reported as not met.

## 3. Secondary endpoints

**Per direction (S2) and within cohort (S1), AUROC [95 % CI]:**

| | Raw | V3-LR | Δ V3-LR − raw | V3-GB | V2 shipped | V2-LR |
|---|---|---|---|---|---|---|
| A: train M → test L10 | 0.698 | 0.779 | **+0.081 [+0.022, +0.142]** | 0.780 | 0.741 | 0.748 |
| B: train L10 → test M | 0.735 | 0.771 | +0.036 [+0.014, +0.059]* | 0.714 | 0.664 | 0.779 |
| Within M (5-fold by patient) | 0.735 | 0.835 | **+0.100 [+0.079, +0.122]** | 0.846 | 0.822 | 0.787 |
| Within L10 (leave-one-patient-out) | 0.698 | 0.770 | +0.072 [−0.008, +0.176] | 0.742 | 0.638 | 0.722 |

\* bootstrap CI holds the fitted model fixed; refitting on resampled L10 patients (A5b) gives mean
0.727 [0.668, 0.782] and 58 % of refits below raw — **direction B is not a reliable gain**.
Direction A is: 50 refits on resampled MSLesSeg patients give 0.768 [0.741, 0.794], none below raw (P2).

**Conformal selection, within MSLesSeg, three-way patient cross-fit (no calibration double use) (S3):**

| α | method | Raw power | V3-LR power | Δ [95 % CI] | V3-GB | V2 shipped | FDR raw / V3-LR | P(scan FDP > α) raw / V3-LR |
|---|---|---|---|---|---|---|---|---|
| 0.1 | BH per scan | 0.048 | 0.242 | +0.194 [+0.138, +0.255] | 0.298 | 0.205 | 0.137 / 0.046 | 0.096 / 0.122 |
| 0.2 | BH per scan | 0.137 | 0.471 | +0.334 [+0.256, +0.407] | 0.510 | 0.448 | 0.138 / 0.078 | 0.122 / 0.070 |
| 0.3 | BH per scan | 0.236 | 0.628 | +0.392 [+0.292, +0.486] | 0.629 | 0.561 | 0.169 / 0.102 | 0.113 / 0.026 |
| 0.2 | FDX layer 1 | 0.048 | 0.230 | +0.182 [+0.105, +0.269] | 0.285 | 0.202 | 0.160 / 0.052 | 0.044 / 0.017 |

Power = selected true candidates / true candidates. Realised FDR stays below α for every learned
score; raw probability exceeds it at α = 0.1 (BH 0.137 [0.071, 0.206], 139 selections — few
selections and within-scan dependence). For FDX the controlled quantity is P(scan FDP > α) ≤ δ = 0.1,
met by all scores within MSLesSeg. Note V2 shipped is almost as good within domain (0.448 at α = 0.2): the within-domain power gain is
mostly "any learned score beats raw probability", not specifically the new families.

**Conformal across cohorts, M (train half / calibration half, 20 splits) → L10 (S4):** at α = 0.2
(BH) power raw 0.096 → V3-LR 0.151 (Δ +0.055 [−0.121, +0.199]), realised FDR 0.096 / 0.055; at
α = 0.3 0.155 → 0.264 (Δ +0.109 [−0.120, +0.297]). Positive point estimates, intervals include 0
(only 10 test scans). V3-LR's realised FDR is below α at every level; raw probability is at or above
it at α = 0.1 (BH 0.105; FDX micro-FDR 0.20 with P(scan FDP > α) = 0.17 > δ = 0.1). Realised, not
guaranteed: there is no cross-cohort exchangeability.

**Healthy controls (S5):** AUROC (L10 true lesions vs control candidates) raw 0.371 [0.277, 0.476],
V3P-LR 0.429, V3P-GB 0.483 — control candidates look *more* lesion-like than true lesions (median
mean probability 0.957 vs 0.941). False detections per 100 healthy scans with an MSLesSeg-calibrated
null, α = 0.2 BH: raw 135, V3P-LR 101 (62–73 % of control scans with ≥ 1 false lesion); FDX layer 1:
75 / 74.

## 4. Adversarial self-check (pre-registered A1–A9 + post-hoc P1–P4)

| Check | Result | Reading |
|---|---|---|
| A1 shuffle-label null | pooled LOCO mean 0.468 (range 0.32–0.60); within-M 0.517 (0.38–0.61); not flagged | no leakage signature; the wide range shows that single-run differences of ±0.1 can come from noise-fitted weights on these correlated features |
| A2 integrity | patient-disjointness asserted in every split; feature code takes no GT (unit test) | passed |
| A3 site identity | cohort-identity AUROC from V3 features **0.982**; FLAIR boundary 0.83, texture 0.71, contrast 0.62 | **strong site signature** in the new FLAIR families → main reason cross-cohort gains are small |
| A4 label definitions | strict IoU > 0.1: Δ +0.024 [−0.000, +0.049]; any-voxel: Δ +0.002 [−0.030, +0.036]; fragments removed: Δ +0.011 [−0.016, +0.040] | the gain is not fragment-hunting, but it vanishes under the v2 any-voxel convention |
| A5 small n | 10 MSLesSeg patients → rest of MSLesSeg: 0.818 (Δ +0.08); events per variable in L10 = 2.2 | within one domain 10 patients suffice; the L10 problem is both domain and very few false examples (94) |
| A6 contamination | M-trained V3-LR: L10 0.779, L12 0.785, FLAMeS-trained Ljubljana 0.741 (raw 0.635) | in-sample maps have a different false-candidate structure (59 % of their FALSE are fragments vs 29 %); they must stay out of training/testing |
| A7 ablation (pooled) | removing FLAIR contrast **raises** pooled AUROC to 0.760; removing FLAIR boundary lowers it to 0.731 | mixed; post-hoc only, not used to select features |
| A8 KS M vs L10 | among true lesions, D up to 0.64 (fl_edge_step), 0.46 (fl_grad_boundary); location proxies ≤ 0.21; raw prob 0.10 | FLAIR features shift strongly between sites (Ljubljana FLAIR is winsorised + different scanners); the MNI-free location proxies transfer well |
| A9 model choice | GB ≥ LR within domain, worse cross-cohort (pooled 0.689) | the transparent LR is the right primary |
| P1 new families vs v2 features, same LR | pooled +0.020 [−0.004, +0.047]; A +0.032 [−0.002, +0.079]; B −0.008; within M +0.048 [+0.030, +0.065] | **new families help within domain; across cohorts the evidence is inconclusive** |
| P2 direction-A refit variance | 0.768 [0.741, 0.794], 0/50 below raw | the M → L10 gain is robust |
| P3 pooled-metric mechanism | mean score 0.63 (A, on L10) vs 0.79 (B, on M) | explains why pooled < each direction |
| P4 bootstrap seed | Δ +0.0139 with CI [−0.012, +0.042] for 3 seeds | stable |

Exploratory (not confirmatory): trained on all 30 Ljubljana maps (incl. FLAMeS-trained; not a leak for
M) → M: 0.803 vs 0.735 raw (Δ +0.068 [+0.039, +0.099]); pooled LOCO with scan-context features 0.760
(Δ +0.032 [+0.009, +0.058]); new families alone 0.751; + T1 0.746; + MNI 0.736.

## 5. What is new in v3 and what carries the signal

New (not in v2): FLAIR contrast vs a NAWM shell (per-scan robust z), FLAIR texture, boundary
sharpness on FLAIR and on the probability map, multi-threshold persistence, MNI-free scale-normalised
location proxies (depth / ventricle proxy / CSF contact), plus exploratory T1 contrast and scan
context, and ready-to-use code for ensemble disagreement and LST-AI agreement. Strongest new
single features (univariate AUROC M | L10, post-hoc P5; below 0.5 = inverse direction):
probability-map boundary gradient 0.745 | 0.699, survival at P ≥ 0.9 0.726 | 0.698, volume of the
low-threshold (P ≥ 0.1) component containing the candidate 0.301 | 0.333, FLAIR texture spread
~0.69 | 0.68. FLAIR contrast itself is weak (0.555 | 0.543); FLAIR CNR is site-dependent (0.688 |
0.574); the MNI-free location proxies are individually near 0.5 but transfer well (A8). Much of the
new signal is correlated with size and confidence. On every probability-map feature the control
candidates sit on the "true lesion" side of Ljubljana's true lesions (median mean probability 0.957
vs 0.941, larger, rounder, sharper, more persistent, more isolated) — which is why no
probability-map score can reject them.

## 6. Honest interpretation

1. v3 is a clear improvement **within one acquisition domain** and **in the well-powered transfer
   direction** (train on 75 MSLesSeg patients, apply to clean Ljubljana). It does not meet the
   pre-registered cross-cohort criterion, and its advantage over v2's features with the same model is
   not established across cohorts.
2. The bottleneck is the site signature of image features (A3, A8), not the conformal machinery, and
   two cohorts with 10 clean test scans cannot resolve it.
3. Probability-map features cannot reject the confident false positives FLAMeS produces on healthy
   brains from another site. This is the label-shift failure documented in August, now measured on
   real controls with a leak-free design.
4. Nothing here justifies wiring v3 into the guarantee path.

## 7. Limitations

Two lesion cohorts; L10 has 10 scans and 94 false candidates (wide intervals); bootstrap CIs hold the
model fixed (refit variance reported separately); controls only 30 and probability-map features
only; location proxies are heuristic (failed on 3 scans of one patient); one rater-protocol per
cohort; same author designed and evaluated (mitigated by committing protocol and code first).

## 8. Inputs needed next from the cloud run (exact format)

The builder already accepts them (`build_features.py --folds-dir/--lstai-dir/--control-flair-dir`);
evaluation under a v3.1 protocol amendment written **before** the new families are run.

1. **FLAMeS per-fold probability maps, folds 0–4, run separately** (`nnUNetv2_predict -d 004 -c
   3d_fullres -tr nnUNetTrainer_8000epochs -f k --disable_tta --save_probabilities`, one call per k —
   not `-f 0 1 2 3 4`, which averages). For every case already in `mslesseg-flames` (115),
   `openms-flames` (30) and `sibbms-controls-flames` (30; ideally all 100 controls).
   * Content: lesion channel `probabilities[1]` of the `.npz`, transposed `(2, 1, 0)` exactly as the
     existing maps, float32 (float16 acceptable), saved with the input FLAIR's affine/header.
   * Name: `{case}_prob_f{k}.nii.gz` with the existing case ids (`mslesseg_P10_T1`,
     `openms_patient16`, `sub-001`), one folder per cohort, e.g. `data/cohorts/mslesseg-flames-folds/`.
   * Check enforced by the builder: fold 0 must reproduce the existing `{case}_prob.nii.gz` within
     1e-3 (otherwise refused). Size ≈ 175 × 5 × 7 MB ≈ 6 GB (fits the 28 GB free).
   * Also return: nnU-Net version, weights archive SHA-256, and the run log. Contamination rule:
     with all 5 folds only Ljubljana 16–20, 26–30 are clean; 04 and 07 are clean for fold 0 only.
2. **LST-AI probability maps for the same cases** (LST-AI v1.2.0, `--probability_map --stripped`,
   T1 + FLAIR; MSLesSeg P49_T2 cannot run — its T1 is empty).
   * Content: the ensemble lesion probability in [0, 1] (and, if the tool can, the 3 individual
     U-Net maps as `{case}_lstai_prob_m{j}.nii.gz`), **resampled (trilinear) into the exact grid of
     `{case}_prob.nii.gz`** (same shape and affine; the builder refuses a mismatch), float32.
   * Name: `{case}_lstai_prob.nii.gz` in `data/cohorts/{cohort}-lstai/`, plus the transform and
     command used.
   * Must be verified: LST-AI's training data do not include MSLesSeg, Ljubljana or SibBMS.
3. **Skull-stripped control images** (the HD-BET output the control run already produced but did not
   keep): `{case}_FLAIR.nii.gz` (and `{case}_T1.nii.gz`) on the controls' probability-map grid, in
   `data/cohorts/sibbms-controls-flair/`. This is what lets the full FLAIR model be tested on healthy
   brains — currently the weakest point.
