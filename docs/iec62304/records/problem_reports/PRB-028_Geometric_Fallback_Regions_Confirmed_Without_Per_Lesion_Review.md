# PRB-028 — Regions From the Geometric Fallback Could Feed DIS Without a Lesion-by-Lesion Review

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: next free after PRB-027 on every branch
(checked 2026-10-31). GitHub Issue: not raised — owner action.*

**Problem ID**: PRB-028
**Reporter**: film capture of 2026-10-28 (MSLesSeg P51); accepted by the owner as "fix in the next version"; analysed and
fixed by the AI coding agent on branch `fix/next-safety-round`
**Date**: 2026-10-31
**Version**: `main` @ `ca600c2` (present since the region classification has a geometric fallback)
**Severity**: **Major** (proposed; a DIS result can rest on region labels that are wrong for most lesions — HAZ-005,
HAZ-008). **N. G. Bonilla Vargas — approved 2026-10-31 (PR #74).**
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
- Negative controls G1–G9 (server), U1–U8 and P2 (viewer): **18 of 18 detected** (whole run 62 of 62, throwaway worktree of `5cc88b9`, 2026-10-31, after the review of PR #74; first run 14 of 14 of the first round's set, `05cdf37`) — `scripts/safety/prb028_031_negative_controls.py`, record
  `records/risk_verification/PRB-028-031_negative_controls_2026-10-31.json`.
- Fixture change, no assertion removed: the PRB-003 test classification record states the atlas method ("msmask")
  instead of "geometric", so those tests keep testing their own rule.

## 4. Residual risk and limits
- A tick is the radiologist's attestation that he checked the region. Since the review of PR #74 (m2) a tick can be
  given only after its "open slice" was pressed, and only while this segmentation is open and drawn in the Standard
  view; this shows that the slice was put on screen, **not that it was read**. The server checks only that the request
  echoes the digest the DIS state served: a direct API call or another client can send it without any tick (RMF-001,
  residual risk of RC-071 and RC-090).
- The ticks live in the card: they are cleared when the served list changes, when the segmentation is closed or another
  one is opened, and when the page is reloaded.
- The usability cost falls on native-space clinical images, where the atlas is refused: every lesion must be ticked
  (about one click and one slice per lesion; 45 for P51), and more than 100 lesions cannot be confirmed on a geometric
  classification at all. A parcellation of the image (FreeSurfer labels) or MNI registration avoids it.

## 6. Independent review of PR #74 (`290e407`) — corrections (2026-10-31, DRAFT, N. G. Bonilla Vargas — approved 2026-10-31 (PR #74))
No blocker and no major issue; the claims hold. Tests written first (on `290e407` they fail except their positive controls: `records/risk_verification/PRB-028-031_review1_tests_on_290e407_2026-10-31.json`), then the corrections, then the negative controls (`PRB-028-031_negative_controls_2026-10-31.json`, re-run).
| # | Finding | Correction | Tests / controls |
|---|---|---|---|
| m2 | Ticks could be given on an expanded card whose segmentation was not open (another one on screen) and survived opening another one | A tick only while THIS segmentation is open and drawn (`overlayOnScreen`), only after its "open slice"; ticks and opened slices cleared when it is closed or another one is opened; §4 corrected | `LesionDashboard.prb028.review.test.tsx` (m2, 4); U7, U8 |
| m3 | The honest limit of the tick was in this report only | Stated in RMF-001 (RC-090 row) and §4 above | — (document) |
| m4 | After a confirmation with ticks, the same mask classified again with the atlas gave "geometric_regions_not_reviewed" | The geometric binding is compared only while there are geometric-fallback lesions (`dis_review_gate.review_state`) | `test_prb028_031_review_findings.py` (m4, 2); G9 |
| m5 | The reset of the ticks on a changed list had no test | Ticks keyed by first voxel AND region; regression test; negative control | `LesionDashboard.prb028.review.test.tsx` (m5); U6 |

**Known limits recorded (review m10, not changed here):** region *corrections* above 100 can still be acknowledged while
only 100 are listed (unlike the geometric list, refused above 100); the atlas path's default deep white matter for a
lesion outside atlas coverage is not offered for a per-lesion check (deep white matter does not count for DIS: a possible
false negative, not a false DIS); the confirmation history event does not record that a per-lesion check was part of the
confirmation (the confirmation record itself does).

## 5. Owner decisions (PENDING)
1. Severity Major.
2. Accept the per-lesion tick as the "explicit review" (rather than refusing DIS outright on geometric classifications),
   with its usability cost for native-space clinical images (§4), and the 100-lesion limit.
3. Whether the P51 figures (MSLesSeg data) may be quoted in the user interface; the texts now say only that the
   geometric regions "often differ from the atlas".
4. Raise a GitHub Issue (SPR-001).
5. The independent review of the change: `dis_review_gate.py` and the confirmation route are not on the Class C list
   but decide what a Class C result may rest on.
