# PRB-005 — The 3D View and the "W/L GPU" View Fail on a Host Name Without a Dot

*Software problem report per SPR-001 §1 (layout of PRB-001). No GitHub Issue raised — owner action.*

**Problem ID**: PRB-005 (GitHub Issue: not raised — owner action)
**Reporter**: browser capture session of the release candidate (PR #69 @ `6d1fde2`, finding F01 in
`mstool-film/assets/app-captures/CAPTURES.md` §5; screenshots `findings/F01_3d_fails_on_localhost_toUpperCase.png`,
`findings/F01b_wl_gpu_fails_on_localhost_toUpperCase.png`; log `logs/exploration/explore4.console.log`); reproduced on
`main` and record drafted by the AI coding agent
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7`. 3D view: blob URLs without a name since `67fa336` / `247c1b8` (2026-02-28); GPU view since
`4584b81` (2026-08-21). The release branch does not change this.
**Severity**: **Major** (proposed; SPR-001 §2: significant functional loss — the 3D view and the GPU view are unusable
on such a host; the standard 2D view, where review and editing happen, works). Not safety-related: nothing wrong is
displayed, the view shows an error. **N. G. Bonilla Vargas — approved 2026-10-30 (PR #72).**
**Status**: OPEN — DRAFT. Fix implemented on branch `fix/viewer-display-orientation-prb004` (draft PR).

**Description**: Hospitals run applications on internal host names without a dot (`http://localhost`,
`http://mstool`, `http://radiology-viewer`). There, opening the 3D view (volume or multiplanar) or the W/L GPU render
mode fails with *"Cannot read properties of undefined (reading 'toUpperCase')"*. The page hands niivue a blob URL
(`blob:http://localhost:4173/<uuid>`) with no file name; niivue's `loadVolumes` derives the file type from the URL's
"extension" with `/(?:\.([^.]+))?$/`, which on a dot-less origin finds none and calls `toUpperCase()` on `undefined`.
On `app.mstool-ai.com` the URL contains dots, so the parser finds a nonsense "extension" (`COM/<uuid>`) and niivue falls
back to reading the bytes — the production site worked by accident.

**Steps to Reproduce**: serve the app from `http://localhost:<port>` (or any dot-less host), open a study, click *3D*,
or choose the *W/L GPU* render mode.

**Expected Behavior**: the views load on any host name.

**Actual Behavior** (`main` @ `70cc5c7`): `frontend/src/components/ImageViewer3D.tsx:362` and `:455`
(`nv.loadVolumes([{ url: <blob URL>, colormap, opacity }])`, no `name`), `frontend/src/components/NiivueViewer2D.tsx:135`
(same). niivue 0.67.0 `getFileExt()` (`dist/index.js:37146-37157`, called by `addVolumesFromUrl`) throws. Reproduced with
niivue's own function: `getFileExt('blob:http://localhost:4173/<uuid>')` → TypeError; the same call with
`blob:https://app.mstool-ai.com/<uuid>` → `"COM/<UUID>"` (no error). The masks are loaded with
`NVImage.loadFromUrl`, which tolerates a missing extension; only the image volume fails.

**Safety Impact Assessment**:
- [ ] Could contribute to a hazardous situation — no: the view fails visibly; no wrong content is shown.
- [ ] Affects a Class C software item of the CLAUDE.md list — no.
- [ ] Requires regulatory notification — no.

## 1. Root Cause

The volume was identified to niivue by a URL that carries no file name. niivue documents `name` as the way to give the
type of a URL without an extension; it was never passed. The behaviour depended on the host name, which no test varied.

## 2. Impact Analysis

All `loadVolumes` / `NVImage.loadFromUrl` calls of the app (two components; `grep` of `@niivue/niivue` imports): every
volume now carries an explicit NIfTI name chosen by its bytes (`.nii.gz` when gzip, else `.nii`), and the GPU view hands
niivue the downloaded buffer itself (no blob URL). Requirement: new **REQ-FUNC-101**. No risk control affected.

## 3. Resolution — implemented on branch, N. G. Bonilla Vargas — approved 2026-10-30 (PR #72)

- `frontend/src/utils/niivueVoxelGrid.ts`: `niftiNameFor(buffer, stem)`.
- `frontend/src/components/ImageViewer3D.tsx`: `name` on the image volume (volume and multiplanar) and on every overlay.
- `frontend/src/components/NiivueViewer2D.tsx`: `NVImage.loadFromUrl({ buffer, name })` for the image and the mask.

## 4. Verification

- Failing-first tests: `frontend/src/components/ImageViewer3D.prb005.test.tsx` (3D volume and multiplanar, on
  `http://localhost:4173` and `http://mstool-viewer`: the 4 `prb005` tests fail on `main` with the exact error) and the two
  `prb005` tests of `NiivueViewer2D.prb004.test.tsx` (both fail on `main`). niivue's loaders are real in these tests
  (`src/test/niivueHarness.ts`: the fake `loadVolumes` runs niivue's own `getFileExt`). Record
  `records/risk_verification/PRB-004_tests_on_base_2026-10-28.json`.
- Negative controls N1–N4 (blob URL back in the GPU view, name removed in 3D volume / multiplanar, a name without an
  extension): **4 of 4 detected** — `records/risk_verification/PRB-004_negative_controls_2026-10-28.json`.
- Real browser on `http://localhost` (real niivue, headless Edge): fixed branch — GPU and 3D views drawn, no page error;
  `main` — the GPU view shows "Cannot read properties of undefined (reading 'toUpperCase')" and the 3D view draws nothing —
  `records/risk_verification/PRB-004_viewer_display_probe_2026-10-28.json`.

## 5. Owner decisions

- Severity Major (not safety-related).

## 6. Closure — not applicable yet
