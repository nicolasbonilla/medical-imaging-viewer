import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { patientAPI, type PatientSearchParams } from '@/services/patientApi';
import type {
  Patient,
  PatientCreate,
  PatientUpdate,
  PatientListResponse,
  MedicalHistory,
  MedicalHistoryCreate,
  Gender,
  PatientStatus
} from '@/types';

// Query keys
export const patientKeys = {
  all: ['patients'] as const,
  lists: () => [...patientKeys.all, 'list'] as const,
  list: (params: { page?: number; pageSize?: number; status?: string }) =>
    [...patientKeys.lists(), params] as const,
  search: (query: string, params?: Record<string, unknown>) =>
    [...patientKeys.all, 'search', query, params] as const,
  details: () => [...patientKeys.all, 'detail'] as const,
  detail: (id: string) => [...patientKeys.details(), id] as const,
  byMrn: (mrn: string) => [...patientKeys.all, 'mrn', mrn] as const,
  history: (patientId: string) => [...patientKeys.detail(patientId), 'history'] as const,
};

/**
 * Hook to fetch paginated list of patients
 */
export function usePatientList(
  page: number = 1,
  pageSize: number = 20,
  status?: PatientStatus
) {
  return useQuery<PatientListResponse>({
    queryKey: patientKeys.list({ page, pageSize, status }),
    queryFn: () => patientAPI.list(page, pageSize, status),
  });
}

/**
 * Hook to search patients
 */
export function usePatientSearch(
  query: string,
  params?: {
    family_name?: string;
    given_name?: string;
    birth_date?: string;
    gender?: Gender;
    status?: PatientStatus;
    page?: number;
    page_size?: number;
  }
) {
  const searchParams: PatientSearchParams = {
    query,
    ...params,
  };

  return useQuery<PatientListResponse>({
    queryKey: patientKeys.search(query, params),
    queryFn: () => patientAPI.search(searchParams),
    enabled: query.length >= 2 || Object.keys(params || {}).length > 0,
  });
}

/**
 * Hook to fetch a single patient by ID
 */
export function usePatient(patientId: string | undefined, includeStats: boolean = true) {
  return useQuery<Patient>({
    queryKey: patientKeys.detail(patientId!),
    queryFn: () => patientAPI.getById(patientId!, includeStats),
    enabled: !!patientId,
  });
}

/**
 * Hook to fetch a patient by MRN
 */
export function usePatientByMrn(mrn: string | undefined) {
  return useQuery<Patient | null>({
    queryKey: patientKeys.byMrn(mrn!),
    queryFn: () => patientAPI.getByMrn(mrn!),
    enabled: !!mrn,
  });
}

/**
 * Hook to fetch patient medical history
 */
export function useMedicalHistory(patientId: string | undefined, activeOnly: boolean = false) {
  return useQuery<MedicalHistory[]>({
    queryKey: patientKeys.history(patientId!),
    queryFn: () => patientAPI.getMedicalHistory(patientId!, activeOnly),
    enabled: !!patientId,
  });
}

/**
 * Hook to create a new patient
 */
export function useCreatePatient() {
  const queryClient = useQueryClient();

  return useMutation<Patient, Error, PatientCreate>({
    mutationFn: (data) => patientAPI.create(data),
    onSuccess: () => {
      // Invalidate and refetch patient lists
      queryClient.invalidateQueries({ queryKey: patientKeys.lists() });
    },
  });
}

/**
 * Hook to update a patient
 */
export function useUpdatePatient() {
  const queryClient = useQueryClient();

  return useMutation<Patient, Error, { id: string; data: PatientUpdate }>({
    mutationFn: ({ id, data }) => patientAPI.update(id, data),
    onSuccess: (patient) => {
      // Update the patient in cache
      queryClient.setQueryData(patientKeys.detail(patient.id), patient);
      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: patientKeys.lists() });
    },
  });
}

/**
 * Hook to delete (deactivate) a patient
 */
export function useDeletePatient() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (id) => patientAPI.delete(id),
    onSuccess: (_, patientId) => {
      // Remove from cache
      queryClient.removeQueries({ queryKey: patientKeys.detail(patientId) });
      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: patientKeys.lists() });
    },
  });
}

/**
 * Hook to add medical history entry
 */
export function useAddMedicalHistory() {
  const queryClient = useQueryClient();

  return useMutation<MedicalHistory, Error, { patientId: string; data: MedicalHistoryCreate }>({
    mutationFn: ({ patientId, data }) => patientAPI.addMedicalHistory(patientId, data),
    onSuccess: (_, { patientId }) => {
      // Invalidate medical history
      queryClient.invalidateQueries({ queryKey: patientKeys.history(patientId) });
    },
  });
}

/**
 * Hook to update medical history entry
 */
export function useUpdateMedicalHistory() {
  const queryClient = useQueryClient();

  return useMutation<
    MedicalHistory,
    Error,
    { historyId: string; patientId: string; isActive: boolean; resolutionDate?: string }
  >({
    mutationFn: ({ historyId, isActive, resolutionDate }) =>
      patientAPI.updateMedicalHistory(historyId, isActive, resolutionDate),
    onSuccess: (_, { patientId }) => {
      // Invalidate medical history
      queryClient.invalidateQueries({ queryKey: patientKeys.history(patientId) });
    },
  });
}
