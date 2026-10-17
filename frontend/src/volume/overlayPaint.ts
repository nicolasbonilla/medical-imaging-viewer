/**
 * Colourise display-order mask planes (from maskPlane.gatherPlane) into RGBA.
 * Pure functions — the client viewport only blits the results. Semantics follow the
 * legacy 2D canvas (same layers, same opacity rules, same fail-closed fusion), with
 * colours from the shared clinical palette so overlays agree with every legend.
 */
import type { RGB } from '@/utils/clinicalPalette';
import { CONFORMAL_TIER_RGB, LONGITUDINAL_RGB, MAGNIMS_ZONE_RGB } from '@/utils/clinicalPalette';

export interface LabelStyle {
  id: number;
  color: string;     // #RRGGBB
  opacity: number;   // 0..1 (label's own opacity)
}

export type ColorTable = Array<[number, number, number, number] | undefined>;

function hexRgb(hex: string): RGB {
  const h = hex.replace('#', '');
  return [parseInt(h.slice(0, 2), 16) || 0, parseInt(h.slice(2, 4), 16) || 0, parseInt(h.slice(4, 6), 16) || 0];
}

/** Per-label RGBA (visible labels only), alpha scaled by the global lesion opacity. */
export function labelColorTable(
  labels: readonly LabelStyle[] | undefined,
  visibility: Record<number, boolean>,
  lesionOpacity: number,
): ColorTable {
  const table: ColorTable = [];
  for (const l of labels ?? []) {
    if (l.id === 0 || visibility[l.id] === false) continue;
    const [r, g, b] = hexRgb(l.color);
    table[l.id] = [r, g, b, Math.round(Math.round(l.opacity * 255) * lesionOpacity)];
  }
  return table;
}

/** MAGNIMS zone colours at a given alpha (0..255). */
export function zoneColorTable(alpha: number): ColorTable {
  const t: ColorTable = [];
  for (const [k, rgb] of Object.entries(MAGNIMS_ZONE_RGB)) t[Number(k)] = [rgb[0], rgb[1], rgb[2], alpha];
  return t;
}

export function conformalColorTable(): ColorTable {
  const t: ColorTable = [];
  for (const [k, rgb] of Object.entries(CONFORMAL_TIER_RGB)) t[Number(k)] = [rgb[0], rgb[1], rgb[2], 200];
  return t;
}

/** Paint every non-zero value that has a colour; everything else stays transparent. */
export function paintTable(plane: Uint8Array, table: ColorTable, out?: Uint8ClampedArray): Uint8ClampedArray {
  const buf = out && out.length === plane.length * 4 ? out : new Uint8ClampedArray(plane.length * 4);
  buf.fill(0);
  for (let p = 0; p < plane.length; p++) {
    const v = plane[p];
    if (v === 0) continue;
    const c = table[v];
    if (!c) continue;
    const o = p * 4;
    buf[o] = c[0]; buf[o + 1] = c[1]; buf[o + 2] = c[2]; buf[o + 3] = c[3];
  }
  return buf;
}

/**
 * Zone colourisation of a lesion plane (legacy createZoneColorizedSlice): if the mask
 * already carries MAGNIMS labels 1–4 use them; otherwise colour each lesion voxel by
 * the zone map underneath (visual reference only).
 */
export function zoneColorizedPlane(lesion: Uint8Array, zone: Uint8Array): Uint8Array {
  const out = new Uint8Array(lesion.length);
  let classified = false;
  for (let i = 0; i < lesion.length; i++) if (lesion[i] >= 1 && lesion[i] <= 4) { classified = true; break; }
  for (let i = 0; i < lesion.length; i++) {
    if (classified) { if (lesion[i] >= 1 && lesion[i] <= 4) out[i] = lesion[i]; }
    else if (lesion[i] > 0 && zone[i] > 0) out[i] = zone[i];
  }
  return out;
}

/** Fused longitudinal overlay; caller guarantees both planes are on the same grid. */
export function longitudinalRGBA(tp1: Uint8Array, tp2: Uint8Array): Uint8ClampedArray {
  const buf = new Uint8ClampedArray(tp1.length * 4);
  const a = Math.round(0.55 * 255);
  for (let p = 0; p < tp1.length; p++) {
    const in1 = tp1[p] > 0, in2 = tp2[p] > 0;
    if (!in1 && !in2) continue;
    const c = in1 && in2 ? LONGITUDINAL_RGB.persistent : in1 ? LONGITUDINAL_RGB.resolved : LONGITUDINAL_RGB.newLesion;
    const o = p * 4;
    buf[o] = c[0]; buf[o + 1] = c[1]; buf[o + 2] = c[2]; buf[o + 3] = a;
  }
  return buf;
}

/** FLAIR subtraction heat map (uint8, 128 = no change), legacy dead-band and ramps. */
export function subtractionRGBA(plane: Uint8Array): Uint8ClampedArray {
  const buf = new Uint8ClampedArray(plane.length * 4);
  const NEUTRAL = 128, DEAD = 17, MAXA = 0.6 * 255;
  for (let p = 0; p < plane.length; p++) {
    const v = plane[p] - NEUTRAL;
    const o = p * 4;
    if (v > DEAD) {
      const t = Math.min(1, (v - DEAD) / (127 - DEAD));
      buf[o] = 245; buf[o + 1] = 130 - Math.round(60 * t); buf[o + 2] = 40; buf[o + 3] = Math.round(MAXA * t);
    } else if (v < -DEAD) {
      const t = Math.min(1, (-v - DEAD) / (128 - DEAD));
      buf[o] = 60; buf[o + 1] = 130; buf[o + 2] = 245; buf[o + 3] = Math.round(MAXA * t);
    }
  }
  return buf;
}
