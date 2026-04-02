/**
 * @deprecated Use GCS storage paths instead
 * Kept for backward compatibility during migration
 */
export interface StorageFileInfo {
  id: string;
  name: string;
  mimeType: string;
  size?: number;
  modifiedTime?: string;
  path?: string;
}

/** @deprecated Alias for StorageFileInfo - use StorageFileInfo instead */
export type DriveFileInfo = StorageFileInfo;

export interface ImageMetadata {
  patient_id?: string;
  patient_name?: string;
  study_date?: string;
  study_description?: string;
  series_description?: string;
  modality?: string;
  manufacturer?: string;
  institution_name?: string;
  rows?: number;
  columns?: number;
  slices?: number;
  pixel_spacing?: number[];
  slice_thickness?: number;
  window_center?: number;
  window_width?: number;
  extra_fields?: Record<string, any>;
}

export interface ImageSlice {
  slice_index: number;
  image_data: string;
  format: 'dicom' | 'nifti';
  width: number;
  height: number;
  window_center?: number;
  window_width?: number;
}

export interface ImageSeriesResponse {
  id: string;
  name: string;
  format: 'dicom' | 'nifti';
  metadata: ImageMetadata;
  total_slices: number;
  slices?: ImageSlice[];
  file_id?: string;  // GCS object path for 3D rendering
}

export interface WindowLevelRequest {
  window_center: number;
  window_width: number;
  slice_index: number;
}

export type ImageOrientation = 'axial' | 'sagittal' | 'coronal';

export interface VolumeData {
  volume: number[][][];
  shape: [number, number, number];
  orientation: ImageOrientation;
  metadata: ImageMetadata;
}

export interface Point3D {
  x: number;
  y: number;
  z: number;
}

export interface Measurement {
  type: 'distance' | 'angle' | 'area' | 'volume';
  points: Point3D[];
  value: number;
  unit: string;
  label?: string;
}

// ============================================================================
// EHR Types - Patient, Study, Document
// ============================================================================

export type Gender = 'male' | 'female' | 'other' | 'unknown';
export type PatientStatus = 'active' | 'inactive' | 'deceased';
export type Modality = 'CT' | 'MR' | 'US' | 'XR' | 'MG' | 'NM' | 'PT' | 'CR' | 'DX' | 'RF' | 'OT';
export type StudyStatus = 'registered' | 'available' | 'cancelled' | 'entered-in-error';
export type DocumentCategory =
  | 'clinical-note'
  | 'radiology-report'
  | 'ms-assessment'
  | 'other';
export type DocumentStatus = 'current' | 'superseded' | 'entered-in-error';

export interface Patient {
  id: string;
  mrn: string;
  given_name: string;
  middle_name?: string;
  family_name: string;
  name_prefix?: string;
  name_suffix?: string;
  full_name: string;
  birth_date: string;
  gender: Gender;
  age: number;
  phone_home?: string;
  phone_mobile: string;
  phone_work?: string;
  email?: string;
  address_line1?: string;
  address_line2?: string;
  city?: string;
  state?: string;
  postal_code?: string;
  country: string;
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
  emergency_contact_relationship?: string;
  insurance_provider?: string;
  insurance_policy_number?: string;
  status: PatientStatus;
  deceased_date?: string;
  created_at: string;
  updated_at: string;
  study_count?: number;
  document_count?: number;
}

export interface PatientSummary {
  id: string;
  mrn: string;
  full_name: string;
  birth_date: string;
  gender: Gender;
  status: PatientStatus;
}

export interface PatientCreate {
  mrn: string;
  given_name: string;
  middle_name?: string;
  family_name: string;
  name_prefix?: string;
  name_suffix?: string;
  birth_date: string;
  gender: Gender;
  phone_home?: string;
  phone_mobile: string;
  phone_work?: string;
  email?: string;
  address_line1?: string;
  address_line2?: string;
  city?: string;
  state?: string;
  postal_code?: string;
  country?: string;
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
  emergency_contact_relationship?: string;
  insurance_provider?: string;
  insurance_policy_number?: string;
}

export interface PatientUpdate extends Partial<Omit<PatientCreate, 'mrn'>> {
  status?: PatientStatus;
  deceased_date?: string;
}

export interface PatientListResponse {
  items: Patient[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface MedicalHistory {
  id: string;
  patient_id: string;
  condition_name: string;
  condition_code?: string;
  condition_system?: string;
  is_active: boolean;
  onset_date?: string;
  resolution_date?: string;
  severity?: 'mild' | 'moderate' | 'severe';
  notes?: string;
  recorded_by?: string;
  recorded_at: string;
}

export interface MedicalHistoryCreate {
  condition_name: string;
  condition_code?: string;
  condition_system?: string;
  is_active?: boolean;
  onset_date?: string;
  resolution_date?: string;
  severity?: 'mild' | 'moderate' | 'severe';
  notes?: string;
}

export interface ImagingStudy {
  id: string;
  patient_id: string;
  study_instance_uid: string;
  accession_number?: string;
  status: StudyStatus;
  modality: Modality;
  body_site?: string;
  study_date: string;
  study_description?: string;
  reason_for_study?: string;
  referring_physician_name?: string;
  performing_physician_name?: string;
  institution_name?: string;
  series_count?: number;
  instance_count?: number;
  total_size_bytes?: number;
  created_at: string;
  updated_at?: string;
}

export interface StudySummary {
  id: string;
  patient_id: string;
  accession_number?: string;
  modality: Modality;
  study_date: string;
  study_description?: string;
  status: StudyStatus;
  series_count?: number;
  instance_count?: number;
  total_size_bytes?: number;
}

export interface StudyCreate {
  patient_id: string;
  modality: Modality;
  body_site?: string;
  study_date: string;
  study_description?: string;
  reason_for_study?: string;
  referring_physician_name?: string;
  performing_physician_name?: string;
  institution_name?: string;
}

export interface StudyUpdate {
  status?: StudyStatus;
  study_description?: string;
  reason_for_study?: string;
  referring_physician_name?: string;
  performing_physician_name?: string;
  body_site?: string;
}

export interface StudyListResponse {
  items: StudySummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ImagingSeries {
  id: string;
  study_id: string;
  series_instance_uid: string;
  series_number: number;
  modality: Modality;
  series_description?: string;
  body_part_examined?: string;
  instance_count?: number;
  total_size_bytes?: number;
  created_at: string;
}

export interface ImagingInstance {
  id: string;
  series_id: string;
  sop_instance_uid: string;
  sop_class_uid?: string;
  instance_number?: number;
  gcs_object_name: string;
  original_filename: string;
  content_type: string;
  file_size_bytes: number;
  checksum_sha256?: string;
  rows?: number;
  columns?: number;
  bits_allocated?: number;
  photometric_interpretation?: string;
  transfer_syntax_uid?: string;
  created_at: string;
}

export interface UploadInitRequest {
  study_id: string;
  series_number: number;
  filename: string;
  content_type: string;
  file_size_bytes: number;
  modality?: Modality;
  series_description?: string;
}

export interface UploadInitResponse {
  upload_id: string;
  signed_url: string;
  expires_at: string;
  headers?: Record<string, string>;
  series_id?: string;
  gcs_object_name: string;
}

export interface UploadCompleteRequest {
  upload_id: string;
  checksum_sha256: string;
}

export interface UploadCompleteResponse {
  instance_id: string;
  series_id: string;
  study_id: string;
  gcs_object_name: string;
  file_size_bytes: number;
}

export interface DownloadUrlResponse {
  instance_id: string;
  url: string;
  filename: string;
  expires_at: string;
}

export interface Document {
  id: string;
  patient_id: string;
  study_id?: string;
  title: string;
  description?: string;
  category: DocumentCategory;
  document_date: string;
  status: DocumentStatus;
  version: number;
  original_filename: string;
  content_type: string;
  file_size_bytes: number;
  checksum_sha256?: string;
  gcs_object_name?: string;
  author_name?: string;
  created_at: string;
  updated_at?: string;
  created_by?: string;
}

export interface DocumentSummary {
  id: string;
  patient_id: string;
  title: string;
  category: DocumentCategory;
  document_date: string;
  status: DocumentStatus;
  version: number;
  content_type: string;
  file_size_bytes: number;
  created_at: string;
}

export interface DocumentCreate {
  patient_id: string;
  study_id?: string;
  title: string;
  description?: string;
  category: DocumentCategory;
  document_date: string;
  author_name?: string;
}

export interface DocumentUpdate {
  title?: string;
  description?: string;
  category?: DocumentCategory;
  document_date?: string;
  status?: DocumentStatus;
  author_name?: string;
}

export interface DocumentListResponse {
  items: DocumentSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface DocumentVersion {
  id: string;
  document_id: string;
  version: number;
  original_filename: string;
  content_type: string;
  file_size_bytes: number;
  checksum_sha256: string;
  gcs_object_name: string;
  created_at: string;
  created_by?: string;
  change_summary?: string;
}

export interface DocumentUploadInit {
  patient_id: string;
  study_id?: string;
  title: string;
  category: DocumentCategory;
  document_date: string;
  filename: string;
  content_type: string;
  file_size_bytes: number;
  description?: string;
  author_name?: string;
}

export interface DocumentUploadInitResponse {
  upload_id: string;
  signed_url: string;
  expires_at: string;
  headers: Record<string, string>;
  document_id: string;
  gcs_object_name: string;
}

export interface DocumentUploadComplete {
  upload_id: string;
  checksum_sha256: string;
}

export interface DocumentUploadCompleteResponse {
  document: Document;
  is_new_version: boolean;
  version_count: number;
}

export interface VersionUploadInit {
  document_id: string;
  filename: string;
  content_type: string;
  file_size_bytes: number;
  change_summary?: string;
}

export interface VersionUploadInitResponse {
  upload_id: string;
  signed_url: string;
  expires_at: string;
  headers: Record<string, string>;
  new_version: number;
  gcs_object_name: string;
}

export interface DocumentDownloadUrl {
  document_id: string;
  version: number;
  url: string;
  filename: string;
  content_type: string;
  expires_at: string;
}

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
export type ExportFormat = 'nifti' | 'dicom_seg' | 'nrrd';

/**
 * Request to export segmentation.
 */
export interface ExportRequest {
  format: ExportFormat;
  include_metadata?: boolean;
  compress?: boolean;
}

/**
 * Response with export download information.
 */
export interface ExportResponse {
  download_url: string;
  filename: string;
  format: ExportFormat;
  size_bytes: number;
  expires_at: string;
}

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
 * Segmentation count by series (for UI indicators).
 */
export interface SeriesSegmentationCount {
  series_id: string;
  count: number;
  has_approved: boolean;
  has_in_progress: boolean;
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
// AI Segmentation Types
// ============================================================================

export type AIModel = 'sam_med3d' | 'nninteractive' | 'synthseg' | 'mindglide';

export type AITaskStatus = 'pending' | 'processing' | 'completed' | 'failed';

export type AIMode = 'interactive' | 'auto' | null;

export interface ClickPoint3D {
  x: number;
  y: number;
  z: number;
  label: 'positive' | 'negative';
}

export interface InteractiveSegmentRequest {
  file_id: string;
  click_points: ClickPoint3D[];
  model: AIModel;
  current_mask_id?: string;
}

export interface AutoSegmentRequest {
  file_id: string;
  model: AIModel;
}

export interface AITaskResult {
  task_id: string;
  status: AITaskStatus;
  progress: number;
  segmentation_id?: string;
  error?: string;
  processing_time_ms?: number;
}

export interface BrainAnomaly {
  type: 'ms_lesion' | 'active_lesion' | 'chronic_lesion' | 'black_hole';
  location: string;
  confidence: number;
  volume_mm3?: number;
  gadolinium_enhancement?: boolean;
  bounding_box?: {
    x_min: number; y_min: number; z_min: number;
    x_max: number; y_max: number; z_max: number;
  };
}

export interface AnomalyDetectionResult {
  anomalies: BrainAnomaly[];
  heatmap_segmentation_id?: string;
  overall_confidence: number;
  processing_time_ms?: number;
}

export interface AIModelInfo {
  id: string;
  name: string;
  type: 'interactive' | 'auto';
  description: string;
  prompt_types?: string[];
  structures_count?: number;
  configured: boolean;
}

/**
 * SynthSeg brain structure labels (FreeSurfer convention).
 * Used when loading auto-segmentation results from AI.
 */
export const BRAIN_STRUCTURE_LABELS: LabelInfo[] = [
  { id: 0,  name: 'Background', color: '#000000', opacity: 0.0, visible: false },
  { id: 2,  name: 'L Cerebral WM', color: '#F5F5DC', opacity: 0.5, visible: true, snomed_code: '61392005' },
  { id: 3,  name: 'L Cerebral Cortex', color: '#CD853F', opacity: 0.5, visible: true, snomed_code: '68594002' },
  { id: 4,  name: 'L Lateral Ventricle', color: '#4169E1', opacity: 0.6, visible: true, snomed_code: '66720007' },
  { id: 5,  name: 'L Inf Lat Ventricle', color: '#6495ED', opacity: 0.5, visible: true },
  { id: 7,  name: 'L Cerebellum WM', color: '#F0E68C', opacity: 0.5, visible: true },
  { id: 8,  name: 'L Cerebellum Cortex', color: '#BDB76B', opacity: 0.5, visible: true },
  { id: 10, name: 'L Thalamus', color: '#2E8B57', opacity: 0.6, visible: true, snomed_code: '42695009' },
  { id: 11, name: 'L Caudate', color: '#00CED1', opacity: 0.6, visible: true, snomed_code: '11000004' },
  { id: 12, name: 'L Putamen', color: '#FF69B4', opacity: 0.6, visible: true, snomed_code: '89278009' },
  { id: 13, name: 'L Pallidum', color: '#FF1493', opacity: 0.6, visible: true },
  { id: 14, name: '3rd Ventricle', color: '#1E90FF', opacity: 0.5, visible: true },
  { id: 15, name: '4th Ventricle', color: '#00BFFF', opacity: 0.5, visible: true },
  { id: 16, name: 'Brain Stem', color: '#8B4513', opacity: 0.5, visible: true, snomed_code: '15926001' },
  { id: 17, name: 'L Hippocampus', color: '#FFD700', opacity: 0.7, visible: true, snomed_code: '5366008' },
  { id: 18, name: 'L Amygdala', color: '#FF8C00', opacity: 0.7, visible: true, snomed_code: '4958002' },
  { id: 24, name: 'CSF', color: '#87CEEB', opacity: 0.4, visible: true },
  { id: 26, name: 'L Accumbens', color: '#DA70D6', opacity: 0.6, visible: true },
  { id: 28, name: 'L VentralDC', color: '#9370DB', opacity: 0.5, visible: true },
  { id: 41, name: 'R Cerebral WM', color: '#FFFACD', opacity: 0.5, visible: true },
  { id: 42, name: 'R Cerebral Cortex', color: '#DEB887', opacity: 0.5, visible: true },
  { id: 43, name: 'R Lateral Ventricle', color: '#6495ED', opacity: 0.6, visible: true },
  { id: 44, name: 'R Inf Lat Ventricle', color: '#87CEFA', opacity: 0.5, visible: true },
  { id: 46, name: 'R Cerebellum WM', color: '#EEE8AA', opacity: 0.5, visible: true },
  { id: 47, name: 'R Cerebellum Cortex', color: '#D2B48C', opacity: 0.5, visible: true },
  { id: 49, name: 'R Thalamus', color: '#3CB371', opacity: 0.6, visible: true },
  { id: 50, name: 'R Caudate', color: '#48D1CC', opacity: 0.6, visible: true },
  { id: 51, name: 'R Putamen', color: '#FF69B4', opacity: 0.6, visible: true },
  { id: 52, name: 'R Pallidum', color: '#FF1493', opacity: 0.6, visible: true },
  { id: 53, name: 'R Hippocampus', color: '#FFD700', opacity: 0.7, visible: true },
  { id: 54, name: 'R Amygdala', color: '#FF8C00', opacity: 0.7, visible: true },
  { id: 58, name: 'R Accumbens', color: '#DA70D6', opacity: 0.6, visible: true },
  { id: 60, name: 'R VentralDC', color: '#9370DB', opacity: 0.5, visible: true },
];

// ============================================================================
// Brain Volumetry Types
// ============================================================================

export interface BrainStructureVolume {
  label_id: number;
  structure_name: string;
  volume_mm3: number;
  volume_ml: number;
  normative_percentile?: number;
  is_abnormal: boolean;
  abnormality_type?: 'atrophy' | 'enlargement';
}

export interface VolumetryResult {
  segmentation_id: string;
  structures: BrainStructureVolume[];
  total_brain_volume_ml?: number;
  intracranial_volume_ml?: number;
  processing_time_ms?: number;
}

export interface VolumetryComparisonResult {
  patient_id: string;
  timepoints: Array<{ study_id: string; date: string }>;
  changes: Array<{
    label_id: number;
    structure: string;
    volume_first_ml: number;
    volume_last_ml: number;
    change_percent: number;
    trend: 'stable' | 'increasing' | 'decreasing';
  }>;
}

export interface VolumetryRequest {
  segmentation_id: string;
  voxel_spacing?: [number, number, number];
  patient_age?: number;
  patient_sex?: 'M' | 'F';
}

// ============================================================================
// AI Report Types
// ============================================================================

export type ReportTemplateType = 'general' | 'ms_activity' | 'ms_comprehensive' | 'ms_lesion_burden' | 'ms_longitudinal';

export interface ReportGenerateRequest {
  template_type: ReportTemplateType;
  language: string;
  findings: Record<string, any>;
  volumetry?: Record<string, any> | null;
}

export interface ReportResponse {
  report_id: string;
  content: string;
  template_type: ReportTemplateType;
  language: string;
  processing_time_ms: number;
  model?: string;
  tokens_used?: { input: number; output: number };
}

export interface ReportTemplateInfo {
  id: ReportTemplateType;
  name: string;
  description: string;
}

// ============================================================================
// Edge AI Types (Browser-based ONNX screening)
// ============================================================================

export interface EdgeAIScreeningResult {
  normal: number;
  abnormal: number;
  inferenceTimeMs: number;
  label: 'normal' | 'abnormal';
  confidence: number;
}

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
export interface DISAssessment {
  segmentation_id: string;
  dis_met_brain: boolean;
  dis_criteria_version: string;
  brain_regions_with_lesions: number;
  total_dis_regions: number;         // 5 (McDonald 2024)
  brain_regions_evaluated: number;   // 3
  spinal_cord_evaluated: boolean;
  optic_nerve_evaluated: boolean;
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

// ============================================================================
// Clinical Tools Types (LST-AI, SynthSeg)
// ============================================================================

export interface ClinicalToolInfo {
  id: string;
  name: string;
  version: string;
  available: boolean;
  healthy?: boolean;
  description: string;
  citation: string;
  license: string;
  fda_status: 'research_only' | '510k_cleared';
  required_inputs: string[];
}

export type ToolTaskStatus =
  | 'pending'
  | 'downloading'
  | 'processing'
  | 'storing'
  | 'completed'
  | 'failed';

export interface ToolTaskResult {
  task_id: string;
  tool: string;
  status: ToolTaskStatus;
  progress: number;
  segmentation_id?: string;
  error?: string;
  processing_time_ms?: number;
  validation_source: string;
  created_at: string;
}
