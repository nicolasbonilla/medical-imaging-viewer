# FLAMeS in the browser — design of the "AI switched on for free" prototype

| | |
|---|---|
| Status | **PROTOTYPE — research only, not for clinical use.** Behind `VITE_ENABLE_BROWSER_FLAMES` (default **OFF**). Not deployed. |
| Branch | `feat/flames-in-browser` |
| Safety class | Touches IEC 62304 **Class C** behaviour (lesion segmentation, HAZ-001; orientation, HAZ-006). Change proposal: [CHANGE-PROPOSAL.md](CHANGE-PROPOSAL.md). Since the 2026-10-17 review fixes ([REVIEW-RESPONSE.md](REVIEW-RESPONSE.md)) the controlled documents carry DRAFT entries (SRS 1.7, RMF 1.9, TM 1.6, SOUP 1.2, CMP 1.1), every approval field N. G. Bonilla Vargas — approved 2026-10-30 (PR #70). |
| Date | 2026-10-17 |

## 0. Summary

The server-side FLAMeS worker needs a paid GPU and is dark. This prototype runs the **same FLAMeS model
(nnU-Net v2, Dataset004_WML, single FLAIR, Zenodo 17955359 v2.0, CC BY 4.0) inside the clinician's browser** with
ONNX Runtime Web (WebGPU when available, WebAssembly otherwise). No GPU server, no inference cost, the image
never leaves the browser.

Measured on public data (MSLesSeg P57, CC BY 4.0), fold 0, no test-time mirroring:

| Case | Browser path vs `nnUNetv2_predict` (PyTorch) | vs nnU-Net predictor running the same ONNX | Lesions (browser / nnU-Net) | Time, ORT Web WebAssembly 8 threads (Node 24) |
|---|---|---|---|---|
| P57 FLAIR 1 mm isotropic (182×218×182) | **Dice 0.99940** (47 of ~38 900 voxels differ) | Dice 0.99946 (42 voxels) | 85 / 85 | 266 s (8 windows, 32.5 s/window) |
| P57 averaged to 4 mm slices (182×218×45) — exercises the anisotropic ("separate-z") path | **Dice 0.99934** (13 of ~9 900 voxels) | Dice 0.99934 (13 voxels) | 62 / 63 | 218 s (8 windows, 25.5 s/window) |

In a real browser (headless Edge 155, production build, WebAssembly 8 threads) the 1 mm case took **230 s** and gave
a mask bit-identical to the Node run (§7.1). **WebGPU did not work on this machine** (ONNX Runtime Web 1.24.1 has no
3D convolution on WebGPU; 1.29.0 has it, but the integrated GPU lost the device) — the fail-closed fallback to
WebAssembly worked both times. The target in the brief (Dice ≥ 0.99) is met on both cases.
These numbers say the **port reproduces nnU-Net**; they say nothing new about FLAMeS' clinical accuracy
(for context only: fold 0 vs the MSLesSeg expert mask of P57 = Dice 0.768).

## 1. Scope

In scope: automatic draft segmentation of MS lesions from **one skull-stripped 3D FLAIR** NIfTI already stored in a
study, run in a Web Worker, opened as a **local, unsaved, visibly-labelled AI draft** that the clinician must review,
edit and explicitly save.

Out of scope for the prototype: skull stripping (§9), the 5-fold ensemble (supported by the design, not wired), test-time
mirroring by default (implemented, off), DICOM input, mobile devices, deployment.

## 2. Architecture

```
UI thread                                                    Web Worker (flamesInBrowser.worker.ts)
─────────                                                    ───────────────────────────────────────
ClinicalToolsPanel ─(flag on)─▶ BrowserFlamesCard (lazy chunk)
        │ "Segment in this browser"
        ▼
useBrowserFlames ── GET /api/v1/imaging/nifti/{fileId} ──┐   (existing authenticated route, object-level auth CAPA-009)
        │  (apiClient: bearer + refresh)                 │
        └── postMessage({nifti bytes, pinned model}) ────┼──▶ modelStore: Cache Storage hit? → else fetch → SHA-256 + size pin
                                                         │    nifti.ts: gunzip (DecompressionStream) + NIfTI-1 parse
                                                         │    pipeline.ts ─ gates → preprocess.ts → slidingWindow.ts
                                                         │         └─ runPatch → ONNX Runtime Web (webgpu │ wasm)
                                                         │    postprocess.ts → mask in app order (k,i,j)
        ◀── exactly one terminal message: result | error ┘
        │
checkDraftGrid (same file + same rows/columns/slices)  ── fail closed
        ▼
importDraftCallback (Zustand) → useSegmentationData.createSegmentationFromMask
        → local-{uuid} segmentation, orange label "Lesion (AI draft, unreviewed)", isDirty
        → clinician reviews / edits with the normal tools
        → Save (unchanged path): POST /segmentation/create (description = provenance stamp)
                                  → PUT /segmentation/{id}/mask/binary (If-Match, durability check)
```

| File | Role |
|---|---|
| `frontend/src/services/flames/plan.ts` | Every FLAMeS/nnU-Net constant, transcribed from the model's own `plans.json`/`dataset.json`/`debug.json`; pinned model asset |
| `.../nifti.ts` | Minimal NIfTI-1 reader (gzip, 8 datatypes, scl_slope/inter, sform/qform), fails closed on anything else |
| `.../axes.ts` | The three axis layouts and their conversions (§3.1) |
| `.../preprocess.ts` | crop_to_nonzero + hole filling, z-score, nnU-Net resampling |
| `.../slidingWindow.ts` | steps, Gaussian, padding, stitching, optional mirroring, constant/NaN-score check |
| `.../pipeline.ts` | Orchestration + input/output gates |
| `.../postprocess.ts` | argmax, probability, 26-connected lesion count/volume, Dice |
| `.../modelStore.ts` | Download, SHA-256 pin, Cache Storage |
| `.../draft.ts` | Grid/file gate, provenance stamp, draft label |
| `.../protocol.ts` | Worker message types (no partial-result message exists) |
| `frontend/src/workers/flamesInBrowser.worker.ts` | ORT Web session, WebGPU → WebAssembly restart, provenance |
| `frontend/src/hooks/useBrowserFlames.ts` | Worker lifecycle (one worker per job, terminated after) |
| `frontend/src/components/BrowserFlamesCard.tsx` | Minimal UI, only rendered with the flag |
| `useSegmentationMask.importMask`, `useSegmentationData.createSegmentationFromMask`, store `importDraftCallback` | Additive hand-over into the existing local-first flow |
| `research/flames_in_browser/*.py` | Export, fixtures, nnU-Net references, comparisons, negative controls, browser smoke harness |

The Class C file `frontend/src/workers/edgeAI.worker.ts` is **not modified**.

## 3. Exact preprocessing and inference (must match nnU-Net)

Sources: FLAMeS `plans.json` / `dataset.json` / `fold_0/debug.json` from the Zenodo archive, and the nnunetv2 2.8.1
source (`preprocessing/resampling/default_resampling.py`, `preprocessing/cropping/cropping.py`,
`preprocessing/normalization/default_normalization_schemes.py`, `inference/predict_from_raw_data.py`,
`inference/sliding_window_prediction.py`, `inference/export_prediction.py`). Every bullet below is backed by a unit
test against fixtures computed by that code (`make_fixtures.py`), except where marked.

### 3.1 Reading and axis order (HAZ-006)

* `dataset.json` sets `overwrite_image_reader_writer: SimpleITKIO`. SimpleITK returns the stored voxels as a C-order
  array **(k, j, i)** — no reorientation, no resampling, `scl_slope/scl_inter` applied. nnU-Net then applies
  `transpose_forward = [2, 0, 1]`, so the network sees **(i, k, j)**; spacing follows: (sx, sz, sy).
* FLAMeS' target spacing `[1.0, 0.9, 0.9]` and patch `[112, 128, 160]` are in that order: 1.0 mm along NIfTI i,
  0.9 mm along k and j.
* The app's segmentation convention (RC-031) is **(k, i, j)**: backend `m = img.transpose(2, 0, 1)`; frontend
  `index = slice·H·W + row·W + col` with slice = k (dim3), row = i (dim1), column = j (dim2).

| Layout | Shape | Flat index of voxel (i, j, k) |
|---|---|---|
| NIfTI storage (what `readNifti` returns) | (nx, ny, nz), i fastest | `i + nx·(j + ny·k)` |
| nnU-Net network order | (nx, nz, ny) C-order | `(i·nz + k)·ny + j` |
| App segmentation order (RC-031) | (nz, nx, ny) C-order | `(k·nx + i)·ny + j` |

Verification: `axes-nifti.test.ts` writes NIfTI files with nibabel (float32 LAS gz; int16 with slope 2 / inter 10 and
an **oblique, permuted** affine; uint8 anisotropic), reads them with **SimpleITK exactly as nnU-Net does**, and
requires the TypeScript reader + conversions to reproduce SimpleITK's network-order array, nibabel's data and affine,
and the backend's `transpose(2, 0, 1)`; plus a blob-localisation test through the whole pipeline (`pipeline.test.ts`).
Negative controls M2, M4, M10 (§10) prove these tests fail when the order is wrong.

Note: nothing is reoriented anywhere. FLAMeS was trained on whatever orientation its 668 training scans had; nnU-Net
relies on mirroring augmentation for robustness. A FLAIR stored in an unusual orientation is segmented as nnU-Net
itself would segment it — the browser does not add or remove orientation behaviour.

### 3.2 Cropping (`crop_to_nonzero`)
Nonzero mask (`data != 0`) → `scipy.ndimage.binary_fill_holes` (6-connected: background not connected to the array
border becomes foreground) → bounding box `[min, max+1)` per axis. Outside the mask the segmentation is 0.

### 3.3 Intensity normalisation (`ZScoreNormalization`, `use_mask_for_norm = true`)
Mean and population standard deviation over the filled nonzero mask; inside: `(x − mean) / max(std, 1e-8)`;
outside: unchanged (it is 0 by construction). Normalisation happens **before** resampling, as in nnU-Net.

### 3.4 Resampling to 1.0 × 0.9 × 0.9 mm (`resample_data_or_seg_to_shape`, order 3, order_z 0)
* New shape: `int(round(old_spacing / new_spacing · old_shape))` with Python's half-to-even rounding.
* "Separate z" when `max(spacing)/min(spacing) > 3` (strictly) for the current spacing, else for the target, **and**
  exactly one axis is the coarsest. Then: per-slice 2D cubic resize in-plane, nearest neighbour along the slice axis.
  A ratio of exactly 3 is **not** separate-z (fixture `ratio_exactly_3_not_sepz`).
* Otherwise: 3D cubic. Cubic = `skimage.transform.resize(order 3, mode 'edge', anti_aliasing False)` =
  `scipy.ndimage.zoom(grid_mode=True, mode='nearest')` with a 12-voxel edge pre-pad before the B-spline pre-filter.
  Output clipped to the input range (per slice in separate-z mode).
* Agreement with nnunetv2 on 8 fixtures (isotropic up/down, step edges with overshoot clipping, separate-z on axes 0
  and 1, order 1 forward/back): max abs error < 1e-5.

### 3.5 Sliding window (`predict_sliding_window_return_logits`)
* Zero-pad to at least the patch size (below = ⌊diff/2⌋).
* Steps: `ceil((size − patch)/(patch·0.5)) + 1` windows, positions `round(i · (size − patch)/(n − 1))` (numpy half-to-even).
* Gaussian importance map: `gaussian_filter` of a centred delta, σ = patch/8, normalised (scale irrelevant); zeros → min.
* Logits accumulated as Σ(logit·g)/Σ(g). Only the lesion − background **difference** is kept (sufficient for
  argmax and for the 2-class softmax).
* Optional mirroring TTA over network axes (0, 1, 2): 8 network calls per window, as nnU-Net's default.
  **Off by default** in the prototype (8× time). The FLAMeS authors' published command uses nnU-Net's default
  (mirroring **on**); Neurodesk's validation ran without it. Impact on accuracy not measured here (open item).
* **Deliberate deviation:** nnunetv2 2.8.1 accumulates logits and weights in **float16** to save GPU memory
  (`predicted_logits`/`n_predictions` are `torch.half`); the browser accumulates in float32. This is a numerical
  improvement, and a plausible source of part of the residual 13–47 differing voxels (not isolated).

### 3.6 Back to the image grid, postprocessing
* The **logits** (not probabilities) are resampled back to the cropped shape with order 1 (same separate-z rule),
  then argmax ⇔ `lesion − background > 0`, pasted into the bounding box, transposed back. This is
  `convert_predicted_logits_to_segmentation_with_correct_shape`. (Neurodesk's port resamples probabilities instead —
  we follow nnU-Net.)
* No connected-component removal: the Zenodo archive contains no `postprocessing.pkl`, so `nnUNetv2_predict` applies
  none; adding one would change the validated model's output.
* The UI reports the number of 26-connected components and the volume (mL) — descriptive only.

### 3.7 Differences from the Neurodesk port (for reviewers)
1. Logits vs probabilities resampled (above). 2. Half-to-even rounding in `compute_new_shape` and steps.
3. Hole filling in the nonzero mask. 4. No pre-downsampling of inputs finer than 1 × 0.9 × 0.9 mm: the mask must stay on
the stored FLAIR grid (app constraint); cost: memory for very fine 3D FLAIR (bounded by the 96 M-voxel reader limit).
5. Fail-closed gates and draft hand-over (§8, §9).

## 4. Model

| Item | Value |
|---|---|
| Source | Zenodo 10.5281/zenodo.17955359, **version 2.0**, `Dataset004_WML.zip` (2 351 319 537 B, md5 8b90b789…), licence **cc-by-4.0** (Zenodo API, 2026-10-17) |
| Downloaded | only `plans.json`, `dataset.json`, `dataset_fingerprint.json`, `fold_0/debug.json`, `fold_0/checkpoint_final.pth` via HTTP range requests (no 2.35 GB download) |
| Checkpoint | fold 0, sha256 `4fc7db24…3fdf861` (matches Neurodesk's recorded value) |
| Export | `research/flames_in_browser/export_onnx.py` (torch 2.14.1 CPU, opset 17): 5 ConvTranspose → 1×1×1 Conv + depth-to-space (WebGPU has no 3D ConvTranspose); weights stored float16, cast to float32 in-graph |
| Artefact | `flames-fold0.onnx`, 61 642 305 B, sha256 **`2a10bb9d72dc33381a3f44dd6a59ec612dfd87534e02f15488b426ae127176ae`** |
| Checks | PyTorch vs ONNX (float32): max |Δlogit| 0.0029; after rewrite: identical; after float16 storage: 0.028 on a random-noise patch, 99.9997 % same class. On real data the nnU-Net predictor gives Dice 0.99991 (7 voxels) between the PyTorch checkpoint and this ONNX on P57, and identical masks on the 4 mm case |
| Independent cross-check | Neurodesk's published `flames-fold0.onnx` (HF dataset `neurodeskorg/webapps` @ee0b2a1d, sha256 `fe21c420…`): **bit-identical logits and identical initialisers** to ours; only the producer-version metadata differs (torch 2.14.0 vs 2.14.1), hence a different file hash |
| I/O | `input` float32 [1,1,112,128,160] → `logits` float32 [1,2,112,128,160] (0 background, 1 lesion) |

Ensemble: the other 4 folds can be exported identically (≈ 62 MB each, 5× time). Neurodesk's measurements (MSLesSeg
test split, n = 22) show fold 0 alone over-segments relative to the 5-fold ensemble (Dice 0.608 vs 0.647, AVD 84 % vs
45 %; their `validation/README.md`). **For clinical use the ensemble (and probably mirroring) should be the default;
the single fold is only the prototype.**

## 5. Parity harness (how to reproduce)

```sh
# 0) isolated venv (scratch): torch CPU, nnunetv2 2.8.1, onnx, onnxruntime, remotezip
# 1) fixtures for vitest (already committed: src/services/flames/__tests__/fixtures/nnunet_reference.json)
python -I research/flames_in_browser/make_fixtures.py frontend/src/services/flames/__tests__/fixtures/nnunet_reference.json
# 2) export (needs the Zenodo trainer folder with fold_0/checkpoint_final.pth)
python -I research/flames_in_browser/export_onnx.py <trainer folder> 0 flames-fold0.onnx --manifest flames-fold0.json
# 3) nnU-Net references on a public FLAIR (CPU)
python -I research/flames_in_browser/reference_nnunet.py <trainer folder> P57_FLAIR.nii.gz ref_torch.nii.gz --backend torch
python -I research/flames_in_browser/reference_nnunet.py <trainer folder> P57_FLAIR.nii.gz ref_onnx.nii.gz --backend onnx --onnx flames-fold0.onnx
# 4) anisotropic case
python -I research/flames_in_browser/make_thick_slice_case.py P57_FLAIR.nii.gz P57_thick4mm.nii.gz --factor 4
# 5) browser path (ORT Web WebAssembly in Node) — skipped unless the env vars are set
cd frontend
FLAMES_PARITY_FLAIR=… FLAMES_PARITY_MODEL=flames-fold0.onnx FLAMES_PARITY_REFS="torch=ref_torch.nii.gz,onnx=ref_onnx.nii.gz" \
FLAMES_PARITY_GT=P57_MASK.nii.gz FLAMES_PARITY_OUT=summary.json \
  npx vitest run src/services/flames/__tests__/parity.flames.test.ts --pool=threads
# 6) unit tests (CI-safe, no model, no data)
npx vitest run src/services/flames --pool=threads
```

Reference timings on the same machine (Ryzen 7 5800H, 8 threads): `nnUNetv2_predict`-equivalent with PyTorch CPU
128 s (1 mm) / 124 s (4 mm); native ONNX Runtime CPU ≈ 10 s per 112×128×160 window.

## 6. Hosting and caching

* **Not in git.** `frontend/public/models/flames/` is ignored. The artefact is a release asset identified by its
  SHA-256; the build/release step copies it to `frontend/public/models/flames/flames-fold0-2a10bb9d.onnx`
  (content-addressed name) after checking the hash (`research/flames_in_browser/stage_model.py`). Archive, hash pin
  and release step: CMP-001 §6 (`docs/iec62304/07_Configuration_Management_Plan.md`) — research bucket
  `gs://mstool-research-data` (proposed, not created) + release attachment; Git LFS rejected.
* **Served same-origin by Firebase Hosting** under the app (no CORS, no COEP issues, no third-party dependency at
  run time). `VITE_FLAMES_MODEL_URL` can point elsewhere; the SHA-256 pin is enforced regardless.
* Proposed `firebase.json` header (not applied in this branch):
  `{"source": "/models/**", "headers": [{"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}]}`.
  The ONNX Runtime wasm (27 MB, `ort-wasm-simd-threaded.asyncify-*.wasm`) is already content-hashed by Vite.
* In the browser the verified model is kept in **Cache Storage** (`mstool-flames-models-v1`), re-verified on every use,
  evicted and re-downloaded if corrupted. A workstation downloads ≈ 62 MB (model) + 27 MB (runtime) once per version.
* **Cost (honest):** Firebase Hosting gives 10 GB storage and **360 MB/day** transfer at no cost, then $0.15/GB
  (firebase.google.com/pricing, 2026-10-17). ≈ 89 MB per first-time workstation ⇒ ≈ 4 new workstations/day free,
  ≈ $0.013 each beyond. Repeat use is served from the browser cache. The 5-fold ensemble would be ≈ 310 MB per
  workstation (≈ $0.05). Zero-cost alternative: Neurodesk's Hugging Face copy (functionally identical, pin its hash
  `fe21c420…`) — free, but adds a third-party availability dependency (integrity is still guaranteed by the pin).

## 7. Time and memory budget

| Configuration | Measured / estimated | Source |
|---|---|---|
| ORT Web **WebAssembly, 8 threads**, Node 24 (this machine, Ryzen 7 5800H, 15 GB) | **266 s** (1 mm, 8 windows) · **218 s** (4 mm) | measured (parity harness) |
| Headless **Edge 155**, built worker, WebAssembly 8 threads, cross-origin isolated | **230 s** (1 mm, ≈ 27.5 s/window) | measured (smoke harness, §7.1) |
| Headless Edge, **WebGPU** requested (AMD Radeon integrated, 512 MB dedicated) | **not usable** — see §7.1; fell back to WebAssembly (242 s / 263 s total) | measured |
| Chromium WebAssembly 8 threads, Neurodesk example (2.3 mm clinical FLAIR, 6 windows) | ≈ 3 min | Neurodesk validation README (not re-measured) |
| WebAssembly **1 thread** (page NOT cross-origin isolated — today's app) | estimated 6–8× slower ⇒ 20–40 min | estimate, not measured |
| Discrete-GPU workstation, WebGPU (needs ONNX Runtime Web ≥ 1.29) | expected < 1 min | **not measured** |

### 7.1 Real-browser smoke test (headless Microsoft Edge 155, this machine)

`research/flames_in_browser/browser_smoke/` serves the **production build** of the worker (`vite build`) on
127.0.0.1 with COOP/COEP headers, plus the pinned model and the public P57 FLAIR; a page drives the worker exactly as
`useBrowserFlames` does and posts the result back. A temporary browser profile was used; nothing else was touched.

| Run | ONNX Runtime Web | Backend actually used | Total | Mask vs `nnUNetv2_predict` | Notes |
|---|---|---|---|---|---|
| 1 | 1.24.1 (app's lockfile) | WebAssembly ×8 (`crossOriginIsolated = true`, 16 logical cores) | **230 s** | **Dice 0.99940** (47 voxels), 85 lesions | mask **bit-identical** to the Node run; model downloaded once, SHA-256 verified |
| 2 | 1.24.1, WebGPU preferred | WebGPU **failed**: `Only Conv1d and Conv2d are supported` (the JSEP WebGPU backend in 1.24 has no 3D convolution) → whole job restarted on WebAssembly | 242 s | identical to run 1 (0 voxels differ) | fallback reason stored in provenance; model served from **Cache Storage** (no second download) |
| 3 | 1.29.0 (scratch build only; repository dependency unchanged) | WebGPU started (3D conv supported) but the integrated GPU reported **`Device is lost`** during the first 112×128×160 window → restarted on WebAssembly | 263 s | identical to run 1 | likely GPU memory/timeout limit of a 512 MB iGPU |

Consequences: (1) the WebAssembly path works in a real browser with the expected time; (2) **WebGPU needs a SOUP
upgrade of ONNX Runtime Web to ≥ 1.29** (Class C SOUP change, also affects `edgeAI.worker.ts`) **and** a GPU with
enough memory — on integrated GPUs it should not even be attempted (check `adapter.limits`/`info` first); (3) the
fail-closed fallback (RC-044) was exercised for real twice and behaved as designed.

Memory: the largest activation of one 112×128×160 patch is 64 channels × 2.29 M voxels × 4 B ≈ **587 MB** (decoder
concat); the worker's WebAssembly heap peaks at roughly 2.5–3.5 GB (estimate; the 32-bit wasm ceiling is 4 GB). On
this 15 GB machine two native sessions in parallel already failed to allocate that buffer, so the design runs one
session at a time and **terminates the worker after each job** to return the heap. Device classes:

| Class | Expectation |
|---|---|
| Desktop/laptop ≥ 16 GB RAM, ≥ 8 cores, Chrome/Edge, app cross-origin isolated | supported (3–5 min WebAssembly; faster with WebGPU) |
| Same, app NOT cross-origin isolated (current hosting headers) | works but 1 thread (estimated 20–42 min); since 2026-10-17 the card states the expected duration before the run, shows the elapsed time and can be cancelled without touching the open segmentation (REQ-FUNC-096) |
| ≤ 8 GB RAM, tablets, phones | not supported — should be refused up front with `navigator.deviceMemory` (next step) |

Cross-origin isolation (needed for WebAssembly threads, not for WebGPU) requires `Cross-Origin-Opener-Policy:
same-origin` + `Cross-Origin-Embedder-Policy: require-corp` (or `credentialless`) on the app's HTML. That can break
cross-origin resources and must be its own tested change. Impact analysis: [COOP-COEP-IMPACT.md](COOP-COEP-IMPACT.md)
(the app has no OAuth pop-ups; the real breakage is the document preview of GCS signed URLs).

## 8. Failure handling — fail closed

A job ends with exactly one message: a **complete, gated** result or an error. There is no partial-result message.

| Failure | Behaviour |
|---|---|
| Model bytes differ from the pin (size or SHA-256), download error | `ModelIntegrityError` / error, nothing runs; corrupted cache entry deleted |
| Not NIfTI-1, NIfTI-2, 4D, unsupported datatype, truncated, NaN/Inf voxels, invalid spacing, > 96 M voxels | reader error, nothing runs |
| Spacing outside 0.1–6 mm, any dim < 16 | `FlamesInputError` |
| Not skull-stripped: > 2 % of the FOV border nonzero, filled nonzero region outside 500–2600 mL, or a skull clue: > 1 % of the outer 6 mm very bright (scalp fat) or > 20 % of the filled region very dark (also with a zero background) | `FlamesInputError` before the model download (RC-043; validated on public data, [FLAIR-GATE-VALIDATION.md](FLAIR-GATE-VALIDATION.md)) |
| Not a FLAIR (`flair-gate/2`): header names another sequence or an inversion time < 1400 ms; image content with white matter brighter than cortex or a large darker grey-matter class (T1), or bright CSF (T2/PD); contrast not measurable; **or no positive evidence** — neither the clinician's per-file confirmation of the sequence (checkbox before the run, recorded with the draft) nor a header with a FLAIR inversion time (a "FLAIR" label alone is not proof) | `FlamesInputError` before the model download (RC-049; [FLAIR-GATE-VALIDATION.md](FLAIR-GATE-VALIDATION.md)) |
| Network returns NaN/Inf or the same score everywhere (known WebGPU failure mode), wrong output size | error; if on WebGPU, the **whole** job restarts on WebAssembly (backends never mixed); provenance records the fallback reason |
| Lesions > 25 % of the brain | result discarded as implausible |
| Worker crash / `onerror`, user cancel | worker terminated, no result |
| Result for a different file than the one on screen, or rows/columns/slices differ | the draft cannot be opened (`checkDraftGrid`) |
| `importMask` with mismatched dimensions | refused, local draft removed |
| Empty result (0 voxels) | explicit warning, never a plain "0 lesions"; the draft opens only after the user acknowledges it (RC-051, REQ-FUNC-036) |
| Open draft while the open segmentation has unsaved changes | nothing changes; the user chooses "keep my work" or "discard my unsaved changes and open the draft" (RC-050) |
| Tab closed / reloaded with an AI draft open | browser warning only — an AI segmentation is never saved by the save-on-unload of manual work (RC-047) |
| Save | explicit only: create **with `ai_provenance`** incl. `sequence_evidence` (server stores `segmentation_type = automatic`, `review_status = unreviewed`, `sequence_confirmed_by` = authenticated user), refused and the record removed unless the server echoes exactly the provenance sent, still unreviewed; then PUT with `If-Match` (A-2) and durability check (P-4.3) (RC-047) |
| Mask changed after a confirmed review (any path) | the review is reset to "unreviewed" at the service's single save point (`enforce_review_binding`); after saving corrections the app re-reads the provenance (RC-047) |

## 9. How the output enters the app

1. `BrowserFlamesCard` (only with the flag): the clinician ticks "I confirm that the selected image is a skull-stripped
   T2-FLAIR …" for **this** file (cleared when the file changes) → `useBrowserFlames.run(flairFileId, { clinicianConfirmedFlair: true })`.
2. On result, the card shows count / volume / time / backend. **Nothing is displayed on the image yet.**
3. "Open as AI draft for review" is enabled only when the viewer shows **that** FLAIR with the **same** grid.
4. `importDraftCallback` → `createSegmentationFromMask`: a `local-{uuid}` segmentation (same path as a manual new
   segmentation), label 1 = **"Lesion (AI draft, unreviewed)"**, orange, description = provenance stamp
   (`AI DRAFT (unreviewed) — FLAMeS fold 0 …, model sha256 2a10bb9d72dc, WebAssembly x8, N lesions, V mL, timestamp`),
   `isDirty = true`, undo history reset, `metadata.ai_provenance` = model name/version/SHA-256/fold/pipeline/runtime/
   lesion count/annotated voxels, `review_status = unreviewed`. **If the open segmentation has unsaved changes nothing
   happens** until the user explicitly chooses (RC-050). An empty result needs an explicit acknowledgement (RC-051).
5. The clinician reviews/edits with the normal tools; only an explicit **Save** persists it, with its provenance (never
   the save-on-unload). Manual segmentations keep exactly the previous request body.
6. A persistent banner "AI draft — UNREVIEWED" is shown wherever the segmentation is open, saved or not; the saved list
   names it `[AI draft — UNREVIEWED] FLAMeS fold 0`. A radiologist can confirm the review
   (`POST /segmentation/{id}/ai-review/confirm`, reviewer + time recorded) (RC-047) — only with no unsaved corrections
   (no button otherwise), and only for the exact stored mask: the client sends the SHA-256 of the mask on screen, the
   server refuses (409) unless it equals the stored mask, and records it as `reviewed_mask_sha256`. Any later change of
   the mask resets the review to "unreviewed".

## 10. Verification done in this branch

* **55 unit tests** (vitest, node env, `--pool=threads`) in `frontend/src/services/flames/__tests__/`, CI-safe (no model,
  no data): fixtures computed by nnunetv2/scipy/skimage/SimpleITK/nibabel; fake-network stitching with closed-form
  expectations; blob localisation through anisotropic resampling; every gate; grid gate; integrity pin.
* **Negative controls** (`research/flames_in_browser/negative_controls.py`): 12 injected defects (Math.round, spacing
  not permuted, no hole filling, wrong network order, no clipping, floor instead of nearest, Gaussian σ doubled, mirror
  not undone, rows/columns swapped in the grid gate, RC-031 transpose dropped, skull-strip gate disabled, integrity
  check skipped) → **12/12 detected**, sources restored and hash-verified.
* **Parity**: §0 / §5. **Type check** `tsc --noEmit` clean; **production build** succeeds (worker 135 kB chunk, card
  7 kB lazy chunk; nothing loaded when the flag is off).
* **Real browser** (§7.1): built worker in headless Edge, 3 runs, masks identical, fallback exercised.
* **Full frontend suite**: 171 passed, 1 skipped (the opt-in parity test).
* **After the 2026-10-17 review fixes** ([REVIEW-RESPONSE.md](REVIEW-RESPONSE.md)): full frontend suite 218 passed, 3 skipped
  (opt-in parity, gate-validation and replay harnesses); backend unit suite 1302 passed; review negative controls 28/28;
  input-gate validation on 495 public volumes ([FLAIR-GATE-VALIDATION.md](FLAIR-GATE-VALIDATION.md)).
* **After re-review 2** (2026-10-18/21): full frontend suite 236 passed, 3 skipped; backend unit suite 1307 passed; type
  check clean; production build with the flag absent; negative controls 45/46 (G6 not detectable with phantoms), reviewed
  code fails the new tests 6/6; FLAIR gate `flair-gate/2` validated on 533 public volumes incl. ISBI-2015 with
  leave-one-dataset-out ([FLAIR-GATE-VALIDATION.md](FLAIR-GATE-VALIDATION.md)).
* Not done: visual QA in the real app with a logged-in study; clinical accuracy study; WebGPU on a discrete GPU;
  5-fold ensemble parity; mirroring parity.

## 11. Licences

| Component | Used how | Licence (verified) | Source of the verification | Obligations / verdict |
|---|---|---|---|---|
| FLAMeS weights v2.0 (Zenodo 17955359) | converted to ONNX, would be hosted by us | **CC BY 4.0** | Zenodo REST API `metadata.license.id = cc-by-4.0`, 2026-10-17 | Attribution + indicate changes (format conversion, float16 storage) — done in `NOTICE.md` and provenance. **Use only the Zenodo v2 release**: Neurodesk reports that the Hugging Face copy is labelled CC BY-NC 4.0 (not re-checked). OK |
| FLAMeS paper | citation | — | Dereskewicz et al., J Neuroimaging 2025;35(5):e70085 | cite |
| nnU-Net v2 (MIC-DKFZ) | algorithm re-implemented in TS; Python used offline for export/reference | **Apache-2.0** | GitHub repo licence | cite; no source shipped. OK |
| Neurodesk webapps — `packages/white-matter-lesions`, `apps/white-matter-lesions/scripts/export_model.py` | resampling kernels + stitching structure ported to TS; export script adapted | **Apache-2.0** (per-package `LICENSE`; `registry/apps.yml`). The repository has **no blanket licence** (`LICENSES.md`) | files read at commit `main` 2026-10-17 | keep notice, state changes, ship licence text — done in `NOTICE.md`. OK |
| ONNX Runtime Web 1.24.1 | browser runtime (already a dependency) | **MIT** | npm `package.json` | keep copyright notice. OK. **SOUP-FE-008 lists 1.21.0; the lockfile resolves 1.24.1** — SOUP BOM out of date |
| SynthStrip **weights** | **not used** | **MIT or CC BY 4.0** (licensee's choice) | synthstrip.io "Code and Weights" section | usable for a future skull-strip step |
| SynthStrip **code** (`mri_synthstrip`, FreeSurfer repo) | **not used** | **FreeSurfer Software License v1.0**: royalty-free, derivatives and commercial use allowed, but "designed for research purposes only … CLINICAL APPLICATIONS ARE NEITHER RECOMMENDED NOR ADVISED", Part B terms must accompany copies, modified versions must be marked | `freesurfer/freesurfer` `LICENSE.txt` (dev) | not a prohibition, but a clinical-use disclaimer + notice duties → **legal review before shipping any port** |
| Neurodesk `@neurodesk/synthstrip` (JS port) | **not used** | labelled Apache-2.0 by Neurodesk; its `model.js` labels the weights Apache-2.0 | `packages/synthstrip/NOTICE`, `src/model.js` | Labelling inconsistent with upstream (weights are MIT/CC BY; processing ported from FreeSurfer-licensed code) → treat the upstream terms as attaching to the derived parts until legal review |
| HD-BET (alternative skull stripper) | not used | code **Apache-2.0** (GitHub); weights licence **not verified** | GitHub API | candidate |
| Brainchop / MindGrab (alternative) | not used | code **MIT** (GitHub); model licence **not verified** | GitHub API | candidate |
| MSLesSeg dataset | parity testing only, local, read-only | **CC BY 4.0** | figshare API, doi 10.6084/m9.figshare.27919209 | cite in any publication |

### Skull stripping — constraint and options
FLAMeS expects a skull-stripped FLAIR (authors recommend SynthStrip `--no-csf`). The prototype therefore **accepts only
skull-stripped input** and refuses anything that does not look stripped (gate RC-043, extended 2026-10-17 with a skull-presence clue). Options, in order of preference:
1. **SynthStrip weights (MIT) + a clean-room browser implementation of its pre/post-processing written from the
   paper** (Hoopes et al., NeuroImage 2022), with legal sign-off on the FreeSurfer licence question; ≈ 10 MB model.
2. HD-BET (Apache-2.0 code) after verifying its weight licence; heavier.
3. MindGrab (MIT code) after verifying its model licence and validating it on FLAIR.
4. Server-side stripping on CPU (no GPU needed, but a recurring CPU cost — conflicts with the no-recurring-cost rule).

## 12. Known limitations and next steps
1. Visual QA in the real app (flag on, logged-in study with a public, skull-stripped FLAIR).
2. Export folds 1–4; make the 5-fold ensemble (± mirroring) the default; parity for both.
3. Skull stripping (§11).
4. Cross-origin isolation headers as a separate, tested change; device gate (`deviceMemory`, cores, WebGPU) and an
   explicit time estimate before starting.
4b. WebGPU: upgrade ONNX Runtime Web to ≥ 1.29 (SOUP change), attempt WebGPU only when the adapter's limits/memory
   suffice, and measure on a discrete GPU.
5. Release step that copies the model into `public/models/flames/` with a hash check; `firebase.json` caching header.
6. Clinical validation of the draft (Dice/lesion-F1 vs experts on held-out public data, then local data under the QMS).
7. Update SOUP BOM (ONNX Runtime Web version), SRS/RMF/traceability through the Class C change process (CHANGE-PROPOSAL.md).
