/**
 * The REAL viewer page (ViewerApp) opening a study that holds only preprocessed images —
 * the case of the public demo study and of any study uploaded already preprocessed.
 *
 *   PRB-007: the 2x2 (and 1x2) grid showed "No image assigned" in every panel and a "1/0" slider:
 *          the grid took its images from the "originals" group only, which is empty here. With
 *          four images of which two are T1-weighted (T1w and T1w after contrast) the fourth panel
 *          stayed empty. Required: the grid is filled from the images the study has.
 *   PRB-008: the viewer opened on slice 1 of 182 — outside the head, a blank image. Required: an
 *          image opens on its middle slice; switching to another image of the same size keeps
 *          the slice; switching to an image of another size opens it on its middle slice; grid
 *          panels open on the middle slice of their image.
 *   PRB-009: every opening of the viewer requested /models/brain_screening.onnx (a model that is
 *          not shipped), which failed in the console, and the "Quick Screen" button appeared.
 *          Required: the screening is behind a build flag that is off; with it off the viewer
 *          requests nothing and shows nothing of it.
 *
 * Only the backend, the WebGL renderer, animations and the side panels are replaced.
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
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
  const inst = (id: string, name: string) =>
    ({ id, series_id: SE, gcs_object_name: file(`${id}.nii.gz`), original_filename: name, file_size_bytes: 4_400_000 });
  // As the public demo study: four preprocessed images, two of them T1-weighted.
  const INSTANCES = [
    inst('i-flair', 'sub-13_space-MNI_desc-preproc_FLAIR.nii.gz'),
    inst('i-t1', 'sub-13_space-MNI_desc-preproc_T1w.nii.gz'),
    inst('i-t2', 'sub-13_space-MNI_desc-preproc_T2w.nii.gz'),
    inst('i-t1ce', 'sub-13_space-MNI_ce-gad_desc-preproc_T1w.nii.gz'),
  ];
  const SLICES: Record<string, number> = { 'i-flair': 7, 'i-t1': 7, 'i-t2': 9, 'i-t1ce': 7 };
  const requests: string[] = [];
  return { anyApi, P, S, SE, INSTANCES, SLICES, requests,
    USER: { id: 'u1', username: 'dr', email: 'dr@example.org', full_name: 'Dr Test', role: 'RADIOLOGIST' },
    PATIENT: { id: P, full_name: 'Ana Torres', mrn: 'MRN-99120', age: 40, gender: 'female' } };
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
    processImage: vi.fn(async (fileId: string) => {
      const id = fx.INSTANCES.find((i) => i.gcs_object_name === fileId)!.id;
      const n = fx.SLICES[id];
      return {
        id: fileId, name: fileId, format: 'nifti', total_slices: n,
        metadata: { rows: 218, columns: 182, slices: n, pixel_spacing: [1, 1], anatomical_orientation: 'LAS' },
        slices: Array.from({ length: n }, (_, i) => ({ slice_index: i, image_data: `AA${i}`, format: 'nifti', width: 182, height: 218 })),
      };
    }),
  }),
}));
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: fx.anyApi({ listSegmentationsByFileIds: vi.fn(async () => []), listSegmentations: vi.fn(async () => []) }),
}));
// Side panels are irrelevant here and need their own backends. QuickScreenBadge is NOT replaced.
vi.mock('./components/ControlPanel', () => ({ default: () => null }));
vi.mock('./components/ViewerControls', () => ({ default: () => null }));
vi.mock('./components/AIReportPanel', () => ({ AIReportPanel: () => null, default: () => null }));
vi.mock('./components/LesionDashboard', () => ({ LesionDashboard: () => null }));
vi.mock('./components/MAGNIMSZoneMapPanel', () => ({ MAGNIMSZoneMapPanel: () => null }));
vi.mock('./components/ReportViewerModal', () => ({ ReportViewerModal: () => null }));

import ViewerApp from './ViewerApp';
import { useViewerStore } from '@/store/useViewerStore';
import { useMultiViewerStore } from '@/store/useMultiViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';

const saved: Record<string, PropertyDescriptor | undefined> = {};
beforeAll(() => {
  for (const [key, value] of [['clientWidth', 800], ['clientHeight', 600]] as const) {
    saved[key] = Object.getOwnPropertyDescriptor(HTMLElement.prototype, key);
    Object.defineProperty(HTMLElement.prototype, key, { configurable: true, get: () => value });
  }
  // A static file server (vite preview, nginx without SPA fallback for /models): the model is absent.
  const reply = (ok: boolean, contentType: string | null) => ({
    ok, status: ok ? 200 : 404,
    headers: { get: (): string | null => contentType },
    arrayBuffer: async (): Promise<ArrayBuffer> => new ArrayBuffer(16),
    text: async (): Promise<string> => (ok ? '' : 'Not Found'),
    json: async (): Promise<unknown> => ({}),
  });
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    fx.requests.push(url);
    return url.includes('/models/') ? reply(false, 'text/plain') : reply(true, null);
  }));
  URL.createObjectURL = vi.fn(() => 'blob:prb007');
  URL.revokeObjectURL = vi.fn();
});
afterAll(() => {
  for (const key of ['clientWidth', 'clientHeight']) {
    if (saved[key]) Object.defineProperty(HTMLElement.prototype, key, saved[key]!);
  }
  vi.unstubAllGlobals();
});
beforeEach(() => {
  fx.requests.length = 0;
  useViewerStore.getState().reset();
  useMultiViewerStore.getState().reset();
  useSegmentationStore.setState({ selectedLesion: null, currentSegmentation: null });
});

async function openViewer() {
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
  await waitFor(() => expect(document.querySelector('#main-content canvas')).not.toBeNull(), { timeout: 5000 });
}

const fileOf = (id: string) => fx.INSTANCES.find((i) => i.id === id)!;
/** The toolbar's slice counter (the label next to the toolbar's slice slider). */
const sliceLabel = () => document.querySelector('#main-content input[type="range"]')!.previousElementSibling as HTMLElement;

describe('PRB-007 — the grid uses the images the study has', () => {
  it('prb007 a study of preprocessed images only: the 2x2 grid shows all four images, none empty', async () => {
    await openViewer();
    fireEvent.click(screen.getByRole('button', { name: /2x2/ }));

    await waitFor(() => {
      const panels = useMultiViewerStore.getState().panels;
      expect(panels.map((p) => p.instanceId)).toEqual(['i-flair', 'i-t1', 'i-t2', 'i-t1ce']);
      expect(panels.every((p) => p.imageData)).toBe(true);
    }, { timeout: 5000 });
    const viewport = document.getElementById('main-content')!;
    expect(within(viewport).queryByText('No image assigned')).not.toBeInTheDocument();
    expect(sliceLabel().textContent).not.toMatch(/\/0$/);
  });

  it('prb007 a study of preprocessed images only: the 1x2 grid shows two images', async () => {
    await openViewer();
    fireEvent.click(screen.getByRole('button', { name: /1x2/ }));
    await waitFor(() => {
      const panels = useMultiViewerStore.getState().panels.slice(0, 2);
      expect(panels.map((p) => p.instanceId)).toEqual(['i-flair', 'i-t1']);
      expect(panels.every((p) => p.imageData)).toBe(true);
    }, { timeout: 5000 });
  });

  it('prb007 the image-source switch names the source actually shown (Preproc, not Original)', async () => {
    await openViewer();
    fireEvent.click(screen.getByRole('button', { name: /2x2/ }));
    await waitFor(() => expect(useMultiViewerStore.getState().panels[0].imageData).toBeTruthy(), { timeout: 5000 });
    expect(screen.queryByRole('button', { name: /^Original$/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Preproc$/ })).toBeInTheDocument();
  });
});

describe('PRB-008 — the viewer opens on a slice inside the head', () => {
  it('prb008 the first image opens on its middle slice (7 slices: slice 4 of 7)', async () => {
    await openViewer();
    await waitFor(() => expect(useViewerStore.getState().currentSliceIndex).toBe(3));
    expect(sliceLabel()).toHaveTextContent('4/7');
  });

  it('prb008 another image of the same size keeps the slice; an image of another size opens on its middle slice', async () => {
    await openViewer();
    useViewerStore.getState().setCurrentSliceIndex(5);
    fireEvent.click(screen.getByText(fileOf('i-t1').original_filename));
    await waitFor(() => expect(useViewerStore.getState().currentSeries?.file_id).toBe(fileOf('i-t1').gcs_object_name));
    expect(useViewerStore.getState().currentSliceIndex).toBe(5);

    fireEvent.click(screen.getByText(fileOf('i-t2').original_filename));
    await waitFor(() => expect(useViewerStore.getState().currentSeries?.file_id).toBe(fileOf('i-t2').gcs_object_name));
    expect(useViewerStore.getState().currentSliceIndex).toBe(4); // 9 slices → slice 5 of 9
  });

  it('prb008 grid panels open on the middle slice of their image, not slice 1', async () => {
    await openViewer();
    fireEvent.click(screen.getByRole('button', { name: /1x2/ }));
    await waitFor(() => {
      const panels = useMultiViewerStore.getState().panels.slice(0, 2);
      expect(panels.every((p) => p.imageData)).toBe(true);
      expect(panels.map((p) => p.sliceIndex)).toEqual([3, 3]);
      expect(panels.map((p) => p.imageData)).toEqual(['data:image/png;base64,AA3', 'data:image/png;base64,AA3']);
    }, { timeout: 5000 });
    expect(sliceLabel()).toHaveTextContent('4/7');
  });
});

describe('PRB-009 — the unshipped screening model is a switched-off feature, not an error', () => {
  it('rc075 opening the viewer requests no screening model and shows no Quick Screen button', async () => {
    await openViewer();
    await new Promise((r) => setTimeout(r, 50));
    expect(fx.requests.filter((u) => u.includes('brain_screening.onnx'))).toEqual([]);
    expect(screen.queryByRole('button', { name: /Quick Screen/i })).not.toBeInTheDocument();
  });
});
