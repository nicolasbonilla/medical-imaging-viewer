# PRB-006 — The Lesion Mask Was Coloured With the MRI's Display Window ("Red Fog", Nearly Invisible Lesions)

*Software problem report per SPR-001 §1 (layout of PRB-001). No GitHub Issue raised — owner action.*

**Problem ID**: PRB-006 (GitHub Issue: not raised — owner action)
**Reporter**: browser capture session of the release candidate (PR #69 @ `6d1fde2`, finding F02 in
`mstool-film/assets/app-captures/CAPTURES.md` §5; screenshots `findings/F02_3d_red_fog_overlay_inherits_mri_display_range.png`,
`findings/F02b_multiplanar_red_tint_and_mask_empty_card.png`); reproduced on `main` and record drafted by the AI coding agent
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7`. The stored mask copies the MRI header since `c019b93` (2026-01-18); the 3D overlays have no
display range of their own since `67fa336` (2026-02-28), the GPU view's since `4584b81` (2026-08-21).
**Severity**: **Major — safety-related** (proposed; the lesions can be missed in the 3D and GPU views — HAZ-001 and, for the
two visit masks of the longitudinal overlay, HAZ-007; the standard 2D view, where the mask is reviewed, was not affected).
**PENDING owner approval.**
**Status**: OPEN — DRAFT. Fix implemented on branch `fix/viewer-display-orientation-prb004` (draft PR).

**Description**: A segmentation is stored as a NIfTI written with a copy of the source MRI's header, so that it lines
up exactly in other viewers. The copy kept the MRI's *display window* — `cal_min`/`cal_max`, e.g. −15.5 / 189.2 in the
demo study. niivue honours that window when it colours an overlay: the mask's background value 0 lies inside the window
and gets a faint red, every lesion label (1, 2, …) lies at the bottom of the colour scale and is nearly transparent. In
the 3D volume render the faint red of every background voxel adds up along each ray: the whole volume is tinted red and
the lesions are hard to see; in the multiplanar and GPU views the slices are tinted. The mask's colours depended on the
image's window, which they must not.

**Steps to Reproduce**: open a study whose MRI header has a display window (`cal_max` > 0 — many converters write one), open
a saved segmentation, switch to *3D* (volume or multiplanar) or to the *W/L GPU* mode.

**Expected Behavior**: background transparent, every lesion label drawn in full colour, whatever the image's window or the
mask header says; a stored mask carries its own display range.

**Actual Behavior** (`main` @ `70cc5c7`):
- `backend/app/services/segmentation_service.py:1011` copies the MRI header; `:1055-1059` reset the data type, scaling and
  description but not `cal_min`/`cal_max`.
- `frontend/src/components/ImageViewer3D.tsx:369` (mask), `:394` / `:403` (earlier / later visit), `:462`, `:489`, `:497`
  (multiplanar) and `frontend/src/components/NiivueViewer2D.tsx:144` load the masks with no display range: niivue uses the
  header's (`readNifti`, `trustCalMinMax`). Reproduced with niivue's own loader: a mask with `cal_min`/`cal_max`
  −15.5 / 189.2 loads with exactly that range (failing-first tests, §4).

**Safety Impact Assessment**:
- [x] Could contribute to a hazardous situation — HAZ-001 (lesions not seen in the 3D and GPU views) and HAZ-007 (visit
  masks of the longitudinal overlay tinted). Cause recorded in RMF §3.
- [ ] Affects a Class C software item of the CLAUDE.md list — no.
- [ ] Requires regulatory notification — no.

## 1. Root Cause

A spatial header was reused as a whole for data of another kind (labels, not intensities); only the fields known to
matter (data type, scaling) were reset. On the display side every overlay relied on niivue's defaults, which read the
header. Nothing tested the colours a mask is given.

## 2. Impact Analysis

| Path | Before | After |
|---|---|---|
| Stored mask NIfTI (every save) | MRI window | `cal_min` 0, `cal_max` highest label (at least 1); spatial header, RC-031 marker, verbatim labels (P-4.1) unchanged |
| Stored mask without the MRI header (fallback, MRI unreadable) | 0 / 0 | the same rule |
| 3D volume / multiplanar: lesion mask, earlier visit, later visit | header window | fixed 0 … 1 |
| GPU 2D view: lesion mask | header window | fixed 0 … 1 |
| Zone map (MAGNIMS colours) | fixed 0 … 4 | unchanged |
| Standard / matplotlib / multi-panel | own colouring | unchanged |

Masks stored before the fix keep the MRI window in their file until they are saved again; the app ignores it now. External
viewers (ITK-SNAP, FSLeyes) see the stored window of old files — owner decision D-1. Requirement: new **REQ-SAFE-042**;
risk control: new **RC-074**.

## 3. Resolution — implemented on branch, PENDING owner approval

- `backend/app/services/segmentation_service.py`: `_label_display_range()`; both header paths of `_save_masks_to_gcs` set it.
- `frontend/src/utils/niivueVoxelGrid.ts`: `LABEL_MASK_DISPLAY_RANGE` = { cal_min 0, cal_max 1 } — passed to every mask
  overlay of `ImageViewer3D.tsx` and `NiivueViewer2D.tsx`.

## 4. Verification

- Failing-first tests (named `rc074`): `backend/tests/unit/test_prb006_mask_display_range.py` (6 of 7 fail on `main`; the
  guard that the spatial header and marker are unchanged passes on both), the two `rc074` tests of
  `ImageViewer3D.prb005.test.tsx` and the `rc074` test of `NiivueViewer2D.prb004.test.tsx` (all fail on `main`: the overlay's
  range is −15.5 / 189.2). Record `records/risk_verification/PRB-004_tests_on_base_2026-10-28.json`.
- Negative controls R1–R9 (each niivue overlay with its header range, a fixed range hiding label 1, the stored header keeping the
  MRI window, a stored range cut at 1, the fallback header without a range): **9 of 9 detected** — `records/risk_verification/PRB-004_negative_controls_2026-10-28.json`.
- Real browser (real niivue/WebGL, synthetic study whose mask header carries the window −15.5 / 189.2): share of the viewport
  tinted red with the mask shown — `main` (127.0.0.1): 63 % of the W/L GPU view, 47 % of the 3D render, the lesion not drawn
  red; fixed branch: 2 % and 5 % (the lesion, and niivue's crosshair in 3D) —
  `records/risk_verification/PRB-004_viewer_display_probe_2026-10-28.json`.

## 5. Owner decisions

- **D-1**: rewrite the display range of masks already stored (a header-only rewrite at the next save happens anyway), or
  leave them (the app no longer reads it).
- **D-2**: severity Major, safety-related.

## 6. Closure — not applicable yet
