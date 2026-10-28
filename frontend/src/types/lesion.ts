/**
 * Lesion analysis: DIS assessment, longitudinal tracking, MAGNIMS region classification, CVS/PRL.
 *
 * Split out of the former single types/index.ts barrel (Fase 2.1) — re-exported
 * from ./index.ts, so `@/types` consumers are unchanged.
 */

// ============================================================================
// Lesion Analysis + DIS Assessment Types
// ============================================================================

export interface LesionCentroid {
  z: number;
  y: number;
  x: number;
}

export interface LesionBoundingBox {
  z_min: number; z_max: number;
  y_min: number; y_max: number;
  x_min: number; x_max: number;
}

export type LesionSizeCategory = 'small' | 'medium' | 'large';

export interface LesionInfo {
  id: number;
  label_id: number;
  region: string;
  voxel_count: number;
  volume_mm3: number;
  volume_ml: number;
  size_category: LesionSizeCategory;
  centroid: LesionCentroid;
  bounding_box: LesionBoundingBox;
}

export interface RegionSummary {
  label_id: number;
  lesion_count: number;
  total_voxels: number;
  total_volume_mm3: number;
  total_volume_ml: number;
}

export interface LesionAnalysisResult {
  segmentation_id: string;
  lesions: LesionInfo[];
  total_count: number;
  total_burden_mm3: number;
  total_burden_ml: number;
  regions: Record<string, RegionSummary>;
  size_distribution: { small: number; medium: number; large: number };
  unique_labels: number[];
}

export interface DISRegionDetail {
  label_id: number;
  present: boolean;
  voxel_count: number;
  qualifying_lesion_count?: number;
}

/**
 * McDonald 2024 DIS assessment (Montalban et al., Lancet Neurology 2025).
 * Evaluates 3 brain MRI regions (PV, JC, IT) out of 5 total DIS regions
 * (spinal cord and optic nerve require separate imaging).
 */
export interface DISSupportiveMarkers {
  central_vein_sign: boolean | null;
  paramagnetic_rim_lesion: boolean | null;
  csf_specific: boolean | null; // OCB or elevated kappa FLC
}

/**
 * PRB-003 (RC-070): the confirmation a DIS state rests on. `source` says where the segmentation comes
 * from: an AI draft (reviewed through its own banner, RC-047), a server tool, or an origin that is not
 * recorded (drawn here or uploaded) — the last two are confirmed with `confirmSegmentationReview` (RC-071).
 */
export interface DISSegmentationReview {
  status: 'confirmed' | 'unconfirmed' | 'outdated';
  source: 'ai_draft' | 'automatic_tool' | 'origin_not_recorded';
  /** Shown to radiologists and administrators only; null for other roles (second review of PR #68, N5). */
  reviewed_by: string | null;
  reviewed_by_role?: string | null;
  reviewed_at: string | null;
  reviewed_mask_sha256: string | null;
  current_mask_sha256: string;
}

/**
 * PRB-003 (RC-070): DIS is evaluated only on a segmentation a radiologist confirmed for its current mask.
 * Otherwise the server returns this explicit state — no met / not met, no region presence.
 */
export interface DISNotEvaluated {
  segmentation_id: string | null;
  evaluation_status: 'not_evaluated';
  not_evaluated_reason: 'regions_not_classified' | 'lesion_labels_invalid' | 'ai_review_missing'
    | 'segmentation_not_confirmed' | 'confirmation_outdated' | 'segmentation_not_identified' | 'assessment_failed';
  message: string;
  reason_detail?: string;
  segmentation_review: DISSegmentationReview | null;
  dis_criteria_version: string;
  /** Information for safety on automatic lesion marking (RC-072), present for a lesion-detection tool's output. */
  information_for_safety?: string;
  regions?: DISRegionsState | null;
}

/** One label of a lesion, named as the lesion table names it (third review of PR #68, m-1): its table number, or a
 *  "small component" below the lesion-size floor, which the table leaves out. */
export interface DISLesionPart {
  lesion: number | null;
  small_component: boolean;
  label: number;
  label_name: string;
  voxels: number;
  /** 0-based slice the viewer opens for the table row (rounded centroid); the viewer shows slice + 1. */
  slice: number;
}

/** A lesion that carries no MAGNIMS region or more than one (second review of PR #68, N1). */
export interface DISInvalidLesion {
  /** The table number of its largest part (third review, m-1); null for a small component. */
  lesion: number | null;
  small_component?: boolean;
  /** 0-based slice of its largest part, as the lesion table (the viewer shows slice + 1). */
  slice: number;
  first_voxel: [number, number, number];
  voxels: number;
  labels: number[];
  label_names: string[];
  /** Its labels part by part, in table order (third review, m-1). */
  parts?: DISLesionPart[];
}

/** A lesion whose region differs from the classifier's: a correction by hand (second review of PR #68, N1). */
export interface DISRegionCorrection {
  /** The lesion table's number (third review of PR #68, m-1); null for a small component. */
  lesion: number | null;
  small_component?: boolean;
  slice: number;
  first_voxel: [number, number, number];
  voxels: number;
  classified_region: number;
  classified_region_name: string;
  current_region: number;
  current_region_name: string;
}

/** Review of PR #68: whether the labels are MAGNIMS regions assigned by the classification to these lesions —
 *  one region per lesion — and which regions were changed by hand since (second review, N1). */
export interface DISRegionsState {
  classified: boolean;
  label_scheme: 'magnims' | 'other';
  edited_after_classification?: boolean | null;
  method?: string | null;
  lesion_count?: number | null;
  lesions_valid?: boolean | null;
  invalid_lesions?: DISInvalidLesion[];
  invalid_lesion_count?: number;
  corrections?: DISRegionCorrection[];
  correction_count?: number;
  /** Digest the radiologist sends to acknowledge exactly these corrections in the confirmation. */
  corrections_sha256?: string | null;
  listed_limit?: number;
}

/** A DIS state from the server: evaluated (on a confirmed segmentation) or explicitly not evaluated. */
export type DISAssessment = DISEvaluated | DISNotEvaluated;

/** True only for a result the server evaluated on a confirmed segmentation; anything else is not shown as DIS. */
export function isDisEvaluated(d: unknown): d is DISEvaluated {
  return !!d && typeof d === 'object' && (d as { evaluation_status?: unknown }).evaluation_status === 'evaluated';
}

export interface DISEvaluated {
  evaluation_status: 'evaluated';
  segmentation_review: DISSegmentationReview;
  regions?: DISRegionsState;
  segmentation_id: string;
  dis_met_brain: boolean;
  dis_criteria_version: string;
  brain_regions_with_lesions: number;
  total_dis_regions: number;         // 5 (McDonald 2024)
  brain_regions_evaluated: number;   // 3
  spinal_cord_evaluated: boolean;
  optic_nerve_evaluated: boolean;
  spinal_cord_involved?: boolean | null;
  optic_nerve_involved?: boolean | null;
  // McDonald 2024 five-topography integration (folds in external evidence).
  total_topographies_involved: number;
  dis_met_full: boolean;
  /** ≥4 of 5 topographies → dissemination in time may be waived (2024). */
  dit_waiver_supported: boolean;
  supportive_specificity_markers: DISSupportiveMarkers;
  specificity_marker_present: boolean;
  external_evidence_provided: boolean;
  decision_support_note: string;
  note: string;
  region_details: Record<string, DISRegionDetail>;
  dwm_lesion_count: number;
  dwm_voxels: number;
  has_active_lesions: boolean;
  has_black_holes: boolean;
  active_voxels: number;
  black_hole_voxels: number;
  // Legacy fields for backwards compatibility
  dis_met?: boolean;
  regions_with_lesions?: number;
}

/** Optional McDonald-2024 external evidence supplied to the DIS endpoint. */
export interface DISExternalEvidence {
  spinal_cord_involved?: boolean;
  optic_nerve_involved?: boolean;
  cvs_positive?: boolean;
  prl_present?: boolean;
  csf_specific?: boolean;
}

// ============================================================================
// Longitudinal Tracking Types
// ============================================================================

export type LesionChangeStatus = 'new' | 'resolved' | 'enlarged' | 'shrunk' | 'stable';

export interface LesionChange {
  centroid_z: number;
  centroid_y: number;
  centroid_x: number;
  volume_tp1_mm3: number;
  volume_tp2_mm3: number;
  volume_tp1_ml: number;
  volume_tp2_ml: number;
  change_mm3: number;
  change_percent: number;
  status: LesionChangeStatus;
  iou: number;
  /** For status==='new': false when the lesion is below the MAGNIMS ~3 mm-diameter
   *  size gate (reported but not counted as a change candidate). */
  clinically_significant?: boolean;
  /** CAPA-013 (RC-060): key of a reviewable candidate (new >= 3 mm or enlarged) for the masks
   *  compared — what a radiologist's decision is recorded against. */
  candidate_key?: string;
  /** CAPA-013 (RC-060): the radiologist's decision on this candidate, if any, for these masks. */
  reader_review?: LongitudinalReaderReview;
  /** MAGNIMS region id (1=PV, 2=JC, 3=IT, 4=DWM) from the MSMask atlas, or null when
   *  no zone map was available (off-MNI input / atlas failure). Candidate-quality. */
  region_id?: number | null;
  /** Human-readable MAGNIMS region name (Periventricular / Juxtacortical /
   *  Infratentorial / Deep White Matter), or null. */
  region_name?: string | null;
  /** Advisory FLAIR-subtraction confirmation for status==='new' candidates: mean
   *  normalized subtraction signal (SD units) within the lesion. Positive = brighter
   *  at follow-up (supports a true new lesion). null when unavailable. */
  subtraction_signal?: number | null;
  /** True when the new candidate is brighter at follow-up on the FLAIR subtraction (signal at or
   *  above the advisory bar). A SIGNAL, never a confirmation: in paper C (PR #60) candidates
   *  passing this check were still false in 19 of 20 patients (CAPA-013, RC-061). null/absent for
   *  non-new changes or when subtraction was unavailable/withheld. NEVER a diagnostic verdict. */
  subtraction_confirmed?: boolean | null;
  /** Why the subtraction verdict is what it is: 'assessed' | 'border' | 'unmatched' |
   *  'outside-domain' | 'no-centroid'. 'border' = at brain/FOV edge → verdict withheld. */
  subtraction_note?: string;
}

/** A single Slowly-Expanding Lesion candidate (Jacobian expanding-fraction). */
export interface SELCandidate {
  centroid_z: number;
  centroid_y: number;
  centroid_x: number;
  /** Baseline (TP1) lesion volume in mm³. */
  baseline_volume_mm3: number;
  /** Fraction of lesion voxels locally expanding (per-voxel Jacobian ≥ floor). */
  expanding_fraction: number;
  /** Mean Jacobian within the lesion (context only; >1 = expansion). */
  mean_jacobian: number;
}

/** Result of SEL (slowly-expanding lesion) candidate detection. */
export interface SELResult {
  ok: boolean;
  reason: string;
  sels: SELCandidate[];
  /** Number of pre-existing lesions examined. */
  n_existing: number;
  /** Number flagged as SEL candidates. */
  n_sel: number;
  /** Per-subject registration-noise floor (expanding fraction of normal tissue). */
  background_expanding_fraction?: number;
  voxel_expansion_floor?: number;
  registration_verified?: boolean;
  adjudication_required?: boolean;
  method?: string;
  caveat?: string;
}

export interface LongitudinalReaderReview {
  decision: 'confirmed' | 'rejected';
  reviewed_by: string | null;
  reviewed_at: string | null;
}

export interface LongitudinalCandidateSummary {
  new: number;
  enlarging: number;
  total: number;
  confirmed: number;
  rejected: number;
  awaiting_review: number;
  /** True when decisions existed for other (since changed) masks and were not applied. */
  earlier_decisions_voided?: boolean;
  /** True when the stored decisions could not be read: the counts above are null, nothing may be
   *  shown as "awaiting review" and no decision may be recorded (review of PR #63). */
  decisions_unavailable?: boolean;
}

export interface LongitudinalVisitCheck {
  status: 'ok' | 'same_visit' | 'wrong_order' | 'unknown';
  tp1_study_date?: string | null;
  tp2_study_date?: string | null;
}

export interface LongitudinalReaderConfirmed {
  rule: string;
  confirmed_new: number;
  confirmed_enlarging: number;
  confirmed_by: string[];
  first_confirmed_at: string;
  last_confirmed_at: string;
}

export type LongitudinalAcquisitionField =
  | 'manufacturer' | 'manufacturer_model_name' | 'magnetic_field_strength_t' | 'mr_acquisition_type'
  | 'slice_thickness_mm' | 'voxel_spacing_mm' | 'repetition_time_ms' | 'echo_time_ms'
  | 'inversion_time_ms' | 'spacing_between_slices_mm';

export interface LongitudinalAcquisitionCheck {
  status: 'same' | 'differs' | 'not_established';
  comparable?: boolean;
  required_fields: LongitudinalAcquisitionField[];
  fields_compared: LongitudinalAcquisitionField[];
  differing: { field: LongitudinalAcquisitionField; tp1: unknown; tp2: unknown }[];
  missing: { field: LongitudinalAcquisitionField; timepoints: ('tp1' | 'tp2')[] }[];
  source?: string;
}

export interface LongitudinalFalseCandidateEvidence {
  asset: string;
  version: string;
  measured_on: string;
  dataset: string;
  segmenter: string;
  patients: number;
  stable_patients: number;
  patients_with_false_candidate: number;
  false_candidates_per_patient: number;
  false_candidates_per_patient_ci95: [number, number] | number[];
  after_subtraction_per_patient: number;
  after_subtraction_per_patient_ci95?: [number, number] | number[];
  /** False candidates and all candidates in the source record, and their ratio (review of PR #63). */
  false_candidates?: number;
  all_candidates?: number;
  false_share_of_candidates?: number;
  source: string;
  source_record?: string;
  source_commit?: string;
}

export interface LongitudinalResult {
  changes: LesionChange[];
  /** null when the comparison abstained (RC-062): no quantity of either visit is compared. */
  total_lesions_tp1: number | null;
  total_lesions_tp2: number | null;
  burden_tp1_mm3: number | null;
  burden_tp2_mm3: number | null;
  burden_tp1_ml: number | null;
  burden_tp2_ml: number | null;
  /** null when the comparison abstained (RC-062). */
  burden_delta_mm3: number | null;
  burden_delta_percent: number | null;
  /** null when the comparison abstained (RC-062). */
  status_counts: Record<LesionChangeStatus, number> | null;
  /** The ~3 mm-diameter minimum for a new candidate to be counted. */
  new_lesion_min_diameter_mm?: number;
  // ── CAPA-013 (RC-060/061/062, HAZ-007). The former activity_candidate / dit_candidate flags
  //    and the "clinically significant" count names are no longer sent: unconfirmed candidates
  //    are never an activity or dissemination-in-time statement. ──
  /** Unconfirmed change candidates (new >= 3 mm, enlarged) and the reader decisions on them.
   *  null when the comparison abstained. */
  change_candidates?: LongitudinalCandidateSummary | null;
  /** Present ONLY when a radiologist confirmed at least one candidate for the masks compared:
   *  MAGNIMS 2021 (>= 1 new or enlarging T2 lesion) applied to the confirmed candidates. */
  reader_confirmed_activity?: LongitudinalReaderConfirmed;
  /** SHA-256 of both stored masks; a decision is recorded against it. null = no decision possible. */
  review_binding?: { tp1_mask_sha256: string; tp2_mask_sha256: string } | null;
  /** RC-062: true when the acquisition of the two visits differs or could not be established. */
  abstained?: boolean;
  acquisition_check?: LongitudinalAcquisitionCheck;
  /** Visit 2 later than visit 1 and a different visit; "unknown" makes the comparison abstain. */
  visit_check?: LongitudinalVisitCheck;
  /** RC-061: the measured false-candidate rate (versioned asset), or null when not available. */
  false_candidate_evidence?: LongitudinalFalseCandidateEvidence | null;
  /** MAGNIMS region stratification (MSMask atlas) of new + enlarging candidates by
   *  McDonald region. null when no zone map was available (off-MNI / atlas failure). */
  region_stratification?: Record<string, { new: number; enlarging: number }> | null;
  /** Candidate/atlas-quality caveat for region_stratification (present only when
   *  regions were computed): atlas-based, MNI-assumed, not lesion-scale certified. */
  region_atlas_note?: string;
  // ── Class C safety framing (the compare performs NO spatial registration) ──
  // The backend always sends these; the UI must gate any "change/new-lesion" wording on
  // them so a candidate is never presented as a verified finding (over-diagnosis hazard).
  /** True only if TP2 was spatially co-registered to TP1. Currently ALWAYS false — equal
   *  array dimensions are not voxel alignment. Do not assert change without this. */
  registration_verified?: boolean;
  /** True when a radiologist must adjudicate each candidate before it informs a diagnosis. */
  adjudication_required?: boolean;
  /** False when voxel spacing could not be resolved and fell back to (1,1,1) → volumes/mL are approximate. */
  spacing_resolved?: boolean;
  /** Human-readable alignment status, e.g. "equal array shape; NOT verified as spatially co-registered". */
  alignment?: string;
  /** The authoritative caveat string from the backend — prefer it over any hardcoded copy. */
  caveat?: string;
  /** True when TP2 was rigidly co-registered to TP1 before comparison (advisory, removes
   *  head-pose misregistration false positives). Distinct from registration_verified,
   *  which certifies lesion-scale alignment and is ALWAYS false. */
  registration_applied?: boolean;
  /** Why registration was or was not applied (e.g. "rigid registration converged" /
   *  "source intensities unavailable ..."). */
  registration_reason?: string;
  /** Advisory-only registration QC (brain-overlap Dice, rotation °, translation mm). NOT a
   *  lesion-scale certification. */
  registration_advisory_qc?: {
    brain_overlap_dice?: number;
    rotation_deg?: number;
    translation_mm?: number;
    [k: string]: unknown;
  };
  /** True when FLAIR subtraction confirmation ran on the co-registered intensities. */
  subtraction_available?: boolean;
  /** How many of the NEW candidates the subtraction map confirmed as genuinely brighter
   *  at follow-up (advisory false-positive filter). */
  subtraction_summary?: {
    new_total: number;
    new_subtraction_confirmed: number;
    new_withheld?: number;
    min_signal_sd: number;
  };
  /** Base64 uint8 diverging heatmap of the FLAIR subtraction (co-registered TP1 grid,
   *  internal (k,a0,a1)): 128=no change, >128=brighter at follow-up (new signal),
   *  <128=darker. For the visual subtraction overlay. Omitted when too large. */
  subtraction_volume_b64?: string;
  /** Shape [depth,height,width] of the subtraction heatmap volume. */
  subtraction_shape?: [number, number, number];
  /** The ±SD clip used to build the heatmap (for the legend). */
  subtraction_clip_sd?: number;
  /** True when the inline heatmap volume was omitted for size (confirmation flags still ship). */
  subtraction_volume_omitted?: boolean;
}

// ============================================================================
// Region Classification Types (MAGNIMS / SynthSeg + EDT)
// ============================================================================

export type ClassificationMethod = 'auto' | 'parcellation' | 'msmask' | 'geometric';

export interface LesionDistances {
  to_ventricle: number;
  to_cortex: number;
  to_infratentorial: number;
}

export interface ClassifiedLesion {
  lesion_id: number;
  region_id: number;
  region: string;
  /** Always null (HAZ-005 / REQ-SAFE-010 amended): region assignment is a deterministic MAGNIMS
   *  rule with no calibrated per-lesion probability. Never render a "confidence" for it. */
  confidence: number | null;
  confidence_note?: string;
  /** MSMask path only: fraction of lesion voxels inside the assigned zone (descriptive). */
  region_overlap_fraction?: number | null;
  /** MSMask path only: fraction of lesion voxels inside ANY white-matter zone. */
  zone_coverage_fraction?: number | null;
  /** MSMask path only: false when no lesion voxel lies in any white-matter zone — Deep White
   *  Matter was then assigned by DEFAULT, not by the MAGNIMS rule (possible DIS false negative). */
  atlas_coverage?: boolean;
  volume_mm3: number;
  volume_ml: number;
  voxel_count: number;
  centroid: LesionCentroid;
  distances_mm: LesionDistances;
}

export interface RegionClassificationResult {
  segmentation_id: string;
  method: 'parcellation' | 'geometric' | 'msmask' | 'lst-ai';
  /** RC-032: set when the MNI-space MSMask atlas was NOT applied because the image is not in
   *  MNI space (the geometric fallback was used instead). */
  atlas_unavailable_reason?: string;
  /** RC-032 (CAPA-006 review): the atlas path FAILED (a fault, not a refusal); the geometric
   *  fallback was applied. */
  atlas_error?: string;
  lesions: ClassifiedLesion[];
  total_classified: number;
  classification_summary: Record<string, number>;
  thresholds_mm: Record<string, number | string>;
  processing_time_ms: number;
  mask_updated: boolean;
  labels_updated: boolean;
  /** The label scheme the server stored with the classified mask (release 2026-10-25, capture finding F08). */
  labels?: Array<{ id: number; name: string; color: string; opacity: number; visible: boolean }>;
  /** Lesion components the classification removed from the mask (below the minimum lesion size; finding F09). */
  removed_small_components?: RemovedSmallComponents;
}

export interface RemovedSmallComponents {
  components: number;
  voxels: number;
  volume_mm3: number;
  min_lesion_volume_mm3: number;
  reason: string;
}

export interface ZoneMapStat {
  zone_id: number;
  voxel_count: number;
  volume_mm3: number;
  volume_ml: number;
  percentage: number;
}

export interface ZoneMapResult {
  segmentation_id: string;
  file_id: string;
  zone_stats: Record<string, ZoneMapStat>;
  total_brain_voxels: number;
  processing_time_ms: number;
}

// ============================================================================
// CVS / PRL Annotations (McDonald 2024 Biomarkers)
// ============================================================================

export interface LesionAnnotation {
  lesion_id: number;
  cvs_status: 'positive' | 'negative' | 'indeterminate' | null;
  prl_status: 'positive' | 'negative' | 'indeterminate' | null;
  annotated_by: string | null;
  annotated_at: string | null;
  notes: string | null;
}

/** Counts of a clinician's CVS readings (CAPA-008: counts only, never "criteria met"). */
export interface CVSSummary {
  total_evaluated: number;
  cvs_positive: number;
  cvs_negative: number;
  meets_select6: boolean;     // McDonald 2024 "select 6": >=6 lesions read CVS+
  cvs_majority?: boolean;     // CVS+ outnumber CVS− (McDonald 2024: counts only if <10 WM lesions)
  // The former "40% rule" is withdrawn (CAPA-008): it is not part of McDonald 2024.
}

/** Counts of a clinician's PRL readings. >=1 PRL is supportive only in specific situations. */
export interface PRLSummary {
  total_evaluated: number;
  prl_positive: number;
  meets_criteria: boolean;    // >=1 lesion read PRL+ (not, by itself, a diagnostic criterion)
}
