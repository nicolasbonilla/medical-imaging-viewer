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
| 2D multi-panel grid | stored voxel order (server slices) | unchanged; draws no segmentation (§9, m7) |
| 2D W/L GPU | scanner affine (anatomical axial), slice between voxels | **stored voxel order, voxel-centre slice** — the same as Standard |
| 3D volume / multiplanar | scanner affine | unchanged (a 3D rendering must keep the anatomy's handedness; RC-023 letters stay off). Masks requested aligned to the image and drawn only with a known voxel order and scanner position; "go to slice" on the slice's own axis; no colour bar under the laterality caveat (§9) |

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
- **D-3 (resolved on the branch by the review fix, §9 M1)**: a legacy mask (stored before RC-031) that lies on the image's
  grid is now realigned by the server and drawn in the GPU and 3D views; a legacy mask on another grid stays refused there,
  with the reason (it is still drawn in Standard through the marker-aware loader). Migrating the stored masks remains an
  owner option.

## 8. Closure (SPR-001 §4, step 6) — not applicable yet

## 9. Independent review of the draft PR #71 (2026-10-28) — findings, resolution, verification — PENDING owner approval

An independent review of the draft PR at `39f9d44` (report kept by the coordinator) found the items below; two more
display findings came from the film capture the same day (§9.2). Every item was reproduced by a test written before
its fix; the tests fail on `39f9d44` (`records/risk_verification/PRB-004_review_tests_on_39f9d44_2026-10-28.json`) and on `main` @ `70cc5c7`
(`records/risk_verification/PRB-004_tests_on_base_2026-10-28.json`). Items of other reports: m2 → PRB-006, m10 → PRB-007,
m4 and the sidebar slice → PRB-008, m1 and m6 → PRB-010.

### 9.1 Review findings

| Item | At `39f9d44` | Resolution on the branch | Tests (written first) |
|---|---|---|---|
| **M1** (HAZ-006) | The 3D view (volume and multiplanar) drew the lesion mask and both visit masks by their own affine with no check (`ImageViewer3D.tsx:208-212, :374-377, :473-480`): a mask saved before RC-031 (in-plane transpose, no marker) mirrored about the diagonal, a mask saved with the identity fallback (no scanner position) at an arbitrary place, silently. The aligned route `GET /segmentation/{id}/nifti?ref_file_id=` raised `NameError: io` (`io` imported only inside another function — CAPA-006 PA-6.4), and its code copied the MRI's header: RC-031 marker dropped, MRI display window copied (PRB-006), and the reference affine stamped onto ANY mask of the same shape — an identity-fallback or other-grid mask would have been presented as aligned. | Route: `io` imported; `SegmentationService.align_stored_mask_to_reference` realigns only a mask whose stored voxel-to-scanner transform IS the reference image's (0.001 per element, RC-039's tolerance), undoing the legacy transpose by the RC-031 marker, and serves it with the image's affine, the RC-031 marker and the mask's own display range; any other mask is served unchanged. The GPU and 3D views request every mask with `ref_file_id` (`segmentationNiftiPath`). The 3D view draws a mask only with the RC-031 marker and a scanner position (`maskPlaceableIn3D`); otherwise an amber notice names it (segmentation / earlier visit / later visit) and the reason. | `backend/tests/unit/test_prb004_review_ref_alignment.py` (5; the real FastAPI route, storage and authorization replaced, offline), `ImageViewer3D.prb004.review.test.tsx` (M1: 5), `NiivueViewer2D.prb004.review.test.tsx` (M1: 1) |
| **M2** | A segmentation not saved yet (`local-…`) and unsaved edits were silently absent from the GPU view (`NiivueViewer2D.tsx:115-116`) and the 3D view. | GPU view: "not drawn: it is not saved yet" / "unsaved edits are not shown in this view: it draws the last saved segmentation"; `ImageViewer2D` passes `hasUnsavedEdits` (mask hook or store). 3D: the segmentation named, "not saved yet". | GPU 3 (one checks the `ImageViewer2D` call site, as rc016 does), 3D 1 |
| **M3** (HAZ-006) | 3D "go to slice" (comparison and longitudinal panels) set niivue's axial fraction to index / (depth − 1) (`ImageViewer3D.tsx:690-716`): off by up to half a slice, and on the wrong axis for a sagittally or coronally stored volume. Twin of the selected-lesion path, which already went voxel → mm → niivue (RC-037). | Storage slice k: the centre voxel of slice k through the volume's affine to scanner mm, then niivue's own `mm2frac`, on the niivue axis along which k advances; the other two coordinates kept. | 3D 2 (axial LAS; sagittally stored) |
| **m3** | niivue's own keys (V view type, C clip plane, Ctrl+U/D slice, M drag mode), its wheel (slice) and double-click (contrast reset) acted on the GPU view behind the store: the view could show another slice or window than the one the app reports. | Hotkeys off; the canvas is not focusable; keys, wheel and double-click stopped before niivue's canvas listeners; the wheel steps the store's slice. | GPU 1 |
| **m5** | The GPU notice sat at the top (`top-12`), where the patient-identity block covers it in a narrow view. | Bottom centre, above the standing laterality caveat. Measured in a real browser (headless Edge, the app's Tailwind CSS, the overlay and the GPU view composed as in `ImageViewer2D`, 1100 × 700, 600 × 420, 480 × 330): fully visible, overlapping neither the identity block, the orientation banner nor the caveat. The measurement found that the first review fix (`bottom-10`) touched the caveat where it wraps to two lines; now `bottom-14`. At `39f9d44`: notice over the identity block at 600 × 420. | `NiivueViewer2D.prb004.layout.test.tsx` (real browser), GPU 1 (placement) |
| **m7** | The multi-panel grid kept a mask-overlay path no caller wired (no grid check, colours of its own); REQ-SAFE-041 said every multi-panel cell draws the mask only on its grid. | Path removed; REQ-SAFE-041 now states that the grid draws no segmentation. | `MultiPanelViewer.prb004.review.test.ts` |
| **m8** | Both safety scripts changed source files in the developer's checkout; an interrupted run could leave a mutation in real code. | Both run in a throwaway detached worktree of the commit (`scripts/safety/prb004_throwaway_worktree.py`; `node_modules` a junction removed with `os.rmdir`, never recursively; leftovers of interrupted runs removed first; one run at a time by a lock; `--only` refuses a record of another commit). An interrupted run during this work left the checkout untouched; the next run removed its worktree. | the runs below |
| **m9** | The notice for a mask on another grid sent the reader to the Standard view, which draws a mask voxel for voxel on whatever image it is shown with. | The Standard view is offered only for an older voxel order, a load failure and unsaved work. | GPU 1 |
| **D-3** | — | Resolved by M1 (§7). | as M1 |

### 9.2 Film capture (coordinator, 2026-10-28)

- **3D colour bar under the laterality caveat** (RC-023, HAZ-006 context; CAPA-010): niivue drew its colour bar along the
  bottom of the 3D render (volume view and the 3D cell of multiplanar), under the safety overlay's standing "Laterality not
  labelled — confirm side against the source study" — both unreadable. The colour bar is off in every 3D niivue instance (the
  colour scale of an MRI in arbitrary units is not a measurement; the colormap is named in the sidebar). Test:
  `ImageViewer3D.prb004.review.test.tsx` (`rc023 3D volume / multiplanar`, 2; fail on `39f9d44`). Owner option: bring a colour
  bar back in a place that covers no safety annotation.
- **Sidebar slice in the side-by-side panels**: recorded in PRB-008 §R.

### 9.3 Negative controls

`scripts/safety/prb004_negative_controls.py`, run in a throwaway worktree of `d28890b`: review and film mutations
V1–V43 — 43 of 43 detected; the whole set 95 of 95 (`records/risk_verification/PRB-004_negative_controls_2026-10-28.json`). The real-browser probe of §6 was not
re-run for the review changes: the GPU and 3D changes are covered by tests with niivue's own loaders and math, the notice
placement by the real-browser layout test.

### 9.4 Remaining limits

- The 3D zone map (MAGNIMS zone overlay) is not yet requested aligned nor checked for voxel order and position (it is
  generated by the server on the image's grid; not covered by the review).
- A segmentation of another visit on another grid is composited by its own affine in 3D: no registration (the existing caveat
  "NOT spatially registered" stays).
- The label colour of a value missing from the label table is cyan in the GPU and 3D views (`UNLISTED_LABEL_HEX`); PR #69
  adds a fallback colour for the 2D overlay — the two are to be made one constant when the branches meet.
