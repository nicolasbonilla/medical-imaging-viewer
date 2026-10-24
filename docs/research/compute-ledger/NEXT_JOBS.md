# Next research cloud jobs — SibBMS healthy controls (Job 1) and LST-AI maps (Job 2)

Prepared 2026-10-17 on branch `research/cloud-jobs-controls-lstai`. **Nothing has been launched.**
Project `mstool-research` and bucket `gs://mstool-research-data` only. No script references any
other project.

> **Resumen en español sencillo.** Dos trabajos listos para lanzar cuando se revisen.
> (1) Los **100 controles sanos** de SibBMS (el conjunto público tiene exactamente 100): se sacan
> FLAIR y T1 del archivo público sin bajar los 11 GB, se les quita el cráneo con HD-BET y se pasan
> por los 5 modelos de FLAMeS por separado. (2) Los **mapas de probabilidad de LST-AI v1.2.0** para
> 114 casos de MSLesSeg (P49_T2 se salta: su T1 está vacía), 30 de Ljubljana y los 100 controles.
> Coste esperado ≈ 7,6 USD (≈ 6,7 EUR), en el peor caso estimado ≈ 11,3 USD (≈ 10 EUR), dentro de
> los 240 EUR.
> Cuidado con las licencias: los datos de SibBMS y los pesos de HD-BET v2 son **solo para uso no
> comercial**; sirven para investigación y artículos, no para el producto que se vende.

## 0. Before launching (once)

1. Wait until `flames-full-a/b/c` have deleted themselves: they hold the whole quota
   (2 × n2d-standard-4 + 1 × n2-standard-4 = 12 vCPU; at most 8 N2D vCPU per region).
2. Upload the job code from this branch (the VMs download it; the manifests record its SHA-256):

```bash
export CLOUDSDK_CONFIG="C:/Users/Nicolas/.gcloud-mstool"     # isolated config, project mstool-research
B=gs://mstool-research-data
gcloud storage cp research/cloud/sibbms_controls_prep.py research/cloud/job_common.py $B/controls/code/
gcloud storage cp research/cloud/lstai_driver.py research/cloud/job_common.py $B/lstai/code/
# flames_ensemble_driver.py is unchanged on this branch; the controls job reuses the copy already at
# $B/flames-ensemble/code/. Check it is the same file (both md5 values must match):
gcloud storage hash research/cloud/flames_ensemble_driver.py
gcloud storage objects describe $B/flames-ensemble/code/flames_ensemble_driver.py --format="value(md5_hash)"
```

3. Optional but advisable: fill in the SibBMS request-access form once
   (<https://forms.gle/VqTenJ4n8S8qvtxQA>); the direct zip link works without it (see §4).

`launch_vm.py` prices every VM from the official catalog (cores + RAM + boot disk) and records it.

## 1. Job 1 — SibBMS healthy controls (`vm_sibbms_controls_v2.sh`)

**What the public release contains** (zip central directory read on 2026-10-17 by HTTP range
requests, 271 KB, no image data; index saved as `research/cloud/tests/fixtures/sibbms_norm_index.json`):
`Output/Norm/` has **100 healthy controls, sub-001 … sub-100**, one session each, every one with
`FLAIR`, `T1w`, `T2w` (5 also have `ce-GAD_T1w`). FLAIR + T1w of all 100 = 1.38 GB compressed, so
the 11 GB zip (10,971,922,363 bytes, ETag `"28dfa3fbb-63b86c4486840"`, Last-Modified 2025-08-04) is
never downloaded. Headers of sub-001/050/100: FLAIR and T1w share the same 197 × 233 × 189 grid,
1 mm, RAS, origin (−98, −134, −72), identical to the August control FLAMeS maps — so the T1 needs no
interpolation (checked on the real sub-001 T1w: transform = identity). These images are **not**
native space (the registry says so): the paper registers every series to a reference FLAIR
volume ("NMRI225 Flair").

**Steps per control** (resumable, uploaded case by case):
1. FLAIR + T1w from the bucket mirror `inputs/sibbms_norm/` (with `.sha256`), or the first time
   from the public zip with remotezip (zip CRC-32 checked) and mirrored.
2. HD-BET v2.0.1 (commit `678e44d`, the code August installed), CPU, test-time augmentation ON
   (August setting, so the 30 August controls can be compared), on the FLAIR → stripped FLAIR + mask.
3. T1w onto the FLAIR grid (identity when the grids match, else trilinear, recorded) × the same mask.
4. FLAMeS folds 0–4 **separately** with the unchanged `flames_ensemble_driver.py` (one model per
   fold, no TTA, uint8 storage) fed by `/w/cases.json`.

**Outputs**

| What | Path in `gs://mstool-research-data/` |
|---|---|
| Skull-stripped FLAIR (float32, Norm grid) | `controls/sibbms/{case}_FLAIR.nii.gz` |
| Skull-stripped T1 on the FLAIR grid (float32) | `controls/sibbms/{case}_T1.nii.gz` |
| HD-BET brain mask (uint8 0/1) | `controls/sibbms/{case}_brainmask.nii.gz` |
| FLAMeS fold k, k = 0..4 (uint8, max error 0.00196) | `flames-ensemble/cohort/{case}_f{k}_prob.nii.gz` |
| All-zero lesion mask | `flames-ensemble/cohort/{case}_gt.nii.gz` |
| Step-1 manifest (zip identity, HD-BET commit + weight checksum, per-case CRC/SHA-256, grids, brain volume, timings, peak memory) | `controls/manifests/<run>.json` |
| FLAMeS manifest (versions, checkpoint checksums, per case-fold seconds) | `flames-ensemble/manifests/<run>.json` |
| Mirrored inputs | `inputs/sibbms_norm/*`, `inputs/hdbet_release_v1.5.0.zip(.sha256)` |
| Frozen environment | `env/requirements-controls.lock` (FLAMeS lock + HD-BET + remotezip) |
| Cost, log, ledger | `controls/cost/<run>.txt`, `controls/logs/<run>.log`, `runs/<run>/runinfo.json` |

`{case}` = `sub-001` … `sub-100`, the ids the detector already uses.

**Pilot** (2 controls: sub-001 = August parity, sub-021 = one of the 10 lost in August):

```bash
python research/cloud/launch_vm.py --name sibbms-ctl-pilot --machine-type n2d-standard-4 \
  --startup research/cloud/vm_sibbms_controls_v2.sh --paper "A,detector-v3" --max-hours 2 \
  --purpose "SibBMS controls pilot: sub-001 (August parity) + sub-021, HD-BET + FLAMeS folds 0-4" \
  --meta cases="sub-001 sub-021" folds="0 1 2 3 4" hdbet-tta=1
```

**Pilot pass/fail** (after the VM has deleted itself):

```bash
D=C:/tmp/mstool-pilot-controls
gcloud storage cp "$B/controls/sibbms/sub-001_*" "$B/controls/sibbms/sub-021_*" $D/controls/sibbms/
gcloud storage cp "$B/flames-ensemble/cohort/sub-001_*" "$B/flames-ensemble/cohort/sub-021_*" $D/flames-ensemble/cohort/
gcloud storage cp $B/controls/manifests/sibbms-ctl-pilot.json $D/prep_manifest.json
gcloud storage cp $B/flames-ensemble/manifests/sibbms-ctl-pilot.json $D/flames_manifest.json
python research/cloud/check_outputs.py controls --controls-dir $D/controls/sibbms \
  --folds-dir $D/flames-ensemble/cohort --august-dir data/cohorts/sibbms-controls-flames --cases sub-001 sub-021
```

PASS only if all of these hold:
- `check_outputs.py` prints PASS for both: FLAIR, T1, mask on one grid; mask binary; nothing
  outside the mask; 5 fold maps on the FLAIR grid with values in [0, 1].
- sub-001 fold 0 vs the August map: Dice(>0.5) ≥ 0.95 (expected 1.0) and max difference ≤ 0.0025
  (= uint8 rounding). A larger difference is a WARN: HD-BET did not reproduce the August mask.
- Prep manifest: `errors` empty; `t1_transform.kind == "identity"`; `skull_strip.direct_url` shows
  commit `678e44d…`; `checkpoint_sha256` present; `source_zip.matches_2026_10_17` true; brain volume
  plausible; `hdbet_peak_swap_used_gb` ≈ 0.
- FLAMeS manifest: 10 case-fold entries ok, no errors. VM gone; `runinfo.json` and cost file present.
- Read `seconds_hdbet` and the FLAMeS seconds: if HD-BET takes > 10 min per control, decide before
  the full run (switching TTA off would break parity with the 30 August controls).

**Full run** (3 chunks, fills the quota; the pilot's two controls are skipped automatically):

```bash
S=research/cloud/vm_sibbms_controls_v2.sh
python research/cloud/launch_vm.py --name sibbms-ctl-a --machine-type n2d-standard-4 --startup $S --max-hours 12 \
  --paper "A,detector-v3" --purpose "SibBMS controls sub-001..sub-034: HD-BET + FLAMeS folds 0-4" --meta case-offset=0 case-limit=34
python research/cloud/launch_vm.py --name sibbms-ctl-b --machine-type n2d-standard-4 --startup $S --max-hours 12 \
  --paper "A,detector-v3" --purpose "SibBMS controls sub-035..sub-067: HD-BET + FLAMeS folds 0-4" --meta case-offset=34 case-limit=33
python research/cloud/launch_vm.py --name sibbms-ctl-c --machine-type n2-standard-4 --startup $S --max-hours 12 \
  --paper "A,detector-v3" --purpose "SibBMS controls sub-068..sub-100: HD-BET + FLAMeS folds 0-4" --meta case-offset=67 case-limit=0
```

## 2. Job 2 — LST-AI v1.2.0 probability maps (`vm_lstai_maps.sh`, `lstai_driver.py`)

**Tool, exactly.** Docker Hub `jqmcginnis/lst-ai:v1.2.0`, pinned by digest
`sha256:2b2a0d6454e6efff60a350df3c650ae9584f1926338dec7842f9e71912cc6c85` (the tag August used; built
2024-12-18; 11.1 GB compressed; image config `sha256:959900db…`). Its layers, read from Docker Hub
on 2026-10-17, contain LST-AI branch `jqm/old_hd_bet` @ `4d930aa` (= `main` @ `3a65a12` with only
`setup.py` changed, so `pip` reports version 1.1.0), the U-Net weights from release v1.1.0
`lst_data.zip`, TensorFlow 2.13.1, greedy @ `1eafa4c`. There is no v1.2.0 git tag; the Docker tag is
the version. The driver refuses to start if the image id differs or the three
`UNet3D_MS_final_mdl{A,B,C}.h5` are not found, and records their SHA-256, the atlas checksums, the
in-image git commit, TensorFlow and greedy versions.

**Command per case** (recorded in the manifest):

```
docker run --rm -v <case_dir>:/work lstai:v1.2.0 --t1 /work/in/t1.nii.gz --flair /work/in/flair.nii.gz \
  --output /work/out --temp /work/tmp --probability_map --stripped --device cpu --threads 4 --segment_only
```

`--segment_only` skips the McDonald-region annotation, which runs after the segmentation and does
not touch the probability maps (LST_AI/lst @ 3a65a12); it only saves a deformable registration per
case. Set `segment-only=0` to run it anyway.

**Inputs.** MSLesSeg (Figshare file 52771814, same cached mirror as the FLAMeS runs): FLAIR
`P*_T*_FLAIR` / T1 `P*_T*_T1` (train) and `P*_FLAIR` / `P*_T1` (test); 115 scans, **P49_T2 skipped**
(T1 all zero, recorded in `skipped`) → 114. Ljubljana (open_ms_data `cross_sectional/MNI`, same
mirror): FLAIR `FLAIR_N4_noneck_reduced_winsor_regtoFLAIR_brain_N4_regtoMNI.nii.gz`, T1
`T1_N4_noneck_reduced_winsor_regtoFLAIR_brain_N4_regtoMNI.nii.gz` (exists for all 30; **not**
`T1POST_…`, which is post-gadolinium) → 30. Controls: Job 1 `controls/sibbms/{case}_FLAIR/_T1` → 100.
All are already skull-stripped, hence `--stripped`. The local dry run of the case builder on
`data/external` gives exactly 114 + 30 cases, skips only P49_T2, and the ids equal the existing
FLAMeS cohort ids.

**Maps and resampling.** With `--probability_map`, LST-AI writes to `--temp`
`sub-X_ses-Y_space-FLAIR_seg-lst_prob.nii.gz` (ensemble = mean of the three U-Nets) and
`…_prob_{1,2,3}.nii.gz`, already warped back by greedy (linear) onto the input FLAIR grid. Since
the input FLAIR is the very file FLAMeS used, the reference grid is the FLAMeS grid. The driver
compares shape + affine (tolerance 1e-4 mm): identical → values copied (no interpolation); otherwise
trilinear through world coordinates (`scipy.ndimage.affine_transform`, order 1, 0 outside), and the
4 × 4 voxel matrix is recorded per map. Values are clipped to [0, 1] and stored as uint8 with the
NIfTI slope: **max error = range / 510 ≤ 0.00196**, re-measured on every file
(`storage_max_abs_error`). `store-dtype=float32` stores them exactly instead (≈ 4× larger).

**Outputs**

| What | Path in `gs://mstool-research-data/` |
|---|---|
| Ensemble probability | `lstai/cohort/{case}_lstai_prob.nii.gz` (uploaded last = case complete) |
| U-Net A, B, C | `lstai/cohort/{case}_lstai_prob_m1.nii.gz`, `_m2`, `_m3` |
| LST-AI binary mask, affines to MNI | `lstai/aux/{case}_lstai_seg.nii.gz`, `{case}_affine_{flair,t1w}_to_mni.mat` |
| Manifest (command, image digest/id, commit, model + atlas SHA-256, per-case input SHA-256, seconds, peak memory/swap, transform, storage error, ensemble − mean(3) check) | `lstai/manifests/<run>.json` |
| Frozen host env | `env/requirements-lstai-host.lock` |
| Cost, log, ledger | `lstai/cost/<run>.txt`, `lstai/logs/<run>.log`, `runs/<run>/runinfo.json` |

Case ids: `mslesseg_P10_T1`, `mslesseg_P54`, `openms_patient16`, `sub-001` (same as FLAMeS).

**Pilot** (after the Job 1 pilot, because it uses control sub-001): 2 cases on two different grids
(MSLesSeg 182 × 218 × 182 LAS, control 197 × 233 × 189 RAS) plus the P49_T2 skip check:

```bash
python research/cloud/launch_vm.py --name lstai-pilot --machine-type n2d-standard-4 --disk-gb 100 \
  --startup research/cloud/vm_lstai_maps.sh --paper "detector-v3" --max-hours 2 \
  --purpose "LST-AI v1.2.0 pilot: mslesseg_P10_T1 + sub-001, P49_T2 skip check" \
  --meta datasets="mslesseg controls" cases="mslesseg_P49_T2 mslesseg_P10_T1 sub-001"
```

**Pilot pass/fail:**

```bash
D=C:/tmp/mstool-pilot-lstai
gcloud storage cp "$B/lstai/cohort/mslesseg_P10_T1_*" "$B/lstai/cohort/sub-001_*" $D/lstai/cohort/
gcloud storage cp $B/lstai/manifests/lstai-pilot.json $D/
python research/cloud/check_outputs.py lstai --lstai-dir $D/lstai/cohort \
  --ref-dirs data/cohorts/mslesseg-flames C:/tmp/mstool-pilot-controls/flames-ensemble/cohort \
  --cases mslesseg_P10_T1 sub-001
```

PASS only if:
- Manifest: `image.matches_expected.image_id` and `.lstai_commit` true; three model checksums;
  `skipped` = [mslesseg_P49_T2, "blank …"]; 2 cases ok, `errors` empty.
- Per map: `transform.kind` = `identity` expected (trilinear is acceptable, but then look why);
  `storage_max_abs_error` ≤ 0.00196; `ensemble_minus_mean_of_3_max_abs` ≤ 1e-4.
- `check_outputs.py` PASS: 4 maps per case on the FLAMeS grid, values in [0, 1], ensemble ≈ mean
  of the three. Sanity (WARN only): Dice vs the expert mask of P10_T1 should be well above 0.2
  (a flip would give ≈ 0); the healthy control should have very little above 0.5.
- `peak_mem_used_gb` < 15 and `peak_swap_used_gb` ≈ 0 on the 16 GB machine; otherwise use a
  32 GB machine (n2d-highmem-4 / n2-highmem-4) for the full run.
- Read `seconds_lstai`; if it is above ~8 min per case, raise `--max-hours` or add a chunk.

**Full run** (after the three `sibbms-ctl-*` VMs are gone; one sorted list of 245 candidates:
115 MSLesSeg, 30 Ljubljana, 100 controls; offsets apply before the P49_T2 skip):

```bash
S=research/cloud/vm_lstai_maps.sh; M='datasets=mslesseg openms controls'
python research/cloud/launch_vm.py --name lstai-a --machine-type n2d-standard-4 --disk-gb 100 --startup $S --max-hours 12 \
  --paper "detector-v3" --purpose "LST-AI v1.2.0 maps, candidates 1-82 (MSLesSeg P1_T1..P54)" --meta "$M" case-offset=0 case-limit=82
python research/cloud/launch_vm.py --name lstai-b --machine-type n2d-standard-4 --disk-gb 100 --startup $S --max-hours 12 \
  --paper "detector-v3" --purpose "LST-AI v1.2.0 maps, candidates 83-164 (MSLesSeg P55.., Ljubljana, sub-001..019)" --meta "$M" case-offset=82 case-limit=82
python research/cloud/launch_vm.py --name lstai-c --machine-type n2-standard-4 --disk-gb 100 --startup $S --max-hours 12 \
  --paper "detector-v3" --purpose "LST-AI v1.2.0 maps, candidates 165-245 (controls sub-020..sub-100)" --meta "$M" case-offset=164 case-limit=0
```

(`lstai-a` needs no controls, so it may start as soon as one `sibbms-ctl-*` VM has finished.)
`mirror-image=1` would also keep a copy of the image in `inputs/` (≈ 30 GB, ≈ 0.60 USD/month);
it is off because the digest already guarantees the same bytes and only Docker Hub availability
would be gained.

## 3. Time and cost (list prices, USD/h incl. boot disk)

Rates: n2d-standard-4 0.17583, n2-standard-4 0.20109 (50 GB disk); +0.00685/h for the 100 GB disk
of Job 2 (pd-balanced 0.10 USD per GiB-month ÷ 730; `launch_vm.py` records the catalog value).

| Item | Basis | Low | Expected | High |
|---|---|---|---|---|
| FLAMeS per case-fold, 4 vCPU | measured 65.5–70.2 s (ledger); control grid ~20 % larger | 70 s | 75 s | 85 s |
| HD-BET per control, TTA on, 4 vCPU | HD-BET README: "about 2 minutes on CPU (using --disable_tta)"; August: 30 controls took 3.18 VM-hours on n2-standard-8 incl. setup and FLAMeS fold 0 ≈ 3–3.5 min of HD-BET per control on 8 vCPU | 3 min | 6.5 min | 10 min |
| LST-AI per case, 4 vCPU, `--segment_only` | paper: "1–2 min on a CPU-only system"; August: 19 cases in 2,280 s on e2-standard-8 including the 11 GB image pull (≈ 1.5–2 min/case; the ledger note "~7 min/case" does not match its own numbers) | 2 min | 4 min | 7 min |
| Setup per VM | env from locks, cached weights; Job 2 also pulls 11 GB | 0.25 h | 0.25–0.3 h | 0.35 h |

| Run | VM-hours (low / expected / high) | Wall clock per chunk | USD (low / expected / high) |
|---|---|---|---|
| Job 1 pilot (2 controls, 5 folds) | 0.6 / 0.8 / 1.0 (cap 2 h) | — | 0.11 / 0.14 / 0.18 |
| Job 2 pilot (2 cases) | 0.4 / 0.5 / 0.6 (cap 2 h) | — | 0.07 / 0.09 / 0.11 |
| Job 1 full, 100 controls, 3 VMs | 15.5 / 22.0 / 29.2 | 5.3 / 7.5 / 10 h | 2.85 / 4.05 / 5.39 |
| Job 2 full, 244 cases, 3 VMs | 9.0 / 17.2 / 29.4 | 3 / 5.8 / 10 h | 1.73 / 3.28 / 5.62 |
| **Total** | **25.5 / 40.5 / 60.2** | ≈ 13–14 h end to end (expected) | **4.8 / 7.6 / 11.3** (≈ 4.2 / 6.7 / 10.0 EUR) |

Storage after both jobs: ≈ 3.5 GB more (stripped images 1.2 GB, mirror 1.4 GB, LST-AI maps
≈ 0.5–1 GB) ≈ 0.07 USD/month. Every VM is capped by `--max-hours` (12 h guard) and
`--max-run-duration` (13 h hard stop): even if all six chunks and both pilots ran to their hard stop
the bill would be ≈ 16 USD. Credit used so far ≈ 0.22 EUR of the 240 EUR own cap.

## 4. Licences (checked 2026-10-17)

| Component | Licence | Source | Consequence |
|---|---|---|---|
| SibBMS data | "Creative Commons Attribution 3.0 International license (CC BY-NC-SA 3.0)" — name and abbreviation disagree; take the stricter **CC BY-NC-SA 3.0** | Tuchinov et al., medRxiv 10.1101/2025.08.14.25333741, §2.1.5; access "via a request-access form" (Data availability) | research and papers only; derived images/maps share-alike and non-commercial |
| HD-BET code | Apache-2.0 | github.com/MIC-DKFZ/HD-BET (`pyproject.toml`, repo licence) | free |
| HD-BET v2 weights (used by Job 1) | **CC BY-NC 4.0** | zenodo.org/records/14445620 ("HD-BET v1.5 parameters", md5 f97a36f8…) | non-commercial |
| HD-BET v1 weights (inside the LST-AI image, unused with `--stripped`) | CC BY 4.0 | zenodo.org/records/2540695 | — |
| FLAMeS weights | CC BY 4.0 | zenodo.org/records/17955359 | free with attribution |
| LST-AI code | MIT ("Copyright (c) 2023 Julian McGinnis") | github.com/CompImg/LST-AI LICENSE | free; README: "research-only tool … not validated, licensed or approved for any clinical usage" |
| LST-AI weights | released as assets of the MIT repository (v1.0.0/v1.1.0 `lst_data.zip`); no separate weights licence found | GitHub releases | treat as MIT; not verified with the authors |
| greedy | Apache-2.0 | github.com/pyushkevich/greedy | free |
| MSLesSeg | CC BY 4.0 | figshare 27919209 (published 2025-06-01) | free with attribution |
| Ljubljana (open_ms_data) | CC-BY | `cross_sectional/LICENSE.txt` | free with attribution |

The image also carries the NVIDIA CUDA base-image licence (`NGC-DL-CONTAINER-LICENSE`), TensorFlow
(Apache-2.0) and PyTorch (BSD): fine for internal research.

## 5. Contamination check for LST-AI (is any of our data in its training?)

- **Training data**: "an in-house dataset consisting of 491 paired 3D FLAIR and 3D T1-weighted
  images acquired on a 3.0 T Achieva scanner (Philips…)", TUM Munich (Wiltgen et al., *LST-AI: A
  deep learning ensemble for accurate MS lesion segmentation*, NeuroImage: Clinical 42 (2024) 103611,
  §2.1 and Table 1). Weights released 2023-11-29 (v1.0.0 `lst_data.zip`); the v1.1.0 asset that
  the image downloads has exactly the same size (387,820,340 bytes); the v2.0.0rc1 notes
  (2026-08-20) say the released weights were never changed.
- **MSLesSeg — not in training**: released 2024–2025 (Figshare 2025-06-01), after the weights; not
  among LST-AI's test sets either.
- **Ljubljana (open_ms_data, Lesjak 2018) — not in training, but it is one of LST-AI's published
  TEST sets** ("msljub", 30 subjects, Table 1, "dataset published by Laboratory of Imaging
  Technologies"). Clean for training; LST-AI's reported accuracy includes it. The paper describes no
  model selection on test data.
- **SibBMS — not in training**: released August 2025 (zip Last-Modified 2025-08-04; preprint
  2025-08-16), long after the weights.
- Not checked here: whether the Dec-2025 FLAMeS weights (Zenodo 17955359) saw SibBMS; the
  registry's FLAMeS training list (refs 12–14: ISBI, Ljubljana, MSSEG-2016) does not include it.

## 6. After the runs: dropping the outputs into lesion-detector v3

```bash
D=C:/tmp/mstool-cloud-out
gcloud storage cp -r $B/flames-ensemble/cohort $D/flames-ensemble/
gcloud storage cp -r $B/lstai/cohort $D/lstai/
gcloud storage cp -r $B/controls/sibbms $D/controls/
python research/cloud/stage_for_detector.py --download-root $D --out-root data/cohorts \
  --extend-controls-cohort data/cohorts/sibbms-controls-flames      # optional, see (3)
python research/lesion_detector_v3/build_features.py --folds-dir data/cohorts/all-flames-folds \
  --lstai-dir data/cohorts/all-lstai --control-flair-dir data/cohorts/sibbms-controls-flair
```

Things the detector side must know (I did not change its code):
1. **Names**: the builder reads `{case}_prob_f{k}.nii.gz`; the bucket (all FLAMeS runs, as
   specified) has `{case}_f{k}_prob.nii.gz`. `stage_for_detector.py` renames on copy. LST-AI and
   control FLAIR/T1 names already match. The builder takes one folder per option, so all cohorts
   go in one folder (case ids are unique).
2. **Fold-0 check will refuse uint8 maps**: `build_features.py` raises if fold 0 differs from
   `{case}_prob.nii.gz` by more than 1e-3, but uint8 storage alone gives up to 0.00196 — this hits
   the 145 MS cases of `flames-full-*` too. The tolerance needs to be ≥ 0.0025 (or the comparison
   made on Dice), or the maps stored as float32.
3. **70 new controls are invisible to the builder** unless they have `{case}_prob.nii.gz` and
   `{case}_gt.nii.gz` in `cohorts/sibbms-controls-flames` (it only enumerates that folder).
   `--extend-controls-cohort` adds them from fold 0 + the all-zero mask, never touching the 30
   August files, and lists them in `PROVENANCE_added.txt`.
4. The 30 August controls: fold 0 matches August only if HD-BET reproduces the August mask; the
   pilot measures this on sub-001.

## 7. Risks and what could not be verified locally

- **Not run anywhere**: no VM was started, so HD-BET-with-TTA time, LST-AI time and LST-AI memory
  on 4 vCPU / 16 GB are estimates (ranges above). Swap (8 GB / 16 GB) is a safety net and peak
  memory is recorded per case; the pilots decide.
- LST-AI behaviour was verified by reading its code at the exact commit in the image and the image
  layers, not by executing the image. Whether greedy writes the FLAIR-space maps with exactly the
  input affine is decided at run time (identity vs trilinear, recorded).
- Docker Hub: anonymous pulls are rate-limited; each VM pulls once. If Docker Hub fails, relaunch
  with `mirror-image=1` after one successful pull.
- ai.nsu.ru must be reachable on the first controls run (the pilot mirrors two controls; each chunk
  mirrors its own on first use). After that the bucket mirror is enough.
- The SibBMS request form's exact terms were not seen (only the paper's licence sentence).
- Side findings, not acted on: (a) the August LST-AI script (`docs/calm-ms/src/vm-startup.sh`)
  copied `*space-mni_seg-lst_prob_1.nii.gz`, i.e. **U-Net A alone in MNI space, not the ensemble**,
  as `{case}_prob_mni` — worth checking before reusing `cohorts/isbi19-lstai`; (b) the registry
  calls SibBMS "native space", but `Output/Norm` is a common 1 mm template grid.

## 8. Files

| File | Role |
|---|---|
| `research/cloud/vm_sibbms_controls_v2.sh` | Job 1 VM script |
| `research/cloud/sibbms_controls_prep.py` | Job 1 step 1: fetch/mirror, HD-BET, T1 on FLAIR grid, uploads, cases.json |
| `research/cloud/flames_ensemble_driver.py` | unchanged; Job 1 step 2 |
| `research/cloud/vm_lstai_maps.sh` | Job 2 VM script |
| `research/cloud/lstai_driver.py` | Job 2: case list, image checks, LST-AI per case, resampling, uploads |
| `research/cloud/job_common.py` | shared: selection, grids, trilinear, uint8 storage, blank check, memory |
| `research/cloud/check_outputs.py` | local pilot checks (no cloud calls) |
| `research/cloud/stage_for_detector.py` | local layout for `build_features.py` (no cloud calls) |
| `research/cloud/tests/` | 19 tests (`python -m pytest research/cloud/tests -q`) incl. the SibBMS index fixture and a dry run on local public data |
| `research/cloud/build_ledger.py` | now also reads `controls/cost`, `lstai/cost`, `lstai/manifests` |
| `docs/research/compute-ledger/annotations.json` | Spanish purposes for the planned run names |
