/**
 * 3D lesion box corners must name the SAME voxels as the 2D viewer.
 * The backend reports the box on the internal (k, a0, a1) mask (z, y, x) — the NIfTI
 * voxel of a corner is (i, j, k) = (y, x, z). Before v3 the 3D box used (x, y, z),
 * transposing it in-plane. Asymmetric box + LAS-like affine so a swap is visible.
 */
import { describe, it, expect, vi } from 'vitest';

vi.mock('@niivue/niivue', () => ({ NVMeshUtilities: {} }));

import { voxelCornersToMM } from './boundingBoxMesh';
import { maskZYXToVoxel } from '@/volume/maskPlane';
import { voxelToWorld } from '@/volume/nifti';

const AFFINE = [
  [-1, 0, 0, 90],
  [0, 1.2, 0, -126],
  [0, 0, 3, -72],
  [0, 0, 0, 1],
];
const BOX = { x_min: 40, x_max: 44, y_min: 10, y_max: 12, z_min: 5, z_max: 6 };

describe('voxelCornersToMM (3D lesion box)', () => {
  it('corner 0 is the voxel the 2D viewer names for (z_min, y_min, x_min)', () => {
    const corners = voxelCornersToMM(BOX, AFFINE);
    const v = maskZYXToVoxel({ layout: 'kij', dims: [182, 218, 182] }, BOX.z_min, BOX.y_min, BOX.x_min);
    expect(v).toEqual([10, 40, 5]);
    expect(corners[0]).toEqual(voxelToWorld(AFFINE, ...v));
  });

  it('keeps the corner bit layout (bit0 = x, bit1 = y, bit2 = z) used by the edge table', () => {
    const c = voxelCornersToMM(BOX, AFFINE);
    const w = (z: number, y: number, x: number) => voxelToWorld(AFFINE, y, x, z);
    expect(c[1]).toEqual(w(BOX.z_min, BOX.y_min, BOX.x_max));
    expect(c[2]).toEqual(w(BOX.z_min, BOX.y_max, BOX.x_min));
    expect(c[7]).toEqual(w(BOX.z_max, BOX.y_max, BOX.x_max));
  });

  it('would fail for the old (x, y, z) construction (negative control, inline)', () => {
    const old = voxelToWorld(AFFINE, BOX.x_min, BOX.y_min, BOX.z_min);
    expect(voxelCornersToMM(BOX, AFFINE)[0]).not.toEqual(old);
  });
});
