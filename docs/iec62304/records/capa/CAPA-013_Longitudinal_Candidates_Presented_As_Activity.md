# CAPA-013 — Longitudinal Comparison: Unconfirmed Change Candidates Presented as Disease Activity

**CAPA ID**: CAPA-013
**Date Opened**: 2026-10-22 (DRAFT — opening, severity and actions **PENDING owner approval**)
**Source**: RMF-OBS-001 (RMF-001 §3.5, PR #62), from the paper C pilot (PR #60, branch `research/paper-c-pilot` @ `0501bd1`: `docs/research/paper-c/RESULTS.md` §0, §2b; record `docs/research/records/2026-10-21_paper_c_pilot.json`, keys `arms.A4.fixed.B_all` / `B_app_sub`, SHA-256 `3cbf0b53…af27b`). Every finding below was re-checked in the code of PR #62 (`qms/capa012-and-problem-reports` @ `2018277`) on 2026-10-22 and reproduced by tests written before the fix (§5).
**Severity**: **CRITICAL, safety-related** (proposed, as RMF-OBS-001; QP-002 §5: patient safety risk / SPR-001 §2: safety impact; raised from Major on 2026-10-23 together with RMF-OBS-001 after the independent review of PR #62). The first draft proposed Major because the device is not in clinical use, the counts were labelled candidates, and harm needs a reader to accept a false candidate; those facts lower the probability of harm, not the class.
**Owner**: *(to be assigned — a person; the AI coding agent cannot own a CAPA)*
**Status**: DRAFT. Interim controls implemented on branch `fix/longitudinal-activity-display-capa013` (draft PR #63, based on PR #62; **merge after #52, #51, #53, #59, #49 and #62**). Nothing merged, nothing deployed. **Owner approval: PENDING owner approval.** Effectiveness is not verified.
**Identifiers**: RC-060, RC-061, RC-062 and REQ-SAFE-037 are the identifiers PR #62 reserved for exactly these controls (proposed there, NOT IMPLEMENTED). They are implemented here under those identifiers rather than renumbered, so each control keeps one identifier. The next free identifiers after PR #62 were checked on every open branch on 2026-10-22 (RC-063, REQ-SAFE-038, REQ-FUNC-100, CAPA-013: unused; RC-054..058, REQ-SAFE-034..036, REQ-FUNC-098/099 are reserved by PR #59) — none is needed. Document versions follow PR #62's: **SRS 1.10, RMF 1.12, TM 1.9** (drafts).
**CAPA linkage**: PR #62 proposed these controls as CAPA-008 actions CA-8.11–CA-8.13. CAPA-008 addresses a different problem (assistant layer, clinical-rule fidelity; its approved actions were implemented in PR #46); a dedicated CAPA is proposed instead (decision D-2).
**Procedure**: QP-002 (`docs/qms/QP-002_CAPA_Procedure.md`) · SPR-001
**Related**: HAZ-007 (HAZ-003 for reports) · REQ-SAFE-037 · REQ-FUNC-054/055/055a · REQ-SAFE-024 · RC-014b · RC-035 · RC-029 · RC-033 · RC-047 · RMF-OBS-001 · CAPA-008

---

## 1. Findings (code of PR #62, `2018277`)

Measured (paper C, arm A4, pre-registered secondary arm; open_ms, 20 patients, FLAMeS 5-fold, **expert change masks**): the device's rule (`longitudinal_tracking_service.compare_timepoints`: new >= 3 mm, enlarged > 20 %) proposed **>= 1 false new/enlarging candidate in 20/20 patients** (CI 0.83–1.00), **8.9 per patient** (5.8–12.6); after its own FLAIR-subtraction check 19/20 and 5.4 per patient (3.45–7.7). MSLesSeg (approximate truth): 25/25, 8.24 per patient. No stable patients were studied.

### Finding 1 — The view turned unconfirmed candidates into an activity statement

`LongitudinalCompare.tsx` (lines 452–488): whenever `activity_candidate` or `dit_candidate` was true — i.e. in essentially every comparison — a purple banner **"Active-disease CANDIDATE"** (or "Dissemination-in-time CANDIDATE") with "MAGNIMS 2021: any new or enlarging T2 lesion marks activity; a new lesion supports DIT", and a badge **"NEDA-3 MRI (T2-arm): activity CANDIDATE"**. The flags came from `longitudinal_tracking_service.py:316–317` and travelled unchanged in the `/segmentation/longitudinal/compare` response (`segmentation_analysis.py:562–777`).

### Finding 2 — Review was stated, not recorded

The caveat asked a reader to "adjudicate each candidate", `adjudication_required` was always true, but no route, field or button recorded a reader's decision; nothing distinguished a reviewed candidate from an unreviewed one.

### Finding 3 — The subtraction check was worded as a confirmation

"FLAIR subtraction: {c} of {n} new candidates **confirmed** brighter at follow-up" (line 422) and, per lesion, "✓sub — FLAIR brighter at follow-up … **supports a genuine new lesion**" (line 664) — while subtraction-checked candidates were still false in 19/20 patients.

### Finding 4 — The safety texts were English in every language

Of the 40 `longitudinal.*` keys the view used, **24 had no entry** in `es.json` / `de.json` (banner, NEDA badge, subtraction texts, region and SEL texts — the English default was shown); three texts were hard-coded ("Select study...", "Select segmentation...", "No lesion segmentations found"), dates were formatted `en-US`, table cells read "+new"/"gone"/"TP1"/"TP2", and the backend's English `caveat` took precedence over the translated one (line 390).

### Finding 5 — No check of the acquisition

`compare_longitudinal` read no scanner or protocol information. No acquisition record exists for any image: the PACS import (`dicomweb_service.py`) stored none and `study_service_firestore.extract_dicom_metadata` is never called. In paper C the two MSLesSeg patients with the strongest false candidates are pairs where a scanner change is plausible (not shown).

### Finding 6 — Every consumer of the longitudinal result (searched 2026-10-22)

| Consumer | What it received (PR #62) |
|---|---|
| The view (`LongitudinalCompare.tsx`, mounted by `ControlPanel.tsx`) | Findings 1–4 |
| AI assistant (`mcp/ms_clinical_server.py` `compare_longitudinal`, `generate_ms_report`) | the raw response, incl. `activity_candidate` / `dit_candidate` |
| Report draft (`/ai/report/generate` → `brain_report_service.py`, Class C) | `status_counts` labelled "candidate"; but the `ms_longitudinal` template asked for a "DISEASE ACTIVITY CLASSIFICATION — **Active**: new enhancing or new/enlarging T2 lesions", "Activity classification (active/not active)", "evidence of ongoing inflammatory activity", NEDA-3 — an instruction to a language model, not a deterministic filter |
| Report panel (`AIReportPanel.tsx`) | sends no longitudinal data (checked) |
| Exports (DICOM-SEG, FHIR DiagnosticReport) | carry no longitudinal content (checked) |
| `ai_segmentation.py` "longitudinal volumetry" | brain volumes, not lesion change — out of scope |
| RC-035 test / CAPA-008 negative control C6 | bind the service flag `activity_candidate` (kept, see §8) |

## 2. Root cause

1. The candidate framing (RC-014b) qualified the counts but left the derived conclusion in place: a field named `activity_candidate`, a banner and a NEDA badge — information that a reader must disregard, not a gate.
2. The false-candidate rate of the rule was unknown until paper C; no requirement asked for it to be stated.
3. "Review" was specified as a sentence in a caveat, never as a recorded decision (contrast RC-035 for CVS/PRL readings, RC-047 for AI drafts).
4. No test checked that the view's texts exist in every shipped language; the component carried English defaults, which hid the missing entries.
5. Acquisition harmonisation between visits was never specified, and no import path recorded the acquisition.

## 3. Corrections and corrective actions (implemented on the branch — PENDING owner approval)

| ID | Action | Control | Where |
|---|---|---|---|
| CA-13.1 | One presentation step for every consumer: `activity_candidate`, `dit_candidate` and the "clinically significant" count names are removed from the comparison response; new and enlarging results are `change_candidates` (new >= 3 mm, enlarging, total, confirmed, rejected, awaiting review). The counting rule, matching and segmentation are unchanged | RC-060 (b) | `services/longitudinal_candidate_safety.py` (`present_comparison`), `api/routes/segmentation_analysis.py` |
| CA-13.2 | Reader decisions: each reviewable candidate gets a stable key; `POST /segmentation/longitudinal/review` records "confirmed" / "rejected" — object authorization first (RC-029), **radiologists only** (403, as RC-047), **bound to the SHA-256 of both stored masks** (409 when either changed), stored on the follow-up segmentation with the authenticated reader (`reviewed_by`, `reviewed_by_id`) and the time; decisions for other masks are discarded. `reader_confirmed_activity` — the only field carrying the word — exists only when >= 1 candidate is confirmed for the masks compared, and applies MAGNIMS 2021 (>= 1) to the confirmed candidates only | RC-060 (a), (c) | same + `LongitudinalResultPanel.tsx` (Confirm / Reject per candidate) |
| CA-13.3 | Consumers: the assistant's backend client drops the legacy flags at any depth (also against an older backend); the review route is not on its compute-only list; assistant instructions updated. Report prompt: unconfirmed candidates passed as such, the template no longer asks for an Active/Not active classification, and **no reader decision ever reaches a report draft** (a decision in a report request cannot be verified; it is removed — §10, blocker 1); a fixed notice in the report language (en/es/de), written by code after the model, ends every draft that received a comparison | RC-060 (b) | `mcp/_backend.py`, `mcp/ms_clinical_server.py`, `services/brain_report_service.py` (Class C, §6), `api/routes/ai_report.py` |
| CA-13.4 | Measured false-candidate rate: versioned asset `services/assets/longitudinal_false_candidate_evidence.json` (v1.0.0) with its source record, commit and SHA-256; bound to the rule parameters in force (3 mm, 20 %, IoU 0.3, 0.5 SD) — a different rule, or an unreadable / incomplete asset, gives no rate and the view says so. Served with every comparison; rendered by the view and the report notice; no figure in a component | RC-061 | `longitudinal_candidate_safety.py` (`load_false_candidate_evidence`), asset, `LongitudinalResultPanel.tsx`, `ai_report.py` |
| CA-13.5 | Wording and language: subtraction = "brighter at follow-up — a signal, not a confirmation"; every text of the view (pickers, caveat, candidates, rate, abstention, table, legend, SEL) in en/es/de, no English default in the component, dates and numbers in the reader's locale; the backend's English caveat is no longer shown | RC-061 | `LongitudinalCompare.tsx`, `LongitudinalResultPanel.tsx`, `i18n/locales/{en,es,de}.json` |
| CA-13.6 | Abstention: the acquisition of the two visits is compared — manufacturer, scanner model, field strength, 2D/3D, slice thickness (required), repetition / echo / inversion time and spacing between slices (when recorded), voxel size of the two image files. Differs, or cannot be established → no candidate, count, burden change, region breakdown or decision; the reason and the metadata compared are stated; the overlay stays for visual review. The PACS import now stores the acquisition record of each series (from its DICOM header) | RC-062 | `longitudinal_candidate_safety.py` (`compare_acquisitions`, `acquisition_from_dicom`, `read_source_acquisition`), `segmentation_analysis.py`, `dicomweb_service.py`, `LongitudinalResultPanel.tsx` |
| CA-13.7 | Verification: tests written first (§5), negative controls, manifest RC-060/061/062 → implemented on the branch | — | §5 |
| CA-13.8 | Corrections after the independent review of PR #63 (2026-10-23, §10): no reader decision in report drafts; no quantity of either visit when the comparison abstains; visit 2 a different, later visit (refused otherwise; unknown dates abstain); SEL search gated the same way; assistant rate from the asset; false share stated as measured (46 %); read errors of stored decisions reported; append-only decision history | RC-060, RC-061, RC-062 | §10 |

### What the clinician sees

| | Before (PR #62) | After (this branch) |
|---|---|---|
| Typical comparison | "Active-disease CANDIDATE — 3 new (≥3 mm) + 1 enlarging. MAGNIMS 2021: any new or enlarging T2 lesion marks activity…", "NEDA-3 MRI (T2-arm): activity CANDIDATE" | "4 unconfirmed change candidates (3 new ≥3 mm, 1 enlarging), to be reviewed one by one by a radiologist. Awaiting review: 4 · confirmed: 0 · rejected: 0. The software makes no statement about the course of the disease from these candidates…" + "In a public test with expert-marked change (20 patients, FLAMeS 5-fold ensemble), this rule proposed on average 8.9 false new or enlarging candidates per patient (95% CI 5.8–12.6), 46% of all the candidates it proposed; 5.4 after the subtraction check. No stable patients were studied. Source: Paper C pilot, arm A4 (PR #60), 2026-10-22." |
| After a radiologist confirms one | — (nothing recorded) | "MRI activity confirmed by a radiologist: 1 new and 0 enlarging lesion(s), confirmed by dr_x (date). MAGNIMS 2021: … This is the radiologist's confirmation, not a software result" — in the view only; a report draft never states it (§10) |
| Subtraction | "confirmed brighter at follow-up", "✓sub — supports a genuine new lesion" | "brighter at follow-up — a signal, not a confirmation", "↑sub — a signal only, it does not confirm a new lesion" |
| Spanish / German reader | the above in English | the above in Spanish / German |
| Different scanner, or acquisition unknown | the same counts | "No automatic change candidates for this pair — the acquisition differs between the two visits: Manufacturer: visit 1 SIEMENS → visit 2 Philips" (or "could not be established. Missing: Field strength (T) (visit 2)"), the metadata compared, "Compare the images visually with the overlay." No count, no lesion load or count of either visit, no SEL search (§10). Same visit or visit 2 not later: refused; unknown visit dates: the same abstention |

**Consequence today:** images uploaded as NIfTI (all research datasets now in the app) carry no acquisition record, so every comparison between them **abstains** — the view shows the overlay and the explanation, no automatic counts. Only series imported from a PACS after this change carry the record. This is the fail-closed behaviour REQ-SAFE-037 (e) asks for; whether it is acceptable until another capture path exists is decision D-3.

## 4. Preventive actions (proposed — PENDING owner approval)

| ID | Action |
|---|---|
| PA-13.1 | Locale-completeness test for every clinical view (keys used in the component present and non-empty in en/es/de; safety texts not copied from English), as done here for the longitudinal view |
| PA-13.2 | Design rule for the SDP review checklist: a field or text carrying a clinical conclusion (activity, dissemination, "criteria met", NEDA) is produced only from reader-confirmed data, and its absence when unconfirmed is test-bound |
| PA-13.3 | Acquisition capture on every import path: NIfTI upload with its BIDS sidecar (dcm2niix JSON: Manufacturer, ManufacturersModelName, MagneticFieldStrength, MRAcquisitionType, SliceThickness, RepetitionTime, EchoTime, InversionTime); `extract_dicom_metadata` wired or removed. Until then uploaded-NIfTI comparisons abstain |
| PA-13.4 | Append-only history of reader decisions — implemented 2026-10-23 after the review (CA-13.8) |

## 5. Verification (by the author — not independent; owner approval PENDING)

**Tests written before the fix, failing on PR #62.** `backend/tests/unit/test_capa013_longitudinal_candidates.py` (41 cases, `test_rc060_*`, `test_rc061_*`, `test_rc062_*`) and `frontend/src/components/LongitudinalCompare.capa013.test.tsx` (13 cases, `rc060 …`, `rc061 …`, `rc062 …`; drives the real panel: study and segmentation pickers, Compare button, mocked API). Re-run against the PR #62 source files by `scripts/safety/capa013_tests_on_base.py` → record `docs/iec62304/records/risk_verification/CAPA-013_tests_on_base_2026-10-22.json`: backend **40 of 41 cases fail** (reasons recorded: the comparison still returns `activity_candidate`; the review route does not exist (404); no evidence asset or acquisition check; the report template still asks for an activity class), frontend **13 of 13 fail** ("Active-disease CANDIDATE" rendered; no Confirm/Reject; no measured rate; 144 missing locale entries; "confirmed brighter at follow-up"; on an abstained response the PR #62 panel renders nothing). The one case passing on the base, `test_rc060_assistant_cannot_record_a_decision`, is a regression guard (the review route must never join the assistant's compute-only list).

**After the fix.** Both files pass (41/41, 13/13). Whole backend test tree (`pytest tests`): 1611 passed, 20 skipped, 5 xfailed, **1 failed** — `tests/integration/test_auth_endpoints.py::TestWebAuthnEndpoints::test_webauthn_credentials_endpoint_exists`, because `webauthn` is not installed in the local environment; it fails identically on the PR #62 code. Full frontend suite (vitest `--pool=threads`): 36 files, 283 tests — 280 passed, 3 skipped (FLAMeS tests that need local research data), 0 failed. Type check (`tsc --noEmit`): clean. Production build (`vite build`): passes. Existing tests updated with the change: `test_rc029_*` and `test_capa009_*` (the new route classified as `authorize_mask_specs`), `test_brain_report_service.py::test_build_findings_prompt_longitudinal` (new labels).

**Negative controls.** `scripts/safety/capa013_negative_controls.py` — one mutation at a time in the real source, each anchor asserted unique, bytes restored: **45 mutations, 45 detected** (RC-060: B1–B15, F1–F5; RC-061: E1–E6, F6–F12, F15; RC-062: A1–A9, F13–F14), each re-introducing one defect (several exactly as found: the legacy banner, the English backend caveat, "confirmed brighter", "supports a genuine new lesion", a missing Spanish text, no abstention); bound tests green after byte-exact restore. Record: `docs/iec62304/records/risk_verification/CAPA-013_negative_controls_2026-10-22.json`. The first full run (45 mutations) found one gap: F12 — the German rate text left partly in English — was not detected, because the language test compared whole strings only. The test now also refuses any English three-word phrase of the view's English texts in the Spanish and German texts and in the rendered Spanish and German panel (one proper name allowed: "MSMask MNI152 atlas"); F15 (Spanish caveat partly in English) was added and the frontend mutations were re-executed with the strengthened test (`--only F`). A later full-tree run showed that one new backend test used `asyncio.run`, which cleared the session's event loop and made 100 later async tests fail; it is now a native async test, and the backend mutations were re-executed against the final test file. The record holds each mutation's execution time and the SHA-256 of the tests it ran.

**Not verified.** No test in a real browser (jsdom only); no run against Firestore or a real PACS import (the acquisition lookup and the import field are unit- and source-tested); no usability evaluation (IEC 62366); effectiveness on clinical use not measurable (not in use).

## 6. Class C module modified — justification (CLAUDE.md)

`backend/app/services/brain_report_service.py` (Class C) was modified, in two places only: the `ms_longitudinal` template and the longitudinal block of `_build_findings_prompt`. **Strictly necessary:** the instruction to classify the disease as "Active / Not active" from the interval counts lives in that template; no upstream filter can remove an instruction from the system prompt, and the findings block is where unconfirmed candidates were labelled as "New-lesion count". In the `ms_longitudinal` template the items that drew a conclusion from the candidates or from data the device does not measure were removed with the activity class: "evidence of ongoing inflammatory activity", the annualised new-lesion rate, the improving/stable/worsening trajectory class, treatment-efficacy assessment, PIRA and NEDA-3 (cf. CAPA-008 CA-8.9, still open for the other templates). The disclaimer (RC-006), the other templates and the generation path are unchanged; the deterministic notice is added outside the module (`ai_report.py`). This change needs the code review CLAUDE.md requires for Class C modules (decision D-5). No other Class C module was touched (`lesion_analysis_service.py`, `ms_region_classifier.py`, `nifti_utils.py`, `dicom_utils.py`, … unchanged; `longitudinal_tracking_service.py` — the counting rule — unchanged).

## 7. Residual risk and open items

1. The candidates are still mostly false (about 9 per patient in the measurement); the controls change how they are presented and recorded, not how many there are. The calibrated subtraction threshold (paper C A4) is not a control yet (RMF-001 §7.2 item 4).
2. The rate was measured on highly active patients only; the false-activity rate in stable patients is unknown (MSSEG-2 needed).
3. The report body is written by a language model: the prompt no longer asks for an activity class from candidates, carries no reader decision, and a fixed notice is appended, but the body is not filtered deterministically. A radiologist's confirmation therefore never appears in a report draft (only in the view).
4. A decision is bound to the exact candidate (position and volumes) and to both masks; a re-computation that moves a candidate (e.g. a different registration outcome) voids the decision — safe, possibly annoying.
5. The decision history is append-only (CA-13.8); it is stored in the follow-up segmentation's record, not in a separate audit store.
6. Abstention in practice for uploaded NIfTI (D-3, PA-13.3); the acquisition record of PACS imports is read from the first instance of the series.
7. `activity_candidate` is still computed inside `longitudinal_tracking_service.py` (RC-035 test, CAPA-008 negative control C6) but never leaves the backend; REQ-SAFE-024's last sentence now applies to confirmed candidates (REQ-SAFE-037).
8. HAZ-007 determination stays as proposed in PR #62 (UNDETERMINED) until the stable-patient measurement.

## 10. Independent review of PR #63 (2026-10-23) — findings and corrections (PENDING owner approval)

An independent review of the first version of this PR (head `ad144ba`) asked for two blockers and six further corrections before any merge. All are corrected on the same branch; each has a behavioural test written first and failing on `ad144ba` (record `records/risk_verification/CAPA-013_review1_tests_on_pr63_2026-10-23.json`: backend 15 of 52 cases fail, frontend 7 of 18) and new negative controls.

| # | Finding (verified) | Correction | Tests (`test_*` / vitest) | Mutations |
|---|---|---|---|---|
| Blocker 1 | A forged confirmation reached the AI report: `/ai/report/generate` passed the client's `findings.longitudinal` through and the prompt builder accepted a client-sent `reader_confirmed_activity` — a TECHNICIAN with no stored decision obtained "confirmed by radiologist dr.house … indicates activity" in the prompt. **This defect was introduced by the first version of this PR** (PR #62 never read the block) | Report requests are client data: the route removes every reader decision and decision count (`drop_unverifiable_decisions`), and the builder (Class C) never states a reader decision — "the radiologist's decisions are recorded in the application and are not part of this draft". The confirmed statement exists only in the view, built server-side from stored, role-checked decisions bound to both masks. The report notice no longer states a confirmed count | `rc060_forged_confirmation_never_reaches_the_report` (real route, real prompt builder, model stand-in), `rc060_report_route_drops_a_confirmation_sent_by_the_client`, `rc060_report_prompt_never_states_a_reader_confirmation_from_its_input` | B16, B17 |
| Blocker 2 | When counts were withheld, the view still showed "load 2.0 → 5.5 mL" and "lesions 10 → 18", and the report prompt received both loads while the template asked to compare them | Abstention withholds every quantity: no lesion load, lesion count or change of either visit in the response (`ABSTAINED_NULL_FIELDS`), the view or the report prompt; the template asks for the load only "if supplied" | `rc062_comparison_abstains_without_counts`, `rc062_report_prompt_for_an_abstained_comparison_has_no_counts`, `rc062 when counts are withheld no lesion load or lesion count…` | A6, A10, A11, F16 |
| 3 | The template list still advertised "NEDA-3 evaluation" | Description rewritten | `rc060_template_list_offers_no_neda` | E9 |
| 4 | Visit 2 was not checked to be a different, later visit | Same segmentation, same file or same study → refused (400); visit 2 not later → refused (400); dates unknown or equal → abstention with the reason. The view disables Compare and says why | `rc062_two_different_visits_in_order_are_required`, `rc062_unknown_visit_dates_abstain`, `rc062 the second visit must be a different, later visit`, `rc062 an unknown visit order abstains and says so` | A12–A14, A16, F18, F19, F22 |
| 5 | The slowly-expanding-lesion search still gave counts when the candidates were withheld | Same gates (visit check, acquisition check) in `/longitudinal/sel`; the view does not offer it when the comparison abstains | `rc062_slowly_expanding_lesion_search_is_withheld_with_the_counts`, `rc062 the slowly-expanding-lesion search is not offered…` | A15, F17 |
| 6 | The assistant's instructions hard-coded "about 9" | Built from the versioned asset (`assistant_rate_sentence()`); no figure in the assistant's code | `rc061_assistant_rate_is_read_from_the_asset` | E7 |
| 7 | "Most candidates may be false" overstated: 178 of 390 candidates (46 %) were false in the source record (`arms.A4.describe`, re-checked) | The rate is stated as measured: "8.9 false new or enlarging candidates per patient, 46 % of all the candidates it proposed" (view en/es/de, API caveat, report notice, assistant) | `rc061_false_share_is_stated_precisely`, `rc061 the measured false-candidate rate…` | E8, F21 |
| 8 | A read error of the stored decisions showed them silently as "awaiting review"; a new decision overwrote the previous one | A read error is reported (`decisions_unavailable`; counts null; no decision can be recorded; red message in the view; caveat); the review route refuses (500) rather than overwrite unreadable decisions. Every decision is appended to an append-only `history` (reader, time, both mask hashes), kept across mask changes | `rc060_unreadable_decisions_are_reported_not_hidden`, `rc060 decisions that could not be read…`, `rc060_decision_history_is_kept` | B18–B20, F20 |

Verification after the corrections: CAPA-013 files 52/52 and 18/18; whole backend tree 1622 passed, 1 failed (the local-only WebAuthn test, as on PR #62); frontend 288 tests, 285 passed, 3 skipped, 0 failed; type check clean; production build passes. Negative controls (full re-run 2026-10-23, all mutations against the final tests): **66 mutations, 66 detected** (B12 retired; B16–B20, E7–E9, A10–A16, F16–F22 added for the review findings). On PR #62 the tests now fail 50 of 52 (backend) and 18 of 18 (frontend) — `CAPA-013_tests_on_base_2026-10-22.json` (re-run 2026-10-23 with the final tests).

## 8. Owner decisions (PENDING owner approval)

| ID | Decision |
|---|---|
| D-1 | Severity: Critical, safety-related (proposed; raised from Major on 2026-10-23 with RMF-OBS-001) |
| D-2 | Linkage: CAPA-013 instead of CAPA-008 CA-8.11–8.13 (PR #62) |
| D-3 | Accept that comparisons of uploaded NIfTI images abstain until an acquisition capture path exists (PA-13.3) |
| D-4 | Wording of the interim texts in en/es/de (radiologist review of the translations) |
| D-5 | Code review of the Class C change (`brain_report_service.py`, §6) by a person other than the author |
| D-6 | Merge order: after #52, #51, #53, #59, #49, #62 |

## 9. Approvals

| Role | Name | Decision | Date |
|---|---|---|---|
| CAPA owner | *(to be assigned)* | PENDING owner approval | — |
| Owner / Project Lead | — | PENDING owner approval | — |
| Code review (Class C, D-5) | — | PENDING owner approval | — |
| Effectiveness check | — | PENDING owner approval | — |

*Drafted by the AI coding agent (development tool, SDP-001 §5.1.4). No approval is recorded in this document; approvals are to be recorded by the owner (CAPA-012).*
