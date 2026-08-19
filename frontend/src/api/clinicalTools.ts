import { apiClient } from '@/services/apiClient';
import type { ClinicalToolInfo, ToolTaskResult } from '@/types';

const PREFIX = '/api/v1/clinical';

export const clinicalToolsAPI = {
  async listTools(): Promise<ClinicalToolInfo[]> {
    const response = await apiClient.get(`${PREFIX}/tools`);
    return response.data;
  },

  async runLSTAI(
    t1FileId: string,
    flairFileId: string,
    patientId?: string,
    studyId?: string,
  ): Promise<ToolTaskResult> {
    const response = await apiClient.post(`${PREFIX}/lst-ai/segment`, {
      t1_file_id: t1FileId,
      flair_file_id: flairFileId,
      patient_id: patientId,
      study_id: studyId,
    });
    return response.data;
  },

  async runFLAMeS(
    flairFileId: string,
    patientId?: string,
    studyId?: string,
  ): Promise<ToolTaskResult> {
    const response = await apiClient.post(`${PREFIX}/flames/segment`, {
      flair_file_id: flairFileId,
      patient_id: patientId,
      study_id: studyId,
    });
    return response.data;
  },

  async runSynthSeg(
    fileId: string,
    patientId?: string,
    studyId?: string,
  ): Promise<ToolTaskResult> {
    const response = await apiClient.post(`${PREFIX}/synthseg/parcellate`, {
      file_id: fileId,
      patient_id: patientId,
      study_id: studyId,
    });
    return response.data;
  },

  async getTaskStatus(taskId: string): Promise<ToolTaskResult> {
    const response = await apiClient.get(`${PREFIX}/task/${taskId}`);
    return response.data;
  },

  async getTaskResult(taskId: string): Promise<{
    task: ToolTaskResult;
    validation: {
      source: string;
      citation: string;
      fda_status: string;
      disclaimer: string;
    };
  }> {
    const response = await apiClient.get(`${PREFIX}/task/${taskId}/result`);
    return response.data;
  },
};
