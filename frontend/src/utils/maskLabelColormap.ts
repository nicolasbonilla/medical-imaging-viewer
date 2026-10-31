/**
 * PRB-004 review (m6) / PRB-010 — the colours niivue draws a segmentation mask in (W/L GPU view and 3D view).
 *
 * Both views drew every label value in one colour (niivue's "red"), so a region-classified mask showed all four
 * MAGNIMS regions alike while the 2D overlay and the legends coloured them. Here each label value takes its
 * label's colour, a label named after a MAGNIMS region the region's colour from the one shared mapping
 * (utils/regionColors.ts), whatever colour was stored with it — as in the 2D overlay.
 *
 * A value present in the mask but missing from its label table is still drawn, in UNLABELLED_FALLBACK_COLOR (cyan,
 * the app's one colour for it, utils/regionColors.ts): a voxel the mask marks is never silently left out. Value 0
 * (background) is transparent.
 *
 * Built as an ordinary niivue colormap (registered with `addColormap`) rather than a label colormap
 * (`colormapLabel`), which the 3D volume rendering does not colour (see registerZoneMapColormap in
 * ImageViewer3D). niivue samples a colormap texture with linear filtering, so each label value owns a wide
 * band of the 256 entries (as the zone-map colormap does) and the display range is 0 .. highest label + 1:
 * value v falls in the middle of its band, and every value above the highest listed label lands in the
 * top band, drawn in UNLABELLED_FALLBACK_COLOR.
 */
import type { LabelInfo } from '@/types/segmentation';
import { withRegionColors, UNLABELLED_FALLBACK_COLOR } from './regionColors';

/** Prefix of the names mask colormaps are registered under in niivue (one name per label table: niivue's
 *  colormap registry is shared by every viewer instance). */
export const MASK_LABEL_COLORMAP = 'mstool_mask_labels';

export interface NiivueColormap { R: number[]; G: number[]; B: number[]; A: number[]; I: number[] }

export interface MaskLabelColormap {
  name: string;
  colormap: NiivueColormap;
  /** The display range that puts label value v in the middle of its band. */
  cal_min: number;
  cal_max: number;
}

const HEX = /^#[0-9a-f]{6}$/i;
const rgbOf = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));

/**
 * The niivue colormap and display range for a mask with this label table, or null when the table lists no label
 * value 1..255 (the caller then keeps one colour for every value >= 1).
 */
export function maskLabelColormap(labels: ReadonlyArray<Pick<LabelInfo, 'id' | 'name' | 'color'>> | null | undefined): MaskLabelColormap | null {
  const listed = withRegionColors(
    (labels ?? []).filter((l) => Number.isInteger(l.id) && l.id >= 1 && l.id <= 255 && HEX.test(l.color ?? '')).map((l) => ({ ...l })),
  );
  if (listed.length === 0) return null;
  const top = Math.max(...listed.map((l) => l.id));
  const lastBand = top + 1; // every value above the highest listed label
  const colourOf = (v: number): string | null =>
    v === 0 ? null : (v <= top ? listed.find((l) => l.id === v)?.color : undefined) ?? UNLABELLED_FALLBACK_COLOR;

  const R = new Array<number>(256).fill(0);
  const G = new Array<number>(256).fill(0);
  const B = new Array<number>(256).fill(0);
  const A = new Array<number>(256).fill(0);
  const I = Array.from({ length: 256 }, (_, n) => n);
  for (let t = 0; t < 256; t++) {
    const hex = colourOf(Math.round((t * lastBand) / 255));
    if (!hex) continue;
    [R[t], G[t], B[t]] = rgbOf(hex);
    A[t] = 255;
  }
  const name = `${MASK_LABEL_COLORMAP}_${listed.map((l) => `${l.id}${l.color.slice(1).toUpperCase()}`).join('_')}`;
  return { name, colormap: { R, G, B, A, I }, cal_min: 0, cal_max: lastBand };
}
