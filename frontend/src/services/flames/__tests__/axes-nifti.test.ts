// @vitest-environment node
/**
 * HAZ-006 (orientation) controls for the in-browser FLAMeS path.
 *
 * The expected arrays come from research/flames_in_browser/make_fixtures.py: NIfTI files written
 * by nibabel and read back by SimpleITK exactly as nnU-Net's SimpleITKIO does, then
 * transpose_forward [2, 0, 1]. The app-order expectation is the backend's RC-031 convention
 * m = nib_data.transpose(2, 0, 1).
 */
import { describe, expect, it } from 'vitest';
import fx from './fixtures/nnunet_reference.json';
import {
  appShape,
  networkShape,
  networkSpacing,
  networkToApp,
  networkToNifti,
  niftiToApp,
  niftiToNetwork,
  type Dims3,
} from '../axes';
import { parseNifti, readNifti } from '../nifti';

const b64 = (s: string) => Uint8Array.from(Buffer.from(s, 'base64'));

function expectClose(actual: ArrayLike<number>, expected: number[], tol = 1e-5) {
  expect(actual.length).toBe(expected.length);
  let worst = 0;
  for (let i = 0; i < expected.length; i++) worst = Math.max(worst, Math.abs(actual[i] - expected[i]));
  expect(worst).toBeLessThanOrEqual(tol);
}

/** asymmetric synthetic volume: value encodes (i, j, k) uniquely */
function synthetic(dims: Dims3): Float32Array {
  const [nx, ny, nz] = dims;
  const out = new Float32Array(nx * ny * nz);
  for (let k = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) out[i + nx * (j + ny * k)] = i + 100 * j + 10000 * k;
  return out;
}

describe('axis order conversions (synthetic, asymmetric)', () => {
  const dims: Dims3 = [3, 4, 5];
  const data = synthetic(dims);

  it('rc042 network order is (i, k, j) C-order', () => {
    const net = niftiToNetwork(data, dims);
    const [s0, s1, s2] = networkShape(dims);
    expect([s0, s1, s2]).toEqual([3, 5, 4]);
    for (let i = 0; i < 3; i++) for (let k = 0; k < 5; k++) for (let j = 0; j < 4; j++) {
      expect(net[(i * s1 + k) * s2 + j]).toBe(i + 100 * j + 10000 * k);
    }
  });

  it('rc042 app order is (k, i, j) C-order = RC-031 transpose(2, 0, 1)', () => {
    const app = niftiToApp(data, dims);
    const { depth, height, width } = appShape(dims);
    expect([depth, height, width]).toEqual([5, 3, 4]);
    for (let k = 0; k < depth; k++) for (let i = 0; i < height; i++) for (let j = 0; j < width; j++) {
      // useSegmentationMask index: sliceIndex * H * W + row * W + col
      expect(app[k * height * width + i * width + j]).toBe(i + 100 * j + 10000 * k);
    }
  });

  it('round trips and network->app equals nifti->app', () => {
    const net = niftiToNetwork(data, dims);
    expect(Array.from(networkToNifti(net, dims))).toEqual(Array.from(data));
    expect(Array.from(networkToApp(net, dims))).toEqual(Array.from(niftiToApp(data, dims)));
    const u8 = Uint8Array.from(data, (v) => v % 7);
    expect(Array.from(networkToNifti(niftiToNetwork(u8, dims), dims))).toEqual(Array.from(u8));
  });

  it('network spacing is (sx, sz, sy) — target 1 mm axis is NIfTI i', () => {
    expect(networkSpacing([0.5, 0.6, 3])).toEqual([0.5, 3, 0.6]);
  });
});

describe('readNifti against nibabel + SimpleITK (fixtures)', () => {
  for (const c of (fx as any).nifti_axes as any[]) {
    it(`${c.name}: voxels, geometry and axis order match nnU-Net's reader`, async () => {
      const vol = await readNifti(b64(c.bytes_b64));
      expect(vol.dims).toEqual(c.dims);
      expectClose(vol.spacing, c.zooms, 1e-6);
      expectClose(vol.data, c.expected_nifti_order, 1e-4);
      for (let r = 0; r < 4; r++) expectClose(vol.affine[r], c.expected_affine[r], 1e-4);
      const net = niftiToNetwork(vol.data, vol.dims);
      expect(networkShape(vol.dims)).toEqual(c.expected_network_shape);
      expectClose(net, c.expected_network, 1e-4);
      expectClose(networkSpacing(vol.spacing), c.expected_network_spacing, 1e-5);
      expectClose(niftiToApp(vol.data, vol.dims), c.expected_app_order, 1e-4);
    });
  }
});

describe('readNifti fails closed', () => {
  const header = () => {
    const buf = new Uint8Array(352 + 4 * 8);
    const v = new DataView(buf.buffer);
    v.setInt32(0, 348, true);
    [3, 2, 2, 2, 1, 1, 1, 1].forEach((d, n) => v.setInt16(40 + 2 * n, d, true));
    v.setInt16(70, 16, true);
    v.setInt16(72, 32, true);
    [1, 1, 1, 1].forEach((p, n) => v.setFloat32(76 + 4 * n, p, true));
    v.setFloat32(108, 352, true);
    buf.set([0x6e, 0x2b, 0x31, 0], 344);
    return { buf, v };
  };

  it('parses a minimal valid header', () => {
    const { buf } = header();
    const vol = parseNifti(buf);
    expect(vol.dims).toEqual([2, 2, 2]);
    expect(vol.data.length).toBe(8);
  });

  it('rejects NIfTI-2, 4D, truncated, NaN and unsupported datatypes', () => {
    const n2 = header();
    n2.v.setInt32(0, 540, true);
    expect(() => parseNifti(n2.buf)).toThrow(/NIfTI-2/);
    const d4 = header();
    d4.v.setInt16(40, 4, true);
    d4.v.setInt16(48, 3, true);
    expect(() => parseNifti(d4.buf)).toThrow(/single 3D volume/);
    const tr = header();
    expect(() => parseNifti(tr.buf.subarray(0, 360))).toThrow(/Truncated/);
    const dt = header();
    dt.v.setInt16(70, 128, true);
    expect(() => parseNifti(dt.buf)).toThrow(/datatype/);
    const nan = header();
    nan.v.setFloat32(352, Number.NaN, true);
    expect(() => parseNifti(nan.buf)).toThrow(/non-finite/);
    const sp = header();
    sp.v.setFloat32(80, 0, true);
    expect(() => parseNifti(sp.buf)).toThrow(/spacing/);
  });
});
