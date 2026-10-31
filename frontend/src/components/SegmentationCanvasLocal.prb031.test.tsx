/**
 * PRB-031 — the longitudinal overlay of the 2D view drew "persistent" green against "new" red (and "resolved" blue):
 * persistent and new lesions cannot be told apart with red-green colour blindness (about 8 % of men), the same defect
 * PRB-010 removed from the region colours. It now uses colours of the shared colour-blind-safe (Okabe-Ito) palette of
 * `utils/regionColors.ts`. Checked on what reaches the canvas (a recording 2D context; jsdom has none), with the same
 * thresholds as PRB-010: no red against green, every pair apart for deutan, protan and tritan readers opaque, and as
 * drawn (its fixed 55 %) over mid and bright grey. The drawn opacity is the one the Confirm check of PRB-031 uses.
 *
 * Written before the correction (fails on ca600c2).
 */
import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { createRef } from 'react';

import { SegmentationCanvasLocal } from './SegmentationCanvasLocal';
import { useSegmentationStore } from '@/store/useSegmentationStore';

const OKABE_ITO = ['#E69F00', '#56B4E9', '#009E73', '#F0E442', '#0072B2', '#D55E00', '#CC79A7'];

let written: Uint8ClampedArray[] = [];
const savedGetContext = HTMLCanvasElement.prototype.getContext;
beforeAll(() => {
  const ctx = new Proxy({} as Record<string, unknown>, {
    get(target, prop) {
      if (prop === 'createImageData') return (w: number, h: number) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) });
      if (prop === 'putImageData') return (img: { data: Uint8ClampedArray }) => { written.push(img.data.slice()); };
      if (prop === 'measureText') return () => ({ width: 0 });
      if (prop in target) return target[prop as string];
      return () => undefined;
    },
    set(target, prop, value) { target[prop as string] = value; return true; },
  });
  HTMLCanvasElement.prototype.getContext = (() => ctx) as unknown as typeof HTMLCanvasElement.prototype.getContext;
});
afterAll(() => { HTMLCanvasElement.prototype.getContext = savedGetContext; });
beforeEach(() => { written = []; });

// 2 x 2 slice: voxel 0 in both visits (persistent), 1 in the first only (resolved), 2 in the second only (new), 3 none.
const DIMS = { depth: 1, height: 2, width: 2 };
const TP1 = Uint8Array.from([1, 1, 0, 0]);
const TP2 = Uint8Array.from([1, 0, 1, 0]);
const emptyMask = {
  isLoaded: true, getSliceMask: () => new Uint8Array(4),
  state: { dimensions: DIMS, isDirty: false, isLoading: false, conflict: null },
  paintStroke: () => {}, beginStroke: () => {}, endStroke: () => {},
};

async function drawLongitudinal(): Promise<number[][]> {
  useSegmentationStore.setState({
    zoneMapVisible: false, zoneMapMask: null, conformalVisible: false, longitudinalSubtractionVisible: false,
    selectedLesion: null, longitudinalVisible: true, longitudinalTp1Mask: TP1, longitudinalTp1Dims: DIMS,
    longitudinalTp2Mask: TP2, longitudinalTp2Dims: DIMS,
  } as never);
  const container = document.createElement('div');
  document.body.appendChild(container);
  render(
    <SegmentationCanvasLocal
      ref={createRef()}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      segmentationMask={emptyMask as any}
      sliceIndex={0} imageWidth={2} imageHeight={2} containerRef={{ current: container }} onPaintStroke={() => {}}
      selectedLabelId={1} brushSize={1} eraseMode={false} showOverlay={false} enabled={false} baseImageData=""
      zoomLevel={1} panOffset={{ x: 0, y: 0 }} showBaseImage={false} renderedImageSize={{ width: 200, height: 200 }}
    />,
  );
  await waitFor(() => expect(written.some((d) => d[3] > 0)).toBe(true));
  const d = written.filter((x) => x[3] > 0).pop()!;
  return [0, 1, 2, 3].map((v) => [d[v * 4], d[v * 4 + 1], d[v * 4 + 2], d[v * 4 + 3]]);
}

const toHex = (c: number[]) => `#${c.slice(0, 3).map((x) => x.toString(16).padStart(2, '0')).join('').toUpperCase()}`;
const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const over = (c: number[], grey: number) => c.slice(0, 3).map((v) => Math.round((v * c[3] + grey * (255 - c[3])) / 255));
function lin(c: number) { const x = c / 255; return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }
function lab(rgbLin: number[]) {
  const [r, g, b] = rgbLin.map((v) => Math.min(1, Math.max(0, v)));
  const X = 0.4124 * r + 0.3576 * g + 0.1805 * b, Y = 0.2126 * r + 0.7152 * g + 0.0722 * b, Z = 0.0193 * r + 0.1192 * g + 0.9505 * b;
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  const fx = f(X / 0.95047), fy = f(Y), fz = f(Z / 1.08883);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}
// Machado, Oliveira & Fernandes 2009, severity 1.0 (on linear RGB) — the matrices of the PRB-010 test
const DEUTAN = [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]];
const PROTAN = [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]];
const TRITAN = [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]];
const NORMAL = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
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

describe('PRB-031: the longitudinal overlay is readable for colour-blind readers', () => {
  it('rc093 prb031 persistent, resolved and new are drawn in the shared colour-blind-safe palette at the fixed 55 %', async () => {
    const drawn = await drawLongitudinal();
    expect(drawn[3][3]).toBe(0);                                         // no lesion: nothing drawn
    for (const c of drawn.slice(0, 3)) {
      expect(OKABE_ITO).toContain(toHex(c));
      expect(c[3]).toBe(Math.round(0.55 * 255));
    }
    expect(new Set(drawn.slice(0, 3).map(toHex)).size).toBe(3);
  });

  it('rc093 prb031 no two of them are red against green, and every pair stays apart for colour-blind readers', async () => {
    const drawn = (await drawLongitudinal()).slice(0, 3);
    const hexes = drawn.map(toHex);
    for (let a = 0; a < 3; a++) {
      for (let b = a + 1; b < 3; b++) {
        const pair = `${hexes[a]} / ${hexes[b]}`;
        expect(isRed(hexes[a]) && isGreen(hexes[b]) || isGreen(hexes[a]) && isRed(hexes[b]), pair).toBe(false);
        for (const m of [DEUTAN, PROTAN, TRITAN]) expect(dE(seenAs(hexes[a], m), seenAs(hexes[b], m)), pair).toBeGreaterThan(15);
        for (const grey of [128, 220]) {
          const ca = toHex(over(drawn[a], grey)), cb = toHex(over(drawn[b], grey));
          for (const m of [NORMAL, DEUTAN, PROTAN, TRITAN]) expect(dE(seenAs(ca, m), seenAs(cb, m)), `${pair} on grey ${grey}`).toBeGreaterThan(9);
        }
      }
    }
  });
});
