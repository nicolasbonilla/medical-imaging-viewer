# CAPA-016 — Dissemination in Space Evaluated on a Segmentation No Clinician Has Confirmed

**CAPA ID**: CAPA-016
**Date Opened**: 2026-10-24 (DRAFT — opening, severity and actions **PENDING owner approval**)
**Source**: PRB-003 (`records/problem_reports/PRB-003_DIS_Evaluated_On_Unreviewed_Segmentation.md`), from the paper A
v0.3 healthy-control addendum (branch `research/paper-a-v0.3`, PR #54, `f3b22cd`; record
`docs/research/records/2026-10-24_paper_a_v03c_controls.json`, key `app_dis`). Every finding below was re-checked in
the code of `main` @ `70cc5c7` on 2026-10-24 and reproduced by tests written before the fix (§5).
**Severity**: **CRITICAL, safety-related** (proposed; QP-002 §5 patient safety risk / SPR-001 §2 safety impact, as
PRB-003). The device is not in clinical use and the AI tools are believed off in production: that lowers the
probability of harm, not the class.
**Owner**: *(to be assigned — a person; the AI coding agent cannot own a CAPA)*
**Status**: DRAFT. Corrections implemented on branch `fix/dis-requires-reviewed-segmentation-prb003` (draft PR #68, from
`main` @ `70cc5c7`). Nothing merged, nothing deployed. **PENDING owner approval.** Effectiveness is not verified.
**Identifiers**: RC-070, RC-071, RC-072; REQ-SAFE-038, REQ-SAFE-039, REQ-SAFE-040; CAPA-016; no new hazard. Checked on
every open branch on 2026-10-24: PR #67 (CAPA-014) holds RC-064..066, REQ-SEC-021..023, HAZ-016, SRS 1.11, RMF 1.13,
TM 1.10; PR #65 (CAPA-015) holds RC-067..069, REQ-SEC-024..026, SRS 1.12, RMF 1.14, TM 1.11 (RC-063 is unused but was
skipped by #67; not taken, to avoid a collision with an unannounced reservation). Document versions here: **SRS 1.13,
RMF 1.15, TM 1.12** (drafts; merge after #67 and #65, or renumber the version rows at merge).
**CAPA linkage**: a dedicated CAPA (decision D-1): the root cause — a computation that never consumed the review
record that exists — is not the one of CAPA-006 (labelling and atlas space) or CAPA-013 (longitudinal candidates).
**Procedure**: QP-002 (`docs/qms/QP-002_CAPA_Procedure.md`) · SPR-001
**Related**: HAZ-008 · HAZ-005 · HAZ-003 · REQ-SAFE-015 · REQ-SAFE-030 (RC-047) · RC-029 · RC-033 · RC-034 · PRB-001 ·
CAPA-013 · paper A app spec §5 rule 6

---

## 1. Findings (code of `main` @ `70cc5c7`)

Measured (paper A, 100 public healthy controls, SibBMS, one site, template-normalised, not expert-read, CC BY-NC-SA
3.0): the raw automatic FLAMeS 5-fold segmentation marked at least one lesion in **85 / 100** (2.6 per scan); the
device's brain-DIS code (MSMask zones → MAGNIMS contact rule → `compute_dis_criteria`) returned **"DIS met (brain)" in
19 / 100** (95 % CI 11.8–28.1 %); **63 %** of false marks were periventricular.

### Finding 1 — DIS was computed on any loaded segmentation
`segmentation_analysis.get_dis_assessment` (lines 498-607) checked neither the origin nor any review. An unreviewed
AI draft, a server-tool output and a mask uploaded through `PUT /mask/binary` were evaluated like hand-drawn work.

### Finding 2 — The review that exists was never consumed
RC-047 binds the AI-draft review to the SHA-256 of the stored mask and resets it on any change, but no computation
reads it. Server-tool outputs carry `segmentation_type = automatic` and no provenance: they could not be confirmed at
all (`confirm_ai_review` → 409). Hand-drawn and uploaded masks are indistinguishable and have no review record.

### Finding 3 — A stored conclusion was displayed outside any route
`classify_regions` stored a DIS result for any mask; `LesionDashboard` showed `analysis_data.dis_assessment` straight
from the segmentation metadata.

### Finding 4 — The report and the assistant restated an unverified DIS
The report route forwarded the client's DIS block; the prompt builder (Class C) printed "NOT MET" for a missing flag;
the templates ask the model for a DIS table from lesion counts. The assistant passed the route's result through.

### Finding 5 — Every consumer of DIS (searched 2026-10-24)
DIS route, its cache, classify-regions, segmentation metadata (`GET /{id}`, `/list`), lesion panel, AI report (route,
prompt, templates), AI assistant (`summarize_dis_items`, `generate_ms_report`). Not affected: FHIR, DICOM-SEG and CSV
exports (no DIS), the longitudinal comparison (no DIS; DIT handled by CAPA-013).

## 2. Root cause

1. No requirement stated on which segmentation DIS may be computed (REQ-SAFE-015 covers only the display).
2. AI segmentation and its review (CP-FLAMES-BROWSER-001) were added without requiring the downstream computations to
   use the review; server tools got no provenance.
3. A derived clinical conclusion was persisted and displayed outside the route that computes it.
4. Client data (report findings) were trusted for a clinical conclusion.

## 3. Corrections and corrective actions (implemented on the branch — PENDING owner approval)

| ID | Action | Control | Where |
|---|---|---|---|
| CA-16.1 | DIS evaluated only when a radiologist's confirmation is bound to the SHA-256 of the current stored mask (AI draft: RC-047 review reused; any other segmentation: the new clinician confirmation); otherwise the explicit state "not evaluated: requires clinician review of the segmentation" with reason, origin and no met / not met, region presence or topography count; nothing computed or cached | RC-070 | `services/dis_review_gate.py` (new), `segmentation_analysis.assess_dis` |
| CA-16.2 | Stored DIS never served: the cache only for an evaluated block under a passing gate; classify-regions stores the gated state; metadata responses never carry `dis_assessment` | RC-070 | `segmentation_analysis.py`, `segmentation_regions.py`, `segmentation.py` |
| CA-16.3 | Report: DIS re-derived on the server for the segmentation named (RC-029 authorization; compute-only, nothing stored); "NOT EVALUATED" plus a rule against deriving DIS in the prompt; fixed notice in en/es/de after the model; a request whose only measurement is an unevaluated DIS refused (RC-034) | RC-070 | `ai_report.py`, `brain_report_service.py` (Class C, §6) |
| CA-16.4 | Assistant: only an evaluated block passes (also against an older backend); instructions and workflow: report "not evaluated", never derive DIS from counts or regions | RC-070 | `mcp/ms_clinical_server.py`, `mcp/_backend.py` (comment) |
| CA-16.5 | Viewer: the lesion panel reads only the gated route; "not evaluated" card (reason, origin, confirm action, notice); met / not met, five-topography panel and badges only for an evaluated result of the saved mask (withheld while the mask on screen has unsaved changes, read again after a save), naming the confirming radiologist; review records re-read after a reclassification | RC-070 | `LesionDashboard.tsx`, `types/lesion.ts`, `types/segmentation.ts`, `api/segmentation.ts` |
| CA-16.6 | Confirmation of a segmentation without AI provenance: `POST /segmentation/{id}/review/confirm` — radiologist only (403), the SHA-256 of the mask on screen must equal the stored mask (409), AI drafts refused (409, own review), authenticated user and time recorded; removed by any later change of the mask (single save point); no confirm button with unsaved changes | RC-071 | `models/schemas.py` (`ClinicianReview`), `segmentation.py`, `segmentation_service.enforce_review_binding`, `LesionDashboard.tsx` |
| CA-16.7 | Information for safety wherever an automatic segmentation is shown — "Automatic marking also marks spots in most healthy brains, mostly next to the ventricles. A marked spot is not evidence of multiple sclerosis; every spot needs expert review." (paper A wording A, no numbers) — in en/es/de: AI draft banner, segmentation panel (server-tool output), "not evaluated" card and API state, report notice and prompt, assistant instructions | RC-072 | `AutomaticMarkingNotice.tsx` (new), `AiDraftBanner.tsx`, `SegmentationPanel.tsx`, locales, `dis_review_gate.AUTOMATIC_MARKING_NOTICE` |

### What the clinician sees
- Lesion panel, segmentation not confirmed: an amber card "DIS (brain MRI): not evaluated", the reason (no radiologist
  has confirmed / changed since it was confirmed), the origin (AI draft → confirm in its banner; clinical tool; origin
  not recorded), the healthy-brain notice for automatic segmentations, and — for a radiologist on a saved mask — "I have
  checked every lesion and region — confirm this segmentation". No green or red badge, no 5-topography panel.
- After the confirmation: the DIS result as before, with "Segmentation confirmed by <name>". Any later save of a
  changed mask, or a new region classification, returns the card to "not evaluated".
- AI report: a draft without an evaluated DIS ends with "Dissemination in space: not evaluated …" and the notice.

## 4. Preventive actions (proposed — PENDING owner approval)

| ID | Action |
|---|---|
| PA-16.1 | SRS rule: any computation that turns a segmentation into a clinical criterion (DIS, DIT, counts for McDonald) states its input precondition (confirmed segmentation) and is bound to a test. |
| PA-16.2 | Give server-tool outputs AI provenance (model, version, SHA-256) at storage, so their origin is recorded like the in-browser draft. |
| PA-16.3 | Never persist a derived clinical conclusion in record metadata; store measurements and compute conclusions in the gated route. |
| PA-16.4 | Add `services/dis_review_gate.py` to the Class C module list (CLAUDE.md, owner action). |
| PA-16.5 | Labelling: IFU-001 / CER-001 state that DIS requires a radiologist's confirmation of the segmentation. |

## 5. Verification (by the author — not independent; owner approval PENDING)

**Tests written before the fix, failing on `70cc5c7`.** `backend/tests/unit/test_prb003_dis_requires_confirmed_segmentation.py`
(41 cases: `test_rc070_*`, `test_rc071_*`, `test_rc072_*`; real routes, real `SegmentationService` with the datastore
stubbed, real prompt builder, real assistant module with `fastmcp` stubbed) and
`frontend/src/components/LesionDashboard.prb003.test.tsx` (12 cases; the real panel and banner with mocked API).
Re-run against the base source files by `scripts/safety/prb003_tests_on_base.py` → record
`records/risk_verification/PRB-003_tests_on_base_2026-10-24.json`: backend **39 of 41 fail** (the base returns
`brain_regions_with_lesions: 2` and "DIS met" for an unreviewed AI draft, a server-tool mask and an upload; serves a
stored conclusion; has no confirm route; prints NOT MET; forwards a forged block), frontend **12 of 12 fail**. The two
cases passing on the base are positive controls (an evaluated block still reaches the prompt and the assistant).
Three cases were added after the first base run while writing the negative controls (a stored "not evaluated" state
never relabelled as a result; a block without the evaluated state never shown as met; a result withheld while the mask
on screen has unsaved changes and re-read after saving) and one source-level assertion was adapted to the
implementation's variable name; the base record was produced again with the final test files.

**After the fix.** Both files pass (41 / 41, 12 / 12). Backend unit tree (`pytest tests/unit`, offline per PRB-002):
see §5a. Frontend full suite (vitest `--pool=threads`): see §5a. `tsc --noEmit`: clean; production build passes. Existing tests changed with the
contract (stated): `test_analysis_flow_ci_guard.py::test_dis_assessment_returns_200`,
`test_brain_report_service.py::test_build_findings_prompt_dis_assessment`, `test_capa009_*` (new route registered,
object authorization), `tests/integration/test_segmentation_route_characterization.py::test_dis_assessment_contract`
(requires Firestore; deselected in CI). The anchors of every existing negative-control script (236) still occur exactly
once, so CP-FLAMES-BROWSER-001, CAPA-008..013 and RC-029/032 controls can be re-run unchanged.

**Negative controls.** `scripts/safety/prb003_negative_controls.py` — one mutation at a time in the real source, each
anchor asserted unique, bytes restored: see §5a.

**Not verified.** No test in a real browser (jsdom only); no run against Firestore, GCS or the real model provider;
no usability evaluation (IEC 62366) of the confirmation step; effectiveness in clinical use not measurable (not in use).
The report's protection against a model that writes a DIS statement anyway rests on the prompt rule and the fixed
notice after the draft — the model's text itself is not checked.

### 5a. Results

| Check | Result | Record |
|---|---|---|
| PRB-003 tests on `70cc5c7` | backend 39 of 41 fail (2 positive controls pass), frontend 12 of 12 fail | `records/risk_verification/PRB-003_tests_on_base_2026-10-24.json` |
| PRB-003 tests on the fix | 41 / 41, 12 / 12 pass | — |
| Negative controls | **37 mutations, 37 detected** — RC-070: G1–G9 (gate, binding, AI review, cache, metadata, list, classify-regions, conclusion in the state), R1–R7 (report: client block, authorization, compute-only, MET for an unevaluated block, rule against deriving DIS, notice, unevaluated-only request), A1–A2 (assistant), F1–F2, F12–F13 (display); RC-071: C1–C5 (role, mask, AI draft, binding, reviewer), F3–F5, F10–F11; RC-072: N1, F6–F9. Bound tests green after byte-exact restore | `records/risk_verification/PRB-003_negative_controls_2026-10-24.json` |
| Whole backend test tree, offline (PRB-002), Firestore/GCS/PACS deselected as in CI | 1759 passed, 5 xfailed, 1 failed: `test_webauthn_credentials_endpoint_exists` (`webauthn` not installed locally; known, unrelated) | — |
| Frontend suite (vitest `--pool=threads`) | 343 passed, 3 skipped (FLAMeS tests needing local research data), 0 failed | — |
| `tsc --noEmit`, production build | clean / passes | — |
| Anchors of the existing negative-control scripts | 236 checked, all still unique | — |

## 6. Class C module modified — justification (CLAUDE.md)

`backend/app/services/brain_report_service.py` — **only the DIS block of `_build_findings_prompt`** and one new constant
`DIS_NOT_EVALUATED_PROMPT`: a DIS result is passed to the model only when the block is marked evaluated (set by the
report route from the stored segmentation); otherwise the prompt says NOT EVALUATED and forbids deriving DIS from the
lesion counts or regions. Before, a missing `dis_met` printed "NOT MET". No template, no other branch changed.
`lesion_analysis_service.py` and `ms_region_classifier.py` are **not modified**. The new gate module decides whether
`compute_dis_criteria` may run; proposed for the Class C list (PA-16.4). **Code review required before merge.**

## 7. Residual risk and open items

- A radiologist can confirm a segmentation without checking it; the confirmation records who and for which mask, and
  the dialog states what is confirmed. Usability evaluation (IEC 62366) open.
- The report model may still write a DIS sentence despite the rule; the fixed notice says no DIS statement in the draft
  comes from the software.
- Stored DIS blocks written before the fix stay in the records (no longer served). Read-only check of production data
  proposed (owner).
- Persisting a confirmation (`persist()`) rewrites the unchanged mask object, as the RC-047 confirmation and the analysis
  routes already do; a client holding the previous storage generation may then get the existing stale-write conflict
  (A-2) on its next save. Pre-existing behaviour, not changed here.
- HAZ-008 residual risk to be re-estimated by the owner with RC-070..072 (RMF-001 §5.2).

## 8. Owner decisions (PENDING owner approval)

| ID | Decision |
|---|---|
| D-1 | Severity (Critical, proposed) and a dedicated CAPA-016 (vs. an action under CAPA-006). |
| D-2 | Every segmentation — also hand-drawn — needs a radiologist's confirmation before DIS is shown; only the radiologist role confirms. |
| D-3 | `dis_review_gate.py` in the Class C list (PA-16.4). |
| D-4 | Production checks (read-only): stored `dis_assessment` blocks and automatic-source segmentations; values of the AI tool flags. |
| D-5 | SibBMS licence before any number is quoted in product text. |
| D-6 | IFU-001 / CER-001 wording (PA-16.5). |
| D-7 | Merge order with PR #67 (`report_payload_guard` must carry `evaluation_status`) and #65 (document version rows). |

## 9. Approvals

| Role | Name | Decision | Date |
|---|---|---|---|
| Owner / management representative | *(owner)* | **PENDING owner approval** | — |
| Code review of the Class C change | *(reviewer)* | **PENDING** | — |
