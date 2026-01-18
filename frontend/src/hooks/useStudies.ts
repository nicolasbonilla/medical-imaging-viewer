import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { studyAPI } from '@/services/studyApi';
import type {
  ImagingStudy,
  StudyCreate,
  StudyUpdate,
  StudyListResponse,
  ImagingSeries,
  ImagingInstance,
} from '@/types';

// Query keys
export const studyKeys = {
  all: ['studies'] as const,
  lists: () => [...studyKeys.all, 'list'] as const,
  list: (params: { page?: number; pageSize?: number; status?: string }) =>
    [...studyKeys.lists(), params] as const,
  search: (params: Record<string, unknown>) =>
    [...studyKeys.all, 'search', params] as const,
  details: () => [...studyKeys.all, 'detail'] as const,
  detail: (id: string) => [...studyKeys.details(), id] as const,
  byAccession: (accession: string) =>
    [...studyKeys.all, 'accession', accession] as const,
  byPatient: (patientId: string, params?: { page?: number; pageSize?: number }) =>
    [...studyKeys.all, 'patient', patientId, params] as const,
  series: (studyId: string) => [...studyKeys.detail(studyId), 'series'] as const,
  seriesDetail: (seriesId: string) =>
    [...studyKeys.all, 'series', seriesId] as const,
  instances: (seriesId: string) =>
    [...studyKeys.seriesDetail(seriesId), 'instances'] as const,
  instanceDetail: (instanceId: string) =>
    [...studyKeys.all, 'instance', instanceId] as const,
};

/**
 * Hook to fetch paginated list of studies
 */
export function useStudyList(
  page: number = 1,
  pageSize: number = 20,
  status?: string
) {
  return useQuery<StudyListResponse>({
    queryKey: studyKeys.list({ page, pageSize, status }),
    queryFn: () => studyAPI.list(page, pageSize, status),
  });
}

/**
 * Hook to search studies with filters
 */
export function useStudySearch(params: {
  patient_id?: string;
  modality?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}) {
  return useQuery<StudyListResponse>({
    queryKey: studyKeys.search(params),
    queryFn: () => studyAPI.search(params),
    enabled: Object.keys(params).length > 0,
  });
}

/**
 * Hook to fetch studies for a specific patient
 */
export function usePatientStudies(
  patientId: string | undefined,
  page: number = 1,
  pageSize: number = 20
) {
  return useQuery<StudyListResponse>({
    queryKey: studyKeys.byPatient(patientId!, { page, pageSize }),
    queryFn: () => studyAPI.listByPatient(patientId!, page, pageSize),
    enabled: !!patientId,
  });
}

/**
 * Hook to fetch a single study by ID
 */
export function useStudy(studyId: string | undefined, includeStats: boolean = true) {
  return useQuery<ImagingStudy>({
    queryKey: studyKeys.detail(studyId!),
    queryFn: () => studyAPI.getById(studyId!, includeStats),
    enabled: !!studyId,
  });
}

/**
 * Hook to fetch a study by accession number
 */
export function useStudyByAccession(accessionNumber: string | undefined) {
  return useQuery<ImagingStudy | null>({
    queryKey: studyKeys.byAccession(accessionNumber!),
    queryFn: () => studyAPI.getByAccession(accessionNumber!),
    enabled: !!accessionNumber,
  });
}

/**
 * Hook to fetch series for a study
 */
export function useStudySeries(studyId: string | undefined) {
  return useQuery<ImagingSeries[]>({
    queryKey: studyKeys.series(studyId!),
    queryFn: () => studyAPI.listSeries(studyId!),
    enabled: !!studyId,
  });
}

/**
 * Hook to fetch a specific series
 */
export function useSeries(seriesId: string | undefined) {
  return useQuery<ImagingSeries>({
    queryKey: studyKeys.seriesDetail(seriesId!),
    queryFn: () => studyAPI.getSeries(seriesId!),
    enabled: !!seriesId,
  });
}

/**
 * Hook to fetch instances for a series
 */
export function useSeriesInstances(seriesId: string | undefined) {
  return useQuery<ImagingInstance[]>({
    queryKey: studyKeys.instances(seriesId!),
    queryFn: () => studyAPI.listInstances(seriesId!),
    enabled: !!seriesId,
  });
}

/**
 * Hook to fetch a specific instance
 */
export function useInstance(instanceId: string | undefined) {
  return useQuery<ImagingInstance>({
    queryKey: studyKeys.instanceDetail(instanceId!),
    queryFn: () => studyAPI.getInstance(instanceId!),
    enabled: !!instanceId,
  });
}

/**
 * Hook to create a new study
 */
export function useCreateStudy() {
  const queryClient = useQueryClient();

  return useMutation<ImagingStudy, Error, StudyCreate>({
    mutationFn: (data) => studyAPI.create(data),
    onSuccess: (study) => {
      // Invalidate study lists
      queryClient.invalidateQueries({ queryKey: studyKeys.lists() });
      // Invalidate patient's study list
      queryClient.invalidateQueries({
        queryKey: studyKeys.byPatient(study.patient_id),
      });
    },
  });
}

/**
 * Hook to update a study
 */
export function useUpdateStudy() {
  const queryClient = useQueryClient();

  return useMutation<ImagingStudy, Error, { id: string; data: StudyUpdate }>({
    mutationFn: ({ id, data }) => studyAPI.update(id, data),
    onSuccess: (study) => {
      // Update the study in cache
      queryClient.setQueryData(studyKeys.detail(study.id), study);
      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: studyKeys.lists() });
    },
  });
}

/**
 * Hook to delete a study
 */
export function useDeleteStudy() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, { id: string; patientId: string; hardDelete?: boolean }>({
    mutationFn: ({ id, hardDelete }) => studyAPI.delete(id, hardDelete),
    onSuccess: (_, { id, patientId }) => {
      // Remove from cache
      queryClient.removeQueries({ queryKey: studyKeys.detail(id) });
      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: studyKeys.lists() });
      // Invalidate patient's study list
      queryClient.invalidateQueries({ queryKey: studyKeys.byPatient(patientId) });
    },
  });
}

/**
 * Hook to delete a series
 */
export function useDeleteSeries() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, { seriesId: string; studyId: string }>({
    mutationFn: ({ seriesId }) => studyAPI.deleteSeries(seriesId),
    onSuccess: (_, { seriesId, studyId }) => {
      // Remove from cache
      queryClient.removeQueries({ queryKey: studyKeys.seriesDetail(seriesId) });
      // Invalidate study's series list
      queryClient.invalidateQueries({ queryKey: studyKeys.series(studyId) });
      // Invalidate study detail (counts change)
      queryClient.invalidateQueries({ queryKey: studyKeys.detail(studyId) });
    },
  });
}

/**
 * Hook to delete an instance
 */
export function useDeleteInstance() {
  const queryClient = useQueryClient();

  return useMutation<
    void,
    Error,
    { instanceId: string; seriesId: string; studyId: string }
  >({
    mutationFn: ({ instanceId }) => studyAPI.deleteInstance(instanceId),
    onSuccess: (_, { instanceId, seriesId, studyId }) => {
      // Remove from cache
      queryClient.removeQueries({ queryKey: studyKeys.instanceDetail(instanceId) });
      // Invalidate series instances
      queryClient.invalidateQueries({ queryKey: studyKeys.instances(seriesId) });
      // Invalidate series detail (counts change)
      queryClient.invalidateQueries({ queryKey: studyKeys.seriesDetail(seriesId) });
      // Invalidate study detail (counts change)
      queryClient.invalidateQueries({ queryKey: studyKeys.detail(studyId) });
    },
  });
}
