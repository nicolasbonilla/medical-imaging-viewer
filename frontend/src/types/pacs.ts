/**
 * DICOMweb / PACS integration.
 *
 * Split out of the former single types/index.ts barrel (Fase 2.1) — re-exported
 * from ./index.ts, so `@/types` consumers are unchanged.
 */

// ============================================================================
// DICOMweb / PACS Integration Types
// ============================================================================

export interface PACSConnection {
  id: string;
  name: string;
  base_url: string;
  auth_type: 'none' | 'basic' | 'bearer';
  username?: string;
  verify_ssl: boolean;
  created_at: string;
  last_tested?: string;
  is_reachable?: boolean;
}

export interface PACSConnectionCreate {
  name: string;
  base_url: string;
  auth_type: 'none' | 'basic' | 'bearer';
  username?: string;
  password?: string;
  bearer_token?: string;
  verify_ssl: boolean;
}

export interface DICOMwebStudyResult {
  study_instance_uid: string;
  patient_name?: string;
  patient_id?: string;
  study_date?: string;
  study_description?: string;
  modality?: string;
  accession_number?: string;
  number_of_series?: number;
  number_of_instances?: number;
}

export interface DICOMwebSeriesResult {
  series_instance_uid: string;
  series_number?: number;
  modality?: string;
  series_description?: string;
  body_part_examined?: string;
  number_of_instances?: number;
}

export interface DICOMwebImportRequest {
  connection_id: string;
  study_instance_uid: string;
  series_instance_uid: string;
  patient_id: string;
  study_description?: string;
}

export interface DICOMwebImportJob {
  job_id: string;
  status: 'pending' | 'downloading' | 'converting' | 'uploading' | 'registering' | 'completed' | 'failed';
  progress_percent: number;
  error_message?: string;
  instances_downloaded: number;
  instances_total?: number;
  study_id?: string;
  series_id?: string;
  instance_id?: string;
  created_at?: string;
  completed_at?: string;
}
