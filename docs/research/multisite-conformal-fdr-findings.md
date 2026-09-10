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
above 0.10. **This holds despite the FP-score law being non-exchangeable by KS** between the
two sites (D = 0.15) — so the BH-on-conformal-p-value guarantee is more robust than its
strict exchangeability assumption. The conclusion **survives a stricter ≥0.10-overlap TP rule**
(openms→mslesseg FDR 0.153, mslesseg→openms 0.074 at α=0.20), i.e. it is not an artifact of the
lenient any-voxel matching.

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

## Honest bottom line

Distribution-free conformal lesion-FDR is **more robust than its assumption** (it transports
across real same-segmenter acquisition/population shift and beats a naive threshold), but its
guarantee is **marginal** (per-scan FDP varies widely), and it degrades exactly where it matters
clinically: **specificity under population shift** and **power under segmenter change** — with the
few-shot fix running at **low recall**. That honest characterization, on reproducible public
data with an auditable Class-C implementation, is the contribution — a MELBA / MICCAI-workshop
scoped result, **not** a novel-method claim. The still-missing pieces a reviewer will demand:
more than two real acquisition-shift sites, a run of weighted/label-conditional conformal (WCS)
as a second baseline, and per-scan FDX control — all logged as future work.
