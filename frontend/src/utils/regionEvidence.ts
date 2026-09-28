/**
 * RC-010 (amended) / HAZ-005 / REQ-SAFE-010 (amended) — what the lesion table shows in the
 * region-evidence column.
 *
 * MAGNIMS region assignment is a deterministic rule; there is no calibrated per-lesion
 * probability, so the UI never renders a "confidence". MSMask lesions carry the fraction of their
 * voxels inside the assigned zone (descriptive; a low value is normal under the contact rule).
 * A lesion that lies in no white-matter zone was assigned Deep White Matter BY DEFAULT — the only
 * per-lesion signal of a possible DIS false negative — so it is surfaced as a data-quality warning.
 * A `confidence` value on the object is deliberately IGNORED, even if a (stale) backend sends one.
 */
export interface RegionEvidenceInput {
  region_overlap_fraction?: number | null;
  atlas_coverage?: boolean;
  confidence?: number | null;
}

export type RegionEvidence =
  | { kind: 'overlap'; value: number }
  | { kind: 'outsideZones' }
  | { kind: 'none' };

export function regionEvidence(cl: RegionEvidenceInput): RegionEvidence {
  if (cl.atlas_coverage === false) return { kind: 'outsideZones' };
  if (cl.region_overlap_fraction != null) return { kind: 'overlap', value: cl.region_overlap_fraction };
  return { kind: 'none' };
}

export const REGION_ABBREV: Record<string, string> = {
  Periventricular: 'PV',
  Juxtacortical: 'JC',
  Infratentorial: 'IT',
  'Deep White Matter': 'DWM',
};
