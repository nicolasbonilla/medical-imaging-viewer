# PRB-028 — Regions From the Geometric Fallback Could Feed DIS Without a Lesion-by-Lesion Review

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: next free after PRB-027 on every branch
(checked 2026-10-31). GitHub Issue: not raised — owner action.*

**Problem ID**: PRB-028
**Reporter**: film capture of 2026-10-28 (MSLesSeg P51); accepted by the owner as "fix in the next version"; analysed and
fixed by the AI coding agent on branch `fix/next-safety-round`
**Date**: 2026-10-31
**Version**: `main` @ `ca600c2` (present since the region classification has a geometric fallback)
**Severity**: **Major** (proposed; a DIS result can rest on region labels that are wrong for most lesions — HAZ-005,
HAZ-008). **PENDING owner approval.**
**Status**: OPEN — DRAFT. Fixed on branch `fix/next-safety-round` (draft PR), not merged, not deployed.

## 1. What happened
When the MNI atlas cannot be used (the image is not on an MNI grid), `classify-regions` falls back to the geometric
heuristics of `ms_region_classifier.py` (Class C; coordinate rules, not anatomical landmarks). Evidence
(`mstool-film/assets/app-captures-p51/data/`): on the same 45 lesions of MSLesSeg P51 (FLAMeS 5-fold, after the filmed
edits) the geometric fallback labelled **42 of 45 periventricular**, the MSMask atlas 10 periventricular, 10
juxtacortical, 3 infratentorial, 22 deep white matter; the two agreed on **11 of 45** (`lesions_world_mm_p51.json`,
`agreement_count`). Both are app outputs, not expert labels. The classification card only said "accuracy has not been
measured; verify every region", and one DIS confirmation covered every region at once: nothing showed that each region
had been looked at.

## 2. Fix (route and viewer level; the Class C classifier's algorithm is not changed — as for the < 3 mm³ removals)
- `dis_review_gate.regions_state` lists every lesion whose region comes from the geometric fallback and that nobody
  relabelled (`regions.geometric_regions`, named as the lesion table names them, with their count and a digest of
  first voxel and region). A lesion the radiologist relabelled is a region correction, listed and acknowledged as
  before (the existing mechanism, second review of PR #68, N1).
- The DIS card lists those lesions, each with its region, a button that opens its slice and a tick; Confirm stays off
  until every listed lesion is ticked; the dialog names the per-lesion check.
- `POST /segmentation/{id}/review/confirm` refuses (409) unless the request carries the digest of the list
  (`geometric_regions_reviewed_sha256`); it always refuses when there are more such lesions than the list can hold
  (100): they cannot be shown to have been checked one by one. The confirmation records the digest, the count and
  the list.
- `review_state`: a confirmation that does not cover the geometric regions (recorded before this rule, or by another
  client) does not make DIS evaluable; the reason is `geometric_regions_not_reviewed`, and the card offers the
  confirmation again with the list.
- An atlas, parcellation or LST-AI classification needs no tick (unchanged).

Requirement **REQ-SAFE-044**; risk control **RC-090** (HAZ-005, HAZ-008).

## 3. Verification
- Failing first: `backend/tests/unit/test_prb028_geometric_fallback_review.py` (10) and
  `frontend/src/components/LesionDashboard.prb028.test.tsx` (7) — on `ca600c2` all fail except the atlas positive
  control (record `records/risk_verification/PRB-028-031_tests_on_base_2026-10-31.json`).
- Negative controls G1–G8 (server) and U1–U5 (viewer): `scripts/safety/prb028_031_negative_controls.py`, record
  `records/risk_verification/PRB-028-031_negative_controls_2026-10-31.json`.
- Fixture change, no assertion removed: the PRB-003 test classification record states the atlas method ("msmask")
  instead of "geometric", so those tests keep testing their own rule.

## 4. Residual risk and limits
- The tick states that the radiologist checked a region; it cannot show that he looked at the right slice (the button
  opens it). As for the DIS confirmation itself, a direct API call can send the digest served in the DIS state
  (RMF-001, residual risk of RC-071).
- The ticks live in the open card: closing the segmentation or reloading the page clears them.
- The usability cost falls on native-space clinical images, where the atlas is refused: every lesion must be ticked
  (about one click and one slice per lesion; 45 for P51), and more than 100 lesions cannot be confirmed on a geometric
  classification at all. A parcellation of the image (FreeSurfer labels) or MNI registration avoids it.

## 5. Owner decisions (PENDING)
1. Severity Major.
2. Accept the per-lesion tick as the "explicit review" (rather than refusing DIS outright on geometric classifications),
   with its usability cost for native-space clinical images (§4), and the 100-lesion limit.
3. Whether the P51 figures (MSLesSeg data) may be quoted in the user interface; the texts now say only that the
   geometric regions "often differ from the atlas".
4. Raise a GitHub Issue (SPR-001).
5. The independent review of the change: `dis_review_gate.py` and the confirmation route are not on the Class C list
   but decide what a Class C result may rest on.
