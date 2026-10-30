/**
 * The "W/L GPU" 2D view (NiivueViewer2D) against the standard 2D view.
 *
 *   PRB-004 (HAZ-006): the standard 2D view (and the matplotlib and multi-panel views) draw
 *          storage voxel (i, j) of slice k at row i, column j: rows run down the screen, columns
 *          to the right. niivue placed the same voxel by the scanner affine, so the GPU view
 *          showed every slice rotated by 90 degrees (and, depending on the stored orientation,
 *          mirrored), and its slider picked a fractional position between two slices.
 *          Required: the GPU view draws every voxel of the image AND of the mask where the
 *          standard view draws it, on the same slice; a mask that is not on the image's own
 *          voxel grid in the standard voxel order is not drawn in this view, and the view says so.
 *   PRB-005: the view failed with "Cannot read properties of undefined (reading 'toUpperCase')"
 *          when the page was served from a host name without a dot (localhost, a hospital server
 *          name): niivue derives the file type from the blob URL's "extension".
 *   PRB-006: the mask was coloured with the display range its header copied from the MRI, so
 *          the background of the mask (0) was tinted and the lesions (1) were nearly invisible.
 *
 * niivue's renderer is replaced (jsdom has no WebGL); its parser, affine math and loaders are
 * real (src/test/niivueHarness.ts). Each test asserts where niivue places a voxel or what it
 * loads, never what the component passed in.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';

vi.mock('@niivue/niivue', async (orig) =>
  (await import('@/test/niivueHarness')).harnessModule(await orig()));

import { NiivueViewer2D } from './NiivueViewer2D';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { harness, installBrowserNetwork, niivueAxialScreenOf } from '@/test/niivueHarness';
import { syntheticNifti, voxelIndex, LAS_AFFINE } from '@/test/syntheticNifti';

const FILE = 'patients/p/studies/s/series/se/flair.nii.gz';
const SEG = 'seg-0001';
const DIMS: [number, number, number] = [6, 8, 5]; // rows 6, columns 8, slices 5 — every axis distinct
const V2 = 'RC031-ORIENT-V2';

function image(): ArrayBuffer {
  const data = new Uint8Array(DIMS[0] * DIMS[1] * DIMS[2]);
  for (let n = 0; n < data.length; n++) data[n] = (n * 7) % 251;
  return syntheticNifti({ dims: DIMS, affine: LAS_AFFINE, data, calMin: -15.5, calMax: 189.2, gzip: true });
}

function mask(opts: { dims?: [number, number, number]; affine?: number[][]; descrip?: string } = {}): ArrayBuffer {
  const dims = opts.dims ?? DIMS;
  const data = new Uint8Array(dims[0] * dims[1] * dims[2]);
  data[voxelIndex(dims, 1, 2, 3)] = 1;
  return syntheticNifti({
    dims, affine: opts.affine ?? LAS_AFFINE, data, calMin: -15.5, calMax: 189.2,
    descrip: opts.descrip ?? V2, gzip: true,
  });
}

function setStores(sliceIndex = 2, withMask = true) {
  useViewerStore.setState({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    currentSeries: {
      id: FILE, name: 'flair', format: 'nifti', file_id: FILE, total_slices: DIMS[2],
      metadata: { rows: DIMS[0], columns: DIMS[1], slices: DIMS[2], anatomical_orientation: 'LAS' },
      slices: [],
    } as any,
    currentSliceIndex: sliceIndex,
    windowCenter: 0,
    windowWidth: 0,
  });
  useSegmentationStore.setState({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    currentSegmentation: withMask ? ({ segmentation_id: SEG } as any) : null,
    isOverlayVisible: true,
    lesionOpacity: 0.6,
  });
}

async function mounted(wantVolumes: number) {
  await waitFor(() => {
    expect(harness.instances.length).toBeGreaterThan(0);
    expect(harness.instances[harness.instances.length - 1].volumes.length).toBe(wantVolumes);
  }, { timeout: 5000 });
  return harness.instances[harness.instances.length - 1];
}

beforeEach(() => {
  harness.reset();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe('PRB-004 — the W/L GPU view draws each voxel where the standard view draws it', () => {
  it('rc073 harness pin: niivue axial 2D puts patient left (−X) on the left and anterior (+Y) on top', async () => {
    // niivueAxialScreenOf() relies on this convention. It is read from niivue's own orientation
    // text routine with the options the component uses (letters switched back on only here).
    setStores(2, false);
    installBrowserNetwork('http://127.0.0.1:4173', { [`/api/v1/imaging/nifti/${FILE}`]: image() });
    render(<NiivueViewer2D />);
    const nv = await mounted(1);
    expect(nv.opts.isRadiologicalConvention ?? false).toBe(false);

    const actual = await vi.importActual<typeof import('@niivue/niivue')>('@niivue/niivue');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const real = new actual.Niivue({ ...nv.opts, isOrientationTextVisible: true }) as any;
    real.gl = { canvas: { width: 400, height: 400 }, viewport() {} };
    const drawn: Record<string, string> = {};
    real.drawTextBelow = (_xy: number[], t: string) => { drawn.top = t; };
    real.drawTextRight = (_xy: number[], t: string) => { drawn.left = t; };
    real.drawTextAbove = (_xy: number[], t: string) => { drawn.bottom = t; };
    real.drawTextLeft = (_xy: number[], t: string) => { drawn.right = t; };
    real.opts.showAllOrientationMarkers = true;
    real.drawSliceOrientationText([0, 0, 400, 400], 0 /* AXIAL */);
    expect(drawn).toEqual({ top: 'A', left: 'L', bottom: 'P', right: 'R' });
  });

  it('rc073 every voxel of the slice is drawn at the standard view position: row i down, column j right', async () => {
    setStores(2, false);
    installBrowserNetwork('http://127.0.0.1:4173', { [`/api/v1/imaging/nifti/${FILE}`]: image() });
    render(<NiivueViewer2D />);
    const nv = await mounted(1);
    const base = nv.volumes[0];

    for (let i = 0; i < DIMS[0]; i++) {
      for (let j = 0; j < DIMS[1]; j++) {
        const s = niivueAxialScreenOf(base, i, j, 2);
        expect(s.down).toBeCloseTo((i + 0.5) / DIMS[0], 6);
        expect(s.right).toBeCloseTo((j + 0.5) / DIMS[1], 6);
      }
    }
  });

  it('rc073 the slice shown is the standard view slice index, at the centre of that voxel slice', async () => {
    setStores(0, false);
    installBrowserNetwork('http://127.0.0.1:4173', { [`/api/v1/imaging/nifti/${FILE}`]: image() });
    render(<NiivueViewer2D />);
    const nv = await mounted(1);
    const base = nv.volumes[0];

    for (let k = 0; k < DIMS[2]; k++) {
      act(() => useViewerStore.setState({ currentSliceIndex: k }));
      await waitFor(() => expect(nv.scene.crosshairPos[2]).toBeCloseTo(niivueAxialScreenOf(base, 0, 0, k).depth, 6));
      expect(nv.scene.crosshairPos[2]).toBeCloseTo((k + 0.5) / DIMS[2], 6);
    }
  });

  it('rc073 the mask is drawn on exactly the image voxels the standard view overlays it on', async () => {
    setStores(3, true);
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: image(),
      [`/api/v1/segmentation/${SEG}/nifti`]: mask(),
    });
    render(<NiivueViewer2D />);
    const nv = await mounted(2);
    const [base, overlay] = nv.volumes;

    for (const [i, j, k] of [[1, 2, 3], [0, 0, 0], [5, 7, 4], [5, 0, 1]]) {
      const b = niivueAxialScreenOf(base, i, j, k);
      const m = niivueAxialScreenOf(overlay, i, j, k);
      expect(m.down).toBeCloseTo((i + 0.5) / DIMS[0], 6);
      expect(m.right).toBeCloseTo((j + 0.5) / DIMS[1], 6);
      expect(m.depth).toBeCloseTo((k + 0.5) / DIMS[2], 6);
      expect([m.down, m.right, m.depth]).toEqual([b.down, b.right, b.depth]);
    }
  });

  it('rc073 a mask on another voxel grid is not drawn in this view, and the view says so', async () => {
    setStores(2, true);
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: image(),
      [`/api/v1/segmentation/${SEG}/nifti`]: mask({ dims: [6, 8, 4] }),
    });
    render(<NiivueViewer2D />);
    await mounted(1);
    // Review m9: it names the cause; the Standard view is not offered for a mask on another grid.
    expect(await screen.findByTestId('niivue-mask-not-shown')).toHaveTextContent(/voxel grid differs/i);
  });

  it('rc073 a mask with the image shape but another position in the scanner is not drawn', async () => {
    const shifted = LAS_AFFINE.map((r) => [...r]);
    shifted[0][3] += 0.5; // half a voxel
    setStores(2, true);
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: image(),
      [`/api/v1/segmentation/${SEG}/nifti`]: mask({ affine: shifted }),
    });
    render(<NiivueViewer2D />);
    await mounted(1);
    expect(await screen.findByTestId('niivue-mask-not-shown')).toBeInTheDocument();
  });

  it('rc073 a mask stored without the RC-031 voxel-order marker (legacy in-plane transpose) is not drawn', async () => {
    setStores(2, true);
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: image(),
      [`/api/v1/segmentation/${SEG}/nifti`]: mask({ descrip: '' }),
    });
    render(<NiivueViewer2D />);
    await mounted(1);
    expect(await screen.findByTestId('niivue-mask-not-shown')).toBeInTheDocument();
  });

  it('rc073 a mask that cannot be loaded is not silently missing: the view says it is not drawn', async () => {
    setStores(2, true);
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: image(),
      [`/api/v1/segmentation/${SEG}/nifti`]: 500,
    });
    render(<NiivueViewer2D />);
    await mounted(1);
    expect(await screen.findByTestId('niivue-mask-not-shown')).toHaveTextContent(/could not be loaded/i);
  });

  it('rc073 a mask on the image grid is drawn and no "not shown" notice appears', async () => {
    setStores(2, true);
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: image(),
      [`/api/v1/segmentation/${SEG}/nifti`]: mask(),
    });
    render(<NiivueViewer2D />);
    await mounted(2);
    expect(screen.queryByTestId('niivue-mask-not-shown')).not.toBeInTheDocument();
  });
});

describe('PRB-005 — served from a host name without a dot', () => {
  for (const origin of ['http://localhost:4173', 'http://mstool-viewer']) {
    it(`prb005 the W/L GPU view loads the image and the mask on ${origin}`, async () => {
      setStores(2, true);
      installBrowserNetwork(origin, {
        [`/api/v1/imaging/nifti/${FILE}`]: image(),
        [`/api/v1/segmentation/${SEG}/nifti`]: mask(),
      });
      render(<NiivueViewer2D />);
      await mounted(2);
      expect(screen.queryByText(/toUpperCase/)).not.toBeInTheDocument();
    });
  }
});

describe('PRB-006 — the mask colours do not depend on the display range in its header', () => {
  it('rc074 mask background (0) is transparent and every lesion label (>= 1) full colour despite an MRI-copied range', async () => {
    setStores(3, true);
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: image(),
      [`/api/v1/segmentation/${SEG}/nifti`]: mask(),
    });
    render(<NiivueViewer2D />);
    const nv = await mounted(2);
    const overlay = nv.volumes[1];
    // Precondition on the fixture: read as stored, the mask's header carries the MRI's window.
    const { NVImage } = await vi.importActual<typeof import('@niivue/niivue')>('@niivue/niivue');
    const asStored = await NVImage.loadFromUrl({ url: 'm.nii', name: 'm.nii', buffer: mask() });
    expect(asStored.cal_min).toBeCloseTo(-15.5, 3);
    expect(asStored.cal_max).toBeCloseTo(189.2, 3);
    // niivue: value <= cal_min → colour-map index 0 (alpha 0, transparent); >= cal_max → full colour.
    expect(0).toBeLessThanOrEqual(overlay.cal_min);
    expect(1).toBeGreaterThanOrEqual(overlay.cal_max);
    expect(overlay.cal_max).toBeGreaterThan(overlay.cal_min);
  });
});
