# Viewer v3 — QMS impact (for the owner / safety officer)

Nothing here is approved. The SRS carries the proposals as version **1.5 (proposed),
PENDING owner approval**; the RMF, traceability matrix and compliance documents were
NOT edited (their verification statuses are formal records).

## Requirements (SRS-001, proposed 1.5)

| Item | Change |
|---|---|
| REQ-FUNC-001a (new) | In-browser 2D rendering from stored intensities, three planes from the affine, one voxel↔screen mapping for image and overlays, fail-closed agreement with server metadata, server fallback, voxel order when orientation is not established. |
| REQ-FUNC-005a | "server-side" → "in the browser on the default path, server-side on matplotlib". |
| REQ-FUNC-023 | undo/redo snapshots of the plane painted (any plane). |
| REQ-SAFE-016 | note: identity also annotated in 3D and multi-panel viewports. |

Already covered by existing requirements: REQ-FUNC-001, -004 (MPR with synchronised
cursor), -005, -006, -020, -027, -028, -091.

## Risk management file (RMF-001) — rows to update

| Control | Impact |
|---|---|
| RC-012 (HAZ-006) auto-transpose | New path uses the same dimensional rule but requires the full 3-D grid to match (depth included) and refuses otherwise (fail closed). Legacy canvas unchanged. Tests: `maskPlane.test.ts`. |
| RC-014 (HAZ-007) tri-colour longitudinal overlay | Still tri-colour, colours changed for colour-vision safety (Okabe-Ito): resolved = sky blue, new = vermillion, persistent = yellow (was blue / red / green). Legends updated to match. Row text "blue / red / green" must be revised. |
| RC-016 (HAZ-009) identity in viewport | Was "VERIFIED — 2D ONLY; 3D and multi-panel unannotated (CA-4.2 open)". Now annotated in 3D and every multi-panel cell; static wiring tests added to `ViewportSafetyOverlay.test.tsx`. Candidate to close that part of CA-4.2 after review. |
| RC-023 (HAZ-006) orientation reported, never guessed | 2D anatomical planes only when the browser's axis codes equal the server's (else voxel order, explicit notice); niivue orientation cube / edge text disabled in 3D; still no L/R edge labels (CA-4.3 open). |
| RC-024 spacing | Measurements use the spacing of the displayed axes; legacy measurement overlay zoom/pan defect fixed (see below). |

## Problem reports suggested (IEC 62304 clause 9) — latent defects found and fixed

1. **3D lesion crosshair and bounding-box mesh transposed in-plane** — backend (z, y, x)
   was used as (k, j, i). Wrong location on non-square slices (e.g. 182 × 218). Fixed
   in `ImageViewer3D.tsx` / `boundingBoxMesh.ts`, test `boundingBoxMesh.test.ts`.
2. **Measurement overlay ignored zoom and pan** — at zoom 2 a ruler reported twice the
   true distance (legacy 2D canvas). Fixed, test `viewportTransform.test.ts`.
3. **Standing laterality caveat clipped** — the legacy layout pushed the bottom of the
   2D viewport off-screen, hiding "Laterality not labelled" at common window sizes.
4. **Legend / overlay colour mismatch** — MAGNIMS zone colours differed between the
   lesion table (Okabe-Ito) and the zone map / overlay (red / green / blue / yellow).
5. **niivue orientation cube with L/R letters in 3D** while RC-023 forbids laterality
   labels.

## Software items / classification

New units (display + mask editing geometry, same class as the existing image viewer /
segmentation canvas items, B per the master compliance document):
`frontend/src/volume/*`, `frontend/src/components/viewer2d/*`,
`frontend/src/components/workspace/*`, `frontend/src/components/ui/*` (primitives).
No Class C module listed in CLAUDE.md was modified (`edgeAI.worker.ts` untouched; the
quick screen receives bit-identical input, see PARITY.md).
