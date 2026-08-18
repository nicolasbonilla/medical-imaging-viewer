# CALM-MS — multi-site data strategy (honest, after 3 adversarial audits)

*2026-08-18. Synthesis of three adversarial audits — experimental-design/confound, SOTA data
landscape, statistical feasibility — against `data/registry.yaml`.* This document states what the
multi-site F1 fix actually requires, what the available data can and cannot support, and the
corrected roadmap. It is deliberately sobering: the honest conclusion is that the **certified
guarantee is not reachable with public data**, and that our existing 2-site result is confounded.

## 1. The validity problem in what we already have (must fix first)

**Base-model contamination (CRITICAL, confirmed).** FLAMeS — the base segmenter behind every
probability map and the frozen null — was trained on data that includes, per its own bibliography
(refs 12–14): **ISBI-2015, the Ljubljana 3D-MS-DB (= our `open_ms_data`), and MSSEG-2016.**
Consequences:
- `open_ms_data` probability maps are **in-sample** → its false-candidate scores are optimistically
  sharp → the conformal null built from it is **not exchangeable** with held-out cases. The frozen
  null asset (openms + mslesseg) is half-contaminated; the openms within-site ECE (0.02–0.03) is an
  in-sample artefact, not good calibration.
- `ISBI-2015` (our current validation cohort) and `MSSEG-2016` (the natural annotation-uniform
  scanner-isolation anchor) are **also FLAMeS training data** — forbidden for a FLAMeS-based null.
- **Shifts-MS** (the field benchmark, §3) aggregates ISBI + MSSEG-1 + Ljubljana → contaminated the
  same way for a FLAMeS base.

**Scanner-vs-annotation confound (CRITICAL, confirmed).** `open_ms_data` and `mslesseg` differ on
≥5 axes simultaneously (scanner, annotation protocol, 3 mm lesion floor, base-rate 3.3×,
in/out-of-sample, cohort). The cross-site shift we measured is **mostly a label-protocol + base-rate
+ in-sample shift**, not scanner physics — the isotonic→ECE≈0 decomposition is the fingerprint. So
the cross-site study is a **motivating illustration, not a scanner-shift validation** (now caveated
in that doc).

**Fix (actionable now):** (a) mark base-model overlap in the registry as a hard inclusion gate; (b)
**rebuild any "clean-calibration/held-out" conformal claim from FLAMeS-INDEPENDENT data only**
(clean pool with the current base model: `mslesseg`, `msseg2`, `ms3seg`, `msmri_dib`, `pedims`,
`sibbms`); (c) to ever use openms/ISBI/MSSEG-2016, swap to a base model with a documented
leave-those-out fold and publish the exclusion manifest.

## 2. The feasibility ceiling (why public data can't certify the guarantee)

The calibration unit is a **scan** (false candidates cluster within a scan), so the effective N is
scans, not lesions, and the smallest conformal p-value is `1/(n_scans+1)`.

| dataset | usable masks | scanners | **masks/scanner** | coarsest resolvable α |
|---|---|---|---|---|
| MSSEG-2016 | 15 | 4 | ~3.75 | **≈0.21** |
| MSSEG-2 | 40 | 15 | ~2.7 | **≈0.27** |

- **The multi-scanner "gold" sets cannot give a per-site null** — 3–4 scans/scanner can't emit a
  p-value below ~0.2, so per-site FDR control at α=0.10 is arithmetically impossible (F1).
- The **training-conditional (Mondrian) bound** needs **~150–600 scans/site**; k=10 gives a vacuous
  "FDR ≤ 0.49" certificate (F2). **Not deliverable on public data** — remove this promise from the
  roadmap until new data exists.
- **Power is AUC-capped** (~0.75–0.82) and N-independent: α=0.10 with usable recall needs AUC
  ~0.90–0.95. The feasible envelope is **α ≈ 0.2–0.3 at recall ~0.4–0.6** (F3). A better *score*
  (segmenter/features), not more calibration data, is the lever for tighter α.
- Only `mslesseg` + `open_ms` are single-site 3D-MNI (the status quo); every clean third site is
  2D-native (geometry-incompatible — resampling fabricates lesion signal) or contaminated (F4).
- Multiplicity: 0/30 resamples bounds true per-cell exceedance only at ≤10% (rule of three); across
  3 presets × N sites × T timepoints one cannot claim "controls FDR" simultaneously (F5).

**Conclusion (F6):** a certified ≥3-clean-site per-site Mondrian FDR guarantee **strictly requires
NEW data acquisition** — ~20–30 labelled scans/scanner at ≥3–5 scanners for a point estimate,
~150/scanner for a certificate. Public have+gated data cannot reach it.

## 3. Align with the field benchmark — but know its limits

**Shifts / Shifts 2.0 MS Lesion benchmark** (Malinin et al., NeurIPS 2022; Zenodo 7051658/7051692)
is the purpose-built distribution-shift MS benchmark (in-domain vs shifted `dev_out`/`eval_out`
splits; ~6 centers, multi-vendor). A conformal-FDR-under-shift paper is expected to report on it.
**But:** (a) it is FLAMeS-contaminated for our base model; (b) license is **CC-BY-NC-SA 4.0 /
OFSEP DUA — non-commercial, 3-year term**, a hard flag for a commercial-adjacent device; (c) it
supports a **marginal (pooled) shift** evaluation, not the per-site Mondrian nulls the method needs.

**Also add:** MICCAI-2008 (Boston CHB/UNC, 2 sites, 0.5 mm iso, public masks — external OOD test,
single-rater); adopt **lesion-wise F1/PPV + error-retention curves** as the primary metric axis (the
field has moved past Dice); cite FeTS/QU-BraTS as multi-site protocol precedent (non-MS).

## 4. The corrected roadmap (what is actually achievable, in order)

1. **Decontaminate (DONE, 2026-08-18).** The frozen null was rebuilt from FLAMeS-independent data
   only — `calm_ms_null_flames_v2.npz` (MSLesSeg, 115 cases; contaminated open_ms_data dropped, the
   v1 asset removed); `base_model_overlap` gates added to the registry; the OOD threshold re-validated
   on the v2 reference (unchanged at 5.0); 59/59 conformal tests green. The null is now genuinely
   exchangeable for a FLAMeS base, at the cost of being single-site (Catania) — the honest scope.
2. **Scanner-isolated measurement (needs one DUA + a base-model swap).** Measure the shift *within*
   **MSSEG-2** (15 scanners, uniform 4-rater annotation, FLAMeS-independent) — the one clean
   multi-scanner instrument — accepting FLAIR-only + new-lesion-task limits. This is where a
   label-free baseline might genuinely break and the Mondrian advantage could be shown.
3. **Better score (orthogonal, unbounded upside).** The α-ceiling is AUC, not data. Improving the
   learned score / base segmenter (better features, a stronger or fine-tuned segmenter) is the only
   lever for α<0.2 and is independent of the data-acquisition bottleneck.
4. **New multi-site acquisition (the real prerequisite).** For a certified per-site guarantee:
   ~20–30 labelled scans/scanner at ≥3–5 real scanners in one geometry — a clinical-partnership /
   prospective-collection effort, not a download. `sibbms`'s 100 controls seed one site's null but
   cannot substitute for multi-site acquisition.

## 5. Honest bottom line

The public-data route can support (a) a **decontaminated within-domain** result, (b) a **marginal
Shifts-based shift** characterisation, and (c) a **motivating** (confounded) 2-site illustration —
**not** a certified site-conditional guarantee. That guarantee, and any tighter-than-α≈0.2 operating
point, require **new multi-site data and a better score** — which is the honest, high-value thing to
tell a collaborator or reviewer, and the reason the feature stays DARK.
