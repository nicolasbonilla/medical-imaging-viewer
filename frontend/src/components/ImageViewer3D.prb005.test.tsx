/**
 * The 3D view (volume and multiplanar) on a hospital host name, and its mask colours.
 *
 *   PRB-005: the 3D view failed with "Cannot read properties of undefined (reading 'toUpperCase')"
 *          when the page was served from a host name without a dot (localhost, an intranet server
 *          name): niivue derives the file type from the blob URL, and a dot-less origin gives none.
 *   PRB-006: every mask overlay (lesion mask, earlier and later visit) was coloured with the display
 *          range its header copied from the MRI: the whole volume was tinted (a "red fog") and the
 *          lesions were nearly invisible. Required: background 0 transparent, any label >= 1 in full
 *          colour, whatever the header says.
 *
 * niivue's renderer is replaced (jsdom has no WebGL); its loaders, parser and display-range logic
 * are real (src/test/niivueHarness.ts).
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('@niivue/niivue', async (orig) =>
  (await import('@/test/niivueHarness')).harnessModule(await orig()));

import ImageViewer3D from './ImageViewer3D';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { harness, installBrowserNetwork } from '@/test/niivueHarness';
import { syntheticNifti, voxelIndex, LAS_AFFINE } from '@/test/syntheticNifti';

const FILE = 'patients/p/studies/s/series/se/flair.nii.gz';
const DIMS: [number, number, number] = [6, 8, 5];

const img = () => syntheticNifti({ dims: DIMS, affine: LAS_AFFINE, calMin: -15.5, calMax: 189.2, gzip: true,
  data: Uint8Array.from({ length: DIMS[0] * DIMS[1] * DIMS[2] }, (_, n) => (n * 7) % 251) });
const msk = () => {
  const data = new Uint8Array(DIMS[0] * DIMS[1] * DIMS[2]);
  data[voxelIndex(DIMS, 1, 2, 3)] = 1;
  return syntheticNifti({ dims: DIMS, affine: LAS_AFFINE, data, calMin: -15.5, calMax: 189.2,
    descrip: 'RC031-ORIENT-V2', gzip: true });
};
const ROUTES = () => ({
  [`/api/v1/imaging/nifti/${FILE}`]: img(),
  '/api/v1/segmentation/seg-0001/nifti': msk(),
  '/api/v1/segmentation/seg-tp1/nifti': msk(),
  '/api/v1/segmentation/seg-tp2/nifti': msk(),
});

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

function setScene(mode: 'volume' | 'multiplanar', longitudinal = false) {
  useViewerStore.setState({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    currentSeries: {
      id: 's1', name: 'FLAIR', format: 'nifti', total_slices: DIMS[2], file_id: FILE,
      metadata: { rows: DIMS[0], columns: DIMS[1], slices: DIMS[2], anatomical_orientation: 'LAS' },
    } as any,
    render3DMode: mode,
  });
  useSegmentationStore.setState({
    selectedLesion: null,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    currentSegmentation: { segmentation_id: 'seg-0001' } as any,
    zoneMapSegId: null,
    longitudinalTp1SegId: longitudinal ? 'seg-tp1' : null,
    longitudinalTp2SegId: longitudinal ? 'seg-tp2' : null,
    longitudinalVisible: longitudinal,
  });
}

async function loaded(mode: 'volume' | 'multiplanar', volumesEach: number) {
  const want = mode === 'volume' ? 1 : 4;
  await waitFor(() => {
    expect(harness.instances.length).toBe(want);
    for (const inst of harness.instances) expect(inst.volumes.length).toBe(volumesEach);
  }, { timeout: 8000 });
}

describe('PRB-005 — the 3D view on a host name without a dot', () => {
  for (const origin of ['http://localhost:4173', 'http://mstool-viewer']) {
    for (const mode of ['volume', 'multiplanar'] as const) {
      it(`prb005 3D ${mode}: image and mask load on ${origin}`, async () => {
        setScene(mode);
        installBrowserNetwork(origin, ROUTES());
        render(<ImageViewer3D patientName="Ana Torres" />);
        await loaded(mode, 2);
        expect(screen.queryByText(/toUpperCase/)).not.toBeInTheDocument();
      });
    }
  }
});

describe('PRB-006 — 3D mask colours do not depend on the display range in the mask header', () => {
  for (const mode of ['volume', 'multiplanar'] as const) {
    it(`rc074 3D ${mode}: lesion mask and both visit masks — 0 transparent, labels >= 1 full colour`, async () => {
      setScene(mode, true);
      installBrowserNetwork('http://127.0.0.1:4173', ROUTES());
      render(<ImageViewer3D patientName="Ana Torres" />);
      await loaded(mode, 4); // image + lesion mask + earlier visit + later visit
      // Precondition on the fixture: read as stored, the mask's header carries the MRI's window.
      const { NVImage } = await vi.importActual<typeof import('@niivue/niivue')>('@niivue/niivue');
      const asStored = await NVImage.loadFromUrl({ url: 'm.nii', name: 'm.nii', buffer: msk() });
      expect(asStored.cal_min).toBeCloseTo(-15.5, 3);
      for (const inst of harness.instances) {
        for (const overlay of inst.volumes.slice(1)) {
          expect(0).toBeLessThanOrEqual(overlay.cal_min);
          expect(1).toBeGreaterThanOrEqual(overlay.cal_max);
          expect(overlay.cal_max).toBeGreaterThan(overlay.cal_min);
        }
      }
    });
  }
});
