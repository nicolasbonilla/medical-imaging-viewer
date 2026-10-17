/**
 * PARITY on a REAL public MS case (open_ms_data patient01, CC-BY): every slice the
 * server's ImagingService renders as PNG is reproduced pixel-for-pixel by the browser,
 * for the FLAIR and the T1 (182 slices each); the browser's grid, spacing and
 * orientation agree with the server metadata; and the expert lesion mask lands on the
 * same voxels through the anatomical views.
 *
 * Fixtures are LOCAL and gitignored (scripts/viewer/build_demo_fixtures.py); when they
 * are absent (CI) this file is skipped — the committed synthetic parity test
 * (parity.test.ts) still runs everywhere.
 */
import { describe, it, expect } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { buildClientVolume, checkClientVolume, viewsFor } from './clientVolume';
import { buildVoxelViews, voxelOf } from './sliceGeometry';
import { parityUint8Slice } from './windowing';
import { gatherPlane, maskIndex, resolveMaskGrid } from './maskPlane';

const DIR = join(__dirname, '..', '..', '.dev-data', 'viewer-demo');
const HAVE = existsSync(join(DIR, 'server-slices-flair.u8'));

function ab(path: string): ArrayBuffer {
  const b = readFileSync(path);
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
}

describe.skipIf(!HAVE)('real public case — browser vs server rendering', () => {
  for (const key of ['flair', 't1']) {
    it(`${key}: all slices identical to the server PNGs, metadata agrees`, async () => {
      const vol = await buildClientVolume(key, ab(join(DIR, `${key}.nii.gz`)));
      const meta = JSON.parse(readFileSync(join(DIR, `metadata-${key}.json`), 'utf8')).metadata;
      const check = checkClientVolume(vol, meta);
      expect(check.problems).toEqual([]);
      expect(check.renderable).toBe(true);
      expect(check.anatomical).toBe(true);
      expect(vol.orientation).toBe(meta.anatomical_orientation);

      const server = new Uint8Array(ab(join(DIR, `server-slices-${key}.u8`)));
      const view = buildVoxelViews(vol.nifti.dims, vol.nifti.zooms).axial;
      const n = view.rows * view.cols;
      expect(server.length).toBe(n * view.depth);
      let mismatches = 0;
      for (let k = 0; k < view.depth; k++) {
        const got = parityUint8Slice(vol.nifti, view, k, vol.stats);
        const want = server.subarray(k * n, (k + 1) * n);
        for (let p = 0; p < n; p++) if (got[p] !== want[p]) mismatches++;
      }
      expect(mismatches).toBe(0);
    }, 120_000);
  }

  it('expert mask voxels coincide with image voxels in all three anatomical planes', async () => {
    const vol = await buildClientVolume('flair', ab(join(DIR, 'flair.nii.gz')));
    const bin = new Uint8Array(ab(join(DIR, 'mask-gold.bin')));
    const dv = new DataView(bin.buffer, bin.byteOffset, 12);
    const dims = { depth: dv.getUint32(0, true), height: dv.getUint32(4, true), width: dv.getUint32(8, true) };
    const mask = bin.subarray(12);
    const grid = resolveMaskGrid(dims, vol.nifti.dims)!;
    expect(grid.layout).toBe('kij');
    const gold = await buildClientVolume('gold', ab(join(DIR, 'gold.nii.gz')));
    const views = viewsFor(vol, true);
    let checked = 0;
    for (const v of Object.values(views)) {
      for (const s of [Math.floor(v.depth / 3), Math.floor(v.depth / 2)]) {
        const plane = gatherPlane(mask, grid, v, s);
        for (let r = 0; r < v.rows; r += 3) {
          for (let c = 0; c < v.cols; c += 3) {
            const [i, j, k] = voxelOf(v, s, r, c);
            // the internal mask, displayed at (r, c), equals the expert NIfTI at that voxel
            const g = gold.nifti.raw[i + gold.nifti.dims[0] * (j + gold.nifti.dims[1] * k)];
            expect(plane[r * v.cols + c]).toBe(g);
            expect(mask[maskIndex(grid, i, j, k)]).toBe(g);
            checked++;
          }
        }
      }
    }
    expect(checked).toBeGreaterThan(10_000);
  }, 120_000);
});
