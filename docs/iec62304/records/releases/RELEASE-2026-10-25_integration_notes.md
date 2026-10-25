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
| (records commit) | These notes, the integrated-tree negative-control records, the manifest's negative-control fields (RC-064..072), CAPA-015 D-4 note |

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
| Backend unit (`tests/unit`, as CI) | **2048 passed, 0 failed** |
| Backend integration (CI selection: not PACS / GCS / Firestore) | **25 passed, 1 failed, 20 deselected** — the failure is the known local one (`test_webauthn_credentials_endpoint_exists`: `webauthn` not installed in the local venv; CI installs it) |
| Backend security (CI selection) | **112 passed, 5 xfailed** |
| Manifest gate (`test_risk_control_manifest.py`) | passes (70 controls, every named test file exists and names its control) |
| Frontend vitest (`--pool=threads`) | **404 passed, 3 skipped** (45 files passed, 3 skipped — as on `main`) |
| Frontend `tsc --noEmit` | clean |
| Frontend production build | passes |

### Negative controls (one script at a time; every source file restored byte for byte; `git status` clean after each)

| Script (PR) | Mutations | Result on the integrated tree | Script change | Record (integrated tree) |
|---|---|---|---|---|
| `prb002_negative_controls.py` (#66) | 19 | **19 detected** | none | `RELEASE-2026-10-25_PRB-002_negative_controls.json` |
| `capa015_negative_controls.py` (#65) | 108 | **107 detected, 1 declared equivalent** (R9 — the same mutation #65's record declares equivalent; R9b, which removes both protections, is detected) | none | `RELEASE-2026-10-25_CAPA-015_negative_controls.json` |
| `capa014_negative_controls.py` (#67) | 94 | **94 detected** | P17 only: its anchor (#67's own not-evaluated branch of the prompt builder) no longer exists because #68's rule replaced it (merge note 1); the anchor is now the merged builder line, and the mutation still sends a not-evaluated DIS to MET / NOT MET (5 tests fail) | `RELEASE-2026-10-25_CAPA-014_negative_controls.json` |
| `prb003_negative_controls.py` (#68) | 119 | **119 detected** (R2, removal of `authorize_mask_specs`, still detected through the spy in `report_env`) | none | `RELEASE-2026-10-25_PRB-003_negative_controls.json` |
| `release_2026_10_25_negative_controls.py` (new) | 7 | **7 detected** (I1, I1b, I2, I3, I4, I5 by their tests; I6 by the suite failing to collect, because the application's start-up check refuses the 60-minute lifetime — exit 4) | new | `RELEASE-2026-10-25_integration_negative_controls.json` |
| **Total** | **347** | **346 detected, 1 declared equivalent** | | |

Notes on the runs:
- The scripts ran one after another (never two at once); after each one every source file was back byte for byte and
  `git status` was clean. The bound tests of each script passed again after the restore (CAPA-015 backend 56 /
  frontend 24, CAPA-014 backend 374 / frontend 13, PRB-003 backend 143 / frontend 36, integration 10).
- Each PR's own record in `records/risk_verification/` was left as the PR committed it: the scripts write there, so
  each output was copied to the release-named file above and the PR's record restored from git.
- `prb002_negative_controls.py` compares its anchors without normalising line endings; this Windows working copy
  (`core.autocrlf=true`) checks `conftest.py` out with CRLF, so its first run stopped at the anchor check before any
  mutation. It was re-run on an LF working copy of the same committed content (`git diff HEAD` empty; the record's
  `conftest_sha256` is that of the committed file). The script is unchanged.
- T22 of CAPA-014 (a quadratic e-mail pattern, re-introduced on purpose) takes about 25 minutes because the runaway
  pattern keeps the processor busy after the 3-second test has failed — as in #67's own record.
- Timestamps in the records are local time; the runs crossed the end of summer time (03:00 CEST → 02:00 CET), so
  later runs can carry earlier clock times.

## 7. Residuals and notes for the owner's review

- Two authorizations of the same segmentation in the report route (C3 (c)) — deliberate, see above.
- A server-derived DIS block marked "evaluated" but without a yes/no conclusion would reach the model as not
  evaluated with the not-evaluated template (I-2), but the route's notice and output check (keyed on the route's own
  "evaluated" test) would not run for it. It cannot arise from the server's DIS computation (`assess_dis` always
  returns a boolean conclusion); recorded, not changed.
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

*Drafted by the AI coding agent (development tool, SDP-001 §5.1.4). No approval is recorded in this document;
approvals are to be recorded by the owner (CAPA-012).*
