/**
 * API client for AI report generation.
 *
 * Uses the shared apiClient (inherits auth token, refresh, error handling).
 *
 * @module api/aiReport
 */

import { apiClient } from '@/services/apiClient';
import type {
  ReportGenerateRequest,
  ReportResponse,
  ReportTemplateInfo,
} from '@/types';

const API_PREFIX = '/api/v1/ai/report';

export const aiReportAPI = {
  /**
   * Generate a structured brain MRI report using Claude API.
   * HIPAA compliant: only de-identified findings are sent.
   */
  async generateReport(request: ReportGenerateRequest): Promise<ReportResponse> {
    const response = await apiClient.post<ReportResponse>(
      `${API_PREFIX}/generate`,
      request
    );
    return response.data;
  },

  /**
   * List available report templates.
   */
  async listTemplates(): Promise<ReportTemplateInfo[]> {
    const response = await apiClient.get<ReportTemplateInfo[]>(
      `${API_PREFIX}/templates`
    );
    return response.data;
  },
};
