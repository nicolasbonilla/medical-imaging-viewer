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
  let res;
  try {
    res = await apiClient.post('/api/v1/conformal/status-mask',
      { prob_file_id: probFileId, preset },
      { responseType: 'arraybuffer' });
  } catch (e: unknown) {
    // responseType:'arraybuffer' also decodes 4xx/5xx bodies as ArrayBuffer, so the
    // JSON `detail` is unreadable unless we decode it — re-attach it for the caller.
    const err = e as { response?: { data?: unknown } };
    const data = err?.response?.data;
    if (data instanceof ArrayBuffer) {
      try {
        const parsed = JSON.parse(new TextDecoder().decode(data));
        if (err.response) err.response.data = parsed;
      } catch { /* leave as-is if not JSON */ }
    }
    throw e;
  }
  const buf = res.data as ArrayBuffer;
  if (buf.byteLength < 12) throw new Error('conformal status-mask: truncated header');
  const header = new DataView(buf, 0, 12);
  const depth = header.getUint32(0, true);
  const height = header.getUint32(4, true);
  const width = header.getUint32(8, true);
  const expected = depth * height * width;
  if (buf.byteLength - 12 !== expected) {
    throw new Error(`conformal status-mask: body ${buf.byteLength - 12} != expected ${expected}`);
  }
  const mask = new Uint8Array(buf, 12);
  return { mask, dims: { depth, height, width } };
}
