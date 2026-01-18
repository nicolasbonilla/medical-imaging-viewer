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
} from '../types/segmentation';

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
};
