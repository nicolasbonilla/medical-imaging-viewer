---
title: "Where did the gain come from? Two pre-registered negative results in multiple sclerosis lesion segmentation: thick-slice augmentation and learned false-positive filtering"
short_title: "Two pre-registered negative results in MS lesion segmentation"
author:
  - name: "N. G. Bonilla Vargas"
    affiliation: "MSTool-AI [TODO: full affiliation and city]"
    corresponding: true
    email: "[TODO: corresponding e-mail]"
  - name: "[TODO: co-authors, if any; see Author contributions]"
date: "Draft v0.2, 2026-10-31"
bibliography: references.bib
keywords: [multiple sclerosis, lesion segmentation, FLAMeS, nnU-Net, slice thickness, data augmentation, fine-tuning, false-positive reduction, deep ensembles, site confounding, shortcut learning, pre-registration, negative results]
---

> **Submission note (internal; delete before submission).** Recommended venue: **MELBA (Machine
> Learning for Biomedical Imaging)** as a full-length paper. It publishes long methodological papers
> for the medical-imaging machine-learning community, had no article processing charge when checked
> on 2026-10-17 (a small submission fee was mentioned), and its readers are the people who run the
> experiments these lessons are about. **Alternative: PLOS ONE**, which judges submissions on rigour
> rather than on the direction of the result and accepts negative and null results (an article
> processing charge applies; check the current fee and waivers). A 4-page version could also go to an
> "I Can't Believe It's Not Better" (ICBINB) workshop at NeurIPS or ICLR if a call is open; past
> editions were non-archival, which would not block the journal version (verify for the edition you
> target). Before submission: fill the TODOs, confirm the references flagged in `references.bib`,
> archive the code, records and `data/github_timing_evidence_2026-10-31.json` on Zenodo, and re-run
> `scripts/check_numbers.py`.

## Structured abstract

**Background.** Pre-registered negative results are rare in medical-image segmentation. We report two
pre-registered studies from one research programme on multiple sclerosis (MS) lesion segmentation with
FLAMeS, a public single-FLAIR nnU-Net. Neither delivered a gain that held up against the appropriate
control or comparator. Both teach something general about how gains are made and attributed.

**Methods.** *Study 1 (FLAMeS-thick)* fine-tuned FLAMeS fold 0 on MSLesSeg-train with an on-the-fly
simulation of thick-slice 2D acquisition (arm A). A matched control arm (B) had identical fine-tuning
without the simulation. Training used two free Kaggle T4 GPUs. Evaluation used 211 scans from five
public sources: 179 real thick-slice scans (3.9–8.3 mm) from three sites never used for training, and
32 scans delivered at 1 mm, of which 10 were acquired thin. *Study 2* tested a learned lesion-level
false-positive filter in three pre-registered stages: v3 (new FLAIR and probability-map features, two
cohorts, 4,400 candidates), v3.1 (fold-disagreement features, three unseen thick-slice sites, 6,493
candidates) and v3.2 (100 healthy controls). Each protocol fixed its endpoints, smallest effects of
interest, comparators and decision rules before any result of the model under test existed; what was
already known about the comparators is declared in each protocol. The protocols are dated by git
commits whose hashes we report.

**Results.** *Study 1:* on the thick-slice sites, arm A improved lesion-wise F1 over the original model
by +0.025 [95 % CI +0.010, +0.039] and had fewer false lesions (ratio 0.810 [0.763, 0.862]). The point
estimate is below the pre-registered smallest effect of interest (+0.03), so the primary result is
*inconclusive*. Non-inferiority at 1 mm was *not shown*: on Ljubljana-10, the only site acquired as thin
3D FLAIR, Dice fell by 0.172. The simulation had no detectable effect over the control arm (ΔF1 −0.005
[−0.017, +0.006]); fine-tuning on MSLesSeg alone explained the gain (B vs original +0.030 [+0.016,
+0.044]). *Study 2:* v3 did not meet its criterion (ΔAUROC +0.014 [−0.012, +0.041]); its 42 features
identified the cohort with AUROC 0.98. v3.1 met its criterion against the single-fold probability
(AUROC 0.721 → 0.832). In a post-hoc analysis with candidates taken from the 5-fold mean map, FLAMeS's
default ensemble, the learned filter added only +0.013 [+0.008, +0.018]. v3.2 did not meet its
criterion (+0.017 [+0.005, +0.030]). Healthy-control false candidates were recognisable as a cohort
(AUROC 0.848), and a model trained with them as its only negatives did not transfer to patients' false
candidates (ΔAUROC −0.168 against the ensemble mean). None of the models was adopted. Study 1 used
0 USD of training compute and 1.42 USD (list price) of evaluation compute.

**Conclusions.** We draw four lessons. (1) Cohort identity (site, preprocessing and, with healthy
controls, possibly health status) is easy for a model to learn, so probe it before modelling and gate
on it. (2) Fine-tuning alone can produce a gain that looks like an augmentation effect; a matched
no-augmentation arm exposed this. A test site from the fine-tuning source can also hide an
out-of-domain loss in a pooled non-inferiority test; a separate thin-data guard rail exposed that.
(3) The comparator for a learned filter is the ensemble as it is meant to be used, including its
candidate map, not a single fold. (4) Pre-registration turned "statistically positive" into
"inconclusive" and kept a model that lost sensitivity on thin 3D FLAIR from being adopted. It did not
choose the right candidate definition, and it is only third-party verifiable if the protocol is public
before the run.

---

## 1. Introduction

Automatic segmentation of MS white-matter lesions on FLAIR MRI performs well on curated, thin-slice
research data [@dereskewicz2025flames; @wiltgen2024lstai]. Two practical problems remain for clinical
use. First, routine scans often have thick 2D slices, and small lesions are missed more often as
slices get thicker; the reference model in Study 1 shows this pattern (Fig. 3). Second, segmenters
produce false lesions, and on healthy brains FLAMeS's false candidates can look at least as confident
as real lesions (§3.2, v3). The literature offers fixes for both problems. Resolution-agnostic training
simulates low-resolution acquisitions during training [@billot2023synthseg; @goebl2025mindglide].
Lesion-level false-positive filters or uncertainty scores re-rank candidate lesions
[@nair2020uncertainty]. Both are usually reported as positive results on held-out data.

This paper reports two pre-registered attempts, one for each problem, that did not deliver the hoped-for
gain. Each was built on FLAMeS, a public single-FLAIR nnU-Net trained on 668 scans
[@dereskewicz2025flames; @isensee2021nnunet; @larosa2025flamesweights]. Study 1 asked whether
fine-tuning FLAMeS with simulated thick-slice acquisitions improves lesion detection on real
thick-slice scans from unseen sites. Study 2 asked whether a learned, lesion-level classifier can
separate true from false candidate lesions better than the segmenter's own probability, across cohorts
and on healthy brains. The second question matters because such a score is what powers conformal
lesion selection [@jin2023selection; @benjamini1995fdr].

We report these studies because their failures are informative, and because such results are rarely
published [@fanelli2012negative]. Read without its controls, either study would have yielded a
publishable positive claim: "thick-slice augmentation improves F1 on three unseen sites, CI excluding
zero, and cuts false lesions by 19 %", or "a learned filter raises lesion-level AUROC from 0.72 to 0.83
on three unseen sites". Both would have been wrong about *where the gain came from*. In Study 1 a
pre-registered control arm exposed this. In Study 2 the second claim *was* the pre-registered primary
result; only a post-hoc comparison with the ensemble as it is meant to be used exposed it. We organise
the discussion around four lessons: site and cohort confounding; fine-tuning masquerading as an
augmentation gain, with an in-domain test site hiding a loss; learned filters versus ensembles; and the
value, and the limits, of pre-registration.

## 2. Methods

### 2.1 Programme context

Both studies belong to an open research programme that evaluates lesion-level reliability for an
investigational MS imaging application. Research code is kept separate from any medical-device code,
and no product code was changed by either study. Both studies were designed to inform decisions about
that application; their decision rules are part of the protocols. Study 2 was preceded by an
unregistered version (v2, August 2026). An internal adversarial review later retracted its headline
cross-site claim: its shift test had altered only the false candidates, and its calibration data had
also been used for training, a form of leakage [@kapoor2023leakage]. The honest leave-one-site-out AUROC of v2 was 0.624, below raw
probability. That episode is why every later stage was pre-registered.

### 2.2 Pre-registration practice

Each protocol was written as a Markdown file and committed to the project's git repository before the
model under test was trained or scored. The protocol fixed the hypotheses, primary endpoint, smallest
effect of interest [@lakens2017equivalence], comparators, models and hyper-parameters, seeds,
resampling, decision rules and pre-stated limitations. Each protocol has a change log (Study 1, §14) or
deviations log (Study 2, §10–§11). Every entry records its date and whether any result existed at that
time. Analyses added after results were seen are labelled *post hoc* and could only weaken a claim.

The comparators were not blind, and each protocol says what had been seen. For Study 1, the reference
model's behaviour on the thick-slice sites was known from an earlier internal audit by the same author,
which motivated the study. For v3, the raw-probability AUROCs and the v2 results on the same two
cohorts were known. For v3.1, all v3 results were known, so only the three new sites are confirmatory.
For v3.2, all MS-side results were known, and an earlier analysis by the same author (committed the
same day) had reported the ensemble-mean scores of the 263 control candidates. In v3.2 only the
learned, fold-disagreement and LST-AI values of the control candidates were blind.

The registrations are not in an external registry such as OSF. Table 1 therefore reports three kinds
of evidence: the commit hashes, the SHA-256 of each protocol file as first committed, and the earliest
time at which the protocol was public on GitHub. Pull-request creation times remain queryable on
GitHub. Push times come from GitHub's repository events, which are kept only for a limited period, so
we archived the responses queried on 2026-10-31 (`data/github_timing_evidence_2026-10-31.json`). The
repository was public when queried. [TODO: confirm it was public on the dates in Table 1.]

**Table 1. Pre-registration record.** Times are UTC. Commit times are author-controlled. "First public"
is a GitHub pull-request or push timestamp. Full 40-character commit hashes and 64-character SHA-256
values are in Appendix A.

| Study / stage | Protocol commit (time) | Protocol SHA-256 (first 16) | Results commit (time) | Protocol first public |
|---|---|---|---|---|
| Study 1, FLAMeS-thick | `5b286f2` (2026-10-21 03:57) | `7fa1bb50e208d654` | `b19293c` (2026-10-23 10:09) | 2026-10-21 05:08 (PR #56), before any Kaggle session |
| Study 2, detector v3 | `59cc796` (2026-10-17 17:30) | `9c411143b124d350` | `a5b6308` (2026-10-17 18:47) | 2026-10-21 03:14 (PR #55), **together with its results** |
| Study 2, detector v3.1 | `129d2ff` (2026-10-21 02:14) | `effcbbc359ca6367` | `d451fbb` (2026-10-21 03:13) | 2026-10-21 03:14 (PR #55), **together with its results** |
| Study 2, detector v3.2 | `3c24977` (2026-10-24 16:26) | `461c9819c8dc039c` | `90797a9` (2026-10-24 17:02) | 2026-10-24 16:26 (push), 37 min before the results push |

In every case the protocol commit is an ancestor of the results commit. For Study 1, the protocol was
public about 11 hours before the first Kaggle session. The amendment that moved training to Kaggle and
fixed the epoch rule and pilot checks (`73e9651`) was pushed at 17:19:42, 31 s before the first full
training session started at 17:20:13. The smoke and pilot sessions ran before it, but no study model
existed then. The logged early-look decision (`aba9a54`) was pushed at 18:40:54, before the second
session at 18:42:02. Every Kaggle session also records the git commit it ran. For v3 and v3.1, the
protocols first reached GitHub in the same push as their results. Their precedence therefore rests on
author-controlled commit timestamps and the commit graph (Fig. 6). We return to this in §4.4.

### 2.3 Data and training-set overlap

All data are public (Table 2). Study 1 fine-tuned on 78 of the 93 MSLesSeg-train scans (patients
P1–P53) [@guarnera2025mslesseg; @mslesseg2025data]; the other 15 formed an internal monitoring split. A
hard-coded guard, covered by unit tests, refused every evaluation scan. The thick-slice evaluation
sites were MS3SEG [@bawil2026ms3seg], Muslim et al. [@muslim2022baghdad] and PediMS [@popa2025pedims].
The 1-mm sites were the ten Ljubljana patients never used by any FLAMeS fold [@lesjak2018ljubljana] and
the MSLesSeg test split. Study 2 used MSLesSeg (all 115 scans of 75 patients) and the same ten
Ljubljana patients for training and testing. v3.1 and v3.2 added the three thick-slice sites as
external tests, and v3 (30 scans) and v3.2 (100 scans) added SibBMS healthy controls
[@tuchinov2025sibbms].

**Table 2. Cohorts.** Slice spacing is the largest voxel side.

| Cohort | Scans / patients | Slice spacing | Role | Relation to FLAMeS training |
|---|---|---|---|---|
| MSLesSeg train (P1–P53) | 93 / 53 | 1 mm MNI (native 2–5 mm) | Study 1 fine-tuning (78) and monitoring (15); Study 2 train/test | Clean: 0 of 115 MSLesSeg scans match the FLAMeS training fingerprint |
| MSLesSeg test (P54–P75) | 22 / 22 | 1 mm MNI (native 2–5 mm) | Study 1 H2 (in-domain for arms A and B); Study 2 train/test | Clean |
| Ljubljana-10 (patients 16–20, 26–30) | 10 / 10 | 3D FLAIR, MNI 1 mm | Study 1 H2 guard rail; Study 2 train/test | Never in any FLAMeS fold |
| MS3SEG | 100 / 100 | 6.0–8.1 mm (2D axial) | Study 1 H1; Study 2 external (v3.1, v3.2) | Excluded by the fingerprint, which has no case with spacing ≥ 3 mm or an axis < 40 voxels |
| Muslim et al. (axial subset) | 51 / 51 | 4.86–8.3 mm; in-plane size estimated | as MS3SEG | as MS3SEG |
| PediMS | 28 / 9 children | 3.9 mm | as MS3SEG | as MS3SEG |
| SibBMS healthy controls | 30 (v3), 100 (v3.2) | 1 mm, template-normalised | Study 2 negatives only | Not among FLAMeS's cited training sources |

*Training-set overlap.* FLAMeS was trained on, among others, ISBI-2015 [@carass2017isbi], MSSEG-2016
[@commowick2018msseg] and 20 of the 30 Ljubljana scans. We never used ISBI-2015 or MSSEG data. We used
only the ten clean Ljubljana patients in every primary analysis; the other 20 served only as a
contamination reference and in one exploratory v3 analysis. That reference confirmed that the overlap
matters: on FLAMeS-trained Ljubljana scans, 59 % of the false candidates are fragments of real
lesions, against 29 % on the clean scans. LST-AI, used in Study 2 only as an agreement feature, was
trained on 491 in-house scans [@wiltgen2024lstai]; we did not verify its training data independently.

*Other caveats.* The MSLesSeg test split shares source, protocol and annotators with the fine-tuning
set, so it is in-domain for arms A and B. MSLesSeg is delivered at 1 mm, but its native FLAIR slice
thickness is 2–5 mm; only 8 of the 93 training scans were acquired at 4–5 mm. The only site acquired
as thin 3D FLAIR is Ljubljana. Its images also differ from MSLesSeg in other ways: they are rigidly
placed in MNI space rather than size-normalised (brain volume about 1.2–1.4 L against about 1.8–2.0 L),
N4-corrected and winsorised, and come from a different scanner.

### 2.4 Base segmenter

FLAMeS (nnU-Net v2, `Dataset004_WML`, `nnUNetTrainer_8000epochs`) was run on CPU with tile step 0.5,
Gaussian weighting and no test-time mirroring. The fold-0 checkpoint has SHA-256
`4fc7db24…df861`. Probability maps were stored on the FLAIR grid. All arms received identical inputs:
the evaluation job checked the SHA-256 of every input and aborted on any mismatch. MS3SEG, Muslim and
the SibBMS controls were skull-stripped once with HD-BET [@isensee2019hdbet] and the result was reused.
"Ensemble" means the mean probability of the five FLAMeS folds [@lakshminarayanan2017ensembles],
FLAMeS's default way of combining its folds (here without test-time mirroring).

### 2.5 Study 1 — FLAMeS-thick

*Arms.* R is FLAMeS fold 0, unchanged. A is R fine-tuned on MSLesSeg-train with the thick-slice
simulation. B is identical to A without the simulation (probability 0). E is the original 5-fold
ensemble, included as context. A and B used the same initial weights, split, schedule and GPU model,
and trained side by side, one T4 each, in every session.

*Training.* The FLAMeS plans were transferred unchanged, and all fold-0 weights, including the
segmentation heads, were loaded strictly. Training ran for 300 epochs of 250 iterations (batch 2) with
SGD (Nesterov momentum 0.99). The initial learning rate was 10⁻³, with a 5-epoch warm-up and
polynomial decay. nnU-Net's default augmentation was kept. The final checkpoint was evaluated with no
checkpoint selection. Training is not bit-reproducible, because nnU-Net's data loader restarts after a
pause.

*Simulation (arm A).* With probability 2/3, each training image was made to look like a 2D multi-slice
acquisition. Slice thickness was drawn uniformly from 3–8 mm and the axis was axial with probability
0.8. Half of the samples had a gap of 0–0.5 × thickness. The slice profile was a box or a Gaussian,
and the grid phase was random. The image was resampled back by nearest-slice (probability 0.7) or
linear interpolation. Labels were left untouched.

*Outcomes.* A lesion is an 18-connected component of 3 mm³ or more in the prediction (probability ≥
0.5) or in the expert mask. Prediction and expert lesions were matched one-to-one by Hungarian maximum
IoU, with IoU > 0 as the primary rule and IoU ≥ 0.10 as a sensitivity analysis. For each scan we
computed lesion-wise F1 = 2TP / (2TP + FP + FN), the number of false lesions and voxel Dice
[@maierhein2024metrics].

*Hypotheses and decision rules (fixed before any study model existed).* **H1 (primary)**, on the pooled
thick-slice sites (179 scans, 160 patients), A vs R: success required the lower ΔF1 confidence bound
> 0, ΔF1 ≥ +0.03 (the smallest effect of interest), and the upper bound of the false-lesion ratio CI
≤ 1.10. The result was *refuted* if the ΔF1 upper bound was < +0.03 or the ratio's lower bound was
> 1.10, and *inconclusive* otherwise. **H2** (non-inferiority at about 1 mm, 32 scans): the pooled
ΔDice lower bound had to be > −0.02 and the ΔF1 lower bound > −0.03. In addition, on Ljubljana-10, the
point estimates had to satisfy ΔDice ≥ −0.02 and ΔF1 ≥ −0.03. A model failing H2 is "not deployable"
whatever H1 says. **H3** (mechanism): A vs B on the thick sites. An augmentation effect counted as
shown if the ΔF1 lower bound was > 0. Secondary analyses were S1 (detection by lesion size and
thickness band), S2 (per-site metrics), S4 (A vs E), S5 (MSLesSeg test by native thickness), S6
(strict matching; excluding one atypical PediMS patient) and S7 (fit on the internal monitoring split).

### 2.6 Study 2 — lesion-level false-positive filter (v3, v3.1, v3.2)

*Candidates and labels.* A candidate is an 18-connected component of the FLAMeS probability map at or
above 0.5 with volume ≥ 3 mm³. A candidate is TRUE if it is matched one-to-one (Hungarian, IoU > 0) to
an expert lesion, and FALSE otherwise. Surplus fragments of a real lesion therefore count as FALSE.
Features never use ground truth, and a unit test checks this. Reproduction gates required candidate and
label counts to equal earlier records before any modelling.

*Models.* The primary model was an L2 logistic regression (C = 0.1) after median imputation,
winsorisation at the training 1st/99th percentiles and standardisation. The secondary model was
gradient boosting (depth 3, 300 iterations). There was no tuning, and the seed was 20261017.

*v3* (protocol 2026-10-17). The 42 v3 features comprise 9 grid-invariant v2 features (probability
moments and shape) and five new families, 17 of the 42 features being derived from FLAIR intensities.
The new families are FLAIR contrast against a normal-appearing white matter shell, FLAIR texture,
boundary sharpness on FLAIR and on the probability map, persistence of the candidate across probability
thresholds, and location proxies scaled to each brain without MNI coordinates. The primary endpoint was
the pooled leave-one-cohort-out lesion-level AUROC: train on MSLesSeg and test on Ljubljana-10, and the
reverse, giving 4,400 candidates from 85 patients. The model was V3-LR, compared with the raw fold-0
mean probability. Success required ΔAUROC ≥ +0.05 with the paired CI lower bound > 0.

*v3.1* (protocol 2026-10-21). This stage added the *fold-disagreement* family (F8): across-fold mean
and SD of the candidate's mean probability, fraction of folds detecting the candidate, voxelwise
variance and mutual information. It also added an LST-AI agreement family (F9). The model was a
"grid-robust" logistic regression (GR-LR, 14 features computable at any resolution). It was trained on
all MSLesSeg and Ljubljana-10 candidates and tested on the three never-analysed thick-slice sites
(6,493 fold-0 candidates, 160 patients). The primary comparator was the raw fold-0 probability, with
the same +0.05 criterion. Key secondaries were H2 (GR-LR vs the ensemble mean, scored on the same
fold-0 candidates), H3 (fold disagreement adds), H4 (fold disagreement, and separately LST-AI
agreement, less site-specific than each FLAIR family) and H4b (the same, per new site). Analyses on
MSLesSeg and Ljubljana-10 re-used v3 data and are not confirmatory.

*v3.2* (protocol 2026-10-24). Candidates came from the 5-fold *mean* map. This choice followed the
v3.1 post-hoc finding. The stage added 100 SibBMS healthy controls; all 263 of their candidates are
false. The primary endpoint was the out-of-fold AUROC separating real 1-mm MS lesions from control
candidates, for GR+C-LR (GR trained with the controls) against the ensemble mean. The criterion was
again +0.05 with the CI lower bound > 0. A pre-registered *confound gate* addressed the fact that the
controls differ from the patients in three ways at once: health status, site, and template
normalisation. It had three parts. K2 was a cohort-identity probe on false candidates only, read as
"controls identifiable" above 0.70. K3 was a transfer test: a model trained with controls as its only
negatives must also reject MS false candidates. K4 removed the template-scaled volume feature. A
learned re-scorer could be proposed only if H1, H3 and H4 were met and the gate passed.

### 2.7 Statistical analysis

Study 1 used a paired percentile bootstrap over patients [@efron1993bootstrap] with B = 10,000 and seed
20261021. The size-bin tables used 2,000 draws, as written in the analysis code before any map existed.
Study 2 used a patient-clustered percentile bootstrap, stratified by cohort, with B = 2,000 and seed
20261017 plus fixed offsets. Paired differences used the same resamples. AUROC was computed as the
Mann–Whitney statistic with ties averaged [@hanley1982auc]. In Study 2 the bootstrap holds each fitted
model fixed. Refit variance was measured separately: 50 patient-bootstrap refits in v3 and in v3.1.
Secondary endpoints carry no multiplicity correction and no verdicts unless the protocol defined one.
Study 2's secondary conformal analyses used conformal p-values [@jin2023selection] and per-scan
Benjamini–Hochberg selection [@benjamini1995fdr], with calibration patients kept disjoint from
training patients.

### 2.8 Compute and cost

Google Cloud blocked GPU jobs in the research project. Study 1 therefore moved, before any study run,
to Kaggle's free GPUs. Each session used two NVIDIA T4s, one per arm, and four vCPUs. Sessions lasted at
most 12 h; each run paused at a soft deadline and resumed in the next session. Training took 20.7 h of
session time over three sessions, plus 0.45 h of smoke and pilot sessions, for 0 USD. The evaluation
(211 scans × 2 arms) ran on two 4-vCPU cloud CPU VMs at 68 s per case-model, plus a 5-scan pilot. It
used 8.09 VM-hours and cost 1.42 USD at list price. The Study 2 evaluation scripts ran on the author's
workstation (v3 16 min, v3.1 6.7 min, v3.2 4.8 min, as recorded; feature extraction was not timed).
Both studies also consumed probability maps produced by shared cloud runs: FLAMeS 5 folds, LST-AI, and
skull-stripping of the controls. Those runs took 61.82 VM-hours and cost 11.35 USD at list price, and
they also served other studies. All cloud costs in these totals were charged against a free-trial
credit (estimated from list prices; not yet reconciled with the billing report). The research project's
total list-price spend to date, for all studies, is 26.22 USD. The fold-0 maps used for the v3
candidates came from earlier (August 2026) runs paid by another account and are not included.

### 2.9 Deviations

**Table 3. Deviations and changes, with timing.**

| Study | Change | When | Results existing then |
|---|---|---|---|
| 1 | Platform changed from Vertex AI Spot GPU to Kaggle 2 × T4. Unchanged: GPU model, code, software lock, schedule, augmentation, split and initial weights. | 2026-10-21, before any study run | no study model; only the Kaggle pilot (2 training scans) |
| 1 | 15-USD epoch rule replaced by a GPU-quota rule (E = 300 kept). | 2026-10-21, after the pilot | pilot models only |
| 1 | Pilot criterion (internal pseudo-Dice > 0.5 after fine-tuning on one scan) found mis-calibrated and replaced by a GPU-parity check and an early-look rule. | 2026-10-21, before the full runs | pilot models only |
| 1 | S1 size tables used 2,000 bootstrap draws (code) rather than 10,000 (protocol text). S2 and S5 are reported without CIs because the pre-registered code does not bootstrap them. | in code before any map existed | none |
| 2 (v3) | D1: fragment-free re-scoring. D2: refit variance for the 10-patient direction. D3: an empty public T1 (MSLesSeg P49_T2) disables only the exploratory T1 family. D4: site probe folds stratified by cohort, after a dry run on random features showed a pooled-AUROC bias (0.31 for uninformative features). | 2026-10-17, before any outcome | none |
| 2 (v3.1) | None to the registered analyses. Post hoc: candidates redefined on the 5-fold mean map. | 2026-10-21, after outcomes (labelled) | all v3.1 results |
| 2 (v3.2) | D1: the K2 probe uses the fold-wise mean AUROC, because a dry run showed pooled out-of-fold AUROC biased below 0.5 (0.470 / 0.440 / 0.419 vs fold-wise 0.502 / 0.492 / 0.498). | 2026-10-24, before any control feature | none |

## 3. Results

### 3.1 Study 1 — FLAMeS-thick

All 211 scans were evaluated for every arm, with 0 errors and none dropped. Every evaluation input and
expert mask matched the reference runs. Training finished as pre-registered: 300 epochs per arm, three
sessions, two clean pause-and-resume hand-overs. On the 15 internal monitoring scans, nnU-Net's
patch-based pseudo-Dice stayed between 0.799 and 0.846 for A and between 0.807 and 0.856 for B, and
the whole-scan validation Dice was 0.737 (A) and 0.757 (B), against 0.689 for unchanged FLAMeS (S7).
This shows that the models fitted the fine-tuning domain. It cannot show that they kept FLAMeS's
original domain; Ljubljana-10 (H2) is the closest evidence, and it shows a loss.

**Table 4. Study 1, pre-registered verdicts** (thick sites: 179 scans, 160 patients; 95 % CIs).

| Hypothesis | Estimate | Verdict |
|---|---|---|
| H1: A vs R, ΔF1 | +0.025 [+0.010, +0.039] (A 0.632 vs R 0.607) | **inconclusive**: CI excludes 0, but the point estimate is below +0.03 |
| H1: A vs R, false-lesion ratio | 0.810 [0.763, 0.862] (11.24 vs 13.87 per scan) | passes the 1.10 margin |
| H2: pooled ~1 mm, ΔDice / ΔF1 | −0.004 [−0.063, +0.054] / −0.022 [−0.084, +0.034] | **not shown**: both lower bounds outside the margins |
| H2: Ljubljana-10 guard rail, ΔDice / ΔF1 | −0.172 / −0.181 | **fails** → A is "not deployable" |
| H3: A vs B, ΔF1 | −0.005 [−0.017, +0.006]; false-lesion ratio 1.107 [1.051, 1.176] | **augmentation effect not shown** |
| context: B vs R, ΔF1 | +0.030 [+0.016, +0.044]; false-lesion ratio 0.732 [0.688, 0.775] | (estimate) |
| S4: A vs E, ΔF1 | +0.000 [−0.013, +0.013]; false-lesion ratio 0.981 [0.921, 1.048] | (estimate) |

The thick-site gain was consistent across sites but small (Fig. 1a). ΔF1 was +0.026 [+0.008, +0.044]
for MS3SEG, +0.025 [−0.002, +0.052] for Muslim and +0.018 [−0.030, +0.056] for PediMS. No site showed
harm. The sensitivity analyses agreed. Strict matching gave +0.018 [+0.002, +0.033], and excluding the
PediMS patient with Baló-type lesions gave +0.025 [+0.010, +0.039]. Both are inconclusive under the H1
rule. Fewer false lesions was the clearest change: the false-lesion ratio was 0.868, 0.773 and 0.673 at
the three sites (Fig. 1b).

Three results locate the source of the gain. First, the control arm B, fine-tuned without any
simulation, did as well as or better than A on thick slices. B's F1 was 0.637 against A's 0.632, and B
had fewer false lesions (10.15 against 11.24 per scan). With one training run per arm, differences of
this size between A and B cannot be separated from run-to-run variance. Second, the change in what the
models detect runs opposite to the hypothesised mechanism (Fig. 3; secondary estimates with marginal,
overlapping CIs). On the thickest bands, detection of 14–50 mm³ lesions was lower with A: 0.38 against
0.44 for R at 4.5–6.5 mm, and 0.33 against 0.42 above 6.5 mm. Detection of lesions ≥ 500 mm³ was
higher: 0.88 against 0.76, and 0.87 against 0.72. The 50 %-detection size stayed at 50–150 mm³ for
every arm at 4.5–8 mm. Third, the largest gains were in-domain (Fig. 2). On MSLesSeg test, F1 rose from
0.66 (R) to 0.71 (A) and 0.72 (B), and false lesions fell from 10.55 to 5.95 and 5.59 per scan. Among
those scans, the A − R gain was largest for the 7 acquired at 4–5 mm (ΔF1 +0.124, ΔDice +0.191)
compared with the 15 acquired at ≤ 3 mm (+0.015, +0.016); these are point estimates without CIs. On
Ljubljana-10, both fine-tuned models lost sensitivity at unchanged precision: 0.60 for R, 0.49 for B
and 0.38 for A, with precision 0.80, 0.82 and 0.82. In the ≤ 1.5 mm band, which pools Ljubljana-10 and
the MSLesSeg test split, detection of the smallest lesions (3–14 mm³) fell from 0.38 (R) to 0.22 (B)
and 0.14 (A). Finally, one fine-tuned model merely matched the original 5-fold ensemble on thick slices
(S4: ΔF1 +0.000).

### 3.2 Study 2 — learned lesion-level false-positive filter

**v3.** The reproduction gate passed exactly: 3,866 candidates (1,348 false) in MSLesSeg, 534 (94) in
Ljubljana-10 and 83 in 30 controls. The primary criterion was **not met** (Fig. 4a). Pooled
leave-one-cohort-out AUROC was 0.742 [0.716, 0.772] for V3-LR against 0.728 [0.703, 0.754] for raw
probability, a difference of +0.014 [−0.012, +0.041]. For every learned model the pooled value sat
below both per-direction AUROCs, because pooling also ranks candidates across two models calibrated to
different base rates; raw probability is immune to this. Gains appeared within one domain (MSLesSeg
patient-grouped CV, 0.835 against 0.735, +0.100 [+0.079, +0.122]) and in the well-powered transfer
direction (MSLesSeg → Ljubljana-10, 0.779 against 0.698, +0.081 [+0.022, +0.142]; 0 of 50 refits below
raw). The reverse direction, training on 10 Ljubljana scans, was unreliable: 58 % of refits fell below
raw. With the same logistic specification, the new families added +0.020 [−0.004, +0.047] over the v2
features (post hoc). The diagnostic finding was the cohort signature (Fig. 5a). The 42 v3 features
identified the cohort (MSLesSeg vs Ljubljana-10) with AUROC 0.98, and the FLAIR boundary family alone
reached 0.83. On the 30 healthy controls, FLAMeS's false candidates looked *more* lesion-like than real
lesions: AUROC for Ljubljana true lesions vs control candidates was 0.371 [0.277, 0.476] for raw
probability.

**v3.1.** The primary criterion was **met** on the three unseen sites (Fig. 4b). AUROC was 0.832
[0.818, 0.846] for GR-LR against 0.721 [0.703, 0.740] for raw fold-0 probability, a difference of
+0.111 [+0.096, +0.125]. The gain held at every site: +0.119 [+0.103, +0.136] for MS3SEG, +0.077
[+0.052, +0.102] for Muslim and +0.128 [+0.062, +0.149] for PediMS. GR-LR also beat the ensemble mean
scored on the same fold-0 candidates, 0.789 [0.774, 0.802], by +0.044 [+0.037, +0.051] (H2 met), and
fold disagreement added +0.074 [+0.060, +0.087] (H3 met). Refit variance was negligible: 50 refits gave
0.831 [0.828, 0.832], none below raw. H4 was met for fold disagreement and not for LST-AI agreement.
Fold disagreement carried little cohort signature between the two 1-mm MS cohorts (pooled
cohort-identity AUROC 0.502, against 0.700–0.855 for the FLAIR families; Fig. 5b). The pooled estimator
is biased downward for weak signals, and the fold-wise v3.2 probe on false candidates of the same two
cohorts gave 0.535. LST-AI agreement gave 0.637, not reliably below FLAIR contrast (separability
difference −0.063 [−0.154, +0.019]). Per new site (H4b), fold disagreement was less site-specific than
the other grid-robust features for MS3SEG (0.524) and Muslim (0.577), but not for PediMS, which every
family identified strongly (pooled cohort-identity AUROC 0.22–0.29).

The post-hoc analysis changed the reading. When candidates are taken from the 5-fold mean map, the
ensemble mean probability alone reaches 0.796 [0.781, 0.812]. GR-LR then reaches 0.809 [0.794, 0.825],
a gain of only **+0.013 [+0.008, +0.018]**. Of that, fold disagreement contributes +0.001 over the same
model without it. The ensemble map yielded 432 fewer false candidates (2,051 vs 2,483; −17.4 %) and 9
fewer true ones (4,001 vs 4,010; −0.2 %) at the external sites (net counts of two independently defined
candidate sets). On Ljubljana-10 the learned model did not beat the ensemble mean with either candidate
definition: +0.011 [−0.019, +0.055] with fold-0 candidates and +0.017 [−0.016, +0.042] with ensemble
candidates. The research recommendation was therefore to keep the 5-fold ensemble and not to adopt the
learned detector.

**v3.2.** Both reproduction gates (file integrity and candidate identity) passed. The control
candidates were identical to those of an earlier analysis by the same author on the same maps, whose
ensemble-mean results on them had been seen before the v3.2 protocol was written: 263 candidates in 85
of the 100 controls, 2.63 per scan. The primary criterion was **not met** (Fig. 4c). AUROC for real
1-mm MS lesions against control candidates was 0.822 [0.787, 0.857] for GR+C-LR and 0.805 [0.764, 0.846]
for the ensemble mean, a difference of +0.017 [+0.005, +0.030]. This is statistically positive but far
below +0.05. The fold-wise version gave +0.021 [+0.008, +0.032], the same reading. Key secondary H2
was met (+0.027 [+0.022, +0.033] over the MS-trained detector), but only because the MS-trained detector
scored below the ensemble on controls. At a threshold that keeps 90 % of real lesions, the ensemble mean
left 1.02 [0.72, 1.35] false candidates per healthy scan and GR+C-LR left 0.97 [0.70, 1.34] (difference
−0.05 [−0.13, +0.09]; H3 not met). The MS-trained v3.1 detector (GR-LR) was *worse* than the ensemble on
healthy brains: 1.31 [0.95, 1.62] false candidates per scan, +0.29 [+0.13, +0.41]. On the unseen MS
sites, training with controls changed nothing: AUROC 0.810 against 0.809, difference +0.001 [−0.002,
+0.003], non-inferior (H4 met). Within the 1-mm MS data it cost nothing either (+0.005 [−0.002, +0.013]
against the ensemble mean). A blindness split gave the same direction on the 30 controls already
analysed in v3 (ensemble 0.838, GR+C-LR 0.852) and on the 70 others (0.793, 0.811). A threshold
calibrated on healthy scans controlled the healthy false-alarm rate as designed (8 of 100 held-out
controls flagged at α = 0.1), but it kept only 16–23 % of real 1-mm lesions visible.

The confound gate failed (Fig. 5c). On false candidates only, where lesion status cannot help, the
grid-robust features told control candidates from MS patients' candidates with fold-wise AUROC
**0.848 [0.806, 0.882]**. Between the two MS cohorts the same probe gave 0.550 [0.469, 0.656].
Brain-size normalisation alone did not explain the separation: MSLesSeg (affine-scaled to MNI, like the
template) gave 0.844, and Ljubljana (rigidly placed, native size) gave 0.855. Site, template resampling
and health status remain confounded. A model whose only negatives were control candidates scored 0.914
on the primary endpoint. On held-out MS candidates, however, it scored 0.650 against 0.817 for the
ensemble, a difference of **−0.168 [−0.202, −0.134]** (K3 failed). A probe trained only to tell MS
false candidates from control candidates, never on a true lesion, scored 0.833 [0.794, 0.866] on the
primary endpoint. That equals GR+C-LR (difference +0.011 [−0.040, +0.058]). Removing the
template-scaled volume feature erased the GR+C-LR gain (+0.003 [−0.004, +0.011]). Among the
descriptive secondaries, fold disagreement alone, with no training, separated real lesions from control
candidates better than the ensemble mean: 0.852 [0.821, 0.883], +0.047 [+0.033, +0.062]. It was,
however, worse than the ensemble mean on MS false candidates (0.800 against 0.817, −0.017 [−0.026,
−0.009]), and it is also what makes the controls recognisable (0.813 [0.767, 0.851]), so its value on
healthy brains is plausible, not established. Self-checks passed. The shuffle-label null had mean
0.477. A separately written re-implementation reproduced the candidates exactly and the AUROCs to four
decimals. The result was stable across bootstrap seeds and without the one control flagged for quality
control.

### 3.3 Timeline

Fig. 6 shows when protocols, amendments, compute and results happened. For Study 1 and detector v3.2,
the protocol was public before the work it governs. For v3 and v3.1 it was not.

## 4. Discussion

Neither study delivered a gain that held up against the appropriate control or comparator. The
informative part is *why*. In Study 1 a straightforward reading would have attributed the gain to the
wrong mechanism; in Study 2 the pre-registered success itself turned out to be mostly a property of the
comparator.

### 4.1 Lesson 1 — Site and cohort are the easiest things to learn

A cohort's identity leaks into many image-derived features, including some designed to be
site-independent. Across our stages this happened in three ways. The 42 v3 features (17 of them
FLAIR-derived) identified the cohort with AUROC 0.98, and the FLAIR boundary family alone with 0.83.
The grid-robust probability-map features identified healthy-control candidates with AUROC 0.85, and
fold disagreement alone with 0.81. A probe that never saw a true lesion matched the primary lesion
model on the primary endpoint (0.833 against 0.822). This resembles the shortcut learning documented in
chest radiographs [@zech2018pneumonia; @degrave2021shortcuts; @geirhos2020shortcut] and the scanner
effects of multi-site neuroimaging [@glocker2019scanner], and the distribution shift already
benchmarked for MS lesion segmentation [@malinin2022shifts2], here at the level of individual
candidate lesions. With one control site we cannot tell whether the control signature reflects the SibBMS site,
its template resampling, or real differences between false marks in healthy and MS brains. Three
practices made the problem visible and, we suggest, should be routine. (i) Run a *cohort-identity
probe* per feature family, on negatives only, before any modelling, and report it next to the main
result. (ii) Run a *transfer test*: a model trained where the shortcut is available must also work
where it is not. Our controls-only model scored 0.914 where the shortcut was available and 0.650 where
it was not. (iii) Distrust pooled out-of-fold AUROCs built from several fold models. Both of our dry
runs on random features showed a bias below 0.5, large enough to make an "uninformative feature"
threshold too easy to pass (Table 3); this also means that our pooled v3 and v3.1 values near 0.5
understate separability. Harmonisation [@fortin2018combat] might reduce the FLAIR signature, but it
cannot separate health status from site when both change together. Only data that break the confound
can: MS patients and controls from the same scanner (SibBMS also releases MS patients), or controls
from a second site in native space.

In Study 1 the same problem appears as confounding between thickness and site. The thick-slice sites
differ from the 1-mm sites in thickness, scanner, population and annotation protocol all at once, and
Ljubljana-10 differs from MSLesSeg also in brain scaling and intensity preprocessing. Neither a gain
"on thick slices" nor the loss "on thin slices" can be attributed to slice thickness alone without a
design that varies thickness alone.

### 4.2 Lesson 2 — Fine-tuning can masquerade as an augmentation gain, and an in-domain site can hide a loss

Without arm B, Study 1 would read as follows: thick-slice augmentation improved F1 on three unseen
thick-slice sites (+0.025, CI excluding zero), cut false lesions by 19 % (fewer at every site), and
improved on held-out scans of its fine-tuning set. All three numbers are correct, and all three would
mislead. The matched control showed no detectable effect of the simulation (−0.005; false-lesion ratio
1.107, with the one-run caveat of §3.1). Fine-tuning on MSLesSeg explains the thick-site gain (B vs R
+0.030), even though the thick sites share no source with MSLesSeg. The size profile of the change, with
fewer small detections and more large ones, fits a transfer of MSLesSeg's annotation style rather than
a better reading of thick slices; that remains a hypothesis we did not test.

The in-domain site matters for the second half of the lesson. The change was largest on the MSLesSeg
test split, which shares its source with the fine-tuning set, smaller on the thick sites and negative on
Ljubljana-10. We did not measure similarity to MSLesSeg, so this ordering is descriptive. Pooled with
the in-domain improvement, the Ljubljana loss produced a wide, uninformative non-inferiority interval;
only the separate guard rail on Ljubljana-10 exposed it. Two design choices therefore did the work: a
control arm identical in every respect except the factor of interest, trained side by side on the same
hardware, and a guard rail on the one thin-acquired site, kept separate from the pooled test. We
recommend both for any augmentation study that also fine-tunes, together with a fine-tuning set that
shares no source with any evaluation site and a report of how detection changes by lesion size.

### 4.3 Lesson 3 — The comparator for a learned filter is the ensemble as it is meant to be used

v3.1 is a pre-registered success whose gain shrank to a small one against the ensemble as it is meant to
be used. The learned detector beat the single-fold probability by +0.111 AUROC on three unseen sites,
consistently, with negligible refit variance. Most of that gain, however, is what the 5-fold ensemble
already provides. It has two parts: the ensemble's candidate map, which yields 17.4 % fewer false
candidates and 0.2 % fewer true ones, and the ensemble's own score. Measured against both, the detector
adds +0.013 AUROC. Whether so small a gain justifies a learned component in a safety-critical path is
an open question; we judged that it did not. The same pattern appeared in Study 1, where one fine-tuned
model only matched the original ensemble (ΔF1 +0.000). It appeared again in v3.2, where the MS-trained
detector made healthy scans *worse* than the plain ensemble at the same sensitivity (1.31 against 1.02
false candidates per scan). The general point is familiar from benchmark culture
[@isensee2024revisited; @varoquaux2022failures]: the strongest cheap baseline must be in the comparison,
and it must be applied as it is used. For lesion-level filters this means defining candidates on the
ensemble map and separating "ensemble candidates" from "ensemble features" in the ablation. The one
training-free signal that separated real lesions from healthy-control candidates, fold disagreement
[@lakshminarayanan2017ensembles; @nair2020uncertainty], comes from the ensemble itself; it was worse
than the ensemble mean on MS false candidates, and its healthy-brain advantage is confounded with site.

### 4.4 Lesson 4 — What pre-registration did, and what it did not do

*What it did.* A fixed smallest effect of interest [@lakens2017equivalence] turned two
"statistically significant" improvements into honest non-findings: +0.025 F1 in Study 1 and +0.017
AUROC in v3.2. A pre-registered non-inferiority guard rail declared arm A not deployable despite its
thick-slice gain. A pre-registered control arm showed that the gain was not due to the augmentation. A
pre-registered confound gate stopped us from reading three v3.2 models that *did* clear +0.05 as better
lesion judgement: gradient boosting (+0.053), LST-AI with controls (+0.066) and the controls-only model
(+0.110). Reproduction gates, shuffle-label nulls and a separately written re-implementation were part
of the protocol, not afterthoughts. The unregistered predecessor (v2) had overclaimed and was
retracted; under the clean protocol of v3 its honest number was approximately reproduced (0.639
against 0.624).

*What it did not do.* First, pre-registration does not choose the right comparison. v3.1 froze the
single-fold probability as its primary comparator and scored the ensemble only on single-fold
candidates (key secondary H2, met). Only a post-hoc analysis with candidates defined on the ensemble map
showed how little the learned model adds to the ensemble as it is meant to be used. Second, it does not
make an endpoint sound. The pooled leave-one-cohort-out AUROC of v3 penalises any learned model whose
two directions are calibrated to different base rates. A dry run on synthetic random features caught
this mechanism before any outcome (deviation D4); we recommend such dry runs as standard. Third, it does
not make comparators blind: the comparators' behaviour was known from earlier work in every stage (§2.2),
which is acceptable only because it is declared. Fourth, a protocol is only third-party verifiable if it
is public before the run. For Study 1 and v3.2 it was. For v3 and v3.1 the protocol reached GitHub in the
same push as its results, and its precedence rests on commit timestamps that the author controls
(Table 1). A push before the run narrows this gap, but repository event logs expire; an external
registry closes it [@nosek2018preregistration]. Fifth, the same team, with one AI coding agent,
designed, ran and analysed every study. Pre-registration constrains that analyst but does not replace
an independent one.

### 4.5 Limitations

Study 1 used one fold and one training seed per arm, so run-to-run variance of fine-tuning is unknown,
and differences between A and B of about 0.005 cannot be separated from it. Ljubljana-10 has ten scans,
and its guard rail has no CI by design. PediMS has nine children. Muslim's in-plane pixel size is
estimated. 3D connected components on 4–8 mm slices can merge or split lesions; the same rule was used
for every arm. Each cohort has one annotation protocol. In Study 2, the bootstrap CIs hold fitted models
fixed, and refit variance was measured only for some analyses. The v3 location proxies failed on three
scans of one patient (imputed). The healthy controls come from one site, are template-normalised, and
are licensed for non-commercial use. Pooled cohort-identity AUROCs in v3 and v3.1 (Fig. 5a, b) are
biased downward for weak signals, so values near or below 0.5 understate separability. LST-AI's
training data were not verified independently. No human reader study was done. None of the protocols
is in an external registry, and the comparators were not blind (§2.2).

## 5. Conclusions

Thick-slice simulation during fine-tuning did not measurably improve FLAMeS on real thick-slice scans,
and the gain that did appear on the thick sites came from fine-tuning on MSLesSeg itself: the matched
arm without simulation did as well. A learned lesion-level false-positive filter beat a single model
but added little to the 5-fold ensemble it would replace. Trained with healthy controls, its small gain
could not be distinguished from recognition of the control cohort: a probe that never saw a true lesion
matched it, and the gain vanished without the template-scaled volume feature. Both studies were cheap:
0 USD of training and 1.42 USD of evaluation for Study 1, and evaluation scripts that ran in minutes for
each stage of Study 2. Both negative results changed what was planned for the application. We hope the
four lessons, and the pre-registration record that makes them checkable, are useful to others who try
the same ideas.

---

## Declarations

**Data availability.** All imaging data are public from their original sources
[@guarnera2025mslesseg; @mslesseg2025data; @lesjak2018ljubljana; @bawil2026ms3seg; @muslim2022baghdad;
@popa2025pedims; @tuchinov2025sibbms]; no image or image-derived map is redistributed. The result
records cited in this paper hold only per-scan or per-candidate summary metrics, with SHA-256 of their
inputs. They are in the public repository `github.com/nicolasbonilla/medical-imaging-viewer`.
Study 1 is at commit `b19293c` on branch `research/flames-thick` (merged into
`research/cloud-compute-ledger` through PR #56): `docs/research/records/2026-10-23_flames_thick_results.json`.
Study 2 is at commit `90797a9` on branch `research/lesion-detector-v3` (PR #55):
`docs/research/records/2026-10-17_*`, `2026-10-21_*` and `2026-10-24_lesion_detector_*`. The compute
ledger is at commit `c8b4239`. Every result number in this manuscript is extracted from these files by
`scripts/extract_results.py` and checked by `scripts/check_numbers.py`; the remaining values (protocol
facts, dataset descriptors, timing evidence) are traced in `NUMBERS_CHECK.md` §3. The GitHub timing
evidence is archived in `data/github_timing_evidence_2026-10-31.json`. [TODO: archive a snapshot with a
DOI (e.g. Zenodo) before submission.] The fine-tuned weights of arms A and B are not released. [TODO:
decide; if released, they must carry: "Fine-tuned from FLAMeS fold 0 (Dereskewicz et al., J
Neuroimaging 2025; F. La Rosa, Zenodo 10.5281/zenodo.17955359, CC BY 4.0) on MSLesSeg-train; changes
by MSTool-AI."]

**Code availability.** The analysis, training and evaluation code is in the same repository:
`research/flames_thick/`, `research/lesion_detector_v3/` and `research/cloud/`. The figure and
number-check scripts are in `docs/research/negative-results/manuscript/scripts/`. [TODO: state the
licence of the research code before submission; the repository has no licence file today.]

**Licences of data and tools.** MSLesSeg data: CC BY 4.0. Ljubljana (open_ms_data): at the time of the
studies we relied on the public mirror's CC BY statement. On 2026-10-28 we found that the laboratory's
official page states CC BY-NC-ND, and we now apply those terms: no Ljubljana-derived model, threshold
or figure is used in any product, and no derivative is redistributed. These research results informed a
decision *not* to adopt either method. MS3SEG, Muslim et al. and PediMS data: CC BY 4.0. SibBMS: the
source states both CC BY 3.0 and CC BY-NC-SA 3.0; we apply the stricter, non-commercial terms, and the
wording is pending clarification with the authors. ISBI-2015 and MSSEG-2016 data were not analysed. They
are relevant only as FLAMeS training data, and they are distributed under their challenges' own terms
of use. FLAMeS weights: CC BY 4.0. nnU-Net: Apache-2.0. HD-BET: code Apache-2.0, weights for
non-commercial use, used only to skull-strip input images (evaluation scans and the SibBMS controls).
LST-AI: MIT-licensed code, used for research only.

**Ethics.** Only public, de-identified datasets were analysed under their licences; no new data were
collected. [TODO: confirm whether the target journal requires a formal statement or waiver.]

**Use of AI assistance.** The protocols, analysis and training code, the execution of the runs and
analyses, and the drafting of this manuscript were carried out with substantial help from an AI coding
agent. This was Claude Opus 5.5 (Anthropic), used through Claude Code, and it is recorded as co-author
in the trailer of every study commit. The agent worked under the direction of the author, who decided
what to study, approved the cloud and Kaggle runs, and is responsible for the content. The agent is not
an author. Safeguards against agent error were: pre-registration before results, reproduction gates,
adversarial self-checks, a separately written re-implementation (v3.2 K6), a separate agent's
adversarial review of this text against the source documents, and a script that checks every result
number in this text against the committed records. These safeguards do not replace an independent
human analyst. [TODO, author: confirm or correct this description of your own role and review.]

**Competing interests.** N. G. Bonilla Vargas develops MSTool-AI, MS imaging software that could
incorporate the methods studied here; neither method was incorporated, because of the results reported
here. [TODO: complete with company role, ownership and any other interests; co-authors' declarations.]

**Funding.** No external funding [TODO: confirm]. Compute used Kaggle's free GPU quota and a cloud
provider's free-trial credit (§2.8).

**Author contributions (CRediT).** N. G. Bonilla Vargas: conceptualisation, funding of compute
accounts, supervision, decisions on runs and on product use [TODO: confirm and add writing – review &
editing once reviewed]. [TODO: co-authors and their roles.]

**Acknowledgements.** We thank the creators of FLAMeS, MSLesSeg, the Ljubljana MS dataset, MS3SEG,
the Muslim et al. dataset, PediMS, SibBMS, nnU-Net, HD-BET and LST-AI for making their work public.

## Figure legends

All figures use a colour-blind-safe palette [@wong2011color] and give every series its own marker.

**Figure 1. Study 1 primary and key secondary results.** (a) Difference in mean per-scan lesion-wise F1
on the thick-slice sites, with the pre-registered smallest effect of interest (+0.03) dashed. (b) Ratio
of mean false lesions per scan, with the 1.10 margin dashed. (c) H2 non-inferiority at about 1 mm:
pooled estimates with CIs and the Ljubljana-10 guard-rail point estimates, with margins −0.02 (Dice,
dashed) and −0.03 (F1, dotted). Paired patient-bootstrap 95 % CIs (B = 10,000). File
`figures/fig1_flames_thick_primary.(png|pdf)`.

**Figure 2. Study 1 per-site means for all four arms** (point estimates; the pre-registered code does
not bootstrap S2). Below the line: the 1-mm sites, one of which (MSLesSeg test) is in-domain for the
fine-tuned arms.

**Figure 3. Study 1 detection by expert lesion volume and slice-spacing band**, with patient-bootstrap
95 % CIs (2,000 draws). Dashed lines mark 50 % and 80 % detection. The CIs are marginal per arm; no
paired comparison between arms was pre-registered for this table.

**Figure 4. Study 2 lesion-level AUROC by stage.** (a) v3, pooled leave-one-cohort-out. (b) v3.1, three
unseen thick-slice sites; hollow markers are the post-hoc analysis with ensemble candidates. (c) v3.2,
real 1-mm MS lesions vs healthy-control candidates, including the two confound probes.
Patient-clustered bootstrap 95 % CIs (B = 2,000).

**Figure 5. Cohort-identity probes.** (a) v3 and (b) v3.1: separability of MSLesSeg from Ljubljana-10
by feature family (pooled out-of-fold AUROC, biased downward for weak signals). (c) v3.2: separability,
on false candidates only, of healthy-control candidates from MS patients' candidates (filled), and of
the two MS cohorts (hollow, reference). Fold-wise AUROC with 95 % CIs. Solid line at 0.5; dashed line
at 0.70, the v3.2 pre-registered reading threshold (shown for reference in a and b).

**Figure 6. Pre-registration timeline.** (a) Study 1: protocol and amendment commits, their first
public appearance on GitHub, Kaggle sessions and evaluation VMs. The results push is shown hollow
because it comes from the author's local log only. (b) Study 2: protocol commit, results commit and
first public appearance for each stage. Commit times are author-controlled; GitHub times are
third-party.

## References

::: {#refs}
:::

---

## Appendix A. Full pre-registration identifiers

| Stage | Protocol file | Pre-registration commit | SHA-256 of the protocol file at that commit | Results commit |
|---|---|---|---|---|
| FLAMeS-thick | `docs/research/flames-thick/PROTOCOL.md` | `5b286f2a105e5f548b80a6ac7766cb47dcc05a13` | `7fa1bb50e208d6541571f698bc40a3c7beb41144f3bb5e6dff6341396f25af7b` | `b19293c48302b93bc6934230ad5ab97627df5362` |
| Detector v3 | `docs/research/lesion-detector-v3/PROTOCOL.md` | `59cc7969cac57d44342bad96cd0e16425d2e3c9e` | `9c411143b124d350081486e2bf48d74a6f158b01ff73541ab39b15cffdcccc9b` | `a5b63081d86c3ba637b3728b0e4660ef9c570e6c` |
| Detector v3.1 | `docs/research/lesion-detector-v3/PROTOCOL-v3.1.md` | `129d2ff6efb70d606b3bc899e5d19a9ac41ade0f` | `effcbbc359ca6367375f689d3652369d5a63b120f590c420d3a2f1a719f855ac` | `d451fbb00cf88a89197790846bb967bea2d09e6c` |
| Detector v3.2 | `docs/research/lesion-detector-v3/PROTOCOL-v3.2.md` | `3c2497747f722d64838484c51c92082a2a3a11bc` | `461c9819c8dc039cd2eb39f7e4df770de17b71b33a0f52ecb897d2d38df75a23` | `90797a93611fcc8e2c8275b738bbf5f1b44921bc` |

Study 1 amendment commits: `73e9651466a85447c36f3c6d1bffb48f0eed7615` (Kaggle platform, epoch rule,
pilot criterion) and `aba9a54e98ea90c85fe062c40b75640417053337` (early-look decision). Training-complete
commit: `c4fd2e588db88efede0b353cd3af73265901fcf2`. Fine-tuned model archives (SHA-256): arm A
`54448dd08e447acec55635655bc097a284cabaa87404bc1b25f13ec78b8ef8cc`, arm B
`9b2aab1d7a5a05603042b4fdc87c86503637edaf9dc9f535d2de4e30ebe71c62`.

## Appendix B. Consequences for the application (for transparency)

No product code was changed by either study. Following the pre-registered decision rules, the
fine-tuned models were not adopted as the segmenter, because H2 failed. The learned false-positive
filter was not adopted, because its gain over the 5-fold ensemble was small and the MS-trained version
was worse on healthy brains. Healthy-control figures from v3.2 are not used in any product material,
because of the SibBMS licence and the single-site design. The research recommendation that remains is
the 5-fold ensemble. A per-lesion fold-disagreement indicator may be described in research
documentation only with the caveats above: it was worse than the ensemble mean on MS false candidates,
and its healthy-brain advantage is confounded with site.
