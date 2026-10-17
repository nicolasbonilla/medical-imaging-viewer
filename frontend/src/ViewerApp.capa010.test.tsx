/**
 * CAPA-010 — the REAL viewer page (ViewerApp) wires the safety annotation into every view,
 * and the annotation is laid out inside the visible part of the page.
 *
 *   RC-016 (HAZ-009): the patient identity the page loaded reaches the viewport in single
 *          2D, multi-panel 2D and 3D — rendered by the real viewers, not stubs.
 *   RC-023 (HAZ-006): the standing "Laterality not labelled" caveat of every view is fully
 *          visible. jsdom has no layout engine, so the rendered page (with the app's real
 *          Tailwind CSS) is measured in a real headless browser at common window sizes.
 *          Before CAPA-010 the 2D column stacked a toolbar on top of an `h-full` viewport,
 *          pushing the bottom of the viewport — caveat included — under the
 *          `overflow-hidden` frame.
 *
 * Only the backend, the WebGL renderer, animations and the side panels are replaced.
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach } from 'vitest';
import { render, screen, waitFor, within, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import './index.css';
import { findChromium, measureInRealBrowser, type LayoutCase } from '@/test/realBrowserLayout';

const fx = vi.hoisted(() => {
  const P = '11111111-1111-4111-8111-111111111111';
  const S = '22222222-2222-4222-8222-222222222222';
  const SE = '33333333-3333-4333-8333-333333333333';
  const file = (name: string) => `patients/${P}/studies/${S}/series/${SE}/${name}`;
  // An API object whose unknown members resolve to an empty object.
  const anyApi = (known: Record<string, unknown>) => new Proxy(known, {
    get: (target, key: string) => (key in target ? target[key] : async () => ({})),
  });
  return {
    anyApi,
    P, S, SE,
    USER: { id: 'u1', username: 'dr', email: 'dr@example.org', full_name: 'Dr Test', role: 'RADIOLOGIST' },
    PATIENT: { id: P, full_name: 'Ana Torres', mrn: 'MRN-99120', age: 40, gender: 'female' },
    INSTANCES: [
      { id: 'i-flair', series_id: SE, gcs_object_name: file('flair.nii.gz'), original_filename: 'sub-01_FLAIR.nii.gz' },
      { id: 'i-t1', series_id: SE, gcs_object_name: file('t1.nii.gz'), original_filename: 'sub-01_T1w.nii.gz' },
    ],
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
  segmentationAPI: fx.anyApi({ listSegmentationsByFileIds: vi.fn(async () => []), listSegmentations: vi.fn(async () => []) }),
}));

// Side panels are irrelevant to the viewport and need their own backends.
vi.mock('./components/ControlPanel', () => ({ default: () => null }));
vi.mock('./components/ViewerControls', () => ({ default: () => null }));
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
  URL.createObjectURL = vi.fn(() => 'blob:capa010');
  URL.revokeObjectURL = vi.fn();
});
afterAll(() => {
  for (const key of ['clientWidth', 'clientHeight']) {
    if (saved[key]) Object.defineProperty(HTMLElement.prototype, key, saved[key]!);
  }
  vi.unstubAllGlobals();
});

beforeEach(() => {
  fakeNiivue.instances.length = 0;
  useViewerStore.setState({ viewMode: '2d', currentSeries: null, render3DMode: 'volume' });
  useMultiViewerStore.getState().reset();
  useSegmentationStore.setState({ selectedLesion: null, currentSegmentation: null });
});

type Mode = '2d' | 'multi' | '3d-volume' | '3d-mpr';

async function renderViewer(mode: Mode) {
  if (mode.startsWith('3d')) {
    useViewerStore.setState({ viewMode: '3d', render3DMode: mode === '3d-mpr' ? 'multiplanar' : 'volume' });
  }
  // Mount into #root like main.tsx does: index.css sizes #root (body is a flex box).
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
  // The page loads the study, auto-selects the first image and loads it.
  await waitFor(() => expect(useViewerStore.getState().currentSeries).not.toBeNull(), { timeout: 5000 });
  if (mode === 'multi') {
    // What the "1x2" layout button does.
    useMultiViewerStore.getState().setLayout('1x2');
    useMultiViewerStore.getState().autoAssign([
      { instanceId: 'i-flair', sequence: 'FLAIR' },
      { instanceId: 'i-t1', sequence: 'T1w' },
    ]);
  }
  // Wait until the view itself is up (independent of the annotation under test).
  await waitFor(() => {
    if (mode === 'multi') {
      expect(useMultiViewerStore.getState().panels.slice(0, 2).every((p) => p.imageData)).toBe(true);
    } else if (mode.startsWith('3d')) {
      const want = mode === '3d-mpr' ? 4 : 1;
      expect(fakeNiivue.instances.filter((n) => n.volumes.length > 0).length).toBeGreaterThanOrEqual(want);
    } else {
      expect(document.querySelector('#main-content canvas')).not.toBeNull();
    }
  }, { timeout: 5000 });
  return document.getElementById('main-content')!;
}

async function expectIdentityOnEveryView(mode: Mode) {
  const viewport = await renderViewer(mode);
  const views = mode === 'multi' ? 2 : 1;

  await waitFor(() => expect(within(viewport).getAllByTestId('viewport-safety-overlay')).toHaveLength(views));
  const identities = within(viewport).getAllByTestId('viewport-patient-identity');
  expect(identities).toHaveLength(views);
  for (const identity of identities) {
    expect(identity).toHaveTextContent('Ana Torres');
    expect(identity).toHaveTextContent('MRN-99120');
  }
  expect(screen.queryByTestId('viewport-identity-missing')).not.toBeInTheDocument();
}

describe('RC-016 — the viewer page puts the patient identity on every view', () => {
  it('rc016 ViewerApp 2d: the loaded patient name and MRN are on the viewport', async () => {
    await expectIdentityOnEveryView('2d');
  });

  it('rc016 ViewerApp multi-panel: the loaded patient name and MRN are on every panel', async () => {
    await expectIdentityOnEveryView('multi');
  });

  it('rc016 ViewerApp 3D volume: the loaded patient name and MRN are on the viewport', async () => {
    await expectIdentityOnEveryView('3d-volume');
  });

  it('rc016 ViewerApp 3D multiplanar: the loaded patient name and MRN are on the viewport', async () => {
    await expectIdentityOnEveryView('3d-mpr');
  });
});

describe('RC-023 — the standing laterality caveat is inside the visible page (real browser layout)', () => {
  const browser = findChromium();

  it('rc023 ViewerApp: every view shows its laterality caveat in full at 1366x768, 1600x900 and 1920x1080', async (ctx) => {
    // A layout check that silently skips in CI would be documentation, not verification
    // (CAPA-004 §9.3): in CI a missing browser FAILS. Locally it is reported as skipped.
    if (!browser && !process.env.CI) ctx.skip('no Chromium-family browser found (set CAPA010_BROWSER or CHROME_BIN)');
    expect(browser, 'a Chromium-family browser is required in CI (set CAPA010_BROWSER or CHROME_BIN)').toBeTruthy();
    const cases: LayoutCase[] = [];
    for (const mode of ['2d', 'multi', '3d-volume', '3d-mpr'] as const) {
      fakeNiivue.instances.length = 0;
      await renderViewer(mode);
      await new Promise((r) => setTimeout(r, 300));
      const html = `<!doctype html>${document.documentElement.outerHTML}`;
      for (const [width, height] of [[1366, 768], [1600, 900], [1920, 1080]]) {
        cases.push({ name: `${mode} ${width}x${height}`, html, width, height,
          selector: '[data-testid="viewport-safety-overlay"] div', text: 'Laterality not labelled' });
      }
      cleanup();
      useViewerStore.setState({ viewMode: '2d', currentSeries: null, render3DMode: 'volume' });
      useMultiViewerStore.getState().reset();
    }

    const results = measureInRealBrowser(browser!, cases);
    const summary = results.map((r) => `${r.name}: ${r.matches.map((m) => m.visibleFraction.toFixed(2)).join(',') || 'none'}`);
    for (const r of results) {
      const expected = r.name.startsWith('multi') ? 2 : 1;
      expect(r.matches.length, summary.join(' | ')).toBe(expected);
      for (const m of r.matches) expect(m.visibleFraction, summary.join(' | ')).toBeGreaterThan(0.999);
    }
  }, 120000);
});
