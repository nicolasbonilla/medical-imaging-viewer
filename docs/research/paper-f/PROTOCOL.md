# Paper F — Public CPU lesion segmenters vs the FLAMeS ensemble on real thick-slice FLAIR

**Pre-registered analysis protocol, version 1.0 — 2026-10-21.** Research only, not part of the
medical device. Branch `research/paper-f-tool-benchmark`. This file, `research/paper_f/metrics.py`,
`research/paper_f/evaluate.py` and `research/paper_f/flames_inputs.json` are committed **before any
output of MindGlide, WMH-SynthSeg or SAMSEG exists** (no job has been launched). Any later change is
listed in section 12 with its date and reason; the git history is the audit trail.

> **Resumen en español sencillo.** Queremos saber si alguna herramienta pública que funciona sin
> tarjeta gráfica marca las lesiones de esclerosis múltiple igual o mejor que FLAMeS (el modelo que ya
> usamos) en resonancias FLAIR de **cortes gruesos** (4–8 mm), que son las más comunes en los
> archivos de hospitales. Comparamos MindGlide, WMH-SynthSeg y SAMSEG (y LST-AI donde ya existe)
> contra FLAMeS en 324 estudios de 5 colecciones públicas. Lo que más cuenta: cuántas lesiones acierta
> (F1 por lesión) y cuántas lesiones falsas marca por estudio. Todas las reglas están escritas aquí
> antes de ver un solo resultado, para que nadie pueda ajustarlas después a conveniencia.

## 1. Question and why it matters

FLAMeS (nnU-Net, 5-fold ensemble, FLAIR only) is the reference segmenter of the MSTool-AI research
pipeline. It was trained on 3D/near-isotropic FLAIR (ISBI-2015, Ljubljana, MSSEG-2016). Routine
clinical archives are dominated by **2D FLAIR with 4–8 mm slices**. On three public thick-slice cohorts
the FLAMeS fold-0 pilot gave Dice 0.40–0.80 on one case each (section 11).

**Primary question.** On real thick-slice 2D FLAIR (slice spacing > 3 mm), does any public lesion
segmenter that runs on CPU (MindGlide, WMH-SynthSeg, SAMSEG) achieve a different lesion-wise F1, or a
different number of false lesions per scan, than the FLAMeS 5-fold ensemble?

**Secondary questions.** (a) The same on isotropic 1 mm FLAIR, including LST-AI; (b) whether a tool
degrades less than FLAMeS from isotropic to thick slices; (c) whether disagreement between FLAMeS and
a second tool flags scans where FLAMeS is poor (input for a "second opinion" feature, APP-FEATURE.md).

What this paper will **not** claim: clinical validity, new-lesion detection, any use of T1, or
superiority on data seen in training (section 3).

## 2. Cohorts (fixed; 324 scans)

The inputs are the exact FLAIR files the FLAMeS maps were computed from (same SHA-256, frozen in
`research/paper_f/flames_inputs.json` from the FLAMeS run manifests); the expert masks are the
`{case}_gt.nii.gz` files on the same grid. No case is added or removed after this date, except by the
rules of section 9.

| Cohort | Scans / patients | Scanner, sequence | Grid the tools receive (slice spacing) | Band | Skull strip | Licence |
|---|---|---|---|---|---|---|
| MSLesSeg (Figshare 52771814) | 115 / 75 (longitudinal) | 1.5 T, Catania | MNI 1 mm iso, 182×218×182 | iso | provided | CC BY 4.0 |
| Ljubljana, open_ms_data (Lesjak 2018) | 30 / 30 | 3 T Siemens, 3D FLAIR | MNI 1 mm iso | iso | provided | CC BY |
| MS3SEG (Figshare 10.6084/m9.figshare.30393475) | 100 / 100 | Toshiba 1.5 T, axial 2D | 0.898² × 6.0–8.1 mm, native | thick (> 5.5) | HD-BET 2.0.1 (from the FLAMeS run) | CC BY 4.0 |
| Muslim et al. 2022 (Mendeley 8bctsm8jz7) | 51 / 51 axial | 1.5 T, ~20 centres, 2D | 0.41–0.97² (estimated) × 4.86–8.3 mm | thick (24 in 3–5.5, 27 > 5.5) | HD-BET 2.0.1 (idem) | CC BY 4.0 |
| PediMS (Figshare 10.6084/m9.figshare.28701065) | 28 / 9 children (longitudinal) | Siemens Skyra 3 T, 2D | 0.75² × 3.9 mm | thick (3–5.5) | SynthStrip (dataset) | CC BY 4.0 |

Iso band: 145 scans / 105 patients. Thick band: 179 scans / 160 patients. Cohort details, rater
protocols and caveats: `docs/research/cohorts-extra.md` (MS3SEG, Muslim, PediMS) and
`data/registry.yaml` (MSLesSeg, Ljubljana).

## 3. Tools, versions, licences, training data and contamination

| Tool | Exact version | Code licence | Weights licence | Training data | Overlap with our 5 cohorts |
|---|---|---|---|---|---|
| **FLAMeS** (reference) | nnU-Net v2, 5 folds, Zenodo 17955359 (Dec 2025); maps already computed (Oct 2026 runs) | Apache-2.0 (nnU-Net) | CC BY 4.0 | ISBI-2015, Ljubljana, MSSEG-2016 (FLAMeS refs 12–14; `data/registry.yaml`) | **Ljubljana: in training except patients 16–20 and 26–30** → those 20 scans are excluded from every FLAMeS comparison |
| **LST-AI** | v1.2.0 Docker image `jqmcginnis/lst-ai@sha256:2b2a0d64…`, 3 U-Nets; maps already computed for MSLesSeg (114; P49_T2 has a blank T1) + Ljubljana (30) | MIT | released with the MIT repo; no separate licence found | 491 in-house 3D FLAIR + T1, Philips 3 T, TUM (Wiltgen 2024) | none; Ljubljana is one of LST-AI's published **test** sets (kept, noted) |
| **MindGlide** | 1.3.0, `ghcr.io/ms-pinpoint/mindglide@sha256:14e88f61d6cba18322d03774b168682e255383387aaab55e6a5aa33a2dbdd971` (built 2026-08-13; 4.66 GB compressed); weights `_20240404_conjurer_trained_dice_7733.pt` sha256 `881e30ef…e76ca` (Hugging Face MS-PINPOINT/mindglide @ a1969821) | MIT (UCL 2023) | **not stated** (no model card; trained on industry trial data) | 4,247 real scans (2,092 T1, 2,155 FLAIR; 2,871–2,934 patients, 592 scanners; ADVANCE, ASCEND, BRAVO, DEFINE/CONFIRM/ENDORSE, EXPAND, INFORMS, SPI2, UCL PITMS) + 4,303 SynthSeg-2.0 synthetic scans with random 1–9 mm resolution; lesion labels from an automated CNN on FLAIR | none; Ljubljana (and ISBI) were in its **external test** (n = 50 masks / 35 patients) |
| **WMH-SynthSeg** | FreeSurfer 8.2.0 `mri_WMHsynthseg`, `freesurfer/freesurfer@sha256:5648104ca75a24f6ee5a8786146f99b405c2bda1da12bff723a15056da8ddf6b`; model `WMH-SynthSeg_v10_231110.pth` (790,531,383 bytes, MGH FTP; SHA-256 frozen at first download) | FreeSurfer Software License Agreement | not stated; FreeSurfer licence assumed | synthetic images only, from real label maps: HCP (897), ADNI (1,148), WMH challenge, **ISBI-2015 (15)**, **MSSEG-2016**; random slice spacing 2.5–8.5 mm | none |
| **SAMSEG** (`--lesion`) | FreeSurfer 8.2.0 `run_samseg` (same image; samseg code `2ce2b6be`) | FreeSurfer licence; samseg `setup.cfg` says MIT | atlas/VAE in FreeSurfer (FreeSurfer licence) | atlas: 20 manually segmented subjects; lesion shape VAE: 212 MS subjects, Basel; evaluated on MSSEG-2016 and ISBI-2015 (Cerri 2021) | none |

Licence consequences (details and sources: RUNBOOK.md section 6): all five are fine for a research
paper. **None is cleared for the product** as is: the FreeSurfer licence allows broad use but states
the software is "designed for research purposes only… clinical applications are neither recommended
nor advised"; MindGlide's weights have no stated licence and come from private trial data; LST-AI is
"research-only… not validated, licensed or approved for any clinical usage".

**Not included and why.** LST-AI on the thick cohorts (needs a co-registered T1 that the FLAMeS
staging did not prepare; out of scope). LST-LPA (needs MATLAB + SPM). SynthSeg (no lesion class).
Tools that need per-site training (BIANCA) or a GPU.

**CPU feasibility rule (owner's rule: < ~15 min per scan on CPU).** MindGlide (README: ~1.5 min for a
2 mm scan, "a few minutes" for 1 mm, multi-core CPU) and WMH-SynthSeg (wiki: ~1 min per scan on CPU,
but ~32 GB RAM → run on 32 GB machines) are expected to pass. SAMSEG is uncertain: Cerri 2021 report
~10 min CPU (12-core i7) + ~5 min GPU; no CPU-only figure is published. The pilot measures it and
section 4.4 fixes what happens.

## 4. Processing (identical for every tool)

4.1 **Input**: the FLAMeS FLAIR file, byte-identical (SHA-256 checked on the VM against
`flames_inputs.json`; a mismatch excludes the case and is reported). Skull-stripped for all cohorts
(provided, or the HD-BET brain the FLAMeS run used). No other preprocessing; tool defaults except the
flags listed in 4.2. CPU only, 4 vCPU per job, containers pinned by digest and run with
`--network=none`.

4.2 **Commands** (recorded verbatim in each run manifest):
- MindGlide: `-i flair -o seg --device cpu` (defaults: RAS reorientation, 1 mm internal grid, sliding
  window, largest-component cleanup — applied to the whole non-zero label map, `ndimage.label(seg > 0)`
  in `transforms.py`, so lesions inside the brain are kept; output label map on the input grid;
  **lesion = label 18**; no probability map).
- WMH-SynthSeg: `mri_WMHsynthseg --i flair --o seg --csv_vols vols --device cpu --threads 4
  --save_lesion_probabilities` (output on its own 1 mm grid; **WMH = label 77**; probability map
  `<out>.lesion_probs`). Pre-stated memory fallback: `--crop` if the pilot shows > 30 GB peak or an
  out-of-memory stop on the 32 GB machine.
- SAMSEG: `run_samseg --input flair --output dir --lesion --lesion-mask-pattern 1 --pallidum-separate
  --threads 4 --random-seed 12345 --save-posteriors Lesions` (input voxel space; **lesion = label 99**;
  lesion posterior `posteriors/Lesions.mgz`).

4.3 **Onto the FLAMeS grid**: identity when the tool output has the FLAIR shape and affine (1e-4 mm);
otherwise the **footprint mean** (`job_common.footprint_to_grid`: each FLAMeS voxel is sampled at
⌈edge length in source voxels⌉ points per axis, trilinear, averaged). The tool's hard lesion label
becomes a lesion fraction per FLAMeS voxel and the binary mask is the **majority (fraction ≥ 0.5)**;
probability maps become their footprint mean. Rationale: a 1 mm output point-sampled onto a 6–8 mm
slice keeps or loses thin lesions by chance.

4.4 **Run order and budget tiers (fixed now; based on runtime only, never on accuracy).**
Tool-major order, cheapest first (WMH-SynthSeg, MindGlide, SAMSEG); within a tool, thick-band scans
first. After the pilot, with m = pilot median minutes per thick-slice scan for SAMSEG:
- m > 15 min → **SAMSEG dropped** (CPU rule), reported as "not feasible on CPU".
- otherwise the largest tier whose projected total spend (pilot + wave 1 actual + SAMSEG projection
  = scans × m × 1.25 at list price) stays ≤ 15 USD: **Tier A** all 324 scans; **Tier B** the 179
  thick-band scans; **Tier C** a fixed thick subsample = all PediMS (28) + all Muslim (51) + MS3SEG
  odd ids (50) = 129 scans; if none fits, SAMSEG is dropped for budget.
- MindGlide and WMH-SynthSeg run on all 324 scans unless their own pilot median exceeds 15 min per
  scan (then dropped by the same CPU rule). A tool that is not run on a cell is reported as
  "not run", never imputed.
- The rule is implemented, with tests, in `research/paper_f/plan_budget.py` (it reads only timings
  and memory from the pilot manifest).

## 5. Outcomes and exact definitions (`research/paper_f/metrics.py`)

**Co-primary**: (1) lesion-wise F1; (2) false lesions per scan. **Secondary**: voxel Dice; lesion-wise
precision and recall; recall by reference lesion size; predicted vs reference lesion volume (mL);
failure rate; CPU seconds and peak memory per scan.

- Predictions: FLAMeS = mean of the 5 fold probabilities > 0.5; LST-AI = ensemble probability > 0.5
  (LST-AI's own binarisation); MindGlide, WMH-SynthSeg, SAMSEG = the tool's own hard label, on the
  FLAMeS grid per 4.3. Reference = expert mask (> 0.5).
- Lesion = 3D connected component, 26-connectivity, on the FLAMeS grid.
- Size filter: components < **14.137 mm³** (sphere of 3 mm diameter; the 3 mm criterion of MAGNIMS and
  the MS3SEG / MSLesSeg annotation floors) are removed from prediction and reference before matching.
- Match: a predicted component is a true positive if it overlaps (≥ 1 voxel) any reference component;
  a reference component is detected if any predicted component overlaps it.
- Lesion precision = matched predicted / predicted; recall = detected reference / reference;
  F1 = 2PR/(P+R); F1 = 0 when nothing is predicted; **undefined when the reference is empty** (scan
  excluded from F1, kept for false lesions).
- False lesions per scan = predicted components (after the filter) touching no reference lesion.
- Dice on the unfiltered binary masks; undefined when the reference is empty.
- Size bins of reference lesions (mm³): 14–50, 50–200, 200–1000, ≥ 1000.
- Volumes = voxel count × voxel volume of the FLAMeS grid.

## 6. Bands

Slice spacing = largest voxel dimension of the grid the tools receive. **iso** ≤ 1.5 mm (MSLesSeg,
Ljubljana); **thick** > 3 mm (MS3SEG, Muslim, PediMS); exploratory sub-bands 3–5.5 mm (PediMS, 24
Muslim) and > 5.5 mm (MS3SEG, 27 Muslim). MSLesSeg's native acquisition may have been thicker; it is
classed by the grid the tools receive (resampled 1 mm MNI) and this is stated as a limitation.

## 7. Pre-stated comparisons (`evaluate.py prestated()`)

Inference for every comparison: per-scan differences (tool − FLAMeS) on scans where both are usable
and neither is contaminated; **patient-cluster bootstrap stratified by cohort**, 10,000 replicates,
seed 20261021; estimate = mean over cohorts of the per-cohort mean difference (each cohort counts
once); 95% percentile CI; two-sided bootstrap p (H0: difference 0). Equivalence: 90% CI inside
±0.05 F1 or ±1 false lesion per scan.

7.1 **Primary family (6 tests, Holm, α = 0.05 two-sided)**: for each of MindGlide, WMH-SynthSeg,
SAMSEG — Δ lesion F1 and Δ false lesions per scan vs FLAMeS, **thick band**.
Reading: a tool "outperforms FLAMeS on thick slices" only if Holm-p < 0.05 with ΔF1 > 0 **and**
Δ false lesions not worse beyond +1 per scan (or Holm-p < 0.05 with fewer false lesions and ΔF1 not
below −0.05). "Equivalent" when both 90% CIs lie inside the margins.

7.2 **Secondary family (11 tests, Holm separately)**: Δ F1 and Δ false lesions vs FLAMeS on the
**iso** band for MindGlide, WMH-SynthSeg, SAMSEG and **LST-AI** (8 tests; Ljubljana limited to the 10
FLAMeS-clean patients); degradation contrast (Δ F1 thick − Δ F1 iso) for the three new tools (3 tests;
the two bands share no patient, so their bootstraps are independent).

7.3 **Descriptive** (CIs, no tests): every tool × cohort × outcome; sub-bands; size bins; volumes;
failures; runtime and memory.

7.4 **Sensitivity** (primary family re-run, no Holm): S1 no size filter; S2 3 mm³ filter (MSSEG-2016
style); S3 in-plane 8-connectivity (components do not join across thick slices); S4 complete-case
(failures dropped instead of scored empty); S5 iso comparisons including the 20 FLAMeS-training
Ljubljana scans (flagged); S6 thick band without Muslim (estimated in-plane spacing changes mm³
thresholds); S7 scan-weighted instead of cohort-weighted.

7.5 **Exploratory (second opinion; APP-FEATURE.md)**: E1 AUROC of disagreement (1 − lesion F1 between
tool and FLAMeS) for scans where FLAMeS lesion F1 < 0.5, per tool and band; E2 "FLAMeS lesions
confirmed by the tool" (FLAMeS components overlapping the tool) vs FLAMeS alone: Δ F1 and Δ false
lesions. Labelled exploratory in every report.

7.6 **Secondary arm "MindGlide on its intended input"** (added 2026-10-22 before any full-run output
was examined, section 12; the primary arm and 7.1–7.5 are unchanged). MindGlide's README says "Feed it
raw NIfTI files. No skull-stripping, no bias correction, no registration, no reorienting needed", and it
was trained on images with skull; the identical-input rule (4.1) may handicap it. This arm gives
MindGlide the FLAIR **before skull stripping**, same command, label, grid rule and outcomes; outputs
`{case}_mindglide-raw_seg.nii.gz`.
- MS3SEG (100) and Muslim (51): the FLAIR in `inputs/extra_cohorts_raw_v1.tar.gz`, i.e. the file HD-BET
  was run on. The FLAMeS input is that image × the HD-BET mask saved with the same shape and affine
  (`cohorts_extra.hdbet_strip`), so both share the grid by construction.
- PediMS (28): `raw/defaced_FLAIR.nii.gz` from the PediMS Figshare record (defaced, skull present;
  Figshare MD5 checked; cached as `inputs/pedims_raw_flair_v1.tar.gz`), same shape and affine as the
  `processed/brain_FLAIR.nii.gz` FLAMeS input for all 28 (header check, cohorts-extra.md 3.3).
- On the VM every raw file's shape and affine are re-checked against the FLAMeS grid
  (`flames_inputs.json`, 1e-4 mm); a mismatch excludes the case and is reported.
- Not in this arm: MSLesSeg (public only as skull-stripped MNI images) and Ljubljana (a raw FLAIR exists
  in open_ms_data `cross_sectional/raw`, but not on the MNI grid of the FLAMeS maps and no transform is
  shipped; a new registration would add its own error). The arm therefore covers the **thick band**
  (179 scans).
- Comparisons, own Holm family (4 tests, thick band, inference as in 7.1): R1/R2 Δ F1 and Δ false
  lesions, MindGlide-raw − FLAMeS ("each tool on its intended input"; FLAMeS keeps the skull-stripped
  FLAIR it was run on); R3/R4 the same, MindGlide-raw − MindGlide on the skull-stripped input ("what
  skull stripping costs MindGlide"). Implemented as `secondary_raw_arm` in `evaluate.py`.

## 8. Precision (no formal power claim)

Thick band: 179 scans, 160 independent patients (PediMS: 9 children). Assuming a per-scan SD of 0.15
for ΔF1, the cohort-weighted 95% CI half-width is about ±0.04 F1, dominated by PediMS's 9 patients;
the scan-weighted estimate (S7) is tighter. Effects under ~0.04 F1 will be reported as inconclusive
unless the equivalence criterion is met.

## 9. Missing data, failures, exclusions

- Tool failure or timeout (45 min per scan) = empty prediction (intention to segment); S4 shows the
  complete-case view. Failure rate per tool and cohort is reported.
- Input SHA-256 mismatch → case excluded for all tools (expected: none).
- Contaminated cells (section 3) → excluded from comparisons with that tool, reported apart.
- Scans with an empty reference → excluded from F1/Dice, kept for false lesions (none expected).
- No outlier removal. The three pilot scans stay in the analysis.

## 10. Execution and blinding

Jobs and checks: RUNBOOK.md. The pilot is checked **structurally** (grid, binary, files, timings);
its plausibility warnings (Dice < 0.1 = orientation or label error) are the only accuracy numbers
looked at before the full run, and they cannot change any rule above except to fix a technical error
(e.g. a wrong label number), which would be logged in section 12. `evaluate.py run` is executed once
on the full outputs; the commit hash of the code used is written into the results.

## 11. Known before this protocol (disclosure)

- FLAMeS ensemble accuracy on MSLesSeg and Ljubljana (records/2026-10-18_flames_5fold_ensemble_check.txt:
  MSLesSeg median Dice 0.727, lesion F1 0.744; Ljubljana-clean Dice 0.673, F1 0.788).
- FLAMeS fold-0 Dice on one case per extra cohort (pilot: MS3SEG 0.59, Muslim 0.40, PediMS 0.80).
- LST-AI pilot sanity Dice on MSLesSeg P10_T1 (WARN threshold only).
- MindGlide's published external test on Ljubljana + ISBI (median Dice 0.606).
- No output of MindGlide, WMH-SynthSeg or SAMSEG on any of our scans; no LST-AI vs FLAMeS comparison.
- Added 2026-10-22: the MindGlide pilot (stripped input, 3 scans) was seen before 7.6 was registered —
  see the section 12 row of that date.

## 12. Deviations log

| Date | Change | Reason | Seen results before? |
|---|---|---|---|
| 2026-10-21 | 4.2: wording only — states that MindGlide's largest-component cleanup acts on the whole label map (checked in its source), not per label | clarification; no rule changed | no (nothing launched) |
| 2026-10-22 | Added the secondary arm 7.6 (MindGlide on the FLAIR before skull stripping; MS3SEG, Muslim, PediMS) with its own Holm family R1–R4; primary arm, outcomes and all other comparisons unchanged and running as registered | MindGlide's README asks for raw, non-skull-stripped input; the identical-input rule may handicap it | Only the MindGlide pilot (3 scans, stripped input): timings (~84 s/scan, peak 5.5 GB) and one plausibility volume — mslesseg_P10_T1: MindGlide 17.0 mL vs expert 3.0 mL (FLAMeS 3.1 mL). No full-run output had been examined; no raw-input output existed |
| 2026-10-24 | WMH-SynthSeg full run launched **without** `--crop`, although section 4 states "`--crop` if the pilot shows > 30 GB peak" and the FS pilot peaked at 31.32 GB (ms3seg_001; swap 1.41 GB). The coordinator applied RUNBOOK §3 step 6 instead (keep if peak swap < 2 GB), which contradicts this protocol; the contradiction was noticed during the run. Decision: keep the default (no crop) for **all** 324 scans, so every scan is processed the same way with the tool's default settings; any out-of-memory stop is re-run with `--crop` and reported as such. RUNBOOK §3 step 6 to be aligned with this protocol | process error (two documents with different rules); the run was 76/324 scans in, no out-of-memory stop (2 scans used 7.8–8.3 GB swap: ms3seg_002, ms3seg_040, 7.6–8.0 min) | Runtime and memory only (manifest timings, peak memory, swap). **No accuracy output of the full run had been examined** |
| 2026-10-24 | Not a deviation — application of the pre-stated budget tiers (section 4.4, `plan_budget.py`): spent 3.55 USD (pilots, MindGlide arms) + WMH-SynthSeg projected 7.46 USD = 11.01 USD; no SAMSEG tier fits under 15 USD, so **SAMSEG is dropped by the budget rule**. Raising the cap would be a protocol amendment (owner decision), to be logged here before any SAMSEG run | budget rule | Runtime only |
| 2026-10-28 | Not a deviation — the wave-2 step of the budget rule (RUNBOOK §4: "re-run the planner with the real spend so far") applied after wave 1 finished. Real spend: 3.55 USD (pilots, MindGlide arms) + WMH-SynthSeg full run **5.58 USD** (80,884 s on n2d-highmem-4, below the 7.46 USD projection) + ~0.1 USD for the muslim_16 re-run = 9.25 USD. `plan_budget.py --spent-usd 9.25` → **SAMSEG tier C** (all PediMS + all Muslim + MS3SEG odd ids = 129 scans; 3 VMs × 43; 7.6 h each; max-hours 9; 4.51 USD; projected total 13.76 USD ≤ 15). The 2026-10-24 "dropped" entry above was based on the projection; the rule's own re-run with real spend supersedes it. No cap change. Operational: boot disk 80 GB instead of the RUNBOOK's 150 GB (the FS pilot used 58 GB incl. the 41 GB image and 16 GB swap) so three VMs fit the 250 GB regional SSD quota | budget rule with real spend | Runtime and cost only. **No accuracy output of WMH-SynthSeg or any SAMSEG output had been examined** |
| 2026-10-28 | WMH-SynthSeg: 320 scans done, 1 out-of-memory stop (muslim_16, exit 137). As pre-stated (section 4 and the 2026-10-24 entry), muslim_16 is re-run with `--crop` and reported as cropped in the results | pre-stated OOM fallback | Runtime only |

## References (tools)

- MindGlide: Goebl P, …, Eshaghi A. *Enabling new insights from old scans by repurposing clinical MRI
  archives for multiple sclerosis research.* Nat Commun 16:3149 (2025), doi:10.1038/s41467-025-58274-8;
  code github.com/MS-PINPOINT/mindGlide (MIT).
- WMH-SynthSeg: Laso P, Cerri S, …, Iglesias JE. *Quantifying white matter hyperintensity and brain
  volumes in heterogeneous clinical and low-field portable MRI.* IEEE ISBI 2024,
  doi:10.1109/ISBI56570.2024.10635502 (arXiv 2312.05119).
- SAMSEG lesions: Cerri S, et al. *A contrast-adaptive method for simultaneous whole-brain and lesion
  segmentation in multiple sclerosis.* NeuroImage 225:117471 (2021), doi:10.1016/j.neuroimage.2020.117471.
- LST-AI: Wiltgen T, et al. *LST-AI: a deep learning ensemble for accurate MS lesion segmentation.*
  NeuroImage: Clinical 42:103611 (2024).
- FLAMeS weights: Zenodo record 17955359 (CC BY 4.0).
