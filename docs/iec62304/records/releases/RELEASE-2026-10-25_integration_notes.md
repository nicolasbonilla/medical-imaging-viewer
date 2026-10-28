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
| (records commit) | §6 and §10 of these notes, capture-round control records, document rows, manifest |

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
| Backend unit (`tests/unit`, as CI) | **2069 passed, 0 failed** (2048 before the review of #69; +17 review tests, +1 draft-assembly test, +3 capture tests) |
| Backend integration (CI selection: not PACS / GCS / Firestore) | **25 passed, 1 failed, 20 deselected** — the failure is the known local one (`test_webauthn_credentials_endpoint_exists`: `webauthn` not installed in the local venv; CI installs it) |
| Backend security (CI selection) | **112 passed, 5 xfailed** |
| Manifest gate (`test_risk_control_manifest.py`) | passes (70 controls, every named test file exists and names its control) |
| Frontend vitest (`--pool=threads`) | **413 passed, 3 skipped** (47 files passed, 3 skipped as on `main`; 404 before the review's and the capture session's tests) |
| Frontend `tsc --noEmit` | clean |
| Frontend production build | passes |

### Negative controls (one script at a time; every source file restored byte for byte; `git status` clean after each)

| Script (PR) | Mutations | Result on the integrated tree | Script change | Record (integrated tree) |
|---|---|---|---|---|
| `prb002_negative_controls.py` (#66) | 19 | **19 detected** — re-run 2026-10-28 on the Windows CRLF checkout | review of #69, item 5: anchors on the LF text, mutations with the file's own line endings, byte-exact restore, hash on the LF text | `RELEASE-2026-10-25_PRB-002_negative_controls.json` |
| `capa015_negative_controls.py` (#65) | 108 | **107 detected, 1 declared equivalent** (R9 — the same mutation #65's record declares equivalent; R9b, which removes both protections, is detected) — run 2026-10-25; not repeated after the review: no CAPA-015 file and no bound test changed | none | `RELEASE-2026-10-25_CAPA-015_negative_controls.json` |
| `capa014_negative_controls.py` (#67) | 94 | **94 detected** — re-run 2026-10-28 | P17 only: anchored on the merged builder line (#68's rule replaced #67's branch, merge note 1), and after review item 3 on the one-rule line `if not gate.is_evaluated(dis):`; the mutation still sends a not-evaluated DIS to MET / NOT MET. The first re-run after the review corrections left **M10** undetected (the route now removes format characters before the DIS check, so the draft assembly's own removal had become a second layer); a direct test of the assembly (`test_rc066_release_the_draft_assembly_removes_format_characters_itself`) now detects it | `RELEASE-2026-10-25_CAPA-014_negative_controls.json` |
| `prb003_negative_controls.py` (#68) | 119 | **119 detected** — re-run 2026-10-28 after the review and again after the capture corrections (R2, removal of `authorize_mask_specs`, still detected through the spy in `report_env`) | R4: anchored on the one-rule line (review item 3); F11: anchored on the one awaited DIS read after the confirmation (capture F10); mutations unchanged | `RELEASE-2026-10-25_PRB-003_negative_controls.json` |
| `rc029_negative_controls.py` (CAPA-007, pre-existing) | 11 | **11 detected** — run 2026-10-28 | review of #69, item 5: byte-exact restore on a CRLF checkout (it wrote files back with the platform's line endings) | `RELEASE-2026-10-25_RC-029_negative_controls.json` |
| `release_2026_10_25_negative_controls.py` (new) | 23 | **23 detected** — run 2026-10-28 after the capture corrections (I6 by design through the start-up failure: the application refuses a 60-minute access token, the module cannot be collected, exit 4 — stated in the record). I2 was redefined after it went undetected once the one rule was in (choosing the raw block alone had become equivalent by construction); it now re-introduces the raw block with its own status-only rule. I13–I21 cover the capture findings | new | `RELEASE-2026-10-25_integration_negative_controls.json` |
| `rc032_negative_controls.py` (CAPA-006, pre-existing; touches `segmentation_regions.py`, `LesionDashboard.tsx`) | 45 | **42 detected, 3 declared equivalent** (B, B2, L5 — the same three its own record declares) — run 2026-10-28 | none | `RELEASE-2026-10-25_RC-032_negative_controls.json` |
| `slice_thickness_negative_controls.py` (CP-SLICE-THICKNESS-001, pre-existing; touches `LesionDashboard.tsx`) | 38 | **38 detected** — run 2026-10-28 | none | `RELEASE-2026-10-25_CP-SLICE-THICKNESS-001_negative_controls.json` |
| `capa008_negative_controls.py` (CAPA-008, pre-existing; touches `LesionDashboard.tsx`) | 17 | **17 detected** — run 2026-10-28 | none | `RELEASE-2026-10-25_CAPA-008_negative_controls.json` |
| **Total** | **474** | **470 detected, 4 declared equivalent** (R9 of CAPA-015; B, B2, L5 of RC-032 — each as its own record declares) | | |

Not repeated after the capture corrections, with the reason: CAPA-015, CAPA-014 and CAPA-013 (`capa013_negative_controls.py`, 66 mutations) touch the changed locale files only, where new keys were added and no anchored text changed; their bound tests pass in the full suites. Every anchor of these scripts is still unique.

Notes on the runs:
- The scripts ran one after another (never two at once); after each one every source file was back byte for byte and
  `git status` was clean. The bound tests of each script passed again after the restore (CAPA-015 backend 56 /
  frontend 24, CAPA-014 backend 374 / frontend 13, PRB-003 backend 143 / frontend 36, integration 10).
- Each PR's own record in `records/risk_verification/` was left as the PR committed it: the scripts write there, so
  each output was copied to the release-named file above and the PR's record restored from git.
- `prb002_negative_controls.py` compared its anchors without normalising line endings; on this Windows working copy
  (`core.autocrlf=true`, `conftest.py` with CRLF) its first run on 2026-10-25 stopped at the anchor check before any
  mutation and was repeated on an LF working copy. After the review of #69 (item 5) the script matches anchors on the
  LF text and restores the exact bytes; it was re-run on 2026-10-28 **on the CRLF checkout** (record field
  `line_endings_of_checkout: CRLF`): 19/19.
- T22 of CAPA-014 (a quadratic e-mail pattern, re-introduced on purpose) takes about 25 minutes because the runaway
  pattern keeps the processor busy after the 3-second test has failed — as in #67's own record.
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
The radiologist must see exactly what they confirm, so they block the release. Same process: tests written first
(`7c7c70d`: on `c7a06cf` **backend 3 of 3 and frontend 4 of 5 fail**, the passing case is a positive control — record
`RELEASE-2026-10-25_capture_tests_on_c7a06cf.json`), corrections `e9935eb`, scripts `09cd029`. PENDING owner approval.

| # | Finding | Cause | Correction | Tests / negative controls |
|---|---|---|---|---|
| F08 (clinical safety) | After "Auto-Classify Regions", lesions labelled 2–4 (juxtacortical, infratentorial, deep white matter) were not drawn on the 2D image until the study was reopened; a radiologist could confirm without seeing them | The 2D canvas and NiiVue draw from `activeSegmentation.labels`; the classification replaced only `currentSegmentation.metadata.labels`, and only after the mask reload — so only label 1 had a colour | `classify-regions` returns the label scheme it stored; new store action `applyServerLabels` writes it to `currentSegmentation` AND `activeSegmentation`, every region visible, without marking a local edit; `LesionDashboard` calls it BEFORE reloading the mask | vitest `rc070 release f08 …`; backend `test_rc070_release_f09_the_route_returns_the_labels_it_stored`; I13, I14, I16 |
| F09 | The classification removed lesion components smaller than 3 mm³ from the stored mask without telling the user (capture: 29,903 → 29,886 voxels); the radiologist then confirmed a mask that had changed | Every classifier path in the Class C `ms_region_classifier.py` skips components below `MIN_LESION_VOLUME_MM3` and builds the classified mask from zeros | **The Class C module is unchanged.** The `classify-regions` route compares the mask before and after (18-connected components, as the classifier) and returns `removed_small_components` (components, voxels, volume, minimum, reason), also kept in the stored classification record so a later session shows it too. The classification card, the "not evaluated" DIS card and the confirm dialog state it before the radiologist confirms (en/es/de) | backend `test_rc070_release_f09_*` (the REAL geometric classifier drops two one-voxel specks of 1 mm³); vitest `rc070 release f09 …` (card, DIS card, dialog; nothing said when nothing was removed); I15, I17, I18 |
| F10 | After "confirm", the DIS card kept saying "No radiologist has confirmed this segmentation" for 6–12 s with no progress | The card kept the old state while the DIS state of the confirmed mask was being read (the server reads the source image for its voxel geometry) | A pending state replaces the reason line and the button: "Recording your confirmation…" until the server answers, then "Confirmation recorded — reading the DIS result for the confirmed mask…" (role=status) until the one awaited read returns; a failed read says that the confirmation was recorded and to press Analyze | vitest `rc071 release f10 …`; I19, I20; PRB-003 F11 (anchor moved, still detected) |
| F04 | A literal "—" in the per-region rows | Escape sequence in JSX text | `{'—'}` | vitest `rc070 release f04 …`; I21 |

F12 of the capture session (an application note "[unlisted label 1] = not confirmed" in a plain draft) is item 1 of the
integration review, corrected in §9. The other findings of the capture session (F01–F03, F05–F07, F11, F13–F21: e.g.
the native confirm dialog, the login footer's MFA claim, open self-registration, the axial rotation between viewer
modes) were not part of this request and are not addressed in this release; they are listed for the owner in the PR.

*Drafted by the AI coding agent (development tool, SDP-001 §5.1.4). No approval is recorded in this document;
approvals are to be recorded by the owner (CAPA-012).*
