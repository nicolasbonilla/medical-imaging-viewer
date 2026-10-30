# MSTool-AI: Software Detailed Design Specification

## IEC 62304 Clause 5.4 — Class C Software Unit Design

**Document ID**: DD-001
**Version**: 1.4 DRAFT (2026-10-25 — release integration: DD-RPT-001 amended (template variants, order in the route); PENDING owner approval) — previous: 1.3 DRAFT (2026-10-24 — DD-LES-003 added, DD-LES-002 and DD-RPT-001 annotated, PRB-003 / CAPA-016; PENDING owner approval), 1.2 DRAFT (2026-10-24 — DD-RPT-001 amended, DD-RPT-002 added, CAPA-014, updated after the second and third reviews and the final check; PENDING owner approval) — all integrated on `release/owner-signoff-2026-10-25` — last approved: 1.1
**Effective Date**: September 28, 2026 (v1.0: April 12, 2026)
**Software Safety Class**: IEC 62304 Class C

| Version | Date | Author | Approved By | Change |
|---------|------|--------|-------------|--------|
| 1.0 | 2026-04-12 | Development Team | — | Initial release |
| 1.1 | 2026-09-28 | Development Team | N. G. Bonilla Vargas — approved 2026-10-17 (PR #43) | DD-CLS-001 amended. (a) Audit #8 (HAZ-005, REQ-SAFE-010 amended, PR #42): per-lesion confidence removed. The amendment note in DD-CLS-001 was entered on 2026-09-28 under the v1.0 header; it is covered by this version. (b) CAPA-006 / RC-032 / REQ-SAFE-021: v1.0 described only the parcellation path. DD-CLS-001 now also specifies: the four-path order used by `method="auto"`; the LST-AI path as a voxel-wise copy with no contact rule and no priority; the MSMask atlas path; the MNI grid gate (`looks_mni`: isotropy, unpermuted axis alignment, per-axis field of view, grid centre, header transform; `NotMNISpaceError`) and its limits (SPM12 default bounding box refused; a well-behaved native 3D isotropic axial scan can pass); the zone-map reorientation and shape checks (`classify_lesions_with_atlas`, `classify_from_zone_mask`); that a persisted zone map is never reused for classification; parcellation identity (`looks_like_freesurfer_parcellation`: all of {2, 3, 4, 16, 41, 42, 43}, not a zone map, >= 500 mL; same image and grid); the geometric preconditions (`prepare_geometric_image`, `GeometricPreconditionError`, slice axis within 30° of inferior-superior); refusal (HTTP 422) versus fault (HTTP 500, `atlas_error`) handling; object-level authorization of both region routes (RC-029); the generate-zone-map order (authorize, validate, create and persist, then delete older zone maps); zone-map volumes from the image voxel volume; and the longitudinal compare route's use of the same gate. The 1.5 mm thresholds are unchanged; v1.0 already stated them. The 3 mm / 4 mm / 3 mm thresholds and two-tier cascade stated in IFU-001, AIA-001, CER-001 and GSPR-001 were wrong when those documents were issued on 2026-04-12 (the code had applied 1.5 mm since 2026-02-28, commit 67fa336, while DD-001 v1.0, issued the same day, stated 1.5 mm); they are withdrawn there. (c) Unit renamed from "MAGNIMS Region Classifier (EDT)": EDT is used by one of four paths only. (d) Withdrawn from the Safety paragraph (v1.0 text, quoted there): "EDT-based classification is more robust than pixel-adjacency methods" (no evidence) and "Distance thresholds (1.5mm) match LST-AI dilation criteria" (inexact; restated). (e) Implements / traceability now list REQ-SAFE-021, RC-032 and RC-029 |
| 1.2 (draft) | 2026-10-24 | Development Team | PENDING owner approval | CAPA-014. DD-RPT-001 amended: its statements that report generation was de-identified and that no name, date of birth or record number reached the provider were not true before CAPA-014 (the clinician's free text and the exact age were sent) — withdrawn. Now (redesign after the review of PR #67): structured payload only, the clinician's text merged by the route, a detection-only check before the call, counts logged. DD-RPT-002 added (`report_payload_guard.py`, RC-064/RC-065). Updated after the second independent review (N1–N10): numbered placeholders and the draft layout, "not available", physical ranges, record-number matching, the device's own words and pairs. Updated after the third review (R1–R4, M2): the patient's own numbers refused in number fields, range exceptions, boxes the model cannot produce, bidirectional controls, cut text marked. Updated after the final check: the entry and the notes as response fields rendered outside Markdown |
| 1.3 (draft) | 2026-10-24 | Development Team | PENDING owner approval | PRB-003 / CAPA-016. DD-LES-003 added (`dis_review_gate.py`, RC-070/RC-071: DIS only on a segmentation a radiologist confirmed for its current mask). DD-LES-002: called only after DD-LES-003 (unit unchanged). DD-RPT-001: the DIS block of the prompt passes a result only when it is marked evaluated, otherwise NOT EVALUATED and a rule against deriving DIS; Amended 2026-10-24 after the independent review of PR #68 at 4c601f2: DIS only on MAGNIMS regions assigned by the classification to the current lesions; DIS confirmation for every segmentation (AI drafts after their own review), bound to mask and labels, idempotent, with history, metadata-only, durable; report bound to its own segmentation, no regions and no DIS instruction to the model without an evaluated DIS, model DIS lines replaced; region caveat; notice for lesion-detection tools only; Amended again 2026-10-24 after the second independent review of PR #68 at 29abe29: DD-LES-003 amended (one region per connected lesion, region corrections acknowledged, confirmer name and history by role, review fields written alone, report lesion table on the server, per-sentence model-text check, templates without per-region sections) |
| 1.4 (draft) | 2026-10-25 | Development Team | PENDING owner approval | Release integration of PRs #67 and #68 (`release/owner-signoff-2026-10-25`). DD-RPT-001: the provider receives one of the fixed template variants (RC-064 amended, REQ-SEC-021 (f)), chosen on the DIS block of the payload; in the route, PRB-003's output check runs on the model's text before CAPA-014's draft assembly (`draft_parts` / `draft_text`); one `segmentation_id` request field serves both PRs (patient record for the identifier check; DIS state and lesion table derived on the server). Record: `records/releases/RELEASE-2026-10-25_integration_notes.md`. *Amended 2026-10-28 after the independent integration review of PR #69 at 6d1fde2 (`records/releases/RELEASE-2026-10-25_integration_notes.md` §9): DD-RPT-001 — rows without a region and a fixed "regions not confirmed" line when the regions are unconfirmed; format characters removed from the model's text before the DIS output check; `dis_review_gate.is_evaluated` is the one "evaluated" rule; the geometry 422 starts with `GEOMETRY_UNREADABLE_PHRASE`.* *Amended 2026-10-28 after the browser capture session of the release build (`records/releases/RELEASE-2026-10-25_integration_notes.md` §10): classify-regions returns `labels` (the stored scheme) and `removed_small_components` (route-level comparison of the mask before and after; the Class C classifier is unchanged); the viewer store applies the server's labels to what it draws (`applyServerLabels`).* *Amended 2026-10-28 after the second independent review of PR #69 (`records/releases/RELEASE-2026-10-25_integration_notes.md` §11): `utils/drawnLabels.ts` (what the 2D canvas draws, the fallback colour for a value without a label — cyan `#00FFFF`, as #71's `UNLISTED_LABEL_HEX` — the check before a confirmation); the store's `maskValuesCallback` / `maskLabelValues` and its opacity floor when a session is restored; `ViewerApp` opens a segmentation from `getSegmentation()`; `dis_review_gate.regions_state` returns `removed_small_components` for the current lesion footprint only; classify-regions carries an earlier removal forward (`includes_earlier_classifications`); the assistant's filter requires a boolean `dis_met`; a lesion-table failure other than the voxel geometry starts with `LESION_TABLE_FAILED_PHRASE`. NiiVue's views are not changed (PR #71 overlap). Film capture "DWM: 1 lesions": DD-RPT-001 — the findings prompt writes "1 lesion" for a count of one (`_lesions`), and the synthetic payloads of the device's own words print both forms (RC-065); the lesion dashboard takes its lesion counts from `lesions.countOne/Other` and `lesions.dwmCountOne/Other` (en/es/de).* *Placement corrected: the capture-session sentence above had been written into the approval column of this row; moved here, text unchanged.* *Amended 2026-10-29 after the final check of PR #69 (`records/releases/RELEASE-2026-10-25_integration_notes.md` §12): `ImageViewer2D` publishes the segmentation the standard 2D view draws (`overlayOnScreen`, store); `undrawnMaskValues` also checks the view on screen and, on a classified segmentation, the stored labels (`regions.stored_labels`, served by `dis_review_gate.regions_state`); the overlay controls lock the label preset on a classified segmentation; the confirmation sends `drawn_labels_sha256` (`utils/drawnLabels.ts` / `dis_review_gate.drawn_labels_sha256`, same canonical text), checked by `POST /segmentation/{id}/review/confirm`.* |

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
| DD-RPT-001 | Report Generation | `brain_report_service.py` | C | HAZ-003, HAZ-016 |
| DD-RPT-002 | Report Provider Payload and Check (draft 2026-10-24, CAPA-014) | `report_payload_guard.py` | C (part of the report item) | HAZ-016 |
| DD-LES-001 | Lesion Analysis — analyze_lesions | `lesion_analysis_service.py` | C | HAZ-005 |
| DD-LES-002 | Lesion Analysis — compute_dis_criteria | `lesion_analysis_service.py` | C | HAZ-008 |
| DD-LES-003 | DIS precondition — confirmed segmentation (draft 2026-10-24, PRB-003; Class C proposed, CAPA-016 PA-16.4) | `dis_review_gate.py` | C (proposed) | HAZ-008, HAZ-005, HAZ-003 |
| DD-CLS-001 | MAGNIMS Region Classifier (four paths; renamed v1.1, was "(EDT)") | `ms_region_classifier.py` | C | HAZ-005 |
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

**Purpose**: Generates structured clinical report drafts via Claude API from the device's measurements only. *(Amended 2026-10-24, CAPA-014 — draft, PENDING owner approval. The earlier purpose and safety lines, which said the generation was de-identified, are withdrawn: nothing de-identified then.)*

**Interface**:
```
Input:  template_type: str ("general"|"ms_activity"|"ms_lesion_burden"|"ms_comprehensive"|"ms_longitudinal")
        findings: Dict (only the structured payload of DD-RPT-002 reaches the prompt)
        volumetry: Optional[Dict]
        language: str ("en"|"es"|"de")
        identifiers: PatientIdentifiers (required; read by the route from the record of the patient of the
                     analysed segmentation — DD-RPT-002)
Output: Dict { report_id: str, content: str, template_type: str, language: str, processing_time_ms: int, model: str, tokens_used: Dict,
                unlisted_labels: Dict[placeholder, label as written] (for the draft only; the route removes it) }
```

**Pre-conditions**: ANTHROPIC_API_KEY configured. `identifiers` supplied (otherwise `PatientRecordUnavailable`, nothing sent).
**Post-conditions**: Report content is MAGNIMS-formatted clinical text with the RC-006 disclaimer. The provider received one of the fixed template variants (as written, or with its DIS and per-region instructions replaced when DIS was not evaluated — PRB-003; amended 2026-10-25, PENDING owner approval) and a prompt built from the structured payload only; the draft itself is model output and is not filtered. The route returns the parts of the draft as response fields (`draft_parts`): `disclaimer`; `clinician_entry` (heading, labelled fields exactly as typed, at most 5000 characters each, a cut flagged with its note); `ai_draft_heading`; `app_notes` (the names of unlisted labels); `ai_text` — the model's text without any Unicode format character, a line that is exactly one of the application's headings replaced by a fixed line, followed by the application's notices. `content` (`draft_text`) is the whole draft as one text for copy and export: fixed headings, the entry's fields and the notes quoted in plain fenced blocks. The report viewer renders the entry and the notes in components of their own, outside the Markdown renderer, and only `ai_text` as Markdown (CAPA-014 second and third reviews, final check).

**Algorithm**:
1. Validate template_type exists in REPORT_TEMPLATES; fallback to "general"
2. Refuse (`PatientRecordUnavailable`) when `identifiers` is missing — before any client exists (RC-065)
3. Construct system_prompt from REPORT_TEMPLATES[template_type] (fixed text, no patient data)
4. `provider_payload(findings, volumetry)` (DD-RPT-002, RC-064) → `_build_findings_prompt(payload…)`: language, the instruction that the clinician's text is added by the application (only when something was typed), age band, sex (M/F), measurements and fixed labels — no free text; `ImplausibleMeasurement` (nothing sent) when a number is outside the physical range of its field
5. `assert_prompt_carries_no_identifier(user_prompt, identifiers)` — detection only; `IdentifierInPrompt`, nothing sent (RC-065)
6. Log `privacy_check="passed"` and the withheld counts — never the payload (RC-066)
7. Initialize Anthropic client (lazy load); call `client.messages.create(model, max_tokens, system, messages)`; apply the RC-006 disclaimer; return report with metadata and token usage

**Error Handling**: RuntimeError if API key missing. `ProviderGuardError` raised before the client is created or called; the route maps it to 503 with a message naming no identifier. Generic Exception caught, logged, re-raised.

**Safety**:
- **Data sent to the provider** *(2026-10-24, CAPA-014 — draft)*: measurements, labels of the device's fixed vocabulary, sex and a 5-year age band — no free text, no names, dates of birth or record numbers (CAPA-014 §6).
- **Report includes mandatory disclaimer**: "AI-Generated — Requires Physician Review"
- Timeout: relies on httpx default timeout (configurable)

**Implements**: REQ-FUNC-060, REQ-FUNC-061, REQ-FUNC-063, REQ-SAFE-006, REQ-SAFE-007, REQ-SEC-007, REQ-SEC-021, REQ-SEC-022, REQ-SEC-023

---

### DD-RPT-002: Report Provider Payload and Check *(added 2026-10-24, CAPA-014 — draft, PENDING owner approval)*

**Purpose**: Builds the only payload the provider may receive (RC-064) and checks the final prompt before it leaves (RC-065, detection only). Called only by DD-RPT-001; part of the Class C report item.

**Interface**:
```
provider_payload(findings, volumetry, identifiers=None) -> ProviderPayload(findings, volumetry, withheld, unlisted)
    inputs not modified; withheld = {free_text_fields, unknown_fields, unlisted_labels, values_not_numbers: count};
    unlisted = {"[unlisted label N]": label as written} (for the draft only, never sent);
    raises ImplausibleMeasurement when a number is outside the physical range of its field, and IdentifierInPrompt
    when a whole number equals one of identifiers.number_forms() (record number, phone, birth date as digits)
PatientIdentifiers.from_record(record) -> PatientIdentifiers
    raises PatientRecordUnavailable when None or without mrn, given_name, family_name or birth_date
find_identifiers(text, identifiers, safe_words, safe_pairs) -> [category, ...]    # never edits the text
assert_no_identifiers(text, identifiers, safe_words, safe_pairs) -> None           # raises IdentifierInPrompt
age_band(value) -> "45-49" | "90 or older" | None
```

**Payload** (allow-list): lesion analysis, DIS assessment, longitudinal comparison, zone statistics, volumetry — numbers only where numbers are printed — a value that is not a number becomes `NOT_AVAILABLE` (prints "not available" whatever the format), a number outside its field's physical range raises `ImplausibleMeasurement` (counts < 100 000; voxel counts < 2^31; lesion volumes ≤ 2 500 000 mm³ / 2 500 mL; volumetry ≤ 3 000 mL; anomaly volume ≤ 3 000 000 mm³; centroid 0–4096; percentage and percentile 0–100; a slack of 10⁻⁶ of the bound for rounding) — except the burden change outside −100 % to 999 999 % (derived, no physical bound: `NOT_AVAILABLE`) and a confidence outside 0–1 (left out); a whole number equal to one of the patient's own numbers raises `IdentifierInPrompt`; labels only from `label_vocabulary()` (MAGNIMS_REGIONS, REGION_NAMES, STRUCTURE_NAMES, SYNTHSEG_LABELS, size classes, abnormality types, `APP_LABEL_NAMES` — the label names of the application's presets), other labels → "[unlisted label N]", one number per distinct label; sex M/F; 5-year age band ("90 or older" from 90); the flag `clinician_entry` when something was typed; the DIS block keeps an "evaluated" state as received (PR #68), and one not evaluated, in an unknown state or without a yes/no conclusion becomes `{"evaluation_status": "not_evaluated"}` only (printed "NOT EVALUATED", never "NOT MET"). Free-text fields and unknown fields are counted and left out.

**Check** (on the final user prompt, after NFKC, removal of format characters, look-alike and accent mapping, casefold): text over 400 000 characters refused; the patient's names, contact, city and street words as whole words or inside a longer word (≥ 4 letters) unless the word is one of the device's own (`fixed_prompt_words()`: words of the builder's output on synthetic payloads — what the user prompt can contain, not the system templates); given + family name next to each other or joined, unless the two words stand in that order in the device's own text (`fixed_prompt_pairs()`) or the joined word is one of the device's words; letter-and-digit record numbers with up to 3 separator characters between characters; all-digit record numbers, and the digits of a prefixed one (≥ 6 digits), as a whole number not part of a decimal number nor followed by a unit (under 6 digits excepted); birth date patterns (D M Y, M D Y, Y M D with numeric, month-name en/es/de and Roman months; D M or year after a birth word); phone digit strings (with/without country code and trunk 0, ≥ 7 digits) inside any digit run; record e-mail; generic e-mail, dated text, "+" phone, ≥ 9-digit or grouped numbers, ID-like tokens (≥ 5 digits with letters, not a number with a unit), titled names. All patterns are bounded or anchored (linear time).

**Safety**: never edits the text, so it cannot alter clinical wording; it can only refuse to send. Known limits (CAPA-014 §8): a name that is also one of the device's words is found only next to the other name; all-digit record numbers under 6 digits are not checked (they cannot be told from measurements); a name made of two device words in the device's order ("Deep White") is not found; a whole number equal to an all-digit record number refuses (it cannot be told from it); further forms are listed in CAPA-014 §8 item 2.

**Implements**: REQ-SEC-021, REQ-SEC-022 (RC-064, RC-065)

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

**Precondition (2026-10-24, PRB-003, DRAFT)**: called only after DD-LES-003 has found a radiologist's confirmation bound to the current mask (`segmentation_analysis.assess_dis`, `segmentation_regions.classify_regions`). The unit itself is unchanged.

---

### DD-LES-003: DIS precondition — classified, confirmed segmentation (draft, PRB-003; corrected after the review of PR #68)

**Purpose**: Decide whether dissemination in space may be evaluated for a stored segmentation (RC-070), and produce the
explicit "not evaluated" state otherwise. Paper A: the DD-LES-002 rule applied to raw automatic FLAMeS segmentations was
met in 19 of 100 healthy controls. Review of PR #68: DD-LES-002 reads label ids 1/2/3 as PV/JC/IT whatever they mean, so a
confirmation of the mask alone was not enough.

**Interface** (`backend/app/services/dis_review_gate.py`):
```
footprint_sha256(mask) -> SHA-256 of (mask > 0)        labels_sha256(labels) -> SHA-256 of sorted (id, name), id > 0
labels_are_magnims(labels) -> ids 1-4 = PV, JC, IT, DWM names; every other id a MAGNIMS label
regions_state(metadata, mask) -> {classified, label_scheme, edited_after_classification, method, lesion_count,
                                   lesions_valid, invalid_lesions, corrections, correction_count, corrections_sha256}
classification_record(classified_mask, voxel_spacing) -> footprint + mask digests + classified_lesion_regions
                          [[first voxel, voxels, region]] + voxel_volume_mm3
_table_entries(mask, voxel_volume) -> the lesion table's entries (as analyze_lesions: per-label components, size order,
                          table number, slice of the row; below the floor: small component)   (third review, m-1)
review_state(metadata, mask) -> {confirmed, status, reason, source, lesion_detection, regions, reviewed_by, reviewed_at,
                                 reviewed_mask_sha256, current_mask_sha256, current_labels_sha256}
not_evaluated(segmentation_id, state, reason=None) / evaluated(result, state) / is_evaluated(block)
region_status(state) / without_stored_dis(metadata) / without_region_breakdown(lesion_analysis)
scrub_unevaluated_dis(text, language) -> (text, statements replaced or removed)   (per sentence; backstop)
dis_for_viewer(block, user) / metadata_for_viewer(metadata, user) / without_reviewer_identity(block) / capped_history(events)
```

**Algorithm**:
```
classified  = labels_are_magnims AND unique(mask) within the label ids AND
              analysis_data.classification.classified_lesion_footprint_sha256 == footprint_sha256(mask)
ai_ok       = no AI provenance OR (review_status == 'confirmed' AND reviewed_mask_sha256 == sha256(mask))
lesions     = 18-connected components of (mask > 0), in raster order of their first voxel (RC-030)
classified  = ... AND classification.classified_lesion_regions describes exactly these lesions
valid       = every lesion carries exactly one label, in 1-4                           (second review, N1)
corrections = lesions whose label differs from their classified region (digest over all of them)
bound       = clinician_review.reviewed_mask_sha256 == sha256(mask) AND .reviewed_labels_sha256 == labels_sha256(labels)
              AND (.reviewed_region_corrections_sha256 or digest([])) == digest(corrections)
confirmed   = classified AND valid AND ai_ok AND bound
reason      = regions_not_classified | lesion_labels_invalid | ai_review_missing | confirmation_outdated |
              segmentation_not_confirmed
```

**Safety**: the "not evaluated" state carries no `dis_met*`, `region_details`, `brain_regions_with_lesions`,
`total_topographies_involved` or `dit_waiver_supported`. The classification is bound to the lesions (footprint), so a
radiologist may correct a region label; the confirmation is bound to the mask and labels, so the correction is covered and
any later change voids it (with a history entry). The confirmation is set only by `POST /segmentation/{id}/review/confirm`
(radiologist; after the classification; idempotent; metadata-only write via `SegmentationService.persist_metadata`).
*Second review of PR #68 (at 29abe29):* a region changed by hand is a correction the radiologist acknowledges (the digest
of the listed corrections, recorded in the confirmation); `persist_metadata` writes only `clinician_review` and
`clinician_review_history` (field update, stored history merged, update-time precondition → 409); the confirmer's name,
id and the history are returned to radiologists and administrators only; the report's lesion table is derived on the
server (`segmentation_analysis.lesion_table`). *Third review (m-1):* every list names a lesion by the lesion table's
number and the slice its row opens; components below the lesion-size floor are "small components"; a lesion with two
labels is listed part by part.

**Implements**: REQ-SAFE-038, REQ-SAFE-039 (RC-070, RC-071); tests UT-PRB003, UT-PRB003-R1, UT-PRB003-R2, UI-PRB003,
UI-PRB003-R1, UI-PRB003-R2

---

### DD-CLS-001: MAGNIMS Region Classifier

**Purpose**: Classifies MS lesions into MAGNIMS anatomical regions by the MAGNIMS contact criterion (MAGNIMS / McDonald 2024; Filippi et al. 2019): periventricular (PV) = abutting the lateral ventricles; juxtacortical (JC) = abutting the cortex; infratentorial (IT) = in or touching the brainstem or cerebellum; otherwise deep white matter (DWM). Priority when several apply: IT > PV > JC > DWM. Only PV, JC and IT count towards brain DIS; the spinal cord and optic nerve are not evaluated. The unit provides four classification paths; the route `POST /segmentation/{id}/classify-regions` (`backend/app/api/routes/segmentation_regions.py`) selects between them.

**Path selection** (`method`, default `"auto"`; the path actually used is returned in `method`). In `auto`, the first path that produces a result is used, in this order:

| Order | `method` | Function | Used when | "Abutting" implemented as |
|-------|----------|----------|-----------|---------------------------|
| 1 | `lst-ai` | route (inline) | Another segmentation of the same file has a `validation_source` containing `lst-ai`. The LST-AI integration is disabled by default. | Voxel-wise copy: each lesion voxel takes the LST-AI zone value at that voxel, and lesion voxels in no zone get DWM. There is no per-lesion contact rule, no IT > PV > JC priority and no minimum volume, so one lesion can receive several regions |
| 2 | `parcellation` | `classify_lesions_with_parcellation` | An explicit `parcellation_id` of the same image (`metadata.file_id`) and grid that passes `looks_like_freesurfer_parcellation` (otherwise HTTP 422, also in `auto`). Or, without `parcellation_id`, another segmentation of the same file, on the lesion mask's grid, that passes it (auto-detection, below). The SynthSeg integration is disabled in the current configuration. | Minimum EDT distance from the lesion to the ventricle / cortex / infratentorial labels <= 1.5 mm (algorithm below) |
| 3 | `msmask` | `classify_lesions_with_atlas` (zone map generated fresh in every call) | The source image, as loaded with its header, passes the MNI grid gate (`looks_mni`, below). On an MNI-grid image this path is used unless an LST-AI segmentation or a parcellation of the image exists (the LST-AI and SynthSeg integrations are disabled by default). A persisted zone map is never reused for classification. | Any lesion voxel in an atlas zone. The zones are the MSMask ventricle / cortex / infratentorial masks dilated by one voxel (3x3x3 cube; adapted from LST-AI, which dilates the lesion instead), within atlas white matter, plus the infratentorial label itself |
| 4 | `geometric` | `classify_lesions_geometric` | None of the paths above produced a result, and `prepare_geometric_image` accepts the source image (below). Accuracy not measured. | Coordinate heuristics, not anatomical landmarks: centroid in the lowest 25 % of the brain's extent along array axis 0, which `prepare_geometric_image` requires to be the slice axis pointing superior = IT; mean distance from the brain centre < 35 % of the maximum = PV; minimum distance to the brain surface < min(8 mm, 15 % of the brain radius) = JC |

With an explicit `method`, a path that cannot run is an error rather than a fall-through:
- `lst-ai` without an LST-AI segmentation: HTTP 400.
- `parcellation` with an unknown `parcellation_id`: HTTP 404. In `auto`, an unknown `parcellation_id` falls through to the next path.
- `parcellation` without a `parcellation_id` when no parcellation is auto-detected: HTTP 400 ("No classification method available").
- A `parcellation_id` of another image or grid, or one that is not a FreeSurfer parcellation: HTTP 422, with `parcellation` or `auto`.
- `parcellation` whose classification raises: HTTP 500.
- `msmask` on a non-MNI image: HTTP 422 (refusal). Atlas file or nilearn missing: HTTP 400. Any other failure: HTTP 500.
- `geometric` whose preconditions fail: HTTP 422 (refusal). A fault in the heuristics: HTTP 500.
- An unknown `method`: HTTP 400.

In `auto`, a **refusal** and a **fault** are kept apart (REQ-SAFE-021):
- The atlas path refused (`NotMNISpaceError`): the geometric path is tried, and the reason is returned as `atlas_unavailable_reason`.
- The atlas path faulted (atlas file missing, nilearn missing, any other exception): the geometric path is tried, and the fault is returned as `atlas_error` with the geometric result. It is not reported as a refusal.
- The geometric path refused (`GeometricPreconditionError`): its reason is kept.
- If no path produced a result and the atlas or geometric path **faulted**: HTTP 500 "Region classification failed", with the fault and any refusal reasons.
- If no path produced a result and every applicable path **refused**: HTTP 422 "No region-classification method can be applied validly to this image", followed by the reasons.
- A non-FreeSurfer or foreign `parcellation_id` does not fall through; it gets HTTP 422.
- An exception inside the parcellation path is logged and the next path is tried. It is not returned in the response (unlike `atlas_error`); the auto-detection loop likewise skips a candidate whose check raises.

Either route: source-image geometry that cannot be read (`VoxelSpacingUnavailableError`) gives HTTP 422; any other unhandled exception gives HTTP 500.

**Authorization (HAZ-010, RC-029; CAPA-006 finding 10)**: `classify-regions` depends on `require_segmentation_access` and `generate-zone-map` calls `authorize_file_scope` for the requested `file_id` before anything else. A caller who may not access the patient of the image gets HTTP 404 (REQ-SEC-014/015). Both routes were split out of `segmentation.py` by the C3 decomposition (2026-07-10) after RC-029 had been wired there, and had authentication only until 2026-09-28. Verified by `test_rc032_classify_route_enforces_object_level_access` and `test_rc032_zone_map_route_enforces_image_access`.

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
- `looks_mni`: `MNI_ISOTROPY_TOLERANCE = 1.05` (max/min voxel size); axis alignment |Rn[c,c]| >= 0.999 (about 2.5°); `MNI_REFERENCE_FOV_MM = (181, 217, 181)`; `MNI_FOV_TOLERANCE = 0.25` (per axis); `MNI_REFERENCE_CENTRE_MM = (0, -18, 18)`; `MNI_CENTRE_TOLERANCE_MM = 10.0`. The longitudinal compare route's former private `_looks_mni` (commit f208149, 2026-08-22) used |cos| >= 0.999 in any permutation and sorted extents within 25 % of the MNI152 box, with no isotropy, centre or header condition; it is replaced by this gate (below)
- `FREESURFER_REQUIRED_LABELS = {2, 3, 4, 16, 41, 42, 43}`; `MIN_PARCELLATION_FOREGROUND_ML = 500.0`; `ZONE_MAP_DESCRIPTION = "MAGNIMS Zone Map"`
- `GEOMETRIC_MAX_SLICE_TILT_DEG = 30.0`

**Algorithm (path 3, MSMask atlas, `generate_zone_map_atlas` + `classify_lesions_with_atlas`)**:
```
// generate_zone_map_atlas(target_img, voxel_spacing)
IF NOT looks_mni(target_img.affine, target_img.shape):
    RAISE NotMNISpaceError                      // HAZ-005 / RC-032: fail closed, before the atlas is loaded
atlas = MSMask (MNI152 space)
S = ones(3,3,3)                                 // one-voxel dilation of the atlas structures, adapted from
                                                // LST-AI (LST-AI dilates the lesion instead)
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
zone_stats[z].volume_mm3 = count(zone == z) * prod(|voxel_spacing|)  // image voxel volume (RC-024); assumed
                                                // 1 mm^3 before 2026-09-28, understating a 2 mm grid 8x
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

The `classify-regions` route always calls `classify_lesions_with_atlas`, so the zone map used for classification is generated fresh in every call. **A persisted zone map is never reused for classification** (CAPA-006). The zone map written by `generate-zone-map` came back transposed ((k, a1, a0)) after a GCS reload, because that route overwrote the blob without the RC-031 orientation marker. On MNI grids this raised an IndexError, which `auto` swallowed into a silent geometric fallback; on grids with a square in-plane matrix the zones were silently transposed. The overwrite has been removed (below). Before 2026-09-28 the route reused the zone map linked in `zone_map_seg_id` whenever one existed; that reuse path no longer exists.

**MNI grid gate (HAZ-005, RC-032, CAPA-006)**: the MSMask atlas is in MNI152 space and the software performs no registration, so the atlas is only valid on images that are already in MNI152 space.
- `looks_mni(affine, shape, header=None)` returns True only if every one of these holds:
  1. Isotropic voxels: max/min voxel size <= 1.05.
  2. Axis-aligned and not permuted: for each voxel axis c, |Rn[c,c]| >= 0.999 (within about 2.5°), where Rn is the direction-cosine matrix.
  3. Field of view |R[c,c]|·(shape[c] − 1) within 25 % of (181, 217, 181) mm on each world axis. Extents are not sorted.
  4. Grid centre within 10 mm of the MNI152 template centre (0, -18, 18).
  5. If a header is given, a spatial transform is set (sform or qform code != 0).

  Any exception returns False (fail closed). The longitudinal route's former private gate (below) compared sorted extents, accepted axis alignment in any permutation and had no isotropy, centre or header condition; it accepted native 2D FLAIR, e.g. 240x240x48 at 0.94x0.94x3 mm (CAPA-006 review, 2026-09-28).

  Conditions 2 and 3 overlap for permuted axes: a permuted affine has near-zero diagonal terms, so its per-axis field of view also fails. Condition 2 alone rejects an oblique grid (more than about 2.5°). Condition 3 is also tested on its own, on an isotropic, axis-aligned grid centred like MNI (`test_rc032_rejects_a_centred_isotropic_native_scan_by_field_of_view`).
- `generate_zone_map_atlas` raises `NotMNISpaceError` (a `ValueError` subclass) when `looks_mni(affine, shape)` is False.
- `classify-regions` route: loads the original source image and checks it with `looks_mni(affine, shape, header)` before calling `classify_lesions_with_atlas`. With `method="msmask"` the request is refused with HTTP 422. With `method="auto"` the route falls through to the geometric path and returns `atlas_unavailable_reason`. `LesionDashboard` then shows the amber alert `classify.atlasUnavailable` ("Atlas regions not used: this image is not in MNI space, so the geometric fallback (coordinate rules, not anatomical landmarks) was applied. Verify every region before using it for DIS."). When the response carries `atlas_error` (an atlas fault in `auto`), it shows the amber alert `classify.atlasError` ("Atlas regions could not be computed (internal error), so the geometric fallback was applied. Verify every region before using it for DIS."). Whenever the method is `geometric` and neither `atlas_unavailable_reason` nor `atlas_error` is set, it shows the amber warning `classify.geometricWarning` ("Geometric heuristics: coordinate rules, not anatomical landmarks; their accuracy has not been measured. Verify every region before using it for DIS.").
- `generate-zone-map` route: see "Zone-map generation" below. The route returns HTTP 422 and generates or persists nothing for a non-MNI image.
- Longitudinal compare route (`segmentation_analysis.py`, MAGNIMS region stratification of new lesions): imports the classifier's `looks_mni` as `_looks_mni`, so one gate decides wherever the atlas is applied (REQ-SAFE-021 (a)). From commit f208149 (2026-08-22) until 2026-09-28 this route had its own weaker `_looks_mni` (sorted extents, no isotropy, centre or header condition), deployed in production, deciding whether new lesions were stratified by region with the MSMask atlas. The route calls the gate with the affine and shape only, so condition 5 (header transform) is not checked there. Verified by `test_rc032_longitudinal_route_uses_the_same_gate`.
- Limitations (the gate checks only the grid; it is not a registration check):
  - It cannot certify that an image is truly normalised. An image resampled onto an MNI grid without being registered to it, an imperfectly normalised image, or a well-behaved native 3D isotropic axial scan whose field of view and position happen to be MNI-like (e.g. a 1 mm 3D T1 or FLAIR positioned near the scanner isocentre) can pass.
  - Conversely, images normalised with SPM12's default "Normalise: Write" bounding box ([-78 -112 -70; 78 76 85]) are refused: their grid centre, (0, -18, 7.5) mm, is about 10.5 mm from (0, -18, 18). This is fail-safe: the atlas is not used, and in `auto` the geometric fallback runs with its warning.
- Rationale for the gate: in a controlled experiment without registration (30 MNI-registered MSLesSeg scans with expert lesions, 2026-09-28; `scripts/safety/haz005_atlas_misregistration_probe.py`, run 2, which uses the product's region rule), moving the anatomy inside the MNI grid by a random amount **up to** 3° / 3 % / 5 mm changed the region of 216 of 786 expert lesions (27.5 %); up to 8° / 7 % / 10 mm, 338 of 786 (43.0 %); up to 15° / 10 % / 20 mm, 433 of 785 (55.2 %). Brain DIS changed in 4, 1 and 3 of the 30 scans respectively.

**Atlas path orientation (`classify_lesions_with_atlas`)**: `generate_zone_map_atlas` returns the zone map in NIfTI-native (a0, a1, k) order, while lesion masks are internal (k, a0, a1). The function transposes the zone map with (2, 0, 1) and raises `ValueError` if the result does not have the lesion mask's shape. Before 2026-09-28 the transpose was missing: the path failed with a shape error on non-cubic volumes and would have applied rotated zones on cubic ones. The `generate-zone-map` route applies the same (2, 0, 1) transpose. `classify_from_zone_mask` itself also raises `ValueError` when the zone map's shape differs from the lesion mask's. Before this check a mismatch surfaced as an IndexError, which `auto` turned into a silent geometric fallback. A zone map of the same shape but transposed (square in-plane grid) cannot be detected there, so callers must supply the zone map in (k, a0, a1) order.

**Parcellation identity (`looks_like_freesurfer_parcellation(label_values, description=None, foreground_ml=None)`, RC-032, CAPA-006)**: returns True only if all of these hold:
1. the segmentation contains **every** label of `FREESURFER_REQUIRED_LABELS` = {2, 3, 4, 16, 41, 42, 43}: cerebral white matter, cortex and lateral ventricles in both hemispheres, and the brainstem;
2. its description is not "MAGNIMS Zone Map" (`ZONE_MAP_DESCRIPTION`);
3. when the caller passes the labelled volume, it is at least `MIN_PARCELLATION_FOREGROUND_ML` = 500 mL (a whole-brain parcellation covers about 1-1.6 L; a lesion mask covers a few mL). Both routes pass it, computed with the source image's voxel volume.

A MAGNIMS zone map (labels 1-4), a region-classified lesion mask (1-6), an instance-labelled lesion mask (1..N), and an aparc+aseg whose cortex labels (1000+/2000+) cannot be read as 3/42 all fail.

In addition, the route checks where the parcellation comes from:
- `classify-regions`: an explicit `parcellation_id` must belong to the same image (`metadata.file_id`) and have the lesion mask's shape, else HTTP 422 ("not a parcellation of this image"); this check comes before the label test. A parcellation of another image, e.g. another timepoint on the same protocol grid, would otherwise be used unregistered. An auto-detected candidate (a segmentation listed for the same file) must have the lesion mask's shape.
- `generate-zone-map`: an explicit `parcellation_id` must belong to the requested image (HTTP 422); auto-detection lists the segmentations of that image.

History: before 2026-09-28 the test was ">= 3 of {2, 3, 4, 7, 8, 10, 16, 41, 42, 43}". A MAGNIMS zone map (labels 1-4) passed it, and its label 4 (Deep White Matter) was read as the FreeSurfer lateral ventricle (label 4), so DWM lesions were reported as Periventricular. An instance-labelled lesion mask with 20 lesions also passed it, and so did a parcellation without cortex labels, on which JC could never be assigned. Verified by `test_rc032_parcellation_test_rejects_zone_maps_and_lesion_masks`, `test_rc032_instance_labelled_mask_is_not_read_as_a_parcellation`, `test_rc032_foreign_image_parcellation_is_refused` and `test_rc032_same_image_parcellation_is_used`.

**Geometric preconditions (`prepare_geometric_image(affine, native_image, lesion_shape)`, RC-032, CAPA-006)**: returns the source image in the lesion mask's (k, a0, a1) order. It raises `GeometricPreconditionError` (a `ValueError` subclass) when:
- the image cannot be read;
- the orientation is indeterminate (affine not 4x4, not finite, or singular);
- the slice axis (native axis k) is tilted more than `GEOMETRIC_MAX_SLICE_TILT_DEG` = 30° from the inferior-superior axis (`aff2axcodes` alone would accept up to 45°);
- the slice axis (native axis k) does not point Superior (`nib.aff2axcodes(affine)[2] != "S"`), as in sagittal, coronal or superior-to-inferior acquisitions;
- the image is not 3-D after trailing singleton dimensions are dropped (an (x, y, z, 1) image is accepted as (x, y, z));
- the reordered image does not match the lesion mask's shape;
- the image is blank.

`classify_lesions_geometric` raises `ValueError` when `image_data` does not match the lesion mask's shape. Before 2026-09-28 the route passed the image in native order, and the heuristics silently replaced it with the whole array as "brain" on every non-cubic volume (JC then meant "near the array corner"). The IT rule also ran on whatever axis 0 happened to be. The heuristics themselves are unchanged coordinate rules.

**Zone-map generation (`POST /segmentation/generate-zone-map`, RC-032, CAPA-006)**: zone maps are for display only; `classify-regions` never reads them (see above). The route runs in this order:
1. `file_id` is required (HTTP 400). The caller is authorized for the image's patient with `authorize_file_scope` before anything else (HTTP 404 on denial; RC-029).
2. Voxel spacing comes from the source image header (`_voxel_spacing_from_source_image`). The former fallback read the undefined names `metadata` / `segmentation_id` (NameError, HTTP 500).
3. Find and validate the parcellation. An explicit `parcellation_id` must exist (HTTP 404), belong to this image (HTTP 422) and pass `looks_like_freesurfer_parcellation` (HTTP 422). Without one, a segmentation of the file that passes the test is auto-detected.
4. Generate. With a parcellation: `generate_zone_map` (EDT, 1.5 mm). Without one: MSMask. The original loaded image, including its header, must pass `looks_mni` (else HTTP 422). A `NotMNISpaceError` from `generate_zone_map_atlas` also gives HTTP 422. The result is transposed (2, 0, 1) to (k, a0, a1).
5. An empty zone map gives HTTP 400.
6. Create the "MAGNIMS Zone Map" segmentation, write the mask (`set_mask`) and persist it through `persist()` only (MRI-native, RC-031 v2 marker). The former raw GCS overwrite, which dropped the marker, has been removed.
7. **Only then** delete the file's older "MAGNIMS Zone Map" segmentations, excluding the new one. A failure to delete one is logged. Before 2026-09-28 they were deleted first, which destroyed them on every refusal and left `zone_map_seg_id` dangling. Now a refusal, or a failure to create or persist the new zone map (HTTP 500), leaves the existing zone maps in place (`test_rc032_generate_zone_map_refuses_non_mni_and_keeps_existing_zone_maps`, `test_rc032_zone_map_replacement_is_atomic`).
8. Propagate `zone_map_seg_id` to the file's other segmentations.

Zone statistics (`zone_stats`) of the atlas zone map use the image voxel volume, the product of the voxel spacing (RC-024). Before 2026-09-28 `generate_zone_map_atlas` assumed 1 mm³, which understated a 2 mm MNI grid 8x (`test_rc032_zone_volumes_use_the_voxel_volume`). The parcellation zone map (`generate_zone_map`) already used the voxel spacing.

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
- `NotMNISpaceError` when the image grid is not MNI-like (a refusal): HTTP 422 for `method="msmask"` and for `generate-zone-map`; for `method="auto"`, the geometric path with `atlas_unavailable_reason`.
- An atlas fault (atlas file or nilearn missing, or any other exception in the atlas path): HTTP 400 (file / nilearn) or HTTP 500 for `method="msmask"`; for `method="auto"`, the geometric path with `atlas_error`. A fault is never reported as a refusal.
- `GeometricPreconditionError` when the geometric heuristics cannot be applied validly (a refusal): HTTP 422 for `method="geometric"`; in `auto` the reason is kept. A fault in the heuristics: HTTP 500.
- HTTP 422 for a `parcellation_id` of another image or grid, or one that is not a FreeSurfer parcellation.
- When no path produced a result: HTTP 500 if a path faulted; HTTP 422 "No region-classification method can be applied validly to this image" plus the reasons if every applicable path refused; HTTP 400 for an unknown `method` or when an explicitly requested path has nothing to run on (no LST-AI segmentation, no parcellation).
- HTTP 404 when the caller may not access the image's patient (RC-029).
- Empty result if no lesions found.

**Safety**: Each path is used only when its precondition holds (RC-032): the MNI-space atlas only on MNI-like grids; a parcellation only if it is a whole-brain FreeSurfer-label parcellation of the same image and grid; the geometric heuristics only on a readable, non-blank, axial inferior-to-superior 3-D image in the lesion mask's axis order, with the slice axis within 30° of inferior-superior. Otherwise the path is refused. A fault is reported as a fault (HTTP 500, or `atlas_error` with the geometric result in `auto`), never as a refusal and never silently. If no path remains, the request fails with the reasons. The atlas zone map is generated fresh, reoriented and shape-checked; a persisted zone map is never reused. The grid gate cannot certify true normalisation (see its limitations above). The 1.5 mm distance thresholds approximate LST-AI's one-voxel (3x3x3) dilation at 1 mm isotropic: face- and edge-adjacent voxels (1.0 and 1.41 mm) count as contact, corner-adjacent voxels (1.73 mm) do not. *(v1.0 text withdrawn in v1.1, CAPA-006: "EDT-based classification is more robust than pixel-adjacency methods" (no evidence); "Distance thresholds (1.5mm) match LST-AI dilation criteria" (inexact).)* The priority cascade makes the assignment deterministic. No per-lesion confidence is emitted (RC-010 (amended)). The accuracy of region assignment has NOT been measured against expert region labels on any path, so the HAZ-005 residual risk is UNDETERMINED (RMF-001).

**Implements**: REQ-FUNC-053, REQ-SAFE-010 (amended 2026-09-28), REQ-SAFE-011, REQ-SAFE-021 (RC-032, CAPA-006); the region routes also implement REQ-SEC-014/015 (RC-029)

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
| DD-RPT-001 | REQ-FUNC-060, 061, 063, REQ-SAFE-006, 007, REQ-SEC-007, REQ-SEC-021..023 (draft) | RC-006, RC-007, RC-064..RC-066 (draft) |
| DD-RPT-002 (draft) | REQ-SEC-021, REQ-SEC-022 | RC-064, RC-065 |
| DD-LES-001 | REQ-FUNC-050, 051 | RC-010 |
| DD-LES-002 | REQ-FUNC-052, REQ-SAFE-015 | RC-015 |
| DD-CLS-001 | REQ-FUNC-053, REQ-SAFE-010 (amended 2026-09-28), 011, 021, REQ-SEC-014/015 (region routes) | RC-010 (amended), RC-011, RC-032 (path preconditions: MNI grid gate, also on the longitudinal compare route; parcellation identity; geometric preconditions; refusal vs fault; CAPA-006), RC-029 (object-level authorization of classify-regions and generate-zone-map; CAPA-006) |
| DD-NII-001 | REQ-DATA-001 | RC-012 |
| DD-NII-002 | REQ-SAFE-012 | RC-012 |
| DD-EDGE-001/002/003 | REQ-FUNC-033, REQ-SAFE-008, 009 | RC-008, RC-009 |

---

*End of Detailed Design Specification*

*This document is maintained under configuration management in the Git repository at `docs/iec62304/06_Detailed_Design_Specification.md`.*
