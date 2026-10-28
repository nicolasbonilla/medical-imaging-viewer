# PRB-004 — The "W/L GPU" 2D View Showed Every Slice Rotated by 90° Against the Standard View

*Software problem report per SPR-001 (`docs/iec62304/08_Problem_Resolution_Procedure.md` §1), following PRB-001's
layout. SPR-001 says problem reports are GitHub Issues; none has been raised in this repository. This record is kept
under `docs/iec62304/records/problem_reports/`. A GitHub Issue citing this ID is to be raised by the owner; the agent
did not raise one.*

**Problem ID**: PRB-004 (GitHub Issue: not raised — owner action)
**Reporter**: browser capture session of the release candidate (PR #69, `release/owner-signoff-2026-10-25` @ `6d1fde2`,
finding F16 / F14 in `mstool-film/assets/app-captures/CAPTURES.md` §5, screenshot
`findings/F16_standard_vs_wlgpu_axial_rotated_90deg.png`); reproduced on `main` and record drafted by the AI coding agent
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7`. The GPU view exists since `4584b81` (2026-08-21); the standard view has drawn the stored
voxel order since the first commit. The release branch does not change either file's display logic.
**Severity**: **Critical — safety-related** (proposed; SPR-001 §2 classes a problem with a safety impact as Critical;
HAZ-006). **PENDING owner approval.**
**Status**: OPEN — DRAFT. Fix implemented on branch `fix/viewer-display-orientation-prb004` (draft PR, not merged, not
deployed). No Class C module of the CLAUDE.md list is changed by this fix; it changes how a Class C image is presented,
so a code review is required before merge.

**Description**: The viewer's 2D image has three "render modes": *Standard*, *Matplotlib* and *W/L GPU* (fast
window/level in niivue, view-only). Standard and Matplotlib draw the server's slice of the stored array as it is:
storage voxel (i, j) of slice k at row i (down the screen), column j (to the right); the lesion mask is overlaid voxel
for voxel in that same order, and painting happens there. The multi-panel grid draws the same server slices. The W/L
GPU view instead handed the NIfTI to niivue, which places every voxel by the scanner affine and shows an anatomical
axial view (anterior up). For the usual storage orientations the two layouts differ by a 90° rotation and, depending on
the stored orientation, a mirror. Switching mode turned the image (and the mask) on the screen; a clinician comparing
the two, or locating in one mode a lesion seen in the other, could look at the wrong place or the wrong side. The GPU
view's slider also addressed a position between two slices (`index / (depth − 1)`), so most slices were a blend of two
neighbouring slices and slice 1 was the volume's outer edge.

**Steps to Reproduce** (each step reproduced by a test written before the fix, §6):
1. Open any NIfTI study whose axial slices are stored in the usual order (e.g. LAS from dcm2niix or FSL, RAS from
   nibabel tools) — the demo study is LAS.
2. In *Standard*, note where a lesion is; switch the render mode to *W/L GPU*.
3. The slice is rotated by 90° (anterior to the side in Standard, on top in W/L GPU), the lesion elsewhere on the screen.

**Expected Behavior**: Every 2D render mode shows the same slice with the same voxel-to-screen layout, and the mask on the
same voxels; a mask that cannot be drawn voxel for voxel on the image is not drawn, and the view says so.

**Actual Behavior** (`main` @ `70cc5c7`):
- Standard / Matplotlib / multi-panel: `backend/app/services/imaging_service.py:268` (`slice_data = pixel_array[:, :, i]`,
  also `:379`, `:635`) — row = storage axis 0, column = storage axis 1, no affine; drawn as is by
  `frontend/src/hooks/useCanvasRendering.ts` and the mask by `SegmentationCanvasLocal.tsx` (internal (k, a0, a1), RC-031).
- W/L GPU: `frontend/src/components/NiivueViewer2D.tsx:133-135` loads the raw NIfTI into niivue, which lays it out by
  `hdr.affine` (anatomical axial view); `:144` loads the mask the same way. `:71` with
  `frontend/src/utils/niivueWindowLevel.ts:51` (`index / (depth − 1)`) sets the slice.
- Measured with niivue's own transforms on a 6 × 8 × 5 LAS volume (failing-first test, §6): the voxel the standard view
  draws top-left (row 0, column 0) is drawn by the GPU view bottom-right of the slice (fraction right 0.94, down 0.92);
  rows run right-to-left and columns bottom-to-top — a 90° rotation plus a mirror. The slider: niivue reads a fraction f
  as voxel f · depth − 0.5, so with 5 slices index 0 → −0.5 (the volume's outer edge; fraction 0 instead of 0.1), 1 → 0.75,
  3 → 3.25 (blends of two slices); with 182 slices index 45 → 44.75 (three quarters of slice 45, one quarter of slice 44).

**Safety Impact Assessment**:
- [x] Could contribute to a hazardous situation — **HAZ-006** (orientation/laterality error: the same lesion shown on
  another side or in another quadrant in a view of the same patient). Cause recorded in RMF §3.
- [ ] Affects a Class C software item of the CLAUDE.md list — no (`NiivueViewer2D.tsx`, `niivueWindowLevel.ts`); the
  presentation of Class C image and mask data is affected.
- [ ] Requires regulatory notification (EU MDR Article 87) — no: the device is not CE-marked and not in clinical use.

---

## 1. Triage (SPR-001 §3.1)

- **Reproducible**: yes, on `main` by the failing-first tests (§6) and in a real browser (§6, probe on `main`).
- **Severity**: proposed Critical, safety-related (§5).
- **Assigned to**: *(to be assigned — owner decision)*.

## 2. Root Cause (SPR-001 §3.2)

1. **Two coordinate conventions for one image.** The standard view (and the editor, the mask store and every lesion
   coordinate) uses the stored voxel order; niivue uses the scanner affine. The GPU view was added (2026-08-21) on top of
   niivue's default without mapping one convention to the other. Its header said "opt-in, never the default, until
   browser visual-QA confirms slice/orientation parity with the standard viewer" — that check was never done, and nothing
   tested the parity. Same family as CAPA-010 ("coordinate conventions re-implemented per view").
2. **The slice mapping was written as a proportion, not a voxel address** (`index / (depth − 1)`), while niivue reads a
   fraction f as voxel f · depth − 0.5.
3. **Orientation of the 2D display is not an established control.** RC-013 (canonical orientation on load) is NOT
   IMPLEMENTED (RMF §4); every 2D view shows the stored voxel order. The 3D view shows the anatomy by the affine. There is
   no requirement that the 2D render modes agree.

## 3. Impact Analysis (SPR-001 §3.3)

| View | Layout before | After the fix |
|---|---|---|
| 2D Standard (editing) | stored voxel order (row i down, column j right) | unchanged |
| 2D Matplotlib | stored voxel order (server, `imshow(origin='upper')`) | unchanged |
| 2D multi-panel grid | stored voxel order (server slices) | unchanged |
| 2D W/L GPU | scanner affine (anatomical axial), slice between voxels | **stored voxel order, voxel-centre slice** — the same as Standard |
| 3D volume / multiplanar | scanner affine | unchanged (a 3D rendering must keep the anatomy's handedness; RC-023 letters stay off) |

- Mask in the GPU view: given the image's layout, so drawn voxel for voxel as in Standard. Drawn only when stored on the
  image's own grid (same dimensions, voxel-to-scanner transform within 0.001 per element — RC-039's tolerance) and in the
  image's voxel order (RC-031 marker); a legacy mask (in-plane transpose on disk, undetectable by shape on a square slice),
  a mask on another grid or one that fails to load is **not drawn** and an amber notice says why and to use the Standard
  view. Before, the GPU view drew any mask by its own affine and silently skipped one that failed.
- Requirements: new **REQ-SAFE-041**. RC-023 (no laterality glyph) unchanged: the GPU view still draws no letters.
- Risk controls: new **RC-073**; RC-013 stays NOT IMPLEMENTED (owner decision D-1).
- Released versions: the GPU view is opt-in and has been in production since 2026-08-21 (deploys after `4584b81`);
  how often it was used is unknown (no usage record exists).

## 4. Resolution (SPR-001 §4) — implemented on branch, PENDING owner approval

- `frontend/src/utils/niivueVoxelGrid.ts` (new): `standardViewAffine` — voxel (i, j, k) → display (x = j·s1, y = −i·s0,
  z = k·s2) for niivue's axial screen (+x right, +y up); `placeAsStandardView` applies it before a volume is added;
  `maskMatchesImageGrid` (dimensions, affine within 0.001, RC-031 marker). Display transform only: nothing is written to
  any file, the 3D view keeps the scanner affine.
- `frontend/src/components/NiivueViewer2D.tsx`: the image's grid is read, then the image AND the mask get the image's
  standard-view layout; the mask is refused with a stated reason when not on the image grid / order or not loadable;
  `isRadiologicalConvention: false` stated (the layout assumes it).
- `frontend/src/utils/niivueWindowLevel.ts`: `sliceIndexToVoxelCentreFraction` ((index + 0.5) / depth) replaces
  `sliceIndexToFraction`; the GPU view shows the standard view's slice exactly.
- Texts en/es/de: `viewer.gpuMaskNotShown*`.

## 5. Severity Rationale (SPR-001 §2)

A view of the same patient that turns the image by 90° (and may mirror it) when a display option is switched is an
orientation/laterality hazard (HAZ-006, severity S5 in RMF §5.1). The GPU view is opt-in and view-only, painting stays in
Standard, and the viewport carries "Laterality not labelled — confirm side against the source study" — these lower the
probability, not the severity. Proposed Critical.

## 6. Verification

- **Failing-first tests** (`frontend/src/components/NiivueViewer2D.prb004.test.tsx`, tests named `rc073`; niivue's renderer
  replaced, its parser, affine math and loaders real — `src/test/niivueHarness.ts`, `src/test/syntheticNifti.ts`): on `main`
  @ `70cc5c7` **7 of the 9 `rc073` tests fail** (voxel layout, slice, mask layout, refusal for another grid / another
  position / no RC-031 marker / a load failure); the harness pin (niivue's own
  orientation-text routine draws "L" left and "A" top with the view's options) and the guard "a mask on the image grid is
  drawn" pass on both. `frontend/src/utils/niivueWindowLevel.test.ts`: the 5 voxel-centre slice tests fail on `main`
  (function absent; the 5 window/level tests are unchanged and pass). Record:
  `records/risk_verification/PRB-004_tests_on_base_2026-10-28.json` (`scripts/safety/prb004_tests_on_base.py`).
- **Negative controls**: `scripts/safety/prb004_negative_controls.py`, mutations O1–O13 (layout removed for the image or
  the mask, transposed or flipped layout, radiological flip, each refusal removed or loosened, refusal or load failure not
  stated, old slice mapping, grid read after the transform): **13 of 13 detected**; failing tests per mutation in
  `records/risk_verification/PRB-004_negative_controls_2026-10-28.json` (52 mutations for PRB-004..010, 52 detected).
- **Real browser** (`scripts/safety/prb004_viewer_display_probe.mjs`: real app, real niivue/WebGL in headless Edge, synthetic
  40 × 48 × 36 LAS study with two markers and a lesion mask, slice 18 of 36, positions from the rendered pixels relative to
  the drawn head): fixed branch — marker B at (0.180, 0.769) in Standard and (0.179, 0.770) in W/L GPU, the lesion drawn red
  at (0.867, 0.397) and (0.867, 0.398); `main` (served on 127.0.0.1, since on `localhost` its GPU view does not load, PRB-005) —
  in W/L GPU marker B at (0.326, 0.635), marker A at (0.602, 0.130), the lesion not drawn red. Record:
  `records/risk_verification/PRB-004_viewer_display_probe_2026-10-28.json`.

## 7. Owner decisions

- **D-1 (open)**: every 2D view still shows the stored voxel order, which for common files is not the radiological
  convention (anterior up); the 3D multiplanar slices are anatomical. RC-013 (canonical display with verified
  orientation) changes the painting coordinates and needs its own change with browser QA — proposed, not done here.
- **D-2**: severity Critical and the CAPA linkage (proposed: CAPA-010 extended with CA-10.9, same root cause; or a new CAPA).
- **D-3**: legacy masks (stored before RC-031) are no longer drawn in the GPU view (they are still drawn in Standard,
  through the marker-aware loader). Accept, or migrate the stored masks.

## 8. Closure (SPR-001 §4, step 6) — not applicable yet
