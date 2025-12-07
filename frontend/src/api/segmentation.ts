/**
 * API client for segmentation operations
 */

import axios from 'axios';
import type {
  CreateSegmentationRequest,
  SegmentationResponse,
  PaintStroke,
  LabelInfo,
  OverlayImageResponse,
} from '../types/segmentation';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const API_V1 = `${API_BASE_URL}/api/v1`;

export const segmentationAPI = {
  /**
   * Create a new segmentation for a file
   */
  async createSegmentation(request: CreateSegmentationRequest): Promise<SegmentationResponse> {
    const response = await axios.post<SegmentationResponse>(
      `${API_V1}/segmentation/create`,
      request
    );
    return response.data;
  },

  /**
   * List all segmentations, optionally filtered by file_id
   */
  async listSegmentations(fileId?: string): Promise<SegmentationResponse[]> {
    const params = fileId ? { file_id: fileId } : {};
    const response = await axios.get<SegmentationResponse[]>(
      `${API_V1}/segmentation/list`,
      { params }
    );
    return response.data;
  },

  /**
   * Get segmentation by ID
   */
  async getSegmentation(segmentationId: string): Promise<SegmentationResponse> {
    const response = await axios.get<SegmentationResponse>(
      `${API_V1}/segmentation/${segmentationId}`
    );
    return response.data;
  },

  /**
   * Apply a paint stroke to the segmentation
   */
  async applyPaintStroke(segmentationId: string, stroke: PaintStroke): Promise<void> {
    await axios.post(`${API_V1}/segmentation/${segmentationId}/paint`, stroke);
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
    const params: any = {};
    if (options?.windowCenter !== undefined) params.window_center = options.windowCenter;
    if (options?.windowWidth !== undefined) params.window_width = options.windowWidth;
    if (options?.colormap) params.colormap = options.colormap;
    if (options?.showLabels) params.show_labels = options.showLabels.join(',');

    const response = await axios.get<OverlayImageResponse>(
      `${API_V1}/segmentation/${segmentationId}/slice/${sliceIndex}/overlay`,
      { params }
    );
    return response.data;
  },

  /**
   * Update label definitions
   */
  async updateLabels(segmentationId: string, labels: LabelInfo[]): Promise<void> {
    await axios.put(`${API_V1}/segmentation/${segmentationId}/labels`, labels);
  },

  /**
   * Delete a segmentation
   */
  async deleteSegmentation(segmentationId: string): Promise<void> {
    await axios.delete(`${API_V1}/segmentation/${segmentationId}`);
  },
};
