export interface DriveFileInfo {
  id: string;
  name: string;
  mimeType: string;
  size?: number;
  modifiedTime?: string;
  webViewLink?: string;
  thumbnailLink?: string;
}

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
  file_id?: string;  // Google Drive file ID for 3D rendering
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
