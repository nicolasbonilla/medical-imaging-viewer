/**
 * Hand-over of an in-browser FLAMeS result to the app's local-first segmentation flow.
 * Pure helpers (unit-tested): grid gate (HAZ-006) and the provenance stamp / draft label (HAZ-001).
 */
import { appShape, type Dims3 } from './axes';
import type { FlamesProvenance } from './protocol';
import type { LesionSummary } from './postprocess';

export interface ViewerSeriesLike {
  file_id?: string;
  total_slices: number;
  metadata: { rows?: number; columns?: number };
}

export type GridCheck = { ok: true; shape: { rows: number; columns: number; slices: number } } | { ok: false; reason: string };

/**
 * The draft may be opened only over the SAME file it was computed from, and only if the viewer's
 * grid (rows = NIfTI dim1, columns = dim2, slices = dim3; backend imaging_service) equals the FLAIR's.
 */
export function checkDraftGrid(resultFileId: string, dims: Dims3, series: ViewerSeriesLike | null): GridCheck {
  if (!series || !series.file_id) return { ok: false, reason: 'Open the FLAIR series in the viewer first.' };
  if (series.file_id !== resultFileId) {
    return { ok: false, reason: 'The viewer shows a different image. Open the FLAIR that was segmented first.' };
  }
  const { depth, height, width } = appShape(dims);
  const rows = series.metadata.rows;
  const columns = series.metadata.columns;
  if (rows !== height || columns !== width || series.total_slices !== depth) {
    return {
      ok: false,
      reason: `Grid mismatch: viewer ${rows}×${columns}×${series.total_slices}, segmentation ${height}×${width}×${depth}. Draft not opened.`,
    };
  }
  return { ok: true, shape: { rows: height, columns: width, slices: depth } };
}

export const DRAFT_LABELS = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
  { id: 1, name: 'Lesion (AI draft, unreviewed)', color: '#FF8C00', opacity: 0.5, visible: true },
];

/** Stored as the segmentation description (max 1000 chars on the server). */
export function draftDescription(p: FlamesProvenance, s: LesionSummary): string {
  const text =
    `AI DRAFT (unreviewed) — ${p.model}, in-browser ${p.pipeline}; model sha256 ${p.modelSha256.slice(0, 12)}; ` +
    `${p.backend === 'webgpu' ? 'WebGPU' : `WebAssembly x${p.threads}`}${p.mirror ? ', mirroring TTA' : ''}; ` +
    `${s.lesionCount} lesions, ${s.lesionVolumeMl.toFixed(2)} mL; ${p.generatedAt}. ` +
    'Research prototype: must be reviewed and edited by a clinician before any use.';
  return text.slice(0, 1000);
}
