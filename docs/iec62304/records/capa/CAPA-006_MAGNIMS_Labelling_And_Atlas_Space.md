# CAPA-006 — MAGNIMS Region Classification: Labelling Wrong When Issued, Route Outage, Path Preconditions Never Enforced

**CAPA ID**: CAPA-006
**Date Opened**: 2026-09-28
**Source**: Internal audit (world-vanguard gap review, finding #3 "labelling ↔ code threshold mismatch"). Further defects were found while investigating it and by five independent adversarial reviews of the correction: round 1 covered code, labelling vs code and traceability; round 2 covered the code delta and record consistency. All took place on 2026-09-28.
**Severity**: **CRITICAL**. A wrong MAGNIMS region can change Dissemination in Space (DIS), a McDonald 2024 diagnostic criterion (HAZ-005). The labelling described a method the device did not run (MDR Annex I §23.4). QP-002 §5.
**Owner**: *(to be assigned: Software Safety Officer / QMS Manager)*
**Status**: OPEN.
- Implemented in PR #43, **approved by N. G. Bonilla Vargas on 2026-10-17** (human Class C approval) and merged: CA-6.1 to CA-6.8, CA-6.12 and PA-6.1.
- Partial: PA-6.3, PA-6.5 and PA-6.7.
- Pending: CA-6.9 to CA-6.11, PA-6.2, PA-6.4, PA-6.6 and PA-6.8.
- Effectiveness is not verified.

**Procedure**: QP-002 Corrective and Preventive Action (`docs/qms/QP-002_CAPA_Procedure.md`) · Problem report: SPR-001 (a GitHub Issue is to be raised with this CAPA's ID)
**Related**: HAZ-005 · HAZ-010 · REQ-FUNC-053 (corrected) · REQ-SAFE-021 (new) · REQ-SAFE-020 (not implemented) · RC-032 (new) · RC-010 (amended, PR #42) · RC-024 / CAPA-001 CA-5 (erratum, §3) · RC-029 (erratum, Finding 10) · PR #23 · CAPA-007 (analysis-route authorization; separate PR)

---

## 1. Summary

| # | Finding | Since | Status |
|---|---------|-------|--------|
| 1 | IFU, AIA and GSPR were **issued stating 3 / 4 / 3 mm** thresholds; CER stated 3 / 4 mm. The code had not applied these for six weeks. Labelling and design documents also misdescribed the cascade and claimed validation and accuracy with no evidence. | 2026-04-12 (issue) | Corrected (CA-6.1) |
| 2 | `classify-regions` and `generate-zone-map` returned **HTTP 500 on every call** | 2026-07-18 (`e39cdaa`) | Corrected (CA-6.2) |
| 3 | The **MNI152 MSMask atlas was applied to non-MNI images**, with no registration and no check | 2026-02-28 (`67fa336`) | Corrected (CA-6.3) |
| 4 | The fresh atlas zone map and the lesion mask were combined in **different axis orders** | 2026-03-14 (`a637cdf`) | Corrected (CA-6.4) |
| 5 | A **persisted zone map came back transposed** after a GCS reload and was reused | 2026-03-14 (`a637cdf`) | Corrected (CA-6.4) |
| 6 | A **zone map, a classified lesion mask or another image's segmentation was read as a FreeSurfer parcellation** | 2026-02-22 (`cf780f4`) | Corrected (CA-6.7) |
| 7 | The **geometric fallback** ignored image orientation and dropped the brain outline | 2026-02-22 (IT rule) / 2026-03-14 (outline) | Corrected (CA-6.6) |
| 8 | The first version of this CAPA's own MNI gate **accepted native 2D FLAIR** | branch only | Corrected before merge (CA-6.3) |
| 9 | The **same weak gate was live in the longitudinal compare route** | 2026-08-22 (`f208149`) | Corrected (CA-6.3) |
| 10 | The two region routes had **no object-level authorization** (RC-029 was wired only in `segmentation.py`) | 2026-07-10 (`5ebe5f6`) | Corrected for these 2 routes; 8 analysis routes → CAPA-007 |
| 11 | **Faults were reported as refusals, or degraded silently**; the zone-map replacement was not atomic | various | Corrected (CA-6.8, RC-032) |
| — | Open related defects (§12) | various | Pending |

---

## 2. Finding 1: the labelling was wrong when issued

**Timeline** (git history):

| Date | Commit | What |
|---|---|---|
| 2026-02-22 | `cf780f4` | Code applies 3.0 / 4.0 / 3.0 mm with a Harvard-Oxford zone map |
| 2026-02-28 10:37 | `67fa336` | Code changed to 1.5 mm ("direct contact"); MSMask atlas added |
| 2026-02-28 19:48 | `e0ba3d5` | README states 3 / 4 / 3 mm, nine hours **after** the code change |
| 2026-03-14 | `a637cdf` | Four-path cascade: LST-AI zones → parcellation → MSMask → geometric |
| 2026-04-03 | `e2b4afc` | README corrected to 1.5 mm |
| 2026-04-12 | `18a9bfa` | DDS issued stating 1.5 mm (parcellation path only) |
| 2026-04-12 | `9ac536d` | **IFU-001, AIA-001 and GSPR-001 issued stating 3 / 4 / 3 mm; CER-001 stating 3 / 4 mm (PV / JC)** |

**What was wrong:**

- **3 / 4 / 3 mm distance thresholds**, which GSPR-001 called "published". MAGNIMS defines the regions by contact.
- **A misdescribed cascade**: SRS REQ-FUNC-053 and the README ("Tier 2 / Tier 1"), UEF H-09 ("two-tier classification with fallback"), and the technical documentation and its PDF ("Tier 2" / "Tier 1" sections). The DDS described only the parcellation path.
- **Claims with no evidence**: "~90 %+ agreement with expert neuroradiologists" and "~70 %" (route and classifier docstrings); "the only published, validated method" and "exact methodology" (classifier docstrings); "MAGNIMS classification validated against expert annotations" (GSPR 9).
- **Stale descriptions**:
  - SynthSeg presented as available and "hosted on Google Vertex AI" (IFU §10.1 and AIA). It is disabled by default and, when enabled, runs as a separate service.
  - On-screen text promising "brain parcellation (SynthSeg)" and an "Auto (best)" method.

## 3. Finding 2: the region routes were dead for ten weeks

CAPA-001 CA-5 (`e39cdaa`, 2026-07-18) replaced the 1 mm spacing defaults with
`resolve_voxel_spacing(metadata)`. `SegmentationMetadata` never carries voxel spacing, so
**every one of the four route sites that `e39cdaa` introduced returned HTTP 500**:

| Route | Outage window |
|---|---|
| lesion-analysis, dis-assessment | 2026-07-18 until PR #23 (`8006e7b` 2026-08-14, merged `96f3b51` 2026-08-15) |
| classify-regions | 2026-07-18 until this CAPA |
| generate-zone-map | 2026-07-18 until this CAPA. The route also referenced the undefined names `metadata` and `segmentation_id`, introduced by the same commit; pyflakes on `e39cdaa^` finds no undefined names. |

**Why the RC-024 source check stayed green.** It passed on text alone. The region routes contained
`resolve_voxel_spacing(` calls that always raised, and the analysis file contained the string only
in a docstring. It now counts real calls in the AST.

**Remaining 1 mm assumption.** The compare and SEL routes still fall back to `(1.0, 1.0, 1.0)`
spacing, contradicting RC-024. This is CAPA-007 scope.

**Erratum.** CAPA-001 §8, the RMF RC-024 row and the manifest RC-024 entry carry an erratum (CA-6.12).

**Detection.** A pyflakes undefined-name sweep found the zone-map NameError. It also found `io` used
without import in `GET /segmentation/{id}/nifti?ref_file_id=…` (since `8afc140`, 2026-04-02). The
UI no longer sends `ref_file_id`, so that branch fails closed; it is tracked under PA-6.4.

**Not swept.** PR #23 fixed the sibling routes only. The longitudinal compare route had its own
MNI gate and transpose (`f208149`), and neither was applied to classify-regions (see Finding 9).

## 4. Finding 3: the MNI atlas was applied to non-MNI images

`generate_zone_map_atlas` placed the MNI152 MSMask atlas on the target grid by resampling only.
When the image centre was 30 mm or more from the atlas centre, it re-centred the atlas by a
translation taken from the affine diagonal. No registration was ever performed.

**Measured effect.** Probe: `scripts/safety/haz005_atlas_misregistration_probe.py`. Output:
`docs/research/records/haz005_atlas_misregistration_output.txt`, run 2, which uses the product's
region rule. Data: 30 MNI-registered MSLesSeg scans with expert lesions. The anatomy was moved by a
random amount **up to** the stated level.

| Misalignment (up to) | Lesions whose region changed | Scans whose brain DIS changed |
|---|---|---|
| 3°, 3 %, 5 mm | 216 / 786 (27.5 %) | 4 / 30 |
| 8°, 7 %, 10 mm | 338 / 786 (43.0 %) | 1 / 30 |
| 15°, 10 %, 20 mm | 433 / 785 (55.2 %) | 3 / 30 |

Run 1 (28.1 / 44.8 / 62.0 %) counted "in no zone" as its own class. It is superseded; the DIS
figures are the same.

**Correction (RC-032).** `looks_mni` now requires all of the following:

- isotropic voxels;
- axes aligned and not permuted (within about 2.5°);
- field of view within 25 % of 181 × 217 × 181 mm **on each axis**;
- grid centre within 10 mm of the MNI template centre (0, −18, 18);
- a spatial transform in the header.

The gate is applied in `generate_zone_map_atlas` and by both routes to the source image as loaded.

**Limitations (stated in the IFU and DDS).** The gate checks the grid, not registration:

- An image resampled onto an MNI grid without registration passes.
- A well-behaved native 3D isotropic axial scan with an MNI-like field of view and centre can pass.
- SPM12 "Normalise: Write" outputs with the default bounding box are **refused**, a fail-safe
  outcome: their centre is about 10.5 mm from the reference.

A content-based registration check is CA-6.13.

## 5. Finding 4: the fresh atlas zone map was in the wrong axis order

`classify_lesions_with_atlas` passed the atlas zone map in NIfTI-native (a0, a1, k) order next to
the (k, a0, a1) lesion mask (RC-031).

- On non-cubic grids this raised a shape error. `auto` swallowed it and fell back to geometric
  with no reason given; `msmask` returned 500.
- On cubic grids the zones were rotated, silently.

**Correction.** Transpose `(2, 0, 1)`. `classify_from_zone_mask` now refuses any zone map whose
shape differs from the lesion mask.

## 6. Finding 5: persisted zone maps came back transposed

Since `a637cdf`, generate-zone-map saved through `persist()` and then overwrote the blob with a raw
upload that carried the MRI header but **no RC-031 orientation marker**. Since RC-031 v2
(`fcf09ce`, 2026-08-07) the marker distinguishes MRI-native files from legacy ones, and a marker-less
file is always read with the legacy transpose `(2, 1, 0)`. The zone map therefore came back as
(k, a1, a0), and classify-regions reused it with no check. The instance cache decided **whether**
a reload happened; the grid decided **what** went wrong:

- on MNI grids, an IndexError, which `auto` swallowed, giving a silent geometric fallback;
- on square in-plane grids, zones transposed with no error.

**Correction.**
- The raw overwrite is removed.
- Persisted zone maps are **never reused** for classification; the zone map is always generated
  fresh.
- Stored zone maps serve display only (CA-6.9).

## 7. Finding 6: other segmentations read as a parcellation

The auto-detection accepted any sibling with three or more of {2, 3, 4, 7, 8, 10, 16, 41, 42, 43}.

- **A MAGNIMS zone map (labels 1–4) passed.** Its label 4 (DWM) was read as the lateral ventricle,
  so DWM lesions came out **Periventricular**. Its label 3 (IT) was read as cortex, so IT lesions
  came out **Juxtacortical**.
- **An explicit `parcellation_id` was not checked** in either endpoint.
- **Holes in the first fix** (review round 2):
  - a parcellation of **another image**, such as another timepoint on the same protocol grid;
  - an **instance-labelled lesion mask** with labels 1..20;
  - a parcellation **without cortex labels**, where JC can never be assigned.

**Correction.** `looks_like_freesurfer_parcellation` requires:

- **all** of {2, 3, 4, 16, 41, 42, 43};
- not a zone map;
- a labelled volume of at least 500 mL;
- for an explicit parcellation, the **same image** (`file_id`) and grid, otherwise 422.

It is used by both endpoints.

## 8. Finding 7: the geometric fallback

- **Orientation.** Infratentorial was defined as "the lowest 25 % along array axis 0", whatever the
  orientation. This dates from `cf780f4`.
- **Brain outline.** Since `a637cdf` the image was passed in native (a0, a1, k) order against the
  (k, a0, a1) mask.
  - On non-cubic grids the outline was replaced by the whole array. Juxtacortical then meant "near
    the array corner", juxtacortical lesions were under-counted, and DIS could come out falsely
    negative.
  - On cubic grids a permuted outline was used.

**Correction.** `prepare_geometric_image` hands the image over in (k, a0, a1) order. It refuses an
image that:

- cannot be read;
- has an indeterminate orientation;
- has a slice axis that does not run inferior to superior, or is tilted more than 30°;
- is not 3-D (a trailing singleton dimension is accepted);
- is on a different grid;
- is blank.

The classifier also refuses a mismatched image.

## 9. Finding 8 and Finding 9: a gate that was too weak — here and in production

The first `looks_mni` of this CAPA compared **sorted** extents and had no isotropy, permutation,
centre or header condition. It accepted native axial 2D FLAIR, for example 240 × 240 × 48 at
0.94 × 0.94 × 3 mm. The code review found it before merge.

It was **not** only a draft. It was a copy of the `_looks_mni` that `f208149` (2026-08-22) had put
in the **longitudinal compare route**, where it has been live in production ever since, deciding
whether region stratification of new lesions used the atlas.

**Correction.** The compare route now imports the classifier's strict gate, which is pinned by
`test_rc032_longitudinal_route_uses_the_same_gate`. Exposure is in §13.

## 10. Finding 10: no object-level authorization on the region routes

The region routes were split out of `segmentation.py` in the C3 decomposition (`5ebe5f6`,
2026-07-10). CAPA-002 RC-029 was verified on 2026-07-19 **only on the routes that remained in
`segmentation.py`**: the RC-029 wiring test reads that one file. classify-regions, which rewrites
and persists a segmentation, and generate-zone-map, which deletes and creates zone maps for any
`file_id`, checked authentication only. They were dead (500) from 2026-07-18, and this CAPA revives
them.

**Correction.** classify-regions depends on `require_segmentation_access`. generate-zone-map calls
`authorize_file_scope` before anything else. Cross-patient denial tests return 404.

The **8 analysis routes** in `segmentation_analysis.py` have the same gap and are live:

- lesion-analysis, dis-assessment
- compare, agreement-map
- longitudinal/compare, longitudinal/sel
- lesion-annotations (a write)
- export/dicom-seg

These are opened as **CAPA-007** (HAZ-010) with a separate PR, together with the RC-024 1 mm
fallback in compare and SEL.

## 11. Finding 11: faults reported as refusals; a non-atomic replacement

- **Atlas fault.** In `auto`, an atlas fault (missing file, missing nilearn, any exception)
  degraded silently to geometric, the Finding-4 pattern. It is now returned as `atlas_error` and
  shown by a separate amber alert.
- **Geometric fault.** A geometric fault was reported as the image's fault (422) or as "no lesion
  voxels" (400). It is now 500. 422 means every applicable path **refused** the image, and 400
  means an unknown method.
- **Zone-map replacement.** generate-zone-map deleted the old zone maps before validating, and
  later before persisting. A refusal or a persist failure now leaves them in place: create, then
  persist, then delete.
- **Zone volumes.** Zone statistics assumed 1 mm³ voxels; they now use the image voxel volume.

## 12. Open related defects (not corrected in this change)

- **CA-6.9: stored results.** Every region classification stored before 2026-07-18 was computed with
  1 mm spacing and the pre-RC-032 paths. These results remain in `analysis_data`, are displayed,
  and are forwarded to the MCP assistant. Stored zone maps may also be transposed or built off-MNI.
  Remedy: mark them stale or regenerate them. This needs the owner's decision on data access.
- **CA-6.10: in-place rewrite.** classify-regions erases components below 3 mm³ and merges
  Gd+ (5) and black-hole (6) labels into region labels 1–4, because region and activity share one
  label value. This is a design decision.
- **CA-6.11: LST-AI path.** The path is voxel-wise with no contact rule or priority, and its result
  is incomplete (no `lesions` or `classification_summary`). It is disabled by default.
- **CA-6.13: registration check.** A content-based registration check for the atlas path, for
  example Dice between the image's brain mask and the resampled MSMask brain with a threshold
  calibrated on the probe, as defence in depth behind the grid gate (§4 limitations).
- **PA-6.4.** The `io` NameError in `segmentation.py` (§3) and an undefined-name check in CI.
- **PA-6.5.** nilearn is now recorded as Class C in the SOUP BOM (SOUP-BE-020), and the atlas file
  has a provenance entry (SOUP-BE-025). Still to do: the version pin (`>=0.10.0` today), the stale
  requirements comment, and confirmation of the atlas licence.
- **PA-6.6.** RC-030 is in the manifest but not in RMF §5.1. RC-031 is in neither.
- **PA-6.8.** Other unsupported labelling claims, starting with Vertex AI hosting:
  - SRS REQ-FUNC-030 and REQ-IF-003;
  - DDS §2 and SAD component tables;
  - Master compliance document;
  - RMF hazard rows (66, 187);
  - README architecture and deployment tables;
  - SOUP-BE-012;
  - GSPR 8;
  - technical documentation and PDF deployment tables;
  - IFU line 65, "designed and validated exclusively for brain MRI".
- **Referral, not investigated here.** Review round 2 reported that
  `dicomweb_service._build_affine` may write DICOM LPS coordinates without converting them to RAS,
  and may swap the in-plane axes. The gates in this CAPA consume that affine for DICOMweb imports.
  This needs its own investigation and CAPA.
- **Minor.** Storage failures during spacing resolution map to 422, not a retryable 5xx. A missing
  atlas or missing nilearn maps to 400 when `msmask` is requested explicitly.

## 13. Exposure

- **2026-02-22 to 2026-07-18** (routes alive; every classification assumed 1 mm spacing), wrong
  regions could come from:
  - a zone map or a classified sibling read as a parcellation (DWM → PV, IT → JC);
  - the atlas applied off-MNI;
  - rotated or transposed zones;
  - geometric regions with no brain outline (JC under-counted) and an orientation-naive IT rule.
- **2026-07-18 to now**: classify-regions and generate-zone-map returned 500, so they produced no
  regions.
- **2026-08-22 to now**, longitudinal compare: images that passed the weak gate had their new
  lesions stratified by atlas region. This includes anisotropic 2D FLAIR with an MNI-like field of
  view.
- Stored results are still displayed (CA-6.9).
- Whether any real study was affected is **not determined**: production data was not accessed, by
  the owner's decision. The device is not in clinical use.

## 14. Root Cause Analysis (QP-002 §4.3)

**Problem statement:** the device assigned MAGNIMS regions by methods whose preconditions were never
checked. Its labelling described a different method, and the routes were broken, and exposed to any
authenticated user, without detection.

**Method.** A fishbone (Ishikawa) analysis is used because the causes are parallel, not a single
chain. Five Whys was applied within each branch. A fault-tree analysis was not performed.
Justification: the top event is not a single failure path but four independent process gaps.

| Branch | Cause | Why it persisted |
|---|---|---|
| **Method** | Labelling authored and issued without verification against design outputs (IFU vs code/DDS, same day) | No design-output → labelling verification step; numbers not bound to anything executable |
| **Materials / inputs** | Path preconditions were assumptions: "MNI space", "a sibling with FreeSurfer labels is a parcellation", "the image is in the mask's order", "axis 0 is inferior → superior" | Stated in docstrings or not at all; never enforced |
| **Measurement / verification** | Controls accepted on evidence that could not observe the failure: source-text checks, mock metadata, service-level tests, a wiring test that read one file | No app-level route tests; RC-029 and RC-024 verification did not enumerate the routes actually mounted |
| **Machine / tooling** | No static undefined-name check; a second persistence path bypassed the canonical save | No pyflakes in CI; raw blob uploads allowed |
| **Change process** | Fixes applied route by route (PR #23, `f208149`); a refactor (C3) moved routes out of a verified file | No sweep of sibling routes after a defect class is found; no re-verification after a refactor |

**Root causes.**
- **(a)** Labelling is not verified against design outputs.
- **(b)** Path preconditions were not enforced.
- **(c)** Verification evidence could not observe the failure.
- **(d)** No axis-order or persistence contract at boundaries.
- **(e)** Refactors and fixes were not swept.

## 15. Action Plan (QP-002 §4.4)

Owner: *(to be assigned — Software Safety Officer)*. Implementation due 2026-10-05. Verification due 2026-11-04 (30 days, QP-002 §4.6).

| ID | Type | Action | Acceptance criteria | Status |
|----|------|--------|--------------------|--------|
| **CA-6.1** | Corrective | Correct the labelling and design documents (Finding 1), with revision rows stating what was wrong and when | Every document states the contact criterion, 1.5 mm, the four paths with their preconditions, the MNI gate and its limits, and the geometric refusal; no withdrawn claim remains; PA-6.1 passes | **DONE** (PR #43) |
| **CA-6.2** | Corrective | Spacing from the source image in both region routes; no undefined names | App-level route tests: 200 / 422, never 500 | **DONE**: RC-032 |
| **CA-6.3** | Corrective | Strict MNI gate in the service, both routes and the longitudinal compare route | Accepts FSL 1 / 2 mm and ICBM 2009c; rejects oblique, anisotropic, permuted, off-centre, non-MNI-FOV and no-transform grids | **DONE**: RC-032 |
| **CA-6.4** | Corrective | Fresh zone map in lesion order; shape check; no persisted reuse; no raw overwrite | Per-lesion equality with the orientation-consistent reference; a stale persisted zone map has no effect; no raw upload | **DONE**: RC-032 |
| **CA-6.5** | Corrective | UI: why the atlas was not used, atlas-fault alert, geometric warning, corrected panel texts | Frontend source-level tests (not render tests) | **DONE**: RC-032 |
| **CA-6.6** | Corrective | Geometric preconditions | JC assigned under the cortex; sagittal, reversed and > 30° tilted slices refused | **DONE**: RC-032 |
| **CA-6.7** | Corrective | Parcellation identity: same image and grid, full landmark set, brain-sized | Zone map, instance mask and foreign-image parcellation refused or not used; genuine parcellation used | **DONE**: RC-032 |
| **CA-6.8** | Corrective | Fault vs refusal; atomic zone-map replacement; authorization on both region routes; zone volumes | Tests: atlas fault reported, geometric fault 500, persist failure keeps old zone maps, cross-patient 404 | **DONE**: RC-032 / RC-029 |
| **CA-6.9** | Corrective | Stored pre-fix classifications and zone maps: mark stale or regenerate | None displayed or forwarded to MCP without a stale flag | **PENDING** (owner decision on data access) |
| **CA-6.10** | Corrective | Stop the in-place rewrite from destroying labels 5 / 6 and sub-floor components | Design decision recorded; test that no annotation is lost | **PENDING** (design decision) |
| **CA-6.11** | Corrective | LST-AI path parity or removal | Contact rule, priority, complete result | **PENDING** (path disabled) |
| **CA-6.12** | Corrective | Errata to CAPA-001 CA-5, RC-024 (all four sites) and RC-029 | Errata recorded; history preserved | **DONE** (records) |
| **CA-6.13** | Corrective | Content-based registration check behind the grid gate | Threshold calibrated on the probe data; refuses the perturbed images | **PENDING** |
| **PA-6.1** | Preventive | Bind the labelling to the code (19 documents, code files and UI locales): IFU distances equal the code constants; withdrawn values, "two-tier", validation, "exact methodology" and MAGNIMS accuracy-% claims allowed only beside a CAPA-006 withdrawal note; a missing document fails | `test_capa006_labelling_bound_to_code.py` in CI; negative controls executed | **DONE** (PR #43) |
| **PA-6.2** | Preventive | Every route producing or changing clinical data has an app-level test **and** an authorization check, found by enumerating the mounted routes | CI enumerates the routes and fails on a gap | **PENDING** (CAPA-007 implements the authorization half) |
| **PA-6.3** | Preventive | Every precondition in a Class C docstring is enforced by tested code or removed | Review checklist; Class C sweep | **PARTIAL**: MAGNIMS paths |
| **PA-6.4** | Preventive | pyflakes F821 in CI; fix `segmentation.py` `io` | CI fails on any undefined name | **PENDING** |
| **PA-6.5** | Preventive | nilearn as Class C SOUP and pinned; atlas provenance and licence | SOUP BOM; pinned version; licence confirmed | **PARTIAL**: BOM entries done |
| **PA-6.6** | Preventive | Register RC-030 and RC-031 in RMF §5.1 and the manifest | Bound to tests with negative controls | **PENDING** |
| **PA-6.7** | Preventive | No mask is persisted through any path other than the canonical save | Raw-upload sweep; test | **PARTIAL**: zone maps |
| **PA-6.8** | Preventive | Sweep the labelling for other unsupported claims (§12), extending the PA-6.1 mechanism | Each claim traced to code or withdrawn | **PENDING** |

## 16. Verification Evidence (executed 2026-09-28)

**Tests:**
- `backend/tests/unit/test_rc032_region_atlas_guard.py`: 36 `test_rc032_*`. The 22 route tests run
  through the real FastAPI app with fake services; the fixture **fails** rather than skipping. The
  other 14 are unit tests.
- `frontend/src/components/LesionDashboard.rc032.test.ts`: 6 `rc032` tests (source-level, not
  render).
- `backend/tests/unit/test_capa006_labelling_bound_to_code.py`: 60 tests.
- `test_rc024_voxel_spacing.py`: the route check now counts calls in the AST.

**Negative controls.** Script `scripts/safety/rc032_negative_controls.py` (kept in the repository, so anyone can
re-run it). Executed one mutation at a time against the final code, with each mutation's application
asserted and the failing test names recorded. Hashes are SHA-256 of the files
as read by Python (UTF-8, universal newlines, i.e. LF-normalised); a raw CRLF working-tree hash
differs. Record: `docs/iec62304/records/risk_verification/RC-032_negative_controls_2026-09-28.json`,
entries LAB1–LAB6 for PA-6.1.

- **Backend:** 34 mutations, 31 detected. The 3 not detected are redundant by design and stated in
  the record: each of the two route MNI gates is covered by the service gate (they are detected
  when mutated together), and diagonal dominance is covered by the per-axis FOV check.
- **Frontend:** 5 of 5 mutations detected.
- **Labelling (PA-6.1):** 6 of 6 mutations detected.
- **Unexpected undetected mutations:** none.
- **Restored:** 36, 6 and 60 tests passed.

A first run of the final series found that removing the identity check of an explicitly supplied
parcellation went undetected, because the same-image check refused the test's parcellation first.
Two tests were added (a same-image zone map given explicitly), and the run was repeated.

**Full suites on the final code (2026-10-17).** Backend 1073 passed; frontend 15 files and 116
tests; tsc clean; build OK. Before review round 2 the figures were 1048 and 114.

**CI finding (2026-10-17).** The first CI run on PR #43 failed two jobs: Backend Pytest and Risk
Control Verification. The generate-zone-map route tests built the real patient service for the
authorization check, and that service needs cloud credentials. CI has none; the developer machine
had them, which hid the dependency locally.

The route fixture now substitutes the authorization services. The full backend suite was then
re-run locally with no cloud credentials, and all 1073 tests passed. A check confirmed that the real
service fails in that environment exactly as it does in CI. The negative controls were re-run
against the corrected test file.

**Effectiveness check** (pending, after deployment; needs authenticated access by the owner):
- a native study gives geometric regions with the warning, or 422 with reasons;
- an MNI study uses MSMask;
- zone-map generation on a native study returns 422 and the existing zone map is kept;
- a user without access to the patient gets 404;
- CA-6.9 is completed.

## 17. Regulatory Assessment (QP-002 §7)

- The device is **not CE-marked, not FDA-cleared and not in clinical use**. There is no vigilance
  or field-safety reporting obligation (MDR Art. 87) at this time. If any clinical or
  investigational use occurred, the owner must assess it.
- No Declaration of Conformity may be signed while this CAPA is open; the RMF banner includes
  CAPA-006.
- Finding 1 would be a GSPR 23.4 non-conformity on a marketed device. Finding 10 would be an
  MDR Annex I §17.4 / GDPR Art. 32 issue.

## 18. Links

- `docs/qms/QP-002_CAPA_Procedure.md` · SPR-001 (`docs/iec62304/08_Problem_Resolution_Procedure.md`)
- `docs/iec62304/03_Risk_Management_File.md` (HAZ-005, HAZ-010, RC-032, RC-024 and RC-029 errata)
- `docs/iec62304/02_Software_Requirements_Specification.md` (REQ-FUNC-053, REQ-SAFE-020, REQ-SAFE-021)
- `docs/iec62304/records/risk_verification/rc_test_manifest.json` (RC-032, RC-024, RC-029)
- `docs/iec62304/records/capa/CAPA-001_Risk_Control_Verification_Integrity.md` (CA-5 erratum)
- PR #43

## 19. Revision of this record

This record was drafted and revised on the same day, before its first issue in PR #43. Independent
reviews found the following false or overstated statements in earlier drafts, all corrected above:

- **Wrong history.** The 3 / 4 / 3 mm values were said to have "described an earlier software
  version"; see §2.
- **Wrong commit.** "The NameError predates `e39cdaa`"; see §3.
- **Wrong path claim.** "The persisted-zone-map path was orientation-consistent"; see §6.
- **Misquotation.** A quoted docstring "assumed MNI-registered" does not exist; see §4.
- **Wrong attributions.**
  - "the usual path" was attributed to the issued labelling; it appeared only in this CAPA's own
    drafts;
  - "three-tier" was attributed to the PDF;
  - "Vertex AI" was attributed to IFU §9.3.
- **Undercounted outage.** RC-024 was said to have failed at "two of four" route sites; all four
  failed.
- **Overstated verification.**
  - "Every sub-control was mutated": the per-axis FOV condition was not, until a dedicated test was
    added.
  - "Never deployed" was said of the weak gate; see Finding 9.

The first draft also omitted Findings 5–11.

---

**Prepared by**: internal audit, 2026-09-28. The facts in §2–§13 were checked against the git
history and the source, and by execution. Five independent adversarial reviews preceded this issue.
**Requires**: review, confirmation of the root cause, and sign-off by the Software Safety Officer.
Human approval is required before merge (a Class C module is changed: `ms_region_classifier.py`).
