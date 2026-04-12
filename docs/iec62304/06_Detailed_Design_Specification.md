# MSTool-AI: Software Detailed Design Specification

## IEC 62304 Clause 5.4 — Class C Software Unit Design

**Document ID**: DD-001
**Version**: 1.0
**Effective Date**: April 12, 2026
**Software Safety Class**: IEC 62304 Class C

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
| DD-CLS-001 | MAGNIMS Region Classifier (EDT) | `ms_region_classifier.py` | C | HAZ-005 |
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

### DD-CLS-001: MAGNIMS Region Classifier (EDT)

**Purpose**: Classifies MS lesions into MAGNIMS anatomical regions using Euclidean Distance Transform from brain parcellation.

**Interface**:
```
Input:  lesion_mask: np.ndarray (D,H,W), binary (>0 = lesion)
        parcellation_mask: np.ndarray (D,H,W), FreeSurfer labels
        voxel_spacing: tuple (dz, dy, dx) in mm
Output: Dict { classified_mask: np.ndarray (uint8, labels 1-4), lesions: List[Dict], classification_summary: Dict }
```

**Algorithm**:
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

    // Priority cascade: IT > PV > JC > DWM
    IF d_IT <= 1.5 mm:
        region = 3 (Infratentorial)
        confidence = max(0.70, 0.95 - 0.25 * d_IT / 1.5)
    ELIF d_PV <= 1.5 mm:
        region = 1 (Periventricular)
        confidence = max(0.70, 0.95 - 0.25 * d_PV / 1.5)
    ELIF d_JC <= 1.5 mm:
        region = 2 (Juxtacortical)
        confidence = max(0.70, 0.95 - 0.25 * d_JC / 1.5)
    ELSE:
        region = 4 (Deep White Matter)
        d_min = min(d_IT, d_PV, d_JC)
        confidence = min(0.90, 0.60 + 0.30 * min(1.0, (d_min - 1.5) / 10))

    classified_mask[C_k] = region

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

**Error Handling**: ValueError if mask shapes don't match. Empty result if no lesions found.

**Safety**: EDT-based classification is more robust than pixel-adjacency methods. Distance thresholds (1.5mm) match LST-AI dilation criteria. Priority cascade prevents ambiguous classification.

**Implements**: REQ-FUNC-053, REQ-SAFE-010, REQ-SAFE-011

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
| DD-CLS-001 | REQ-FUNC-053, REQ-SAFE-010, 011 | RC-010, RC-011 |
| DD-NII-001 | REQ-DATA-001 | RC-012 |
| DD-NII-002 | REQ-SAFE-012 | RC-012 |
| DD-EDGE-001/002/003 | REQ-FUNC-033, REQ-SAFE-008, 009 | RC-008, RC-009 |

---

*End of Detailed Design Specification*

*This document is maintained under configuration management in the Git repository at `docs/iec62304/06_Detailed_Design_Specification.md`.*
