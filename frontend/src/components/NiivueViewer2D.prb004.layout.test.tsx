/**
 * PRB-004 — independent review of PR #71 (m5), measured in a real browser: the W/L GPU view's "segmentation not
 * drawn" notice is fully visible and overlaps none of the viewport's safety annotations (patient identity block,
 * orientation banner, standing laterality caveat).
 *
 * jsdom has no layout engine. The GPU view and the safety overlay are rendered as ImageViewer2D composes them (the
 * overlay first, the GPU view in an `absolute inset-0 z-10` layer), with the app's real Tailwind CSS, and the
 * snapshot is measured in a headless Chromium-family browser (src/test/realBrowserLayout.ts) at a usual and at a
 * narrow 2D viewport (where the identity block and the laterality caveat wrap to more lines). At 39f9d44 the notice
 * sat at the top (`top-12`), across the identity block in a narrow viewport; the first review fix (`bottom-10`)
 * touched the two-line caveat — this test found it.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import '../index.css';

vi.mock('@niivue/niivue', async (orig) =>
  (await import('@/test/niivueHarness')).harnessModule(await orig()));

import { NiivueViewer2D } from './NiivueViewer2D';
import ImageViewer3D from './ImageViewer3D';
import { ViewportSafetyOverlay } from './ViewportSafetyOverlay';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { harness, installBrowserNetwork } from '@/test/niivueHarness';
import { syntheticNifti, LAS_AFFINE } from '@/test/syntheticNifti';
import { findChromium, measureInRealBrowser, type LayoutCase, type Measured } from '@/test/realBrowserLayout';

const FILE = 'patients/p/studies/s/series/se/flair.nii.gz';
const SEG = 'seg-0001';
const DIMS: [number, number, number] = [6, 8, 5];

afterEach(() => { cleanup(); vi.unstubAllGlobals(); harness.reset(); });

const SELECTORS = {
  notice: '[data-testid="niivue-mask-not-shown"]',
  identity: '[data-testid="viewport-patient-identity"]',
  orientation: '[data-testid="viewport-orientation"]',
  caveat: '[data-testid="viewport-safety-overlay"] div',
} as const;

function overlapArea(a: Measured, b: Measured): number {
  const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  return w > 0 && h > 0 ? w * h : 0;
}

describe('PRB-004 review — the GPU notice in a real browser layout', () => {
  const browser = findChromium();

  it('rc073 m5: the notice is fully visible and covers no safety annotation, in a usual and a narrow viewport', async (ctx) => {
    if (!browser && !process.env.CI) ctx.skip('no Chromium-family browser found (set CAPA010_BROWSER or CHROME_BIN)');
    expect(browser, 'a Chromium-family browser is required in CI (set CAPA010_BROWSER or CHROME_BIN)').toBeTruthy();

    // A mask on another voxel grid: the notice exists both before and after the review fix (only its place differs).
    useViewerStore.setState({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      currentSeries: { id: FILE, name: 'flair', format: 'nifti', file_id: FILE, total_slices: DIMS[2],
        metadata: { rows: DIMS[0], columns: DIMS[1], slices: DIMS[2] }, slices: [] } as any,
      currentSliceIndex: 2, windowCenter: 0, windowWidth: 0,
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    useSegmentationStore.setState({ currentSegmentation: { segmentation_id: SEG } as any, isOverlayVisible: true, lesionOpacity: 0.6 });
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: syntheticNifti({ dims: DIMS, affine: LAS_AFFINE, gzip: true }),
      [`/api/v1/segmentation/${SEG}/nifti`]: syntheticNifti({ dims: [6, 8, 4], affine: LAS_AFFINE, gzip: true,
        data: new Uint8Array(6 * 8 * 4), descrip: 'RC031-ORIENT-V2' }),
    });

    // As ImageViewer2D composes them, filling the window.
    render(
      <div style={{ position: 'fixed', inset: 0 }}>
        <div className="relative h-full bg-black">
          <ViewportSafetyOverlay
            patientName="Ana María Torres-Villanueva de la Fuente"
            patientMRN="MRN-99120"
            studyDescription="Brain MRI with and without contrast, follow-up"
            anatomicalOrientation="LAS"
          />
          <div className="absolute inset-0 z-10"><NiivueViewer2D /></div>
        </div>
      </div>,
    );
    await screen.findByTestId('niivue-mask-not-shown', undefined, { timeout: 5000 });
    const html = `<!doctype html>${document.documentElement.outerHTML}`;

    const sizes: Array<[number, number]> = [[1100, 700], [600, 420], [480, 330]];   // usual to narrow 2D viewports
    const cases: LayoutCase[] = [];
    for (const [width, height] of sizes) {
      for (const [what, selector] of Object.entries(SELECTORS)) {
        cases.push({ name: `${what} ${width}x${height}`, html, width, height, selector,
          text: what === 'caveat' ? 'Laterality not labelled' : undefined });
      }
    }
    const results = measureInRealBrowser(browser!, cases);
    assertClear(results, sizes);
  }, 120000);

  it('rc073 R1: the 3D notice is fully visible and covers no safety annotation, in a usual and a narrow viewport', async (ctx) => {
    if (!browser && !process.env.CI) ctx.skip('no Chromium-family browser found (set CAPA010_BROWSER or CHROME_BIN)');
    expect(browser, 'a Chromium-family browser is required in CI (set CAPA010_BROWSER or CHROME_BIN)').toBeTruthy();
    for (const [key, value] of [['clientWidth', 800], ['clientHeight', 600]] as const) {
      Object.defineProperty(HTMLElement.prototype, key, { configurable: true, get: () => value });
    }
    useViewerStore.setState({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      currentSeries: { id: 's', name: 'f', format: 'nifti', total_slices: DIMS[2], file_id: FILE,
        metadata: { rows: DIMS[0], columns: DIMS[1], slices: DIMS[2], anatomical_orientation: 'LAS' } } as any,
      render3DMode: 'volume', currentSliceIndex: 0,
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    useSegmentationStore.setState({ currentSegmentation: { segmentation_id: SEG } as any, longitudinalVisible: false,
      zoneMapSegId: null, selectedLesion: null });
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: syntheticNifti({ dims: DIMS, affine: LAS_AFFINE, gzip: true }),
      [`/api/v1/segmentation/${SEG}/nifti`]: syntheticNifti({ dims: DIMS, affine: LAS_AFFINE, gzip: true,
        data: new Uint8Array(DIMS[0] * DIMS[1] * DIMS[2]), descrip: '' }),   // older voxel order: refused, named
    });
    render(
      <div style={{ position: 'fixed', inset: 0 }}>
        <ImageViewer3D patientName="Ana María Torres-Villanueva de la Fuente" patientMRN="MRN-99120"
          studyDescription="Brain MRI with and without contrast, follow-up" />
      </div>,
    );
    await screen.findByTestId('niivue-3d-mask-not-shown', undefined, { timeout: 8000 });
    const html = `<!doctype html>${document.documentElement.outerHTML}`;
    const sizes: Array<[number, number]> = [[1100, 700], [600, 420], [480, 330]];
    const cases: LayoutCase[] = [];
    for (const [width, height] of sizes) {
      for (const [what, selector] of Object.entries({ ...SELECTORS, notice: '[data-testid="niivue-3d-mask-not-shown"]' })) {
        cases.push({ name: `${what} ${width}x${height}`, html, width, height, selector,
          text: what === 'caveat' ? 'Laterality not labelled' : undefined });
      }
    }
    assertClear(measureInRealBrowser(browser!, cases), sizes);
  }, 120000);
});

function assertClear(results: ReturnType<typeof measureInRealBrowser>, sizes: Array<[number, number]>) {
  {
    const at = (what: string, w: number, h: number) => results.find((r) => r.name === `${what} ${w}x${h}`)!.matches;
    for (const [w, h] of sizes) {
      const [notice] = at('notice', w, h);
      expect(notice, `notice at ${w}x${h}`).toBeDefined();
      expect(notice.visibleFraction, `notice at ${w}x${h}`).toBeGreaterThan(0.999);
      for (const other of ['identity', 'orientation', 'caveat']) {
        const boxes = at(other, w, h);
        expect(boxes.length, `${other} at ${w}x${h}`).toBeGreaterThan(0);
        for (const b of boxes) {
          expect(overlapArea(notice, b), `notice over the ${other} at ${w}x${h}: ${JSON.stringify({ notice, b })}`).toBe(0);
        }
      }
    }
  }
}
