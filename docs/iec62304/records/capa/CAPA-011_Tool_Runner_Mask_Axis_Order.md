# CAPA-011 — Clinical-Tool Masks Stored in the Wrong Axis Order (Double Transpose on Load)

**CAPA ID**: CAPA-011
**Date Opened**: 2026-10-17
**Source**: Independent code review, confirmed by the reviewer with a local test; reproduced by this CAPA with a behavioural round-trip test (§5)
**Severity**: **CRITICAL**. A lesion mask or parcellation produced by a clinical tool is shown, and used for region classification, at a different voxel than the one the tool segmented (HAZ-006 orientation error; HAZ-001 lesion delineation; HAZ-005 MAGNIMS region, and through it HAZ-008 DIS). On cubic volumes the error is silent. QP-002 §5.
**Owner**: *(to be assigned: Software Safety Officer / QMS Manager)*
**Status**: OPEN.
- Implemented on branch `fix/tool-runner-mask-axes-capa011` (PR #51, draft, based on `fix/viewer-safety-capa010`; **merge after PR #52 / CAPA-010**): CA-11.1 to CA-11.5, PA-11.1. **Owner approval: approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63).**
- Identifiers: **RC-039** and **REQ-SAFE-028**, renumbered on 2026-10-17 from RC-038 / REQ-SAFE-025, which CAPA-010 (merged first) uses. The document versions follow CAPA-010's: SRS 1.6, RMF 1.8, TM 1.5.
- Pending: PA-11.2 (data check, owner decision), PA-11.4, PA-11.5 (development environment writes to production, owner decision).
- Effectiveness is not verified.

**Procedure**: QP-002 (`docs/qms/QP-002_CAPA_Procedure.md`) · SPR-001
**Related**: HAZ-006 · HAZ-001 · HAZ-005 · HAZ-008 · new REQ-SAFE-028 · REQ-FUNC-034/035 · RC-031 (unregistered, CAPA-006 PA-6.6) · new RC-039 · CAPA-006

---

## 1. Findings

### Finding 1 — Tool masks were transposed twice

The app keeps a segmentation in memory in its internal order (k, a0, a1): slice first, then the
two in-plane axes of the MRI (RC-031). On disk, a mask carrying the RC-031 v2 marker
(`descrip = RC031-ORIENT-V2`) must hold the MRI's own voxel order (a0, a1, k). The loader
(`SegmentationService._load_masks_from_gcs` → `_nifti_native_to_internal`) reads the marker and
applies the (2, 0, 1) transpose once.

`ToolRunnerService._store_nifti_as_segmentation` (`tool_runner_service.py:883-885` and `:924` on
`main`, with the transpose at `:829-831`):
1. brought the tool's mask into the internal order (k, a0, a1);
2. wrote **that** array to `segmentations/{id}/masks.nii.gz`;
3. tagged it with the v2 marker.

On load the (2, 0, 1) transpose was applied a second time. The axes came back swapped:
- **non-cubic volume** (6 × 9 × 4): the loaded mask had shape (9, 4, 6) instead of (4, 6, 9);
- **cubic volume** (7 × 7 × 7): the shape matched and the lesion at MRI voxel (5, 1, 4) was loaded
  at (4, 5, 1). Nothing signals the error.

The stored file itself was also wrong for direct display (3D viewer, ITK-SNAP): the array was in
(k, a0, a1) order under an affine that describes (a0, a1, k).

**Affected:** every mask written through this path:

| Tool | Call site | Stored mask |
|---|---|---|
| FLAMeS | `_execute_flames` | lesion mask |
| LST-AI | `_execute_lstai` | lesion-types mask (zones), used by the MAGNIMS "LST-AI zones" path |
| SynthSeg | `_execute_synthseg` | parcellation, used by the MAGNIMS parcellation path |
| mindGlide | `_execute_mindglide` | lesion mask and structure mask (two stores) |

**Consequences** (not observed in use — see Finding 4): the overlay at the wrong place in the 2D
and 3D viewers; lesion position, region (PV/JC/IT/DWM) and DIS computed at the wrong place. The
MAGNIMS paths that read these masks (LST-AI zones, parcellation) combine them voxel by voxel with
the lesion mask and can only notice a shape difference, so on cubic data a transposed mask is
accepted. Lesion counts and total volume do not depend on axis order.

### Finding 2 — The stored affine did not match the stored array after reorientation

When a tool writes its mask in a different voxel order than the MRI (for example canonical RAS),
RC-031 reorients the array onto the MRI grid by affine. The file was then written with the
**tool's** affine, which describes the array before reorientation. A directly served file was
therefore at the wrong physical position whenever reorientation changed the array.

### Finding 3 — A mask whose position could not be established was still stored

Without a usable reference image (none passed, file missing or unreadable) or with an affine that
cannot place the mask on it, RC-031 "failed safe" to the legacy (2, 1, 0) order and stored the
mask. That order is known to be the in-plane transpose of the display, and the file was also
tagged v2. A clinician would have received a mask in a position the software could not vouch for.
With an indeterminate affine the old path happened to crash inside the NIfTI library ("Could not
decompose affine") before upload: nothing was stored, but by accident and with an unclear error.
Now refused (CA-11.4).

### Finding 4 — Exposure

- **Production:** the four tools are off. `config.py` defaults `LSTAI_ENABLED`, `SYNTHSEG_ENABLED`,
  `MINDGLIDE_ENABLED` and `FLAMES_ENABLED` to `False`, and the live Cloud Run services set none of
  them (verified by the requester before this CAPA; this audit ran no cloud command). No clinician
  has seen a tool mask in production.
- **Local:** `docker-compose.yml` enables LST-AI, SynthSeg and mindGlide, and by default points at
  production storage (Finding 7). A local run could therefore have written affected masks into the
  **production** bucket and Firestore. This was not checked (PA-11.2).
- **Window:** from 2026-08-19 (commit `7fcf1cd`, which switched the store to the canonical NIfTI
  path with the v2 marker, and `e1aea68`, which fixed the upload signature) until this fix. Before
  that, no tool mask could be stored at all (upload `TypeError`) or loaded (non-canonical `.bin`
  path).

### Finding 5 — No other writer has the defect

Searched every NIfTI writer in `backend/app` and `flames-worker`, and every use of the marker
(constant and literal):

| Writer | Order on disk | Marker | Status |
|---|---|---|---|
| `SegmentationService._save_masks_to_gcs` (painted / edited masks, zone maps) | `_internal_to_nifti_native` → (a0, a1, k) | v2 | Correct (bound by `test_rc031_save_orientation.py`) |
| `SegmentationService._save_as_nifti` (local fallback) | `transpose_for_nifti` → legacy (a1, a0, k) | none | Consistent: read with the legacy order |
| `ToolRunnerService._store_nifti_as_segmentation` | internal (k, a0, a1) | v2 | **Defect (this CAPA)** |
| `flames-worker/server.py` | tool output on the FLAIR grid | none | Staging file only; re-stored by the tool runner |
| `segmentation.py` `/nifti?ref_file_id=` | served, not stored | — | Reads the marker (RC-031) |
| Upload scripts (`scripts/upload_isbi_segmentations.py`, `migrate_cross_session_masks.py`) | through the API (internal order) | set by the server | Correct path |

### Finding 6 — Why nothing caught it

1. **No round trip was tested.** The ingest helper (`_orient_mask_to_display`) was tested on its
   own; the store test checked only the upload path and signature. No test stored a tool mask and
   loaded it back through the viewer's path.
2. **The contract lived in two places.** The tool runner copied the marker as a literal
   (`b"RC031-ORIENT-V2"`) without the array transform that the marker requires.
3. **RC-031 was never registered.** It is in neither the RMF nor the manifest (CAPA-006 PA-6.6
   pending), so no bound test enforced its storage contract.
4. **Cubic test volumes hide it.** The shape is unchanged; only the voxel position reveals it.

### Finding 8 — A mask on another grid was stored (pre-merge review, 2026-10-18)

The reorientation (RC-031) only permutes and flips axes; nothing checked that the tool's mask,
after reorientation, is on the **same grid** as the image it was computed on. The pre-merge review
reproduced it: a 20 × 20 × 30 mask at 1 mm over a 40 × 40 × 10 study was stored silently and the
task ended "completed". SynthSeg returns its parcellation at 1 mm, so any study not acquired at
1 mm would hit this; the overlay, regions and volumes would then be computed on a grid that does
not match the image. REQ-SAFE-028 already promised that a mask whose position cannot be
established is not stored. Now refused (CA-11.5).

Consequence for the owner: until a sidecar returns its result on the input image's own grid (for
SynthSeg, resampling the parcellation back to the input grid), its results on such studies are
refused, not stored (PA-11.4).

### Finding 7 — OPEN (owner): the local development setup writes to production storage

`docker-compose.yml` turns on three of the four clinical tools (`LSTAI_ENABLED`,
`SYNTHSEG_ENABLED`, `MINDGLIDE_ENABLED` = `true`; FLAMeS is not enabled there) and sets **no**
storage target, so the production defaults apply:
- bucket: `GCS_BUCKET_NAME` defaults to `brain-mri-medical-images` (`app/core/config.py`);
- Firestore project: `GOOGLE_CLOUD_PROJECT` defaults to `brain-mri-476110`
  (`app/core/firebase.py`);
- it mounts `backend/credentials.json` (a `brain-mri-476110` service account). Whether the
  container authenticates depends on the developer's credentials (it sets no
  `GOOGLE_APPLICATION_CREDENTIALS`).

A local or development environment must never write to production: development runs (and any
defect they carry, such as this CAPA's) would appear in clinicians' patient records.

**Proposed fix (not implemented in this PR; owner decision, PA-11.5):**
1. A separate development GCP project (or at least a separate bucket and Firestore database) with
   its own service account that has **no** access to production.
2. `docker-compose.yml` sets `ENVIRONMENT=development`, `GCS_BUCKET_NAME=<dev bucket>`,
   `GOOGLE_CLOUD_PROJECT=<dev project>` and `GOOGLE_APPLICATION_CREDENTIALS` pointing at the
   development key; the production key is never mounted.
3. A start-up guard: outside `ENVIRONMENT=production`, refuse to start when the bucket or project
   is the production one.
4. Remove the production defaults from `config.py` / `firebase.py` (no default = must be set
   explicitly), so a forgotten variable fails closed instead of reaching production.

## 2. Corrective Actions

| ID | Action | Status |
|----|--------|--------|
| **CA-11.1** | New `ToolRunnerService._orient_mask_for_storage` returns the array and affine to store: the mask reoriented onto the reference MRI's voxel order (a0, a1, k), stored under the v2 marker. `_store_nifti_as_segmentation` stores that array, not the internal one | **DONE** (branch) |
| **CA-11.2** | The stored affine is the affine of the reoriented array (the tool's affine composed with the same axis permutation/flips). It equals the MRI's affine when the tool kept the MRI grid | **DONE** (branch) |
| **CA-11.3** | The internal mask used for counts and shape is computed through the loader's own decode (`SegmentationService._nifti_native_to_internal`), and the marker comes from the shared constant, so ingest and load cannot diverge again | **DONE** (branch) |
| **CA-11.4** | **Fail closed** (follow-up requested during review, consistent with the project's fail-closed rule, e.g. CAPA-009's 404 when it cannot decide). When the reference image is not passed, missing or unreadable, or the mask cannot be placed on it (indeterminate affine), nothing is stored: no mask object, no segmentation record. The error is logged (`[RC-039] Clinical-tool mask NOT stored`) and raised as `SegmentationException` (`TOOL_MASK_REFERENCE_UNAVAILABLE`); the tool's task ends **FAILED** with the message "The tool's segmentation was not stored: … its position in the image cannot be established (RC-039). Re-run the tool." The legacy-order fallback is removed. Existing tests adapted: `test_rc031_ingest_orientation_fix.py` (`TestFailsSafeToLegacy` → `TestFailsClosed`, 3 tests now expect the refusal); `test_flames_integration.py` and `test_clinical_tool_empty_mask.py` now pass the reference image, which is required | **DONE** (branch) |
| **CA-11.5** | **Same grid required** (pre-merge review, Finding 8). After reorientation the mask must have the image's array shape and a voxel-to-scanner transform equal to the image's within `_GRID_TOLERANCE` = 0.001 in every element (mm per voxel, mm): float rounding of a re-written header passes, a sub-millimetre shift or another voxel size does not. Otherwise nothing is stored, the refusal is logged and raised as `SegmentationException` `TOOL_MASK_GRID_MISMATCH` ("… it is not on the grid of the image it was computed on (mask … voxels, image …) … The tool must return its result on the image's own grid."), and the tool's task ends FAILED | **DONE** (branch) |

No Class C module listed in `CLAUDE.md` was modified. `tool_runner_service.py` and
`segmentation_service.py` are not on that list; `segmentation_service.py` is unchanged.

## 3. Preventive Actions

| ID | Action | Status |
|----|--------|--------|
| **PA-11.1** | `test_rc039_tool_runner_mask_axes.py` (28 `test_rc039_*` cases), bound to RC-039 in `rc_test_manifest.json`. Real store path and real load path (`SegmentationService.get_mask`), on a non-cubic asymmetric volume with a flipped, anisotropic, translated affine and one marked voxel; asserts the same voxel (a0, a1, k), the same scanner position, the same slice layout, and the same position in the stored file served to the 3D viewer. Also: the cubic silent case; a tool writing another voxel order; the LST-AI types mask; the marker/order contract; **every tool end to end** through its real `_execute_*` method (FLAMeS, LST-AI, SynthSeg, mindGlide lesion and structure masks), each in the MRI's grid and in another voxel order; **fail closed** — no reference, missing file, unreadable file, indeterminate affine → error, no mask object, no record; and each of the four tools end to end with an unreadable reference → task FAILED with a clear error, nothing stored; **same grid** (pre-merge review) — a different array shape, a 0.5 mm shift, and a SynthSeg-like 1 mm output over a 0.5 × 0.5 × 3 mm study are refused with nothing stored, the SynthSeg run end to end with a 1 mm output ends FAILED with nothing stored, and a transform differing only by float rounding is accepted (positive control); **stored record** — `image_shape` = [a0, a1, k] of the image, `annotated_voxels`, and agreement with the loaded mask's dimensions. Negative controls: `scripts/safety/capa011_negative_controls.py` | **DONE** (branch) |
| **PA-11.2** | Read-only data check for masks already stored with swapped axes (procedure in §6). No data migrated | **PENDING** — owner decision |
| **PA-11.3** | Decide whether the legacy fallback should refuse instead | **SUPERSEDED** by CA-11.4 (implemented on branch; approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63)) |
| **PA-11.4** | Before any tool is enabled anywhere: run each real sidecar once and confirm, with this round-trip check, that its output is on the input image's grid. Since CA-11.5 an output on another grid is refused rather than stored; SynthSeg returns 1 mm, so its sidecar must resample the parcellation back to the input grid (nearest neighbour) or its results on non-1 mm studies will be refused. Not examined with real sidecars by this CAPA | **PENDING** |
| **PA-11.5** | Separate the development environment from production storage (Finding 7: separate project/bucket and credentials via environment variables, start-up guard, no production defaults). Not implemented in this PR | **PENDING** — owner decision |

CAPA-006 PA-6.6 (register RC-031 in RMF §5.1 and the manifest) remains open. RC-039 covers only
the clinical-tool part of RC-031's storage contract.

## 4. Root Cause

1. **Verification that could not observe the failure** (fourth occurrence, after CAPA-006,
   CAPA-007 and CAPA-009): each half of the contract was tested alone, never the round trip a
   clinician depends on.
2. **A safety convention duplicated by hand.** The orientation marker was copied as a literal into a
   second writer without its paired transform.
3. **An unregistered risk control.** RC-031 had no bound test, so changing a writer could not turn
   CI red.
4. **Reorientation taken for placement** (Finding 8, found in the pre-merge review of this CAPA):
   permuting axes was assumed to put the mask on the image's grid; the precondition (same grid)
   was neither stated nor checked, and the first version of this CAPA's tests used tool outputs
   on the image's grid only.

## 5. Verification Evidence (executed 2026-10-17; grid check 2026-10-18)

- **Reproduced on `main` (before the fix):** the round-trip tests (then named `test_rc038_*`, now
  `test_rc039_tool_runner_mask_axes.py`) → **14 failed**.
  Examples:
  - non-cubic: "loaded mask has shape (9, 4, 6); the MRI's internal grid is (4, 6, 9)";
  - cubic: "lesion loaded at internal [(1, 4, 5)]; it was computed at MRI voxel (a0,a1,k)=(5,1,4)
    -> internal (4, 5, 1)" — the reviewer's (5, 1, 4) → (4, 5, 1);
  - marker contract: "a v2-marked mask must be stored in the MRI's voxel order".
- **After the first fix** (commit `a623671`, before the fail-closed change; squashed into one
  commit when the branch was rebased onto CAPA-010): those 14 passed; the existing RC-031 ingest,
  save-orientation, FLAMeS store-back and empty-mask tests passed unchanged.
- **Fail closed (CA-11.4):** the 8 new fail-closed cases were run against that first-fix code
  (legacy fallback still in place; the same state is re-created by negative control F1 in the
  durable record): **8 failed** — 3 store-path cases "DID NOT RAISE"
  (the mask was stored), the indeterminate-affine case crashed inside the NIfTI library ("Could not
  decompose affine", not a clear refusal), and the 4 tool runs ended COMPLETED with a mask stored.
  With CA-11.4: all 21 cases passed.
- **Same grid (CA-11.5, pre-merge review, 2026-10-18):** the 7 new cases were first run against
  the code before CA-11.5: the **4 grid cases failed** — shape mismatch, 0.5 mm shift and 1 mm
  resampled output "DID NOT RAISE" (the mask was stored), and the SynthSeg run with a 1 mm output
  ended COMPLETED. The 2 stored-record cases and the float-rounding positive control passed
  before and after, as designed (they guard against mutation M1 and an over-strict tolerance).
  With CA-11.5: all 28 cases pass.
- **Negative controls** (`docs/iec62304/records/risk_verification/CAPA-011_negative_controls_2026-10-17.json`,
  re-run 2026-10-18 after CA-11.5): 22 mutations, one at a time, every anchor asserted unique; **22 of 22 detected**; restored 28 passed. G2 is detected only by the shape-mismatch case, G3 and G4 only by the 0.5 mm shift case (the 1 mm resampled cases are refused on shape as well); each sub-check therefore rests on one test.

  | Mutation | Re-introduces | Failed (of 28) |
  |---|---|---|
  | D0 | The pre-fix store block, byte for byte | 16 |
  | D1 | Internal array under the marker (affine and marker otherwise correct) | 16 |
  | D2 | In-plane swap (a1, a0, k) under the marker | 16 |
  | D3 | Tool's affine after reorientation | 5 |
  | D4 | Reorientation skipped | 6 |
  | D6 | Marker never set | 16 |
  | L1 | Loader ignores the marker | 15 |
  | F1 | **The former fallback** (legacy (2,1,0) order) instead of the refusal | 12 |
  | F2 | Fallback storing the tool's array as-is | 12 |
  | F3 | Fallback only for a missing / absent reference | 2 |
  | F4 | Fallback only for an unreadable reference / indeterminate affine | 6 |
  | F5 | Store path catches the refusal and stores anyway | 12 |
  | G1 | **Grid check removed** (the defect the pre-merge review reproduced) | 4 |
  | G2 | Shape check removed (transform only) | 1 |
  | G3 | Transform check removed (shape only) | 1 |
  | G4 | Grid tolerance loosened to 1 mm | 1 |
  | M1 | Stored record computed from the mask read in the legacy order | 2 |
  | T1–T5 | Reference MRI dropped at the LST-AI, FLAMeS, SynthSeg, mindGlide-lesion, mindGlide-structure call site | 2, 2, 3, 2, 2 |

  Earlier runs: before CA-11.4, 13 mutations (incl. "marker always set on the fail-safe file", which
  no longer applies), 13/13 detected; after CA-11.4, 17/17. The pre-merge review found that a
  mutation reading the internal mask in the old order survived, because no test checked the
  dimensions written to the stored record; it is now mutation M1, covered by the stored-record
  test.
- **Full backend suite** (no cloud credentials, as in CI), after CA-11.5:
  - `tests/unit`: **1249 passed**, 0 failed (the 28 RC-039 cases included);
  - risk-control manifest gate: 222 passed; `-k test_rc` gate: 426 passed;
  - `tests/integration` (CI filter): 25 passed, 1 failed —
    `test_auth_endpoints.py::TestWebAuthnEndpoints::test_webauthn_credentials_endpoint_exists`, because
    the local environment lacks the `webauthn` package. Local only, unrelated to this change; not
    modified.

**Not verified.** Real sidecar outputs (the tools are off; no sidecar was run). Stored data
(PA-11.2). The 2D viewer's behaviour when it received a mask of the wrong shape.

## 6. Proposed Data Check (PA-11.2 — read-only, not executed)

Run by the owner, with read-only access, against the production project:

1. Firestore `segmentations` collection: documents with `created_by == "system"` (written only by
   the tool runner) and `validation_source` in `flames-v1.0`, `lst-ai-v1.0.3`, `synthseg-v2.0`,
   `mindglide-v1.0`, `mindglide-v1.0-structures`, and `created_at >= 2026-08-19`.
2. For each one, read the header of `segmentations/{id}/masks.nii.gz` and of the source image
   (`file_id`).
   - Marker present and stored shape = (k, a0, a1) of the source image → affected.
   - Cubic source image: the shape cannot tell → treat as affected. Every tool mask written in the
     window carries the defect by construction.
3. Report the count. Expected result if no local run reached production: **zero documents**.

If any are found, the owner decides between deleting them and re-running the tool, or a controlled
one-off rewrite. No data was migrated by this CAPA.

## 7. Regulatory Assessment

- The device is not CE-marked and not in clinical use; the tools are off in production. No
  vigilance reporting obligation.
- No clinician is known to have seen an affected mask.

---

**Prepared by**: internal audit, 2026-10-17.
**Approval**: approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63) (required before merge and deployment).
