/**
 * PRB-030 (L1 of the last check of PR #69), on the real viewer page — the standard 2D view says which image it draws
 * under the open segmentation, with both grids, so Confirm can be refused while the mask is drawn over an image of
 * another grid (sheared or cut off). Published together with `overlayOnScreen` (the standard view, one panel,
 * segmentation mode on), and withdrawn with it in every other view.
 *
 * Written before the correction (fails on ca600c2). Harness of ViewerApp.release20261029.test.tsx.
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

import ViewerApp from './ViewerApp';
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

type ImageOnScreen = { segmentationId: string; imageFileId: string | null;
  image: { width: number; height: number; depth: number }; mask: { width: number; height: number; depth: number } | null };
const imageOnScreen = () =>
  (useSegmentationStore.getState() as unknown as { overlayImageOnScreen?: ImageOnScreen | null }).overlayImageOnScreen;
const flair = `patients/${fx.P}/studies/${fx.S}/series/${fx.SE}/flair.nii.gz`;

async function openSegmentation() {
  const row = await renderViewer();
  fireEvent.click(row);
  await waitFor(() => expect(useSegmentationStore.getState().currentSegmentation?.segmentation_id).toBe('seg-1'));
}

describe('PRB-030: the standard 2D view publishes the image it draws under the segmentation', () => {
  it('rc092 prb030 the image file and its grid (columns x rows x slices) are published with the open segmentation', async () => {
    await openSegmentation();
    await waitFor(() => expect(imageOnScreen()).toEqual(expect.objectContaining({
      segmentationId: 'seg-1', imageFileId: flair, image: { width: 182, height: 218, depth: 3 } })));
    expect(imageOnScreen()).toHaveProperty('mask');
  });

  it.each(['render niivue', 'render matplotlib'])('rc092 prb030 %s: nothing is published', async (button) => {
    await openSegmentation();
    await waitFor(() => expect(imageOnScreen()?.segmentationId).toBe('seg-1'));
    fireEvent.click(screen.getByText(button));
    await waitFor(() => expect(imageOnScreen()).toBeNull());
  });

  it('rc092 prb030 segmentation mode off, the 3D view or the multi-panel layout: nothing is published', async () => {
    await openSegmentation();
    await waitFor(() => expect(imageOnScreen()?.segmentationId).toBe('seg-1'));
    fireEvent.click(screen.getByText('toggle segmentation mode'));
    await waitFor(() => expect(imageOnScreen()).toBeNull());
    fireEvent.click(screen.getByText('toggle segmentation mode'));
    await waitFor(() => expect(imageOnScreen()?.segmentationId).toBe('seg-1'));
    act(() => useViewerStore.getState().setViewMode('3d'));
    await waitFor(() => expect(imageOnScreen()).toBeNull());
    act(() => useViewerStore.getState().setViewMode('2d'));
    await waitFor(() => expect(imageOnScreen()?.segmentationId).toBe('seg-1'));
    act(() => useMultiViewerStore.getState().setLayout('1x2'));
    await waitFor(() => expect(imageOnScreen()).toBeNull());
  });
});
