/**
 * v3 client viewer — painting + undo/redo through useSegmentationMask in ALL THREE
 * planes, on an asymmetric mask (n0 ≠ n1 ≠ n2), interleaved with the legacy k-slice
 * path. Pins: a dab lands on voxelOf(view, slice, r, c); undo/redo are exact inverses
 * across planes in LIFO order; draw-over protection holds; a stale grid paints nothing.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const get = vi.fn();
vi.mock('@/services/apiClient', () => ({
  apiClient: { get: (...a: unknown[]) => get(...a), put: vi.fn() },
}));

import { useSegmentationMask } from './useSegmentationMask';
import { buildAnatomicalViews, buildVoxelViews, voxelOf, PLANES } from '@/volume/sliceGeometry';
import { maskIndex, type MaskGrid } from '@/volume/maskPlane';

const N0 = 6, N1 = 9, N2 = 4; // image grid (i, j, k); mask is (k, i, j) = (4, 6, 9)
const DIMS = [N0, N1, N2] as const;
const GRID: MaskGrid = { layout: 'kij', dims: DIMS };

function maskBuffer(seed: (idx: number) => number = () => 0): ArrayBuffer {
  const buf = new ArrayBuffer(12 + N0 * N1 * N2);
  const dv = new DataView(buf);
  dv.setUint32(0, N2, true); // depth
  dv.setUint32(4, N0, true); // height
  dv.setUint32(8, N1, true); // width
  const m = new Uint8Array(buf, 12);
  for (let i = 0; i < m.length; i++) m[i] = seed(i);
  return buf;
}

async function loaded(seed?: (idx: number) => number) {
  get.mockResolvedValue({ data: maskBuffer(seed), headers: {} });
  const hook = renderHook(() => useSegmentationMask());
  await act(async () => { await hook.result.current.loadMask('seg'); });
  return hook;
}

const anat = buildAnatomicalViews(DIMS, [1, 1.2, 3], ['L', 'A', 'S']);
const vox = buildVoxelViews(DIMS, [1, 1.2, 3]);
const ALL = [...PLANES.map((p) => anat[p]), ...PLANES.map((p) => vox[p])];

describe('useSegmentationMask — plane painting (all planes)', () => {
  beforeEach(() => get.mockReset());

  it('a 1-voxel dab sets exactly the voxel under the cursor, in every view', async () => {
    for (const view of ALL) {
      const { result } = await loaded();
      const [s, r, c] = [1, view.rows - 2, 1];
      act(() => {
        result.current.beginPlaneStroke(GRID, view, s);
        result.current.paintPlane({ grid: GRID, view, sliceIndex: s, r, c, brushSize: 1, brushShape: 'circle', labelId: 5, erase: false });
      });
      const mask = result.current.getMaskArray()!;
      const [i, j, k] = voxelOf(view, s, r, c);
      expect(mask[maskIndex(GRID, i, j, k)]).toBe(5);
      expect(mask.reduce((a, v) => a + (v ? 1 : 0), 0)).toBe(1);
      expect(result.current.state.isDirty).toBe(true);
    }
  });

  it('undo / redo are exact across planes, in LIFO order, interleaved with the legacy k-slice path', async () => {
    const { result } = await loaded((idx) => (idx % 7 === 0 ? 2 : 0));
    const original = Uint8Array.from(result.current.getMaskArray()!);
    const snapshots: Uint8Array[] = [];
    const strokes: Array<() => void> = [
      () => { result.current.beginPlaneStroke(GRID, anat.axial, 2); result.current.paintPlane({ grid: GRID, view: anat.axial, sliceIndex: 2, r: 3, c: 3, brushSize: 3, brushShape: 'square', labelId: 1, erase: false }); },
      () => { result.current.beginPlaneStroke(GRID, anat.sagittal, 4); result.current.paintPlane({ grid: GRID, view: anat.sagittal, sliceIndex: 4, r: 1, c: 5, brushSize: 5, brushShape: 'circle', labelId: 3, erase: false }); },
      () => { result.current.beginStroke(1); result.current.paintStroke({ x: 4, y: 2, sliceIndex: 1, brushSize: 3, labelId: 4, erase: false }); },
      () => { result.current.beginPlaneStroke(GRID, anat.coronal, 6); result.current.paintPlane({ grid: GRID, view: anat.coronal, sliceIndex: 6, r: 2, c: 2, brushSize: 3, brushShape: 'circle', labelId: 0, erase: true }); },
    ];
    for (const s of strokes) {
      snapshots.push(Uint8Array.from(result.current.getMaskArray()!));
      act(s);
    }
    const final = Uint8Array.from(result.current.getMaskArray()!);
    expect(Buffer.from(final).equals(Buffer.from(original))).toBe(false);

    for (let n = strokes.length - 1; n >= 0; n--) {
      act(() => { expect(result.current.undo()).toBe(true); });
      expect(Buffer.from(result.current.getMaskArray()!).equals(Buffer.from(snapshots[n]))).toBe(true);
    }
    expect(Buffer.from(result.current.getMaskArray()!).equals(Buffer.from(original))).toBe(true);

    for (let n = 0; n < strokes.length; n++) act(() => { result.current.redo(); });
    expect(Buffer.from(result.current.getMaskArray()!).equals(Buffer.from(final))).toBe(true);
  });

  it('draw-over "empty only" protects another label in a reformatted plane', async () => {
    const { result } = await loaded();
    const view = anat.coronal;
    const [i, j, k] = voxelOf(view, 3, 1, 4);
    result.current.getMaskArray()![maskIndex(GRID, i, j, k)] = 9;
    act(() => {
      result.current.beginPlaneStroke(GRID, view, 3);
      result.current.paintPlane({ grid: GRID, view, sliceIndex: 3, r: 1, c: 4, brushSize: 3, brushShape: 'square', labelId: 1, erase: false, drawOverMode: 'emptyOnly' });
    });
    expect(result.current.getMaskArray()![maskIndex(GRID, i, j, k)]).toBe(9);
  });

  it('fails closed: a grid that does not describe the loaded mask paints nothing', async () => {
    const { result } = await loaded();
    const stale: MaskGrid = { layout: 'kij', dims: [N0, N1, N2 + 1] };
    let changed = -1;
    act(() => {
      changed = result.current.paintPlane({ grid: stale, view: anat.axial, sliceIndex: 0, r: 0, c: 0, brushSize: 3, brushShape: 'circle', labelId: 1, erase: false });
    });
    expect(changed).toBe(0);
    expect(result.current.getMaskArray()!.every((v) => v === 0)).toBe(true);
  });

  it('every in-memory change bumps the render revision (load, paint, undo)', async () => {
    const { result } = await loaded();
    const r0 = result.current.revision;
    act(() => {
      result.current.beginPlaneStroke(GRID, anat.axial, 0);
      result.current.paintPlane({ grid: GRID, view: anat.axial, sliceIndex: 0, r: 0, c: 0, brushSize: 1, brushShape: 'circle', labelId: 1, erase: false });
    });
    const r1 = result.current.revision;
    expect(r1).toBeGreaterThan(r0);
    act(() => { result.current.undo(); });
    expect(result.current.revision).toBeGreaterThan(r1);
  });
});
