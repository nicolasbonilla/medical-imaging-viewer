# Paper A v0.3 — pre-registered analysis protocol

*Research code, not the medical device. Written 2026-10-21 and committed **before** any v0.3
outcome (candidate labels, selections, FDP, recall, AUROC) was computed on the new data.
Deviations after this commit are logged in §13 with a reason, before the affected result is
looked at.*

**What had been seen when this was written.** (i) The v0.2 manuscript, records and code
(results on MSLesSeg, the 10 FLAMeS-held-out Ljubljana scans and 30 healthy controls, all with
FLAMeS fold 0 — so the fold-0 arm on those cohorts is *not* blind). (ii) The input inventory
`docs/research/records/2026-10-21_paper_a_v03_inventory.json` (`research/paper_a/v03_inventory.py`):
file hashes, shapes, voxel sizes, value ranges, expert-mask voxel counts, and a voxelwise
comparison of the new fold-0 maps with the August fold-0 maps. Nothing else. In particular, no
candidate, label, selection, recall or AUROC has been computed on MS3SEG, Muslim, PediMS, on any
5-fold ensemble map, or on LST-AI maps.

**Inventory result (gate G0, passed).** 324 cases × (5 FLAMeS folds + expert mask) and 144 ×
(LST-AI ensemble + 3 sub-models) open; every map has the shape and affine of its mask; masks are
binary; maps decode (NIfTI `scl_slope`) to probabilities in [0, 1]; 30 control maps open with
all-zero masks. The new fold-0 maps reproduce the August fold-0 maps of MSLesSeg and Ljubljana
(145 scans): max |Δp| = 0.0022 (uint8 storage), 6 voxels of 145 scans change side of 0.5.

---

## 1. Questions

- **Q1** Does the lesion-level false-discovery guarantee hold when calibrating on 1-mm (3D /
  isotropically delivered) FLAIR sites and testing on thick-slice 2D-FLAIR sites (MS3SEG, Muslim,
  PediMS)? And on every site held out (leave-one-site-out)?
- **Q2** How do validity and power change with slice thickness? Produce the per-thickness table a
  "reliability by slice thickness" app feature would be built on (guarantee status per band,
  minimum reliably detected lesion size, expected false lesions).
- **Q3** Does the 5-fold FLAMeS ensemble change validity / power relative to fold 0 alone?
- **Q4** Does per-site recalibration restore validity where it fails, and with how many
  calibration patients?

## 2. Data and eligibility

| site | scans / patients used | native FLAIR | slice spacing (header) | acq. class | FLAMeS overlap |
|---|---|---|---|---|---|
| MSLesSeg | 115 / 75 (up to 4 timepoints) | 1.5 T, ~3 scanners; delivered in MNI 1 mm; native geometry not published in the sources we could access | 1 mm | 1-mm | clean (FLAMeS external test) |
| Ljubljana open_ms_data | **10 / 10** (patients 16–20, 26–30) | 3T Siemens 3D FLAIR, MNI 1 mm here | 1 mm | 1-mm | patients 01–15, 21–25 are FLAMeS training data → **excluded from every FLAMeS analysis** (also as calibration) |
| MS3SEG | 100 / 100 | Toshiba 1.5 T, 2D, HD-BET | 6.0–8.1 mm (median 7.2) | thick | none known |
| Muslim 2022 | 51 / 51 (axial only) | ~20 centres 1.5 T, 2D, HD-BET; **in-plane pixel estimated** | 4.86–8.3 mm (median 6.0) | thick | none known |
| PediMS | 28 / 9 (children, longitudinal) | Siemens Skyra 3 T, 2D, SynthStrip | 3.9 mm | thick | none known |
| SibBMS healthy controls | 30 / 30 | FLAMeS **fold 0 only** (August run) | 1 mm | — | clean |

LST-AI v1.2.0 maps (ensemble + sub-models m1–m3) exist for MSLesSeg (114; P49_T2 skipped,
blank T1) and Ljubljana (30). LST-AI never trained on either (v0.2 Table 2), so all 30 Ljubljana
scans are LST-AI-clean; analyses that pair LST-AI with FLAMeS use only the 10 FLAMeS-clean ones.

**Unit of resampling and splitting: the patient.** Repeated timepoints of one patient
(MSLesSeg, PediMS) are never split across calibration and test, and are resampled together.

**Thickness bands** (from header slice spacing, fixed here from the inventory, before outcomes):
B1 ≤ 1.5 mm (MSLesSeg, Ljubljana; 125 scans) · B2 (1.5, 4.5] mm (PediMS; 28) · B3 (4.5, 6.5] mm
(Muslim 45, MS3SEG 31; 76) · B4 > 6.5 mm (MS3SEG 69, Muslim 6; 75). Bands are confounded with site;
every band result is also reported per site × band.

## 3. Candidates and lesion matching (v0.2 rule, unchanged)

- Candidate = 18-connected component of {p ≥ 0.5} of the probability map with **physical**
  volume ≥ 3 mm³ (voxel count × voxel volume of that scan). v0.2 data were 1 mm isotropic, so this
  is v0.2's rule; on thick grids one voxel (2.2–6.5 mm³) can already pass. We keep it rather than
  invent a thickness-specific rule.
- Expert lesions = 18-connected components of the mask with volume ≥ 3 mm³ ("detectable");
  "clinical" lesions ≥ 14.14 mm³ (3-mm-diameter sphere).
- One-to-one Hungarian (maximum-IoU) matching of candidates to detectable expert lesions;
  **primary lenient** (IoU > 0), **secondary strict** (IoU ≥ 0.10). A candidate is *true* iff
  matched; surplus fragments are false.
- Known limitation, accepted a priori: 3D components across 4–8 mm gaps can merge or split
  lesions; the same rule applies to candidates and expert lesions.

## 4. Scores and arms

- **Ensemble arm (primary).** Map = voxelwise mean of the 5 fold probabilities (nnU-Net's
  ensembling). Candidates on that map. **Primary score** = mean ensemble probability over the
  candidate.
- **Secondary score: fold disagreement.** For each ensemble candidate, p̄_k = mean of fold k's
  probability over the candidate (k = 0..4). Score S_cons = min_k p̄_k (lesion-like only if every
  fold agrees; parameter-free). Disagreement D = SD_k(p̄_k) is reported descriptively (AUROC of −D
  for true vs false).
- **Fold-0 arm** (Q3; = v0.2 pipeline). Map = fold 0; candidates on it; score = mean fold-0
  probability. Folds 1–4 are run the same way as context ("is fold 0 typical?").
- **LST-AI arms** (exploratory): ensemble map and sub-model m1, same candidate rule and score.
- Controls: fold-0 arm only.

## 5. Procedures (higher score = more lesion-like)

- **P1 conformal BH (primary FDR procedure; v0.2 primary).** Null = all false-candidate scores
  of all scans of the calibration patients; conformal p_j = (1 + #{null ≥ s_j}) / (n + 1); BH at α
  within each test scan. Guarantee E[FDP_scan] ≤ α under candidate-level exchangeability.
- **P2 scan-conformal FDX threshold (primary FDX procedure).** One scan per calibration patient
  (its first timepoint). For scan i, FDP_i(λ) = false/selected among {s ≥ λ} (0 if empty), on the
  grid λ ∈ {0, 0.001, …, 1, ∞}; safe threshold t_i = smallest grid λ with FDP_i(λ') ≤ γ for all
  grid λ' ≥ λ. λ̂ = the ⌈(K+1)(1−δ)⌉-th smallest t_i (λ̂ = ∞, i.e. abstain, if that index > K);
  select {s ≥ λ̂}. Guarantee P(FDP_test > γ) ≤ δ under exchangeability of calibration and test
  **patients** (no candidate-level assumption). This is a split-conformal quantile (the scan-level
  idea of v0.2 §5.3 applied to a single global threshold), not a new method.
- **Baselines carried over from v0.2:** B1 precision-matched global threshold (lowest threshold
  whose pooled calibration micro-FDR ≤ α; no guarantee); B2 conformal risk control, global
  threshold, per-scan FDP loss (E[FDP_scan] ≤ α under scan exchangeability); B3 Learn-then-Test,
  Hoeffding–Bentkus, δ = 0.1. B2/B3 use one scan per calibration patient. Implementations are the
  committed v0.2 `baselines.py` functions with the grid widened to [0, 1] (S_cons can be < 0.5).
- **Not carried over (decided now):** weighted conformal selection (its shape features are not
  comparable across anisotropic grids); Lee & Ren e-values (hierarchical variant had zero power at
  our group sizes in v0.2; the subsampling variant is randomised and was dominated); subsampled-null
  BH (no FDR guarantee); v0.2 Layer-1/Layer-2 FDX with region certificates (not re-run in v0.3 —
  scope; P2 shares Layer 2's validity basis but certifies only the selected set).

## 6. Calibration designs

- **D1 within-site.** Patient-grouped cross-fitting inside one site: 5 folds for MSLesSeg,
  MS3SEG, Muslim; leave-one-patient-out for Ljubljana-10 and PediMS-9. Every test scan once.
- **D2 leave-one-site-out (held-out site).** Calibrate on all eligible patients of the other four
  sites, test on all scans of the held-out site.
- **D3 1-mm → thick (Q1 primary).** Calibrate on MSLesSeg + Ljubljana-10; test on MS3SEG, Muslim,
  PediMS separately. **D3r** (secondary): thick → 1-mm (calibrate on the three thick sites, test on
  MSLesSeg and Ljubljana-10).
- **D4 pooled.** Patient-grouped 5-fold cross-fitting over the union of all five sites (folds
  assigned within each site), every scan tested once; reported per site and per band.
- **D5 recalibration curve (Q4).** For MS3SEG, Muslim, PediMS and Ljubljana-10: draw k
  calibration patients of the target site (k ∈ {1, 2, 3, 5, 10, 20, 40}, k ≤ patients − 4), test on
  all remaining patients of that site; R = 200 draws per k. Two modes: *site-only* (k target
  patients) and *augmented* (1-mm sites + k target patients). P2 site-only abstains by
  construction when k < 9 (δ = 0.1); reported as such.

## 7. Targets

FDR α ∈ {0.1, 0.2} (primary); α = 0.3 secondary (continuity with v0.2). FDX: γ ∈ {0.1, 0.2},
δ = 0.1. Baselines B1–B3 at α ∈ {0.1, 0.2}.

## 8. Outcomes

**Primary.** On held-out sites — D3 (3 thick sites) and D2 (all 5 sites) — for the ensemble arm,
primary score, lenient matching:
- P1: realised lesion-level FDR = **mean per-scan FDP** over the site's test scans (FDP = 0 when
  nothing is selected) vs α;
- P2: realised FDX = **fraction of test scans with FDP > γ** vs δ = 0.1;
with 95 % **patient-cluster bootstrap** intervals (2000 resamples, test patients resampled,
calibration fixed). 32 primary cells (P1: 8 site-designs × 2 α; P2: 8 × 2 γ).

**Secondary.**
1. Power: end-to-end lesion sensitivity at the guarantee = selected-and-matched expert lesions /
   all detectable expert lesions (≥ 3 mm³); clinical sensitivity (≥ 14.14 mm³); selection recall;
   pooled micro-FDR; scans with ≥ 1 selection; mean selections per scan.
2. Healthy controls (fold-0 arm): P1, P2, B1–B3 calibrated on the fold-0 candidates of (a) all
   five patient sites, (b) the 1-mm sites, (c) MSLesSeg only (v0.2 reference) → false detections
   per 100 control scans and controls with ≥ 1 false detection (exact CI); P1 own-null floor
   (leave-one-control-out).
3. Thickness stratification (Q2): per band B1–B4 under D2 and D4: realised FDR / FDX, power,
   false lesions per scan. **Minimum reliably detected lesion size** per band: expert lesions
   binned by volume [3, 14.14), [14.14, 50), [50, 150), [150, 500), ≥ 500 mm³; sensitivity per bin
   (a) of the raw segmentation (any lenient match, no selection) and (b) at the guarantee (P1
   α = 0.2 and P2 γ = 0.2, D2 calibration). Min reliable size = lower edge of the smallest bin such
   that it and every larger bin reach sensitivity ≥ 0.8 (also reported at ≥ 0.5); bins with < 10
   lesions in a band are flagged "insufficient".
4. Q3: ensemble minus fold 0 (paired by patient, same scans, same expert lesions): Δ realised FDR
   and Δ end-to-end sensitivity, patient-paired bootstrap CI, under D2, D3, D4 (P1 α = 0.2 primary
   contrast; others reported). Per-site candidate AUROC (patient-cluster CI) for ensemble mean,
   S_cons, −D, fold 0 and folds 1–4.
5. Q4: from D5, per k: mean over draws of realised FDR / FDX, share of draws with realised FDR > α
   (calibration-conditional failure), mean power. k* = smallest k with mean realised FDR ≤ α
   **and** mean power ≥ 0.9 × the D1 power of that site.
6. Mechanism (descriptive): per-site false-candidate score distribution (mean, quartiles),
   candidate AUROC, ICC of false-candidate scores by scan; scan-clustered permutation KS test of
   the false-score law of each thick site vs the 1-mm sites (2000 permutations).
7. LST-AI (exploratory): D1 within MSLesSeg and Ljubljana-30 for LST-AI ensemble and m1; segmenter
   shift FLAMeS-calibrated → LST-AI-tested and the reverse, 5-fold patient cross-fit on MSLesSeg
   (calibration and test patients disjoint).

## 9. Statistics

- Patient-cluster percentile bootstrap, 2000 resamples, seed 20261021. Single-timepoint sites:
  exact Clopper–Pearson intervals for scan proportions in addition.
- **Cell classification** (FDR: nominal α; FDX: nominal δ = 0.1; margin 0.05 absolute):
  *violated* if the CI lower bound > nominal; *holds* if the CI upper bound ≤ nominal + 0.05;
  otherwise *inconclusive*. A non-violated cell with < 10 selections in total or end-to-end
  sensitivity < 0.05 is additionally flagged *uninformative (abstention)*.
- Multiplicity: with 32 primary cells, ~0.8 spurious one-sided 2.5 % "violations" are expected
  under exact validity; we also report each primary cell's classification with a Bonferroni
  interval (level 1 − 0.05/32).
- Secondary for primary cells: two-level bootstrap (calibration patients and test patients both
  resampled, 500 resamples) — the marginal (unconditional) view of the guarantee.

## 10. Success / failure criteria (decided now)

- **Q1 supported** if no D3 thick-site cell of P1 (α = 0.1, 0.2) is *violated* and the MS3SEG and
  Muslim cells *hold*; **refuted** if any D3 cell is *violated*; otherwise inconclusive. Same rule
  separately for P2 (γ = 0.1, 0.2). D2 cells are classified the same way and reported in full.
  Validity reached only through abstention is reported as such, not as success.
- **Q2** has no pass/fail: the deliverable is the per-band table. A band is labelled
  "guarantee holds" in the app spec only if its D2 P1 cells at α = 0.1 and 0.2 *hold* and are not
  uninformative.
- **Q3** "ensemble helps" if the paired Δ end-to-end sensitivity (P1, α = 0.2) has a CI excluding
  0 in the ensemble's favour in D2 and D3 without a new violated cell; "hurts" if excluding 0
  against; otherwise "no detectable difference".
- **Q4** k* per site and mode as defined in §8.5; "recalibration restores validity" for a site
  whose D2/D3 cell was *violated* if its D1 cell is not violated and k* exists.

## 11. Sensitivity analyses (pre-specified)

Strict matching (IoU ≥ 0.10) for the primary cells; secondary score S_cons for the primary
cells; Muslim lesion and candidate volumes scaled × 0.9 and × 1.1 (estimated pixel size) for the
size-bin table; PediMS without patient P9 (Baló's concentric sclerosis); α = 0.3.

## 12. Gates

- **G0 inventory** — passed (above).
- **G1 pipeline reproduction** — before any new-cohort outcome is read, the fold-0 arm on
  MSLesSeg and the 10 clean Ljubljana scans must reproduce v0.2's cached candidates (same counts
  and one-to-one labels on ≥ 99 % of candidates; scores within 0.003). If not, stop and log.

## 13. Deviations log

*(empty at the protocol commit 9951494)*

**2026-10-21, entries 1–4 — implementation clarifications, written while candidate extraction was
running and before any v0.3 outcome (label, selection, FDP, recall, AUROC) had been displayed.**

1. *FDX interval.* The percentile bootstrap of a scan proportion degenerates to [0, 0] when no
   scan exceeds γ (0/10 would be classified "holds" with upper bound 0, whereas the exact upper
   bound is 0.31). FDX cells are therefore classified with the **union** (wider envelope) of the
   patient-cluster bootstrap interval and the exact Clopper–Pearson interval over scans. FDR
   (mean per-scan FDP) cells keep the bootstrap interval; their small-site intervals (Ljubljana
   10, PediMS 9 patients) under-cover and are flagged as such.
2. *Bonferroni intervals* (§9) use 20 000 bootstrap resamples (2000 leave ~1.6 resamples beyond
   the 0.078 % tails).
3. *Muslim ±10 % volume sensitivity* rescales expert-lesion volumes for the size-bin table only;
   the 3 mm³ eligibility floor and the candidate set stay as extracted at the nominal pixel size.
4. *Gate G1 tolerance.* The inventory showed 6 voxels in 5 scans crossing 0.5 between the August
   and the new fold-0 maps, so candidate counts may legitimately differ in those scans. G1 passes
   if (a) scans with a different candidate count are among those 5, (b) lenient labels agree on
   ≥ 99 % of compared candidates and (c) scores agree within 0.003.

## 14. Compute

Local CPU only (8 workers), no cloud command. Derived candidate caches go to the git-ignored
`research/paper_a/.cache/`; their SHA-256 and the SHA-256 of every input file are written into
the records. Code: `research/paper_a/v03_*.py`; tests `research/paper_a/test_v03_metrics.py`.
