/**
 * useAISegmentation - Orchestrator hook for AI brain segmentation.
 *
 * Handles:
 * - Interactive segmentation: accumulate clicks → send to backend → load mask
 * - Auto segmentation: trigger → poll task → load mask
 * - Result integration with useSegmentationMask (same mask format as manual)
 *
 * @module hooks/useAISegmentation
 */

import { useCallback } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useAIStore } from '@/store/useAIStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { aiSegmentationAPI } from '@/api/aiSegmentation';
import { segmentationAPI } from '@/api/segmentation';
import type { ClickPoint3D, AITaskResult } from '@/types';

interface UseAISegmentationOptions {
  fileId: string | undefined;
  currentSliceIndex: number;
}

export function useAISegmentation({ fileId, currentSliceIndex }: UseAISegmentationOptions) {
  const {
    aiMode,
    clickPoints,
    selectedModel,
    isProcessing,
    taskId,
    progress,
    error,
    setAIMode,
    addClickPoint,
    removeLastClick,
    clearClicks,
    setProcessing,
    setTaskId,
    setProgress,
    setLastResult,
    setError,
    reset: resetAI,
  } = useAIStore();

  const setCurrentSegmentation = useSegmentationStore((s) => s.setCurrentSegmentation);

  // Poll task status when we have a taskId
  const { data: taskStatus } = useQuery({
    queryKey: ['ai-task', taskId],
    queryFn: () => aiSegmentationAPI.getTaskStatus(taskId!),
    enabled: !!taskId && isProcessing,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.status === 'completed' || data?.status === 'failed') return false;
      return 2000; // Poll every 2 seconds
    },
  });

  // When task completes, load the resulting segmentation
  if (taskStatus?.status === 'completed' && taskStatus.segmentation_id && isProcessing) {
    setProcessing(false);
    setProgress(100);
    setLastResult(taskStatus);
    setTaskId(null);

    // Load the AI-generated segmentation as current
    segmentationAPI.getSegmentation(taskStatus.segmentation_id).then((seg) => {
      setCurrentSegmentation(seg);
    }).catch((err) => {
      setError(`Failed to load AI result: ${err.message}`);
    });
  }

  if (taskStatus?.status === 'failed' && isProcessing) {
    setProcessing(false);
    setError(taskStatus.error || 'AI task failed');
    setTaskId(null);
    setLastResult(taskStatus);
  }

  if (taskStatus?.progress && isProcessing) {
    setProgress(taskStatus.progress);
  }

  // Interactive segmentation mutation
  const interactiveMutation = useMutation({
    mutationFn: () => {
      if (!fileId) throw new Error('No file selected');
      return aiSegmentationAPI.segmentInteractive({
        file_id: fileId,
        click_points: clickPoints,
        model: selectedModel,
      });
    },
    onMutate: () => {
      setProcessing(true);
      setError(null);
      setProgress(10);
    },
    onSuccess: (result: AITaskResult) => {
      if (result.status === 'completed' && result.segmentation_id) {
        // Immediate result — load it
        setProcessing(false);
        setProgress(100);
        setLastResult(result);
        segmentationAPI.getSegmentation(result.segmentation_id).then((seg) => {
          setCurrentSegmentation(seg);
        });
      } else if (result.status === 'failed') {
        setProcessing(false);
        setError(result.error || 'Interactive segmentation failed');
        setLastResult(result);
      } else {
        // Async task — start polling
        setTaskId(result.task_id);
      }
    },
    onError: (err: Error) => {
      setProcessing(false);
      setError(err.message);
    },
  });

  // Auto segmentation mutation
  const autoMutation = useMutation({
    mutationFn: () => {
      if (!fileId) throw new Error('No file selected');
      return aiSegmentationAPI.segmentAuto({
        file_id: fileId,
        model: selectedModel,
      });
    },
    onMutate: () => {
      setProcessing(true);
      setError(null);
      setProgress(10);
    },
    onSuccess: (result: AITaskResult) => {
      if (result.status === 'completed' && result.segmentation_id) {
        setProcessing(false);
        setProgress(100);
        setLastResult(result);
        segmentationAPI.getSegmentation(result.segmentation_id).then((seg) => {
          setCurrentSegmentation(seg);
        });
      } else if (result.status === 'failed') {
        setProcessing(false);
        setError(result.error || 'Auto segmentation failed');
        setLastResult(result);
      } else {
        setTaskId(result.task_id);
      }
    },
    onError: (err: Error) => {
      setProcessing(false);
      setError(err.message);
    },
  });

  // Add a click point at the current slice position
  const handleCanvasClick = useCallback(
    (x: number, y: number, isPositive: boolean) => {
      if (aiMode !== 'interactive') return;
      const point: ClickPoint3D = {
        x,
        y,
        z: currentSliceIndex,
        label: isPositive ? 'positive' : 'negative',
      };
      addClickPoint(point);
    },
    [aiMode, currentSliceIndex, addClickPoint]
  );

  // Run the segmentation based on current mode
  const runSegmentation = useCallback(() => {
    if (aiMode === 'interactive') {
      if (clickPoints.length === 0) {
        setError('Add at least one click point');
        return;
      }
      interactiveMutation.mutate();
    } else if (aiMode === 'auto') {
      autoMutation.mutate();
    }
  }, [aiMode, clickPoints.length, interactiveMutation, autoMutation, setError]);

  // Cancel current operation
  const cancelAI = useCallback(() => {
    setProcessing(false);
    setTaskId(null);
    setProgress(0);
    setError(null);
  }, [setProcessing, setTaskId, setProgress, setError]);

  return {
    // State
    aiMode,
    clickPoints,
    selectedModel,
    isProcessing,
    progress,
    error,

    // Actions
    setAIMode,
    handleCanvasClick,
    removeLastClick,
    clearClicks,
    runSegmentation,
    cancelAI,
    resetAI,
    setSelectedModel: useAIStore.getState().setSelectedModel,
  };
}
