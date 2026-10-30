# PRB-008 — The Viewer Opened Every Image on Slice 1, Outside the Head

*Software problem report per SPR-001 §1 (layout of PRB-001). No GitHub Issue raised — owner action.*

**Problem ID**: PRB-008 (GitHub Issue: not raised — owner action)
**Reporter**: browser capture session of the release candidate (PR #69 @ `6d1fde2`, finding F15 / F13 in
`mstool-film/assets/app-captures/CAPTURES.md` §5; screenshot `findings/F15_viewer_opens_at_slice_1_blank.png`); reproduced on
`main` and record drafted by the AI coding agent
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7`; slice index 0 at opening since the first commit. The release branch does not change this.
**Severity**: **Minor** (proposed; a blank first view, one scroll away from the brain). Not safety-related. **PENDING owner
approval.**
**Status**: OPEN — DRAFT. Fix implemented on branch `fix/viewer-display-orientation-prb004` (draft PR).

**Description**: Every image opened on slice index 0 ("1/182"): for a head MRI the first axial slice is below or at the edge of
the head, an empty black image. Switching to another image kept whatever index was set before — also when the new image had
fewer slices (index outside the image, nothing drawn) or belonged to another study. Grid panels opened on slice 1 as well.

**Expected Behavior** (rule, REQ-FUNC-103): an image opens on its middle slice, floor((n − 1) / 2); another image of the same
study with the same number of slices keeps the current slice (comparing sequences of one examination at the same level); any
other switch opens the new image on its middle slice; a grid panel opens on the middle slice of its image unless it already
has a position (synchronised scrolling). The slice does not move when a segmentation is opened or closed. (Opening on the slice
with the most mask voxels was considered and not chosen: it would move the slice whenever a mask is opened, and a slice chosen
by the mask can lead the reader to look only where the mask is.)

**Actual Behavior** (`main` @ `70cc5c7`): `frontend/src/store/useViewerStore.ts:103` (`currentSliceIndex: 0`), never reset on
opening; `frontend/src/ViewerApp.tsx:355` (`setCurrentSeries` only); `frontend/src/components/MultiPanelViewer.tsx:277` (first
image of a panel = slice 0); `frontend/src/store/useMultiViewerStore.ts` (panels assigned at index 0).

**Safety Impact Assessment**: none. Class C item: no.

## 1. Root Cause

No requirement said which slice an image opens on; the store's initial value 0 served as the answer.

## 2. Resolution — implemented on branch, PENDING owner approval

- `frontend/src/utils/sliceOnOpen.ts` (new): `middleSliceIndex`, `sliceIndexOnOpen` (the rule above).
- `frontend/src/store/useViewerStore.ts`: `openSeries(series, { sameStudy })` sets the image and its slice in one update.
- `frontend/src/ViewerApp.tsx`: opens every image through `openSeries`, remembering the study of the last opened image.
- `frontend/src/components/MultiPanelViewer.tsx` + `useMultiViewerStore.setPanelSliceIndex`: a panel's first image is its
  middle slice.

## 3. Verification

- Failing-first tests: `frontend/src/ViewerApp.prb007.test.tsx` (3 `prb008` tests on the real viewer page, all fail on `main`:
  index 0; index 5 kept for a 9-slice image; grid panels at 0); `frontend/src/utils/sliceOnOpen.test.ts` (the rule; on `main`
  the file fails to load: the module does not exist).
  Record `records/risk_verification/PRB-004_tests_on_base_2026-10-28.json`.
- Negative controls S1–S6 (slice 0, the page bypassing the rule, kept across studies, kept for another size, grid panels on
  slice 0, a different middle): **6 of 6 detected** — `records/risk_verification/PRB-004_negative_controls_2026-10-28.json`.
- Real browser: the synthetic 36-slice study opens on "18/36" (fixed) and on "1/36" (`main`) —
  `records/risk_verification/PRB-004_viewer_display_probe_2026-10-28.json`.

## 4. Owner decisions

- The opening rule (middle slice; keep within one study for images of the same size) — REQ-FUNC-103 to be approved, and stated
  in the IFU.

## 5. Closure — not applicable yet

## R. Independent review of PR #71 and film capture (2026-10-28) — PENDING owner approval

- **m4 (review)**: the slice was kept on an image switch within one study whenever the slice COUNT matched. Two sequences with the
  same number of slices but another matrix, voxel size, slice thickness or stored orientation put the same index at another
  anatomical level. The slice is now kept only when the two images report the same voxel grid (slice count, rows, columns,
  slices, pixel spacing and slice thickness within 0.001 mm, stored orientation; a field neither reports cannot tell them apart)
  — `sameReportedGrid` in `utils/sliceOnOpen.ts`. REQ-FUNC-103 reworded. Test `utils/sliceOnOpen.review.test.ts` (4 + a guard);
  fails on `39f9d44`. Negative controls V31–V34.
- **Sidebar slice in the side-by-side panels (film capture)**: the sidebar's slice navigator (`ControlPanel`) read the single
  view's slice index while the 1x2 / 2x2 grid navigates its own per-panel index: it named a slice the panels did not show, gave
  the single image's slice count, and its slider moved nothing on screen. It now follows the active panel, as the toolbar does
  (`useActiveSliceInfo`). Test `components/ControlPanel.prb008.test.tsx` (2 + a guard); fails on `39f9d44` (`records/risk_verification/PRB-004_review_tests_on_39f9d44_2026-10-28.json`). Negative
  controls V41–V43.
