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
export type Modality = 'CT' | 'MR' | 'US' | 'XR' | 'MG' | 'NM' | 'PT' | 'CR' | 'DX' | 'OT';
export type StudyStatus = 'registered' | 'available' | 'cancelled' | 'entered-in-error';
export type DocumentCategory =
  | 'lab-result'
  | 'prescription'
  | 'clinical-note'
  | 'discharge-summary'
  | 'radiology-report'
  | 'consent-form'
  | 'referral'
  | 'operative-note'
  | 'pathology-report'
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
 * Default labels for common segmentation tasks.
 */
export const DEFAULT_SEGMENTATION_LABELS: LabelInfo[] = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0.0, visible: false },
  { id: 1, name: 'Lesion', color: '#FF0000', opacity: 0.5, visible: true },
  { id: 2, name: 'Tumor', color: '#00FF00', opacity: 0.5, visible: true },
  { id: 3, name: 'Edema', color: '#0000FF', opacity: 0.5, visible: true },
  { id: 4, name: 'Necrosis', color: '#FFFF00', opacity: 0.5, visible: true },
];

/**
 * Brain tumor segmentation labels (BraTS standard).
 */
export const BRATS_SEGMENTATION_LABELS: LabelInfo[] = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0.0, visible: false },
  { id: 1, name: 'Necrotic Core (NCR)', color: '#FF0000', opacity: 0.6, visible: true, snomed_code: '6574001' },
  { id: 2, name: 'Peritumoral Edema (ED)', color: '#00FF00', opacity: 0.5, visible: true, snomed_code: '79654002' },
  { id: 4, name: 'Enhancing Tumor (ET)', color: '#FFFF00', opacity: 0.6, visible: true, snomed_code: '86049000' },
];

/**
 * Label presets for quick segmentation setup.
 */
export const DEFAULT_LABEL_PRESETS = {
  DEFAULT: DEFAULT_SEGMENTATION_LABELS,
  BRATS: BRATS_SEGMENTATION_LABELS,
};
