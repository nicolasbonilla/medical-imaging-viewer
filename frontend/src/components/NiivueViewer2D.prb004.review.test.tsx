/**
 * PRB-004 — independent review of PR #71 (39f9d44): the W/L GPU view.
 *
 *   M1  the view asks for the mask aligned to the image it shows (`?ref_file_id=`), so a mask saved before
 *       RC-031 that lies on the image's grid is realigned by the server and drawn (was: refused, D-3);
 *   M2  a segmentation not saved yet, or unsaved edits, were silently missing from the view;
 *   m3  niivue's own keys (V view type, C clip plane, Ctrl+U/D slice, M drag mode) acted on the view and
 *       bypassed the store;
 *   m5  the "not drawn" notice sat at the top, where the identity block can cover it;
 *   m6  a region-classified mask was drawn all red; it is drawn in the label colours (regions: the shared
 *       mapping), and a label value missing from the table is still drawn;
 *   m9  the notice for a mask on another grid told the reader to use the Standard view.
 *
 * niivue's renderer replaced (jsdom has no WebGL), its loaders and math real (src/test/niivueHarness.ts).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('@niivue/niivue', async (orig) =>
  (await import('@/test/niivueHarness')).harnessModule(await orig()));

import { NiivueViewer2D } from './NiivueViewer2D';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { harness, installBrowserNetwork } from '@/test/niivueHarness';
import { syntheticNifti, voxelIndex, LAS_AFFINE } from '@/test/syntheticNifti';

const FILE = 'patients/p/studies/s/series/se/flair.nii.gz';
const SEG = 'seg-0001';
const DIMS: [number, number, number] = [6, 8, 5];
const LEGEND = ['#E69F00', '#56B4E9', '#009E73', '#D55E00'];
const STORED_REGION_LABELS = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
  { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true },
  { id: 2, name: 'Juxtacortical', color: '#00CC00', opacity: 0.6, visible: true },
  { id: 3, name: 'Infratentorial', color: '#0066FF', opacity: 0.6, visible: true },
  { id: 4, name: 'Deep White Matter', color: '#FFD700', opacity: 0.6, visible: true },
];

const image = () => syntheticNifti({ dims: DIMS, affine: LAS_AFFINE, gzip: true,
  data: Uint8Array.from({ length: DIMS[0] * DIMS[1] * DIMS[2] }, (_, n) => (n * 7) % 251) });
function mask(o: { dims?: [number, number, number]; descrip?: string; labels?: number[] } = {}) {
  const dims = o.dims ?? DIMS;
  const data = new Uint8Array(dims[0] * dims[1] * dims[2]);
  (o.labels ?? [1]).forEach((v, n) => { data[voxelIndex(dims, n % dims[0], 2, 3 % dims[2])] = v; });
  return syntheticNifti({ dims, affine: LAS_AFFINE, data, descrip: o.descrip ?? 'RC031-ORIENT-V2', gzip: true });
}

function setStores(segmentation: Record<string, unknown> | null) {
  useViewerStore.setState({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    currentSeries: { id: FILE, name: 'flair', format: 'nifti', file_id: FILE, total_slices: DIMS[2],
      metadata: { rows: DIMS[0], columns: DIMS[1], slices: DIMS[2] }, slices: [] } as any,
    currentSliceIndex: 2, windowCenter: 0, windowWidth: 0,
  });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useSegmentationStore.setState({ currentSegmentation: segmentation as any, isOverlayVisible: true, lesionOpacity: 0.6 });
}

async function mounted(wantVolumes: number) {
  await waitFor(() => {
    expect(harness.instances.length).toBeGreaterThan(0);
    expect(harness.instances[harness.instances.length - 1].volumes.length).toBe(wantVolumes);
  }, { timeout: 5000 });
  return harness.instances[harness.instances.length - 1];
}

beforeEach(() => harness.reset());
afterEach(() => vi.unstubAllGlobals());

const hex = (lut: ArrayLike<number>, min: number, v: number) =>
  `#${[0, 1, 2].map((c) => lut[(v - min) * 4 + c].toString(16).padStart(2, '0')).join('').toUpperCase()}`;

describe('PRB-004 review — W/L GPU view', () => {
  it('rc073 M1: the mask is requested aligned to the image the view shows (ref_file_id)', async () => {
    setStores({ segmentation_id: SEG });
    const net = installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: image(), [`/api/v1/segmentation/${SEG}/nifti`]: mask() });
    render(<NiivueViewer2D />);
    await mounted(2);
    expect(net.requests.some((u) => u.includes(`/api/v1/segmentation/${SEG}/nifti?ref_file_id=${encodeURIComponent(FILE)}`))).toBe(true);
  });

  it('rc073 M2: a segmentation not saved yet is not drawn here, and the view says so', async () => {
    setStores({ segmentation_id: 'local-1234' });
    installBrowserNetwork('http://127.0.0.1:4173', { [`/api/v1/imaging/nifti/${FILE}`]: image() });
    render(<NiivueViewer2D />);
    await mounted(1);
    expect(await screen.findByTestId('niivue-mask-not-shown')).toHaveTextContent(/not saved/i);
  });

  it('rc073 M2: with unsaved edits the saved mask is drawn and the view says the edits are not shown', async () => {
    setStores({ segmentation_id: SEG });
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: image(), [`/api/v1/segmentation/${SEG}/nifti`]: mask() });
    render(<NiivueViewer2D hasUnsavedEdits />);
    await mounted(2);
    expect(await screen.findByTestId('niivue-mask-not-shown')).toHaveTextContent(/unsaved/i);
  });

  it('rc073 m3: niivue keys never reach niivue, and its view-type / clip-plane hotkeys are off', async () => {
    setStores(null);
    installBrowserNetwork('http://127.0.0.1:4173', { [`/api/v1/imaging/nifti/${FILE}`]: image() });
    const { container } = render(<NiivueViewer2D />);
    const nv = await mounted(1);
    expect(nv.opts.viewModeHotKey).toBe('');
    expect(nv.opts.clipPlaneHotKey).toBe('');
    const canvas = container.querySelector('canvas')!;
    for (const code of ['KeyV', 'KeyC', 'KeyM', 'KeyU', 'KeyD']) {
      fireEvent.keyDown(canvas, { code, ctrlKey: code === 'KeyU' || code === 'KeyD' });
      fireEvent.keyUp(canvas, { code });
    }
    expect(harness.keysSeenByNiivue).toEqual([]);
  });

  it('rc073 m5: the notice is placed at the bottom of the view, clear of the identity block and orientation banner', async () => {
    setStores({ segmentation_id: 'local-1234' });
    installBrowserNetwork('http://127.0.0.1:4173', { [`/api/v1/imaging/nifti/${FILE}`]: image() });
    render(<NiivueViewer2D />);
    const notice = await screen.findByTestId('niivue-mask-not-shown');
    expect(notice.className).toMatch(/\bbottom-/);
    expect(notice.className).not.toMatch(/\btop-/);
  });

  it('rc073 m9: for a mask on another grid the notice does not send the reader to the Standard view', async () => {
    setStores({ segmentation_id: SEG });
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: image(), [`/api/v1/segmentation/${SEG}/nifti`]: mask({ dims: [6, 8, 4] }) });
    render(<NiivueViewer2D />);
    const notice = await screen.findByTestId('niivue-mask-not-shown');
    expect(notice).toHaveTextContent(/voxel grid/i);
    expect(notice).not.toHaveTextContent(/Standard/);
  });

  it('rc076 m6: a region-classified mask is coloured by region with the shared mapping; an unknown label value is still drawn', async () => {
    setStores({ segmentation_id: SEG, metadata: { labels: STORED_REGION_LABELS } });
    installBrowserNetwork('http://127.0.0.1:4173', {
      [`/api/v1/imaging/nifti/${FILE}`]: image(),
      [`/api/v1/segmentation/${SEG}/nifti`]: mask({ labels: [1, 2, 3, 4, 9] }) });
    render(<NiivueViewer2D />);
    const nv = await mounted(2);
    const cm = nv.volumes[1].colormapLabel as { lut: Uint8ClampedArray; min: number } | undefined;
    expect(cm).toBeDefined();
    expect([1, 2, 3, 4].map((v) => hex(cm!.lut, cm!.min, v))).toEqual(LEGEND);
    expect(cm!.lut[(9 - cm!.min) * 4 + 3]).toBeGreaterThan(0);
    expect(cm!.lut[(0 - cm!.min) * 4 + 3]).toBe(0);
  });
});
