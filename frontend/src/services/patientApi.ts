import { apiClient } from './apiClient';
import type {
  Patient,
  PatientCreate,
  PatientUpdate,
  PatientListResponse,
  MedicalHistory,
  MedicalHistoryCreate,
  PatientStatus,
  Gender,
} from '@/types';

export interface PatientSearchParams {
  query?: string;
  mrn?: string;
  family_name?: string;
  given_name?: string;
  gender?: Gender;
  status?: PatientStatus;
  city?: string;
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export const patientAPI = {
  // Create a new patient
  create: async (data: PatientCreate): Promise<Patient> => {
    const { data: response } = await apiClient.post('/api/v1/patients', data);
    return response;
  },

  // Get patient by ID
  getById: async (patientId: string, includeStats = true): Promise<Patient> => {
    const { data } = await apiClient.get(`/api/v1/patients/${patientId}`, {
      params: { include_stats: includeStats },
    });
    return data;
  },

  // Get patient by MRN
  getByMrn: async (mrn: string): Promise<Patient> => {
    const { data } = await apiClient.get(`/api/v1/patients/by-mrn/${mrn}`);
    return data;
  },

  // List patients with pagination
  list: async (
    page = 1,
    pageSize = 20,
    status?: PatientStatus
  ): Promise<PatientListResponse> => {
    const { data } = await apiClient.get('/api/v1/patients', {
      params: {
        page,
        page_size: pageSize,
        status,
      },
    });
    return data;
  },

  // Search patients
  search: async (params: PatientSearchParams): Promise<PatientListResponse> => {
    const { data } = await apiClient.get('/api/v1/patients/search', {
      params: {
        query: params.query,
        mrn: params.mrn,
        family_name: params.family_name,
        given_name: params.given_name,
        gender: params.gender,
        status: params.status,
        city: params.city,
        page: params.page || 1,
        page_size: params.page_size || 20,
        sort_by: params.sort_by || 'family_name',
        sort_order: params.sort_order || 'asc',
      },
    });
    return data;
  },

  // Update patient
  update: async (patientId: string, data: PatientUpdate): Promise<Patient> => {
    const { data: response } = await apiClient.put(`/api/v1/patients/${patientId}`, data);
    return response;
  },

  // Delete (deactivate) patient
  delete: async (patientId: string): Promise<void> => {
    await apiClient.delete(`/api/v1/patients/${patientId}`);
  },

  // Medical History
  addMedicalHistory: async (
    patientId: string,
    data: MedicalHistoryCreate
  ): Promise<MedicalHistory> => {
    const { data: response } = await apiClient.post(
      `/api/v1/patients/${patientId}/history`,
      data
    );
    return response;
  },

  getMedicalHistory: async (
    patientId: string,
    activeOnly = false
  ): Promise<MedicalHistory[]> => {
    const { data } = await apiClient.get(`/api/v1/patients/${patientId}/history`, {
      params: { active_only: activeOnly },
    });
    return data;
  },

  updateMedicalHistory: async (
    historyId: string,
    isActive: boolean,
    resolutionDate?: string
  ): Promise<MedicalHistory> => {
    const { data } = await apiClient.patch(`/api/v1/patients/history/${historyId}`, null, {
      params: {
        is_active: isActive,
        resolution_date: resolutionDate,
      },
    });
    return data;
  },
};

export default patientAPI;
