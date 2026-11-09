# Paper 1 — Addendum: an MS mimic with expert masks, a second cohort without MS, a controlled slice-thickness experiment and a pre-specified safeguard

**Pre-registration addendum, version 1.0 — 2026-11-09.** Research only, not part of the medical device; no
app code is changed (the app's region and DIS functions are imported read-only, as in the healthy arm).
Branch `research/paper-1-healthy-controls` (on top of 1ca4268, the healthy arm's final results). This file
is committed and pushed **before any tool output exists for the new data**: no segmentation tool has been
run on WMH 2017, on DLBS, or on any simulated thickness (section 12). Later changes go to section 14 with
date, reason and what had been seen; the git history is the audit trail. The rules of
`PREREG-healthy-controls.md` (commit 1e62f5c) apply wherever this file does not say otherwise.

**Amendment 1 (2026-11-09, section 15, before any VM launch):** Spot VMs, hard cap **45 USD**, DLBS sample of
100, SAMSEG on a 50-scan subset in part C1, C2 at 7 mm only. Where sections 1–13 and section 15 differ,
section 15 rules.

> **Resumen en español sencillo.** Añadimos cuatro piezas al artículo 1, todas con datos públicos y el
> crédito gratuito de Google. **(A)** 170 personas mayores de clínicas de memoria con lesiones de la
> sustancia blanca de origen vascular (el "imitador" más común de la esclerosis múltiple), con lesiones
> dibujadas por expertos: medimos cuántas veces la regla de diseminación en el espacio sale cumplida con
> la salida de cada herramienta **y también con el dibujo perfecto del experto** (eso muestra cuánto falla
> la regla sola). **(B)** Un segundo grupo sin esclerosis múltiple: 275 adultos de 50 a 89 años del estudio
> de Dallas (descarga libre), para repetir el resultado de los 100 cerebros sanos. **(C)** Un experimento
> controlado: a 145 estudios de esclerosis múltiple de 1 mm (y a los 100 sanos) les engrosamos los cortes
> a 3, 5 y 7 mm por cálculo, para medir cuánto empeora cada herramienta según el grosor. **(D)** Una
> protección escrita de antemano: subir el umbral de FLAMeS y el tamaño mínimo de lesión hasta que la
> regla salga cumplida en 5 % o menos de los sanos, y medir cuántas lesiones reales se pierden a cambio.
> Las reglas quedan escritas aquí antes de ver un solo resultado. Tope de gasto: 110 USD.

## 1. Questions

- **Q-A (MS mimic).** In people with white-matter hyperintensities (WMH) of presumed vascular origin and no
  MS diagnosis, how often is the McDonald 2024 brain dissemination-in-space (DIS) rule, as MSTool-AI
  computes it, met (i) on each tool's unreviewed output and (ii) on the **expert** WMH masks fed to the
  same rule? (ii) isolates the rule's own non-specificity from segmentation error.
- **Q-B (second cohort without MS).** Does the healthy-arm headline (FLAMeS 19 %, LST-AI 16 %,
  WMH-SynthSeg 49 %, MindGlide 97 %, SAMSEG 0 % of SibBMS controls meeting DIS) replicate in older adults
  scanned at another site and vendor with native 2.5-mm 2D FLAIR, and how does it depend on age?
- **Q-C (controlled thickness).** When the same 1-mm MS scans (and the same healthy brains) are re-sectioned
  to 3, 5 and 7 mm, how do lesion detection, lesion-wise F1, false lesions and DIS of each tool change,
  and does any tool degrade less than the FLAMeS ensemble?
- **Q-D (safeguard).** If FLAMeS's probability threshold and minimum lesion size are chosen in advance to
  keep DIS on healthy controls at ≤ 5 %, does that hold on cohorts never used for the choice, and what does
  it cost in lesions and DIS calls in MS?

**Not claimed:** diagnostic accuracy of any tool or of the app; anything about dissemination in time, the
spinal cord or optic nerve; MS mimics other than vascular WMH; that "healthy" or "no MS" scans are free of
real lesions (only that no MS diagnosis applies); any clinical or product use (section 2.5).

## 2. Data and analysis sets (fixed)

All analysis sets are frozen in `research/paper_1/mimics/analysis_sets.json` (case ids, input files and
their SHA-256, grids, contamination flags), built from the mirror manifests before any tool was run.
Image data and masks never enter git (public repository; licences): only lists, hashes and header facts.

### 2.1 A — MICCAI 2017 WMH Segmentation Challenge (MS mimic with expert masks)

- **Record:** DataverseNL `doi:10.34894/AECRSD`, "Data of the White Matter Hyperintensity (WMH)
  Segmentation Challenge", version 1.0, released 2022-12-21, depositor H. Kuijf (UMC Utrecht); 1,791 files,
  8.76 GB, **0 restricted files, no access request, no guestbook**; anonymous download through the
  Dataverse API works (checked 2026-11-09).
- **Licence (verdict).** The record's "License/Data Use Agreement" is **CC BY-NC 4.0**, with the dataset
  terms: *"Our Community Norms as well as good scientific practices expect that proper credit is given via
  citation. Please use the data citation shown on the dataset page."* The Terms of Access field reads:
  *"By downloading or otherwise accessing the materials, the downloader represents his/her acceptance of
  the Terms of Use"* (the Terms of Use being the licence). CC BY-NC 4.0 allows sharing and adapting,
  including publishing derived results, for non-commercial purposes with attribution. **Research use and
  publication of derived results are allowed.**
  *Conflict noted and handled:* the bundled `readme.pdf` (Dec 2022) reproduces the 2017 challenge
  "Terms of participation", e.g. *"The data provided may only be used for preparing an entry to be
  submitted to this challenge. The data may not be used for other purposes in scientific studies and may
  not be used to train or develop other algorithms, including but not limited to algorithms used in
  commercial products, without prior participation in the challenge and approval by the organizers"*, and
  *"This agreement needs to be signed and mailed, to activate your registration and get access to the
  data"*. The same text says *"Test data will not be released"*, which the 2022 record itself contradicts,
  so we read it as the historical registration agreement superseded by the licensed public release.
  Handling at no cost: research only; nothing redistributed (no image, mask or tool output leaves the
  bucket); no algorithm is trained or tuned on these data (they are never used in part D's selection);
  no number may appear in the product, its labelling or marketing; a courtesy notice to the dataset
  contact at manuscript submission (it does not gate the analysis); if the data owners object, part A is
  withdrawn from the publication.
- **Required citations:** the data citation shown on the record — *Kuijf, Hugo; Biesbroek, Matthijs; de
  Bresser, Jeroen; Heinen, Rutger; Chen, Christopher; van der Flier, Wiesje; Barkhof; Viergever, Max;
  Biessels, Geert Jan, 2022, "Data of the White Matter Hyperintensity (WMH) Segmentation Challenge",
  https://doi.org/10.34894/AECRSD, DataverseNL, V1* — and the paper the readme asks for: *H. J. Kuijf et
  al., "Standardized Assessment of Automatic Segmentation of White Matter Hyperintensities and Results of
  the WMH Segmentation Challenge", IEEE Trans Med Imaging 38(11):2556–2568, 2019, doi:10.1109/TMI.2019.2905770*.
- **Subjects:** memory-clinic patients (UMC Utrecht, VU Amsterdam) and the Memory Ageing and Cognition
  Centre cohort (NUHS Singapore); age 70.1 ± 9.3 years, 50 % men (whole dataset; per-site ages are not
  published); WMH volume median 11.2 mL (IQR 3.2–23.0), median 57 WMH per subject (Kuijf 2019). MS was not
  an inclusion or exclusion criterion and is not expected in these cohorts (stated as a caveat).
- **Acquisition** (Kuijf 2019 and the readme; **delivered voxel size verified in every NIfTI header** of
  the mirror; slice axis = third voxel axis, orientation LPS):

| Site / scanner | Training / test | FLAIR as acquired | FLAIR as delivered (header) |
|---|---|---|---|
| UMC Utrecht, 3 T Philips Achieva | 20 / 30 | 2D axial, 48 slices, 0.96 × 0.95 × **3.0 mm**, TR/TE/TI 11000/125/2800 ms | 240 × 240 × 48, 0.958 × 0.958 × **3.0 mm** |
| NUHS Singapore, 3 T Siemens TrioTim | 20 / 30 | 2D axial, 1.0 × 1.0 × **3.0 mm**, TR/TE/TI 9000/82/2500 ms | 232 × 256 × 48 (2 of 50: 256 × 232 × 48), 1.0 × 1.0 × **3.0 mm** |
| VU Amsterdam, 3 T GE Signa HDxt | 20 / 30 | 3D sagittal, 0.98 × 0.98 × 1.2 mm, TR/TE/TI 8000/126/2340 ms | resampled by the organisers to axial **3.0 mm**: 132 × 256 × 83 (124–140 × 256 × 83), 1.2 × 0.977 × 3.0 mm |
| VU Amsterdam, 1.5 T GE Signa HDxt | 0 / 10 | 3D sagittal, 1.21 × 1.21 × 1.3 mm, TR/TE/TI 6500/117/1987 ms | axial **3.0 mm**: 128 (124) × 256 × 103, 1.30 × 1.21 × 3.0 mm |
| VU Amsterdam, 3 T Philips Ingenuity PET/MR | 0 / 10 | 3D sagittal, 1.04 × 1.04 × 0.56 mm, TR/TE/TI 4800/279/1650 ms | axial **3.0 mm**: 321 × 240 × 83, 0.56 × 1.04 × 3.0 mm |

  All 170 FLAIRs are delivered with **3.0-mm sections** (2D native at two sites; 3D resampled to 3 mm at the
  three Amsterdam scanners). `orig/T1.nii.gz` (3D T1 aligned by the organisers with elastix) and `wmh.nii.gz`
  are on the FLAIR grid for all 170 (header check). Paper F's bands put 3.0 mm between "iso" (≤ 1.5) and
  "thick" (> 3); here the cohort is called **"3-mm sections"**, matching part C's 3-mm level.
- **Expert reference:** `wmh.nii.gz` (label 1 = WMH, label 2 = other pathology — lacunes, infarcts,
  haemorrhages — dilated 1 voxel in-plane and ignored in the challenge's evaluation), traced by observer O1
  (STRIVE criteria) and peer-reviewed by O2 (11 years of neuroradiology). Released for all 170 subjects.
  The 60 training subjects also have observers O3 and O4 (`additional_annotations/`).
- **Mirror (done 2026-11-09):** `gs://mstool-research-data/wmh2017/` — 941 files, 812,471,599 bytes: for
  each subject `orig/FLAIR`, `orig/T1`, `orig/{FLAIR,T1}_mask` (face masks, Amsterdam only),
  `orig/reg_3DT1_to_FLAIR.txt`, `wmh.nii.gz`; the 120 extra-observer masks; `readme.pdf`. Not mirrored:
  `pre/*` (SPM12 bias-corrected copies) and the native `3DT1` (no arm uses them). **SHA-1 of all 941 files
  equals the DataverseNL record**; SHA-256 manifest and headers: `research/paper_1/mimics/manifests/wmh2017/`
  (digest of the sorted path/SHA-256 list `f9571b89…22d76c`). The folder `Philips_VU .PETMR_01.` is stored
  as `Philips_VU_PETMR_01` (mapping in the manifest). Self-deleting VM `mirror-wmh-dlbs`, e2-standard-2,
  469 s, 0.009 USD.
- **Analysis set A = all 170 subjects** (60 training + 110 test). **WMH-SynthSeg contamination:** its
  published model was trained with the label maps of the 60 training subjects (Laso et al. 2024: GE3T,
  Singapore and Utrecht training subsets, "the model in this experiment is trained with all the datasets
  from the first experiment"), so WMH-SynthSeg's cells on the 60 training subjects are excluded from every
  comparison and reported apart (paper F rule); its primary set is the 110 test subjects. FLAMeS (training
  sets in Dereskewicz et al. 2025, Table 1: RADIEMS, NIH, LCL, MSSEG-1, MSCog, ISBI, PubMRI, NYU — all MS),
  LST-AI (491 TUM scans), MindGlide (MS trial data) and SAMSEG (no lesion training on these data) do not
  include WMH 2017.

### 2.2 B — Dallas Lifespan Brain Study (second cohort without MS)

- **Record:** OpenNeuro `ds004856` v1.3.0 (2025-07-10), doi:10.18112/openneuro.ds004856.v1.3.0;
  `dataset_description.json`: `"License": "CC0"`; README: *"This dataset is licensed under the Creative
  Commons Zero (CC0) v1.0 License"*. No application; anonymous download. **Acknowledgement requested**
  (`HowToAcknowledge`): *Park, D.C. et al. The Dallas Lifespan Brain Study: A Comprehensive Adult Lifespan
  Data Set of Brain and Cognitive Aging. Sci Data 12, 846 (2025). https://doi.org/10.1038/s41597-025-04847-7*.
- **Why this cohort** (search of OpenNeuro and other open repositories, 2026-11-09; table in section 2.4): the
  largest open-access, no-application set of older adults without MS that has FLAIR. Exclusion criteria:
  cohort 1 — *"major psychiatric or neurological disorder … history of central nervous system disease or
  brain injury"*, MMSE < 26; cohort 2 (149, aged 50–89, recruited for the amyloid PET study, hypertension
  or diabetes allowed) — *"a major psychiatric or neurological disorder within the last 3 years … history
  of central nervous systems disease or brain injury"*, MMSE < 26. MS is not named; its absence follows
  from the CNS-disease exclusion. **No radiological read or WMH rating is shared.**
- **Acquisition:** one 3 T Philips Achieva (wave 1). FLAIR protocol `T2W_FLAIR642.5nogapSENSE` (cohort 2:
  same sequence, name prefixed `WIP`), TR/TE/TI 11000/125/2800 ms (sidecars); **header-verified 2D axial,
  512 × 512 × 64, 0.449 × 0.449 × 2.5 mm, no gap** (379 of 383 files 2.4999–2.5001 mm, one 2.5227 mm). T1w
  MPRAGE 256 × 256 × 160, 1 mm isotropic (sagittal). The 84 earlier wave-1 scans with the 24-slice
  `T2W_FLAIRCLEAR` protocol are not used.
- **Analysis set B1 (primary): the 275 wave-1 participants aged ≥ 50 with a 64-slice FLAIR** — age 50–89
  (mean 68.0, SD 10.6; 70 in their 50s, 73 in their 60s, 81 in their 70s, 51 aged 80–89), 168 women,
  107 men; recruitment cohort 1: 126, cohort 2: 149; MMSE 26–30 (median 28; one missing).
  **B2 (lifespan extension, lowest budget priority):** the 105 participants aged 21–49 with the same
  protocol (mean 34.3). Selection used only age and protocol (participants.tsv, sidecars), no image.
  Run rule: where wave 1 has two FLAIR runs (repeat for motion, README), the last run is used (sub-2872,
  sub-3693 in B1; sub-779 in B2); the T1w run likewise.
- **Mirror (done 2026-11-09):** `gs://mstool-research-data/dlbs/` — 1,531 files, 6,233,902,560 bytes: the
  wave-1 FLAIR and MPRAGE (NIfTI + JSON) of the 380 participants of B1 + B2, and the top-level
  `participants.tsv/json`, `README`, `dataset_description.json`, `CHANGES`; SHA-256 manifest and headers in
  `research/paper_1/mimics/manifests/dlbs/` (digest `15c5f3db…db5267`; OpenNeuro publishes no per-file
  checksum, so the SHA-256 at mirroring is the reference).

### 2.3 C — controlled thickness: inputs

- **C1, MS:** the 145 1-mm MS exams of paper F's iso band — MSLesSeg (Figshare 52771814, 115 scans / 75
  patients, CC BY 4.0) and Ljubljana (open_ms_data, 30 / 30, CC BY) — on the MNI 1-mm grid 182 × 218 × 182,
  skull-stripped as distributed. Inputs: the exact FLAIR files the FLAMeS maps were computed from
  (`research/paper_f/flames_inputs.json`, SHA-256 re-checked on every VM), stored in
  `gs://mstool-research-data/inputs/mslesseg_52771814.zip` and `inputs/open_ms_data_MNI.tar.gz`; expert masks
  `flames-ensemble/cohort/{case}_gt.nii.gz` (paper F at 1d3be48). LST-AI also receives each scan's 1-mm T1,
  unchanged at every thickness (as in paper F); `mslesseg_P49_T2` has a blank T1 and has no LST-AI cell.
  **FLAMeS contamination:** Ljubljana patients 1–15 and 21–25 were in FLAMeS training → excluded from every
  FLAMeS cell and every comparison with FLAMeS (125 FLAMeS-clean scans), as in paper F and paper D.
- **"1 mm" is the delivered grid, not always the acquisition.** MSLesSeg's own
  `info_dataset/patient_scanners_info/patient_scanners_info_FLAIR.csv` lists native FLAIR slice thickness
  2–2.3 mm (43 scans), 3 mm (52), 4–5 mm (15), unknown (5), resampled to MNI 1 mm; Ljubljana is truly thin
  (3D FLAIR 0.47 × 0.47 × 0.8 mm) — found and documented in the FLAMeS-thick protocol. The simulation adds
  thickness on top of the delivered image (effective thickness ≥ the simulated one); this is analysed by
  native-thickness stratum (section 6.3).
- **C2, healthy:** the 100 SibBMS controls of the healthy arm (`controls/sibbms/sub-XXX_FLAIR.nii.gz`, frozen
  in `research/paper_1/controls_inputs.json`; template grid 197 × 233 × 189, 1 mm; LST-AI T1 unchanged).
- The simulated inputs are written once, by `research/paper_1/mimics/simulate_thick.py`, to
  `gs://mstool-research-data/thicksim/T{3,5,7}/{case}_FLAIR.nii.gz` with a SHA-256 manifest frozen before any
  tool runs on them; every tool VM re-checks them.

### 2.4 Second-cohort search (candidates, verified 2026-11-09 from OpenNeuro file lists, participants.tsv and sidecars)

| Rank | Dataset | People with FLAIR / ≥ 50 y | Scanner; FLAIR | Read or WMH rating | Licence, access | Verdict |
|---|---|---|---|---|---|---|
| 1 | **DLBS** ds004856 v1.3.0 | 464 wave 1 / 336 (275 with the 64-slice protocol) | Philips Achieva 3 T; 2D axial 0.45 × 0.45 × 2.5 mm, no gap | none shared | CC0, anonymous | **chosen (B)** |
| 2 | Neurocognitive Aging (Spreng) ds003592 v1.0.13 | 251 / 109 (older group 60–83) | GE MR750 3 T 1 × 1 × 3 mm and Siemens TimTrio 3 T 0.8 × 0.8 × 3 mm (2D) | none (visible anomalies excluded) | CC0, anonymous | reserve (two vendors) |
| 3 | MPI-Leipzig LEMON ds000221 v1.0.0 | 305 / 78 (5-year age bands) | Siemens Verio 3 T; 2D axial 0.9 × 0.9 × 4 mm (188) or 3D SPACE 1 mm (117) | screened, results not shared | CC0, anonymous | reserve (only one naming MS as exclusion) |
| 4 | Stockholm Sleepy Brain ds000201 v1.0.3 | 83 / 38 (65–75) | GE MR750 3 T; 3D CUBE FLAIR 1.2 mm | none | CC0, anonymous | too small |

Rejected: NIMH Healthy Research Volunteers (ds004215 no longer public; successor ds005752 v2.1.0 has only
27 people ≥ 50 with FLAIR, and one participant was flagged "multiple T2 hyper-intensities consistent with
MS"); ds005123 (39 ≥ 50, exclusion criteria undocumented); epilepsy, stroke, MS and paediatric sets;
PREVENT-AD, ADNI, OASIS-3, UK Biobank, HCP-Aging, Cam-CAN (application or data-use agreement needed);
IXI (no FLAIR).

### 2.5 Licences together

WMH 2017 CC BY-NC 4.0; DLBS CC0; MSLesSeg CC BY 4.0; Ljubljana CC BY; SibBMS CC BY-NC-SA 3.0; FLAMeS
weights (Zenodo 17955359) and the other tools as recorded in paper F section 3. All permit this research paper; **no number of
this addendum may appear in the product, its labelling or marketing** (non-commercial clauses, and the tools'
own research-only terms).

## 3. Arms, inputs and grids

The six arms are exactly those of `PREREG-healthy-controls.md` section 3 — **FLAMeS-ens** (reference; mean
of folds 0–4 ≥ 0.5), **FLAMeS-f0** (fold 0 ≥ 0.5, the shipped network), **LST-AI** v1.2.0 (ensemble ≥ 0.5,
`--stripped --segment_only --probability_map`), **MindGlide** 1.3.0 (label 18), **WMH-SynthSeg** FreeSurfer
8.2.0 (label 77, no `--crop`), **SAMSEG** FreeSurfer 8.2.0 (`--lesion …`, label 99) — same images pinned by
digest, same weights and checksums, same commands, `--network=none`, 4 threads, 45-min timeout per
case-tool, outputs put on the FLAIR grid by the paper F rule (`job_common.to_grid_footprint`; identity when
the grids match). Per cohort:

| Cohort | FLAIR given to every tool (= "FLAMeS grid") | Skull stripping | LST-AI T1 |
|---|---|---|---|
| A WMH 2017 | `orig/FLAIR.nii.gz` × HD-BET mask (as delivered: face removed, no bias correction) | HD-BET v2.0.1 commit 678e44d, CPU, TTA on, on `orig/FLAIR` (as MS3SEG, Muslim, SibBMS) | `orig/T1.nii.gz` (on the FLAIR grid) × the same mask — exactly the controls' recipe |
| B DLBS | FLAIR (last run) × HD-BET mask, native 2.5-mm grid | HD-BET as above, on the FLAIR | MPRAGE × its own HD-BET mask, native grid (LST-AI registers both images itself) |
| C1 MS 1 mm | the paper F input (T = 1) or its simulation (T = 3, 5, 7), MNI 1 mm | as distributed | the 1-mm T1, unchanged |
| C2 SibBMS | the healthy-arm input (T = 1) or its simulation, template 1 mm | HD-BET (healthy arm) | the healthy-arm T1, unchanged |

Outputs that already exist and are **reused, not re-run** (SHA-256 re-checked against their manifests,
gate G0): T = 1 of C1 — FLAMeS folds 0–4 (`flames-ensemble/cohort/`), LST-AI (`lstai/cohort/`), MindGlide and
WMH-SynthSeg (paper F `toolbench/`); T = 1 of C2 — all six arms (healthy arm). **New at T = 1:** SAMSEG on the
145 C1 scans (paper F ran SAMSEG on thick scans only).

## 4. Definitions (identical to the healthy arm and paper F)

- **Lesion, counting and DIS (paper A rule, the app's RC-030 convention):** 18-connected component of the
  arm's binary mask with volume ≥ 3 mm³; DIS = `dis_met_brain` of the app's `compute_dis_criteria` after
  `generate_zone_map_atlas` (MSMask) → `classify_from_zone_mask` (priority IT > PV > JC > DWM), through
  `hc_core.AppDIS`, unchanged: qualifying lesions in ≥ 2 of PV, JC, IT; cord and optic nerve not supplied;
  dissemination in time not assessed. App file blob hashes as in the healthy arm (e0776a87…, 52840d45…,
  ab8c7dc4…, atlas fb768b4f…), their SHA-256 written into the results.
- **Lesion-wise accuracy (paper F rule, `research/paper_f/metrics.py`):** 26-connected components ≥ 14.137
  mm³, a match = ≥ 1 voxel overlap; lesion precision, recall, F1 (F1 = 0 when nothing is predicted); false
  lesions per scan = predicted components touching no reference lesion; voxel Dice.
- **Expert-mask DIS (D_E):** the expert lesion mask (A: `wmh.nii.gz` label 1; C1: the 1-mm `_gt` mask) passed
  through the same lesion rule and `AppDIS` — **the DIS the app's own code reports from a perfect
  segmentation** (paper D's reference decision "E, v3, APP, G0"; not a radiologist's DIS read).
- **A, label 2 ("other pathology"):** predicted voxels inside label 2 are removed before the accuracy metrics
  (the challenge ignores label 2). For DIS the arms' masks are used as they are; D_E uses label 1 only
  (primary) and labels 1 ∪ 2 (sensitivity: "every FLAIR-hyperintense lesion the expert outlined").
- **PV ≥ 3 variant (exploratory, all parts):** DIS recounted from the app's own per-lesion regions with the
  periventricular region satisfied only by ≥ 3 PV lesions (MAGNIMS 2016; the McDonald 2017 panel's
  suggestion to seek more periventricular lesions in older people or those with vascular risk factors). No app
  code is changed; the count uses `classify_from_zone_mask`'s labels.

### 4.1 MNI normalisation for the native-space cohorts A and B (needed for DIS only)

The app refuses atlas regions on grids that are not MNI-like (`looks_mni`, RC-032: anisotropic voxels fail
condition 1), so on native WMH 2017 or DLBS scans it would report no DIS at all. To evaluate **the app's
rule on these scans the way the app requires them — registered to MNI —** every native mask is normalised:

1. **Registration:** affine, 12 degrees of freedom, greedy (picsl_greedy 1.4.0.3, as paper D):
   `greedy -d 3 -a -dof 12 -m NMI -ia-image-centers -n 100x50x10 -i <atlas T1 brain> <subject FLAIR brain> -o aff.mat`.
   Fixed image: the MSMask atlas T1 `sub-mni152_space-mni_t1.nii.gz` (LST-AI v1.1.0 `lst_data.zip`,
   SHA-256 `d4104bbd…476b`, ICBM 2009c 1 mm, 193 × 229 × 193) multiplied by MSMask > 0; moving image: the
   HD-BET-stripped FLAIR that every tool received.
2. **Warping each mask** (each arm's binary lesion mask on the FLAIR grid, and the expert masks):
   `greedy -d 3 -rf <atlas T1> -ri LINEAR -rm <mask> <out> -r aff.mat`, then **≥ 0.5** (the paper F majority
   rule) → binary mask on the 193 × 229 × 193 MNI grid (which passes `looks_mni`), then section 4 lesion
   rule and `AppDIS` exactly as for the template-space controls.
3. **Registration gate GR (computed before any outcome):** Dice between the warped HD-BET brain mask and the
   atlas brain (MSMask > 0) ≥ **0.85**. A scan below is excluded from the DIS endpoints of every arm (kept for
   the native-space accuracy endpoints) and listed; if > 10 % of a cohort fails, its DIS analysis stops for an
   owner decision (section 9.5). Sensitivity: all scans regardless of GR.

Lesion-wise accuracy (A) is computed in native space (no registration); counts for DIS are on the MNI grid,
like every DIS of paper 1.

## 5. Part C — the simulation and the reference

- **Operator:** `research/paper_1/mimics/thick_slice.py`, a verbatim copy of the unit-tested FLAMeS-thick
  simulator (research/flames-thick @ b6342ec, git blob `34ba9ec5…`), called by `simulate_thick.py` with fixed
  parameters: axial axis (voxel axis 2 = I-S, checked), **T ∈ {3, 5, 7} mm, no gap, box slice profile (slab
  average), phase 0 (first slice centred on voxel 0), linear interpolation back to the 1-mm grid**; voxels
  that are 0 in the 1-mm input stay 0. Tests: `research/paper_1/tests/test_simulate_thick.py` (10 pass).
- **Reference = the 1-mm expert mask at every thickness (chosen).** The patient's true lesions do not change
  with the acquisition; the question is how much of the *true* lesion burden, and of the true DIS status, a
  tool recovers from thicker sections. Degrading the mask with the image would redefine the truth per
  thickness and hide exactly the loss we want to measure (small lesions that thick sections dilute). The
  degraded view is kept as a secondary decomposition: **"resolvable" reference lesions** = those with ≥ 1
  voxel ≥ 0.5 after the same operator is applied to the binary expert mask; recall restricted to them
  separates "physically not resolvable at T" from "resolvable but missed".
- Thicknesses are within-scan conditions: every scan contributes at T = 1, 3, 5, 7.

## 6. Endpoints and comparisons

Common inference: exact two-sided 95 % Clopper–Pearson intervals for proportions (one-sided 95 % upper
bound when x = 0); **exact two-sided McNemar** for paired binary outcomes (binomial on discordant pairs,
p = 1 when there are none); paired differences of proportions with a 95 % percentile bootstrap (10,000
resamples, seed **20261109**); continuous per-scan metrics with the **patient-cluster bootstrap stratified by
cohort** of paper F (`metrics.bootstrap_distribution`, 10,000, seed 20261109), **scan-weighted** (primary for
C, because MSLesSeg and the 10 FLAMeS-clean Ljubljana scans differ in what "1 mm" means; cohort-weighted as
sensitivity), two-sided bootstrap p. **Holm within each registered family** (α = 0.05 two-sided); a test that
cannot run keeps its place with p = 1 (paper F rule); Holm over all 40 primary tests of this addendum is also
reported as the strictest reading. Reading as in the healthy arm: "more / fewer / degrades less" only with
Holm p < 0.05 in the family, otherwise "no difference shown" (never "equivalent").

### 6.1 Part A (WMH 2017; n = 170, WMH-SynthSeg n = 110; DIS endpoints on the scans passing GR)

- **A0 (headline estimate): D_E**, the share of subjects whose expert WMH mask meets the app's DIS rule, with
  exact CI; also D_E by site and for O3 and O4 on the 60 training subjects (agreement of the three experts'
  DIS, Fleiss κ, descriptive). Reading pre-specified: if the exact 95 % lower bound of D_E exceeds 5 %, we
  state that the rule, fed expert-quality segmentation, is met in at least 5 % of these people without MS.
- **Family A-1 (primary, 6 tests): each arm's DIS vs D_E** on the same subjects (exact McNemar; b = arm
  only, c = expert only); "the tool calls DIS more (less) often than its expert segmentation would".
- **Family A-2 (5 tests): each other arm vs FLAMeS-ens** on DIS (exact McNemar), as the healthy arm.
- Secondary (descriptive, CIs): lesion-wise F1, recall, precision, false lesions per scan and Dice vs label 1
  (native space, label-2 voxels removed); total volume tool vs expert (median ratio, Spearman); regions
  PV/JC/IT/DWM of tool and expert lesions; "≥ 1 lesion in a DIS region"; D_E with labels 1 ∪ 2; everything by
  site and training/test; WMH-SynthSeg's 60 training subjects apart; PV ≥ 3 variant for every arm and D_E.

### 6.2 Part B (DLBS; B1 n = 275 primary, B2 n = 105 extension)

- Per arm, as the healthy arm: **(a)** ≥ 1 lesion called (here not necessarily false — older adults have real
  WMH), **(b) DIS met on unreviewed output**, and ≥ 1 lesion in a DIS region; exact CIs.
- **Families B-a and B-b (5 tests each): each other arm vs FLAMeS-ens**, exact McNemar, Holm per endpoint.
- Secondary: by decade (50s, 60s, 70s, 80s) and recruitment cohort (1 vs 2); logistic regression of DIS on
  age per decade per arm (exploratory, Wald CI); the healthy arm's S1–S7 analogues (lesions per scan, volume,
  regions, size bins, paper F lesion rule, distance to the mask edge); PV ≥ 3 variant; cross-tool consensus
  (E1). **Replication contrast** (descriptive): B1 rate minus SibBMS rate per arm with Newcombe 95 % CI
  (unpaired; different people, scanner, grid). B2, if run: the same endpoints; DIS by age over 21–89.

### 6.3 Part C (controlled thickness)

- **Per arm × T ∈ {1, 3, 5, 7} (C1):** lesion-wise F1, recall (detection), precision, false lesions per scan,
  Dice, "resolvable" recall (section 5); DIS agreement with D_E (share agreeing), **false DIS** (arm DIS among
  D_E-negative scans) and **missed DIS** (no arm DIS among D_E-positive scans). Analysis sets: FLAMeS arms
  and every comparison with FLAMeS on the 125 FLAMeS-clean scans; other arms on 145 (LST-AI 144).
- **Family C-1 (primary, 6 tests): Δ lesion-wise F1 (7 mm − 1 mm) per arm** (bootstrap as above).
- **Family C-2 (5 tests): differential degradation** — [ΔF1(7 − 1)]_tool − [ΔF1(7 − 1)]_FLAMeS-ens, paired on
  the FLAMeS-clean scans: "the tool degrades less (more) than the FLAMeS ensemble" (paper F's question b,
  now on identical anatomy).
- **Family C-3 (6 tests, C2 healthy): DIS at 7 mm vs 1 mm per arm** on the 100 SibBMS controls, exact McNemar.
- Descriptive dose-response: every metric at 1/3/5/7 mm with CIs; per-scan least-squares slope of F1 on T;
  3 and 5 mm vs 1 mm; strata of native MSLesSeg thickness (≤ 2.3 mm incl. Ljubljana, 3 mm, 4–5 mm, unknown;
  expected: little change at T = 3 where the native thickness is already 3 mm); size bins of reference
  lesions; C2 false lesions and DIS at 3/5/7 mm (if run, section 9.4). Sensitivity: cohort-weighted
  bootstrap; Ljubljana's 20 FLAMeS-training scans added (flagged).

### 6.4 Part D (pre-specified safeguard; no new tool runs)

- **Operating points:** FLAMeS-ens (primary) and FLAMeS-f0 (the shipped network; secondary) with probability
  threshold t ∈ {0.50, 0.55, …, 0.95} and minimum lesion volume m ∈ {3, 14.137, 25, 50, 100} mm³ (50 points;
  lesion = 18-connected component of p ≥ t with volume ≥ m; only those lesions are passed to `AppDIS`). The
  default (0.50, 3) is the healthy arm's rule.
- **Selection data (and only these):** the 100 SibBMS controls (false DIS) and the 125 FLAMeS-clean 1-mm MS
  scans (DIS sensitivity = share of D_E-positive scans whose arm DIS is met; lesion-wise recall).
- **Selection rule:** feasible = points with SibBMS DIS ≤ 5/100; choose the feasible point with the highest MS
  DIS sensitivity; ties → higher MS lesion-wise recall → lower t → lower m. Strict variant: feasible = exact
  one-sided 95 % upper bound ≤ 5 % (≤ 1/100). If no point is feasible, that is the result.
- **Validation (never used for selection):** DLBS B1 (and B2 if run), WMH 2017 (DIS and **excess DIS** =
  arm DIS with D_E negative), C1 at 3/5/7 mm (sensitivity cost under thickness), C2 at 3/5/7 mm (false DIS
  under thickness), and paper F's thick cohorts (lesion recall only; native space, no DIS).
- **Family D-1 (2 tests):** false DIS on DLBS B1 at the selected point vs the default (0.50, 3), exact McNemar,
  for FLAMeS-ens and FLAMeS-f0, Holm. **Transfer reading:** "holds" if on B1 the point estimate is ≤ 5 % and the
  exact one-sided 95 % upper bound ≤ 10 %; "fails" if the exact lower bound exceeds 5 %; otherwise
  "inconclusive". **Cost:** Δ MS DIS sensitivity and Δ lesion-wise recall vs the default (paired bootstrap)
  on the selection MS scans (labelled apparent) and on C1 at 3/5/7 mm. The full 50-point surface (false DIS
  on each cohort vs MS sensitivity) is reported. LST-AI (thresholds only) is exploratory.

### 6.5 Precision (no power claim)

Exact 95 % CI half-widths: n = 170 → about ±7.5 points near 50 % and ±6 near 20 %; n = 275 → ±5.9 and ±4.7; a
5 % rate on 275 has CI ≈ 2.8–8.4 %. C1: with a per-scan SD of 0.10 for ΔF1, the 95 % CI half-width is
≈ ±0.02 F1 on 125 scans.

## 7. Multiplicity summary

| Family | Tests | Question |
|---|---|---|
| A-1 | 6 | arm DIS vs expert-mask DIS (WMH 2017) |
| A-2 | 5 | arm vs FLAMeS-ens, DIS (WMH 2017) |
| B-a, B-b | 5 + 5 | arm vs FLAMeS-ens, ≥ 1 lesion and DIS (DLBS B1) |
| C-1 | 6 | ΔF1 7 mm vs 1 mm per arm (MS) |
| C-2 | 5 | differential degradation vs FLAMeS-ens (MS) |
| C-3 | 6 | DIS 7 mm vs 1 mm per arm (SibBMS) |
| D-1 | 2 | selected vs default operating point, DLBS false DIS |

Total 40 tests in 8 families; strictest reading: Holm over all 40. Everything else is descriptive or
exploratory and labelled so.

## 8. Gates (before any write-up)

- **G0 data and inputs:** WMH 2017 SHA-1 = record for all 941 files (**passed 2026-11-09**); DLBS SHA-256
  manifest frozen (done); every tool VM re-checks its input SHA-256 against `analysis_sets.json`, the simulated
  inputs' manifest or the paper F / healthy-arm frozen inputs (a mismatch excludes that cell, reported); the
  reused outputs of section 3 match their recorded SHA-256.
- **G1 reproduction:** the new evaluation code must reproduce (i) the healthy arm's final table exactly (all
  six arms: e.g. FLAMeS-ens 85/100 and 19/100, SAMSEG 6/100 and 0/100) from the existing outputs, and (ii) at
  T = 1, paper F's per-scan lesion counts (TP, FP, FN) on the iso band for FLAMeS-ens, LST-AI, MindGlide and
  WMH-SynthSeg, and paper D's reference decisions D_E on its 124 scans. Any mismatch stops the write-up and
  is logged in section 14.
- **G2 independent recount:** a separately written script (own NIfTI decoding, own neighbour search, own
  volume filter, own fold averaging, own slab-average-and-interpolate re-implementation of the simulation on
  5 seeded cases with |difference| ≤ 1e-4 of the intensity range) must equal the main counts and volumes
  exactly for every new case-arm.
- **G3 structural check of every new output:** on the FLAIR grid, binary uint8, lesion label as recorded,
  SHA-256 equal to the run manifest (`evaluate_controls.py check` logic).
- **GR registration** (section 4.1), before any outcome.

## 9. Compute plan, budget and stop rules

### 9.1 Where and how

Project `mstool-research` only, bucket `gs://mstool-research-data`, isolated gcloud configuration, list
prices; self-deleting standard VMs (`--max-run-duration`, `--instance-termination-action=DELETE`, in-VM
wall-clock guard, exit trap) through `research/cloud/launch_vm.py`; cost ledger exactly as paper F
(`*/cost/<run>.txt`, manifests, `runs/<run>/{plan,vm,runinfo}.json`). Machine types as the healthy arm:
WMH-SynthSeg on n2d-highmem-4; FLAMeS, HD-BET, LST-AI, MindGlide, SAMSEG on n2d-standard-4 (n2-standard-4
allowed for SAMSEG, as before). The registration (section 4.1) and the final evaluation run on one
n2d-standard-4 VM (not on the owner's computer).

### 9.2 Projection (`research/paper_1/mimics/plan_mimics.py`, ledger medians, list prices of 2026-11-09)

Seconds per scan, 4 vCPU: HD-BET 139, FLAMeS 68.5 per fold (× 5), LST-AI 120, MindGlide 84, WMH-SynthSeg 216,
SAMSEG 552. Rates: n2d-standard-4 + 80 GB 0.17994 USD/h, n2d-highmem-4 + 90 GB 0.24029, n2-standard-4 0.20519
(Spot 0.10084 / 0.13357 / 0.12747). Central = measured seconds; high = × 1.25 + 0.25 h set-up per machine type.

| Block (priority order) | Work | VM-h | CPU-h | USD central – high |
|---|---|---|---|---|
| A WMH 2017 | 170 × (HD-BET + 6 arms) | 68.6 | 275 | 13.1 – 16.3 |
| B1 DLBS ≥ 50 | 275 × (2 HD-BET + 6 arms) | 121.6 | 487 | 23.0 – 28.7 |
| C1 MS thickness | 145 × 3 thicknesses × 6 arms + SAMSEG at 1 mm (145) | 181.0 | 724 | 34.2 – 42.8 |
| C2 SibBMS thickness | 100 × 3 × 6 arms | 109.5 | 438 | 20.9 – 26.1 |
| B2 DLBS < 50 | 105 × (2 HD-BET + 6 arms) | 46.4 | 186 | 8.8 – 11.0 |
| Fixed | 3 pilots 1.5, registration + evaluation VMs 2.0, mirror 0.1 | | | 3.6 |
| **All** | | **527** | **2,109** | **103.6 – 128.5** (Spot: 59.6 – 73.5) |

Storage added: 7.05 GB (≈ 0.14 USD per month).

### 9.3 Pilots (structural only, G3)

One pilot VM per data type, all six arms: A — `training/Utrecht/0` and `test/Amsterdam/GE1T5/150`; B —
`sub-142` and `sub-1800` (lowest participant number of each protocol in B1); C — `mslesseg_P10_T1` and
`openms_patient16` at 3, 5 and 7 mm, and SibBMS `sub-001` at 7 mm. The pilot logs print lesion-voxel counts
(as in the healthy arm); no component, count, region or DIS is computed from pilots before the full runs.
Pilot cases stay in the analysis.

### 9.4 Budget rule (runtime only, never accuracy) — cap **110 USD** for this addendum

After the pilots, with the pilot's mean seconds per step replacing the ledger medians:
projected = spent so far + Σ blocks (high). The largest plan whose projection ≤ 110 USD runs, reducing in
this fixed order until it fits: (1) drop B2; (2) C2 at 7 mm only; (3) Spot provisioning for all blocks
(drivers are resumable per case; a pre-empted VM is relaunched with identical settings; outputs do not
depend on provisioning); if nothing fits, stop (owner decision). With the ledger medians the rule selects
steps (1)–(2): **80.9 – 100.2 USD** (A + B1 + C1 + C2 at 7 mm), ≈ 72 – 90 EUR at 1.1165 USD/EUR, inside the
free credit (≈ 166 EUR left). Guards: each VM's `max-hours` is set so that, even if every VM ran to its guard,
total spend stays ≤ 110 USD. Re-runs (section 10) only inside the cap.

### 9.5 Stop rules

(1) Cumulative ledger spend reaches 110 USD → no new VM; running VMs end under their guards. (2) A pilot fails
G3 twice for a data type → that block stops, owner decision. (3) G0 fails for a cohort → its block is not run.
(4) GR fails for > 10 % of a cohort → its DIS analysis stops (owner decision; another registration is an
amendment). (5) The WMH 2017 data owners object → part A is withdrawn from publication. (6) Any VM outside
project mstool-research, or any command without the isolated configuration, is a stop-and-report incident.

Wall-clock: ≈ 410 VM-hours for the selected plan; with three VMs in parallel (regional quotas: 250 GB SSD,
4 addresses, 8 N2D vCPUs) about 6 days.

## 10. Missing data, failures, exclusions

As the healthy arm section 9: input SHA-256 mismatch → cell excluded; **one** re-run of a failed or
timed-out case-tool with the same settings (a WMH-SynthSeg out-of-memory stop is re-run with `--crop`,
flagged); still missing → missing for that arm (complete-case primary; worst / best case as sensitivity);
> 5 % missing in a cohort-arm → "incomplete" in every table. LST-AI: a case without a usable T1 is missing
for LST-AI only. GR exclusions as section 4.1. No outlier removal. Paper F's contamination rules as in
sections 2.1 and 2.3.

## 11. Execution order and protocol deviations

Order: (1) this file, the analysis sets, the mirror manifests and the simulator committed and pushed;
(2) driver extensions — cohorts `wmh2017`, `dlbs`, `thicksim` in `toolbench_driver.py`,
`flames_ensemble_driver.py`, `lstai_driver.py` and an HD-BET prep step reusing `sibbms_controls_prep.py`'s
code; the simulation job; tests without cloud credentials; (3) pilots, G3 only; (4) budget rule; (5) full
runs; (6) registration job and GR; (7) the evaluation code (`research/paper_1/mimics/evaluate_mimics.py`,
reusing `hc_core`, `evaluate_controls` and paper F `metrics`) committed before it is run on any new output;
(8) one final evaluation with the code commit written into the results; G1, G2.

**Protocol deviation** = any change to analysis sets, inputs, tool versions/digests/commands, thresholds,
labels, lesion definitions, DIS path, registration, simulation parameters, endpoints, tests, families or
reading rules; a machine type not in section 9.1; a re-run outside section 10; spending above 110 USD; any
outcome of the new data looked at before the step that allows it; an analysis-code fix after a result was
seen. Each is logged in section 14 with date, reason and exactly what had been seen.

## 12. Known before this registration (disclosure)

1. The healthy arm's final results (`research/paper_1/results/tables.md`, all six arms) — the motivation of
   this addendum and the selection data of part D (SibBMS false DIS at the default is 19/100 for FLAMeS-ens).
2. Paper F's final results (1d3be48), including every 1-mm output and its accuracy on the 145 C1 scans (e.g.
   FLAMeS-ens MSLesSeg median Dice 0.727, lesion F1 0.744; Ljubljana-clean 0.673 / 0.788) and the thick
   cohorts; FLAMeS-thick's results (fine-tuning with simulated thick slices did not help on real thick data).
3. Paper D's results v1 (5a16052): flip rates of automated DIS on 124 C1 scans across thresholds 0.3–0.7,
   minimum sizes and registrations, and the expert-mask DIS (D_E) of those scans — so part D's patient-side
   numbers for t ≤ 0.7 at m ∈ {3, 14.137} are partly known.
4. Published facts used for design: Kuijf 2019 (dataset description above); Laso 2024 (WMH-SynthSeg training
   data); Dereskewicz 2025 (FLAMeS training data); the DLBS README and paper.
5. Mirror: file sizes, SHA-1/SHA-256 and **NIfTI headers only** (shape, voxel size, orientation, transform
   codes, data type) of every mirrored file; no voxel content was read, no image or mask was viewed, no lesion
   volume or count of WMH 2017 or DLBS was computed. DLBS participants.tsv (age, sex, MMSE) and wave-1 FLAIR
   sidecars (protocol names) were read to define B1 and B2.
6. No tool has been run on WMH 2017, DLBS or any simulated thickness (bucket listing 2026-11-09: no
   `thicksim/`, no tool output under `wmh2017/` or `dlbs/`).

Caveats stated a priori: WMH 2017 subjects are memory-clinic patients with vascular WMH (not a general
population) and MS was not formally excluded; DLBS has no radiological read, so lesions called there may be
real age-related WMH — the endpoint is "DIS met in people without MS", not "false lesions"; MNI normalisation
is affine and its error moves lesions across region borders (paper D quantified this; GR bounds it); the
simulation (box profile, no gap, one phase, linear back-resampling) is one idealised model of 2D acquisition
and is applied on top of MSLesSeg's native 2–5-mm acquisitions; the app's shipped pipeline (SynthStrip +
in-browser fold 0) is not what runs here (FLAMeS-f0 is the shipped network, not the shipped pipeline).

## 13. Files of this registration

`docs/research/paper-1/PREREG-mimics-thickness.md` (this file);
`research/paper_1/mimics/analysis_sets.json`; `research/paper_1/mimics/manifests/{wmh2017,dlbs}/`
(`files.csv`, `headers.csv`, `summary.json`); `research/paper_1/mimics/lists/{wmh2017,dlbs}.tsv` and
`build_mirror_lists.py`; `research/cloud/mirror_public.py`, `research/cloud/vm_mirror_public.sh`
(the mirror job); `research/paper_1/mimics/thick_slice.py` (verbatim), `simulate_thick.py` and
`research/paper_1/tests/test_simulate_thick.py`; `research/paper_1/mimics/plan_mimics.py` (projection and
budget rule; launching disabled until step 3). `research/cloud/launch_vm.py`: the bucket copy of the plan now
also carries `--project=mstool-research`.

## 14. Deviations log

*(empty at registration, commit effa3a9)*

| Date | Entry | Rule changed? | Seen before? |
|---|---|---|---|
| 2026-11-09 | **Not a deviation — pilot and budget rule applied.** `mimics-pilot` (c2d-highmem-4 Spot, 8,782 s, 0.317 USD, no interruption): all 585 C inputs simulated and frozen (C1 485, C2 100), HD-BET + every tool on the four pilot inputs, 0 errors, **G3 36/36 PASS**. Mean seconds per input: HD-BET 380 (WMH FLAIR), 833 (DLBS, FLAIR 561 + MPRAGE 1105), FLAMeS 5 folds 306–317, LST-AI 116–136, MindGlide 57–77, WMH-SynthSeg 264–283 (peak 31.3 GB), SAMSEG 425–573 (DLBS peak 8.3 GB, so no rerouting). Budget rule → **full amendment-1 plan** (no reduction). | no | pilot timings, memory, disk use and PASS/FAIL only; no output value read |
| 2026-11-09 | **Execution note (layout, no rule changed).** (1) The pilot measured the docker disk use of the images (FreeSurfer 41.2 GB, LST-AI 30.2 GB, MindGlide 13.3 GB), more than section 15.3's four-VM layout allowed under the 250 GB SSD quota; (2) the first launch then met the project's **global CPU quota (12 vCPUs = three 4-vCPU machines)**: three of four VMs had started (`mimics-nn-l`, `mimics-nn-m`, `mimics-fs-a`, about 4 minutes each, ≈ 0.02 USD, nothing finished) and were deleted by name. Final layout, three Spot VMs balanced on the pilot timings: `mimics-v1` (c2d-standard-4, 65 GB: HD-BET of A, LST-AI everywhere, a share of FLAMeS), `mimics-v2` (c2d-highmem-4, 95 GB: WMH-SynthSeg and MindGlide everywhere, shares of SAMSEG and FLAMeS), `mimics-v3` (c2d-standard-4, 75 GB: HD-BET of B, shares of SAMSEG and FLAMeS); 235 GB. Same tools, inputs, settings and outputs; only which machine runs what. Projection on this layout: 33.5 USD central, 41.7 USD high (≤ 45), wall clock ≈ 105 h (high 131 h); guards 137 h per VM, worst case 43.6 USD. | no | as above |
| 2026-11-09 | **Amendment 1 (section 15): budget.** Spot VMs, hard cap 45 USD, DLBS stratified sample of 100 (B2 dropped), SAMSEG on a pre-listed 50-scan subset in part C1, C2 at 7 mm only, WMH-SynthSeg run on the 110 WMH test subjects only, new reduction order, one-input-per-data-type pilot. Registered and pushed before any VM of the addendum (pilot included) was launched. | yes (sections 2.1, 2.2, 6.2, 6.3, 6.5, 9, 13) | nothing beyond section 12: no tool had run on any new input |

## 15. Amendment 1 — budget (2026-11-09, before any VM launch; pre-analysis)

**Why.** The owner had been told this addendum would cost about 10–20 USD; the projection of section 9
(81–100 USD) uses too much of the remaining free credit, and the billing account is a paid account, so a
hard cap is mandatory. No output of any tool exists for any new input (the only cloud job so far is the data
mirror of section 2), so this is a pre-analysis amendment. Everything not changed here stays as registered.

### 15.1 Provisioning

- **All VMs are Spot (pre-emptible)**, self-deleting as before (`--max-run-duration`, termination action
  DELETE, in-VM guard, exit trap). Every driver is resumable per case (an output already in the bucket is
  never recomputed). **Interruptions are recorded**: each VM carries a shutdown script that writes
  `gs://mstool-research-data/mimics/interruptions/<vm>-<unix time>.txt` with the metadata server's
  `preempted` flag; a pre-empted VM may be relaunched with identical settings **only while the cap of 15.3
  is not exceeded** (no relaunch beyond the cap).
- **Machine family C2D** (AMD EPYC Milan, the processor generation of the healthy arm's N2D machines; quota
  32 vCPUs): `c2d-highmem-4` (32 GB) for WMH-SynthSeg and for the pilot, `c2d-standard-4` (16 GB) otherwise.
  If C2D Spot capacity is exhausted in every us-central1 zone, the N2D machine of the same memory is used and
  recorded. The machine of every output is in its run manifest; tool settings and inputs are identical.
- Spot list prices (catalog 2026-11-09, boot disk included): c2d-standard-4 + 50 GB **0.09003 USD/h**, + 75 GB
  0.09346; c2d-highmem-4 + 75 GB **0.12248**, + 130 GB 0.13002 (pilot).

### 15.2 Analysis sets (frozen in `research/paper_1/mimics/analysis_sets.json` by `freeze_amendment_sets.py`)

- **A (WMH 2017): unchanged, 170 subjects** for every arm except **WMH-SynthSeg, which is run only on the 110
  test subjects** (its 60 contaminated training cells are not produced at all; the "reported apart" clause of
  section 2.1 is dropped). Families A-1 and A-2 are unchanged (WMH-SynthSeg comparisons on the 110).
- **B1 (DLBS): a stratified random sample of 100** of the 275 B1 participants: **25 per decade** (50–59,
  60–69, 70–79, 80–89; pools 70 / 73 / 81 / 51). Within each decade the ids are sorted by participant number
  and drawn with one `numpy.random.RandomState(20261109)` stream, decades in ascending order
  (`rng.permutation(n)[:25]`). The 100 ids, each one's decade and draw rank are in `B1_sample`.
  **B2 is dropped.** Families B-a and B-b keep their 5 tests each, on n = 100; the replication contrast and
  age analyses use the 100 (25 per decade). Reduction (iii) "DLBS 75" = draw ranks 1–19 in the 50s, 60s and
  70s and 1–18 in the 80s (`B1_sample.reduced_75`, 75 ids).
- **C1 (controlled thickness, MS):** FLAMeS (both arms), LST-AI, MindGlide and WMH-SynthSeg at 3, 5 and 7 mm on
  all 145 scans (FLAMeS comparisons on the 125 FLAMeS-clean, LST-AI 144), exactly as registered. **SAMSEG runs
  only on a pre-listed subset of 50 scans, at 1 mm and at 3, 5 and 7 mm**: all 10 Ljubljana-clean scans (the
  only truly thin acquisitions) + 40 FLAMeS-clean MSLesSeg scans stratified by native slice thickness in
  proportion to 43 / 52 / 15 / 5 (≤ 2.3 mm: 15, 3 mm: 18, 4–5 mm: 5, unknown: 2), drawn with
  `RandomState(20261109).permutation` per stratum in that order over sorted ids (`C1_samseg_subset`; native
  thickness per scan from the dataset CSV, SHA-256 in `C1_native_thickness`). SAMSEG's C-1 test and C-2
  contrast use these 50 (FLAMeS-clean by construction). The native-thickness stratification of section 6.3 is
  kept for every arm.
- **C2 (SibBMS thickened): 7 mm only** (100 controls, every arm). Family C-3 is unchanged (it compared 7 mm with
  1 mm); the 3- and 5-mm descriptive rows for C2 are dropped.
- **D:** unchanged rules; validation on DLBS uses the 100 sample (D-1 on n = 100; transfer reading unchanged),
  on C1 the thicknesses actually run.
- **Precision now:** n = 100 → exact 95 % CI half-width ≈ ±10 points near 50 % and ±8 near 20 %; 5 % on 100 →
  1.6–11.3 %. SAMSEG ΔF1 on 50 scans ≈ ±0.03.

### 15.3 Cap, projection and budget rule (replaces section 9.2–9.4)

- **Hard cap: 45 USD** for the whole addendum = list price of everything that runs, Spot (mirror 0.009 USD,
  pilot, preparation, tool VMs, registration and evaluation VM).
- **Layout** (quotas: 4 external addresses, 250 GB SSD): two "nn" VMs (c2d-standard-4, 50 GB) do the HD-BET
  preparation of their block (A on `mimics-nn-a`, B on `mimics-nn-b`) and then FLAMeS 5 folds, LST-AI and
  MindGlide on their share of the inputs; two "fs" VMs do WMH-SynthSeg then SAMSEG (`mimics-fs-a`,
  c2d-highmem-4 75 GB) and SAMSEG (`mimics-fs-b`, c2d-standard-4 75 GB), processing C2 and C1 first and A and
  B only after the preparation of those blocks is complete (a completion marker per block). Work is split to
  equalise projected hours; the split never changes an output.
- **Projection before the pilot** (`plan_mimics.py`, ledger seconds on N2D, conservative for C2D):

| Variant | VM-h | CPU-h | USD central – high | wall clock (high) |
|---|---|---|---|---|
| full amendment-1 plan | 270 | 1,074 | **27.3 – 33.9** | ≤ 86 h |
| (i) drop C2 | 233 | 928 | 23.6 – 29.3 | ≤ 76 h |
| (i) + (ii) C1 at {3, 7} mm | 195 | 775 | 19.9 – 24.7 | ≤ 62 h |
| (i) + (ii) + (iii) DLBS 75 | 184 | 730 | 18.8 – 23.3 | ≤ 59 h |

  (high = measured seconds × 1.25 + 0.35 h set-up per VM, + 0.6 USD for the registration/evaluation VM.)
- **Rule after the pilot:** the pilot's mean seconds per step (per data type where they differ) replace the
  ledger values and the spend so far is added; if the HIGH projection exceeds 45 USD, reduce **in this order
  until it fits: (i) drop C2** (family C-3 → "not run", p = 1 in the strictest reading); **(ii) C1 at {3, 7}
  mm only** (the 5-mm rows are not produced; C-1 and C-2 use 7 mm and are unaffected); **(iii) DLBS sample 75**.
  If nothing fits: stop (owner decision). The full runs are launched only if the selected projection is
  ≤ 45 USD.
- **Guards:** each VM's in-VM guard and `--max-run-duration` are set so that, if every VM ran to its guard, the
  total spend would still be ≤ 45 USD (`plan_mimics.guards`). VMs self-delete; nothing is relaunched beyond the cap.

### 15.4 Pilot (replaces section 9.3)

One Spot VM (`mimics-pilot`, c2d-highmem-4, 130 GB): (1) writes **all** simulated inputs of C1 (145 × 3 + the
SAMSEG subset's 50 1-mm copies) and C2 (100 × 7 mm) with their SHA-256 manifest and completion markers — the
simulated inputs are therefore frozen before any tool sees them; (2) HD-BET for its A and B inputs; (3) every
tool on one input per data type: `wmh_utrecht_1` (test), DLBS `sub-178` (lowest participant number of the
sample's recruitment cohort 1), `mslesseg_P10_T1` at 7 mm (in the SAMSEG subset) and SibBMS `sub-001` at 7 mm.
Pass = every output present, on the input grid, binary where required, SHA-256 equal to its manifest (G3,
`check_structure.py`, prints PASS/FAIL only); timings and peak memory recorded. Pilot outputs stay in the
analysis. If DLBS SAMSEG peaks above 13 GB in the pilot, block B's SAMSEG is routed to the 32-GB VM.

### 15.5 What is printed before the frozen evaluation

Driver logs carry timings, memory and grid-transform kinds only; the toolbench drivers run with
`--log-outcomes 0` (no lesion-voxel counts, unlike the healthy arm's pilot), and no one reads the values of
any output before the evaluation code is committed and run once (section 11 steps 7–8). The structural check
reads files and prints PASS/FAIL. The MNI registration QC (gate GR) is computed and written before any
outcome, as registered.

### 15.6 Sections superseded

2.2 (B1 → the 100 sample; B2 dropped), 2.1 (WMH-SynthSeg cells on the 60 training subjects not produced),
6.2 (B2 analyses), 6.3 (SAMSEG subset; C2 at 7 mm), 6.5 (precision), 9.1–9.4 (provisioning, projection,
pilot, budget rule; the stop rules of 9.5 stand with "110 USD" read as "45 USD"), 13 (files: + 
`freeze_amendment_sets.py`, the amended `plan_mimics.py`, and the execution code of step 2).

## References

- Kuijf HJ, et al. Standardized assessment of automatic segmentation of white matter hyperintensities and
  results of the WMH Segmentation Challenge. IEEE Trans Med Imaging 2019;38(11):2556–2568.
  doi:10.1109/TMI.2019.2905770 (arXiv 1904.00682). Data: doi:10.34894/AECRSD (CC BY-NC 4.0).
- Park DC, et al. The Dallas Lifespan Brain Study: a comprehensive adult lifespan data set of brain and
  cognitive aging. Sci Data 2025;12:846. doi:10.1038/s41597-025-04847-7. Data: doi:10.18112/openneuro.ds004856.v1.3.0 (CC0).
- Laso P, et al. Quantifying white matter hyperintensity and brain volumes in heterogeneous clinical and
  low-field portable MRI. IEEE ISBI 2024 (arXiv 2312.05119).
- Dereskewicz E, et al. A novel convolutional neural network for automated multiple sclerosis brain lesion
  segmentation (FLAMeS). J Neuroimaging 2025. doi:10.1111/jon.70085.
- Montalban X, et al. 2024 revisions of the McDonald criteria. Lancet Neurol 2025;24(10):850–865.
  doi:10.1016/S1474-4422(25)00304-7.
- Thompson AJ, et al. Diagnosis of multiple sclerosis: 2017 revisions of the McDonald criteria. Lancet Neurol
  2018;17(2):162–173.
- Filippi M, et al. MRI criteria for the diagnosis of multiple sclerosis: MAGNIMS consensus guidelines.
  Lancet Neurol 2016;15(3):292–303.
- Tools: as `PREREG-healthy-controls.md` and paper F `PROTOCOL.md` (MindGlide, WMH-SynthSeg, SAMSEG, LST-AI,
  FLAMeS weights Zenodo 17955359).
