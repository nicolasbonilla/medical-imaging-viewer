# CAPA-014 — AI Report Draft: Patient Data Sent to the Model Provider Without De-identification

**CAPA ID**: CAPA-014
**Date Opened**: 2026-10-24 (DRAFT — opening, severity and actions PENDING owner approval)
**Source**: code reading of `main` @ `70cc5c7` on 2026-10-24 (orchestrating session), verified the same day by behavioural tests written before the fix (§5). Earlier records of the same gap: RCV-SUMMARY 2026-07-18 (RC-007′ "No de-identification routine exists"), CAPA-001 §2.3 and action CA-4 (still PENDING), CAPA-008 finding 4 and CA-8.5. **Redesigned the same day** after an independent adversarial review of the first version (draft PR #67 @ `4bfdd7e`, §11).
**Severity**: **CRITICAL** (proposed; QP-002 §5: regulatory non-compliance — special-category health data sent to a third-party processor without de-identification and without a recorded data-processing agreement; REQ-SEC-007 not met). Not a direct patient-injury defect.
**Owner**: *(to be assigned — a person; the AI coding agent cannot own a CAPA)*
**Status**: DRAFT. Corrections implemented on branch `fix/ai-report-deidentification-capa014` (draft PR #67, based on `main` @ `70cc5c7`). Nothing merged, nothing deployed. **Owner approval: PENDING.** Effectiveness not verified.
**Identifiers**: RC-064, RC-065, RC-066; REQ-SEC-021, REQ-SEC-022, REQ-SEC-023; HAZ-016 (new). Document versions **SRS 1.11, RMF 1.13, TM 1.10, DD-001 1.2** (drafts). The parallel CAPA-015 PR reserves RC-067..RC-069, REQ-SEC-024..026, SRS 1.12, RMF 1.14, TM 1.11; if it also adds a hazard, HAZ-016 must be reconciled at merge (D-8).
**Procedure**: QP-002 (`docs/qms/QP-002_CAPA_Procedure.md`) · SPR-001
**Related**: HAZ-016 (HAZ-003, HAZ-013) · REQ-SEC-007 · REQ-IF-004 · RC-006 · RC-033 · RC-034 · RC-036 · CAPA-001 CA-4 · CAPA-008 · CAPA-009 · PRB-002

---

## 1. Findings (code of `main` @ `70cc5c7`)

### Finding 1 — The service header claimed a de-identification that did not exist

`backend/app/services/brain_report_service.py` (Class C), module header lines 13–16, stated that patient data was de-identified before sending to Claude API and that no names, IDs or dates were sent (claim withdrawn). The class docstring of the same file (line 443) said the opposite: "this service does NOT de-identify" (CAPA-008 CA-8.5 had withdrawn the claim there and in the route description, but not in the module header). The frontend API client, the report viewer footer shown on every draft and its printed page, the README, TD-001, AIA-001, ISMS-001, CSA-001, DD-001, the master compliance document and the technical documentation carried the same kind of statement (all withdrawn, §3 CA-14.4). No de-identification code existed anywhere in `backend/app/`.

### Finding 2 — Everything the clinician typed reached the provider verbatim

`POST /api/v1/ai/report/generate` (`ai_report.py:195`) passed `findings` and `volumetry` to `BrainReportService.generate_report`, which built the user prompt with `_build_findings_prompt` and called `client.messages.create(model=CLAUDE_MODEL, system=<template>, messages=[<prompt>])` — model `claude-sonnet-4-5-20250929` (`config.py:218`). The prompt carried the clinical indication, technique and additional observations as typed, the **exact age**, the sex (any value other than "M" shown as Female), every string of the structured findings (segmentation label names, anomaly types and locations, region and zone names, volumetry structure names), and — through fields printed without a number format — any value placed where a count was expected. Reproduced on `70cc5c7` with a mocked provider client (record `CAPA-014_tests_on_base_2026-10-24.json`).

### Finding 3 — The route did not know whose identifiers they were

The request referenced no patient or stored object, so no server-side record could be used; the burden was put on the caller ("callers must not send direct identifiers"), a rule a clinician typing free text cannot follow and no code enforced. The AI assistant's MS report tool sent its findings the same way.

### Finding 4 — No record of what was sent

The route logged template and language only (no payload — correct), but nothing recorded that any check ran.

### Finding 5 — Probably live

`ANTHROPIC_API_KEY` is one of the variables required in production (`DEPLOYMENT_CHECKLIST.md` line 18). Whether drafts were generated in production before this fix, and with what text, cannot be established from the repository (owner action D-4).

## 2. Root cause

1. A privacy control was written as a description of intent (header, client comment, viewer footer, CSA-001), the same defect class as CAPA-001: REQ-SEC-007 carried the verification "Test + Inspection" with no test.
2. The report route was designed as stateless text generation that forwards whatever the client sends; no allow-list defined what may leave the application.
3. CAPA-008 corrected the wording in two places and moved the burden to the caller instead of implementing CAPA-001 CA-4.
4. *(Added after the review, §11.)* The first correction treated the problem as text cleaning: a protective measure on free text, which cannot be complete (ISO 14971 §7.1 requires inherent safety by design first).

## 3. Corrections and corrective actions (implemented on the branch — PENDING owner approval)

| ID | Action | Control | Where |
|---|---|---|---|
| CA-14.1 | **Structured payload only (inherent safety by design).** `provider_payload` builds the only payload the provider receives: measurements as numbers (any other value dropped — also in the fields printed without a number format), labels only from the device's fixed vocabulary (`MAGNIMS_REGIONS`, `REGION_NAMES`, `STRUCTURE_NAMES`, size classes, abnormality types — single source of truth, imported from the producing services) with any other label replaced by "[unlisted label]", sex only M or F, age only as a 5-year band ("90 or older" from 90). Free-text fields (clinical indication, technique, observations) and unknown fields are counted and left out. The prompt builder prints no free text even if called directly. The system prompt is the fixed template | RC-064 | `services/report_payload_guard.py` (new, part of the Class C report item), `brain_report_service.py` |
| CA-14.2 | **The clinician's text stays in the application.** The route adds the typed indication, technique and observations to the draft after the model returns, right after the RC-006 disclaimer, under a heading in the report language ("Clinician's entry (added in the application; not sent to the AI service)"); the model is told that this text is added by the application | RC-064, RC-066 | `ai_report.py` (`clinician_entry`, `with_clinician_entry`), `brain_report_service.py` (`CLINICIAN_TEXT_INSTRUCTION`) |
| CA-14.3 | **Fail closed and a detection-only tripwire.** Segmentation required (400 — not 422, which the panel reads as "no measurements"), authorized for the caller (`authorize_segmentation_id`, 404 as RC-036), patient record readable and complete (503). Before the call, `find_identifiers` checks the final prompt — after NFKC, removal of format characters (soft hyphen, zero-width characters, BOM), look-alike and accent mapping — for the patient's own name (alone, inside a longer word, German ae/oe/ue spellings, and for names that are also words of the device's fixed text, next to the other name), record number (up to 3 separator characters between characters), birth date (numeric, month-name en/es/de, Roman; day and month or year after a birth word), phone (with and without country code and trunk 0), e-mail, contact name, city and street, and for generic e-mail, dated text, "+" phones, long or grouped numbers, ID-like tokens and titled names. Any finding: 503, nothing sent. It never edits text, never reports the device's own words alone (derived from the templates and from the builder's output on synthetic payloads), refuses texts over 400 000 characters and uses only bounded or anchored patterns | RC-065 | `report_payload_guard.py`, `brain_report_service.py` (`assert_prompt_carries_no_identifier`, `fixed_prompt_words`), `ai_report.py`, `security/resource_access.py`, `AIReportPanel.tsx`, `mcp/ms_clinical_server.py` |
| CA-14.4 | **Records and true statements.** The log records `privacy_check="passed"` and the withheld counts (free-text fields, unlisted labels, unknown fields), never the payload, prompt or typed text. Panel note directly above the draft button and report viewer footer, en/es/de: only the measurements, sex and a 5-year age range are sent — no names, dates of birth, record numbers or free text; the typed text is added in the application. False claims corrected in the service header, API client, viewer footer (old `hipaaNote` key removed), README (badge removed), TD-001, AIA-001, ISMS-001, CSA-001, DD-001, master compliance document, technical documentation and its PDF generator; a repository test fails on any new claim (historical records, tests and negative-control scripts excepted). Data categories recorded (§6) | RC-066 | `brain_report_service.py`, `AIReportPanel.tsx`, `ReportViewerModal.tsx`, `i18n/locales/{en,es,de}.json`, `aiReport.ts`, documents listed, §6 |
| CA-14.5 | Verification: tests written first (twice: before the first version and before the redesign, §5), negative controls, manifest RC-064..066 → implemented on the branch | — | §5 |
| CA-14.6 | The scrubbing module of the first version (`report_deidentification.py`) and its tests are removed; no unused complex code stays in the Class C item | — | §11 |

### What the clinician sees

| | Before (`70cc5c7`) | After (this branch) |
|---|---|---|
| Report panel | Template, language, three text fields, "Generate Report" | The same, plus one line directly above the button: "Sent to the AI service (Anthropic): only the measurements, sex and a 5-year age range — no names, dates of birth, record numbers or free text. Your text in the fields above is added to the draft here, in the application; it is not sent to the AI service." (es/de translated) |
| The draft | Written by the model from everything, including the typed text | Written by the model from the measurements; the typed text appears under "Clinician's entry (added in the application; not sent to the AI service)" right after the disclaimer; the model writes "See the clinician's entry…" under indication and technique |
| Footer of every draft (screen and print) | "HIPAA Compliant — Only de-identified clinical findings were used … No protected health information (PHI) was transmitted to external services." (false) | "AI draft written by Anthropic's model from the device's measurements only, with sex and a 5-year age range. No names, dates of birth, record numbers or free text were sent. The clinician's entry was added in the application." (es/de translated) |
| No open segmentation | "No measurements are available…" (422) | Unchanged |
| Record unreadable, or the check finds something | Draft generated | Refused; the panel shows its generic error, the API says "The request was not sent to the AI service (…). Nothing was sent." (PA-14.4) |

## 4. Preventive actions (proposed — PENDING owner approval)

| ID | Action |
|---|---|
| PA-14.1 | SDP review-checklist rule: any code that sends data to an external service sends an allow-listed structured payload, and has a test that plants markers in every input field and inspects the exact outbound payload |
| PA-14.2 | Claims check extended beyond the AI path: compliance badges and statements ("HIPAA", "GDPR compliant") only with a linked, test-bound control (login page badge, session components, `firebase.py` comment are out of this CAPA's scope) |
| PA-14.3 | Independent re-review of the redesign (adversarial, as the first review) before merge |
| PA-14.4 | Show the server's reason for a refused draft in the panel (UI change, owner decision) |
| PA-14.5 | REQ-SEC-007 also names Vertex AI: check what the AI segmentation path sends (image headers such as NIfTI `descrip`, DICOM tags) — separate CAPA if needed |
| PA-14.6 | The AI assistant's own model provider receives the other tools' responses with identifier keys dropped (RC-033) but free text not scrubbed; apply the structured-payload principle there too |

## 5. Verification (by the author — not independent; owner approval PENDING)

**Tests written first.** First version: `test_capa014_report_deidentification.py` and the panel test, committed before the fix (`2964063`), failed on `70cc5c7`; that version and its records are kept in git history (`4bfdd7e`). Redesign: `backend/tests/unit/test_capa014_report_provider_payload.py` and the rewritten `frontend/src/components/AIReportPanel.capa014.test.tsx`, committed before the redesign (`f975368`): on the PR #67 head `4bfdd7e` the backend file failed 116 of its 163 cases and the frontend file 6 of 10. After the redesign the backend file was completed with cases that only one control catches (a name made of two device words, a particle surname, an Austrian short phone, a "+" phone, the payload itself) and the timing test was given a deadline thread; the claims pattern was widened to the phrasings found in the documents. No assertion was weakened.

**Existing tests adapted.** `test_brain_report_service.py`: identifiers passed; the clinical-indication case now asserts that the indication is NOT in the prompt and the model is told it is added by the application; the age case asserts the band. `test_capa008_assistant_read_only.py`, `test_capa013_longitudinal_candidates.py`: report requests send `segmentation_id` with a readable record (assertions unchanged). `test_capa009_object_authorization_everywhere.py`: route classified `call:authorize_segmentation_id`, 404 probe.

### 5.1 Results

| Check | Result |
|---|---|
| Redesign tests on the PR #67 head `4bfdd7e` (final files) | backend **129 of 176 fail**, frontend **6 of 10 fail**; the cases that pass there are the fail-closed controls the first version already had, age bands it already sent, and collision names that do not occur in the prompt (record `CAPA-014_review1_tests_on_pr67_2026-10-24.json`) |
| Redesign tests on `main` `70cc5c7` (final files) | backend **129 of 176 fail**, frontend **10 of 10 fail**; the cases that pass there are regression guards (fixed system prompt, measurement lines, collision names — `main` rewrote nothing) (record `CAPA-014_tests_on_base_2026-10-24.json`) |
| Redesign tests on the branch | backend 176/176, frontend 10/10 |
| Negative controls (executed 2026-10-24 14:55) | **52 mutations, 52 detected** (RC-064: P1–P9; RC-065: T1–T22, F1–F6, U5; RC-066: M1–M3, L1–L3, C1–C2, U1–U4, U6–U7); files restored byte for byte; restored run backend 301 passed, frontend 10 passed. A first run of the redesign left L2 (prompt logged) undetected — the prompt holds no identifier, so the log test saw nothing; the test now also checks that no prompt line is logged (commit `fbbbd4c`) (record `CAPA-014_negative_controls_2026-10-24.json`) |
| Whole backend test tree (`pytest tests`, local, offline per PRB-002) | 1894 passed, 20 skipped, 5 xfailed, 1 failed — the local-only WebAuthn test (webauthn not installed here; fails the same way on main) |
| Whole frontend suite (vitest `--pool=threads`) | 344 tests: 341 passed, 3 skipped (as on main), 0 failed |
| Type check (`tsc --noEmit`) | clean |

**Not verified.** No call to the real provider (the client is mocked; the exact call arguments are inspected). No run against Firestore (patient store mocked) or a deployed backend. No independent re-review of the redesign yet (PA-14.3). No usability evaluation of the notes (IEC 62366). No legal assessment (§6 is a draft for the owner and the data protection officer). **PRB-002:** the backend runs of the first version (2026-10-24 morning, before PRB-002 was known) had the machine's default cloud credentials available; whether they wrote test records to the production datastore is for PRB-002 to establish. Every run of the redesign was made offline (missing credentials file, empty configuration folder, project `mstool-offline-tests`, no API key).

## 6. Data that reaches the model provider — draft for the data-processing agreement (AV-Vertrag) — owner and data protection officer to confirm

| Item | Content |
|---|---|
| Recipient | Anthropic (Claude API), model `claude-sonnet-4-5-20250929` (`CLAUDE_MODEL`), called over HTTPS by the backend (Cloud Run, project `brain-mri-476110`) with the server's API key |
| Purpose | Drafting a structured report text from the device's measurements, for review, correction and signature by a physician (RC-006) |
| Sent | (1) Measurements: lesion counts and volumes, lesion centroid voxel coordinates, size classes, DIS items and voxel counts, zone statistics, longitudinal burdens and candidate counts, volumetry volumes, percentiles and flags. (2) Labels of the device's fixed vocabulary only (MAGNIMS regions, zones, structures, size classes, abnormality types; anything else as "[unlisted label]"). (3) Sex (male/female). (4) Age as a 5-year band ("90 or older" from 90). (5) Template and report language. (6) The fixed system prompt and a fixed instruction text (no personal data) |
| Not sent | Any free text (clinical indication, technique, observations, notes) — added to the draft in the application; the patient's name, record number, birth date, contact details and address; the clinician's identity; identifiers of segmentations or files |
| Identifiability | Measurements with sex and a 5-year age band. For the provider, identification is unlikely; whether the data remain personal data (pseudonymised health data, GDPR Art. 4(5), Art. 9) is for the owner and the data protection officer to decide — the agent gives no legal opinion |
| Points for the owner / data protection officer | Legal basis; processor agreement (Art. 28); transfer to the USA (Art. 44 ff.); retention and training terms of the provider; professional secrecy (§203 StGB); DPIA (Art. 35); Ley 1581 de 2012 if Colombian patients are processed |

## 7. Class C module modified — justification (CLAUDE.md)

`backend/app/services/brain_report_service.py` (Class C) was modified: the module header and class docstring (false claim withdrawn, data sent described), the prompt builder (the three free-text lines removed, sex only M/F, the age band line, the instruction that the clinician's text is added by the application), `generate_report` (identifiers required, `provider_payload`, the tripwire, the count log), and two module functions (`fixed_prompt_words`, `assert_prompt_carries_no_identifier`). **Strictly necessary:** the provider is called in this method and the prompt is built here; the payload must be restricted where the prompt is built, and the tripwire must run on the final prompt. No template text and no measurement formatting changed. The new `backend/app/services/report_payload_guard.py` is part of the same Class C item; it should be added to the Class C module list of `CLAUDE.md` (D-6 — the agent does not edit `CLAUDE.md`). Review by a person other than the author is required before merge (D-7).

## 8. Residual risk and open items

1. No free text leaves the application by design; what remains is measurements, fixed labels, sex and an age band. A name that is also one of the device's words (White, Black, Pons, Do …) is found by the tripwire only next to the other name; all-digit record numbers under 6 digits are not checked (they cannot be told from measurements) — both only matter if a future change re-opened a path for text, which RC-064's tests would catch first.
2. The draft written by the model is not filtered (unchanged: RC-006 and the physician's review).
3. The panel shows a generic error when a draft is refused (PA-14.4).
4. HAZ-016 residual proposed P1 / ACCEPTABLE, pending the re-review (PA-14.3), the owner's decision and the data-processing agreement (D-3).

## 9. Owner decisions (PENDING)

| ID | Decision |
|---|---|
| D-1 | Severity: Critical (proposed: regulatory non-compliance, QP-002 §5) |
| D-2 | HAZ-016 in RMF-001 with a confidentiality harm mapped to S3 (the §1.3 scale is defined for physical injury), or a separate security risk assessment under IEC 81001-5-1 |
| D-3 | Data-processing agreement / AV-Vertrag, transfer mechanism, retention and DPIA with the provider (§6, with the data protection officer). Until settled: recommendation to keep the report draft off in production (`ANTHROPIC_API_KEY` unset) |
| D-4 | Check whether drafts were generated in production before this fix (provider usage for the production key; backend logs "[Report] Generate request") and, if so, assess notification duties (GDPR Art. 33/34) |
| D-5 | Age sent as 5-year bands with "90 or older" is clinically acceptable for the templates |
| D-6 | Add `backend/app/services/report_payload_guard.py` to the Class C module list in `CLAUDE.md` |
| D-7 | Code review of the Class C change (§7) by a person other than the author |
| D-8 | Merge order with the parallel CAPA-015 PR (document versions and a possible second HAZ-016) |
| D-9 | Wording of the panel note, the "Clinician's entry" heading and the report viewer footer in en/es/de (radiologist review of the translations) |

## 10. Approvals

| Role | Name | Decision | Date |
|---|---|---|---|
| CAPA owner | *(to be assigned)* | PENDING owner approval | — |
| Owner / Project Lead | — | PENDING owner approval | — |
| Code review (Class C, D-7) | — | PENDING owner approval | — |
| Data protection (D-3, D-4) | — | PENDING owner approval | — |
| Effectiveness check | — | PENDING owner approval | — |

## 11. Independent review of PR #67 (2026-10-24) — findings and how the redesign removes them

The first version (PR #67 @ `4bfdd7e`) removed identifiers from the free text with pattern rules and a residual check sharing the same rules. An independent adversarial review (scripts `adv1.py`, `adv2.py`, `adv3.py`, `e2e.py`, `e2e_dob.py`) found it should not be merged. Each finding was verified; the decision was to change the design (ISO 14971 §7.1: inherent safety by design before protective measures).

| # | Finding (verified) | How the redesign removes it | Tests / mutations |
|---|---|---|---|
| 1 | The patient's own identifiers still leaked and the residual check could not see them (same rules): 9-digit phones (Spain, France — `digits[-10:]` kept a country-code digit), "DOB: 9. 11. 1975", "9-Nov-1975", "geb. 9.11.", "9.XI.1975", particle surnames (Do, Du, Le), soft hyphen and zero-width characters inside names, names written together ("Fuentemüller", "delaFuente"), "Muenchen" for München | No free text is sent at all (RC-064). The tripwire is a separate, detection-only implementation: phones with and without country code and trunk 0, birth date by its day/month/year parts in numeric, month-name and Roman forms and partial forms after a birth word, particle surnames kept when they are the whole surname, format characters removed and look-alikes mapped before matching, names inside longer words, German spellings both ways | `test_rc064_no_free_text_or_unlisted_label_reaches_the_provider`, `test_rc065_tripwire_refuses_each_leak_form` (all the review's forms); P1–P5, T2–T3, T8–T9, T17–T20 |
| 2 | Ages were not grouped: ≥ 90 kept the exact age; the exact age written in the text was sent | The age field is sent only as a 5-year band with "90 or older"; the text is not sent | `test_rc064_age_is_sent_as_a_five_year_band`, `test_rc064_an_age_that_is_not_a_number_is_not_sent`; P7, P8 |
| 3 | Over-removal rewrote the device's own labels: "Deep [name removed] Matter" for a patient named White, "[name removed] Hole" for Black; "small", "pons", "sustancia blanca", the word "may" | Nothing is rewritten: labels come from the vocabulary unchanged; the tripwire only refuses, and never reports the device's own words alone | `test_rc064_rc065_names_equal_to_device_labels_change_nothing_and_never_block` (White, Black, Small, Pons, Blanca, May, Do, Le, Du, Matter, Brain; en/es/de; with and without longitudinal); T4 |
| 4 | False "HIPAA compliant / no PHI transmitted" claims remained, in more places than this CAPA admitted (viewer footer and its translations, README, TD-001, AIA-001, ISMS-001, master document, technical documentation) | All corrected to the true statement; the viewer footer replaced; a repository-wide test fails on any such claim | `test_rc066_no_false_ai_privacy_claim_anywhere_in_the_repository`, UI-CAPA014; C1, C2, U6, U7 |
| 5 | Many pattern gaps (institutions, persons, addresses, dates in local forms …) | Patterns no longer decide what is sent; the payload is an allow-list | RC-064 tests |
| 6 | The e-mail rule took time growing with the square of the text length (27 s on 80 KB) in an async route | The scrubbing code is removed; every tripwire pattern is bounded or anchored; the scanned text is capped at 400 000 characters | `test_rc065_tripwire_runs_in_linear_time` (deadline thread), `test_rc065_tripwire_caps_the_text_it_scans`; T21, T22 |
| 7 | Wrong labels (redaction categories that did not match what was removed) | No redaction labels exist any more; the log counts what was withheld from the payload | `test_rc066_logs_say_the_check_ran_with_counts_never_the_payload`; L1–L3 |
| 8 | The tests missed all of the above | Tests now plant markers in every field and inspect the exact call; leak forms of the review, collision names and timing are tested; negative controls cover every sub-control | §5 |

*Drafted by the AI coding agent (development tool, SDP-001 §5.1.4). No approval is recorded in this document; approvals are to be recorded by the owner (CAPA-012).*
