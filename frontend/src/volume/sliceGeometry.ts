/**
 * Slice geometry — the ONE mapping between screen pixels and voxels used by every
 * layer of the client 2D viewer (image, segmentation mask, zone map, painting,
 * cursor read-out, lesion box, measurements). Class C: because image and overlays go
 * through the same `voxelOf` / `displayOf`, they cannot drift apart; the tests in
 * `sliceGeometry.test.ts` / `maskPlane.test.ts` prove it on asymmetric volumes.
 *
 * A SliceView fixes one voxel axis (`normal`) at a slice index and shows the other
 * two as rows/columns, optionally flipped:
 *
 *    display (r, c)  ->  voxel[row] = rowFlip ? rows-1-r : r
 *                        voxel[col] = colFlip ? cols-1-c : c
 *                        voxel[normal] = slice
 *
 * Two families of views:
 *  - VOXEL views (`buildVoxelViews`): array order, no anatomical claim. Its "k" view
 *    is bit-for-bit the legacy server PNG layout (rows = axis 0, cols = axis 1).
 *  - ANATOMICAL views (`buildAnatomicalViews`): axial / coronal / sagittal derived
 *    from the affine axis codes, in the same display convention niivue uses for the
 *    3D/MPR panels (see DISPLAY_CONVENTION), so 2D and 3D never disagree. Only built
 *    when the orientation is determinate; otherwise the caller must use voxel views.
 *
 * Laterality is NEVER labelled here (RC-023 / CAPA-004 CA-4.3 open): views carry an
 * orientation, not L/R text.
 */
import { codeAxis, type AxisCodes } from './orientation';

export type Axis = 0 | 1 | 2;
export type PlaneName = 'axial' | 'coronal' | 'sagittal';
export const PLANES: PlaneName[] = ['axial', 'coronal', 'sagittal'];

/**
 * Display convention shared by the 2D client viewer and the niivue 3D/MPR panels
 * (ImageViewer3D passes `isRadiologicalConvention` from this). 'neurological' =
 * patient left on screen left (niivue default, what the 3D view has always shown);
 * 'radiological' = patient right on screen left (PACS norm). Changing it changes
 * both views together. Owner decision recorded in docs/research/viewer-v3.
 */
export type DisplayConvention = 'neurological' | 'radiological';
export const DISPLAY_CONVENTION: DisplayConvention = 'neurological';

export interface SliceView {
  /** Slot name. For voxel views this is NOT an anatomical claim (see `anatomical`). */
  plane: PlaneName;
  /** True when built from a determinate affine (anatomical axial/coronal/sagittal). */
  anatomical: boolean;
  normal: Axis;
  row: Axis;
  col: Axis;
  rowFlip: boolean;
  colFlip: boolean;
  rows: number;
  cols: number;
  depth: number;
  /** Physical size (mm) of one display row / column step and of one slice step. */
  rowSpacing: number;
  colSpacing: number;
  sliceSpacing: number;
}

export type Dims3 = readonly [number, number, number];
export type Spacing3 = readonly [number, number, number];

function safeSpacing(s: number): number {
  return Number.isFinite(s) && s > 0 ? s : 1;
}

export function makeView(
  plane: PlaneName, anatomical: boolean, dims: Dims3, spacing: Spacing3,
  normal: Axis, row: Axis, col: Axis, rowFlip: boolean, colFlip: boolean,
): SliceView {
  if (new Set([normal, row, col]).size !== 3) throw new Error('view axes must be a permutation of 0,1,2');
  return {
    plane, anatomical, normal, row, col, rowFlip, colFlip,
    rows: dims[row], cols: dims[col], depth: dims[normal],
    rowSpacing: safeSpacing(spacing[row]),
    colSpacing: safeSpacing(spacing[col]),
    sliceSpacing: safeSpacing(spacing[normal]),
  };
}

/**
 * Array-order views. 'axial' slot = fixed axis 2, rows = axis 0, cols = axis 1, no
 * flips: identical to the legacy server PNG (`pixel_array[:, :, k]`). The other two
 * slots show axis 2 increasing upwards (a display choice, labelled by voxel axis in
 * the UI — no anatomical claim).
 */
export function buildVoxelViews(dims: Dims3, spacing: Spacing3): Record<PlaneName, SliceView> {
  return {
    axial: makeView('axial', false, dims, spacing, 2, 0, 1, false, false),
    coronal: makeView('coronal', false, dims, spacing, 1, 2, 0, true, false),
    sagittal: makeView('sagittal', false, dims, spacing, 0, 2, 1, true, false),
  };
}

/**
 * Anatomical views from the affine axis codes (niivue-compatible, non-oblique
 * "nearest axis" reslicing — the same as niivue's default 2D mode):
 *   axial:    up = Anterior, right = patient Right (neurological) / Left (radiological)
 *   coronal:  up = Superior, right = as axial
 *   sagittal: up = Superior, right = Anterior (niivue default, nose right)
 */
export function buildAnatomicalViews(
  dims: Dims3, spacing: Spacing3, codes: AxisCodes,
  convention: DisplayConvention = DISPLAY_CONVENTION,
): Record<PlaneName, SliceView> {
  const byWorld: { axis: Axis; sign: 1 | -1 }[] = [];
  codes.forEach((code, voxelAxis) => {
    const { world, sign } = codeAxis(code);
    byWorld[world] = { axis: voxelAxis as Axis, sign };
  });
  if (byWorld.length !== 3 || byWorld.some((v) => !v)) {
    throw new Error('axis codes must name three distinct world axes');
  }
  const lr = byWorld[0], ap = byWorld[1], si = byWorld[2];
  // Screen-right = +R in neurological, = +L in radiological.
  const lrFlip = convention === 'neurological' ? lr.sign === -1 : lr.sign === 1;
  // Row 0 is the top: superior/anterior at the top means flip when index grows towards S/A.
  const siFlip = si.sign === 1;
  const apUpFlip = ap.sign === 1;
  const apRightFlip = ap.sign === -1;
  return {
    axial: makeView('axial', true, dims, spacing, si.axis, ap.axis, lr.axis, apUpFlip, lrFlip),
    coronal: makeView('coronal', true, dims, spacing, ap.axis, si.axis, lr.axis, siFlip, lrFlip),
    sagittal: makeView('sagittal', true, dims, spacing, lr.axis, si.axis, ap.axis, siFlip, apRightFlip),
  };
}

/** Voxel (i, j, k) shown at display (r, c) of `slice`. */
export function voxelOf(view: SliceView, slice: number, r: number, c: number): [number, number, number] {
  const out: [number, number, number] = [0, 0, 0];
  out[view.normal] = slice;
  out[view.row] = view.rowFlip ? view.rows - 1 - r : r;
  out[view.col] = view.colFlip ? view.cols - 1 - c : c;
  return out;
}

/** Inverse of voxelOf: where voxel (i, j, k) appears in this view. */
export function displayOf(view: SliceView, ijk: readonly [number, number, number]): { slice: number; r: number; c: number } {
  const a = ijk[view.row], b = ijk[view.col];
  return {
    slice: ijk[view.normal],
    r: view.rowFlip ? view.rows - 1 - a : a,
    c: view.colFlip ? view.cols - 1 - b : b,
  };
}

/**
 * Strides to walk a Fortran-order volume (index = i + n0*(j + n1*k)) in display
 * order: index(r, c) = base + r*rowStep + c*colStep. Lets renderers fill a slice
 * without per-pixel voxelOf calls while staying exactly equivalent to it.
 */
export function volumeStrides(view: SliceView, dims: Dims3, slice: number): { base: number; rowStep: number; colStep: number } {
  const stride = [1, dims[0], dims[0] * dims[1]];
  const r0 = view.rowFlip ? view.rows - 1 : 0;
  const c0 = view.colFlip ? view.cols - 1 : 0;
  return {
    base: slice * stride[view.normal] + r0 * stride[view.row] + c0 * stride[view.col],
    rowStep: (view.rowFlip ? -1 : 1) * stride[view.row],
    colStep: (view.colFlip ? -1 : 1) * stride[view.col],
  };
}

/** Clamp a slice index into the view's depth. */
export function clampSlice(view: SliceView, slice: number): number {
  return Math.max(0, Math.min(view.depth - 1, Math.round(slice)));
}

/** Physical aspect (width / height) of the displayed slice. */
export function physicalAspect(view: SliceView): number {
  return (view.cols * view.colSpacing) / (view.rows * view.rowSpacing);
}
