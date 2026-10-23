/**
 * Imaging & viewer primitives (storage, image metadata, slices, geometry).
 *
 * Split out of the former single types/index.ts barrel (Fase 2.1) — re-exported
 * from ./index.ts, so `@/types` consumers are unchanged.
 */

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
  /**
   * Anatomical axis codes, e.g. "RAS" or "LAS" — the direction of INCREASING
   * index along each axis. Risk control RC-023 for HAZ-006 (CAPA-004).
   *
   * "UNKNOWN" is a real value, not a missing one: it means the affine does not
   * determine an orientation. Never coerce it to a default. The viewport must
   * warn instead of drawing a laterality label it cannot justify.
   */
  anatomical_orientation?: string;
  /**
   * Slice thickness of the ORIGINAL acquisition with its source and state
   * (RC-054, CP-SLICE-THICKNESS-001 — DRAFT). Not `slice_thickness` above, which is a
   * legacy display value (1.0 mm by default for a DICOM without the tag). Absent on
   * responses from before this field existed: the client treats that as not determinable.
   */
  acquisition_geometry?: AcquisitionGeometry | null;
  extra_fields?: Record<string, any>;
}

/** Backend `AcquisitionGeometry` (app/models/schemas.py). Parsed strictly by
 *  utils/sliceThicknessReliability.parseGeometry before any use. */
export interface AcquisitionGeometry {
  state: string; // 'native' | 'at_least' | 'not_determinable'
  effective_mm?: number | null;
  source?: string; // 'dicom_header' | 'nifti_grid' | 'none'
  reason?: string | null;
  slice_thickness_mm?: number | null;
  spacing_between_slices_mm?: number | null;
  grid_spacing_mm?: number[] | null;
  mr_acquisition_type?: string | null;
  image_type?: string[] | null;
  method_version?: string;
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
