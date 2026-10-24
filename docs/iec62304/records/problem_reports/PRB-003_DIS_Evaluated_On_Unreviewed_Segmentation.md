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
**Status**: OPEN — DRAFT. Fix implemented on branch `fix/dis-requires-reviewed-segmentation-prb003` (draft PR, not
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

Branch `fix/dis-requires-reviewed-segmentation-prb003` (draft PR), from `main` @ `70cc5c7`:
- **RC-070** — `backend/app/services/dis_review_gate.py` (new) decides; `segmentation_analysis.assess_dis` (DIS route and
  report route), `segmentation_regions.classify_regions`, `segmentation.get_segmentation` / `list_segmentations`,
  `ai_report.server_dis_assessment` / `dis_notice`, `brain_report_service._build_findings_prompt` (Class C, DIS block
  only), `mcp/ms_clinical_server.only_evaluated_dis` + instructions, `LesionDashboard.tsx`, `types/lesion.ts`.
  `lesion_analysis_service.compute_dis_criteria` (Class C) is **unchanged** and runs only after the gate.
- **RC-071** — `ClinicianReview` (schemas), `POST /segmentation/{id}/review/confirm` (radiologist, exact stored mask,
  authenticated user and time recorded, 409 for an AI draft), `enforce_review_binding` removes it on any mask change.
- **RC-072** — the healthy-brain notice (paper A wording A, no numbers) in en/es/de: AI draft banner, segmentation
  panel for server-tool output, the "not evaluated" card and API state of an automatic segmentation, report notice,
  report prompt and assistant instructions.

**Verification**:

| ID | Check | Result |
|---|---|---|
| V1 | Tests written first: `backend/tests/unit/test_prb003_dis_requires_confirmed_segmentation.py` (41), `frontend/src/components/LesionDashboard.prb003.test.tsx` (12) | On `70cc5c7`: backend 39 fail, 2 pass (positive controls: an evaluated block still reaches the prompt and the assistant unchanged); frontend 12 / 12 fail — `records/risk_verification/PRB-003_tests_on_base_2026-10-24.json` |
| V2 | Same tests on the fix | 41 / 41 and 12 / 12 pass |
| V3 | Negative controls `scripts/safety/prb003_negative_controls.py` (one mutation at a time, anchors asserted unique, bytes restored) | **37 mutations, 37 detected** (backend 24: gate, cache, metadata, classify-regions, confirmation, report, assistant, notice; frontend 13: display, confirmation, notices, unsaved changes); bound tests green after restore — `records/risk_verification/PRB-003_negative_controls_2026-10-24.json` |
| V4 | Regression | Whole backend test tree, offline (PRB-002), Firestore/GCS/PACS tests deselected as in CI: 1759 passed, 5 xfailed, 1 failed — `test_webauthn_credentials_endpoint_exists` (`webauthn` not installed locally; known, unrelated); frontend suite 343 passed / 3 skipped; `tsc --noEmit` clean; production build passes; every anchor of the existing negative-control scripts still unique (236 checked) |
| V5 | Existing tests changed to the new contract (stated, not hidden) | `test_analysis_flow_ci_guard.py::test_dis_assessment_returns_200` (confirmed segmentation evaluated, unconfirmed "not evaluated"); `test_brain_report_service.py::test_build_findings_prompt_dis_assessment` (block marked evaluated); `test_capa009_*` route registry (new route, object authorization); integration characterization `test_dis_assessment_contract` (requires Firestore, deselected in CI) |
| V6 | Review and approval | Code review of the Class C change and owner approval — **PENDING** |

## 7. Closure (SPR-001 §4, step 6) — not applicable yet

Resolution description, verification evidence, commit SHA of the merged fix, affected and fixed versions: *to be
completed when the fix is reviewed, approved and merged.*

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
8. Merge order with PR #67 (CAPA-014): it rewrites the report payload (`report_payload_guard.dis_assessment` keeps only
   `dis_met`, forced to a boolean). Whichever merges second must carry `evaluation_status` through that guard, or a
   "not evaluated" state would print "NOT MET" — a test of this PR (`test_rc070_report_prompt_never_states_met_*`) will
   fail if the merge drops it.

---

**Prepared by**: AI coding agent (Claude Code) from paper A, 2026-10-24.
**Approval**: **PENDING owner approval** — severity, CAPA linkage, the fix and the decisions in §8. No approval is
recorded here.
