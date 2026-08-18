# CALM-MS — cross-site lesion selection: the shift, and a few-shot site-conditional candidate (preliminary)

*Preliminary, 2-site, empirical study — 2026-08-18. Feature remains DARK.*
Artifacts: `scripts/calm-ms/cross_site_selection_study.py`,
`backend/app/services/assets/cross_site_selection_record.json`.
Supersedes a flawed `wcs_experiment.py` (removed) whose headline result was a calibration
double-use leak (two adversarial audits).

> **⚠ VALIDITY CAVEAT — base-model contamination + confound (adversarial data audit, 2026-08-18).**
> One of the two "sites", `open_ms_data` (Ljubljana), is in the **training set of the FLAMeS base
> model** (FLAMeS paper refs 12–14 = ISBI-2015, Ljubljana, MSSEG-2016). Its probability maps are
> therefore **in-sample**, its false-candidate null is not exchangeable with held-out data, and its
> "clean" within-site ECE (0.02–0.03) is optimistic — an in-sample artefact, not evidence of good
> calibration. Moreover openms↔mslesseg differ on ≥5 axes at once (scanner, annotation protocol
> [3-rater consensus vs single-rater + 3 mm floor], base-rate 3.3×, in/out-of-sample, cohort), so
> the measured "cross-site shift" is **confounded** and is mostly a label-protocol/base-rate shift
> (the isotonic→ECE≈0 fingerprint), NOT scanner physics. **This study is therefore a MOTIVATING
> ILLUSTRATION only, not a scanner-shift validation.** A valid measurement must use a
> FLAMeS-independent base model and measure the shift *within* an annotation-uniform multi-scanner
> dataset (MSSEG-2). See `docs/calm-ms/DATA-STRATEGY.md`.

## Why this study

The consolidation named Weighted Conformalized Selection (WCS; Jin & Candès, arXiv
2307.09291) as the candidate remedy for the cross-site shift that breaks the lesion-FDR
guarantee. Two adversarial audits then established: (1) an earlier WCS prototype used the
calibration site's candidates **both** to fit the learned scorer **and** as the conformal
null — a double-use leak that manufactured its power; (2) plain BH on marginal weighted
conformal p-values is not WCS and carries no FDR guarantee; (3) the shift is plausibly
**posterior drift** (P(true|x) changes across scanners), which no covariate-reweighting
method can fix. This study re-runs the question leak-free and tests those claims.

Leak fix: the learned scorer is **cross-fit** on the calibration site (5-fold out-of-fold),
so the conformal null uses OOF scores; the test site is scored out-of-sample. No test labels
enter any selection procedure (evaluation only). Intervals are over 30 resamples.

## Q1 — the shift is a rank-preserving calibration-map shift (more than covariate, not risk-reordering)

For the *same* learned score, the false-candidate rate differs across sites — and it persists
inside the covariate-overlap region (domain-classifier prob ∈ [0.35, 0.65], X roughly matched),
so it is not purely covariate shift:

| learned-score bin | openms false-rate | mslesseg false-rate |
|---|---|---|
| 0.0–0.2 | 0.07 | 0.36 |
| 0.2–0.4 | 0.24 | 0.68 |

Cross-site calibration error of P(true|x) is **0.22–0.29** vs **0.02–0.03** within-site. But the
honest decomposition (adversarially verified) is important: **~half** of that ECE is a **label
(base-rate) shift** (false-rate 0.09 vs 0.30, 3.3×) that a BBSE-style correction removes
(0.217 → 0.118); and **isotonic recalibration of the same score drives ECE to ≈0.000** — i.e.
the score's *ranking* of P(false|x) is preserved across sites and only the score→probability map
shifts. So the shift **violates WCS's P(Y|X)-invariance assumption** (a covariate-reweighting
method alone cannot fully repair it), but it is a monotone calibration-map + label shift, **not**
the risk-reordering "posterior drift" strongly connotes — which is exactly why a few labelled
cases can recalibrate it.

## Q2 — leak-free weighted conformal does not add power

With the leak removed and honest weights (marginal density ratio, ESS 65–552), weighted
selection either collapses power (0.00 power, openms→mslesseg) or gives only a marginal change
(mslesseg→openms) — never a controlled-and-powerful improvement over the naive learned baseline.
**Disclosure (important):** the leak-free *naive* cross-site conformal selection **already held
empirical FDR ≤ α** at all α in both directions (openms→mslesseg 0.047/0.103/0.164;
mslesseg→openms 0.004/0.006/0.015) — a single-draw empirical result with **no exchangeability
guarantee**, not a broken one. So the motivation for a fix is *restoring the guarantee*, not
rescuing an empirically-broken FDR.

## Q3 — a promising candidate fix: few-shot site-conditional (Mondrian) selection

Give the deployment site a small **labelled slice**: use those cases' false-candidate learned
scores as the site's own conformal null (Mondrian/site-conditional), and select on the disjoint
remaining cases. This is the one arrangement whose FDR control rests on a **valid exchangeability
argument** rather than luck. FDR (mean ± sd over 30 label-slice resamples) / power, with the
fraction of resamples exceeding α = **0.00** in every cell except one (k=2, α=0.10: 1/30):

| labelled cases (k) | FDR @α=0.20 | power @α=0.20 | FDR @α=0.30 | power @α=0.30 |
|---|---|---|---|---|
| k=2  | 0.01–0.04 | 0.23–0.30 | 0.03–0.07 | 0.35–0.47 |
| k=5  | 0.02–0.05 | 0.30–0.41 | 0.03–0.08 | 0.46–0.58 |
| k=10 | 0.02–0.06 | 0.37–0.47 | 0.03–0.09 | 0.51–0.59 |
| k=20 | 0.01–0.06 | 0.39–0.44 | 0.03–0.09 | 0.51–0.59 |

**FDR is controlled from k=2**; the ≈5–10 range is a **power** threshold (power plateaus by k≈10),
not an FDR-control one. This is a *promising candidate* fix — not "the deployable fix": it is a
2-site empirical result with no finite-sample bound, and (Q2) a no-label baseline matched its FDR
control here. Its distinctive claim is the **guarantee** (site-conditional exchangeability), which
the label-free methods lack.

## Honest limitations (do not over-read)

- **Two sites only.** Both directions agree, but this is not multi-site validation; the k-shot
  requirement and the power levels will change with more heterogeneous scanners.
- **Empirical, not a finite-sample proof.** The k-shot FDR is a mean over 30 label-slice
  resamples, not a theorem; split-conformal FDR control *should* hold per-slice (Mondrian), but
  the scan-clustered null and small k warrant a proper training-conditional bound.
- **Modest power.** Even site-conditional recovers only ~0.3–0.5 of true lesions at α=0.2–0.3 —
  a consequence of genuine TP/FP score overlap, not calibration.
- **Set-level, not per-case, control.** The FDR is over the site's *pooled* candidate set; at
  k=10/α=0.20 roughly 6–12% of individual scans still have a case-level FDP > α (a few reach 1.0).
  Marginal FDR is a set quantity — a clinician reading one scan is not individually guaranteed.
- **Tiny test site.** openms has only 30 cases, so "k=10 per site" is a third of it; the
  "per new site" generalisation rests on 2 sites, one small.
- Not wired into the product; clinical enablement still needs multi-site data, the IEC 62366-1
  study, and per-preset validation.

## Roadmap update

The F1 fix is now specified more precisely: **not** weighted-covariate conformal (its
P(Y|X)-invariance assumption is violated), but **few-shot site-conditional (Mondrian)
calibration with the learned score** — a small labelled slice per deployment site — as the
*candidate* with a valid exchangeability argument. Next: validate on ≥3–5 real scanners
(where a label-free baseline may finally break, motivating the guarantee empirically too), add a
training-conditional (Mondrian) FDR bound, and study active/optimal selection of the labelled
slice (which k cases to label).
