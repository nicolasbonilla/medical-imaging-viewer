# Response to the adversarial reviews ("do not approve yet", "do not merge yet") — CP-FLAMES-BROWSER-001

| | |
|---|---|
| Date | 2026-10-17/18 |
| Branch | `feat/flames-in-browser` (flag `VITE_ENABLE_BROWSER_FLAMES` still **OFF** by default; nothing deployed) |
| Records | SRS 1.7, RMF 1.9, TM 1.6, SOUP 1.2, CMP 1.1 — all **DRAFT, PENDING owner approval** (versions 1.5/1.6, 1.7/1.8, 1.4/1.5 are reserved by open PRs #52 and #51: merge this after them) |
| Negative controls | `docs/iec62304/records/risk_verification/CP-FLAMES-BROWSER-001_negative_controls_2026-10-17.json` (script `research/flames_in_browser/negative_controls_v2.py`) |
| Re-review 2 | 2026-10-18, made on commit `c838bb1` ("do not merge yet"): see **§8** — FLAIR gate redesigned (positive evidence, fail closed), review confirmation bound to the exact mask, stricter provenance echo |

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

**Validation on public data, as first reported (gate `flair-gate/1`; 495 volumes; superseded — see §8):**
* contrast part **alone**: T1 refused 151/151, T1 post-contrast 30/30, T2 149/151; stripped FLAIRs accepted 136/151.
  *Correction (re-review 2): "accepts 136/151 good FLAIR" was quoted in the PR for the gate as a whole; that is the
  contrast part alone.*
* **complete** input gate: stripped FLAIRs accepted **112/151** (0.742 [0.667–0.805]); non-FLAIR refused 343/344 (MSLesSeg
  `P71_T2` accepted); with-skull FLAIRs refused 12/12.
* Not known then: on ISBI-2015 (an unseen scanner) the complete `flair-gate/1` gate accepted **10 of 19 skull-stripped
  T1** as FLAIR. Hence §8.1.

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

## 8. Re-review 2 (2026-10-18, on `c838bb1`): "do not merge yet"

### 8.1 "The FLAIR gate does not generalise" — confirmed; redesigned to fail closed (RC-049, REQ-SAFE-033)

* Confirmed on the recorded rows: the complete `flair-gate/1` gate accepted 10 of 19 ISBI-2015 skull-stripped T1.
* **Leave-one-dataset-out** (MSLesSeg, open_ms_data, ISBI-2015 — every local public set with image volumes;
  `research/flames_in_browser/gate_lodo.py`): fitting on two sets and testing on the third, the content check refuses
  18/19 (ISBI-2015), 229/230 (MSLesSeg) and 102/102 (open_ms_data) non-FLAIR volumes with the full gate; content alone
  lets 1 T1 (ISBI `case007`) and 33 T2 (MSLesSeg) through. **Content alone cannot guarantee it.**
* **`flair-gate/2`:** content is refusal-only (re-fitted: T1 rule 0.915, new grey-matter-class T1 rule 27 %, T2 rule
  2.5 %); acceptance needs **positive evidence** — the clinician's explicit per-file confirmation of the sequence
  (recorded with the draft as `sequence_evidence = clinician`, the server records `sequence_confirmed_by` from the
  authenticated user), or a header with a FLAIR inversion time (≥ 1400 ms). A "FLAIR" text label alone is not proof.
  Without evidence nothing is accepted: **0/170 FLAIR, 0/351 non-FLAIR** on the 533 public volumes.
* With the clinician's confirmation (most permissive input), apparent: FLAIR 87/170 accepted (ISBI 12/19, MSLesSeg
  40/115, open_ms 35/36), non-FLAIR 351/351 refused, with skull 12/12 refused. About half of genuine FLAIRs are refused —
  a safe failure, recorded as a usability limit.
* Full tables, per held-out dataset with Wilson intervals: `FLAIR-GATE-VALIDATION.md` §3–§5; evidence
  `evidence/gate-flair-gate-2-2026-10-18.json`, `evidence/gate-validation-isbi2015-2026-10-18.json`.

**Tests.** `inputGates.test.ts` (no evidence → refused; a FLAIR label alone → refused; header with inversion time →
accepted; T1/T2 refused even when "confirmed"; grey-class rule), `pipeline.test.ts`, `BrowserFlamesCard.test.tsx` (run
disabled until the clinician ticks the confirmation; cleared when the file changes), `useBrowserFlames.cancel.test.tsx`
(confirmation forwarded only when given), backend `test_rc047_ai_draft_provenance.py` (`sequence_confirmed_by` from
the authenticated user). Negative controls E1–E6, B10; BEFORE-R1 (the re-reviewed `contrastGate.ts` + `pipeline.ts`)
fails the new tests.

### 8.2 "Radiologist confirmation is not bound to the mask" — confirmed; fixed (RC-047, REQ-SAFE-030)

* The confirmation now records `reviewed_mask_sha256`: the SHA-256 of the exact stored mask (depth × height × width
  bytes; identical on the client and the server). The confirm route requires the client to send the SHA-256 of the mask
  on screen and refuses (409) unless it equals the stored mask.
* **Any mask change resets the review to "unreviewed".** Enforced at the single save point of the service
  (`_save_segmentation` → `enforce_review_binding`), so every path that changes the mask (full upload, slice edits,
  tools) is covered; the mask upload route also reports `ai_review_reset`.
* The banner has **no confirm button while there are unsaved corrections** ("save them first"); after saving
  corrections the app re-reads the provenance from the server (and shows "unreviewed" if that fails). A confirmed
  review names the saved mask it covers.

**Tests (fail before, pass after).** Backend `test_rc047_ai_draft_provenance.py`: confirm binds the hash; a mismatched
hash is refused; the reviewer's scenario (radiologist confirms, technician replaces the whole mask → unreviewed);
identical re-upload keeps the confirmation; any persist path resets. Frontend `AiDraftBanner.test.tsx` (no button with
unsaved corrections; the digest of the mask on screen is sent; refusal shown), `useSegmentationData.flamesDraft.test.tsx`
(provenance re-read after saving corrections; fail-safe "unreviewed"; unsaved flag and digest published). Negative
controls B6–B9, U1–U5; BEFORE-R2a (frontend) and BEFORE-R2b (backend) fail the new tests.

### 8.3 "`provenanceRecorded` accepts another model hash or an already confirmed echo" — fixed

The server echo must carry exactly the model name, version, SHA-256, fold, source checkpoint, pipeline version and
sequence evidence that were sent, with `review_status = unreviewed` and no reviewer, review time or reviewed-mask hash;
otherwise the record is deleted and the save fails. Tests: `draft-model.test.ts` (every field mutated),
`useSegmentationData.flamesDraft.test.tsx` (another hash, another fold, "confirmed" → refused, orphan deleted). Negative
controls P1, P2; BEFORE-R3 fails.
