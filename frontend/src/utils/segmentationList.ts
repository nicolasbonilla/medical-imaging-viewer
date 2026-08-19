/**
 * Build the viewer sidebar's segmentation list from raw API summaries.
 */

export interface RawSegmentationSummary {
  segmentation_id: string;
  file_id: string;
  metadata?: { description?: string | null; validation_source?: string | null } | null;
}

/**
 * Provenance of a mask — a Class C traceability requirement (mirrors the DICOM
 * Segmentation IOD `Segment Algorithm Type`: MANUAL / SEMIAUTOMATIC / AUTOMATIC +
 * algorithm identification). A clinician must be able to tell, at a glance, whether
 * the lesions they are trusting are a human's, a validated auto-segmenter's, or the
 * known-over-segmenting legacy model.
 *
 * - `expert`    — human ground truth (e.g. "Expert Rater")
 * - `ai`        — a KNOWN, validated automatic tool (FLAMeS / LST-AI / SynthSeg / mindGlide)
 * - `ai-legacy` — the legacy thesis auto-segmenter ("Output Mask … Lesion Prediction"):
 *                 Dice 0.52, **precision 0.22** (over-segments). Surfaced research-only.
 * - `unknown`   — a provenance we cannot vouch for (a `validation_source` that is neither a
 *                 known validated tool nor an explicit manual marker, e.g. the tool runner's
 *                 `'unknown'` fallback). NEVER presented as "validated" — the unsafe direction.
 * - `manual`    — hand-drawn in-app (or no provenance recorded and no algorithmic name cues)
 * - `zonemap`   — the MAGNIMS anatomical zone map (an overlay layer, not a lesion mask)
 */
export type SegOrigin = 'expert' | 'ai' | 'ai-legacy' | 'unknown' | 'manual' | 'zonemap';

export interface ViewerSegmentationItem {
  id: string;
  name: string;
  status: 'saved';
  fileId: string;
  origin: SegOrigin;
}

const ZONE_MAP_NAME = 'MAGNIMS Zone Map';
// Known, validated auto-segmenters (matched in validation_source or the name).
const KNOWN_AUTO_TOOL = /flames|lst[\s_-]?ai|synthseg|mindglide|ms-pinpoint/i;
// The legacy thesis over-segmenter family: the display name "Output Mask N -
// Lesion Prediction" (the word "output"), plus the filename tokens "out_mask" /
// "out-mask". Broadened past a single exact substring so the research-only warning
// does not hinge on one marketing-exact string (adversarial finding: the backend's
// own provenance classifier flags this token set as algorithmic).
const LEGACY_OUTPUT_MASK = /output[\s_-]*mask|(?:^|[\s_-])out[_-]mask/i;

/**
 * Classify a mask's provenance from its name/description and structured
 * `validation_source` (set by the tool runner to e.g. 'flames-v1.0',
 * 'lst-ai-v1.0.3', 'synthseg-v2.0', 'mindglide-v1.0'; 'manual'/'custom-edt' for
 * hand-drawn; 'unknown' on its fallback path). Structured `validation_source` is
 * preferred; the name is the fallback for legacy masks stored before it existed.
 *
 * SAFETY DIRECTION: when provenance is ambiguous we degrade toward LESS trust —
 * an unrecognised source is `unknown` (never `ai`/"validated"), and the legacy
 * over-segmenter is flagged even if a later automatic source is attached. Pure + testable.
 */
export function classifySegOrigin(
  name: string,
  validationSource?: string | null,
): SegOrigin {
  if (name === ZONE_MAP_NAME) return 'zonemap';
  const n = (name || '').toLowerCase();
  const vs = (validationSource || '').toLowerCase();

  // 1. Legacy thesis AI over-segmenter — highest-priority flag (research-only gate),
  //    checked before any "validated" path so it can never be mislabelled as trusted.
  if (LEGACY_OUTPUT_MASK.test(n)) return 'ai-legacy';

  // 2. Human expert ground truth.
  if (n.includes('expert rater') || vs === 'expert') return 'expert';

  // 3. KNOWN validated automatic tools (structured source first, then name).
  if (KNOWN_AUTO_TOOL.test(vs) || KNOWN_AUTO_TOOL.test(n) || n.includes('automated')) return 'ai';

  // 4. Explicit manual markers.
  if (vs === 'manual' || vs === 'custom-edt') return 'manual';

  // 5. A recorded-but-unrecognised source (e.g. the tool runner's 'unknown' fallback).
  //    Do NOT call this "validated" — surface it as unverified.
  if (vs) return 'unknown';

  // 6. No provenance recorded and no algorithmic name cues → treat as manual.
  return 'manual';
}

/**
 * Map raw segmentation summaries to the viewer's item shape and DEDUPE zone
 * maps — only the first "MAGNIMS Zone Map" per study is kept (a study can
 * accumulate several from re-runs, but the sidebar should show one).
 *
 * `defaultName` is injected rather than read from i18n so this stays a pure,
 * unit-testable function. Extracted from an inline IIFE in ViewerApp (Fase 2.2).
 */
export function buildSegmentationList(
  rawSegs: ReadonlyArray<RawSegmentationSummary> | null | undefined,
  defaultName: string,
): ViewerSegmentationItem[] {
  const all = (rawSegs ?? []).map((seg) => {
    const name = seg.metadata?.description || defaultName;
    return {
      id: seg.segmentation_id,
      name,
      status: 'saved' as const,
      fileId: seg.file_id,
      origin: classifySegOrigin(name, seg.metadata?.validation_source),
    };
  });

  let zoneMapSeen = false;
  return all.filter((seg) => {
    if (seg.name === ZONE_MAP_NAME) {
      if (zoneMapSeen) return false;
      zoneMapSeen = true;
    }
    return true;
  });
}
