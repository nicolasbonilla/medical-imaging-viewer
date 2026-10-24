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

*The rows below are the first version (`4c601f2`); they were corrected after the independent review of PR #68 — see §10,
which supersedes CA-16.1, CA-16.3, CA-16.5, CA-16.6 and CA-16.7 where they differ (e.g. an AI draft is no longer refused by
the confirmation route: it needs its own review AND the DIS confirmation).*

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
The report's protection against a model that writes a DIS statement anyway rests on the earlier layers (no region sent,
the system safety rule, no DIS or per-region template section) and the fixed notice after the draft; the output check on
the model's text (per sentence, en/es/de wordings) is a backstop and cannot recognise every paraphrase (second review,
N3).

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
| Second review of PR #68 at `29abe29` — tests on the base | backend 46 of 51, frontend 6 of 6 fail | `records/risk_verification/PRB-003_review2_tests_on_29abe29_2026-10-24.json` |
| Second review — tests on the corrections | 51 backend, 6 frontend pass | — |
| Negative controls after the second review | **112 mutations, 112 detected** (G/C/R/A/S/N/F of the previous runs, anchors updated; W1-W35 and WF1-WF8 for the second review) | `records/risk_verification/PRB-003_negative_controls_2026-10-24.json` |
| Regression after the second review | backend 1858 passed, 5 xfailed, 1 failed (webauthn, known); frontend 365 passed, 3 skipped; tsc clean; build passes; 353 anchors unique | — |

## 6. Class C module modified — justification (CLAUDE.md)

`backend/app/services/brain_report_service.py` — (1) the DIS block of `_build_findings_prompt` and the constant
`DIS_NOT_EVALUATED_PROMPT`: a DIS result is passed to the model only when the block is marked evaluated (set by the
report route from the stored segmentation); otherwise the prompt says NOT EVALUATED and forbids deriving DIS from the
lesion counts or regions. Before, a missing `dis_met` printed "NOT MET". (2) *Added after the review of PR #68 (finding
4):* `dis_not_evaluated_template()` and three lines in `generate_report`: without an evaluated DIS the template's DIS
sections are replaced by "not evaluated", every other line asking for DIS is removed, format rule 4 keeps only its CMSC
prohibition, and a safety rule heads the system prompt. (3) *Added after the second review (N4):* in the same function,
the per-region sections become one section without regions, and the region column, "by anatomical region", "(region)",
the "distribution pattern" item, "periventricular confluency" and the McDonald reference of the introduction are removed.
The template texts themselves are unchanged.
`lesion_analysis_service.py` and `ms_region_classifier.py` are **not modified**. The new gate module decides whether
`compute_dis_criteria` may run; proposed for the Class C list (PA-16.4). **Code review required before merge.**

## 7. Residual risk and open items

- A radiologist can confirm a segmentation without checking it; the confirmation records who and for which mask, and
  the dialog states what is confirmed. Usability evaluation (IEC 62366) open.
- The report model may still write a DIS sentence despite the rule and the adapted template; the output check replaces
  statements per sentence (en/es/de wordings, markup and hyphens normalised, region tables and headings removed) and the
  notice says how many — a paraphrase it does not recognise would pass. It is a backstop (second review, N3).
- A radiologist can acknowledge a region correction without looking (second review, N1); a lesion relabelled Active (Gd+) /
  Black Hole (T1) blocks DIS until corrected (PRB-003 §8.12).
- Until PR #67 is merged, a report request without a segmentation uses the client's lesion counts (no regions, DIS not
  evaluated) (second review, N7).
- A mask save (`_save_segmentation`) still rewrites the whole metadata document from the instance's cache, so it can erase
  a confirmation written meanwhile by another instance; DIS then reads "not evaluated" (fail-safe) and must be confirmed
  again (third review; pre-existing save path).
- Regions of an unconfirmed segmentation stay visible to the radiologist (lesion table, region bars, lesion analysis,
  assistant region tools), caveated "not a DIS assessment"; the report model receives none (review of PR #68, finding 3).
- Stored DIS blocks written before the fix stay in the records (no longer served). Read-only check of production data
  proposed (owner).
- The DIS confirmation is written as metadata only (review of PR #68, finding 5). The RC-047 AI-review confirmation and the
  analysis caches still use `persist()`, which rewrites the unchanged mask object; a client holding the previous storage
  generation may then get the existing stale-write conflict (A-2) on its next save. Pre-existing, not changed here.
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
| D-7 | Merge order with PR #67. *(Corrected 2026-10-24 after the review of PR #68.)* #67's `report_payload_guard.dis_assessment()` drops `evaluation_status`, so after a merge a CONFIRMED DIS would print NOT EVALUATED (not "NOT MET" as first written). The #67 agent was asked to keep the state and print "not evaluated" when it is missing; `test_rc070_r2_e2e_*` fails on a merge that drops it. PR #65: document version rows, RMF §3.6 vs §3.7, and `ROUTE_ACTIONS` must map `POST /segmentation/{id}/review/confirm` to `CLINICAL_SEGMENTATION_CONFIRM`. **Merge instructions (second review, N2):** keep #68's DIS block (NOT EVALUATED when there is no state); run #68's output check on the model's text BEFORE #67's `assemble_draft` (never on the clinician's typed entry); unify the two `segmentation_id` request fields into one; the end-to-end fixture already stubs #67's patient checks — run `test_prb003_*` on the merged tree. |
| D-8 | The word "most" in the information-for-safety text rests on the CC BY-NC-SA control data (as the numbers do). |
| D-9 | Deploy the frontend before the backend (DEPLOYMENT_CHECKLIST.md). |
| D-10 | Region corrections by hand (revised after the second review, N1): one region per lesion; a correction is listed and must be acknowledged in the confirmation, which records it; labels 5 / 6 on a lesion block DIS until corrected (PRB-003 §8.12). |
| D-11 | Label definitions changeable by radiologists and technicians only (403 for viewers and administrators). |
| D-12 | Who confirmed (names, ids, history) shown to radiologists and administrators only; others: role and time; history capped at 50 events (second review, N5). |
| D-13 | Merge with #67 (third review): amend RC-064 to "one of the fixed template variants" (owner approval) and adapt about six fixtures and two contract tests (CAPA-014 route fixture, CAPA-013 report fixture, capa008, brain_report, PRB-003 `report_env`, second-review report fixture); accept the N6 residual (a mask save on another instance can erase a confirmation; DIS fail-safe). |

## 10. Independent review of PR #68 (2026-10-24, at `4c601f2`) — findings and corrections (PENDING owner approval)

Tests written before the corrections fail on `4c601f2`: backend 45 of 47 (`test_prb003_review1_findings.py`), frontend 14 of
17 (`LesionDashboard.prb003.review1.test.tsx`, `SegmentationPanel.prb003.test.tsx`); the passing ones are positive controls —
`records/risk_verification/PRB-003_review1_tests_on_4c601f2_2026-10-24.json`. Negative controls re-run in full after the corrections: 69 mutations, 69 detected (the 37 of the first version with anchors updated, and 32 for the review findings; bound tests green after byte-exact restore) — records/risk_verification/PRB-003_negative_controls_2026-10-24.json. A first full run left 2 undetected (gate's label binding, served cache of a not-evaluated state); one test was added and one made realistic, and the whole set was re-run.

| # | Finding (review of PR #68 at `4c601f2`) | Correction on this branch | Verified by |
|---|---|---|---|
| B1 | **Blocker.** DIS was evaluated on any confirmed mask whatever its labels meant: `compute_dis_criteria` reads ids 1/2/3 as PV/JC/IT, so a confirmed binary "Lesion" mask gave a confirmed NOT MET (false negative) and the default preset (1 = MS Lesion Active, 2 = Chronic) a false MET | DIS only when the labels are the MAGNIMS scheme (ids 1-4 named PV/JC/IT/DWM; no other id or mask value) AND the region classification recorded these lesions (`classified_lesion_footprint_sha256` written by classify-regions equals the current `mask > 0`); reason `regions_not_classified` otherwise. The confirmation is offered only after the classification and binds the mask AND the label scheme. AI drafts: own review (RC-047) + the DIS confirmation. `test_analysis_flow_ci_guard` rewritten (it encoded the defect: DIS evaluated on a binary "MS Lesion" mask); gate docstring corrected. *Deliberate choice, for the reviewer:* the classification is bound to the lesion **footprint**, not to the exact mask hash, so that a radiologist can correct a region label without the correction being thrown away by a re-classification; the correction is covered by the confirmation (bound to the exact mask and labels) and is flagged (`edited_after_classification`) | `test_rc070_r1_*`, `test_rc071_r1_*`, `test_dis_assessment_returns_200`; mutations G10-G14, C6, F5 |
| M2 | #67's payload guard drops `evaluation_status`, so after a merge a confirmed DIS prints NOT EVALUATED (PRB-003 §8.8 and CAPA D-7 described the opposite failure); the report re-derived DIS for whatever id the client put in the DIS block | §8.8 / D-7 corrected; end-to-end test through the real `generate_report` path with only the provider mocked (`test_rc070_r2_e2e_*`) fails if a merge drops the state. The request names its segmentation (`segmentation_id`, authorized in the route); a lesion-analysis or DIS block naming another segmentation is refused (409); without it DIS is not evaluated. Frontend and assistant send it | `test_rc070_r2_*`; mutations R2, R8, A4, F19 |
| M3 | Per-region presence still shown and sent for unconfirmed segmentations | Caveat "Regions not confirmed by a radiologist; not a DIS assessment." on the lesion table and the region bars, in `/lesion-analysis` (`region_status`), in the assistant's region tools (`note`, `regions_note`); the report model receives no region at all without an evaluated DIS. RESIDUAL: the regions stay visible to the reviewer, who needs them to confirm | `test_rc070_r3_*`, `review1` caveat tests; mutations R9, A3, F16 |
| M4 | Templates and format rule 4 still asked the model for DIS; the not-evaluated rule was only in the user message; misleading notice wording | Without an evaluated DIS the template's DIS sections are replaced and every other DIS instruction removed (`dis_not_evaluated_template`, Class C), a safety rule heads the system prompt; every line of the model's text stating DIS (en/es/de) is replaced and counted in the notice; notice reworded ("this draft must not be read as a statement on dissemination in space") | `test_rc070_r4_*`, `test_rc072_r4_*`; mutations R10-R12 |
| M5 | Confirmation not idempotent, not auditable, rewrote the mask (next save 409), ignored durability | First confirmer kept (`already_confirmed`); append-only `clinician_review_history` (confirmed / confirmation_repeated / voided, with user, time, digests, reason); user logged; metadata-only write (`persist_metadata`); 503 and undone when not durable; 409 and cached entry discarded when another session saved a newer mask. PR #65 must map this route to `CLINICAL_SEGMENTATION_CONFIRM` in `ROUTE_ACTIONS` on merge | `test_rc071_r5_*`; mutations C7-C12 |
| m6 | Renaming labels after a confirmation kept it | The confirmation is bound to the label scheme and removed (history: `labels_changed`) when a renamed scheme is saved; `PUT /labels` limited to radiologists and technicians (403 otherwise) | `test_rc071_r1_renaming_*`, `test_rc071_r1_only_clinical_roles_*`; mutations G2b, C13, C14 |
| m7 | Confirm button offered on any expanded segmentation, though the digest is the open mask's | Offered only when the panel's segmentation is the open one ("Open this segmentation to confirm it" otherwise); checked again in the handler | `review1` open-segmentation tests; mutation F14 |
| m8 | Race between the hash and the awaited spacing download; stale `refreshDis` replies | The gate and the rule run on one snapshot of mask and labels; a result is cached only if the stored mask is still the snapshot; every DIS request takes a ticket, older replies are dropped | `test_rc070_r8_*`, `review1` late-reply test; mutations S1, S2, F15 |
| m9 | Information-for-safety text missing on the FLAMeS result and the tool "Segmentation ready" card, inaccurate on SynthSeg / mindGlide structures; "most" rests on CC BY-NC data | Added to both cards; shown for lesion-detection tools only (FLAMeS, LST-AI, mindGlide lesions) everywhere (panel, cards, API state); wording "Automatic **lesion** marking …"; "most" listed as an owner decision | `test_rc072_r9_*`, `review1` notice tests, `SegmentationPanel.prb003.test.tsx` (behavioural, replaces the regex check); mutations N2, F8, F17, F18 |
| m10 | An old frontend crashes on a "not evaluated" block | Deploy the FRONTEND FIRST (DEPLOYMENT_CHECKLIST.md, PR); the lesion panel is wrapped in an error boundary; the new panel shows both answers | `review1` error-boundary check; mutation F20 |
| m11 | `server_dis_assessment` docstring vs re-raised HTTP errors | Docstring states which errors are raised (404 of a missing segmentation; authorization now in the route) and that any other failure gives "not evaluated" | inspection |

Existing tests changed with the corrected contract (stated): the original PRB-003 tests now seed a classification record and
bind the confirmation to the labels; an AI draft's confirmation goes through both reviews; the report tests name the
report's segmentation; `test_brain_report_service.py::test_each_template_uses_correct_system_prompt` (adapted template
without an evaluated DIS, the template as written with one); `test_capa009_*` (the report route now references a
segmentation, authorized with `authorize_mask_specs`, 404 for a stranger); the integration characterisation (reason
`regions_not_classified`; the evaluated contract is pinned by the CI-run `test_analysis_flow_ci_guard`); the source-text
panel check replaced by a behavioural test.

## 11. Second independent review of PR #68 (2026-10-24, at `29abe29`) — findings and corrections (PENDING owner approval)

The second review closed M5 and m6-m11 and found B1, M3 and M4 only partly closed. Every finding was answered on the same branch with the same process: tests written before the corrections — they fail on `29abe29` (backend 46 of 51, frontend 6 of 6; `records/risk_verification/PRB-003_review2_tests_on_29abe29_2026-10-24.json`) — then the corrections, then the negative controls re-run in full: 112 mutations, 112 detected (the 69 of the previous run with anchors updated and 43 for the second review; bound tests green after byte-exact restore) — `records/risk_verification/PRB-003_negative_controls_2026-10-24.json`. A first full run left one mutation undetected (C6: the new per-lesion check also refused lesions that were never classified, so removing the classification check changed nothing visible); the per-lesion check now reads classified lesions only, a test asserts the reason of each refusal (and the card shows the server's reason), the record of the tests on `29abe29` was produced again with the final test files, and the whole set was re-run.

| # | Finding (second review of PR #68 at `29abe29`) | Correction on this branch | Verified by |
|---|---|---|---|
| N1 | **Major.** Label edits after the classification were trusted: `regions_state` checked only that the lesion voxels were unchanged, so — each after a radiologist's confirmation — one connected lesion classified periventricular with half of it painted juxtacortical gave a false MET, a periventricular lesion painted Active (Gd+) a false NOT MET, and a classified mask flattened back to label 1 (for example by "overwrite" in the stale-save dialog) a false NOT MET; `edited_after_classification` was computed but never shown | classify-regions records each lesion's region (`classified_lesion_regions`: first voxel, voxel count, region; 18-connectivity, the classifier's own, RC-030). The gate requires every connected lesion to carry exactly ONE region 1-4 — no lesion split between regions, no Active (Gd+) / Black Hole (T1) label in a mask whose DIS is evaluated (reason `lesion_labels_invalid`, the lesions listed with slice and labels; the confirmation is refused, 409). A lesion whose region differs from the classifier's is a correction by hand: listed (lesion, slice, voxels, classifier's region → current region) in the DIS state, in the card and in the confirm dialog; the radiologist ticks an acknowledgement and the digest of exactly these corrections is sent (409 without it, or for another set); the confirmation records them (`region_corrections`, count, digest) and is bound to them. "Region labels were changed by hand after the region classification" is shown; an evaluated result says it includes acknowledged corrections. Consequences: §8.12 | `test_rc070_n1_*`, `test_rc071_n1_*` (each probe of the review: split lesion, Active (Gd+), flattened mask, relabelled regions), `rc070/rc071 review2` (frontend); mutations W1-W9, WF1-WF7, G12, G14 |
| N2 | Coordination with PR #67: its pushed head still drops the evaluated state (its local `6040905` / `9a8393e` fix it) | Merge instructions written in the PR description and in CAPA-016 D-7: keep #68's DIS block (NOT EVALUATED when there is no state); run #68's output check on the model's text BEFORE #67's `assemble_draft`, so it never touches the clinician's typed entry; unify the two `segmentation_id` request fields into one (#67's is required, #68's derives the DIS state and the lesion table); the end-to-end fixture of `test_prb003_review1_findings.py` now also stubs #67's report-segmentation and patient checks (`authorize_segmentation_id`, `_patient_service`) when they exist, so the same tests drive the merged route | `test_rc070_r2_e2e_*` (fixture); inspection |
| N3 | The output check on the model's text was overstated: it missed "spatial dissemination", "disseminated in space", "dissemination in **space**", "≥2 of the McDonald 2024 topographies", "Spatial distribution meets McDonald criteria", "diseminación espacial", "3 de las 4 regiones características", "räumliche Streuung", "örtliche Dissemination", region table rows, lines that also say "not evaluated", sentences wrapped over two lines — and removed whole paragraph lines | Rewritten: per sentence and per ';' clause, across wrapped lines, on text with markup, accents and hyphens normalised; terms added in en/es/de (dissemination / disseminated in space, spatial dissemination / distribution, D.I.S., McDonald, topographies, typical / characteristic regions or locations, counts of regions, two or more DIS regions named, one DIS region with a presence or a number); a sentence saying "not evaluated" AND claiming something is replaced; region tables and per-region headings are removed; only the statement is replaced, the rest of the paragraph is kept; the notice states the number of statements replaced or removed. **The M4 claim is corrected:** the main controls are the earlier layers — no region is sent to the model, the system prompt opens with the not-evaluated safety rule, no template asks for DIS or for a per-region section (N4); the output check is a BACKSTOP for common wordings and cannot recognise every paraphrase | `test_rc070_n3_*` (every wording of the review's probe and the kept-text cases); mutations W10-W21 |
| N4 | The not-evaluated templates still asked for per-region sections (`general`, `ms_lesion_burden`, `ms_comprehensive`) | Without an evaluated DIS (Class C `dis_not_evaluated_template`): the per-region sections (Periventricular / Cortical-Juxtacortical / Infratentorial / Deep White Matter / Regional Distribution) become ONE "White Matter Lesions" section that says the regions were not confirmed and are not given; the region column of the lesion inventory, "Detailed lesion inventory by anatomical region", "(region)", the "distribution pattern" item, "periventricular confluency" and the McDonald reference of the introduction are removed. The template texts themselves are unchanged | `test_rc070_n4_*` (prints each template in that state); mutations W22, W23 |
| N5 | The confirmation history (names, ids, times) went to every role with patient access, without a size limit; the AI assistant received the confirmer's user name | Names, ids and the history are returned to radiologists and administrators only (`GET /segmentation/{id}`, `/list`, the DIS state); other roles get the confirmation with the role and the time and the history's length (`clinician_review_history_count`); the card then reads "Segmentation confirmed by a radiologist". The history keeps the most recent 50 events (every event is also in the server log). The AI assistant and the report model get the role and the time, never the person | `test_rc071_n5_*`, `test_rc070_n5_*`, `rc071 review2` (frontend); mutations W24-W29, WF8 |
| N6 | `persist_metadata` could overwrite newer metadata written by another instance (whole-document set from the cached copy) | A Firestore field update of `clinician_review` and `clinician_review_history` only; the stored history is read and merged (events of another instance kept); the update carries the read document's update time as precondition — a change in between gives 409 and the cached entry is discarded; a missing document is not durable (503) | `test_rc071_n6_*`; mutations W30-W33 |
| N7 | Removing `segmentation_id` from the client lesion block bypassed the 409 binding | With a report segmentation the lesion table is derived on the server for it (`segmentation_analysis.lesion_table`, compute-only, nothing stored); a client table — with, without or with another `segmentation_id` — never reaches the model; a table that cannot be computed gives 422. Without a report segmentation (possible only until #67, which makes it mandatory, is merged) the client's counts are used without regions and DIS is not evaluated | `test_rc070_n7_*`; mutations W34, W35 |

Existing tests changed with the corrected contract (stated, not hidden): `test_rc070_r1_a_region_corrected_after_classification_keeps_the_classification` (a correction now needs the acknowledgement), `test_rc070_assistant_receives_an_evaluated_assessment_unchanged` (unchanged except the confirmer, given by role), the test helpers (`_classification` / `_classify` record each lesion's region, computed in the test with scipy, independently of the code under test; `_FakeDB` supports field updates with an update-time precondition; `_seed` stores the metadata document as production has it), `test_analysis_flow_ci_guard.py` (the classification record classify-regions writes) and the end-to-end fixture (N2).

## 12. Third independent review of PR #68 (2026-10-24, at `2e20b8a`) — findings and corrections (PENDING owner approval)

The third review found no blocker or major finding in #68 alone: N1-N7 closed, the N1 design cannot be gamed by
splitting or merging lesions, and the evaluated state survives a merge with #67's pushed head `a3f3305`. Two minor
findings were answered with the same process — tests written first (they fail on `2e20b8a`: backend 4 of 4, frontend 2 of 2;
`records/risk_verification/PRB-003_review3_tests_on_2e20b8a_2026-10-24.json`), the correction, the negative controls
re-run in full (119 mutations, 119 detected, bound tests green after byte-exact restore).

| # | Finding (third review of PR #68 at `2e20b8a`) | Correction | Verified by |
|---|---|---|---|
| m-1 | Usability (IEC 62366): the gate numbered lesions in raster order and counted components below the lesion-size floor, while the lesion table numbers them by size and leaves those out — "Lesion 2 … Juxtacortical → Periventricular" in the correction list could be "Lesion 1" in the table | The gate builds the lesion table's entries as `analyze_lesions` does (Class C, not modified): per-label 18-connected components, the same centroid call, size order, the floor from the voxel volume that classify-regions now records (`voxel_volume_mm3`). Every list (corrections, lesions with more than one label, the refusal message, the confirm dialog) names a lesion by the table's number and by the slice its table row opens; a component below the floor is "Small component (N voxels, slice S)"; a lesion with two labels is listed part by part | `test_rc070_m1_*`, `test_rc071_m1_*` (the gate's lists compared with the real `/lesion-analysis` table of the same segmentation), `rc070/rc071 review3` (frontend); mutations W36-W40, WF9, WF10 |
| m-3 | Mutation G14 only broke the import (removing the only statement of an `if` block gave an IndentationError) | G14 now replaces the statement with `pass` and is detected by the classify-regions tests | negative-control record |

**Merge with PR #67 (noted by the third review; coordinated by the owner's agent after #67's final round):** besides the
instructions in §8 item 8, the merge needs (a) RC-064 amended from "the system prompt is the fixed template" to "one of
the fixed template variants" — **owner approval**; (b) about six test fixtures and two contract tests adapted: the
CAPA-014 route fixture, the CAPA-013 report fixture, `test_capa008_*`, `test_brain_report_service.py`, the PRB-003
`report_env` fixture and the second-review report fixture.

**Residual risk noted by the third review (N6):** `SegmentationService._save_segmentation` (any mask save) still rewrites
the whole metadata document from the instance's cached copy, so a save on one instance can erase a confirmation written
meanwhile by `persist_metadata` on another. The failure is safe: without its confirmation the segmentation reads "not
evaluated" and must be confirmed again; no DIS result is shown on a confirmation that is not stored. Not changed here
(pre-existing save path, CAPA-006/A-2).

## 9. Approvals

| Role | Name | Decision | Date |
|---|---|---|---|
| Owner / management representative | *(owner)* | **PENDING owner approval** | — |
| Code review of the Class C change | *(reviewer)* | **PENDING** | — |
