/**
 * What the 2D canvas draws, and the check that runs before a radiologist confirms a segmentation.
 *
 * Release 2026-10-25 — second independent review of PR #69 (blocker B1, major M3) and its final check (R1, R2): the
 * browser refuses the DIS confirmation unless every value of the open mask is drawn in the view on screen. Checked:
 * the view on screen is the standard 2D view, in segmentation mode, drawing this segmentation (R1); each value has a
 * label in the table drawn (otherwise the canvas draws it in UNLABELLED_FALLBACK_COLOR, with a warning), not switched
 * off with its eye toggle, not too faint; the overlay is on and the lesion opacity not below a visible minimum; on a
 * classified segmentation each value is drawn with the label the server stored for it — same name and colour (R2).
 * Not checked here: what the radiologist looked at; a direct API call or another client skips this check (the server
 * only compares the drawn label table, `drawnLabelsSha256`).
 *
 * Next safety round (2026-10-31), PENDING owner approval:
 *  - PRB-030 (RC-092, L1): the image the standard view draws under the mask has the mask's grid (columns, rows, slices
 *    against the mask's width, height, depth); the server checks the image header (shape, affine, same study);
 *  - PRB-031 (RC-093, L2): no layer drawn UNDER the lesions above MAX_UNDERLAY_OPACITY — the zone map at its user
 *    opacity, the longitudinal overlay, the FLAIR subtraction heat map and the conformal tiers at their fixed opacities
 *    (defined here, drawn with these values by SegmentationCanvasLocal).
 * The check is run, for both confirmations (DIS and AI draft), by utils/confirmDrawCheck.ts.
 */
import type { LabelInfo } from '@/types';
import { MAGNIMS_REGIONS } from './regionColors';

/** The lesion-opacity slider below which lesions count as not drawn (the confirmation is refused). */
export const MIN_VISIBLE_LESION_OPACITY = 0.25;
/** A label's own opacity times the slider below which that label counts as not drawn. */
export const MIN_VISIBLE_LABEL_ALPHA = 0.1;

/**
 * PRB-031 (RC-093): the highest opacity of a layer drawn under the lesions at which a confirmation is accepted. A layer of
 * opacity a over the image leaves (1 - a) of the image contrast and of the lesion colour's own contrast inside an area of
 * the same colour (a periventricular lesion inside the periventricular zone): at 30 % — the zone map's default — at least
 * 70 % remains. Chosen by the agent (owner decision); the lesion opacity minimum above is the companion rule.
 */
export const MAX_UNDERLAY_OPACITY = 0.3;
/** Fixed opacities of the other layers drawn under the lesions (SegmentationCanvasLocal draws them with these values). */
export const LONGITUDINAL_OVERLAY_OPACITY = 0.55;
export const SUBTRACTION_MAX_OPACITY = 0.6;
export const CONFORMAL_TIER_OPACITY = 200 / 255;

export type UnderlayLayer = 'zone_map' | 'longitudinal' | 'subtraction' | 'conformal';

/** PRB-030 (RC-092): a grid as the viewer names it — columns (width), rows (height), slices (depth). */
export interface GridDims {
  width: number;
  height: number;
  depth: number;
}
/**
 * Colour of a mask value the label table does not name: drawn, never transparent — cyan, which no preset label and no
 * MAGNIMS zone uses (not magenta, the "Active (Gd+)" colour). Release 2026-10-30 (merge of #69 and #71): ONE
 * definition, in regionColors.ts, shared with the GPU and 3D views; re-exported here for the 2D canvas.
 */
export { UNLABELLED_FALLBACK_COLOR } from './regionColors';

/** Ids 1-255 that the label table does not name: the canvas draws them with the fallback colour. */
export function idsWithoutLabel(labels: ReadonlyArray<Pick<LabelInfo, 'id'>> | null | undefined): number[] {
  const named = new Set((labels ?? []).map((l) => l.id));
  const out: number[] = [];
  for (let id = 1; id <= 255; id++) if (!named.has(id)) out.push(id);
  return out;
}

/** The distinct non-zero values of a mask, ascending. */
export function distinctMaskValues(mask: Uint8Array): number[] {
  const seen = new Uint8Array(256);
  for (let i = 0; i < mask.length; i++) seen[mask[i]] = 1;
  const out: number[] = [];
  for (let v = 1; v <= 255; v++) if (seen[v]) out.push(v);
  return out;
}

export type UndrawnReason =
  | { kind: 'not_on_screen' }
  | { kind: 'stored_labels_unknown' }
  | { kind: 'not_stored_label'; value: number; drawn: string; drawnColor: string; stored: string; storedColor: string }
  | { kind: 'overlay_off' }
  | { kind: 'opacity_low'; opacity: number }
  | { kind: 'no_label'; value: number }
  | { kind: 'hidden'; value: number; name: string }
  | { kind: 'faint'; value: number; name: string }
  | { kind: 'grid_unknown' }
  | { kind: 'grid_mismatch'; image: GridDims; mask: GridDims }
  | { kind: 'underlay_opaque'; layer: UnderlayLayer; opacity: number }
  | { kind: 'zone_colorized' };

export interface DrawCheckInput {
  /** distinct non-zero values present in the open mask */
  values: ReadonlyArray<number>;
  labels: ReadonlyArray<LabelInfo>;
  labelVisibility: Record<number, boolean>;
  isOverlayVisible: boolean;
  lesionOpacity: number;
  /** Final check of PR #69, R1: the standard 2D view on screen draws this segmentation (omitted: not checked). */
  onScreen?: boolean;
  /** R2: on a classified segmentation, the label table the server stored (null: not read; omitted: not checked). */
  storedLabels?: ReadonlyArray<Pick<LabelInfo, 'id' | 'name' | 'color'>> | null;
  /** PRB-030: the grids of the image under the mask and of the mask (null: not known — refused; omitted: not checked). */
  grid?: { image: GridDims; mask: GridDims | null } | null;
  /** PRB-031: the layers drawn under the lesions now, with the opacity each is drawn at (omitted: not checked). */
  underlays?: ReadonlyArray<{ layer: UnderlayLayer; opacity: number }>;
  /** Review of PR #74 (m1): the lesions are drawn coloured by MAGNIMS zone ("Colorize by zone"): values 1-4 in the
   *  region palette whatever their label, other values not drawn on a slice that has any 1-4. */
  zoneColorized?: boolean;
}

const sameGrid = (a: GridDims, b: GridDims) => a.width === b.width && a.height === b.height && a.depth === b.depth;

/** Every reason why a value of the mask would not be drawn; empty when every lesion is drawn. */
export function undrawnMaskValues(input: DrawCheckInput): UndrawnReason[] {
  const out: UndrawnReason[] = [];
  if (input.onScreen === false) out.push({ kind: 'not_on_screen' });
  if (input.storedLabels === null) out.push({ kind: 'stored_labels_unknown' });
  if (!input.isOverlayVisible) out.push({ kind: 'overlay_off' });
  if (!(input.lesionOpacity >= MIN_VISIBLE_LESION_OPACITY)) out.push({ kind: 'opacity_low', opacity: input.lesionOpacity });
  if (input.grid === null || (input.grid && !input.grid.mask)) {
    out.push({ kind: 'grid_unknown' });
  } else if (input.grid?.mask && !sameGrid(input.grid.image, input.grid.mask)) {
    out.push({ kind: 'grid_mismatch', image: input.grid.image, mask: input.grid.mask });
  }
  // m1: zone colouring draws exactly the stored labels only when every value present is a MAGNIMS region id drawn with
  // that region's label (a classified segmentation); anything else (an AI draft "Lesion", a value 5 or 6) is refused.
  if (input.zoneColorized && input.values.some((v) => v !== 0
      && !(v >= 1 && v <= 4 && input.labels.find((l) => l.id === v)?.name === MAGNIMS_REGIONS[v - 1]))) {
    out.push({ kind: 'zone_colorized' });
  }
  for (const u of input.underlays ?? []) {
    // compared in whole percent, as the slider sets it (0.3 is 30 %, accepted)
    if (!(Math.round(u.opacity * 100) <= Math.round(MAX_UNDERLAY_OPACITY * 100))) {
      out.push({ kind: 'underlay_opaque', layer: u.layer, opacity: u.opacity });
    }
  }
  for (const value of input.values) {
    if (value === 0) continue;
    const label = input.labels.find((l) => l.id === value);
    if (!label) {
      out.push({ kind: 'no_label', value });
    } else if (input.labelVisibility[value] === false) {
      out.push({ kind: 'hidden', value, name: label.name });
    } else if ((label.opacity ?? 0.6) * Math.max(input.lesionOpacity, MIN_VISIBLE_LESION_OPACITY) < MIN_VISIBLE_LABEL_ALPHA) {
      out.push({ kind: 'faint', value, name: label.name });
    }
    if (label && input.storedLabels) {
      const stored = input.storedLabels.find((l) => l.id === value);
      if (!stored || stored.name !== label.name || String(stored.color).toUpperCase() !== String(label.color).toUpperCase()) {
        out.push({ kind: 'not_stored_label', value, drawn: label.name, drawnColor: String(label.color).toUpperCase(),
          stored: stored?.name ?? '', storedColor: String(stored?.color ?? '').toUpperCase() });
      }
    }
  }
  return out;
}

/**
 * The label table as drawn, as text: [[id, name, colour], …] by id, colours upper case, background left out — the
 * same canonical text as the server's `dis_review_gate.drawn_labels_sha256` (final check of PR #69, R2).
 */
export function drawnLabelsCanonical(labels: ReadonlyArray<Pick<LabelInfo, 'id' | 'name' | 'color'>>): string {
  const rows = labels
    .filter((l) => Number.isInteger(l.id) && l.id > 0)
    .map((l): [number, string, string] => [l.id, String(l.name), String(l.color).toUpperCase()])
    .sort((a, b) => a[0] - b[0]);
  return JSON.stringify(rows);
}

/** SHA-256 (hex) of `drawnLabelsCanonical`: sent with the DIS confirmation; the server refuses another table. */
export async function drawnLabelsSha256(labels: ReadonlyArray<Pick<LabelInfo, 'id' | 'name' | 'color'>>): Promise<string> {
  const bytes = new TextEncoder().encode(drawnLabelsCanonical(labels));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}
