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
import type { AIProvenance, PaintStroke, ImageShape, Segmentation, SegmentationResponse } from '@/types';
import type { ImportDraftResult } from '@/store/useSegmentationStore';
import { isAiSegmentation, provenanceRecorded } from '@/services/flames/draft';
import { distinctMaskValues } from '@/utils/drawnLabels';

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

  // Release 2026-10-25 (review of PR #69, B1): the distinct values of the mask as loaded from the server, so the
  // overlay controls can warn about a value the label table does not name (drawn in the fallback colour).
  const publishMaskValues = useCallback((loaded: boolean) => {
    const bytes = loaded ? segmentationMask.getMaskSnapshot() : null;
    useSegmentationStore.getState().setMaskLabelValues(bytes ? distinctMaskValues(bytes) : null);
  }, [segmentationMask]);

  // Load mask when segmentation changes (skip local-only — mask is already initialized)
  useEffect(() => {
    if (!currentSegmentation?.segmentation_id) {
      segmentationMask.clearMask();
      useSegmentationStore.getState().setMaskLabelValues(null);
    } else if (!currentSegmentation.segmentation_id.startsWith('local-')) {
      if (skipNextLoadRef.current) {
        // After save: mask is already in memory, skip redundant server fetch
        skipNextLoadRef.current = false;
        return;
      }
      void segmentationMask.loadMask(currentSegmentation.segmentation_id).then(publishMaskValues);
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
        // Origin is taken from the stored provenance, never assumed: an AI draft (local or saved)
        // is 'automatic' and carries its provenance; only segmentations without it are 'manual'.
        const aiProvenance = currentSegmentation.metadata?.ai_provenance ?? null;
        const synced: Segmentation = {
          id: segId,
          patient_id: '',
          study_id: '',
          series_id: currentSeries?.file_id || '',
          file_id: currentSegmentation.file_id,
          name: currentSegmentation.metadata?.description || 'Segmentation',
          segmentation_type: aiProvenance ? 'automatic' : 'manual',
          ai_provenance: aiProvenance,
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

  // Unsaved work in the open segmentation: edits not yet saved, or edits kept after a refused (409)
  // save. Read through a ref so a callback registered in the store never sees a stale value.
  const unsavedWorkRef = useRef(false);
  unsavedWorkRef.current = Boolean(
    currentSegmentation && (segmentationMask.state.isDirty || segmentationMask.state.conflict != null),
  );

  /**
   * Create a LOCAL segmentation pre-filled with an externally computed mask (in-browser FLAMeS
   * prototype). Same local-first path as createSegmentation: nothing reaches the server until the
   * clinician reviews and clicks Save.
   *
   * Never discards unsaved work (REQ-SAFE-032): if the open segmentation has unsaved changes, NOTHING
   * is touched and { ok: false, reason: 'unsaved-work' } is returned so the UI can ask the clinician.
   * Only an explicit `discardUnsavedWork: true` (after that question) replaces it.
   * On a grid mismatch nothing is touched either.
   */
  const createSegmentationFromMask = useCallback(
    (
      fileId: string,
      imageShape: ImageShape,
      mask: Uint8Array,
      meta: { description: string; labels?: typeof defaultLabels; aiProvenance: AIProvenance },
      options: { discardUnsavedWork?: boolean } = {},
    ): ImportDraftResult => {
      const expected = imageShape.slices * imageShape.rows * imageShape.columns;
      if (mask.length !== expected) {
        console.error('[SegmentationData] Draft mask size does not match the image grid', { expected, got: mask.length });
        return { ok: false, reason: 'grid-mismatch' };
      }
      if (unsavedWorkRef.current && !options.discardUnsavedWork) {
        const open = currentSegmentationRef.current;
        return {
          ok: false,
          reason: 'unsaved-work',
          openSegmentationName: open?.metadata?.description || 'Segmentation',
        };
      }
      const tempId = `local-${crypto.randomUUID()}`;
      const now = new Date().toISOString();
      const labels = meta.labels ?? defaultLabels;
      setCurrentSegmentation({
        segmentation_id: tempId,
        file_id: fileId,
        total_slices: imageShape.slices,
        metadata: {
          file_id: fileId,
          description: meta.description,
          labels,
          created_at: now,
          modified_at: now,
          segmentation_type: 'automatic',
          ai_provenance: { ...meta.aiProvenance, review_status: 'unreviewed', reviewed_by: null, reviewed_at: null },
        },
      });
      segmentationMask.initEmptyMask(imageShape.slices, imageShape.rows, imageShape.columns);
      const ok = segmentationMask.importMask(mask, {
        depth: imageShape.slices,
        height: imageShape.rows,
        width: imageShape.columns,
      });
      if (!ok) {
        setCurrentSegmentation(null);
        segmentationMask.clearMask();
        return { ok: false, reason: 'grid-mismatch' };
      }
      return { ok: true };
    },
    [setCurrentSegmentation, segmentationMask],
  );

  /** RC-047: refresh the AI provenance of an open segmentation from the server after a mask save. */
  const refreshAiProvenance = useCallback(
    async (segmentationId: string, seg: SegmentationResponse) => {
      let provenance: AIProvenance | null | undefined;
      try {
        provenance = (await segmentationAPI.getSegmentation(segmentationId)).metadata?.ai_provenance;
      } catch {
        provenance = seg.metadata.ai_provenance
          ? { ...seg.metadata.ai_provenance, review_status: 'unreviewed', reviewed_by: null, reviewed_at: null, reviewed_mask_sha256: null }
          : null;
      }
      const store = useSegmentationStore.getState();
      const cur = store.currentSegmentation;
      if (cur && cur.segmentation_id === segmentationId) {
        store.setCurrentSegmentation({ ...cur, metadata: { ...cur.metadata, ai_provenance: provenance ?? null } });
      }
      if (store.activeSegmentation && store.activeSegmentation.id === segmentationId) {
        store.setActiveSegmentation({ ...store.activeSegmentation, ai_provenance: provenance ?? null });
      }
    },
    [],
  );

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
    // AUDIT #3 (silent multi-label annotation destruction): SegmentationCanvasLocal ALREADY
    // applied this stroke locally — honouring drawOverMode/drawOverLabel — before firing
    // onPaintStroke -> here. Re-painting again without the mode (it defaults to 'all')
    // overwrote a DIFFERENT clinician-drawn label that the first, protective paint had
    // preserved (e.g. Draw-Over "Empty only"/"Active label only"). This callback must NOT
    // paint a second time; it only notifies the data layer for UI refresh. isDirty is
    // already set by the canvas's paint.
    onPaintComplete?.(stroke.slice_index);
  }, [onPaintComplete]);

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
        // Provenance: only non-default descriptions (e.g. the in-browser AI draft stamp) are sent,
        // so manual segmentations keep exactly the previous request body.
        const localDescription = currentSegmentation.metadata?.description;
        const aiProvenance = currentSegmentation.metadata?.ai_provenance ?? undefined;
        serverSeg = await segmentationAPI.createSegmentation({
          file_id: currentSegmentation.file_id,
          image_shape: {
            rows: dims?.height ?? 256,
            columns: dims?.width ?? 256,
            slices: dims?.depth ?? 1,
          },
          labels: currentSegmentation.metadata?.labels ?? defaultLabels,
          ...(localDescription && localDescription !== 'Segmentation' ? { description: localDescription } : {}),
          ...(aiProvenance ? { ai_provenance: aiProvenance } : {}),
        });

        // REQ-SAFE-030: an AI draft is stored ONLY with its AI provenance. A server that did not
        // record it (e.g. an older backend that ignores the field) would store it as manual work:
        // remove that record and fail the save instead (fail closed).
        if (aiProvenance && !provenanceRecorded(aiProvenance, serverSeg.metadata?.ai_provenance)) {
          const orphan = serverSeg.segmentation_id;
          serverSeg = null;
          await segmentationAPI.deleteSegmentation(orphan).catch((e: unknown) =>
            console.error('[SegmentationData] Could not remove a record created without AI provenance:', e),
          );
          throw new Error('The server did not record the AI provenance; the AI draft was NOT saved.');
        }

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
      // RC-047: the server resets a confirmed AI review when the mask changed; never keep showing a
      // stale "confirmed" locally — re-read the provenance (fail safe: mark unreviewed if that fails).
      const savedId = serverSeg?.segmentation_id ?? currentSegmentation.segmentation_id;
      if (!serverSeg && currentSegmentation.metadata?.ai_provenance) {
        await refreshAiProvenance(savedId, currentSegmentation);
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
  }, [currentSegmentation, segmentationMask, setCurrentSegmentation, queryClient, refreshAiProvenance]);

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

  // Register import-draft callback so the (feature-flagged) in-browser FLAMeS button can hand over its mask
  useEffect(() => {
    useSegmentationStore.getState().setImportDraftCallback(createSegmentationFromMask);
    return () => useSegmentationStore.getState().setImportDraftCallback(null);
  }, [createSegmentationFromMask]);

  // RC-047: expose the digest of the open mask (bound to a review confirmation) and its unsaved state.
  const getMaskSnapshot = segmentationMask.getMaskSnapshot;
  useEffect(() => {
    const digest = async (): Promise<string | null> => {
      const bytes = getMaskSnapshot();
      if (!bytes) return null;
      const buf = await crypto.subtle.digest('SHA-256', bytes as unknown as ArrayBuffer);
      return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, '0')).join('');
    };
    useSegmentationStore.getState().setMaskDigestCallback(digest);
    return () => useSegmentationStore.getState().setMaskDigestCallback(null);
  }, [getMaskSnapshot]);

  // Release 2026-10-25 (review of PR #69, B1/M3): the values of the open mask, read at the moment of a confirmation.
  useEffect(() => {
    const values = (): number[] | null => {
      const bytes = getMaskSnapshot();
      return bytes ? distinctMaskValues(bytes) : null;
    };
    useSegmentationStore.getState().setMaskValuesCallback(values);
    return () => useSegmentationStore.getState().setMaskValuesCallback(null);
  }, [getMaskSnapshot]);

  const unsavedMask = Boolean(segmentationMask.state.isDirty || segmentationMask.state.conflict != null);
  useEffect(() => {
    useSegmentationStore.getState().setHasUnsavedMaskChanges(unsavedMask);
  }, [unsavedMask]);

  // Register reload-mask callback so LesionDashboard can reload after auto-classify
  const reloadCurrentMask = useCallback(async () => {
    const seg = useSegmentationStore.getState().currentSegmentation;
    if (seg) {
      const loaded = await segmentationMask.loadMask(seg.segmentation_id);
      publishMaskValues(loaded);
      return loaded;
    }
    return false;
  }, [segmentationMask, publishMaskValues]);

  useEffect(() => {
    useSegmentationStore.getState().setReloadMaskCallback(reloadCurrentMask);
    return () => useSegmentationStore.getState().setReloadMaskCallback(null);
  }, [reloadCurrentMask]);

  // Warn (and best-effort save) before unload when there are unsaved changes.
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (currentSegmentation && segmentationMask.state.isDirty) {
        // REQ-SAFE-030: an AI segmentation (unreviewed draft or saved AI result) is NEVER saved
        // without an explicit clinician action. Only the native "leave page?" warning is shown.
        if (!isAiSegmentation(currentSegmentation.metadata)) {
          // Best-effort save through the UNIFIED path. The low-level
          // `segmentationMask.saveMask()` NO-OPS on a `local-` (never-persisted) id —
          // it has no server id to upload to — so using it here silently saved nothing
          // for brand-new segmentations (audit F-1.2). `saveSegmentation` instead
          // create-then-uploads a local id. NOTE: browsers do not await `beforeunload`,
          // so this is genuinely best-effort — the RELIABLE protection against losing
          // unsaved work is the native confirmation dialog triggered below.
          saveSegmentation().catch(err => console.error('Failed to save on unload:', err));
        }
        e.preventDefault();
        e.returnValue = '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [currentSegmentation, segmentationMask, saveSegmentation]);

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
