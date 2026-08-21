# CALM-MS — V&V Enablement Dossier

**Requirement:** REQ-FUNC-CALM-001 · **Flag:** `CALM_MS_RESEARCH_ENABLED` (default `False` — dark) · **Class:** C

This dossier is the **enablement contract** for the CALM-MS conformal second reader.
`CALM_MS_RESEARCH_ENABLED` may flip to `true` **only when every gate in
`vv_gate_status.json` is `pass`**. A CI test
(`backend/tests/unit/test_calm_ms_enablement_gate.py`) enforces this: enabling the
flag while any gate is not `pass` turns the build **red**. This makes "dark for
cause" self-enforcing rather than a convention — closing the one real
premature-enable path (a one-line env flip) that the 2026-08-21 adversarial review
flagged as unguarded.

## What the feature is (and is not)

An **additive** second-reader overlay on a FLAMeS lesion probability map. It never
alters, filters, or deletes the base mask. It runs the candidates through a
**conformal selection + Benjamini-Hochberg** procedure and paints an **ordinal
review-priority tier** (high/medium/low). It exposes the preset's **target alpha**
as a *population-level* scope. It never exposes a per-lesion probability or a
per-scan realized FDR — those would be false precision (RC-CALM-2 / RC-CALM-3).

## The guarantee, stated exactly

> Under label-conditional exchangeability of *false* candidates with the frozen
> MSLesSeg null, BH-on-conformal-p-values controls the **marginal, population-level
> lesion-instance FDR at ≤ α**, averaged over the exchangeable draw of
> (calibration ∪ test).

It is **not** per-scan (per-scan FDP disperses — ~25% of scans exceed α at α=0.30),
**not** per-lesion (a conformal p-value is not P(real)), and **conditional on an
exchangeability premise that cannot be certified at inference** (the OOD monitor
sees only the mixed *marginal*, not the label-conditional false-candidate law).

## Prior-art positioning (Gate 3)

| Work | Controls | Relation to CALM-MS |
|---|---|---|
| Angelopoulos & Bates, Conformal Risk Control (2208.02814) | E[monotone bounded loss] via one threshold λ | Root framework; CLS's engine. Not the theorem CALM-MS uses. |
| CLS, Conformal Lesion Segmentation (2510.17897, 2025) | test-time **FNR / recall** (under-segmentation) | **Closest prior art; orthogonal axis.** CALM-MS controls the opposite failure. |
| Jin & Candès, conformal selection / WCS (2307.09291) | selective inference **FDR** via conformal p-values | CALM-MS's actual engine (unweighted selection). WCS's covariate-shift remedy does **not** repair the MS *label*-shift. |

**Honest novelty verdict:** the wrapper is not novel (conformal lesion-FDR already
exists for tumour/nodule). The defensible contribution is the **cautionary
characterization of the MS acquisition-driven label-shift failure** + a transparent
within-domain scorer. Publishable as an applied negative/scoping result, not as a
deployed guarantee.

## Gate status (see `vv_gate_status.json` for the machine-readable source of truth)

| Gate | Status | One-line |
|---|---|---|
| 1 · Calibration validity | **pass** | Conformal-p + BH marginal-FDR valid by theorem; fail-closed matrix enforced + tested. |
| 2 · Coverage on held-out | **fail** | Cite the **served** raw-prob coverage (not the unwired learned scorer); cross-site is UNTESTED on clean data + fails under a synthetic confident-FP shift. |
| 3 · Prior-art differentiation | **pass** | Precision/FDR vs CLS's FNR; honest not-novel-wrapper framing. |
| 4 · Usability (IEC 62366-1) | **blocked** | Summative study (HAZ-CALM-2/3/8) does not exist. |
| 5 · Change control (PCCP) | **blocked** | Per-preset clinical validation + authorized PCCP do not exist. |
| 6 · Base-model-bound producer | **blocked** | REQ-FUNC-CALM-007: a non-FLAMeS map on the right grid is not caught today. |
| 7 · Multi-site external validation | **blocked** | Needs new acquisition (≥3–5 real scanners); not meetable on public data. |

**Overall: NOT_READY — enable not permitted. The endpoint stays dark.**

## Honesty corrections applied 2026-08-21 (adversarial pass)

Independently verified against ground truth, then fixed (calibration data unchanged
— only provenance/labels corrected; null & OOD arrays byte-identical):

1. **Null provenance no longer claims "single-site Catania 1.5T."** MSLesSeg
   (ICPR-2024) is a **multi-center** cohort — its 115 series were acquired at
   different hospitals (Nature Sci Data 2025, s41597-025-05250-y), curated/annotated
   by Unict/IPLab. Provenance now reads `acquisition_scope` = a single curated
   multi-center dataset, not validated on external scanners.
2. **OOD threshold justification corrected.** The comment cited "145 legit cases /
   ≥95% / ~100% +6SD detection"; the shipped record is **115 cases**, false-OOD
   **2.6%** and +6SD detection **~92%** at threshold 5.0. Threshold 5.0 is still the
   correct pick on the 115-case record; only the justifying numbers were stale.
3. **`lesion_scorer_record.json` relabelled.** The learned scorer was marked
   "SHIPPED"; it is **built but wired into no runtime service** (the served path uses
   raw pooled probability). It is also trained on `openms` (FLAMeS-in-sample) — a
   contamination warning was added. Its numbers must not be cited as the endpoint's
   coverage.
4. **Contamination gate hardened (fail-closed).** `load_null_asset` now refuses any
   null not stamped `base_model_independent=true`, making a contaminated rebuild
   structurally un-shippable rather than trusted by convention.

## What must be TRUE before dark → live

Gates 4–7 are **not code** — they are a usability study, a clinical-validation +
PCCP program, a base-model-bound producer, and new multi-site acquisition. Until
they exist and Gate 2 is re-based on the served statistic with measured cross-site
coverage ≤ α, the correct state is **dark**.
