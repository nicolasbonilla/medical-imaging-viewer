# Class C change proposal — in-browser FLAMeS automatic lesion segmentation

| | |
|---|---|
| Proposal ID | CP-FLAMES-BROWSER-001 (draft) |
| Date | 2026-10-17 |
| Branch | `feat/flames-in-browser` (prototype behind `VITE_ENABLE_BROWSER_FLAMES`, default OFF; not deployed) |
| Safety class | **C** (IEC 62304:2006+A1:2015) |
| Design | [DESIGN.md](DESIGN.md) |
| Status | **Proposal only.** The controlled documents (SRS-001, RMF-001, traceability matrix, SOUP BOM) are **not** edited by this branch; the IDs below are proposed and must be allocated through the configuration-management process. Requires a code review and the owner's approval before any merge. |

## 1. What changes and why

The validated FLAMeS model (REQ-FUNC-034) currently can only run on a GPU inference worker that is not deployed
because of its recurring cost. This change adds a second execution path that runs the **same model and the same
nnU-Net arithmetic in the clinician's browser** (ONNX Runtime Web), so automatic MS-lesion drafts become available with
no GPU server and no inference cost. The output enters the existing local-first segmentation flow as an **unsaved,
visibly-labelled AI draft** that the clinician must review, edit and explicitly save.

Code touched (all frontend): new `src/services/flames/*`, new `src/workers/flamesInBrowser.worker.ts`,
new `src/hooks/useBrowserFlames.ts`, new `src/components/BrowserFlamesCard.tsx`; additive changes to
`useSegmentationMask.ts` (`importMask`), `useSegmentationData.ts` (`createSegmentationFromMask`, description sent
only when non-default), `useSegmentationStore.ts` (`importDraftCallback`), `ClinicalToolsPanel.tsx` (lazy card behind
the flag), `config/features.ts` (flag). **No listed Class C module is modified** (`edgeAI.worker.ts`, backend
services and utils are untouched). No backend change.

## 2. Proposed requirements (text for SRS-001)

| Proposed ID | Requirement | Priority | Class | Verification | Hazards |
|---|---|---|---|---|---|
| REQ-FUNC-093 | The system shall be able to compute the FLAMeS MS-lesion segmentation (REQ-FUNC-034 model) entirely inside the user's browser, from one stored 3D FLAIR NIfTI, without sending image data to any server other than the existing authenticated image download. | Should | C | Test (parity harness) | HAZ-001, HAZ-006 |
| REQ-FUNC-094 | The in-browser computation shall reproduce nnU-Net v2's preprocessing, sliding-window inference and resampling for the FLAMeS plans such that, on the public verification cases, the mask agrees with `nnUNetv2_predict` (same fold, same test-time-augmentation setting) with Dice ≥ 0.99. | Must | C | Test | HAZ-001 |
| REQ-FUNC-095 | The in-browser result shall be produced on the stored FLAIR's own voxel grid and handed to the segmentation store in the RC-031 internal order (k, i, j); it shall only be opened over the same file, with identical rows, columns and slices. | Must | C | Test | HAZ-006 |
| REQ-SAFE-025 | The in-browser segmentation shall fail closed: any model-integrity, input, numerical or output-plausibility failure shall yield no mask at all (no partial result), with a user-visible reason. | Must | C | Test | HAZ-001 |
| REQ-SAFE-026 | An in-browser segmentation shall be presented as a local, unsaved draft labelled "AI draft, unreviewed", visually distinct from clinician labels, and persisted only by an explicit user Save that records model identity (SHA-256), pipeline version, backend and timestamp. | Must | C | Test + usability | HAZ-001 |
| REQ-SAFE-027 | The browser shall execute only the model artefact whose byte length and SHA-256 equal the values pinned in the released software. | Must | C | Test | HAZ-001 |

REQ-FUNC-035/036 (draft, provenance, fail-closed) apply to this path as well; REQ-SAFE-026 makes the "visible label"
part concrete for it.

## 3. Hazards touched

* **HAZ-001** — incorrect lesion delineation (over/under-segmentation). New causes introduced by this path:
  (a) port arithmetic differs from nnU-Net; (b) wrong or tampered model; (c) non-skull-stripped input;
  (d) GPU driver returning garbage (known WebGPU failure: all-zero outputs); (e) partial result shown after a crash
  or cancel; (f) single fold without mirroring is less accurate than the published ensemble (Neurodesk: Dice 0.608 vs
  0.647, AVD 84 % vs 45 % on MSLesSeg n = 22); (g) user mistakes the draft for a reviewed segmentation.
* **HAZ-006** — orientation/laterality. New causes: (a) axis order between NIfTI, nnU-Net (transpose_forward
  [2, 0, 1]) and the app (RC-031, (k, i, j)); (b) mask opened over a different image or a different grid.
* Not touched: HAZ-005 (region classification), HAZ-008 (DIS) — only indirectly, because a saved draft can later feed
  those features exactly like a manual mask.

## 4. Proposed risk controls

| Proposed ID | Control | Type | Implemented in prototype | Bound to |
|---|---|---|---|---|
| RC-F1 (→ RC-037) | Model pinned by size + SHA-256; mismatch ⇒ no run; cached copy re-verified each use | Protective | Yes | `modelStore.ts`; test `draft-model.test.ts`; negative control M12 |
| RC-F2 (→ RC-038) | nnU-Net-faithful port verified against nnunetv2 fixtures and end-to-end parity (Dice ≥ 0.99) | Design | Yes (2 public cases) | `preprocess/slidingWindow/axes` tests; `parity.flames.test.ts`; NC M1, M3, M5–M8 |
| RC-F3 (→ RC-039) | Axis-order control: explicit (i,j,k)→(i,k,j)→(k,i,j) conversions tested against SimpleITK and the backend convention; blob-localisation test | Design | Yes | `axes-nifti.test.ts`, `pipeline.test.ts`; NC M2, M4, M10 |
| RC-F4 (→ RC-040) | Skull-stripped plausibility gate (border nonzero ≤ 2 %, filled region 500–2600 mL); spacing 0.1–6 mm; dims ≥ 16 | Protective (heuristic) | Yes — **thresholds unvalidated** | `pipeline.ts`; NC M11 |
| RC-F5 (→ RC-041) | Numerical guard: NaN/Inf or constant scores ⇒ error; on WebGPU the whole job restarts on WebAssembly; output > 25 % of brain ⇒ discarded | Protective | Yes | `slidingWindow.ts`, worker; tests |
| RC-F6 (→ RC-042) | One terminal message per job; no partial-result message type; worker terminated on cancel/crash | Design | Yes | `protocol.ts`, `useBrowserFlames.ts` |
| RC-F7 (→ RC-043) | Draft opened only over the same file with identical rows/columns/slices; `importMask` refuses any dimension mismatch | Protective | Yes | `draft.ts`, `useSegmentationMask.importMask`; NC M9 |
| RC-F8 (→ RC-044) | Draft labelling: orange "Lesion (AI draft, unreviewed)" label, provenance description, unsaved until explicit Save | Information for safety | Partially — label/description done; **no persistent on-image banner**, and the server record does not yet mark `segmentation_type = automatic` | `draft.ts`, `BrowserFlamesCard.tsx` |
| RC-F9 (→ RC-045) | Feature flag OFF by default; enabled only after this change is approved | Design | Yes | `config/features.ts` |
| RC-F10 (proposed, not implemented) | Clinical-accuracy configuration: 5-fold ensemble (+ mirroring) as default before clinical use | Design | **No** | — |
| RC-F11 (proposed, not implemented) | Device gate: refuse ≤ 8 GB RAM / non-isolated single-thread pages with an explicit message and time estimate | Protective | **No** | — |

## 5. Verification plan

| # | Activity | Acceptance | Status (2026-10-17) |
|---|---|---|---|
| V1 | Unit tests vs nnunetv2/scipy/skimage/SimpleITK fixtures (`src/services/flames/__tests__`) | all pass in CI | **55/55 pass** locally (`--pool=threads`) |
| V2 | Negative controls (12 mutations) | every mutation detected | **12/12** |
| V3 | Parity on public 1 mm FLAIR (MSLesSeg P57) vs `nnUNetv2_predict` fold 0, no TTA | Dice ≥ 0.99 | **0.99940** (vs ONNX-backed nnU-Net 0.99946) |
| V4 | Parity on public anisotropic case (P57 → 4 mm slices) | Dice ≥ 0.99 | **0.99934** |
| V5 | Real-browser smoke (headless Edge, built worker): WebAssembly and WebGPU | completes, Dice ≥ 0.99 vs V3 reference | **WebAssembly: pass** (230 s, Dice 0.99940, bit-identical to V3). **WebGPU: fail on this machine** (ORT Web 1.24.1: no 3D conv; 1.29.0: iGPU device lost) — fallback worked, result identical. DESIGN.md §7.1 |
| V6 | Parity for the 5-fold ensemble, with and without mirroring | Dice ≥ 0.99 | not done |
| V7 | ≥ 10 further public cases incl. other scanners/orientations (MSLesSeg test, MICCAI 2016/2008 where licences allow) | Dice ≥ 0.99 each | not done |
| V8 | Skull-strip gate validation: stripped vs unstripped public FLAIRs | 0 unstripped accepted; ≤ 5 % stripped refused | not done |
| V9 | In-app QA (flag on, staging): open draft over the right FLAIR, edit, save, reload, compare saved NIfTI with the browser mask; laterality check with an asymmetric phantom | identical; L/R preserved | not done |
| V10 | Usability: clinicians identify the draft as unreviewed AI output | per IEC 62366 plan | not done |
| V11 | Performance on the device classes of DESIGN.md §7 | documented | partial |

## 6. Residual-risk view (proposed)
With RC-F1…F9 the new causes (a)–(e) and (g) of HAZ-001 and (a)–(b) of HAZ-006 are controlled at the software level;
cause (f) (single-fold accuracy) is **not** controlled until RC-F10 and a clinical-accuracy study exist. The feature
must therefore stay **OFF** in production until V6–V10 pass and the owner approves.

## 7. Other findings made during this work (out of scope, recorded for triage)
1. **Probable defect (dark server path, found by code reading, not executed):** `ToolRunnerService._store_nifti_as_segmentation`
   (`backend/app/services/tool_runner_service.py` ≈ l. 886–923) orients the mask to the internal (k, a0, a1) order and
   then writes it **as-is** into a NIfTI tagged `RC031-ORIENT-V2`, while `segmentation_service._nifti_native_to_internal`
   (l. 874–879, used by `_load_masks_from_gcs` l. 1167) applies `(2, 0, 1)` to V2 files — i.e. it expects the
   MRI-native order produced by `_internal_to_nifti_native` `(1, 2, 0)`. If confirmed, every server-side tool mask
   (FLAMeS GPU worker, LST-AI, SynthSeg) would load with permuted axes (HAZ-006). Needs a round-trip test before the
   GPU worker is ever enabled.
2. `ClinicalToolsPanel.refreshSegmentations` invalidates `['segmentations', fileId]` but the lists use
   `['segmentations', 'study', studyId]`; prefix matching does not reach them, so a finished server-side tool run may
   not appear until reload (UX, dark path).
3. SOUP BOM lists ONNX Runtime Web 1.21.0 (SOUP-FE-008) but the lockfile resolves 1.24.1. The WebGPU path of this
   feature additionally needs ≥ 1.29 (1.24.1's WebGPU backend rejects 3D convolutions) — a Class C SOUP change that
   also affects `edgeAI.worker.ts`.
