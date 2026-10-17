/**
 * v3 slice state: one 3-D cursor; the slider index always means "position along the
 * active plane's normal axis"; leaving the in-browser path restores the k-plane
 * meaning; a different image resets the cursor (never reuse a voxel of another grid).
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { useViewerStore } from './useViewerStore';
import type { ImageSeriesResponse } from '@/types';

const series = (file: string) => ({
  id: file, name: file, format: 'nifti', metadata: { rows: 10, columns: 20, slices: 30 },
  total_slices: 30, slices: [], file_id: file,
}) as ImageSeriesResponse;

describe('viewer store — 3-D cursor and active plane', () => {
  beforeEach(() => useViewerStore.getState().reset());

  it('slice index follows the active normal axis and moves only that cursor coordinate', () => {
    const s = useViewerStore.getState();
    s.setCurrentSeries(series('a'));
    s.setCursorVoxel([4, 9, 14]);
    s.setActiveSliceGeometry(0, 10);            // sagittal-like: normal = i
    expect(useViewerStore.getState().currentSliceIndex).toBe(4);
    useViewerStore.getState().setCurrentSliceIndex(7);
    expect(useViewerStore.getState().cursorVoxel).toEqual([7, 9, 14]);
    useViewerStore.getState().setActiveSliceGeometry(2, 30);  // back to k
    expect(useViewerStore.getState().currentSliceIndex).toBe(14);
  });

  it('clamps the slice index into the active depth', () => {
    const s = useViewerStore.getState();
    s.setCurrentSeries(series('a'));
    s.setCursorVoxel([4, 19, 29]);
    s.setActiveSliceGeometry(1, 20);
    expect(useViewerStore.getState().currentSliceIndex).toBe(19);
  });

  it('resetSliceGeometry restores the legacy k-plane meaning', () => {
    const s = useViewerStore.getState();
    s.setCurrentSeries(series('a'));
    s.setCursorVoxel([4, 9, 14]);
    s.setActiveSliceGeometry(0, 10);
    useViewerStore.getState().resetSliceGeometry();
    const st = useViewerStore.getState();
    expect(st.sliceNormalAxis).toBe(2);
    expect(st.sliceCount).toBeNull();
    expect(st.currentSliceIndex).toBe(14);
  });

  it('a different image drops the cursor; the same image keeps it', () => {
    const s = useViewerStore.getState();
    s.setCurrentSeries(series('a'));
    s.setCursorVoxel([1, 2, 3]);
    useViewerStore.getState().setCurrentSeries(series('a'));
    expect(useViewerStore.getState().cursorVoxel).toEqual([1, 2, 3]);
    useViewerStore.getState().setCurrentSeries(series('b'));
    expect(useViewerStore.getState().cursorVoxel).toBeNull();
    expect(useViewerStore.getState().sliceCount).toBeNull();
  });

  it('legacy path without a cursor behaves exactly as before', () => {
    useViewerStore.getState().setCurrentSliceIndex(12);
    expect(useViewerStore.getState().currentSliceIndex).toBe(12);
    expect(useViewerStore.getState().cursorVoxel).toBeNull();
  });
});
