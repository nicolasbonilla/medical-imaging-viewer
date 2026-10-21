/**
 * Hand-over of an in-browser FLAMeS result to the app's local-first segmentation flow.
 * Pure helpers (unit-tested): grid gate (HAZ-006), the provenance stamp / draft label and the
 * persisted AI provenance (HAZ-001, REQ-SAFE-030), the empty-result wording (REQ-FUNC-036).
 */
import { appShape, type Dims3 } from './axes';
import type { FlamesProvenance } from './protocol';
import type { LesionSummary } from './postprocess';
import type { AIProvenance } from '@/types';

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

/** An empty result is never a silent "0 lesions" (REQ-FUNC-036). */
export function isEmptyResult(s: LesionSummary): boolean {
  return s.lesionVoxels === 0 || s.lesionCount === 0;
}

export const EMPTY_RESULT_WARNING =
  'The AI found NO lesion. This does NOT show that the scan is free of lesions: the model can return nothing ' +
  'when the image is not a suitable FLAIR, is degraded, or when the model failed. Review the FLAIR yourself.';

/** Stored as the segmentation description (max 1000 chars on the server). */
export function draftDescription(p: FlamesProvenance, s: LesionSummary): string {
  const result = isEmptyResult(s)
    ? 'EMPTY RESULT: 0 lesions, 0 voxels — not a confirmation of a lesion-free scan'
    : `${s.lesionCount} lesions, ${s.lesionVolumeMl.toFixed(2)} mL (${s.lesionVoxels} voxels)`;
  const text =
    `AI DRAFT (unreviewed) — ${p.model}, in-browser ${p.pipeline}; model sha256 ${p.modelSha256.slice(0, 12)}; ` +
    `${p.backend === 'webgpu' ? 'WebGPU' : `WebAssembly x${p.threads}`}${p.mirror ? ', mirroring TTA' : ''}; ` +
    `${result}; ${p.generatedAt}. ` +
    'Research prototype: must be reviewed and edited by a clinician before any use.';
  return text.slice(0, 1000);
}

/** Model identity fields stored with every AI draft (FLAMeS Zenodo record, version 2.0). */
export const FLAMES_MODEL_NAME = 'FLAMeS';
export const FLAMES_MODEL_VERSION = 'Zenodo 10.5281/zenodo.17955359 v2.0 (Dataset004_WML)';

/**
 * Provenance persisted with the segmentation when the clinician explicitly saves the draft.
 * Always 'unreviewed' here; only an explicit confirmation can change that (server-side).
 */
export function buildAiProvenance(p: FlamesProvenance, s: LesionSummary, fold: number): AIProvenance {
  return {
    kind: 'ai_draft',
    model_name: FLAMES_MODEL_NAME,
    model_version: FLAMES_MODEL_VERSION,
    model_sha256: p.modelSha256,
    fold,
    source_checkpoint_sha256: p.sourceCheckpointSha256,
    pipeline_version: p.pipeline,
    runtime:
      `onnxruntime-web ${p.onnxRuntimeWeb} ${p.backend === 'webgpu' ? 'webgpu' : `wasm x${p.threads}`}` +
      `${p.mirror ? ' mirror-tta' : ''}${p.fallbackReason ? ' (webgpu fallback)' : ''}`,
    generated_at: p.generatedAt,
    lesion_count: s.lesionCount,
    annotated_voxels: s.lesionVoxels,
    review_status: 'unreviewed',
    reviewed_by: null,
    reviewed_at: null,
    reviewed_mask_sha256: null,
    sequence_evidence: p.sequenceEvidence,
  };
}

/** True for any segmentation that carries AI provenance (local draft or saved AI segmentation). */
export function isAiSegmentation(meta: { ai_provenance?: AIProvenance | null } | null | undefined): boolean {
  return Boolean(meta?.ai_provenance && meta.ai_provenance.kind === 'ai_draft');
}

/**
 * The server's echo of a saved draft must carry EXACTLY the model identity that was sent and must still be
 * 'unreviewed' with no reviewer and no reviewed-mask hash; anything else (another model hash, another fold,
 * an already "confirmed" record) is rejected and the save fails closed (REQ-SAFE-030).
 */
export function provenanceRecorded(sent: AIProvenance, echoed: AIProvenance | null | undefined): boolean {
  if (!echoed || echoed.kind !== 'ai_draft') return false;
  const sameModel =
    echoed.model_name === sent.model_name &&
    echoed.model_version === sent.model_version &&
    echoed.model_sha256 === sent.model_sha256 &&
    echoed.fold === sent.fold &&
    echoed.source_checkpoint_sha256 === sent.source_checkpoint_sha256 &&
    echoed.pipeline_version === sent.pipeline_version &&
    echoed.sequence_evidence === sent.sequence_evidence;
  const stillUnreviewed =
    echoed.review_status === 'unreviewed' && !echoed.reviewed_by && !echoed.reviewed_at && !echoed.reviewed_mask_sha256;
  return sameModel && stillUnreviewed;
}
