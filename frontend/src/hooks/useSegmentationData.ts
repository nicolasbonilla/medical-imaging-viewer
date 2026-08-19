/**
 * Hook for managing segmentation data - ITK-SNAP Style Architecture
 *
 * KEY ARCHITECTURAL CHANGE:
 * - OLD: Each paint stroke makes an API call → slow, unreliable
 * - NEW: All painting happens locally in memory → instant, save only on demand
 *
 * This matches how professional tools like ITK-SNAP work.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useCallback, useEffect, useState } from 'react';
import { segmentationAPI } from '@/api/segmentation';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { useSegmentationMask, type LocalPaintStroke } from './useSegmentationMask';
import type { PaintStroke, ImageShape, Segmentation, SegmentationResponse } from '@/types';

interface UseSegmentationDataProps {
  /** Called when a paint stroke completes - receives the slice index for cache management */
  onPaintComplete?: (sliceIndex: number) => void;
}

export function useSegmentationData({
  onPaintComplete,
}: UseSegmentationDataProps) {
  const { currentSeries, currentStudyId, allFileIds } = useViewerStore();
  const queryClient = useQueryClient();

  // Read currentSegmentation from Zustand (single source of truth)
  const currentSegmentation = useSegmentationStore((s) => s.currentSegmentation);
  const setCurrentSegmentation = useSegmentationStore((s) => s.setCurrentSegmentation);

  // ITK-SNAP style mask management
  const segmentationMask = useSegmentationMask();

  // State for save status feedback
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [lastSaveTime, setLastSaveTime] = useState<Date | null>(null);

  // Ref for current segmentation to avoid stale closures
  const currentSegmentationRef = useRef(currentSegmentation);
  currentSegmentationRef.current = currentSegmentation;

  // Flag to skip loadMask when transitioning from local-ID to server-ID after save
  const skipNextLoadRef = useRef(false);

  // Load mask when segmentation changes (skip local-only — mask is already initialized)
  useEffect(() => {
    if (!currentSegmentation?.segmentation_id) {
      segmentationMask.clearMask();
    } else if (!currentSegmentation.segmentation_id.startsWith('local-')) {
      if (skipNextLoadRef.current) {
        // After save: mask is already in memory, skip redundant server fetch
        skipNextLoadRef.current = false;
        return;
      }
      segmentationMask.loadMask(currentSegmentation.segmentation_id);
    }
    // local- IDs already have an empty mask initialized by createSegmentation
  }, [currentSegmentation?.segmentation_id]);

  // Sync currentSegmentation → Zustand activeSegmentation so the panel shows paint tools.
  // Re-runs when mask loading completes (annotatedVoxels changes) to show real progress.
  const annotatedVoxels = segmentationMask.state.annotatedVoxels;
  const maskDimensions = segmentationMask.state.dimensions;

  // The mask id last fully seeded into activeSegmentation. A same-id re-fire (progress
  // recomputed after load/save) must NOT re-seed — that path resets the user's active
  // label + per-label visibility and drops label-preset edits (adversarially verified
  // data-loss bug). Only a genuinely NEW mask re-seeds.
  const lastSyncedIdRef = useRef<string | null>(null);

  useEffect(() => {
    const store = useSegmentationStore.getState();
    if (currentSegmentation) {
      // Compute actual annotated slice count from mask data
      let slicesAnnotated = 0;
      const totalSlices = currentSegmentation.total_slices;
      if (segmentationMask.isLoaded && maskDimensions) {
        const { height, width } = maskDimensions;
        const sliceSize = height * width;
        for (let s = 0; s < totalSlices; s++) {
          const slice = segmentationMask.getSliceMask(s);
          if (slice) {
            for (let i = 0; i < sliceSize; i++) {
              if (slice[i] > 0) { slicesAnnotated++; break; }
            }
          }
        }
      }
      const progressPct = totalSlices > 0 ? Math.round((slicesAnnotated / totalSlices) * 100) : 0;

      const segId = currentSegmentation.segmentation_id;
      const sameMask = store.activeSegmentation != null && lastSyncedIdRef.current === segId;

      if (sameMask) {
        // Progress-only update — preserve activeLabel / labelVisibility / label edits.
        store.updateActiveSegmentationProgress({
          slices_annotated: slicesAnnotated,
          total_slices: totalSlices,
          progress_percentage: progressPct,
        });
      } else {
        // New mask: full seed (this legitimately (re)sets the active label + visibility).
        const labels = currentSegmentation.metadata?.labels || [
          { id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
          { id: 1, name: 'Lesion', color: '#FF0000', opacity: 0.5, visible: true },
        ];
        const synced: Segmentation = {
          id: segId,
          patient_id: '',
          study_id: '',
          series_id: currentSeries?.file_id || '',
          file_id: currentSegmentation.file_id,
          name: currentSegmentation.metadata?.description || 'Segmentation',
          segmentation_type: 'manual' as Segmentation['segmentation_type'],
          status: 'in_progress' as Segmentation['status'],
          progress_percentage: progressPct,
          slices_annotated: slicesAnnotated,
          total_slices: totalSlices,
          created_by: 'current_user',
          labels,
          created_at: currentSegmentation.metadata?.created_at || new Date().toISOString(),
          modified_at: currentSegmentation.metadata?.modified_at || new Date().toISOString(),
        };
        store.setActiveSegmentation(synced);
        lastSyncedIdRef.current = segId;
      }
    } else {
      // Only clear if Zustand still holds a segmentation from this flow
      if (store.activeSegmentation) {
        store.setActiveSegmentation(null);
      }
      lastSyncedIdRef.current = null;
    }
  }, [currentSegmentation, currentSeries?.file_id, annotatedVoxels, maskDimensions]);

  // Fetch segmentations list for ALL images in the study
  const { data: segmentations } = useQuery({
    queryKey: ['segmentations', 'study', currentStudyId],
    queryFn: () =>
      allFileIds.length > 0
        ? segmentationAPI.listSegmentationsByFileIds(allFileIds)
        : Promise.resolve([]),
    enabled: allFileIds.length > 0,
  });

  // Default labels for new segmentations
  const defaultLabels = [
    { id: 0, name: 'Background', color: '#000000', opacity: 0.0, visible: false },
    { id: 1, name: 'Lesion', color: '#FF0000', opacity: 0.5, visible: true },
  ];

  // Create segmentation LOCALLY (no server call until Save)
  const createSegmentation = useCallback((fileId: string, imageShape: ImageShape) => {
    const tempId = `local-${crypto.randomUUID()}`;
    const now = new Date().toISOString();

    const localSeg: SegmentationResponse = {
      segmentation_id: tempId,
      file_id: fileId,
      total_slices: imageShape.slices,
      metadata: {
        file_id: fileId,
        description: 'Segmentation',
        labels: defaultLabels,
        created_at: now,
        modified_at: now,
      },
    };

    setCurrentSegmentation(localSeg);
    // Initialize empty mask in memory (no network)
    segmentationMask.initEmptyMask(imageShape.slices, imageShape.rows, imageShape.columns);
  }, [setCurrentSegmentation, segmentationMask]);

  // Placeholder for backward compatibility (no longer an actual mutation)
  const createSegmentationMutation = {
    mutate: ({ fileId, imageShape }: { fileId: string; imageShape: ImageShape }) =>
      createSegmentation(fileId, imageShape),
    isPending: false,
    isError: false,
    error: null,
  };

  /**
   * Apply paint stroke LOCALLY (instant, no network!)
   *
   * This is the key change from the old architecture.
   * The stroke is applied to the in-memory mask immediately.
   * No API call is made. The mask is only saved when the user clicks "Save".
   */
  const applyPaintStrokeLocal = useCallback((stroke: PaintStroke) => {
    const localStroke: LocalPaintStroke = {
      x: stroke.x,
      y: stroke.y,
      sliceIndex: stroke.slice_index,
      brushSize: stroke.brush_size,
      labelId: stroke.label_id,
      erase: stroke.erase,
    };

    // Apply locally (instant!)
    segmentationMask.paintStroke(localStroke);

    // Notify caller that paint was applied (for UI refresh)
    onPaintComplete?.(stroke.slice_index);
  }, [segmentationMask, onPaintComplete]);

  // Legacy mutation object for compatibility (but now it's instant, no network)
  const paintStrokeMutation = {
    mutate: applyPaintStrokeLocal,
    mutateAsync: async (stroke: PaintStroke) => {
      applyPaintStrokeLocal(stroke);
      return { success: true, sliceIndex: stroke.slice_index };
    },
    isPending: false,
    isError: false,
    error: null,
  };

  /**
   * Save segmentation to server (explicit save only).
   *
   * For local-only segmentations (temp ID), this creates on the server first,
   * then uploads the mask. For existing server segmentations, just uploads the mask.
   */
  const saveSegmentation = useCallback(async () => {
    if (!currentSegmentation) return;

    const isLocal = currentSegmentation.segmentation_id.startsWith('local-');

    // For existing segmentations, skip save if nothing changed
    if (!isLocal && !segmentationMask.state.isDirty) return;

    setSaveStatus('saving');

    // If local-only, create on server first to get a real ID
    let serverSeg: SegmentationResponse | null = null;
    if (isLocal) {
      try {
        const dims = segmentationMask.state.dimensions;
        serverSeg = await segmentationAPI.createSegmentation({
          file_id: currentSegmentation.file_id,
          image_shape: {
            rows: dims?.height ?? 256,
            columns: dims?.width ?? 256,
            slices: dims?.depth ?? 1,
          },
          labels: currentSegmentation.metadata?.labels ?? defaultLabels,
        });

        // Update mask hook with the real server ID (ref only — no React state change yet)
        segmentationMask.updateSegmentationId(serverSeg.segmentation_id);
        // DON'T call setCurrentSegmentation here — that would trigger loadMask
        // and overwrite the local mask before saveMask can upload it
      } catch (error) {
        console.error('[SegmentationData] Failed to create segmentation on server:', error);
        setSaveStatus('error');
        setTimeout(() => setSaveStatus('idle'), 5000);
        return;
      }
    }

    // Upload the mask (uses segmentationIdRef which was just updated)
    const success = await segmentationMask.saveMask();

    if (success) {
      // NOW it's safe to update Zustand with the server response.
      // Set skip flag so the useEffect doesn't reload the mask we just saved.
      if (serverSeg) {
        skipNextLoadRef.current = true;
        setCurrentSegmentation(serverSeg);
      }
      setSaveStatus('saved');
      setLastSaveTime(new Date());
      // Refresh the list so the saved segmentation appears in the sidebar
      queryClient.invalidateQueries({ queryKey: ['segmentations', 'study', currentStudyId] });
      setTimeout(() => setSaveStatus('idle'), 3000);
    } else {
      console.error('[SegmentationData] Failed to save segmentation');
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 5000);
    }
  }, [currentSegmentation, segmentationMask, setCurrentSegmentation, queryClient]);

  // Legacy save mutation for compatibility
  const saveSegmentationMutation = {
    mutate: () => saveSegmentation(),
    mutateAsync: saveSegmentation,
    isPending: segmentationMask.state.isSaving,
    isError: saveStatus === 'error',
    error: segmentationMask.state.error,
  };

  // Register save callback in Zustand so SegmentationPanel can trigger saves
  useEffect(() => {
    useSegmentationStore.getState().setSaveCallback(saveSegmentation);
    return () => useSegmentationStore.getState().setSaveCallback(null);
  }, [saveSegmentation]);

  // Register create callback in Zustand so SegmentationPanel can create locally
  useEffect(() => {
    useSegmentationStore.getState().setCreateCallback(createSegmentation);
    return () => useSegmentationStore.getState().setCreateCallback(null);
  }, [createSegmentation]);

  // Register reload-mask callback so LesionDashboard can reload after auto-classify
  const reloadCurrentMask = useCallback(async () => {
    const seg = useSegmentationStore.getState().currentSegmentation;
    if (seg) {
      await segmentationMask.loadMask(seg.segmentation_id);
    }
  }, [segmentationMask]);

  useEffect(() => {
    useSegmentationStore.getState().setReloadMaskCallback(reloadCurrentMask);
    return () => useSegmentationStore.getState().setReloadMaskCallback(null);
  }, [reloadCurrentMask]);

  // Auto-save before unload (only if there are unsaved changes)
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (currentSegmentation && segmentationMask.state.isDirty) {
        // Try to save (best effort - may not complete before unload)
        segmentationMask.saveMask()
          .catch(err => console.error('Failed to save on unload:', err));
        // Show browser warning
        e.preventDefault();
        e.returnValue = '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [currentSegmentation, segmentationMask]);

  return {
    segmentations,
    createSegmentationMutation,
    createSegmentation,
    paintStrokeMutation,
    saveSegmentation,
    saveSegmentationMutation,
    hasUnsavedChanges: segmentationMask.state.isDirty,
    isCreatingSegmentation: createSegmentationMutation.isPending,
    isSaving: segmentationMask.state.isSaving,
    // Save status for UI feedback
    saveStatus,
    lastSaveTime,
    // NEW: Expose mask functions for rendering
    segmentationMask,
  };
}
