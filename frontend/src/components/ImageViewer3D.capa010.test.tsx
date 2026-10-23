/**
 * CAPA-010 — the 3D viewer (ImageViewer3D), rendered for real with niivue replaced by a
 * recording stand-in (jsdom has no WebGL).
 *
 *   RC-016 (HAZ-009): patient identity is annotated on the 3D viewport, in volume and
 *          multiplanar mode — not only in 2D.
 *   RC-023 (HAZ-006): no laterality glyph is drawn in 3D. The effective niivue options of
 *          every instance are fed to the REAL niivue drawing routines, which must draw
 *          neither the orientation cube nor the L/R/A/P slice letters; the orientation is
 *          reported as text by the safety overlay instead, with the standing caveat.
 *   RC-037 (HAZ-006): the selected-lesion crosshair and bounding box are placed at the
 *          voxel the lesion analysis reported. The analysis runs on the internal
 *          (k, a0, a1) mask, so its (z, y, x) is NIfTI voxel (i, j, k) = (y, x, z).
 *          Using (x, y, z) transposed both markers in-plane.
 *
 * Each test asserts what reaches the screen or the renderer, never what was passed in.
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';

vi.mock('@niivue/niivue', async () => (await import('@/test/fakeNiivue')).niivueModule);

import ImageViewer3D from './ImageViewer3D';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type { LesionInfo } from '@/types';
import { fakeNiivue, FAKE_AFFINE } from '@/test/fakeNiivue';

const nv = { instances: fakeNiivue.instances, AFFINE: FAKE_AFFINE };

// ── the lesion: asymmetric so that a swap of any two axes is visible ──
const LESION: LesionInfo = {
  id: 7,
  label_id: 1,
  region: 'Periventricular',
  voxel_count: 30,
  volume_mm3: 108,
  volume_ml: 0.108,
  size_category: 'medium',
  centroid: { z: 5, y: 10, x: 40 },
  bounding_box: { z_min: 5, z_max: 6, y_min: 10, y_max: 12, x_min: 40, x_max: 44 },
};
const world = (i: number, j: number, k: number) =>
  [0, 1, 2].map((r) => nv.AFFINE[r][0] * i + nv.AFFINE[r][1] * j + nv.AFFINE[r][2] * k + nv.AFFINE[r][3]);

// ── jsdom stand-ins for layout, download and blob URLs ──
const saved: Record<string, PropertyDescriptor | undefined> = {};
beforeAll(() => {
  for (const [key, value] of [['clientWidth', 800], ['clientHeight', 600]] as const) {
    saved[key] = Object.getOwnPropertyDescriptor(HTMLElement.prototype, key);
    Object.defineProperty(HTMLElement.prototype, key, { configurable: true, get: () => value });
  }
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    headers: { get: () => null },
    arrayBuffer: async () => new ArrayBuffer(16),
    text: async () => '',
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

function setScene(mode: 'volume' | 'multiplanar', lesion: LesionInfo | null = null) {
  nv.instances.length = 0;
  useViewerStore.setState({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    currentSeries: {
      id: 's1', name: 'FLAIR', format: 'nifti', total_slices: 60, file_id: 'f1',
      metadata: { rows: 182, columns: 218, slices: 60, anatomical_orientation: 'LAS' },
    } as any,
    render3DMode: mode,
  });
  useSegmentationStore.setState({ selectedLesion: lesion, currentSegmentation: null });
}

async function rendered(mode: 'volume' | 'multiplanar') {
  const want = mode === 'volume' ? 1 : 4;
  await waitFor(() => {
    expect(nv.instances.length).toBe(want);
    for (const inst of nv.instances) expect(inst.volumes.length).toBeGreaterThan(0);
  });
}

beforeEach(() => {
  nv.instances.length = 0;
});

describe('RC-016 — patient identity on the 3D viewport', () => {
  it('rc016 3D volume mode renders the patient name and MRN on the viewport', async () => {
    setScene('volume');
    render(<ImageViewer3D patientName="Ana Torres" patientMRN="MRN-99120" />);
    await rendered('volume');

    const identity = screen.getByTestId('viewport-patient-identity');
    expect(identity).toHaveTextContent('Ana Torres');
    expect(identity).toHaveTextContent('MRN-99120');
  });

  it('rc016 3D multiplanar mode renders the patient name and MRN on the viewport', async () => {
    setScene('multiplanar');
    render(<ImageViewer3D patientName="Ana Torres" patientMRN="MRN-99120" />);
    await rendered('multiplanar');

    expect(screen.getByTestId('viewport-patient-identity')).toHaveTextContent('Ana Torres');
    expect(screen.getByTestId('viewport-patient-identity')).toHaveTextContent('MRN-99120');
  });

  it('rc016 3D view warns that the patient is not identified when identity is absent', async () => {
    setScene('volume');
    render(<ImageViewer3D />);
    await rendered('volume');

    expect(screen.getByTestId('viewport-identity-missing')).toBeInTheDocument();
  });
});

describe('RC-023 — no laterality glyph in 3D; orientation reported as text', () => {
  /** Feed the component's EFFECTIVE options to the real niivue drawing routines. */
  async function realNiivueGlyphs(passed: Record<string, unknown>) {
    const actual = await vi.importActual<typeof import('@niivue/niivue')>('@niivue/niivue');
    const real = new actual.Niivue(passed) as unknown as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
    const glCalls: string[] = [];
    real.gl = new Proxy({ canvas: { width: 400, height: 400, clientWidth: 400, clientHeight: 400 } }, {
      get(target: Record<string, unknown>, prop) {
        if (prop in target) return target[prop as string];
        if (typeof prop === 'string' && /^[A-Z0-9_]+$/.test(prop)) return 0;
        return () => { glCalls.push(String(prop)); };
      },
    });
    real.orientCubeShader = { use() {}, uniforms: {} };
    real.drawOrientationCube([0, 0, 400, 400], 0, 15);

    const letters: string[] = [];
    real.draw2DMain = () => {};
    for (const fn of ['drawTextBelow', 'drawTextRight', 'drawTextAbove', 'drawTextLeft', 'drawTextRightBelow']) {
      real[fn] = (_xy: unknown, text: string) => { letters.push(text); };
    }
    real.textWidth = () => 8;
    for (const axCorSag of [0, 1, 2]) real.draw2D([0, 0, 400, 400], axCorSag);
    return { cubeDrawn: glCalls.includes('drawArrays'), letters };
  }

  it('rc023 the niivue default would draw slice letters, so the viewer must switch them off explicitly', async () => {
    // Guards the reasoning of the next tests: omitting the option is NOT enough.
    const { letters } = await realNiivueGlyphs({});
    expect(letters).toEqual(expect.arrayContaining(['A', 'L']));
  });

  it('rc023 3D volume mode draws no orientation cube and no slice letters', async () => {
    setScene('volume');
    render(<ImageViewer3D patientName="Ana Torres" />);
    await rendered('volume');

    for (const inst of nv.instances) {
      const glyphs = await realNiivueGlyphs(inst.opts);
      expect(glyphs.cubeDrawn).toBe(false);
      expect(glyphs.letters).toEqual([]);
    }
  });

  it('rc023 3D multiplanar mode draws no orientation cube and no slice letters in any of its 4 panels', async () => {
    setScene('multiplanar');
    render(<ImageViewer3D patientName="Ana Torres" />);
    await rendered('multiplanar');

    expect(nv.instances).toHaveLength(4);
    for (const inst of nv.instances) {
      const glyphs = await realNiivueGlyphs(inst.opts);
      expect(glyphs.cubeDrawn).toBe(false);
      expect(glyphs.letters).toEqual([]);
    }
  });

  it('rc023 3D view reports the orientation read from the affine and the standing laterality caveat', async () => {
    setScene('volume');
    render(<ImageViewer3D patientName="Ana Torres" />);
    await rendered('volume');

    const overlay = screen.getByTestId('viewport-safety-overlay');
    expect(within(overlay).getByTestId('viewport-orientation')).toHaveTextContent('LAS');
    expect(within(overlay).getByText(/confirm side against the source study/i)).toBeInTheDocument();
  });
});

describe('RC-037 — selected-lesion markers in 3D sit on the reported voxel', () => {
  it('rc037 the volume-mode crosshair is placed at affine * (y, x, z) of the lesion centroid', async () => {
    setScene('volume', LESION);
    render(<ImageViewer3D patientName="Ana Torres" />);
    await rendered('volume');

    const inst = nv.instances[0];
    await waitFor(() => expect(inst.mm2fracCalls.length).toBeGreaterThan(0));
    const expected = world(LESION.centroid.y, LESION.centroid.x, LESION.centroid.z); // (i, j, k)
    const placed = inst.scene.crosshairPos;
    placed.forEach((v, a) => expect(v).toBeCloseTo(expected[a], 6));
  });

  it('rc037 every multiplanar panel puts its crosshair on the same, correct lesion point', async () => {
    setScene('multiplanar', LESION);
    render(<ImageViewer3D patientName="Ana Torres" />);
    await rendered('multiplanar');

    const expected = world(LESION.centroid.y, LESION.centroid.x, LESION.centroid.z);
    await waitFor(() => {
      for (const inst of nv.instances) {
        inst.scene.crosshairPos.forEach((v, a) => expect(v).toBeCloseTo(expected[a], 6));
      }
    });
  });

  it('rc037 the bounding box mesh spans exactly the lesion box in scanner space', async () => {
    setScene('volume', LESION);
    render(<ImageViewer3D patientName="Ana Torres" />);
    await rendered('volume');

    const inst = nv.instances[0];
    await waitFor(() => expect(inst.meshes.length).toBe(1));
    const verts = inst.meshes[0].buffer;
    const lo = [Infinity, Infinity, Infinity];
    const hi = [-Infinity, -Infinity, -Infinity];
    for (let n = 0; n < verts.length; n += 3) {
      for (let a = 0; a < 3; a++) {
        lo[a] = Math.min(lo[a], verts[n + a]);
        hi[a] = Math.max(hi[a], verts[n + a]);
      }
    }
    // Corners of the box: i = y range, j = x range, k = z range, through the affine.
    const bb = LESION.bounding_box;
    const corners = [];
    for (const i of [bb.y_min, bb.y_max]) for (const j of [bb.x_min, bb.x_max]) for (const k of [bb.z_min, bb.z_max]) corners.push(world(i, j, k));
    const radius = 0.3; // tube radius used by the viewer
    for (let a = 0; a < 3; a++) {
      const cmin = Math.min(...corners.map((c) => c[a]));
      const cmax = Math.max(...corners.map((c) => c[a]));
      expect(lo[a]).toBeGreaterThanOrEqual(cmin - radius - 1e-4);
      expect(lo[a]).toBeLessThanOrEqual(cmin + 1e-4);
      expect(hi[a]).toBeLessThanOrEqual(cmax + radius + 1e-4);
      expect(hi[a]).toBeGreaterThanOrEqual(cmax - 1e-4);
    }
  });
});
