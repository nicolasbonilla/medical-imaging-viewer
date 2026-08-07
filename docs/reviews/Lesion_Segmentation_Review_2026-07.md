# Lesion Segmentation — In-Depth Code Review

**Date**: 2026-07-27
**Scope**: How lesion segmentation is produced, represented, analysed, persisted and
exported in the application *as it stands today*, plus the lesion layer/mask.
**Method**: Four parallel code explorations (pipeline, analysis, frontend, persistence),
each cross-checked against the source by direct inspection. Every claim carries a
`file:line`. Read-only; nothing was changed.

---

## 0. The one-paragraph picture

Lesion segmentation today is **manual-painting-first**. A radiologist draws the lesion
mask in the browser with a brush/eraser directly onto a slice; the mask is a flat
`Uint8Array` labelmap edited locally and uploaded on Save. **AI lesion segmentation
(LST-AI, mindGlide) exists in code and is fully orchestrated, but is disabled by
default, depends on external Docker sidecar images that are not shipped in the repo,
and — critically — its UI trigger is not currently rendered.** The only genuinely
in-house, runnable analytic is **MAGNIMS zone classification** of an already-existing
mask (SciPy/NumPy, no ML). CVS/PRL exist as manual-annotation plumbing with rule
aggregation, but there is **no automated CVS/PRL detection**.

---

## 1. How a lesion mask is produced

| Method | Mechanism | Where it runs | Inputs → Outputs | Status |
|---|---|---|---|---|
| **Manual paint** | brush/eraser writes a label into a `uint8` (D,H,W) mask | in-browser + `segmentation_service.py:232-361` | user strokes → lesion mask | **Fully working, primary path** |
| **LST-AI** | HTTP → sidecar → `subprocess ["lst",…]` | external Docker sidecar (`docker/lst-ai/server.py:94`) | T1w + FLAIR → binary lesion mask + MAGNIMS types | Coded + routed (`POST /clinical/lst-ai/segment`), **off by default**, image external |
| **SynthSeg** | HTTP → sidecar → `SynthSeg.predict`/`mri_synthseg` | external sidecar | any MRI → 30+ FreeSurfer parcellation (**not lesions**) | Coded + routed, **off by default** |
| **mindGlide** | HTTP → sidecar → `mindglide.segment` | external sidecar | any MRI → lesion mask + structures | Coded, **no API route**, off by default; **returns all-zeros if the package is missing** (`docker/mindglide/server.py:101-113`) |
| **Interactive / SAM-like** | — | — | — | **Stub** — "not yet available" (`ai_segmentation_service.py:83-95`) |
| **Vertex AI** | — | — | — | **Removed** — "never deployed" (`ai_segmentation_service.py:7`) |
| **nnU-Net** | — | — | — | **Absent** (no references) |
| **MAGNIMS zone classification** | SciPy EDT / atlas dilation / geometric relabel of an *existing* mask | in-process (`ms_region_classifier.py`) | mask (+parcellation/atlas) → PV/JC/IT/DWM labels | **Wired; MSMask atlas present in repo** |

**There is no proprietary lesion-detection model.** Lesion masks come only from manual
painting or from external research tools. Enablement flags all default to false
(`config.py:181-189`: `LSTAI_ENABLED=False`, `SYNTHSEG_ENABLED=False`,
`MINDGLIDE_ENABLED=False`, endpoints `""`).

---

## 2. The lesion layer / mask — representation and lifecycle

### 2.1 Representation
- **Browser**: a flat `Uint8Array` holding a 3D labelmap in `(depth, height, width)`
  order, kept in a `useRef` (not React state) for instant, network-free edits
  (`useSegmentationMask.ts:130-133`). Voxel index `z*(H*W) + y*W + x`. `0` =
  background/transparent; `1..255` = labels.
- **Backend**: `np.zeros((depth, height, width), dtype=np.uint8)`
  (`segmentation_service.py:157`). Same `(D,H,W)` convention.
- **Labels/presets** (`types/segmentation.ts`): **Default** = 4 lesion labels
  (Active/Chronic/T2-FLAIR/Black-Hole) + background; **MAGNIMS** = 6 (PV, JC, IT, DWM,
  Active Gd+, Black Hole). Locally-created segs use a minimal `{0 Background, 1 Lesion}`
  (`useSegmentationData.ts:131-134`).

### 2.2 Editing
- **Brush** = a filled disc stamped into the 2D slice view of the 3D buffer
  (`applyCircularBrush`, `useSegmentationMask.ts:87-114`). **Eraser** is the same path
  with `value = 0`. A `drawOverMode` predicate controls which existing voxels may be
  overwritten (`emptyOnly` / `activeLabel` / `all`).
- **Undo/redo** = slice-level snapshots, capped at 50, entirely in `useSegmentationMask`
  (`:234-299`). `beginStroke` copies the full H×W slice before edits.
- **2D only.** All paint tools, save, draw-over are gated behind `!is3D`
  (`SegmentationPanel.tsx:799/814/832/855`). In 3D the mask is display-only.

### 2.3 Rendering
- **2D**: a custom two-canvas stack (base MRI + overlay) in `SegmentationCanvasLocal.tsx`,
  redrawn from local memory on every edit. Per-label colour and per-label visibility come
  from Zustand, alpha scaled by the `lesionOpacity` slider (`:597-605`).
- **3D**: NiiVue, loading the mask as a *separate NIfTI volume* via
  `/segmentation/{id}/nifti` (`ImageViewer3D.tsx:194-197`).
- **Longitudinal tri-colour** (TP1 blue / TP2 red / overlap green) at fixed 0.55 opacity
  (`SegmentationCanvasLocal.tsx:516-566`).

### 2.4 Create → Save → Load (ITK-SNAP-style local-first)
- **Create is local-only**: a `local-{uuid}` temp id + empty in-memory mask, **no server
  call** (`useSegmentationData.ts:137-157`).
- **Save is the temp→server transition**: for a `local-` seg it first
  `POST /segmentation/create` to get a real id, then `PUT /{id}/mask/binary` uploads the
  bytes, then swaps the id into Zustand — with two deliberate race-avoidance mechanisms
  (`updateSegmentationId` touches a ref only; `skipNextLoadRef` suppresses the reload)
  (`useSegmentationData.ts:210-267`).
- **Load**: `GET /{id}/mask/binary`, header-parsed and size-validated.

### 2.5 Wire format
Raw octet-stream: **12-byte little-endian header** (`<III` = depth, height, width) +
`D*H*W` bytes of `uint8` (`segmentation.py:793-797`, mirrored in
`useSegmentationMask.ts:156-165`). **No magic number, no version field** — the only guard
is the byte-exact length check (`expected == D*H*W`). dtype is hard-locked to `uint8` on
both ends, which is what makes a Float32-vs-Int8 confusion (the historical `brain.bin`
incident) fail loudly as a size mismatch rather than silently corrupt.

### 2.6 Persistence
- **Firestore (metadata) + GCS (mask NIfTI)**, local disk on exception
  (`_save_segmentation`, `segmentation_service.py:701-740`).
- GCS writes only `segmentations/{id}/masks.nii.gz`; the loader still reads a legacy
  `masks.npz` for old records (`:879-929`) — asymmetric but backward-compatible.
- Metadata (`schemas.py:166-185`) has **no `patient_id`** — the patient is derived from
  `file_id` (RC-029), and every route enforces `require_segmentation_access`.

### 2.7 DICOM-SEG export (real, and wired)
`GET /segmentation/{id}/export/dicom-seg` (`segmentation_analysis.py:600-673`) →
`create_dicom_seg` (`dicom_utils.py:480-696`): SOP Class `1.2.840.10008.5.1.4.1.1.66.4`,
`SegmentationType=BINARY`, bit-packed, one `SegmentSequence` per label typed as
"Morphologically Abnormal Structure" (lesion). *Note*: a second service-level "DICOM
export" produces a **Secondary Capture** series, not a true SEG — don't confuse them.

---

## 3. Lesion analysis (once a mask exists)

- **Connected components** via `scipy.ndimage.label`, run **per-label**
  (`lesion_analysis_service.py:86-89`). Connectivity is **never set** → scipy default =
  **6-connectivity** (faces only). Implicit and undocumented.
- **Min lesion size** = `MIN_LESION_VOLUME_MM3 = 3.0` — **duplicated as an independent
  literal** in two modules (`lesion_analysis_service.py:38`, `ms_region_classifier.py:93`).
- **Volume** = `voxel_count * prod(voxel_spacing)`; per-lesion mm³/mL, size category,
  centroid, bbox (`:102,128-129`). **`voxel_spacing` is required** — the route resolves it
  and raises `VoxelSpacingUnavailableError` if absent (RC-024/CAPA-001 CA-5); no silent
  1 mm assumption.
- **Region classification** (`ms_region_classifier.py`): four regions (PV/JC/IT/DWM),
  methods = parcellation/EDT, atlas/MSMask, geometric, or LST-AI pre-computed zones;
  `auto` cascades lst-ai → parcellation → msmask → geometric. **Per-lesion confidence is
  emitted** for the calibrated paths and **honestly withheld (`None`)** for the geometric
  fallback (`:408-417`) — RC-010.
- **DIS (McDonald 2024)**: **3 of 5 regions** (PV/JC/IT); spinal cord and optic nerve are
  **honestly marked not-evaluated** (`compute_dis_criteria`, `:280-285`) — correct, since
  they cannot be assessed from a brain scan. DIS met when ≥2 brain regions present; a
  region is "present" only with ≥1 component ≥3 mm³.
- **CVS/PRL**: manual-annotation storage + rule aggregation (Select-6, 40%, ≥1 PRL) exist
  (`schemas.py:146-160`, `segmentation_analysis.py:498-593`). **No automated detection** on
  SWI/T2*/phase — all `cvs`/`prl` code is annotation plumbing or documentation.

---

## 4. Findings, ranked by impact

### Clinical-correctness (highest priority)

1. **6-connectivity for lesion components, implicit and undocumented.** Faces-only
   connectivity fragments a diagonally-touching lesion into multiple components, inflating
   lesion *count* and depressing per-lesion *size* versus the 18/26-connectivity commonly
   used in MS lesion analysis. `scipy.ndimage.label` is called with no `structure`
   everywhere (`lesion_analysis_service.py:89,240`; `ms_region_classifier.py:180,362,491`;
   `longitudinal_tracking_service.py:36`). This is a defensible choice **only if
   deliberate and documented** — it is neither. It changes lesion count and DIS
   ("≥2 regions with a qualifying lesion") outcomes.

2. **Inconsistent small-lesion filtering across endpoints.** Per-lesion analysis and DIS
   drop components < 3 mm³; **total lesion burden** (`lesion_analysis_service.py:154-156`)
   and **longitudinal tracking** (`longitudinal_tracking_service.py`) apply **no** filter.
   The same study yields different lesion accounting depending on which endpoint is asked.

3. **`MIN_LESION_VOLUME_MM3` duplicated as two independent literals.** Comments claim
   consistency; nothing enforces it. A future edit to one silently diverges the
   qualifying-lesion threshold between analysis and classification.

4. **Ambiguous-square-mask orientation.** All transpose auto-detection keys on
   `width !== height`. For a **256×256** (standard) acquisition a genuine axis swap is
   undetectable, so a transposed square mask renders and *paints* mis-oriented with no
   correction (`SegmentationCanvasLocal.tsx:577-583`). This is the same class as CAPA-004
   (RC-012) and remains open on the paint/render path.

### Functional gaps that mislead the user

5. **The AI auto-segmentation UI is not rendered.** `AISegmentationTab` (mode buttons,
   model select, progress bar, Run/Cancel) is defined (`SegmentationPanel.tsx:255`) but the
   panel only renders `load | new | tools` (`:655-677`), and `onAIRun`/`onAICancel` are
   unused. So there is **no surfaced "Run AI" button** in the current build. (The
   interactive-click flow can still fire via canvas clicks in `ImageViewer2D`, but the
   auto flow has no entry point.)

6. **AI tool output is stored in a format the main loader does not read.** Sidecar results
   write `segmentations/clinical-tools/{id}/mask.bin` (12-byte-header binary + flat
   Firestore doc) (`tool_runner_service.py:602-692`), but `_load_masks_from_gcs` reads only
   `segmentations/{id}/masks.nii.gz` / `.npz` (`segmentation_service.py:879-929`). A
   LST-AI/mindGlide result therefore may not be loadable by the standard
   `SegmentationService.get_loaded()` path the classifier and viewer use. (Conditional —
   AI is off by default, so this path is not exercised in the default deployment — but it
   is a real integration seam to close before enabling AI.)

7. **mindGlide degrades to an all-zero mask when the package is absent**
   (`docker/mindglide/server.py:101-113`) — a silent "success" producing zero lesions. A
   missing model should fail, not return an empty segmentation that reads as "no disease."

8. **`qualifying_lesion_count` computed but never shown.** It reaches the API and the
   frontend type (`types/lesion.ts:61`) but no component renders it — the DIS-supporting
   count a clinician would want is discarded at the UI.

### Cosmetic / naming (low, but they erode trust in a Class C tool)

9. **"Circular" brush paints a square** on the backend (`_apply_circular_brush` writes a
   rectangle, `segmentation_service.py:361`); the frontend brush is a true disc but ignores
   the `'square'` shape setting (`useSegmentationMask.ts:334`).

10. **The "Fill" tool does not flood-fill.** The toolbar shows Fill
    (`SegmentationPanel.tsx:173-181`) but there is no flood-fill code; selecting it paints
    like a brush. (Same class as the earlier "decoy Fill tool" finding.)

11. **Selected-lesion box uses a separate, "empirically" hard-coded axis convention**
    (`SegmentationCanvasLocal.tsx:685-700`), independent of the mask's transpose logic — a
    latent source of box-vs-overlay misalignment.

---

## 5. What is genuinely solid

- The **local-first mask architecture** (in-memory `Uint8Array`, single binary
  upload, ref-based id-swap with explicit race avoidance) is clean and correct.
- **`voxel_spacing` is required, not assumed** — measurements refuse to compute from
  unknown geometry (RC-024).
- **Per-lesion confidence is honestly `None`** on the uncalibrated geometric path rather
  than fabricated (RC-010).
- **DIS honestly reports 3/5** and discloses the two regions a brain scan cannot assess.
- **Object-level authorization** is enforced on every segmentation route (RC-029), with
  the patient derived from `file_id`.
- **DICOM-SEG export** is a real, standards-correct Segmentation object (SOP
  `…66.4`, BINARY, per-label segments) — the right integration primitive per the
  build-vs-buy research (§4b of the strategy doc: emit DICOM SR/SEG into the customer's
  viewer).
- The **NIfTI-native orientation-on-save** logic, including the documented zone-map
  transpose workaround, reuses the original MRI affine so masks align in ITK-SNAP/NiiVue.

---

## 6. Recommended next steps (not yet actioned)

1. **Decide and document connectivity** (likely 18- or 26-connectivity for MS lesions),
   set `structure` explicitly at every `cc_label` call, and add a test pinning lesion
   count on a known diagonal-touching phantom.
2. **Unify the min-size filter** into one shared constant and apply it consistently
   (or deliberately document where it is not applied and why).
3. **Fix the square-mask orientation ambiguity** on the paint/render path (derive axis
   order from the NIfTI affine, as CAPA-004 CA-4.1 did for the loader) — this is a
   patient-safety item (wrong-side/mis-located painting).
4. **Close the AI storage seam** (make sidecar output land as `masks.nii.gz` under
   `segmentations/{id}/`, or teach the loader the clinical-tools layout) **before**
   enabling any AI tool; make a missing model **fail**, never emit an empty mask.
5. **Render `qualifying_lesion_count`** and either wire or remove the dead AI tab and the
   non-functional Fill tool — a Class C tool should not present controls that do nothing.

Items 1–3 change reported numbers and should be treated as risk-controlled changes
(new hazard/RC, test-bound, negative-controlled) in the same manner as the CAPA work.

---

## 7. State-of-the-art evidence and resolution — 2026-07-27

A focused deep-research pass (22 claims confirmed, 3 refuted, primary sources) set
defensible standards for the three clinical-correctness items above.

### 7.1 Connectivity (issue #1) — RESOLVED as RC-030

**Finding (HIGH):** the two canonical MS challenges both define a discrete lesion as
an **18-connected component**:
- ISBI-2015 (Carass et al., NeuroImage 2017): "the 18-connected components of MR."
  https://pmc.ncbi.nlm.nih.gov/articles/PMC5344762/
- MSSEG-2016 (Commowick et al., Sci Rep 2018): "connected components … with a
  18-connectivity kernel." https://www.nature.com/articles/s41598-018-31911-7

scipy's default is 6-connectivity, which over-counts. **Resolved**: all seven
lesion-counting sites now use a shared `label_lesions` (18-connectivity) in
`app/services/lesion_metrics.py`, bound to `test_rc030_lesion_metrics.py`
(negative control: revert to 6-conn → 3 failed).

**Honest limits recorded in the control:** 18-conn is the challenge-*evaluation*
standard, not a clinical consensus (MAGNIMS/OFSEP prescribe none); and CC labelling
cannot separate **confluent** lesions at any connectivity, so lesion **count** is
inherently less reliable than **volume/load** (ρ ~0.92–0.97 vs ~0.83–0.94;
ConfLUNet, Dumont et al. 2025). Downstream reporting must weight count accordingly.

### 7.2 Minimum lesion size (issues #2, #3) — RESOLVED as RC-030

**Finding (HIGH):** the only genuinely citable 3 mm³ figure is MSSEG-2016's
evaluation gate (removes lesions < 3 mm³ before detection scoring), applied in mm³
(resolution-agnostic). **Critical confound (verified):** the clinical "3 mm" MS
lesion threshold is a **DIAMETER** (~14 mm³ sphere), not 3 mm³; and the claim that
LST-AI enforces a 3 mm³ floor was **REFUTED (0-3)**. The old "~3 voxels at 1 mm"
comment conflated these.

**Resolved**: the constant is kept at 3.0 mm³ **but** re-anchored to MSSEG-2016 and
explicitly documented as *not* the 3 mm-diameter criterion; the duplicated literal
is consolidated into `lesion_metrics.MIN_LESION_VOLUME_MM3`; longitudinal tracking
now applies the same floor (issue #2 filtering-inconsistency). Total lesion **load**
deliberately still counts all voxels — it is a volume, and volume is the reliable
metric (see §7.1), so that is correct, not inconsistent; now documented as such.

### 7.3 Reporting standards (informs future work)

**Findings (HIGH):** the 2021 MAGNIMS-CMSC-NAIMS consensus anchors on **3D-FLAIR**
with **new-lesion detection** as the monitoring endpoint; **volume/load** is far more
reliably measured than count. A world-class product must report **lesion-wise
detection F1 (precision/recall) alongside Dice**, per public dataset (MSSEG-2016,
ISBI-2015, MSLesSeg/ICPR-2024, Shifts), because failures concentrate in small
lesions that voxel-Dice hides. Today's SOTA is voxel Dice ~0.65–0.80 / lesion-F1
~0.63 (LST-AI). These set the bar for the planned validation harness (CAPA-005) and
the report layer.

### 7.4 Pipeline / licensing (informs the AI enablement decision)

**Findings (HIGH):** **LST-AI** (paired 3D T1 + FLAIR, containerized) is the
best-documented open default (Dice ~0.67, lesion-F1 ~0.63), **but its licence is
NOT confirmed permissive** (a permissive-licence claim was refuted) — this must be
resolved before enabling it in a commercial Class C device. Combined with the
issues already logged (§4.6 AI output not read by the loader; §4.7 mindGlide emits
an all-zero mask when its package is missing), **the AI lesion path must not be
enabled until: (a) LST-AI licensing is cleared, (b) the storage seam is closed, and
(c) a missing model fails rather than returning empty.**
