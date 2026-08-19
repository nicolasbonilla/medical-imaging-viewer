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
 * - `ai`        — a validated automatic tool (FLAMeS / LST-AI / SynthSeg / mindGlide)
 * - `ai-legacy` — the legacy thesis auto-segmenter ("Output Mask"): Dice 0.52,
 *                 **precision 0.22** (over-segments). Must be surfaced research-only.
 * - `manual`    — hand-drawn in-app
 * - `zonemap`   — the MAGNIMS anatomical zone map (an overlay layer, not a lesion mask)
 */
export type SegOrigin = 'expert' | 'ai' | 'ai-legacy' | 'manual' | 'zonemap';

export interface ViewerSegmentationItem {
  id: string;
  name: string;
  status: 'saved';
  fileId: string;
  origin: SegOrigin;
}

const ZONE_MAP_NAME = 'MAGNIMS Zone Map';
const AUTO_TOOL = /flames|lst[\s_-]?ai|synthseg|mindglide|ms-pinpoint/i;

/**
 * Classify a mask's provenance from its name/description and structured
 * `validation_source` (set by the tool runner to e.g. 'flames-v1.0',
 * 'lst-ai-v1.0.3', 'synthseg-v2.0', 'mindglide-v1.0'; 'manual'/'custom-edt' for
 * hand-drawn). Structured `validation_source` is preferred; the name is the
 * fallback for legacy masks stored before that field existed. Pure + testable.
 */
export function classifySegOrigin(
  name: string,
  validationSource?: string | null,
): SegOrigin {
  if (name === ZONE_MAP_NAME) return 'zonemap';
  const n = (name || '').toLowerCase();
  const vs = (validationSource || '').toLowerCase();

  // Legacy thesis AI over-segmenter — highest-priority flag (research-only gate).
  if (n.includes('output mask')) return 'ai-legacy';

  // Human expert ground truth.
  if (n.includes('expert rater') || vs === 'expert') return 'expert';

  // Validated automatic tools — structured source first, then name heuristics.
  if (AUTO_TOOL.test(vs) || AUTO_TOOL.test(n) || n.includes('automated')) return 'ai';
  if (vs && vs !== 'manual' && vs !== 'custom-edt') return 'ai';

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
