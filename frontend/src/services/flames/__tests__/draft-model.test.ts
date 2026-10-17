// @vitest-environment node
/**
 * Hand-over gates of the in-browser FLAMeS draft (HAZ-006 grid/file gate, HAZ-001 provenance)
 * and the model integrity pin (RC-F1).
 */
import { describe, expect, it } from 'vitest';
import { checkDraftGrid, draftDescription, DRAFT_LABELS } from '../draft';
import { ModelIntegrityError, sha256Hex, verifyModel } from '../modelStore';
import { FLAMES_FOLD0_MODEL, type FlamesModelAsset } from '../plan';
import type { FlamesProvenance } from '../protocol';

const series = (file_id: string, rows: number, columns: number, slices: number) => ({
  file_id,
  total_slices: slices,
  metadata: { rows, columns },
});

describe('checkDraftGrid', () => {
  it('accepts the same file with rows=dim1, columns=dim2, slices=dim3', () => {
    const r = checkDraftGrid('p/s/flair.nii.gz', [182, 218, 160], series('p/s/flair.nii.gz', 182, 218, 160));
    expect(r).toEqual({ ok: true, shape: { rows: 182, columns: 218, slices: 160 } });
  });
  it('refuses another file, a missing viewer, and swapped in-plane dims', () => {
    expect(checkDraftGrid('a', [10, 12, 14], series('b', 10, 12, 14)).ok).toBe(false);
    expect(checkDraftGrid('a', [10, 12, 14], null).ok).toBe(false);
    expect(checkDraftGrid('a', [10, 12, 14], series('a', 12, 10, 14)).ok).toBe(false);
    expect(checkDraftGrid('a', [10, 12, 14], series('a', 10, 12, 15)).ok).toBe(false);
  });
});

describe('draft provenance', () => {
  const p: FlamesProvenance = {
    pipeline: 'mstool-flames-browser/0.1.0-prototype',
    model: 'FLAMeS fold 0 (Zenodo 10.5281/zenodo.17955359 v2.0, CC BY 4.0)',
    modelSha256: FLAMES_FOLD0_MODEL.sha256,
    sourceCheckpointSha256: FLAMES_FOLD0_MODEL.sourceCheckpointSha256,
    backend: 'wasm',
    threads: 8,
    onnxRuntimeWeb: '1.24.1',
    mirror: false,
    windows: 8,
    networkCalls: 8,
    resampledShape: [142, 174, 200],
    seconds: 266,
    generatedAt: '2026-10-17T20:00:00.000Z',
  };
  it('marks the result as an unreviewed AI draft with model identity, within 1000 chars', () => {
    const d = draftDescription(p, { lesionCount: 85, lesionVoxels: 38892, lesionVolumeMl: 38.892, componentVolumesMl: [] });
    expect(d).toMatch(/^AI DRAFT \(unreviewed\)/);
    expect(d).toContain('2a10bb9d72dc');
    expect(d).toContain('85 lesions');
    expect(d.length).toBeLessThanOrEqual(1000);
    expect(DRAFT_LABELS[1].name).toMatch(/AI draft/);
  });
});

describe('model integrity pin', () => {
  it('accepts bytes with the pinned size and SHA-256, rejects any change', async () => {
    const bytes = new TextEncoder().encode('not a real model, just pinned bytes');
    const asset: FlamesModelAsset = { ...FLAMES_FOLD0_MODEL, bytes: bytes.length, sha256: await sha256Hex(bytes) };
    await expect(verifyModel(bytes, asset)).resolves.toBeUndefined();
    const tampered = bytes.slice();
    tampered[3] ^= 1;
    await expect(verifyModel(tampered, asset)).rejects.toBeInstanceOf(ModelIntegrityError);
    await expect(verifyModel(bytes.subarray(1), asset)).rejects.toThrow(/size/);
  });
  it('pins the exported fold-0 artefact', () => {
    expect(FLAMES_FOLD0_MODEL.sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(FLAMES_FOLD0_MODEL.bytes).toBe(61642305);
    expect(FLAMES_FOLD0_MODEL.url).toContain(FLAMES_FOLD0_MODEL.sha256.slice(0, 8));
  });
});
