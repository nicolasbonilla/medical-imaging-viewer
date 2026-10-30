/**
 * PRB-008 — which slice an image opens on.
 *
 * The viewer opened every image on slice index 0 — for a head MRI the first axial slice, below or
 * at the edge of the head: an empty image (the demo study opened on "1/182"). Rule (SRS-001
 * REQ-FUNC-103, draft):
 *   - an image opens on its MIDDLE slice, floor((n − 1) / 2) (182 slices → index 90, "91/182"),
 *     which for a head scan lies inside the brain;
 *   - switching to another image OF THE SAME STUDY ON THE SAME VOXEL GRID keeps the current slice
 *     (comparing sequences of one examination at the same level). Same grid: same number of slices and,
 *     as far as the images report them, the same matrix (rows, columns, slices), pixel spacing, slice
 *     thickness and stored orientation (review of PR #71, m4: the slice count alone let a sequence with
 *     another matrix, voxel size or orientation keep an index that points at another anatomical level);
 *   - any other switch (another grid, another study) opens the new image on its middle slice — a
 *     kept index would point at an unrelated level, or outside the new image.
 * The slice is not moved when a segmentation is opened or closed.
 */
interface GridMetadata {
  rows?: number;
  columns?: number;
  slices?: number;
  pixel_spacing?: number[];
  slice_thickness?: number;
  anatomical_orientation?: string;
}

interface SliceCounted {
  total_slices?: number;
  slices?: unknown[];
  metadata?: GridMetadata | null;
}

const GRID_TOLERANCE_MM = 1e-3;

function sameNumber(a: number | undefined, b: number | undefined, tol = 0): boolean {
  if (a === undefined || a === null || b === undefined || b === null) return a == null && b == null;
  return Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) <= tol;
}

/**
 * Review m4: the two images are on the same voxel grid as far as their metadata tell: every grid field one
 * of them reports, the other reports equally (a field reported by neither cannot tell them apart).
 */
export function sameReportedGrid(a: SliceCounted, b: SliceCounted): boolean {
  if (sliceCount(a) !== sliceCount(b)) return false;
  const ma: GridMetadata = a.metadata ?? {};
  const mb: GridMetadata = b.metadata ?? {};
  if (!sameNumber(ma.rows, mb.rows) || !sameNumber(ma.columns, mb.columns) || !sameNumber(ma.slices, mb.slices)) return false;
  if (!sameNumber(ma.slice_thickness, mb.slice_thickness, GRID_TOLERANCE_MM)) return false;
  const pa = ma.pixel_spacing ?? null;
  const pb = mb.pixel_spacing ?? null;
  if ((pa === null) !== (pb === null)) return false;
  if (pa && pb && (pa.length !== pb.length || pa.some((v, n) => !sameNumber(v, pb[n], GRID_TOLERANCE_MM)))) return false;
  return (ma.anatomical_orientation ?? null) === (mb.anatomical_orientation ?? null);
}

/** Number of slices of an opened image (0 when unknown). */
export function sliceCount(series: SliceCounted | null | undefined): number {
  const n = series?.total_slices ?? series?.slices?.length ?? 0;
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

/** Middle slice index of a volume of `n` slices: floor((n − 1) / 2); 0 for n ≤ 1. */
export function middleSliceIndex(n: number): number {
  return Number.isFinite(n) && n > 1 ? Math.floor((n - 1) / 2) : 0;
}

/** The slice index an image opens on (rule above). */
export function sliceIndexOnOpen(
  next: SliceCounted | null,
  previous: SliceCounted | null,
  previousIndex: number,
  sameStudy: boolean,
): number {
  const n = sliceCount(next);
  if (n === 0) return 0;
  const keep = sameStudy && previous !== null && next !== null && sameReportedGrid(next, previous)
    && Number.isInteger(previousIndex) && previousIndex >= 0 && previousIndex < n;
  return keep ? previousIndex : middleSliceIndex(n);
}
