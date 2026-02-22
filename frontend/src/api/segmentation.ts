/**
 * API client for segmentation operations
 */

import { apiClient } from '@/services/apiClient';
import type {
  CreateSegmentationRequest,
  SegmentationResponse,
  PaintStroke,
  LabelInfo,
  OverlayImageResponse,
  LesionAnalysisResult,
  DISAssessment,
  LongitudinalResult,
  RegionClassificationResult,
  ClassificationMethod,
  ZoneMapResult,
} from '@/types';

const API_PREFIX = '/api/v1';

export const segmentationAPI = {
  /**
   * Create a new segmentation for a file
   */
  async createSegmentation(request: CreateSegmentationRequest): Promise<SegmentationResponse> {
    const response = await apiClient.post<SegmentationResponse>(
      `${API_PREFIX}/segmentation/create`,
      request
    );
    return response.data;
  },

  /**
   * List all segmentations, optionally filtered by file_id
   */
  async listSegmentations(fileId?: string): Promise<SegmentationResponse[]> {
    const params = fileId ? { file_id: fileId } : {};
    const response = await apiClient.get<SegmentationResponse[]>(
      `${API_PREFIX}/segmentation/list`,
      { params }
    );
    return response.data;
  },

  /**
   * List segmentations across multiple file_ids (study-level query)
   */
  async listSegmentationsByFileIds(fileIds: string[]): Promise<SegmentationResponse[]> {
    if (fileIds.length === 0) return [];
    const response = await apiClient.get<SegmentationResponse[]>(
      `${API_PREFIX}/segmentation/list`,
      { params: { file_ids: fileIds.join(',') } }
    );
    return response.data;
  },

  /**
   * Get segmentation by ID
   */
  async getSegmentation(segmentationId: string): Promise<SegmentationResponse> {
    const response = await apiClient.get<SegmentationResponse>(
      `${API_PREFIX}/segmentation/${segmentationId}`
    );
    return response.data;
  },

  /**
   * Apply a paint stroke to the segmentation
   */
  async applyPaintStroke(segmentationId: string, stroke: PaintStroke): Promise<void> {
    await apiClient.post(`${API_PREFIX}/segmentation/${segmentationId}/paint`, stroke);
  },

  /**
   * Get overlay image (base image + segmentation mask)
   */
  async getOverlayImage(
    segmentationId: string,
    sliceIndex: number,
    options?: {
      windowCenter?: number;
      windowWidth?: number;
      colormap?: string;
      showLabels?: number[];
    }
  ): Promise<OverlayImageResponse> {
    const params: Record<string, unknown> = {};
    if (options?.windowCenter !== undefined) params.window_center = options.windowCenter;
    if (options?.windowWidth !== undefined) params.window_width = options.windowWidth;
    if (options?.colormap) params.colormap = options.colormap;
    if (options?.showLabels) params.show_labels = options.showLabels.join(',');

    const response = await apiClient.get<OverlayImageResponse>(
      `${API_PREFIX}/segmentation/${segmentationId}/slice/${sliceIndex}/overlay`,
      { params }
    );
    return response.data;
  },

  /**
   * Update label definitions
   */
  async updateLabels(segmentationId: string, labels: LabelInfo[]): Promise<void> {
    await apiClient.put(`${API_PREFIX}/segmentation/${segmentationId}/labels`, labels);
  },

  /**
   * Delete a segmentation
   */
  async deleteSegmentation(segmentationId: string): Promise<void> {
    await apiClient.delete(`${API_PREFIX}/segmentation/${segmentationId}`);
  },

  /**
   * Save segmentation to persistent storage (Firestore + GCS)
   * Should be called when changing slices or when user explicitly saves
   */
  async saveSegmentation(segmentationId: string): Promise<{ success: boolean; message: string }> {
    const response = await apiClient.post<{ success: boolean; message: string }>(
      `${API_PREFIX}/segmentation/${segmentationId}/save`
    );
    return response.data;
  },

  /**
   * Compare 2+ masks (segmentation or expert instance).
   * Returns pairwise Dice, Hausdorff, volume diff, and per-slice Dice.
   */
  async compareMasks(masks: { type: 'segmentation' | 'instance'; id: string; label: string }[]): Promise<ComparisonResult> {
    const response = await apiClient.post<ComparisonResult>(
      `${API_PREFIX}/segmentation/compare`,
      { masks }
    );
    return response.data;
  },

  /**
   * Analyze lesions using connected components.
   * Returns per-lesion stats, region summary, total burden, DIS info.
   */
  async analyzeLesions(segmentationId: string): Promise<LesionAnalysisResult> {
    const response = await apiClient.get<LesionAnalysisResult>(
      `${API_PREFIX}/segmentation/${segmentationId}/lesion-analysis`
    );
    return response.data;
  },

  /**
   * Evaluate McDonald 2024 DIS criteria for a segmentation.
   */
  async getDISAssessment(segmentationId: string): Promise<DISAssessment> {
    const response = await apiClient.get<DISAssessment>(
      `${API_PREFIX}/segmentation/${segmentationId}/dis-assessment`
    );
    return response.data;
  },

  /**
   * Compare lesion masks from two timepoints.
   * Returns per-lesion changes and burden delta.
   */
  async compareLongitudinal(
    tp1: { type: 'segmentation' | 'instance'; id: string },
    tp2: { type: 'segmentation' | 'instance'; id: string },
  ): Promise<LongitudinalResult> {
    const response = await apiClient.post<LongitudinalResult>(
      `${API_PREFIX}/segmentation/longitudinal/compare`,
      { tp1, tp2 }
    );
    return response.data;
  },

  /**
   * Auto-classify lesions into MAGNIMS regions (PV, JC, IT, DWM).
   * Uses brain parcellation + EDT for high accuracy when available,
   * falls back to geometric heuristics otherwise.
   * The segmentation mask is reclassified in-place on the server.
   */
  async classifyRegions(
    segmentationId: string,
    options?: { parcellationId?: string; method?: ClassificationMethod },
  ): Promise<RegionClassificationResult> {
    const response = await apiClient.post<RegionClassificationResult>(
      `${API_PREFIX}/segmentation/${segmentationId}/classify-regions`,
      {
        parcellation_id: options?.parcellationId,
        method: options?.method ?? 'auto',
      },
    );
    return response.data;
  },

  /**
   * Get voxel-wise agreement map across N masks.
   * Returns binary data: [D:4][H:4][W:4][count:4][agreement:D*H*W bytes]
   */
  async getAgreementMap(masks: { type: 'segmentation' | 'instance'; id: string }[]): Promise<{
    data: Uint8Array;
    depth: number;
    height: number;
    width: number;
    maskCount: number;
  }> {
    const response = await apiClient.post(
      `${API_PREFIX}/segmentation/agreement-map`,
      { masks },
      { responseType: 'arraybuffer' }
    );
    const buffer = response.data as ArrayBuffer;
    const view = new DataView(buffer);
    const depth = view.getUint32(0, true);
    const height = view.getUint32(4, true);
    const width = view.getUint32(8, true);
    const maskCount = view.getUint32(12, true);
    const data = new Uint8Array(buffer, 16);
    return { data, depth, height, width, maskCount };
  },

  /**
   * Generate a MAGNIMS zone map for a brain MRI.
   * Creates a new segmentation where every brain voxel is classified into
   * PV / JC / IT / DWM zones using parcellation + EDT.
   */
  async generateZoneMap(
    fileId: string,
    parcellationId?: string,
  ): Promise<ZoneMapResult> {
    const response = await apiClient.post<ZoneMapResult>(
      `${API_PREFIX}/segmentation/generate-zone-map`,
      { file_id: fileId, parcellation_id: parcellationId },
    );
    return response.data;
  },
};

/** Comparison result types */
export interface PairwiseComparison {
  label_a: string;
  label_b: string;
  dice: number;
  hausdorff_mm: number | null;
  volume: {
    volume_a_mm3: number;
    volume_b_mm3: number;
    diff_mm3: number;
    diff_percent: number;
  };
  per_slice_dice: number[];
}

export interface ComparisonResult {
  comparisons: PairwiseComparison[];
  mask_count: number;
}
