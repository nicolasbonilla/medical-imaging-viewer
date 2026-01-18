/**
 * Segmentation Hooks - React Query hooks for segmentation operations.
 *
 * Provides data fetching with caching, optimistic updates, and
 * automatic refetching for the hierarchical segmentation system.
 *
 * @module hooks/useSegmentations
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect } from 'react';
import * as segmentationApi from '@/services/segmentationApi';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type {
  Segmentation,
  SegmentationSummary,
  SegmentationListResponse,
  SegmentationCreate,
  SegmentationUpdate,
  SegmentationStatusUpdate,
  SegmentationStatistics,
  SegmentationComparisonRequest,
  SegmentationComparisonResponse,
  PaintStroke,
  PaintStrokeBatch,
  LabelInfo,
  LabelUpdate,
  ExportRequest,
  ExportResponse,
  SegmentationSearch,
} from '@/types';

// ============================================================================
// Query Keys
// ============================================================================

export const segmentationKeys = {
  all: ['segmentations'] as const,

  // List queries
  lists: () => [...segmentationKeys.all, 'list'] as const,
  listBySeries: (patientId: string, studyId: string, seriesId: string) =>
    [...segmentationKeys.lists(), 'series', patientId, studyId, seriesId] as const,
  listByStudy: (patientId: string, studyId: string) =>
    [...segmentationKeys.lists(), 'study', patientId, studyId] as const,
  listByPatient: (patientId: string) =>
    [...segmentationKeys.lists(), 'patient', patientId] as const,
  search: (params: SegmentationSearch) =>
    [...segmentationKeys.lists(), 'search', params] as const,

  // Detail queries
  details: () => [...segmentationKeys.all, 'detail'] as const,
  detail: (id: string) => [...segmentationKeys.details(), id] as const,
  statistics: (id: string) => [...segmentationKeys.detail(id), 'statistics'] as const,

  // Count queries (for UI indicators)
  counts: () => [...segmentationKeys.all, 'count'] as const,
  countBySeries: (seriesId: string) =>
    [...segmentationKeys.counts(), 'series', seriesId] as const,
  countByStudy: (patientId: string, studyId: string) =>
    [...segmentationKeys.counts(), 'study', patientId, studyId] as const,

  // Comparison queries
  comparison: (ids: string[]) =>
    [...segmentationKeys.all, 'comparison', ids.sort().join('-')] as const,
};

// ============================================================================
// List Hooks
// ============================================================================

/**
 * Fetch segmentations for a specific series.
 */
export function useSegmentationsBySeries(
  patientId: string | undefined,
  studyId: string | undefined,
  seriesId: string | undefined,
  page = 1,
  pageSize = 20
) {
  return useQuery<SegmentationListResponse>({
    queryKey: segmentationKeys.listBySeries(patientId!, studyId!, seriesId!),
    queryFn: () =>
      segmentationApi.listSegmentationsBySeries(patientId!, studyId!, seriesId!, page, pageSize),
    enabled: !!patientId && !!studyId && !!seriesId,
    staleTime: 30000, // 30 seconds
  });
}

/**
 * Fetch all segmentations for a study (across series).
 */
export function useSegmentationsByStudy(
  patientId: string | undefined,
  studyId: string | undefined,
  page = 1,
  pageSize = 20
) {
  return useQuery<SegmentationListResponse>({
    queryKey: segmentationKeys.listByStudy(patientId!, studyId!),
    queryFn: () =>
      segmentationApi.listSegmentationsByStudy(patientId!, studyId!, page, pageSize),
    enabled: !!patientId && !!studyId,
    staleTime: 30000,
  });
}

/**
 * Fetch all segmentations for a patient (across studies).
 */
export function useSegmentationsByPatient(
  patientId: string | undefined,
  page = 1,
  pageSize = 20
) {
  return useQuery<SegmentationListResponse>({
    queryKey: segmentationKeys.listByPatient(patientId!),
    queryFn: () => segmentationApi.listSegmentationsByPatient(patientId!, page, pageSize),
    enabled: !!patientId,
    staleTime: 30000,
  });
}

/**
 * Search segmentations with filters.
 */
export function useSegmentationSearch(search: SegmentationSearch, enabled = true) {
  return useQuery<SegmentationListResponse>({
    queryKey: segmentationKeys.search(search),
    queryFn: () => segmentationApi.searchSegmentations(search),
    enabled: enabled && Object.keys(search).length > 0,
    staleTime: 30000,
  });
}

/**
 * Get segmentation count for a series (for UI badges).
 */
export function useSegmentationCount(seriesId: string | undefined) {
  return useQuery({
    queryKey: segmentationKeys.countBySeries(seriesId!),
    queryFn: () => segmentationApi.getSegmentationCountBySeries(seriesId!),
    enabled: !!seriesId,
    staleTime: 60000, // 1 minute
  });
}

/**
 * Get segmentation count for a study (for UI badges on StudyCard).
 */
export function useSegmentationCountByStudy(
  patientId: string | undefined,
  studyId: string | undefined
) {
  return useQuery({
    queryKey: segmentationKeys.countByStudy(patientId!, studyId!),
    queryFn: () => segmentationApi.getSegmentationCountByStudy(patientId!, studyId!),
    enabled: !!patientId && !!studyId,
    staleTime: 60000, // 1 minute
  });
}

// ============================================================================
// Detail Hooks
// ============================================================================

/**
 * Fetch a single segmentation by ID.
 */
export function useSegmentation(segmentationId: string | undefined) {
  const setActiveSegmentation = useSegmentationStore(
    (state) => state.setActiveSegmentation
  );

  const query = useQuery<Segmentation>({
    queryKey: segmentationKeys.detail(segmentationId!),
    queryFn: () => segmentationApi.getSegmentation(segmentationId!),
    enabled: !!segmentationId,
    staleTime: 30000,
  });

  // Update store when data changes (replaces onSuccess)
  useEffect(() => {
    if (query.data) {
      setActiveSegmentation(query.data);
    }
  }, [query.data, setActiveSegmentation]);

  return query;
}

/**
 * Fetch segmentation statistics.
 */
export function useSegmentationStatistics(segmentationId: string | undefined) {
  return useQuery<SegmentationStatistics>({
    queryKey: segmentationKeys.statistics(segmentationId!),
    queryFn: () => segmentationApi.getSegmentationStatistics(segmentationId!),
    enabled: !!segmentationId,
    staleTime: 60000,
  });
}

/**
 * Compare multiple segmentations.
 */
export function useSegmentationComparison(
  request: SegmentationComparisonRequest | undefined
) {
  return useQuery<SegmentationComparisonResponse>({
    queryKey: segmentationKeys.comparison(request?.segmentation_ids ?? []),
    queryFn: () => segmentationApi.compareSegmentations(request!),
    enabled: !!request && request.segmentation_ids.length >= 2,
    staleTime: 120000, // 2 minutes
  });
}

// ============================================================================
// Mutation Hooks
// ============================================================================

/**
 * Create a new segmentation.
 */
export function useCreateSegmentation() {
  const queryClient = useQueryClient();
  const setActiveSegmentation = useSegmentationStore(
    (state) => state.setActiveSegmentation
  );

  return useMutation({
    mutationFn: ({
      patientId,
      studyId,
      seriesId,
      data,
    }: {
      patientId: string;
      studyId: string;
      seriesId: string;
      data: SegmentationCreate;
    }) => segmentationApi.createSegmentation(patientId, studyId, seriesId, data),
    onSuccess: (data, variables) => {
      // Invalidate relevant lists
      queryClient.invalidateQueries({
        queryKey: segmentationKeys.listBySeries(
          variables.patientId,
          variables.studyId,
          variables.seriesId
        ),
      });
      queryClient.invalidateQueries({
        queryKey: segmentationKeys.listByStudy(variables.patientId, variables.studyId),
      });
      queryClient.invalidateQueries({
        queryKey: segmentationKeys.listByPatient(variables.patientId),
      });
      queryClient.invalidateQueries({
        queryKey: segmentationKeys.countBySeries(variables.seriesId),
      });

      // Set as active segmentation
      setActiveSegmentation(data);
    },
  });
}

/**
 * Update segmentation metadata.
 */
export function useUpdateSegmentation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      segmentationId,
      data,
    }: {
      segmentationId: string;
      data: SegmentationUpdate;
    }) => segmentationApi.updateSegmentation(segmentationId, data),
    onSuccess: (data) => {
      // Update cache
      queryClient.setQueryData(segmentationKeys.detail(data.id), data);
      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: segmentationKeys.lists() });
    },
  });
}

/**
 * Update segmentation status (workflow transition).
 */
export function useUpdateSegmentationStatus() {
  const queryClient = useQueryClient();
  const setActiveSegmentation = useSegmentationStore(
    (state) => state.setActiveSegmentation
  );

  return useMutation({
    mutationFn: ({
      segmentationId,
      status,
    }: {
      segmentationId: string;
      status: SegmentationStatusUpdate;
    }) => segmentationApi.updateSegmentationStatus(segmentationId, status),
    onSuccess: (data) => {
      queryClient.setQueryData(segmentationKeys.detail(data.id), data);
      queryClient.invalidateQueries({ queryKey: segmentationKeys.lists() });
      setActiveSegmentation(data);
    },
  });
}

/**
 * Delete a segmentation.
 */
export function useDeleteSegmentation() {
  const queryClient = useQueryClient();
  const setActiveSegmentation = useSegmentationStore(
    (state) => state.setActiveSegmentation
  );
  const activeSegmentation = useSegmentationStore((state) => state.activeSegmentation);

  return useMutation({
    mutationFn: (segmentationId: string) =>
      segmentationApi.deleteSegmentation(segmentationId),
    onSuccess: (_, segmentationId) => {
      // Remove from cache
      queryClient.removeQueries({
        queryKey: segmentationKeys.detail(segmentationId),
      });
      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: segmentationKeys.lists() });
      queryClient.invalidateQueries({ queryKey: segmentationKeys.counts() });

      // Clear active if it was the deleted one
      if (activeSegmentation?.id === segmentationId) {
        setActiveSegmentation(null);
      }
    },
  });
}

// ============================================================================
// Label Mutation Hooks
// ============================================================================

/**
 * Add a new label to segmentation.
 */
export function useAddLabel() {
  const queryClient = useQueryClient();
  const { addLabel } = useSegmentationStore();

  return useMutation({
    mutationFn: ({
      segmentationId,
      label,
    }: {
      segmentationId: string;
      label: LabelInfo;
    }) => segmentationApi.addLabel(segmentationId, label),
    onMutate: async ({ label }) => {
      // Optimistic update
      addLabel(label);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(segmentationKeys.detail(data.id), data);
    },
    onError: () => {
      // Revert on error - refetch
      queryClient.invalidateQueries({ queryKey: segmentationKeys.details() });
    },
  });
}

/**
 * Update a label.
 */
export function useUpdateLabel() {
  const queryClient = useQueryClient();
  const { updateLabel: updateLabelInStore } = useSegmentationStore();

  return useMutation({
    mutationFn: ({
      segmentationId,
      labelId,
      update,
    }: {
      segmentationId: string;
      labelId: number;
      update: LabelUpdate;
    }) => segmentationApi.updateLabel(segmentationId, labelId, update),
    onMutate: async ({ labelId, update }) => {
      updateLabelInStore(labelId, update);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(segmentationKeys.detail(data.id), data);
    },
  });
}

/**
 * Remove a label.
 */
export function useRemoveLabel() {
  const queryClient = useQueryClient();
  const { removeLabel: removeLabelFromStore } = useSegmentationStore();

  return useMutation({
    mutationFn: ({
      segmentationId,
      labelId,
    }: {
      segmentationId: string;
      labelId: number;
    }) => segmentationApi.removeLabel(segmentationId, labelId),
    onMutate: async ({ labelId }) => {
      removeLabelFromStore(labelId);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(segmentationKeys.detail(data.id), data);
      queryClient.invalidateQueries({
        queryKey: segmentationKeys.statistics(data.id),
      });
    },
  });
}

// ============================================================================
// Paint Mutation Hooks
// ============================================================================

/**
 * Apply paint stroke with debouncing.
 */
export function usePaintStroke() {
  const { addPendingStroke, setIsDirty } = useSegmentationStore();

  return useMutation({
    mutationFn: ({
      segmentationId,
      stroke,
    }: {
      segmentationId: string;
      stroke: PaintStroke;
    }) => segmentationApi.applyPaintStroke(segmentationId, stroke),
    onMutate: async ({ stroke }) => {
      addPendingStroke(stroke);
      setIsDirty(true);
    },
  });
}

/**
 * Apply batch of paint strokes (optimized for performance).
 */
export function usePaintBatch() {
  const queryClient = useQueryClient();
  const { clearPendingStrokes, setIsDirty } = useSegmentationStore();

  return useMutation({
    mutationFn: ({
      segmentationId,
      batch,
    }: {
      segmentationId: string;
      batch: PaintStrokeBatch;
    }) => segmentationApi.applyPaintBatch(segmentationId, batch),
    onSuccess: (_, variables) => {
      clearPendingStrokes();
      // Invalidate statistics after painting
      queryClient.invalidateQueries({
        queryKey: segmentationKeys.statistics(variables.segmentationId),
      });
    },
  });
}

/**
 * Save segmentation to persistent storage.
 */
export function useSaveSegmentation() {
  const queryClient = useQueryClient();
  const { setIsDirty, setIsSaving, setLastSavedAt, setActiveSegmentation } =
    useSegmentationStore();

  return useMutation({
    mutationFn: (segmentationId: string) =>
      segmentationApi.saveSegmentation(segmentationId),
    onMutate: () => {
      setIsSaving(true);
    },
    onSuccess: (data) => {
      setIsDirty(false);
      setIsSaving(false);
      setLastSavedAt(new Date().toISOString());
      setActiveSegmentation(data);
      queryClient.setQueryData(segmentationKeys.detail(data.id), data);
      queryClient.invalidateQueries({ queryKey: segmentationKeys.lists() });
    },
    onError: () => {
      setIsSaving(false);
    },
  });
}

// ============================================================================
// Export Mutation Hooks
// ============================================================================

/**
 * Export segmentation to file.
 */
export function useExportSegmentation() {
  return useMutation({
    mutationFn: ({
      segmentationId,
      request,
    }: {
      segmentationId: string;
      request: ExportRequest;
    }) => segmentationApi.exportSegmentation(segmentationId, request),
  });
}

// ============================================================================
// Utility Hooks
// ============================================================================

/**
 * Load segmentation into memory for editing.
 */
export function useLoadSegmentationIntoMemory() {
  return useMutation({
    mutationFn: (segmentationId: string) =>
      segmentationApi.loadSegmentationIntoMemory(segmentationId),
  });
}

/**
 * Unload segmentation from memory (auto-saves).
 */
export function useUnloadSegmentationFromMemory() {
  const { setActiveSegmentation, reset } = useSegmentationStore();

  return useMutation({
    mutationFn: (segmentationId: string) =>
      segmentationApi.unloadSegmentationFromMemory(segmentationId),
    onSuccess: () => {
      setActiveSegmentation(null);
      reset();
    },
  });
}

/**
 * Custom hook for managing the full segmentation editing workflow.
 */
export function useSegmentationEditor(segmentationId: string | undefined) {
  const queryClient = useQueryClient();
  const store = useSegmentationStore();

  const { data: segmentation, isLoading } = useSegmentation(segmentationId);
  const { data: statistics } = useSegmentationStatistics(segmentationId);
  const { mutateAsync: saveAsync, isPending: isSaving } = useSaveSegmentation();
  const { mutateAsync: paintBatchAsync } = usePaintBatch();

  const save = useCallback(async () => {
    if (!segmentationId) return;

    // First flush pending strokes
    const pendingStrokes = store.flushPendingStrokes();
    if (pendingStrokes.length > 0) {
      await paintBatchAsync({
        segmentationId,
        batch: { strokes: pendingStrokes },
      });
    }

    // Then save to storage
    await saveAsync(segmentationId);
  }, [segmentationId, store, paintBatchAsync, saveAsync]);

  const close = useCallback(async () => {
    if (!segmentationId) return;

    // Auto-save if dirty
    if (store.isDirty) {
      await save();
    }

    // Unload from memory
    await segmentationApi.unloadSegmentationFromMemory(segmentationId);

    // Reset store
    store.reset();
  }, [segmentationId, store, save]);

  return {
    segmentation,
    statistics,
    isLoading,
    isSaving,
    isDirty: store.isDirty,
    save,
    close,
    // Paint tools
    paintTool: store.paintTool,
    setPaintTool: store.setPaintTool,
    setBrushSize: store.setBrushSize,
    // Labels
    activeLabel: store.activeLabel,
    setActiveLabel: store.setActiveLabel,
    labels: (segmentation?.labels as LabelInfo[]) ?? [],
    // Overlay
    overlaySettings: store.overlaySettings,
    isOverlayVisible: store.isOverlayVisible,
    setGlobalOpacity: store.setGlobalOpacity,
    toggleOverlayVisibility: store.toggleOverlayVisibility,
    // Undo/Redo
    canUndo: store.canUndo(),
    canRedo: store.canRedo(),
    undo: store.undo,
    redo: store.redo,
  };
}

export default {
  segmentationKeys,
  useSegmentationsBySeries,
  useSegmentationsByStudy,
  useSegmentationsByPatient,
  useSegmentationSearch,
  useSegmentationCount,
  useSegmentationCountByStudy,
  useSegmentation,
  useSegmentationStatistics,
  useSegmentationComparison,
  useCreateSegmentation,
  useUpdateSegmentation,
  useUpdateSegmentationStatus,
  useDeleteSegmentation,
  useAddLabel,
  useUpdateLabel,
  useRemoveLabel,
  usePaintStroke,
  usePaintBatch,
  useSaveSegmentation,
  useExportSegmentation,
  useLoadSegmentationIntoMemory,
  useUnloadSegmentationFromMemory,
  useSegmentationEditor,
};
