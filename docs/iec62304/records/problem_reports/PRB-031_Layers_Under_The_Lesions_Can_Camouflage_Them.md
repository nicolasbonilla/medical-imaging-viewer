# PRB-031 — The Zone Map and the Longitudinal Overlay Could Camouflage Lesions at Confirmation (L2)

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: next free after PRB-030. GitHub Issue: not
raised — owner action.*

**Problem ID**: PRB-031
**Reporter**: last check of PR #69 (item L2, `records/releases/RELEASE-2026-10-25_integration_notes.md` §7); accepted by
the owner as "fix in the next version"; fixed by the AI coding agent on branch `fix/next-safety-round`
**Date**: 2026-10-31
**Version**: `main` @ `ca600c2` (pre-existing)
**Severity**: **Minor** (proposed; visually obvious — the whole brain is painted — but a lesion inside its own zone can
be invisible when the radiologist confirms — HAZ-005, HAZ-008; the red / green longitudinal colours, HAZ-007).
**PENDING owner approval.**
**Status**: OPEN — DRAFT. Fixed on branch `fix/next-safety-round` (draft PR), not merged, not deployed.

## 1. What happened
The MAGNIMS zone map is drawn under the lesions in the same region colours, at a user opacity of up to 100 % that is
kept across sessions (not filtered like the lesion opacity): a periventricular lesion inside the periventricular zone
cannot be seen. The longitudinal overlay (fixed 55 %), the FLAIR subtraction heat map (up to 60 %) and the conformal
tiers (78 %) are drawn under the lesions the same way. Confirm was accepted with any of them on. The 2D longitudinal
overlay also drew "persistent" green against "new" red (red-green colour blindness, the defect PRB-010 removed from the
region colours).

## 2. Fix
- **Threshold (proposed, owner decision): 30 %** (`MAX_UNDERLAY_OPACITY`). Rationale: a layer of opacity a drawn over the
  image leaves (1 − a) of the image's own contrast and of the lesion colour's contrast inside an area of the same colour
  (alpha compositing); at 30 % at least 70 % remains. 30 % is the zone map's default, so the default never refuses; the
  companion rule, the lesion opacity minimum of 25 %, is unchanged.
- The shared check (`utils/confirmDrawCheck.ts`, both confirmations) refuses while a layer under the lesions is drawn
  above 30 %: the zone map above it, the longitudinal overlay, the subtraction heat map or the conformal tiers at all
  (their fixed opacities — now constants read by both the drawing and the check — are above it), naming the layer, its
  opacity and the limit.
- A stored zone-map opacity above 30 % (or not a number) is not restored in a new session; the default (30 %) is used.
  Within a session the slider still goes to 100 % for looking at the zones.
- The 2D longitudinal overlay uses the shared Okabe-Ito palette (`LONGITUDINAL_OVERLAY_COLORS` in `regionColors.ts`):
  persistent yellow #F0E442, resolved blue #0072B2, new reddish purple #CC79A7 (since the review of PR #74, m6; first
  vermillion #D55E00, the deep-white-matter colour); as drawn (55 % over mid and bright grey) every pair stays more than
  ΔE76 12.9 apart for normal, deutan, protan and tritan vision (worst pair; 12.2 for the old colours, more than 9
  required), opaque more than 22 for the colour-blind simulations, and "new" more than 15 from every region and lesion
  label colour. The legend of the comparison result takes the same colours (review m6). The 3D view (each visit in one
  colour, blue / red) is unchanged.

Requirement **REQ-SAFE-047**; risk control **RC-093** (HAZ-005, HAZ-008, HAZ-007).

## 3. Verification
- Failing first: `frontend/src/components/LesionDashboard.prb031.test.tsx` (9),
  `frontend/src/store/useSegmentationStore.prb031.test.ts` (3), `frontend/src/components/SegmentationCanvasLocal.prb031.test.tsx`
  (2), and the PRB-031 case of `AiDraftBanner.prb029.test.tsx`; on `ca600c2` every refusal fails; the zone map at 30 % or
  hidden and a stored opacity at or below 30 % are positive controls (record `PRB-028-031_tests_on_base_2026-10-31.json`).
- Negative controls O1–O8, L1–L5 and D1: **14 of 14 detected** (whole run 62 of 62, throwaway worktree of `5cc88b9`, 2026-10-31, after the review of PR #74; first run 11 of 11 of the first round's set, `05cdf37`)
  — record `PRB-028-031_negative_controls_2026-10-31.json`.

## 4. Limits
- ~~Vermillion is also the deep-white-matter region colour~~ — corrected (review m6): "new" is reddish purple, used by
  no region and no lesion label.
- *Corrected (review m6):* this report first said there was no legend. There is one, in the comparison result
  (`LongitudinalResultPanel`), and it hard-coded the former blue / green / red: after the first round of this PR changed
  the overlay colours, the legend no longer matched the image. It now takes its colours from the constant the canvas
  draws with (`LongitudinalOverlayLegend`), with CAPA-013's neutral words.
- Zone colouring (switched on with the zone map) is refused at confirmation unless it draws exactly the stored region
  labels (review m1, PRB-029 §6).

## 5. Owner decisions (PENDING)
1. Severity Minor.
2. The 30 % threshold (§2) and that the longitudinal overlay, the subtraction heat map and the conformal tiers refuse
   Confirm whenever shown (rather than being drawn lighter).
3. The longitudinal colours (yellow / blue / reddish purple).

## 6. Independent review of PR #74 (`290e407`) — corrections (2026-10-31, DRAFT, PENDING owner approval)
No blocker and no major issue; the claims hold. Tests written first (on `290e407` they fail except their positive controls: `records/risk_verification/PRB-028-031_review1_tests_on_290e407_2026-10-31.json`), then the corrections, then the negative controls (`PRB-028-031_negative_controls_2026-10-31.json`, re-run).
| # | Finding | Correction | Tests / controls |
|---|---|---|---|
| m6 | Longitudinal "new" = the deep-white-matter vermillion; "no 2D legend" (in fact the existing legend of the comparison result still showed the former blue / green / red after this PR's first round) | "new" reddish purple #CC79A7 (checked against persistent, resolved and every region and lesion label colour); the result panel's legend is one component coloured from the canvas's constant, neutral words kept | `SegmentationCanvasLocal.prb031.test.tsx` (m6), `LongitudinalOverlayLegend.prb031.test.tsx` (2), `LongitudinalCompare.capa013.test.tsx` (legend kept); L3, L4, L5 |
| m1 | Zone colouring not seen by the check | See PRB-029 §6 | Z1, Z2 |
4. Raise a GitHub Issue (SPR-001).
