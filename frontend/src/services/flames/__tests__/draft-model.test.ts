// @vitest-environment node
/**
 * Hand-over gates of the in-browser FLAMeS draft (HAZ-006 grid/file gate, HAZ-001 provenance)
 * and the model integrity pin (RC-040).
 */
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { buildAiProvenance, checkDraftGrid, draftDescription, DRAFT_LABELS, provenanceRecorded } from '../draft';
import { ModelIntegrityError, sha256Hex, verifyModel } from '../modelStore';
import { FLAMES_FOLD0_MODEL, type FlamesModelAsset } from '../plan';
import type { FlamesProvenance } from '../protocol';

const series = (file_id: string, rows: number, columns: number, slices: number) => ({
  file_id,
  total_slices: slices,
  metadata: { rows, columns },
});

describe('checkDraftGrid', () => {
  it('rc046 accepts the same file with rows=dim1, columns=dim2, slices=dim3', () => {
    const r = checkDraftGrid('p/s/flair.nii.gz', [182, 218, 160], series('p/s/flair.nii.gz', 182, 218, 160));
    expect(r).toEqual({ ok: true, shape: { rows: 182, columns: 218, slices: 160 } });
  });
  it('rc046 refuses another file, a missing viewer, and swapped in-plane dims', () => {
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
    sequenceEvidence: 'clinician',
  };
  it('marks the result as an unreviewed AI draft with model identity, within 1000 chars', () => {
    const d = draftDescription(p, { lesionCount: 85, lesionVoxels: 38892, lesionVolumeMl: 38.892, componentVolumesMl: [] });
    expect(d).toMatch(/^AI DRAFT \(unreviewed\)/);
    expect(d).toContain('2a10bb9d72dc');
    expect(d).toContain('85 lesions');
    expect(d.length).toBeLessThanOrEqual(1000);
    expect(DRAFT_LABELS[1].name).toMatch(/AI draft/);
  });

  const summary = { lesionCount: 3, lesionVoxels: 120, lesionVolumeMl: 0.12, componentVolumesMl: [] };
  it('rc049 records the positive evidence of the sequence with the draft', () => {
    const sent = buildAiProvenance(p, summary, 0);
    expect(sent.sequence_evidence).toBe('clinician');
    expect(sent.review_status).toBe('unreviewed');
    expect(sent.reviewed_mask_sha256).toBeNull();
  });

  it('rc047 accepts only an exact, still-unreviewed echo of the provenance that was sent', () => {
    const sent = buildAiProvenance(p, summary, 0);
    const echo = { ...sent, sequence_confirmed_by: 'dr_rev' };
    expect(provenanceRecorded(sent, echo)).toBe(true);
    expect(provenanceRecorded(sent, null)).toBe(false);
    expect(provenanceRecorded(sent, { ...echo, kind: 'manual' as never })).toBe(false);
    // another model / weights / fold / pipeline / evidence — the record would not describe what produced the mask
    expect(provenanceRecorded(sent, { ...echo, model_sha256: 'f'.repeat(64) })).toBe(false);
    expect(provenanceRecorded(sent, { ...echo, source_checkpoint_sha256: 'e'.repeat(64) })).toBe(false);
    expect(provenanceRecorded(sent, { ...echo, fold: 1 })).toBe(false);
    expect(provenanceRecorded(sent, { ...echo, model_version: 'other' })).toBe(false);
    expect(provenanceRecorded(sent, { ...echo, model_name: 'other' })).toBe(false);
    expect(provenanceRecorded(sent, { ...echo, pipeline_version: 'other' })).toBe(false);
    expect(provenanceRecorded(sent, { ...echo, sequence_evidence: 'header' })).toBe(false);
    // already "confirmed" (or carrying any reviewer trace) — a draft must never arrive pre-confirmed
    expect(provenanceRecorded(sent, { ...echo, review_status: 'confirmed' })).toBe(false);
    expect(provenanceRecorded(sent, { ...echo, reviewed_by: 'dr_rev' })).toBe(false);
    expect(provenanceRecorded(sent, { ...echo, reviewed_at: '2026-10-18T10:00:00Z' })).toBe(false);
    expect(provenanceRecorded(sent, { ...echo, reviewed_mask_sha256: 'a'.repeat(64) })).toBe(false);
  });
});

describe('model integrity pin', () => {
  it('rc040 accepts bytes with the pinned size and SHA-256, rejects any change', async () => {
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
  it('CM: the pin equals the committed export manifest (CMP-001 §6), the model binary is not in git', () => {
    const repo = join(__dirname, '..', '..', '..', '..', '..');
    const manifest = JSON.parse(
      readFileSync(join(repo, 'docs/research/flames-in-browser/evidence/export-fold0-manifest.json'), 'utf-8'),
    );
    expect(manifest.sha256).toBe(FLAMES_FOLD0_MODEL.sha256);
    expect(manifest.bytes).toBe(FLAMES_FOLD0_MODEL.bytes);
    expect(manifest.source_checkpoint_sha256).toBe(FLAMES_FOLD0_MODEL.sourceCheckpointSha256);
    expect(readFileSync(join(repo, '.gitignore'), 'utf-8')).toMatch(/^frontend\/public\/models\/flames\/$/m);
  });
});
