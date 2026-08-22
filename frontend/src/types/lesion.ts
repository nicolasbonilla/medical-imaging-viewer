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

export interface DISAssessment {
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
   *  clinical size gate (reported but excluded from activity/DIT candidate counts). */
  clinically_significant?: boolean;
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
  /** True when the new candidate's subtraction signal clears the advisory bar (likely
   *  a genuine new lesion, not a segmentation/registration artifact). null/absent for
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

export interface LongitudinalResult {
  changes: LesionChange[];
  total_lesions_tp1: number;
  total_lesions_tp2: number;
  burden_tp1_mm3: number;
  burden_tp2_mm3: number;
  burden_tp1_ml: number;
  burden_tp2_ml: number;
  burden_delta_mm3: number;
  burden_delta_percent: number;
  status_counts: Record<LesionChangeStatus, number>;
  // ── MAGNIMS clinical CANDIDATE signals (advisory — never a diagnosis) ──
  /** The ~3 mm-diameter minimum used to count a "clinically significant" new lesion. */
  new_lesion_min_diameter_mm?: number;
  /** Count of new lesions clearing the ≥3 mm size gate. */
  new_clinically_significant_count?: number;
  /** Count of enlarging lesions. */
  enlarging_count?: number;
  /** ≥1 significant new lesion → supports dissemination-in-time (CANDIDATE — a reader
   *  must confirm; the report builder is barred from asserting DIT). */
  dit_candidate?: boolean;
  /** ≥2 new/enlarging lesions → MAGNIMS active-disease signal (CANDIDATE only). */
  activity_candidate?: boolean;
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
  confidence: number;
  volume_mm3: number;
  volume_ml: number;
  voxel_count: number;
  centroid: LesionCentroid;
  distances_mm: LesionDistances;
}

export interface RegionClassificationResult {
  segmentation_id: string;
  method: 'parcellation' | 'geometric';
  lesions: ClassifiedLesion[];
  total_classified: number;
  classification_summary: Record<string, number>;
  thresholds_mm: Record<string, number | string>;
  processing_time_ms: number;
  mask_updated: boolean;
  labels_updated: boolean;
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

export interface CVSSummary {
  total_evaluated: number;
  cvs_positive: number;
  cvs_negative: number;
  meets_select6: boolean;     // McDonald 2024: >=6 CVS+ lesions
  meets_40pct: boolean;       // McDonald 2024: >=40% CVS+ of evaluated
}

export interface PRLSummary {
  total_evaluated: number;
  prl_positive: number;
  meets_criteria: boolean;    // McDonald 2024: >=1 PRL
}
