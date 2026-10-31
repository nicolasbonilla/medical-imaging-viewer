# PRB-029 — The AI-Draft Review Was Confirmed Without Checking That the Lesions Were Drawn

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: next free after PRB-028. GitHub Issue: not
raised — owner action.*

**Problem ID**: PRB-029
**Reporter**: integration notes of release 2026-10-25 (§7, "known pre-existing issue"); accepted by the owner as "fix in
the next version"; fixed by the AI coding agent on branch `fix/next-safety-round`
**Date**: 2026-10-31
**Version**: `main` @ `ca600c2`
**Severity**: **Major** (proposed; the AI report stays ON in production by owner decision, and the AI draft's review is
the first confirmation a radiologist gives on an AI segmentation — HAZ-001, HAZ-003). **N. G. Bonilla Vargas — approved 2026-10-31 (PR #74).**
**Status**: OPEN — DRAFT. Fixed on branch `fix/next-safety-round` (draft PR), not merged, not deployed.

## 1. What happened
Since the final check of PR #69 the DIS confirmation is refused unless every lesion is drawn on screen (the standard 2D
view in segmentation mode, every value drawn with its stored label, visible, overlay on, lesion opacity above the
minimum) and the server compares the drawn label table. The AI-draft review (`AiDraftBanner`, RC-047) had none of
this: it was accepted with segmentation mode off, in the 3D view, with the overlay off, a label hidden or another label
preset selected.

## 2. Fix
- The check of the view on screen moved into ONE shared module, `frontend/src/utils/confirmDrawCheck.ts`
  (`confirmDrawCheck`, `undrawnText`), used by both confirmations — the DIS card's code was moved, not copied.
- `AiDraftBanner` reads the label table stored on the server when Confirm is pressed (shown as the viewer draws it, in
  the shared region colours), runs the shared check, and lists the reasons when it refuses (no dialog, no request).
  It also gets the checks of PRB-030 (image grid) and PRB-031 (layers under the lesions).
- The request carries the drawn label table (`drawn_labels_sha256`) and the image under the mask
  (`displayed_image_file_id`); `POST /segmentation/{id}/ai-review/confirm` refuses (409) a table other than the stored
  one as drawn — the same server function as the DIS confirmation (`_drawn_labels_problem`).

Requirement **REQ-SAFE-045**; risk control **RC-091** (HAZ-001, HAZ-003).

## 3. Verification
- Failing first: `frontend/src/components/AiDraftBanner.prb029.test.tsx` (10) and the PRB-029 cases of
  `backend/tests/unit/test_prb029_prb030_confirm_view_checks.py` (5); on `ca600c2` every refusal fails, the case drawn
  with the stored labels is a positive control (record `PRB-028-031_tests_on_base_2026-10-31.json`).
- Negative controls A1–A3 (server), B1–B3 and Z1–Z3 (viewer): **9 of 9 detected** (whole run 62 of 62, throwaway worktree of `5cc88b9`, 2026-10-31, after the review of PR #74; first run 5 of 5 of the first round's set, `05cdf37`); the shared-check mutations C4, C6, O1, O3, O7
  also run the AI-draft tests (all detected; whole run 49 of 49, throwaway worktree of `05cdf37`) — record
  `PRB-028-031_negative_controls_2026-10-31.json`.
- Fixture changes, no assertion removed: `AiDraftBanner.test.tsx` seeds the draft drawn on screen and the stored labels;
  its exact-argument assertion also names what the call now carries; `test_rc047_ai_draft_provenance.py` sends the drawn
  table and the image under the mask.

## 4. Residual risk
As for the DIS confirmation: the drawn-lesion check runs in the browser; a direct API call or another client can state
the stored table without drawing it (RMF-001, residual risk of RC-071).

## 6. Independent review of PR #74 (`290e407`) — corrections (2026-10-31, DRAFT, N. G. Bonilla Vargas — approved 2026-10-31 (PR #74))
No blocker and no major issue; the claims hold. Tests written first (on `290e407` they fail except their positive controls: `records/risk_verification/PRB-028-031_review1_tests_on_290e407_2026-10-31.json`), then the corrections, then the negative controls (`PRB-028-031_negative_controls_2026-10-31.json`, re-run).
| # | Finding | Correction | Tests / controls |
|---|---|---|---|
| m1 | "Colorize by zone" (switched on with the zone map) draws values 1-4 in the region palette whatever their label, and does not draw a value 5 or 6 on a slice that has any 1-4; the shared check did not see it — an AI draft drawn orange as "periventricular", a value-5 lesion invisible, Confirm accepted | Both confirmations are refused while zone colouring is drawn, unless every value present is a region id 1-4 drawn with that region's label (a classified segmentation, where zone colouring draws exactly the stored labels) | `AiDraftBanner.prb029.review.test.tsx` (4, 2 positive controls); Z1, Z2 |
| m7 | A tab opened before the update sends only the mask digest and got the label-table message | A request that states neither the drawn label table nor the image under the mask gets one answer on both routes: "This viewer is out of date … Reload the page". (An old AI-draft banner shows only the status code; the old DIS card shows the server's message.) | `test_prb028_031_review_findings.py` (m7, 2); A3 |

## 5. Owner decisions (PENDING)
Severity Major; raise a GitHub Issue (SPR-001).
