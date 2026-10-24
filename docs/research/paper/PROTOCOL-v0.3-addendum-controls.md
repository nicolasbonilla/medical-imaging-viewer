# Paper A v0.3 — pre-registered addendum: 100 healthy controls (SibBMS)

*Research code, not the medical device. Written 2026-10-24 and committed **before** any outcome
(candidate, selection, count, DIS status) was computed on the 100 control ensemble maps or on the 70
control fold-0 maps never analysed before. Deviations after this commit go to §11 with a reason,
before the affected result is looked at.*

**What had been seen when this was written.**
1. The v0.3 results (`RESULTS-v0.3.md`, Table 7): **fold-0** outcomes on 30 of these 100 controls
   (sub-001…020, sub-031…040, August fold-0 maps). The fold-0 arm on those 30 is therefore **not
   blind**; on the other 70, and for the ensemble arm on all 100, nothing outcome-related was seen.
2. Gate C0 inventory (`research/paper_a/v03c_inventory.py` →
   `docs/research/records/2026-10-24_paper_a_v03c_inventory.json`): SHA-256 of all 700 inputs,
   grid, dtype and scaling, a yes/no check that maps decode into [0, 1] (no maximum and no count of
   voxels ≥ 0.5 was recorded), HD-BET brain volumes, MSMask-atlas alignment, new-vs-August fold 0
   on the 30 known controls, and a check against the FLAMeS training fingerprint.
3. The frozen calibration (`research/paper_a/v03c_calibration.py` →
   `docs/research/records/2026-10-24_paper_a_v03c_calibration.json`), computed from the v0.3
   **patient** candidate cache only.
4. Processing manifests (`flames-ensemble/manifests/sibbms-ctl-{pilot,a,b,c}.json`,
   `controls/manifests/…`): status, timings, versions, grids, brain volume — no outcome. The cloud
   pilot `sibbms-ctl-pilot` (sub-001 + sub-021) was checked by `research/cloud/check_outputs.py`,
   which prints grid and value-range checks and, for the August control sub-001 only, fold-0 vs
   August agreement; no lesion outcome of a new control was displayed.

## 1. Contamination check — were SibBMS subjects in FLAMeS's training data?

**Answer: no evidence of overlap; treated as clean.** Sources:
- FLAMeS journal paper (Dereskewicz, La Rosa et al., *J Neuroimaging* 35(5):e70085, 2025;
  PMC12426979), Table 1: the training set is 668 FLAIR scans from 11 sources — RADIEMS 241, NIH 200,
  LCL 64, MSSEG-1 centres 01/03/07/08 (15/8/15/15), MSCog 66, ISBI-2015 20, PubMRI (= Ljubljana) 20,
  NYU 4 (sum 668) — all described as people with MS; no healthy-control or Siberian/Russian source.
- Zenodo 17955359 (v2.0, 2025-12-16, the weights we use): "trained on 668 MRI scans acquired using
  Siemens, GE, and Philips 1.5T and 3T scanners"; no dataset added.
- The released weights' nnU-Net `dataset_fingerprint.json` has exactly 668 entries (v0.2 record
  `2026-10-17_flames_fold_membership.json`: 668/668 identifiers mapped).
- Timing: FLAMeS was submitted and posted on 2025-05-23; the SibBMS archive is dated 2025-08-04 and
  its preprint (Tuchinov et al., medRxiv 10.1101/2025.08.14.25333741) 2025-08-14.
- Supporting forensic check (gate C0): of the 319 fingerprint entries with 1-mm spacing, none has a
  crop near the SibBMS template grid (197 × 233 × 189, as an unstripped Norm image would) and none is
  within 2 voxels (any axis order) of any control's brain box; FLAMeS's 1-mm training brains are
  smaller (median box 132 × 137 × 172 vs 146 × 155 × 182 voxels for the template-space controls).
  This is supporting only — boxes from another skull-stripping tool need not match exactly.
- Residual uncertainty: the FLAMeS preprint mentions a later expansion "by an additional 507 scans
  from three external datasets"; the released weights' fingerprint has 668 entries, so the weights we
  use do not contain it. The registry note "not among the 11 training sources" (2026-10-17) is
  confirmed.

## 2. Data

- **100 SibBMS healthy controls** (sub-001…sub-100, one scan each, the full set in the public
  release; `Output/Norm`, i.e. spatially normalised to a template). Licence **CC BY-NC-SA 3.0**
  (the paper also states CC BY 3.0; we apply the stricter one): research use only.
- Processing (manifests): HD-BET v2.0.1 (commit 678e44d, CPU, TTA on, same as August) on the Norm
  FLAIR; FLAMeS folds 0–4 (`nnUNetTrainer_8000epochs`, checkpoint_final, no TTA); maps stored
  uint8 + `scl_slope` (max decoding error ≈ 0.002). 0 errors (HD-BET 100/100, FLAMeS 500/500).
- **Gate C0 (passed):** one grid for all 100 (197 × 233 × 189, 1 mm, axis-aligned, origin
  (−98, −134, −72)); every map on the mask grid; masks all zero; maps in [0, 1]; the app's MNI-grid
  check `looks_mni` passes; the MNI152 MSMask atlas overlaps the HD-BET brain masks with median Dice
  0.968 (min 0.796); new fold 0 reproduces the August fold 0 on the 30 known controls (max |Δp|
  0.0023, **0 voxels** change side of 0.5). HD-BET brain volume median 1987 mL (template space; a
  native adult brain mask is ≈ 1.2–1.6 L).
- **QC flag fixed now, from the inventory, before outcomes:** sub-075's HD-BET mask is 2829 mL and
  overlaps the atlas with Dice 0.80 (34 % of the mask lies outside the atlas brain: likely
  extra-cerebral tissue left in). It stays in the primary analysis (the app would process it) and is
  removed in sensitivity analysis S6.

## 3. Quantities (v0.3 §3–§4 rules, unchanged; v0.3 code reused)

- Candidates: 18-connected components of {p ≥ 0.5} with physical volume ≥ 3 mm³; score = mean
  probability over the candidate (`v03_candidates.candidates`).
  - **Ensemble arm (primary):** map = voxelwise mean of the 5 fold maps.
  - **Fold-0 arm (secondary; the v0.1/v0.2 pipeline).** Folds 1–4 as context only.
- Every control candidate is false (all-zero mask). A **reported lesion** is a selected candidate.
- Per control i at an operating point: R_i = 1{≥ 1 reported lesion}, F_i = number of reported
  lesions. Raw (no selection, = the full lesion overlay): C_i = number of candidates.
- **Why R_i is the right quantity.** On a lesion-free scan FDP = R_i, so E[FDP] = P(R = 1). The
  procedures' guarantees therefore become bounds on the healthy false-alarm rate, *if* control
  candidates are exchangeable with the patients' false candidates (P1) or controls with calibration
  patients (P2, B2, B3): P1 conformal BH: P(R = 1) ≤ α; P2 FDX threshold: P(FDP > γ) = P(R = 1) ≤ δ
  = 0.1 for any γ < 1; B2 conformal risk control: ≤ α; B3 Learn-then-Test: ≤ α with probability
  ≥ 0.9 over calibration; B1 precision-matched threshold: no guarantee (reported against α,
  descriptive). Calibration is fixed, so the 100 controls are independent test scans given the
  calibration and the exact binomial interval is the right one for the calibration-conditional rate.

## 4. Calibration configurations (frozen; patient data only)

From `2026-10-24_paper_a_v03c_calibration.json` (patient cache SHA-256 2096109e…, unchanged since
v0.3). Pools use FLAMeS-clean scans only, as in v0.3. P1 uses the pool's whole false-candidate null
and BH within each control scan; the "cut" is the score a candidate must exceed to be selected in a
scan with a single candidate (p ≤ α). The fold-0 thresholds reproduce v0.3's control section
exactly (16/16).

| arm · pool | scans / null size | P1 cut α = 0.1 / 0.2 / 0.3 | P2 γ = 0.1 / 0.2 | B1 α = 0.1 / 0.2 | B2 α = 0.1 / 0.2 | B3 α = 0.1 / 0.2 |
|---|---|---|---|---|---|---|
| **ens · 1-mm sites (primary)** | 125 / 1339 | 0.914 / 0.883 / 0.854 | 0.965 / 0.965 | 0.894 / 0.777 | 0.961 / 0.916 | 0.970 / 0.885 |
| ens · all five patient sites | 304 / 3390 | 0.924 / 0.893 / 0.860 | 0.975 / 0.974 | 0.916 / 0.798 | 0.971 / 0.952 | 0.972 / 0.885 |
| ens · MSLesSeg only | 115 / 1257 | 0.914 / 0.883 / 0.853 | 0.965 / 0.965 | 0.900 / 0.811 | 0.961 / 0.918 | 0.970 / 0.899 |
| ens · thick-slice sites | 179 / 2051 | 0.932 / 0.901 / 0.867 | 0.981 / 0.980 | 0.929 / 0.815 | 0.975 / 0.959 | 0.983 / 0.907 |
| f0 · 1-mm sites | 125 / 1442 | 0.963 / 0.949 / 0.933 | 0.983 / 0.983 | abstain / 0.924 | 0.981 / 0.977 | 0.990 / 0.978 |
| f0 · all five patient sites | 304 / 3925 | 0.969 / 0.955 / 0.941 | 0.994 / 0.994 | abstain / 0.953 | 0.991 / 0.983 | 0.993 / 0.979 |
| f0 · MSLesSeg only | 115 / 1348 | 0.963 / 0.949 / 0.933 | 0.982 / 0.982 | abstain / 0.931 | 0.981 / 0.977 | 0.990 / 0.979 |
| f0 · thick-slice sites | 179 / 2483 | 0.973 / 0.958 / 0.945 | 0.996 / 0.996 | abstain / 0.961 | 0.993 / 0.987 | 0.996 / 0.988 |
| LST-AI ens · 1-mm sites (deferred, E1) | 144 / 3294 | 0.780 / 0.729 / 0.677 | 0.887 / 0.882 | 0.919 / 0.770 | 0.878 / 0.850 | 0.892 / 0.852 |

Why the **1-mm-site pool is primary**: the controls are delivered on a 1-mm MNI-type grid after
registration and resampling, like MSLesSeg (the bulk of that pool), and the app research spec allows
the false-lesion dial only with 1-mm-site or same-site calibration. Note: P2 γ = 0.1 and γ = 0.2 have
the same threshold (0.965) in the primary pool, so those two primary cells will be identical; they
are kept for continuity with v0.3, not counted as independent evidence.

## 5. Primary endpoint

**Ensemble arm, 1-mm-site calibration, four operating points: P1 α = 0.1, P1 α = 0.2, P2 γ = 0.1,
P2 γ = 0.2.** For each: x = number of the 100 controls with ≥ 1 reported lesion; exact two-sided
95 % Clopper–Pearson interval [L, U] on 100 distinct scans (and the one-sided 95 % upper bound when
x = 0, 2.95 %). Classification (v0.3 §9 rule, nominal ν = α for P1, ν = δ = 0.1 for P2, margin 0.05):
**violated** if L > ν; **holds** if U ≤ ν + 0.05; otherwise **inconclusive**. In counts out of 100:
at ν = 0.1 holds iff x ≤ 7, violated iff x ≥ 17; at ν = 0.2 holds iff x ≤ 16, violated iff x ≥ 29.
Bonferroni intervals (level 1 − 0.05/4) are also reported.

## 6. Secondary endpoints

- **S1 every operating point:** ensemble and fold-0 arms × the four pools × P1 (α 0.1, 0.2, 0.3),
  P2 (γ 0.1, 0.2), B1–B3 (α 0.1, 0.2); same x, CP interval and class (B1: against α, labelled "no
  guarantee"). Own-null floor (leave-one-control-out null, controls exchangeable by construction)
  for P1, both arms. Folds 1–4 raw candidate counts as context.
- **S2 false lesions per scan:** mean, SD, median, max and distribution (0 / 1 / 2 / ≥ 3) of F_i at
  every operating point, and of C_i raw; per-100-scan totals for continuity with v0.3 Table 7.
- **S3 the app's dissemination-in-space rule on healthy scans.** The code path *can* run on these
  data: the app's `looks_mni` check passes and the MSMask atlas is aligned (gate C0). Per control,
  the lesion set is turned into a binary mask and passed through the app's own functions —
  `ms_region_classifier.generate_zone_map_atlas` (MSMask zones), `classify_from_zone_mask`
  (MAGNIMS contact rule) and `lesion_analysis_service.compute_dis_criteria` (`dis_met_brain`:
  qualifying lesions in ≥ 2 of periventricular, juxtacortical, infratentorial; spinal cord and optic
  nerve not available → `None`; dissemination in time not assessed). Lesion sets: (a) raw ensemble
  segmentation (all candidates = what the overlay shows), (b) raw fold 0, (c) ensemble selections at
  the four primary operating points, (d) ensemble, all-sites pool, P1 α = 0.1 / 0.2. Outcome: share
  of controls with `dis_met_brain`, CP interval; also share with ≥ 1 lesion in any DIS region.
  Caveat stated a priori: the atlas is applied without registration, exactly as in the app; on a
  template-normalised image that is the app's most favourable case.
- **S4 ensemble vs fold 0** (same 100 controls, paired): at the four primary operating points and
  for raw "≥ 1 candidate": difference in x/100, exact McNemar two-sided p, paired bootstrap 95 %
  interval (2000 resamples, seed 20261024); difference in mean false lesions per scan.
- **S5 blindness sensitivity:** fold-0 arm on the 70 never-analysed controls vs the 30 analysed
  before; ensemble arm on the same split.
- **S6 QC sensitivity:** primary and S3 without sub-075.
- **S7 where the false lesions sit (descriptive):** per raw and per selected ensemble candidate:
  distance to the HD-BET brain-mask boundary (Euclidean distance transform inside the mask, mm; share
  within 3 mm = "skull-strip edge"), app region (PV / JC / IT / DWM / outside atlas coverage), volume,
  score.
- **S8 reproduction:** fold-0 control candidates of the 30 August controls vs the v0.3 cache
  (counts equal; scores within 0.003).
- **E1 (deferred, exploratory) LST-AI arm.** LST-AI v1.2.0 control maps are being computed (VM
  `lstai-ctl`). When they exist, the same analysis runs for the LST-AI ensemble with the frozen LST-AI
  1-mm-site calibration above (null = LST-AI false candidates of MSLesSeg 114 + Ljubljana 30) —
  P1 α 0.1 / 0.2, P2 γ 0.1 / 0.2, raw counts, S3. Paper A's multi-site results use FLAMeS only, so
  E1 does not block anything. **TODO** until the maps exist.

## 7. Independent check (before any result is written into the paper)

A second, short script written separately (`v03c_controls_check.py`) recomputes the primary counts
with independent code: its own 18-neighbour labelling (breadth-first search over voxels ≥ 0.5), its
own volume filter and mean score, its own conformal p-values and BH, the P2 threshold from the frozen
record, and the null re-derived from the patient cache by its own selection code (its SHA-256 must
equal the frozen one). Counts must match exactly; any mismatch stops the write-up and is logged
in §11.

## 8. How the old "0/200 healthy DIS, CI ≤ 1.8 %" claim is replaced

v0.1 claimed "0 of 200 healthy scans certified as DIS, 95 % CI ≤ 1.8 %"; the 200 were 20 re-splits
of 30 scans. v0.2 corrected it to 0/30 distinct scans (one-sided 95 % upper bound 9.5 %) — still a
statement about v0.2's Layer-2 *certificates* on fold-0 maps. v0.3 did not re-run Layer 2, and this
addendum does not either (scope). The paper will:
1. remove every sentence that presents a healthy-DIS rate from 30 (or 200) scans as current evidence;
2. report instead, on **100 distinct controls**, the app's DIS rule applied to the raw segmentation
   and to the conformally selected lesions (S3), with exact intervals, and the primary false-alarm
   counts (§5);
3. keep the v0.2 certificate result only in the changelog / negative-results record, labelled
   "v0.2, Layer 2, fold 0, 30 scans, not re-evaluated".

## 9. Decision rules — what the paper and the app may claim

**Paper.**
- Primary cell *violated* → the paper (abstract included) states that the lesion-level guarantee
  calibrated on MS patients **does not transfer to healthy brains** at that operating point, with the
  numbers.
- *Holds* → "x of 100 healthy controls from one site received ≥ 1 reported lesion (95 % CI L–U %),
  consistent with the nominal level". Never "guaranteed specificity", never a population claim.
- *Inconclusive* → "undecided", with the interval.
- Whatever the primary result, all S1 cells are reported, including any violated fold-0 or
  other-pool cell, and the fold-0 cells on the 30 known controls are flagged as not blind.
- S3: the raw-segmentation DIS rate is reported whatever it is. If its interval's lower bound
  exceeds 5 %, the paper and the app document must say that the unselected automatic segmentation
  fulfils the app's brain-DIS rule in that share of healthy brains.
- Everything is "one site, one scanner population, template-normalised, non-commercial licence".

**App (research input only; no app code is changed by this addendum).**
- A healthy-brain false-alarm figure may be described for an operating point only if its primary
  cell is **not violated**, and only as the observed x/100 with its upper bound and the evidence
  ("100 healthy adults, one public research dataset, one site, template-normalised images"), for the
  matching configuration (FLAMeS 5-fold ensemble, same version, 1-mm-site calibration, 1-mm-grid
  study). It never applies to thick-slice studies or to other calibration types.
- For an operating point whose cell is violated or inconclusive, the app may only say that the
  setting is not validated on healthy brains (and, if violated, that false lesions appeared in about
  x of 100 healthy scans).
- The general rule "no guarantee for healthy or screening populations" stays in any case (one site).
- SibBMS is CC BY-NC-SA: before any number derived from it appears in a commercial product or its
  labelling, the licence must be clarified with the authors. Until then it is research evidence only.

## 10. Statistics and compute

Exact two-sided 95 % Clopper–Pearson intervals; one-sided 95 % bound for x = 0; classification
margin 0.05; Bonferroni over the 4 primary cells; exact McNemar (binomial on discordant pairs);
paired bootstrap 2000 resamples, seed 20261024. One scan per subject, so scan = subject = unit.
Local CPU only, no cloud compute; inputs in a scratch folder (hashes in the C0 record), control
candidates cached in the git-ignored `research/paper_a/.cache/v03c_controls.pkl` (SHA-256 in the
results record). Code: `research/paper_a/v03c_{inventory,calibration,controls,controls_check}.py`.
The app modules are imported read-only, in a process with the offline test environment
(`GOOGLE_APPLICATION_CREDENTIALS` = missing file, empty `CLOUDSDK_CONFIG`,
`GOOGLE_CLOUD_PROJECT=mstool-offline-tests`), never with research credentials.

## 11. Deviations log

*(empty at the addendum commit)*
