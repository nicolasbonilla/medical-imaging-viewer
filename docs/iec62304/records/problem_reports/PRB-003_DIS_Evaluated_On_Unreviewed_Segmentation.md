# PRB-003 — Dissemination in Space Evaluated on a Segmentation No Clinician Has Confirmed

*Software problem report per SPR-001 (`docs/iec62304/08_Problem_Resolution_Procedure.md` §1), following
PRB-001's layout. SPR-001 says problem reports are GitHub Issues; none has been raised in this repository.
This record is kept under `docs/iec62304/records/problem_reports/`. A GitHub Issue citing this ID is to be
raised by the owner; the agent did not raise one.*

**Problem ID**: PRB-003 (GitHub Issue: not raised — owner action)
**Reporter**: Paper A v0.3 healthy-control addendum (branch `research/paper-a-v0.3`, PR #54, commits `caa47e7`
(pre-registration), `413f5b5` (results), `f3b22cd` (app spec §5 rule 6); record
`docs/research/records/2026-10-24_paper_a_v03c_controls.json`, key `app_dis`); verified in the code and
record drafted by the AI coding agent
**Date**: 2026-10-24
**Version**: `main` @ `70cc5c7`. The DIS route exists since `cf780f4` (2026-02-22); classify-regions has stored a DIS
result for any mask, and the viewer has displayed it from the metadata, since `a637cdf` (2026-03-14)
**Severity**: **Critical — safety-related** (proposed; SPR-001 §2 classes a problem with a safety impact as Critical;
rationale in §5). **PENDING owner approval.**
**Status**: OPEN — DRAFT. Corrected after the independent review of PR #68 (§9), its second review (§10) and its third review (§11). Fix implemented on branch `fix/dis-requires-reviewed-segmentation-prb003` (draft PR #68, not
merged, not deployed); it changes one Class C module (`brain_report_service.py`, DIS block of the report prompt) and
needs a code review before merge (CLAUDE.md). **PENDING owner approval.**

**Description**: The device evaluates the brain-MRI dissemination-in-space (DIS) items of McDonald 2024 and shows
"DIS (Brain MRI): … Criterion Met / Not Met" on **any** loaded segmentation. Nothing checks where the segmentation
comes from or whether a clinician has checked it. An existing review record — the AI-draft review bound to the
SHA-256 of the stored mask (RC-047, `enforce_review_binding`) — is never consulted by DIS. Paper A measured what
this means on healthy brains: with the raw automatic FLAMeS segmentation, the device's own brain-DIS code returned
"DIS met (brain)" in **19 of 100 healthy controls**.

**Steps to Reproduce** (each step reproduced by a test written before the fix, §6):
1. Create a segmentation without AI provenance (`POST /segmentation/create`) and upload any mask with lesions in two
   of periventricular / juxtacortical / infratentorial (`PUT /segmentation/{id}/mask/binary` accepts any bytes of the
   right size — for example a mask produced by another AI program); or open an unreviewed in-browser AI draft; or
   load a server-tool output (`segmentation_type = automatic`, no AI provenance).
2. Run the region classification (`POST /segmentation/{id}/classify-regions`), or label the regions by hand.
3. `GET /segmentation/{id}/dis-assessment`, open the lesion panel, ask the AI assistant (`summarize_dis_items`) or
   draft an AI report.

**Expected Behavior**: DIS is evaluated and shown only for a segmentation a radiologist has confirmed, lesion by
lesion and region by region, for the exact stored mask. Otherwise every path states "not evaluated: requires
clinician review of the segmentation" — never "met" or "not met", no region presence, no topography count.

**Actual Behavior** (`main` @ `70cc5c7`):
- `backend/app/api/routes/segmentation_analysis.py:498-607` (`get_dis_assessment`) loads the mask and calls
  `compute_dis_criteria` (lines 574-576) with no check of `ai_provenance`, `segmentation_type` or any review; a
  cached block is returned whenever `analysis_mask_modified_at` matches (lines 544-550).
- `backend/app/api/routes/segmentation_regions.py:482-491` (`classify_regions`) computes DIS on the reclassified mask
  and stores it in `analysis_data.dis_assessment`; `frontend/src/components/LesionDashboard.tsx:151` displays that
  stored block straight from the metadata, and lines 553-566 render "Criterion Met / Not Met".
- `backend/app/services/brain_report_service.py:583-585` prints `DIS Assessment: MET` / `NOT MET` from whatever block
  the request carries (a missing flag prints NOT MET); `backend/app/api/routes/ai_report.py:205-232` passes the
  client-supplied findings through unverified. The report templates ask the model for a DIS table from lesion counts.
- `backend/app/mcp/ms_clinical_server.py:124` and `:206` hand the DIS route's result to the AI assistant and its report
  tool.
- `backend/app/services/segmentation_service.py:278-293` (`enforce_review_binding`) and
  `backend/app/api/routes/segmentation.py:612-665` (`confirm_ai_review`) implement RC-047, but DIS reads neither; a
  segmentation without AI provenance cannot be confirmed at all (`segmentation.py:641`, 409).

**Evidence (paper A, record `2026-10-24_paper_a_v03c_controls.json`)**:

| What was measured on 100 healthy controls (raw FLAMeS 5-fold ensemble, no selection) | Result |
|---|---|
| Controls with at least one marked lesion | **85 / 100** (95 % CI 76.5–91.4 %); 263 marks, **2.6 per scan** |
| Controls meeting the app's brain-DIS rule (MSMask zones → MAGNIMS contact rule → `compute_dis_criteria`, spinal cord / optic nerve not supplied) | **19 / 100** (95 % CI **11.8–28.1 %**); 22 / 100 with a single fold (fold 0) |
| Controls with a mark in at least one DIS region | 79 / 100 |
| Region of the false marks | periventricular 165 / 263 (**63 %**), deep white matter 61, juxtacortical 33, infratentorial 4 |
| Without the one control with a quality flag (sub-075) | 18 / 99 meet the brain-DIS rule |
| With the high-confidence selection (10 % / 20 % setting) | 2 / 100 and 3 / 100 — not a substitute for review (paper A app spec, rule 6) |

The record names the app code it ran (`ms_region_classifier.py`, `lesion_analysis_service.py`, `lesion_metrics.py`,
with their SHA-256), so these are the device's own functions.

**Limits of the evidence** (stated in the paper and its protocol, and repeated here so the numbers are not over-read):
- **One site, one public dataset** (SibBMS, 100 adults); ages not verified.
- **Template-normalised images** (`Output/Norm`, a 1-mm MNI-type template grid): whether normalisation makes these
  brains easier or harder than clinical scans is unknown; the MSMask zones were applied on that grid.
- **No expert review of the controls**: "lesion-free" is assumed from the dataset, not read by a radiologist.
- **Licence CC BY-NC-SA 3.0** (the paper also states CC BY 3.0; the stricter one is applied): research use only. The
  numbers are not used in any product text until the licence is clarified (owner decision); the information-for-safety
  text added by this fix carries no number for that reason.
- One segmenter (FLAMeS) and one configuration; it does not extend to thick-slice studies, other segmenters or children.
- The device's DIS rule is decision support, not a diagnosis; a clinician would also see the images. The hazard is
  the anchoring effect of a "Criterion Met" badge or a report sentence computed from unchecked marks.

**Safety Impact Assessment**:
- [x] Could contribute to a hazardous situation — **HAZ-008** (DIS evaluated incorrectly: "met" on a healthy brain or
  on false marks), **HAZ-005** (region assignment of unchecked marks feeds the DIS count; 63 % of false marks are
  periventricular), **HAZ-003** (the AI report and the assistant restate the unverified DIS result).
- [x] Affects a Class C software item — `lesion_analysis_service.py` (its DIS output is consumed unguarded; not
  modified), `ms_region_classifier.py` (its regions feed the count; not modified), `brain_report_service.py`
  (modified by the fix).
- [ ] Requires regulatory notification (EU MDR Article 87) — no: the device is not CE-marked and not in clinical use.

---

## 1. Triage (SPR-001 §3.1)

- **Reproducible**: yes. Paper A ran the device's functions on 100 controls; on `main` the defect is reproduced by
  the failing-first tests of this report (§6, 39 of 41 backend and 12 of 12 frontend tests fail on `70cc5c7`).
- **Severity**: proposed Critical, safety-related (§5).
- **Assigned to**: *(to be assigned — Class C change; owner decision)*.

## 2. How an unreviewed automatic mask can reach DIS in production today

Production configuration was **not** read (no access to production was used); the statements below come from the
repository's configuration and code at `70cc5c7`.

| Path | Enabled in production? | Reaches DIS unreviewed? |
|---|---|---|
| Mask uploaded through the API into a segmentation without provenance (`POST /create` then `PUT /{id}/mask/binary`) — e.g. another AI program's output, a script, a future import | **Yes**: any authenticated user with access to the patient can do it; the route checks size and grid only | **Yes** — and it is indistinguishable from manual work (no `segmentation_type`, no provenance) |
| Viewer "Upload segmentation" button | No: disabled, "Importing a segmentation is not available yet" (`ViewerApp.tsx:487`) | — |
| Server tools (LST-AI, FLAMeS GPU worker, SynthSeg, mindGlide) | Believed off: `*_ENABLED` default `False` (`config.py:182-196`); `cloudbuild.yaml` sets only `GOOGLE_CLOUD_PROJECT` but uses `--update-env-vars`, so a flag set out of band would persist — **not verified** | **Yes when on**: stored with `segmentation_type = automatic` and **no** AI provenance (`tool_runner_service.py:1037`), so they could never be confirmed (`segmentation.py:641` → 409) |
| In-browser FLAMeS AI draft | Believed off: `VITE_ENABLE_BROWSER_FLAMES` absent from the tracked `frontend/.env.production` (default false, `features.ts:66`) | **Yes when on**: a saved, unreviewed draft is evaluated like any other mask (RC-047 not consulted) |
| Hand-drawn segmentation | Yes | Evaluated without any record of who checked the lesions and regions (the device cannot tell it from an upload) |
| Stored DIS blocks written before the fix (classify-regions) | Yes, if any exist | Displayed from the metadata without any route (`LesionDashboard.tsx:151`) |
| AI report / AI assistant | Report: yes (`ANTHROPIC_API_KEY` dependent); assistant: `MCP_ENABLED` default false | Yes: they restate the DIS route's result, and the report route trusts a client-supplied block |

Whether production holds segmentations made from automatic sources (for example research uploads) was not checked:
it needs a read-only query of production data, which only the owner may authorise.

## 3. Root Cause (SPR-001 §3.2)

1. **The DIS requirement never had a precondition on its input.** REQ-SAFE-015 / RC-015 cover the display of the
   per-region detail; no requirement says on which segmentation DIS may be computed. The DIS route was written when
   every segmentation was hand-drawn (2026-02/03).
2. **AI segmentation and its review were added later without a consumer.** CP-FLAMES-BROWSER-001 added the RC-047
   review (bound to the mask) to stop an AI draft being *mistaken for manual work*, but no downstream computation was
   required to use it; server-tool outputs got no provenance at all, so they could never be confirmed.
3. **A derived conclusion was stored and displayed outside the route.** classify-regions persisted the DIS result in
   the metadata and the viewer showed it from there — a second path with no possible gate (same family as CAPA-013:
   a conclusion field kept under a decision-support framing).
4. **The report path trusted client data** and turned a missing flag into "NOT MET".

## 4. Impact Analysis (SPR-001 §3.3)

Every path that computes, stores, forwards or displays DIS, and what the fix does:

| Path | File (base) | After the fix |
|---|---|---|
| DIS route | `segmentation_analysis.py:498-607` | Gated (`assess_dis`): evaluated only when a confirmation is bound to the current mask; otherwise the explicit "not evaluated" state; nothing computed or cached |
| Stored DIS cache | `segmentation_analysis.py:544-550` | Served only if it is an evaluated block and the gate passes now |
| classify-regions | `segmentation_regions.py:482-491` | Stores the gated state (reclassifying changes the mask and voids an earlier confirmation) |
| Metadata responses (`GET /{id}`, `/list`) | `segmentation.py` | Never carry `analysis_data.dis_assessment` (stored record untouched) |
| Viewer lesion panel | `LesionDashboard.tsx:151, 553-700` | Reads only the gated route; "not evaluated" card with reason, origin, confirm action and notice; met / not met, five-topography panel and badges only for an evaluated result, with the confirming radiologist named |
| AI report | `ai_report.py`, `brain_report_service.py:583-593` | DIS re-derived on the server for the segmentation named (authorized, compute-only); NOT EVALUATED + rule against deriving DIS in the prompt; fixed notice appended in en/es/de; a request whose only "measurement" is an unevaluated DIS is refused (RC-034) |
| AI assistant | `ms_clinical_server.py:124, 206` | Only an evaluated block passes (also against an older backend); instructions: report "not evaluated", never derive DIS from counts or regions |
| Exports | FHIR (`fhir.py`), DICOM-SEG (`export_dicom_seg`), CSV (`handleExportCSV`) | Carry no DIS — not affected. The PDF of a report is the report text, covered above |
| Longitudinal comparison | — | Carries no DIS (dissemination in time handled by CAPA-013) — not affected |

**Requirements affected**: REQ-SAFE-015 (display) unchanged; new **REQ-SAFE-038** (DIS only on a confirmed
segmentation, every path), **REQ-SAFE-039** (confirmation of a segmentation without AI provenance), **REQ-SAFE-040**
(information for safety on automatic marking). REQ-SAFE-030 (RC-047) is reused, not changed.
**Risk controls**: new **RC-070, RC-071, RC-072** (RMF-001 v1.15 DRAFT). Numbers chosen after the open PRs: #67
uses RC-064..066 and HAZ-016, #65 RC-067..069; no HAZ number is added.
**Labelling**: IFU-001 / CER-001 describe the DIS output; they must state that DIS needs a radiologist's confirmation
of the segmentation (owner action, not changed here).
**Previously released versions**: every version since `cf780f4` (2026-02-22).

## 5. Severity Rationale (SPR-001 §2)

SPR-001 §2 has three levels; a problem with a safety impact is **Critical**. This one can contribute to HAZ-008 (a
"DIS met" badge or report sentence for a healthy brain) and to HAZ-003. Proposed: **Critical, safety-related**. What
bears on probability and urgency, not on the class: the device is not in clinical use; the AI tools are believed
off in production; DIS is decision support next to the images. What keeps it safety-related: the upload path is
open today, a hand-drawn segmentation has no record of who checked it, and in early MS or a clinically isolated
syndrome a single false periventricular mark can decide the brain-DIS item.

**CAPA linkage (SPR-001 §4.1)**: Critical severity and a Class C item → a CAPA is required. Proposed: **CAPA-016**
(new; the root cause — a downstream computation not bound to the review that exists — differs from CAPA-006/013).
Record: `records/capa/CAPA-016_DIS_Requires_Confirmed_Segmentation.md`. **Owner decision — PENDING.**

## 6. Resolution (SPR-001 §4) — implemented on branch, NOT merged

Branch `fix/dis-requires-reviewed-segmentation-prb003` (draft PR #68), from `main` @ `70cc5c7`:
- **RC-070** — `backend/app/services/dis_review_gate.py` (new) decides; `segmentation_analysis.assess_dis` (DIS route and
  report route), `segmentation_regions.classify_regions`, `segmentation.get_segmentation` / `list_segmentations`,
  `ai_report.server_dis_assessment` / `dis_notice`, `brain_report_service._build_findings_prompt` (Class C, DIS block
  only), `mcp/ms_clinical_server.only_evaluated_dis` + instructions, `LesionDashboard.tsx`, `types/lesion.ts`.
  `lesion_analysis_service.compute_dis_criteria` (Class C) is **unchanged** and runs only after the gate.
- **RC-071** — `ClinicianReview` (schemas), `POST /segmentation/{id}/review/confirm` (radiologist, exact stored mask,
  authenticated user and time recorded), `enforce_review_binding` removes it on any mask change.
- **RC-072** — the healthy-brain notice (paper A wording A, no numbers) in en/es/de: AI draft banner, segmentation
  panel for server-tool output, the "not evaluated" card and API state of an automatic segmentation, report notice,
  report prompt and assistant instructions.
- *Corrected after the independent review of PR #68 (§9):* DIS also requires MAGNIMS regions classified for the current
  lesions; the confirmation is given for every segmentation (an AI draft after its own review), only after the
  classification, bound to mask AND label scheme, idempotent, with an append-only history, written as metadata only and
  refused when not durable; the report is bound to its own segmentation, gets no region and no DIS instruction without an
  evaluated DIS, and any DIS line the model writes is replaced; regions of unconfirmed segmentations are caveated; the
  notice is shown for lesion-detection tools only (also on the FLAMeS and tool result cards).
- *Corrected after the second review of PR #68 (§10):* every connected lesion carries exactly one region 1-4; a region
  changed by hand after the classification is listed and acknowledged in the confirmation (recorded, bound); who
  confirmed is shown to radiologists and administrators only (the assistant and the report model get the role and the
  time), the history is capped at 50 events; the confirmation writes only its own fields of the metadata document, with
  an update-time precondition; the report's lesion table is derived on the server; the output check on the model's text
  works per sentence and is a backstop; the not-evaluated templates ask for no per-region section.

**Verification**:

| ID | Check | Result |
|---|---|---|
| V1 | Tests written first: `backend/tests/unit/test_prb003_dis_requires_confirmed_segmentation.py` (41), `frontend/src/components/LesionDashboard.prb003.test.tsx` (12) | On `70cc5c7`: backend 39 fail, 2 pass (positive controls: an evaluated block still reaches the prompt and the assistant unchanged); frontend 12 / 12 fail — `records/risk_verification/PRB-003_tests_on_base_2026-10-24.json` |
| V2 | Same tests on the fix | 41 / 41 and 12 / 12 pass |
| V3 | Negative controls `scripts/safety/prb003_negative_controls.py` (one mutation at a time, anchors asserted unique, bytes restored) | **37 mutations, 37 detected** (backend 24: gate, cache, metadata, classify-regions, confirmation, report, assistant, notice; frontend 13: display, confirmation, notices, unsaved changes); bound tests green after restore — `records/risk_verification/PRB-003_negative_controls_2026-10-24.json` |
| V4 | Regression | Whole backend test tree, offline (PRB-002), Firestore/GCS/PACS tests deselected as in CI: 1759 passed, 5 xfailed, 1 failed — `test_webauthn_credentials_endpoint_exists` (`webauthn` not installed locally; known, unrelated); frontend suite 343 passed / 3 skipped; `tsc --noEmit` clean; production build passes; every anchor of the existing negative-control scripts still unique (236 checked) |
| V5 | Existing tests changed to the new contract (stated, not hidden) | `test_analysis_flow_ci_guard.py::test_dis_assessment_returns_200` (confirmed segmentation evaluated, unconfirmed "not evaluated"); `test_brain_report_service.py::test_build_findings_prompt_dis_assessment` (block marked evaluated); `test_capa009_*` route registry (new route, object authorization); integration characterization `test_dis_assessment_contract` (requires Firestore, deselected in CI) |
| V6 | Independent review of PR #68 at `4c601f2` (2026-10-24) | Findings and corrections in §9; review-finding tests fail on `4c601f2` (backend 45 of 47, frontend 14 of 17: `records/risk_verification/PRB-003_review1_tests_on_4c601f2_2026-10-24.json`) and pass on the corrections; whole backend tree (offline, PRB-002; Firestore/GCS/PACS deselected as in CI) 1807 passed, 5 xfailed, 1 failed (webauthn not installed locally, known); frontend 359 passed, 3 skipped; tsc clean; production build passes |
| V8 | Second independent review of PR #68 at `29abe29` (2026-10-24) | Findings and corrections in §10; the second-review tests fail on `29abe29` (backend 46 of 51, frontend 6 of 6: `records/risk_verification/PRB-003_review2_tests_on_29abe29_2026-10-24.json`) and pass on the corrections (51 backend, 6 frontend); negative controls 112 mutations, 112 detected; whole backend tree (offline, PRB-002; Firestore/GCS/PACS deselected as in CI) 1858 passed, 5 xfailed, 1 failed (webauthn not installed locally, known); frontend 365 passed, 3 skipped; tsc clean; production build passes; anchors of every negative-control script still unique (353 checked) |
| V9 | Third independent review of PR #68 at `2e20b8a` (2026-10-24) | Findings and corrections in §11; m-1 tests fail on `2e20b8a` (backend 4 of 4, frontend 2 of 2: `records/risk_verification/PRB-003_review3_tests_on_2e20b8a_2026-10-24.json`) and pass on the correction; negative controls 119 mutations, 119 detected; backend tree 1862 passed, 5 xfailed, 1 failed (`webauthn` not installed locally, known); frontend 367 passed, 3 skipped; `tsc --noEmit` clean; production build passes; 360 negative-control anchors unique |
| V7 | Review and approval | Code review of the Class C change and owner approval — **PENDING** |

## 7. Closure (SPR-001 §4, step 6) — not applicable yet

Resolution description, verification evidence, commit SHA of the merged fix, affected and fixed versions: *to be
completed when the fix is reviewed, approved and merged.*

## 9. Independent review of PR #68 (2026-10-24, at `4c601f2`) — findings and corrections

The review said: do not merge as-is; the core idea is sound. Every finding was answered on the same branch with the same
process — tests written before the corrections (they fail on `4c601f2`:
`records/risk_verification/PRB-003_review1_tests_on_4c601f2_2026-10-24.json`), the corrections, negative controls re-run in
full. Negative controls re-run in full after the corrections: 69 mutations, 69 detected (the 37 of the first version with anchors updated, and 32 for the review findings; bound tests green after byte-exact restore) — records/risk_verification/PRB-003_negative_controls_2026-10-24.json. A first full run left 2 undetected (gate's label binding, served cache of a not-evaluated state); one test was added and one made realistic, and the whole set was re-run.

| # | Finding (review of PR #68 at `4c601f2`) | Correction on this branch | Verified by |
|---|---|---|---|
| B1 | **Blocker.** DIS was evaluated on any confirmed mask whatever its labels meant: `compute_dis_criteria` reads ids 1/2/3 as PV/JC/IT, so a confirmed binary "Lesion" mask gave a confirmed NOT MET (false negative) and the default preset (1 = MS Lesion Active, 2 = Chronic) a false MET | DIS only when the labels are the MAGNIMS scheme (ids 1-4 named PV/JC/IT/DWM; no other id or mask value) AND the region classification recorded these lesions (`classified_lesion_footprint_sha256` written by classify-regions equals the current `mask > 0`); reason `regions_not_classified` otherwise. The confirmation is offered only after the classification and binds the mask AND the label scheme. AI drafts: own review (RC-047) + the DIS confirmation. `test_analysis_flow_ci_guard` rewritten (it encoded the defect: DIS evaluated on a binary "MS Lesion" mask); gate docstring corrected. *Deliberate choice, for the reviewer:* the classification is bound to the lesion **footprint**, not to the exact mask hash, so that a radiologist can correct a region label without the correction being thrown away by a re-classification; the correction is covered by the confirmation (bound to the exact mask and labels) and is flagged (`edited_after_classification`) — *revised by the second review (N1, §10): each lesion must carry one region, and a correction must be acknowledged in the confirmation* | `test_rc070_r1_*`, `test_rc071_r1_*`, `test_dis_assessment_returns_200`; mutations G10-G14, C6, F5 |
| M2 | #67's payload guard drops `evaluation_status`, so after a merge a confirmed DIS prints NOT EVALUATED (PRB-003 §8.8 and CAPA D-7 described the opposite failure); the report re-derived DIS for whatever id the client put in the DIS block | §8.8 / D-7 corrected; end-to-end test through the real `generate_report` path with only the provider mocked (`test_rc070_r2_e2e_*`) fails if a merge drops the state. The request names its segmentation (`segmentation_id`, authorized in the route); a lesion-analysis or DIS block naming another segmentation is refused (409); without it DIS is not evaluated. Frontend and assistant send it | `test_rc070_r2_*`; mutations R2, R8, A4, F19 |
| M3 | Per-region presence still shown and sent for unconfirmed segmentations | Caveat "Regions not confirmed by a radiologist; not a DIS assessment." on the lesion table and the region bars, in `/lesion-analysis` (`region_status`), in the assistant's region tools (`note`, `regions_note`); the report model receives no region at all without an evaluated DIS. RESIDUAL: the regions stay visible to the reviewer, who needs them to confirm | `test_rc070_r3_*`, `review1` caveat tests; mutations R9, A3, F16 |
| M4 | Templates and format rule 4 still asked the model for DIS; the not-evaluated rule was only in the user message; misleading notice wording | Without an evaluated DIS the template's DIS sections are replaced and every other DIS instruction removed (`dis_not_evaluated_template`, Class C), a safety rule heads the system prompt; the model's text is checked and DIS statements replaced and counted in the notice — *corrected by the second review (N3, §10): the first check was line-based and missed many wordings; the main controls are the earlier layers (no region sent, the system safety rule, no DIS template section) and the output check is a backstop*; notice reworded ("this draft must not be read as a statement on dissemination in space") | `test_rc070_r4_*`, `test_rc072_r4_*`; mutations R10-R12 |
| M5 | Confirmation not idempotent, not auditable, rewrote the mask (next save 409), ignored durability | First confirmer kept (`already_confirmed`); append-only `clinician_review_history` (confirmed / confirmation_repeated / voided, with user, time, digests, reason); user logged; metadata-only write (`persist_metadata`); 503 and undone when not durable; 409 and cached entry discarded when another session saved a newer mask. PR #65 must map this route to `CLINICAL_SEGMENTATION_CONFIRM` in `ROUTE_ACTIONS` on merge | `test_rc071_r5_*`; mutations C7-C12 |
| m6 | Renaming labels after a confirmation kept it | The confirmation is bound to the label scheme and removed (history: `labels_changed`) when a renamed scheme is saved; `PUT /labels` limited to radiologists and technicians (403 otherwise) | `test_rc071_r1_renaming_*`, `test_rc071_r1_only_clinical_roles_*`; mutations G2b, C13, C14 |
| m7 | Confirm button offered on any expanded segmentation, though the digest is the open mask's | Offered only when the panel's segmentation is the open one ("Open this segmentation to confirm it" otherwise); checked again in the handler | `review1` open-segmentation tests; mutation F14 |
| m8 | Race between the hash and the awaited spacing download; stale `refreshDis` replies | The gate and the rule run on one snapshot of mask and labels; a result is cached only if the stored mask is still the snapshot; every DIS request takes a ticket, older replies are dropped | `test_rc070_r8_*`, `review1` late-reply test; mutations S1, S2, F15 |
| m9 | Information-for-safety text missing on the FLAMeS result and the tool "Segmentation ready" card, inaccurate on SynthSeg / mindGlide structures; "most" rests on CC BY-NC data | Added to both cards; shown for lesion-detection tools only (FLAMeS, LST-AI, mindGlide lesions) everywhere (panel, cards, API state); wording "Automatic **lesion** marking …"; "most" listed as an owner decision | `test_rc072_r9_*`, `review1` notice tests, `SegmentationPanel.prb003.test.tsx` (behavioural, replaces the regex check); mutations N2, F8, F17, F18 |
| m10 | An old frontend crashes on a "not evaluated" block | Deploy the FRONTEND FIRST (DEPLOYMENT_CHECKLIST.md, PR); the lesion panel is wrapped in an error boundary; the new panel shows both answers | `review1` error-boundary check; mutation F20 |
| m11 | `server_dis_assessment` docstring vs re-raised HTTP errors | Docstring states which errors are raised (404 of a missing segmentation; authorization now in the route) and that any other failure gives "not evaluated" | inspection |

## 10. Second independent review of PR #68 (2026-10-24, at `29abe29`) — findings and corrections

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

## 11. Third independent review of PR #68 (2026-10-24, at `2e20b8a`) — findings and corrections

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

## 8. Owner decisions pending

1. Severity (Critical, proposed) and CAPA linkage (CAPA-016, proposed).
2. Approve that **every** segmentation — also hand-drawn ones — needs a radiologist's confirmation before DIS is shown
   (the device cannot tell a hand-drawn mask from an uploaded one); and that only the radiologist role may confirm.
3. Add `backend/app/services/dis_review_gate.py` to the Class C module list in CLAUDE.md (risk-control module for
   HAZ-008; the agent does not edit CLAUDE.md).
4. Read-only check of production data: do stored segmentations carry `analysis_data.dis_assessment` blocks, and do
   any come from automatic sources? (No longer displayed after the fix, but relevant to past exposure.)
5. Confirm the production values of `LSTAI/SYNTHSEG/MINDGLIDE/FLAMES_ENABLED` and `VITE_ENABLE_BROWSER_FLAMES`.
6. SibBMS licence: may the healthy-control numbers be quoted in a product text (today: no number is shown)?
7. IFU-001 / CER-001: state that DIS requires a confirmed segmentation.
8. Merge order with PR #67 (CAPA-014). *(Corrected 2026-10-24 after the review of PR #68: the first draft described the
   opposite failure.)* #67's `report_payload_guard.dis_assessment()` keeps only `dis_met` and drops `evaluation_status`,
   so after a merge a **confirmed** DIS would reach the prompt as NOT EVALUATED (checked on the merged tree by the
   reviewer). The #67 agent has been asked to keep the evaluated / not-evaluated state and to print "not evaluated" when it
   is missing. The end-to-end test `test_rc070_r2_e2e_a_confirmed_dis_reaches_the_model_through_the_real_report_service` (real
   `generate_report`, only the model provider mocked) fails on a merge that drops it. *Merge instructions (second review,
   N2):* (a) keep #68's DIS block — NOT EVALUATED when there is no state; (b) run #68's output check
   (`scrub_unevaluated_dis`) on the model's text BEFORE #67's `assemble_draft`, so it never touches the clinician's typed
   entry; (c) unify the two `segmentation_id` request fields into one (required as in #67; used by #68 to derive the DIS
   state and the lesion table); (d) the end-to-end fixture already stubs #67's report-segmentation and patient checks when
   they exist — run `test_prb003_*` on the merged tree. #67's pushed head still drops the state (its local `6040905` /
   `9a8393e` fix it).
9. PR #65 (CAPA-015): its `ROUTE_ACTIONS` must map `POST /segmentation/{id}/review/confirm` to
   `CLINICAL_SEGMENTATION_CONFIRM` on merge.
10. Deploy the frontend **before** the backend (DEPLOYMENT_CHECKLIST.md): a frontend older than PRB-003 cannot render the
    "not evaluated" state.
11. The word "most" in the information-for-safety text rests on the CC BY-NC-SA control data (as the numbers do).
12. *(Rewritten after the second review, N1, §10.)* Region corrections by hand. The classification now records each
    lesion's region, and the gate enforces: (a) every connected lesion carries exactly ONE region 1-4 — a lesion partly
    repainted, or relabelled Active (Gd+) / Black Hole (T1), blocks DIS (reason `lesion_labels_invalid`, the lesions
    listed) until it is corrected or the classification is run again; consequence: on a mask whose DIS is to be evaluated
    a radiologist cannot mark a lesion's Gd+ / black-hole status with labels 5 / 6 (owner decision: accept, or record the
    lesion type in its own layer later); (b) a radiologist may still correct the classifier's region of a whole lesion:
    the correction is listed (lesion, slice, voxels, classifier's region → current region) in the card and in the confirm
    dialog, must be ticked, and is recorded in the confirmation with its digest; DIS then rests on the radiologist's
    region and the evaluated result says it includes acknowledged corrections; (c) a mask flattened to one label (for
    example "overwrite" in the stale-save dialog) shows every changed lesion as a correction — it can no longer pass
    silently, but a radiologist could still tick it without looking (residual, human); (d) running the classification
    again replaces the corrections by the classifier's regions and voids the confirmation. Accept (b) — correction with an
    explicit acknowledgement — rather than forcing a new classification.
13. *(Second review, N5.)* Who confirmed is shown to radiologists and administrators only; technicians and viewers see
    "confirmed by a radiologist" and the time; the AI assistant and the report model never get the name. The history on
    the segmentation keeps the most recent 50 events (the server log keeps every event). Approve these roles.
14. *(Second review, N7.)* With a report segmentation the lesion table is derived on the server; until #67 is merged a
    report without a segmentation still uses the client's lesion counts (without regions, DIS not evaluated).
15. *(Third review of PR #68.)* Approve the RC-064 amendment needed by the merge with #67 ("one of the fixed template
    variants"), and accept the N6 residual: a mask save on one instance can erase a confirmation written meanwhile on
    another — DIS then reads "not evaluated" (safe) and must be confirmed again.

---

**Prepared by**: AI coding agent (Claude Code) from paper A, 2026-10-24.
**Approval**: **PENDING owner approval** — severity, CAPA linkage, the fix and the decisions in §8. No approval is
recorded here.
