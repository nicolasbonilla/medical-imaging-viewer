# Does conformal lesion-level false-discovery control survive site, slice-thickness and segmenter shift in MS MRI? A pre-registered five-cohort audit with training-overlap control

*Draft v0.3 (2026-10-21) — target venue: MELBA (full) / MICCAI UNSURE workshop (short). Every
number comes from a committed script and a dated record in this repository (Reproducibility
section). The v0.3 analysis was pre-registered (`docs/research/paper/PROTOCOL-v0.3.md`, committed
before any v0.3 outcome was computed); post-hoc explanations are labelled as such. Numbers that
could not be recomputed are marked "not re-verified". Research code, not the medical device.*

*Authors: N. G. Bonilla Vargas [+ co-authors TBD]*

---

## Changelog v0.2 → v0.3 (2026-10-21)

1. **New data (local CPU analysis, no cloud command).** FLAMeS run fold-by-fold (five folds, no
   test-time augmentation) on MSLesSeg (115 scans / 75 patients), Ljubljana (30; only the 10
   FLAMeS-clean scans used), and three thick-slice 2D-FLAIR cohorts: **MS3SEG** (Iran, 100 patients,
   6.0–8.1 mm), **Muslim 2022** (Baghdad, ~20 centres, 51 axial scans, 4.86–8.3 mm, in-plane pixel
   size estimated) and **PediMS** (28 scans of 9 children, 3.9 mm). LST-AI maps on the same MSLesSeg
   and Ljubljana images (paired segmenter comparison). Thirty healthy controls (fold 0 only).
   Every input file opened, matched its mask's grid and is hashed in the inventory record; the new
   fold-0 maps reproduce the August maps used by v0.1/v0.2 (max |Δp| 0.002) and the v0.2 candidate
   labels (4400/4400 identical).
2. **Pre-registration** of candidates, scores, procedures, calibration designs, targets, outcomes,
   statistics and success criteria before any outcome (protocol commits 9951494, c0c5fa1; one
   gate deviation, 50c9b08, logged before outcomes).
3. **New questions**: transport from 1-mm to thick-slice sites; validity and power by slice
   thickness (with a lesion-size table); 5-fold ensemble vs single fold; per-site recalibration
   size; a paired (same-image) segmenter shift.
4. **New procedure in the comparison, not a new method**: a scan-conformal FDX threshold (P2: the
   split-conformal quantile of per-scan "safe thresholds"), the single-threshold analogue of v0.2's
   Layer 2, evaluated next to conformal BH (P1) and v0.2's baselines.
5. **Claims changed by v0.3** (details §7.3): v0.2's lesion-level AUROC 0.70–0.75 was a property of
   a *single fold*; the 5-fold ensemble scores 0.78–0.82 at every site. v0.2's "segmenter change
   collapses power (the FDR-safe direction)" was half of the story: on the same images the reverse
   direction violates the guarantee (realised FDR 0.21 at α = 0.1). The v0.2 fold-0 pipeline
   violates the guarantee on a thick-slice site (MS3SEG) where the ensemble does not.
6. v0.2's per-scan region certificates (Layer 1/Layer 2, §6) were not re-run on the new sites.

*The v0.1 → v0.2 changelog is kept in Appendix A.*

---

## Abstract

Conformal selection gives lesion detectors a distribution-free *precision dial*: select candidate
lesions so that the expected false-discovery proportion (FDR) per scan is at most α. Whether the
dial survives the shifts of real multiple-sclerosis (MS) imaging — other sites, thick-slice 2D
FLAIR, another segmenter — and whether it is evaluated on data the segmenter never saw, is
untested. In a pre-registered audit of five public cohorts (304 scans, 245 patients; 1-mm 3D/MNI
data from Italy and Slovenia and 2D FLAIR with 3.9–8.3 mm slices from Iran, Iraq and a paediatric
cohort), segmented by the five folds of FLAMeS, we excluded the 20 Ljubljana scans FLAMeS trained
on (identified from the released model files) and calibrated with patients, never scans, as the
resampling unit. Conformal Benjamini–Hochberg selection (P1) was not violated in any of 16
held-out-site cells: calibrated on 1-mm sites, realised FDR on thick-slice sites was 0.107
[95 % CI 0.074, 0.145] (MS3SEG), 0.122 [0.062, 0.197] (Muslim) and 0.041 [0.009, 0.102] (PediMS)
at α = 0.1, and ≤ 0.123 at α = 0.2 — so validity is consistent but not established for every site
at α = 0.1. A per-scan false-discovery-exceedance threshold (P2) calibrated on 1-mm sites failed
on thick slices (21 % and 29 % of scans above γ = 0.1 against a 10 % budget); site-only
recalibration with ≥ 10 patients restored it, adding site patients to the foreign pool did not.
With slice thickness, the slack of P1 shrinks (realised FDR at α = 0.2: 0.018, 0.050, 0.101, 0.120
from ≤ 1.5 mm to > 6.5 mm) and raw detection of small lesions falls (50 % detection needs ≥ 50 mm³
on 4.5–8.3 mm slices vs ≥ 14 mm³ on 1-mm scans; 80 % is never reached on 2D slices). The largest
effect is the ensemble: averaging the five folds raised candidate AUROC from 0.67–0.76 to 0.78–0.82,
doubled lesion sensitivity at the guarantee (0.20 vs 0.10 leave-one-site-out) and removed the
violations that the single-fold pipeline produced on MS3SEG (0.201 [0.166, 0.242] at α = 0.1).
On the same images, calibrating on LST-AI and selecting on FLAMeS violated the guarantee (0.207 at
α = 0.1). The guarantee is real but conditional: on the segmenter version, on site-level
recalibration for per-scan promises, and on slice thickness for what it can find.

---

## 1. Introduction

Automated MS lesion segmentation reaches voxel Dice ≈ 0.7–0.75 on external data with
nnU-Net-class models such as FLAMeS, but a radiologist reading one scan needs to know how many of
the flagged lesions are false. Conformal selection [Jin & Candès 2023] turns any score into a
selector with a finite-sample FDR guarantee, provided the false candidates of a new scan are
exchangeable with a calibration set. MS imaging stresses that proviso: sites differ in scanner and
protocol, much routine FLAIR is still acquired as 2D slices of 4–8 mm, lesion load differs across
populations, segmenters are replaced, false candidates within a scan are correlated, and public
MS cohorts are often in the training data of the segmenter being evaluated.

This paper does not propose a new conformal method. It is an **honest, pre-registered,
reproducible audit** of where lesion-level conformal false-discovery control holds and where it
fails on real MS data, with the safeguards such a claim needs: a check of which evaluation scans
the segmenter trained on, the patient as the unit of splitting and resampling, held-out sites,
multiplicity-aware intervals, and plainly reported negative results.

**Contributions.**
1. A five-cohort, training-overlap-aware evaluation of conformal lesion selection under
   acquisition shift including **thick-slice 2D FLAIR** (3.9–8.3 mm), with leave-one-site-out and
   1-mm → thick designs (§5.1).
2. A **slice-thickness reliability table** — validity, power, per-scan exceedance and the smallest
   reliably detected lesion size per thickness band (§5.2) — intended as input to a
   "reliability by slice thickness" display (research input only).
3. Evidence that **ensembling the segmenter's folds** matters more for the guarantee's usefulness
   — and, at one site, for its validity — than the choice of conformal wrapper (§5.3).
4. A **recalibration-size** analysis: how many local patients restore validity and power (§5.4).
5. A **paired segmenter-shift** experiment on identical images showing the guarantee breaking in
   one direction (§5.6), and the v0.2 training-overlap forensics (§3.2).
6. A negative-results record (§7.3), including claims of our own earlier drafts.

## 2. Related work

**Conformal selection and FDR.** Conformal p-values with a shared calibration set are PRDS, so
Benjamini–Hochberg on them controls FDR [Bates et al. 2023]; Jin & Candès [2023] cast selection
by prediction in this framework. Covariate shift can be handled by weighted conformal p-values
[Tibshirani et al. 2019] and weighted conformal selection, at the cost of estimated likelihood
ratios; group-conditional (Mondrian) calibration [Vovk et al. 2005, *verify*] calibrates within
strata such as sites or thickness bands.

**Grouped data and scan-level risk control.** Dunn, Wasserman & Ramdas [2023] calibrate at the
group level; Lee & Ren [2025, arXiv 2501.02514] give subsampling and hierarchical conformal
e-values with e-BH, requiring group sizes independent of the observations. Conformal risk control
[Angelopoulos et al. 2024] and Learn-then-Test [Angelopoulos et al. 2021, *verify venue*] control
the expectation (or a high-probability bound) of a bounded loss over exchangeable units; with the
scan as unit and the per-scan FDP or the indicator {FDP > γ} as loss they give scan-level FDR or
FDX control for a global threshold (our P2 and baselines).

**Simultaneous FDP bounds.** Reference-family bounds [Blanchard, Neuvial & Roquain 2020],
closed-form bounds under independence [Katsevich & Ramdas 2020], the exact joint law of conformal
p-values [Gazin, Blanchard & Roquain 2024] and everywhere-valid bounds for conformal inference
[Song, Jin & Candès 2026] underlie per-scan certificates (§6); all assume candidate-level
exchangeability.

**Uncertainty in MS lesion segmentation.** Conformal prediction has been applied to patient-level
MS diagnosis [npj Digital Medicine 2025, *verify*] and to lesion-level miss-rate (FNR) control in
3D segmentation [arXiv:2510.17897, *verify*] — the complementary error to ours. Deep ensembles
improve calibration and ranking of predictive uncertainty [Lakshminarayanan et al. 2017,
*verify*]; Shifts 2.0 benchmarks MS segmentation under shift with cohorts that are FLAMeS training
data. To our knowledge no study characterises lesion-level FDR/FDX guarantees across site,
slice-thickness and paired segmenter shift while controlling for the segmenter's training-set
overlap; we make no stronger novelty claim.

## 3. Data and training-set overlap

### 3.1 Cohorts

**Table 1. Cohorts (ensemble arm; candidates and labels as defined in §4.1).**

| cohort | scans / patients | native FLAIR (slice spacing) | detectable expert lesions | candidates (false) | candidate AUROC: 5-fold ensemble [95 % CI] | fold 0 |
|---|---|---|---:|---|---|---|
| MSLesSeg [Rondinella et al. 2025] | 115 / 75 | 1.5 T, ~3 scanners; delivered in MNI 1 mm | 3344 | 3788 (1257) | 0.818 [0.798, 0.837] | 0.735 [0.708, 0.761] |
| Ljubljana, FLAMeS-clean (16–20, 26–30) [Lesjak et al. 2018] | 10 / 10 | 3 T 3D FLAIR; MNI 1 mm | 667 | 517 (82) | 0.802 [0.729, 0.883] | 0.698 [0.625, 0.773] |
| MS3SEG [Bawil et al. 2026] | 100 / 100 | Toshiba 1.5 T 2D (6.0–8.1 mm, median 7.2) | 3354 | 3402 (1162) | 0.802 [0.786, 0.816] | 0.720 [0.701, 0.737] |
| Muslim 2022 [Muslim et al. 2022] | 51 / 51 | ~20 centres, 1.5 T 2D (4.86–8.3 mm); in-plane pixel **estimated** | 1819 | 1540 (568) | 0.784 [0.741, 0.822] | 0.746 [0.710, 0.782] |
| PediMS [Popa et al. 2025] | 28 / 9 (children) | Siemens 3 T 2D (3.9 mm) | 1104 | 1110 (321) | 0.801 [0.774, 0.864] | 0.698 [0.679, 0.768] |
| SibBMS healthy controls [Tuchinov et al. 2025, *verify*] | 30 / 30 | 1 mm (fold 0 only) | 0 | 83 (83) | — | — |

MS3SEG and Muslim were skull-stripped with HD-BET 2.0.1 (CPU, no TTA); PediMS is distributed
stripped. Maps are on each scan's native grid for the thick-slice cohorts (voxels 2.2–6.5 mm³) and
on the MNI 1-mm grid for MSLesSeg and Ljubljana. LST-AI v1.2.0 maps exist for MSLesSeg (114; one
scan skipped for a blank T1) and all 30 Ljubljana scans. Expert masks: MS3SEG's MS-lesion class
excludes periventricular hyperintensities its raters judged non-MS; Muslim's masks come from a
sequential correction chain; PediMS has one rater validated by two specialists.

### 3.2 Training-set overlap

**Table 2. Was the cohort part of the segmenter's training data?**

| segmenter | Ljubljana (30) | MSLesSeg (115) | MS3SEG / Muslim / PediMS | SibBMS controls | ISBI-2015 (v0.2 only) |
|---|---|---|---|---|---|
| FLAMeS 5-fold ensemble | **contaminated 20/30** (01–15, 21–25); clean 16–20, 26–30 | clean (FLAMeS external test) | no known overlap (dataset descriptions; not forensically checked) | clean | contaminated |
| LST-AI | clean (test-only in the LST-AI paper) | clean | not used | not used | clean |

*How the 20 were identified (v0.2).* The released FLAMeS weights contain nnU-Net's
`dataset_fingerprint.json` (per-case spacing and brain bounding box of all 668 training cases).
Twenty consecutive entries carry the Ljubljana spacing and match the bounding box of exactly one
patient each, with zero voxels of disagreement on all three axes — patients 01–15 and 21–25. The
training logs show that each fold trains on 4/5 of the cases, so only the ten never-trained scans
are clean for the ensemble. They are excluded from every FLAMeS analysis, including calibration.
(Details, scripts and the HTTP-range recipe: v0.2 records `2026-10-17_flames_*`.)

## 4. Methods (pre-registered)

### 4.1 Candidates, expert lesions, matching

Candidates are 18-connected components of {p ≥ 0.5} with physical volume ≥ 3 mm³ (v0.2's rule,
with each scan's own voxel volume); expert lesions are 18-connected components of the mask with
volume ≥ 3 mm³ (clinical: ≥ 14.14 mm³). A candidate is true if it is the Hungarian
(maximum-IoU, one-to-one) match of an expert lesion (lenient IoU > 0; strict IoU ≥ 0.10 as
sensitivity analysis); surplus fragments are false.

### 4.2 Scores and arms

*Ensemble arm (primary)*: candidates on the voxelwise mean of the five fold probabilities; score =
mean ensemble probability over the candidate. *Secondary score*: S_cons = minimum over folds of
the per-fold mean probability (fold-agreement score). *Fold-0 arm*: the v0.2 pipeline (fold 0
alone); folds 1–4 likewise as context. *LST-AI arms*: ensemble and sub-model 1.

### 4.3 Procedures

- **P1, conformal BH (FDR).** Null = all false-candidate scores of the calibration patients;
  p_j = (1 + #{null ≥ s_j}) / (n + 1); BH at α within each test scan. Guarantee E[FDP_scan] ≤ α
  under candidate-level exchangeability.
- **P2, scan-conformal FDX threshold.** For each calibration patient (first timepoint), the safe
  threshold t_i is the smallest grid value above which the scan's FDP never exceeds γ; the
  threshold is the ⌈(K+1)(1−δ)⌉-th smallest t_i (abstain if that exceeds K). Guarantee
  P(FDP_test > γ) ≤ δ under exchangeability of calibration and test *patients*.
- **Baselines (v0.2)**: B1 precision-matched global threshold (no guarantee); B2 conformal risk
  control, per-scan FDP loss; B3 Learn-then-Test (Hoeffding–Bentkus, δ = 0.1). Weighted conformal
  selection (features not comparable across anisotropic grids) and Lee–Ren e-values (no power at
  our group sizes in v0.2) were not carried over — decided before results.

Targets: α ∈ {0.1, 0.2} (0.3 secondary); γ ∈ {0.1, 0.2}, δ = 0.1.

### 4.4 Calibration designs

D1 within-site (patient-grouped 5-fold; leave-one-patient-out for Ljubljana-10 and PediMS-9);
**D2 leave-one-site-out**; **D3 1-mm → thick** (calibrate on MSLesSeg + Ljubljana-10, test each
thick-slice site); D3r the reverse; D4 pooled 5-fold over all sites; D5 recalibration curve (k
target-site patients, k ∈ {1, 2, 3, 5, 10, 20, 40}, 200 draws, site-only or added to the 1-mm
pool). Repeated timepoints of a patient are never split across calibration and test.

### 4.5 Outcomes and statistics

Primary: on held-out sites (D3: 3 thick sites; D2: 5 sites), realised FDR (mean per-scan FDP,
FDP = 0 when nothing is selected) for P1 and realised FDX (share of test scans with FDP > γ) for P2
— 32 cells — with 95 % patient-cluster bootstrap intervals (2000 resamples; FDX: union with the
exact Clopper–Pearson interval). A cell is *violated* if the lower bound exceeds the nominal
level, *holds* if the upper bound is ≤ nominal + 0.05, otherwise *inconclusive*; a non-violated
cell with < 10 selections or end-to-end sensitivity < 0.05 is flagged as abstention. Bonferroni
intervals (32 cells) and a two-level bootstrap (calibration and test patients resampled) are
reported. Secondary: end-to-end lesion sensitivity at the guarantee; false detections per 100
healthy controls; thickness bands (≤ 1.5, 3.9, 4.5–6.5, > 6.5 mm) with lesion-size bins; ensemble
vs fold 0 (patient-paired bootstrap); recalibration size k*.

## 5. Results

### 5.1 Held-out sites, including 1-mm → thick-slice transport

**Table 3. Primary cells (ensemble arm): realised value [95 % CI] → class; end-to-end sensitivity.**

| design · site | P1 α = 0.1 | P1 α = 0.2 | P2 γ = 0.1 (vs δ = 0.1) | P2 γ = 0.2 |
|---|---|---|---|---|
| 1-mm → MS3SEG | 0.107 [0.074, 0.145] holds*; 0.26 | 0.123 [0.099, 0.151] holds; 0.40 | **0.21 [0.13, 0.30] violated**; 0.12 | 0.12 [0.06, 0.20] inconcl. |
| 1-mm → Muslim | **0.122 [0.062, 0.197] inconcl.**; 0.10 | 0.097 [0.058, 0.146] holds; 0.23 | **0.29 [0.17, 0.44] violated**; 0.04 | **0.27 [0.16, 0.42] violated** |
| 1-mm → PediMS | 0.041 [0.009, 0.102] holds; 0.12 | 0.086 [0.056, 0.122] holds; 0.33 | 0.07 [0.00, 0.24] inconcl.; 0.05 | 0.07 [0.00, 0.24] inconcl. |
| LOSO MSLesSeg | 0.009 holds (abstention); 0.01 | 0.018 [0.004, 0.042] holds; 0.09 | 0.02 holds (abstention) | 0.03 holds (abstention) |
| LOSO Ljubljana-10 | 0.000 holds (abstention); 0.01 | 0.011 [0.000, 0.033] holds; 0.12 | 0.00 [0, 0.31] inconcl. (abstention) | same |
| LOSO MS3SEG | 0.087 [0.059, 0.121] holds; 0.20 | 0.116 [0.093, 0.142] holds; 0.38 | 0.16 [0.09, 0.25] inconcl.; 0.09 | 0.12 [0.06, 0.20] inconcl. |
| LOSO Muslim | 0.082 [0.033, 0.137] holds (abstention); 0.03 | 0.100 [0.048, 0.163] holds; 0.14 | 0.18 [0.08, 0.31] inconcl. (abstention) | same |
| LOSO PediMS | 0.007 [0.000, 0.022] holds; 0.06 | 0.050 [0.016, 0.093] holds; 0.16 | 0.00 [0, 0.12] holds (abstention) | same |

\*point estimate above α, upper bound within the pre-registered +0.05 margin.

**No P1 cell is violated**, but the pre-registered verdict for 1-mm → thick transport of P1 is
*inconclusive*, because Muslim at α = 0.1 is not established. The two-level bootstrap gives the
same picture (MS3SEG α = 0.1: 0.101 [0.070, 0.136]; Muslim: 0.104 [0.042, 0.182]). **P2 is refuted**
(three violated cells; Muslim γ = 0.1 survives Bonferroni, [0.12, 0.52]). Strict matching and
dropping the one PediMS patient with Baló's concentric sclerosis change no class. With the
fold-consensus score S_cons every 1-mm → thick P1 cell holds (Muslim α = 0.1: 0.068 [0.026, 0.122])
and no P2 cell is violated, at a modest power cost (sensitivity 0.30 vs 0.34 at α = 0.2) — a
pre-specified sensitivity analysis, not the primary result.

Among all procedures, only conformal BH had no violated 1-mm → thick cell: the precision-matched
threshold B1 was violated on MS3SEG at α = 0.1 and 0.2 (0.164 [0.136, 0.196]; 0.230 [0.206, 0.255])
and on Muslim at α = 0.1 (0.144 [0.107, 0.180]); conformal risk control B2 on Muslim at α = 0.1
(0.180 [0.103, 0.265]).

*Mechanism (post hoc).* Thick-slice sites produce more very-confident false candidates: the
false-score law differs from the 1-mm sites' (scan-clustered permutation KS: MS3SEG D = 0.107,
p = 0.0005; Muslim D = 0.094, p = 0.025; PediMS D = 0.057, p = 0.51), and the share of scans with a
false candidate above the 1-mm-calibrated P2 threshold (0.965) is 24 % (MS3SEG) and 29 % (Muslim)
vs 6–10 % on the 1-mm sites — almost exactly the realised FDX. A single threshold carries that
tail into exceedance; P1's expectation-level guarantee absorbs it with reduced slack. In the
opposite direction, foreign calibration makes the 1-mm sites nearly silent (MSLesSeg, α = 0.1:
sensitivity 0.010 vs 0.102 within-site).

### 5.2 Slice thickness

**Table 4. By thickness band (leave-one-site-out calibration, ensemble).**

| band | scans / patients | P1 α = 0.2: realised FDR [CI] | scans with FDP > 0.1 | sensitivity [CI] | false / true lesions per scan | P2 γ = 0.1: FDX [CI] |
|---|---|---|---:|---|---|---|
| ≤ 1.5 mm | 125 / 85 | 0.018 [0.004, 0.040] | 6 % | 0.094 [0.053, 0.141] | 0.13 / 3.0 | 0.016 [0.002, 0.057] (abstention) |
| 3.9 mm | 28 / 9 | 0.050 [0.016, 0.093] | 14 % | 0.164 [0.042, 0.440] | 0.50 / 6.5 | 0.000 [0, 0.12] (abstention) |
| 4.5–6.5 mm | 76 / 76 | 0.101 [0.063, 0.145] | 30 % | 0.236 [0.180, 0.298] | 0.88 / 7.9 | 0.158 [0.079, 0.260] |
| > 6.5 mm | 75 / 75 | 0.120 [0.093, 0.152] | 49 % | 0.355 [0.310, 0.402] | 1.73 / 12.4 | 0.173 [0.093, 0.278] |

The marginal guarantee holds in every band, its slack shrinks with thickness, and per-scan
variability grows; the pooled design gives the same ordering. Power at the guarantee rises with
thickness because thick-slice expert lesions are larger (median 108–117 mm³ vs 68 mm³ on MSLesSeg)
and because the 1-mm band is penalised by the foreign null. Bands coincide with sites, so this is
not a controlled thickness experiment; within MS3SEG (6.0–8.1 mm) per-scan FDP does not trend with
spacing (ρ = 0.03, post hoc).

**Table 5. Expert-lesion sensitivity by lesion volume** (raw segmentation / at P1 α = 0.2).

| band | [3, 14) mm³ | [14, 50) | [50, 150) | [150, 500) | ≥ 500 | raw ≥ 80 % from | raw ≥ 50 % from |
|---|---|---|---|---|---|---|---|
| ≤ 1.5 mm | 0.36 / 0.02 | 0.72 / 0.04 | 0.81 / 0.09 | 0.87 / 0.20 | 0.90 / 0.21 | 50 mm³ | 14 mm³ |
| 3.9 mm | 0.37 / 0.03 | 0.67 / 0.08 | 0.76 / 0.19 | 0.77 / 0.22 | 0.80 / 0.33 | not reached | 14 mm³ |
| 4.5–6.5 mm | 0.13 / 0.00 | 0.45 / 0.10 | 0.59 / 0.23 | 0.66 / 0.30 | 0.76 / 0.38 | not reached | 50 mm³ |
| > 6.5 mm | 0.21 / 0.06 | 0.43 / 0.10 | 0.69 / 0.32 | 0.72 / 0.48 | 0.70 / 0.56 | not reached | 50 mm³ |

On 2D slices of 4.5 mm or more, lesions below ~4.6 mm in diameter are found less than half the
time, and no size is found 80 % of the time. At the guarantee, sensitivity exceeds 50 % only for
lesions ≥ 500 mm³ on > 6.5 mm slices. Muslim's estimated pixel size moves its own 50 %-detection
size between 50 and 150 mm³ (volumes × 0.9 / × 1.1).

### 5.3 The 5-fold ensemble vs a single fold

Every single fold scores candidates with AUROC 0.67–0.76; the ensemble mean, 0.78–0.82 at every
site (Table 1); fold disagreement alone reaches 0.77–0.81. At the guarantee (P1, α = 0.2) the
ensemble's end-to-end sensitivity is twice fold 0's — leave-one-site-out 0.203 vs 0.102
(Δ +0.10 [0.07, 0.13]); 1-mm → thick 0.341 vs 0.194 (Δ +0.15 [0.12, 0.18]); within-site 0.219 vs
0.078 — with lower realised FDR (1-mm → thick 0.110 vs 0.178, Δ −0.068 [−0.098, −0.037]). **With
fold 0 alone — the v0.2 pipeline — MS3SEG is violated** (1-mm → thick α = 0.1: 0.201
[0.166, 0.242]; leave-one-site-out α = 0.1: 0.176 [0.139, 0.216]; every MS3SEG P2 cell, FDX
0.39–0.62). Folds 1–4 behave like fold 0, so the gain comes from averaging, not from a bad fold.
The ensemble removes five violated cells and adds two (Muslim P2, where fold 0 was inconclusive
at sensitivity 0.024): pre-registered verdict "helps on power, but with new violated cells".
Post hoc, the share of false candidates scoring ≥ 0.95 falls from 16–32 % (fold 0) to 3–6 %
(ensemble). With LST-AI the ensemble does not rank better than its first sub-model (AUROC 0.737
vs 0.758 on MSLesSeg) but produces far fewer false candidates (precision 0.45 vs 0.25), so its
sensitivity at the guarantee is again higher (0.10 vs 0.02).

### 5.4 Per-site recalibration

Within-site calibration kept P1 well below α at every site (α = 0.2: realised 0.034–0.075) with
sensitivity 0.14–0.31; P2's FDX was 0.08–0.10 (PediMS abstains: 8 calibration patients < 9).
On the recalibration curve, site-only P1 stays below α at every k and reaches ~90 % of the full
within-site power with 10 patients (MS3SEG α = 0.2: realised 0.069, sensitivity 0.183 vs 0.198;
Muslim 0.053, 0.150 vs 0.163); 2 patients suffice on the small sites (PediMS, Ljubljana). P2
needs ≥ 9 site patients to select at all and is restored on MS3SEG with 10 (FDX 0.075, sensitivity
0.038) and on Muslim only by near-total abstention (0.092, 0.006). Adding site patients to the
85-patient 1-mm pool never restored P2 (MS3SEG 0.16–0.20, Muslim 0.20–0.28 for k ≤ 40) and kept P1
at α = 0.1 on the edge (MS3SEG 0.10–0.11 with k ≤ 10): the foreign pool dominates the quantile.

### 5.5 Healthy controls (fold-0 maps; ensemble maps pending)

False detections per 100 healthy scans at α = 0.1 (controls affected, of 30): own-null floor 10.0
(3); MSLesSeg-calibrated P1 83.3 (17) (v0.2: 86.7; one detection differs by ≤ 0.008 score changes);
1-mm sites 86.7 (17); all five patient sites 36.7 (10); P2 with all sites 16.7 (5; exact CI
6–35 %). Pooling heterogeneous patient sites more than halves false detections on healthy brains
but stays 3.7× the floor.

### 5.6 Paired segmenter shift (same MSLesSeg images)

With calibration and test patients disjoint (5-fold), FLAMeS-calibrated selection on LST-AI
candidates selected nothing (power collapse, as in v0.2 with ISBI). The reverse — LST-AI
calibration, FLAMeS candidates — **violated the guarantee**: realised FDR 0.207 [0.175, 0.240] at
α = 0.1 and 0.236 [0.203, 0.268] at α = 0.2, with 78 % of scans above FDP 0.1. Within-segmenter
calibration was valid for both (FLAMeS 0.019 / 0.052; LST-AI 0.053 / 0.095). Because the images,
patients and expert masks are identical, this isolates the segmenter: calibration must come from
the deployed segmenter version.

## 6. Per-scan region certificates (v0.2 analysis; not re-run on the new sites)

v0.2 measured a scan-level random effect in false-candidate scores (ICC 0.094 on MSLesSeg with
fold 0; reproduced in v0.3: 0.095; with the ensemble 0.104) and proposed a two-layer per-scan
procedure: an exact lattice-path envelope under the conformal rank law (Layer 1, valid only under
candidate-level exchangeability, which the scan effect breaks) and split-conformal calibration of
the simultaneous event across scans (Layer 2), which yields certificates such as **certified
dissemination in space** with P(false certificate) ≤ δ. On v0.2's data the simultaneous curve was
violated in 4.1 % of draws on MSLesSeg [1.3, 7.6] and 5.0 % on healthy controls [0, 12] against
δ = 10 %; no healthy control was ever certified as DIS (0/30 distinct scans, one-sided 95 % upper
bound 9.5 %), at the cost of 92–100 % abstention and lesion-level power ≤ 0.02. Those results come
from fold-0 maps; §5.3 suggests the ensemble would raise power, and §5.1 that thick-slice sites
need their own calibration. Re-running Layer 2 on the ensemble and the new sites is future work.
(Full v0.2 text, tables and synthetic study: v0.2 of this file, commit 87e998d.)

## 7. Discussion

### 7.1 What a deployer can rely on
- **Average false-lesion control (P1) transported** to unseen sites, including thick-slice 2D
  FLAIR, in every tested cell — but on one thick-slice site at α = 0.1 the data cannot establish it,
  and the slack shrinks with slice thickness. Report realised FDR per thickness band.
- **Per-scan promises (P2) do not transport** from thin to thick slices; they need site-only
  calibration with ≥ 10 local patients, and can still be useless (Muslim: abstention).
- **Ensemble the segmenter.** The single-fold pipeline violated the guarantee at one site and had
  half the power; nnU-Net's own 5-fold ensemble fixed both there.
- **Calibrate with the deployed segmenter**; a calibration set from a different segmenter can
  produce twice the promised false-discovery rate.
- **Detection itself is thickness-limited**: on 4.5–8.3 mm slices, lesions under ~50 mm³ are
  missed more often than found, before any conformal selection.
- Healthy or screening populations remain outside the guarantee.

### 7.2 The cost
At the guarantee, end-to-end lesion sensitivity is 0.01–0.40 (P1) and 0.001–0.12 (P2). Better
scores move this frontier: the ensemble's AUROC gain doubled power without touching the
wrapper.

### 7.3 Claims we retracted or changed (negative-results record)
From v0.2 (changed by v0.3):
1. *"Lesion-level AUROC 0.70–0.75 on the clean cohorts; the score is the bottleneck."* True for a
   single fold; the 5-fold ensemble scores 0.78–0.82. The bottleneck was partly self-inflicted by
   running one fold.
2. *"A segmenter change collapses power — the FDR-safe direction."* Half the story: on the same
   images the reverse direction violates the guarantee (§5.6).
3. *"Marginal lesion-FDR control is reliable within a site and consistent with transport."* With
   fold 0, transport to MS3SEG is violated (§5.3); with the ensemble it holds.
From v0.1 (corrected in v0.2, still valid): the training-set contamination of Ljubljana (20/30);
the healthy-control interval (1.8 % → 9.5 %); repeated splits counted as independent scans;
"7–13× the floor"; "candidate AUC 0.75–0.82" without a source; "conformal outperforms a
precision-matched threshold" (direction-dependent in v0.2; in v0.3 the threshold is violated on
thick-slice sites); the "transport, p = 0.71" claim; "44–95 % of scans exceed α"; "conformal breaks
across MS site shift" (refuted by our own same-segmenter axis).

### 7.4 Limitations
- One segmenter family (FLAMeS) for the multi-site results; LST-AI only on the 1-mm cohorts.
- **Contamination**: the 20 FLAMeS-trained Ljubljana scans are excluded everywhere; the clean
  Ljubljana set has 10 scans. Overlap of MS3SEG, Muslim and PediMS with FLAMeS training is excluded
  only by the dataset descriptions, not forensically.
- **Muslim's in-plane pixel size is estimated** (±5 % per axis, ±10 % in volume); it moves Muslim's
  size thresholds (50 vs 150 mm³). Muslim also mixes ~20 centres and sequential annotation.
- **PediMS: 9 children** (28 scans); bootstrap intervals with 9–10 patient clusters (PediMS,
  Ljubljana) under-cover; within-site P2 is impossible there.
- **Healthy controls: fold 0 only and 30 scans**; the ensemble arm is untested on healthy brains.
- Site, thickness, scanner, population and annotation protocol are confounded; MS3SEG's protocol
  counts FLAMeS hits on "normal" periventricular hyperintensities as false.
- MSLesSeg's native FLAIR geometry is not published in the sources we accessed.
- 3D components on 4–8 mm slices can merge or split lesions; lesion counts across grids are not
  comparable.
- The "holds" rule tolerates realised values up to α + 0.05 at the CI upper bound.
- Region certificates (§6) were not re-evaluated on the new data.

**TODO before submission.** (1) Ensemble maps for ≥ 100 healthy controls (data-access form
pending). (2) A second site per thickness band; MSSEG-2 / MICCAI-2008 if obtainable. (3) Layer 2 on
the ensemble and the new sites. (4) Mondrian (per-band) calibration as a pre-registered remedy.
(5) Verify citations marked *verify*; confirm SibBMS licence.

## Reproducibility

| result | script | record |
|---|---|---|
| v0.3 protocol + deviations | — | `docs/research/paper/PROTOCOL-v0.3.md` |
| input hashes, grids, fold-0 reproduction | `research/paper_a/v03_inventory.py` | `docs/research/records/2026-10-21_paper_a_v03_inventory.json` |
| candidates, labels, gate G1 | `research/paper_a/v03_candidates.py` | `docs/research/records/2026-10-21_paper_a_v03_candidates.json` |
| Tables 1, 3–5; §5.1–5.6 | `research/paper_a/v03_analysis.py` (+ `v03_metrics.py`, `v03_data.py`) | `docs/research/records/2026-10-21_paper_a_v03_results.json` |
| post-hoc explanations (labelled) | `research/paper_a/v03_posthoc.py` | `docs/research/records/2026-10-21_paper_a_v03_posthoc.json` |
| metric tests (33 pass) | `research/paper_a/test_v03_metrics.py` | — |
| full v0.3 results | — | `docs/research/paper/RESULTS-v0.3.md` |
| training-overlap forensics, v0.2 §4–§5 | `research/paper_a/*_v02.py`, `ljubljana_flames_match.py`, `flames_fold_membership.py` | `docs/research/records/2026-10-17_*` |
| exact DP, Layer 1/2 (v0.2) | `research/conformal_fdx/`, `scripts/calm-ms/calm_fdx_realdata.py` | v0.2 records |

## References (to be formatted; *verify* = citation not yet checked)
- Angelopoulos, Bates, Candès, Jordan, Lei (2021). Learn then Test. arXiv:2110.01052 — *verify venue*.
- Angelopoulos, Bates, Fisch, Lei, Schuster (2024). Conformal risk control. *ICLR*.
- Bates, Candès, Lei, Romano, Sesia (2023). Testing for outliers with conformal p-values. *Ann. Stat.* 51(1).
- Bawil M. B., Shamsi M., Ghalehasadi A., Jafargholkhanloo A. F., Bavil A. S. (2026). A multiple sclerosis MRI dataset with tri-mask annotations for lesion segmentation (MS3SEG). *Sci. Data* 13:867, doi:10.1038/s41597-026-07184-5; data doi:10.6084/m9.figshare.30393475 (CC BY 4.0).
- Blanchard, Neuvial, Roquain (2020). Post hoc confidence bounds on false positives using reference families. *Ann. Stat.* 48(3).
- Dereskewicz E., La Rosa F., et al. (2025). FLAMeS. *J. Neuroimaging*, doi:10.1111/jon.70085; weights Zenodo 17955359.
- Dunn, Wasserman, Ramdas (2023). Distribution-free prediction sets for two-layer hierarchical models. *JASA* 118(544).
- Gazin, Blanchard, Roquain (2024). Transductive conformal inference with adaptive scores. *AISTATS*.
- Isensee et al. (2021). nnU-Net. *Nature Methods* 18:203–211.
- Jin, Candès (2023). Selection by prediction with conformal p-values. *JMLR* 24(244).
- Katsevich, Ramdas (2020). Simultaneous high-probability bounds on the FDP. *Ann. Stat.* 48(6).
- Lakshminarayanan, Pritzel, Blundell (2017). Simple and scalable predictive uncertainty estimation using deep ensembles. *NeurIPS* — *verify*.
- Lee Y., Ren Z. (2025). Selection from hierarchical data with conformal e-values. arXiv:2501.02514.
- Lesjak Ž. et al. (2018). A novel public MR image dataset of multiple sclerosis patients with lesion segmentations based on multi-rater consensus. *Neuroinformatics* 16 — *verify pages*.
- Muslim A. M., Mashohor S., Gawwam G. A., et al. (2022). Brain MRI dataset of multiple sclerosis with consensus manual lesion segmentation and patient meta information. *Data in Brief* 42:108139, doi:10.1016/j.dib.2022.108139; data doi:10.17632/8bctsm8jz7.1 (CC BY 4.0).
- Popa M., Vișa G. A., Șofariu C. R. (2025). PediMS: a pediatric multiple sclerosis lesion segmentation dataset. *Sci. Data* 12:1184, doi:10.1038/s41597-025-05346-5; data doi:10.6084/m9.figshare.28701065 (CC BY 4.0).
- Rondinella et al. (2025). MSLesSeg. *Sci. Data*.
- Song, Jin, Candès (2026). Everywhere valid bounds on false discovery proportions in conformal inference. arXiv:2605.20726.
- Tibshirani, Barber, Candès, Ramdas (2019). Conformal prediction under covariate shift. *NeurIPS*.
- Tuchinov et al. (2025). SibBMS — *verify citation and licence*.
- Vovk, Gammerman, Shafer (2005). *Algorithmic Learning in a Random World* (Mondrian conformal prediction) — *verify*.
- Wiltgen T., McGinnis J., et al. (2024). LST-AI. *NeuroImage: Clinical* 42:103611.
- Conformal MS diagnosis (npj Digital Medicine 2025) — *verify*. arXiv:2510.17897 — *verify*.

---

## Appendix A. Changelog v0.1 → v0.2 (2026-10-17, kept)

v0.1 contained two errors a reviewer would have found fatal. (1) **Training-set contamination**:
20 of the 30 Ljubljana scans are FLAMeS training data (patients 01–15, 21–25, identified exactly
from the released nnU-Net fingerprint); all-30 results were reclassified as in-distribution and
every analysis re-run on the 10 never-trained scans; patient nulls were rebuilt from MSLesSeg only.
(2) **Healthy-control interval**: "0 of 200 healthy scans certified as DIS, 95 % CI ≤ 1.8 %" counted
repeated splits of 30 scans as independent; corrected to 0/30 distinct scans, one-sided upper bound
9.5 %. Further: all figures that pooled repeated splits were re-expressed per distinct scan; labels
harmonised to one-to-one matching; numbers without a committed script recomputed (ICC 0.078/0.094;
top-ranked candidate false in 21/115 = 18.3 %, not 16.5 %); "candidate AUC 0.75–0.82" withdrawn
(measured 0.70–0.75 with fold 0); three scan-aware baselines added (subsampled null, CRC/LTT, Lee &
Ren e-values); citations of FLAMeS, LST-AI and Lee & Ren checked against primary sources.
