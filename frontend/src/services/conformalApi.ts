/**
 * CALM-MS conformal second-reader API (INVESTIGATIONAL).
 *
 * Additive population-level lesion-FDR annotation. The backend is dark unless
 * CALM_MS_RESEARCH_ENABLED; every call fails closed (404 dark, 409 provenance,
 * 422 bad preset/prob, 503 null-missing). NEVER a per-lesion probability, never a
 * per-scan realized FDR — the response carries only ordinal tiers + the preset's
 * target and a population-scope string.
 */
import apiClient from './apiClient';
import type { ConformalSummary } from '../store/useSegmentationStore';

export type ConformalPreset = 'high_sensitivity' | 'balanced' | 'high_precision';

export interface ConformalStatusMask {
  mask: Uint8Array;
  dims: { depth: number; height: number; width: number };
}

/** POST /conformal/select — the tiered lesion summary (small JSON). */
export async function runConformalSelect(
  probFileId: string,
  preset: ConformalPreset,
): Promise<ConformalSummary> {
  const { data } = await apiClient.post<ConformalSummary>('/api/v1/conformal/select', {
    prob_file_id: probFileId,
    preset,
  });
  return data;
}

/** POST /conformal/status-mask — the additive tier overlay in [D][H][W]+uint8 framing. */
export async function fetchConformalStatusMask(
  probFileId: string,
  preset: ConformalPreset,
): Promise<ConformalStatusMask> {
  const res = await apiClient.post('/api/v1/conformal/status-mask',
    { prob_file_id: probFileId, preset },
    { responseType: 'arraybuffer' });
  const buf = res.data as ArrayBuffer;
  const header = new DataView(buf, 0, 12);
  const depth = header.getUint32(0, true);
  const height = header.getUint32(4, true);
  const width = header.getUint32(8, true);
  const mask = new Uint8Array(buf, 12);
  return { mask, dims: { depth, height, width } };
}
