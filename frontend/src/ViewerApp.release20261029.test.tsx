/**
 * Release 2026-10-25 — final check of PR #69 (dd22708..39d9730), R1 and R2, on the real viewer page.
 *
 *  - R1: the DIS confirmation guard must know which view is on screen. Only the standard 2D view (one panel), in
 *    segmentation mode, draws the open segmentation with its label table; it now publishes the segmentation it draws
 *    (`overlayOnScreen`). Segmentation mode off, the NiiVue or matplotlib render modes, the multi-panel layout and the
 *    3D view publish nothing (nothing, plain red or the overlay loaded before the classification is drawn there).
 *  - R2: the label-preset switch of the overlay controls is locked while a classified segmentation is open (it
 *    redrew the MAGNIMS values with the "Default" names and colours).
 *
 * Written before the corrections (fails on 39d9730). Harness of ViewerApp.release20261028.test.tsx; the viewer
 * controls are replaced by buttons that call the same setters the real ones do.
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

const fx = vi.hoisted(() => {
  const P = '11111111-1111-4111-8111-111111111111';
  const S = '22222222-2222-4222-8222-222222222222';
  const SE = '33333333-3333-4333-8333-333333333333';
  const file = (name: string) => `patients/${P}/studies/${S}/series/${SE}/${name}`;
  const anyApi = (known: Record<string, unknown>) => new Proxy(known, {
    get: (target, key: string) => (key in target ? target[key] : async () => ({})),
  });
  const BINARY = [{ id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
                  { id: 1, name: 'Lesion', color: '#FF0000', opacity: 0.5, visible: true }];
  const MAGNIMS = [{ id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
                   { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true },
                   { id: 2, name: 'Juxtacortical', color: '#00CC00', opacity: 0.6, visible: true },
                   { id: 3, name: 'Infratentorial', color: '#0066FF', opacity: 0.6, visible: true },
                   { id: 4, name: 'Deep White Matter', color: '#FFD700', opacity: 0.6, visible: true }];
  const seg = (labels: unknown[], analysis: Record<string, unknown> | null) => ({
    segmentation_id: 'seg-1', file_id: file('flair.nii.gz'), total_slices: 3,
    metadata: { file_id: file('flair.nii.gz'), description: 'Expert Rater', created_at: 'T0', modified_at: 'T2',
                labels, analysis_data: analysis },
  });
  return {
    anyApi, P, S, SE,
    USER: { id: 'u1', username: 'dr', email: 'dr@example.org', full_name: 'Dr Test', role: 'RADIOLOGIST' },
    PATIENT: { id: P, full_name: 'Ana Torres', mrn: 'MRN-99120', age: 40, gender: 'female' },
    INSTANCES: [{ id: 'i-flair', series_id: SE, gcs_object_name: file('flair.nii.gz'), original_filename: 'sub-01_FLAIR.nii.gz' }],
    BINARY, MAGNIMS,
    // the sidebar list fetched BEFORE the classification ...
    STALE: seg(BINARY, null),
    // ... and the server's record AFTER it (labels 1-4 stored with the classified mask)
    FRESH: seg(MAGNIMS, { classification: { method: 'geometric' } }),
    getSegmentation: { fn: null as unknown as (id: string) => Promise<unknown> },
  };
});

vi.mock('@niivue/niivue', async () => (await import('@/test/fakeNiivue')).niivueModule);
vi.mock('framer-motion', async () => {
  const React = await import('react');
  const cache = new Map<string, unknown>();
  const motion = new Proxy({}, {
    get: (_t, tag: string) => {
      if (!cache.has(tag)) {
        cache.set(tag, React.forwardRef((props: Record<string, unknown>, ref) => {
          const { initial: _i, animate: _a, exit: _e, transition: _t2, whileHover: _h, whileTap: _w, layout: _l, ...rest } = props;
          return React.createElement(tag, { ...rest, ref });
        }));
      }
      return cache.get(tag);
    },
  });
  return { motion, AnimatePresence: ({ children }: { children: unknown }) => children };
});
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: fx.USER, logout: vi.fn(), isAuthenticated: true, isLoading: false }),
}));
vi.mock('@/contexts/ThemeContext', () => ({
  useTheme: () => ({ theme: 'dark', toggleTheme: vi.fn(), setTheme: vi.fn() }),
}));
vi.mock('@/hooks/usePatients', () => ({ usePatient: () => ({ data: fx.PATIENT }) }));
vi.mock('@/api/study', () => ({
  studyAPI: {
    getById: vi.fn(async () => ({ id: fx.S, patient_id: fx.P, study_description: 'Brain MRI', modality: 'MR', study_date: '2026-01-01' })),
    listSeries: vi.fn(async () => [{ id: fx.SE, study_id: fx.S }]),
    listInstances: vi.fn(async () => fx.INSTANCES),
  },
}));
vi.mock('@/api/imaging', () => ({
  imagingAPI: fx.anyApi({
    processImage: vi.fn(async (fileId: string) => ({
      id: fileId, name: fileId, format: 'nifti', total_slices: 3,
      metadata: { rows: 218, columns: 182, slices: 3, pixel_spacing: [1, 1], anatomical_orientation: 'LAS' },
      slices: [0, 1, 2].map((i) => ({ slice_index: i, image_data: 'AAAA', format: 'nifti', width: 182, height: 218 })),
    })),
  }),
}));
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: fx.anyApi({
    listSegmentationsByFileIds: vi.fn(async () => [fx.STALE]),
    listSegmentations: vi.fn(async () => [fx.STALE]),
    getSegmentation: (id: string) => fx.getSegmentation.fn(id),
  }),
}));
vi.mock('./components/ControlPanel', () => ({ default: () => null }));
vi.mock('./components/ViewerControls', () => ({
  default: (p: { segmentationMode: boolean; setSegmentationMode: (v: boolean) => void; setRenderMode: (m: string) => void }) => (
    <div>
      <button onClick={() => p.setSegmentationMode(!p.segmentationMode)}>toggle segmentation mode</button>
      <button onClick={() => p.setRenderMode('niivue')}>render niivue</button>
      <button onClick={() => p.setRenderMode('matplotlib')}>render matplotlib</button>
      <button onClick={() => p.setRenderMode('standard')}>render standard</button>
    </div>
  ),
}));
vi.mock('./components/AIReportPanel', () => ({ AIReportPanel: () => null, default: () => null }));
vi.mock('./components/LesionDashboard', () => ({ LesionDashboard: () => null }));
vi.mock('./components/MAGNIMSZoneMapPanel', () => ({ MAGNIMSZoneMapPanel: () => null }));
vi.mock('./components/ReportViewerModal', () => ({ ReportViewerModal: () => null }));
vi.mock('./components/QuickScreenBadge', () => ({ QuickScreenBadge: () => null }));

import ViewerApp, { OverlayControls } from './ViewerApp';
import { useViewerStore } from '@/store/useViewerStore';
import { useMultiViewerStore } from '@/store/useMultiViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { fakeNiivue } from '@/test/fakeNiivue';

const saved: Record<string, PropertyDescriptor | undefined> = {};
beforeAll(() => {
  for (const [key, value] of [['clientWidth', 800], ['clientHeight', 600]] as const) {
    saved[key] = Object.getOwnPropertyDescriptor(HTMLElement.prototype, key);
    Object.defineProperty(HTMLElement.prototype, key, { configurable: true, get: () => value });
  }
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, headers: { get: () => null }, arrayBuffer: async () => new ArrayBuffer(16), text: async () => '', json: async () => ({}),
  })));
  URL.createObjectURL = vi.fn(() => 'blob:release');
  URL.revokeObjectURL = vi.fn();
});
afterAll(() => {
  for (const key of ['clientWidth', 'clientHeight']) {
    if (saved[key]) Object.defineProperty(HTMLElement.prototype, key, saved[key]!);
  }
  vi.unstubAllGlobals();
});
beforeEach(() => {
  cleanup();
  fakeNiivue.instances.length = 0;
  useViewerStore.setState({ viewMode: '2d', currentSeries: null, render3DMode: 'volume' });
  useMultiViewerStore.getState().reset();
  useSegmentationStore.setState({ selectedLesion: null, currentSegmentation: null, activeSegmentation: null });
  fx.getSegmentation.fn = vi.fn(async () => JSON.parse(JSON.stringify(fx.FRESH)));
});

async function renderViewer() {
  const root = document.createElement('div');
  root.id = 'root';
  document.body.appendChild(root);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[`/app/viewer?studyId=${fx.S}`]}>
        <ViewerApp />
      </MemoryRouter>
    </QueryClientProvider>,
    { container: root },
  );
  await waitFor(() => expect(useViewerStore.getState().currentSeries).not.toBeNull(), { timeout: 5000 });
  return screen.findByText('Expert Rater', {}, { timeout: 5000 });
}

const labelIds = (labels: Array<{ id: number }> | undefined) => (labels ?? []).map((l) => l.id);

const onScreen = () => (useSegmentationStore.getState() as unknown as { overlayOnScreen?: string | null }).overlayOnScreen;

async function openSegmentation() {
  const row = await renderViewer();
  fireEvent.click(row);
  await waitFor(() => expect(useSegmentationStore.getState().currentSegmentation?.segmentation_id).toBe('seg-1'));
}

describe('R1: the view on screen says which segmentation it draws with its label table', () => {
  it('rc071 release final r1 the standard 2D view in segmentation mode publishes the open segmentation', async () => {
    await openSegmentation();
    await waitFor(() => expect(onScreen()).toBe('seg-1'));
  });

  it('rc071 release final r1 segmentation mode off: nothing is published', async () => {
    await openSegmentation();
    await waitFor(() => expect(onScreen()).toBe('seg-1'));
    fireEvent.click(screen.getByText('toggle segmentation mode'));
    await waitFor(() => expect(onScreen()).toBeNull());
    fireEvent.click(screen.getByText('toggle segmentation mode'));
    await waitFor(() => expect(onScreen()).toBe('seg-1'));
  });

  it.each(['render niivue', 'render matplotlib'])('rc071 release final r1 %s: nothing is published', async (button) => {
    await openSegmentation();
    await waitFor(() => expect(onScreen()).toBe('seg-1'));
    fireEvent.click(screen.getByText(button));
    await waitFor(() => expect(onScreen()).toBeNull());
  });

  it('rc071 release final r1 the 3D view: nothing is published', async () => {
    await openSegmentation();
    await waitFor(() => expect(onScreen()).toBe('seg-1'));
    act(() => useViewerStore.getState().setViewMode('3d'));
    await waitFor(() => expect(onScreen()).toBeNull());
  });

  it('rc071 release final r1 the multi-panel layout: nothing is published', async () => {
    await openSegmentation();
    await waitFor(() => expect(onScreen()).toBe('seg-1'));
    act(() => useMultiViewerStore.getState().setLayout('1x2'));
    await waitFor(() => expect(onScreen()).toBeNull());
  });

  it('rc071 release final r1 closing the segmentation: nothing is published', async () => {
    await openSegmentation();
    await waitFor(() => expect(onScreen()).toBe('seg-1'));
    fireEvent.click(screen.getByText('Expert Rater'));
    await waitFor(() => expect(onScreen()).toBeNull());
  });
});

describe('R2: the label preset cannot be switched while a classified segmentation is open', () => {
  const seed = (analysis: Record<string, unknown> | null) => useSegmentationStore.setState({
    currentSegmentation: { ...JSON.parse(JSON.stringify(fx.FRESH)), metadata: { ...fx.FRESH.metadata, analysis_data: analysis } },
    activeSegmentation: { id: 'seg-1', labels: fx.MAGNIMS } as never,
    labelVisibility: { 0: false, 1: true, 2: true, 3: true, 4: true },
    maskLabelValues: [1, 2, 3, 4],
  } as never);

  it('rc071 release final r2 the preset switch is locked on a classified segmentation', () => {
    seed({ classification: { method: 'geometric' } });
    render(<OverlayControls />);
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select).toBeDisabled();
    expect(screen.getByTestId('label-preset-locked')).toBeInTheDocument();
    fireEvent.change(select, { target: { value: 'default' } });
    expect(useSegmentationStore.getState().activeSegmentation?.labels.map((l) => l.name))
      .toEqual(fx.MAGNIMS.map((l) => l.name));
  });

  it('rc071 release final r2 an unclassified segmentation keeps the preset switch (positive control)', () => {
    seed(null);
    render(<OverlayControls />);
    expect(screen.getByRole('combobox')).not.toBeDisabled();
    expect(screen.queryByTestId('label-preset-locked')).not.toBeInTheDocument();
  });
});
