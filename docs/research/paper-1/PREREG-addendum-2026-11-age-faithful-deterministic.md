# Paper 1 — Addendum 2: deterministic registration, the Dallas age curve from the 20s, and a clinically faithful automated rule

**Prespecified protocol, version 1.0 — 2026-11-18.** Research only, not part of the medical device; no application
code is changed (the app's region and DIS functions are imported read-only, exactly as in the first addendum). Branch
`research/paper-1-healthy-controls` (on top of 3046faf). This file, the frozen sample
(`research/paper_1/mimics/analysis_sets_addendum2.json`) and the code that produces and evaluates the new outputs are
committed and pushed **before any new output exists** (section 2). Later changes go to section 10 with date, reason and
what had been seen; the git history is the audit trail. Where this file is silent, `PREREG-mimics-thickness.md`
(effa3a9, amendment 1 d0fdee6, log up to 3046faf) and `PREREG-healthy-controls.md` apply. The word used for these
GitHub-committed protocols is "prespecified".

> **Resumen en español sencillo.** Tres análisis nuevos, aprobados por el dueño, con el crédito gratuito de Google (tope
> 25 USD). **(1)** El alineamiento de cada cerebro al atlas daba resultados un poco distintos cada vez (14 de 5.696
> decisiones cambiaron entre dos repeticiones). Lo repetimos dos veces en máquinas distintas con un solo hilo de
> cálculo; si las dos copias salen idénticas byte a byte, esa versión pasa a ser la que el artículo informa para los
> grupos de Dallas y de lesiones vasculares. **(2)** 75 adultos de Dallas de 20 a 49 años (25 por década), con las
> mismas seis herramientas, para ver cómo sube con la edad la proporción de personas sin esclerosis múltiple que
> "cumplen" la regla automática, de los 20 a los 80 años. **(3)** Una versión más fiel a la clínica de la regla, en el
> espacio propio de cada persona: lesiones de al menos 3 mm de largo, periventricular = tocando los ventrículos,
> yuxtacortical = tocando la corteza, infratentorial = tronco o cerebelo, con la anatomía segmentada por SynthSeg.
> Medimos cuánto separa la esclerosis múltiple de los grupos sin ella (cociente de verosimilitud positivo). Todo queda
> escrito aquí antes de ver un solo resultado nuevo.

## 1. Questions

- **Q1 (reproducibility).** Can the affine MNI normalisation of the first addendum (section 4.1) be made bit-for-bit
  reproducible, and how much do the reported WMH 2017 and Dallas results move when it is? The deterministic run
  ("run 3") then becomes the reported run for blocks A and B.
- **Q2 (age).** In adults without MS, how does the share of people meeting the app's automated location-only rule
  change from the 20s to the 80s, per tool configuration?
- **Q3 (a clinically faithful rule).** If the automated rule is made closer to how a radiologist applies the location
  criteria — lesions of at least 3 mm in their longest extent, periventricular meaning in contact with the lateral
  ventricles, juxtacortical meaning in contact with the cortex, infratentorial meaning brainstem or cerebellum, all in
  the person's own image space — how often is it met in MS and in the cohorts without MS, and does it separate them
  (positive likelihood ratio)?

**Not claimed:** diagnostic accuracy of any tool or of the app; a radiologist's read (the faithful rule is still
automated); anything about dissemination in time, the spinal cord or the optic nerve; population prevalence (the
Dallas samples are stratified by decade); any product, labelling or marketing use (non-commercial data, section 8).

## 2. Known before this protocol (disclosure)

1. **Run 1** (`mimics-eval-3aa6d9f`, the reported run of the first addendum; `results_run1/`): every table and record,
   including (DIS met, app rule) WMH 2017 experts' masks 167/170, FLAMeS ensemble 164/170, fold 0 165/170, LST-AI
   165/170, MindGlide 169/170, WMH-SynthSeg 91/110, SAMSEG 130/170 (PV ≥ 3: experts 143/170); Dallas 50–89 FLAMeS
   ensemble 96/100 (by decade 22, 24, 25, 25 of 25), fold 0 94, LST-AI 88, MindGlide 99, WMH-SynthSeg 57, SAMSEG 60;
   part D selected FLAMeS ensemble (0.65, 25 mm³) and fold 0 (0.50, 50 mm³), Dallas 86/100 and 84/100 at those points
   (transfer "fails"); family decisions (A-1: WMH-SynthSeg and SAMSEG established; A-2: WMH-SynthSeg, SAMSEG; B-a:
   SAMSEG; B-b: WMH-SynthSeg, SAMSEG; D-1: both). The manuscript analyses built on run 1 (Table 3 of the rule, the
   PV ≥ 3 table, cluster-adjusted MS intervals, LR+ of the app rule, `papers/P1_thick_healthy/work/rule_stats.md`).
2. **Run 2** (`mimics-eval-da93797`, reproduction, `results/`): all 270 transforms differ from run 1's (run 1's were
   not kept; run 2's are in `gs://mstool-research-data/mimics/registration/mimics-eval-da93797/registration/`); brain
   Dice differs by ≤ 0.0008, no GR decision changes; **14 of 5,696 per-person DIS decisions differ** (WMH 2017:
   SAMSEG 3, WMH-SynthSeg 4, MindGlide 1; Dallas: WMH-SynthSeg 3, SAMSEG 2, fold 0 1; none for the FLAMeS ensemble or
   the experts' masks); 18 PV ≥ 3 decisions differ; **the MNI-grid component counts differ in 841 of 1,560
   person-configuration pairs of A and B** (|Δ| = 1: 529, 2: 212, 3: 73, 4: 20, 5: 2, 6: 3, 8: 2; median count 24;
   exact agreement 25–65 % and ICC(A,1) 0.942–0.999 by block and configuration — computed 2026-11-18 while testing the
   comparison code of section 3.4 on runs 1 and 2); no gate and no test decision changes; C1 and C2 are byte-identical. Run 2's `records.json` (with native-grid
   component counts of every unit) exists locally and was used for block C1 only.
3. **New data:** for the 105 Dallas participants aged 21–49 (set "B2" of `analysis_sets.json`), only what the
   2026-11-09 mirror recorded — age, sex, MMSE, protocol names, NIfTI headers, SHA-256. **No HD-BET, no tool, no
   registration and no SynthSeg has been run on any of them.** SynthSeg has not been run on any scan of this project
   (bucket listing 2026-11-18: no `mimics/anat/`). The faithful rule (section 5) has never been computed on any data.
4. Published facts used for design: the SynthSeg documentation (FreeSurfer wiki: robust variant for clinical scans
   with large slice spacing, automated QC, 1-mm output whatever the input; no recommended QC threshold), McDonald 2024
   (Montalban 2025) and MAGNIMS 2016 (Filippi 2016) definitions of the regions and of the 3-mm lesion size.

## 3. Analysis 1 — deterministic registration (run 3)

### 3.1 Registration

- **Command:** exactly section 4.1 of the first addendum with one thread:
  `greedy -d 3 -a -dof 12 -m NMI -ia-image-centers -n 100x50x10 -i <atlas T1 brain> <subject FLAIR brain> -o <id>.mat -threads 1`
  (`evaluate_mimics.GREEDY_AFFINE` with t = 1), process environment `ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=1`,
  `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`. **Amendment 1 (section 10): `-seed 20261118` is
  appended.** Version 1.0 said the command used no randomised option; that was wrong — greedy's affine mode jitters its
  sample points at random by default (`-jitter 0.5`) with an unfixed seed, and the pilot pre-check showed one thread
  alone is not reproducible. The jitter is kept (it is part of the registered method) and its seed fixed. The
  initialisation (`-ia-image-centers`) is deterministic; `-search` is not used.
- **Environment pinned for both runs and the evaluation:** greedy venv `picsl_greedy==1.4.0.3 numpy==1.26.4
  SimpleITK==2.5.3 typing_extensions==4.12.2` (earlier runs left the greedy dependencies unpinned); the fixed image
  (atlas T1 × MSMask > 0) is built by the same lines as `evaluate_mimics.cmd_register` in a venv with the evaluation
  pins (numpy 1.26.4, scipy 1.13.1, nibabel 5.3.0); its SHA-256 is recorded by each run.
- **Subjects:** A (170), the Dallas 50–89 sample (100) and the new Dallas 21–49 sample (75; analysis 2) = 345.
- **Two independent runs:** `detreg-a` on VM `mimics-x1` and `detreg-b` on VM `mimics-x3` (separate machines of the
  same family c2d, same code and environment), four single-threaded greedy processes in parallel, one subject each.
  Each transform is uploaded at once to `gs://mstool-research-data/mimics/registration/detreg-{a,b}/registration/<id>.mat`
  with a manifest (SHA-256, seconds, environment). **All transforms are kept.**
- **Pilot pre-check (informative only):** on the pilot VM, `wmh_utrecht_1`, `wmh_singapore_50` and `sub-178` are each
  registered twice in a row, single-threaded, and the two transforms compared byte for byte. If they differ, the full
  runs are not launched; the cause is investigated and logged first.

### 3.2 Gate DG (fixed now)

- **Primary criterion:** for all 345 subjects, the `detreg-a` and `detreg-b` transform files are byte-identical
  (equal SHA-256).
- **Fallback (only if the primary fails):** every matrix entry differs by ≤ 1e-6 (absolute) between the runs **and**
  the evaluation repeated with the `detreg-b` transforms (A, B and B2, same code) gives, for every person and
  configuration, identical DIS, PV ≥ 3, any-DIS-region decisions, identical MNI-grid component counts and identical
  part-D grids, and identical experts' decisions. The paper then states that greedy is reproducible to 1e-6 and in
  every decision, not bitwise.
- If both fail: no run of this addendum replaces run 1 (owner decision; logged). In either pass case the reported
  transforms are `detreg-a`'s.

### 3.3 Re-evaluation = run 3

On the evaluation VM, the `detreg-a` transforms are placed in the registration folder and the **unchanged**
`evaluate_mimics.py` runs `register` (it computes an affine only when no transform exists, so it reuses them and
computes gate GR), `check` (G3), `run` (once) and `check_counts_mimics.py` (G2). `evaluate_mimics.py`'s SHA-256 as
archived for the VM must equal that of run 1 (45de5403…, the git-archive copy; checked 2026-11-18). **Gate DC:** run 3's C1 and C2 rows of `per_unit.csv` and `lesions.csv` must equal
run 1's exactly (they do not pass through the registration); if not, the write-up stops. **Run 3 replaces run 1 as the
reported run for blocks A and B** (every A and B endpoint, the families A-1, A-2, B-a, B-b and D-1, part D's
validation on A and B); C1, C2 and part D's selection are unchanged by construction.

### 3.4 Endpoints (descriptive)

For blocks A and B, each configuration and the experts' masks, run 3 against run 1 and against run 2: the number of
people whose DIS decision differs (also PV ≥ 3 and "≥ 1 lesion in a DIS region"); for the MNI-grid component counts,
the exact-agreement proportion, the largest |difference| and ICC(A,1) (two-way, absolute agreement, single measure;
McGraw and Wong 1996) between the two runs; the largest brain-Dice difference; every family-test decision (within
family and Holm over all 40) that changes. Reported in the supplement next to the run 1/run 2 comparison.

## 4. Analysis 2 — Dallas participants aged 20–49 (age curve)

### 4.1 Sample (frozen in `analysis_sets_addendum2.json`, `B2_sample`)

- **Pool:** the 105 wave-1 participants aged 21–49 with the same 64-slice 2.5-mm 2D FLAIR protocol and the same
  last-run rule as the 50–89 sample (set "B2" of `analysis_sets.json`, mirrored and hashed on 2026-11-09). Decade
  pools: 21–29: 29 (no participant is 20), 30–39: 46, 40–49: 30.
- **Draw:** 25 per decade; within a decade the ids are sorted by participant number and drawn with one
  `numpy.random.RandomState(20261118)` stream, decades in ascending order (`rng.permutation(n)[:25]`), by
  `freeze_addendum2_sets.py` (the rule of the 50–89 sample with the new seed). **Nobody is excluded after outputs
  are seen**; missing outputs follow section 10 of the first addendum (one re-run; > 5 % missing marks a cell
  "incomplete").
- **Pilot participants (stay in the analysis):** the lowest participant number among the drawn 20s (`sub-615`) and
  among the drawn 40s (`sub-587`).

### 4.2 Processing and evaluation

Exactly block B: HD-BET v2.0.1 (TTA on) on the FLAIR and separately on the MPRAGE; the six configurations (FLAMeS
5-fold ensemble and fold 0, LST-AI, MindGlide, WMH-SynthSeg, SAMSEG) with the same images, weights, commands, threads,
timeouts and grid rule, run through the unchanged `mimics_vm.py` (block label "B2"); registration as analysis 1 (the
`detreg-a` transform; gate GR ≥ 0.85, > 10 % failing stops the DIS endpoints of B2 for an owner decision); evaluation
with the unchanged `evaluate_mimics.one_unit` as block B (warp to the atlas, `AppDIS`, part-D grid for the FLAMeS
arms), G3 and G2 as block B.

### 4.3 Endpoints

Per configuration, by decade (20s, 30s, 40s from B2; 50s–80s from run 3's block B), each with an exact 95 % CI:

- **E1 (primary): the app's automated rule** (`dis_met_brain`, lesions ≥ 3 mm³, MNI grid).
- **E2:** PV ≥ 3 variant (as the first addendum).
- **E3:** only lesions ≥ 14.137 mm³ (the volume of a 3-mm sphere; paper F's minimum) counted, recounted from the app's
  per-lesion regions (18-connected on the MNI grid; not the healthy arm's 26-connected variant).
- **E4 (safeguard):** the operating points part D selected — FLAMeS ensemble (t 0.65, m 25 mm³) and fold 0
  (0.50, 50 mm³) — read from each person's part-D grid. If run 3's part-D selection were to differ (it cannot by
  gate DC), run 3's points are used and the change logged.
- (a) ≥ 1 lesion called (native grid), descriptive.

**Trend:** logistic regression of each endpoint on age (years / 10) over the 175 participants of 20–89 (IRLS; Wald
95 % CI and two-sided Wald p); odds ratio per decade. Not estimable (reported as such, p = 1 in the family) when the
outcome is constant, when IRLS does not converge in 100 iterations or when |β| > 10 per decade. Sampling depends on age
only (25 per decade), so the age slope is not biased by it; pooled 20–89 proportions are equal-weight-per-decade, not
population estimates. **Family G-1 (primary, 6 tests):** the age slope of E1 per configuration, Holm within the family
(α 0.05); "the rule is met more often with age" only with Holm p < 0.05 and OR > 1. Everything else is descriptive:
E2–E4 trends; 20–49 pooled vs SibBMS controls and vs 50–89 (Newcombe 95 % CI); lesions per scan by decade.

## 5. Analysis 3 — a clinically faithful automated rule, in each person's own space

### 5.1 Anatomy: SynthSeg 2.0 (robust)

- **Tool:** FreeSurfer 8.2.0 `mri_synthseg --i <FLAIR> --o <labels> --robust --vol <csv> --qc <csv> --threads 4 --cpu`,
  in the same container pinned by digest as WMH-SynthSeg and SAMSEG (`freesurfer/freesurfer@sha256:5648104c…`),
  `--network=none`, 45-min timeout, one re-run on failure.
- **Input:** exactly the FLAIR every tool received — A, B and B2: the HD-BET FLAIR on the native grid; C1: the paper F
  1-mm input (SHA-256 = `flames_inputs.json`); C2: the healthy-arm input (template space, SHA-256 =
  `controls_inputs.json`); and the MNI atlas T1 of the MSMask (`sub-mni152_space-mni_t1.nii.gz`, SHA-256 d4104bbd…)
  for the SibBMS sensitivity analysis. 591 label maps, kept as SynthSeg writes them (its own 1-mm grid, aligned with the
  input) in `gs://mstool-research-data/mimics/anat/synthseg/`, with the QC and volume tables.
- **Why SynthSeg:** contrast- and resolution-agnostic, with a robust variant for clinical scans with thick sections;
  automated QC; it is none of the six configurations being evaluated (so the anatomy is independent of every lesion
  output); same pinned container; the tool runs kept only the binary lesion masks of SAMSEG and WMH-SynthSeg, not their
  whole-brain labels, and re-running SAMSEG would take about four times longer.
- **Labels:** lateral ventricles {4, 5, 43, 44} (including the temporal horns); cerebral cortex {3, 42};
  infratentorial {7, 8, 16, 46, 47} (cerebellar white matter and cortex, brainstem). Resampled to each lesion grid by
  nearest neighbour in world coordinates.
- **Gate GS (before any rule outcome).** (i) *Pilot validation, 11 label maps* (two per data type plus the atlas: `wmh_utrecht_1`,
  `wmh_singapore_50`, Dallas `sub-178`, `sub-408`, `sub-615`, `sub-587`, `mslesseg_P10_T1`, `openms_patient16`,
  SibBMS `sub-001`, `sub-002`, and the atlas): an image with the ventricle, cortex and infratentorial contours on the
  FLAIR at three axial levels, inspected by the researcher. Pass = ventricle labels on the ventricular CSF, cortex on
  the cortical ribbon, infratentorial labels on the brainstem and cerebellum, no gross failure (missing structure,
  labels displaced or swallowing white-matter hyperintensities wholesale). A failure stops the full launch until an
  amendment (logged). The figures show the FLAIR (and hence visible hyperintensities) but no tool output, and no rule
  is computed from them. (ii) *Every scan:* the label map exists and contains ventricle, cortex and brainstem labels
  (structural); the SynthSeg QC scores are read and a scan is **QC-flagged when any score is < 0.65** (threshold chosen
  here; the documentation gives none). Flagged scans **stay in the primary analysis**; a sensitivity analysis excludes
  them; a cohort with > 10 % flagged carries a note in every table.

### 5.2 The rule (code: `research/paper_1/mimics/faithful_rule.py`)

- **Lesion:** an 18-connected component of the binary map on the image's own voxel grid — map ≥ 0.5 for the FLAMeS
  (mean of folds for the ensemble) and LST-AI maps, the tool label for MindGlide, WMH-SynthSeg and SAMSEG, the experts'
  masks (WMH 2017 label 1; C1 the 1-mm `_gt` > 0.5) — kept when its **longest extent F ≥ 3 mm**. F = the maximum
  Euclidean distance in mm (world coordinates from the image affine) between the **centres** of any two of its voxels
  (the 3-D maximum Feret diameter of the voxel-centre set; one voxel has F = 0). **No volume criterion.**
  Sensitivity: F_corner, the same over the 8 corners of every voxel (the full extent of the voxelised lesion, an
  upper bound; with 3-mm sections it admits single voxels).
- **Contact:** the lesion dilated by one voxel with the 3 × 3 × 3 (26-neighbour) element contains ≥ 1 voxel of the
  structure; overlap counts. On thick-section grids one voxel through-plane is 2.5–3 mm: contact is judged at the
  image's own resolution, as on the radiologist's screen.
- **Region (one per lesion; priority IT > PV > JC, the app's convention):** infratentorial when ≥ 50 % of its voxels
  carry an infratentorial label; else periventricular when in contact with a lateral ventricle; else juxtacortical when
  in contact with the cerebral cortex; else other.
- **Rule met:** qualifying lesions in ≥ 2 of PV, JC, IT. **Variant:** PV counts only with ≥ 3 PV lesions.

### 5.3 Where it is applied

| Cohort | Space | Configurations |
|---|---|---|
| MS 1 mm (C1 at 1 mm: MSLesSeg 115, Ljubljana 30) | the delivered MNI 1-mm grid (the only space these data exist in) | experts' masks (145); FLAMeS on the 125 FLAMeS-clean; LST-AI 144; MindGlide, WMH-SynthSeg 145; SAMSEG on its 50-scan subset |
| WMH 2017 (A, 170) | native | experts' masks (label 1), every configuration (WMH-SynthSeg on the 110 test subjects) |
| Dallas 50–89 (B, 100) and 20–49 (B2, 75) | native | every configuration |
| SibBMS controls (C2, 100) | **template space** (they exist only there) | every configuration; primary: SynthSeg on each control's template-space FLAIR; sensitivity: atlas-derived labels (SynthSeg of the MNI atlas T1, nearest neighbour by world coordinates) |

### 5.4 Endpoints (a prespecified sensitivity analysis; descriptive, no new confirmatory family)

- The proportion meeting the faithful rule (and the PV ≥ 3 variant, and with F_corner), per cohort and configuration:
  exact 95 % CI; MS: also the cluster-adjusted exact CI of the manuscript (Clopper–Pearson on n / DEFF,
  DEFF = 1 + (m̄ − 1) ICC, ANOVA ICC within patients).
- **Positive likelihood ratio** per configuration = proportion in MS 1 mm ÷ proportion in each non-MS cohort (WMH 2017,
  Dallas 20–49, Dallas 50–89, Dallas 20–89, SibBMS), 95 % percentile bootstrap that resamples MS patients and non-MS
  participants independently (10,000 replicates, `RandomState(20261118)` per estimate); ∞ when the denominator is 0.
  Experts' masks: against WMH 2017 only (the only non-MS cohort with expert masks).
- The faithful rule against the app's rule on the same scans: discordant counts and exact McNemar p (exploratory,
  unadjusted); qualifying lesions per region; Dallas by decade (20s–80s) with the logistic trend; the QC-excluded
  sensitivity; SibBMS with atlas-derived labels.

## 6. Statistics common to all three analyses

Exact two-sided Clopper–Pearson 95 % intervals (one-sided 95 % upper bound reported when x = 0); exact McNemar
(binomial on discordant pairs); Newcombe method 10 for independent differences; bootstrap seeds 20261118 (new
quantities) — run 3 keeps the first addendum's seed 20261109 for every quantity it re-estimates. Code:
`evaluate_addendum2.py` (new quantities), `evaluate_mimics.py` (run 3, unchanged).

## 7. Compute plan, budget and gates

### 7.1 Where and how

Project `mstool-research` only, isolated gcloud configuration `CLOUDSDK_CONFIG=C:/Users/Nicolas/.gcloud-mstool`,
explicit `--project=mstool-research`, bucket `gs://mstool-research-data`. **Spot VMs only, named `mimics-x*`,
self-deleting** (`--max-run-duration`, termination action DELETE, in-VM wall-clock guard, exit trap), launched by
`research/paper_1/mimics/launch_x.py` through `research/cloud/launch_vm.py` with the code of the **committed HEAD**
(git archive). Every output, transform and record is uploaded as soon as it exists, before the VM can delete itself.
Interruption markers in `mimics/interruptions/`; a pre-empted VM is relaunched with its identical plan only within the
cap (drivers skip finished outputs). Layout (quota 12 vCPUs, 250 GB SSD): `mimics-x1` c2d-standard-4 (HD-BET share,
LST-AI, FLAMeS share, `detreg-a`), `mimics-x2` c2d-highmem-4 (HD-BET share, WMH-SynthSeg, MindGlide, SAMSEG and SynthSeg
shares), `mimics-x3` c2d-standard-4 (HD-BET share, SAMSEG share, SynthSeg incl. all of C1, `detreg-b`); the split never
changes an output. Evaluation: one c2d-standard-8 Spot VM (`mimics-xe-<commit>`), no cloud credentials in the analysis
process.

### 7.2 Pilot

One Spot VM (`mimics-xp`, c2d-highmem-4, 130 GB): HD-BET and all six configurations on the two pilot participants
(4.1); SynthSeg on the 11 pilot scans (5.1) with the overlay figures; the registration pre-check (3.1). Pass: every
output present and structurally valid (G3), pre-check identical, GS(i) passed. Timings and peak memory recorded.

### 7.3 Budget rule — hard cap **25 USD** for this addendum

Spend = list price of every `mimics-x*` VM from the project's audit log (insert to first pre-emption or deletion;
running VMs to now). After the pilot, `launch_x.py full` replaces assumed timings by the pilot's means and computes
the projection (central = measured hours; high = 1.25 × hours + 1.0 h set-up per VM (amendment 1); + spent + 1.5 USD reserved for the
evaluation VM). **The full runs are launched only if the high projection ≤ 25 USD and per-VM guards exist whose worst
case (every VM running to its guard) also stays ≤ 25 USD.** Otherwise: stop and report (owner decision). Before any VM
that imports app code (the evaluation VM), the static import closure is listed and the pins are resolved with
`pip install --dry-run --python-version 3.10 --platform manylinux2014_x86_64 --only-binary=:all:` (done for this
version: section 9).

### 7.4 Stop rules

(1) Spend reaches 25 USD → no new VM. (2) The pilot fails G3 or GS(i), or the registration pre-check differs → no full
launch until the cause is fixed and logged. (3) DG fails both criteria → run 3 is not reported (owner decision).
(4) GR fails for > 10 % of B2 → B2's DIS endpoints stop (owner decision). (5) Any VM outside project mstool-research, or
any command without the isolated configuration, is a stop-and-report incident.

### 7.5 Order of execution

(1) This file, the frozen sample and all code (`freeze_addendum2_sets.py`, `faithful_rule.py` with
`research/paper_1/tests/test_faithful_rule.py`, `x_jobs.py`, `launch_x.py`, `evaluate_addendum2.py`,
`research/cloud/vm_mimics_x.sh`, `research/cloud/vm_mimics_eval_x.sh`) committed and pushed; (2) pilot; (3) budget rule;
(4) full runs; (5) one evaluation (DG, run 3 with GR/G3/G2/G1/DC, B2 with GR/G3/G2, GS(ii), the faithful rule, the
summary) from a committed commit; (6) results downloaded to `research/paper_1/mimics/results_addendum/` (gitignored;
only the aggregate `SUMMARY.md` is committed).

**Protocol deviation** = any change to the sample, inputs, tool versions/digests/commands, registration command or
environment, SynthSeg settings or labels, lesion, contact or region definitions, endpoints, tests, families, reading
rules or gates; a re-run outside the rules; spending above 25 USD; any new output looked at before the step that allows
it; an analysis-code fix after a result was seen. Each is logged in section 10.

## 8. Licences

DLBS CC0 (acknowledgement as in the first addendum); WMH 2017 CC BY-NC 4.0; SibBMS CC BY-NC-SA 3.0; MSLesSeg CC BY 4.0;
Ljubljana CC BY; FreeSurfer licence (SynthSeg, research use). **No per-participant derived data of WMH 2017 or SibBMS
enters the repository** (results folders are gitignored); no number of this addendum may appear in the product, its
labelling or marketing.

## 9. Pre-launch checks done for this version

- `pip install --dry-run --python-version 3.10 --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64
  --only-binary=:all:` resolved (2026-11-18) both the evaluation pins (numpy 1.26.4, scipy 1.13.1, nibabel 5.3.0,
  fastapi 0.115.0, starlette 0.38.6, anyio 4.11.0, pydantic 2.9.0, pydantic-settings 2.5.0, python-dotenv 1.0.1,
  python-json-logger 2.0.7, Pillow 10.4.0, pydicom 2.4.4, nilearn 0.14.1, scikit-image 0.24.0, scikit-learn 1.7.2 —
  the environment that ran runs 1 and 2) and the greedy pins (picsl_greedy 1.4.0.3 has only a manylinux_2_28 cp310
  wheel; numpy 1.26.4, SimpleITK 2.5.3, typing_extensions 4.12.2).
- Static import closure of the evaluation: `evaluate_addendum2.py` → `evaluate_mimics`, `faithful_rule`, `hc_core`
  (stdlib, numpy, nibabel, scipy.ndimage/stats); `evaluate_mimics` → `hc_core`, paper F `metrics`, `thick_slice`,
  `simulate_thick`; `hc_core.AppDIS` → `app.services.lesion_analysis_service`, `app.services.ms_region_classifier`
  (and through them `app.utils`, PIL, pydicom, nilearn, skimage, scikit-learn, pydantic(-settings), fastapi) — the
  closure that ran successfully in run 2; the new modules add no package.

## 10. Deviations log

*(empty at commit 22ba245)*

| Date | Entry | Rule changed? | Seen before? |
|---|---|---|---|
| 2026-11-18 | **Amendment 1 — registration seed (before the full launch; pre-outcome).** The pilot pre-check (`mimics-xp`) registered `wmh_utrecht_1`, `wmh_singapore_50` and `sub-178` twice in a row with one thread: all three pairs differed (matrix entries by up to about 3e-3, translations by up to 0.06 mm). Cause: greedy's default sampling jitter (`-jitter 0.5`, documented in the greedy reference: "the sample locations where metric is calculated are randomly displaced from voxel centers") draws from an unfixed seed; the source (`GreedyParameters.cxx`) offers `-seed`. A local check with the same greedy 1.4.0.3 (Windows build, `sub-178`, one thread) gave byte-identical transforms twice with `-seed 1` and twice with `-jitter 0`. **Change:** the registration command gets `-seed 20261118` (jitter kept, as registered; section 3.1). Stop rule 2 applied: a Linux re-check (`mimics-xt`, c2d-standard-2, same three subjects twice) must give identical transforms before the full launch. Also: the set-up allowance of the budget rule is raised from 0.5 to 1.0 h per VM (the pilot's set-up took 55 min); more conservative, no other effect. | yes (section 3.1; budget computation) | the pilot's six pre-check transforms (registration output, no outcome); the pilot log (timings, memory) |
| 2026-11-18 | **Not a deviation — pilot, Linux re-check and budget rule applied.** `mimics-xt` (c2d-standard-2 Spot, 6512051): the three subjects registered twice with `-seed 20261118`, one thread: **3/3 byte-identical** (fixed image SHA-256 8d8152d4…, the same on both VMs). `mimics-xp` (c2d-highmem-4 Spot, 10,860 s, 0.38 USD, no interruption): HD-BET and the six configurations on `sub-615` and `sub-587`, 0 errors, **G3 18/18 PASS**; SynthSeg on the 11 pilot scans, 0 errors (143–197 s each, peak memory ≤ 9.8 GB); **GS(i) passed**: in the overlay figures of all 11 scans the ventricle labels lie on the ventricular CSF, the cortex labels on the cortical ribbon and the infratentorial labels on the brainstem and cerebellum; white-matter hyperintensities (visible in WMH 2017 and Dallas 50–89 pilot scans) are not labelled cortex or ventricle. Mean seconds: HD-BET (FLAIR + MPRAGE) 1,684, FLAMeS 5 folds 321, LST-AI 138, MindGlide 65, WMH-SynthSeg 277 (peak 31.3 GB), SAMSEG 517, SynthSeg 174, greedy (one thread) 16. Budget rule: projection **11.7 USD central / 14.1 USD high** (spent 0.38), guards 46/62/62 h, worst case 19.8 USD ≤ 25: full runs launched. | no | timings, memory, PASS/FAIL and the 11 anatomy overlays (FLAIR + labels; no tool output, no rule) |
| 2026-11-18 | **Execution note (launcher only, after the full launch; no rule changed).** `launch_x.py`: the evaluation is tied to a record in the bucket (`mimics/plans/xeval.json`: commit, VM name, launches) instead of the current HEAD, so a later commit cannot start a second evaluation; it is relaunched at most once after a failure without results. `tick` relaunches a work VM only when its last instance was pre-empted (audit log); a VM that ended with work missing for another reason is reported for the one re-run the rules allow. Text correction: the pilot SynthSeg set is 11 scans (10 + the atlas), not 13. | no | no |

## References

- Billot B, et al. Robust machine learning segmentation for large-scale analysis of heterogeneous clinical brain MRI
  datasets. Proc Natl Acad Sci USA 2023;120(9):e2216399120 (SynthSeg 2.0).
- McGraw KO, Wong SP. Forming inferences about some intraclass correlation coefficients. Psychol Methods 1996;1:30–46.
- Montalban X, et al. 2024 revisions of the McDonald criteria. Lancet Neurol 2025;24(10):850–865.
- Filippi M, et al. MRI criteria for the diagnosis of multiple sclerosis: MAGNIMS consensus guidelines. Lancet Neurol
  2016;15(3):292–303.
- Park DC, et al. The Dallas Lifespan Brain Study. Sci Data 2025;12:846 (data: doi:10.18112/openneuro.ds004856.v1.3.0).
- Newcombe RG. Interval estimation for the difference between independent proportions. Stat Med 1998;17:873–890.
- Others as `PREREG-mimics-thickness.md`.
