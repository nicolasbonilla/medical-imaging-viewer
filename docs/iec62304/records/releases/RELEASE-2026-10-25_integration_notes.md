# RELEASE-2026-10-25 — integration notes (`release/owner-signoff-2026-10-25`)

**Status: DRAFT for the owner's single sign-off. PENDING owner approval.** Nothing was merged to `main`, nothing was
deployed, nothing was signed. No cloud service, no Firestore, no model provider and no GCP project was contacted;
every backend run was offline per PRB-002. Every approval field in every document still reads
"PENDING owner approval".

Prepared by the AI coding agent (release integrator) on 2026-10-25. Like the previous release (PR #64), this is one
integration branch that the owner signs and merges once; the four draft PRs can then be closed as merged here.

## 1. What was integrated

Base: `origin/main` @ `70cc5c7` (merge of PR #64). The four branches were fetched on 2026-10-25; every pushed head was
identical to the head named in the request. Each was merged with `git merge --no-ff` (no rebase), so the reviewed
commits and every commit hash cited in the records stay valid.

| Order | PR | Branch @ head | What it does | IDs | Merge commit |
|---|---|---|---|---|---|
| 1 | #66 PRB-002 | `fix/test-cloud-isolation-prb002` @ `fbc78d2` | The backend test suite can never reach a real cloud service (five-layer guard in `backend/tests/conftest.py`) | PRB-002 (not safety-related; test configuration only) | `d3dbbf9` |
| 2 | #65 CAPA-015 | `fix/audit-trail-and-session-capa015` @ `2c27282` | Durable, append-only audit trail; rotating session refresh without losing unsaved work | RC-067..069, REQ-SEC-024..026, HAZ-010, HAZ-001 | `0dc66f7` |
| 3 | #67 CAPA-014 | `fix/ai-report-deidentification-capa014` @ `a471d9a` | The AI report draft sends measurements only; the clinician's text and the application's notes are separate draft parts | RC-064..066, REQ-SEC-021..023, HAZ-016 (new), HAZ-003 | `327322d` |
| 4 | #68 PRB-003 / CAPA-016 | `fix/dis-requires-reviewed-segmentation-prb003` @ `b990521` | DIS only on a radiologist-confirmed, MAGNIMS-classified segmentation | RC-070..072, REQ-SAFE-038..040, HAZ-008, HAZ-005, HAZ-003 | `94c42ef` |

Integration commits after the four merges (one concern each):

| Commit | Content |
|---|---|
| `4320744` | Test-fixture reconciliation (§4) |
| `f93eafd` | #68's confirmation route recorded by CAPA-015's audit trail (§3, S1) |
| `929ce0c` | RC-064 amended — "one of the fixed template variants" (§3, S2) — PENDING owner approval |
| `fe4487d` | Integration tests I-1, I-2, C-1 (§3, S3) |
| `57933c3` | Negative-control scripts: P17 anchor, new integration script (§6) |
| `6d1fde2` | These notes (first version), the integrated-tree negative-control records, the manifest's negative-control fields (RC-064..072), CAPA-015 D-4 note |
| `26ecb82` | Integration review of #69: tests written first (§9) |
| `269317d` | Integration review of #69: corrections of items 1, 2, 3 and 6 (§9) |
| `9c78d2d` | Integration review of #69: CRLF-safe control scripts (item 5), R4 / P17 anchors, integration controls I7–I12 |
| `9e8fa48` | CAPA-014 M10 kept detectable by a direct test; integration mutation I2 redefined (§6) |
| `c7a06cf` | §6 and §9 of these notes, re-run records, documents (SRS 1.14, RMF 1.16, TM 1.13, DD-001 1.4 rows; CAPA-014 §12; CAPA-016 §13), manifest |
| `7c7c70d` | Capture session: tests written first for F08, F09, F10, F04 (§10) |
| `e9935eb` | Capture session: corrections of F08, F09, F10, F04 (§10) |
| `09cd029` | PRB-003 F11 anchor after F10; integration controls I13–I21 |
| `dd22708` | §6 and §10 of these notes, capture-round control records, document rows, manifest |
| `9d5a51f` | Second review of #69: tests written first for B1 and M3 (§11) |
| `ebf39c3` | Second review of #69: corrections of B1 and M3 (§11) |
| `30d9067` | Second review of #69: tests written first for M1, M2 and the minor items (§11) |
| `38494ed` | Second review of #69: corrections of M1, M2, m1–m5 and n1 (§11) |
| `21b0df8` | Integration controls I22–I41; PRB-003 A1 and integration I12 anchors moved (§11) |
| `40f1d5c`, `197b918` | Film capture "DWM: 1 lesions": tests written first (§11) |
| `a8ca653` | Film capture: a count of one is singular (dashboard en/es/de; findings prompt, Class C text) (§11) |
| `d3104c3` | Integration controls I42–I45 (§11) |
| `9c16548` | Re-review of PR #71: test written first for the fallback colour (§11) |
| `1c66562` | Fallback colour cyan, not the Active (Gd+) magenta (§11) |
| `b3a376e` | Integration controls I46, I47 (§11) |
| `39d9730` | §6, §7, §10 (F08 cause, m3) and §11 of these notes, second-review control records (also CAPA-010 and CAPA-013, now run on the integrated tree), document rows, manifest |
| `1d3c495` | Final check of #69: tests written first for R1 and R2 (§12) |
| `a11b648` | Final check of #69: Confirm only in the standard 2D view drawing the stored region labels; preset lock; drawn label table checked by the server (§12) |
| `0ca1967` | Integration controls I48–I57; PRB-003 F4 and WF3 anchors moved (§12) |
| (records commit) | §6, §7, §10, §11 wording and §12 of these notes, final-tree control records, document rows, manifest |

## 2. Conflicts and how each was resolved

### C1 — `backend/tests/conftest.py` (#66 + #65; merged without a text conflict, resolved by hand)

Git merged the file automatically, but put CAPA-015's lines **above** the PRB-002 guard, including CAPA-015's weaker
`os.environ.setdefault('GOOGLE_APPLICATION_CREDENTIALS', …)` and `setdefault` for the two in-memory backends.
Resolution (`0dc66f7`):
- #66's five-layer guard kept **verbatim** (the diff of the file against #66's head is only the added CAPA-015 block),
  forced, before any application import;
- CAPA-015's settings placed **after** the guard and before the application import, all **forced**:
  `AUDIT_SINK_BACKEND=memory`, `REFRESH_TOKEN_BACKEND=memory`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15`,
  `REFRESH_TOKEN_IDLE_MINUTES=30`, `REFRESH_TOKEN_ABSOLUTE_HOURS=12`;
- CAPA-015's `setdefault` credentials line dropped (PRB-002 layer 1 forces the credentials file).
Evidence: PRB-002 tests 19/19 pass; new test `test_release_c1_conftest_forces_the_capa015_test_settings`; integration
negative controls I4–I6 (§6); the PRB-002 negative controls (§6).

### C2 — merge of #67: documents only

| Document | Resolution |
|---|---|
| SRS-001 | revision rows 1.11 (#67) then 1.12 (#65); REQ-SEC-021..023 then REQ-SEC-024..026; header lists both. #67's correction of the header ("last approved: 1.10", not 1.4) kept |
| RMF-001 | rows 1.13 (#67) then 1.14 (#65); RC-064..066 then RC-067..069; header lists both, "last approved: 1.12" as corrected by #67 |
| TM-001 | rows 1.10 then 1.11; addendum CAPA-014 then CAPA-015 (separated by a blank line); header lists both |
| `capa_register.md` | CAPA-014 row then CAPA-015 row |
| `rc_test_manifest.json` | `capa_reference` lists CAPA-014 and CAPA-015; RC-064..066 then RC-067..069 (67 controls, valid JSON) |

### C3 — merge of #68: code and documents (per the merge notes of both PRs)

| File | Resolution |
|---|---|
| `backend/app/api/routes/ai_report.py` | (a) both imports kept. (b) **One** `segmentation_id` field in `ReportGenerateRequest`, required as in #67 (400 without it, used to read the patient's record) and used by #68 to derive the DIS state and the lesion table on the server, with #68's 409 for a block naming another segmentation; the description states both uses. (c) **Both authorizations of the report's segmentation kept**: #67's `authorize_segmentation_id` (returns the patient for the identifier check) and #68's `authorize_mask_specs` (RC-029). They apply the same rule; keeping both keeps each PR's reviewed control and its negative control (CAPA-014 F2, PRB-003 R2) meaningful. Cost: one more metadata read per report. (d) **Order after the model returns**, as both merge notes ask: model text with the RC-006 disclaimer → #68's `scrub_unevaluated_dis` (only when DIS is not evaluated) → #67's `draft_parts` → CAPA-013 longitudinal notice → #68's `dis_notice` → #67's `draft_text`. The check never sees the clinician's typed entry or the application's notes; both notices are appended to `ai_text`, so they appear in the viewer and in the single text. |
| `backend/app/services/brain_report_service.py` (**Class C**) | #67's `CLINICIAN_TEXT_INSTRUCTION` and #68's `DIS_NOT_EVALUATED_PROMPT` / `dis_not_evaluated_template` both kept. **#68's DIS block wins**: MET / NOT MET only for a block marked "evaluated"; anything else, also a block with no state, gets `DIS_NOT_EVALUATED_PROMPT` (#67's own not-evaluated branch removed, as #67's merge note 1 says). In `generate_report`: #67's identifiers check, `provider_payload` and tripwire kept; the template variant is chosen on the DIS block of the **RC-064 payload** (`payload.findings`) — what the model receives — instead of the raw findings (integration decision, so the template and the findings prompt always agree; test I-2, negative control I2). The not-evaluated prompt text joins the device's own words automatically (`fixed_prompt_words()` prints a not-evaluated DIS), as #67's merge note 4 says. |
| `backend/app/mcp/_backend.py`, `ms_clinical_server.py` | comments merged; one `segmentation_id` sent by the assistant's report tool |
| `frontend/src/components/AIReportPanel.tsx`, `frontend/src/types/ai.ts` | one `segmentation_id`; both comments kept; #67's response types kept |
| `DEPLOYMENT_CHECKLIST.md` | both sections kept. **Deployment order**: CAPA-015 said "backend, then hosting"; PRB-003 says "frontend first". For this release the order is **hosting first, then the backend at once**: a new page against the old backend only opens the re-login dialog and keeps the work (CAPA-015 review M4) and reads both DIS answers, while an old page against the new backend breaks the lesion panel (PRB-003 m10) and gets 15-minute sessions without silent renewal (CAPA-015). CAPA-015 step 1 rewritten accordingly (a step 0 explains why); step 1b (client address through a Firebase Hosting preview channel) now runs right after the backend deploy and **before go-live** (before clinical use resumes). CAPA-015 decision D-4 still says "backend first" — the owner decides (§8). |
| SRS-001 | rows 1.11, 1.12, **1.13 (#68)**; REQ-SAFE-038..040 |
| RMF-001 | rows 1.13, 1.14, **1.15 (#68)**; §3.6 (CAPA-015) then §3.7 (PRB-003); RC-064..069 then RC-070..072; §7 open items: CAPA-014 row then PRB-003 row |
| TM-001 | rows 1.10, 1.11, **1.12 (#68)** |
| DD-001 | rows 1.2 (#67) then 1.3 (#68); header lists both |
| `capa_register.md` | CAPA-014, CAPA-015, CAPA-016 |
| `rc_test_manifest.json` | RC-064..072 (70 controls); `capa_reference` also lists CAPA-016 (#68 had not added it) |

Merged automatically and checked: the locale files (en/es/de, valid JSON), `LesionDashboard.tsx` (#65 + #68),
`test_capa009_object_authorization_everywhere.py` (#65, #67, #68), `firebase.json`, `firestore.indexes.json`,
`firestore.rules` (#65 only). Type check, build and tests pass on the result (§6).

No identifier is duplicated: REQ-SEC-021..026, REQ-SAFE-038..040, RC-064..072 and HAZ-016 are each defined once.

## 3. Changes made at the integration (not text conflicts)

**S1 — #65 + #68: the DIS confirmation is audited** (`f93eafd`). CAPA-015's `ROUTE_ACTIONS` maps
`POST /api/v1/segmentation/{segmentation_id}/review/confirm` (RC-071) to `CLINICAL_SEGMENTATION_CONFIRM`, resource
"segmentation" (asked by #68's review, M5, and #68's merge notes). Test
`test_rc067_prb003_dis_confirmation_is_a_recorded_clinical_action`: the route is mounted under that template, the
mapping holds, a refused confirmation leaves one durable record (actor, role, segmentation id, outcome, request id).
It fails without the mapping (KeyError) and passes with it; negative control I3.

**S2 — RC-064 amended — PENDING owner approval** (`929ce0c`). Asked by the third independent review of #68: #68
replaces the DIS and per-region instructions of the template when DIS was not evaluated, so CAPA-014's
"(f) the system prompt is the fixed template" becomes "**one of the fixed template variants**" (as written, or with
those instructions replaced), chosen on the DIS block of the payload. Both variants are fixed text; no request data is
in the system prompt. Recorded in SRS-001 1.14 (REQ-SEC-021 (f)), RMF-001 1.16 (RC-064 row and §7 open item D-10),
DD-001 1.4 (DD-RPT-001), CAPA-014 §12 and new decision D-10, the manifest's RC-064 description; every one reads
"PENDING owner approval". The test `test_rc064_system_prompt_is_the_fixed_template` now checks **both** variants
exactly and that no request data is in the system prompt (its name is kept because the CAPA-014 records cite it).

**S3 — integration tests** (`fe4487d`, `backend/tests/unit/test_release_2026_10_25_integration.py`, 9 cases; real
route and real report service, only the provider, the patient record, the authorization hooks and the server-derived
blocks stubbed):
- I-1 (en/es/de) `test_rc070_release_i1_*`: a DIS statement in the model's text is replaced and stated in the notice;
  the same statement typed by the clinician stays exactly as typed (field and quoted text, once in the single text);
  the RC-006 disclaimer is still recognised; the typed text is never sent;
- I-2 (five templates) `test_rc064_release_i2_*`: a block marked "evaluated" without a yes/no conclusion is sent as
  not evaluated by the payload, and the system prompt is then the not-evaluated variant;
- C-1 `test_release_c1_*`: conftest forces CAPA-015's settings.
TM-001 1.13 (test rows UT-REL-20261025); the manifest's RC-064 and RC-070 name the file.

## 4. Test-fixture reconciliation — no assertion was weakened (`4320744`)

Each PR's route tests stubbed only their own hooks. On the merged route they either reached a real store (stopped by
the PRB-002 guard — the risk #67's merge note 6 named) or met the other PR's new contract. Before reconciliation the
unit suite had 151 failures in exactly the files #68's reviewer listed (CAPA-014 131, PRB-003 11, CAPA-013 6,
CAPA-015 1, CAPA-008 1, report service 1).

| # | Test file / fixture | Change | Why no assertion was weakened |
|---|---|---|---|
| F1 | `test_capa014_report_provider_payload.py`, `route` fixture and the 404 test | Stubs #68's `authorize_mask_specs` (records the specs), `server_lesion_table` and `server_dis_assessment` as a server that derived exactly the measurements the test sends (`_post` hands them to the stubs); `_dis_services` raises, so no CAPA-014 test can reach the segmentation store. The 404 test uses the same stubs, so only CAPA-014's own authorization decides | Every CAPA-014 assertion unchanged; the merged route still replaces the client's blocks — with the server's — which #68's tests check |
| F2 | same file, `_measurements()` | The DIS block carries `"evaluation_status": "evaluated"` | After #68 regions travel with the lesion table and MET / NOT MET is printed only for an evaluated DIS; without the state the test data would no longer contain what the CAPA-014 checks inspect (device labels unchanged, markers, ranges) |
| F3 | same file, `test_rc064_dis_evaluated_state_is_kept_and_reported` | The "legacy" block without state is now checked to print **NOT EVALUATED** and never MET / NOT MET / "3/5 regions" (was: "MET (3/5 regions)"); "no state is invented" kept | Contract changed deliberately by #67's merge note 1 (#68's rule wins); the new check is stricter |
| F4 | `test_capa015_audit_and_session.py`, AI-report audit test | Sends `segmentation_id`; #67's and #68's hooks stubbed | The CAPA-015 record checks (one durable record, template, language, outcome, no free text) unchanged |
| F5 | `test_capa013_longitudinal_candidates.py` (report helper), `test_capa008_assistant_read_only.py` (report fixture) | #68's `authorize_mask_specs` stubbed (CAPA-008 also the lesion table and DIS state); `_dis_services` raises | Assertions unchanged |
| F6 | `test_brain_report_service.py::test_each_template_uses_correct_system_prompt` | The evaluated-DIS call passes `identifiers` | Without identifiers the merged service sends nothing (CAPA-014); assertion unchanged |
| F7 | `test_prb003_dis_requires_confirmed_segmentation.py`, `report_env` (also used by review2 and review3) | Stubs #67's `authorize_segmentation_id` and patient record, as #68's review1 e2e fixture already did | RC-029 still observed through `authorized`; assertions unchanged |
| F8 | PRB-003 "no segmentation" tests (`..._dis_block_naming_no_segmentation_is_not_evaluated`, review1 `..._without_the_report_segmentation_is_not_evaluated`) | Now assert **400**, "nothing was sent", no model call, nothing authorized; the main-file test also checks that `server_dis_assessment(None, …)` is still "not evaluated" | Contract changed by CAPA-014 (REQ-SEC-022 (a)): a request without the report's segmentation is refused before anything is derived or sent — stronger than "sent as not evaluated". Names kept (records cite them) |
| F9 | PRB-003 notice test (`test_rc072_report_draft_ends_with_the_not_evaluated_notice_in_its_language`) | `ai_text` starts with the model's text and carries the notice after it; `content` starts with the fixed AI heading and ends with `ai_text` (was `content.startswith("draft body")`) | Contract changed by CAPA-014 (RC-066: the single text starts with the fixed heading); the notice is still checked after the model's text, in its language, in both fields |

## 5. Documents — version sequence on the integrated tree

| Document | Versions (all DRAFT, PENDING owner approval) | Last approved |
|---|---|---|
| SRS-001 | 1.11 #67 · 1.12 #65 · 1.13 #68 · **1.14 integration** (REQ-SEC-021 (f)) | 1.10 |
| RMF-001 | 1.13 #67 · 1.14 #65 · 1.15 #68 · **1.16 integration** (RC-064) | 1.12 |
| TM-001 | 1.10 #67 · 1.11 #65 · 1.12 #68 · **1.13 integration** (tests) | 1.9 |
| DD-001 | 1.2 #67 · 1.3 #68 · **1.4 integration** (DD-RPT-001) | 1.1 |
| CAPA records | CAPA-014 (+ §12, D-10), CAPA-015, CAPA-016; PRB-002, PRB-003 unchanged | — |
| `rc_test_manifest.json` | 70 controls (RC-064..072 added); the manifest gate passes | — |

## 6. Verification on the integrated tree

All backend runs offline: `GOOGLE_APPLICATION_CREDENTIALS` = a missing file, `CLOUDSDK_CONFIG` = an empty folder,
`GOOGLE_CLOUD_PROJECT=mstool-offline-tests`, `ANTHROPIC_API_KEY` unset, plus #66's guard in conftest.

| Check | Result |
|---|---|
| Backend unit (`tests/unit`, as CI) | **2087 passed, 0 failed** (2048 before the review of #69; +17 review tests, +1 draft-assembly test, +3 capture tests, +6 second-review tests, +12 plural tests, +4 final-check tests) |
| Backend integration (CI selection: not PACS / GCS / Firestore) | **25 passed, 1 failed, 20 deselected** — the failure is the known local one (`test_webauthn_credentials_endpoint_exists`: `webauthn` not installed in the local venv; CI installs it) |
| Backend security (CI selection) | **112 passed, 5 xfailed** |
| Manifest gate (`test_risk_control_manifest.py`) | passes (70 controls, every named test file exists and names its control) |
| Frontend vitest (`--pool=threads`) | **482 passed, 3 skipped** (57 files passed, 3 skipped as on `main`; 404 before the review's and the capture session's tests, 413 before the second review's, 440 before the plural tests, 446 before the fallback-colour test, 464 before the final-check tests) |
| Frontend `tsc --noEmit` | clean |
| Frontend production build | passes |

### Negative controls (one script at a time; every source file restored byte for byte; `git status` clean after each)

| Script (PR) | Mutations | Result on the integrated tree | Script change | Record (integrated tree) |
|---|---|---|---|---|
| `prb002_negative_controls.py` (#66) | 19 | **19 detected** — re-run 2026-10-28 on the Windows CRLF checkout | review of #69, item 5: anchors on the LF text, mutations with the file's own line endings, byte-exact restore, hash on the LF text | `RELEASE-2026-10-25_PRB-002_negative_controls.json` |
| `capa015_negative_controls.py` (#65) | 108 | **107 detected, 1 declared equivalent** (R9 — the same mutation #65's record declares equivalent; R9b, which removes both protections, is detected) — run 2026-10-25; not repeated after the review: no CAPA-015 file and no bound test changed | none | `RELEASE-2026-10-25_CAPA-015_negative_controls.json` |
| `capa014_negative_controls.py` (#67) | 94 | **94 detected** — re-run 2026-10-28, last on the final tree `0ca1967` (2026-10-29; m6: the record's source and locale hashes now include every release change) | P17 only: anchored on the merged builder line (#68's rule replaced #67's branch, merge note 1), and after review item 3 on the one-rule line `if not gate.is_evaluated(dis):`; the mutation still sends a not-evaluated DIS to MET / NOT MET. The first re-run after the review corrections left **M10** undetected (the route now removes format characters before the DIS check, so the draft assembly's own removal had become a second layer); a direct test of the assembly (`test_rc066_release_the_draft_assembly_removes_format_characters_itself`) now detects it | `RELEASE-2026-10-25_CAPA-014_negative_controls.json` |
| `prb003_negative_controls.py` (#68) | 119 | **119 detected** — re-run 2026-10-28 after the review and after the capture corrections, and on the final tree `0ca1967` (2026-10-29) (R2, removal of `authorize_mask_specs`, still detected through the spy in `report_env`) | R4: anchored on the one-rule line (review item 3); F11: anchored on the one awaited DIS read after the confirmation (capture F10); A1: anchored on the assistant's one-rule line (second review, m4); F4 and WF3: anchored on the one confirm call line (final check, §12); mutations unchanged | `RELEASE-2026-10-25_PRB-003_negative_controls.json` |
| `rc029_negative_controls.py` (CAPA-007, pre-existing) | 11 | **11 detected** — run 2026-10-28 | review of #69, item 5: byte-exact restore on a CRLF checkout (it wrote files back with the platform's line endings) | `RELEASE-2026-10-25_RC-029_negative_controls.json` |
| `release_2026_10_25_negative_controls.py` (new) | 59 | **59 detected** — run on the final tree `0ca1967` (2026-10-29) (I6 by design through the start-up failure: the application refuses a 60-minute access token, the module cannot be collected, exit 4 — stated in the record). I2 was redefined after it went undetected once the one rule was in (choosing the raw block alone had become equivalent by construction); it now re-introduces the raw block with its own status-only rule. I13–I21 cover the capture findings, I22–I41 the second review, I42–I45 the plural, I46–I47 the fallback colour (§11), I48–I57 R1 and R2 (§12; I12 anchored inside the geometry branch, n1); a frontend mutation runs its own bound test file | new | `RELEASE-2026-10-25_integration_negative_controls.json` |
| `rc032_negative_controls.py` (CAPA-006, pre-existing; touches `segmentation_regions.py`, `LesionDashboard.tsx`) | 45 | **42 detected, 3 declared equivalent** (B, B2, L5 — the same three its own record declares) — run 2026-10-28, again on the final tree `0ca1967` (2026-10-29) | none | `RELEASE-2026-10-25_RC-032_negative_controls.json` |
| `slice_thickness_negative_controls.py` (CP-SLICE-THICKNESS-001, pre-existing; touches `LesionDashboard.tsx`) | 38 | **38 detected** — run 2026-10-28, again on the final tree `0ca1967` (2026-10-29) | none | `RELEASE-2026-10-25_CP-SLICE-THICKNESS-001_negative_controls.json` |
| `capa008_negative_controls.py` (CAPA-008, pre-existing; touches `LesionDashboard.tsx`) | 17 | **17 detected** — run 2026-10-28, again on the final tree `0ca1967` (2026-10-29) | none | `RELEASE-2026-10-25_CAPA-008_negative_controls.json` |
| `capa010_negative_controls.py` (CAPA-010, pre-existing; touches `ViewerApp.tsx`) | 26 | **25 detected, 1 declared equivalent** (L2 — as its own record declares) — first run on the integrated tree: the final tree `0ca1967` (2026-10-29) | none | `RELEASE-2026-10-25_CAPA-010_negative_controls.json` |
| `capa013_negative_controls.py` (CAPA-013, pre-existing; touches `ai_report.py`, `ms_clinical_server.py`, the locale files) | 66 | **66 detected** — first run on the integrated tree: the final tree `0ca1967` (2026-10-29) | none | `RELEASE-2026-10-25_CAPA-013_negative_controls.json` |
| **Total** | **602** | **597 detected, 5 declared equivalent** (R9 of CAPA-015; B, B2, L5 of RC-032; L2 of CAPA-010 — each as its own record declares) | | |

Not repeated on the final tree, with the reason: CAPA-015 (`capa015_negative_controls.py`) touches the changed locale files only, where new keys were added and no anchored text changed (every anchor still unique; its bound tests pass in the full suites); PRB-002 and RC-029 touch no file the second review changed. CAPA-010 and CAPA-013 had not been run on the integrated tree before although the merges had changed `ViewerApp.tsx` and the report route; both were run on the final tree (rows above). Two first passes (on `21b0df8` and `d3104c3`) were stopped to include the plural and the fallback-colour corrections (§11). After the final check (§12) every affected script ran once more on `0ca1967`, in a throwaway worktree of that commit (the release worktree was not mutated meanwhile); the records were copied here and the throwaway worktree removed.

Notes on the runs:
- The scripts ran one after another (never two at once); after each one every source file was back byte for byte and
  `git status` was clean. The bound tests of each script passed again after the restore (CAPA-015 backend 56 /
  frontend 24, CAPA-014 backend 374 / frontend 13, PRB-003 backend 143 / frontend 36, integration 10; after the
  final check, on `0ca1967`: integration backend 81 / frontend 78 in 12 files, PRB-003 backend 143 / frontend 36,
  CAPA-008 46, slice thickness backend 39 / frontend 46, RC-032 36 / 60 / 6, CAPA-010 47, CAPA-013 backend 52 /
  frontend 18, CAPA-014 backend 375 / frontend 13).
- Each PR's own record in `records/risk_verification/` was left as the PR committed it: the scripts write there, so
  each output was copied to the release-named file above and the PR's record restored from git.
- `prb002_negative_controls.py` compared its anchors without normalising line endings; on this Windows working copy
  (`core.autocrlf=true`, `conftest.py` with CRLF) its first run on 2026-10-25 stopped at the anchor check before any
  mutation and was repeated on an LF working copy. After the review of #69 (item 5) the script matches anchors on the
  LF text and restores the exact bytes; it was re-run on 2026-10-28 **on the CRLF checkout** (record field
  `line_endings_of_checkout: CRLF`): 19/19.
- T22 of CAPA-014 (a quadratic e-mail pattern, re-introduced on purpose) takes about 25 minutes because the runaway
  pattern keeps the processor busy after the 3-second test has failed — as in #67's own record.
- One full frontend run after the second review's corrections had a single failure in CAPA-013's longitudinal
  comparison test under load; it passed alone and in the next full run, with no code changed (timing, not a
  defect; noted for the owner).
- Timestamps in the records are local time; the runs crossed the end of summer time (03:00 CEST → 02:00 CET), so
  later runs can carry earlier clock times.

## 7. Residuals and notes for the owner's review

- Two authorizations of the same segmentation in the report route (C3 (c)) — deliberate, see above.
- ~~A DIS block marked "evaluated" without a yes/no conclusion was judged differently by the route and by the
  prompt / template.~~ Resolved by the review of #69 (item 3, §9): one rule, `dis_review_gate.is_evaluated`.
- Deployment order changed for this release (C3, `DEPLOYMENT_CHECKLIST.md`); CAPA-015 D-4's "backend first" is
  superseded by this plan unless the owner decides otherwise.
- #68's reviewer listed `_dis_services` among the hooks to stub in the CAPA-014 fixture; the fixture stubs the three
  functions that use it and makes `_dis_services` refuse, which is stricter (a test that reached it fails).
- NiiVue's opt-in 2D view and the 3D view load the overlay once per segmentation with a fixed colormap (nothing is
  hidden there) and are not reloaded after a classification (§11, m3). Not changed in this release because PR #71
  (`fix/viewer-display-orientation-prb004`) rewrites NiivueViewer2D and the colour tables; to be handled there.
- The confirmation is refused below a lesion opacity of 25 % and a per-label visibility of 0.1
  (`frontend/src/utils/drawnLabels.ts`): values chosen by the agent so that a lesion is plainly visible; the owner
  may set others (owner decision).
- **The drawn-lesion check runs in the browser** (§12): a direct API call, an old cached client or a modified client
  can record a DIS confirmation without it. The server checks only that the label table the client says it drew
  is the stored one (`drawn_labels_sha256`); that closes R2 and stale-label defects for this client, not a client
  that states the stored table without drawing it. Stated as the RC-071 residual risk in RMF-001 1.16.
- Known pre-existing issue, not changed here: the AI-draft review confirmation (`AiDraftBanner`, RC-047) has no
  drawn-lesion check; the DIS confirmation that must follow it has one.
- R1 refuses the confirmation in the NiiVue and matplotlib render modes, the multi-panel layout and the 3D view;
  making those views draw region colours is left to PR #71.
- The plural correction (§11) changes the text of the Class C `brain_report_service.py` (findings prompt, synthetic
  payloads of the RC-065 allow-list): it needs the independent review of a Class C change like every other one in
  this release. Two counts outside the region counts still print the plural for one (the in-browser FLAMeS card,
  the Spanish longitudinal reader-confirmation text); not changed here.
- **Merging PR #71 after this release** (reported by the coordinator's trial merge of 2026-10-29; not resolved
  here): text conflicts in SRS-001, RMF-001, TM-001, `rc_test_manifest.json` and four frontend imports; and this
  branch still imports `sliceIndexToFraction` (`NiivueViewer2D.tsx`, `niivueWindowLevel.test.ts`), which #71
  removed (its own slice mapping replaces it) — the merge must take #71's version and drop that import and its
  test. This release's `UNLABELLED_FALLBACK_COLOR` and #71's `UNLISTED_LABEL_HEX` are the same cyan; one constant
  can then serve both. To be done by the owner's merge of #71 (owner decision on the order).
- DD-001 1.4: the capture-session sentence (§10) had been written into the approval column of the version row; it
  was moved to the change column with its text unchanged.
- `frontend/node_modules` was reused through a junction to #68's worktree (identical `package-lock.json`); nothing was
  installed.

## 8. Owner decisions and owner-only actions

See the PR description "Owner decisions" and "Owner-only actions" (consolidated from PRB-002 §5/§7, CAPA-015 §9
D-1..D-10, CAPA-014 §9 D-1..D-10, PRB-003 §8 items 1–15 incl. §8.12 and the history-visibility decision, CAPA-016 §8
D-1..D-13).

## 9. Independent integration review of PR #69 at `6d1fde2` — corrections (2026-10-28)

The review found that nothing reviewed was lost in the integration and no blocker or major issue. Its six items were
corrected with the same process: tests written first (`26ecb82`; on the uncorrected code **backend 13 of 17 and
frontend 3 of 4 fail**, the passing cases are positive controls — record
`RELEASE-2026-10-25_review_tests_on_6d1fde2.json`), then the corrections (`269317d`), then the control scripts
(`9c78d2d`). Everything stays PENDING owner approval.

| # | Finding | Correction | Tests / negative controls |
|---|---|---|---|
| 1 | On a segmentation whose regions no radiologist confirmed, #68's `without_region_breakdown` set every lesion's region to "not confirmed", which #67's label check treated as an unlisted label: `[unlisted label 1] = not confirmed` in the prompt and an application note in every unconfirmed draft | `report_payload_guard.py` (RC-064): when `region_status.confirmed` is False the payload carries no region summary and no region in the lesion rows (`regions_confirmed: False`); `brain_report_service.py` (Class C) prints the fixed line "Lesion regions: not confirmed by a radiologist; not given. Do not assign, count or tabulate the lesions by region." and a lesion table without a region column; the line joins the device's own words (new synthetic payload). No placeholder, no note | `test_rc064_release_r1_*` (en/es/de + confirmed positive control); I7, I7b |
| 2 | Zero-width characters (ZWJ, ZWSP) hid a DIS statement from PRB-003's output check, which ran before CAPA-014 removed the format characters | `ai_report.py`: CAPA-014's rule (ZWSP → space, every other format character removed) is applied to the model's text **before** the check; the clinician's typed text is not part of that text and never passes through the check | `test_rc070_release_r2_*` with the reviewer's probe ("dissem‍ination in space … juxta​cortical"), en/es/de; I8 |
| 3 | Two "evaluated" rules: the template and the findings prompt needed "evaluated + a yes/no conclusion", the route (notice, check, regions withheld) only the status | `dis_review_gate.is_evaluated` is **the one rule** (status "evaluated" AND a boolean conclusion); the route, the RC-064 payload's "evaluated" mark, the findings prompt and the template variant all call it, so they cannot disagree. (The assistant's MCP filter keeps its own status check against older backends; it decides nothing in the report.) | `test_rc070_release_r3_*` over seven DIS blocks: route notice, regions, prompt and template agree; I9, I10 |
| 4 | Test gap: the fully real path | `test_rc064_release_r4_*`: CAPA-014's markers in every field and the patient's identifiers through the real route, the real report service and #68's real server-side lesion table and DIS state (in-memory segmentation store, real voxel geometry); only the provider, `authorize_segmentation_id`, `authorize_mask_specs` and the patient store stubbed — unconfirmed (a renamed label carrying a marker) and confirmed (MAGNIMS, classified, confirmed: "DIS Assessment: MET" reaches the model). **0 markers and 0 identifiers reach the provider** in both | — (a test; the confirmed case passed already on 6d1fde2, the unconfirmed case failed through item 1) |
| 5 | `prb002_negative_controls.py` missed every anchor on a Windows CRLF checkout | Anchors matched on the LF text, mutations written with the file's own line endings, exact original bytes restored, conftest hash on the LF text; `rc029_negative_controls.py` wrote files back with the platform's line endings and is now byte-exact too (the other scripts already normalised). Integration mutation I6 is kept; its record states that it is detected **by design** through the start-up failure (the application's start-up check refuses a 60-minute access token, so the test module cannot be collected — exit 4) | PRB-002 re-run **on the CRLF checkout**: 19/19; RC-029 11/11 |
| 6 | A 422 from the server-side lesion table (image geometry unreadable) showed "no measurements" in the report panel | `ai_report.py`: the 422 starts with `GEOMETRY_UNREADABLE_PHRASE` ("The image geometry could not be read; report not generated"); `AIReportPanel.tsx` recognises it and shows `report.geometryUnreadable` (en/es/de); CAPA-008's message is kept for a request without measurements. A backend test checks that server and panel use the same phrase | `test_rc070_release_r6_*`; vitest `AIReportPanel.release20261025.test.tsx` (4 cases); I11 (frontend), I12 |

Script anchors moved by item 3 (mutation unchanged): PRB-003 **R4** and CAPA-014 **P17** now anchor on the builder's
`if not gate.is_evaluated(dis):`.

## 10. Browser capture session of the release build — findings F08, F09, F10, F04 (2026-10-28)

A browser capture session of this release build (offline, local; `mstool-film/assets/app-captures/CAPTURES.md`,
evidence in `findings/` and `logs/`) found defects in the confirmation flow that this release introduces or relies on.
What a radiologist confirms must be drawn on screen, so they block the release (§11 and §12 say exactly what the browser now checks, and what it cannot). Same process: tests written first
(`7c7c70d`: on `c7a06cf` **backend 3 of 3 and frontend 4 of 5 fail**, the passing case is a positive control — record
`RELEASE-2026-10-25_capture_tests_on_c7a06cf.json`), corrections `e9935eb`, scripts `09cd029`. PENDING owner approval.

| # | Finding | Cause | Correction | Tests / negative controls |
|---|---|---|---|---|
| F08 (clinical safety) | After "Auto-Classify Regions", lesions labelled 2–4 (juxtacortical, infratentorial, deep white matter) were not drawn on the 2D image until the study was reopened; a radiologist could confirm without seeing them | The 2D canvas draws from `activeSegmentation.labels` (corrected in §11, m3: NiiVue's views do not use the label table); the classification replaced only `currentSegmentation.metadata.labels`, and only after the mask reload — so only label 1 had a colour | `classify-regions` returns the label scheme it stored; new store action `applyServerLabels` writes it to `currentSegmentation` AND `activeSegmentation`, every region visible, without marking a local edit; `LesionDashboard` calls it BEFORE reloading the mask | vitest `rc070 release f08 …`; backend `test_rc070_release_f09_the_route_returns_the_labels_it_stored`; I13, I14, I16 |
| F09 | The classification removed lesion components smaller than 3 mm³ from the stored mask without telling the user (capture: 29,903 → 29,886 voxels); the radiologist then confirmed a mask that had changed | Every classifier path in the Class C `ms_region_classifier.py` skips components below `MIN_LESION_VOLUME_MM3` and builds the classified mask from zeros | **The Class C module is unchanged.** The `classify-regions` route compares the mask before and after (18-connected components, as the classifier) and returns `removed_small_components` (components, voxels, volume, minimum, reason), also kept in the stored classification record so a later session shows it too. The classification card, the "not evaluated" DIS card and the confirm dialog state it before the radiologist confirms (en/es/de) | backend `test_rc070_release_f09_*` (the REAL geometric classifier drops two one-voxel specks of 1 mm³); vitest `rc070 release f09 …` (card, DIS card, dialog; nothing said when nothing was removed); I15, I17, I18 |
| F10 | After "confirm", the DIS card kept saying "No radiologist has confirmed this segmentation" for 6–12 s with no progress | The card kept the old state while the DIS state of the confirmed mask was being read (the server reads the source image for its voxel geometry) | A pending state replaces the reason line and the button: "Recording your confirmation…" until the server answers, then "Confirmation recorded — reading the DIS result for the confirmed mask…" (role=status) until the one awaited read returns; a failed read says that the confirmation was recorded and to press Analyze | vitest `rc071 release f10 …`; I19, I20; PRB-003 F11 (anchor moved, still detected) |
| F04 | A literal "—" in the per-region rows | Escape sequence in JSX text | `{'—'}` | vitest `rc070 release f04 …`; I21 |

F12 of the capture session (an application note "[unlisted label 1] = not confirmed" in a plain draft) is item 1 of the
integration review, corrected in §9. The other findings of the capture session (F01–F03, F05–F07, F11, F13–F21: e.g.
the native confirm dialog, the login footer's MFA claim, open self-registration, the axial rotation between viewer
modes) were not part of this request and are not addressed in this release; they are listed for the owner in the PR.

## 11. Second independent review of PR #69 (`6d1fde2..dd22708`) — corrections (2026-10-28)

The review found round 1 (§9), F10 and F04 sound, and **1 blocker and 3 majors**. Each finding was reproduced by a test
written before its correction. B1 and M3 were pushed first (`ebf39c3`) because the film's app re-capture runs on this
branch. Everything stays PENDING owner approval.

| Commit | Content |
|---|---|
| `9d5a51f` | Tests first for B1 and M3 (on `dd22708`: **frontend 12 of 14 fail**; `drawnLabels.test.ts` does not load — the module did not exist) — record `RELEASE-2026-10-25_review2_b1_m3_tests_on_dd22708.json` |
| `ebf39c3` | Corrections of B1 and M3 (pushed and announced first) |
| `30d9067` | Tests first for M1, M2, m1, m2, m4, m5, m7, n1 (on `ebf39c3`: **backend 4 of 6, frontend 8 of 9 fail**; the passing cases are positive controls or gaps of correct code) — record `RELEASE-2026-10-25_review2_rest_tests_on_ebf39c3.json` |
| `38494ed` | Corrections of M1, M2, m1, m2, m3, m4, m5, n1 |
| `21b0df8` | Negative controls I22–I41; PRB-003 A1 and integration I12 anchors moved |
| `40f1d5c`, `197b918` | Film capture "DWM: 1 lesions": tests written first (on `21b0df8`: **frontend 6 of 6, backend 1 of 12 fail**; the other 11 are positive controls — the second commit only extends the allow-list cases before the correction) — record `RELEASE-2026-10-25_plural_tests_on_21b0df8.json` |
| `a8ca653` | Correction of the plural (below) |
| `d3104c3` | Negative controls I42–I45 |
| `9c16548` | Re-review of PR #71: test written first for the fallback colour (on `d3104c3`: **frontend 5 of 18 fail**; the other 13 are positive controls) — record `RELEASE-2026-10-25_fallback_colour_tests_on_d3104c3.json` |
| `1c66562` | Fallback colour cyan, not magenta (below) |
| `b3a376e` | Negative controls I46, I47 |

| # | Finding | Correction | Tests / negative controls |
|---|---|---|---|
| **B1** (blocker) | F08 still reachable: the sidebar list (`['segmentations','study',studyId]`) was never refreshed by the classification, and the viewer opened (and reopened) a segmentation from it — after close/reopen, or after classifying a segmentation that was not open, only label 1 was drawn while the mask held 1–4, and the confirmation was offered and accepted | (1) the classification invalidates every `['segmentations', …]` cache; (2) `ViewerApp` opens a segmentation from `getSegmentation()` (the server), every time — a segmentation the server cannot return is not opened; (3) the 2D canvas draws any mask value the label table does not name in a fallback colour (cyan, never transparent; first magenta, corrected below) and the overlay controls warn ("Mask value(s) … have no label"); (4) the browser refuses the confirmation unless every value present in the open mask is drawn on the 2D canvas (M3 below; §12 adds the view on screen and the stored labels) | `ViewerApp.release20261028.test.tsx` (real viewer page: open, close/reopen, server failure, warning); `LesionDashboard.release20261028b.test.tsx` (cache invalidation); `drawnLabels.test.ts`; I22–I26 |
| **M3** (pre-existing) | A label's eye toggle, the overlay switch or a lesion opacity of 0 (kept across sessions) let a radiologist confirm with lesions hidden | Confirm refuses, before any dialog or request, with a message per reason, while any value of the open mask has no label, is hidden, is too faint, the overlay is off, the lesion opacity is below 25 %, or the open mask cannot be read (`utils/drawnLabels.ts`, `maskValuesCallback`); a stored opacity below 25 % is not restored in a new session (persist `merge`) | `LesionDashboard.release20261028b.test.tsx` (5 refusals + positive control); `useSegmentationStore.release20261028.test.ts`; I26–I30 |
| **M1** | The F09 notice was read from the OPEN segmentation's `analysis_data` in every dashboard, and `patchAnalysisData` wrote into it whatever the dashboard showed | `dis_review_gate.regions_state` serves `removed_small_components` only while the classification record describes the current lesions; the DIS card and the confirm dialog take it from the server's DIS state of the dashboard's own segmentation; the auto-populate effect and `patchAnalysisData` are guarded by `segmentation_id` | backend `test_rc070_release2_m1_*`; vitest `rc070 release2 m1 …` (3); I31–I34 |
| **M2** | A second classification started from the cleaned mask, recorded 0 and overwrote the stored figure | `classify-regions` carries the earlier removal forward when the "before" mask has the previously classified footprint (`includes_earlier_classifications`); a saved mask with other lesions starts again | backend `test_rc070_release2_m2_*` (2); I35 |
| m1 | A failed mask reload after classify was silent | The reload result is checked: an error is shown and the confirmation is refused until the segmentation is reopened | vitest `rc071 release2 m1 …`; I36 |
| m2 | Classify reloaded the open mask and discarded its unsaved edits (also from another dashboard) | Auto-Classify only on the open segmentation without unsaved changes (button disabled with a message; the handler checks it too). This also removes the "classify while not open" path of B1 | vitest `rc070 release2 m2 …` (2); I37 |
| m3 | The comment and §10 said NiiVue draws from the label table | Corrected: only the 2D canvas uses the label table. NiiVue's opt-in 2D view and the 3D view load the overlay once per segmentation with a fixed colormap (nothing hidden there) and are not reloaded after a classification; not changed here because PR #71 (`fix/viewer-display-orientation-prb004`) rewrites NiivueViewer2D and the colour tables — overlap noted | — |
| m4 | "Evaluated" was still decided by the status alone in the viewer (`isDisEvaluated`) and the assistant | Both require a boolean `dis_met`, as `dis_review_gate.is_evaluated`; the assistant mirrors the rule instead of importing the gate (it reaches the backend over HTTP and stays free of the gate's storage dependencies) | vitest `rc070 release2 m4 …`; backend `test_rc070_release2_m4_*`; I38, I39; PRB-003 A1 (anchor moved) |
| m5 | A failed read-back after a recorded confirmation left "No radiologist has confirmed" and the confirm button | "Your confirmation was recorded, but the DIS result could not be read; press Analyze …" replaces the reason line and the button until the next read | vitest `rc071 release2 m5 …`; I40 |
| m6 | The CAPA-014 record's locale hashes predated `e9935eb` | CAPA-014 negative controls re-run on the final tree (§6) | record `RELEASE-2026-10-25_CAPA-014_negative_controls.json` |
| m7 | Test gaps | Reopen and server failure (ViewerApp), classify-while-not-open (now refused, m2), reload failure (m1), anisotropic F09 (3 × 0.5 × 0.4 mm, `test_rc070_release2_m7_*`), F10 failure paths (refused POST never says "recorded"; m5) | as listed |
| n1 | Every lesion-table failure was reported as "image geometry" | Only `VoxelSpacingUnavailableError` gives the geometry phrase; any other failure gives `LESION_TABLE_FAILED_PHRASE` with its error type; the report panel shows its own message for each | backend `test_rc070_release2_n1_*`; I41 |

Fixture changes (no assertion changed): the confirm tests of #68 and of the capture round seed the open mask they
confirm (its values drawn), as the guard requires; the capture F09 test serves the removal in the server's DIS state
(M1 contract); the PRB-003 assistant test's evaluated block carries `dis_met`, as the server's does (m4).

Not reachable from a test: the canvas's own call of the fallback colours (jsdom has no 2D canvas); its helper is
tested (I24) and the film's capture checks the drawing.

**Re-review of PR #71 (2026-10-29): the fallback colour.** B1's fallback colour was magenta (`#FF00FF`), and its comment said no preset used it — it is the MAGNIMS "Active (Gd+)" label colour, so a mask value without a label looked exactly like an active, gadolinium-enhancing lesion. Corrected (`1c66562`): `UNLABELLED_FALLBACK_COLOR` is cyan `#00FFFF`, the colour PR #71 uses for the same purpose in the GPU and 3D views (`UNLISTED_LABEL_HEX`); the warnings of the overlay controls and of the refused confirmation say cyan / cian / Cyan; comment corrected. Test `drawnLabels.fallback.test.ts` (18): cyan, more than 100 RGB units from every preset label colour (default and MAGNIMS) and every MAGNIMS zone colour of the canvas, warnings naming it in en/es/de; I46, I47.

**Film capture of the release build (same day): "DWM: 1 lesions".** The region summary in the sidebar showed
"DWM: 1 lesions" (plural with a count of one, and in English only), and the report text had the same pattern because
the findings prompt gave the model "Deep White Matter: 1 lesions, …". Corrected (`a8ca653`):

| Where | Correction | Tests / negative controls |
|---|---|---|
| `LesionDashboard.tsx` — deep-white-matter count of the evaluated DIS card; lesion count of the lesion table | `lesions.dwmCountOne/Other` and `lesions.countOne/Other` in en/es/de: the One text for exactly one (the CLDR "one" category of all three languages), the Other text for any other count | vitest `rc070 release plural …` (6: en/es/de × 1 and 2); I42, I43 |
| `brain_report_service.py` (**Class C**, text only) — regional summary, individual lesion data, longitudinal counts of the findings prompt | "1 lesion" / "N lesions" (`_lesions`); the synthetic payloads of the RC-065 allow-list print both forms, with and without the region column, so the tripwire keeps every word and word pair the device can write | `test_release_2026_10_25_plural_counts.py` (12); I44, I45 |

Other counts with a noun were checked: the remaining ones are written as fractions ("1/3 regions") or with "(s)"
("lesion component(s)", "region correction(s)") and read correctly for one. Not changed (outside the region counts):
the in-browser FLAMeS card's "N lesions" and the longitudinal reader-confirmation text ("{{n}} lesiones nuevas"),
listed for the owner.

The control chain that had started on `21b0df8` (integration 43/43; PRB-003 stopped after 67 of 119 mutations, all
detected) was stopped to include this correction, so every script ran once on the final tree; the one source line
the stopped run had left mutated (`AIReportPanel.tsx`) was restored from git before anything else, and `git status`
was clean.

## 12. Final check of PR #69 (`dd22708..39d9730`) — R1 and R2 of the confirmation guard (2026-10-29)

The final check found B1, M1, M2, M3 and the minor items fixed, the `brain_report_service.py` change text only, and no
blocker. It found **two major gaps in the confirmation guard** of §11. Both were reproduced by tests written before the
correction (`1d3c495`: on `39d9730` **backend 3 of 4 and frontend 17 of 18 fail**; the passing cases are positive
controls — record `RELEASE-2026-10-25_final_check_tests_on_39d9730.json`); correction `a11b648`; controls and anchors
`0ca1967`. PENDING owner approval.

**What the guard checks now** (it replaces the wording of §11, which said more than the code did). Before any dialog or
request, the browser refuses the DIS confirmation unless:
- the view on screen is the standard 2D view (one panel, standard render mode) in segmentation mode, drawing this
  segmentation (R1);
- every value present in the open mask has a label there, is not hidden with its eye toggle and is not too faint; the
  overlay is on and the lesion opacity is at least 25 % (M3);
- on a classified segmentation, each of those values is drawn with the label the server stored for it — same name and
  colour (R2).

It does not record what the radiologist looked at. It runs in the browser, so a direct API call, an old cached
client or a modified client skips it. The server checks only one part: the label table the client says it drew must
be the stored one (below).

| # | Finding | Correction | Tests / negative controls |
|---|---|---|---|
| **R1** (major) | The guard read the 2D canvas settings, not the view on screen. With "Segmentation mode" off while the segmentation was open, or in the multi-panel, 3D, NiiVue or matplotlib views, nothing was drawn (or every lesion plain red, or the overlay loaded before the classification), and Confirm was accepted | The standard 2D view (`ImageViewer2D`), in the standard render mode and segmentation mode, with an image, publishes the segmentation it draws (`overlayOnScreen` in the segmentation store); every other state, and every other view (it is then not mounted), publishes nothing. Confirm is refused unless it is this dashboard's segmentation: "The view on screen does not draw this segmentation with its region labels. Switch to the Standard view (2D, one panel) with Segmentation mode on to confirm." (en/es/de). The other views are not changed to draw region colours (PR #71's area) | `ViewerApp.release20261029.test.tsx` (real viewer page: published in the standard view; nothing with segmentation mode off, NiiVue, matplotlib, 3D, multi-panel, closed); `LesionDashboard.release20261029.test.tsx` (2 refusals); I48–I50 |
| **R2** (major) | Switching the label preset to "Default" redrew the MAGNIMS values with other names and colours (juxtacortical lesions gold as "MS Lesion (Chronic)"; deep white matter purple, the "Black Hole (T1)" colour), and Confirm was accepted | (a) the preset switch is locked while a classified segmentation is open (a classification record, and ids 1–4 named as the regions), with a note; (b) on a classified segmentation the guard compares each value present with the label table the server stored — the DIS state now serves it (`regions.stored_labels`) — and refuses on any difference of name or colour, naming the value, or when that table could not be read | `ViewerApp.release20261029.test.tsx` (lock + unclassified positive control); `LesionDashboard.release20261029.test.tsx` (the reviewer's preset path, one colour changed, table not read, positive control); I51–I53 |
| Server (partial safeguard) | The confirmation route could not know what was drawn | The confirmation sends `drawn_labels_sha256`: SHA-256 of `[[id, name, colour], …]` by id, colours upper case, background left out — the same canonical text in `dis_review_gate.drawn_labels_sha256` and `utils/drawnLabels.ts` (`drawnLabelsSha256`, Web Crypto). The route refuses (409) a missing or different table. This closes R2 and stale-label defects for this client; it cannot catch a client that states the stored table without drawing it | `test_release_2026_10_25_final_check.py` (shared vector `72bdfec9…`, stored table served, missing / Default / other table refused, stored table recorded); `drawnLabels.digest.test.ts` (node: the same vector, order and colour case, the request body); I54–I57 |

Fixtures (no assertion removed): the confirm tests seed the standard view drawing the open segmentation and, in the
server's DIS state, the stored label table; the two exact-argument assertions of #68's tests also name the label table
the call now carries; the capture round's F09 and F10 confirm tests draw the classified segmentation with the labels
the server stored (they drew binary labels on a classified segmentation, which R2 now refuses); the PRB-003 backend
confirm requests state the label table read from the server (`_drawn`). The "stored labels could not be read" case of
the new dashboard test was corrected after its failing-first record (an explicit `undefined` took the default table);
it failed on `39d9730` either way. PRB-003 F4 and WF3 anchor on the one confirm call line; their mutations are
unchanged.

**Known pre-existing issue, not changed here:** the AI-draft review confirmation (`AiDraftBanner`, RC-047) has no
drawn-lesion check. The DIS confirmation that must follow it has one.

*Drafted by the AI coding agent (development tool, SDP-001 §5.1.4). No approval is recorded in this document;
approvals are to be recorded by the owner (CAPA-012).*
