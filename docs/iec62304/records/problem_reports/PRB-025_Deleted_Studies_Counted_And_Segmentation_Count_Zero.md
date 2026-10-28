# PRB-025 — Deleted Studies Stay Listed and Counted; "SEGM." Always 0; Permanent Deletion Open to Any User

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: see PRB-020. GitHub Issue: not raised.*

**Problem ID**: PRB-025
**Reporter**: browser capture of the release candidate, 2026-10-28 (F07; `findings/F07*.png`: STUDIES 3, IMAGING DATA
9 images, "3 scans tracked" with two deleted studies; every study card SEGM. 0); permanent-deletion finding by the AI
coding agent while reproducing it
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7`
**Severity**: **Major** (proposed; wrong counts on the patient record and dashboard, a monitoring view built on deleted
studies). The permanent-deletion part could be **Critical** (irreversible loss of images by any user with access) —
owner decision. **PENDING owner approval.**
**Status**: OPEN — DRAFT. Fix on branch `fix/platform-security-findings-prb020`.

**Description**:
1. Deleting a study is a soft delete: the record gets status `cancelled` (`study_service_firestore.py:421-426`) — right
   for record keeping — but the patient's study list (`list_patient_studies`, `:507-560`) and search (`:438-505`) return
   it, and the patient's counts (`patient_service_firestore.py:281-292` and the list counts at `:455`, `:549`) count it.
   Everything built on the list counts it too: studies tab, "IMAGING STUDIES", "IMAGING DATA … images", "N scans
   tracked", the monitoring window, the dashboard's "MRI STUDIES". Deleted documents (`entered-in-error`) were filtered
   from document lists but still counted in the patient's document count.
2. The study card's "SEGM." is a constant: `const segmentationInfo = undefined` (`StudyCard.tsx:64`) rendered as
   `?? 0` (`:233`); no count was ever computed.
3. `DELETE /studies/{id}?hard_delete=true` erases every file of the study from storage. Its docstring says
   "ADMIN only for hard_delete" (`studies.py:185`), but the route checks only patient access (`:187`): any user on the
   care team (a viewer included) could erase a study's images permanently through the API (the interface never sends it).

**Fix** (on branch):
- `study_service_firestore.py`: without an explicit status filter, `cancelled` and `entered-in-error` studies are
  excluded from the page **and** the total (in memory, like documents: no inequality query, no composite index, no loss
  of records without a status field); with an explicit status filter that status is returned (a deleted study can still
  be found on purpose); `list_patient_studies` uses the same path. `StudySummary.segmentation_count`: the saved
  segmentations whose image lies under the study's storage prefix, MAGNIMS zone maps excluded; `None` when it cannot be
  counted.
- `patient_service_firestore.py`: study and document counts exclude the deleted statuses (equality-only count queries);
  a count that fails is `None`, not 0.
- `StudyCard.tsx`, `PatientCard.tsx`: the count the server reported, or "—" — never a 0 nobody counted.
- `studies.py`: `hard_delete` is administrator-only (403 otherwise); the soft delete records who deleted.
- Requirement **REQ-FUNC-110**; risk control **RC-085** (HAZ-009 wrong data shown for the patient, HAZ-010 permanent
  deletion).

**Verification**: `test_prb021_patient_scope_creator_counts.py` — `test_rc085_prb025_*` (6) and
`StudyCard.prb025.test.tsx` — `rc085 prb025 *` (4): deleted studies not listed; deleted studies and documents not counted
(service and route); explicit status filter finds a cancelled study; segmentation count 2 of 4 documents (zone map and
another study excluded); deleting through the route removes it from the list and the count but keeps the record; hard
delete by a radiologist → 403, study intact; the card shows 2, "—" when unknown, 0 only when reported. On `70cc5c7`
every backend test and three of the four frontend tests fail (0 shown when the server reports 0 is the positive control). Negative controls K1–K7, F6–F8.

**What the fix does not do**: deleted studies cannot be viewed or restored from the interface (no "show deleted"
view); the document delete route still allows a permanent delete by any user with access (not claimed otherwise in its
docstring — owner decision); the counts of the patient overview tiles come from the list and are not stored.

**Owner decisions (PENDING)**: severity (Major; Critical for the permanent-deletion part?); whether permanent deletion of
documents is also restricted to administrators; whether a view of deleted studies is wanted.
