# PRB-010 — Region Colours on the Image Differed From the Legend, Periventricular Red Against Juxtacortical Green

*Software problem report per SPR-001 §1 (layout of PRB-001). No GitHub Issue raised — owner action.*

**Problem ID**: PRB-010 (GitHub Issue: not raised — owner action)
**Reporter**: coordinator of the release-candidate capture session (region overlay colours of the viewer against the
lesion panel's legend); reproduced on `main` and record drafted by the AI coding agent
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7`. The overlays' red / green / blue / gold since `67fa336` (2026-02-28); the lesion legend
switched to Okabe-Ito on 2026-08-18 (`79bcfee`, "red/green indistinguishable … a clinical-safety defect") without the
overlays. The release branch does not change these colours.
**Severity**: **Major — safety-related** (proposed; HAZ-005: the region a reader sees on the image is the region the device
counts for DIS — a reader who cannot tell periventricular from juxtacortical on the image, or who reads the image with the
legend's colours, can misjudge the regions). **PENDING owner approval.**
**Status**: OPEN — DRAFT. Fix implemented on branch `fix/viewer-display-orientation-prb004` (draft PR, with PRB-004..009).

**Description**: After region classification, the lesions are coloured by MAGNIMS region. The lesion panel's legend
(`LesionDashboard`) uses the Okabe-Ito colour-blind-safe palette: periventricular **#E69F00** (orange), juxtacortical
**#56B4E9** (sky blue), infratentorial **#009E73** (bluish green), deep white matter **#CC79A7** (reddish purple). The image
itself was coloured otherwise: the 2D overlay of a classified segmentation, the 2D zone-colouring and zone-map layers, the 3D
zone map and both legends of the zone-map panel drew periventricular **red**, juxtacortical **green**, infratentorial
**blue**, deep white matter **gold/yellow**. The picture and the legend disagreed (orange means periventricular in the legend,
nothing on the image), and red against green — the two most common lesion zones — cannot be told apart with red-green colour
blindness (about 8 % of men): simulated deuteranopia puts them ΔE76 10 apart (protanopia: juxtacortical against deep white
matter ΔE 13).

**Steps to Reproduce**: open a segmentation, run "Auto-Classify Regions" (or open one classified before), look at the 2D image
and the region legend of the lesion panel; or switch on the zone map / zone colouring, or open the 3D view with the zone map.

**Expected Behavior**: one mapping region → colour for every legend and every overlay (2D and 3D); no region pair red against
green; every pair distinguishable for deutan and protan readers.

**Actual Behavior** (`main` @ `70cc5c7`):
- `backend/app/api/routes/segmentation_regions.py:432-435` (classify-regions) and `:695-698` (generate-zone-map) store the region
  labels with #FF0000 / #00CC00 / #0066FF / #FFD700; the 2D overlay draws the stored label colours
  (`frontend/src/components/SegmentationCanvasLocal.tsx`, `storeLabels`).
- `frontend/src/types/segmentation.ts:345-354` (MAGNIMS label preset): the same four colours.
- `frontend/src/components/SegmentationCanvasLocal.tsx:99-104` (zone-coloured lesions) and `:508-513` (zone-map layer):
  hard-coded red / green / blue / yellow.
- `frontend/src/components/ImageViewer3D.tsx:95-114` (3D zone colormap): the same.
- `frontend/src/components/MAGNIMSZoneMapPanel.tsx:29-41` (zone statistics legend) and `:221-224` (zone-colouring legend):
  `bg-red-500` / `bg-green-500` / `bg-blue-500` / `bg-yellow-500`.
- `frontend/src/components/LesionDashboard.tsx:66-71`: the only Okabe-Ito mapping (the legend).

**Safety Impact Assessment**:
- [x] Could contribute to a hazardous situation — HAZ-005 (region of a lesion misread on the image; the device's DIS count
  rests on the regions). Cause recorded in RMF §3.8 (e).
- [ ] Affects a Class C software item of the CLAUDE.md list — no (`ms_region_classifier.py` is not changed; only the colours
  stored with the labels by the route that calls it).
- [ ] Requires regulatory notification — no.

## 1. Root Cause

The region → colour mapping was written in seven places (two backend label lists, the label preset, two 2D canvas layers, the
3D colormap, three legends). The 2026-08-18 colour-blind fix changed one of them (the lesion legend) and nothing tied the others
to it; no test looked at the colours drawn on the image.

## 2. Resolution — implemented on branch, PENDING owner approval

- `frontend/src/utils/regionColors.ts` (new): the ONE mapping (`MAGNIMS_REGION_PALETTE`, by region name and label value),
  legend classes, canvas RGBA (`regionZoneRgba`) and `withRegionColors` (a label named after a region shows the region's colour,
  whatever colour was stored — classified segmentations stored before the fix carry red / green / blue / gold).
- Read by: the lesion legend (`LesionDashboard.tsx`), both legends of `MAGNIMSZoneMapPanel.tsx`, the MAGNIMS label preset
  (`types/segmentation.ts`), both 2D layers of `SegmentationCanvasLocal.tsx`, the 3D zone colormap (`ImageViewer3D.tsx`), and the
  segmentation store (`setActiveSegmentation` applies `withRegionColors`, so the overlay and the label list agree).
- `backend/app/api/routes/segmentation_regions.py`: `MAGNIMS_REGION_LABEL_COLORS`, the same four colours, for both label lists
  (also what a DICOM-SEG export of a classified segmentation carries).
- Requirement: new **REQ-SAFE-043**; risk control: new **RC-076** (HAZ-005).

## 3. Verification

- Failing-first tests (named `rc076`): `frontend/src/components/SegmentationCanvasLocal.prb010.test.tsx` — what the overlay
  writes to the canvas (a recording 2D context; jsdom has none) for a segmentation whose stored labels are red / green / blue /
  gold, the zone-coloured lesions, the zone-map layer, the colours niivue receives for the 3D zone map, and the dots of both
  zone-map legends; that no drawn region pair is red against green and every pair stays more than ΔE76 15 apart under simulated
  deuteranopia and protanopia (Machado 2009). **7 of 7 fail on `main`** (red / green drawn; PV–JC ΔE 10 for deutan). The
  zone-colouring legend test was added during the work (it also fails on the first fix commit `68b49bb`).
  `frontend/src/utils/regionColors.test.ts` (the mapping, the legend classes, the preset, one source for the legends and layers):
  fails to load on `main` (module absent). `backend/tests/unit/test_prb010_region_label_colours.py`: 2 of 2 fail on `main`.
  Record `records/risk_verification/PRB-004_tests_on_base_2026-10-28.json`.
- Negative controls P1–P11 (region drawn in its stored colour, each layer / legend with its own colours, red and green in the
  mapping, preset or backend off the mapping, region names matched case-sensitively, a legend keeping its own copy):
  **11 of 11 detected** — `records/risk_verification/PRB-004_negative_controls_2026-10-28.json`.
- The real-browser probe of PRB-004..009 does not cover the region colours (it ran before this fix and its mask carries no
  region labels).
- Not done: a check with colour-blind readers; the palette is the published Okabe-Ito set, and the simulation is a model.

## 4. Owner decisions

- Severity Major, safety-related (proposed).
- Segmentations classified before the fix keep red / green / blue / gold in their stored labels; the viewer shows the mapping
  anyway. Re-save (or a migration) to change the stored colours — owner decision.

## 5. Closure — not applicable yet

## R. Independent review of PR #71 (2026-10-28) — PENDING owner approval

- **m1 — the colour-blind claim was measured on the opaque colours, the image shows them translucent.** A region is drawn at
  label opacity 0.6 × lesion opacity 0.6 (the default) = 36 %, over grey tissue. Measured that way (Machado 2009 severity 1,
  CIELAB ΔE76, 8-bit source-over on grey 128 and 220), the first mapping kept **infratentorial (#009E73) and deep white matter
  (#CC79A7) only ΔE 5.3 apart for a deutan reader** — less than the old red / green / blue / gold (worst 7.9, protan); the
  REQ-SAFE-043 / RC-076 claim (> 15) held only for the opaque legend dots.
  Resolution: **deep white matter vermillion #D55E00** (Okabe-Ito). As drawn at the default opacity on grey 128 / 220 the worst
  pair is now ΔE 9.8 deutan, 12.7 protan, 9.1 tritan, 14.3 normal vision; opaque, every pair above 15 for deutan, protan and
  tritan. The legends follow (one mapping). Trade-off: for normal vision orange (PV) and vermillion (DWM) are closer than orange
  and purple were (ΔE 14.3 as drawn instead of 21.8) — still clearly distinct; owner decision to confirm. The test now checks
  the colours as written to the canvas at the default opacity, composited on grey 128 and 220 (> 9 for normal, deutan, protan
  and tritan vision), plus the opaque colours (> 15); fails on `39f9d44` (`records/risk_verification/PRB-004_review_tests_on_39f9d44_2026-10-28.json`). Negative control V20.
  Not done: a check with colour-blind readers.
- **m6 — the GPU and 3D views drew a region-classified mask all red.** Both now draw every label value in its label's colour
  (a label named after a region in the region's colour from the one mapping), a value missing from the label table in cyan,
  background transparent (`utils/maskLabelColormap.ts`; an ordinary niivue colormap with one wide band per value, since niivue's
  label colormap is not coloured in 3D volume rendering). Tests `NiivueViewer2D.prb004.review.test.tsx` and
  `ImageViewer3D.prb004.review.test.tsx` (`rc076 m6`); fail on `39f9d44`. Negative controls V21–V25.
- **Known issue, not fixed here: the longitudinal layer of the 2D view draws voxels present at both visits green and voxels
  present only at the later visit (new) red** (visit-1-only blue; `SegmentationCanvasLocal.tsx`, longitudinal layer) — the same
  red / green pair for a red-green colour-blind reader; and the result panel's status colours (`LongitudinalResultPanel.tsx`:
  new blue, resolved green, enlarged red) use another code than the image. Left for the longitudinal work (CAPA-013 and PR #69
  touch that view); proposed: one colour-blind-safe code for the layer and the panel, plus a non-colour cue.
