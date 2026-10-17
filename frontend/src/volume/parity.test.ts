/**
 * PARITY: browser rendering vs the REAL server rendering path.
 *
 * Fixture produced by scripts/viewer/build_parity_fixture.py, which runs each
 * synthetic NIfTI through the backend's own `ImagingService.load_nifti` +
 * `process_image` and records the decoded PNG pixels, the metadata, and nibabel's
 * affine / axis codes / scaled values. Every case is asymmetric (n0 ≠ n1 ≠ n2 and
 * voxel values encode (i, j, k)), so a transposed or flipped client slice fails.
 *
 * Negative control: swap rows/cols in volumeStrides, drop the scl_slope, or skip
 * the big-endian swap in nifti.ts — these tests must fail.
 */
import { describe, it, expect } from 'vitest';
import fixture from './__fixtures__/parity-cases.json';
import { readNifti, valueAt } from './nifti';
import { axisCodesFromAffine, describeOrientation } from './orientation';
import { buildClientVolume, checkClientVolume } from './clientVolume';
import { buildVoxelViews } from './sliceGeometry';
import { computeStats, parityUint8Slice } from './windowing';

interface Case {
  name: string;
  gzipped: boolean;
  nifti_b64: string;
  shape: number[];
  server_metadata: {
    rows: number; columns: number; slices: number;
    pixel_spacing: number[]; slice_thickness: number;
    anatomical_orientation: string;
  };
  server_total_slices: number;
  server_slices_uint8_b64: string[];
  nibabel_axcodes: string[] | null;
  nibabel_affine: number[][];
  nibabel_zooms: number[];
  scaled_min: number;
  scaled_max: number;
  probe_voxels: { ijk: [number, number, number]; value: number }[];
}

const cases = (fixture as unknown as { cases: Case[] }).cases;

function bytesOf(b64: string): ArrayBuffer {
  const buf = Buffer.from(b64, 'base64');
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
}

describe('client NIfTI reading matches nibabel / the server', () => {
  it('fixture covers the risky encodings', () => {
    const names = cases.map((c) => c.name).join(' ');
    for (const needle of ['scaled', 'gz', 'qform_only', 'oblique', 'bigendian', 'singular', 'exclusion', 'uint16', 'int8']) {
      expect(names).toContain(needle);
    }
  });

  for (const c of cases) {
    describe(c.name, () => {
      it('grid, spacing and scaled values', async () => {
        const vol = await readNifti(bytesOf(c.nifti_b64));
        expect([...vol.dims]).toEqual(c.shape.slice(0, 3));
        vol.zooms.forEach((z, i) => expect(z).toBeCloseTo(c.nibabel_zooms[i], 5));
        for (const p of c.probe_voxels) {
          expect(valueAt(vol, ...p.ijk)).toBeCloseTo(p.value, 9);
        }
        const stats = computeStats(vol);
        expect(stats.min).toBeCloseTo(c.scaled_min, 9);
        expect(stats.max).toBeCloseTo(c.scaled_max, 9);
      });

      it('affine (sform/qform precedence) equals nibabel', async () => {
        const vol = await readNifti(bytesOf(c.nifti_b64));
        for (let r = 0; r < 4; r++) for (let col = 0; col < 4; col++) {
          expect(vol.affine[r][col]).toBeCloseTo(c.nibabel_affine[r][col], 4);
        }
      });

      it('rc023 orientation codes equal the server (never guessed)', async () => {
        const vol = await readNifti(bytesOf(c.nifti_b64));
        const codes = axisCodesFromAffine(vol.affine);
        expect(codes).toEqual(c.nibabel_axcodes);
        expect(describeOrientation(codes)).toBe(c.server_metadata.anatomical_orientation);
      });

      it('every server PNG slice is reproduced pixel-for-pixel (voxel view)', async () => {
        const cv = await buildClientVolume(c.name, bytesOf(c.nifti_b64));
        const view = buildVoxelViews(cv.nifti.dims, cv.nifti.zooms).axial;
        expect(view.rows).toBe(c.server_metadata.rows);
        expect(view.cols).toBe(c.server_metadata.columns);
        expect(view.depth).toBe(c.server_total_slices);
        c.server_slices_uint8_b64.forEach((b64, k) => {
          const expected = new Uint8Array(bytesOf(b64));
          const got = parityUint8Slice(cv.nifti, view, k, cv.stats);
          expect(Buffer.from(got).equals(Buffer.from(expected))).toBe(true);
        });
      });

      it('agrees with the server metadata (fail-closed check passes)', async () => {
        const cv = await buildClientVolume(c.name, bytesOf(c.nifti_b64));
        const check = checkClientVolume(cv, c.server_metadata);
        expect(check.problems).toEqual([]);
        expect(check.renderable).toBe(true);
        // Anatomical views only when the orientation is determinate.
        expect(check.anatomical).toBe(c.nibabel_axcodes !== null);
      });
    });
  }
});

describe('fail-closed agreement check', () => {
  const base = cases[0];
  it('refuses client rendering when the grid disagrees with the server', async () => {
    const cv = await buildClientVolume('x', bytesOf(base.nifti_b64));
    const check = checkClientVolume(cv, { ...base.server_metadata, rows: base.server_metadata.rows + 1 });
    expect(check.renderable).toBe(false);
  });

  it('refuses client rendering when the voxel spacing disagrees (measurements)', async () => {
    const cv = await buildClientVolume('x', bytesOf(base.nifti_b64));
    const check = checkClientVolume(cv, { ...base.server_metadata, pixel_spacing: [2, 2] });
    expect(check.renderable).toBe(false);
  });

  it('rc023 drops anatomical views when server and browser orientations disagree', async () => {
    const cv = await buildClientVolume('x', bytesOf(base.nifti_b64));
    const check = checkClientVolume(cv, { ...base.server_metadata, anatomical_orientation: 'RAS' });
    expect(check.renderable).toBe(true);
    expect(check.anatomical).toBe(false);
  });

  it('rc023 drops anatomical views when the server orientation is missing', async () => {
    const cv = await buildClientVolume('x', bytesOf(base.nifti_b64));
    const { anatomical_orientation: _omit, ...rest } = base.server_metadata;
    void _omit;
    expect(checkClientVolume(cv, rest).anatomical).toBe(false);
  });
});
