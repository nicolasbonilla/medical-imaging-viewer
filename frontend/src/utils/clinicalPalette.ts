/**
 * ONE colour vocabulary for clinical overlays, legends and tables (viewer v3).
 *
 * Before v3 the same MAGNIMS region was orange in the lesion table (Okabe-Ito) but
 * red in the zone-map legend and on the image — and new-vs-persistent lesions were
 * red-vs-green, the pair ~8% of men cannot tell apart. A legend that disagrees with
 * the picture is a reading hazard, so every surface now takes its colours from here.
 *
 * Palette: Okabe & Ito (2008) colour-universal-design set — distinguishable under
 * the common colour-vision deficiencies and on the dark viewport.
 */

export type RGB = readonly [number, number, number];

export const OKABE_ITO = {
  orange: [230, 159, 0] as RGB,       // #E69F00
  skyBlue: [86, 180, 233] as RGB,     // #56B4E9
  bluishGreen: [0, 158, 115] as RGB,  // #009E73
  yellow: [240, 228, 66] as RGB,      // #F0E442
  blue: [0, 114, 178] as RGB,         // #0072B2
  vermillion: [213, 94, 0] as RGB,    // #D55E00
  reddishPurple: [204, 121, 167] as RGB, // #CC79A7
};

/** MAGNIMS zone label value (zone map / classified lesion mask) -> colour. */
export const MAGNIMS_ZONE_RGB: Record<number, RGB> = {
  1: OKABE_ITO.orange,        // Periventricular
  2: OKABE_ITO.skyBlue,       // Juxtacortical / cortical
  3: OKABE_ITO.bluishGreen,   // Infratentorial
  4: OKABE_ITO.reddishPurple, // Deep white matter
};

export const MAGNIMS_ZONE_NAMES: Record<number, { key: string; abbrev: string; name: string }> = {
  1: { key: 'Periventricular', abbrev: 'PV', name: 'Periventricular' },
  2: { key: 'Juxtacortical', abbrev: 'JC', name: 'Juxtacortical' },
  3: { key: 'Infratentorial', abbrev: 'IT', name: 'Infratentorial' },
  4: { key: 'Deep White Matter', abbrev: 'DWM', name: 'Deep white matter' },
};

/** Longitudinal change: new (TP2 only), resolved (TP1 only), persistent (both). */
export const LONGITUDINAL_RGB = {
  newLesion: OKABE_ITO.vermillion,
  resolved: OKABE_ITO.skyBlue,
  persistent: OKABE_ITO.yellow,
} as const;

/** CALM-MS conformal tiers (1 high, 2 medium, 3 low confidence). */
export const CONFORMAL_TIER_RGB: Record<number, RGB> = {
  1: OKABE_ITO.bluishGreen,
  2: OKABE_ITO.orange,
  3: [148, 163, 184],
};

export function rgbHex(c: RGB): string {
  return `#${c.map((v) => v.toString(16).padStart(2, '0')).join('').toUpperCase()}`;
}

export function rgbCss(c: RGB, alpha = 1): string {
  return alpha >= 1 ? `rgb(${c[0]}, ${c[1]}, ${c[2]})` : `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${alpha})`;
}

/** Region name as used by the lesion analysis (e.g. "Periventricular") -> colour. */
export function regionRgb(region: string): RGB | null {
  const entry = Object.entries(MAGNIMS_ZONE_NAMES).find(([, n]) => n.key === region);
  return entry ? MAGNIMS_ZONE_RGB[Number(entry[0])] ?? null : null;
}
