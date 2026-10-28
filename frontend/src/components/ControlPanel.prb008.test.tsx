/**
 * PRB-008 — film capture (coordinator, 2026-10-28): in the side-by-side 2D panels, the slice number of the sidebar
 * (ControlPanel's slice navigator) did not follow the panels. It read the single view's slice index while the grid
 * navigates its own per-panel index (useMultiViewerStore): the sidebar said one slice, the panels showed another,
 * and its slider moved nothing on screen. The toolbar already reads the active slice (useActiveSliceInfo).
 *
 * The real ControlPanel; its patient / study queries and its two sub-panels replaced.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@niivue/niivue', async () => (await import('@/test/fakeNiivue')).niivueModule);
vi.mock('@/hooks/usePatients', () => ({ usePatient: () => ({ data: null }), useMedicalHistory: () => ({ data: null }) }));
vi.mock('@/api/study', () => ({ studyAPI: new Proxy({}, { get: () => async () => [] }) }));
vi.mock('./LongitudinalCompare', () => ({ LongitudinalCompare: () => null }));
vi.mock('./SegmentationComparison', () => ({ SegmentationComparison: () => null }));

import ControlPanel from './ControlPanel';
import { useViewerStore } from '@/store/useViewerStore';
import { useMultiViewerStore } from '@/store/useMultiViewerStore';

const SERIES = {
  id: 's', name: 'flair', format: 'nifti', file_id: 'f.nii.gz', total_slices: 40,
  metadata: { rows: 8, columns: 8, slices: 40 }, slices: [],
};

function renderPanel() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ControlPanel />
    </QueryClientProvider>,
  );
}

/** The sidebar's slice navigator: its "n / total" text and its slider. */
function sidebarSlice() {
  const slider = document.querySelector('input[type="range"]') as HTMLInputElement;
  const label = slider.parentElement!.querySelector('span.font-mono') as HTMLElement;
  return { slider, text: label.textContent?.replace(/\s+/g, ' ').trim() };
}

beforeEach(() => {
  useViewerStore.getState().reset();
  useMultiViewerStore.getState().reset();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useViewerStore.setState({ viewMode: '2d', currentSeries: SERIES as any, currentSliceIndex: 3 });
});

describe('PRB-010 R6 — the cursor readout names the label under the cursor', () => {
  it('rc076 R6: the sidebar names the region under the cursor, and an unlisted value as such', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    useViewerStore.setState({ cursorInfo: { x: 3, y: 4, z: 3, intensity: 120, label: { value: 4, name: 'Deep White Matter' } } as any });
    const { unmount } = render(
      <QueryClientProvider client={new QueryClient()}><ControlPanel /></QueryClientProvider>);
    expect(screen.getByTestId('cursor-label')).toHaveTextContent('Deep White Matter');
    unmount();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    useViewerStore.setState({ cursorInfo: { x: 3, y: 4, z: 3, intensity: 120, label: { value: 9, name: null } } as any });
    render(<QueryClientProvider client={new QueryClient()}><ControlPanel /></QueryClientProvider>);
    expect(screen.getByTestId('cursor-label')).toHaveTextContent(/9.*not in the label table/i);
  });

  it('rc076 R6: the 2D viewer puts the label under the cursor into the readout (call site)', async () => {
    const { readFileSync } = await import('node:fs');
    const { join } = await import('node:path');
    const src = readFileSync(join(__dirname, 'ImageViewer2D.tsx'), 'utf-8');
    expect(src).toMatch(/labelUnderCursor\(segmentationMask\.getSliceMask\(currentSliceIndex\)/);
    expect(src).toMatch(/setCursorInfo\(\{[^}]*\blabel\b/);
  });
});

describe('PRB-008 — the sidebar slice follows the side-by-side panels', () => {
  it('prb008 single view: the sidebar shows the viewer slice (guard)', () => {
    renderPanel();
    expect(sidebarSlice().text).toBe('4 / 40');
  });

  it('prb008 2x2: the sidebar shows the active panel slice and its slice count', () => {
    const multi = useMultiViewerStore.getState();
    multi.setLayout('2x2');
    multi.setPanelImageData('panel-0', 'AA', { rows: 8, columns: 8, slices: 40 });
    multi.setPanelImageData('panel-1', 'AA', { rows: 8, columns: 8, slices: 24 });
    multi.setPanelSliceIndex('panel-0', 19);
    multi.setPanelSliceIndex('panel-1', 11);
    multi.setActivePanelId('panel-1');
    renderPanel();
    expect(sidebarSlice().text).toBe('12 / 24');
  });

  it('prb008 2x2: moving the sidebar slider moves the panels, not a hidden single-view index', () => {
    const multi = useMultiViewerStore.getState();
    multi.setLayout('2x2');
    multi.setPanelImageData('panel-0', 'AA', { rows: 8, columns: 8, slices: 40 });
    multi.setPanelSliceIndex('panel-0', 19);
    renderPanel();
    fireEvent.change(sidebarSlice().slider, { target: { value: '25' } });
    expect(useMultiViewerStore.getState().panels[0].sliceIndex).toBe(25);
    expect(useViewerStore.getState().currentSliceIndex).toBe(3);
    expect(screen.getByText('26 / 40')).toBeInTheDocument();
  });
});
