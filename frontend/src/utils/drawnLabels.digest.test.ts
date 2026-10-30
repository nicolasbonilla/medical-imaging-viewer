// @vitest-environment node
/**
 * Release 2026-10-25 — final check of PR #69 (dd22708..39d9730), R2 (server-side part).
 *
 * The confirmation states the label table the mask was DRAWN with: `drawn_labels_sha256`, the SHA-256 of
 * [id, name, colour] of every label but the background, by id — the same canonical text as the server's
 * `dis_review_gate.drawn_labels_sha256` (backend/tests/unit/test_release_2026_10_25_final_check.py uses the same
 * vector). The server refuses a confirmation drawn with another table (e.g. the "Default" preset).
 *
 * Written before the correction (fails on 39d9730). Node environment: Web Crypto as in the browser.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const post = vi.fn();
vi.mock('@/services/apiClient', () => ({ apiClient: { post: (...a: unknown[]) => post(...a) } }));

import * as drawn from './drawnLabels';
import { segmentationAPI } from '@/api/segmentation';
// Release 2026-10-30 (merge with #71): the MAGNIMS preset now carries #71's shared region colours, so the shared
// vector is computed on this fixed table (the colours of the vector), not on the preset.
const MAGNIMS_TABLE = [
  { id: 0, name: 'Background', color: '#000000' }, { id: 1, name: 'Periventricular', color: '#FF0000' },
  { id: 2, name: 'Juxtacortical', color: '#00CC00' }, { id: 3, name: 'Infratentorial', color: '#0066FF' },
  { id: 4, name: 'Deep White Matter', color: '#FFD700' }, { id: 5, name: 'Active (Gd+)', color: '#FF00FF' },
  { id: 6, name: 'Black Hole (T1)', color: '#9932CC' },
];
const DEFAULT_TABLE = [
  { id: 0, name: 'Background', color: '#000000' }, { id: 1, name: 'MS Lesion (Active)', color: '#FF0000' },
  { id: 2, name: 'MS Lesion (Chronic)', color: '#FFD700' }, { id: 3, name: 'T2/FLAIR Hyperintensity', color: '#4169E1' },
  { id: 4, name: 'Black Hole (T1)', color: '#9932CC' },
];
const DEFAULT_LABEL_PRESETS = { magnims: MAGNIMS_TABLE, default: DEFAULT_TABLE };

const MAGNIMS_TEXT = '[[1,"Periventricular","#FF0000"],[2,"Juxtacortical","#00CC00"],[3,"Infratentorial","#0066FF"],'
  + '[4,"Deep White Matter","#FFD700"],[5,"Active (Gd+)","#FF00FF"],[6,"Black Hole (T1)","#9932CC"]]';
const MAGNIMS_SHA = '72bdfec92427dae7278166fdb50768a2bfdef44e3899db765ec5549ef906051d';
const DEFAULT_SHA = '008ef1592a098da2e85e6264e3e358c05fb093079715e14e2d1e77db13551f99';

const api = drawn as unknown as {
  drawnLabelsCanonical: (labels: unknown[]) => string;
  drawnLabelsSha256: (labels: unknown[]) => Promise<string>;
};

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({ data: { success: true, clinician_review: { reviewed_by: 'dr' } } });
});

describe('R2: the label table the mask was drawn with, as the server digests it', () => {
  it('rc071 release final the canonical text and its digest match the server', async () => {
    expect(api.drawnLabelsCanonical(DEFAULT_LABEL_PRESETS.magnims)).toBe(MAGNIMS_TEXT);
    expect(await api.drawnLabelsSha256(DEFAULT_LABEL_PRESETS.magnims)).toBe(MAGNIMS_SHA);
    expect(await api.drawnLabelsSha256(DEFAULT_LABEL_PRESETS.default)).toBe(DEFAULT_SHA);
  });

  it('rc071 release final the digest ignores order and colour case, not names or colours', async () => {
    const shuffled = [...DEFAULT_LABEL_PRESETS.magnims].reverse().map((l) => ({ ...l, color: l.color.toLowerCase() }));
    expect(await api.drawnLabelsSha256(shuffled)).toBe(MAGNIMS_SHA);
    const recoloured = DEFAULT_LABEL_PRESETS.magnims.map((l) => (l.id === 2 ? { ...l, color: '#FFD700' } : l));
    expect(await api.drawnLabelsSha256(recoloured)).not.toBe(MAGNIMS_SHA);
  });

  it('rc071 release final the confirmation sends the digest of the drawn table', async () => {
    await segmentationAPI.confirmSegmentationReview('seg-1', 'a'.repeat(64), null, DEFAULT_LABEL_PRESETS.magnims as never);
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][1]).toEqual({ mask_sha256: 'a'.repeat(64), drawn_labels_sha256: MAGNIMS_SHA });
    await segmentationAPI.confirmSegmentationReview('seg-1', 'a'.repeat(64), 'c'.repeat(64), DEFAULT_LABEL_PRESETS.default as never);
    expect(post.mock.calls[1][1]).toEqual({
      mask_sha256: 'a'.repeat(64), region_corrections_sha256: 'c'.repeat(64), drawn_labels_sha256: DEFAULT_SHA,
    });
  });
});
