# RELEASE-2026-10-30 — integration notes (`release/owner-signoff-2026-10-30`): #69 + #71

**Status: DRAFT for the owner's single sign-off. PENDING owner approval.** Nothing was merged to `main`, nothing was
deployed, nothing was signed. No cloud service, no Firestore, no model provider and no GCP project was contacted; every
backend run was offline per PRB-002. Every approval field in every document still reads "PENDING owner approval".

Prepared by the AI coding agent (release integrator) on 2026-10-30.

## 1. What this branch is, and what it supersedes

`release/owner-signoff-2026-10-30` = `release/owner-signoff-2026-10-25` @ `33f9425` (PR #69: #66 PRB-002, #65 CAPA-015,
#67 CAPA-014, #68 PRB-003 / CAPA-016, found READY for owner sign-off at `0e1ee22`, plus the L4 wording of its last
check) + PR #71 (`fix/viewer-display-orientation-prb004` @ `79a9010`: PRB-004 .. PRB-010, viewer display, orientation
and region colours) merged with `git merge --no-ff` (no rebase, so every reviewed commit and every hash cited in the
records stays valid).

**Since 2026-10-30 the branch also contains `main` after PR #70 (owner-signed; §7).** **It supersedes merging #69 and #71 separately:** the two conflict (documents, manifest, four frontend imports, a
removed helper), and their safety checks interact (below). The owner signs and merges this branch once; #69 and #71
can then be closed as merged here. **PR #70 stays separate** (urgent; not part of this branch).

| Commit | Content |
|---|---|
| `b0aae45` | Merge of #71 (`79a9010`) — conflicts resolved (§2) |
| `53c1e57` | Tests written first for the integration decisions (§3; on `b0aae45`: **backend 3 of 3, frontend 1 of 4 fail**; the 3 others are a contract test that passes by design — record `RELEASE-2026-10-30_merge_tests_on_b0aae45.json`) |
| `5da4c95` | Integration decisions (§3) and test adaptations to #71's display contract (§4) |
| `04fd105` | Negative-control scripts: integration I58, I59; I46, I54 and CAPA-009 O2 re-anchored |
| `530b953` | CAPA-009 O2: the original two-edit mutation restored (the first re-anchor kept the authorization and went undetected; §5) |
| (records commit) | These notes, the merged-tree control records, document versions and rows, manifest |

## 2. Conflicts and how each was resolved

| File | Resolution |
|---|---|
| `ImageViewer3D.tsx`, `LesionDashboard.tsx`, `SegmentationCanvasLocal.tsx`, `useSegmentationStore.ts` (imports) | Both sides kept: the release's session / drawn-label helpers (CAPA-015 `fetchWithSession`, `getAccessToken`; `drawnLabels`) and #71's grid / region-colour helpers (`niivueVoxelGrid`, `regionColors`, `maskLabelColormap`, `maskDisplayLayout`) |
| `NiivueViewer2D.tsx` (imports) | #71's `sliceIndexToVoxelCentreFraction` replaces `sliceIndexToFraction`, which #71 removed (the stale import was dropped); CAPA-015's `fetchWithSession` kept (the merged body already uses it). `niivueWindowLevel.test.ts` merged without a conflict: #71's slice block, no stale import left |
| SRS-001, RMF-001, TM-001 (version rows) | The release's rows, then #71's: SRS 1.11–1.14 then 1.15; RMF 1.13–1.16 then 1.17; TM 1.10–1.13 then 1.14 (#71 had numbered its versions after the release's). The version headers now name the latest version |
| RMF-001 §3 | §3.6, §3.7 (release) then §3.8 (#71, which had reserved 3.6 / 3.7 for the release) |
| SRS-001 §3 | REQ-SAFE-038..040 (release) then REQ-SAFE-041..043 (#71) |
| TM-001 (test rows, test files) | The rows of both |
| `rc_test_manifest.json` | RC-064..072 (release) then RC-073..076 (#71): 74 controls, valid JSON; the manifest gate passes |

`capa_register.md`, the locale files, `ViewerApp.tsx`, `ImageViewer2D.tsx` and `types/segmentation.ts` merged without a
conflict and were checked: the two sides' keys / rows / changes are all present.

## 3. Integration decisions (tests written first)

**(a) The drawn-label check (#69, R2) and #71's display colours.** #71 (PRB-010) draws a label named after a MAGNIMS
region in the shared region colour, whatever colour was stored with it (`withRegionColors`; segmentations classified
before #71 store red / green / blue / gold). #69's confirmation check compares the labels drawn with the label table
of the DIS state, and the server compares the digest of the table the client drew with the stored table. As merged,
every segmentation classified before #71 would have been refused (drawn orange, stored red), and a client stating
colours the viewer never draws would have passed. Now the server serves and checks the stored table **as the viewer
draws it**: `dis_review_gate.stored_labels` applies `MAGNIMS_REGION_LABEL_COLORS` (the backend side of
`withRegionColors`; #71's test keeps the two equal), the route compares the client's digest with that table, and
`drawn_labels_sha256` stays a pure digest of the table given (the shared vector of #69's tests is unchanged).
Tests: `test_release_2026_10_30_merge.py` (served as drawn; drawn in region colours → recorded; colours the viewer
never draws → refused), `LesionDashboard.release20261030.test.tsx` (opened through the store's real path; confirmed
against the table as drawn; refused against colours not drawn); controls I58.

**(b) One fallback colour.** #69 (B1) defined `UNLABELLED_FALLBACK_COLOR` for the 2D canvas, #71 the same cyan for the
GPU and 3D views. One definition now, in `regionColors.ts`, re-exported by `drawnLabels.ts`
(`fallbackColour.release20261030.test.ts`; controls I59, and I46 now mutates that one constant).

**(c) L3 of #69's last check — lesion-table chips against image colours: resolved by #71.** The chips use
`REGION_DOT_CLASSES` (`regionColors.ts`); the 2D overlay draws the labels from `activeSegmentation.labels`, which the
store passes through `withRegionColors`; the 2D zone layers use `regionZoneRgba`; the 3D zone colormap and the GPU / 3D
mask colours use the same mapping. One palette for table and image (checked in the code; #71's
`SegmentationCanvasLocal.prb010.test.tsx` and `regionColors.test.ts` pass on the merged tree).

## 4. Tests adapted to #71's display contract (no check removed)

- `drawnLabels.digest.test.ts`: the shared digest vector is computed on a fixed table with the colours of the vector,
  since the MAGNIMS preset now carries the region colours.
- `LesionDashboard.release20261028.test.tsx` (F08): the canvas draws the server's labels in the region colours
  (`withRegionColors(SERVER_LABELS)`), as #71 intends.
- `test_release_2026_10_25_final_check.py`: the DIS-state table is served as drawn (deep white matter `#D55E00`; the
  fixture stores `#CC79A7`); its independent digest helper digests the table as drawn.
- `test_prb003_dis_requires_confirmed_segmentation.py` `_drawn`: the confirm requests state the table as drawn.

## 5. Verification on the merged tree

All backend runs offline: `GOOGLE_APPLICATION_CREDENTIALS` = a missing file, `CLOUDSDK_CONFIG` = an empty folder,
`GOOGLE_CLOUD_PROJECT=mstool-offline-tests`, `ANTHROPIC_API_KEY` unset, plus #66's guard in conftest.

| Check | Result |
|---|---|
| Backend unit (`tests/unit`, as CI) | **2139 passed, 0 failed** (#69 2091, #71 +45, merge +3) |
| Backend integration (CI selection) | **25 passed, 1 failed, 20 deselected** — the known local `test_webauthn_credentials_endpoint_exists` (`webauthn` not in the local venv; CI installs it) |
| Backend security (CI selection) | **112 passed, 5 xfailed** |
| Manifest gate | passes (74 controls) |
| Frontend vitest (`--pool=threads`) | **591 passed, 3 skipped** (76 files passed, 3 skipped as on `main`) |
| Frontend `tsc --noEmit` / production build | clean / passes |

### Negative controls — every script of both branches, once, on `04fd105`

Run one script at a time in a throwaway worktree of `04fd105` (removed afterwards; the release worktree was not
mutated); `git status` clean before and after each; each tracked record copied to `RELEASE-2026-10-30_*` and restored.

| Script (origin) | Mutations | Result on the merged tree | Record |
|---|---|---|---|
| `release_2026_10_25_negative_controls.py` (#69 integration + this merge) | 61 | **61 detected** (I58, I59 new; I46, I54 re-anchored) | `RELEASE-2026-10-30_integration_negative_controls.json` |
| `prb004_negative_controls.py` (#71) | 114 | **114 detected** (its own nested throwaway worktree, as #71 designed) | `RELEASE-2026-10-30_PRB-004_negative_controls.json` |
| `prb003_negative_controls.py` (#68) | 119 | **119 detected** | `RELEASE-2026-10-30_PRB-003_negative_controls.json` |
| `capa015_negative_controls.py` (#65) | 108 | **107 detected, 1 declared equivalent** (R9, as its own record) | `RELEASE-2026-10-30_CAPA-015_negative_controls.json` |
| `capa014_negative_controls.py` (#67) | 94 | **94 detected** | `RELEASE-2026-10-30_CAPA-014_negative_controls.json` |
| `capa013_negative_controls.py` | 66 | **66 detected** | `RELEASE-2026-10-30_CAPA-013_negative_controls.json` |
| `capa008_negative_controls.py` | 17 | **17 detected** | `RELEASE-2026-10-30_CAPA-008_negative_controls.json` |
| `capa009_negative_controls.py` | 32 | **32 detected** — on `530b953` (the first run, on `04fd105`, left O2 undetected: the re-anchor after #71 kept the reference image's authorization; O2 is again the original two-edit mutation) | `RELEASE-2026-10-30_CAPA-009_negative_controls.json` |
| `capa010_negative_controls.py` | 26 | **25 detected, 1 declared equivalent** (L2, as its own record) | `RELEASE-2026-10-30_CAPA-010_negative_controls.json` |
| `capa011_negative_controls.py` | 22 | **22 detected** | `RELEASE-2026-10-30_CAPA-011_negative_controls.json` |
| `slice_thickness_negative_controls.py` | 38 | **38 detected** | `RELEASE-2026-10-30_CP-SLICE-THICKNESS-001_negative_controls.json` |
| `rc032_negative_controls.py` | 45 | **42 detected, 3 declared equivalent** (B, B2, L5, as its own record) | `RELEASE-2026-10-30_RC-032_negative_controls.json` |
| `prb002_negative_controls.py` (#66) | 19 | **19 detected** | `RELEASE-2026-10-30_PRB-002_negative_controls.json` |
| `rc029_negative_controls.py` | 11 | **11 detected** | `RELEASE-2026-10-30_RC-029_negative_controls.json` |
| **Total (14 scripts)** | **772** | **767 detected, 5 declared equivalent** (each as its own record declares) | |

Every script ran on `04fd105` except the CAPA-009 re-run on `530b953`, which differs from `04fd105` only in that script.

## 6. For the owner

- The owner decisions and owner-only actions of #69 and of #71 apply unchanged (their PR descriptions; every one
  PENDING owner approval), plus the deployment order of #69's plan (hosting first, then the backend at once).
- Known minor items of #69's last check that remain: **L1** (another image under the open segmentation draws it
  sheared; Confirm accepted) and **L2** (a high zone-map or longitudinal overlay opacity can camouflage lesions).
  **L3 is resolved** by #71 (§3 c). The residual risk of #69 (the drawn-lesion check runs in the browser) is unchanged.
- Class C changes needing an independent reviewer: those of #69 (`brain_report_service.py`, `report_payload_guard.py`,
  `dis_review_gate.py` — owner decision D-3) and of #71; the merge adds `dis_review_gate.stored_labels` (§3 a).

## 7. Merge of `main` after PR #70 (owner-signed) — 2026-10-30

The owner signed PR #70 himself (`5561999`, PRB-020 .. PRB-027, RC-080 .. RC-089) and merged it into `main` at
`cc7b692`. `main` was merged into this branch with `git merge --no-ff` (no rebase), so PR #72 merges cleanly and every
signed commit keeps its hash.

| Commit | Content |
|---|---|
| `9ffaaaf` | Merge of `main` @ `cc7b692` — conflicts resolved, both sides kept |
| `4a28806` | #70's account tests on this branch's durable audit trail (fixtures only); test written first for the account-creation audit (on `9ffaaaf`: **1 of 2 fails**; the other is a positive control — record `RELEASE-2026-10-30_main_merge_tests_on_9ffaaaf.json`) |
| `b3b61b1` | Integration decision: #70's privileged account creation recorded as a role assignment, the created account as the target |
| `c3f3e8e` | Integration controls I60, I61 |
| (records commit) | This section, the control records, document rows, manifest |

**#70's owner approvals are untouched.** Every line carrying the owner's approval entry of PR #70 (dated 2026-10-30) is
byte-identical to `main`, in all 16 files that carry one (checked line by line after the resolution). No approval was
written by the agent.

**Conflicts and how each was resolved (both sides kept):**

| File | Resolution |
|---|---|
| `backend/app/models/schemas.py`, `frontend/src/types/segmentation.ts` | PRB-003's `clinician_review` / history fields (this branch) and PRB-026's `created_by` (#70) |
| `ImageViewer2D.tsx` | #70's translated GPU-viewer fallback text with #71's `hasUnsavedEdits` prop |
| `NiivueViewer2D.tsx` | #71's head of the component, which already declares `t` (#70 added the same line); #70's other changes (translated texts, load-failure marker) merged without a conflict |
| `SegmentationPanel.tsx`, `useSegmentationData.ts` | Both sides' imports |
| `DEPLOYMENT_CHECKLIST.md` | This branch's troubleshooting rows, then #70's "Accounts" and "Care teams — run BEFORE deploying the backend" sections |
| SRS-001, RMF-001, TM-001 | This branch's version rows, then #70's signed rows; REQ-SEC-021..026 and RC-064..076 rows (this branch), then #70's REQ-SEC-030..035 and RC-080..089; the owner-action tables of both |
| `rc_test_manifest.json` | RC-064..076 (this branch) then RC-080..089 (#70): 84 controls, valid JSON; the gate passes |

The i18n files, `auth.py`, the patient / study routes and the other files #70 changed merged without a conflict.

**Version numbering.** #70 numbered its versions above this branch's planned ones and the owner approved them as SRS
1.16, RMF 1.18 and TM 1.15 (on `main`). This branch's draft versions keep the numbers its records cite — SRS 1.11–1.15,
RMF 1.13–1.17, TM 1.10–1.14, all below #70's — and the merged documents are new versions above #70's: **SRS 1.17, RMF
1.19, TM 1.16** (DRAFT, PENDING owner approval; one row each, naming the merge; headers updated). #70's rows are unchanged.

| Document | This branch (drafts) | #70 on `main` (approved by the owner) | Merged document |
|---|---|---|---|
| SRS-001 | 1.11 – 1.15 | 1.16 | **1.17** |
| RMF-001 | 1.13 – 1.17 | 1.18 | **1.19** |
| TM-001 | 1.10 – 1.14 | 1.15 | **1.16** |

**Integration decision (test written first).** #70 (review of PR #70, m1) records an administrator account created by
an administrator twice: `register_user` and `privileged_account_created`. CAPA-015 (RC-067, in this branch) sends audit
events to the durable trail through a fixed action → event-type mapping, and an action it does not know is recorded as
"authz.access.granted"; its record keeps only allow-listed detail keys, so #70's `details["target_user_id"]` was
dropped. Merged, the privileged creation would have read as an access grant, and neither record would have named the
account created. Now `privileged_account_created` maps to "authz.role.assigned" and #70's `target_user_id` is recorded
as the target identifier (`test_release_2026_10_30_main_merge.py`; controls I60, I61).

**#70's tests on this branch.** #70's account tests patched the per-process audit list `_audit_logs`, which CAPA-015
replaced with the durable trail: 24 of them errored in their fixtures on the merge. The fixtures now capture the audit
calls for the test's duration (each call still reaches the durable trail); the test bodies and assertions are
unchanged.

**Verification on `c3f3e8e`** (offline, as always):

| Check | Result |
|---|---|
| Backend unit | **2309 passed, 0 failed** (2139 + #70's + 2 merge tests) |
| Backend integration (CI selection) | **25 passed, 1 failed, 20 deselected** — the known local `webauthn` one |
| Backend security (CI selection) | **112 passed, 5 xfailed** |
| Frontend vitest | **621 passed, 3 skipped** (83 files passed) — no frontend file changed after `9ffaaaf` |
| `tsc --noEmit` / production build | clean / passes |
| Manifest gate | passes (84 controls) |

**Negative controls re-run on `c3f3e8e`** (once each, one at a time, in a throwaway worktree removed afterwards; `git
status` clean after each): the scripts whose mutated files or bound tests the merge changed, plus #70's
`prb020_negative_controls.py`. The others (CAPA-008, CAPA-010, slice thickness, PRB-002, RC-029) touch no file the merge
changed; their §5 records stand.

| Script (origin) | Mutations | Result on `c3f3e8e` | Record |
|---|---|---|---|
| `release_2026_10_25_negative_controls.py` (#69 integration + these merges) | 63 | **63 detected** (I60, I61 new) | `RELEASE-2026-10-30_integration_negative_controls.json` |
| `prb004_negative_controls.py` (#71) | 114 | **114 detected** | `RELEASE-2026-10-30_PRB-004_negative_controls.json` |
| `prb020_negative_controls.py` (#70) | 99 | **99 detected** (first run on this branch) | `RELEASE-2026-10-30_PRB-020_negative_controls.json` |
| `prb003_negative_controls.py` (#68) | 119 | **119 detected** | `RELEASE-2026-10-30_PRB-003_negative_controls.json` |
| `capa015_negative_controls.py` (#65) | 108 | **107 detected, 1 declared equivalent** (R9, as its own record) | `RELEASE-2026-10-30_CAPA-015_negative_controls.json` |
| `capa013_negative_controls.py` | 66 | **66 detected** | `RELEASE-2026-10-30_CAPA-013_negative_controls.json` |
| `capa009_negative_controls.py` | 32 | **32 detected** | `RELEASE-2026-10-30_CAPA-009_negative_controls.json` |
| `capa011_negative_controls.py` | 22 | **22 detected** | `RELEASE-2026-10-30_CAPA-011_negative_controls.json` |
| `rc032_negative_controls.py` | 45 | **42 detected, 3 declared equivalent** (B, B2, L5, as its own record) | `RELEASE-2026-10-30_RC-032_negative_controls.json` |
| `capa014_negative_controls.py` (#67) | 94 | **94 detected** | `RELEASE-2026-10-30_CAPA-014_negative_controls.json` |
| **Re-run (10 scripts)** | **762** | **758 detected, 4 declared equivalent** | |
| Not re-run — CAPA-008 (17), CAPA-010 (26: 25 + L2 declared equivalent), slice thickness (38), PRB-002 (19), RC-029 (11) | 111 | their records of §5 (run on `04fd105`) stand: none of their mutated files or bound tests changed in the merge, and every file hash in those records was checked equal to `c3f3e8e` | §5 records |
| **All 15 scripts on the final tree** | **873** | **868 detected, 5 declared equivalent** (each as its own record declares) | |

Every record was checked after the run: a finished run, every mutation of the script accounted for, and every source
and test hash equal to `c3f3e8e` (LF basis). The run was interrupted once by a network error in the agent's session
after the last script had finished; nothing was left mutated (the throwaway worktree held only the records).

*Drafted by the AI coding agent (development tool, SDP-001 §5.1.4). No approval is recorded in this document;
approvals are to be recorded by the owner (CAPA-012).*
