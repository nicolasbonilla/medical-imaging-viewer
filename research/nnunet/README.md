# nnU-Net base lesion segmenter + CALM-MS conformal control

A reproducible, GPU-ready **nnU-Net v2** MS-lesion segmenter (FLAIR ±T1 → binary lesion
mask) that plugs **underneath** the repo's already-shipped, model-agnostic **CALM-MS**
conformal precision-control layer. nnU-Net is the strong probabilistic *base*; CALM-MS is
the *dial* that turns its probability map into a lesion set with a guaranteed false-discovery
rate. Together they replace the legacy thesis segmenter (lesion **precision ≈ 0.22**,
Dice ≈ 0.52) with a modern base whose over-segmentation is provably controlled.

> **This environment is CPU-only.** Training/prediction runs on a free GPU (Kaggle/Colab).
> The three non-GPU stages — dataset conversion, candidate/conformal bridging on a given
> probability map, and benchmarking — are real, importable, and covered by a synthetic CPU
> test (`test_pipeline.py`, all green). Nothing here is trained locally.

## Why this fits the repo without changing it

The CALM-MS layer (`backend/app/services/calm_ms_inference.py`,
`calm_ms_lesion_features.py`, `conformal_lesion_fdr.py`) is **model-agnostic**: it consumes a
per-voxel probability map, extracts 18-connected lesion **candidates** with a pooled score,
computes 14 contractual per-candidate features, and selects an FDR-controlled subset. This
package imports those exact functions (via `_bridge.py`) instead of re-implementing them, so
the nnU-Net output is, by construction, the format CALM-MS already calibrates against — the
same format the shipped `scripts/calm-ms/build_null_bundle.py` and
`build_lesion_scorer_asset.py` consume (`data/cohorts/<sub>/<case>_prob.nii.gz` + `_gt.nii.gz`).

## Files

| File | Role | GPU? |
| --- | --- | --- |
| `dataset_conversion.py` | Public datasets → nnU-Net v2 raw (`imagesTr/labelsTr/dataset.json`) | no |
| `train.md` | Exact `nnUNetv2_*` plan/preprocess/train commands for a free GPU | GPU |
| `infer_to_candidates.py` | Trained nnU-Net (or any prob map) → CALM-MS candidates + cohort + conformal mask | no |
| `benchmark.py` | Voxel Dice + lesion-wise TPR/PPV/F1 (18-conn, ISBI/MSSEG); CSV+MD table | no |
| `_bridge.py` | Imports the CALM-MS layer + repo metrics (vendored metric fallback) | no |
| `test_pipeline.py` | Tiny synthetic CPU test for all non-GPU parts | no |

## The full recipe

### 1. Download the public datasets — **requires registration**
The MS-lesion leaderboards are **not** open downloads; you must register/agree to terms:
* **MSLesSeg** (ICPR-2024, multi-center; FLAMeS-independent external test) — the recommended
  primary set; the repo's CALM-MS null is already scoped to its acquisition distribution.
* **ISBI-2015** Longitudinal MS Lesion Segmentation Challenge.
* **MSSEG-2016** (Commowick et al.) — the 18-connectivity + 3 mm³ evaluation convention this
  repo follows (RC-030).
* **Ljubljana** 3D-FLAIR MS lesion dataset.

Optional upstream: `research/data_pipeline` (if present) can pool/register/resample several of
these to a common MNI grid; `dataset_conversion.py` reads its folder-per-case output with
`--layout generic`. Otherwise point the converter at any single dataset's own layout.

### 2. Convert → nnU-Net v2 raw
```bash
export nnUNet_raw=... nnUNet_preprocessed=... nnUNet_results=...
python dataset_conversion.py --root <dataset_root> --layout mslesseg \
  --dataset-id 501 --dataset-name MSLesionFLAIR      # add --with-t1 if T1 is available
```

### 3. Train on a free GPU
Follow **`train.md`**: `nnUNetv2_plan_and_preprocess -d 501 -c 3d_fullres`, then
`nnUNetv2_train 501 3d_fullres 0` (use the 250-epoch trainer + `--c` to resume across
Kaggle/Colab session limits). **Target bar: FLAMeS single-FLAIR Dice ≈ 0.74.**

### 4. Predict with probabilities → CALM-MS candidates
```bash
nnUNetv2_predict -i imagesTs -o predsTs -d 501 -c 3d_fullres -f 0 --save_probabilities
python infer_to_candidates.py --prob predsTs/CASE.npz --reference predsTs/CASE.nii.gz \
  --gt gt/CASE.nii.gz --out-candidates out/CASE_candidates.json \
  --out-cohort data/cohorts/nnunet-mslesseg
```
`--out-cohort` writes the `<case>_prob.nii.gz` (+ `_gt.nii.gz`) that the repo's calibration
scripts glob for — no downstream change needed.

### 5. CALM-MS conformal precision control
Build the conformal null from the cohort, then select at a clinician-set FDR α:
```bash
python ../../scripts/calm-ms/build_null_bundle.py            # -> calm_ms_null_*.npz
python infer_to_candidates.py --prob predsTs/CASE.npz --reference predsTs/CASE.nii.gz \
  --calib-null <null>.npz --alpha 0.1 --out-mask out/CASE_conformal.nii.gz
```
The conformal mask is the FDR≤α risk-controlled lesion set (`select_lesions_conformal`).
α is the false-positive-tolerance dial; per RC-CALM-2 no per-lesion "confidence" is exposed.

### 6. Benchmark on the leaderboard metrics
```bash
python benchmark.py --pred-dir predsTs --ref-dir gt --spacing 1 1 1 \
  --out-csv benchmark_results.csv --out-md benchmark_results.md
```
Reports voxel **Dice** + lesion-wise **TPR/PPV/F1** (18-connectivity, ISBI any-voxel /
MSSEG overlap gate via `--min-overlap`), per-case and aggregated (macro means + micro pooled
F1). Score the **raw nnU-Net argmax** and the **CALM-MS conformal** mask to show the
precision the conformal dial buys.

## Verify (CPU, no GPU, no downloads)
```bash
cd research/nnunet
python test_pipeline.py          # or: pytest test_pipeline.py
```

## Honest scope
* **Training and prediction need a GPU.** Only the bridging/benchmark stages run on CPU here.
* **Leaderboard data needs registration** — none of it is redistributed in this repo.
* **CALM-MS exchangeability:** the conformal null must be built from cases on the *same grid*
  and from a base model *independent of the calibration cohort's training set* (the repo's
  v2 null is FLAMeS-decontaminated to MSLesSeg-only). A new nnU-Net base means rebuilding the
  null against **its** false-candidate scores; don't reuse the FLAMeS-provenance null with a
  different base model — `build_null_bundle.py` stamps and the endpoint fails closed on
  provenance mismatch.
* **Metrics** are the repo's audited RC-030 implementation when the backend is importable;
  a convention-identical vendored fallback keeps `benchmark.py` runnable on a bare checkout.
