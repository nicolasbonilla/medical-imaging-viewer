/**
 * Build the viewer sidebar's segmentation list from raw API summaries.
 */

export interface RawSegmentationSummary {
  segmentation_id: string;
  file_id: string;
  metadata?: { description?: string | null } | null;
}

export interface ViewerSegmentationItem {
  id: string;
  name: string;
  status: 'saved';
  fileId: string;
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
  const all = (rawSegs ?? []).map((seg) => ({
    id: seg.segmentation_id,
    name: seg.metadata?.description || defaultName,
    status: 'saved' as const,
    fileId: seg.file_id,
  }));

  let zoneMapSeen = false;
  return all.filter((seg) => {
    if (seg.name === 'MAGNIMS Zone Map') {
      if (zoneMapSeen) return false;
      zoneMapSeen = true;
    }
    return true;
  });
}
