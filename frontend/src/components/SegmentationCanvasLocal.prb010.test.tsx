/**
 * PRB-010 — the MAGNIMS region colours drawn on the image are the legend's colours, and readable
 * for a colour-blind reader.
 *
 * The region legend of the lesion panel (LesionDashboard) uses the Okabe-Ito palette: periventricular
 * #E69F00 (orange), juxtacortical #56B4E9 (sky blue), infratentorial #009E73 (bluish green), deep white
 * matter #CC79A7 (reddish purple). The 2D overlay drew the same regions red / green / blue / gold — the
 * colours classify-regions stores with the labels and the zone-map layers hard-code — and the 3D zone map
 * and the zone-map panel's legend did the same. So the picture and the legend disagreed, and
 * periventricular red against juxtacortical green cannot be told apart with red-green colour blindness.
 *
 * What is checked is what reaches the canvas (the pixels the overlay writes, through a recording 2D
 * context — jsdom has none), the colormap handed to niivue for the 3D zone map, and the legend dots the
 * zone-map panel renders.
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import { render, waitFor, screen } from '@testing-library/react';
import { createRef } from 'react';

vi.mock('@niivue/niivue', async (orig) =>
  (await import('@/test/niivueHarness')).harnessModule(await orig()));

import { SegmentationCanvasLocal } from './SegmentationCanvasLocal';
import ImageViewer3D from './ImageViewer3D';
import { MAGNIMSZoneMapPanel } from './MAGNIMSZoneMapPanel';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { useViewerStore } from '@/store/useViewerStore';
import { harness, installBrowserNetwork } from '@/test/niivueHarness';
import { syntheticNifti, LAS_AFFINE } from '@/test/syntheticNifti';

// The legend's mapping (LesionDashboard REGION_COLORS on main @ 70cc5c7).
const LEGEND: Record<string, string> = {
  Periventricular: '#E69F00',
  Juxtacortical: '#56B4E9',
  Infratentorial: '#009E73',
  'Deep White Matter': '#CC79A7',
};
const REGION_BY_LABEL = ['Periventricular', 'Juxtacortical', 'Infratentorial', 'Deep White Matter'];
const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));

// What classify-regions stores with a classified segmentation on main (segmentation_regions.py).
const STORED_LABELS = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
  { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true },
  { id: 2, name: 'Juxtacortical', color: '#00CC00', opacity: 0.6, visible: true },
  { id: 3, name: 'Infratentorial', color: '#0066FF', opacity: 0.6, visible: true },
  { id: 4, name: 'Deep White Matter', color: '#FFD700', opacity: 0.6, visible: true },
];

// ── a recording 2D context: every putImageData is kept ──
let written: Uint8ClampedArray[] = [];
const savedGetContext = HTMLCanvasElement.prototype.getContext;
beforeAll(() => {
  const ctx = new Proxy({} as Record<string, unknown>, {
    get(target, prop) {
      if (prop === 'createImageData') return (w: number, h: number) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) });
      if (prop === 'putImageData') return (img: { data: Uint8ClampedArray }) => { written.push(img.data.slice()); };
      if (prop === 'measureText') return () => ({ width: 0 });
      if (prop === 'getImageData') return (_x: number, _y: number, w: number, h: number) => ({ data: new Uint8ClampedArray(w * h * 4) });
      if (prop in target) return target[prop as string];
      return () => undefined;
    },
    set(target, prop, value) { target[prop as string] = value; return true; },
  });
  HTMLCanvasElement.prototype.getContext = (() => ctx) as unknown as typeof HTMLCanvasElement.prototype.getContext;
});
afterAll(() => { HTMLCanvasElement.prototype.getContext = savedGetContext; });
beforeEach(() => { written = []; harness.reset(); });
afterEach(() => vi.unstubAllGlobals());

// A 2 x 2 slice whose four voxels hold labels / zones 1, 2, 3, 4.
const SLICE = Uint8Array.from([1, 2, 3, 4]);
const fakeMask = (showLabels: boolean) => ({
  isLoaded: true,
  getSliceMask: () => (showLabels ? SLICE : new Uint8Array(4)),
  state: { dimensions: { depth: 1, height: 2, width: 2 }, isDirty: false, isLoading: false, conflict: null },
  paintStroke: () => {}, beginStroke: () => {}, endStroke: () => {},
});

function drawOverlay(showLabels: boolean) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const containerRef = { current: container };
  render(
    <SegmentationCanvasLocal
      ref={createRef()}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      segmentationMask={fakeMask(showLabels) as any}
      sliceIndex={0}
      imageWidth={2}
      imageHeight={2}
      containerRef={containerRef}
      onPaintStroke={() => {}}
      selectedLabelId={1}
      brushSize={1}
      eraseMode={false}
      showOverlay={showLabels}
      enabled={false}
      baseImageData=""
      zoomLevel={1}
      panOffset={{ x: 0, y: 0 }}
      showBaseImage={false}
      renderedImageSize={{ width: 200, height: 200 }}
    />,
  );
}

/** The colour the overlay wrote for each of the four voxels (label / zone 1..4). */
async function drawnColours(): Promise<string[]> {
  await waitFor(() => expect(written.some((d) => d[3] > 0)).toBe(true));
  const drawnLayers = written.filter((x) => x[3] > 0);
  const d = drawnLayers[drawnLayers.length - 1];
  return [0, 1, 2, 3].map((v) => `#${[d[v * 4], d[v * 4 + 1], d[v * 4 + 2]].map((c) => c.toString(16).padStart(2, '0')).join('').toUpperCase()}`);
}

function setClassifiedSegmentation() {
  const s = useSegmentationStore.getState();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  s.setActiveSegmentation({ id: 'seg-1', labels: STORED_LABELS } as any);
  useSegmentationStore.setState({
    lesionOpacity: 1, zoneColorizeEnabled: false, zoneMapVisible: false, zoneMapMask: null, zoneMapDims: null,
    longitudinalVisible: false, conformalVisible: false, selectedLesion: null,
  });
}

// ── colour-blind readability ──
function lin(c: number) { const x = c / 255; return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }
function lab(rgbLin: number[]) {
  const [r, g, b] = rgbLin.map((v) => Math.min(1, Math.max(0, v)));
  const X = 0.4124 * r + 0.3576 * g + 0.1805 * b, Y = 0.2126 * r + 0.7152 * g + 0.0722 * b, Z = 0.0193 * r + 0.1192 * g + 0.9505 * b;
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  const fx = f(X / 0.95047), fy = f(Y), fz = f(Z / 1.08883);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}
// Machado, Oliveira & Fernandes 2009, severity 1.0 (on linear RGB)
const DEUTAN = [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]];
const PROTAN = [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]];
function seenAs(hex: string, m: number[][]) { const l = rgb(hex).map(lin); return lab(m.map((row) => row[0] * l[0] + row[1] * l[1] + row[2] * l[2])); }
const dE = (a: number[], b: number[]) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
function hue(hex: string) {
  const [r, g, b] = rgb(hex).map((v) => v / 255); const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  if (d === 0) return NaN;
  const h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return (h * 60 + 360) % 360;
}
const isRed = (hex: string) => { const h = hue(hex); return h >= 345 || h <= 15; };
const isGreen = (hex: string) => { const h = hue(hex); return h >= 90 && h <= 150; };

describe('PRB-010 — region colours on the image are the legend colours', () => {
  it('rc076 2D overlay of a classified segmentation: each region drawn in its legend colour (stored labels say red/green/blue/gold)', async () => {
    setClassifiedSegmentation();
    drawOverlay(true);
    expect(await drawnColours()).toEqual(REGION_BY_LABEL.map((r) => LEGEND[r]));
  });

  it('rc076 2D zone-coloured lesions (MAGNIMS zone colouring on) use the legend colours', async () => {
    setClassifiedSegmentation();
    useSegmentationStore.setState({ zoneColorizeEnabled: true, zoneMapMask: SLICE.slice(), zoneMapDims: { depth: 1, height: 2, width: 2 } });
    drawOverlay(true);
    expect(await drawnColours()).toEqual(REGION_BY_LABEL.map((r) => LEGEND[r]));
  });

  it('rc076 2D zone-map background layer uses the legend colours', async () => {
    setClassifiedSegmentation();
    useSegmentationStore.setState({ zoneMapVisible: true, zoneMapOpacity: 0.5, zoneMapMask: SLICE.slice(), zoneMapDims: { depth: 1, height: 2, width: 2 } });
    drawOverlay(false);
    expect(await drawnColours()).toEqual(REGION_BY_LABEL.map((r) => LEGEND[r]));
  });

  it('rc076 no two regions drawn on the image are red against green, and every pair stays apart for deutan and protan readers', async () => {
    setClassifiedSegmentation();
    drawOverlay(true);
    const drawn = await drawnColours();
    for (let a = 0; a < 4; a++) {
      for (let b = a + 1; b < 4; b++) {
        expect(isRed(drawn[a]) && isGreen(drawn[b]) || isGreen(drawn[a]) && isRed(drawn[b])).toBe(false);
        for (const m of [DEUTAN, PROTAN]) expect(dE(seenAs(drawn[a], m), seenAs(drawn[b], m))).toBeGreaterThan(15);
      }
    }
  });

  it('rc076 3D zone map: niivue receives the legend colours for zones 1-4', async () => {
    const DIMS: [number, number, number] = [6, 8, 5];
    const zones = new Uint8Array(DIMS[0] * DIMS[1] * DIMS[2]).map((_, n) => 1 + (n % 4));
    installBrowserNetwork('http://127.0.0.1:4173', {
      '/api/v1/imaging/nifti/f.nii.gz': syntheticNifti({ dims: DIMS, affine: LAS_AFFINE, gzip: true }),
      '/api/v1/segmentation/zm-1/nifti': syntheticNifti({ dims: DIMS, affine: LAS_AFFINE, data: zones, gzip: true }),
    });
    for (const k of ['clientWidth', 'clientHeight'] as const) {
      Object.defineProperty(HTMLElement.prototype, k, { configurable: true, get: () => 600 });
    }
    useViewerStore.setState({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      currentSeries: { id: 's', name: 'f', format: 'nifti', total_slices: 5, file_id: 'f.nii.gz', metadata: { rows: 6, columns: 8, slices: 5 } } as any,
      render3DMode: 'volume',
    });
    useSegmentationStore.setState({ currentSegmentation: null, zoneMapSegId: 'zm-1', zoneMapVisible: true, longitudinalVisible: false });
    render(<ImageViewer3D patientName="Ana Torres" />);
    await waitFor(() => expect(harness.colormaps.magnims_zones).toBeDefined(), { timeout: 8000 });
    const cm = harness.colormaps.magnims_zones as { R: number[]; G: number[]; B: number[] };
    // niivue maps value v (cal 0..4) to index round(v / 4 * 255): 64, 128, 191, 255
    const at = (i: number) => `#${[cm.R[i], cm.G[i], cm.B[i]].map((c) => c.toString(16).padStart(2, '0')).join('').toUpperCase()}`;
    expect([64, 128, 191, 255].map(at)).toEqual(REGION_BY_LABEL.map((r) => LEGEND[r]));
  });

  it('rc076 the zone-colouring legend (PV / JC / IT / DWM) shows the same colours as the lesion legend', async () => {
    useSegmentationStore.setState({ zoneMapMask: Uint8Array.from([1, 2, 3, 4]), zoneMapSegId: 'zm-1', zoneMapVisible: true });
    render(<MAGNIMSZoneMapPanel fileId="f.nii.gz" />);
    const abbrev: Record<string, string> = { PV: 'Periventricular', JC: 'Juxtacortical', IT: 'Infratentorial', DWM: 'Deep White Matter' };
    for (const [short, region] of Object.entries(abbrev)) {
      const item = (await screen.findAllByText(short)).find((el) => el.querySelector('span.rounded-full'));
      expect(item).toBeDefined();
      const dot = item!.querySelector('span.rounded-full') as HTMLElement;
      const colour = (dot.getAttribute('class') ?? '') + ' ' + (dot.getAttribute('style') ?? '');
      expect(colour.toUpperCase()).toContain(LEGEND[region]);
    }
  });

  it('rc076 the zone-map panel legend shows the same colours as the lesion legend', async () => {
    const zones = Uint8Array.from([1, 2, 3, 4, 1, 2, 3, 4]);
    useSegmentationStore.setState({ zoneMapMask: zones, zoneMapSegId: 'zm-1', zoneMapVisible: true });
    render(<MAGNIMSZoneMapPanel fileId="f.nii.gz" />);
    for (const region of REGION_BY_LABEL) {
      const text = await screen.findByText(new RegExp(`^${region}: `));
      const dot = text.previousElementSibling as HTMLElement;
      const colour = (dot.getAttribute('class') ?? '') + ' ' + (dot.getAttribute('style') ?? '');
      expect(colour.toUpperCase()).toContain(LEGEND[region]);
    }
  });
});
