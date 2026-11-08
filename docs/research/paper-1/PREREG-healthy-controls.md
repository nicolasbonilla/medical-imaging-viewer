# Paper 1 — Healthy-control arm: false lesions and the app's dissemination-in-space rule on 100 healthy brains, six segmentation arms

**Pre-registration addendum, version 1.0 — 2026-11-08.** Research only, not part of the medical
device; no app code is changed. Branch `research/paper-1-healthy-controls` (from
`research/paper-f-tool-benchmark` at 1d3be48, with `research/paper-a-v0.3` merged in at 7977f76;
`research/cloud-jobs-controls-lstai` 5645fcb is already an ancestor). This file is committed and
pushed **before** any MindGlide, WMH-SynthSeg or SAMSEG output exists for any control, and before
any LST-AI healthy-control outcome is computed. Later changes go to section 12 with date, reason and
what had been seen; the git history is the audit trail.

> **Resumen en español sencillo.** Tomamos 100 cerebros sanos públicos (SibBMS) y contamos cuántas
> "lesiones" falsas marca cada herramienta automática: FLAMeS (el modelo que usa la aplicación, un
> solo pliegue, y el promedio de 5 pliegues que recomiendan sus autores), LST-AI, MindGlide,
> WMH-SynthSeg y SAMSEG. Medimos dos cosas por herramienta: (1) en cuántos cerebros sanos aparece al
> menos una lesión falsa y (2) en cuántos la regla de diseminación en el espacio de McDonald 2024, tal
> como la calcula la aplicación, saldría cumplida si nadie revisara el resultado. Todo se compara con
> el promedio de 5 pliegues de FLAMeS en los mismos 100 cerebros. Las reglas quedan escritas aquí
> antes de ver un solo resultado nuevo. Tope de gasto: 10 USD.

## 1. Question

In brains of healthy volunteers, every automatically segmented lesion is, by assumption, a false
lesion. **How often does each public MS-lesion segmenter produce at least one false lesion, and how
often would the McDonald 2024 brain dissemination-in-space (DIS) rule, exactly as MSTool-AI
implements it, be met on the tool's unreviewed output?** The FLAMeS 5-fold mean (the setting the
FLAMeS authors recommend) is the reference; FLAMeS fold 0 is the model the app ships.

What this arm will **not** claim: diagnostic specificity of any tool or of the app; anything about
patients, other sites, other scanners, native-space volumes, thick-slice studies, or dissemination
in time; superiority on any population other than these 100 controls.

## 2. Analysis set and inputs (fixed)

- **100 SibBMS healthy controls**, sub-001 … sub-100, one scan each (the full public release,
  `Output/Norm`, spatially normalised to a template; licence **CC BY-NC-SA 3.0**, academic research
  use only). Scan = subject = unit of analysis. No control is added or removed after this date,
  except by the rules of section 9.
- **Inputs = the files FLAMeS was run on**: `gs://mstool-research-data/controls/sibbms/sub-XXX_FLAIR.nii.gz`
  (HD-BET v2.0.1 commit 678e44d, CPU, TTA on, applied to the Norm FLAIR; float32 on the original Norm
  grid). Their SHA-256 are the `inputs_sha256` of the FLAMeS run manifests
  `flames-ensemble/manifests/sibbms-ctl-{pilot,a,b,c}.json`; they are frozen in
  `research/paper_1/controls_inputs.json` (built from those manifests and the single control grid of
  the paper A inventory record, no outcome read) and **every new tool run re-checks them on the VM**
  (a mismatch excludes the control for that tool and is reported).
- LST-AI received the same FLAIR (same SHA-256, `lstai/manifests/lstai-ctl.json`) plus the HD-BET-masked
  T1w on the FLAIR grid (`sub-XXX_T1.nii.gz`), run with `--stripped --segment_only --probability_map`.
  MindGlide, WMH-SynthSeg and SAMSEG receive the FLAIR only, as in paper F.
- **Grid**: one grid for all 100 controls (197 × 233 × 189, 1 mm isotropic, axis-aligned, origin
  (−98, −134, −72); paper A gate C0). Every tool output is put on this grid (the FLAMeS grid) by the
  paper F rule (`job_common.to_grid_footprint`: identity when shape and affine match within 1e-4 mm,
  else footprint mean; a hard label becomes the lesion fraction per voxel and the mask is the
  majority, fraction ≥ 0.5). Every transform is recorded per output.
- Lesion-free reference: the all-zero masks `flames-ensemble/cohort/sub-XXX_gt.nii.gz` (lesion-free
  by design). The HD-BET brain masks `controls/sibbms/sub-XXX_brainmask.nii.gz` are used only for the
  descriptive distance-to-edge and brain-volume normalisation (section 6).

## 3. The six arms (tools, versions, exact settings)

| Arm | What runs | Unreviewed lesion mask on the FLAMeS grid |
|---|---|---|
| **FLAMeS-ens** (reference) | FLAMeS nnU-Net v2, Zenodo 17955359 v2.0, `nnUNetTrainer_8000epochs`, checkpoint_final, folds 0–4, no TTA (maps already computed, runs `sibbms-ctl-*`; checkpoint SHA-256 fold 0 `4fc7db24…`, fold 1 `3966dd25…`, fold 2 `734be69b…`, fold 3 `8e989cac…`, fold 4 `ff723a2e…`) | voxelwise **mean of the 5 fold probabilities ≥ 0.5** |
| **FLAMeS-f0** | fold 0 of the same runs (the network the app ships) | **fold-0 probability ≥ 0.5** |
| **LST-AI** | v1.2.0, `jqmcginnis/lst-ai@sha256:2b2a0d6454e6efff60a350df3c650ae9584f1926338dec7842f9e71912cc6c85` (maps already computed, run `lstai-ctl`) | **ensemble probability ≥ 0.5** (`sub-XXX_lstai_prob.nii.gz`; LST-AI's default 0.5) |
| **MindGlide** | 1.3.0, `ghcr.io/ms-pinpoint/mindglide@sha256:14e88f61d6cba18322d03774b168682e255383387aaab55e6a5aa33a2dbdd971`, weights SHA-256 `881e30ef…e76ca`; `-i flair -o seg --device cpu` | **label 18** |
| **WMH-SynthSeg** | FreeSurfer 8.2.0 `mri_WMHsynthseg`, `freesurfer/freesurfer@sha256:5648104ca75a24f6ee5a8786146f99b405c2bda1da12bff723a15056da8ddf6b`, model `WMH-SynthSeg_v10_231110.pth` (790,531,383 bytes, SHA-256 `0ece39dd651357aa95222fc4d45fa32d00f11e763d2583cae3f869989ce35988`); `--device cpu --threads 4 --save_lesion_probabilities`, no `--crop` | **label 77** |
| **SAMSEG** | FreeSurfer 8.2.0 `run_samseg` (same image) `--lesion --lesion-mask-pattern 1 --pallidum-separate --threads 4 --random-seed 12345 --save-posteriors Lesions` | **label 99** |

The three new tools run exactly as in paper F (`research/cloud/toolbench_driver.py`, commands
recorded verbatim in each manifest): containers pinned by digest, `--network=none`, 4 threads,
45-min timeout per case-tool, image digest and MindGlide weight checksum verified on the VM before
any work. The probability maps that WMH-SynthSeg and SAMSEG also return are stored but **not** used
by any endpoint (each tool's own hard label is its unreviewed output, as in paper F).

## 4. Definitions (copied from paper A, `research/paper_a/v03_candidates.py` and `v03c_controls.py`)

- **Lesion (= false lesion here)**: an **18-connected** component (`scipy.ndimage.generate_binary_structure(3, 2)`)
  of the arm's binary mask with physical volume **≥ 3 mm³** (voxel count × voxel volume ≥ 3 − 1e-9).
  This equals paper A's candidate rule and the app's RC-030 convention (`backend/app/services/lesion_metrics.py`:
  18-connectivity, `MIN_LESION_VOLUME_MM3 = 3.0`). For the probability arms the mask is `p ≥ 0.5`
  (paper A, `THRESHOLD = 0.5`, `>=`); the number of LST-AI voxels exactly equal to 0.5 is reported
  (if > 0, the `> 0.5` variant is reported as a sensitivity).
- Every lesion on a control is false. Per control i and arm t: **R_i,t = 1{≥ 1 false lesion}**,
  **F_i,t = number of false lesions**, **V_i,t = total false-lesion volume** (mm³ of the template grid).
- **App DIS rule** (paper A S3 code path, `AppDIS` in `research/paper_a/v03c_controls.py`, reused
  unchanged): the arm's lesion set (all its false lesions) is passed as a binary mask through the
  app's own, read-only imported functions `ms_region_classifier.generate_zone_map_atlas` (MSMask
  MNI152 atlas, applied without registration exactly as the app does; the app's `looks_mni` check
  passes on this grid) → `classify_from_zone_mask` (MAGNIMS contact rule, priority infratentorial >
  periventricular > juxtacortical > deep WM) → `lesion_analysis_service.compute_dis_criteria`.
  **D_i,t = `dis_met_brain`**: qualifying lesions (≥ 3 mm³) in ≥ 2 of periventricular,
  juxtacortical, infratentorial. Spinal cord and optic nerve are not supplied (`None`); dissemination
  in time is not assessed. App files as of this commit (blob hashes identical on paper-a-v0.3,
  paper-f-tool-benchmark and main d5d4726): `ms_region_classifier.py` e0776a87…,
  `lesion_analysis_service.py` 52840d45…, `lesion_metrics.py` ab8c7dc4…, atlas
  `backend/data/msmask/sub-mni152_space-mni_msmask.nii.gz` fb768b4f…; their SHA-256 are written into
  the results.
- **Region of a false lesion**: the region `classify_from_zone_mask` assigns (PV / JC / IT / DWM);
  a lesion touching no atlas zone is DWM by the app's fallback and is also counted as "outside atlas
  coverage".

## 5. Primary endpoints and comparisons

For each of the six arms (on the controls with an output for that arm, section 9):
- **(a) false-alarm scans**: x_a = Σ_i R_i,t out of n_t; rate with the **exact two-sided 95 %
  Clopper–Pearson interval** (and the one-sided 95 % upper bound when x = 0).
- **(b) DIS on unreviewed output**: x_b = Σ_i D_i,t out of n_t; same interval.

**Paired comparisons with the reference.** For each of the five other arms (FLAMeS-f0, LST-AI,
MindGlide, WMH-SynthSeg, SAMSEG) vs FLAMeS-ens, on the controls where both have an output:
**exact two-sided McNemar test** (binomial on the discordant pairs, p = min(1, 2·P[Bin(b + c, ½) ≤
min(b, c)]), p = 1 when b + c = 0). Multiplicity: **Holm across the five arms, separately for
endpoint (a) and endpoint (b)** (two families of 5, α = 0.05 two-sided). A comparison that cannot
be run (arm missing) keeps its place in the family with p = 1 (paper F rule). Holm over all 10 tests
is also reported as the stricter reading. Effect size: difference in proportions (arm − reference)
with a paired bootstrap 95 % percentile interval (10,000 resamples of controls, seed 20261108), and
the discordant counts b (arm only) and c (reference only).

Reading: an arm "flags more (fewer) healthy scans than the FLAMeS ensemble" only if its Holm-adjusted
p < 0.05 in that family; otherwise "no difference shown" (never "equivalent").

## 6. Secondary endpoints (descriptive; CIs, no tests)

- **S1 false lesions per scan**: mean, SD, median, IQR, max and distribution (0 / 1 / 2 / ≥ 3) of
  F_i,t; per-100-scan totals; paired difference in means vs FLAMeS-ens with paired bootstrap 95 % CI.
- **S2 false volume**: V_i,t in mL — median, IQR, mean, max, and share of controls with V > 0.1 mL;
  also relative to the HD-BET brain-mask volume (parts per million), because the template-space brain
  volumes (median 1987 mL) are larger than native ones: absolute volumes are template-space values.
- **S3 MAGNIMS region of each false lesion**: counts and shares PV / JC / IT / DWM (+ outside atlas
  coverage) per arm; number of controls with ≥ 1 false lesion in each region; number with ≥ 1 false
  lesion in any DIS region (PV, JC or IT).
- **S4 size**: false lesions by volume bin 3–14.137 mm³ (below the 3-mm-diameter sphere),
  14.137–50, 50–200, 200–1000, ≥ 1000 mm³; per arm, counts and per-scan means.
- **S5 lesion-definition sensitivity**: (a) and (b) with the paper F lesion rule instead
  (26-connected, ≥ 14.137 mm³; for (b) only those lesions are passed to the app).
- **S6 QC sensitivity**: (a) and (b) without sub-075 (paper A QC flag: HD-BET mask 2829 mL, likely
  extra-cerebral tissue).
- **S7 distance to the brain-mask edge**: per false lesion, minimum Euclidean distance (mm) to the
  HD-BET mask boundary; share within 3 mm (skull-strip edge artefacts).
- **S8 missing-output sensitivity** (only if an arm has failures): failures counted as "false alarm
  and DIS met" (worst case) and as "nothing found" (paper F intention-to-segment).
- **S9 runtime and peak memory** per tool (from the manifests).
- **E1 (exploratory) cross-arm agreement**: for each pair of the five distinct tools (FLAMeS-ens,
  LST-AI, MindGlide, WMH-SynthSeg, SAMSEG), share of one tool's false lesions overlapping (≥ 1 voxel)
  a false lesion of the other; false lesions marked by ≥ 3 of the 5 ("consensus" findings — these may
  be real incidental white-matter hyperintensities of healthy adults, see section 10).

## 7. Reproduction and independent checks (gates before any write-up)

- **G1 reproduction of paper A**: FLAMeS-ens and FLAMeS-f0 must reproduce the paper A record
  `docs/research/records/2026-10-24_paper_a_v03c_controls.json` exactly: controls with ≥ 1 candidate
  85 / 93, candidates 263 / 306, `dis_met_brain` 19 / 22, raw-ensemble regions PV 165, JC 33, IT 4,
  DWM 61. Any mismatch stops the write-up and is logged in section 12.
- **G2 independent count check**: lesion counts and volumes per control and arm recomputed by a
  separately written script that shares no analysis code with the main evaluation (own NIfTI
  decoding, own breadth-first search over the 18 neighbours, own volume filter, own fold averaging)
  must equal the main counts exactly.
- **G3 structural check of every new output** (`evaluate_controls.py check`): FLAMeS grid, binary
  uint8, lesion label found as recorded, SHA-256 equal to the manifest record.

## 8. Compute plan and budget (cap **10 USD** for this arm)

Cloud project `mstool-research` only, bucket `gs://mstool-research-data`, list prices, self-deleting
standard VMs (`--max-run-duration`, `--instance-termination-action=DELETE`, in-VM wall-clock guard
and exit trap), cost ledger exactly as paper F (`toolbench/cost/<run>.txt`,
`toolbench/manifests/<run>.json`, `runs/<run>/{plan,vm,runinfo}.json`). Same machine types and image
digests as paper F: WMH-SynthSeg on **n2d-highmem-4** (needs ~32 GB), SAMSEG on **n2d-standard-4**
and **n2-standard-4**; MindGlide runs after WMH-SynthSeg on the n2d-highmem-4 VM (same N2D processor
family as paper F's n2d-standard-4, more RAM only; the region's 250 GB SSD and 4-address quotas
allow three VMs). Boot disks 80–90 GB (paper F's SAMSEG VMs used 80 GB; the FreeSurfer job used 58 GB).

**Estimate from the paper F cost and manifest files** (`toolbench/cost/`, `toolbench/manifests/`):
measured on 1-mm MNI scans (182 × 218 × 182) WMH-SynthSeg 213 s per scan (n2d-highmem-4, 114
MSLesSeg scans), MindGlide 78–85 s, SAMSEG 556 s (one isotropic scan), image setup ≈ 0.15–0.2 h per
VM; scaled × 1.20 for the larger control grid (197 × 233 × 189). Rates from the same cost files:
n2d-highmem-4 0.2389–0.2485 USD/h, n2d-standard-4 0.1799, n2-standard-4 0.2052 (80 GB disks).

| Run | Machine | Work | Expected h | Expected USD |
|---|---|---|---|---|
| Pilot | 1 × n2d-highmem-4 | 2 controls (sub-001, sub-021) × 3 tools | 0.8 | 0.19 |
| VM A | n2d-highmem-4 | WMH-SynthSeg then MindGlide, 98 controls | 9.8 | 2.35 |
| VM B | n2d-standard-4 | SAMSEG, 49 controls | 9.2 | 1.66 |
| VM C | n2-standard-4 | SAMSEG, 49 controls | 9.2 | 1.89 |
| **Total** | | | **29** | **≈ 6.1** (high, × 1.5 per scan: ≈ 9.2) |

**Budget rule (runtime only, never accuracy).** After the pilot, with m_t = pilot mean seconds per
control for tool t: projected = pilot actual + Σ_VM rate × (0.25 h + Σ_t scans × m_t × 1.25 / 3600).
- projected ≤ 10 USD → **tier A**: every tool on all 100 controls;
- else **tier B**: SAMSEG on the 50 odd-numbered controls only (sub-001, sub-003, …, sub-099), the
  other tools on all 100; SAMSEG comparisons then use those 50;
- else SAMSEG is **not run** (reported as "not run for budget", never imputed).
Guards: each VM's `max-hours` is set so that, even if every VM ran to its guard, total spend stays ≤
10 USD. Re-runs (section 9) are allowed only inside the cap.

## 9. Missing data, failures, exclusions

- A control whose FLAIR SHA-256 differs from the FLAMeS input is excluded for that tool (expected: none).
- Tool failure or timeout: **one** re-run with the same settings (VM loss, guard stop); a WMH-SynthSeg
  out-of-memory stop is re-run with `--crop` (paper F's pre-stated fallback) and flagged. A control still
  without output is **missing** for that arm: the primary analysis is complete-case (n_t < 100, paired
  comparisons on controls where both arms exist); S8 gives worst/best case. An arm with > 5 missing
  controls is labelled "incomplete" in every table.
- The two pilot controls stay in the analysis. No outlier removal.

## 10. Known before this registration (disclosure) and caveats stated a priori

1. **FLAMeS arms are not blind**: paper A (record above) already reported FLAMeS-ens and fold-0
   counts and DIS on these 100 controls (85/100 and 93/100 with ≥ 1 candidate; `dis_met_brain` 19/100
   and 22/100). Here they are recomputed (gate G1) and used as the reference.
2. Paper F results on the five patient cohorts (on 1-mm scans MindGlide and LST-AI produced more false
   lesions per scan than the FLAMeS ensemble; on thick slices WMH-SynthSeg and SAMSEG produced fewer).
3. LST-AI control maps exist since the `lstai-ctl` run (paper A addendum E1, deferred and never run).
   Its processing manifest stores two QC fields per map (maximum probability and number of voxels
   > 0.5). While reading the manifest's structure for this registration, the analyst saw these fields
   for **one** control (sub-001: ensemble maximum 0.575, 7 voxels > 0.5) and for no other. No LST-AI
   control component, count or DIS status has been computed by anyone.
4. No MindGlide, WMH-SynthSeg or SAMSEG output exists for any control (bucket listing 2026-11-08).
5. The pilot's job log prints the number of lesion voxels per case-tool for the two pilot controls;
   this is the only new-tool outcome seen before the full run, and it can change no rule here except
   to fix a technical error (wrong label, grid or orientation), which would be logged in section 12.

Caveats: one site and one scanner population; images template-normalised and HD-BET-stripped (not
the app's own SynthStrip + in-browser ONNX fold-0 pipeline: FLAMeS-f0 is the shipped network, not the
shipped pipeline); the atlas is applied without registration, which on template-normalised images is
the app's most favourable case; "healthy" means recruited healthy volunteers without an expert reading
of these scans, so some "false" lesions may be real incidental white-matter hyperintensities (WMH-SynthSeg
segments WMH, not MS lesions specifically); MindGlide gets skull-stripped input (paper F 7.6 found raw
and stripped input equivalent for MindGlide, so no raw arm is added); non-commercial licence — no number
from this arm may appear in a commercial product or its labelling before the licence is clarified.

## 11. Execution order, code and what counts as a protocol deviation

Order: (1) this file committed and pushed; (2) driver extension for the `sibbms` cohort, frozen
inputs file and tests (no cloud credentials in the test environment); (3) pilot, structural check
only (G3); (4) budget rule; (5) full runs; (6) `research/paper_1/evaluate_controls.py` committed
before it is run on any new-tool output — it may be run on the existing FLAMeS and LST-AI maps after
step (1), labelled interim; (7) the final evaluation runs once, on all outputs, with the code commit
hash written into the results.

**Protocol deviation** = any of: a change to the analysis set, inputs, tool versions/digests/commands,
thresholds, labels, lesion definition, DIS code path, endpoints, tests, multiplicity or reading rules;
a machine type other than those of section 8; a re-run outside section 9; spending above 10 USD; any
new-tool or LST-AI outcome looked at before the step that allows it; an analysis-code fix made after a
result was seen. Each is logged in section 12 with date, reason and exactly what had been seen;
execution notes that change no rule (e.g. a crash fixed before any number was printed) are logged too.

## 12. Deviations log

*(empty at registration)*
