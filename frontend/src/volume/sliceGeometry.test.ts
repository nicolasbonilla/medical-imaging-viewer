/**
 * Slice geometry: the single screen<->voxel mapping shared by image and overlays.
 *
 * Asymmetric grid (5 x 7 x 3) so any transposition changes the shape; a
 * "laterality phantom" (markers placed by WORLD direction through the affine)
 * checks that the anatomical views put Anterior / Superior / patient-Right where the
 * display convention says, for several affines including permuted and oblique ones.
 * Laterality is still never LABELLED (RC-023) — this pins where pixels go.
 */
import { describe, it, expect } from 'vitest';
import {
  buildAnatomicalViews, buildVoxelViews, displayOf, voxelOf, volumeStrides, PLANES,
  type SliceView,
} from './sliceGeometry';
import { axisCodesFromAffine, codeAxis } from './orientation';
import type { Mat4 } from './nifti';

const DIMS = [5, 7, 3] as const;
const SPACING = [0.9, 1.1, 3.0] as const;

function allViews(): SliceView[] {
  const views: SliceView[] = Object.values(buildVoxelViews(DIMS, SPACING));
  for (const codes of [['R', 'A', 'S'], ['L', 'A', 'S'], ['P', 'S', 'L'], ['A', 'L', 'S'], ['L', 'P', 'I']] as const) {
    for (const conv of ['neurological', 'radiological'] as const) {
      views.push(...Object.values(buildAnatomicalViews(DIMS, SPACING, [...codes], conv)));
    }
  }
  return views;
}

describe('voxelOf / displayOf are exact inverses on an asymmetric grid', () => {
  it('for every view, slice and pixel', () => {
    for (const v of allViews()) {
      expect(new Set([v.normal, v.row, v.col]).size).toBe(3);
      expect([v.rows, v.cols, v.depth]).toEqual([DIMS[v.row], DIMS[v.col], DIMS[v.normal]]);
      const seen = new Set<string>();
      for (let s = 0; s < v.depth; s++) for (let r = 0; r < v.rows; r++) for (let c = 0; c < v.cols; c++) {
        const ijk = voxelOf(v, s, r, c);
        ijk.forEach((x, a) => { expect(x).toBeGreaterThanOrEqual(0); expect(x).toBeLessThan(DIMS[a]); });
        expect(displayOf(v, ijk)).toEqual({ slice: s, r, c });
        seen.add(ijk.join(','));
      }
      // A bijection: every voxel shown exactly once across the stack.
      expect(seen.size).toBe(DIMS[0] * DIMS[1] * DIMS[2]);
    }
  });

  it('volumeStrides walks exactly the voxels voxelOf names', () => {
    for (const v of allViews()) {
      for (let s = 0; s < v.depth; s++) {
        const { base, rowStep, colStep } = volumeStrides(v, DIMS, s);
        for (let r = 0; r < v.rows; r++) for (let c = 0; c < v.cols; c++) {
          const [i, j, k] = voxelOf(v, s, r, c);
          expect(base + r * rowStep + c * colStep).toBe(i + DIMS[0] * (j + DIMS[1] * k));
        }
      }
    }
  });

  it('the voxel "axial" view is the legacy server layout: rows = axis 0, cols = axis 1, no flip', () => {
    const v = buildVoxelViews(DIMS, SPACING).axial;
    expect([v.normal, v.row, v.col, v.rowFlip, v.colFlip]).toEqual([2, 0, 1, false, false]);
    expect(voxelOf(v, 2, 3, 6)).toEqual([3, 6, 2]);
    expect(v.anatomical).toBe(false);
  });

  it('carries physical spacing per displayed axis (measurements / aspect)', () => {
    for (const v of allViews()) {
      expect(v.rowSpacing).toBe(SPACING[v.row]);
      expect(v.colSpacing).toBe(SPACING[v.col]);
      expect(v.sliceSpacing).toBe(SPACING[v.normal]);
    }
  });
});

// ---------------------------------------------------------------------------
// Laterality phantom
// ---------------------------------------------------------------------------

function rotZ(deg: number): number[][] {
  const t = (deg * Math.PI) / 180;
  return [[Math.cos(t), -Math.sin(t), 0], [Math.sin(t), Math.cos(t), 0], [0, 0, 1]];
}
function affineFrom(m: number[][]): Mat4 {
  return [[...m[0], 0], [...m[1], 0], [...m[2], 0], [0, 0, 0, 1]];
}

const AFFINES: Record<string, Mat4> = {
  RAS: affineFrom([[1, 0, 0], [0, 1, 0], [0, 0, 1]]),
  LAS: affineFrom([[-1, 0, 0], [0, 1, 0], [0, 0, 1]]),
  LPS: affineFrom([[-1, 0, 0], [0, -1, 0], [0, 0, 1]]),
  PSL: affineFrom([[0, 0, -1.2], [-0.8, 0, 0], [0, 1.5, 0]]),
  oblique50: affineFrom(rotZ(50)),
  sagittalAcq: affineFrom([[0, 0, 1], [1, 0, 0], [0, 1, 0]]), // i->A, j->S, k->R (ASR)
};

/** Voxel at the extreme of a world direction (+1 R/A/S): the phantom marker. */
function extremeVoxel(codes: string[], world: 0 | 1 | 2, towards: 1 | -1): [number, number, number] {
  const ijk: [number, number, number] = [
    Math.floor(DIMS[0] / 2), Math.floor(DIMS[1] / 2), Math.floor(DIMS[2] / 2),
  ];
  codes.forEach((code, axis) => {
    const { world: w, sign } = codeAxis(code as never);
    if (w === world) ijk[axis] = sign === towards ? DIMS[axis] - 1 : 0;
  });
  return ijk;
}

describe('rc023 anatomical views place the laterality phantom by the affine (no labels)', () => {
  for (const [name, aff] of Object.entries(AFFINES)) {
    const codes = axisCodesFromAffine(aff)!;
    it(`${name} (${codes.join('')}) — neurological: patient Right on screen right, Anterior up`, () => {
      const v = buildAnatomicalViews(DIMS, SPACING, codes, 'neurological');
      const right = extremeVoxel(codes, 0, 1);
      const anterior = extremeVoxel(codes, 1, 1);
      const superior = extremeVoxel(codes, 2, 1);
      // axial: right edge = R, top = A
      expect(displayOf(v.axial, right).c).toBe(v.axial.cols - 1);
      expect(displayOf(v.axial, anterior).r).toBe(0);
      // coronal: right edge = R, top = S
      expect(displayOf(v.coronal, right).c).toBe(v.coronal.cols - 1);
      expect(displayOf(v.coronal, superior).r).toBe(0);
      // sagittal: top = S, right edge = A (niivue default "nose right")
      expect(displayOf(v.sagittal, superior).r).toBe(0);
      expect(displayOf(v.sagittal, anterior).c).toBe(v.sagittal.cols - 1);
      // normals: axial ⟂ S/I, coronal ⟂ A/P, sagittal ⟂ R/L
      expect(codeAxis(codes[v.axial.normal]).world).toBe(2);
      expect(codeAxis(codes[v.coronal.normal]).world).toBe(1);
      expect(codeAxis(codes[v.sagittal.normal]).world).toBe(0);
    });

    it(`${name} — radiological mirrors only left/right of axial and coronal`, () => {
      const neuro = buildAnatomicalViews(DIMS, SPACING, codes, 'neurological');
      const radio = buildAnatomicalViews(DIMS, SPACING, codes, 'radiological');
      const right = extremeVoxel(codes, 0, 1);
      expect(displayOf(radio.axial, right).c).toBe(0);
      expect(displayOf(radio.coronal, right).c).toBe(0);
      expect(radio.sagittal).toEqual(neuro.sagittal);
      expect(radio.axial.rowFlip).toBe(neuro.axial.rowFlip);
    });
  }

  it('every plane name maps to a distinct normal axis', () => {
    const v = buildAnatomicalViews(DIMS, SPACING, ['L', 'A', 'S']);
    expect(new Set(PLANES.map((p) => v[p].normal)).size).toBe(3);
  });
});
