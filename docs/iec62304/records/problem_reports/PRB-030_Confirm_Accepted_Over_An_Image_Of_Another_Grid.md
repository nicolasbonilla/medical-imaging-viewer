# PRB-030 — Confirm Was Accepted While the Mask Was Drawn Over an Image of Another Grid (L1)

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: next free after PRB-029. GitHub Issue: not
raised — owner action.*

**Problem ID**: PRB-030
**Reporter**: last check of PR #69 (item L1, `records/releases/RELEASE-2026-10-25_integration_notes.md` §7); accepted by
the owner as "fix in the next version"; fixed by the AI coding agent on branch `fix/next-safety-round`
**Date**: 2026-10-31
**Version**: `main` @ `ca600c2` (pre-existing)
**Severity**: **Minor** (proposed; visibly wrong in most cases, but a confirmed region check can rest on a mask drawn in
the wrong place — HAZ-006, HAZ-008). **N. G. Bonilla Vargas — approved 2026-10-31 (PR #74).**
**Status**: OPEN — DRAFT. Fixed on branch `fix/next-safety-round` (draft PR), not merged, not deployed.

## 1. What happened
The confirmation check required the standard 2D view, but not the segmentation's own image or grid. A radiologist could
select another image (e.g. the original instead of the MNI-preprocessed one) while the segmentation stayed open; the mask
was then drawn sheared (another row length) or cut off (fewer slices) on the other grid, and Confirm was accepted.

## 2. Fix
- The standard 2D view publishes, with the segmentation it draws, the image it draws it over: its storage id, its
  columns, rows and slices, and the mask's width, height and depth (`overlayImageOnScreen`); every other view publishes
  nothing.
- The shared check (`utils/confirmDrawCheck.ts`, both confirmations) refuses while the two grids differ, and when it
  cannot tell (nothing published, another segmentation's image, the mask not loaded, no image id), saying which grids.
- Both confirmation routes take `displayed_image_file_id` and refuse (409) unless it lies on the mask's grid
  (`services/displayed_image_check.py`): the image header (read without loading the voxels; the header reader is now one
  shared method, `SegmentationService.nifti_header_grid`) gives the mask's shape in the internal order, and another image
  than the segmentation's own has the same shape and voxel-to-scanner transform (RC-039 tolerance, 0.001). The image must
  be of the same study (patient and study of the storage path): on MNI-registered data every visit shares one grid, so
  the grid alone cannot tell the follow-up from the baseline. An image that cannot be read is refused; an image the user
  may not open is not read (404).

Requirement **REQ-SAFE-046**; risk control **RC-092** (HAZ-006, HAZ-008).

## 3. Verification
- Failing first: `frontend/src/components/LesionDashboard.prb030.test.tsx` (8), `frontend/src/ViewerApp.prb030.test.tsx`
  (4) and the PRB-030 cases of `backend/tests/unit/test_prb029_prb030_confirm_view_checks.py` (both routes); on
  `ca600c2` every refusal fails; the segmentation's own image and another series of the study on the same grid are
  positive controls (record `PRB-028-031_tests_on_base_2026-10-31.json`).
- Negative controls R1–R11 (server), C1–C8, D2, P1 (viewer): **21 of 21 detected** (whole run 62 of 62, throwaway worktree of `5cc88b9`, 2026-10-31, after the review of PR #74; first run 19 of 19 of the first round's set, `05cdf37`) — record `PRB-028-031_negative_controls_2026-10-31.json`.
- Fixture changes, no assertion removed: the confirmation tests state the image under the mask (the segmentation's own).

## 4. Limits and residual risk
- A segmentation of a non-NIfTI image (no readable header) cannot be confirmed (fail closed). DIS already needs NIfTI
  geometry; for the AI draft (in-browser FLAMeS on NIfTI) nothing changes in practice.
- The server relies on the client stating which image it drew (as the drawn-label digest; RMF-001, RC-071 residual
  risk).
- Deployment order: the viewer first, then the backend (an older viewer does not send the image and would be refused;
  since the review of PR #74, m7, it is told to reload).
- *Review m8 (recorded, not changed):* the "same study" rule assumes that a study is one visit and that file ids follow
  `patients/{patient}/studies/{study}/series/{series}/{file}`: series of different dates uploaded into ONE study are not
  told apart on an MNI grid, and a segmentation whose own file id does not follow the convention accepts only its own
  image (fail closed).

## 6. Independent review of PR #74 (`290e407`) — corrections (2026-10-31, DRAFT, N. G. Bonilla Vargas — approved 2026-10-31 (PR #74))
No blocker and no major issue; the claims hold. Tests written first (on `290e407` they fail except their positive controls: `records/risk_verification/PRB-028-031_review1_tests_on_290e407_2026-10-31.json`), then the corrections, then the negative controls (`PRB-028-031_negative_controls_2026-10-31.json`, re-run).
| # | Finding | Correction | Tests / controls |
|---|---|---|---|
| m9 | Two whole images were downloaded on every confirmation to read a header of a few hundred bytes | The header is read from a byte range (`download_file_range`: a ranged GCS read; 64 KB, grown only while a compressed header is not complete); a storage without ranges still works (whole download) | `test_prb028_031_review_findings.py` (m9, 3); R10 |

## 5. Owner decisions (PENDING)
Severity Minor; the same-study condition (an image of another visit is refused even on the same grid); raise a GitHub
Issue (SPR-001).
