/**
 * EHR domain: patients, studies, series, instances, documents.
 *
 * Split out of the former single types/index.ts barrel (Fase 2.1) — re-exported
 * from ./index.ts, so `@/types` consumers are unchanged.
 */

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
