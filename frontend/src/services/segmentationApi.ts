/**
 * Segmentation API Client.
 *
 * Provides type-safe access to the hierarchical segmentation API
 * with support for Patient → Study → Series → Segmentation hierarchy.
 *
 * @module services/segmentationApi
 */

import { apiClient } from './apiClient';
import type {
  Segmentation,
  SegmentationSummary,
  SegmentationListResponse,
  SegmentationCreate,
  SegmentationUpdate,
  SegmentationStatusUpdate,
  SegmentationStatistics,
  SegmentationComparisonRequest,
  SegmentationComparisonResponse,
  PaintStroke,
  PaintStrokeBatch,
  LabelInfo,
  LabelUpdate,
  OverlaySettings,
  ExportRequest,
  ExportResponse,
  SegmentationSearch,
} from '@/types';

const API_PREFIX = '/api/v1';

// ============================================================================
// Types for API Responses
// ============================================================================

interface PaintStrokeResponse {
  slice_index: number;
  modified_voxels: number;
  label_id: number;
}

interface PaintBatchResponse {
  total_modified_voxels: number;
  affected_slices: number[];
}

// ============================================================================
// CRUD Operations
// ============================================================================

/**
 * Create a new segmentation for a series.
 */
export async function createSegmentation(
  patientId: string,
  studyId: string,
  seriesId: string,
  data: SegmentationCreate
): Promise<Segmentation> {
  const response = await apiClient.post<Segmentation>(
    `${API_PREFIX}/patients/${patientId}/studies/${studyId}/series/${seriesId}/segmentations`,
    data
  );
  return response.data;
}

/**
 * Get a segmentation by ID.
 */
export async function getSegmentation(segmentationId: string): Promise<Segmentation> {
  const response = await apiClient.get<Segmentation>(
    `${API_PREFIX}/segmentations/${segmentationId}`
  );
  return response.data;
}

/**
 * Update segmentation metadata.
 */
export async function updateSegmentation(
  segmentationId: string,
  data: SegmentationUpdate
): Promise<Segmentation> {
  const response = await apiClient.patch<Segmentation>(
    `${API_PREFIX}/segmentations/${segmentationId}`,
    data
  );
  return response.data;
}

/**
 * Delete a segmentation.
 */
export async function deleteSegmentation(segmentationId: string): Promise<void> {
  await apiClient.delete(`${API_PREFIX}/segmentations/${segmentationId}`);
}

// ============================================================================
// List Operations (Hierarchical)
// ============================================================================

/**
 * List segmentations for a specific series.
 */
export async function listSegmentationsBySeries(
  patientId: string,
  studyId: string,
  seriesId: string,
  page = 1,
  pageSize = 20
): Promise<SegmentationListResponse> {
  const response = await apiClient.get<SegmentationListResponse>(
    `${API_PREFIX}/patients/${patientId}/studies/${studyId}/series/${seriesId}/segmentations`,
    {
      params: { page, page_size: pageSize },
    }
  );
  return response.data;
}

/**
 * List all segmentations for a study (across all series).
 */
export async function listSegmentationsByStudy(
  patientId: string,
  studyId: string,
  page = 1,
  pageSize = 20
): Promise<SegmentationListResponse> {
  const response = await apiClient.get<SegmentationListResponse>(
    `${API_PREFIX}/patients/${patientId}/studies/${studyId}/segmentations`,
    {
      params: { page, page_size: pageSize },
    }
  );
  return response.data;
}

/**
 * List all segmentations for a patient (across all studies).
 */
export async function listSegmentationsByPatient(
  patientId: string,
  page = 1,
  pageSize = 20
): Promise<SegmentationListResponse> {
  const response = await apiClient.get<SegmentationListResponse>(
    `${API_PREFIX}/patients/${patientId}/segmentations`,
    {
      params: { page, page_size: pageSize },
    }
  );
  return response.data;
}

/**
 * Search segmentations with multiple filters.
 */
export async function searchSegmentations(
  search: SegmentationSearch
): Promise<SegmentationListResponse> {
  const response = await apiClient.post<SegmentationListResponse>(
    `${API_PREFIX}/segmentations/search`,
    search
  );
  return response.data;
}

/**
 * Get segmentation count for a series (for UI indicators).
 */
export async function getSegmentationCountBySeries(
  seriesId: string
): Promise<{ count: number; has_approved: boolean; has_in_progress: boolean }> {
  const response = await apiClient.get<{
    count: number;
    has_approved: boolean;
    has_in_progress: boolean;
  }>(`${API_PREFIX}/series/${seriesId}/segmentation-count`);
  return response.data;
}

/**
 * Get segmentation count for a study (for UI indicators on StudyCard).
 * Uses the existing /segmentation/list endpoint with study_id filter.
 */
export async function getSegmentationCountByStudy(
  patientId: string,
  studyId: string
): Promise<{ count: number; has_approved: boolean; has_in_progress: boolean }> {
  try {
    // Use the existing /segmentation/list endpoint
    // Note: Currently filters by file_id, but we can use it to check if segmentations exist
    const response = await apiClient.get<Array<{ id: string; status?: string; study_id?: string }>>(
      `${API_PREFIX}/segmentation/list`
    );

    // Filter by study_id if available in the response
    const items = response.data || [];
    const studySegmentations = items.filter((s) => s.study_id === studyId);

    return {
      count: studySegmentations.length,
      has_approved: studySegmentations.some((s) => s.status === 'approved'),
      has_in_progress: studySegmentations.some((s) => s.status === 'in_progress'),
    };
  } catch {
    // Return empty data if endpoint fails (graceful degradation)
    return {
      count: 0,
      has_approved: false,
      has_in_progress: false,
    };
  }
}

// ============================================================================
// Status and Workflow
// ============================================================================

/**
 * Update segmentation status (workflow transition).
 */
export async function updateSegmentationStatus(
  segmentationId: string,
  status: SegmentationStatusUpdate
): Promise<Segmentation> {
  const response = await apiClient.patch<Segmentation>(
    `${API_PREFIX}/segmentations/${segmentationId}/status`,
    status
  );
  return response.data;
}

// ============================================================================
// Label Management
// ============================================================================

/**
 * Add a new label to segmentation.
 */
export async function addLabel(
  segmentationId: string,
  label: LabelInfo
): Promise<Segmentation> {
  const response = await apiClient.post<Segmentation>(
    `${API_PREFIX}/segmentations/${segmentationId}/labels`,
    label
  );
  return response.data;
}

/**
 * Update an existing label.
 */
export async function updateLabel(
  segmentationId: string,
  labelId: number,
  update: LabelUpdate
): Promise<Segmentation> {
  const response = await apiClient.patch<Segmentation>(
    `${API_PREFIX}/segmentations/${segmentationId}/labels/${labelId}`,
    update
  );
  return response.data;
}

/**
 * Remove a label from segmentation.
 */
export async function removeLabel(
  segmentationId: string,
  labelId: number
): Promise<Segmentation> {
  const response = await apiClient.delete<Segmentation>(
    `${API_PREFIX}/segmentations/${segmentationId}/labels/${labelId}`
  );
  return response.data;
}

// ============================================================================
// Paint Operations
// ============================================================================

/**
 * Apply a single paint stroke.
 */
export async function applyPaintStroke(
  segmentationId: string,
  stroke: PaintStroke
): Promise<PaintStrokeResponse> {
  const response = await apiClient.post<PaintStrokeResponse>(
    `${API_PREFIX}/segmentations/${segmentationId}/paint`,
    stroke
  );
  return response.data;
}

/**
 * Apply multiple paint strokes (batch).
 */
export async function applyPaintBatch(
  segmentationId: string,
  batch: PaintStrokeBatch
): Promise<PaintBatchResponse> {
  const response = await apiClient.post<PaintBatchResponse>(
    `${API_PREFIX}/segmentations/${segmentationId}/paint/batch`,
    batch
  );
  return response.data;
}

/**
 * Save segmentation to persistent storage.
 * Uses the v1 endpoint /api/v1/segmentation/{id}/save
 */
export async function saveSegmentation(segmentationId: string): Promise<Segmentation> {
  // Use v1 endpoint (singular "segmentation")
  const response = await apiClient.post<{ success: boolean; segmentation_id: string; message: string }>(
    `${API_PREFIX}/segmentation/${segmentationId}/save`
  );
  // Return a minimal Segmentation object compatible with the store
  return {
    id: segmentationId,
    // Other fields will be populated by the cache/store
  } as Segmentation;
}

// ============================================================================
// Overlay and Mask
// ============================================================================

/**
 * Get overlay image URL for a slice.
 * Returns a URL that can be used directly in an <img> tag.
 */
export function getSliceOverlayUrl(
  segmentationId: string,
  sliceIndex: number,
  settings?: OverlaySettings
): string {
  const params = new URLSearchParams({
    slice_index: sliceIndex.toString(),
  });

  if (settings) {
    if (settings.mode) params.append('mode', settings.mode);
    if (settings.global_opacity !== undefined)
      params.append('opacity', settings.global_opacity.toString());
    if (settings.outline_thickness !== undefined)
      params.append('outline_thickness', settings.outline_thickness.toString());
    if (settings.outline_only !== undefined)
      params.append('outline_only', settings.outline_only.toString());
    if (settings.visible_labels)
      params.append('visible_labels', settings.visible_labels.join(','));
  }

  const token = localStorage.getItem('access_token');
  const baseUrl = apiClient.defaults.baseURL || '';
  return `${baseUrl}${API_PREFIX}/segmentations/${segmentationId}/slices/${sliceIndex}/overlay?${params.toString()}&token=${token}`;
}

/**
 * Get overlay image as Blob.
 */
export async function getSliceOverlay(
  segmentationId: string,
  sliceIndex: number,
  settings?: OverlaySettings
): Promise<Blob> {
  const params: Record<string, any> = {
    slice_index: sliceIndex,
  };

  if (settings) {
    if (settings.mode) params.mode = settings.mode;
    if (settings.global_opacity !== undefined) params.opacity = settings.global_opacity;
    if (settings.outline_thickness !== undefined)
      params.outline_thickness = settings.outline_thickness;
    if (settings.outline_only !== undefined) params.outline_only = settings.outline_only;
    if (settings.visible_labels) params.visible_labels = settings.visible_labels.join(',');
  }

  const response = await apiClient.get(
    `${API_PREFIX}/segmentations/${segmentationId}/slices/${sliceIndex}/overlay`,
    {
      params,
      responseType: 'blob',
    }
  );
  return response.data;
}

/**
 * Get raw mask data for a slice (for canvas operations).
 */
export async function getSliceMask(
  segmentationId: string,
  sliceIndex: number
): Promise<ArrayBuffer> {
  const response = await apiClient.get(
    `${API_PREFIX}/segmentations/${segmentationId}/slices/${sliceIndex}/mask`,
    {
      responseType: 'arraybuffer',
    }
  );
  return response.data;
}

// ============================================================================
// Statistics and Analysis
// ============================================================================

/**
 * Get comprehensive statistics for a segmentation.
 */
export async function getSegmentationStatistics(
  segmentationId: string
): Promise<SegmentationStatistics> {
  const response = await apiClient.get<SegmentationStatistics>(
    `${API_PREFIX}/segmentations/${segmentationId}/statistics`
  );
  return response.data;
}

/**
 * Compare multiple segmentations (inter-rater agreement).
 */
export async function compareSegmentations(
  request: SegmentationComparisonRequest
): Promise<SegmentationComparisonResponse> {
  const response = await apiClient.post<SegmentationComparisonResponse>(
    `${API_PREFIX}/segmentations/compare`,
    request
  );
  return response.data;
}

// ============================================================================
// Export Operations
// ============================================================================

/**
 * Export segmentation to specified format.
 */
export async function exportSegmentation(
  segmentationId: string,
  request: ExportRequest
): Promise<ExportResponse> {
  const response = await apiClient.post<ExportResponse>(
    `${API_PREFIX}/segmentations/${segmentationId}/export`,
    request
  );
  return response.data;
}

/**
 * Download exported segmentation file.
 */
export async function downloadExport(downloadUrl: string): Promise<Blob> {
  const response = await apiClient.get(downloadUrl, {
    responseType: 'blob',
  });
  return response.data;
}

// ============================================================================
// Cache Management
// ============================================================================

/**
 * Load segmentation into memory cache for editing.
 */
export async function loadSegmentationIntoMemory(
  segmentationId: string
): Promise<{ loaded: boolean }> {
  const response = await apiClient.post<{ loaded: boolean }>(
    `${API_PREFIX}/segmentations/${segmentationId}/load`
  );
  return response.data;
}

/**
 * Unload segmentation from memory cache (auto-saves first).
 */
export async function unloadSegmentationFromMemory(
  segmentationId: string
): Promise<{ unloaded: boolean }> {
  const response = await apiClient.post<{ unloaded: boolean }>(
    `${API_PREFIX}/segmentations/${segmentationId}/unload`
  );
  return response.data;
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Generate a new label ID (finds first unused ID 1-255).
 */
export function generateNewLabelId(existingLabels: LabelInfo[]): number {
  const usedIds = new Set(existingLabels.map((l) => l.id));
  for (let i = 1; i <= 255; i++) {
    if (!usedIds.has(i)) return i;
  }
  throw new Error('Maximum label count (255) reached');
}

/**
 * Get default colors for new labels.
 */
export const DEFAULT_LABEL_COLORS = [
  '#FF0000', // Red
  '#00FF00', // Green
  '#0000FF', // Blue
  '#FFFF00', // Yellow
  '#FF00FF', // Magenta
  '#00FFFF', // Cyan
  '#FFA500', // Orange
  '#800080', // Purple
  '#008080', // Teal
  '#FFB6C1', // Light Pink
  '#90EE90', // Light Green
  '#ADD8E6', // Light Blue
];

/**
 * Get a color for a new label based on existing labels.
 */
export function getNextLabelColor(existingLabels: LabelInfo[]): string {
  const usedColors = new Set(existingLabels.map((l) => l.color.toUpperCase()));
  for (const color of DEFAULT_LABEL_COLORS) {
    if (!usedColors.has(color.toUpperCase())) return color;
  }
  // Generate random color if all defaults are used
  return `#${Math.floor(Math.random() * 16777215)
    .toString(16)
    .padStart(6, '0')
    .toUpperCase()}`;
}

export default {
  createSegmentation,
  getSegmentation,
  updateSegmentation,
  deleteSegmentation,
  listSegmentationsBySeries,
  listSegmentationsByStudy,
  listSegmentationsByPatient,
  searchSegmentations,
  getSegmentationCountBySeries,
  updateSegmentationStatus,
  addLabel,
  updateLabel,
  removeLabel,
  applyPaintStroke,
  applyPaintBatch,
  saveSegmentation,
  getSliceOverlayUrl,
  getSliceOverlay,
  getSliceMask,
  getSegmentationStatistics,
  compareSegmentations,
  exportSegmentation,
  downloadExport,
  loadSegmentationIntoMemory,
  unloadSegmentationFromMemory,
  generateNewLabelId,
  getNextLabelColor,
};
