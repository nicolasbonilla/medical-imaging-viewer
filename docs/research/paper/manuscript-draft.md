# When does conformal false-discovery control hold for MS lesion detection? A multi-site characterization, and per-scan guarantees under scan clustering

*Draft v0.1 — target venue: MICCAI UNSURE workshop (short) / MELBA (full). Numbers in §4 are frozen
from committed records; §5 is completed from the per-scan FDX study. Reproducibility: every number
has a script + JSON record in this repository (paths in the Reproducibility section).*

*Authors: N. G. Bonilla Vargas [+ co-authors TBD]*

---

## Abstract

Distribution-free conformal selection offers lesion detectors a *precision dial*: select candidate
lesions so that the false-discovery rate (FDR) is at most α, with no assumption on the segmentation
network. Whether that guarantee survives the realities of multiple sclerosis (MS) MRI — different
scanners, different populations, different segmenters, and candidates that are clustered within
scans — has not been characterized. We study conformal lesion selection (conformal p-values from
false-candidate calibration scores + Benjamini–Hochberg) on four public cohorts: two patient cohorts
and one healthy-control cohort segmented by the same model (FLAMeS), and one cohort segmented by a
different model (LST-AI). Using one-to-one (Hungarian) lesion matching, subject-level resampling and
scan-clustered permutation tests, we find that (i) marginal lesion-FDR control **transports** across
same-segmenter patient cohorts — consistent with their false-positive score laws being exchangeable
at the scan level (permutation p = 0.71) — and outperforms both a precision-matched global
threshold and weighted (covariate-shift) conformal selection, which respectively fail to transport
and overshoot the level at tight α; (ii) the guarantee is only **marginal**: 3–17 % of individual
scans exceed the target false-discovery proportion; (iii) **specificity degrades** under population
shift — a patient-calibrated null yields 90–203 false detections per 100 healthy scans versus 10–27
under the controls' own null — and **power collapses** under a segmenter change; (iv) false-candidate
scores carry a significant **scan-level random effect** (ICC 0.08–0.09, p = 0.0002), violating the
candidate-level exchangeability assumed by recent simultaneous FDP bounds for conformal p-values.
We therefore calibrate per-scan false-discovery exceedance at the level of the scan (subject), not the candidate: an exact lattice-path envelope under the conformal rank law, repaired by split-conformal calibration on the simultaneous event. In a pre-registered evaluation it kept the per-scan guarantee on every cohort (curve violation 3.0–7.5 % at δ = 10 %) and yields **certified dissemination in space**: on healthy controls it certified DIS in 0/200 scans (95 % CI ≤ 1.8 %), whereas the raw segmentation met the brain DIS pattern in 40/200 and BH-selected candidates in 17/200. All selection runs at low
lesion-level recall (≤ 0.30), which we report as the honest cost of guaranteed precision at current
score quality.

---

## 1. Introduction

Automated MS lesion segmentation has reached voxel Dice ≈ 0.7–0.75 on external data with
nnU-Net-class models (e.g. FLAMeS), yet deployed detectors still over-segment: our legacy
thesis-era model had lesion-level precision ≈ 0.22 at sensitivity 0.85. For a radiologist, the
operationally relevant quantity is not Dice but *how many of the flagged lesions are false*.
Conformal selection [Jin & Candès 2023] turns any scoring model into a selector with a finite-sample
FDR guarantee, provided the false candidates of a new scan are exchangeable with a calibration set of
false candidates. That proviso is exactly what MS MRI stresses: acquisition differs across sites,
lesion load differs across populations, the segmenter may change, and — as we show — false
candidates inside one scan are not independent draws.

This paper does not propose a new conformal method. The selection wrapper is a faithful application
of conformal p-values and Benjamini–Hochberg; the per-scan procedure in §5 builds on exact
simultaneous FDP bounds for conformal p-values [Gazin, Blanchard & Roquain 2024; Song, Jin & Candès
2026]. Our contribution is an **honest, reproducible characterization** of where the guarantee holds
and where it fails on real multi-site MS data, with the statistical safeguards that such a claim
requires, and a per-scan procedure that remains valid under the scan clustering we measure.

**Contributions.**
1. A four-cohort study separating three shift axes — same-segmenter acquisition/population shift,
   zero-prevalence population shift (healthy controls), and segmenter shift — with one-to-one lesion
   matching, subject-level bootstrap intervals and scan-clustered permutation tests.
2. Evidence that marginal lesion-FDR control transports across same-segmenter patient cohorts and
   beats a global threshold and weighted conformal selection; and that it degrades in specificity
   under population shift and in power under segmenter shift.
3. Evidence that marginal control is not per-scan control, and that an empirically calibrated
   per-scan operating point transfers only from the more to the less heterogeneous site.
4. Measurement of a significant scan-level random effect in false-candidate scores, which invalidates
   candidate-level exchangeability, and a per-scan false-discovery-exceedance (FDX) procedure whose
   validity rests on scan-level exchangeability instead [§5].
5. A negative-results record: three claims we made and then retracted after adversarial review
   (§6.3), kept in the paper because they are the likely mistakes of anyone repeating this analysis.

## 2. Related work

**Conformal selection and FDR.** Conformal p-values with a shared calibration set are
positively regression dependent on a subset (PRDS), so Benjamini–Hochberg on them controls FDR
[Bates et al. 2023]; Jin & Candès [2023] cast selection by prediction in this framework. Covariate
shift can be handled by weighted conformal p-values [Tibshirani et al. 2019] and weighted conformal
selection, at the cost of estimated likelihood ratios and — for selection — the loss of the
unweighted PRDS argument. Hierarchical data motivate calibrating at the level of the exchangeable
unit [Dunn, Wasserman & Ramdas 2023].

**Simultaneous FDP bounds.** Post hoc bounds on the false-discovery proportion via reference
families and λ-calibration [Blanchard, Neuvial & Roquain 2020], closed-form simultaneous bounds
under independence [Katsevich & Ramdas 2020], the exact (Pólya-urn) joint law of conformal p-values
[Gazin, Blanchard & Roquain 2024], and — most recently — everywhere-valid FDP bounds for conformal
inference [Song, Jin & Candès 2026] provide the machinery for per-scan (FDX) guarantees. All of them
require exchangeability of the null test scores with the calibration scores *at the level of the
individual candidate*.

**Uncertainty for MS lesion segmentation.** Conformal prediction has been applied to patient-level
MS diagnosis [npj Digital Medicine 2025, verify] and to lesion-level miss-rate (FNR) control in 3D
segmentation [arXiv:2510.17897, verify]; the latter controls the complementary error to ours. Shift
benchmarks for MS segmentation exist (Shifts 2.0), but to our knowledge no study characterizes
lesion-level FDR guarantees across real scanner/population/segmenter shift.

## 3. Data and candidate generation

| cohort | segmenter | kind | scans | subjects | candidates | false (one-to-one) | GT lesions ≥3 mm³ / ≥14.14 mm³ |
|---|---|---|---:|---:|---:|---:|---:|
| open_ms_data [Lesjak et al. 2018, verify] | FLAMeS | patients | 30 | 30 | 2358 | 461 | 2892 / 1737 |
| MSLesSeg [Rondinella et al. 2025] | FLAMeS | patients | 115 | 75 | 3866 | 1348 | 3344 / 3082 |
| healthy controls [source, verify] | FLAMeS | controls | 30 (27 with ≥1 candidate) | 27 | 83 | 83 | 0 |
| ISBI-2015 | LST-AI [Wiltgen et al. 2024] | patients | 19 | not recoverable | 1176 | 832 (any-voxel) | — |

All maps are 1 mm isotropic (on three different grids, so no location feature is used). Candidates
are connected components of the probability map at 0.5 with volume ≥ 3 mm³; the candidate score is
the mean lesion probability. A candidate is a true detection if it is the Hungarian (maximum-IoU,
one-to-one) match of a ground-truth lesion (lenient: IoU > 0; strict: IoU ≥ 0.10); unmatched
fragments — including surplus over-segmentation fragments of an already-matched lesion — are false.
Subjects, not scans, are the resampling unit (MSLesSeg patients contribute up to three timepoints).
ISBI-2015 case names do not encode the patient, so ISBI is used only as a test cohort, never as a
calibration source.

## 4. Characterization of marginal lesion-FDR control

**Procedure.** For a test scan with candidate scores s₁…s_m and a calibration set of n false-candidate
scores c₁…c_n (from other subjects of the same site, or from another site), the conformal p-value is
p_j = (1 + #{i : c_i ≥ s_j}) / (n + 1) and candidates are selected by Benjamini–Hochberg at level α
within the scan. We report micro-FDR (pooled false/selected, subject-bootstrap 95 % CI), the fraction
of scans whose own FDP exceeds α (over all scans), and three lesion-level recalls: *selection*
(denominator: GT lesions that some candidate is matched to), *end-to-end* (all GT ≥ 3 mm³) and
*clinical* (GT ≥ 14.14 mm³, the 3 mm-diameter criterion).

### 4.1 Same-segmenter cross-site transport

Cross-site realized FDR (lenient matching), subject-bootstrap 95 % CI:

| α | method | openms → MSLesSeg: FDR [CI] · recall sel/e2e · % scans FDP>α | MSLesSeg → openms: FDR [CI] · recall sel/e2e · % scans FDP>α |
|---|---|---|---|
| 0.30 | conformal BH | 0.182 [0.142, 0.219] · 0.30/0.23 · 13.9 % | 0.160 [0.099, 0.210] · 0.07/0.05 · 3.3 % |
| 0.30 | weighted conformal | 0.146 [0.103, 0.182] · 0.14/0.11 · 8.7 % | 0.142 [0.081, 0.205] · 0.10/0.07 · 6.7 % |
| 0.30 | precision-matched threshold | **0.349** [0.309, 0.388] · 1.00/0.75 · 59.1 % | 0.167 [0.143, 0.197] · 0.90/0.59 · 13.3 % |
| 0.20 | conformal BH | 0.161 [0.120, 0.201] · 0.18/0.14 · 16.5 % | 0.089 [0.020, 0.140] · 0.04/0.02 · 3.3 % |
| 0.20 | weighted conformal | 0.125 [0.080, 0.172] · 0.07/0.05 · 9.6 % | 0.139 [0.088, 0.183] · 0.05/0.03 · 6.7 % |
| 0.20 | precision-matched threshold | **0.349** [0.309, 0.389] · 1.00/0.75 · 80.9 % | 0.128 [0.100, 0.160] · 0.49/0.32 · 30.0 % |
| 0.10 | conformal BH | 0.093 [0.050, 0.141] · 0.07/0.05 · 9.6 % | 0.051 [0.000, 0.118] · 0.02/0.01 · 6.7 % |
| 0.10 | weighted conformal | **0.174** [0.088, 0.275] · 0.03/0.02 · 8.7 % | 0.065 [0.000, 0.125] · 0.02/0.01 · 10.0 % |
| 0.10 | precision-matched threshold | **0.147** [0.108, 0.184] · 0.11/0.08 · 30.4 % | 0.000 (nothing selected) |

Conformal BH keeps the realized FDR at or below α in every cross-site cell. A global threshold tuned
to the calibration site's precision does not transport (it is stuck at FDR 0.35 on MSLesSeg for
every target, or selects nothing), and weighted conformal selection — a marginal approximation with
estimated density ratios fitted transductively — overshoots at α = 0.10 (0.174). The conclusions are
unchanged under the strict IoU ≥ 0.10 criterion.

**Why it transports.** A scan-clustered permutation test (relabelling whole scans between sites,
2000 permutations) finds the two sites' false-candidate score laws indistinguishable (KS-D = 0.048,
p = 0.71). A naive candidate-level KS test reports p ≈ 5·10⁻⁴; it is invalid under within-scan
clustering, and under a lenient many-to-one matching it also mislabels over-segmentation fragments
as true, inflating the apparent shift (D = 0.15).

### 4.2 Marginal is not per-scan

Even where micro-FDR ≤ α, 3–17 % of scans exceed α (table above). An empirically calibrated per-scan
operating point — the largest α whose own-site leave-one-subject-out exceedance P(FDP > 0.2) is
≤ 0.1 — transfers from MSLesSeg (α* = 0.14; achieved exceedance on openms 0.00) but not from
openms to MSLesSeg (α* = 0.22; achieved 0.217). Marginal transport does not imply per-scan
transport; per-scan control calibrated on a homogeneous site fails on a heterogeneous one.

### 4.3 Population shift: specificity on healthy controls

On healthy controls every selection is false, so we report false detections per 100 acquired scans
(all 30 scans in the denominator) against the controls' own leave-one-subject-out null — the
exchangeable floor, which is non-zero because a valid conformal null still fires at roughly its
nominal rate:

| α | own-null floor | openms null | MSLesSeg null | pooled patient null |
|---|---:|---:|---:|---:|
| 0.30 | 26.7 | 203.3 | 183.3 | 186.7 |
| 0.20 | 20.0 | 173.3 | 136.7 | 140.0 |
| 0.10 | 10.0 | 120.0 | 86.7 | 90.0 |

A patient-calibrated null produces 7–13× the floor: about one to two false "lesions" per healthy
scan. Control false candidates score higher (mean 0.94) than patient false candidates (0.86–0.88).

### 4.4 Segmenter shift

A FLAMeS-calibrated null applied to LST-AI-segmented ISBI selects nothing at any α: LST-AI scores
lie lower (false 0.75, true 0.81), so no candidate clears the FLAMeS null. This is a collapse of
power, the FDR-safe direction. ISBI confounds segmenter, acquisition and population, so we do not
attribute the effect to the segmenter alone.

### 4.5 Scan clustering

Grouping false candidates by scan (one-to-one labels), the intraclass correlation of their scores is
0.078 (openms, 28 scans, 460 false) and 0.094 (MSLesSeg, 112 scans, 1346 false); the between-scan
variance is 2.2× and 2.05× its value under exchangeable reshuffling (permutation p = 0.0002 in both).
Candidates of one scan are therefore not exchangeable draws from the pooled false-candidate law —
the assumption under which the joint law of conformal p-values, and every simultaneous FDP bound
built on it, is exact.

## 5. Per-scan false-discovery exceedance control under scan clustering

A radiologist reads one scan. The target is therefore false-discovery *exceedance* control per scan,
P(FDP_scan > γ) ≤ δ, and — since clinical decisions are made per anatomical area — simultaneous
lower bounds on the number of true lesions in any region, with **certified dissemination in space**
as the clinically meaningful consequence.

### 5.1 Layer 1: an exact envelope under the conformal rank law

For a scan with m candidates, write k_j = (n+1)p_j ∈ {1,…,n+1} for the conformal ranks and let
V_k (R_k) be the number of false (all) candidates with rank ≤ k. If the calibration false scores
and the scan's m₀ false scores are jointly exchangeable (assumption A1), (V_1,…,V_{n+1}) follows a
universal law P_{n,m₀}: all C(n+m₀, m₀) interleavings of calibration and false test scores are
equally likely [Gazin, Blanchard & Roquain 2024]; the true candidates never enter a false
candidate's p-value. We fix a non-decreasing integer envelope G^{(r)} per candidate null count r —
a truncated higher-criticism shape G_k = min{r, max_{l≤k} ⌊r t_l + λ √(r t_l(1−t_l)(1+r/n))⌋} on
t_k = k/(n+1) ≤ 0.5 (pre-registered on synthetic data only; a Simes-type template and an
HC∧Simes hybrid are reported as secondary) — and choose λ as the smallest value whose **exact**
crossing probability P_{n,r}(∃k: V_k > G_k) is ≤ δ. The crossing probability is computed exactly by
a dynamic program over the anti-diagonals of the lattice path (state = calibration and test points
consumed; a state is killed when the tests seen before the (i+1)-th calibration point exceed
G_{i+1}); it matches brute-force enumeration of all interleavings to 10⁻¹² and carries no Monte
Carlo error. Unknown m₀ is handled by the completion coupling (adding null test points can only
increase V) and an m₀-adaptive closure over a geometric grid of r, and the bound is self-refined
[Song, Jin & Candès 2026; Blanchard, Neuvial & Roquain 2020]. On the single event
E = {V_k ≤ G^{(r*)}_k ∀k} (probability ≥ 1−δ) this yields B*_k ≥ V_k for all k at once, so the
selection "largest k with B*_k ≤ γR_k" has FDP ≤ γ, and — by interpolation — for **any** subset S
of candidates, #false(S) ≤ min_k(|S ∩ {rank > k}| + B*_k).

A closed-form alternative is not available: the Katsevich–Ramdas constant, derived under
independence, crosses its envelope with probability 0.118–0.136 > δ = 0.1 under the conformal
dependence (exact computation; a regression test pins this).

### 5.2 Layer 1 is not valid on MS data

A1 is a statement about candidates, and it is false for MS MRI: false-candidate scores share a
scan-level component (ICC 0.08–0.09, §4.5; exact permutation tests of cross-scan exchangeability
reject at every site). In the tight regime (few false candidates, strong signal) Layer 1 has no slack,
and a scan random effect of the measured size pushes realized FDX above δ [§5.4, synthetic study].
We therefore report Layer 1 on real data as **empirical only**.

### 5.3 Layer 2: scan-level calibration on the simultaneous event

We index a nested family by an integer inflation c ≥ 0 added to every envelope (B* is
non-decreasing in c, so selections shrink and bounds loosen as c grows). For each of K labelled
subjects (one random scan each) we compute the smallest c such that the scan's true null counts
satisfy V_k ≤ B*_k(c) for **all** k — the simultaneous event, not merely the FDP of one selection —
and set ĉ to the ⌈(K+1)(1−δ)⌉-th smallest value (abstain if that index exceeds K). If the K labelled
subjects and the test subject are exchangeable given the calibration pool, the split-conformal
quantile lemma gives P(the test scan's curve is violated at ĉ) ≤ δ, which covers the selected set,
any post-hoc threshold, and every region certificate at once [cf. Dunn, Wasserman & Ramdas 2023].
Candidate-level exchangeability is no longer required. The pool may come from another site: only
the labelled and test subjects must be exchangeable. (Calibrating Layer 2 on the selected set's FDP
alone — an earlier design — covers only that selection and not the region certificates.)

### 5.4 Certified dissemination in space

Each candidate is assigned a MAGNIMS area with the application's own atlas-based zone map (LST-AI
MSMask, periventricular / juxtacortical / infratentorial / deep white matter; per-lesion cascade
IT > PV > JC, else DWM). For the brain McDonald areas a ∈ {PV, JC, IT}, the certified true-lesion
count is L_a = |S_a| − min(|S_a|, min_k(|S_a ∩ {rank > k}| + B*_k)). DIS is **certified** when
L_a ≥ 1 in at least two areas; on the good event every certified area truly contains a true lesion,
so P(a certified DIS is false) ≤ δ. We compare with DIS read off the raw segmentation and off the
BH-selected candidates, on patients and — decisively — on healthy controls, where every DIS call is
false.

### 5.5 Pre-registration

Template, γ = 0.2, δ = 0.1, grids, labels and splits were fixed and committed to version control
before the real-data run (commit c47c88d). One amendment (v2) was made before any Layer-2 real-data
output was observed, after the adversarial validity review: Layer 2 moved to the simultaneous event
and to pools from other sources; Layer 1 was demoted to empirical. The amendment and its reasons
are recorded verbatim in the evaluation script.

### 5.6 Results

**Synthetic worlds** (`synthetic_icc_study.py`; 1500 worlds per cell; K = 29 labelled scans; γ = 0.2,
δ = 0.1; pool of clustered scans with the same marginal score law as the test scan — only the scan
random effect varies). Entries: probability that the simultaneous curve is violated (the event every
certificate relies on), with power in brackets.

| regime | ICC | Layer 1 (candidate-level) | Layer 2 (scan-level) |
|---|---:|---:|---:|
| MSLesSeg-like (n = 1160, m₀≈8, m₁≈19) | 0.00 | 0.083 (0.97) | 0.051 (0.95) |
| | 0.09 | 0.097 (0.94) | 0.049 (0.89) |
| | 0.23 | 0.104 (0.86) | 0.054 (0.75) |
| | 0.50 | **0.165** (0.65) | 0.075 (0.42) |
| few false candidates (m₀≈2, m₁≈6) | 0.00 | 0.115* (1.00) | 0.050 (0.89) |
| | 0.50 | 0.103 (0.87) | 0.048 (0.67) |
| openms-like (n = 210, m₀≈5, m₁≈10) | 0.00 | 0.079 (0.93) | 0.037 (0.85) |
| | 0.23 | 0.111 (0.81) | 0.050 (0.63) |
| | 0.50 | **0.145** (0.62) | 0.071 (0.37) |

Layer 1 breaks as the scan random effect grows (bold: exceeds δ by > 2 SE); Layer 2 holds in every cell
(0.031–0.075) at a power cost that grows with the ICC. *The 0.115 under A1 is Monte Carlo noise: a
20 000-world rerun of that cell gives 0.1019 ± 0.0021 against the exact prediction 0.0997, matching the
exact crossing probability for every m₀ and never violating the proof invariant — in this regime the
bound is attained, as theory predicts. With a strong synthetic signal (μ = 3–4) power is high; on real
data it is not (below).

**Real data** (pre-registered, commits c47c88d/3e27ee9; results 22d455b). Candidate-level
exchangeability is rejected at both patient sites (Kruskal–Wallis of false scores across scans,
permutation p = 0.0005 at openms and MSLesSeg). Primary template (HC), Layer 2 on the simultaneous
event, 20 random subject splits per site (one scan per subject; γ = 0.2, δ = 0.1):

| cohort (pool → labelled K / test) | curve violated | scans FDP > γ | false certified DIS | certified DIS on true-DIS scans | power | abstention |
|---|---:|---:|---:|---:|---:|---:|
| openms (MSLesSeg pool → 20 / 10) | 15/200 (7.5 %) | 0/200 | **0/200** | 13/200 | 0.011 | 81.5 % |
| MSLesSeg (35-subject pool → 29 / 11) | 9/220 (4.1 %) | 1/220 | **0/220** | 11/195 | 0.022 | 91.8 % |
| MSLesSeg, PAC (device) quantile | 3/220 | 0/220 | 0/220 | 1/195 | 0.003 | 99.1 % |
| healthy controls (patient pool → 20 / 10) | 6/200 (3.0 %) | 0/200 | **0/200 [0, 1.8 %]** | — | — | 100 % |

On the same healthy-control test scans, reading DIS off the raw segmentation met the brain pattern
(≥ 1 candidate in ≥ 2 of PV/JC/IT) in **40/200** scans and off the BH-selected candidates in **17/200**;
per-scan BH at γ exceeded FDP > γ on 151/200. Layer 1 with a patient-calibrated null on controls — the
population-shift case — exceeded FDP > γ on 18/30 scans and wrongly certified an area on 16/30; Layer 2
repairs it. The secondary (hybrid) template is also valid (Layer-2 curve violation ≤ 7.5 %) but less
powerful.

**The honest cost.** Certified DIS was reached in only ~6 % of patient scans that truly meet the
pattern, and lesion-level power is 0.01–0.02. The guarantee is bought with abstention: at the score
quality of the FLAMeS mean probability (candidate AUC ≈ 0.73; the top-ranked candidate is false in 16.5 %
of MSLesSeg scans) no valid per-scan rule can select much. The envelope is not the bottleneck — the
score is. With a strong score (synthetic μ = 3) the same Layer-2 procedure keeps 0.37–0.95 power.

## 6. Discussion

### 6.1 What a deployer can rely on
Within a site and a segmenter, marginal lesion-FDR control is reliable and transports to a similar
site. Per-scan control — what a clinician reading one scan needs — requires calibrating at the level of
the scan: candidate-level guarantees assume away a scan random effect that is present in MS MRI. With
scan-level calibration, the certificate a deployer can rely on is one-sided and strong: a *certified*
DIS or region count is wrong with probability ≤ δ, including on healthy subjects, where uncertified
readings of the same segmentation call DIS in one scan in five. It is not a detector: most scans receive
no certificate. Calibration must be redone with labelled subjects from the target population when the
population (e.g. screening of healthy subjects) or the segmenter changes; with the segmenter the failure
mode is silence (no selections), not false reassurance.

### 6.2 The cost: recall
At the score quality of current models (candidate-level AUC ≈ 0.75–0.82), guaranteed precision is
bought with low lesion-level recall (≤ 0.30 end-to-end at α = 0.3, ≈ 0.01–0.05 at α = 0.1). The
guarantee makes the trade-off explicit; it does not remove it. Better scores, not better conformal
wrappers, move this frontier.

### 6.3 Claims we retracted (negative-results record)
1. *"Conformal lesion-FDR breaks across MS site shift."* Refuted by our own clean axis (§4.1).
2. *"The guarantee transports despite non-exchangeability."* The non-exchangeability was an artifact
   of a candidate-level KS test and many-to-one matching; at the scan level the laws are
   exchangeable (§4.1).
3. *"44–95 % of scans exceed α."* An exceedance denominator restricted to scans that selected
   something; over all scans the figure is 3–17 % (§4.2).
Each retraction came from an independent adversarial review of code and claims and is pinned by a
regression test.

### 6.4 Limitations
Two same-segmenter patient cohorts is a small number of acquisition-shift sites; a self-trained
single segmenter applied to further held-out cohorts is the planned extension. Healthy-control and
ISBI provenance/licensing must be confirmed for publication. The per-scan guarantee of §5 is marginal
over the calibration draw, not conditional on one calibration set.

## Reproducibility

| result | script | record |
|---|---|---|
| §4.1 (any-voxel), §4.3, §4.4 | `scripts/calm-ms/multisite_conformal_fdr.py` | `backend/app/services/assets/multisite_conformal_record.json` |
| §4.1 (one-to-one), §4.2, permutation test | `scripts/calm-ms/multisite_conformal_advanced.py` | `backend/app/services/assets/multisite_conformal_advanced_record.json` |
| cohort handling / leakage rules | `scripts/calm-ms/cohort_registry.py` | — |
| regression tests | `scripts/calm-ms/tests/` | — |
| base segmenter for more sites | `research/nnunet/train_base_segmenter.ipynb` | — |

## References (to be formatted; entries marked *verify* need a checked citation)
- Bates, Candès, Lei, Romano, Sesia (2023). Testing for outliers with conformal p-values. *Annals of Statistics* 51(1).
- Blanchard, Neuvial, Roquain (2020). Post hoc confidence bounds on false positives using reference families. *Annals of Statistics* 48(3):1281–1303.
- Dunn, Wasserman, Ramdas (2023). Distribution-free prediction sets for two-layer hierarchical models. *JASA* 118(544):2491–2502.
- Gazin, Blanchard, Roquain (2024). Transductive conformal inference with adaptive scores. *AISTATS*, PMLR 238:1504–1512.
- Isensee et al. (2021). nnU-Net. *Nature Methods* 18:203–211.
- Jin, Candès (2023). Selection by prediction with conformal p-values. *JMLR* 24(244).
- Katsevich, Ramdas (2020). Simultaneous high-probability bounds on the false discovery proportion in structured, regression and online settings. *Annals of Statistics* 48(6).
- Lesjak et al. (2018). A novel public MR image dataset of multiple sclerosis patients with lesion segmentations based on multi-rater consensus. *Neuroinformatics* 16 — *verify*.
- Rondinella et al. (2025). MSLesSeg: baseline and benchmarking of a new multiple sclerosis lesion segmentation dataset. *Scientific Data*.
- Song, Jin, Candès (2026). Everywhere valid bounds on false discovery proportions in conformal inference. arXiv:2605.20726.
- Tibshirani, Barber, Candès, Ramdas (2019). Conformal prediction under covariate shift. *NeurIPS*.
- Wiltgen et al. (2024). LST-AI. *NeuroImage: Clinical* — *verify*.
- FLAMeS — *verify citation*. Healthy-control cohort — *verify source*. Conformal MS diagnosis (npj Digital Medicine 2025) — *verify*. arXiv:2510.17897 — *verify*.
