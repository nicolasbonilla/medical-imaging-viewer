# Viewer v3 — in-browser 2D rendering and workspace redesign

Branch `feat/viewer-v3` (4 commits on top of `6209131`). Not pushed, not deployed.

## 1. In-browser 2D rendering (audit P0)

Before: every 2D slice was an 8-bit PNG rendered by the server (`/imaging/process`
returned all slices as base64 PNGs), window/level was a server round-trip or a CSS
filter, one plane only, displayed in array order (brain rotated 90° on RAS/LAS data).

Now (default render path "In-browser"):

- The NIfTI the 3D view already downloads is parsed in the browser
  (`frontend/src/volume/nifti.ts`, nibabel-equivalent), so the default load fetches
  only `/imaging/metadata` + `/imaging/nifti` — no PNG payload, no per-slice requests.
- Full-bit-depth window/level in real units (presets Auto / Full range / Server 2–98 %,
  numeric C/W, right-drag on the image), histogram with the active window band.
- Axial / coronal / sagittal from the affine, same convention as the niivue 3D panels
  (`DISPLAY_CONVENTION`), with a 3-D cursor shared by all planes and by the 3D view;
  lesion selection centres every plane on the lesion; vertical stack scrollbar.
- Painting and undo/redo work in every plane (brush footprint shown voxel-exact);
  painting switches the display to nearest-neighbour so the voxels are visible.
- Cursor read-out: voxel (i, j, k), scanner mm, full-precision value, label.
- Server PNG path kept behind the "Display options" menu and used automatically when
  the browser must not render an image (see PARITY.md, fail-closed).

Parity / safety evidence: **[PARITY.md](PARITY.md)**.

## 2. Workspace redesign

`ViewerApp.tsx` 1 139 → ~600 lines; presentation moved to
`frontend/src/components/workspace/*` (toolbar, status bar, insights panel with tabs
Image / Annotate / Analysis / Report, sidebar sections, overlay controls, states).
All workspace panels on the v2 tokens (surface / ink / brand / clinical), 12 px
minimum text, tabular numerals, aria-labels on icon-only controls, skeleton loading.
New accessible primitives in `frontend/src/components/ui` (IconButton, SegmentedControl,
Menu, Switch, Tabs). One clinical colour vocabulary (`utils/clinicalPalette.ts`,
Okabe-Ito) shared by legends, 2D overlays and the 3D zone map.

## 3. Safety-relevant fixes found on the way

- RC-016: patient identity was absent from the 3D viewer and the multi-panel grid → now
  rendered in every view mode (static wiring tests).
- RC-023: the 3D render showed a niivue orientation cube with L/R letters → disabled
  while laterality labelling is unverified (CA-4.3).
- 3D lesion crosshair and bounding box used the backend (z, y, x) as (k, j, i) →
  transposed in-plane (wrong location) on non-square slices → fixed + test.
- Measurement overlay ignored zoom/pan → a ruler at zoom 2 reported twice the length →
  fixed on both paths + test; angles now use physical spacing.
- The legacy 2D layout clipped the bottom of the viewport, hiding the standing
  "Laterality not labelled" caveat at common window sizes → visible again.
- Matplotlib endpoint was queried on every scroll in every 2D mode → only when shown.

## 4. Screenshots (headless Edge, 1600 × 1000, public case, demo harness)

`screenshots/before-01 … 03` — legacy viewer (server PNG, 3D MPR).
`screenshots/after-01 … 16` — axial / sagittal / coronal with overlay, lesion
dashboard, lesion focus in two planes, paint mode, 3D MPR, multi-panel FLAIR + T1,
server fallback path, voxel-order parity view, display menu, Spanish UI, and a
sagittal stroke seen in axial + undone with Ctrl+Z.

## 5. Reproduce

```bash
# fixtures (public data, local, gitignored) — backend venv
backend/venv/Scripts/python.exe scripts/viewer/build_parity_fixture.py
backend/venv/Scripts/python.exe scripts/viewer/build_demo_fixtures.py <path>/data/external
# tests
cd frontend && npx vitest run --pool=threads && npx tsc --noEmit
node ../scripts/viewer/negative_controls.mjs
# demo harness (DEV only): npm run dev → http://localhost:5173/dev/viewer-demo
node ../scripts/viewer/screenshot.mjs ../docs/research/viewer-v3/screenshots name=steps …
```

The harness (`frontend/src/dev/*`, route behind `import.meta.env.DEV`, data served by
an `apply: 'serve'` Vite middleware) is absent from production builds (verified by
grepping `dist/`).

## 6. Not done / open

- Owner decisions: display convention (neurological today, as the 3D view);
  retiring the server PNG fallback after a clinical visual check (PARITY.md).
- Laterality letters on the image edges stay off (RC-023 / CA-4.3 still open).
- Safety-overlay texts have no Spanish/German translations yet (they were English-only
  before too); other new strings are translated (en/es/de).
- ESLint has no flat config in this repo (`eslint .` fails before linting) — not
  addressed; lint is still not a CI gate.
- `ReportViewerModal` (print layout) and the non-viewer pages were not restyled.
- Multi-panel cells use the automatic window per image (the window controls act on the
  single view).
- Defects noticed during the panel restyle and deliberately NOT changed (logic, out of
  scope of a visual pass — candidates for their own tickets):
  - ClinicalToolsPanel: after FLAMeS the list is invalidated with
    `['segmentations', fileId]` but the rail uses `['segmentations','study',studyId]`
    (no refresh); LST-AI / SynthSeg buttons not disabled while a task is pending; a
    network error while polling leaves "Processing" forever.
  - SegmentationPanel: the typed name of a new segmentation is never used; saved
    segmentations list "0/N (0%)" progress; load/delete failures only go to the console.
  - LesionDashboard: highlighted row can desync from the store selection;
    "Classification distances (n)" counts all lesions; DICOM-SEG export uses raw
    `fetch` (no token refresh).
  - MAGNIMSZoneMapPanel: fresh stats are not reset when the image changes.
  - AIReportPanel: active-segmentation hint not reactive; `en-US` style language codes
    match no button.
  - SegmentationConflictDialog: no Escape / focus trap.
  - BrainVolumetryPanel: NaN bar width when all volumes are 0.
