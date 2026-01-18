/**
 * Segmentation Store - Zustand state management for ITK-SNAP style segmentation.
 *
 * Manages:
 * - Active segmentation state
 * - Label palette and visibility
 * - Paint tool settings
 * - Undo/redo history
 * - Overlay rendering settings
 *
 * @module store/useSegmentationStore
 */

import { create } from 'zustand';
import { subscribeWithSelector, persist } from 'zustand/middleware';
import type {
  Segmentation,
  SegmentationSummary,
  LabelInfo,
  PaintStroke,
  OverlaySettings,
  OverlayMode,
  SegmentationStatus,
} from '@/types';

// ============================================================================
// Types
// ============================================================================

/**
 * Paint tool types available for segmentation.
 */
export type PaintTool = 'brush' | 'eraser' | 'fill' | 'polygon' | 'threshold';

/**
 * Brush shape options.
 */
export type BrushShape = 'circle' | 'square';

/**
 * Paint tool configuration.
 */
export interface PaintToolConfig {
  tool: PaintTool;
  brushSize: number;
  brushShape: BrushShape;
  activeLabel: number;
  fillTolerance: number;
  thresholdMin: number;
  thresholdMax: number;
}

/**
 * Undo/redo action for segmentation changes.
 */
export interface SegmentationAction {
  type: 'paint' | 'fill' | 'clear_slice' | 'clear_label';
  timestamp: number;
  sliceIndex: number;
  labelId: number;
  // Compressed data for undo (base64 encoded RLE)
  previousData?: string;
  affectedVoxels?: number;
}

/**
 * Segmentation store state.
 */
interface SegmentationState {
  // =========================================================================
  // Active Segmentation
  // =========================================================================

  /** Currently active segmentation for editing */
  activeSegmentation: Segmentation | null;

  /** Series ID of the active segmentation */
  activeSeriesId: string | null;

  /** Whether segmentation is currently being edited (dirty state) */
  isDirty: boolean;

  /** Whether segmentation is being saved */
  isSaving: boolean;

  /** Last save timestamp */
  lastSavedAt: string | null;

  // =========================================================================
  // Segmentation List (for current series)
  // =========================================================================

  /** Segmentations available for the current series */
  seriesSegmentations: SegmentationSummary[];

  /** Loading state for segmentation list */
  isLoadingList: boolean;

  // =========================================================================
  // Labels
  // =========================================================================

  /** Active label for painting (0-255) */
  activeLabel: number;

  /** Label visibility overrides (label_id -> visible) */
  labelVisibility: Record<number, boolean>;

  // =========================================================================
  // Paint Tool
  // =========================================================================

  /** Current paint tool configuration */
  paintTool: PaintToolConfig;

  /** Whether paint mode is active */
  isPaintMode: boolean;

  /** Pending strokes to send to backend */
  pendingStrokes: PaintStroke[];

  // =========================================================================
  // Overlay Settings
  // =========================================================================

  /** Overlay rendering settings */
  overlaySettings: OverlaySettings;

  /** Whether overlay is visible */
  isOverlayVisible: boolean;

  // =========================================================================
  // Undo/Redo
  // =========================================================================

  /** Undo history stack */
  undoStack: SegmentationAction[];

  /** Redo history stack */
  redoStack: SegmentationAction[];

  /** Maximum undo history size */
  maxUndoSize: number;

  // =========================================================================
  // Actions - Segmentation
  // =========================================================================

  setActiveSegmentation: (segmentation: Segmentation | null) => void;
  setActiveSeriesId: (seriesId: string | null) => void;
  setSeriesSegmentations: (segmentations: SegmentationSummary[]) => void;
  setIsLoadingList: (loading: boolean) => void;
  setIsDirty: (dirty: boolean) => void;
  setIsSaving: (saving: boolean) => void;
  setLastSavedAt: (timestamp: string | null) => void;

  // =========================================================================
  // Actions - Labels
  // =========================================================================

  setActiveLabel: (labelId: number) => void;
  setLabelVisibility: (labelId: number, visible: boolean) => void;
  toggleLabelVisibility: (labelId: number) => void;
  showAllLabels: () => void;
  hideAllLabels: () => void;
  updateLabel: (labelId: number, updates: Partial<LabelInfo>) => void;
  addLabel: (label: LabelInfo) => void;
  removeLabel: (labelId: number) => void;

  // =========================================================================
  // Actions - Paint Tool
  // =========================================================================

  setPaintTool: (tool: PaintTool) => void;
  setBrushSize: (size: number) => void;
  setBrushShape: (shape: BrushShape) => void;
  setFillTolerance: (tolerance: number) => void;
  setThresholdRange: (min: number, max: number) => void;
  togglePaintMode: () => void;
  setIsPaintMode: (active: boolean) => void;

  // =========================================================================
  // Actions - Strokes
  // =========================================================================

  addPendingStroke: (stroke: PaintStroke) => void;
  clearPendingStrokes: () => void;
  flushPendingStrokes: () => PaintStroke[];

  // =========================================================================
  // Actions - Overlay
  // =========================================================================

  setOverlayMode: (mode: OverlayMode) => void;
  setGlobalOpacity: (opacity: number) => void;
  setOutlineThickness: (thickness: number) => void;
  toggleOverlayVisibility: () => void;
  setIsOverlayVisible: (visible: boolean) => void;

  // =========================================================================
  // Actions - Undo/Redo
  // =========================================================================

  pushUndoAction: (action: SegmentationAction) => void;
  undo: () => SegmentationAction | null;
  redo: () => SegmentationAction | null;
  clearHistory: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;

  // =========================================================================
  // Actions - Reset
  // =========================================================================

  reset: () => void;
  resetPaintTool: () => void;
}

// ============================================================================
// Initial State
// ============================================================================

const defaultPaintTool: PaintToolConfig = {
  tool: 'brush',
  brushSize: 5,
  brushShape: 'circle',
  activeLabel: 1,
  fillTolerance: 10,
  thresholdMin: 0,
  thresholdMax: 255,
};

const defaultOverlaySettings: OverlaySettings = {
  mode: 'overlay',
  global_opacity: 0.5,
  visible_labels: undefined,
  outline_thickness: 2,
  outline_only: false,
};

const initialState = {
  // Segmentation
  activeSegmentation: null,
  activeSeriesId: null,
  isDirty: false,
  isSaving: false,
  lastSavedAt: null,

  // List
  seriesSegmentations: [],
  isLoadingList: false,

  // Labels
  activeLabel: 1,
  labelVisibility: {},

  // Paint tool
  paintTool: defaultPaintTool,
  isPaintMode: false,
  pendingStrokes: [],

  // Overlay
  overlaySettings: defaultOverlaySettings,
  isOverlayVisible: true,

  // Undo/Redo
  undoStack: [],
  redoStack: [],
  maxUndoSize: 50,
};

// ============================================================================
// Store
// ============================================================================

export const useSegmentationStore = create<SegmentationState>()(
  subscribeWithSelector(
    persist(
      (set, get) => ({
        ...initialState,

        // =====================================================================
        // Segmentation Actions
        // =====================================================================

        setActiveSegmentation: (segmentation) =>
          set({
            activeSegmentation: segmentation,
            isDirty: false,
            activeLabel: segmentation?.labels.find((l) => l.id !== 0)?.id ?? 1,
            labelVisibility: segmentation?.labels.reduce(
              (acc, label) => ({ ...acc, [label.id]: label.visible }),
              {}
            ) ?? {},
          }),

        setActiveSeriesId: (seriesId) => set({ activeSeriesId: seriesId }),

        setSeriesSegmentations: (segmentations) =>
          set({ seriesSegmentations: segmentations }),

        setIsLoadingList: (loading) => set({ isLoadingList: loading }),

        setIsDirty: (dirty) => set({ isDirty: dirty }),

        setIsSaving: (saving) => set({ isSaving: saving }),

        setLastSavedAt: (timestamp) => set({ lastSavedAt: timestamp }),

        // =====================================================================
        // Label Actions
        // =====================================================================

        setActiveLabel: (labelId) =>
          set((state) => ({
            activeLabel: labelId,
            paintTool: { ...state.paintTool, activeLabel: labelId },
          })),

        setLabelVisibility: (labelId, visible) =>
          set((state) => ({
            labelVisibility: { ...state.labelVisibility, [labelId]: visible },
          })),

        toggleLabelVisibility: (labelId) =>
          set((state) => ({
            labelVisibility: {
              ...state.labelVisibility,
              [labelId]: !state.labelVisibility[labelId],
            },
          })),

        showAllLabels: () =>
          set((state) => {
            const visibility: Record<number, boolean> = {};
            state.activeSegmentation?.labels.forEach((label) => {
              visibility[label.id] = label.id !== 0; // Show all except background
            });
            return { labelVisibility: visibility };
          }),

        hideAllLabels: () =>
          set((state) => {
            const visibility: Record<number, boolean> = {};
            state.activeSegmentation?.labels.forEach((label) => {
              visibility[label.id] = false;
            });
            return { labelVisibility: visibility };
          }),

        updateLabel: (labelId, updates) =>
          set((state) => {
            if (!state.activeSegmentation) return state;
            const labels = state.activeSegmentation.labels.map((label) =>
              label.id === labelId ? { ...label, ...updates } : label
            );
            return {
              activeSegmentation: { ...state.activeSegmentation, labels },
              isDirty: true,
            };
          }),

        addLabel: (label) =>
          set((state) => {
            if (!state.activeSegmentation) return state;
            return {
              activeSegmentation: {
                ...state.activeSegmentation,
                labels: [...state.activeSegmentation.labels, label],
              },
              labelVisibility: {
                ...state.labelVisibility,
                [label.id]: label.visible,
              },
              isDirty: true,
            };
          }),

        removeLabel: (labelId) =>
          set((state) => {
            if (!state.activeSegmentation || labelId === 0) return state;
            const labels = state.activeSegmentation.labels.filter(
              (l) => l.id !== labelId
            );
            const { [labelId]: _, ...visibility } = state.labelVisibility;
            return {
              activeSegmentation: { ...state.activeSegmentation, labels },
              labelVisibility: visibility,
              activeLabel: state.activeLabel === labelId ? 1 : state.activeLabel,
              isDirty: true,
            };
          }),

        // =====================================================================
        // Paint Tool Actions
        // =====================================================================

        setPaintTool: (tool) =>
          set((state) => ({
            paintTool: { ...state.paintTool, tool },
          })),

        setBrushSize: (size) =>
          set((state) => ({
            paintTool: { ...state.paintTool, brushSize: Math.max(1, Math.min(50, size)) },
          })),

        setBrushShape: (shape) =>
          set((state) => ({
            paintTool: { ...state.paintTool, brushShape: shape },
          })),

        setFillTolerance: (tolerance) =>
          set((state) => ({
            paintTool: { ...state.paintTool, fillTolerance: Math.max(0, Math.min(255, tolerance)) },
          })),

        setThresholdRange: (min, max) =>
          set((state) => ({
            paintTool: {
              ...state.paintTool,
              thresholdMin: Math.max(0, min),
              thresholdMax: Math.min(255, max),
            },
          })),

        togglePaintMode: () => set((state) => ({ isPaintMode: !state.isPaintMode })),

        setIsPaintMode: (active) => set({ isPaintMode: active }),

        // =====================================================================
        // Stroke Actions
        // =====================================================================

        addPendingStroke: (stroke) =>
          set((state) => ({
            pendingStrokes: [...state.pendingStrokes, stroke],
            isDirty: true,
          })),

        clearPendingStrokes: () => set({ pendingStrokes: [] }),

        flushPendingStrokes: () => {
          const strokes = get().pendingStrokes;
          set({ pendingStrokes: [] });
          return strokes;
        },

        // =====================================================================
        // Overlay Actions
        // =====================================================================

        setOverlayMode: (mode) =>
          set((state) => ({
            overlaySettings: { ...state.overlaySettings, mode },
          })),

        setGlobalOpacity: (opacity) =>
          set((state) => ({
            overlaySettings: {
              ...state.overlaySettings,
              global_opacity: Math.max(0, Math.min(1, opacity)),
            },
          })),

        setOutlineThickness: (thickness) =>
          set((state) => ({
            overlaySettings: {
              ...state.overlaySettings,
              outline_thickness: Math.max(1, Math.min(5, thickness)),
            },
          })),

        toggleOverlayVisibility: () =>
          set((state) => ({ isOverlayVisible: !state.isOverlayVisible })),

        setIsOverlayVisible: (visible) => set({ isOverlayVisible: visible }),

        // =====================================================================
        // Undo/Redo Actions
        // =====================================================================

        pushUndoAction: (action) =>
          set((state) => {
            const newStack = [...state.undoStack, action];
            // Trim to max size
            if (newStack.length > state.maxUndoSize) {
              newStack.shift();
            }
            return {
              undoStack: newStack,
              redoStack: [], // Clear redo on new action
            };
          }),

        undo: () => {
          const state = get();
          if (state.undoStack.length === 0) return null;

          const action = state.undoStack[state.undoStack.length - 1];
          set({
            undoStack: state.undoStack.slice(0, -1),
            redoStack: [...state.redoStack, action],
          });
          return action;
        },

        redo: () => {
          const state = get();
          if (state.redoStack.length === 0) return null;

          const action = state.redoStack[state.redoStack.length - 1];
          set({
            redoStack: state.redoStack.slice(0, -1),
            undoStack: [...state.undoStack, action],
          });
          return action;
        },

        clearHistory: () => set({ undoStack: [], redoStack: [] }),

        canUndo: () => get().undoStack.length > 0,

        canRedo: () => get().redoStack.length > 0,

        // =====================================================================
        // Reset Actions
        // =====================================================================

        reset: () => set(initialState),

        resetPaintTool: () =>
          set({
            paintTool: defaultPaintTool,
            isPaintMode: false,
            pendingStrokes: [],
          }),
      }),
      {
        name: 'segmentation-store',
        partialize: (state) => ({
          // Only persist user preferences, not active data
          paintTool: state.paintTool,
          overlaySettings: state.overlaySettings,
          maxUndoSize: state.maxUndoSize,
        }),
      }
    )
  )
);

// ============================================================================
// Selectors (for optimized re-renders)
// ============================================================================

/**
 * Select active segmentation labels.
 */
export const selectLabels = (state: SegmentationState) =>
  state.activeSegmentation?.labels ?? [];

/**
 * Select visible labels only.
 */
export const selectVisibleLabels = (state: SegmentationState) =>
  state.activeSegmentation?.labels.filter(
    (label) => state.labelVisibility[label.id] !== false && label.id !== 0
  ) ?? [];

/**
 * Select active label info.
 */
export const selectActiveLabel = (state: SegmentationState) =>
  state.activeSegmentation?.labels.find((l) => l.id === state.activeLabel);

/**
 * Select segmentation progress.
 */
export const selectProgress = (state: SegmentationState) => ({
  annotated: state.activeSegmentation?.slices_annotated ?? 0,
  total: state.activeSegmentation?.total_slices ?? 0,
  percentage: state.activeSegmentation?.progress_percentage ?? 0,
});

/**
 * Select if there are unsaved changes.
 */
export const selectHasUnsavedChanges = (state: SegmentationState) =>
  state.isDirty && state.activeSegmentation !== null;

// ============================================================================
// Hooks (derived state)
// ============================================================================

/**
 * Get label by ID from active segmentation.
 */
export const useLabel = (labelId: number): LabelInfo | undefined => {
  return useSegmentationStore(
    (state) => state.activeSegmentation?.labels.find((l) => l.id === labelId)
  );
};

/**
 * Check if a series has any segmentations.
 */
export const useSeriesHasSegmentations = (): boolean => {
  return useSegmentationStore((state) => state.seriesSegmentations.length > 0);
};

/**
 * Get segmentation count for indicators.
 */
export const useSegmentationCount = (): number => {
  return useSegmentationStore((state) => state.seriesSegmentations.length);
};
