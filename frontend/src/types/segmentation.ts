/**
 * Segmentation: masks, labels, paint, overlays, comparison, and the ITK-SNAP local-first API contracts.
 *
 * Split out of the former single types/index.ts barrel (Fase 2.1) — re-exported
 * from ./index.ts, so `@/types` consumers are unchanged.
 */

import type { CVSSummary, DISAssessment, LesionAnalysisResult, LesionAnnotation, PRLSummary, RegionClassificationResult } from './lesion';

// ============================================================================
// Segmentation Types - ITK-SNAP Style Multi-Expert Segmentation
// ============================================================================

/**
 * Segmentation status (workflow states).
 */
export type SegmentationStatus =
  | 'draft'           // Created, no annotations yet
  | 'in_progress'     // Active work
  | 'saved'           // Saved by user (local-first flow)
  | 'pending_review'  // Waiting for review
  | 'reviewed'        // Reviewed by another expert
  | 'approved'        // Approved for clinical use
  | 'archived';       // Archived (not active)

/**
 * Segmentation type according to DICOM SEG standard.
 */
export type SegmentationType =
  | 'binary'      // One label per segment (0 or 1)
  | 'labelmap'    // Multiple labels (ITK-SNAP style, 0-255)
  | 'fractional'; // Probability values (AI predictions)

/**
 * Overlay rendering mode.
 */
export type OverlayMode =
  | 'overlay'       // Color overlay with transparency
  | 'outline'       // Contour/border only
  | 'checkerboard'  // Checkerboard pattern for comparison
  | 'side_by_side'; // Side-by-side comparison

/**
 * Label definition for segmentation (ITK-SNAP style).
 * Labels are integers 0-255 where:
 * - 0 = Background/Clear (always transparent)
 * - 1-255 = User-defined labels
 */
export interface LabelInfo {
  id: number;           // Label ID (0-255)
  name: string;         // Label name
  color: string;        // Hex color code (#RRGGBB)
  opacity: number;      // Overlay opacity (0.0 - 1.0)
  visible: boolean;     // Whether label is visible in overlay
  description?: string; // Label description
  snomed_code?: string; // SNOMED-CT code (optional)
  finding_site?: string; // Anatomical location (optional)
}

/**
 * Label update request.
 */
export interface LabelUpdate {
  name?: string;
  color?: string;
  opacity?: number;
  visible?: boolean;
  description?: string;
  snomed_code?: string;
  finding_site?: string;
}

/**
 * Full segmentation response with all metadata.
 */
export interface Segmentation {
  id: string;

  // Hierarchical relationships
  patient_id: string;
  study_id: string;
  series_id: string;

  // For backward compatibility
  file_id?: string;

  // Metadata
  name: string;
  description?: string;
  segmentation_type: SegmentationType;

  // Status and progress
  status: SegmentationStatus;
  progress_percentage: number;
  slices_annotated: number;
  total_slices: number;

  // Authorship
  created_by: string;      // username
  created_by_name?: string; // full name
  reviewed_by?: string;
  reviewed_by_name?: string;
  reviewed_at?: string;
  review_notes?: string;

  // Labels (ITK-SNAP style)
  labels: LabelInfo[];

  // Storage
  gcs_path?: string;

  // Timestamps
  created_at: string;
  modified_at: string;
}

/**
 * Minimal segmentation info for lists (fast loading).
 */
export interface SegmentationSummary {
  id: string;
  name: string;
  status: SegmentationStatus;
  progress_percentage: number;
  slices_annotated: number;
  total_slices: number;
  created_by: string;
  created_by_name?: string;
  created_at: string;
  modified_at: string;
  label_count: number;
  primary_label_color: string; // Color of the primary non-background label
}

/**
 * Paginated list of segmentations.
 */
export interface SegmentationListResponse {
  items: SegmentationSummary[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

/**
 * Request to create a new segmentation.
 */
export interface SegmentationCreate {
  series_id: string;
  name: string;
  description?: string;
  segmentation_type?: SegmentationType;
  labels?: LabelInfo[];
}

/**
 * Request to update segmentation metadata.
 */
export interface SegmentationUpdate {
  name?: string;
  description?: string;
}

/**
 * Request to update segmentation status.
 */
export interface SegmentationStatusUpdate {
  status: SegmentationStatus;
  notes?: string;
}

/**
 * Single paint stroke data for segmentation editing.
 */
export interface PaintStroke {
  slice_index: number;
  label_id: number;     // Label ID to paint (0-255)
  x: number;            // X coordinate (column)
  y: number;            // Y coordinate (row)
  brush_size: number;   // Brush size in voxels
  erase: boolean;       // Erase mode (set to label 0)
}

/**
 * Batch of paint strokes for efficient transmission.
 */
export interface PaintStrokeBatch {
  strokes: PaintStroke[];
}

/**
 * Settings for segmentation overlay rendering.
 */
export interface OverlaySettings {
  mode: OverlayMode;
  global_opacity: number;
  visible_labels?: number[]; // Label IDs to show (null = all visible)
  outline_thickness: number;
  outline_only: boolean;
}

/**
 * Statistics for a single label.
 */
export interface LabelStatistics {
  label_id: number;
  label_name: string;
  voxel_count: number;
  volume_mm3?: number;   // Requires voxel spacing
  percentage: number;
  slices_present: number;
}

/**
 * Complete statistics for a segmentation.
 */
export interface SegmentationStatistics {
  segmentation_id: string;
  total_voxels: number;
  annotated_voxels: number;
  image_shape: [number, number, number]; // [depth, height, width]
  voxel_spacing?: [number, number, number]; // [dz, dy, dx] in mm
  label_statistics: LabelStatistics[];
  computed_at: string;
}

/**
 * Comparison metrics between two segmentations.
 */
export interface ComparisonMetrics {
  segmentation_a: string;
  segmentation_b: string;
  dice_coefficient: number;
  hausdorff_distance?: number;
  volume_difference_percent: number;
  voxel_agreement_percent: number;
}

/**
 * Request to compare multiple segmentations.
 */
export interface SegmentationComparisonRequest {
  segmentation_ids: string[];
  metrics: string[];
}

/**
 * Response with comparison results.
 */
export interface SegmentationComparisonResponse {
  segmentation_ids: string[];
  pairwise_metrics: ComparisonMetrics[];
  consensus_labels?: Record<number, number>;
  computed_at: string;
}

/**
 * Export format options.
 */

/**
 * Search parameters for segmentations.
 */
export interface SegmentationSearch {
  // Hierarchy filters
  patient_id?: string;
  study_id?: string;
  series_id?: string;

  // Status filter
  status?: SegmentationStatus;
  status_in?: SegmentationStatus[];

  // Author filter
  created_by?: string;
  reviewed_by?: string;

  // Date filters
  created_after?: string;
  created_before?: string;
  modified_after?: string;

  // Full-text search
  query?: string;

  // Pagination
  page?: number;
  page_size?: number;

  // Sorting
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

/**
 * Default labels for MS lesion segmentation.
 */
export const DEFAULT_SEGMENTATION_LABELS: LabelInfo[] = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0.0, visible: false },
  { id: 1, name: 'MS Lesion (Active)', color: '#FF0000', opacity: 0.6, visible: true, snomed_code: '421399003' },
  { id: 2, name: 'MS Lesion (Chronic)', color: '#FFD700', opacity: 0.5, visible: true, snomed_code: '24700007' },
  { id: 3, name: 'T2/FLAIR Hyperintensity', color: '#4169E1', opacity: 0.5, visible: true },
  { id: 4, name: 'Black Hole (T1)', color: '#9932CC', opacity: 0.5, visible: true },
];

/**
 * MAGNIMS regional labels for MS lesion classification.
 * Based on McDonald 2024 / MAGNIMS criteria for Dissemination in Space (DIS).
 */
export const MAGNIMS_LESION_LABELS: LabelInfo[] = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0.0, visible: false },
  { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true,
    snomed_code: '12738006', finding_site: 'Periventricular white matter',
    description: 'Dawson fingers — perpendicular to lateral ventricles' },
  { id: 2, name: 'Juxtacortical', color: '#00CC00', opacity: 0.6, visible: true,
    snomed_code: '4479006', finding_site: 'Juxtacortical/cortical',
    description: 'Touching cortex, involving U-fibers' },
  { id: 3, name: 'Infratentorial', color: '#0066FF', opacity: 0.6, visible: true,
    snomed_code: '31065004', finding_site: 'Brainstem/cerebellum',
    description: 'Brainstem, cerebellum, cerebellar peduncles' },
  { id: 4, name: 'Deep White Matter', color: '#FFD700', opacity: 0.6, visible: true,
    snomed_code: '69536005', finding_site: 'Deep white matter',
    description: 'Atypical for MS — common in vascular processes' },
  { id: 5, name: 'Active (Gd+)', color: '#FF00FF', opacity: 0.6, visible: true,
    description: 'Gadolinium-enhancing lesion — acute inflammation' },
  { id: 6, name: 'Black Hole (T1)', color: '#9932CC', opacity: 0.5, visible: true,
    description: 'T1-hypointense — irreversible axonal loss' },
];

/**
 * Label preset identifiers.
 */
export type LabelPreset = 'default' | 'magnims' | 'custom';

/**
 * Label presets for quick segmentation setup.
 */
export const DEFAULT_LABEL_PRESETS: Record<string, LabelInfo[]> = {
  default: DEFAULT_SEGMENTATION_LABELS,
  magnims: MAGNIMS_LESION_LABELS,
};

// ============================================================================
// Segmentation API Types (ITK-SNAP local-first flow)
// ============================================================================

/**
 * Cached MAGNIMS analysis results persisted in Firestore (McDonald 2024).
 */
export interface SegmentationAnalysisData {
  lesion_analysis?: LesionAnalysisResult;
  dis_assessment?: DISAssessment;
  classification?: RegionClassificationResult;
  zone_map_seg_id?: string;
  analysis_mask_modified_at?: string;
  // McDonald 2024 biomarker annotations
  lesion_annotations?: LesionAnnotation[];
  cvs_summary?: CVSSummary;
  prl_summary?: PRLSummary;
}

/**
 * Segmentation metadata returned by the server.
 */
export interface SegmentationMetadata {
  file_id: string;
  created_at: string;
  modified_at: string;
  labels: LabelInfo[];
  description?: string;
  analysis_data?: SegmentationAnalysisData | null;
}

/**
 * Server response when creating or loading a segmentation.
 */
export interface SegmentationResponse {
  segmentation_id: string;
  file_id: string;
  metadata: SegmentationMetadata;
  total_slices: number;
}

/**
 * Image dimensions for creating a new segmentation.
 */
export interface ImageShape {
  rows: number;
  columns: number;
  slices: number;
}

/**
 * Request to create a new segmentation.
 */
export interface CreateSegmentationRequest {
  file_id: string;
  image_shape: ImageShape;
  description?: string;
  labels?: LabelInfo[];
}

/**
 * Response containing a rendered overlay image slice.
 */
export interface OverlayImageResponse {
  slice_index: number;
  overlay_image: string; // Base64 encoded image
}
