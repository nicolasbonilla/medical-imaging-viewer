# Class C change proposal — in-browser FLAMeS automatic lesion segmentation

| | |
|---|---|
| Proposal ID | CP-FLAMES-BROWSER-001 (draft, revision 2 after the adversarial review) |
| Date | 2026-10-17 (revision 2: 2026-10-18) |
| Branch | `feat/flames-in-browser` (prototype behind `VITE_ENABLE_BROWSER_FLAMES`, default OFF; not deployed) |
| Safety class | **C** (IEC 62304:2006+A1:2015) |
| Design | [DESIGN.md](DESIGN.md) · review response [REVIEW-RESPONSE.md](REVIEW-RESPONSE.md) · gate validation [FLAIR-GATE-VALIDATION.md](FLAIR-GATE-VALIDATION.md) · [COOP-COEP-IMPACT.md](COOP-COEP-IMPACT.md) |
| Status | **Draft records written, NOT approved.** SRS 1.7, RMF 1.9, TM 1.6, SOUP 1.2, CMP 1.1 carry the entries below with every approval field "N. G. Bonilla Vargas — approved 2026-10-30 (PR #70)". IDs coordinated with open PRs #52 (CAPA-010: RC-037/038, REQ-SAFE-025..027) and #51 (CAPA-011: RC-039, REQ-SAFE-028): **merge after #52 and #51**. Requires a code review and the owner's approval before any merge; the flag stays OFF. |

## 1. What changes and why

The validated FLAMeS model (REQ-FUNC-034) can only run on a GPU inference worker that is not deployed because of its
recurring cost. This change adds a second execution path that runs the **same model and the same nnU-Net arithmetic in
the clinician's browser** (ONNX Runtime Web), so automatic MS-lesion drafts become available with no GPU server and no
inference cost. The output enters the local-first segmentation flow as an **unsaved, visibly-labelled AI draft** that
the clinician must review, edit and explicitly save; it is stored with its AI provenance and stays "unreviewed" until a
radiologist confirms it.

Code touched — frontend: `src/services/flames/*`, `src/workers/flamesInBrowser.worker.ts`, `src/hooks/useBrowserFlames.ts`,
`src/components/BrowserFlamesCard.tsx`, `src/components/AiDraftBanner.tsx`; changes to `useSegmentationMask.ts`
(`importMask`), `useSegmentationData.ts` (draft hand-off, no save-on-unload for AI, provenance on save),
`useSegmentationStore.ts`, `SegmentationPanel.tsx` (banner, list name), `ClinicalToolsPanel.tsx` (lazy card behind the
flag), `config/features.ts`, `types/segmentation.ts`, `api/segmentation.ts`; `public/licenses/*`; `package.json` pins
onnxruntime-web 1.24.1. Backend (non-Class-C files): `models/schemas.py` (`AIProvenance`), `services/segmentation_service.py`
(`create_segmentation`), `api/routes/segmentation.py` (create passes provenance; `POST /segmentation/{id}/ai-review/confirm`).
**No module listed as Class C in CLAUDE.md is modified** (`edgeAI.worker.ts`, `ai_segmentation_service.py`, … untouched).

## 2. Requirements (entered as DRAFT in SRS 1.7)

| ID | Short text | Class | Verification | Hazards |
|---|---|---|---|---|
| REQ-FUNC-034 (amended) | FLAMeS on a GPU worker **or** in the browser behind a default-OFF flag | C | Test | HAZ-001 |
| REQ-FUNC-036 (amended) | Browser path: empty result is an explicit warning + acknowledgement; 0 voxels in the provenance | C | Test | HAZ-001 |
| REQ-FUNC-093 | Compute FLAMeS entirely in the browser (flag OFF) | C | Test | HAZ-001, HAZ-006 |
| REQ-FUNC-094 | Parity with `nnUNetv2_predict` (Dice >= 0.99) | C | Test | HAZ-001 |
| REQ-FUNC-095 | Result on the FLAIR's grid in RC-031 order; opened only over the same file/grid | C | Test | HAZ-006 |
| REQ-FUNC-096 | Expected duration, elapsed time, cancel without touching the open segmentation | B | Test | — |
| REQ-FUNC-097 | Licence/attribution notices reachable in the app | A | Test | — |
| REQ-SAFE-029 | Fail closed (no partial result; reason shown) | C | Test | HAZ-001 |
| REQ-SAFE-030 | AI draft labelled; never autosaved; saved only explicitly with provenance (server echo must match exactly); unreviewed until a radiologist confirms **the exact saved mask** (SHA-256 bound; any mask change resets it; no confirmation with unsaved corrections); never shown as manual | C | Test + usability (not done) | HAZ-001 |
| REQ-SAFE-031 | Only the pinned model runs (download and cache) | C | Test | HAZ-001 |
| REQ-SAFE-032 | Opening a draft never discards unsaved work | C | Test | HAZ-001 |
| REQ-SAFE-033 | Only a skull-stripped FLAIR: image-content skull gate + FLAIR content check (refusal only) + **positive evidence of the sequence** (clinician's per-file confirmation recorded with the draft, or a header with a FLAIR inversion time) — fail closed; leave-one-dataset-out sensitivity/specificity documented | C | Test + validation | HAZ-001 |

Full texts: `docs/iec62304/02_Software_Requirements_Specification.md`.

## 3. Hazards touched (RMF §3.3)

No new hazard. New causes of **HAZ-001** (port arithmetic; wrong/tampered model; non-stripped input incl. skull with zero
background; **non-FLAIR input**; GPU garbage / partial result; single fold; draft mistaken for clinician work or saved
without an explicit action; **unsaved work silently replaced**; **empty result read as "no lesions"**; device too weak) and
of **HAZ-006** (axis order; wrong image/grid).

## 4. Risk controls (entered as DRAFT in RMF 1.9 §5.1)

| ID (prototype name) | Control | Status |
|---|---|---|
| RC-040 (RC-F1) | Model size + SHA-256 pin, on download **and** from Cache Storage | test-bound |
| RC-041 (RC-F2) | nnU-Net-faithful port; parity Dice >= 0.99 | test-bound (2 public cases) |
| RC-042 (RC-F3) | Axis-order conversions | test-bound |
| RC-043 (RC-F4) | Skull-stripped gate + **skull clue** (dark layer inside the head region), before the model download | test-bound; validated (FLAIR-GATE-VALIDATION.md), few with-skull cases |
| RC-044 (RC-F5) | Numerical/output guard, WebGPU → WebAssembly whole-job restart | test-bound |
| RC-045 (RC-F6) | One terminal message; worker terminated on cancel/crash | test-bound |
| RC-046 (RC-F7) | Same file + same grid | test-bound |
| RC-047 (RC-F8, extended) | AI-draft labelling + persistent banner; **no save-on-unload**; saved only with provenance, refused unless echoed exactly and unreviewed; server forces "unreviewed"; radiologist confirmation **bound to the SHA-256 of the stored mask, reset on any mask change**, not offered with unsaved corrections | test-bound; usability not evaluated |
| RC-048 (RC-F9) | Flag OFF by default | test-bound; production build checked |
| RC-049 (new; `flair-gate/2` after re-review 2) | FLAIR gate: header can refuse; content can only refuse; acceptance needs positive evidence (clinician confirmation recorded with who confirmed, or a FLAIR inversion time) — fail closed | test-bound; leave-one-dataset-out validation on MSLesSeg, open_ms_data, ISBI-2015 (content alone does not generalise — hence the positive evidence) |
| RC-050 (new) | Never discard unsaved work | test-bound |
| RC-051 (new) | Empty result explicit + acknowledgement | test-bound |
| RC-052 (RC-F10) | 5-fold ensemble (+ mirroring) default before clinical use | **NOT IMPLEMENTED** (CA-FLAMES-1) |
| RC-053 (RC-F11) | Device gate / cross-origin isolation | **NOT IMPLEMENTED** (CA-FLAMES-2); interim honest duration + cancel |

RC-001 ("assistive — requires physician review" on all AI results) remains NOT IMPLEMENTED product-wide; this path
provides its own labelling (RC-047) — reconciled in RMF §5.1.

## 5. Verification plan

| # | Activity | Acceptance | Status (2026-10-18) |
|---|---|---|---|
| V1 | Unit tests (`src/services/flames/__tests__`, hand-off, card, cancel, flag; backend `test_rc047_*`) | all pass in CI | **pass locally 2026-10-21 (after re-review 2)**: frontend 236 passed, 3 skipped (opt-in harnesses), type check clean, production build OK (flag absent); backend unit suite 1307 passed |
| V2 | Negative controls: prototype set M1–M12 + review set (H1–H10, I1–I2, G1–G9 + G5b, F1, B1–B10, U1–U5, P1–P2, E1–E6) and BEFORE runs on both reviewed commits | every mutation detected; reviewed code fails the new tests | **45/46 detected** (all re-run 2026-10-18 on the re-review-2 code; G6 — local normalisation removed — not detectable with phantoms, recorded); the same SHA-256 removals against the pre-fix tests: 0/2 detected (the first review's point); reviewed code (d81cb78, c838bb1) fails the new tests 6/6 — `records/risk_verification/CP-FLAMES-BROWSER-001_negative_controls_2026-10-17.json` |
| V3/V4 | Parity on public P57 1 mm / 4 mm | Dice >= 0.99 | 0.99940 / 0.99934 (prototype) |
| V5 | Real-browser smoke | completes, Dice >= 0.99 | WebAssembly pass; WebGPU fails on this machine (DESIGN.md §7.1) |
| V6 | Ensemble ± mirroring parity | Dice >= 0.99 | not done (CA-FLAMES-1) |
| V7 | >= 10 more public cases, other scanners | Dice >= 0.99 each | not done |
| V8 | Input-gate validation (skull + contrast) on public data, leave-one-dataset-out | 0 accepted without positive evidence; content barrier reported per held-out dataset | **done on available data** (533 volumes, 3 datasets) — without evidence 0/521 accepted; held-out content barrier refuses 18/19 (ISBI-2015), 229/230 (MSLesSeg), 102/102 (open_ms_data); FLAIR availability 87/170 — FLAIR-GATE-VALIDATION.md; native clinical data pending (CA-FLAMES-3) |
| V9 | In-app QA (flag on, staging) incl. save → reload → confirm review | identical mask; provenance shown | not done |
| V10 | Usability (IEC 62366): draft recognised as unreviewed AI output | per plan | not done (CA-FLAMES-4) |
| V11 | Performance on device classes | documented | partial; duration shown to the user |

## 6. Residual-risk view

With RC-040…RC-051 the software-level causes are controlled; cause (f) (single fold) is not (RC-052), and the gates are
heuristics validated on public data only. The FLAIR gate's acceptance rests on a human confirmation (or a header
inversion time); the content check is a second barrier that leave-one-dataset-out shows is not guaranteed on an unseen
scanner (one T1 let through on ISBI-2015). The HAZ-001 residual risk for this path is **UNDETERMINED**; the feature must
stay **OFF** until V6, V7, V9, V10 and CA-FLAMES-1..5 are closed and the owner approves.

## 7. Other findings (recorded for triage)

1. Server tool masks written in the wrong axis order (`tool_runner_service._store_nifti_as_segmentation`, HAZ-006) —
   **addressed by PR #51 (CAPA-011)**, not by this branch.
2. `ClinicalToolsPanel.refreshSegmentations` invalidates `['segmentations', fileId]` but the lists use
   `['segmentations', 'study', studyId]` (UX, dark path) — open.
3. ONNX Runtime Web recorded as 1.21.0 while 1.24.1 is built — **corrected** in SOUP 1.2 (draft) and pinned exactly.
   WebGPU for FLAMeS needs >= 1.29 (Class C SOUP change, also affects `edgeAI.worker.ts`) — not done.
4. The pre-existing border gate (<= 2 % nonzero border) refuses some genuine MNI-space FLAIRs whose brain touches the
   field of view (FLAIR-GATE-VALIDATION.md) — a safe failure, recorded.
5. CMP-001 §5 says "no `^` in production" but most `package.json` dependencies use `^` (lockfile pins them) — open.
