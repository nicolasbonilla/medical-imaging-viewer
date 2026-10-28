/**
 * PRB-004 (HAZ-006) — the W/L GPU view places voxels exactly where the standard 2D view does.
 *
 * The standard 2D view, the matplotlib view and the multi-panel grid draw the server's slice
 * images: storage voxel (i, j) of slice k is drawn at row i (down the screen), column j (to the
 * right), and the mask is overlaid voxel for voxel in that same order. No affine is involved.
 * niivue instead places a voxel by the volume's scanner affine, so for the usual storage
 * orientations it showed the same slice rotated by 90 degrees (and, depending on the orientation,
 * mirrored) — the clinician saw one layout while painting and another while windowing.
 *
 * Fix: before a volume is added to the W/L GPU view, its affine is replaced by the affine of the
 * standard view's layout (this file), so niivue's own pipeline puts voxel (i, j, k) at row i,
 * column j of axial slice k. The SAME transform, computed from the image, is given to the mask, so
 * the mask lands on the image voxel for voxel — exactly as in the standard view. That is only right
 * if the mask is stored on the image's own voxel grid in the image's voxel order, so a mask is drawn
 * only when it is (`maskMatchesImageGrid`); otherwise it is not drawn and the view says so.
 *
 * This is a DISPLAY transform of the 2D GPU view only. The 3D view keeps the scanner affine (a 3D
 * rendering must keep the anatomy's handedness), and nothing is written back to any file.
 * Orientation labels stay off in every view (RC-023); the anatomical orientation is reported as text.
 */

/** RC-031: masks stored in the image's own voxel order carry this marker in the header description. */
export const RC031_V2_MARKER = 'RC031-ORIENT-V2';

/** Same tolerance as RC-039's "on the image's own grid" check (per affine element). */
export const SAME_GRID_TOLERANCE = 1e-3;

/** The part of a niivue NVImage header this module reads (niivue 0.67 `hdr`). */
export interface NiftiHeaderLike {
  dims: number[];      // [ndim, d0, d1, d2, ...]
  pixDims: number[];   // [qfac, s0, s1, s2, ...]
  affine: number[][];  // 4x4, rows
  description?: string;
}

export interface VolumeLike {
  hdr: NiftiHeaderLike;
  calculateRAS: () => void;
}

export interface VoxelGrid {
  dims: [number, number, number];
  spacing: [number, number, number];
  affine: number[][];
}

function positive(x: number): number {
  const a = Math.abs(x);
  return Number.isFinite(a) && a > 0 ? a : 1;
}

/** The storage grid of a loaded volume, copied (later changes to the volume do not affect it). */
export function voxelGridOf(vol: VolumeLike): VoxelGrid {
  const d = vol.hdr.dims;
  const p = vol.hdr.pixDims;
  return {
    dims: [Math.max(1, d[1] | 0), Math.max(1, d[2] | 0), Math.max(1, d[3] | 0)],
    spacing: [positive(p[1]), positive(p[2]), positive(p[3])],
    affine: vol.hdr.affine.map((row) => [...row]),
  };
}

/**
 * Voxel (i, j, k) → display coordinates for niivue's axial view, whose screen is +x to the right
 * and +y up (niivue's default, non-radiological convention, which the GPU view sets explicitly):
 * x = j · s1 (column, to the right), y = −i · s0 (row, downwards), z = k · s2 (slice).
 * Voxel sizes are kept, so shapes are drawn in true proportions.
 */
export function standardViewAffine(grid: VoxelGrid): number[][] {
  const [s0, s1, s2] = grid.spacing;
  return [
    [0, s1, 0, 0],
    [-s0, 0, 0, 0],
    [0, 0, s2, 0],
    [0, 0, 0, 1],
  ];
}

/** Give a loaded volume the standard view's layout of `grid` (call before `nv.addVolume`). */
export function placeAsStandardView(vol: VolumeLike, grid: VoxelGrid): void {
  vol.hdr.affine = standardViewAffine(grid);
  vol.calculateRAS();
}

export type MaskGridCheck =
  | { ok: true }
  | { ok: false; reason: 'grid' | 'position' | 'order' };

/**
 * A mask may be drawn voxel for voxel on the image only if it is on the image's own grid (same
 * dimensions, same voxel-to-scanner transform within SAME_GRID_TOLERANCE) and stored in the image's
 * voxel order (RC-031 marker; a legacy mask is the in-plane transpose, undetectable by shape on a
 * square slice). Both affines are the ones the files carry, read before any display transform.
 */
export function maskMatchesImageGrid(mask: VoxelGrid, maskDescription: string | undefined, image: VoxelGrid): MaskGridCheck {
  if (mask.dims.some((d, n) => d !== image.dims[n])) return { ok: false, reason: 'grid' };
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 4; c++) {
      const a = mask.affine[r]?.[c];
      const b = image.affine[r]?.[c];
      if (!Number.isFinite(a) || !Number.isFinite(b) || Math.abs(a - b) > SAME_GRID_TOLERANCE) {
        return { ok: false, reason: 'position' };
      }
    }
  }
  if (!(maskDescription ?? '').includes(RC031_V2_MARKER)) return { ok: false, reason: 'order' };
  return { ok: true };
}

export type Mask3DCheck =
  | { ok: true }
  | { ok: false; reason: 'position' | 'order' };

function isIdentityAffine(affine: number[][]): boolean {
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 4; c++) {
      const a = affine[r]?.[c];
      if (!Number.isFinite(a) || Math.abs(a - (r === c ? 1 : 0)) > SAME_GRID_TOLERANCE) return false;
    }
  }
  return true;
}

/**
 * PRB-004 review (M1): the 3D view composites each mask by the mask's OWN voxel-to-scanner transform (a visit
 * mask may lie on another grid), so it needs no common grid — but it needs a mask whose voxels are in its
 * image's order (RC-031 marker; a legacy mask is the in-plane transpose and would be drawn mirrored about the
 * diagonal) and whose scanner position is known (a mask saved without its image gets the identity transform:
 * drawn by it, it lands at an arbitrary place). The masks are requested aligned to the image shown
 * (`?ref_file_id=`), so a legacy mask on that image's grid arrives realigned, with the marker.
 */
export function maskPlaceableIn3D(mask: VoxelGrid, maskDescription: string | undefined): Mask3DCheck {
  if (isIdentityAffine(mask.affine)) return { ok: false, reason: 'position' };
  if (!(maskDescription ?? '').includes(RC031_V2_MARKER)) return { ok: false, reason: 'order' };
  return { ok: true };
}

/** PRB-004 review (M1): the mask NIfTI of a segmentation, requested aligned to the image `fileId` (server-side
 *  realignment of a mask on that image's grid; any other mask comes back as stored). */
export function segmentationNiftiPath(segmentationId: string, fileId: string | null | undefined): string {
  const base = `/api/v1/segmentation/${segmentationId}/nifti`;
  return fileId ? `${base}?ref_file_id=${encodeURIComponent(fileId)}` : base;
}

/**
 * NIfTI file name for a downloaded buffer, by its content (gzip magic 1f 8b → .nii.gz).
 *
 * PRB-005: niivue derives the file type from the name it is given, or else from the URL. A blob URL
 * has no extension; on a host name without a dot (localhost, an intranet server name) niivue's
 * extension parser then throws "Cannot read properties of undefined (reading 'toUpperCase')". Every
 * volume handed to niivue therefore carries an explicit name.
 */
export function niftiNameFor(buffer: ArrayBuffer, stem = 'volume'): string {
  const b = new Uint8Array(buffer, 0, Math.min(2, buffer.byteLength));
  return b.length === 2 && b[0] === 0x1f && b[1] === 0x8b ? `${stem}.nii.gz` : `${stem}.nii`;
}

/**
 * PRB-006: display range for a lesion / label mask overlay, whatever its header says. A mask NIfTI
 * written with a copy of the MRI's header carries the MRI's display window (e.g. −15.5 … 189.2);
 * niivue would then tint every background voxel and show the labels at the bottom of the colour
 * scale. With 0 … 1, background 0 is transparent and every label ≥ 1 is drawn in full colour.
 */
export const LABEL_MASK_DISPLAY_RANGE = Object.freeze({ cal_min: 0, cal_max: 1 });
