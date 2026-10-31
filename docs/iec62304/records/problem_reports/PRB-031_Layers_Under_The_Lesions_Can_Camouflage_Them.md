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
  persistent yellow #F0E442, resolved blue #0072B2, new vermillion #D55E00; as drawn (55 % over mid and bright grey)
  every pair stays more than ΔE76 19 apart for normal, deutan, protan and tritan vision (worst pair), against 12.2 for
  the old colours. The 3D view (each visit in one colour, blue / red) is unchanged.

Requirement **REQ-SAFE-047**; risk control **RC-093** (HAZ-005, HAZ-008, HAZ-007).

## 3. Verification
- Failing first: `frontend/src/components/LesionDashboard.prb031.test.tsx` (9),
  `frontend/src/store/useSegmentationStore.prb031.test.ts` (9), `frontend/src/components/SegmentationCanvasLocal.prb031.test.tsx`
  (2), and the PRB-031 case of `AiDraftBanner.prb029.test.tsx`; on `ca600c2` every refusal fails; the zone map at 30 % or
  hidden and a stored opacity at or below 30 % are positive controls (record `PRB-028-031_tests_on_base_2026-10-31.json`).
- Negative controls O1–O8, L1, L2: record `PRB-028-031_negative_controls_2026-10-31.json`.

## 4. Limits
- Vermillion is also the deep-white-matter region colour; the longitudinal overlay is drawn under the lesions and is
  refused at confirmation, so the two are not used together for a decision.
- There is still no legend for the 2D longitudinal colours (pre-existing).

## 5. Owner decisions (PENDING)
1. Severity Minor.
2. The 30 % threshold (§2) and that the longitudinal overlay, the subtraction heat map and the conformal tiers refuse
   Confirm whenever shown (rather than being drawn lighter).
3. The longitudinal colours (yellow / blue / vermillion).
4. Raise a GitHub Issue (SPR-001).
