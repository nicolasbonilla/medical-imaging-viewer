/**
 * What the 2D canvas draws, and the check that runs before a radiologist confirms a segmentation.
 *
 * Release 2026-10-25 — second independent review of PR #69, blocker B1 and major M3: a radiologist must never confirm
 * a mask with lesions that are not drawn. A lesion is drawn only when its mask value has an entry in the label table
 * (otherwise the canvas used to leave it transparent; it now gets UNLABELLED_FALLBACK_COLOR and a warning), the label
 * is not switched off with its eye toggle, the overlay is on, and the lesion opacity is not below a visible minimum.
 */
import type { LabelInfo } from '@/types';

/** The lesion-opacity slider below which lesions count as not drawn (the confirmation is refused). */
export const MIN_VISIBLE_LESION_OPACITY = 0.25;
/** A label's own opacity times the slider below which that label counts as not drawn. */
export const MIN_VISIBLE_LABEL_ALPHA = 0.1;
/** Colour of a mask value the label table does not name: drawn, never transparent (magenta, as no preset uses it). */
export const UNLABELLED_FALLBACK_COLOR = '#FF00FF';

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
  | { kind: 'overlay_off' }
  | { kind: 'opacity_low'; opacity: number }
  | { kind: 'no_label'; value: number }
  | { kind: 'hidden'; value: number; name: string }
  | { kind: 'faint'; value: number; name: string };

export interface DrawCheckInput {
  /** distinct non-zero values present in the open mask */
  values: ReadonlyArray<number>;
  labels: ReadonlyArray<LabelInfo>;
  labelVisibility: Record<number, boolean>;
  isOverlayVisible: boolean;
  lesionOpacity: number;
}

/** Every reason why a value of the mask would not be drawn; empty when every lesion is drawn. */
export function undrawnMaskValues(input: DrawCheckInput): UndrawnReason[] {
  const out: UndrawnReason[] = [];
  if (!input.isOverlayVisible) out.push({ kind: 'overlay_off' });
  if (!(input.lesionOpacity >= MIN_VISIBLE_LESION_OPACITY)) out.push({ kind: 'opacity_low', opacity: input.lesionOpacity });
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
  }
  return out;
}
