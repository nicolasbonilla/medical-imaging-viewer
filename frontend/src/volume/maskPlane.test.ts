/**
 * Segmentation overlay stays VOXEL-ALIGNED with the image in all three planes —
 * reading AND painting AND undo — on an asymmetric synthetic volume + mask.
 *
 * Image voxel values and mask labels both encode the voxel (i, j, k), so the test
 * can ask, pixel by pixel, "is the mask pixel drawn here the label of the voxel the
 * image pixel here comes from?". A transposition, a flip, or a wrong layout breaks
 * that equality. Also proves the new path is bit-identical to the legacy 2D canvas
 * on the legacy (voxel axial) view, including the swapped-axes legacy masks.
 */
import { describe, it, expect } from 'vitest';
import { buildAnatomicalViews, buildVoxelViews, voxelOf, type SliceView } from './sliceGeometry';
import {
  brushOffsets, gatherPlane, maskIndex, maskZYXToVoxel, paintPlaneStroke, resolveMaskGrid, scatterPlane,
  type MaskGrid,
} from './maskPlane';
import { renderSliceRGBA } from './windowing';
import type { NiftiVolume } from './nifti';

const DIMS = [6, 9, 4] as const; // n0 ≠ n1 ≠ n2
const SPACING = [0.8, 1.2, 3.5] as const;
const [N0, N1, N2] = DIMS;

/** Label that encodes the voxel; collisions are impossible on this grid (216 < 256). */
const labelOf = (i: number, j: number, k: number) => 1 + ((i + N0 * (j + N1 * k)) % 255);

function syntheticVolume(): NiftiVolume {
  const raw = new Float32Array(N0 * N1 * N2);
  for (let k = 0; k < N2; k++) for (let j = 0; j < N1; j++) for (let i = 0; i < N0; i++) {
    raw[i + N0 * (j + N1 * k)] = labelOf(i, j, k); // grey value == label
  }
  return {
    version: 1, dims: [N0, N1, N2], volumes: 1, datatype: 16, littleEndian: true, raw,
    slope: 1, inter: 0, scaled: false, zooms: [...SPACING] as [number, number, number],
    qformCode: 0, sformCode: 1, affine: [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
    affineSource: 'sform', description: '',
  };
}

/** Internal (k, a0, a1) mask, or the legacy swapped (k, a1, a0). */
function syntheticMask(layout: 'kij' | 'kji'): Uint8Array {
  const m = new Uint8Array(N0 * N1 * N2);
  const grid: MaskGrid = { layout, dims: DIMS };
  for (let k = 0; k < N2; k++) for (let j = 0; j < N1; j++) for (let i = 0; i < N0; i++) {
    m[maskIndex(grid, i, j, k)] = labelOf(i, j, k);
  }
  return m;
}

function views(): SliceView[] {
  return [
    ...Object.values(buildVoxelViews(DIMS, SPACING)),
    ...Object.values(buildAnatomicalViews(DIMS, SPACING, ['L', 'A', 'S'], 'neurological')),
    ...Object.values(buildAnatomicalViews(DIMS, SPACING, ['P', 'S', 'L'], 'radiological')),
    ...Object.values(buildAnatomicalViews(DIMS, SPACING, ['A', 'L', 'S'], 'neurological')),
  ];
}

describe('resolveMaskGrid — the overlay is never stretched onto the wrong grid', () => {
  it('accepts the canonical (k, a0, a1) layout', () => {
    expect(resolveMaskGrid({ depth: N2, height: N0, width: N1 }, DIMS)?.layout).toBe('kij');
  });
  it('accepts the legacy swapped (k, a1, a0) layout (same rule as the legacy canvas)', () => {
    expect(resolveMaskGrid({ depth: N2, height: N1, width: N0 }, DIMS)?.layout).toBe('kji');
  });
  it('refuses a different depth, a different in-plane grid, or no mask', () => {
    expect(resolveMaskGrid({ depth: N2 + 1, height: N0, width: N1 }, DIMS)).toBeNull();
    expect(resolveMaskGrid({ depth: N2, height: N0, width: N1 + 1 }, DIMS)).toBeNull();
    expect(resolveMaskGrid(null, DIMS)).toBeNull();
  });
  it('square slices resolve to canonical (the swap is dimensionally invisible)', () => {
    expect(resolveMaskGrid({ depth: 3, height: 5, width: 5 }, [5, 5, 3])?.layout).toBe('kij');
  });
});

describe('mask pixels coincide with image pixels in every plane', () => {
  const vol = syntheticVolume();
  for (const layout of ['kij', 'kji'] as const) {
    it(`layout ${layout}: gathered label == image grey at every (r, c) of every slice`, () => {
      const mask = syntheticMask(layout);
      const grid = resolveMaskGrid(
        layout === 'kij' ? { depth: N2, height: N0, width: N1 } : { depth: N2, height: N1, width: N0 }, DIMS)!;
      const stats = { min: 0, max: 255, robustLow: 0, robustHigh: 255, histogram: new Uint32Array(256), finiteCount: 1, nonFiniteCount: 0 };
      for (const v of views()) {
        for (let s = 0; s < v.depth; s++) {
          const plane = gatherPlane(mask, grid, v, s);
          // Window 0..255 → grey level == stored value, so pixels are directly comparable.
          const rgba = renderSliceRGBA(vol, v, s, { center: 127.5, width: 255 }, stats);
          for (let p = 0; p < v.rows * v.cols; p++) expect(plane[p]).toBe(rgba[p * 4]);
        }
      }
    });
  }
});

describe('painting through a view lands on the voxel under the cursor (all planes)', () => {
  for (const layout of ['kij', 'kji'] as const) {
    it(`layout ${layout}: single-voxel dab at (r, c) sets exactly voxelOf(view, slice, r, c)`, () => {
      const grid: MaskGrid = { layout, dims: DIMS };
      for (const v of views()) {
        for (const [s, r, c] of [[0, 0, 0], [v.depth - 1, v.rows - 1, v.cols - 1], [1, 2, 3]] as const) {
          if (s >= v.depth || r >= v.rows || c >= v.cols) continue;
          const mask = new Uint8Array(N0 * N1 * N2);
          const n = paintPlaneStroke(mask, grid, { view: v, slice: s, r, c, brushSize: 1, brushShape: 'circle', value: 7 });
          expect(n).toBe(1);
          const [i, j, k] = voxelOf(v, s, r, c);
          expect(mask[maskIndex(grid, i, j, k)]).toBe(7);
          expect(mask.reduce((a, x) => a + (x ? 1 : 0), 0)).toBe(1);
          // ...and it is drawn back at the same display pixel.
          const plane = gatherPlane(mask, grid, v, s);
          expect(plane[r * v.cols + c]).toBe(7);
        }
      }
    });
  }

  it('a brush never leaks into another slice of the view', () => {
    const grid: MaskGrid = { layout: 'kij', dims: DIMS };
    for (const v of views()) {
      const mask = new Uint8Array(N0 * N1 * N2);
      paintPlaneStroke(mask, grid, { view: v, slice: 1, r: 2, c: 2, brushSize: 5, brushShape: 'circle', value: 3 });
      for (let s = 0; s < v.depth; s++) {
        const painted = gatherPlane(mask, grid, v, s).some((x) => x === 3);
        expect(painted).toBe(s === 1);
      }
    }
  });

  it('draw-over protection is honoured voxel by voxel', () => {
    const grid: MaskGrid = { layout: 'kij', dims: DIMS };
    const v = buildAnatomicalViews(DIMS, SPACING, ['L', 'A', 'S']).coronal;
    const mask = new Uint8Array(N0 * N1 * N2);
    const [i, j, k] = voxelOf(v, 2, 1, 1);
    mask[maskIndex(grid, i, j, k)] = 9; // another clinician's label
    paintPlaneStroke(mask, grid, { view: v, slice: 2, r: 1, c: 1, brushSize: 3, brushShape: 'square', value: 4, canOverwrite: (cur) => cur === 0 });
    expect(mask[maskIndex(grid, i, j, k)]).toBe(9);
    expect(gatherPlane(mask, grid, v, 2).filter((x) => x === 4).length).toBe(8);
  });

  it('undo snapshot (gather) + restore (scatter) is lossless in every plane', () => {
    const grid: MaskGrid = { layout: 'kji', dims: DIMS };
    for (const v of views()) {
      const mask = syntheticMask('kji');
      const before = Uint8Array.from(mask);
      const snap = gatherPlane(mask, grid, v, 1);
      paintPlaneStroke(mask, grid, { view: v, slice: 1, r: 1, c: 1, brushSize: 7, brushShape: 'circle', value: 0 });
      expect(Buffer.from(mask).equals(Buffer.from(before))).toBe(false);
      scatterPlane(mask, grid, v, 1, snap);
      expect(Buffer.from(mask).equals(Buffer.from(before))).toBe(true);
    }
  });
});

describe('bit-identical to the legacy 2D canvas on the legacy view', () => {
  const view = buildVoxelViews(DIMS, SPACING).axial;

  it('canonical mask: gatherPlane == the legacy subarray slice', () => {
    const mask = syntheticMask('kij');
    const grid: MaskGrid = { layout: 'kij', dims: DIMS };
    for (let k = 0; k < N2; k++) {
      const legacy = mask.subarray(k * N0 * N1, (k + 1) * N0 * N1);
      expect(Buffer.from(gatherPlane(mask, grid, view, k)).equals(Buffer.from(legacy))).toBe(true);
    }
  });

  it('swapped mask: gatherPlane == the legacy transposeSlice', () => {
    const mask = syntheticMask('kji');
    const grid: MaskGrid = { layout: 'kji', dims: DIMS };
    // legacy: src dims (height=n1, width=n0); dst[w*srcH + h] = src[h*srcW + w]
    for (let k = 0; k < N2; k++) {
      const src = mask.subarray(k * N0 * N1, (k + 1) * N0 * N1);
      const dst = new Uint8Array(src.length);
      for (let h = 0; h < N1; h++) for (let w = 0; w < N0; w++) dst[w * N1 + h] = src[h * N0 + w];
      expect(Buffer.from(gatherPlane(mask, grid, view, k)).equals(Buffer.from(dst))).toBe(true);
    }
  });

  it('circular brush == the legacy applyCircularBrush (x = column, y = row)', () => {
    const grid: MaskGrid = { layout: 'kij', dims: DIMS };
    for (const size of [1, 2, 3, 4, 5, 8]) {
      const mask = new Uint8Array(N0 * N1 * N2);
      paintPlaneStroke(mask, grid, { view, slice: 2, r: 3, c: 4, brushSize: size, brushShape: 'circle', value: 1 });
      const legacy = new Uint8Array(N0 * N1);
      const radius = Math.floor(size / 2);
      for (let dy = -radius; dy <= radius; dy++) for (let dx = -radius; dx <= radius; dx++) {
        if (dx * dx + dy * dy <= radius * radius) {
          const px = 4 + dx, py = 3 + dy;
          if (px >= 0 && px < N1 && py >= 0 && py < N0) legacy[py * N1 + px] = 1;
        }
      }
      expect(Buffer.from(mask.subarray(2 * N0 * N1, 3 * N0 * N1)).equals(Buffer.from(legacy))).toBe(true);
    }
  });

  it('square brush covers exactly the square the cursor outlines', () => {
    expect(brushOffsets(4, 'square').length).toBe(16);
    const rows = brushOffsets(4, 'square').map(([dr]) => dr);
    expect(Math.min(...rows)).toBe(-2);
    expect(Math.max(...rows)).toBe(1);
  });
});

describe('lesion coordinates (backend z, y, x) map to the right voxel', () => {
  it('canonical and swapped layouts', () => {
    expect(maskZYXToVoxel({ layout: 'kij', dims: DIMS }, 3, 4, 5)).toEqual([4, 5, 3]);
    expect(maskZYXToVoxel({ layout: 'kji', dims: DIMS }, 3, 4, 5)).toEqual([5, 4, 3]);
  });
  it('round-trips through maskIndex: the voxel a lesion names holds that lesion', () => {
    for (const layout of ['kij', 'kji'] as const) {
      const grid: MaskGrid = { layout, dims: DIMS };
      const mask = syntheticMask(layout);
      // Recover (z, y, x) of a stored index the way numpy argwhere would.
      const [hgt, wid] = layout === 'kij' ? [N0, N1] : [N1, N0];
      for (const idx of [0, 17, mask.length - 1]) {
        const z = Math.floor(idx / (hgt * wid)), y = Math.floor((idx % (hgt * wid)) / wid), x = idx % wid;
        const [i, j, k] = maskZYXToVoxel(grid, z, y, x);
        expect(mask[maskIndex(grid, i, j, k)]).toBe(mask[idx]);
        expect(maskIndex(grid, i, j, k)).toBe(idx);
      }
    }
  });
});
