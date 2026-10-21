# FLAMeS-thick — pre-registered protocol

*Research code and research findings, not the medical device (IEC 62304 scope excludes `research/`).*
*Written 2026-10-21 on branch `research/flames-thick`, committed **before any training or evaluation
run exists**. No model in this study has been trained when this file is first committed; every later
change is logged in §14 with its date and whether any result existed at that time.*

## 1. Question and rationale

Paper A v0.3 (`docs/research/paper/RESULTS-v0.3.md`, branch `research/paper-a-v0.3`, PR #54) found
that FLAMeS (nnU-Net v2, single FLAIR) loses small lesions on real thick-slice 2D FLAIR: 50 %
detection needs ≥ 50 mm³ on 4.5–8.3 mm slices versus ≥ 14 mm³ on 1-mm scans, no size reaches 80 %
detection on thick slices, and thick-slice sites produce more very-confident false candidates.
The super-resolution study (`reports/Superresolución en resonancia para MSTool.md`, local, untracked)
recommends, instead of a super-resolution front end, teaching the segmenter to read thick slices
(MindGlide recipe: random slice thickening during training).

**Question.** Does fine-tuning FLAMeS (fold-0 weights) on MSLesSeg-train with on-the-fly simulated
thick-slice acquisition improve lesion-wise detection on *real* thick-slice FLAIR from sites it has
never seen, without losing performance on ~1 mm FLAIR?

## 2. Hypotheses

- **H1 (primary, co-primary outcomes).** On the pooled thick-slice evaluation sites (MS3SEG, Muslim,
  PediMS; §7), arm A (FLAMeS-thick) has a higher mean per-scan lesion-wise F1 than the reference R
  (original FLAMeS fold 0), **and** does not raise the mean number of false lesions per scan by more
  than 10 %.
- **H2 (key secondary, non-inferiority at ~1 mm).** On the ~1-mm-delivered sites (Ljubljana clean-10,
  MSLesSeg test), arm A is non-inferior to R in per-scan Dice and lesion-wise F1 (margins §9.2).
- **H3 (mechanism, secondary).** The gain of A over R on thick sites is larger than the gain of the
  control arm B (same fine-tuning without thickening) over R, i.e. it comes from the thick-slice
  augmentation and not only from fine-tuning on new data/labels.

## 3. Arms

| arm | what | produced by |
|---|---|---|
| **R** (reference) | FLAMeS fold 0, unchanged (`Dataset004_WML`, `nnUNetTrainer_8000epochs`, `checkpoint_final.pth`, SHA-256 `4fc7db24e7c1541b59023df2a2f498a964eb629fe38f4eaec763297dd3fdf861`) | existing maps `data/cohorts/cloud-2026-10/flames/{case}_f0_prob.nii.gz` (runs flames-full-a/b/c, flames-extra-a/b; same driver, same inputs) |
| **A** (FLAMeS-thick) | R's weights fine-tuned on MSLesSeg-train with the thick-slice augmentation (§5.3) | trainer `nnUNetTrainerFLAMeSThick` |
| **B** (FLAMeS-FT, control) | identical to A except the thick-slice augmentation is off (p = 0) | trainer `nnUNetTrainerFLAMeSFT` |
| E (context only) | FLAMeS 5-fold ensemble (mean probability) | existing maps `{case}_f{0..4}_prob.nii.gz` |

A and B share every other setting, the same split, the same initial weights and the same GPU type.
The primary comparison is **A vs R** (same fold, as required). B and E are secondary.

## 4. Training data

- **Only MSLesSeg TRAIN** (Figshare `10.6084/m9.figshare.27919209.v1`, file 52771814
  "MSLesSeg Dataset.zip", 1 473 284 755 bytes, md5 `cb30cfb13b0981443c300a5e51dd91cd`; mirrored with
  SHA-256 at `gs://mstool-research-data/inputs/mslesseg_52771814.zip`): patients P1–P53, 93 scans
  (`train/P{n}/T{k}/P{n}_T{k}_{FLAIR,MASK}.nii.gz`, MNI 1 mm, 182 × 218 × 182, LAS, skull-stripped).
  FLAIR only; MASK binarised at 0.5 and stored as uint8 with the FLAIR's geometry.
- **Why MSLesSeg-train only.** (1) FLAMeS never trained on MSLesSeg (fingerprint check:
  `2026-10-17_mslesseg_flames_overlap_check`, 0 of 115 matches), so it adds new information;
  (2) CC BY 4.0 allows derivative weights with attribution; (3) it has an official train/test split,
  so the test split stays a clean held-out ~1-mm-delivered site; (4) the thick-slice sites must stay
  untouched because they are the pre-registered evaluation; (5) the 20 FLAMeS-trained Ljubljana scans
  add nothing FLAMeS has not seen, the 10 clean ones are evaluation data; (6) the other candidate
  sources are non-commercial (SibBMS, MSSEG/Shifts/OFSEP), FLAMeS training data (ISBI-2015, MSSEG-2016)
  or held-out sites.
- **Never used for training (hard-coded guard, unit-tested, `flames_thick/data_prep.py`):**
  MS3SEG, Muslim, PediMS, every Ljubljana scan (in particular the clean patients 16–20 and 26–30),
  MSLesSeg test (P54–P75), SibBMS controls. The guard raises before any file is written.
- **Native thickness of MSLesSeg (finding while writing this protocol).** The dataset's own
  `info_dataset/patient_scanners_info/patient_scanners_info_FLAIR.csv` lists the native FLAIR slice
  thickness: train 2–5 mm (2–2.3 mm: 31 scans, 3 mm: 49, 4–5 mm: 8, unknown: 5), test 2–5 mm
  (2–2.3 mm: 12, 3 mm: 3, 4–5 mm: 7). Both 2D (TR 8000–11000 ms) and 3D (TR 4800, TE ≈ 300 ms)
  FLAIR are present. MSLesSeg is therefore "1-mm-delivered" (registered to MNI 1 mm), not 1-mm
  acquired; the only truly thin site is Ljubljana (3D FLAIR 0.47 × 0.47 × 0.8 mm). The simulated
  thickening is applied on top of the delivered images (effective thickness ≥ the simulated one).
  The Figshare record also holds `MSLesSeg_RAW.zip` (native space) — not used here.
- **Internal split (monitoring only).** Patients P1–P53 sorted numerically, permuted with
  `numpy.random.RandomState(12345)`, cut into 5 groups with `numpy.array_split`; fold 0 trains on
  groups 1–4 (≈ 42 patients) and validates on group 0 (≈ 11 patients). No patient is in both. The
  internal validation (thin, unaugmented) only monitors forgetting; it never selects a checkpoint.

## 5. Training procedure (identical for A and B except §5.3)

### 5.1 Initialisation and plans
- FLAMeS `plans.json` and `dataset.json` from the Zenodo release (CC BY 4.0, `10.5281/zenodo.17955359`
  v2.0, zip md5 `8b90b789d6ceca1886f42fa1724a08cc`, mirrored at `inputs/flames_weights.zip`) are
  transferred unchanged to `Dataset501_MSLesSegFT` (`nnUNetv2_move_plans_between_datasets`), so
  preprocessing, spacing (1.0 × 0.9 × 0.9 mm after transpose `[2, 0, 1]`), patch (112 × 128 × 160),
  batch (2), normalisation (z-score in the non-zero mask) and architecture (6-stage PlainConvUNet,
  32–320 features, deep supervision) are FLAMeS's own.
- **All** weights of fold 0, including the segmentation heads, are loaded strictly (nnU-Net's own
  `-pretrained_weights` re-initialises the heads, so it is not used). The trainer refuses to start
  from random weights (it raises unless weights came from FLAMeS or from a resume checkpoint).

### 5.2 Schedule (justified in §6 and RUNBOOK §2)
- **300 epochs** × 250 iterations (batch 2) = 150 000 patch presentations; 50 validation iterations
  per epoch; SGD Nesterov momentum 0.99, weight decay 3e-5 (nnU-Net defaults); initial LR **1e-3**
  (10 × below nnU-Net's from-scratch 1e-2) with a linear warm-up over 5 epochs (LR × (e + 1)/5)
  then polynomial decay (exponent 0.9) to 0 at epoch 300; mixed precision (fp16 autocast + grad
  scaler); `torch.compile` off; nnU-Net's default augmentation kept unchanged; oversampling of
  foreground 0.33. The model evaluated is `checkpoint_final.pth` (no best-epoch selection).
- Checkpoint every 5 epochs to `gs://mstool-research-data/flames-thick/train/<run>/`; preemption →
  automatic resume from the last checkpoint (the epoch counter, optimiser, grad scaler and logs
  resume; the data loader restarts, so training is not bit-reproducible — nnU-Net training never is).
- Budget stop rule: if the cost guard (§6) stops a run before epoch 300, the last checkpoint is
  evaluated and labelled "truncated at epoch k" (deviation). Below epoch 150 the arm is not evaluated.
- One timing-only exception: if the pilot (RUNBOOK §3) measures that 300 epochs would cost more than
  15 USD per arm at the chosen GPU, the epoch count becomes floor(15 USD / measured cost per epoch)
  (never below 150) for **both** arms, decided and logged in §14 before the full runs start. Timing
  is not an outcome.

### 5.3 Thick-slice augmentation (arm A only) — `flames_thick/thick_slice.py`, `transforms.py`
Physical model of a 2D multi-slice acquisition, applied to the image of each training sample after
nnU-Net's spatial transform (rotation/scaling/crop) and before its intensity transforms:

| parameter | pre-registered distribution |
|---|---|
| applied to a sample | probability **2/3** (1/3 of samples stay thin, to keep ~1-mm performance) |
| slice axis | anatomical axial 0.8 · coronal 0.1 · sagittal 0.1 (axes resolved from the training images' direction cosines and the plans' transpose; all MSLesSeg cases share one orientation, checked at start) |
| slice thickness T | uniform 3–8 mm |
| inter-slice gap G | with probability 0.5: uniform 0–0.5 T; else 0. Slice spacing S = T + G, capped at 10 mm |
| slice grid phase | uniform in [0, S) mm |
| slice profile | box of width T (p 0.5) or Gaussian with FWHM = T (p 0.5); weights integrate the profile over each voxel's extent and are renormalised inside the patch |
| back to the training grid | nearest slice (p 0.7) — what nnU-Net's own preprocessing does at inference for anisotropic input (out-of-plane order 0) — or linear between slice centres (p 0.3) |
| in-plane | unchanged |
| labels | **untouched** (the target stays the thin expert mask) |

Unit tests (`research/flames_thick/tests/test_thick_slice.py`): thickness of the point-spread
function, gaps really unseen, no shift (a linear ramp is reproduced exactly by box/Gaussian
averaging + linear resampling; nearest resampling errs by ≤ S/2), mean preserved, output shape and
dtype, the segmentation passes through bit-identical, the image never depends on the segmentation,
probability of application, axis mapping from direction cosines.

## 6. Compute (details, commands and cost ranges: `RUNBOOK.md`)
*Superseded on 2026-10-21 (before any study run) by Kaggle's free T4 GPUs — §14 and RUNBOOK §10.*
- Vertex AI CustomJob, us-central1, **Spot** (preemptible) GPU quota of `mstool-research` only.
  GPU chosen by estimated cost per finished epoch: **NVIDIA T4** on n1-standard-8 (≈ 0.43 USD/h
  catalogue Spot price; ≈ 195–310 s/epoch → 0.023–0.037 USD/epoch), A100 a close alternative
  (≈ 2.23 USD/h; ≈ 44–66 s/epoch → 0.027–0.041 USD/epoch). The pilot measures the T4 (and optionally
  the A100) and the cheaper measured USD/epoch is used for both arms.
- Hard guards per arm: Vertex `scheduling.timeout`, an in-container cumulative-cost guard
  (catalogue rate × 1.15 safety factor for a possible Vertex premium, plus 5 min per attempt for
  start-up), max 15 USD per arm, and checkpoint/resume after preemption.
- Evaluation: CPU VM (n2d-standard-4, standard provisioning, same conventions and frozen
  environment as the v2 FLAMeS jobs) running `flames_ensemble_driver.py`.

## 7. Evaluation data (211 scans, fixed now)

| site | scans / patients | slice spacing | role |
|---|---|---|---|
| MS3SEG (`ms3seg_001…100`) | 100 / 100 | 6.0–8.1 mm | thick (primary) |
| Muslim 2022 (51 axial, default fetch) | 51 / 51 | 4.86–8.3 mm | thick (primary) |
| PediMS (`pedims_P1_T1…`) | 28 / 9 | 3.9 mm | thick (primary) |
| Ljubljana clean-10 (`openms_patient16–20, 26–30`) | 10 / 10 | 1 mm (3D FLAIR, MNI) | ~1 mm (H2) |
| MSLesSeg test (`mslesseg_P54…P75`) | 22 / 22 | 1 mm MNI (native 2–5 mm) | ~1-mm-delivered (H2; in-domain for A/B) |

Inputs are exactly those of the reference maps: open_ms_data MNI and MSLesSeg from the bucket
mirrors; MS3SEG/Muslim skull-stripped brains cached at `inputs/extra_stripped/{case}_flair_brain.nii.gz`
(HD-BET once, reused), PediMS distributed stripped; extra-cohort raw data from
`inputs/extra_cohorts_raw_v1.tar.gz` (docs/research/cohorts-extra.md §6). The evaluation job
records the SHA-256 of every input; the analysis aborts if any differs from the reference run
manifests. Inference: nnU-Net predictor, fold 0 only, tile step 0.5, Gaussian weighting, **no
test-time mirroring**, CPU, probability of the lesion class stored as uint8 NIfTI on the FLAIR
grid (max error 0.002) — the same settings as R.

## 8. Outcomes (definitions copied from Paper A v0.3 so numbers are comparable)

- Binary prediction = probability ≥ 0.5. Lesions = 18-connected components ≥ 3 mm³ (prediction and
  expert mask alike). One-to-one matching = Hungarian maximum IoU with IoU > 0 (lenient, primary);
  IoU ≥ 0.10 (strict) as sensitivity analysis.
- Per scan: TP = matched pairs, FP = unmatched predicted lesions (**false lesions**), FN = unmatched
  expert lesions. **Lesion-wise F1** = 2TP / (2TP + FP + FN) (= 1 when TP + FP + FN = 0).
  **Dice** = voxel Dice of the binary prediction and the expert mask on the FLAIR grid.
- Detection by size: expert lesions in volume bins [3, 14), [14, 50), [50, 150), [150, 500),
  ≥ 500 mm³; sensitivity per bin; **minimum reliable lesion size** = the smallest bin from which
  sensitivity is ≥ 0.5 (and ≥ 0.8) in that bin and every larger bin.
- Thickness bands by slice spacing (largest voxel side): B1 ≤ 1.5 mm, B2 1.5–4.5, B3 4.5–6.5, B4 > 6.5.

## 9. Analysis and decision rules

Unit of resampling: patient (PediMS by child; all other sites one scan per patient in the
evaluation set). Paired percentile bootstrap over patients, B = 10 000, seed 20261021. Code:
`research/flames_thick/analysis.py` (unit-tested on synthetic volumes before any map exists).
All 211 scans must have a map for every arm; a missing or failed map is re-run, never dropped
(a forced exclusion is a logged deviation).

### 9.1 H1 (primary) — pooled thick sites (179 scans, 160 patients), A vs R
- ΔF1 = mean over scans of (F1_A − F1_R); FP ratio = mean FP_A / mean FP_R.
- **Success**: ΔF1 95 % CI lower bound > 0 **and** ΔF1 ≥ +0.03 (smallest effect of interest)
  **and** FP-ratio 95 % CI upper bound ≤ 1.10. Both outcomes must pass (intersection–union test, no
  multiplicity correction needed).
- **Refuted**: ΔF1 95 % CI upper bound < +0.03, **or** FP-ratio 95 % CI lower bound > 1.10.
- Otherwise **inconclusive**. Each thick site is also reported separately; a success with a site
  whose ΔF1 CI upper bound is < 0 is reported as "success with harm at <site>".

### 9.2 H2 — ~1-mm non-inferiority, A vs R
- Pooled Ljubljana clean-10 + MSLesSeg test (32 scans): ΔDice 95 % CI lower bound > −0.02 **and**
  ΔF1 95 % CI lower bound > −0.03.
- Guard-rail for the truly thin site (MSLesSeg test is in-domain for A): Ljubljana clean-10 point
  estimates ΔDice ≥ −0.02 and ΔF1 ≥ −0.03 (no CI requirement, n = 10).
- Verdict: non-inferior / not shown. A model that fails H2 is "not deployable" whatever H1 says.

### 9.3 Secondary (estimates with 95 % CI; no verdicts unless stated)
- S1 Detection by size bin per thickness band and per arm; minimum reliable lesion size per band
  (expected direction: A lowers the 50 % size on B3/B4 below 50 mm³).
- S2 Per-scan Dice, lesion-wise sensitivity and precision, false lesions per scan, per site.
- S3 (H3) A vs B on the pooled thick sites: ΔF1 (A − B) and FP ratio; "augmentation effect shown" if
  the ΔF1 (A − B) CI lower bound > 0.
- S4 A vs E (5-fold ensemble) on thick sites: can one robust model match the ensemble?
- S5 MSLesSeg test stratified by native slice thickness (≤ 3 mm vs 4–5 mm, from the dataset CSV).
- S6 Strict matching (IoU ≥ 0.10) and PediMS without patient P9 (Baló) for H1.
- S7 Internal-validation pseudo-Dice per epoch (thin, in-domain) — forgetting check.

### 9.4 Not part of this study
Synthetic thickening of 1-mm test scans (circular for A) and conformal calibration of the new
model (Paper A machinery) need their own pre-registration amendment before they are run.

## 10. What is reported
Every pre-registered number, whatever its direction, in `docs/research/flames-thick/RESULTS.md`
with the records (`docs/research/records/<date>_flames_thick_*.json`), the training curves, the
compute ledger rows and every deviation. Negative or inconclusive results are stated as such.

## 11. Pre-stated limitations
- Site, thickness, scanner, population and annotation protocol are confounded at the thick sites
  (Paper A §9); B controls for "fine-tuning on MSLesSeg labels", not for every confound.
- Muslim in-plane pixel size is estimated (±5 %); PediMS has 9 children; Ljubljana-10 is small.
- MSLesSeg (training data) is itself 2–5 mm native resampled to MNI; the simulation is applied on
  top of that blur. MSLesSeg annotation style may transfer to A/B (and help or hurt elsewhere).
- 3D connected components on 4–8 mm slices can merge or split lesions (same rule for every arm).
- One fold only (fold-0 init); variance across folds or training seeds is not estimated.

## 12. Licences and attribution
- FLAMeS weights: CC BY 4.0 (Zenodo `10.5281/zenodo.17955359`, live record checked 2026-10-21).
  Derived weights (A, B) must state: "Fine-tuned from FLAMeS fold 0 (Dereskewicz et al., J
  Neuroimaging 2025; F. La Rosa, Zenodo 10.5281/zenodo.17955359, CC BY 4.0) on MSLesSeg-train with
  thick-slice augmentation; changes by MSTool-AI."
- MSLesSeg: CC BY 4.0 (Figshare `10.6084/m9.figshare.27919209.v1`, live record checked 2026-10-21);
  Guarnera F, Rondinella A, Crispino E, et al., Sci Data 2025.
- Evaluation only (no derivative of the data is distributed): MS3SEG CC BY 4.0, Muslim 2022 CC BY 4.0,
  PediMS CC BY 4.0 (docs/research/cohorts-extra.md §2); open_ms_data (Lesjak 2018) CC BY.
- nnU-Net v2 Apache-2.0; HD-BET weights non-commercial (only used to strip evaluation inputs, as
  in Paper A; not part of the trained model).

## 13. Software
nnunetv2 2.8.1, torch 2.14.1 (CUDA 12.6 build for training, CPU build for evaluation),
batchgeneratorsv2 0.3.6, numpy 2.2.6 — the frozen lock of the v2 FLAMeS jobs
(`research/flames_thick/requirements-gpu.lock`); Python 3.10.12 (Ubuntu 22.04).

## 14. Change log
| date | change | results existing at that time |
|---|---|---|
| 2026-10-21 | first version | none (no training or evaluation run launched) |
| 2026-10-21 | **Compute platform: Kaggle instead of Vertex AI (§6).** Google Cloud blocks every GPU job in mstool-research (Vertex AI preemptible quota 1 CPU, increases auto-denied; Compute Engine GPU quota 0). Training runs on Kaggle's free GPUs (account nicolasbonilna, private kernels; RUNBOOK §10). Unchanged: GPU model (NVIDIA T4 16 GB), trainers, schedule (§5.2), augmentation (§5.3), split, initial weights, checkpoint every 5 epochs, supervisor/worker code path, frozen lock + Python 3.10.12 (installed with uv on Kaggle's image; no pin differs), run ids `flames-thick-a` / `flames-thick-b`. Different: (a) both arms train side by side in every session, one T4 each (same hardware and same time for A and B); (b) Kaggle sessions last ≤ 12 h, so each run PAUSES at a soft session deadline (11 h; resumable checkpoint written) and the next session — a new private kernel that mounts the previous kernel's output — resumes it, exactly like the pre-registered Spot-preemption resume (data loader restarts); (c) the cost guard is replaced by the free weekly GPU quota (0 USD); (d) 4 vCPU per session (nnU-Net data augmentation: its default 4 processes per arm); (e) inputs are private Kaggle datasets holding byte-identical copies of the FLAMeS fold-0 files and of the 186 MSLesSeg-TRAIN FLAIR/MASK members, each SHA-256-checked at every session; the source zips were re-downloaded from Zenodo and Figshare and matched the publishers' size and md5 (SHA-256 `943f49d4…c277` and `7a32c860…4db5`, to compare with the bucket sidecars). | none (no study model trained; only the Kaggle pilot, 2 training scans) |
| 2026-10-21 | **Kaggle pilot and epoch count.** Pilot (2 scans, 6 short epochs, two sessions; `docs/research/flames-thick/kaggle/`): every mechanical check passed — SIGKILL after epoch 0 and in-session resume at epoch 1 (arm A), forced pause after epoch 1 and resume at epoch 2 in a new session (both arms), input hashes, FLAMeS SHA-256, MSLesSeg-train only, axial = patch axis 1, export, GPU self-test. Measured side by side on 2 × T4: arm A 0.904 s/iteration (240.5 s per 250-iteration epoch), arm B 0.796 (212 s). Rule for Kaggle, fixed now in place of the 15-USD rule of §5.2: E = 300 if the projected quota hours (both arms side by side at the slower arm's pace + 8.3 min set-up and 10 min hand-over per session + 30 min final validation) fit the GPU quota left this week minus 1 h, else the largest E ≥ 150 that fits, the same for both arms. Projection 21.2 h ≤ 28.7 h → **E = 300 for both arms (§5.2 unchanged).** | pilot models only (not study models) |
| 2026-10-21 | **Pilot criterion "pseudo-Dice > 0.5 on the internal scan" (RUNBOOK §3d) not met; replaced before any study run.** Internal pseudo-Dice 0.19–0.30 and final validation Dice 0.21 (A) / 0.24 (B) on `mslesseg_P2_T1`. Not a GPU fault: unchanged FLAMeS fold 0 run on the T4 reproduces the CPU reference map of P2_T1 (max \|Δp\| 0.017, 1 of 7.2 M voxels on the other side of 0.5, Dice 0.524 both). The bar was mis-calibrated: unchanged FLAMeS itself scores 0.524 on P2_T1, and the pilot fine-tunes on ONE scan (P1_T1, 360 iterations), after which it over-segments P2_T1 (12.5–14.5 k voxels vs 5.6 k unchanged and 2.3 k expert). Replacement checks: (1) the GPU sanity map above (repeated in the first full session); (2) an early look after a short first full session (≤ 1.5 h, full data): stop and investigate — do not continue — if either arm's internal-validation pseudo-Dice (15 scans of 11 patients; unchanged FLAMeS on them: mean whole-scan Dice 0.689, pooled 0.737) is < 0.5 at its last recorded epoch, or if arm A's measured epoch exceeds 300 s (then E is recomputed with the rule above before continuing); (3) the final-validation bar of RUNBOOK §4 (Dice ≥ 0.5) unchanged. | pilot models only (not study models) |
