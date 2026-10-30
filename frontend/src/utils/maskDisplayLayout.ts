/**
 * How the 2D overlay places one mask slice on the displayed image — ONE rule, used by the overlay
 * (SegmentationCanvasLocal: the mask, the selected lesion's box and centroid) and by the cursor readout
 * (labelUnderCursor), so the label the readout names is the label the overlay draws there (PRB-010, final check F1).
 *
 * A mask slice is stored in the app's internal order (row a0, column a1), `width` columns by `height` rows. Some older
 * back-end masks (zone maps, AI results) were stored with rows and columns swapped; on a non-square image the overlay
 * then transposes the slice for display (RC-031 auto-fix). Any other mismatch cannot be placed on the image.
 */
export type MaskDisplayLayout = 'as-stored' | 'transposed' | 'other';

export interface SliceDims {
  width: number;
  height: number;
}

/** The overlay's rule: as stored when the mask has the image's columns and rows; transposed when they are swapped. */
export function maskDisplayLayout(mask: SliceDims | null | undefined, imageWidth: number, imageHeight: number): MaskDisplayLayout {
  if (!mask) return 'other';
  if (mask.width !== imageWidth && mask.height === imageWidth && mask.width === imageHeight) return 'transposed';
  if (mask.width === imageWidth && mask.height === imageHeight) return 'as-stored';
  return 'other';
}

/** Transpose a 2D mask slice from (srcH × srcW) to (srcW × srcH) layout (what the overlay draws when 'transposed'). */
export function transposeSlice(src: Uint8Array, srcH: number, srcW: number): Uint8Array {
  const dst = new Uint8Array(src.length);
  for (let h = 0; h < srcH; h++) {
    for (let w = 0; w < srcW; w++) {
      dst[w * srcH + h] = src[h * srcW + w];
    }
  }
  return dst;
}

/**
 * Index in the STORED slice of the voxel the overlay draws at image column x, row y — the inverse of `transposeSlice`
 * for 'transposed' (drawn[y · srcH + x] = stored[x · srcW + y]); null when the overlay cannot place the mask.
 */
export function storedIndexOfDisplayedVoxel(
  mask: SliceDims, layout: MaskDisplayLayout, x: number, y: number,
): number | null {
  if (layout === 'as-stored') return y * mask.width + x;
  if (layout === 'transposed') return x * mask.width + y;
  return null;
}
