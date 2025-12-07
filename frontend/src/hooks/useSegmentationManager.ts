/**
 * Custom hook for managing segmentation state and operations
 * Encapsulates segmentation lifecycle: create, load, list, delete
 */

import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { segmentationAPI } from '@/api/segmentation';
import type {
  SegmentationResponse,
  SegmentationListItem,
  CreateSegmentationRequest,
  LabelInfo,
} from '@/types/segmentation';

interface UseSegmentationManagerProps {
  fileId?: string;
  enabled?: boolean;
}

export function useSegmentationManager({
  fileId,
  enabled = false,
}: UseSegmentationManagerProps) {
  const queryClient = useQueryClient();
  const [currentSegmentation, setCurrentSegmentation] =
    useState<SegmentationResponse | null>(null);

  // Query: List all segmentations for current file
  const {
    data: segmentations,
    isLoading: isLoadingList,
    refetch: refetchSegmentations,
  } = useQuery({
    queryKey: ['segmentations', fileId],
    queryFn: async (): Promise<SegmentationListItem[]> => {
      if (!fileId) return [];

      const response = await segmentationAPI.listSegmentations(fileId);

      // Transform to SegmentationListItem format
      return response.map((seg) => {
        // Defensive programming: ensure labels exists and is an array
        const labels = seg.metadata?.labels || [];
        const validLabels = Array.isArray(labels) ? labels : [];

        return {
          segmentation_id: seg.segmentation_id,
          file_id: seg.file_id,
          description: seg.metadata?.description || 'Sin descripción',
          created_at: seg.metadata?.created_at || new Date().toISOString(),
          modified_at: seg.metadata?.modified_at || new Date().toISOString(),
          total_slices: seg.total_slices || 0,
          label_count: validLabels.filter((l) => l.id !== 0).length,
          labels: validLabels,
        };
      });
    },
    enabled: enabled && !!fileId,
    staleTime: 30000, // 30 seconds
  });

  // Mutation: Create new segmentation
  const createSegmentationMutation = useMutation({
    mutationFn: (request: CreateSegmentationRequest) =>
      segmentationAPI.createSegmentation(request),
    onSuccess: (data) => {
      setCurrentSegmentation(data);
      queryClient.invalidateQueries({ queryKey: ['segmentations', fileId] });
    },
  });

  // Mutation: Load existing segmentation
  const loadSegmentationMutation = useMutation({
    mutationFn: async (segmentationId: string) => {
      const response = await segmentationAPI.getSegmentation(segmentationId);
      return response;
    },
    onSuccess: (data) => {
      setCurrentSegmentation(data);
    },
  });

  // Mutation: Delete segmentation
  const deleteSegmentationMutation = useMutation({
    mutationFn: (segmentationId: string) =>
      segmentationAPI.deleteSegmentation(segmentationId),
    onSuccess: () => {
      setCurrentSegmentation(null);
      queryClient.invalidateQueries({ queryKey: ['segmentations', fileId] });
    },
  });

  // Helper: Create new segmentation
  const createSegmentation = useCallback(
    (request: CreateSegmentationRequest) => {
      return createSegmentationMutation.mutateAsync(request);
    },
    [createSegmentationMutation]
  );

  // Helper: Load existing segmentation
  const loadSegmentation = useCallback(
    (segmentationId: string) => {
      return loadSegmentationMutation.mutateAsync(segmentationId);
    },
    [loadSegmentationMutation]
  );

  // Helper: Delete segmentation
  const deleteSegmentation = useCallback(
    (segmentationId: string) => {
      return deleteSegmentationMutation.mutateAsync(segmentationId);
    },
    [deleteSegmentationMutation]
  );

  // Helper: Clear current segmentation
  const clearSegmentation = useCallback(() => {
    setCurrentSegmentation(null);
  }, []);

  // Helper: Update label definitions
  const updateLabels = useCallback(
    async (segmentationId: string, labels: LabelInfo[]) => {
      await segmentationAPI.updateLabels(segmentationId, labels);

      // Refetch current segmentation to get updated metadata
      if (currentSegmentation?.segmentation_id === segmentationId) {
        const updated = await segmentationAPI.getSegmentation(segmentationId);
        setCurrentSegmentation(updated);
      }

      queryClient.invalidateQueries({ queryKey: ['segmentations', fileId] });
    },
    [currentSegmentation, fileId, queryClient]
  );

  return {
    // State
    currentSegmentation,
    segmentations,

    // Loading states
    isLoadingList,
    isCreating: createSegmentationMutation.isPending,
    isLoading: loadSegmentationMutation.isPending,
    isDeleting: deleteSegmentationMutation.isPending,

    // Actions
    createSegmentation,
    loadSegmentation,
    deleteSegmentation,
    clearSegmentation,
    updateLabels,
    refetchSegmentations,

    // Direct access to mutations for advanced usage
    createSegmentationMutation,
    loadSegmentationMutation,
    deleteSegmentationMutation,
  };
}
