/**
 * Types for segmentation functionality (ITK-SNAP style)
 */

export interface LabelInfo {
  id: number;
  name: string;
  color: string; // Hex color code
  opacity: number; // 0.0 to 1.0
  visible: boolean;
}

export interface SegmentationMetadata {
  file_id: string;
  created_at: string;
  modified_at: string;
  labels: LabelInfo[];
  description?: string;
}

export interface PaintStroke {
  slice_index: number;
  label_id: number;
  x: number;
  y: number;
  brush_size: number;
  erase: boolean;
}

export interface SegmentationResponse {
  segmentation_id: string;
  file_id: string;
  metadata: SegmentationMetadata;
  total_slices: number;
}

export interface ImageShape {
  rows: number;
  columns: number;
  slices: number;
}

export interface CreateSegmentationRequest {
  file_id: string;
  image_shape: ImageShape;
  description?: string;
  labels?: LabelInfo[];
}

export interface OverlayImageResponse {
  slice_index: number;
  overlay_image: string; // Base64 encoded image
}

/**
 * Extended segmentation info for listing
 */
export interface SegmentationListItem {
  segmentation_id: string;
  file_id: string;
  description?: string;
  created_at: string;
  modified_at: string;
  total_slices: number;
  label_count: number;
  labels: LabelInfo[];
}

/**
 * Load existing segmentation request
 */
export interface LoadSegmentationRequest {
  segmentation_id: string;
}
