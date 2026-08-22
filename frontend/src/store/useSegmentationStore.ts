/**
 * Segmentation Store - Zustand state management for ITK-SNAP style segmentation.
 *
 * Manages:
 * - Active segmentation and current segmentation response
 * - Label palette and visibility
 * - Paint tool settings
 * - Overlay rendering settings
 *
 * Undo/redo is handled by useSegmentationMask (slice-level snapshots).
 *
 * @module store/useSegmentationStore
 */

import { create } from 'zustand';
import { subscribeWithSelector, persist } from 'zustand/middleware';
import type {
  Segmentation,
  SegmentationSummary,
  SegmentationResponse,
  LabelInfo,
  LabelPreset,
  OverlaySettings,
  OverlayMode,
  LesionInfo,
} from '@/types';
import { DEFAULT_LABEL_PRESETS } from '@/types';

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
 * Draw-over mode controls which existing voxels can be overwritten during painting.
 * - 'all': Overwrite everything (default)
 * - 'emptyOnly': Only paint on empty (background) voxels
 * - 'activeLabel': Only overwrite the currently active label or empty voxels
 */
export type DrawOverMode = 'all' | 'emptyOnly' | 'activeLabel';

/** One candidate in a CALM-MS conformal review (ordinal tier; NEVER a probability). */
export interface ConformalLesion {
  centroid: number[];
  volume_mm3: number;
  n_voxels: number;
  review_priority: 'high' | 'medium' | 'low';
  in_fdr_set: boolean;
}

/** Response of POST /conformal/select — population-level scope, no per-scan FDR. */
export interface ConformalSummary {
  preset: string;
  fdr_target: number;
  /**
   * True when the OOD monitor detected a gross MARGINAL shift and withheld the scope.
   * NOTE: False does NOT certify the guarantee applies — the monitor only sees the
   * mixed candidate-score marginal, not the label-conditional exchangeability the
   * guarantee needs (honest naming, adversarial review 2026-08-21).
   */
  marginal_shift_flagged: boolean;
  guarantee_scope: string;
  ood: { is_ood: boolean; distance: number; threshold: number; detail: string } | null;
  n_candidates: number;
  n_in_fdr_set: number;
  tier_counts: { high: number; medium: number; low: number };
  base_model: string | null;
  null_version: string | null;
  lesions: ConformalLesion[];
}

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
 * Segmentation store state.
 */
interface SegmentationState {
  // =========================================================================
  // Active Segmentation
  // =========================================================================

  /** Current segmentation response (server-side data, selected by user) */
  currentSegmentation: SegmentationResponse | null;

  /** Currently active segmentation for editing (rich Segmentation type for UI) */
  activeSegmentation: Segmentation | null;

  /** Series ID of the active segmentation */
  activeSeriesId: string | null;

  /** Whether segmentation is currently being edited (dirty state) */
  isDirty: boolean;

  /** Whether segmentation is being saved */
  isSaving: boolean;

  /** Save callback set by useSegmentationData — allows panel to trigger save */
  saveCallback: (() => Promise<void>) | null;

  /** Create callback set by useSegmentationData — allows panel to create locally */
  createCallback: ((fileId: string, imageShape: { rows: number; columns: number; slices: number }) => void) | null;

  /** Reload mask callback — allows LesionDashboard to trigger mask reload after auto-classify */
  reloadMaskCallback: (() => Promise<void>) | null;

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

  /** Draw-over mode: controls which voxels can be overwritten */
  drawOverMode: DrawOverMode;

  // =========================================================================
  // Overlay Settings
  // =========================================================================

  /** Overlay rendering settings */
  overlaySettings: OverlaySettings;

  /** Whether overlay is visible */
  isOverlayVisible: boolean;

  // =========================================================================
  // Zone Map (MAGNIMS background overlay)
  // =========================================================================

  /** Zone map segmentation ID (null if not generated) */
  zoneMapSegId: string | null;

  /** Zone map 3D mask data (loaded separately from active segmentation) */
  zoneMapMask: Uint8Array | null;

  /** Zone map mask dimensions */
  zoneMapDims: { depth: number; height: number; width: number } | null;

  /** Whether zone map background overlay is visible */
  zoneMapVisible: boolean;

  /** True when the active segmentation IS the zone map itself (prevents dual rendering) */
  isZoneMapActiveSegmentation: boolean;

  /** Whether lesion mask should be colorized by MAGNIMS zone instead of label colors */
  zoneColorizeEnabled: boolean;

  /** Opacity for lesion segmentation overlay (0-1) */
  lesionOpacity: number;

  /** Opacity for zone map background overlay (0-1) */
  zoneMapOpacity: number;

  // =========================================================================
  // CALM-MS conformal second-reader (INVESTIGATIONAL) — additive tier overlay
  // =========================================================================

  /** Conformal review preset (validated operating point); persisted preference */
  conformalPreset: 'high_sensitivity' | 'balanced' | 'high_precision';
  /** Tier status mask (1=high,2=medium,3=low per candidate voxel, 0 else); additive */
  conformalStatusMask: Uint8Array | null;
  /** Status mask dimensions */
  conformalDims: { depth: number; height: number; width: number } | null;
  /** The /conformal/select summary (counts, fdr_target, population-scope, lesions) */
  conformalSummary: ConformalSummary | null;
  /** Whether the conformal tier overlay is visible */
  conformalVisible: boolean;

  // =========================================================================
  // Longitudinal Overlay (dual mask comparison)
  // =========================================================================

  /** TP1 mask for longitudinal overlay (blue = resolved) */
  longitudinalTp1Mask: Uint8Array | null;
  longitudinalTp1Dims: { depth: number; height: number; width: number } | null;
  longitudinalTp1SegId: string | null;
  /** TP2 mask for longitudinal overlay (red = new) */
  longitudinalTp2Mask: Uint8Array | null;
  longitudinalTp2Dims: { depth: number; height: number; width: number } | null;
  longitudinalTp2SegId: string | null;
  /** Whether longitudinal overlay is visible */
  longitudinalVisible: boolean;
  /** FLAIR subtraction heatmap (co-registered TP1 grid, uint8: 128=0, >128=brighter
   *  at follow-up=new signal, <128=darker). Diverging overlay for new-lesion review. */
  longitudinalSubtractionVolume: Uint8Array | null;
  longitudinalSubtractionDims: { depth: number; height: number; width: number } | null;
  longitudinalSubtractionClipSd: number;
  /** Whether the subtraction heatmap overlay is visible (separate toggle from masks). */
  longitudinalSubtractionVisible: boolean;

  // =========================================================================
  // Selected Lesion (bounding box + centroid highlight)
  // =========================================================================

  /** Currently selected lesion from LesionDashboard click (for bounding box + centroid rendering) */
  selectedLesion: LesionInfo | null;

  // =========================================================================
  // Actions - Segmentation
  // =========================================================================

  setCurrentSegmentation: (segmentation: SegmentationResponse | null) => void;
  setActiveSegmentation: (segmentation: Segmentation | null) => void;
  /**
   * Patch ONLY the mask-derived progress of the active segmentation, preserving
   * activeLabel / labelVisibility / isDirty / label edits — unlike setActiveSegmentation,
   * which re-seeds all of them. Used by the sync effect on a same-mask progress re-fire
   * (mask load complete, or annotatedVoxels recomputed after save) so the user's active
   * label and visibility toggles are not silently reset.
   */
  updateActiveSegmentationProgress: (progress: {
    slices_annotated: number;
    total_slices: number;
    progress_percentage: number;
  }) => void;
  setActiveSeriesId: (seriesId: string | null) => void;
  setSeriesSegmentations: (segmentations: SegmentationSummary[]) => void;
  setIsLoadingList: (loading: boolean) => void;
  setIsDirty: (dirty: boolean) => void;
  setIsSaving: (saving: boolean) => void;
  setLastSavedAt: (timestamp: string | null) => void;
  setSaveCallback: (fn: (() => Promise<void>) | null) => void;
  setCreateCallback: (fn: ((fileId: string, imageShape: { rows: number; columns: number; slices: number }) => void) | null) => void;
  setReloadMaskCallback: (fn: (() => Promise<void>) | null) => void;

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
  setLabelPreset: (preset: LabelPreset) => void;

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
  setDrawOverMode: (mode: DrawOverMode) => void;

  // =========================================================================
  // Actions - Overlay
  // =========================================================================

  setOverlayMode: (mode: OverlayMode) => void;
  setGlobalOpacity: (opacity: number) => void;
  setOutlineThickness: (thickness: number) => void;
  toggleOverlayVisibility: () => void;
  setIsOverlayVisible: (visible: boolean) => void;

  // =========================================================================
  // Actions - Zone Map
  // =========================================================================

  setZoneMap: (segId: string, mask: Uint8Array, dims: { depth: number; height: number; width: number }) => void;
  clearZoneMap: () => void;
  toggleZoneMapVisibility: () => void;
  toggleZoneColorize: () => void;
  setLesionOpacity: (opacity: number) => void;
  setZoneMapOpacity: (opacity: number) => void;

  // Actions - Conformal second-reader (CALM-MS)
  setConformalPreset: (preset: 'high_sensitivity' | 'balanced' | 'high_precision') => void;
  setConformalReview: (mask: Uint8Array, dims: { depth: number; height: number; width: number }, summary: ConformalSummary) => void;
  clearConformal: () => void;
  toggleConformalVisibility: () => void;

  // =========================================================================
  // Actions - Selected Lesion
  // =========================================================================

  setSelectedLesion: (lesion: LesionInfo | null) => void;
  setLongitudinalOverlay: (
    tp1: { mask: Uint8Array; dims: { depth: number; height: number; width: number }; segId: string } | null,
    tp2: { mask: Uint8Array; dims: { depth: number; height: number; width: number }; segId: string } | null,
  ) => void;
  clearLongitudinalOverlay: () => void;
  /** Set the FLAIR subtraction heatmap volume (co-registered TP1 grid) + show it. */
  setLongitudinalSubtraction: (
    sub: { volume: Uint8Array; dims: { depth: number; height: number; width: number }; clipSd: number } | null,
  ) => void;
  /** Toggle the subtraction heatmap overlay visibility. */
  toggleLongitudinalSubtraction: () => void;

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
  brushSize: 1,
  brushShape: 'square',
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

// Factory so every reset()/creation gets FRESH nested objects — returning a
// shared const would let an in-place mutation leak across resets and into the
// module-level defaults.
const createInitialState = () => ({
  // Segmentation
  currentSegmentation: null as SegmentationResponse | null,
  activeSegmentation: null as Segmentation | null,
  activeSeriesId: null as string | null,
  isDirty: false,
  isSaving: false,
  saveCallback: null as (() => Promise<void>) | null,
  createCallback: null as ((fileId: string, imageShape: { rows: number; columns: number; slices: number }) => void) | null,
  reloadMaskCallback: null as (() => Promise<void>) | null,
  lastSavedAt: null as string | null,

  // List
  seriesSegmentations: [] as SegmentationSummary[],
  isLoadingList: false,

  // Labels
  activeLabel: 1,
  labelVisibility: {} as Record<number, boolean>,

  // Paint tool
  paintTool: { ...defaultPaintTool },
  isPaintMode: false,
  drawOverMode: 'all' as DrawOverMode,

  // Overlay
  overlaySettings: { ...defaultOverlaySettings },
  isOverlayVisible: true,

  // Zone Map
  zoneMapSegId: null as string | null,
  zoneMapMask: null as Uint8Array | null,
  zoneMapDims: null as { depth: number; height: number; width: number } | null,
  zoneMapVisible: false,
  isZoneMapActiveSegmentation: false,
  zoneColorizeEnabled: false,
  lesionOpacity: 0.6,
  zoneMapOpacity: 0.3,

  // Conformal second-reader (CALM-MS)
  conformalPreset: 'high_sensitivity' as 'high_sensitivity' | 'balanced' | 'high_precision',
  conformalStatusMask: null as Uint8Array | null,
  conformalDims: null as { depth: number; height: number; width: number } | null,
  conformalSummary: null as ConformalSummary | null,
  conformalVisible: false,

  // Selected lesion
  selectedLesion: null as LesionInfo | null,

  // Longitudinal overlay
  longitudinalTp1Mask: null as Uint8Array | null,
  longitudinalTp1Dims: null as { depth: number; height: number; width: number } | null,
  longitudinalTp1SegId: null as string | null,
  longitudinalTp2Mask: null as Uint8Array | null,
  longitudinalTp2Dims: null as { depth: number; height: number; width: number } | null,
  longitudinalTp2SegId: null as string | null,
  longitudinalVisible: false,
  longitudinalSubtractionVolume: null as Uint8Array | null,
  longitudinalSubtractionDims: null as { depth: number; height: number; width: number } | null,
  longitudinalSubtractionClipSd: 3.0,
  longitudinalSubtractionVisible: false,
});

// ============================================================================
// Store
// ============================================================================

export const useSegmentationStore = create<SegmentationState>()(
  subscribeWithSelector(
    persist(
      (set, get) => ({
        ...createInitialState(),

        // =====================================================================
        // Segmentation Actions
        // =====================================================================

        setCurrentSegmentation: (segmentation) =>
          set({ currentSegmentation: segmentation }),

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

        updateActiveSegmentationProgress: (progress) =>
          set((state) => {
            if (!state.activeSegmentation) return state;
            // Progress-only patch: NEVER touch activeLabel/labelVisibility/isDirty here.
            return {
              activeSegmentation: {
                ...state.activeSegmentation,
                slices_annotated: progress.slices_annotated,
                total_slices: progress.total_slices,
                progress_percentage: progress.progress_percentage,
              },
            };
          }),

        setActiveSeriesId: (seriesId) => set({ activeSeriesId: seriesId }),

        setSeriesSegmentations: (segmentations) =>
          set({ seriesSegmentations: segmentations }),

        setIsLoadingList: (loading) => set({ isLoadingList: loading }),

        setIsDirty: (dirty) => set({ isDirty: dirty }),

        setIsSaving: (saving) => set({ isSaving: saving }),

        setLastSavedAt: (timestamp) => set({ lastSavedAt: timestamp }),

        setSaveCallback: (fn) => set({ saveCallback: fn }),

        setCreateCallback: (fn) => set({ createCallback: fn }),

        setReloadMaskCallback: (fn) => set({ reloadMaskCallback: fn }),

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

        setLabelPreset: (preset) =>
          set((state) => {
            if (!state.activeSegmentation) return state;
            const labels = DEFAULT_LABEL_PRESETS[preset];
            if (!labels) return state;
            const visibility: Record<number, boolean> = {};
            labels.forEach((l) => { visibility[l.id] = l.visible; });
            // Also write the CANONICAL labels onto currentSegmentation.metadata: the
            // sync effect rebuilds activeSegmentation.labels from there, and save reads
            // from there — so previously a preset change lived only on the derived
            // activeSegmentation and was silently lost on the next re-sync and never
            // persisted. Keeping both in step closes that data-loss path.
            const cur = state.currentSegmentation;
            const currentSegmentation = cur
              ? { ...cur, metadata: { ...cur.metadata, labels } }
              : cur;
            return {
              activeSegmentation: { ...state.activeSegmentation, labels },
              currentSegmentation,
              labelVisibility: visibility,
              activeLabel: labels.find((l) => l.id !== 0)?.id ?? 1,
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

        setDrawOverMode: (mode) => set({ drawOverMode: mode }),

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
        // Zone Map Actions
        // =====================================================================

        setZoneMap: (segId, mask, dims) =>
          set({ zoneMapSegId: segId, zoneMapMask: mask, zoneMapDims: dims }),

        clearZoneMap: () =>
          set({ zoneMapSegId: null, zoneMapMask: null, zoneMapDims: null, zoneMapVisible: false, isZoneMapActiveSegmentation: false, zoneColorizeEnabled: false }),

        // Conformal second-reader (CALM-MS) — additive tier overlay
        setConformalPreset: (preset) =>
          // Changing the operating point invalidates the shown result -> force a
          // re-run so the panel never highlights a preset while showing another's tiers.
          set({ conformalPreset: preset, conformalStatusMask: null, conformalDims: null, conformalSummary: null, conformalVisible: false }),
        setConformalReview: (mask, dims, summary) =>
          set({ conformalStatusMask: mask, conformalDims: dims, conformalSummary: summary, conformalVisible: true }),
        clearConformal: () =>
          set({ conformalStatusMask: null, conformalDims: null, conformalSummary: null, conformalVisible: false }),
        toggleConformalVisibility: () =>
          set((state) => ({ conformalVisible: !state.conformalVisible })),

        toggleZoneMapVisibility: () =>
          set((state) => ({
            zoneMapVisible: !state.zoneMapVisible,
            // Auto-sync: colorize lesions when zone map is shown
            zoneColorizeEnabled: !state.zoneMapVisible,
          })),

        toggleZoneColorize: () =>
          set((state) => ({ zoneColorizeEnabled: !state.zoneColorizeEnabled })),

        setLesionOpacity: (opacity) =>
          set({ lesionOpacity: Math.max(0, Math.min(1, opacity)) }),

        setZoneMapOpacity: (opacity) =>
          set({ zoneMapOpacity: Math.max(0, Math.min(1, opacity)) }),

        // =====================================================================
        // Selected Lesion Actions
        // =====================================================================

        setSelectedLesion: (lesion) => set({ selectedLesion: lesion }),
        setLongitudinalOverlay: (tp1, tp2) => set({
          longitudinalTp1Mask: tp1?.mask ?? null,
          longitudinalTp1Dims: tp1?.dims ?? null,
          longitudinalTp1SegId: tp1?.segId ?? null,
          longitudinalTp2Mask: tp2?.mask ?? null,
          longitudinalTp2Dims: tp2?.dims ?? null,
          longitudinalTp2SegId: tp2?.segId ?? null,
          longitudinalVisible: true,
        }),
        clearLongitudinalOverlay: () => set({
          longitudinalTp1Mask: null, longitudinalTp1Dims: null, longitudinalTp1SegId: null,
          longitudinalTp2Mask: null, longitudinalTp2Dims: null, longitudinalTp2SegId: null,
          longitudinalVisible: false,
          longitudinalSubtractionVolume: null, longitudinalSubtractionDims: null,
          longitudinalSubtractionVisible: false,
        }),
        setLongitudinalSubtraction: (sub) => set({
          longitudinalSubtractionVolume: sub?.volume ?? null,
          longitudinalSubtractionDims: sub?.dims ?? null,
          longitudinalSubtractionClipSd: sub?.clipSd ?? 3.0,
          longitudinalSubtractionVisible: sub != null,
        }),
        toggleLongitudinalSubtraction: () => set((s) => ({
          longitudinalSubtractionVisible: !s.longitudinalSubtractionVisible,
        })),

        // =====================================================================
        // Reset Actions
        // =====================================================================

        reset: () => set(createInitialState()),

        resetPaintTool: () =>
          set({
            paintTool: defaultPaintTool,
            isPaintMode: false,
          }),
      }),
      {
        name: 'segmentation-store',
        partialize: (state) => ({
          // Only persist user preferences, not active data
          paintTool: state.paintTool,
          overlaySettings: state.overlaySettings,
          drawOverMode: state.drawOverMode,
          lesionOpacity: state.lesionOpacity,
          zoneMapOpacity: state.zoneMapOpacity,
          conformalPreset: state.conformalPreset,
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
