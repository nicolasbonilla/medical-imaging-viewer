/**
 * PRB-004 — independent review of PR #71 (39f9d44): the 3D view.
 *
 *   M1  the 3D view drew a mask saved before RC-031 (in-plane transpose, no marker) or one stored with the
 *       identity fallback (no scanner position) mirrored or off-position, with no notice — the lesion mask and
 *       the two visit masks. Required: masks requested aligned to the image (`?ref_file_id=`); a mask without the
 *       RC-031 marker or without a scanner position is not drawn, and the view says so;
 *   M2  a segmentation not saved yet was silently absent;
 *   M3  "go to slice" set niivue's axial fraction index / (depth − 1): the wrong level, and the wrong axis for
 *       a sagittally stored volume. Required: storage slice k reached through voxel → mm → niivue's mm2frac;
 *   m2  the later-visit mask was drawn white (top of niivue's "hot" at range 0..1);
 *   m6  a region-classified mask was drawn all red.
 * Re-review (39f9d44..4626d17):
 *   R1  a mask download that failed was only logged: the mask silently missing, or the PREVIOUS mask still drawn
 *       after a switch while the app names the new one;
 *   R3  unsaved edits on a saved segmentation were not stated (3D draws the last saved mask);
 *   R4  an identity-transform mask was refused even when the image's own transform is the identity;
 *   R7  niivue's view-type and clip-plane keys acted in 3D (a panel labelled "Axial" could show another view).
 *
 * niivue's renderer replaced, its loaders, mm2frac and colormaps real (src/test/niivueHarness.ts).
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';

vi.mock('@niivue/niivue', async (orig) =>
  (await import('@/test/niivueHarness')).harnessModule(await orig()));

import ImageViewer3D from './ImageViewer3D';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { harness, installBrowserNetwork } from '@/test/niivueHarness';
import { syntheticNifti, voxelIndex, LAS_AFFINE } from '@/test/syntheticNifti';

const FILE = 'patients/p/studies/s/series/se/flair.nii.gz';
const DIMS: [number, number, number] = [6, 8, 5];
const V2 = 'RC031-ORIENT-V2';
const LEGEND = ['#E69F00', '#56B4E9', '#009E73', '#D55E00'];
// Sagittally stored: storage slices k run left → right (RAS x); i = posterior → anterior, j = inferior → superior.
const SAGITTAL = [[0, 0, 1, -2], [1, 0, 0, -3], [0, 1.2, 0, -4], [0, 0, 0, 1]];

const img = (affine = LAS_AFFINE) => syntheticNifti({ dims: DIMS, affine, gzip: true,
  data: Uint8Array.from({ length: DIMS[0] * DIMS[1] * DIMS[2] }, (_, n) => 50 + (n % 100)) });
function msk(o: { affine?: number[][]; descrip?: string; labels?: number[] } = {}) {
  const data = new Uint8Array(DIMS[0] * DIMS[1] * DIMS[2]);
  (o.labels ?? [1]).forEach((v, n) => { data[voxelIndex(DIMS, n % DIMS[0], 2, 3)] = v; });
  return syntheticNifti({ dims: DIMS, affine: o.affine ?? LAS_AFFINE, data, descrip: o.descrip ?? V2, gzip: true });
}

const saved: Record<string, PropertyDescriptor | undefined> = {};
beforeAll(() => {
  for (const [key, value] of [['clientWidth', 800], ['clientHeight', 600]] as const) {
    saved[key] = Object.getOwnPropertyDescriptor(HTMLElement.prototype, key);
    Object.defineProperty(HTMLElement.prototype, key, { configurable: true, get: () => value });
  }
});
afterAll(() => {
  for (const key of ['clientWidth', 'clientHeight']) {
    if (saved[key]) Object.defineProperty(HTMLElement.prototype, key, saved[key]!);
  }
});
beforeEach(() => harness.reset());
afterEach(() => vi.unstubAllGlobals());

function scene(mode: 'volume' | 'multiplanar', seg: Record<string, unknown> | null, visits = false) {
  useViewerStore.setState({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    currentSeries: { id: 's', name: 'f', format: 'nifti', total_slices: DIMS[2], file_id: FILE,
      metadata: { rows: DIMS[0], columns: DIMS[1], slices: DIMS[2], anatomical_orientation: 'LAS' } } as any,
    render3DMode: mode, currentSliceIndex: 0,
  });
  useSegmentationStore.setState({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    selectedLesion: null, currentSegmentation: seg as any, zoneMapSegId: null,
    longitudinalTp1SegId: visits ? 'tp1' : null, longitudinalTp2SegId: visits ? 'tp2' : null, longitudinalVisible: visits,
  });
}

async function loaded(mode: 'volume' | 'multiplanar', volumesEach: number) {
  const want = mode === 'volume' ? 1 : 4;
  await waitFor(() => {
    expect(harness.instances.length).toBe(want);
    for (const inst of harness.instances) expect(inst.volumes.length).toBe(volumesEach);
  }, { timeout: 8000 });
}

/** The colour niivue draws label value v of `vol` in: its colormap at v's place in its display range. */
function drawnHex(vol: { colormap: string; cal_min: number; cal_max: number }, v: number) {
  const cm = harness.colormaps[vol.colormap] as { R: number[]; G: number[]; B: number[] } | undefined;
  if (!cm) return `unregistered colormap ${vol.colormap}`;
  const t = Math.max(0, Math.min(255, Math.round(((v - vol.cal_min) / (vol.cal_max - vol.cal_min)) * 255)));
  return `#${[cm.R[t], cm.G[t], cm.B[t]].map((c) => c.toString(16).padStart(2, '0')).join('').toUpperCase()}`;
}

describe('PRB-004 review — 3D view', () => {
  it('rc073 M1: the lesion mask and both visit masks are requested aligned to the image (ref_file_id)', async () => {
    scene('volume', { segmentation_id: 'seg-1' }, true);
    const net = installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: img(), '/api/v1/segmentation/seg-1/nifti': msk(),
      '/api/v1/segmentation/tp1/nifti': msk(), '/api/v1/segmentation/tp2/nifti': msk() });
    render(<ImageViewer3D patientName="A" />);
    await loaded('volume', 4);
    const ref = `ref_file_id=${encodeURIComponent(FILE)}`;
    for (const id of ['seg-1', 'tp1', 'tp2']) {
      expect(net.requests.some((u) => u.includes(`/api/v1/segmentation/${id}/nifti?${ref}`))).toBe(true);
    }
  });

  for (const mode of ['volume', 'multiplanar'] as const) {
    it(`rc073 M1: 3D ${mode}: a mask without the RC-031 voxel-order marker is not drawn, and the view says so`, async () => {
      scene(mode, { segmentation_id: 'seg-1' });
      installBrowserNetwork('http://127.0.0.1:4173', {
        [`/api/v1/imaging/nifti/${FILE}`]: img(), '/api/v1/segmentation/seg-1/nifti': msk({ descrip: '' }) });
      render(<ImageViewer3D patientName="A" />);
      await loaded(mode, 1);
      expect(await screen.findByTestId('niivue-3d-mask-not-shown')).toHaveTextContent(/older voxel order/i);
    });
  }

  it('rc073 M1: a mask with no scanner position (identity fallback) is not drawn, and the view says so', async () => {
    scene('volume', { segmentation_id: 'seg-1' });
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: img(),
      '/api/v1/segmentation/seg-1/nifti': msk({ affine: [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]] }) });
    render(<ImageViewer3D patientName="A" />);
    await loaded('volume', 1);
    expect(await screen.findByTestId('niivue-3d-mask-not-shown')).toHaveTextContent(/position/i);
  });

  it('rc073 M1: a legacy later-visit mask is not drawn, the other masks are, and the view names it', async () => {
    scene('volume', { segmentation_id: 'seg-1' }, true);
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: img(), '/api/v1/segmentation/seg-1/nifti': msk(),
      '/api/v1/segmentation/tp1/nifti': msk(), '/api/v1/segmentation/tp2/nifti': msk({ descrip: '' }) });
    render(<ImageViewer3D patientName="A" />);
    await loaded('volume', 3);
    expect(await screen.findByTestId('niivue-3d-mask-not-shown')).toHaveTextContent(/later visit/i);
  });

  it('rc073 M2: a segmentation not saved yet is not shown in 3D, and the view says so', async () => {
    scene('volume', { segmentation_id: 'local-77' });
    installBrowserNetwork('http://127.0.0.1:4173', { [`/api/v1/imaging/nifti/${FILE}`]: img() });
    render(<ImageViewer3D patientName="A" />);
    await loaded('volume', 1);
    expect(await screen.findByTestId('niivue-3d-mask-not-shown')).toHaveTextContent(/not saved/i);
  });

  for (const [name, affine, axis] of [['axial LAS', LAS_AFFINE, 2], ['sagittally stored', SAGITTAL, 0]] as const) {
    it(`rc073 M3: "go to slice" reaches storage slice k on its own axis (${name})`, async () => {
      scene('volume', null);
      installBrowserNetwork('http://127.0.0.1:4173', { [`/api/v1/imaging/nifti/${FILE}`]: img(affine as number[][]) });
      render(<ImageViewer3D patientName="A" />);
      await loaded('volume', 1);
      const nv = harness.instances[0];
      const vol = nv.volumes[0];
      const fracOf = (i: number, j: number, k: number) => {
        const a = vol.hdr.affine as number[][];
        return Array.from(vol.convertMM2Frac([0, 1, 2].map((r) => a[r][0] * i + a[r][1] * j + a[r][2] * k + a[r][3]))) as number[];
      };
      for (const k of [0, 2, 4]) {
        act(() => useViewerStore.setState({ currentSliceIndex: k }));
        const want = fracOf((DIMS[0] - 1) / 2, (DIMS[1] - 1) / 2, k)[axis];
        await waitFor(() => expect(nv.scene.crosshairPos[axis]).toBeCloseTo(want, 6));
      }
    });
  }

  for (const mode of ['volume', 'multiplanar'] as const) {
    // Film capture (coordinator, 2026-10-28): niivue's colour bar, drawn along the bottom of the 3D render, lay under
    // the standing "Laterality not labelled" caveat (RC-023) of the viewport's safety overlay — both unreadable.
    it(`rc023 3D ${mode}: niivue draws no colour bar under the laterality caveat`, async () => {
      scene(mode, null);
      installBrowserNetwork('http://127.0.0.1:4173', { [`/api/v1/imaging/nifti/${FILE}`]: img() });
      render(<ImageViewer3D patientName="A" />);
      await loaded(mode, 1);
      for (const nv of harness.instances) expect(nv.opts.isColorbar).toBe(false);
      expect(screen.getByText(/Laterality not labelled/)).toBeInTheDocument();
    });
  }

  it('rc073 R1: a lesion mask that cannot be downloaded is named in 3D: could not be loaded', async () => {
    scene('volume', { segmentation_id: 'seg-1' });
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: img(), '/api/v1/segmentation/seg-1/nifti': 500 });
    render(<ImageViewer3D patientName="A" />);
    await loaded('volume', 1);
    expect(await screen.findByTestId('niivue-3d-mask-not-shown')).toHaveTextContent(/segmentation.*could not be loaded/i);
  });

  it('rc073 R1: after a switch, a failed download never leaves the previous mask drawn', async () => {
    scene('volume', { segmentation_id: 'seg-1' });
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: img(), '/api/v1/segmentation/seg-1/nifti': msk(),
      '/api/v1/segmentation/seg-2/nifti': 500 });
    render(<ImageViewer3D patientName="A" />);
    await loaded('volume', 2);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    act(() => useSegmentationStore.setState({ currentSegmentation: { segmentation_id: 'seg-2' } as any }));
    expect(await screen.findByTestId('niivue-3d-mask-not-shown')).toHaveTextContent(/could not be loaded/i);
    await waitFor(() => {
      const last = harness.instances[harness.instances.length - 1];
      expect(last.volumes.length).toBe(1);
    }, { timeout: 8000 });
  });

  it('rc073 R1: a later-visit mask that cannot be downloaded is named in 3D', async () => {
    scene('volume', null, true);
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: img(), '/api/v1/segmentation/tp1/nifti': msk(),
      '/api/v1/segmentation/tp2/nifti': 503 });
    render(<ImageViewer3D patientName="A" />);
    expect(await screen.findByTestId('niivue-3d-mask-not-shown', undefined, { timeout: 8000 }))
      .toHaveTextContent(/later visit.*could not be loaded/i);
  });

  it('rc073 R3: unsaved edits on a saved segmentation are stated in 3D', async () => {
    scene('volume', { segmentation_id: 'seg-1' });
    useSegmentationStore.setState({ hasUnsavedMaskChanges: true });
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: img(), '/api/v1/segmentation/seg-1/nifti': msk() });
    render(<ImageViewer3D patientName="A" />);
    await loaded('volume', 2);
    expect(await screen.findByTestId('niivue-3d-unsaved-edits')).toHaveTextContent(/unsaved edits/i);
    useSegmentationStore.setState({ hasUnsavedMaskChanges: false });
  });

  it('rc073 R4: an identity-transform mask is drawn when the image\'s own transform is the identity too', async () => {
    const ID = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]];
    scene('volume', { segmentation_id: 'seg-1' });
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: img(ID), '/api/v1/segmentation/seg-1/nifti': msk({ affine: ID }) });
    render(<ImageViewer3D patientName="A" />);
    await loaded('volume', 2);
    expect(screen.queryByTestId('niivue-3d-mask-not-shown')).toBeNull();
  });

  for (const mode of ['volume', 'multiplanar'] as const) {
    it(`rc073 R7: 3D ${mode}: niivue's view-type and clip-plane keys are off`, async () => {
      scene(mode, null);
      installBrowserNetwork('http://127.0.0.1:4173', { [`/api/v1/imaging/nifti/${FILE}`]: img() });
      render(<ImageViewer3D patientName="A" />);
      await loaded(mode, 1);
      for (const nv of harness.instances) {
        expect([nv.opts.viewModeHotKey, nv.opts.clipPlaneHotKey, nv.opts.cycleClipPlaneHotKey]).toEqual(['', '', '']);
      }
    });
  }

  it('rc074 m2: the later-visit mask is drawn in a saturated colour, not white', async () => {
    scene('volume', null, true);
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: img(),
      '/api/v1/segmentation/tp1/nifti': msk(), '/api/v1/segmentation/tp2/nifti': msk() });
    render(<ImageViewer3D patientName="A" />);
    await loaded('volume', 3);
    const { cmapper } = await vi.importActual<typeof import('@niivue/niivue')>('@niivue/niivue');
    const tp2 = harness.instances[0].volumes[2];
    const lut = cmapper.colormap(tp2.colormap) as Uint8ClampedArray;
    const top = Array.from(lut.slice(255 * 4, 255 * 4 + 3));
    expect(top).not.toEqual([255, 255, 255]);
    expect(Math.max(...top) - Math.min(...top)).toBeGreaterThan(100);
  });

  it('rc076 m6: 3D colours a region-classified mask with the shared region mapping', async () => {
    scene('volume', { segmentation_id: 'seg-1', metadata: { labels: [
      { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true },
      { id: 2, name: 'Juxtacortical', color: '#00CC00', opacity: 0.6, visible: true },
      { id: 3, name: 'Infratentorial', color: '#0066FF', opacity: 0.6, visible: true },
      { id: 4, name: 'Deep White Matter', color: '#FFD700', opacity: 0.6, visible: true },
    ] } });
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: img(), '/api/v1/segmentation/seg-1/nifti': msk({ labels: [1, 2, 3, 4] }) });
    render(<ImageViewer3D patientName="A" />);
    await loaded('volume', 2);
    const vol = harness.instances[0].volumes[1];
    expect([1, 2, 3, 4].map((v) => drawnHex(vol, v))).toEqual(LEGEND);
  });
});
