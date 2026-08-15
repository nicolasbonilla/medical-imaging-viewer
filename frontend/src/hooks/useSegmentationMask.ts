/**
 * useSegmentationMask Hook - ITK-SNAP Style Local-First Segmentation
 *
 * Architecture:
 * 1. Load entire 3D mask once at startup
 * 2. All painting happens locally in memory (instant, no network)
 * 3. Save only when user explicitly clicks "Save"
 * 4. Undo/redo via per-stroke slice snapshots
 * 5. Draw-over rules to prevent accidental label overwriting
 *
 * @module hooks/useSegmentationMask
 */

import { useState, useRef, useCallback } from 'react';
import { apiClient } from '@/services/apiClient';

const API_BASE = '/api/v1/segmentation';
const MAX_UNDO = 50;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type DrawOverMode = 'all' | 'emptyOnly' | 'activeLabel';

export interface LocalPaintStroke {
  x: number;
  y: number;
  sliceIndex: number;
  brushSize: number;
  labelId: number;
  erase: boolean;
  /** Which existing labels can be overwritten */
  drawOverMode?: DrawOverMode;
  /** When drawOverMode is 'activeLabel', which label may be overwritten */
  drawOverLabel?: number;
}

export interface SegmentationMaskState {
  isLoading: boolean;
  isDirty: boolean;
  isSaving: boolean;
  error: string | null;
  dimensions: { depth: number; height: number; width: number } | null;
  annotatedVoxels: number;
}

interface UndoEntry {
  sliceIndex: number;
  /** Copy of the full H*W slice BEFORE the stroke was applied */
  previousData: Uint8Array;
}

export interface UseSegmentationMaskReturn {
  state: SegmentationMaskState;
  loadMask: (segmentationId: string) => Promise<boolean>;
  /** Initialize an empty mask locally (no server call). For local-first creation. */
  initEmptyMask: (depth: number, height: number, width: number) => void;
  /** Update the segmentation ID after server-side creation. */
  updateSegmentationId: (id: string) => void;
  paintStroke: (stroke: LocalPaintStroke) => void;
  getSliceMask: (sliceIndex: number) => Uint8Array | null;
  saveMask: () => Promise<boolean>;
  clearMask: () => void;
  getVoxel: (x: number, y: number, z: number) => number;
  isLoaded: boolean;
  markClean: () => void;
  /** Call on mousedown before painting — captures a slice snapshot for undo */
  beginStroke: (sliceIndex: number) => void;
  /** Call on mouseup / mouseleave */
  endStroke: () => void;
  /** Undo the last stroke. Returns true if successful. */
  undo: () => boolean;
  /** Redo the last undone stroke. Returns true if successful. */
  redo: () => boolean;
  canUndo: boolean;
  canRedo: boolean;
}

// ---------------------------------------------------------------------------
// Brush helpers
// ---------------------------------------------------------------------------

/**
 * Apply circular brush to a 2D slice with optional draw-over predicate.
 */
function applyCircularBrush(
  slice: Uint8Array,
  width: number,
  height: number,
  centerX: number,
  centerY: number,
  brushSize: number,
  value: number,
  canOverwrite?: (currentValue: number) => boolean,
): void {
  const radius = Math.floor(brushSize / 2);

  for (let dy = -radius; dy <= radius; dy++) {
    for (let dx = -radius; dx <= radius; dx++) {
      if (dx * dx + dy * dy <= radius * radius) {
        const px = centerX + dx;
        const py = centerY + dy;

        if (px >= 0 && px < width && py >= 0 && py < height) {
          const index = py * width + px;
          if (!canOverwrite || canOverwrite(slice[index])) {
            slice[index] = value;
          }
        }
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useSegmentationMask(): UseSegmentationMaskReturn {
  const [state, setState] = useState<SegmentationMaskState>({
    isLoading: false,
    isDirty: false,
    isSaving: false,
    error: null,
    dimensions: null,
    annotatedVoxels: 0,
  });

  // 3D mask data
  const maskRef = useRef<Uint8Array | null>(null);
  const segmentationIdRef = useRef<string | null>(null);
  const dimensionsRef = useRef<{ depth: number; height: number; width: number } | null>(null);

  // Undo / redo stacks (slice-level snapshots, one per stroke)
  const undoStackRef = useRef<UndoEntry[]>([]);
  const redoStackRef = useRef<UndoEntry[]>([]);
  // Counter to trigger re-renders when undo/redo availability changes
  const [undoVersion, setUndoVersion] = useState(0);

  // -----------------------------------------------------------------------
  // Load
  // -----------------------------------------------------------------------

  const loadMask = useCallback(async (segmentationId: string): Promise<boolean> => {
    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await apiClient.get(`${API_BASE}/${segmentationId}/mask/binary`, {
        responseType: 'arraybuffer',
      });

      const buffer = response.data as ArrayBuffer;
      if (buffer.byteLength < 12) throw new Error('Invalid binary data: too short');

      const headerView = new DataView(buffer, 0, 12);
      const depth = headerView.getUint32(0, true);
      const height = headerView.getUint32(4, true);
      const width = headerView.getUint32(8, true);

      const maskData = new Uint8Array(buffer, 12);
      const expectedSize = depth * height * width;
      if (maskData.length !== expectedSize) {
        throw new Error(`Invalid mask size: expected ${expectedSize}, got ${maskData.length}`);
      }

      maskRef.current = maskData;
      segmentationIdRef.current = segmentationId;
      dimensionsRef.current = { depth, height, width };

      // Reset undo stacks on new mask load
      undoStackRef.current = [];
      redoStackRef.current = [];
      setUndoVersion(0);

      let annotated = 0;
      for (let i = 0; i < maskData.length; i++) {
        if (maskData[i] > 0) annotated++;
      }

      setState(prev => ({
        ...prev,
        isLoading: false,
        isDirty: false,
        dimensions: { depth, height, width },
        annotatedVoxels: annotated,
      }));

      return true;
    } catch (error: any) {
      console.error('[useSegmentationMask] Failed to load mask:', error);
      setState(prev => ({
        ...prev,
        isLoading: false,
        error: error.message || 'Failed to load mask',
      }));
      return false;
    }
  }, []);

  // -----------------------------------------------------------------------
  // Init empty (local-first creation, no server call)
  // -----------------------------------------------------------------------

  const initEmptyMask = useCallback((depth: number, height: number, width: number): void => {
    const size = depth * height * width;
    maskRef.current = new Uint8Array(size); // All zeros
    segmentationIdRef.current = null; // No server ID yet
    dimensionsRef.current = { depth, height, width };

    undoStackRef.current = [];
    redoStackRef.current = [];
    setUndoVersion(0);

    setState({
      isLoading: false,
      isDirty: false,
      isSaving: false,
      error: null,
      dimensions: { depth, height, width },
      annotatedVoxels: 0,
    });
  }, []);

  const updateSegmentationId = useCallback((id: string): void => {
    segmentationIdRef.current = id;
  }, []);

  // -----------------------------------------------------------------------
  // Undo / Redo
  // -----------------------------------------------------------------------

  /** Capture a snapshot of the current slice BEFORE painting begins. */
  const beginStroke = useCallback((sliceIndex: number): void => {
    const mask = maskRef.current;
    const dims = dimensionsRef.current;
    if (!mask || !dims) return;

    const { height, width } = dims;
    const sliceOffset = sliceIndex * height * width;
    // Copy current slice data (before any modification)
    const snapshot = mask.slice(sliceOffset, sliceOffset + height * width);

    undoStackRef.current.push({ sliceIndex, previousData: snapshot });
    if (undoStackRef.current.length > MAX_UNDO) {
      undoStackRef.current.shift();
    }
    // New action invalidates redo history
    redoStackRef.current = [];
    setUndoVersion(v => v + 1);
  }, []);

  const endStroke = useCallback((): void => {
    // Currently a no-op marker; could be used for stroke batching in the future
  }, []);

  const undo = useCallback((): boolean => {
    const mask = maskRef.current;
    const dims = dimensionsRef.current;
    if (!mask || !dims || undoStackRef.current.length === 0) return false;

    const entry = undoStackRef.current.pop()!;
    const { sliceIndex, previousData } = entry;
    const { height, width } = dims;
    const sliceOffset = sliceIndex * height * width;

    // Save current state to redo stack
    const currentSlice = mask.slice(sliceOffset, sliceOffset + height * width);
    redoStackRef.current.push({ sliceIndex, previousData: currentSlice });

    // Restore the previous state
    mask.set(previousData, sliceOffset);

    setState(prev => ({ ...prev, isDirty: true }));
    setUndoVersion(v => v + 1);
    return true;
  }, []);

  const redo = useCallback((): boolean => {
    const mask = maskRef.current;
    const dims = dimensionsRef.current;
    if (!mask || !dims || redoStackRef.current.length === 0) return false;

    const entry = redoStackRef.current.pop()!;
    const { sliceIndex, previousData } = entry;
    const { height, width } = dims;
    const sliceOffset = sliceIndex * height * width;

    // Save current state to undo stack
    const currentSlice = mask.slice(sliceOffset, sliceOffset + height * width);
    undoStackRef.current.push({ sliceIndex, previousData: currentSlice });

    // Restore the redo state
    mask.set(previousData, sliceOffset);

    setState(prev => ({ ...prev, isDirty: true }));
    setUndoVersion(v => v + 1);
    return true;
  }, []);

  // -----------------------------------------------------------------------
  // Paint
  // -----------------------------------------------------------------------

  const paintStroke = useCallback((stroke: LocalPaintStroke): void => {
    const mask = maskRef.current;
    const dims = dimensionsRef.current;
    if (!mask || !dims) {
      console.warn('[useSegmentationMask] Cannot paint: mask not loaded');
      return;
    }

    const { depth, height, width } = dims;
    const { x, y, sliceIndex, brushSize, labelId, erase, drawOverMode, drawOverLabel } = stroke;

    if (sliceIndex < 0 || sliceIndex >= depth) return;

    const sliceOffset = sliceIndex * height * width;
    const sliceData = new Uint8Array(mask.buffer, mask.byteOffset + sliceOffset, height * width);

    const value = erase ? 0 : labelId;

    // Build draw-over predicate
    let canOverwrite: ((v: number) => boolean) | undefined;
    if (drawOverMode === 'emptyOnly') {
      // Only paint on empty pixels (or allow erasing our own label)
      canOverwrite = (v) => v === 0 || (erase && v === labelId);
    } else if (drawOverMode === 'activeLabel') {
      const target = drawOverLabel ?? labelId;
      canOverwrite = (v) => v === 0 || v === target;
    }
    // 'all' (default): no predicate → overwrites everything

    applyCircularBrush(sliceData, width, height, x, y, brushSize, value, canOverwrite);

    setState(prev => ({ ...prev, isDirty: true }));
  }, []);

  // -----------------------------------------------------------------------
  // Read
  // -----------------------------------------------------------------------

  const getSliceMask = useCallback((sliceIndex: number): Uint8Array | null => {
    const mask = maskRef.current;
    const dims = dimensionsRef.current;
    if (!mask || !dims) return null;

    const { depth, height, width } = dims;
    if (sliceIndex < 0 || sliceIndex >= depth) return null;

    const sliceOffset = sliceIndex * height * width;
    return new Uint8Array(mask.buffer, mask.byteOffset + sliceOffset, height * width);
  }, []);

  const getVoxel = useCallback((x: number, y: number, z: number): number => {
    const mask = maskRef.current;
    const dims = dimensionsRef.current;
    if (!mask || !dims) return 0;

    const { depth, height, width } = dims;
    if (x < 0 || x >= width || y < 0 || y >= height || z < 0 || z >= depth) return 0;

    return mask[z * (height * width) + y * width + x];
  }, []);

  // -----------------------------------------------------------------------
  // Save
  // -----------------------------------------------------------------------

  const saveMask = useCallback(async (): Promise<boolean> => {
    const mask = maskRef.current;
    const dims = dimensionsRef.current;
    const segId = segmentationIdRef.current;
    if (!mask || !dims || !segId) return false;

    setState(prev => ({ ...prev, isSaving: true, error: null }));

    try {
      const { depth, height, width } = dims;
      const headerSize = 12;
      const buffer = new ArrayBuffer(headerSize + mask.length);
      const view = new DataView(buffer);

      view.setUint32(0, depth, true);
      view.setUint32(4, height, true);
      view.setUint32(8, width, true);

      new Uint8Array(buffer, headerSize).set(mask);

      const response = await apiClient.put(`${API_BASE}/${segId}/mask/binary`, buffer, {
        headers: { 'Content-Type': 'application/octet-stream' },
      });

      let annotated = 0;
      for (let i = 0; i < mask.length; i++) {
        if (mask[i] > 0) annotated++;
      }

      // P-4.3: the server reports whether the save was DURABLE. A non-durable
      // save (ephemeral local fallback) must NOT clear the dirty flag — keep the
      // local edit as backup and surface a warning so the user retries. `durable`
      // absent (older backend) is treated as durable for backward compatibility.
      const durable = (response?.data as { durable?: boolean })?.durable !== false;
      if (!durable) {
        const msg =
          (response?.data as { message?: string })?.message ||
          'Save was not durable — your changes may be lost. Please retry.';
        console.warn('[useSegmentationMask] Non-durable save:', msg);
        setState(prev => ({
          ...prev,
          isSaving: false,
          annotatedVoxels: annotated,
          error: msg,
        }));
        return false;
      }

      setState(prev => ({
        ...prev,
        isSaving: false,
        isDirty: false,
        annotatedVoxels: annotated,
        error: null,
      }));

      return true;
    } catch (error: any) {
      console.error('[useSegmentationMask] Failed to save:', error);
      setState(prev => ({
        ...prev,
        isSaving: false,
        error: error.message || 'Failed to save mask',
      }));
      return false;
    }
  }, []);

  // -----------------------------------------------------------------------
  // Clear / Clean
  // -----------------------------------------------------------------------

  const clearMask = useCallback((): void => {
    maskRef.current = null;
    segmentationIdRef.current = null;
    dimensionsRef.current = null;
    undoStackRef.current = [];
    redoStackRef.current = [];
    setUndoVersion(0);
    setState({
      isLoading: false,
      isDirty: false,
      isSaving: false,
      error: null,
      dimensions: null,
      annotatedVoxels: 0,
    });
  }, []);

  const markClean = useCallback((): void => {
    setState(prev => ({ ...prev, isDirty: false }));
  }, []);

  // -----------------------------------------------------------------------
  // Return
  // -----------------------------------------------------------------------

  return {
    state,
    loadMask,
    initEmptyMask,
    updateSegmentationId,
    paintStroke,
    getSliceMask,
    saveMask,
    clearMask,
    getVoxel,
    isLoaded: maskRef.current !== null,
    markClean,
    beginStroke,
    endStroke,
    undo,
    redo,
    canUndo: undoStackRef.current.length > 0,
    canRedo: redoStackRef.current.length > 0,
  };
}

export default useSegmentationMask;
