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
   *Found by the independent review of PR #70 (M1):* `DELETE /studies/series/{id}` and `DELETE /studies/instances/{id}`
   (`studies.py:252-264`, `:322-334` on `main`) erase the series' files and the image file the same way, with the same
   care-team check only; their docstrings named a `STUDY_DELETE` permission that does not exist. The first version of this
   report said permanent deletion was fixed — it was fixed for the study route only.
4. *(review of PR #70, M2)* Cancelling a study (`DELETE /studies/{id}` without `hard_delete`, `studies.py:170-193`) had no
   role check either, and `PUT /studies/{id}` could set `status` to `cancelled` with the care-team check only. Since this
   report's fix a cancelled study is no longer listed or counted for **anyone**, so a read-only account could hide a prior
   scan from a radiologist's longitudinal comparison (HAZ-009).

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
  *Review of PR #70:* `DELETE /studies/series/{id}` and `DELETE /studies/instances/{id}` require **IMAGE_DELETE**
  (administrator only, M1); cancelling a study — `DELETE /studies/{id}`, and a `status` change through
  `PUT /studies/{id}` — requires **PATIENT_UPDATE** (radiologist, administrator; M2), the existing permission that fits a
  change of the patient's record (no `STUDY_DELETE` permission exists; the docstrings that named it are corrected).
  **Effect**: viewers and technicians can no longer cancel a study (the interface's delete answers 403 for them); a
  cancelled study is hidden for everyone and can be found again only through the API
  (`GET /api/v1/studies?patient_id=<id>&status=cancelled`) and restored by a radiologist or administrator with
  `PUT /api/v1/studies/{id}` `{"status": "available"}`.
- `PatientsOverview.tsx` *(review of PR #70, m5)*: the "MRI Studies" and "Documents" tiles show "—" when any patient's
  count is unknown, instead of adding it as 0.
- `patient_service_firestore.py` *(review of PR #70, m6)*: the five count queries of each patient of a page (studies:
  total, cancelled, entered-in-error; documents: total, entered-in-error) run for up to 8 patients at a time instead of
  one after another.
- Requirement **REQ-FUNC-110**; risk control **RC-085** (HAZ-009 wrong data shown for the patient, HAZ-010 permanent
  deletion).

**Verification**: `test_prb021_patient_scope_creator_counts.py` — `test_rc085_prb025_*` (6) and
`StudyCard.prb025.test.tsx` — `rc085 prb025 *` (4): deleted studies not listed; deleted studies and documents not counted
(service and route); explicit status filter finds a cancelled study; segmentation count 2 of 4 documents (zone map and
another study excluded); deleting through the route removes it from the list and the count but keeps the record; hard
delete by a radiologist → 403, study intact; the card shows 2, "—" when unknown, 0 only when reported. On `70cc5c7`
every backend test and three of the four frontend tests fail (0 shown when the server reports 0 is the positive control). Negative controls K1–K7, F6–F8.

**What the fix does not do**: deleted studies cannot be viewed or restored from the interface (no "show deleted"
view; restore through the API as above); the document delete route still allows a permanent delete by any user with
access (not claimed otherwise in its docstring — owner decision); the counts of the patient overview tiles come from the
list and are not stored.

**Known performance limits (review of PR #70, m6)** — measured with the in-memory stand-in only; production latency was
not measured (production was not contacted):
- Each listed patient costs 5 aggregation queries. The patient list page (12 patients) is 60 queries; the patient search
  page the interface requests while a name or sex filter is typed (100 patients) is 500. With a stand-in round trip of
  50 ms, 20 patients took **5.16 s** one after another at `7de9334`; they now run 8 at a time and the test bounds the page at
  2.5 s (`test_rc085_prb025_r1_page_counts_run_concurrently_with_the_same_results`). For a 100-patient page at 50 ms that is
  about 25 s before and about 3 s now. The handlers still call the database synchronously inside `async` routes, so the
  server's event loop is held for that time.
- An administrator's `GET /api/v1/studies` **without** a patient filter reads every study document (one read per study),
  because deleted studies are excluded in memory to keep the total exact. The interface does not call it (the hooks
  `useStudyList` / `useStudySearch` are unused; non-administrators must give a patient, RC-028). Proposed if it is ever
  used: exact totals by count queries and a bounded page read.
- A scoped list reads the caller's assigned patients one by one (PRB-021).

**Owner decisions (PENDING)**: severity (Major; Critical for the permanent-deletion part?); whether permanent deletion of
documents is also restricted to administrators; whether a view of deleted studies is wanted; the choice of PATIENT_UPDATE
for cancelling a study (technicians lose it; proposed: accept, or a new `study:cancel` permission later).

## Review of PR #70 (2026-10-28) *(review of PR #70, 2026-10-28 — DRAFT, PENDING owner approval)*

Verification of M1, M2, m5, m6: `backend/tests/unit/test_prb020_review1_findings.py` — `test_rc085_prb025_r1_*` (8 cases:
viewer, technician and radiologist get 403 on the series and instance deletes and nothing is erased; an administrator still
erases both; viewer and technician get 403 on cancel; a radiologist cancels and restores; a viewer's `PUT status=cancelled`
→ 403 while a description edit still works; page counts concurrent with identical results) and
`frontend/src/pages/PatientsPage.prb021.test.tsx` — `rc085 prb025 *` (null count → "—"; counted values summed). Run at the
previous PR head `7de9334` (`records/risk_verification/PRB-020_review1_tests_on_7de9334_2026-10-28.json`): every M1/M2/m5/m6 test fails there except the positive controls (administrator erases;
radiologist cancels and restores; description edit; counted values summed). Negative controls V1–V5, V23, VF5 (`records/risk_verification/PRB-020_negative_controls_2026-10-28.json`).
