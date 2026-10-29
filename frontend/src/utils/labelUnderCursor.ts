/**
 * PRB-010 — re-review of PR #71 (R6): the label under the cursor, by name — a non-colour cue on the image.
 *
 * Periventricular (orange) and deep white matter (vermillion) are the closest region pair as drawn (36 % over grey
 * tissue), and the pair that matters for DIS. The legends and the lesion rows already name the regions; on the image
 * the colour was the only cue. The sidebar's cursor readout now names the label of the voxel under the cursor.
 *
 * `slice` is one slice of the mask in the app's internal order (row a0, column a1) with dimensions `mask`; the image
 * is `imageWidth` columns by `imageHeight` rows; (x, y) are the image column and row the cursor readout reports.
 * Final check (F1): the voxel is found by the overlay's own placement rule (utils/maskDisplayLayout.ts) — a mask stored
 * with rows and columns swapped is read where the overlay draws it, and a mask the overlay cannot place gives nothing.
 */
import { maskDisplayLayout, storedIndexOfDisplayedVoxel, type SliceDims } from './maskDisplayLayout';

export interface LabelAtCursor {
  value: number;
  /** The label's name from the table; null for a value the table does not list. */
  name: string | null;
}

export function labelUnderCursor(
  slice: Uint8Array | null | undefined,
  mask: SliceDims | null | undefined,
  imageWidth: number,
  imageHeight: number,
  x: number,
  y: number,
  labels: ReadonlyArray<{ id: number; name: string }> | null | undefined,
): LabelAtCursor | null {
  if (!slice || !mask || slice.length !== mask.width * mask.height) return null;
  if (!Number.isInteger(x) || !Number.isInteger(y) || x < 0 || y < 0 || x >= imageWidth || y >= imageHeight) return null;
  const index = storedIndexOfDisplayedVoxel(mask, maskDisplayLayout(mask, imageWidth, imageHeight), x, y);
  if (index === null) return null;
  const value = slice[index];
  if (!value) return null;
  return { value, name: (labels ?? []).find((l) => l.id === value)?.name ?? null };
}
