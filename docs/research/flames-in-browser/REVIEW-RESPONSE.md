# Response to the adversarial review ("do not approve yet") — CP-FLAMES-BROWSER-001

| | |
|---|---|
| Date | 2026-10-17/18 |
| Branch | `feat/flames-in-browser` (flag `VITE_ENABLE_BROWSER_FLAMES` still **OFF** by default; nothing deployed) |
| Records | SRS 1.7, RMF 1.9, TM 1.6, SOUP 1.2, CMP 1.1 — all **DRAFT, PENDING owner approval** (versions 1.5/1.6, 1.7/1.8, 1.4/1.5 are reserved by open PRs #52 and #51: merge this after them) |
| Negative controls | `docs/iec62304/records/risk_verification/CP-FLAMES-BROWSER-001_negative_controls_2026-10-17.json` (script `research/flames_in_browser/negative_controls_v2.py`) |

Each finding below: what was wrong, what changed, the behavioural test, and the evidence that the test fails
before the fix and passes after.

## 1. A skull-stripped T1 passed every gate and returned "0 lesions" as a normal result

**Fix (RC-049, RC-043, RC-051; REQ-SAFE-033, REQ-FUNC-036).**
* FLAIR contrast gate that never uses the file name (`contrastGate.ts`, `headerEvidence.ts`, `nifti.ts`):
  * header evidence — NIfTI `descrip`/`aux_file`/`intent_name`/`db_name`, text in NIfTI extensions, DICOM attributes in a
    DICOM extension (InversionTime, SeriesDescription, ProtocolName, SequenceName) and the series description the app holds
    for the same file — can only **refuse** (inversion time < 1400 ms; T1/MPRAGE/T2/PD/DWI/... named without FLAIR;
    "T1 FLAIR");
  * the image content must always look like FLAIR: white matter not brighter than the cortex after a 15 mm local
    normalisation (T1 rule) and no bright CSF (T2/PD rule); a contrast that cannot be measured is refused.
* Skull clue added to the skull-stripped gate (dark bone layer inside the head region) — see §1b.
* Both gates run in the worker **before the 62 MB model download**, and again inside the pipeline.
* Empty result: explicit warning ("does NOT show that the scan is free of lesions"), opening the draft requires an
  acknowledgement, the description says "EMPTY RESULT", 0 annotated voxels stored in the provenance.

**Validation on public data** (`FLAIR-GATE-VALIDATION.md`; 495 volumes; the harness runs the shipped TypeScript):
* contrast gate alone: T1 refused **151/151**, T1 post-contrast 30/30, T2 149/151 → specificity 0.994 [0.978–0.998];
  genuine stripped FLAIRs accepted 136/151 → sensitivity 0.901 [0.843–0.939] (open_ms 36/36, MSLesSeg 100/115);
* complete input gate: non-FLAIR refused 343/344; stripped FLAIRs accepted 112/151 (0.742) — most extra refusals are
  FLAIRs whose skull stripping left bright orbital/skull-base tissue (9 of 9 inspected visually); with-skull FLAIRs
  refused 12/12.

**Tests.** `inputGates.test.ts` (synthetic FLAIR/T1/T2 phantoms, bias field, header can only refuse, skull with zero
background), `niftiHeader.test.ts`, `pipeline.test.ts` ("refuses a T1-like one before any network call"),
`BrowserFlamesCard.test.tsx` (`rc051`). Before/after: BEFORE-1 (the reviewed `pipeline.ts` lets the T1 phantom run
through the network) fails; G1–G9 detected.

### 1b. "A FLAIR with skull but zero background could pass the gate" — confirmed, fixed
On 6 public open_ms_data FLAIRs with skull, the original border/volume gate **accepted 7 of 12** images (3 as
distributed, 4 with the background set to zero). Two skull clues were added: very bright voxels (scalp fat) within 6 mm
of the region's edge (> 1 %; with-skull images 3.9–7.9 %), and a large very dark share inside the region (> 20 %;
catches noisy-background heads). All 12 are now refused (`FLAIR-GATE-VALIDATION.md` §3.2). A "dark bone layer" clue
was tried first and rejected: on these FLAIRs the skull is not dark enough (zero-background heads 8–11 % dark, stripped
brains up to 17.5 %). Only 6 with-skull subjects (one scanner) were available — limitation recorded in RMF §7.2
(CA-FLAMES-3).

## 2. The unreviewed AI draft could be saved without the clinician pressing Save, as MANUAL work

**Fix (RC-047; REQ-SAFE-030).**
* The save-on-unload of manual work never saves an AI segmentation (local draft or saved AI result); the browser's
  "leave page?" warning remains (`useSegmentationData.ts`).
* While open, the segmentation is `automatic` with its provenance, never `manual`.
* Explicit Save sends `ai_provenance` (model name, model version, model SHA-256, fold, source checkpoint SHA-256,
  pipeline version, runtime, generation time, lesion count, annotated voxels). If the server does not echo it, the record
  is deleted and the save fails (fail closed).
* Backend: `AIProvenance` schema; `create_segmentation` stores `segmentation_type = automatic`,
  `validation_source = flames-browser-fold0-<sha12>` and forces `review_status = unreviewed`; new
  `POST /segmentation/{id}/ai-review/confirm` (radiologist only, object-authorized, records who and when; 409 for manual work).
* UI: persistent "AI draft — UNREVIEWED" banner wherever the segmentation is open; saved list names it
  `[AI draft — UNREVIEWED] FLAMeS fold 0`.

**Tests.** `useSegmentationData.flamesDraft.test.tsx` (`rc047`), `BrowserFlamesCard.test.tsx`,
`backend/tests/unit/test_rc047_ai_draft_provenance.py`, CAPA-009 route classification. BEFORE-2/3 (reviewed code) fails;
H1–H4, B1–B5 detected.

## 3. Opening the draft silently discarded the clinician's unsaved work

**Fix (RC-050; REQ-SAFE-032).** `createSegmentationFromMask` returns `{ok:false, reason:'unsaved-work'}` and touches
nothing when the open segmentation has unsaved edits (or edits kept after a refused save). The card then asks:
"Keep my work (do not open)" or "Discard my unsaved changes and open the draft"; only the second, explicit choice
replaces it.

**Tests.** `useSegmentationData.flamesDraft.test.tsx` and `BrowserFlamesCard.test.tsx` (`rc050`); BEFORE-2/3 fails;
H5, H6 detected.

## 4. Missing tests: model SHA-256 (download and cache) and the hand-off

* `modelStore.test.ts` drives `loadVerifiedModel` (what the worker calls) with a fake Cache Storage and fetch.
  Removing the SHA-256 check on the cache path (I1) or on the download path (I2) now fails tests; the **same
  mutations against the pre-fix test set (I1-old, I2-old) were not detected** — that was the reviewer's point.
* Hand-off tests: see §2 and §3. Cancel test: `useBrowserFlames.cancel.test.tsx` (H10).
* CM consistency: `draft-model.test.ts` checks that the pin equals the committed export manifest and that the model
  folder stays git-ignored.

## 5. IEC 62304 records

* SRS 1.7 (draft): REQ-FUNC-034 amended (it said "executed on an isolated GPU inference worker"), REQ-FUNC-036 amended,
  REQ-FUNC-093..097, REQ-SAFE-029..033.
* RMF 1.9 (draft): HAZ-001/HAZ-006 causes (§3.3), RC-040..RC-051 (test-bound), RC-052/RC-053 **not implemented**,
  RC-001 reconciled honestly (still NOT IMPLEMENTED product-wide; only this path is labelled), residual risk for this
  path UNDETERMINED, open items CA-FLAMES-1..5.
* TM 1.6 (draft): forward, safety and backward rows; `rc_test_manifest.json` entries (manifest gate passes).
* SOUP 1.2 (draft): ONNX Runtime Web **1.24.1** (was recorded as 1.21.0; `package.json` now pins 1.24.1 exactly),
  FLAMeS weights and Neurodesk-derived code added; SBOM corrected.
* CMP 1.1 (draft) §6: model file not in git; SHA-256 pin in `plan.ts` + committed manifest; proposed archive
  `gs://mstool-research-data/models/flames/v2.0/...` (not created, no cloud command run) + release attachment; Git LFS
  rejected; release step `research/flames_in_browser/stage_model.py` (verified against the local archived file).
* Licences reachable in the app: "Licences and attribution" panel in the card (FLAMeS CC BY 4.0, Zenodo 17955359,
  changes; Neurodesk and nnU-Net Apache-2.0; ONNX Runtime MIT) and full texts under `/licenses/`.

## 6. Single-thread WebAssembly (no COOP/COEP)

`firebase.json` is unchanged. Impact analysis: [COOP-COEP-IMPACT.md](COOP-COEP-IMPACT.md) (no OAuth pop-ups; the
real breakage is the PDF/image preview of GCS signed URLs in the document viewer). The card now states the expected
duration ("about 20–42 minutes: this page can use only 1 processor thread (estimate, not measured)"), shows the elapsed
time, and Cancel never touches the open segmentation.

## 7. Conflicts with `feat/viewer-v3` (not merged)

Files changed by both branches (computed with `git diff --name-only` against the common base 6209131; will conflict
or need a manual merge): `.gitignore`, `docs/iec62304/02_Software_Requirements_Specification.md` (viewer-v3 also
proposes an SRS 1.5), `frontend/src/components/ClinicalToolsPanel.tsx`, `frontend/src/components/SegmentationPanel.tsx`,
`frontend/src/hooks/useSegmentationMask.ts`. Semantic dependencies without textual conflict: `useViewerStore`
(`currentSeries`, used by the card's grid check) and `useSegmentationData`'s callers in `ImageViewer2D.tsx`.
