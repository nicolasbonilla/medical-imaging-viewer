/**
 * Release 2026-10-25 — independent review of PR #69 (6d1fde2..dd22708), blocker B1 (F08 still reachable).
 *
 * The real viewer page opened a segmentation from the sidebar's cached list (`['segmentations','study',studyId]`),
 * which the region classification never refreshed: after "Auto-Classify Regions", closing and reopening the
 * segmentation (or opening one classified while it was not open) seeded the drawn labels from the stale list
 * ([Background, Lesion]) while the mask held 1-4 — lesions labelled 2-4 were not drawn, and confirmation was offered.
 * Now a segmentation is opened from the server (`getSegmentation`), every time; and the overlay controls warn when
 * the mask holds a value the label table does not name.
 *
 * Written before the correction (fails on dd22708). Only the backend, the WebGL renderer, animations and the side
 * panels are replaced (harness of ViewerApp.capa010.test.tsx).
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
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
vi.mock('./components/ViewerControls', () => ({ default: () => null }));
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

describe('B1: a segmentation is opened from the server, never from the cached sidebar list', () => {
  it('rc070 release b1 opening takes the labels the server stored, not the list fetched before the classification', async () => {
    const row = await renderViewer();
    fireEvent.click(row);
    await waitFor(() => expect(useSegmentationStore.getState().currentSegmentation?.segmentation_id).toBe('seg-1'));
    expect(fx.getSegmentation.fn).toHaveBeenCalledWith('seg-1');
    expect(labelIds(useSegmentationStore.getState().currentSegmentation?.metadata?.labels)).toEqual([0, 1, 2, 3, 4]);
    await waitFor(() => expect(labelIds(useSegmentationStore.getState().activeSegmentation?.labels)).toEqual([0, 1, 2, 3, 4]));
  });

  it('rc070 release b1 closing and reopening reads the server again (the reopen path of the review)', async () => {
    const row = await renderViewer();
    fireEvent.click(row);
    await waitFor(() => expect(useSegmentationStore.getState().currentSegmentation?.segmentation_id).toBe('seg-1'));
    fireEvent.click(screen.getByText('Expert Rater'));                         // close
    await waitFor(() => expect(useSegmentationStore.getState().currentSegmentation).toBeNull());
    fireEvent.click(screen.getByText('Expert Rater'));                         // reopen
    await waitFor(() => expect(useSegmentationStore.getState().currentSegmentation?.segmentation_id).toBe('seg-1'));
    expect(fx.getSegmentation.fn).toHaveBeenCalledTimes(2);
    expect(labelIds(useSegmentationStore.getState().currentSegmentation?.metadata?.labels)).toEqual([0, 1, 2, 3, 4]);
  });

  it('rc070 release b1 a segmentation the server cannot return is not opened from the stale list', async () => {
    fx.getSegmentation.fn = vi.fn(async () => { throw new Error('network'); });
    const row = await renderViewer();
    fireEvent.click(row);
    await waitFor(() => expect(fx.getSegmentation.fn).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50));
    expect(useSegmentationStore.getState().currentSegmentation).toBeNull();
  });
});

describe('B1 (3): a mask value the label table does not name is drawn and announced', () => {
  it('rc070 release b1 the overlay controls warn about mask values without a label', () => {
    useSegmentationStore.setState({
      activeSegmentation: { id: 'seg-1', labels: fx.BINARY } as never,
      labelVisibility: { 0: false, 1: true },
      maskLabelValues: [1, 2, 3],
    } as never);
    render(<OverlayControls />);
    const warning = screen.getByTestId('unlabelled-mask-values');
    expect(warning).toHaveTextContent(/2, 3/);
    expect(warning).toHaveTextContent(/no label/i);
  });
});
