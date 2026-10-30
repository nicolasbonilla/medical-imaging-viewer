# PRB-009 — The Unshipped Screening Model Was Requested at Every Viewer Opening

*Software problem report per SPR-001 §1 (layout of PRB-001). No GitHub Issue raised — owner action.*

**Problem ID**: PRB-009 (GitHub Issue: not raised — owner action)
**Reporter**: browser capture session of the release candidate (PR #69 @ `6d1fde2`, finding F18 / F19 in
`mstool-film/assets/app-captures/CAPTURES.md` §5; `logs/*.console.log`: `HEAD /models/brain_screening.onnx` failed on every
viewer opening); reproduced on `main` and record drafted by the AI coding agent
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7`; the per-opening request exists since `5c9ffc8` (2026-02-09), the content-type check since
`6f69671` (2026-04-17). The release branch does not change this.
**Severity**: **Minor** (proposed; console noise and a button that appears and vanishes). The feature itself is an assistive
normal/abnormal screening (HAZ-004); making it unreachable unless deliberately built in lowers that risk. **PENDING owner
approval.**
**Status**: OPEN — DRAFT. Fix implemented on branch `fix/viewer-display-orientation-prb004` (draft PR).

**Description**: The viewer mounts "Quick Screen", an in-browser normal/abnormal screening of one slice. Its model file
(`/models/brain_screening.onnx`) is not part of the app (`frontend/public` has no `models` folder; the README calls it
"user-supplied"). Every time the viewer opened, it requested the file. On a static server that answers 404 (vite preview, a
hospital nginx without the SPA fallback for `/models`), the browser logged a failed request each time; on Firebase the SPA
rewrite answers 200 + `index.html`, which the check recognises as absent. While the request was in flight the "Quick Screen"
button was shown, then disappeared.

**Expected Behavior**: an absent model is a switched-off feature: nothing requested, nothing shown, nothing in the console —
unless the screening is deliberately built in; then the model is looked for once per page, the button appears only when the
model is there, and an absent model is silent.

**Actual Behavior** (`main` @ `70cc5c7`): `frontend/src/components/ImageViewer2D.tsx:630` (badge mounted for every image);
`frontend/src/hooks/useEdgeAI.ts:64-71` (HEAD request in every mount); `frontend/src/components/QuickScreenBadge.tsx:90` (button
hidden only once the model is known to be absent).

**Safety Impact Assessment**: no new hazard. HAZ-004 (screening false negative): the feature is now unreachable unless built in
(RC-075, proposed). Class C item of the CLAUDE.md list: `edgeAI.worker.ts` is NOT changed.

## 1. Root Cause

An optional feature whose artefact is not shipped was mounted unconditionally and discovered its own absence at run time, once
per mount, showing its button while it looked.

## 2. Resolution — implemented on branch, PENDING owner approval

- `frontend/src/config/features.ts`: `QUICK_SCREEN`, OFF unless `VITE_ENABLE_QUICK_SCREEN` is `true` or `1` (not set in
  `.env.production`).
- `frontend/src/components/ImageViewer2D.tsx`: the badge is mounted only behind the flag (off: no request, no button).
- `frontend/src/hooks/useEdgeAI.ts`: one model lookup per page, shared by every opening; an absent model resolves `false`
  silently.
- `frontend/src/components/QuickScreenBadge.tsx`: nothing is rendered until the model is known to be served.
- Requirement: new **REQ-FUNC-104**; risk control: new **RC-075** (HAZ-004). RC-008 (disclaimer) and RC-009 (model name) are
  unchanged and apply whenever the feature is built in.

## 3. Verification

- Failing-first tests (named `rc075`): `frontend/src/ViewerApp.prb007.test.tsx` (the real viewer page: no model request, no
  button — fails on `main`), `frontend/src/components/QuickScreenBadge.prb009.test.tsx` (flag on, model absent: no button while
  looking, one lookup for three openings — 2 of 4 fail on `main`; "nothing written to the console" and the guard "button when the
  model is there" pass on both), `frontend/src/config/features.quickScreen.test.ts` (flag default off, mounted behind the flag —
  4 of 5 fail on `main`; the production environment file check passes on both). Record `records/risk_verification/PRB-004_tests_on_base_2026-10-28.json`.
- Negative controls Q1–Q5 (on by default, mounted without the flag, model looked for at every opening, button while looking,
  absent model logged as an error): **5 of 5 detected** — `records/risk_verification/PRB-004_negative_controls_2026-10-28.json`.
- Real browser: fixed — no request for the model, no button; `main` — 4 requests for `/models/brain_screening.onnx` in one
  session (each time the 2D view was mounted) — `records/risk_verification/PRB-004_viewer_display_probe_2026-10-28.json`.
- A failed request is logged by the browser itself, outside the page's JavaScript; with the flag off it cannot occur because
  nothing is requested.

## 4. Owner decisions

- **D-1**: keep the screening off (recommended: the model is not shipped, not validated, and HAZ-004 is UNACCEPTABLE before
  controls in RMF §5.1) — or ship a validated model with its own change.

## 5. Closure — not applicable yet
