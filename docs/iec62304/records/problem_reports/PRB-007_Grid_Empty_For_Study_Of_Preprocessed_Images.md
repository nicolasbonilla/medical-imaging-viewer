# PRB-007 — The 2×2 Grid Showed "No image assigned" for a Study of Preprocessed Images Only

*Software problem report per SPR-001 §1 (layout of PRB-001). No GitHub Issue raised — owner action.*

**Problem ID**: PRB-007 (GitHub Issue: not raised — owner action)
**Reporter**: browser capture session of the release candidate (PR #69 @ `6d1fde2`, finding F05 in
`mstool-film/assets/app-captures/CAPTURES.md` §5; screenshot `findings/F05_grid_no_image_assigned_when_only_preprocessed.png`,
still `stills/06_multipanel_2x2.png`); reproduced on `main` and record drafted by the AI coding agent
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7`. The grid's image source exists since `67fa336` (2026-02-28); the toolbar since `e0bdb7e`
(2026-04-21). The release branch does not change this.
**Severity**: **Minor** (proposed; SPR-001 §2: a workaround exists — the hidden "Original/Preproc" switch). Not
safety-related. **PENDING owner approval.**
**Status**: OPEN — DRAFT. Fix implemented on branch `fix/viewer-display-orientation-prb004` (draft PR).

**Description**: In a study whose images are all preprocessed (the demo study; any study uploaded already registered), the
1×2 and 2×2 grids showed "No image assigned" in every panel and a "1/0" slice counter. The grid took its images from the
"originals" group, empty here, and assigned nothing. With four images of which two are T1-weighted (T1w and T1w after
contrast) the grid filled three panels and left the fourth empty — with a red "ORIENTATION UNKNOWN" banner, because an
empty panel reports no orientation.

**Steps to Reproduce**: open a study whose image names all contain `desc-preproc` (or end in `_pp.nii`), click the 2×2
layout button.

**Expected Behavior**: the grid shows the images the study has; spare panels take the remaining images.

**Actual Behavior** (`main` @ `70cc5c7`): `frontend/src/ViewerApp.tsx:188` (source state `'originals'`), `:233-237`
(the grid reads the originals unless "preprocessed" was chosen), `:243` (nothing assigned when the chosen group is empty);
`frontend/src/utils/sequenceDetection.ts:81-96` (one image per sequence, then only images of unknown sequence).

**Safety Impact Assessment**: none (no wrong content; the panels are empty and say so). Class C item: no.

## 1. Root Cause

The grid's image group was chosen by a UI state with a default ("originals") that does not depend on what the study holds;
the empty case was not considered. The panel filling rule assumed one image per sequence.

## 2. Resolution — implemented on branch, PENDING owner approval

- `frontend/src/utils/instanceClassification.ts`: `multiPanelImages(requested, originals, preprocessed)` — the requested
  group when it has images, otherwise the other; returns the group actually shown.
- `frontend/src/ViewerApp.tsx`: the grid, the layout buttons and the source switch use it; the switch names the group
  actually shown and is disabled (with a tooltip) when the study has no originals.
- `frontend/src/utils/sequenceDetection.ts`: after one image per sequence and the unknown ones, the remaining images fill the
  spare panels in study order; an image is never assigned twice.
- Requirement: new **REQ-FUNC-102**. The orientation banner of an empty panel is unchanged (RC-023: a panel without an image
  reports no orientation) — it now appears only when the study has fewer images than panels.

## 3. Verification

- Failing-first tests: `frontend/src/ViewerApp.prb007.test.tsx` (the real viewer page; the 3 `prb007` tests fail on `main`),
  `frontend/src/utils/sequenceDetection.prb007.test.ts` (2 of 3 fail on `main`; the guard passes on both). Record
  `records/risk_verification/PRB-004_tests_on_base_2026-10-28.json`.
- Negative controls G1–G4 (no fallback, spare panels not filled, an image twice, the switch naming the requested group):
  **4 of 4 detected** — `records/risk_verification/PRB-004_negative_controls_2026-10-28.json`.
- Real browser: 2×2 grid of a four-image preprocessed study — fixed: four panels drawn, none empty; `main`: four panels, all
  "No image assigned" —
  `records/risk_verification/PRB-004_viewer_display_probe_2026-10-28.json`.

## 4. Owner decisions

- Severity Minor.

## 5. Closure — not applicable yet
