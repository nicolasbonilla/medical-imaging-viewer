/**
 * PRB-010 — the ONE colour mapping of the MAGNIMS regions, for every place that colours a region:
 * the lesion legend (LesionDashboard), the zone-map legend (MAGNIMSZoneMapPanel), the MAGNIMS label
 * preset, the 2D overlay of a classified segmentation, the 2D zone-map layers and the 3D zone colormap.
 * The backend stores the same colours with the region labels (segmentation_regions.py,
 * MAGNIMS_REGION_LABEL_COLORS — a test checks the two agree).
 *
 * Okabe-Ito colour-blind-safe palette (orange, sky blue, bluish green, vermillion). Before PRB-010 the legend used it but the overlays drew the
 * regions red / green / blue / gold: the picture and the legend disagreed, and periventricular red against
 * juxtacortical green cannot be told apart with red-green colour blindness (about 8 % of men) — the two
 * most common lesion zones, side by side.
 *
 * The `dot` / `text` class strings are literal so Tailwind generates them (it scans this file).
 */
import type { LabelInfo } from '@/types/segmentation';

export const MAGNIMS_REGIONS = ['Periventricular', 'Juxtacortical', 'Infratentorial', 'Deep White Matter'] as const;
export type MagnimsRegion = (typeof MAGNIMS_REGIONS)[number];

export const MAGNIMS_REGION_PALETTE: Readonly<Record<MagnimsRegion, { id: number; hex: string; dot: string; text: string }>> = Object.freeze({
  Periventricular: { id: 1, hex: '#E69F00', dot: 'bg-[#E69F00]', text: 'text-[#F0A800]' },     // orange
  Juxtacortical: { id: 2, hex: '#56B4E9', dot: 'bg-[#56B4E9]', text: 'text-[#7FC7F0]' },       // sky blue
  Infratentorial: { id: 3, hex: '#009E73', dot: 'bg-[#009E73]', text: 'text-[#2DBF97]' },      // bluish green
  'Deep White Matter': { id: 4, hex: '#D55E00', dot: 'bg-[#D55E00]', text: 'text-[#F07A3A]' },     // vermillion
});
// Review of PR #71 (m1): deep white matter was reddish purple #CC79A7. As drawn (36 % over grey tissue) it
// sat only dE76 5.3 from infratentorial bluish green for a deutan reader. With vermillion the worst pair as
// drawn is 9.1 (tritan), 14.3 for normal vision; opaque, every pair stays above 15 for deutan, protan and
// tritan (SegmentationCanvasLocal.prb010.test.tsx).

/** Legend dot classes / text classes by region name (what the two legends render). */
export const REGION_DOT_CLASSES: Readonly<Record<string, string>> = Object.freeze(
  Object.fromEntries(MAGNIMS_REGIONS.map((r) => [r, MAGNIMS_REGION_PALETTE[r].dot])));
export const REGION_TEXT_CLASSES: Readonly<Record<string, string>> = Object.freeze(
  Object.fromEntries(MAGNIMS_REGIONS.map((r) => [r, MAGNIMS_REGION_PALETTE[r].text])));

function regionByName(name: string): MagnimsRegion | undefined {
  const n = name.trim().toLowerCase();
  return MAGNIMS_REGIONS.find((r) => r.toLowerCase() === n);
}

/** Colour of a region, by its name or by its label / zone value (1 PV, 2 JC, 3 IT, 4 DWM). */
export function regionHex(region: string | number): string | undefined {
  if (typeof region === 'number') return MAGNIMS_REGIONS.map((r) => MAGNIMS_REGION_PALETTE[r]).find((p) => p.id === region)?.hex;
  const r = regionByName(region);
  return r ? MAGNIMS_REGION_PALETTE[r].hex : undefined;
}

/** RGBA of zones / region labels 1..4 at alpha `a` (0-255), for the 2D canvas layers. */
export function regionZoneRgba(a: number): Record<number, { r: number; g: number; b: number; a: number }> {
  const out: Record<number, { r: number; g: number; b: number; a: number }> = {};
  for (const region of MAGNIMS_REGIONS) {
    const { id, hex } = MAGNIMS_REGION_PALETTE[region];
    out[id] = { r: parseInt(hex.slice(1, 3), 16), g: parseInt(hex.slice(3, 5), 16), b: parseInt(hex.slice(5, 7), 16), a };
  }
  return out;
}

/**
 * Labels as displayed: a label named after a MAGNIMS region takes the region's colour, whatever colour
 * was stored with it (classified segmentations stored before PRB-010 carry red / green / blue / gold).
 * Other labels are unchanged.
 */
export function withRegionColors<T extends Pick<LabelInfo, 'name' | 'color'>>(labels: T[]): T[] {
  return labels.map((l) => {
    const hex = regionHex(l.name);
    return hex && l.color.toUpperCase() !== hex ? { ...l, color: hex } : l;
  });
}
