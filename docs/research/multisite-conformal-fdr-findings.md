# Multi-site conformal lesion-FDR under real MS shift — honest characterization

**Status:** research finding, reproducible on in-hand public data (CPU-only).
**Script:** [`scripts/calm-ms/multisite_conformal_fdr.py`](../../scripts/calm-ms/multisite_conformal_fdr.py)
**Record:** [`backend/app/services/assets/multisite_conformal_record.json`](../../backend/app/services/assets/multisite_conformal_record.json)
**Reviewed by:** 3 independent adversarial agents (statistical validity, data/leakage integrity,
over-claiming/confounds). This document reflects the **post-review** claims — an earlier
"conformal breaks across every MS site shift" headline was **refuted by our own clean axis**
and retracted. See the "What we do NOT claim" section.

Positioning: the conformal wrapper (Jin & Candès selection + Benjamini-Hochberg on
FALSE-candidate calibration scores) is a **faithful application, not a novel method** — see
[`vanguard-methods-protocol.md`](vanguard-methods-protocol.md). The publishable asset is this
**honest characterization** of when the distribution-free lesion-FDR guarantee holds, degrades,
and fails on real multi-site MS data, plus the auditable Class-C substrate.

## Data (four public cohorts, all 1 mm isotropic; FLAMeS or LST-AI probability maps)

| site | segmenter | kind | acquired | cand-scans | subjects | FP score mean | TP score mean |
|------|-----------|------|---------:|-----------:|---------:|--------------:|--------------:|
| openms   | FLAMeS | patients | 30  | 30  | 30 | 0.859 | 0.914 |
| mslesseg | FLAMeS | patients | 115 | 115 | 75 | 0.880 | 0.933 |
| sibbms   | FLAMeS | **controls** | 30 | 27 | 27 | 0.944 | — (0 true lesions) |
| isbi     | LST-AI | patients | 19 | 19 | 19 | 0.748 | 0.809 |

Subject grouping is leak-free (MSLesSeg `P<n>` collapses a patient's timepoints; the others
are single-timepoint). Controls' GT masks are all-zero (verified). Candidate score is the
grid-invariant per-lesion mean probability — **no location feature is used**, because the four
cohorts live on different grids (182/181/197 voxels).

## Finding 1 — the guarantee TRANSPORTS across same-segmenter patient-site shift (robustness)

Realized micro-FDR (subject-level bootstrap 95% CI), cross-site and leave-one-site-out POOLED:

| α | openms→mslesseg | mslesseg→openms | POOLED→openms | POOLED→mslesseg |
|---|---|---|---|---|
| 0.30 | 0.18 [0.14, 0.22] | 0.15 [0.08, 0.21] | 0.15 [0.08, 0.21] | 0.18 [0.14, 0.22] |
| 0.20 | 0.15 [0.11, 0.19] | 0.08 [0.02, 0.12] | 0.08 [0.02, 0.12] | 0.15 [0.11, 0.19] |
| 0.10 | 0.09 [0.05, 0.15] | 0.05 [0.00, 0.12] | 0.05 [0.00, 0.12] | 0.09 [0.05, 0.15] |

Every clean cross-site cell is ≤ α at α ∈ {0.2, 0.3}; at α = 0.10 the CI upper edge grazes
above 0.10. The conclusion **survives a stricter ≥0.10-overlap TP rule** (openms→mslesseg
FDR 0.153, mslesseg→openms 0.074 at α=0.20), i.e. it is not an artifact of the lenient
any-voxel matching.

**Why it transports — exchangeability, correctly measured (updated by the advanced pass).**
A candidate-level KS test flags the two sites' FP-score laws as "non-exchangeable" (D=0.15,
p≈5e-4), but that test is invalid (intra-scan clustering, n in the thousands). The rigorous
replacement — a **scan-clustered permutation test under a TRUE one-to-one Hungarian matching**
(see the advanced-pass section) — gives **D=0.048, p=0.71: the FP-score laws are NOT
distinguishable at the scan level.** So conformal transports because the exchangeability
assumption approximately *holds* here, not in spite of it; the apparent non-exchangeability was
largely a labeling artifact of many-to-one any-voxel matching (which mislabels over-segmentation
fragments as TP). This is a cleaner and more honest mechanism than the earlier "robust despite
non-exchangeability" wording, which is retracted.

**Baseline (why conformal, not a threshold):** a naive precision-matched global threshold
calibrated on one site does **not** transport — calibrated on openms it is stuck at FDR ≈ 0.30
on mslesseg for every target α (it cannot tighten), and calibrated on mslesseg it collapses to
power 0.03 on openms at α=0.10. Conformal adapts where the fixed threshold cannot.

## Finding 2 — the guarantee is MARGINAL, not per-scan (honest caveat)

BH bounds the **per-scan** false-discovery proportion in expectation; we report the pooled
micro-FDR above, but the per-scan FDP is far more variable. At α = 0.10, **≈ 44 % of individual
scans exceed α** even in cells whose micro-FDR is ≤ 0.10 (`frac_scans_exceed_alpha` in the
record). A clinician reading one scan does not get the marginal guarantee. This is a property
of marginal FDR control, not a bug — but it must be stated.

## Finding 3 — SPECIFICITY degrades under population/prevalence shift (real, on controls)

On healthy controls (zero prevalence) realized FDR is 1.0 by construction, so we report false
detections per 100 **acquired** control scans (denominator = all 30, including zero-candidate
scans), against the exchangeable **own-null floor**:

| α | own-null floor (sibbms→sibbms) | openms-null | pooled-null |
|---|---:|---:|---:|
| 0.30 | 26.7 | 203.3 | 186.7 |
| 0.20 | 20.0 | 173.3 | 140.0 |
| 0.10 | 10.0 | 120.0 | 90.0 |

A patient-derived null manufactures **7–13× more false detections** on healthy brains than the
controls' own null — i.e. ~1–2 false "lesions" per control scan. The floor is non-zero because
a valid conformal null still fires at ~its nominal rate; the **ratio to the floor** is the real
population-shift signal (not the FDR = 1.0 tautology). This replaces the earlier *synthetic*
confident-FP inflation with real control data.

## Finding 4 — POWER (not FDR) collapses under a segmenter change (confounded probe)

Applying a FLAMeS null to LST-AI-segmented ISBI selects **nothing** (zero power, FDR-safe): the
LST-AI score scale is lower, so no candidate clears the FLAMeS null. **ISBI is triple-confounded**
(different segmenter *and* acquisition *and* population) and its ISBI-2015 patient identity is
not recoverable from the flat `case0NN` naming, so it is used **test-only** and is **excluded**
from the few-shot section (few-shot on its cases would leak within-patient across timepoints).
Do not read ISBI as "algorithm shift" in isolation; isolating that needs a same-image
paired-segmenter design we do not have.

## Finding 5 — the few-shot Mondrian remedy works but at LOW RECALL

Site-conditional recalibration with k labelled subjects of the new site (FLAMeS patient sites
only) keeps FDR controlled but at **recall 0.03–0.33** across α (mean over 50 resamples):

| site | k=20, α=0.30 | k=20, α=0.20 | k=20, α=0.10 |
|------|---|---|---|
| openms   | 0.115 / **0.161** | 0.107 / 0.080 | 0.084 / 0.029 |
| mslesseg | 0.157 / **0.280** | 0.122 / 0.155 | 0.098 / 0.054 |

(fdr / power). Control is achieved **partly by abstention**; at a clinically plausible α = 0.10
the method recovers ~3–5 % of true lesions. This is a low-recall regime at the current score
AUC (~0.75–0.82), **not yet a deployable operating point** — an honest limit, not a selling
point.

## What we do NOT claim (retracted after adversarial review)

- ❌ "Conformal lesion-FDR breaks across MS site shift." The clean same-segmenter patient axis
  **holds**; the two failures are (a) a zero-prevalence cohort where FDR = 1.0 is forced by base
  rate, reframed as a specificity-transfer result, and (b) a confounded segmenter change that is
  a **power** collapse, the FDR-safe direction.
- ❌ "All site pairs are non-exchangeable (KS p < 0.05) → the guarantee fails." KS significance
  at this n with intra-scan clustering is uninformative and **non-predictive**: the pair it flags
  (openms|mslesseg, D=0.15) is exactly the pair where FDR is controlled. We report effect size D
  and gate "meaningful" at D > 0.2.
- ❌ "Mondrian recalibration restores control even under the LST-AI algorithm shift." That block
  was leaking and is removed.

## Advanced pass — reviewer-completeness (one-to-one matching, WCS baseline, per-scan FDX, clustered exchangeability)

Script: [`scripts/calm-ms/multisite_conformal_advanced.py`](../../scripts/calm-ms/multisite_conformal_advanced.py) →
[`multisite_conformal_advanced_record.json`](../../backend/app/services/assets/multisite_conformal_advanced_record.json).
Reviewed by 2 further adversarial agents (WCS/permutation statistics; matching/recall integrity);
their findings were fixed and re-run. All on the clean FLAMeS patient axis (openms, mslesseg).

- **True ONE-TO-ONE matching (Hungarian).** An earlier greedy version was many-to-one, mislabeling
  over-segmentation fragments as TP and deflating FDR. Fixed: each GT lesion is claimed once,
  surplus fragments are FP. This roughly doubled the FP set (openms 228→461 false candidates) and
  slightly raised realized FDR (openms→mslesseg conformal α=0.3: 0.175→**0.182**, still ≤ α).
- **Exchangeability, corrected.** Under the honest one-to-one FP labeling the scan-clustered
  permutation test gives **D=0.048, p=0.71** — the two sites' FP-score laws are NOT distinguishable
  (supersedes the invalid candidate-level KS and the earlier D=0.15). Conformal transports because
  exchangeability approximately holds.
- **Three honest recalls** (lesion-level, denominators consistent with the match): *selection*
  (GT a candidate is matched to), *end-to-end* (all GT ≥3 mm³), *clinical* (GT ≥14.14 mm³ = 3 mm
  diameter). Conformal openms→mslesseg at α=0.3: selection 0.30 / e2e 0.23 / clinical 0.25. Recall
  stays **low** (0.01–0.30) across all cells — the honest cost of FDR control at this score AUC.
- **Per-scan FDP, corrected denominator (over ALL scans).** An earlier version counted only
  selecting scans, inflating the exceedance rate. Corrected: **conformal exceeds α on only 3–17 %
  of scans**; the naive threshold on 30–84 %. So conformal's per-scan behavior is far better than
  the earlier (buggy) 44–95 % suggested — a correction in the method's favor.
- **WCS baseline (1.1), run not asserted.** Weighted conformal (marginal covariate-shift
  approximation, domain-classifier density ratio on grid-invariant features) is **unstable and
  does not reliably beat base BH**: it under-shoots in some cells and **over-shoots the level at
  tight α** (openms→mslesseg α=0.1: FDR 0.174 > 0.10, per-scan FDP p90 0.93). Its extra recall,
  where present, is partly bought by exceeding the FDR target. It carries no finite-sample
  guarantee here (weighted p-values are not identically distributed; the PRDS argument for BH is
  not re-established) and is fit transductively on the test features (optimistic). Honest verdict:
  **WCS is not a fix for this problem.**
- **Naive precision-matched threshold baseline.** Does not transport — calibrated on openms it
  selects everything on mslesseg (FDR 0.35, blows α), calibrated on mslesseg it collapses recall
  or (at strict IoU, α=0.1) selects nothing. Conformal is the better-behaved procedure.

## Positioning vs the conformal-lesion literature (1.6)

The wrapper is a faithful application of **Jin & Candès (2023, conformal selection)** + BH, and the
few-shot recalibration is **Vovk Mondrian / Tibshirani et al. (2019) covariate-shift conformal** —
neither is novel here. Adjacent published work: **npj Digital Medicine (2025)** applies conformal
prediction for patient-level MS diagnosis (different granularity — patient, not lesion); **arXiv
2510.17897** does conformal FNR/recall control for 3D lesion segmentation (controls the miss rate,
the complementary error to our FDR/precision dial). Conformal FDR for *detection candidates* is
established in the tumour/nodule imaging literature. **Our contribution is therefore not the method
but the honest multi-site characterization on MS**: that the lesion-FDR guarantee transports across
same-segmenter acquisition/population shift, is marginal (not per-scan), degrades under population
(specificity) and segmenter (power) shift, that the few-shot Mondrian fix runs at low recall, and
that neither WCS nor a naive threshold does better — all on reproducible public data with an
auditable Class-C implementation.

## Honest bottom line

Distribution-free conformal lesion-FDR **transports** across real same-segmenter acquisition/
population shift (its FP-score law is scan-level exchangeable there, and it controls FDR ≤ α while
a naive threshold and WCS do not), but the guarantee is **marginal** (per-scan FDP exceeds α on
3–17 % of scans), it comes at **low recall** (≤0.30 lesion-level), and it degrades where it matters
clinically: **specificity under population shift** (controls) and **power under segmenter change**
(LST-AI). This honest characterization — five adversarial-review iterations, reproducible on public
data, on an auditable Class-C substrate — is the contribution: a **MELBA / MICCAI-workshop scoped
result, not a novel method**. Genuinely still-missing (reviewer-demanded, needs more data): **>2
real acquisition-shift sites** (needs a self-trained single segmenter over pooled public data — the
nnU-Net GPU step) and a principled **per-scan FDX guarantee** (Katsevich–Ramdas) rather than the
empirical characterization here.
