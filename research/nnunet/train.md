# Training the nnU-Net v2 base lesion segmenter on a free GPU

Exact commands to plan, preprocess, and train the base MS-lesion segmenter (FLAIR ±T1 →
binary lesion mask) on a **free GPU** (Kaggle 30 h/week P100 or T4×2; Colab T4). The trained
model produces the **probability map** that `infer_to_candidates.py` turns into CALM-MS
candidates — nnU-Net is the strong base; CALM-MS is the conformal precision dial on top.

**Target bar:** FLAMeS (single-FLAIR, nnU-Net-based, Zenodo `Dataset004_WML`) reports voxel
**Dice ≈ 0.74** on external MS test data. Treat 0.74 as the bar to match/beat, not a floor.
This replaces the legacy thesis segmenter (lesion **precision ≈ 0.22**).

---

## 0. Environment (Kaggle / Colab)

```bash
pip install nnunetv2            # pulls torch; on Kaggle/Colab torch+CUDA is preinstalled
# nnU-Net v2 needs three env vars (point them at persistent/scratch storage):
export nnUNet_raw="/kaggle/working/nnUNet_raw"
export nnUNet_preprocessed="/kaggle/working/nnUNet_preprocessed"
export nnUNet_results="/kaggle/working/nnUNet_results"
mkdir -p "$nnUNet_raw" "$nnUNet_preprocessed" "$nnUNet_results"
```

Kaggle/Colab sessions are time-limited (Kaggle ≤ 12 h/session, 30 h/week GPU; Colab ~12 h).
Training a single 3d_fullres fold to nnU-Net's default 1000 epochs will **not** finish in one
session — see the epoch cap and checkpoint-resume notes in §4.

---

## 1. Build the dataset (from the converter in this folder)

Convert a pooled/standalone public dataset into nnU-Net v2 raw format:

```bash
python dataset_conversion.py \
  --root /path/to/pooled_or_public_dataset \
  --layout mslesseg \               # or: isbi | msseg | ljubljana | generic
  --dataset-id 501 --dataset-name MSLesionFLAIR \
  --with-t1                         # omit for single-FLAIR (the FLAMeS-style setup)
```

This writes `$nnUNet_raw/Dataset501_MSLesionFLAIR/{imagesTr,labelsTr,dataset.json}`.
Single-FLAIR (`channel_names={"0":"FLAIR"}`) matches the FLAMeS reference and is the most
portable clinically; add `--with-t1` only if every case has a co-registered T1.

Verify integrity before planning:

```bash
nnUNetv2_plan_and_preprocess -d 501 --verify_dataset_integrity
```

---

## 2. Plan + preprocess (produces the dataset fingerprint)

`nnUNetv2_plan_and_preprocess` extracts the **dataset fingerprint** (spacings, shapes,
intensity distribution, class ratios) and derives the network topology, patch size, batch
size, and normalization automatically:

```bash
nnUNetv2_plan_and_preprocess -d 501 -c 3d_fullres --verify_dataset_integrity
```

Inspect the fingerprint / plan (commit these for reproducibility):

```
$nnUNet_preprocessed/Dataset501_MSLesionFLAIR/dataset_fingerprint.json
$nnUNet_preprocessed/Dataset501_MSLesionFLAIR/nnUNetPlans.json
```

MS FLAIR volumes are typically resampled to ~1×1×1 mm (or the dataset median spacing).
For **CALM-MS calibration** the probability maps you later feed to `build_null_bundle.py`
must all share one grid/spacing (the null asset enforces this) — training on MNI-1mm-
registered data, or resampling predictions to a common grid, keeps that invariant.

---

## 3. Configuration and folds

* **Configuration:** `3d_fullres` (best accuracy for 3D lesion volumes; `3d_lowres` /
  cascade is unnecessary at MS FLAIR resolutions and not worth the extra training on a
  free GPU).
* **Folds:** nnU-Net uses 5-fold CV (`0..4`). On a free GPU, train **fold 0** first for a
  working single model; add more folds only if time allows, then ensemble (§5). Report which
  folds were trained — a single fold is a valid, honestly-scoped model.

---

## 4. Train (3d_fullres) with a free-GPU-friendly epoch cap

Default nnU-Net is 1000 epochs (~ many GPU-hours; will not fit one free session). Use a
**shorter trainer variant** and resume across sessions with `--c`:

```bash
# ~250-epoch variant — fits better in Kaggle's weekly budget; expect a few % Dice below the
# full 1000-epoch run. Good enough to clear the "beat legacy 0.22-precision" bar and to
# stand up the CALM-MS stack end to end.
nnUNetv2_train 501 3d_fullres 0 -tr nnUNetTrainer_250epochs

# resume the SAME fold after a session times out (checkpoints auto-saved each ~50 epochs):
nnUNetv2_train 501 3d_fullres 0 -tr nnUNetTrainer_250epochs --c
```

If you have the weekly budget, use the default trainer for the target-bar result:

```bash
nnUNetv2_train 501 3d_fullres 0            # default nnUNetTrainer (1000 epochs)
```

**Expected runtime (order-of-magnitude, single fold, 3d_fullres, ~1 mm FLAIR):**

| GPU (free tier) | per-epoch | 250 epochs | 1000 epochs |
| --- | --- | --- | --- |
| Kaggle P100 16 GB | ~3–6 min | ~half a day (2–4 sessions) | ~2–4 days (span the week + `--c`) |
| Kaggle T4 ×2 | ~4–7 min | similar | plan for multi-session resume |
| Colab T4 16 GB | ~5–8 min | ~1 day (2–3 sessions) | not practical on free Colab |

Numbers scale with case count, patch size, and cases-per-epoch; read the live per-epoch time
nnU-Net prints and re-estimate. Save `$nnUNet_results` to persistent storage (Kaggle dataset
/ Google Drive) between sessions so `--c` can resume.

---

## 5. (Optional) more folds + ensemble + best configuration

```bash
for f in 1 2 3 4; do nnUNetv2_train 501 3d_fullres $f -tr nnUNetTrainer_250epochs; done
nnUNetv2_find_best_configuration 501 -c 3d_fullres      # picks folds/postproc to ensemble
```

---

## 6. Predict WITH PROBABILITIES (the CALM-MS bridge input)

The `--save_probabilities` flag is **required** — CALM-MS consumes the soft posterior, not
the argmax mask:

```bash
nnUNetv2_predict \
  -i /path/to/imagesTs -o /path/to/predsTs \
  -d 501 -c 3d_fullres -f 0 \
  --save_probabilities
```

Each case yields `<CASE>.nii.gz` (argmax seg) **and** `<CASE>.npz` (`probabilities`,
shape `(2, *grid)`; class 1 = lesion). Then:

```bash
# per-case candidates + CALM-MS cohort (_prob.nii.gz) for calibration:
python infer_to_candidates.py \
  --prob /path/to/predsTs/CASE.npz --reference /path/to/predsTs/CASE.nii.gz \
  --gt /path/to/gt/CASE.nii.gz \
  --out-candidates out/CASE_candidates.json \
  --out-cohort data/cohorts/nnunet-mslesseg

# build the conformal null from that cohort (existing repo script), then select:
python ../../scripts/calm-ms/build_null_bundle.py       # -> calm_ms_null_*.npz
python infer_to_candidates.py --prob predsTs/CASE.npz --reference predsTs/CASE.nii.gz \
  --calib-null <null>.npz --alpha 0.1 --out-mask out/CASE_conformal.nii.gz
```

See `README.md` for the full download → convert → train → infer → conformal → benchmark
recipe and `benchmark.py` for scoring on the public leaderboards.
