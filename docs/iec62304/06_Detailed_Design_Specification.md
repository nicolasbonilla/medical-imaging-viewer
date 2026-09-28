# MSTool-AI: Software Detailed Design Specification

## IEC 62304 Clause 5.4 — Class C Software Unit Design

**Document ID**: DD-001
**Version**: 1.2
**Effective Date**: September 28, 2026 (v1.0: April 12, 2026)
**Software Safety Class**: IEC 62304 Class C

| Version | Date | Author | Approved By | Change |
|---------|------|--------|-------------|--------|
| 1.0 | 2026-04-12 | Development Team | — | Initial release |
| 1.1 | 2026-09-28 | Development Team | — | DD-CLS-001 amended. (a) Audit #8 (HAZ-005, REQ-SAFE-010 amended): per-lesion confidence removed; see the amendment note in DD-CLS-001, which was entered on this date under the v1.0 header. (b) CAPA-006: DD-CLS-001 described only the parcellation path. It now also specifies the four-path order used by `method="auto"`, the MSMask atlas path, the MNI grid gate (`looks_mni`, `NotMNISpaceError` in `generate_zone_map_atlas`, HAZ-005 / RC-032) and the zone-map reorientation and shape check in `classify_lesions_with_atlas`. The 1.5 mm thresholds are unchanged. The 3 mm / 4 mm / 3 mm thresholds and two-tier cascade stated in IFU-001, AIA-001, CER-001 and GSPR-001 ~~described an earlier software version (commit cf780f4, February 2026)~~ were wrong when those documents were issued on 2026-04-12 (corrected in v1.2) and are withdrawn there |
| 1.2 | 2026-09-28 | Development Team | — | CAPA-006 / RC-032 / REQ-SAFE-021, DD-CLS-001 brought in line with the final code. (a) Correction of the v1.1 row: it said the 3 mm / 4 mm / 3 mm labelling "described an earlier software version". Not true: the code moved to 1.5 mm on 2026-02-28 (67fa336); IFU-001, AIA-001, CER-001 and GSPR-001 were issued on 2026-04-12 already stating 3 / 4 / 3 mm, while DD-001 v1.0, issued the same day, stated 1.5 mm. (b) A persisted zone map is never reused for classification (v1.1 said the route checked the image before reusing one); the atlas zone map is always generated fresh. (c) The `looks_mni` gate is now specified as implemented: isotropy, unpermuted axis alignment, per-axis field of view, grid centre, header transform. v1.1 described sorted extents and axis alignment only. (d) Added: parcellation detection (`looks_like_freesurfer_parcellation`), geometric preconditions (`prepare_geometric_image`, `GeometricPreconditionError`), the shape check in `classify_from_zone_mask`, the generate-zone-map ordering (delete old zone maps only after a new one exists; `persist()` only, no raw overwrite), and HTTP 422 when no path applies. (e) LST-AI path described as voxel-wise, with no contact rule and no priority. (f) Unit renamed from "MAGNIMS Region Classifier (EDT)": EDT is used by one of four paths only. (g) Withdrawn from the Safety paragraph: "EDT-based classification is more robust than pixel-adjacency methods" (no evidence). Also withdrawn: "Distance thresholds (1.5mm) match LST-AI dilation criteria" (inexact; restated). (h) Implements / traceability now list REQ-SAFE-021 |

---

## 1. Introduction

### 1.1 Purpose

This document provides the detailed design for all Class C software units in MSTool-AI, as required by IEC 62304 Clause 5.4 for software safety Class C. Each unit is described with sufficient detail to enable independent implementation, including interface specifications, algorithm descriptions, data structures, error handling, and safety-related behavior.

### 1.2 Class C Software Units

| Unit ID | Unit Name | File | Safety Class | Risk Reference |
|---------|-----------|------|-------------|---------------|
| DD-AI-001 | AI Segmentation Service | `ai_segmentation_service.py` | C | HAZ-001 |
| DD-VOL-001 | Brain Volumetry — compute_volumes | `brain_volumetry_service.py` | C | HAZ-002 |
| DD-VOL-002 | Brain Volumetry — compare_timepoints | `brain_volumetry_service.py` | C | HAZ-002 |
| DD-RPT-001 | Report Generation | `brain_report_service.py` | C | HAZ-003 |
| DD-LES-001 | Lesion Analysis — analyze_lesions | `lesion_analysis_service.py` | C | HAZ-005 |
| DD-LES-002 | Lesion Analysis — compute_dis_criteria | `lesion_analysis_service.py` | C | HAZ-008 |
| DD-CLS-001 | MAGNIMS Region Classifier (four paths; renamed v1.2, was "(EDT)") | `ms_region_classifier.py` | C | HAZ-005 |
| DD-NII-001 | NIfTI Loader | `nifti_utils.py` | C | HAZ-006 |
| DD-NII-002 | NIfTI Transpose Utilities | `nifti_utils.py` | C | HAZ-006 |
| DD-EDGE-001 | Edge AI Worker — preprocessSlice | `edgeAI.worker.ts` | C | HAZ-004 |
| DD-EDGE-002 | Edge AI Worker — loadModel | `edgeAI.worker.ts` | C | HAZ-004 |
| DD-EDGE-003 | Edge AI Worker — classify | `edgeAI.worker.ts` | C | HAZ-004 |

---

## 2. Unit Designs

### DD-AI-001: AI Segmentation Service

**Purpose**: Orchestrates automatic brain parcellation via SynthSeg on Vertex AI.

**Interface**:
```
Input:  request: AutoSegmentRequest { file_id: str }
Output: AITaskResult { task_id: str, status: str, progress: int, segmentation_id: Optional[str], error: Optional[str] }
```

**Pre-conditions**: User authenticated, file_id references valid NIfTI in GCS.
**Post-conditions**: Returns PROCESSING with task_id, or FAILED with error message.

**Algorithm**:
1. Attempt to load ToolRunnerService from DI container
2. If unavailable → return FAILED with "SynthSeg not configured" message
3. Check `is_synthseg_available()` on ToolRunnerService
4. If available → call `run_synthseg(file_id)` → return PROCESSING with task_id
5. If not available → return FAILED with guidance to use Clinical Tools panel

**Error Handling**: All exceptions caught and encapsulated in AITaskResult.error. No exceptions propagated to caller.

**Safety**: Graceful degradation when AI service unavailable. Never returns partial or corrupted results.

**Implements**: REQ-FUNC-030

---

### DD-VOL-001: Brain Volumetry — compute_volumes

**Purpose**: Computes brain structure volumes from segmentation mask with normative percentile comparison.

**Interface**:
```
Input:  mask: np.ndarray (D,H,W), dtype=uint8, values=FreeSurfer labels
        voxel_spacing: Tuple[float,float,float] in mm
        segmentation_id: str
        patient_age: Optional[int]
        patient_sex: Optional[str] ('M'/'F')
Output: VolumetryResult { structures: List[BrainStructureVolume], total_brain_volume_ml: float, intracranial_volume_ml: float, processing_time_ms: int }
```

**Pre-conditions**: mask is 3D with valid FreeSurfer labels (0-255). voxel_spacing > 0.
**Post-conditions**: All volumes in mm³ and mL. Percentiles in [0, 100].

**Algorithm**:
```
voxel_volume = dz * dy * dx  [mm³]

FOR EACH unique label l in mask (l > 0):
    voxel_count = count(mask == l)
    volume_mm3 = voxel_count * voxel_volume
    volume_ml = volume_mm3 / 1000

    IF patient_age provided:
        age_group = map_to_age_group(patient_age)  // 20-40, 40-60, 60-80, 80+
        (mean, std) = NORMATIVE_VOLUMES[label][age_group]
        IF std > 0:
            z_score = (volume_ml - mean) / std
            percentile = 50 * (1 + erf(z_score / sqrt(2)))
            percentile = clamp(percentile, 0, 100)
        ELSE:
            percentile = 50.0

    is_abnormal = FALSE
    IF label IN VENTRICULAR_LABELS AND percentile > 90:
        is_abnormal = TRUE  // Ventricular enlargement
    ELIF label IN ATROPHY_SENSITIVE_LABELS AND percentile < 10:
        is_abnormal = TRUE  // Atrophy

    total_brain_volume += volume_ml (if not ventricle/CSF)
    intracranial_volume += volume_ml

RETURN VolumetryResult
```

**Error Handling**: Returns empty structures list if no labels found. Division-safe percentile computation (std > 0 check).

**Safety**: Percentile clamped to [0, 100]. Atrophy detection thresholds (10th/90th percentile) are clinically established.

**Implements**: REQ-FUNC-040, REQ-FUNC-041, REQ-FUNC-042, REQ-SAFE-004, REQ-SAFE-005

---

### DD-RPT-001: Report Generation

**Purpose**: Generates structured clinical reports via Claude API with HIPAA-compliant de-identification.

**Interface**:
```
Input:  template_type: str ("general"|"ms_activity"|"ms_lesion_burden"|"ms_comprehensive"|"ms_longitudinal")
        findings: Dict (de-identified clinical data)
        volumetry: Optional[Dict]
        language: str ("en"|"es"|"de")
Output: Dict { report_id: str, content: str, template_type: str, language: str, processing_time_ms: int, model: str, tokens_used: Dict }
```

**Pre-conditions**: ANTHROPIC_API_KEY configured. Findings dict contains ONLY de-identified data (no PHI).
**Post-conditions**: Report content is MAGNIMS-formatted clinical text. No PHI in report.

**Algorithm**:
1. Validate template_type exists in REPORT_TEMPLATES; fallback to "general"
2. Construct system_prompt from REPORT_TEMPLATES[template_type]
3. Construct user_prompt via `_build_findings_prompt(findings, volumetry, language)`
   - Formats clinical indication, technique, patient_age (int only), patient_sex (M/F only)
   - Includes lesion counts, volumes, DIS assessment, longitudinal data
   - Appends language instruction
4. Initialize Anthropic client (lazy load)
5. Call `client.messages.create(model, max_tokens, system, messages)`
6. Extract content from response
7. Return report with metadata and token usage

**Error Handling**: RuntimeError if API key missing. Generic Exception caught, logged, re-raised.

**Safety**:
- **HIPAA Compliance**: Only age (integer), sex (M/F), clinical findings, and measurements are transmitted. No patient name, DOB, MRN, study date, or institution name.
- **Report includes mandatory disclaimer**: "AI-Generated — Requires Physician Review"
- Timeout: relies on httpx default timeout (configurable)

**Implements**: REQ-FUNC-060, REQ-FUNC-061, REQ-FUNC-063, REQ-SAFE-006, REQ-SAFE-007, REQ-SEC-007

---

### DD-LES-001: Lesion Analysis — analyze_lesions

**Purpose**: Identifies individual lesions via connected component analysis with per-lesion metrics.

**Interface**:
```
Input:  mask_3d: np.ndarray (D,H,W), dtype=uint8, values=MAGNIMS labels (0-6)
        voxel_spacing: tuple (dz, dy, dx) in mm, default (1.0, 1.0, 1.0)
        labels: Optional[Dict[int, str]], default MAGNIMS_REGIONS
Output: Dict { lesions: List[Dict], total_count: int, total_burden_mm3: float, total_burden_ml: float, regions: Dict, size_distribution: Dict }
```

**Algorithm**:
```
voxel_volume = dz * dy * dx
lesions = []

FOR EACH unique label l in mask_3d (l > 0):
    binary_mask = (mask_3d == l)
    labeled_array, num_features = scipy.ndimage.label(binary_mask)

    FOR comp_id = 1 TO num_features:
        comp_mask = (labeled_array == comp_id)
        voxel_count = count(comp_mask)
        volume_mm3 = voxel_count * voxel_volume

        IF volume_mm3 < MIN_LESION_VOLUME_MM3 (3.0):
            SKIP  // Noise filter

        centroid = scipy.ndimage.center_of_mass(comp_mask)
        bbox = compute_bounding_box(comp_mask)

        size_category = "small" if < 100mm³, "medium" if 100-1000mm³, "large" if > 1000mm³

        lesions.append({id, label, region, volume_mm3, volume_ml, centroid, bbox, size_category})

SORT lesions BY volume_mm3 DESC
RENUMBER lesion IDs (1, 2, 3...)
COMPUTE per-region statistics and size distribution
RETURN result
```

**Error Handling**: Returns empty result if scipy unavailable (ImportError caught). Returns empty if no lesions found.

**Safety**: 3.0 mm³ minimum volume prevents noise inflation. Connected component analysis is deterministic.

**Implements**: REQ-FUNC-050, REQ-FUNC-051

---

### DD-LES-002: Lesion Analysis — compute_dis_criteria

**Purpose**: Evaluates McDonald 2024 Dissemination in Space criteria.

**Interface**:
```
Input:  mask_3d: np.ndarray (D,H,W) with MAGNIMS labels
        labels: Optional[Dict], voxel_spacing: tuple
Output: Dict { dis_met_brain: bool, brain_regions_with_lesions: int, region_details: Dict, ... }
```

**Algorithm**:
```
DIS_REGIONS = [1 (PV), 2 (JC), 3 (IT)]
regions_with_qualifying_lesions = 0

FOR EACH region_id IN DIS_REGIONS:
    binary = (mask_3d == region_id)
    labeled, num = scipy.ndimage.label(binary)
    qualifying_count = 0

    FOR comp = 1 TO num:
        volume = count(labeled == comp) * voxel_volume
        IF volume >= MIN_LESION_VOLUME_MM3:
            qualifying_count += 1

    IF qualifying_count > 0:
        regions_with_qualifying_lesions += 1

dis_met_brain = (regions_with_qualifying_lesions >= 2)

RETURN { dis_met_brain, brain_regions_with_lesions, region_details, ... }
```

**Safety**: McDonald 2024 requires >= 2 of 5 regions for DIS. Brain-only assessment evaluates 3 of 5 (PV, JC, IT). System explicitly documents that spinal cord and optic nerve are not assessed.

**Implements**: REQ-FUNC-052, REQ-SAFE-015

---

### DD-CLS-001: MAGNIMS Region Classifier

**Purpose**: Classifies MS lesions into MAGNIMS anatomical regions by the MAGNIMS contact criterion (MAGNIMS / McDonald 2024; Filippi et al. 2019): periventricular (PV) = abutting the lateral ventricles; juxtacortical (JC) = abutting the cortex; infratentorial (IT) = in or touching the brainstem or cerebellum; otherwise deep white matter (DWM). Priority when several apply: IT > PV > JC > DWM. Only PV, JC and IT count towards brain DIS; the spinal cord and optic nerve are not evaluated. The unit provides four classification paths; the route `POST /segmentation/{id}/classify-regions` (`backend/app/api/routes/segmentation_regions.py`) selects between them.

**Path selection** (`method`, default `"auto"`; the path actually used is returned in `method`). In `auto`, the first path that produces a result is used, in this order:

| Order | `method` | Function | Used when | "Abutting" implemented as |
|-------|----------|----------|-----------|---------------------------|
| 1 | `lst-ai` | route (inline) | Another segmentation of the same file has a `validation_source` containing `lst-ai`. The LST-AI integration is disabled by default. | Voxel-wise copy: each lesion voxel takes the LST-AI zone value at that voxel, and lesion voxels in no zone get DWM. There is no per-lesion contact rule, no IT > PV > JC priority and no minimum volume, so one lesion can receive several regions |
| 2 | `parcellation` | `classify_lesions_with_parcellation` | An explicit `parcellation_id` that passes `looks_like_freesurfer_parcellation` (otherwise HTTP 422, also in `auto`). Or, without `parcellation_id`, another segmentation of the same file that passes it (auto-detection, below). The SynthSeg integration is disabled in the current configuration. | Minimum EDT distance from the lesion to the ventricle / cortex / infratentorial labels <= 1.5 mm (algorithm below) |
| 3 | `msmask` | `classify_lesions_with_atlas` (zone map generated fresh in every call) | The source image, as loaded with its header, passes the MNI grid gate (`looks_mni`, below). This is the usual path for MNI-space images, because LST-AI and SynthSeg are disabled. A persisted zone map is never reused for classification. | Any lesion voxel in an atlas zone. The zones are the MSMask ventricle / cortex / infratentorial masks dilated by one voxel (3x3x3 cube, as in LST-AI), within atlas white matter, plus the infratentorial label itself |
| 4 | `geometric` | `classify_lesions_geometric` | None of the paths above produced a result, and `prepare_geometric_image` accepts the source image (below). Least accurate. | Coordinate heuristics, not anatomical landmarks: centroid in the lowest 25 % of the brain's extent along array axis 0, which `prepare_geometric_image` requires to be the slice axis pointing superior = IT; mean distance from the brain centre < 35 % of the maximum = PV; minimum distance to the brain surface < min(8 mm, 15 % of the brain radius) = JC |

With an explicit `method`, a path that cannot run is an error rather than a fall-through:
- `lst-ai` without an LST-AI segmentation: HTTP 400.
- `parcellation` with an unknown `parcellation_id`: HTTP 404. In `auto`, an unknown `parcellation_id` falls through to the next path.
- A `parcellation_id` that is not a FreeSurfer parcellation: HTTP 422, with `parcellation` or `auto`.
- `msmask` on a non-MNI image: HTTP 422. Atlas file or nilearn missing: 400. Other failure: 500.
- `geometric` whose preconditions fail: HTTP 422.

In `auto`, a refused atlas or geometric path falls through to the next path. A non-FreeSurfer `parcellation_id` does not fall through; it gets HTTP 422. If no path produces a result and the atlas and/or geometric path was refused, the route returns HTTP 422 "No region-classification method can be applied validly to this image", followed by the reasons. If no path applied and none was refused, the route returns HTTP 400.

**Interface (path 2, parcellation)**:
```
Input:  lesion_mask: np.ndarray (D,H,W), binary (>0 = lesion)
        parcellation_mask: np.ndarray (D,H,W), FreeSurfer labels
        voxel_spacing: tuple (dz, dy, dx) in mm
Output: Dict { classified_mask: np.ndarray (uint8, labels 1-4), lesions: List[Dict], classification_summary: Dict }
```

**Algorithm (path 2, parcellation + EDT, `classify_lesions_with_parcellation`)**:
```
// 1. Extract anatomical reference masks
ventricle_mask = parcellation IN {4, 43}        // Lateral ventricles
cortex_mask = parcellation IN {3, 42}           // Cerebral cortex
infratentorial_mask = parcellation IN {7, 8, 16, 46, 47}  // Brainstem + cerebellum

// 2. Compute distance transforms (mm)
D_vent = EDT(NOT ventricle_mask, sampling=voxel_spacing)
D_cortex = EDT(NOT cortex_mask, sampling=voxel_spacing)
D_infra = EDT(NOT infratentorial_mask, sampling=voxel_spacing)

// 3. Classify each lesion component
FOR EACH connected component C_k in lesion_mask:
    IF volume(C_k) < 3.0 mm³: SKIP

    d_IT = min(D_infra[C_k])
    d_PV = min(D_vent[C_k])
    d_JC = min(D_cortex[C_k])

    // Priority cascade: IT > PV > JC > DWM  (deterministic rule; returns region only)
    IF d_IT <= 1.5 mm:
        region = 3 (Infratentorial)
    ELIF d_PV <= 1.5 mm:
        region = 1 (Periventricular)
    ELIF d_JC <= 1.5 mm:
        region = 2 (Juxtacortical)
    ELSE:
        region = 4 (Deep White Matter)

    classified_mask[C_k] = region
    lesion.confidence = None                     // HAZ-005: no calibrated confidence exists
    lesion.confidence_note = CONFIDENCE_NOTE_DISTANCE
    lesion.distances_mm = { to_ventricle: d_PV, to_cortex: d_JC, to_infratentorial: d_IT }
                                                 // each rounded to 0.01 mm; None if not finite

RETURN { classified_mask, lesions, classification_summary }
```

**Constants**:
- `LATERAL_VENTRICLE_LABELS = {4, 43}`
- `CORTEX_LABELS = {3, 42}`
- `INFRATENTORIAL_LABELS = {7, 8, 16, 46, 47}`
- `PV_DISTANCE_THRESHOLD_MM = 1.5`
- `JC_DISTANCE_THRESHOLD_MM = 1.5`
- `IT_DISTANCE_THRESHOLD_MM = 1.5`
- `MIN_LESION_VOLUME_MM3 = 3.0`
- `MSMASK_PATH = "/app/data/msmask/sub-mni152_space-mni_msmask.nii.gz"` (MSMask labels: 1 CSF, 2 GM/cortex, 3 WM, 4 ventricles, 5 infratentorial)
- `looks_mni`: `MNI_ISOTROPY_TOLERANCE = 1.05` (max/min voxel size); axis alignment |Rn[c,c]| >= 0.999 (about 2.5°); `MNI_REFERENCE_FOV_MM = (181, 217, 181)`; `MNI_FOV_TOLERANCE = 0.25` (per axis); `MNI_REFERENCE_CENTRE_MM = (0, -18, 18)`; `MNI_CENTRE_TOLERANCE_MM = 10.0`. The first version (v1.1) was "|cos| >= 0.999; MNI152 box (181, 217, 181) mm; extent tolerance 25 %" with sorted extents; tightened 2026-09-28 (CAPA-006 review)
- `FREESURFER_PARCELLATION_LABELS = {2, 3, 4, 7, 8, 10, 16, 41, 42, 43}`; `FREESURFER_HIGH_LABELS = {16, 41, 42, 43}`; `ZONE_MAP_DESCRIPTION = "MAGNIMS Zone Map"`

**Algorithm (path 3, MSMask atlas, `generate_zone_map_atlas` + `classify_lesions_with_atlas`)**:
```
// generate_zone_map_atlas(target_img, voxel_spacing)
IF NOT looks_mni(target_img.affine, target_img.shape):
    RAISE NotMNISpaceError                      // HAZ-005 / RC-032: fail closed, before the atlas is loaded
atlas = MSMask (MNI152 space)
S = ones(3,3,3)                                 // one-voxel dilation, as in LST-AI
zone[WM] = 4                                    // DWM
zone[Infratentorial OR (dilate(Infratentorial, S) AND WM)] = 3      // IT
zone[dilate(GM, S) AND WM AND zone != 3] = 2                         // JC
zone[dilate(Ventricles, S) AND WM AND zone != 3] = 1                 // PV (overrides JC)
ref_affine = target_img.affine
IF |centre(target grid) - centre(atlas)| >= 30 mm:                   // e.g. origin not set
    ref_affine = target voxel sizes, re-centred on the atlas centre (axis directions kept)
    // retained from before RC-032. An image that passes looks_mni has its grid centre within
    // 10 mm of (0, -18, 18), which is the MSMask grid centre (193x229x193, 1 mm)
zone = resample_to_img(zone, target grid with ref_affine, nearest)   // nilearn; grid resampling only; NO registration
RETURN zone                                     // NIfTI-native order (a0, a1, k)

// classify_lesions_with_atlas(lesion_mask (k, a0, a1), target_img, voxel_spacing)
zone = transpose(generate_zone_map_atlas(target_img).zone_mask, (2, 0, 1))   // (a0, a1, k) -> (k, a0, a1)
IF zone.shape != lesion_mask.shape:
    RAISE ValueError                            // refuse to classify on a mismatched grid
result = classify_from_zone_mask(lesion_mask, zone, voxel_spacing)
    // IF zone.shape != lesion_mask.shape: RAISE ValueError   (checked again here, RC-032)
    // per lesion: contact rule, any overlap, priority IT > PV > JC; no voxel in any zone -> DWM
    // with atlas_coverage = false
result.method = "msmask"
```

The `classify-regions` route always calls `classify_lesions_with_atlas`, so the zone map used for classification is generated fresh in every call. **A persisted zone map is never reused for classification** (CAPA-006). The zone map written by `generate-zone-map` came back transposed ((k, a1, a0)) after a GCS reload, because that route overwrote the blob without the RC-031 orientation marker. On MNI grids this raised an IndexError, which `auto` swallowed into a silent geometric fallback; on grids with a square in-plane matrix the zones were silently transposed. The overwrite has been removed (below). v1.1 of this document described a reuse path guarded by `looks_mni`; that path no longer exists.

**MNI grid gate (HAZ-005, RC-032, CAPA-006)**: the MSMask atlas is in MNI152 space and the software performs no registration, so the atlas is only valid on images that are already in MNI152 space.
- `looks_mni(affine, shape, header=None)` returns True only if every one of these holds:
  1. Isotropic voxels: max/min voxel size <= 1.05.
  2. Axis-aligned and not permuted: for each voxel axis c, |Rn[c,c]| >= 0.999 (within about 2.5°), where Rn is the direction-cosine matrix.
  3. Field of view |R[c,c]|·(shape[c] − 1) within 25 % of (181, 217, 181) mm on each world axis. Extents are not sorted.
  4. Grid centre within 10 mm of the MNI152 template centre (0, -18, 18).
  5. If a header is given, a spatial transform is set (sform or qform code != 0).

  Any exception returns False (fail closed). v1.1 of this document specified the first version of the gate: sorted extents, axis alignment in any permutation, no isotropy, centre or header condition. That version accepted native 2D FLAIR, e.g. 240x240x48 at 0.94x0.94x3 mm (CAPA-006 review, 2026-09-28).
- `generate_zone_map_atlas` raises `NotMNISpaceError` (a `ValueError` subclass) when `looks_mni(affine, shape)` is False.
- `classify-regions` route: loads the original source image and checks it with `looks_mni(affine, shape, header)` before calling `classify_lesions_with_atlas`. With `method="msmask"` the request is refused with HTTP 422. With `method="auto"` the route falls through to the geometric path and returns `atlas_unavailable_reason`. `LesionDashboard` then shows the amber warning `classify.atlasUnavailable` ("Atlas regions not used: this image is not in MNI space, so the least accurate geometric fallback was applied. Verify every region before using it for DIS."). Whenever the method is `geometric` and no `atlas_unavailable_reason` is set, it shows the amber warning `classify.geometricWarning` ("Geometric heuristics: the least accurate method (coordinate rules, not anatomical landmarks). Verify every region before using it for DIS.").
- `generate-zone-map` route: see "Zone-map generation" below. The route returns HTTP 422 and generates or persists nothing for a non-MNI image.
- Limitation: the gate checks only the grid. It cannot certify that an image is truly normalised: an image resampled onto an MNI grid without being registered to it, or an imperfectly normalised image, can pass. Rationale for the gate: in a controlled experiment without registration (30 MSLesSeg scans with expert lesions, 2026-09-28), moving the anatomy by 3° / 3 % / 5 mm inside an MNI grid changed the region of 28 % of expert lesions (62 % at 15° / 10 % / 20 mm) and flipped brain DIS in up to 13 % of scans.

**Atlas path orientation (`classify_lesions_with_atlas`)**: `generate_zone_map_atlas` returns the zone map in NIfTI-native (a0, a1, k) order, while lesion masks are internal (k, a0, a1). The function transposes the zone map with (2, 0, 1) and raises `ValueError` if the result does not have the lesion mask's shape. Before 2026-09-28 the transpose was missing: the path failed with a shape error on non-cubic volumes and would have applied rotated zones on cubic ones. The `generate-zone-map` route applies the same (2, 0, 1) transpose. `classify_from_zone_mask` itself also raises `ValueError` when the zone map's shape differs from the lesion mask's. Before this check a mismatch surfaced as an IndexError, which `auto` turned into a silent geometric fallback. A zone map of the same shape but transposed (square in-plane grid) cannot be detected there, so callers must supply the zone map in (k, a0, a1) order.

**Parcellation detection (`looks_like_freesurfer_parcellation(label_values, description)`, RC-032, CAPA-006)**: returns True only if the segmentation contains >= 3 of `FREESURFER_PARCELLATION_LABELS` **and** >= 1 of `FREESURFER_HIGH_LABELS` {16, 41, 42, 43}, and its description is not "MAGNIMS Zone Map". Both routes use it for an explicit `parcellation_id` (HTTP 422 if it fails) and for auto-detection of a sibling segmentation. Before 2026-09-28 the test was ">= 3 of the ten labels" only. A MAGNIMS zone map (labels 1-4) passed it, and its label 4 (Deep White Matter) was read as the FreeSurfer lateral ventricle (label 4), so DWM lesions were reported as Periventricular. A zone map or a region-classified lesion mask never carries labels 16 or 41-43.

**Geometric preconditions (`prepare_geometric_image(affine, native_image, lesion_shape)`, RC-032, CAPA-006)**: returns the source image in the lesion mask's (k, a0, a1) order. It raises `GeometricPreconditionError` (a `ValueError` subclass) when:
- the image cannot be read;
- the orientation is indeterminate (affine not 4x4, not finite, or singular);
- the slice axis (native axis k) does not point Superior (`nib.aff2axcodes(affine)[2] != "S"`), as in sagittal, coronal or superior-to-inferior acquisitions;
- the image is not 3-D;
- the reordered image does not match the lesion mask's shape;
- the image is blank.

`classify_lesions_geometric` raises `ValueError` when `image_data` does not match the lesion mask's shape. Before 2026-09-28 the route passed the image in native order, and the heuristics silently replaced it with the whole array as "brain" on every non-cubic volume (JC then meant "near the array corner"). The IT rule also ran on whatever axis 0 happened to be. The heuristics themselves are unchanged coordinate rules.

**Zone-map generation (`POST /segmentation/generate-zone-map`, RC-032, CAPA-006)**: zone maps are for display only; `classify-regions` never reads them (see above).
1. Voxel spacing comes from the source image header (`_voxel_spacing_from_source_image`). The former fallback read the undefined names `metadata` / `segmentation_id` (NameError, HTTP 500).
2. An explicit `parcellation_id` must exist (404) and pass `looks_like_freesurfer_parcellation` (422). Otherwise a sibling segmentation that passes it is auto-detected.
3. With a parcellation: `generate_zone_map` (EDT, 1.5 mm).
4. Without a parcellation: MSMask. The original loaded image, including its header, must pass `looks_mni` (else HTTP 422). A `NotMNISpaceError` from `generate_zone_map_atlas` also gives HTTP 422. The result is transposed (2, 0, 1) to (k, a0, a1).
5. An empty zone map gives HTTP 400.
6. Existing "MAGNIMS Zone Map" segmentations of the file are deleted only after the new zone map has been generated. They used to be deleted first, which destroyed them on every refusal and left `zone_map_seg_id` dangling.
7. The new zone map is persisted only through `persist()` (MRI-native, RC-031 v2 marker). The former raw GCS overwrite, which dropped the marker, has been removed.

**Per-lesion output: evidence, not confidence (RC-010 (amended), HAZ-005, REQ-SAFE-010 amended 2026-09-28)**:

No classification path emits a per-lesion confidence. `confidence` is always `None` and `confidence_note` holds a plain-language statement of how the region was assigned. Each path reports its evidence under its own name instead:

| Path | Function | Evidence fields | Meaning |
|------|----------|-----------------|---------|
| Parcellation (EDT) | `classify_lesions_with_parcellation` | `distances_mm.to_ventricle`, `.to_cortex`, `.to_infratentorial` | Minimum EDT distance (mm) from the lesion to each landmark, rounded to 0.01 mm. `None` when that landmark is absent from the parcellation (infinite distance). Without this, the route sanitiser would turn infinity into 0.0, which reads as "touching". |
| MSMask zone map | `classify_from_zone_mask` | `region_overlap_fraction` | Fraction of ALL the lesion's voxels that lie inside the assigned zone. The denominator is the full lesion voxel count, so a lesion that only just touches a zone is not reported as 100 %. `None` when the lesion is in no zone. |
| | | `zone_coverage_fraction` | Fraction of the lesion's voxels inside any white-matter zone (0.0 when the lesion is in no zone). |
| | | `atlas_coverage` | `false` means the lesion lies in no MSMask white-matter zone, so Deep White Matter was assigned BY DEFAULT and not by the MAGNIMS contact rule. `confidence_note` then says so (`CONFIDENCE_NOTE_DEFAULT_DWM`), and the UI shows an amber data-quality warning ("No WM zone — DWM by default"). |
| Geometric | `classify_lesions_geometric` | (heuristic `distances_mm` proxies only) | `confidence = None`; the geometric distances are heuristic proxies, not landmark distances. |

Descriptive fractions and distances are not probabilities. The region assignment logic is unchanged: the IT > PV > JC > DWM priority, the 1.5 mm thresholds, and the MSMask contact rule (any overlap, priority IT > PV > JC, else DWM).

> **Amendment 2026-09-28 (audit #8, HAZ-005)**: Version 1.0 of this section specified a per-lesion `confidence`. Inside the 1.5 mm threshold it was `max(0.70, 0.95 - 0.25 * d / 1.5)`, used for each of IT, PV and JC. For DWM it was `min(0.90, 0.60 + 0.30 * min(1.0, (d_min - 1.5) / 10))`. The MSMask zone-map path, which that version did not document, reported the in-zone fraction as `confidence`, or a fixed 0.50 when the lesion lay in no zone. None of these values was calibrated against ground truth. The formulas were removed from the code (`_distance_to_confidence` deleted; `_classify_by_distance` now returns `(region_id, region_name)`) and from the algorithm above. Verified by UT-CLS-002 (`backend/tests/unit/test_region_confidence_haz005.py`) and UI-RC010 (`frontend/src/components/LesionDashboard.haz005.test.ts`).

**Error Handling**:
- `ValueError` if mask shapes don't match: parcellation, the atlas zone map after reorientation (`classify_lesions_with_atlas` and `classify_from_zone_mask`), and the geometric image.
- `NotMNISpaceError` when the image grid is not MNI-like: HTTP 422 for `method="msmask"` and for `generate-zone-map`; for `method="auto"`, the next path with `atlas_unavailable_reason`.
- `GeometricPreconditionError` when the geometric heuristics cannot be applied validly: HTTP 422 for `method="geometric"`; in `auto` the reason is kept.
- HTTP 422 for a `parcellation_id` that is not a FreeSurfer parcellation.
- HTTP 422 "No region-classification method can be applied validly to this image" plus the reasons, when every applicable path refused.
- Empty result if no lesions found.

**Safety**: Each path is used only when its precondition holds (RC-032): the MNI-space atlas only on MNI-like grids, a parcellation only if it is a FreeSurfer-label parcellation, and the geometric heuristics only on a readable, non-blank, axial inferior-to-superior 3-D image in the lesion mask's axis order. Otherwise the path is refused. If no path remains, the request fails with the reasons. The atlas zone map is generated fresh, reoriented and shape-checked; a persisted zone map is never reused. The grid gate cannot certify true normalisation. The 1.5 mm distance thresholds approximate LST-AI's one-voxel (3x3x3) dilation at 1 mm isotropic: face- and edge-adjacent voxels (1.0 and 1.41 mm) count as contact, corner-adjacent voxels (1.73 mm) do not. *(v1.0/v1.1 text withdrawn in v1.2, CAPA-006: "EDT-based classification is more robust than pixel-adjacency methods" (no evidence); "Distance thresholds (1.5mm) match LST-AI dilation criteria" (inexact).)* The priority cascade makes the assignment deterministic. No per-lesion confidence is emitted (RC-010 (amended)). The accuracy of region assignment has NOT been measured against expert region labels on any path, so the HAZ-005 residual risk is UNDETERMINED (RMF-001).

**Implements**: REQ-FUNC-053, REQ-SAFE-010 (amended 2026-09-28), REQ-SAFE-011, REQ-SAFE-021 (RC-032, CAPA-006)

---

### DD-NII-001: NIfTI Loader

**Purpose**: Loads NIfTI files from raw bytes with automatic gzip detection.

**Interface**:
```
Input:  file_data: bytes (raw NIfTI file)
        normalize: bool (scale to uint8 [0,255])
Output: Tuple[nibabel.Nifti1Image, np.ndarray]
```

**Algorithm**:
1. Detect gzip by checking magic bytes (0x1f, 0x8b)
2. Set suffix: ".nii.gz" if gzipped, ".nii" otherwise
3. Write to temporary file (nibabel requires file path)
4. Load via nibabel.load(tmp_path)
5. Extract data via img.get_fdata()
6. If normalize: scale to uint8 [0, 255]
7. Delete temporary file (in finally block)
8. Return (image, data)

**Safety**: Temporary file always cleaned up (finally block). No path injection (suffix is hardcoded).

**Implements**: REQ-DATA-001

---

### DD-NII-002: NIfTI Transpose Utilities

**Purpose**: Converts between internal (D,H,W) and NIfTI (W,H,D) array conventions.

**Interface**:
```
transpose_for_nifti(array, from='DHW') → array in (W,H,D)
transpose_from_nifti(array, to='DHW') → array in (D,H,W)
```

**Algorithm**: np.transpose with fixed permutation tables:
- DHW → WHD: axes (2, 1, 0)
- HWD → WHD: axes (1, 0, 2)
- WHD → WHD: identity

**Safety**: Deterministic, reversible. ValueError on unsupported convention.

**Implements**: REQ-SAFE-012 (axis mismatch handling)

---

### DD-EDGE-001/002/003: Edge AI Worker

**Purpose**: Browser-based neural network inference for quick brain screening.

**Interface (classify)**:
```
Input:  imageData: Float32Array (flattened MRI slice)
        width: number, height: number
Output: { normal: number [0,1], abnormal: number [0,1], inferenceTimeMs: number }
```

**Algorithm**:
1. **Preprocess**: Bilinear resize to 224×224, min-max normalize to [0,1]
2. **Infer**: Create ONNX tensor [1,1,224,224], run session
3. **Postprocess**: If logits → softmax (max-subtracted for numerical stability); if probabilities → use directly
4. Return {normal, abnormal, inferenceTimeMs}

**Execution Providers** (priority):
1. WebGPU (hardware accelerated)
2. WASM (fallback, always available)

**Safety**:
- Runs in isolated Web Worker thread (cannot block UI)
- No data leaves browser (privacy)
- Softmax uses max-subtraction for numerical stability
- Model availability checked via HEAD request (hidden when unavailable)

**Implements**: REQ-FUNC-033, REQ-SAFE-008, REQ-SAFE-009

---

## 3. Traceability Summary

| DD Unit | Implements Requirements | Risk Controls |
|---------|------------------------|---------------|
| DD-AI-001 | REQ-FUNC-030 | RC-001, RC-002, RC-003 |
| DD-VOL-001 | REQ-FUNC-040, 041, 042, REQ-SAFE-004, 005 | RC-004, RC-005 |
| DD-VOL-002 | REQ-FUNC-040 | RC-004 |
| DD-RPT-001 | REQ-FUNC-060, 061, 063, REQ-SAFE-006, 007, REQ-SEC-007 | RC-006, RC-007 |
| DD-LES-001 | REQ-FUNC-050, 051 | RC-010 |
| DD-LES-002 | REQ-FUNC-052, REQ-SAFE-015 | RC-015 |
| DD-CLS-001 | REQ-FUNC-053, REQ-SAFE-010 (amended 2026-09-28), 011, 021 | RC-010 (amended), RC-011, RC-032 (path preconditions: MNI grid gate, parcellation check, geometric preconditions; CAPA-006) |
| DD-NII-001 | REQ-DATA-001 | RC-012 |
| DD-NII-002 | REQ-SAFE-012 | RC-012 |
| DD-EDGE-001/002/003 | REQ-FUNC-033, REQ-SAFE-008, 009 | RC-008, RC-009 |

---

*End of Detailed Design Specification*

*This document is maintained under configuration management in the Git repository at `docs/iec62304/06_Detailed_Design_Specification.md`.*
