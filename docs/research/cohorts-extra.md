# Extra public MS cohorts for the FLAMeS job — MS3SEG, Muslim 2022, PediMS

Research use only (not part of the medical device). Prepared 2026-10-17 on branch
`research/cohorts-extra`. Code: `research/cloud/cohorts_extra.py` (fetchers + HD-BET helper),
`research/cloud/check_cohorts_extra.py` (local one-case-per-cohort check),
`research/cloud/extra_cohorts_stage.py` + `vm_flames_ensemble_v2.sh` (cloud job, section 6). Check outputs:
`docs/research/records/cohorts_extra_check/`.

## 1. Summary

| | MS3SEG | Muslim et al. 2022 | PediMS |
|---|---|---|---|
| Obtainable | yes (Figshare, RAR5 archives, members stored → HTTP range per file) | yes (Mendeley, one zip → HTTP range per member) | yes (Figshare, individual files) |
| Format | NIfTI `.nii.gz` (dcm2niix) | NIfTI `.nii`, **no geometry** (pixdim 1 mm, qform/sform 0) | NIfTI `.nii.gz` / `.nii` |
| FLAIR used | `MS_100_patient_registered/NNN/NNN_FLAIR.nii.gz` (native) | `Patient-K/K-Flair.nii` | `PediMS/Pp/Tt/processed/brain_FLAIR.nii.gz` |
| Lesion GT | `MS_100_patient_masks/abWMH_Masks/NNN/NNN_abWMH_Mask.nii.gz` (0/255) | `Patient-K/K-LesionSeg-Flair.nii` (0/1) | `PediMS/Pp/Tt/processed/Consensus.nii` (0/1 float) |
| Mask on FLAIR grid | yes, all 100 (header check) | yes, all 60 (same array shape; no geometry to compare) | yes, all 28 (header check) |
| Skull-stripped | **no** → HD-BET (authors' FSL-BET available, leaves orbital fat) | **no** → HD-BET | **yes** (SynthStrip) |
| Acquisition | Toshiba Vantage 1.5T, axial 2D FLAIR | 1.5T, ~20 centres, 2D FLAIR | Siemens Skyra 3T, 2D FLAIR, children |
| Voxel (mm) | 0.898 × 0.898 × 6.0–8.1 | in-plane **estimated** 0.41–0.97; slices 4.86–8.3 (Suppl. Table 2) | 0.75 × 0.75 × 3.9 |
| Usable cases (default) | **100** | **51** axial (+6 coronal, +3 sagittal optional) | **28 scans / 9 patients** (longitudinal) |
| Case ids | `ms3seg_001…100` | `muslim_01…60` | `pedims_P1_T1…pedims_P9_T1` |
| Licence (live, 2026-10-17) | CC BY 4.0 (Figshare record v6; paper "Data Records" says the same) | CC BY 4.0 (Mendeley Data record v1) | CC BY 4.0 (Figshare record v1) |
| Download (all cases) | ≈ 200 MB + ≈ 460 small header reads (~3 min) | ≈ 190 MB (FLAIR + masks of 60) | ≈ 450 MB (`Consensus.nii` is uncompressed, 15 MB each) |

None of the three overlaps with FLAMeS training data (ISBI-2015, 3D-MR-MS/open_ms_data,
MSSEG-2016, see `data/registry.yaml`) or with the job's openms/MSLesSeg cohorts → all three are
FLAMeS-independent test sets.

## 2. Licences and citations (attribution is mandatory under CC BY 4.0; we also must say what we changed)

- **MS3SEG** — data: Figshare `10.6084/m9.figshare.30393475` (v6, 2026-06-21), CC BY 4.0; code MIT
  (github.com/Mahdi-Bashiri/MS3SEG). Paper: Bawil MB, Shamsi M, Ghalehasadi A, Jafargholkhanloo AF,
  Bavil AS. *A Multiple Sclerosis MRI Dataset with Tri-Mask Annotations for Lesion Segmentation.*
  Sci Data 13, 867 (2026), `10.1038/s41597-026-07184-5`. Note: the **article text** is CC BY-NC-ND 4.0;
  the **data** are CC BY 4.0.
- **Muslim et al.** — data: Mendeley Data `10.17632/8bctsm8jz7.1` (2022-03-31), CC BY 4.0. Paper:
  Muslim AM, Mashohor S, Gawwam GA, Mahmud R, Hanafi MB, Alnuaimi O, Josephine R, Almutairi AD.
  *Brain MRI dataset of multiple sclerosis with consensus manual lesion segmentation and patient meta
  information.* Data Brief 42:108139 (2022), `10.1016/j.dib.2022.108139`.
- **PediMS** — data: Figshare `10.6084/m9.figshare.28701065` (v1, 2025-05-23), CC BY 4.0. Paper: Popa M,
  Vișa GA, Șofariu CR. *PediMS: A Pediatric Multiple Sclerosis Lesion Segmentation Dataset.* Sci Data
  12, 1184 (2025), `10.1038/s41597-025-05346-5`.
- Changes we make (to be stated in any publication): re-encoding to NIfTI-1 `.nii.gz` with identical
  qform/sform; binarised masks; HD-BET skull stripping (MS3SEG, Muslim); for Muslim, reorientation to
  LAS and **estimated** in-plane voxel size.

## 3. Layout findings

### 3.1 MS3SEG (Figshare 30393475)
- 12 files: `MS_100_model_input.rar` (235 MB), `MS_100_patient_registered.rar` (596 MB),
  `MS_100_patient_preprocessed.rar` (711 MB), `MS_100_patient_full.part1-3.rar` (DICOM, 2.5 GB),
  `MS_100_patient_nifti.part1-3.rar` (2.5 GB), `MS_100_patient_masks.rar` (4.4 MB),
  `MS_100_patient_gifs.part1-2.rar`. All RAR5, **non-solid, members stored (no compression)** — so
  every member is one contiguous byte range: we list headers with small range reads and fetch only the
  member bytes (CRC32 verified). No `unrar` needed.
- `registered/NNN/`: `NNN_FLAIR.nii.gz` (native FLAIR, int16, with skull), `NNN_FLAIR_brain.nii.gz` and
  `NNN_brain_mask.nii.gz` (authors' FSL BET), `NNN_T1WI_reg`, `NNN_T2WI_reg`.
- Native axial FLAIR matrix is 256×256 for all 100, so the "standardised 256×256" `preprocessed`
  volumes are the same grid (pad/crop is a no-op; verified on case 001: max abs difference 0.14).
  Despite the paper's wording, `preprocessed` FLAIRs are **not** brain-extracted.
- Geometry (headers of all 100, range reads): 256×256×18–20, 0.898 mm in-plane, 6.0–8.1 mm slice
  spacing (slice thickness 4.7–6.9 mm + gap 0.7–2.1 mm), LAS. Mask shape and affine equal the FLAIR's
  for all 100.
- GT = `abWMH` (MS lesion) class only; `nWMH` (hyperintensities judged non-MS) and `Vent` are separate
  files. `fetch_ms3seg(..., with_nwmh=True)` writes the nWMH mask for an optional ignore-region analysis.
- `model_input/man_4L_masks_new/*.nii.gz` are an **older/different 4-label version** (stored x-flipped,
  value 65535 = lesion; case 001: 783 lesion voxels vs 973 in `abWMH`, 765 shared). Not used.

### 3.2 Muslim et al. 2022 (Mendeley 8bctsm8jz7)
- One zip (745 MB): `Patient-1 … Patient-60`, each with `K-Flair.nii`, `K-T1.nii`, `K-T2.nii` and
  `K-LesionSeg-{Flair,T1,T2}.nii`, plus two xlsx tables (patient info; sequence parameters).
- NIfTI files carry **no geometry**: float64 arrays, pixdim 1×1×1, qform and sform codes 0. FLAIR and
  `LesionSeg-Flair` have identical shapes for all 60 (header range reads), i.e. the mask is on the FLAIR
  voxel grid.
- Arrays are stored in DICOM (row, column, slice) order. Visual review of all 60 scans: **51 axial,
  6 coronal (14, 23, 41, 53, 54, 57), 3 sagittal (32, 48, 56)**. Matrices 224–512, 18–33 slices.
- Slice spacing per patient from Supplementary Table 2 (FLAIR "spacing between slices" 4.86–8.3 mm,
  thickness 3–6 mm), hard-coded in the module.
- **In-plane pixel size is not published anywhere** (the original DICOMs are not shared). The module
  estimates it per scan from the head size: maximum left–right head breadth and antero-posterior
  length, measured with a fixed threshold recipe, divided into reference values calibrated with the
  same recipe on 15 MS3SEG adults of known pixel size (breadth 158.7 ± 7.3 mm, length 193.0 ± 7.5 mm;
  CV ≈ 4.6 %). The two independent estimates agree on the 51 axial scans (ratio 1.04 ± 0.06).
  Result on the 51 axial scans: 0.41–0.97 mm (implied field of view 178–389 mm; scan 16 really has a
  very large FOV — the head fills only half of its 512² matrix). When the head is cut by the field of
  view along an axis that axis is not used (axial 31, 42, 55 use breadth only); when nothing is
  measurable the module falls back to a 240 mm FOV prior (coronal 14, 23, 53 and the 3 sagittal
  scans). Expected error ≈ ±5 % per axis (≈ ±10 % on lesion volumes in mL).
- Output is reoriented to LAS (left, anterior, superior), the orientation HD-BET and the other cohorts
  use. Anterior/posterior and (for coronal) superior/inferior were checked visually; for axial scans
  the slice direction is decided from the head area (vertex end is smaller; scan 16 is stored
  superior→inferior and is flipped). **Left/right cannot be recovered** — irrelevant for FLAMeS/HD-BET
  (mirror-augmented) and for Dice on this grid, but never use it for laterality.
- Default `fetch_muslim` keeps the 51 axial scans; `planes=("axial","coronal","sagittal")` adds the rest.

### 3.3 PediMS (Figshare 28701065)
- 365 individual files; the folder tree exists only in the API field `folder_structure`:
  `PediMS/P<1-9>/T<1-6>/{raw,processed}`. 28 scans (P1×3, P2×6, P3×6, P4×4, P5, P6, P7×3, P8×3, P9).
- `processed/`: `brain_FLAIR.nii.gz` (SynthStrip, uint16), `n4_brain_FLAIR.nii.gz` (+N4),
  `mask_FLAIR.nii.gz` (= **brain** mask, not lesions!), `Consensus.nii` (= **lesion** mask, float32 0/1,
  uncompressed), same for T1/T2. `raw/`: `defaced_{FLAIR,T1,T2}.nii.gz`.
- Geometry (headers of all 28): 290×320×40–50, 0.75×0.75×3.9 mm, LAS (slightly oblique sform);
  `brain_FLAIR`, `Consensus` and `defaced_FLAIR` share shape and affine for all 28.

## 4. Local validation (one case per cohort)

`python research/cloud/check_cohorts_extra.py --workdir <tmp> --outdir docs/research/records/cohorts_extra_check --hdbet --cleanup`

| Check | ms3seg_001 | muslim_01 | pedims_P1_T1 |
|---|---|---|---|
| Shape | 256 × 256 × 20 | 256 × 256 × 23 | 290 × 320 × 40 |
| Voxel (mm) | 0.8984 × 0.8984 × 6.8 | 0.8599 × 0.8599 × 5.5 | 0.75 × 0.75 × 3.9 |
| Orientation | LAS | LAS | LAS |
| FLAIR/mask same shape | yes | yes | yes |
| FLAIR/mask identical affine | yes | yes | yes |
| Mask binary (uint8 0/1) | yes | yes | yes |
| Lesion voxels | 973 | 776 | 1060 |
| Lesion volume (mL) | 5.34 | 3.156 | 2.325 |
| Lesion / surrounding FLAIR (median) | 1.259 | 1.237 | 1.363 |
| Head(brain) left-right (mm) | 161.7 | 163.4 | 130.5 |
| Head(brain) front-back (mm) | 192.3 | 187.5 | 165.0 |
| Needs skull strip | yes | yes | no |
| HD-BET brain fraction | 0.1973 | 0.1882 | — |
| Lesion share outside HD-BET brain | 0.0 | 0.0 | — |
| All checks pass | yes | yes | yes |

Overlays (red = lesion mask, cyan = HD-BET brain outline; patient left on the right, anterior up):
[MS3SEG 001](records/cohorts_extra_check/ms3seg_ms3seg_001.png) · [Muslim 01](records/cohorts_extra_check/muslim_muslim_01.png) · [PediMS P1 T1](records/cohorts_extra_check/pedims_pedims_P1_T1.png). Plane review of all 60 Muslim scans: muslim_plane_review_*.jpg and muslim_nonaxial_orientation.jpg in the same folder (head-extent numbers: muslim_head_extent_stats.tsv, in stored-array axes; its last column compares lesions with the whole head including bright scalp and is NOT an alignment test).
HD-BET 2.0.1 (CPU, no test-time augmentation) ran end-to-end on the MS3SEG and Muslim cases through hdbet_strip(); the brain image keeps the original affine and no lesion voxel fell outside the brain mask.

Additional targeted checks (Muslim): scans 16 (axial, stored superior→inferior → flipped correctly,
pixel 0.760 mm, ring ratio 1.15), 53 (coronal) and 32 (sagittal) reorient correctly to LAS (anterior up,
superior up in the overlays) with ring ratios 1.14 / 1.14. The assembly block of the patched job script
was exercised locally with stub fetchers (selection by `case-offset`/`case-limit`, HD-BET only on the
selected cases, a simulated outage of one source does not stop the run).

## 5. Caveats

- **2D thick slices everywhere** (MS3SEG 6–8 mm, Muslim 4.9–8.3 mm, PediMS 3.9 mm). FLAMeS will see
  a strong domain shift; small lesions suffer partial volume; 3D connected components across 6–8 mm
  gaps are unreliable, so lesion-wise metrics should be reported with that caveat (or per slice).
- **Raters / protocol differ** from FLAMeS' training labels:
  MS3SEG — one junior annotator + one senior neuroradiologist (consensus review), minimum lesion
  diameter 3 mm, automated intensity QC plus morphological opening/closing (smoothed masks), and
  periventricular "normal WMH" deliberately excluded from the lesion class (FLAMeS hits there count as
  false positives by protocol). Muslim — sequential correction chain (radiology resident → consultant
  radiologist → neurologist), not independent raters; masks drawn per sequence, only the FLAIR one is
  used. PediMS — one junior rater, validated by a paediatric neurologist and a radiologist (JIM 9.0).
- **Muslim**: in-plane voxel size is an estimate (see 3.2); 20 uncontrolled centres; several FLAIRs
  have a visibly different contrast (e.g. 2, 3, 10, 26, 28: much brighter parenchyma, CSF still dark)
  and scan 45 lists a FLAIR TR of 3830 ms;
  9 non-axial scans excluded by default; L/R unknown.
- **PediMS**: 28 scans of only 9 children — longitudinal scans of the same child are NOT independent
  (cluster by patient); P9 is Baló's concentric sclerosis (atypical lesions); P1 had an ADEM-like onset.
- **MS3SEG**: all scans from one scanner/centre; native FLAIR has skull (HD-BET) — the authors' BET
  output is available via `use_authors_brain=True` but keeps orbital fat on some slices.
- Skull stripping adds a dependency: HD-BET v2 is run on CPU without test-time augmentation; lesions
  outside its brain mask become false negatives — `hdbet_qc.json` reports that share per case.
- No overlap between these cohorts and FLAMeS training data or the job's other cohorts is known.
- Every fetched case gets a lesion-vs-surrounding FLAIR ratio in manifest.json (cloud run: copied to
  $BK/extra_qc/). A ratio <= 1.0 means the mask is not on hyperintense tissue: inspect before using it.

## 6. Cloud job integration (v2 job script)

The v1 patch prepared on `research/cohorts-extra` was superseded: the cohorts are wired into
`research/cloud/vm_flames_ensemble_v2.sh` through `research/cloud/extra_cohorts_stage.py`.

- `datasets` may list `ms3seg muslim pedims` (alone or with `openms mslesseg`). The VM copies
  `cohorts_extra.py` and `extra_cohorts_stage.py` from `gs://mstool-research-data/flames-ensemble/code/`.
- HD-BET 2.0.1 is installed with every frozen package version as a pip constraint, so torch,
  torchvision, nnU-Net and numpy stay exactly as in `env/requirements.lock` (HD-BET only adds
  scikit-image); an environment self-test runs before any work.
- `build-raw` fetches all three cohorts once and caches them as `inputs/extra_cohorts_raw_v1.tar.gz`
  (+ `.sha256`); later runs only download the tarball.
- `case-offset` / `case-limit` apply to the sorted list of ALL selected datasets; only the selected
  cases that still have a skull go through HD-BET (CPU, no TTA), one case at a time. Each brain is
  uploaded at once to `inputs/extra_stripped/{case}_flair_brain.nii.gz` (QC to `.../qc/`) and reused by
  every later run, so HD-BET runs once per case.
- FLAMeS then runs per fold exactly like the other cohorts (`flames_ensemble_driver.py`).

Launch (pilot: one case per cohort, fold 0; `case-ids` overrides offset/limit):

```
python research/cloud/launch_vm.py --name flames-extra-pilot --machine-type n2d-standard-4 \
    --startup research/cloud/vm_flames_ensemble_v2.sh --purpose "Extra cohorts pilot" --paper A \
    --max-hours 2 --meta "datasets=ms3seg muslim pedims" "case-ids=ms3seg_001 muslim_01 pedims_P1_T1" folds=0
```
