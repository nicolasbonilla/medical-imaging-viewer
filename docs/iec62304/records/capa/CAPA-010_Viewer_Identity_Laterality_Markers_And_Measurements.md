# CAPA-010 — Viewer: Identity, Laterality Glyphs, 3D Lesion Markers, Measurements and a Hidden Caveat

**CAPA ID**: CAPA-010
**Date Opened**: 2026-10-17
**Source**: The viewer redesign branch `feat/viewer-v3` (not merged; `docs/research/viewer-v3/README.md` §3, `QMS_IMPACT.md`) reported five defects in the LIVE viewer and fixed them inside a large redesign. Each was re-checked here against `main` (`6209131`) with tests that fail on `main` and with the real application in a real browser, then fixed minimally on its own branch.
**Severity**: **CRITICAL**. Presentation hazards in the primary clinical workflow: wrong patient (HAZ-009), wrong side or wrong place (HAZ-006), wrong size (HAZ-014; HAZ-008 downstream through the lesion-size criterion). QP-002 §5.
**Owner**: *(to be assigned: Software Safety Officer / QMS Manager)*
**Status**: OPEN.
- Implemented on branch `fix/viewer-safety-capa010`: CA-10.1 to CA-10.5, PA-10.1 to PA-10.3. **Approved by N. G. Bonilla Vargas on 2026-10-23** (PR #52/#51/#53/#59/#49/#62/#63) and merged.
- Pending: CA-10.6 to CA-10.8, PA-10.4.
- Effectiveness is not verified (needs deployment and a clinician's check on real studies).

**Procedure**: QP-002 (`docs/qms/QP-002_CAPA_Procedure.md`) · SPR-001
**Related**: HAZ-006 · HAZ-009 · HAZ-014 · HAZ-008 · REQ-SAFE-016 (amended) · new REQ-SAFE-025/026/027 · RC-016 (extended) · RC-023 (extended) · new RC-037 · new RC-038 · CAPA-004 (CA-4.2, CA-4.3) · audit F-2.1 (PR #22)

---

## 1. Findings

All five were reproduced on `main`. Evidence is of two kinds:
- **Tests on `main`**: 27 new tests; on the `main` sources 25 fail, each for the stated reason, and 2 pass as they should (2D identity, which already worked, and a check of a niivue default). Record: §5.
- **Real application in a real browser**: `scripts/safety/capa010_viewer_layout_probe.mjs` runs the real `ViewerApp` (Vite dev server, real CSS) in headless Microsoft Edge and answers every backend request with a synthetic study (no patient data, no backend). Records: `records/risk_verification/CAPA-010_viewer_probe_main_2026-10-17.json` (before) and `CAPA-010_viewer_probe_fixed_2026-10-17.json` (after).

### Finding 1 — No patient identity in the 3D view and the multi-panel view (HAZ-009)

The safety overlay (identity, orientation, caveat; RC-016/RC-023) was rendered by the 2D viewer only. `ImageViewer3D` took no patient props; `MultiPanelViewer` neither. CAPA-004 recorded this as open (CA-4.2) on 2026-07-18.

**What a doctor saw**: a 3D brain, or two to four sequences side by side, with no name, no MRN and no "patient not identified" warning — a screenshot of those views carries no identity.

**Evidence on `main`**: probe — multi-panel 1x2 at 1366x768, 1600x900, 1920x1080: 0 identities, 0 annotations; 3D volume and 3D multiplanar: 0 identities. Tests: `rc016 3D volume mode …`, `rc016 3D multiplanar mode …`, `rc016 every panel …`, `rc016 ViewerApp multi / 3d-volume / 3d-mpr …` all fail with "Unable to find … viewport-patient-identity / viewport-safety-overlay".

### Finding 2 — 3D crosshair and bounding box of the selected lesion drawn transposed (HAZ-006)

The lesion analysis runs on the internal (k, a0, a1) segmentation mask (RC-031) and reports the centroid and box as (z, y, x). The NIfTI voxel is therefore (i, j, k) = (y, x, z). The 2D canvas uses that rule (fixed under audit F-2.1, PR #22). The 3D view used (x, y, z) as (i, j, k) for both the crosshair (`ImageViewer3D` effect 7) and the box (`boundingBoxMesh.ts`).

**What a doctor saw**: after clicking a lesion in the lesion table, the 3D crosshair and the yellow 3D box pointed at voxel (j, i) instead of (i, j): another place in the slice. On the usual storage (i = left-right) a lesion at i = 150, j = 60 of a 182-wide image is marked at i = 60, on the other side of the midline. The 2D view showed the correct place, so the two views disagreed. It is only right by chance when i = j.

**Evidence on `main`**: on a LAS-like affine (1 / 1.2 / 3 mm, translated) the crosshair landed at x = 50 mm instead of 80 mm; the box spanned x ≈ 45.7 mm instead of ≥ 77.7 mm (`rc037 …` tests).

### Finding 3 — The ruler measured twice the length at zoom 2; the angle ignored the pixel size (HAZ-014)

The default 2D render mode ("Standard") draws the slice with `translate(centre + pan) · scale(zoom) · translate(−centre)`. The measurement overlay converted screen to image coordinates with the base scale only, ignoring zoom and pan. The angle was computed in pixel units, ignoring the row/column spacing.

**What a doctor saw** (values displayed by the real component on `main`):
- a 10 mm segment measured at zoom ×2 read **"20.0 mm"**; the same 5 mm segment read 5.0 / 10.0 / 20.0 mm at zoom 1 / 2 / 4;
- an elliptical ROI of 157.1 mm² at zoom ×2 read **"628.3 mm²"** (×4);
- after zooming, a drawn ruler stayed where it was on the screen instead of following the anatomy;
- on 2 mm × 1 mm pixels, an angle of 63.4° read **"45.0°"**.

A doctor zooms in to measure small lesions, so the error is largest exactly there: a 1.5–2.9 mm focus measured at ×2 reads ≥ 3 mm, the minimum size of an MS lesion (HAZ-008 downstream).

### Finding 4 — The "Laterality not labelled" caveat was rendered off-screen (HAZ-006)

In 2D the page stacked the toolbar above a viewport of `height: 100%` inside a block column. The viewport was taller than the space left by the toolbar (≈ 52 px) and the frame's `overflow: hidden` cut its bottom: the standing caveat sits there.

**What a doctor saw**: no laterality caveat at all in 2D, at any window size, since it was added by CAPA-004 (2026-07-18); and the bottom 5–20 px of the image cut off.

**Evidence on `main`**: probe — caveat visible fraction **0.00** at 1366x768, 1600x900 and 1920x1080; image hidden below the frame by 20 / 14 / 5 px. Test `rc023 ViewerApp: every view shows its laterality caveat …` (real-browser layout of the real rendered page): 2D 0.00, multi-panel and 3D: no caveat.

CAPA-004's tests rendered the overlay in jsdom, which has no layout engine: they could not observe that the caveat was outside the visible page.

### Finding 5 — The 3D view drew laterality letters, contrary to RC-023 (HAZ-006)

RC-023 records that the viewer "deliberately renders NO L/R edge labels" until the axis-to-screen mapping is verified (CAPA-004 CA-4.3). That held in 2D only:
- the 3D render enabled niivue's orientation cube (`isOrientCube`), whose faces carry L/R/A/P/S/I letters;
- the three slice panels of the 3D multiplanar mode drew niivue's slice letters — niivue's default `isOrientationTextVisible` is `true` and the viewer never switched it off: "A" at the top and "L" at the left of the axial panel.

**Evidence on `main`**: probe screenshot of the 3D view: orientation cube with "S" and "P" visible. Tests: the options of every 3D niivue instance, fed to the REAL niivue drawing routines, draw the cube and the slice letters (`rc023 3D volume mode …`, `rc023 3D multiplanar mode …`). The slice letters were shown by the real niivue code path, not observed on a screenshot (the synthetic volume of the probe does not fill the slice panels).

### Mitigating factors

- The device is not CE-marked and not in clinical use.
- 2D identity and orientation (CAPA-004) were already correct; 2D lesion markers were correct since PR #22.

## 2. Corrective Actions

| ID | Action | Status |
|----|--------|--------|
| **CA-10.1** | `ImageViewer3D` and every `MultiPanelViewer` cell render `ViewportSafetyOverlay` first and unconditionally; `ViewerApp` passes the identity it already loads. Each panel reports the orientation of ITS OWN image (`PanelState.orientation`, from the server metadata; cleared when a panel is reassigned, kept on slice changes). The sequence badge of a panel moved to bottom-left so the identity does not cover it | **DONE** — approved 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
| **CA-10.2** | One mapping for lesion markers: `lesionVoxelToNifti(z, y, x) = (y, x, z)` (`utils/boundingBoxMesh.ts`), used by the 3D crosshair and the 3D box | **DONE** — approved 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
| **CA-10.3** | Measurement overlay maps through the canvas transform (`scale = s0 · zoom`, `origin = centre · (1 − zoom) + pan`); the angle uses millimetres per axis | **DONE** — approved 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
| **CA-10.4** | The viewer's centre column is a flex column; the viewport takes the height left by the toolbar (`min-h-0 flex-1`) | **DONE** — approved 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
| **CA-10.5** | Every 3D niivue instance: `isOrientCube: false`, `isOrientationTextVisible: false` | **DONE** — approved 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
| **CA-10.6** | The angle tool cannot place a three-point angle with normal clicks: every mouse-down restarts it, and in a single drag the vertex is the first mouse-move sample. Found here, not fixed (needs an interaction decision) | **PENDING** |
| **CA-10.7** | When the image header has no pixel spacing, the 2D measurement tools still label values in "mm" assuming 1 mm (contrary to RC-024's principle). Found here, not fixed | **PENDING** |
| **CA-10.8** | Cosmetic, from the fix: in 3D volume mode the caveat overlaps the middle of niivue's colour bar; in 3D multiplanar mode the identity block covers the "3D" panel label | **PENDING** (cosmetic) |

## 3. Preventive Actions

| ID | Action | Status |
|----|--------|--------|
| **PA-10.1** | Page-level tests: `ViewerApp.capa010.test.tsx` renders the REAL viewer page (real viewers, mocked backend) in 2D, multi-panel, 3D volume and 3D multiplanar, and checks the loaded identity on every view. The same rendered page, with the app's real Tailwind CSS, is measured in a real headless browser (Edge or Chrome) at 1366x768, 1600x900, 1920x1080: every caveat must be fully visible. In CI a missing browser fails the test instead of skipping it | **DONE** — approved 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
| **PA-10.2** | Third-party defaults cannot silently re-enable glyphs: the tests feed each 3D instance's effective options to the REAL niivue drawing routines; one test pins that niivue's default WOULD draw letters | **DONE** — approved 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
| **PA-10.3** | Negative controls: `scripts/safety/capa010_negative_controls.py`, one mutation at a time, every anchor asserted unique | **DONE** — approved 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) |
| **PA-10.4** | Re-verify the other presentation controls at page level in a real browser (e.g. RC-008 badge, RC-014 overlay legends): a component test in jsdom cannot see clipping or overlap. Owner to prioritise | **PENDING** |

## 4. Root Cause (preliminary — to be confirmed by the Safety Officer)

1. **Presentation controls verified where the failure cannot be seen.** CAPA-004's tests rendered the overlay alone in jsdom (no layout) and checked the 2D wiring by reading source text. They passed while the caveat was off-screen and while the 3D view drew letters through a library default. Fourth occurrence of "verification that could not observe the failure" (CAPA-006, CAPA-007, CAPA-009).
2. **A safety annotation added per view, with the other views left "open".** CA-4.2 stayed open for three months; nothing failed while 3D and multi-panel had no identity.
3. **Coordinate conventions re-implemented per view.** The (z, y, x) → (i, j, k) rule was fixed in 2D (PR #22) and not in 3D; the canvas transform was implemented in three places (canvas, cursor read-out, paint overlay) and missed in the fourth (measurements). There was no shared, tested function.

## 5. Verification Evidence (executed 2026-10-17)

- **Tests on the `main` sources** (the six fixed files restored from `main` at `6209131`, final tests kept): 27 tests, **25 failed for the stated reason, 2 passed** as expected (2D identity; the niivue-default check). Record with every failure message: `records/risk_verification/CAPA-010_tests_on_main_2026-10-17.json`.
- **After the fix**: the 27 pass, plus 4 added on 2026-10-18 after the pre-merge review of PR #52 (non-square image and canvas, anisotropic voxels — not run against `main`). Full frontend suite: **19 files, 147 tests passed** (`npx vitest run --pool=threads`; before: 15 files, 116 tests). `npx tsc --noEmit`: clean. `npm run build`: OK, and the test helpers are not in the production bundle. Backend `tests/unit/test_risk_control_manifest.py` (the manifest changed): 215 passed.
- **Real application, before / after** (headless Edge, synthetic study): caveat visible fraction 0.00 → 1.00 in 2D at three sizes; image cut 20/14/5 px → 0; identities in multi-panel 0 → 2, in 3D 0 → 1; orientation cube gone from the 3D view. On `main` one of the eight page loads timed out on a first pass (1920x1080, a load timing issue of the probe); the recorded run is the complete second pass.
- **Negative controls**: `records/risk_verification/CAPA-010_negative_controls_2026-10-17.json` — **26 mutations, 25 detected, 1 equivalent by design (stated)**; restored: 47 passed, 0 failed, 0 skipped (re-executed 2026-10-18). Details: §5.1.

### 5.1 Negative controls

Executed 2026-10-17 by `scripts/safety/capa010_negative_controls.py` against the final code, one mutation at a time, every anchor asserted to occur once; bound tests: the four CAPA-010 files and `ViewportSafetyOverlay.test.tsx` (43 tests). **Re-executed 2026-10-18** (47 tests) after the pre-merge review of PR #52 found that a vertical zoom centre computed from the canvas WIDTH was not detected — every measurement test used a square image on a square canvas. Checked by hand first: with that mutation the previous 6 `rc038` tests pass and the new redraw test fails. Counts below are from the 2026-10-18 run; R1–R4 counts rose because the new tests also catch them. "Failed" = tests that turned red.

| Mutation | Re-introduces | Failed |
|---|---|---|
| I1 3D overlay removed | the defect as found (no identity, orientation or caveat in 3D) | 7 |
| I2 3D identity not passed by the page | page loads the patient, 3D viewer never gets it | 2 |
| I3 panel overlay removed | the defect as found (multi-panel) | 7 |
| I4 multi-panel identity not passed by the page | — | 1 |
| I5 identity dropped inside the multi-panel viewer | a dead prop | 2 |
| O1 panel orientation not stored | panels never learn their own orientation | 2 |
| O2 orientation lost on slice change | — | 1 |
| O3 stale orientation on reassignment | previous image's orientation shown | 1 |
| O4 stale orientation on auto-assignment | same, other path (detected after the test was corrected: a first run looked at the emptied panel only) | 1 |
| G1 orientation cube restored | the defect as found | 2 |
| G2 niivue default slice letters | the defect as found (L/A letters) | 2 |
| L1 page layout as on `main` | the defect as found (caveat off-screen) | 1 |
| L2 viewport `h-full`, column kept flex | **equivalent by design — not detected, not a defect**: in a flex column an overflow-hidden child of height 100 % shrinks to the space left (flex-shrink 1, automatic minimum height 0 for a scroll container); measured in the real browser | 0 |
| L3 column back to a block, viewport kept flex-1 | the defect | 1 |
| M1 crosshair read as (x, y, z) | the defect as found | 2 |
| M2 box read as (x, y, z) | the defect as found | 1 |
| M3 shared mapping wrong | both markers | 3 |
| R1 zoom and pan ignored | the defect as found | 8 |
| R2 zoom ignored | — | 8 |
| R3 pan ignored | rulers detached on pan | 2 |
| R4 angle in pixel units | the defect as found | 2 |
| R5 vertical zoom centre from the canvas width | found by the PR #52 review; undetected by square fixtures | 1 |
| R6 horizontal zoom centre from the canvas height | — | 1 |
| R7 vertical scale from the horizontal axis | — | 4 |
| R8 row/column spacing swapped in the angle | — | 2 |
| R9 row/column spacing swapped in lengths | — | 2 |

Failing test names per mutation and the SHA-256 of every mutated source and test file are in the record.

**Not verified**: behaviour after deployment; a clinician's visual check on 3–5 real studies (2D, multi-panel, 3D, a lesion selected, a ruler at zoom ×2); the backend was not touched (no backend test run).

## 6. Regulatory Assessment

- The device is not CE-marked and not in clinical use; there is no vigilance reporting obligation.
- On a marketed device, Findings 1, 2 and 3 would be assessed as potential serious-incident precursors (wrong patient, wrong side, wrong size).

---

**Prepared by**: internal audit, 2026-10-17.
**Requires**: human approval before merge and deployment. **Approved by N. G. Bonilla Vargas on 2026-10-23** (PR #52/#51/#53/#59/#49/#62/#63, written authorisation of the owner).

---

## Addendum 2026-10-28 — proposed CA-10.9 (PRB-004, PRB-006, PRB-010) — DRAFT, PENDING owner approval

Three problems found around the browser capture session of the release candidate share this CAPA's root cause ("coordinate
conventions and display settings re-implemented per view"), so they are proposed here as one more corrective action rather
than a new CAPA (owner decision; a new CAPA is the alternative):

| Action | Description | Status |
|---|---|---|
| **CA-10.9** | (a) PRB-004: the W/L GPU 2D view placed voxels by the scanner affine — rotated 90° (and possibly mirrored) against the Standard view where the mask is edited — and showed a position between two slices; a mask of another grid or voxel order was drawn by its own affine. Fixed: the GPU view lays the image and the mask out as the Standard view, voxel-centre slice, a mask drawn only on the image's own grid and voxel order, otherwise not drawn and stated (RC-073, REQ-SAFE-041). (b) PRB-006: every niivue mask overlay used the MRI display window copied into the mask file (red fog, lesions nearly invisible); fixed range for every overlay and a stored range of the mask's own (RC-074, REQ-SAFE-042). (c) PRB-010: the region colours on the image (2D, 3D, zone legends, stored labels) were red / green / blue / gold while the lesion legend is Okabe-Ito; one shared mapping (RC-076, REQ-SAFE-043) | **Implemented on branch `fix/viewer-display-orientation-prb004`** (draft PR) — PENDING owner approval and code review |

Records: `records/problem_reports/PRB-004_GPU_View_Rotated_Against_Standard_View.md`,
`records/problem_reports/PRB-006_Lesion_Mask_Coloured_With_MRI_Display_Window.md`; tests on `main`, negative controls and the
real-browser probe in `records/risk_verification/PRB-004_*_2026-10-28.json`. The prevention side is the same as PA-10.1 (verify a
presentation control where the failure can be seen): this time a real-browser probe with real WebGL
(`scripts/safety/prb004_viewer_display_probe.mjs`) measures the rendered pixels. Still open: RC-013 — a canonical, verified 2D
orientation for every view (PRB-004 D-1).

**Addendum update 2026-10-28 (independent review of PR #71) — DRAFT, PENDING owner approval.** The review found the same root
cause twice more inside the 3D view: masks composited by their own affine with no voxel-order or position check, and "go to
slice" written as a proportion (index / (depth − 1)) on the axial axis while the selected-lesion path of the same component
already went voxel → mm → niivue (RC-037) — a twin of PRB-004's slider defect. Both fixed under CA-10.9 (PRB-004 §9). The film
capture added one more presentation conflict: niivue's 3D colour bar under the standing laterality caveat (RC-023); colour bar
off. Prevention (PA-10.1) applied again: the GPU notice placement is measured in a real browser
(`NiivueViewer2D.prb004.layout.test.tsx`), which caught a defect in the first review fix.