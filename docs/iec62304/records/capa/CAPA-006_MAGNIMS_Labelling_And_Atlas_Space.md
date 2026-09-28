# CAPA-006 — MAGNIMS Region Classification: Labelling Wrong When Issued, Route Outage, Path Preconditions Never Enforced

**CAPA ID**: CAPA-006
**Date Opened**: 2026-09-28
**Source**: Internal audit (world-vanguard gap review, finding #3 "labelling ↔ code threshold mismatch"); further defects found while investigating it and by three independent adversarial reviews of the first correction (code, labelling vs code, traceability), all on 2026-09-28
**Severity**: **CRITICAL**. A wrong MAGNIMS region can change Dissemination in Space (DIS), a McDonald 2024 diagnostic criterion (HAZ-005). The labelling also described a method the device did not run (MDR Annex I §23.4). QP-002 §5.
**Owner**: *(to be assigned: Software Safety Officer / QMS Manager)*
**Status**: OPEN. Corrective actions CA-6.1 to CA-6.8 and CA-6.12, and preventive action PA-6.1, are implemented on branch `docs/labelling-magnims-method-capa006`, pending human review and approval (Class C). CA-6.9 to CA-6.11 and PA-6.2 to PA-6.8 are pending. Effectiveness is not verified.
**Procedure**: QP-002 Corrective and Preventive Action · Problem report: SPR-001 (GitHub Issue to be raised with this CAPA's ID)
**Related**: HAZ-005 · REQ-FUNC-053 (corrected) · REQ-SAFE-021 (new) · REQ-SAFE-020 (not implemented) · RC-032 (new) · RC-010 (amended, PR #42) · RC-024 / CAPA-001 CA-5 (erratum, §3) · PR #23

---

## 1. Summary

| # | Finding | Since | Status |
|---|---------|-------|--------|
| 1 | IFU, AI-Act file, CER and GSPR were **issued stating 3 / 4 / 3 mm** thresholds that the code had not applied for six weeks. The labelling and design documents also misdescribed the classification cascade, and claimed validation and accuracy figures with no evidence. | 2026-04-12 (issue) | Corrected (CA-6.1) |
| 2 | `classify-regions` and `generate-zone-map` returned **HTTP 500 on every call** | 2026-07-18 (`e39cdaa`) | Corrected (CA-6.2) |
| 3 | The **MNI152 MSMask atlas was applied to non-MNI images**, with no registration and no check | 2026-02-28 (`67fa336`) | Corrected (CA-6.3) |
| 4 | Fresh atlas zone map and lesion mask were combined in **different axis orders** | 2026-03-14 (`a637cdf`) | Corrected (CA-6.4) |
| 5 | A **persisted zone map came back transposed** after a GCS reload and was reused for classification | 2026-03-14 (`a637cdf`) | Corrected (CA-6.4) |
| 6 | A **MAGNIMS zone map or a classified lesion mask was read as a FreeSurfer parcellation** | 2026-02-22 (`cf780f4`) | Corrected (CA-6.7) |
| 7 | The **geometric fallback** dropped the brain outline on non-cubic images and ignored image orientation | 2026-02-22 (`cf780f4`) | Corrected (CA-6.6) |
| 8 | The first version of this CAPA's own MNI gate **accepted native 2D FLAIR** | branch only, never deployed | Corrected before merge (CA-6.3) |
| 9 | Open related defects (§10) | various | Pending |

---

## 2. Finding 1: the labelling was wrong when issued

**Timeline** (git history):

| Date | Commit | What |
|---|---|---|
| 2026-02-22 | `cf780f4` | Code applies 3.0 / 4.0 / 3.0 mm, using a Harvard-Oxford zone map |
| 2026-02-28 10:37 | `67fa336` | Code changed to 1.5 mm ("direct contact"); MSMask atlas added |
| 2026-02-28 19:48 | `e0ba3d5` | README states 3 / 4 / 3 mm, nine hours **after** the code change |
| 2026-03-14 | `a637cdf` | Four-path cascade: LST-AI zones → parcellation → MSMask → geometric |
| 2026-04-03 | `e2b4afc` | README corrected to 1.5 mm |
| 2026-04-12 | `18a9bfa` | DDS issued, stating 1.5 mm (parcellation path only) |
| 2026-04-12 | `9ac536d` | **IFU-001, AIA-001, CER-001, GSPR-001 issued stating 3 / 4 / 3 mm** |

The first draft of this CAPA, and the first set of revision rows written in the corrected
documents, said the 3 / 4 / 3 mm values "described an earlier software version" and were "not
updated". That is **false**. These documents were wrong on the day they were issued, and nobody
checked them against the code or against the DDS issued the same day.

**What each document got wrong:**

- **3 / 4 / 3 mm distance thresholds**, called "published" in GSPR-001: IFU, AIA, CER and GSPR.
  MAGNIMS defines the regions by contact; no published 3 / 4 / 3 mm thresholds exist.
- **Misdescribed cascade**: SRS REQ-FUNC-053 ("SynthSeg + EDT (Tier 2) with MSMask fallback
  (Tier 1)"), README ("Tier 2 / Tier 1"), UEF H-09 ("two-tier classification with fallback"), and
  the technical documentation and its PDF ("three-tier"). The DDS described only the parcellation
  path.
- **Claims with no evidence**: "~90 %+ agreement with expert neuroradiologists" and "~70 %" (route
  docstrings); "the only published, validated method" (classifier docstrings); "MAGNIMS
  classification validated against expert annotations" (GSPR 9).
- **Stale descriptions**:
  - SynthSeg presented as an available feature "hosted on Google Vertex AI" (IFU §9.3 and §10.1,
    AIA). It is disabled by default and, when enabled, is a separate service.
  - The MSMask atlas called "the usual path". Native clinical scans fail the MNI gate, so their
    usual path is the geometric fallback.
  - On-screen text promising "brain parcellation (SynthSeg)" and an "Auto (best)" method.

## 3. Finding 2: the region routes were dead for ten weeks

CAPA-001 CA-5 (`e39cdaa`, 2026-07-18) replaced the 1 mm spacing defaults with
`resolve_voxel_spacing(metadata)`. In both region routes this caused an outage:

- **classify-regions**: `metadata` is `SegmentationMetadata`, which never carries voxel spacing
  (`schemas.py`). Every call raised `VoxelSpacingUnavailableError`, which the generic
  `except Exception` turned into HTTP 500.
- **generate-zone-map**: `e39cdaa` also made its spacing fallback reference `metadata` and
  `segmentation_id`, which do not exist in that endpoint, so every call raised `NameError`
  (HTTP 500). pyflakes on `e39cdaa^` reports no undefined names, so this came in with the same
  commit. The first draft of this CAPA said the NameError "predates `e39cdaa`"; that was false.
- **Detection**: a pyflakes undefined-name sweep over `backend/app` found both NameErrors. It also
  found `io` used without import in `GET /segmentation/{id}/nifti?ref_file_id=…` (since `8afc140`,
  2026-04-02). The UI no longer sends `ref_file_id`, so that branch fails closed; it is tracked
  under PA-6.4.

**Erratum to CAPA-001 CA-5 / RC-024.** CA-5 was recorded "DONE — refuses with HTTP 422", and RC-024
as "applied at 4 route sites … VERIFIED". Two of those four sites returned 500 on every call for
ten weeks. The RC-024 source-level test passed only because of a leftover
`resolve_voxel_spacing(parc_meta…)` call that always raised. Both records carry an erratum
(CA-6.12).

**Swept too late.** PR #23 (2026-08-14/15) fixed the same defect for lesion-analysis, DIS and
compare, but no one checked the sibling routes. The longitudinal compare route got an MNI gate and
the axis transpose on 2026-08-22 (`f208149`), and those were not applied to classify-regions either.

## 4. Finding 3: the MNI atlas was applied to non-MNI images

`generate_zone_map_atlas` put the MNI152 MSMask atlas onto the target grid by resampling only.
When the image centre was 30 mm or more from the atlas centre, it re-centred the atlas by a
translation taken from the affine diagonal; otherwise it used the atlas directly. No registration
was performed at any point.

**Measured effect.** Source: `scripts/safety/haz005_atlas_misregistration_probe.py`; output in
`docs/research/records/haz005_atlas_misregistration_output.txt`, run 2, which uses the product's
region rule. Data: 30 MNI-registered MSLesSeg scans with expert lesion masks. The anatomy was moved
by a random amount **up to** the stated level inside the MNI grid, to emulate an unregistered image.

| Misalignment (up to) | Lesions whose region changed | Scans whose brain DIS changed |
|---|---|---|
| 3°, 3 %, 5 mm | 216 / 786 (27.5 %) | 4 / 30 |
| 8°, 7 %, 10 mm | 338 / 786 (43.0 %) | 1 / 30 |
| 15°, 10 %, 20 mm | 433 / 785 (55.2 %) | 3 / 30 |

Run 1 (28.1 / 44.8 / 62.0 %) counted "in no zone" as its own class, where the product assigns DWM.
It is superseded; the DIS figures are the same in both runs. A real unregistered scan usually
differs from MNI by more than the largest level shown.

**Correction (RC-032).** `looks_mni` now requires all of the following:

- isotropic voxels;
- axes aligned with the world axes and not permuted (within about 2.5°);
- a field of view within 25 % of 181 × 217 × 181 mm **on each axis**;
- a grid centre within 10 mm of the MNI template centre, so the silent re-centring can no longer
  apply to a gated image;
- a spatial transform in the header.

The gate is applied in `generate_zone_map_atlas`, and by both routes to the source image as
loaded, header included. An explicit `msmask` request returns 422. In `auto`, the fallback is
used and returns `atlas_unavailable_reason`, which the UI shows as an amber alert.
generate-zone-map returns 422, and **existing zone maps are no longer deleted before validation**
(CA-6.8).

**Limitation.** The gate cannot certify registration: an image resampled onto an MNI grid without
being registered passes.

## 5. Finding 4: fresh atlas zone map in the wrong axis order

The app holds lesion masks in (k, a0, a1) order (RC-031). `classify_lesions_with_atlas` passed the
atlas zone map in NIfTI-native (a0, a1, k) order:

- **Non-cubic grids** (every MNI grid): a shape error. `auto` swallowed it and fell back silently
  to the geometric path, with no reason shown; `msmask` returned 500.
- **Cubic grids**: the zones were applied rotated, without any error.

**Correction.** The zone map is transposed with `(2, 0, 1)`. `classify_from_zone_mask` now refuses
any zone map whose shape differs from the lesion mask, which covers every caller.

## 6. Finding 5: persisted zone maps came back transposed

Since `a637cdf`, generate-zone-map has saved the zone map through `persist()` and then overwritten
the blob with a raw upload that used the MRI header **without the RC-031 orientation marker**. After
a GCS reload the loader applied the legacy transpose `(2, 1, 0)`, so the zone map came back in
(k, a1, a0) order. classify-regions reused persisted zone maps without any shape or order check:

- **MNI grids**: an IndexError, which `auto` swallowed, giving a silent geometric fallback.
- **Square in-plane grids**: silently transposed zones.

Which of the two happened depended on the instance cache. The first draft of this CAPA said the
persisted path was "orientation-consistent"; that was false.

**Correction.**

- The raw overwrite is removed; `persist()` writes the MRI-native array with the marker.
- A persisted zone map is **never reused** for classification. Zones are always generated fresh,
  which takes a few seconds per call.
- Stored zone maps now serve display only. Those already in storage are handled under CA-6.9.

## 7. Finding 6: a zone map was read as a parcellation

classify-regions auto-detected a parcellation as any other segmentation of the same image with
three or more of {2, 3, 4, 7, 8, 10, 16, 41, 42, 43}.

- A MAGNIMS zone map (labels 1–4) passes that test, and so does a lesion mask already
  region-classified in place.
- The classifier then read label 4 (DWM) as the lateral ventricle, so DWM lesions were reported as
  **Periventricular**, and label 3 (IT) as cortex, so IT lesions were reported as **Juxtacortical**.
- Path 2 runs before MSMask, so this was the path actually taken for any study that had a zone map
  or a classified sibling.
- An explicit `parcellation_id` was not checked in either endpoint. In generate-zone-map, the wrong
  zone map was then persisted and propagated to every lesion segmentation.

**Correction.** `looks_like_freesurfer_parcellation` now requires one of the hemispheric or
brainstem labels {16, 41, 42, 43} and excludes zone maps. It is used by auto-detection in both
endpoints. An explicit parcellation that fails the test returns 422.

## 8. Finding 7: the geometric fallback

- **Brain outline dropped.** The route passed the image in native (a0, a1, k) order against the
  (k, a0, a1) mask. On every non-cubic image the brain outline was silently replaced by the whole
  array: juxtacortical then meant "near the array corner", and a lesion 4 mm under the cortex came
  out Deep White Matter. Juxtacortical lesions were therefore under-counted, which can produce a
  **false-negative DIS**.
- **Orientation ignored.** Infratentorial was defined as the lowest 25 % along array axis 0,
  whatever the orientation: wrong on sagittal, coronal and superior-to-inferior acquisitions.
  `canonicalize_orientation()` exists but was never called.

**Correction.** `prepare_geometric_image` hands the image over in (k, a0, a1) order. It refuses
the image if it cannot be read, its orientation cannot be determined, its slice axis does not run
inferior to superior, it is not 3-D, its grid does not match the mask, or it is blank. The
classifier itself now refuses a mismatched image instead of silently dropping it.

When no path applies, the route returns 422 with the reasons. The UI shows an amber "least
accurate" warning whenever regions come from this path.

## 9. Finding 8: the first gate of this CAPA was too weak

The first `looks_mni` compared **sorted** extents and did not check isotropy, axis permutation,
position or the header. It accepted native axial 2D FLAIR, for example 240 × 240 × 48 at
0.94 × 0.94 × 3 mm, and permuted MNI grids; the downstream atlas code reads the affine diagonal and
then failed on the permuted grids. The code review found this before merge, and the version was
never deployed. It is recorded here because the corrective action itself needed correcting.

## 10. Open related defects (not corrected in this change)

- **CA-6.9: stored results.**
  - Every region classification stored before 2026-07-18 was computed with 1 mm isotropic spacing,
    because `SegmentationMetadata` never carries spacing and the route defaulted to 1 mm.
  - Those results were also subject to Findings 3–7.
  - They remain in `analysis_data`, are still displayed, and are forwarded to the MCP assistant.
  - Zone maps already stored may be transposed (Finding 5) or built off-MNI (Finding 3).
  - Remedy: mark them stale or regenerate them. This needs a decision on production data access,
    which is the owner's.
- **CA-6.10: in-place rewrite destroys annotations.** classify-regions rewrites the lesion mask in
  place:
  - components below the 3 mm³ floor are erased;
  - Gd+ (5) and T1 black-hole (6) labels are merged into region labels 1–4.
  Preserving 5 and 6 as they are would take those lesions out of DIS, because region and activity
  share one label value. This is a design decision: activity must be stored separately from region.
- **CA-6.11: LST-AI path.** It copies zones voxel by voxel with no contact rule or priority, so one
  lesion can receive several regions. Its result lacks `lesions` and `classification_summary`, and
  the UI would fail on it. The path is disabled by default.
- **PA-6.4.** The `io` NameError in `segmentation.py` (§3).
- **PA-6.5.** nilearn does the atlas resampling for a Class C function. It is recorded as class B and
  is unpinned (`>=0.10.0`); the atlas data file has no provenance entry.
- **PA-6.6.** RC-030 is in the manifest but not in RMF §5.1. RC-031, the axis-order contract, is in
  neither.
- **PA-6.8.** Found during the labelling correction but outside MAGNIMS:
  - GSPR 8, the technical documentation (architecture diagram and deployment table) and the
    PDF deployment table still say the software "interacts with Vertex AI";
    `ai_segmentation_service.py` says those endpoints were never deployed;
  - the IFU §10.3 evidence table has no row for the LST-AI path.

## 11. Exposure

- **2026-02-22 to 2026-07-18** (routes alive): Findings 3–7 could each produce wrong regions, all
  on assumed 1 mm spacing:
  - zone map read as a parcellation (DWM → PV, IT → JC);
  - atlas applied off-MNI;
  - rotated or transposed zones;
  - geometric regions with no brain outline (JC under-counted, IT orientation-naive).
- **2026-07-18 to now**: both routes returned 500, so no regions were produced.
- Stored results from the first period are still displayed (CA-6.9).
- Whether any real study was affected is **not determined**: production data was not accessed,
  by the owner's decision.

## 12. Root Cause Analysis (QP-002 §4.3 — 5 Whys)

**Problem statement:** the device assigned MAGNIMS regions by methods whose preconditions were
never checked. Its labelling described a different method, and the routes were broken for ten weeks
without detection.

1. **Why did the labelling state 3 / 4 / 3 mm?** It was written from an early design, or copied
   from the README of the time, and issued without being compared with the code or with the DDS
   issued the same day.
2. **Why was no comparison made?** The development process has no step that verifies labelling
   against design outputs, and the numbers in the labelling were not bound to anything executable.
3. **Why did defects in the paths persist?** Each path's precondition existed only as an
   assumption in a docstring or in the developer's head: "patient MRI in MNI space", "a sibling
   with FreeSurfer-range labels is a parcellation", "the image and mask are in the same order",
   "axis 0 runs inferior to superior".
4. **Why did the outage and the NameErrors go unnoticed?**
   - Tests exercised services, not routes through the application.
   - CAPA-001 CA-5 was accepted on source-level and mock-metadata tests, the same lesson as PR #23.
   - Fixes were applied route by route, with no sweep of sibling routes.
   - No static undefined-name check runs in CI.
5. **Why could a transposed zone map be reused?** A second persistence path, the raw overwrite,
   bypassed the canonical save and its orientation marker, and no function boundary checked the
   axis order.

**Root causes.**
- **(a)** Labelling is not verified against design outputs.
- **(b)** Path preconditions were assumptions, not enforced checks.
- **(c)** CAPA and risk-control verification accepted evidence that could not observe the failure:
  source-text and mock tests, and no app-level route test.
- **(d)** No axis-order contract at function and persistence boundaries.

## 13. Action Plan (QP-002 §4.4)

Owner for every action: *(to be assigned — Software Safety Officer)*. Implementation due 2026-10-05.
Verification due 2026-11-04 (30 days after implementation, per QP-002 §4.6).

| ID | Type | Action | Acceptance criteria | Status |
|----|------|--------|--------------------|--------|
| **CA-6.1** | Corrective | Correct the labelling and design documents (Finding 1), with revision rows stating what was wrong and when | Every document states the contact criterion, 1.5 mm, the four paths with their preconditions, the MNI gate and the geometric refusal; no withdrawn claim remains; PA-6.1 passes | **DONE** (branch) |
| **CA-6.2** | Corrective | Spacing from the source image in both routes; no undefined names | App-level route tests return 200 / 422, never 500 | **DONE**: RC-032 |
| **CA-6.3** | Corrective | Strict MNI gate in the service and both routes | Gate accepts FSL 1 mm / 2 mm and ICBM 2009c; rejects oblique, anisotropic, permuted, off-centre and no-transform grids | **DONE**: RC-032 |
| **CA-6.4** | Corrective | Fresh zone map in lesion order; shape check in `classify_from_zone_mask`; no reuse of persisted zone maps; no raw overwrite | Per-lesion equality with the orientation-consistent reference (MNI and cubic); a stale persisted zone map has no effect; no raw upload | **DONE**: RC-032 |
| **CA-6.5** | Corrective | UI: why the atlas was not used; a warning on geometric regions; corrected panel texts | Frontend source-level tests (not a render test) | **DONE**: RC-032 |
| **CA-6.6** | Corrective | Geometric preconditions (image order, orientation, blank, mismatch) | Route and unit tests: JC assigned under the cortex; sagittal and reversed slices refused | **DONE**: RC-032 |
| **CA-6.7** | Corrective | Parcellation identity check, auto and explicit, in both endpoints | A zone map is not used as a parcellation (auto) and is refused as an explicit one | **DONE**: RC-032 |
| **CA-6.8** | Corrective | generate-zone-map validates before deleting existing zone maps | A refusal leaves existing zone maps in place | **DONE**: RC-032 |
| **CA-6.9** | Corrective | Stored pre-fix classifications and zone maps: mark stale or regenerate (§10) | None displayed or forwarded to MCP without a "stale" flag | **PENDING** (owner decision on data access) |
| **CA-6.10** | Corrective | Stop the in-place rewrite from destroying labels 5 / 6 and sub-floor components (§10) | Design decision recorded; a test proves no annotation is lost | **PENDING** (design decision) |
| **CA-6.11** | Corrective | LST-AI path: contact rule and priority, and a complete result (§10) | Parity with the other paths, or the path removed | **PENDING** (path disabled) |
| **CA-6.12** | Corrective | Erratum to CAPA-001 CA-5 and RC-024 (§3) | Erratum recorded; history preserved | **DONE** (records) |
| **PA-6.1** | Preventive | Bind the labelling to the code: IFU distances equal the code constants; withdrawn values, "two-tier", "validated" and "~90 / ~70 %" claims are allowed only beside a CAPA-006 note in 15 documents and code files; a missing document fails | `test_capa006_labelling_bound_to_code.py` in CI; negative controls executed | **DONE** (branch) |
| **PA-6.2** | Preventive | Every route producing a clinical quantity has a test through the real application | CI enumerates the clinical routes and fails when one lacks an app-level test | **PENDING** |
| **PA-6.3** | Preventive | Every precondition in a Class C docstring is enforced by tested code, or removed | Review checklist updated; Class C modules swept | **PARTIAL**: MAGNIMS paths done; sweep pending |
| **PA-6.4** | Preventive | pyflakes F821 (undefined names) in CI; fix `segmentation.py` `io` first | CI fails on any undefined name | **PENDING** |
| **PA-6.5** | Preventive | nilearn reviewed as Class C SOUP and pinned; provenance entry for the atlas file | SOUP BOM updated; version pinned | **PARTIAL**: SOUP entries updated; pin pending |
| **PA-6.6** | Preventive | Register RC-030 and RC-031 in RMF §5.1 and the manifest | Both bound to tests with negative controls | **PENDING** |
| **PA-6.7** | Preventive | No mask is persisted through any path other than the canonical save (RC-031) | Sweep of raw blob uploads; test | **PARTIAL**: zone maps done |
| **PA-6.8** | Preventive | Sweep all labelling for other claims not supported by the code (starting with the Vertex AI hosting statements, §10), using the PA-6.1 mechanism | Each claim traced to code or withdrawn; the gate is extended | **PENDING** |

## 14. Verification Evidence (executed 2026-09-28)

**Tests:**
- `backend/tests/unit/test_rc032_region_atlas_guard.py`: 23 `test_rc032_*` tests, through the real
  FastAPI app with fake services.
- `frontend/src/components/LesionDashboard.rc032.test.ts`: 4 `rc032` tests, source-level.
- `backend/tests/unit/test_capa006_labelling_bound_to_code.py`: 48 tests.
- `test_rc024_voxel_spacing.py`: its route check now requires the source-image resolution.

**Negative controls.** Every sub-control was mutated one at a time against the final code, with
the application of each mutation asserted and the failing test names recorded, in
`docs/iec62304/records/risk_verification/RC-032_negative_controls_2026-09-28.json`.

- **Backend:** 22 mutations, 19 detected. The two route MNI gates are covered by the service gate
  by design, so each alone fails 0 tests; mutated together they are detected. The diagonal-dominance
  condition of `looks_mni` is redundant with its per-axis field-of-view condition (a permuted affine
  has a zero diagonal), so it is not independently tested and is not claimed to be.
- **Frontend:** 3 of 3 mutations detected.
- **Labelling (PA-6.1):** 4 of 4 mutations detected.
- **Restored:** 23, 4 and 48 passed.

**Full suites:** see the PR record.

**Effectiveness check (pending, after deployment; needs authenticated access by the owner):**
- a native clinical study → geometric regions with the amber warning, or 422 with reasons;
- an MNI-registered study → MSMask;
- zone-map generation on a native study → 422, with the existing zone map kept;
- CA-6.9 completed.

## 15. Regulatory Assessment (QP-002 §7)

- The device is **not CE-marked, not FDA-cleared and not in clinical use**. There is no marketed
  product, so there is no vigilance or field-safety reporting obligation (MDR Art. 87) at this
  time. If any clinical or investigational use occurred before 2026-07-18, the owner must assess it.
- No Declaration of Conformity may be signed while this CAPA is open. The RMF banner is updated to
  include CAPA-006.
- The labelling defect (Finding 1) would have been a GSPR 23.4 non-conformity on a marketed device.

## 16. Links

- QP-002 · SPR-001 (`docs/iec62304/08_Problem_Resolution_Procedure.md`)
- `docs/iec62304/03_Risk_Management_File.md` (HAZ-005, RC-032, RC-024 erratum)
- `docs/iec62304/02_Software_Requirements_Specification.md` (REQ-FUNC-053, REQ-SAFE-020, REQ-SAFE-021)
- `docs/iec62304/records/risk_verification/rc_test_manifest.json` (RC-032)
- `docs/iec62304/records/capa/CAPA-001_Risk_Control_Verification_Integrity.md` (CA-5 erratum)

## 17. Revision of this record

The first draft (2026-09-28) contained four false statements, which the independent traceability
review found and which are corrected above:

- "described an earlier software version" (see §2);
- "the NameError predates `e39cdaa`" (see §3);
- "the persisted-zone-map path was orientation-consistent" (see §6);
- a quotation, "assumed MNI-registered", that does not exist in the code. The docstring said
  "patient MRI in MNI space", and the code re-centred the atlas (§4).

The first draft also omitted Findings 5–8.

---

**Prepared by**: internal audit, 2026-09-28. Facts in §2–§11 were checked against the git history
and the source, and by execution. Three independent adversarial reviews preceded this revision.
**Requires**: review, confirmation of the root cause, and sign-off by the Software Safety Officer.
Human approval is required before merge (Class C modules changed: `ms_region_classifier.py`).
