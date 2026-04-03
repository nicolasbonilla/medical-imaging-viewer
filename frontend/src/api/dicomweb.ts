/**
 * DICOMweb PACS Integration API Client.
 *
 * Provides connection management, QIDO-RS study/series search,
 * and WADO-RS import with job tracking.
 *
 * @module api/dicomweb
 */

import { apiClient } from '@/services/apiClient';
import type {
  PACSConnection,
  PACSConnectionCreate,
  DICOMwebStudyResult,
  DICOMwebSeriesResult,
  DICOMwebImportRequest,
  DICOMwebImportJob,
} from '@/types';

const PREFIX = '/api/v1/dicomweb';

export const dicomwebAPI = {
  // ─── Connection CRUD ───

  async listConnections(): Promise<PACSConnection[]> {
    const { data } = await apiClient.get(`${PREFIX}/connections`);
    return data;
  },

  async createConnection(config: PACSConnectionCreate): Promise<PACSConnection> {
    const { data } = await apiClient.post(`${PREFIX}/connections`, config);
    return data;
  },

  async getConnection(connectionId: string): Promise<PACSConnection> {
    const { data } = await apiClient.get(`${PREFIX}/connections/${connectionId}`);
    return data;
  },

  async deleteConnection(connectionId: string): Promise<void> {
    await apiClient.delete(`${PREFIX}/connections/${connectionId}`);
  },

  async testConnection(connectionId: string): Promise<{ success: boolean; message: string }> {
    const { data } = await apiClient.post(`${PREFIX}/connections/${connectionId}/test`);
    return data;
  },

  // ─── QIDO-RS Search ───

  async searchStudies(params: {
    connection_id: string;
    patient_name?: string;
    patient_id?: string;
    study_date?: string;
    modality?: string;
    accession_number?: string;
    limit?: number;
  }): Promise<DICOMwebStudyResult[]> {
    const { data } = await apiClient.post(`${PREFIX}/search/studies`, params);
    return data;
  },

  async searchSeries(connectionId: string, studyUid: string): Promise<DICOMwebSeriesResult[]> {
    const { data } = await apiClient.post(`${PREFIX}/search/series`, null, {
      params: { connection_id: connectionId, study_instance_uid: studyUid },
    });
    return data;
  },

  // ─── WADO-RS Import ───

  async startImport(request: DICOMwebImportRequest): Promise<{ job_id: string }> {
    const { data } = await apiClient.post(`${PREFIX}/import`, request);
    return data;
  },

  async getImportStatus(jobId: string): Promise<DICOMwebImportJob> {
    const { data } = await apiClient.get(`${PREFIX}/import/${jobId}`);
    return data;
  },

  async listImports(): Promise<DICOMwebImportJob[]> {
    const { data } = await apiClient.get(`${PREFIX}/imports`);
    return data;
  },
};
