/**
 * PRB-008 — which slice an image opens on.
 *
 * The viewer opened every image on slice index 0 — for a head MRI the first axial slice, below or
 * at the edge of the head: an empty image (the demo study opened on "1/182"). Rule (SRS-001
 * REQ-FUNC-103, draft):
 *   - an image opens on its MIDDLE slice, floor((n − 1) / 2) (182 slices → index 90, "91/182"),
 *     which for a head scan lies inside the brain;
 *   - switching to another image OF THE SAME STUDY with the same number of slices keeps the current
 *     slice (comparing sequences of one examination on one grid at the same level);
 *   - any other switch (another size, another study) opens the new image on its middle slice — a
 *     kept index would point at an unrelated level, or outside the new image.
 * The slice is not moved when a segmentation is opened or closed.
 */
interface SliceCounted {
  total_slices?: number;
  slices?: unknown[];
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
  const keep = sameStudy && previous !== null && sliceCount(previous) === n
    && Number.isInteger(previousIndex) && previousIndex >= 0 && previousIndex < n;
  return keep ? previousIndex : middleSliceIndex(n);
}
