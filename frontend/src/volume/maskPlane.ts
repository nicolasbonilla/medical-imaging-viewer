/**
 * Segmentation-mask access through the SAME SliceView geometry as the image.
 *
 * Masks live in memory in the RC-031 internal layout (depth, height, width) =
 * (k, a0, a1): index = k*n0*n1 + i*n1 + j. A few legacy / backend-generated masks
 * arrive with the in-plane axes swapped, (k, a1, a0); the legacy 2D canvas detected
 * that by the swapped-dimension signature and transposed on the fly. We keep that
 * exact compatibility rule (`resolveMaskGrid`) — and refuse anything else.
 *
 * FAIL CLOSED (Class C): a mask whose grid does not match the image grid is NOT
 * stretched onto the image (`resolveMaskGrid` returns null; the viewer hides the
 * overlay and says why). A misplaced lesion that looks plausible is the hazard.
 */
import { voxelOf, type Dims3, type SliceView } from './sliceGeometry';

export type MaskLayout = 'kij' | 'kji';

export interface MaskGrid {
  layout: MaskLayout;
  /** Image grid [n0, n1, n2] the mask is aligned to. */
  dims: Dims3;
}

export interface MaskDims {
  depth: number;
  height: number;
  width: number;
}

/**
 * Decide how a (depth, height, width) mask maps onto an image grid [n0, n1, n2].
 * Same rule as the legacy canvas: canonical when (h, w) = (n0, n1); swapped when
 * (h, w) = (n1, n0) and the slice is not square; otherwise not on this grid.
 */
export function resolveMaskGrid(mask: MaskDims | null | undefined, dims: Dims3): MaskGrid | null {
  if (!mask) return null;
  if (mask.depth !== dims[2]) return null;
  if (mask.height === dims[0] && mask.width === dims[1]) return { layout: 'kij', dims };
  if (mask.height === dims[1] && mask.width === dims[0]) return { layout: 'kji', dims };
  return null;
}

/** Linear index of voxel (i, j, k) in a mask stored with `grid.layout`. */
export function maskIndex(grid: MaskGrid, i: number, j: number, k: number): number {
  const [n0, n1] = grid.dims;
  return grid.layout === 'kij' ? (k * n0 + i) * n1 + j : (k * n1 + j) * n0 + i;
}

/**
 * The mask's (z, y, x) array coordinates (what the backend's lesion analysis reports
 * for centroids / bounding boxes) -> image voxel (i, j, k).
 */
export function maskZYXToVoxel(grid: MaskGrid, z: number, y: number, x: number): [number, number, number] {
  return grid.layout === 'kij' ? [y, x, z] : [x, y, z];
}

/** Copy of the mask plane shown by `view` at `slice`, in display order (rows*cols). */
export function gatherPlane(mask: Uint8Array, grid: MaskGrid, view: SliceView, slice: number, out?: Uint8Array): Uint8Array {
  const { rows, cols } = view;
  const buf = out && out.length === rows * cols ? out : new Uint8Array(rows * cols);
  // Strides in mask memory for one display row / column step.
  const [n0, n1] = grid.dims;
  const strideKij = [n1, 1, n0 * n1];          // i, j, k
  const strideKji = [1, n0, n0 * n1];
  const stride = grid.layout === 'kij' ? strideKij : strideKji;
  const r0 = view.rowFlip ? rows - 1 : 0;
  const c0 = view.colFlip ? cols - 1 : 0;
  const rowStep = (view.rowFlip ? -1 : 1) * stride[view.row];
  const colStep = (view.colFlip ? -1 : 1) * stride[view.col];
  const base = slice * stride[view.normal] + r0 * stride[view.row] + c0 * stride[view.col];
  let p = 0;
  for (let r = 0; r < rows; r++) {
    let idx = base + r * rowStep;
    for (let c = 0; c < cols; c++, idx += colStep) buf[p++] = mask[idx];
  }
  return buf;
}

/** Write a display-order plane back into the 3-D mask (inverse of gatherPlane). */
export function scatterPlane(mask: Uint8Array, grid: MaskGrid, view: SliceView, slice: number, plane: Uint8Array): void {
  const { rows, cols } = view;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const [i, j, k] = voxelOf(view, slice, r, c);
      mask[maskIndex(grid, i, j, k)] = plane[r * cols + c];
    }
  }
}

export type BrushShape = 'circle' | 'square';

/**
 * Display-plane offsets covered by a brush of `size` voxels. Circle: the legacy
 * rule (radius = floor(size/2), dx²+dy² <= r²). Square: exactly the square the
 * cursor outlines ([-floor(size/2), size-1-floor(size/2)] on both axes).
 */
export function brushOffsets(size: number, shape: BrushShape): Array<[number, number]> {
  const s = Math.max(1, Math.round(size));
  const out: Array<[number, number]> = [];
  if (shape === 'square') {
    const half = Math.floor(s / 2);
    for (let dr = -half; dr <= s - 1 - half; dr++) for (let dc = -half; dc <= s - 1 - half; dc++) out.push([dr, dc]);
    return out;
  }
  const radius = Math.floor(s / 2);
  for (let dr = -radius; dr <= radius; dr++) {
    for (let dc = -radius; dc <= radius; dc++) if (dr * dr + dc * dc <= radius * radius) out.push([dr, dc]);
  }
  return out;
}

export interface PlaneStroke {
  view: SliceView;
  slice: number;
  /** Display row / column under the cursor. */
  r: number;
  c: number;
  brushSize: number;
  brushShape: BrushShape;
  value: number;
  /** Return false to protect the current voxel value (draw-over rules). */
  canOverwrite?: (current: number) => boolean;
}

/**
 * Paint one brush dab directly into the 3-D mask through the view geometry.
 * Returns the number of voxels changed.
 */
export function paintPlaneStroke(mask: Uint8Array, grid: MaskGrid, s: PlaneStroke): number {
  const { view, slice } = s;
  if (slice < 0 || slice >= view.depth) return 0;
  let changed = 0;
  for (const [dr, dc] of brushOffsets(s.brushSize, s.brushShape)) {
    const r = s.r + dr, c = s.c + dc;
    if (r < 0 || r >= view.rows || c < 0 || c >= view.cols) continue;
    const [i, j, k] = voxelOf(view, slice, r, c);
    const idx = maskIndex(grid, i, j, k);
    const cur = mask[idx];
    if (s.canOverwrite && !s.canOverwrite(cur)) continue;
    if (cur !== s.value) { mask[idx] = s.value; changed++; }
  }
  return changed;
}
