/**
 * Multi-Viewer Store - Zustand state management for multi-panel MRI viewing.
 *
 * Manages layout mode, per-panel state, and synchronized navigation
 * for side-by-side MRI sequence comparison.
 *
 * @module store/useMultiViewerStore
 */

import { create } from 'zustand';
import type { SequenceType } from '@/utils/sequenceDetection';

export type ViewerLayout = 'single' | '1x2' | '2x2';

export interface PanelState {
  id: string;
  instanceId: string | null;
  sequence: SequenceType;
  sliceIndex: number;
  /** Base64 slice images loaded for this panel's instance */
  imageData: string | null;
  /** Image metadata */
  metadata: {
    rows: number;
    columns: number;
    slices: number;
  } | null;
  /** Whether this panel is currently loading */
  isLoading: boolean;
}

interface MultiViewerState {
  /** Current layout mode */
  layout: ViewerLayout;
  /** Per-panel state (1-4 panels) */
  panels: PanelState[];
  /** Whether slice navigation is synchronized across panels */
  syncSlice: boolean;
  /** Which panel is focused for keyboard navigation */
  activePanelId: string;

  // Actions
  setLayout: (layout: ViewerLayout) => void;
  setSliceIndex: (panelId: string, index: number) => void;
  assignInstance: (panelId: string, instanceId: string, sequence: SequenceType) => void;
  setPanelImageData: (panelId: string, imageData: string, metadata: { rows: number; columns: number; slices: number }) => void;
  setPanelLoading: (panelId: string, loading: boolean) => void;
  setActivePanelId: (panelId: string) => void;
  setSyncSlice: (sync: boolean) => void;
  /** Auto-assign instances to panels based on sequence detection */
  autoAssign: (assignments: { instanceId: string; sequence: SequenceType }[]) => void;
  reset: () => void;
}

function createDefaultPanels(): PanelState[] {
  return [
    { id: 'panel-0', instanceId: null, sequence: 'unknown', sliceIndex: 0, imageData: null, metadata: null, isLoading: false },
    { id: 'panel-1', instanceId: null, sequence: 'unknown', sliceIndex: 0, imageData: null, metadata: null, isLoading: false },
    { id: 'panel-2', instanceId: null, sequence: 'unknown', sliceIndex: 0, imageData: null, metadata: null, isLoading: false },
    { id: 'panel-3', instanceId: null, sequence: 'unknown', sliceIndex: 0, imageData: null, metadata: null, isLoading: false },
  ];
}

const initialState = {
  layout: 'single' as ViewerLayout,
  panels: createDefaultPanels(),
  syncSlice: true,
  activePanelId: 'panel-0',
};

export const useMultiViewerStore = create<MultiViewerState>()((set, get) => ({
  ...initialState,

  setLayout: (layout) => set({ layout }),

  setSliceIndex: (panelId, index) => {
    const { syncSlice, panels } = get();
    if (syncSlice) {
      // Sync all panels to the same slice index
      set({
        panels: panels.map((p) => ({ ...p, sliceIndex: index })),
      });
    } else {
      set({
        panels: panels.map((p) =>
          p.id === panelId ? { ...p, sliceIndex: index } : p
        ),
      });
    }
  },

  assignInstance: (panelId, instanceId, sequence) =>
    set((state) => ({
      panels: state.panels.map((p) =>
        p.id === panelId
          ? { ...p, instanceId, sequence, sliceIndex: 0, imageData: null, metadata: null, isLoading: false }
          : p
      ),
    })),

  setPanelImageData: (panelId, imageData, metadata) =>
    set((state) => ({
      panels: state.panels.map((p) =>
        p.id === panelId ? { ...p, imageData, metadata, isLoading: false } : p
      ),
    })),

  setPanelLoading: (panelId, loading) =>
    set((state) => ({
      panels: state.panels.map((p) =>
        p.id === panelId ? { ...p, isLoading: loading } : p
      ),
    })),

  setActivePanelId: (panelId) => set({ activePanelId: panelId }),

  setSyncSlice: (sync) => set({ syncSlice: sync }),

  autoAssign: (assignments) =>
    set((state) => {
      const panels = [...state.panels];
      for (let i = 0; i < Math.min(assignments.length, 4); i++) {
        panels[i] = {
          ...panels[i],
          instanceId: assignments[i].instanceId,
          sequence: assignments[i].sequence,
          sliceIndex: 0,
          imageData: null,
          metadata: null,
          isLoading: false,
        };
      }
      // Clear unused panels
      for (let i = assignments.length; i < 4; i++) {
        panels[i] = {
          ...panels[i],
          instanceId: null,
          sequence: 'unknown',
          sliceIndex: 0,
          imageData: null,
          metadata: null,
          isLoading: false,
        };
      }
      return { panels };
    }),

  reset: () => set(initialState),
}));

/** Get active panels count based on layout */
export function getPanelCount(layout: ViewerLayout): number {
  switch (layout) {
    case 'single': return 1;
    case '1x2': return 2;
    case '2x2': return 4;
    default: return 1;
  }
}
