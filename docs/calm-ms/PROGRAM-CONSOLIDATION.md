# CALM-MS — program consolidation and honest state of the science (2026-08-18)

*Conformal, distribution-free control of the lesion-instance false-discovery rate for MS
lesion segmentation.* This document consolidates what the program has established, what it
has NOT, and where it sits relative to the academic and industrial state of the art. It is
written after four adversarial verification rounds; every internal quantitative claim below
traces to a committed record (external SOTA claims cite public sources). The feature is and
remains **DARK** (`CALM_MS_RESEARCH_ENABLED=False`).

## 1. Thesis

Standard MS-lesion segmenters are tuned to voxel overlap (Dice) and give no per-decision
error control. The legacy in-product AI over-segments (≈0.5 Dice, ≈0.2 lesion precision on
the legacy benchmark; the committed FLAMeS baselines give lesion sensitivity 0.83 on MSLesSeg
and 0.59 on open_ms_data). CALM-MS wraps *any* probabilistic segmenter with **conformal
selection** (Jin & Candès 2023; Bates et al. 2023) so the set of reported lesions carries a
**distribution-free guarantee on the lesion-instance FDR** — a precision dial the clinician
sets via a validated preset α. This is the right unit (a radiologist reasons about lesions,
not voxels) and the right guarantee class (finite-sample, model-agnostic). Conformal FDR
control for lesion *instance* detection is itself not new (brain-tumour: arXiv 2504.04482,
ICIPCA 2025; pulmonary nodules: arXiv 2412.20167) — the program's actual contribution is the
**failure analysis** in §3, not the wrapper (see §6).

## 2. What was built (all DARK, investigational)

- **Lesion-FDR core** (`conformal_lesion_fdr`): conformal p-values `p=(1+#{null≥s})/(n+1)`
  + Benjamini–Hochberg selection. Verified: BH step-up matches reference (0/20000), the
  shared-calibration p-values are PRDS so BH controls marginal FDR, empirical E[FDP] ≤ α in
  every in-distribution regime.
- **Frozen null asset** (`conformal_null_asset`, FLAMeS-derived, 145 labelled cases): loads
  once, fails closed on missing/degenerate/wrong-base-model/provenance-mismatch.
- **OOD monitor** (`conformal_ood`): a gross-marginal-shift disclosure backstop.
- **Learned lesion scorer** (`calm_ms_scorer` + `calm_ms_lesion_features`): a transparent
  degree-2 polynomial logistic regression on scanner-robust features (no pickle, pure-NumPy
  forward pass, fail-closed).
- **Endpoints + UI** (`/conformal/select`, `/conformal/status-mask`, `ConformalPanel`):
  additive-only, ordinal tiers, no per-lesion probability, presets only, gated behind the
  research flag + PHI authz.

## 3. What the adversarial program ESTABLISHED (the honest findings)

Four rounds (design, backend, frontend, and two deep statistical/theoretical/evasion
rounds) produced a consistent, verified picture:

1. **The lesion-FDR core is sound — conditionally.** It controls the marginal FDR **when its
   exchangeability premise holds** (test-case false-candidate scores exchangeable with the
   null).

2. **The premise cannot be certified at inference by any score-only monitor.** The FDR guarantee
   depends on the *label-conditional* false-candidate distribution `P(score | false)`; every
   inference-time observable is a function of the *mixed* marginal `P(score)`. This is a
   **label-shift**, not a covariate-shift (Podkopaev & Ramdas 2021). Confirmed twice
   independently: a case whose summary sits *inside* the calibration envelope can realise
   FDP ≈ 1.0. The OOD monitor is therefore a **marginal-shift backstop only — insufficient
   for, and blind to, the label-conditional axis the guarantee actually depends on** (it lives
   on a different axis; the FDR guarantee does not depend on it).

3. **A better null (site-conditional recalibration) is necessary, not sufficient.** On real
   data a severe confident-FP scanner shift voids the pooled guarantee (realized FDR 0.43–0.63)
   and evades the monitor (0/115 flagged); site-conditional recalibration restores a
   *theoretically* valid (leave-one-case-out) null, but at the measured operating points the
   tiny, clustered selection (20 / 13 / 6 lesions) still yields realized FDR **0.83–0.95** and
   power collapses (1 of 2692 lesions) when false positives are as confident as true ones — the
   raw score is then anti-informative, so neither validity nor power is actually achieved.

4. **A better score (the learned scorer) is necessary, not sufficient.** It is a genuine
   within-domain improvement (patient-grouped AUC 0.796 vs 0.701 raw; ECE 0.032; no overfit;
   location/morphology are legitimate signal), but it does **not** solve cross-site
   non-exchangeability (pooled leave-one-site-out AUC 0.624) and under a *fair* monotone shift
   does not beat raw probability. *(An earlier claim that it did was retracted: the test that
   "proved" it was rigged — it inflated only the false candidates.)*

5. **Second-order honesty corrections.** The frozen null's effective resolution is
   ~1/n_clusters (145 scans), not 1/1391; within-scan dependence keeps the *marginal* FDR valid
   (PRDS holds; the Benjamini–Yekutieli worry was refuted) but disperses the *per-scan* FDP
   (≈25% of scans exceed α at α=0.30), so the guarantee is population-level, not per-scan — the
   FDR-vs-FDP distinction, which has its own remedy (FDP-exceedance / FDX control; Katsevich &
   Ramdas; conformal-FDP bounds).

**Net:** the guarantee is real and the components are individually sound, but **no single
component restores validity under acquisition shift.** This is the program's central, honestly
earned result.

## 4. Position vs the state of the art

**Academia — segmentation.** SOTA MS segmenters are nnU-Net-based — FLAMeS (the base here) beats
SAMSEG/LST-LPA/LST-AI (mean Dice ~0.74). *MSSEG-2 is a challenge/dataset and Anima an evaluation
toolkit, not segmenters.* The frontier has moved past plain nnU-Net, especially for the
new-lesion / longitudinal setting the thesis cares about: deformation-field vision-GNNs
(DEFUSE-MS, MICCAI 2025), calibrated inter-patch blending (MICCAI 2025), and temporal-difference
longitudinal methods. Detection-focused segmenters already do *heuristic* lesion-wise
FP-reduction (triplanar voting; LST-family cascades). CALM-MS is orthogonal: it adds not FP
reduction but a **distribution-free finite-sample guarantee** on the lesion-FDR — which none of
the above provide.

**Academia — conformal / selective inference.** The core is a faithful application of conformal
p-values (Vovk; Bates et al. 2023) + conformal selection (Jin & Candès 2023) + BH, in the
"risk-control" family the program's name invokes (RCPS, Bates et al. 2021; Conformal Risk
Control, Angelopoulos et al. 2024; Learn-then-Test). The open problem the program surfaced —
exchangeability failure of the *false-candidate* law under acquisition shift — is squarely on
the frontier: covariate-shift conformal (Tibshirani et al. 2019), **weighted conformalized
selection for FDR under shift (Jin & Candès, arXiv 2307.09291 — the tool the §5 roadmap
actually needs)**, non-exchangeable conformal (Barber et al. 2023), training-conditional
coverage (Bian & Barber 2023), Mondrian/class-conditional conformal (Vovk). Label-shift is the
*diagnosis* (Podkopaev & Ramdas 2021, conceptual); weighted conformal selection is the candidate
*remedy*.

**Industry.** Cleared/CE MS-reporting products — icometrix *icobrain* (FDA 510(k) + CE), CorTechs
*NeuroQuant* (510(k) + CE), Siemens *AI-Rad Companion Brain MR* and mediaire *mdbrain* (the last
two already do McDonald/MAGNIMS regional lesion reporting) — report lesion counts/volumes with
validation studies but, as far as public labelling shows, **no per-scan, per-lesion
distribution-free error guarantee**. (*LST-AI* and FLAMeS are research-only, not cleared — a
category the earlier draft got wrong.) A working CALM-MS would be a genuine differentiator; the
honest caveat is that these products earned clearance through large multi-scanner validation —
precisely the gap CALM-MS has not closed.

## 5. What clinical enablement actually requires (the honest roadmap)

The F1 fix is a program, not a patch — and it needs all of:

1. **≥3–5 real acquisition sites/scanners** with expert ground truth (currently 2 domains,
   145 cases; pooled cross-domain AUC 0.62). Non-negotiable — everything downstream needs it.
2. **Cross-site score harmonisation and/or a domain-invariant score**, to make the
   false-candidate law comparable. ComBat/neuroComBat (Johnson 2007; Fortin 2017) is the
   standard baseline but harmonises *scalar features estimated from a per-site batch* — it is
   not an inference-time single-case transform, so applying it to a per-lesion score is a
   partial fit; its descendants (ComBat-GAM, CovBat, DeepComBat 2023, DeepResBat 2024) and
   **domain-invariant representation learning / test-time adaptation** are the more apt frames
   for a single-case learned FP score.
3. **Domain-conditional (Mondrian) calibration** with a small labelled slice per deployment
   site, so the null matches the site; cluster-aware (scan-level) for within-scan dependence.
   A preliminary 2-site study (`docs/calm-ms/cross-site-selection-study.md`) supports this over
   *weighted-covariate* conformal (WCS): the cross-site shift violates WCS's P(Y|X)-invariance
   (cross-site calibration ECE 0.22–0.29 vs 0.02–0.03 within), leak-free weighted selection adds
   no power, and few-shot Mondrian selection controls FDR (violation-fraction ≈0 over 30
   resamples) from k=2 with power plateauing by k≈10 — though a leak-free *no-label* baseline also
   held FDR empirically there, so the Mondrian value is the exchangeability *guarantee*, pending
   ≥3–5-site validation and a training-conditional bound.
4. **A base-model-bound probability producer in production** (today: bring-your-own-prob file_id).
5. **IEC 62366-1 summative usability study** proving no per-scan / per-lesion mis-inference.
6. **Per-preset clinical validation + a PCCP** change-control plan.

Until (1)–(3) hold, the guarantee is not deliverable under real acquisition variation and the
feature stays dark.

## 6. The program's real contribution

Not (yet) a deployed guarantee. What it *is*, honestly:

- **A rigorously-scoped result**: conformal lesion-instance FDR control already exists for
  tumours/nodules (arXiv 2504.04482, 2412.20167) — CALM-MS's contribution is not the wrapper
  but the **characterisation of its acquisition-driven label-shift failure mode in MS**: the
  false-candidate law is not exchangeable across scanners, and neither a better-null-only nor a
  better-score-only fix suffices (the combined two-part fix is *hypothesised, not yet
  demonstrated*). A delimitation we believe is publishable, with reproducible evidence.
- **An evaluated within-domain component** (the transparent, calibrated learned scorer) that
  improves TP/FP separability and is a building block of the eventual fix (not device-validated;
  within-domain conformal power is only ~0.47 at α=0.20).
- **An adversarially-hardened, honest engineering substrate** (fail-closed loaders, provenance
  stamping, no labelling-hazard leaks, transparent no-pickle models) ready to carry the valid
  method once the data and calibration exist.

The discipline that produced this — build, adversarially verify, and **retract what does not
survive** — is the reason the record is trustworthy. That is the standard the rest of the
product should be held to.
