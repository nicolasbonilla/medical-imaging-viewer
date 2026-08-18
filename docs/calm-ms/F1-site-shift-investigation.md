# CALM-MS — F1 (site/label-shift) investigation and the true scope of the fix

**Status:** research finding, 2026-08-18. Feature remains DARK (investigational).
**Artifacts:** `scripts/calm-ms/site_recalibration_experiment.py`,
`backend/app/services/assets/site_recalibration_record.json`.

## Background

Adversarial round 2 (2026-08-17) proved that the conformal lesion-FDR guarantee can
be silently voided by a case whose **false-candidate** score distribution is not
exchangeable with the frozen calibration null — a *label-conditional* shift the
score-only OOD monitor cannot detect (`conformal_ood`). The proposed real fix was
**site-conditional (Mondrian) recalibration**: judge each case against the null of its
own site, re-estimated from a small labelled slice per site (Vovk Mondrian conformal;
Tibshirani et al. 2019 covariate-shift conformal). This document tests that fix on real
data and reports what it does — and does not — achieve.

## Experiment

Two FLAMeS cohorts are treated as two sites with (potentially) different false-positive
score regimes: **openms** (open_ms_data, 3-rater consensus, 30 cases) and **mslesseg**
(MSLesSeg, multi-site, 115 cases). Candidates are extracted with the shipped pipeline;
TP/FP labels come from ground truth (experiment time only). Realized micro-FDR is
measured under each (null-source × test-site) combination; the site-conditional diagonal
uses leave-one-case-out. A third, **severe-shift** site models the clinically-likely
failure — a scanner emitting *confident* false positives — by pushing only the FP scores
of the mslesseg cases up in logit space (Δ=1.5), leaving true candidates untouched so the
mixed marginal barely moves.

## Result 1 — real cross-site FP shift exists, but is mild between these cohorts

The FP-score distributions differ significantly (two-sample KS **D=0.150, p=4.7×10⁻⁴**),
so exchangeability is formally broken cross-site. Yet realized FDR stays close to target
in every (null × site) cell — e.g. at α=0.30 all cells fall in 0.12–0.18; the only
breach is a mild one at α=0.10 with the openms null on openms (0.111 vs 0.10). **The
pooled ("one-size-fits-all") null is adequate when the sites are similar**, which these
two academic cohorts are.

## Result 2 — a severe confident-FP shift breaks the guarantee AND evades the monitor

Modelling a scanner that inflates FP confidence (shifted-FP mean 0.969 vs 0.880):

| α | Pooled-null FDR | selected (TP / FP) | OOD monitor |
|---|---|---|---|
| 0.30 | **0.433** (breaks) | 2158 (1224 / 934) | **0 / 115 flagged (blind)** |
| 0.20 | **0.509** (breaks) | 1529 (751 / 778) | blind |
| 0.10 | **0.626** (breaks) | 788 (295 / 493) | blind |

F1 is confirmed with a realistic construction: the pooled guarantee is voided (realized
FDR up to ~6× target) and the score-only OOD monitor flags none of it.

## Result 3 — site-conditional recalibration is NECESSARY BUT NOT SUFFICIENT

Re-estimating the null from the shifted site's own FP scores (leave-one-case-out):

| α | Site-conditional FDR | selected (TP / FP) |
|---|---|---|
| 0.30 | 0.950 | **20 (1 / 19)** |
| 0.20 | 0.923 | 13 (1 / 12) |
| 0.10 | 0.833 | 6 (1 / 5) |

Power **collapses**: of 2692 true lesions, the site-conditional selection recovers **1**.
The site-conditional null correctly recognises the inflated FPs as typical for this site
and therefore selects almost nothing; the handful it does select sit in the FP tail.

**Interpretation.** When false positives are *as confident as, or more confident than*,
true lesions, the raw-probability score is anti-informative — it no longer separates TP
from FP. No conformal calibration can recover a guarantee that is simultaneously **valid**
and **useful**: the pooled null buys power at the cost of a broken guarantee; the
site-conditional null keeps the guarantee honest but at near-zero power. Recalibrating
the *null* fixes the reference distribution, not the *score's* discriminative content.

## The true scope of the F1 fix

F1 is a two-part problem, and only solving both parts restores a useful guarantee:

1. **A scanner-robust, learned lesion score** that separates TP from FP by features
   beyond raw probability (morphology, spatial context, multi-channel evidence) which
   remain discriminative under acquisition shift. This is the "learned calibrated scorer"
   the CALM-MS design explicitly deferred to v2; Result 3 shows it is not optional — it
   is the load-bearing component.
2. **Site-conditional / cluster-aware calibration** (this experiment's mechanism), so the
   null matches the deployment site. Necessary to keep the guarantee valid, but inert
   without (1). Note the calibration must also respect scan-clustering (see round-2 F2/F3):
   pooling FP scores across a site's scans is not per-case exchangeable, which inflates the
   tail behaviour seen above.

## Consequence for the product / roadmap

- The conformal wrapper is only as good as the underlying score's TP/FP separability;
  scanner robustness of that score is the real research problem, not the conformal layer.
- Clinical enablement remains blocked. The gate is now precisely scoped: a scanner-robust
  learned score **and** site-conditional, cluster-aware calibration, validated on real
  mimic/scanner-shift cohorts — not merely a better OOD monitor or a recalibrated null.
- This is a publishable negative/scoping result: it delimits what distribution-free
  guarantees can and cannot deliver for lesion detection under acquisition shift.
