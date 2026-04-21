/**
 * useActiveSliceInfo — Unified slice navigation hook.
 *
 * Single source of truth for slice index, total slices, and setter.
 * Routes to the correct store automatically:
 *   - Single panel → useViewerStore (global slice state)
 *   - Multi panel  → useMultiViewerStore (active panel's slice state)
 *
 * This eliminates the disconnect where the toolbar showed stale data
 * from the single-panel store while multi-panel was active.
 */

import { useViewerStore } from '@/store/useViewerStore';
import { useMultiViewerStore } from '@/store/useMultiViewerStore';

interface ActiveSliceInfo {
  sliceIndex: number;
  totalSlices: number;
  setSliceIndex: (index: number) => void;
}

export function useActiveSliceInfo(): ActiveSliceInfo {
  const layout = useMultiViewerStore((s) => s.layout);
  const isMultiPanel = layout !== 'single';

  // Multi-panel state
  const activePanelId = useMultiViewerStore((s) => s.activePanelId);
  const panels = useMultiViewerStore((s) => s.panels);
  const multiSetSlice = useMultiViewerStore((s) => s.setSliceIndex);

  // Single-panel state
  const singleSliceIndex = useViewerStore((s) => s.currentSliceIndex);
  const singleSetSlice = useViewerStore((s) => s.setCurrentSliceIndex);
  const singleTotalSlices = useViewerStore((s) => s.currentSeries?.total_slices ?? 0);

  if (isMultiPanel) {
    const activePanel = panels.find((p) => p.id === activePanelId);
    return {
      sliceIndex: activePanel?.sliceIndex ?? 0,
      totalSlices: activePanel?.metadata?.slices ?? 0,
      setSliceIndex: (index: number) => multiSetSlice(activePanelId, index),
    };
  }

  return {
    sliceIndex: singleSliceIndex,
    totalSlices: singleTotalSlices,
    setSliceIndex: singleSetSlice,
  };
}
