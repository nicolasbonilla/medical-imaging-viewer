# PRB-027 — Any Role Could Search the PACS by Patient Name; the MRN Conflict Reveals That a Record Exists

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: next free after PRB-026 (PRB-004..009 are used by
the concurrent display work). GitHub Issue: not raised — owner action.*

**Problem ID**: PRB-027
**Reporter**: independent review of PR #70 (finding m9, pre-existing); verified by the AI coding agent on the PR branch
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7` (present before PR #70)
**Severity**: **Major** (proposed; disclosure of patient identities from the connected hospital PACS to any account, a viewer
included — HAZ-010; only when a PACS connection is configured). **PENDING owner approval.**
**Status**: OPEN — DRAFT. Part A fixed on branch `fix/platform-security-findings-prb020` (PR #70); part B recorded with a
proposed fix, not implemented.

## A. PACS patient search and import open to every role — FIXED on branch
**Actual**: `POST /api/v1/dicomweb/search/studies` (`dicomweb.py:113-127`) and `/search/series` (`:130-143`) let **any**
active user, a VIEWER included, query the configured remote PACS by patient name, patient id, birth date, date and
accession number (QIDO-RS); `POST /dicomweb/import` (`:148-166`) let any care-team member import into a patient. The PACS is
the hospital's registry, outside the care-team rule (REQ-SEC-032 cannot apply: the PACS has no assignments), so the search
is a patient-identity lookup over the whole hospital.
**Fix**: the three routes require **IMAGE_UPLOAD** (technician, radiologist, administrator) — searching and importing from the
PACS is part of bringing images in; a viewer gets 403 before the PACS is asked. Connection configuration stays
administrator-only (RC-036). Requirement **REQ-SEC-035**; risk control **RC-089** (HAZ-010).
**Verification**: `backend/tests/unit/test_prb020_review1_findings.py` — `test_rc089_prb027_*` (6: a viewer on the care team
gets 403 on the three routes and the PACS stand-in is never called; a technician still searches and imports — positive
controls). The viewer tests fail at `7de9334` (`records/risk_verification/PRB-020_review1_tests_on_7de9334_2026-10-28.json`). Negative controls V25–V27 (`records/risk_verification/PRB-020_negative_controls_2026-10-28.json`).
**Limit**: a technician or radiologist can still search the whole PACS by name — inherent to finding a study to import.
Proposed (owner decision): record every PACS search in the audit trail with the user and the query fields used.

## B. "Patient with MRN '…' already exists" — RECORDED, not changed
**Actual**: `POST /api/v1/patients` answers 409 with the MRN to any role that may create patients (technician and above)
when a record with that MRN exists, whether or not the caller may see that record. Since PRB-021 the list no longer reveals
other patients, so this is now the only way for a clinician to learn that an MRN is registered.
**Why not changed here**: the answer prevents duplicate records (a second record splits a patient's scans and hides priors
from comparisons — HAZ-009); hiding it would trade a confidentiality signal (one MRN at a time, rate-limited, by a
signed-in clinician) for a safety risk.
**Proposed fix** (owner decision): keep the 409 but word it "A patient record with this MRN already exists. Ask an
administrator to add you to its care team." (no other data); record each conflict in the audit trail (user, time, MRN
hash) so that enumeration is visible; optionally require an administrator to resolve it.

## Owner decisions (PENDING)
Severity Major; part B proposal; audit of PACS searches; raise a GitHub Issue (SPR-001).
