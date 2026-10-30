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

**It supersedes merging #69 and #71 separately:** the two conflict (documents, manifest, four frontend imports, a
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

*Drafted by the AI coding agent (development tool, SDP-001 §5.1.4). No approval is recorded in this document;
approvals are to be recorded by the owner (CAPA-012).*
