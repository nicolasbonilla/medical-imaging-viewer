/**
 * Hook for managing segmentation data queries and mutations.
 * Handles fetching segmentation lists, applying paint strokes, and auto-saving.
 *
 * IMPORTANT: Auto-save runs in background to avoid blocking UI.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef, useCallback, useEffect, useState } from 'react';
import { segmentationAPI } from '@/api/segmentation';
import { useViewerStore } from '@/store/useViewerStore';
import type { SegmentationResponse, PaintStroke, ImageShape } from '../types/segmentation';

interface UseSegmentationDataProps {
  currentSegmentation: SegmentationResponse | null;
  setCurrentSegmentation: (seg: SegmentationResponse | null) => void;
  /** Called when a paint stroke completes - receives the slice index for cache management */
  onPaintComplete?: (sliceIndex: number) => void;
}

// Track if there are unsaved changes (module-level for persistence)
let hasUnsavedChanges = false;

// Debounce timer for auto-save
let autoSaveTimer: NodeJS.Timeout | null = null;

export function useSegmentationData({
  currentSegmentation,
  setCurrentSegmentation,
  onPaintComplete,
}: UseSegmentationDataProps) {
  const { currentSeries } = useViewerStore();
  const queryClient = useQueryClient();

  // State for save status feedback
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [lastSaveTime, setLastSaveTime] = useState<Date | null>(null);

  // Use ref to keep stable reference to setCurrentSegmentation
  const setCurrentSegmentationRef = useRef(setCurrentSegmentation);
  setCurrentSegmentationRef.current = setCurrentSegmentation;

  // Ref for current segmentation to avoid stale closures
  const currentSegmentationRef = useRef(currentSegmentation);
  currentSegmentationRef.current = currentSegmentation;

  // Fetch segmentations list
  const { data: segmentations } = useQuery({
    queryKey: ['segmentations', currentSeries?.file_id],
    queryFn: () =>
      currentSeries?.file_id
        ? segmentationAPI.listSegmentations(currentSeries.file_id)
        : Promise.resolve([]),
    enabled: !!currentSeries?.file_id,
  });

  // Create segmentation mutation
  const createSegmentationMutation = useMutation({
    mutationFn: async ({
      fileId,
      imageShape,
    }: {
      fileId: string;
      imageShape: ImageShape;
    }) => {
      console.log('🎨 Creating segmentation with:', { fileId, imageShape });
      const result = await segmentationAPI.createSegmentation({
        file_id: fileId,
        image_shape: imageShape,
        labels: [
          { id: 0, name: 'Background', color: '#000000', opacity: 0.0, visible: false },
          { id: 1, name: 'Lesion', color: '#FF0000', opacity: 0.5, visible: true },
        ],
      });
      console.log('🎨 API response:', result);
      return result;
    },
    onSuccess: (data) => {
      console.log('✅ Segmentation created successfully:', data);
      console.log('✅ Calling setCurrentSegmentation with data');
      // Use ref to ensure we have the latest setCurrentSegmentation function
      setCurrentSegmentationRef.current(data);
      queryClient.invalidateQueries({ queryKey: ['segmentations'] });
    },
    onError: (error) => {
      console.error('❌ Failed to create segmentation:', error);
      // Log more details about the error
      if (error instanceof Error) {
        console.error('❌ Error message:', error.message);
        console.error('❌ Error stack:', error.stack);
      }
    },
  });

  // Stable function to create segmentation
  const createSegmentation = useCallback((fileId: string, imageShape: ImageShape) => {
    console.log('🚀 createSegmentation called with:', { fileId, imageShape });
    createSegmentationMutation.mutate({ fileId, imageShape });
  }, [createSegmentationMutation]);

  // Paint stroke mutation
  // IMPORTANT: Each paint stroke is saved to GCS immediately by the backend
  // On success, we notify the caller with the slice_index so they can clear local cache
  const paintStrokeMutation = useMutation({
    mutationFn: async (stroke: PaintStroke) => {
      if (!currentSegmentation) {
        throw new Error('No active segmentation');
      }
      // Return both the API response and the stroke info for onSuccess
      const response = await segmentationAPI.applyPaintStroke(currentSegmentation.segmentation_id, stroke);
      return { response, sliceIndex: stroke.slice_index };
    },
    onSuccess: (data) => {
      hasUnsavedChanges = true;
      // Pass the slice index to the callback so the canvas can clear its local paint cache
      onPaintComplete?.(data.sliceIndex);
      console.log(`✅ Paint stroke saved to server for slice ${data.sliceIndex}`);
    },
    onError: (error, variables) => {
      // On error, keep local paints as backup
      console.error(`❌ Failed to save paint stroke for slice ${variables.slice_index}:`, error);
    },
  });

  // Save segmentation mutation (non-blocking with status feedback)
  const saveSegmentationMutation = useMutation({
    mutationFn: async (segmentationId: string) => {
      console.log('💾 Saving segmentation:', segmentationId);
      setSaveStatus('saving');
      return segmentationAPI.saveSegmentation(segmentationId);
    },
    onSuccess: (data) => {
      console.log('✅ Segmentation saved:', data.message);
      hasUnsavedChanges = false;
      setSaveStatus('saved');
      setLastSaveTime(new Date());
      // Reset status after 3 seconds
      setTimeout(() => setSaveStatus('idle'), 3000);
    },
    onError: (error) => {
      console.error('❌ Failed to save segmentation:', error);
      setSaveStatus('error');
      // Reset status after 5 seconds
      setTimeout(() => setSaveStatus('idle'), 5000);
    },
  });

  // Stable function to save segmentation
  const saveSegmentation = useCallback(async () => {
    if (!currentSegmentation) {
      console.log('⚠️ No active segmentation to save');
      return;
    }
    if (!hasUnsavedChanges) {
      console.log('ℹ️ No unsaved changes to save');
      return;
    }
    saveSegmentationMutation.mutate(currentSegmentation.segmentation_id);
  }, [currentSegmentation, saveSegmentationMutation]);

  // Auto-save when slice changes (DEBOUNCED and NON-BLOCKING)
  const { currentSliceIndex } = useViewerStore();
  const previousSliceRef = useRef<number>(currentSliceIndex);

  useEffect(() => {
    if (previousSliceRef.current !== currentSliceIndex && currentSegmentationRef.current && hasUnsavedChanges) {
      // Clear existing timer
      if (autoSaveTimer) {
        clearTimeout(autoSaveTimer);
      }

      // Debounce auto-save by 300ms to avoid blocking rapid slice changes
      autoSaveTimer = setTimeout(() => {
        const segId = currentSegmentationRef.current?.segmentation_id;
        if (segId && hasUnsavedChanges) {
          console.log('🔄 Auto-saving segmentation in background...');
          // Fire and forget - don't await, don't block UI
          segmentationAPI.saveSegmentation(segId)
            .then((data) => {
              console.log('✅ Auto-save complete:', data.message);
              hasUnsavedChanges = false;
              setSaveStatus('saved');
              setLastSaveTime(new Date());
              setTimeout(() => setSaveStatus('idle'), 2000);
            })
            .catch((err) => {
              console.error('❌ Auto-save failed:', err);
              setSaveStatus('error');
              setTimeout(() => setSaveStatus('idle'), 3000);
            });
        }
      }, 300);
    }
    previousSliceRef.current = currentSliceIndex;

    // Cleanup timer on unmount
    return () => {
      if (autoSaveTimer) {
        clearTimeout(autoSaveTimer);
      }
    };
  }, [currentSliceIndex]);

  // Auto-save before unload
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (currentSegmentation && hasUnsavedChanges) {
        // Try to save (best effort - may not complete before unload)
        segmentationAPI.saveSegmentation(currentSegmentation.segmentation_id)
          .catch(err => console.error('Failed to save on unload:', err));
        // Show browser warning
        e.preventDefault();
        e.returnValue = '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [currentSegmentation]);

  return {
    segmentations,
    createSegmentationMutation,
    createSegmentation,
    paintStrokeMutation,
    saveSegmentation,
    saveSegmentationMutation,
    hasUnsavedChanges,
    isCreatingSegmentation: createSegmentationMutation.isPending,
    isSaving: saveSegmentationMutation.isPending,
    // New: save status for UI feedback
    saveStatus,
    lastSaveTime,
  };
}
