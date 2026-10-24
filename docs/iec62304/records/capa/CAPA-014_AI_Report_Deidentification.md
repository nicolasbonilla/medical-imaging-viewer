# CAPA-014 — AI Report Draft: Patient Data Sent to the Model Provider Without De-identification

**CAPA ID**: CAPA-014
**Date Opened**: 2026-10-24 (DRAFT — opening, severity and actions PENDING owner approval)
**Source**: code reading of `main` @ `70cc5c7` on 2026-10-24 (orchestrating session), verified the same day by behavioural tests written before the fix (§5). Earlier records of the same gap: RCV-SUMMARY 2026-07-18 (RC-007′ "No de-identification routine exists"), CAPA-001 §2.3 and action CA-4 (still PENDING), CAPA-008 finding 4 and CA-8.5.
**Severity**: **CRITICAL** (proposed; QP-002 §5: regulatory non-compliance — special-category health data sent to a third-party processor without de-identification and without a recorded data-processing agreement; REQ-SEC-007 not met). Not a direct patient-injury defect; HAZ-003 is touched only through over-removal (§8).
**Owner**: *(to be assigned — a person; the AI coding agent cannot own a CAPA)*
**Status**: DRAFT. Corrections implemented on branch `fix/ai-report-deidentification-capa014` (draft PR, based on `main` @ `70cc5c7`). Nothing merged, nothing deployed. **Owner approval: PENDING.** Effectiveness not verified.
**Identifiers**: RC-064, RC-065, RC-066; REQ-SEC-021, REQ-SEC-022, REQ-SEC-023; HAZ-016 (new). Document versions **SRS 1.11, RMF 1.13, TM 1.10** (drafts). The parallel CAPA-015 PR reserves RC-067..RC-069, REQ-SEC-024..026, SRS 1.12, RMF 1.14, TM 1.11; if it also adds a hazard, HAZ-016 must be reconciled at merge (D-8).
**Procedure**: QP-002 (`docs/qms/QP-002_CAPA_Procedure.md`) · SPR-001
**Related**: HAZ-016 (HAZ-003, HAZ-013) · REQ-SEC-007 · REQ-IF-004 · RC-006 · RC-033 · RC-034 · RC-036 · CAPA-001 CA-4 · CAPA-008 · CAPA-009

---

## 1. Findings (code of `main` @ `70cc5c7`)

### Finding 1 — The service header claimed a de-identification that did not exist

`backend/app/services/brain_report_service.py` (Class C), module header lines 13–16: "HIPAA Compliance: Patient data is de-identified before sending to Claude API … No names, IDs, or dates are sent to the external API". The class docstring of the same file (line 443) said the opposite: "this service does NOT de-identify" (CAPA-008 CA-8.5 withdrew the claim there and in the route description, but not in the module header). The frontend API client (`frontend/src/api/aiReport.ts`) still said "HIPAA compliant: only de-identified findings are sent". CSA-001 recorded "PHI de-identification — Stripped before AI API calls — IMPLEMENTED" and "5.3.6 Data de-identification — IMPLEMENTED". No de-identification code existed anywhere in `backend/app/`.

### Finding 2 — Everything the clinician typed reached the provider verbatim

`POST /api/v1/ai/report/generate` (`ai_report.py:195`) passed `findings` and `volumetry` to `BrainReportService.generate_report`, which built the user prompt with `_build_findings_prompt` and called `client.messages.create(model=CLAUDE_MODEL, system=<template>, messages=[<prompt>])` — model `claude-sonnet-4-5-20250929` (`config.py:218`). The prompt carried the clinical indication, technique and additional observations as typed (`ai_report.py:152–160` describes them as "de-identified"; nothing made them so), the **exact age**, the sex, and every string of the structured findings (segmentation label names, anomaly locations, region names, volumetry structure names). Reproduced on `70cc5c7`: a free text holding the patient's name, record number, birth date, phone, e-mail, address, an accession number, three study dates, a physician and a hospital reached the mocked provider client unchanged (`test_rc064_patient_identifiers_in_free_text_never_reach_the_provider`, record `CAPA-014_tests_on_base_2026-10-24.json`).

### Finding 3 — The route did not know whose identifiers to remove

The request referenced no patient or stored object (CAPA-008 had listed the route as "references no stored object"), so no server-side record could be used to remove the patient's own name, record number or birth date; the burden was put on the caller ("callers must not send direct identifiers"), a rule a clinician typing free text cannot follow and no code enforced. The AI assistant's MS report tool sent its findings the same way.

### Finding 4 — No record that anything was removed

The route logged template and language only (correct: no payload in the log), but nothing recorded that a removal ran or what it removed.

### Finding 5 — Probably live

`ANTHROPIC_API_KEY` is one of the variables required in production (`DEPLOYMENT_CHECKLIST.md` line 18). Whether drafts were generated in production before this fix, and with what text, cannot be established from the repository (owner action D-4).

### Finding 6 — Every displayed and printed draft carries a false statement (found while correcting; NOT changed)

`ReportViewerModal.tsx:313` shows, at the foot of every report draft and on its printed A4 page, `reportViewer.hipaaNote`: "HIPAA Compliant — Only de-identified clinical findings were used for report generation. No protected health information (PHI) was transmitted to external services." (es/de equivalents). It was false before this CAPA and is still inaccurate after it: pseudonymised health data (measurements, sex, age band, the clinician's text after removal) are transmitted. The text was **left unchanged** because this change was limited to one note next to the draft button; REQ-SEC-023 (c) is therefore not met for this footer until the owner decides (D-9, proposed wording there).

## 2. Root cause

1. A privacy control was written as a description of intent (module header, client comment, CSA-001), the same defect class as CAPA-001: REQ-SEC-007 carried the verification "Test + Inspection" with no test, so nothing could contradict the claim.
2. The report route was designed as stateless text generation. Removing a patient's identifiers needs to know the patient; the design never provided that context, so the only possible "control" was an instruction to the caller.
3. CAPA-008 corrected the wording in two places and moved the burden to the caller instead of implementing CAPA-001 CA-4.

## 3. Corrections and corrective actions (implemented on the branch — PENDING owner approval)

| ID | Action | Control | Where |
|---|---|---|---|
| CA-14.1 | One de-identification step for everything sent to the provider: every string of the findings and the volumetry (values and keys) passes it immediately before the prompt is built. (a) The patient's own given, middle and family names, emergency-contact name, record number, insurance policy number, phone numbers, e-mail, address lines, city, postal code and birth date, read from the patient record the server holds — case- and accent-insensitive, German ae/oe/ue spellings, particles ("de", "la", "von") never removed on their own. (b) By pattern (en/es/de): e-mail, phone numbers, numbers after identifier words (MRN, accession, DNI, CC, NHC, Fallnummer …), other numbers of ≥ 6 digits not followed by a unit, titled person names (Dr., Prof. Dr. med., Herr, Sra. …), institution names around Hospital / Klinikum / Clínica / Instituto …, street addresses. (c) Birth date removed in any written form; other exact dates replaced by the interval to the first date met (`[date 2 = date 1 + 7 months]`); a day and month without year removed. (d) Age sent as a 5-year band (15-17 and 18-19 keep the age of majority; "90 or older"), also in the text ("48-year-old" → "45-49-year-old"). (e) Numbers of the measurements never altered; the system prompt is the fixed template; fields the report does not use are never read | RC-064 | `services/report_deidentification.py` (new, part of the Class C report item), `brain_report_service.py::generate_report` |
| CA-14.2 | Patient reference: the request names the analysed segmentation (`segmentation_id`); the route authorizes it for the caller (`authorize_segmentation_id`, same rule and 404 as RC-036) and reads its patient's record; the report panel and the assistant's report tool send it | RC-065 | `ai_report.py`, `security/resource_access.py`, `AIReportPanel.tsx`, `types/ai.ts`, `mcp/ms_clinical_server.py`, `mcp/_backend.py` (comment) |
| CA-14.3 | Fail closed: no segmentation → 400 (not 422: the panel reads every 422 as "no measurements"); no access → 404; record unreadable, missing, or without record number, given name, family name or birth date → 503; the service refuses to build a prompt without identifiers; a residual check on the final prompt (the patient's given and family name together, record number, birth date, e-mail, phone) → 503. In every case the provider is not called and the error names no identifier and says that nothing was sent | RC-065 | `ai_report.py`, `brain_report_service.py`, `report_deidentification.py` |
| CA-14.4 | Records and disclosure: the log states that de-identification ran and the count per category (`deidentification="applied"`, `redactions={...}`), never the payload; false claims withdrawn (service header, API client, route and field descriptions; CSA-001 rows annotated); note directly above the draft button in en/es/de; data categories still sent recorded (§6) | RC-066 | `brain_report_service.py`, `AIReportPanel.tsx`, `i18n/locales/{en,es,de}.json`, `aiReport.ts`, `12_Cybersecurity_Assessment.md`, §6 |
| CA-14.5 | Verification: tests written first (§5), negative controls, manifest RC-064..066 → implemented on the branch | — | §5 |

### What the clinician sees

| | Before (`70cc5c7`) | After (this branch) |
|---|---|---|
| Report panel | Template, language, three text fields, "Generate Report" | The same, plus one line directly above the button: "Sent to the AI provider (Anthropic): the measurements, sex, a 5-year age range and your text. Removed first: the patient's name, record number and birth date (from the patient record), and dates (turned into intervals), phone numbers, e-mail addresses and ID numbers in your text. Other names may not be recognised — do not type them." (es/de translated) |
| Draft with an open segmentation | Generated | Generated (identifiers removed before sending) |
| No open segmentation | "No measurements are available…" (422) | Unchanged |
| Patient record unreadable / incomplete | Generated | Refused; the panel shows its generic error ("Request failed with status code 503"), the API returns "The patient's identifiers could not be removed (…). Nothing was sent to the AI provider." Showing the server's reason in the panel is a UI change left to the owner (PA-14.4) |

Example (synthetic patient of the test file). Sent before: `Clinical indication: Juan Carlos Pérez Gómez (MRN-2025-0042), born 15/03/1978, known RRMS, EDSS 3.5. Follow-up of 12 lesions seen on 12.03.2025.` Sent after: `Clinical indication: [name removed] ([record number removed]), born [birth date removed], known RRMS, EDSS 3.5. Follow-up of 12 lesions seen on [date 1].` — and `Patient age: 48 years` became `Patient age band: 45-49 (years)`.

## 4. Preventive actions (proposed — PENDING owner approval)

| ID | Action |
|---|---|
| PA-14.1 | SDP review-checklist rule: any code that sends data to an external service (language model, cloud AI) goes through a de-identification step and has a test that inspects the exact outbound payload with identifiers planted in it |
| PA-14.2 | Claims check: no "de-identified", "HIPAA", "GDPR compliant" or similar statement in source, API descriptions or documents without a linked, test-bound risk control (review checklist; a repository-wide test is possible) |
| PA-14.3 | Measure removal and over-removal on a realistic corpus before use with real patient data: 50–100 clinical texts in es/de/en written by a clinician with planted identifiers (names with and without titles, institutions, dates in local formats, IDs, phones); recall per category and clinical words lost; extend the rules where needed |
| PA-14.4 | Show the server's reason for a refused draft in the panel (UI change, owner decision — not done here because only the note was to change in the UI) |
| PA-14.5 | REQ-SEC-007 also names Vertex AI: check what the AI segmentation path sends (image headers such as NIfTI `descrip`, DICOM tags) — separate CAPA if needed |
| PA-14.6 | The AI assistant's own model provider receives the other tools' responses with identifier keys dropped (RC-033) but free text not scrubbed; consider reusing `report_deidentification` there |

## 5. Verification (by the author — not independent; owner approval PENDING)

**Tests written before the fix, failing on `70cc5c7`.** `backend/tests/unit/test_capa014_report_deidentification.py` and `frontend/src/components/AIReportPanel.capa014.test.tsx` were committed first (commit `2964063`, "written before the fix"): on `70cc5c7` the backend file failed 34 of its 36 cases and the frontend file 6 of 6. The two passing cases are regression guards (fixed system prompt; measurement lines unchanged). After the fix the backend file was completed with pattern cases (19 more parametrised cases, `test_rc064_pattern_rules`, 55 cases in all) found while checking the rules on examples and after a first run of the negative controls, and the access path of two assertions was corrected (the application's error handler wraps the HTTP detail: the tests read the response text); no assertion was weakened. The first run (48 mutations, 2026-10-24, not kept as a record) left two undetected — D18 (the ≥ 6-digit ID rule: every test number was also caught by another rule) and F10 (the residual e-mail check: the test e-mail contained the patient's name, so the name check caught it) — so cases were added for an ID that only that rule catches and an e-mail without the name. Checking the rules also showed over-removal, corrected with a case each and a mutation each (D27–D32): year ranges ("2019-2021") and year lists removed as ID or phone numbers, the German word "nie" read as an identifier word, nouns ending in "-ring" read as streets, and part of an ID read as a phone number. A request without a segmentation is refused with 400 instead of 422, because the panel reads every 422 as "no measurements". The final test files were re-run against the `70cc5c7` source by `scripts/safety/capa014_tests_on_base.py` — record `records/risk_verification/CAPA-014_tests_on_base_2026-10-24.json` (result in §5.1).

**Existing tests adapted to the new contract (assertions unchanged unless stated).** `test_brain_report_service.py`: the 16 calls of `generate_report` pass a test patient's identifiers; the patient-age case now asserts the band (the contract changed). `test_capa008_assistant_read_only.py`: the report fixture provides an authorized segmentation with a readable record; the "accepts measurements" case sends `segmentation_id`. `test_capa013_longitudinal_candidates.py`: the four report requests send `segmentation_id` with the same fixture. `test_capa009_object_authorization_everywhere.py`: the route is classified `call:authorize_segmentation_id`, a 404 probe for a caller without access was added, and `authorize_segmentation_id` joined the recognised calls.

**Negative controls.** `scripts/safety/capa014_negative_controls.py` — one mutation at a time in the real source, each anchor asserted unique, bytes restored; record `records/risk_verification/CAPA-014_negative_controls_2026-10-24.json` (result in §5.1).

### 5.1 Results

| Check | Result |
|---|---|
| CAPA-014 tests on the `70cc5c7` source (final test files) | backend **53 of 55 fail**, frontend **6 of 6 fail**; the 2 passing backend cases are the regression guards named above (record `CAPA-014_tests_on_base_2026-10-24.json`) |
| CAPA-014 tests on the branch | backend 55/55, frontend 6/6 |
| Negative controls (final run, executed 2026-10-24 12:11) | **54 mutations, 54 detected** (RC-064: D1–D32; RC-065: F1–F12, U5; RC-066: L1–L4, U1–U4, U6); files restored byte for byte, restored run backend 180 passed / frontend 6 passed (record `CAPA-014_negative_controls_2026-10-24.json`) |
| Whole backend test tree (`pytest tests`, local) | 1752 passed, 20 skipped, 5 xfailed, **1 failed**: `tests/integration/test_auth_endpoints.py::TestWebAuthnEndpoints::test_webauthn_credentials_endpoint_exists` — `webauthn` is not installed in the local environment (fails the same way on `main`) |
| Whole frontend suite (vitest `--pool=threads`) | 340 tests: 337 passed, 3 skipped (as on `main`), 0 failed |
| Type check (`tsc --noEmit`) | clean |
| Anchors of the earlier negative-control scripts (CAPA-008, -009, -010, -011, -013) | still unique in the changed sources (checked read-only) |

**Not verified.** No call to the real provider (the client is mocked; the exact arguments of the call are inspected). No run against Firestore (patient store mocked) or a deployed backend. No measurement of removal on real clinical texts (PA-14.3). No usability evaluation of the note (IEC 62366). No legal assessment (§6 is a draft for the owner and the data protection officer). **PRB-002 (reported the same day):** the local backend runs above (whole tree, negative controls, base run) were made before PRB-002 was known, with the machine's default cloud credentials available; whether they wrote test records to the production datastore is for PRB-002 to establish. The last runs (manifest gate, CAPA-014 file) were made with the offline settings PRB-002 prescribes.

## 6. Data that still reaches the model provider — draft for the data-processing agreement (AV-Vertrag) — owner and data protection officer to confirm

| Item | Content |
|---|---|
| Recipient | Anthropic (Claude API), model `claude-sonnet-4-5-20250929` (`CLAUDE_MODEL`), called over HTTPS by the backend (Cloud Run, project `brain-mri-476110`) with the server's API key |
| Purpose | Drafting a structured report text from the device's measurements, for review, correction and signature by a physician (RC-006) |
| Data subjects | Patients whose MRI is analysed; indirectly, persons named in the clinician's text |
| Sent | (1) Measurements: lesion counts and volumes, MAGNIMS regions, size classes, lesion centroid voxel coordinates, DIS items, active / black-hole voxel counts, zone statistics, longitudinal burdens and candidate counts, volumetry volumes, percentiles and flags. (2) Segmentation label names, anomaly types and locations (after removal). (3) Sex (male/female). (4) Age as a 5-year band. (5) The clinician's clinical indication, technique and observations after removal. (6) Template and report language. (7) The fixed system prompt (no personal data) |
| Removed before sending | The patient's name, emergency-contact name, record number, insurance policy number, birth date, phone numbers, e-mail, address, city and postal code (from the patient record); exact dates (sent as intervals); numbers after identifier words; other numbers of ≥ 6 digits without a unit; titled person names; institution names with a recognised word; street addresses |
| Never read by the report | Fields the report does not use (for example segmentation or file identifiers inside the measurement payloads); the identity of the clinician |
| Still possibly identifying | Names without a title, institution names without a recognised word, rare clinical or social details, years, the combination of age band, sex and history. The data are **pseudonymised health data** (GDPR Art. 4(5)), i.e. personal data of a special category (Art. 9) — not anonymous |
| Points for the owner / data protection officer (not legal advice) | Legal basis (Art. 9(2)(h) with national law, e.g. §22 BDSG); processor agreement (Art. 28) with the provider; transfer to the USA (Art. 44 ff.: adequacy decision for a certified recipient, or standard contractual clauses and a transfer impact assessment); retention and training terms of the provider (zero data retention to be agreed if available); professional secrecy (§203 StGB: the provider as a contributing person bound to confidentiality); data protection impact assessment (Art. 35); if Colombian patients are processed, Ley 1581 de 2012 rules on sensitive data and international transfer |

## 7. Class C module modified — justification (CLAUDE.md)

`backend/app/services/brain_report_service.py` (Class C) was modified in four places: the module header (false claim withdrawn, data sent described), the class docstring, the age line of `_build_findings_prompt` (prints the band), and `generate_report` (required `identifiers`, the de-identification step, the residual check, the count log). **Strictly necessary:** the provider is called in this method; a removal only in the route would leave any other caller of the service unprotected, and the residual check must run on the final prompt, which only exists here. No template text, no measurement formatting and no other prompt line changed. The new `backend/app/services/report_deidentification.py` is part of the same Class C software item (it is called only from `generate_report` and decides what leaves the server); it should be added to the Class C module list of `CLAUDE.md` (D-6 — the agent does not edit `CLAUDE.md`). Review by a person other than the author is required before merge (D-7).

## 8. Residual risk and open items

1. The clinician's text can still carry identifiers the rules cannot recognise (names without a title, institutions without a recognised word, rare details, years); the note asks not to type other names. Removal not measured on real texts (PA-14.3).
2. Over-removal (contributes to HAZ-003): a patient's name that is also a clinical word is removed wherever it appears in the strings of the findings (a family name "Black" would remove "black" in "T1 black holes" typed in the text); a number of ≥ 6 digits without a unit in the text is removed; a German noun directly after "Klinikum" or similar is removed with it. The draft is reviewed by a physician (RC-006); measurement lines built from numbers are never touched.
3. A numeric date that could be read both ways (03/04/2025) is read day-first (es/de convention); a US month-first date gives a wrong interval — the date itself is removed either way.
4. Record-based removal covers the patient of the named segmentation only; text about another patient pasted into the request is covered by the pattern rules only.
5. Pattern rules exist for English, Spanish and German only.
6. The panel shows a generic error when a draft is refused (PA-14.4).
7. The footer of every displayed and printed draft still states "HIPAA Compliant … No protected health information (PHI) was transmitted to external services" (Finding 6, D-9): REQ-SEC-023 (c) not met there.
8. HAZ-016 residual not estimated (proposed UNDETERMINED) until PA-14.3 and D-3.

## 9. Owner decisions (PENDING)

| ID | Decision |
|---|---|
| D-1 | Severity: Critical (proposed: regulatory non-compliance, QP-002 §5) |
| D-2 | HAZ-016 in RMF-001 with a confidentiality harm mapped to S3 (the §1.3 scale is defined for physical injury), or a separate security risk assessment under IEC 81001-5-1 |
| D-3 | Data-processing agreement / AV-Vertrag, transfer mechanism, retention and DPIA with the provider (§6, with the data protection officer). Until settled: recommendation to keep the report draft off in production (`ANTHROPIC_API_KEY` unset) |
| D-4 | Check whether drafts were generated in production before this fix (provider usage for the production key; backend logs "[Report] Generate request") and, if so, assess notification duties (GDPR Art. 33/34) |
| D-5 | Age sent as 5-year bands (15-17 / 18-19 split, "90 or older") is clinically acceptable for the templates |
| D-6 | Add `backend/app/services/report_deidentification.py` to the Class C module list in `CLAUDE.md` |
| D-7 | Code review of the Class C change (§7) by a person other than the author |
| D-8 | Merge order with the parallel CAPA-015 PR (document versions and a possible second HAZ-016) |
| D-9 | Replace the false footer of every displayed and printed draft (`reportViewer.hipaaNote`, Finding 6). Proposed: en "Draft written by an AI model (Anthropic) from the device's measurements and the clinician's text. The patient's identifiers were removed before sending; what was sent is pseudonymised, not anonymous." · es "Borrador redactado por un modelo de IA (Anthropic) a partir de las mediciones del programa y del texto del médico. Los identificadores del paciente se eliminaron antes del envío; lo enviado está seudonimizado, no es anónimo." · de "Entwurf eines KI-Modells (Anthropic) aus den Messwerten der Software und dem Text der Ärztin oder des Arztes. Die Identifikatoren des Patienten wurden vor dem Senden entfernt; das Gesendete ist pseudonymisiert, nicht anonym." Until then REQ-SEC-023 (c) is not met for this footer. Related claims outside the report path (login page "HIPAA 2026" badge, session components) belong to PA-14.2 |

## 10. Approvals

| Role | Name | Decision | Date |
|---|---|---|---|
| CAPA owner | *(to be assigned)* | PENDING owner approval | — |
| Owner / Project Lead | — | PENDING owner approval | — |
| Code review (Class C, D-7) | — | PENDING owner approval | — |
| Data protection (D-3, D-4) | — | PENDING owner approval | — |
| Effectiveness check | — | PENDING owner approval | — |

*Drafted by the AI coding agent (development tool, SDP-001 §5.1.4). No approval is recorded in this document; approvals are to be recorded by the owner (CAPA-012).*
