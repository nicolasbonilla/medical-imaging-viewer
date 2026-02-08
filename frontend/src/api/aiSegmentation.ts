/**
 * API client for AI segmentation operations.
 *
 * Uses the shared apiClient (inherits auth token, refresh, error handling).
 *
 * @module api/aiSegmentation
 */

import { apiClient } from '@/services/apiClient';
import type {
  InteractiveSegmentRequest,
  AutoSegmentRequest,
  AITaskResult,
  AnomalyDetectionResult,
  AIModelInfo,
  VolumetryResult,
  VolumetryRequest,
  VolumetryComparisonResult,
} from '@/types';

const API_PREFIX = '/api/v1/ai';

export const aiSegmentationAPI = {
  /**
   * Run interactive segmentation from click points.
   * Returns a task result (may be completed immediately or need polling).
   */
  async segmentInteractive(request: InteractiveSegmentRequest): Promise<AITaskResult> {
    const response = await apiClient.post<AITaskResult>(
      `${API_PREFIX}/segment/interactive`,
      request
    );
    return response.data;
  },

  /**
   * Run automatic brain structure segmentation (SynthSeg).
   * Returns a task result for polling.
   */
  async segmentAuto(request: AutoSegmentRequest): Promise<AITaskResult> {
    const response = await apiClient.post<AITaskResult>(
      `${API_PREFIX}/segment/auto`,
      request
    );
    return response.data;
  },

  /**
   * Detect brain anomalies (tumors, lesions, hemorrhages).
   */
  async detectAnomalies(fileId: string, sensitivity: string = 'medium'): Promise<AnomalyDetectionResult> {
    const response = await apiClient.post<AnomalyDetectionResult>(
      `${API_PREFIX}/anomaly/detect`,
      { file_id: fileId, sensitivity }
    );
    return response.data;
  },

  /**
   * Poll the status of an async AI task.
   */
  async getTaskStatus(taskId: string): Promise<AITaskResult> {
    const response = await apiClient.get<AITaskResult>(
      `${API_PREFIX}/segment/${taskId}/status`
    );
    return response.data;
  },

  /**
   * List available AI models and their configuration status.
   */
  async listModels(): Promise<AIModelInfo[]> {
    const response = await apiClient.get<AIModelInfo[]>(
      `${API_PREFIX}/models`
    );
    return response.data;
  },

  /**
   * Compute brain volumetry from a segmentation mask.
   * Returns per-structure volumes in mm3 and mL with normative comparison.
   */
  async computeVolumetry(request: VolumetryRequest): Promise<VolumetryResult> {
    const response = await apiClient.post<VolumetryResult>(
      `${API_PREFIX}/volumetry/compute`,
      request
    );
    return response.data;
  },

  /**
   * Compare brain volumes across multiple timepoints (longitudinal tracking).
   */
  async compareVolumetry(
    patientId: string,
    timepoints: Array<{ study_id: string; date: string; structures: Array<{ label_id: number; volume_ml: number }> }>,
  ): Promise<VolumetryComparisonResult> {
    const response = await apiClient.post<VolumetryComparisonResult>(
      `${API_PREFIX}/volumetry/compare`,
      { patient_id: patientId, timepoints }
    );
    return response.data;
  },
};
