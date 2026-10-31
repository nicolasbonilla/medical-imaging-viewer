# Third-party notices — in-browser FLAMeS prototype (`src/services/flames/`, `src/workers/flamesInBrowser.worker.ts`)

## FLAMeS model weights — CC BY 4.0
FLAMeS: FLAIR Lesion Analysis in Multiple Sclerosis, version 2.0. La Rosa F. et al.
Zenodo, doi:10.5281/zenodo.17955359 (record licence `cc-by-4.0`, checked through the Zenodo API on 2026-10-17).
Dereskewicz E, La Rosa F, dos Santos Silva J, et al. *A Novel Convolutional Neural Network for Automated
Multiple Sclerosis Brain Lesion Segmentation.* Journal of Neuroimaging 2025;35(5):e70085, doi:10.1111/jon.70085.
Licence: https://creativecommons.org/licenses/by/4.0/
**Changes:** the fold-0 PyTorch checkpoint was converted to ONNX (transposed convolutions rewritten as
1×1×1 convolution + depth-to-space; weights stored as float16) by `research/flames_in_browser/export_onnx.py`.
The weights themselves were not retrained or modified otherwise.

## nnU-Net v2 — Apache-2.0
Isensee F, Jaeger PF, Kohl SAA, Petersen J, Maier-Hein KH. *nnU-Net: a self-configuring method for deep
learning-based biomedical image segmentation.* Nature Methods 2021;18:203–211.
https://github.com/MIC-DKFZ/nnUNet — Copyright German Cancer Research Center (DKFZ), Apache License 2.0.
The preprocessing, sliding-window and export steps in this folder re-implement nnunetv2 2.8.1 behaviour in
TypeScript; no nnU-Net source file is shipped to the browser.

## Neurodesk webapps (white-matter-lesions) — Apache-2.0
https://github.com/neurodesk/webapps — `packages/white-matter-lesions/src/pipeline.js` and
`apps/white-matter-lesions/scripts/export_model.py` (declared Apache-2.0 in `packages/white-matter-lesions/LICENSE`
and `registry/apps.yml`; that repository has no blanket licence, see its `LICENSES.md`).
Portions of `preprocess.ts` (cubic B-spline / linear / nearest line kernels and per-axis resampling) and the
structure of `slidingWindow.ts` (injected patch runner, two-class logit-difference accumulation, constant-score
check) are a TypeScript port of `pipeline.js`; `research/flames_in_browser/export_onnx.py` is adapted from
`export_model.py`.
**Changes by MSTool-AI (2026-10-17):** TypeScript types; numpy/Python half-to-even rounding in
`compute_new_shape` and `compute_steps_for_sliding_window`; nonzero mask with 3D hole filling as nnU-Net's
`create_nonzero_mask`; normalisation leaves outside-mask voxels unchanged; the LOGITS (not the probabilities) are
resampled back before the argmax, as nnU-Net does; inputs are never pre-downsampled (the mask must stay on the
stored FLAIR grid); export script builds the network with nnunetv2's `get_network_from_plans` and checks every
graph stage against PyTorch; fail-closed input/output gates.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use these files except in
compliance with the License. You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0.
Unless required by applicable law or agreed to in writing, software distributed under the License is
distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

## ONNX Runtime Web — MIT
https://github.com/microsoft/onnxruntime — Copyright (c) Microsoft Corporation. MIT License (npm package
`onnxruntime-web`, already a dependency of this app, SOUP-FE-008).
