/**
 * Hand-off of the in-browser FLAMeS AI draft into the segmentation flow (CP-FLAMES-BROWSER-001).
 *
 * Behavioural contract (REQ-SAFE-030, REQ-SAFE-032; HAZ-001):
 *  1. an AI draft is NEVER saved without an explicit clinician action — closing/reloading the tab
 *     only shows the browser's "leave page?" warning, it does not autosave the draft;
 *  2. when the clinician saves it, it is stored with its AI provenance (model, version, SHA-256, fold,
 *     'unreviewed'); a server that does not record the provenance gets no draft (the orphan is removed);
 *  3. while open it is 'automatic' with its provenance, never 'manual';
 *  4. opening a draft never discards unsaved work: nothing is touched unless the clinician explicitly
 *     chooses to discard (discardUnsavedWork);
 *  5. the server echo must be EXACTLY the provenance sent and still unreviewed (another model hash, or an
 *     already "confirmed" record, is refused);
 *  6. a confirmed review is bound to the saved mask: after saving changed voxels the provenance is re-read
 *     (the server resets it to unreviewed), and the banner gets the unsaved flag and the mask digest.
 *
 * Negative controls (recorded in docs/research/flames-in-browser/evidence/handoff-negative-controls.json):
 * restore the d81cb78 versions of useSegmentationData.ts and these tests fail.
 */
import React from 'react';
import { createHash } from 'node:crypto';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiGet = vi.fn();
const apiPut = vi.fn();
vi.mock('@/services/apiClient', () => ({
  apiClient: { get: (...a: unknown[]) => apiGet(...a), put: (...a: unknown[]) => apiPut(...a), post: vi.fn() },
}));

const createSegmentation = vi.fn();
const deleteSegmentation = vi.fn();
const getSegmentation = vi.fn();
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    createSegmentation: (...a: unknown[]) => createSegmentation(...a),
    deleteSegmentation: (...a: unknown[]) => deleteSegmentation(...a),
    getSegmentation: (...a: unknown[]) => getSegmentation(...a),
    listSegmentationsByFileIds: vi.fn().mockResolvedValue([]),
  },
}));

import { useSegmentationData } from './useSegmentationData';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { useViewerStore } from '@/store/useViewerStore';
import type { AIProvenance } from '@/types';

const FILE = 'patients/p1/studies/s1/flair.nii.gz';
const SHAPE = { rows: 4, columns: 5, slices: 3 };
const N = SHAPE.rows * SHAPE.columns * SHAPE.slices;

const PROVENANCE: AIProvenance = {
  kind: 'ai_draft',
  model_name: 'FLAMeS',
  model_version: 'Zenodo 10.5281/zenodo.17955359 v2.0 (Dataset004_WML)',
  model_sha256: '2a10bb9d72dc33381a3f44dd6a59ec612dfd87534e02f15488b426ae127176ae',
  fold: 0,
  source_checkpoint_sha256: '4fc7db24e7c1541b59023df2a2f498a964eb629fe38f4eaec763297dd3fdf861',
  pipeline_version: 'mstool-flames-browser/0.2.0-prototype',
  runtime: 'onnxruntime-web 1.24.1 wasm x1',
  generated_at: '2026-10-17T20:00:00.000Z',
  lesion_count: 1,
  annotated_voxels: 2,
  review_status: 'unreviewed',
  reviewed_by: null,
  reviewed_at: null,
  reviewed_mask_sha256: null,
  sequence_evidence: 'clinician',
};

function draftMask(): Uint8Array {
  const m = new Uint8Array(N);
  m[7] = 1;
  m[8] = 1;
  return m;
}

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function serverEcho(withProvenance: boolean, override: Partial<AIProvenance> = {}) {
  return (req: { file_id: string; description?: string; labels?: unknown; ai_provenance?: AIProvenance }) =>
    Promise.resolve({
      segmentation_id: 'server-1',
      file_id: req.file_id,
      total_slices: SHAPE.slices,
      metadata: {
        file_id: req.file_id,
        created_at: 'x',
        modified_at: 'x',
        labels: req.labels ?? [],
        description: req.description,
        ...(withProvenance && req.ai_provenance
          ? { segmentation_type: 'automatic', ai_provenance: { ...req.ai_provenance, review_status: 'unreviewed', ...override } }
          : {}),
      },
    });
}

function importDraft(options?: { discardUnsavedWork?: boolean }) {
  const cb = useSegmentationStore.getState().importDraftCallback!;
  return cb(
    FILE,
    SHAPE,
    draftMask(),
    { description: 'AI DRAFT (unreviewed) — FLAMeS fold 0', labels: undefined, aiProvenance: PROVENANCE },
    options,
  );
}

function fireBeforeUnload(): Event {
  const ev = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(ev);
  return ev;
}

describe('FLAMeS AI draft hand-off (REQ-SAFE-030, REQ-SAFE-032)', () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPut.mockReset();
    createSegmentation.mockReset();
    deleteSegmentation.mockReset();
    getSegmentation.mockReset();
    deleteSegmentation.mockResolvedValue(undefined);
    apiPut.mockResolvedValue({ data: { durable: true, generation: 1 } });
    useSegmentationStore.getState().reset?.();
    useSegmentationStore.setState({ currentSegmentation: null, activeSegmentation: null });
    useViewerStore.setState({ currentStudyId: 's1', allFileIds: [], currentSeries: null });
  });

  it('rc047 closing or reloading the tab never saves an opened AI draft (only warns)', async () => {
    createSegmentation.mockImplementation(serverEcho(true));
    const { result } = renderHook(() => useSegmentationData({}), { wrapper });
    act(() => {
      importDraft();
    });
    expect(result.current.hasUnsavedChanges).toBe(true);

    const ev = fireBeforeUnload();
    await act(async () => {
      await Promise.resolve();
    });

    expect(createSegmentation).not.toHaveBeenCalled();
    expect(apiPut).not.toHaveBeenCalled();
    expect(ev.defaultPrevented).toBe(true); // the browser still warns that unsaved work would be lost
  });

  it('rc047 an edited AI draft is not autosaved either', async () => {
    createSegmentation.mockImplementation(serverEcho(true));
    const { result } = renderHook(() => useSegmentationData({}), { wrapper });
    act(() => {
      importDraft();
    });
    act(() => {
      result.current.segmentationMask.paintStroke({ x: 0, y: 0, sliceIndex: 0, brushSize: 1, labelId: 1, erase: false });
    });
    fireBeforeUnload();
    await act(async () => {
      await Promise.resolve();
    });
    expect(createSegmentation).not.toHaveBeenCalled();
  });

  it('control: a MANUAL unsaved segmentation keeps its best-effort save on unload', async () => {
    createSegmentation.mockImplementation(serverEcho(false));
    const { result } = renderHook(() => useSegmentationData({}), { wrapper });
    act(() => {
      result.current.createSegmentation(FILE, SHAPE);
    });
    act(() => {
      result.current.segmentationMask.paintStroke({ x: 1, y: 1, sliceIndex: 1, brushSize: 1, labelId: 1, erase: false });
    });
    fireBeforeUnload();
    await act(async () => {
      await Promise.resolve();
    });
    expect(createSegmentation).toHaveBeenCalledTimes(1);
    expect(createSegmentation.mock.calls[0][0].ai_provenance).toBeUndefined();
  });

  it('rc047 while open the draft is "automatic" with its provenance, never "manual"', () => {
    renderHook(() => useSegmentationData({}), { wrapper });
    act(() => {
      importDraft();
    });
    const active = useSegmentationStore.getState().activeSegmentation!;
    expect(active.segmentation_type).toBe('automatic');
    expect(active.ai_provenance?.model_sha256).toBe(PROVENANCE.model_sha256);
    expect(active.ai_provenance?.review_status).toBe('unreviewed');
  });

  it('rc047 an explicit Save stores the draft WITH its AI provenance (model, version, SHA-256, fold, unreviewed)', async () => {
    createSegmentation.mockImplementation(serverEcho(true));
    const { result } = renderHook(() => useSegmentationData({}), { wrapper });
    act(() => {
      importDraft();
    });
    await act(async () => {
      await result.current.saveSegmentation();
    });
    expect(createSegmentation).toHaveBeenCalledTimes(1);
    const req = createSegmentation.mock.calls[0][0];
    expect(req.ai_provenance).toMatchObject({
      kind: 'ai_draft',
      model_name: 'FLAMeS',
      model_version: PROVENANCE.model_version,
      model_sha256: PROVENANCE.model_sha256,
      fold: 0,
      review_status: 'unreviewed',
    });
    expect(apiPut).toHaveBeenCalledTimes(1); // the mask itself is uploaded only after the provenance is recorded
    expect(useSegmentationStore.getState().currentSegmentation?.metadata.ai_provenance?.model_sha256).toBe(
      PROVENANCE.model_sha256,
    );
  });

  it('rc047 a server that does not record the provenance gets no draft (orphan removed, mask not uploaded)', async () => {
    createSegmentation.mockImplementation(serverEcho(false));
    const { result } = renderHook(() => useSegmentationData({}), { wrapper });
    act(() => {
      importDraft();
    });
    await act(async () => {
      await result.current.saveSegmentation();
    });
    expect(deleteSegmentation).toHaveBeenCalledWith('server-1');
    expect(apiPut).not.toHaveBeenCalled();
    expect(result.current.saveStatus).toBe('error');
    expect(result.current.hasUnsavedChanges).toBe(true); // the draft stays on screen, unsaved
  });

  it.each([
    ['another model hash', { model_sha256: 'f'.repeat(64) }],
    ['another fold', { fold: 1 }],
    ['an already "confirmed" review', { review_status: 'confirmed' as const, reviewed_by: 'someone' }],
  ])('rc047 a server echo with %s is refused (orphan removed, mask not uploaded)', async (_label, override) => {
    createSegmentation.mockImplementation(serverEcho(true, override as Partial<AIProvenance>));
    const { result } = renderHook(() => useSegmentationData({}), { wrapper });
    act(() => {
      importDraft();
    });
    await act(async () => {
      await result.current.saveSegmentation();
    });
    expect(deleteSegmentation).toHaveBeenCalledWith('server-1');
    expect(apiPut).not.toHaveBeenCalled();
    expect(result.current.saveStatus).toBe('error');
  });

  function maskBuffer(): ArrayBuffer {
    const buf = new ArrayBuffer(12 + N);
    const dv = new DataView(buf);
    dv.setUint32(0, SHAPE.slices, true);
    dv.setUint32(4, SHAPE.rows, true);
    dv.setUint32(8, SHAPE.columns, true);
    new Uint8Array(buf, 12).set(draftMask());
    return buf;
  }

  const CONFIRMED: AIProvenance = {
    ...PROVENANCE,
    review_status: 'confirmed',
    reviewed_by: 'dr_rev',
    reviewed_at: '2026-10-18T09:00:00Z',
    reviewed_mask_sha256: createHash('sha256').update(draftMask()).digest('hex'),
  };

  async function openSavedAiSegmentation() {
    apiGet.mockResolvedValue({ data: maskBuffer(), headers: {} });
    const hook = renderHook(() => useSegmentationData({}), { wrapper });
    await act(async () => {
      useSegmentationStore.getState().setCurrentSegmentation({
        segmentation_id: 'saved-ai-9',
        file_id: FILE,
        total_slices: SHAPE.slices,
        metadata: {
          file_id: FILE,
          created_at: 'x',
          modified_at: 'x',
          labels: [],
          description: 'AI draft',
          segmentation_type: 'automatic',
          ai_provenance: CONFIRMED,
        },
      });
    });
    await act(async () => {
      await Promise.resolve();
    });
    return hook;
  }

  it('rc047 saving corrections to a confirmed AI segmentation re-reads the provenance: the review shows as reset', async () => {
    const { result } = await openSavedAiSegmentation();
    expect(useSegmentationStore.getState().currentSegmentation?.metadata.ai_provenance?.review_status).toBe('confirmed');
    getSegmentation.mockResolvedValue({
      segmentation_id: 'saved-ai-9',
      metadata: {
        ai_provenance: { ...CONFIRMED, review_status: 'unreviewed', reviewed_by: null, reviewed_at: null, reviewed_mask_sha256: null },
      },
    });
    act(() => {
      result.current.segmentationMask.paintStroke({ x: 0, y: 0, sliceIndex: 0, brushSize: 1, labelId: 1, erase: false });
    });
    await act(async () => {
      await result.current.saveSegmentation();
    });
    expect(apiPut).toHaveBeenCalledTimes(1);
    expect(getSegmentation).toHaveBeenCalledWith('saved-ai-9');
    const prov = useSegmentationStore.getState().currentSegmentation?.metadata.ai_provenance;
    expect(prov?.review_status).toBe('unreviewed');
    expect(prov?.reviewed_by).toBeNull();
  });

  it('rc047 if the provenance cannot be re-read after a save, the review is shown as NOT confirmed (fail safe)', async () => {
    const { result } = await openSavedAiSegmentation();
    getSegmentation.mockRejectedValue(new Error('network down'));
    act(() => {
      result.current.segmentationMask.paintStroke({ x: 0, y: 0, sliceIndex: 0, brushSize: 1, labelId: 1, erase: false });
    });
    await act(async () => {
      await result.current.saveSegmentation();
    });
    const prov = useSegmentationStore.getState().currentSegmentation?.metadata.ai_provenance;
    expect(prov?.review_status).toBe('unreviewed');
    expect(prov?.reviewed_mask_sha256).toBeNull();
  });

  it('rc047 the banner gets the unsaved-changes flag and the SHA-256 of the exact mask bytes on screen', async () => {
    const { result } = await openSavedAiSegmentation();
    const digest = useSegmentationStore.getState().maskDigestCallback!;
    expect(await digest()).toBe(CONFIRMED.reviewed_mask_sha256); // same bytes as the server hashes
    expect(useSegmentationStore.getState().hasUnsavedMaskChanges).toBe(false);
    act(() => {
      result.current.segmentationMask.paintStroke({ x: 0, y: 0, sliceIndex: 0, brushSize: 1, labelId: 1, erase: false });
    });
    expect(useSegmentationStore.getState().hasUnsavedMaskChanges).toBe(true);
    expect(await digest()).not.toBe(CONFIRMED.reviewed_mask_sha256);
  });

  it('rc050 opening a draft never discards unsaved work in a new manual segmentation', () => {
    const { result } = renderHook(() => useSegmentationData({}), { wrapper });
    act(() => {
      result.current.createSegmentation(FILE, SHAPE);
    });
    const manual = useSegmentationStore.getState().currentSegmentation!;
    act(() => {
      result.current.segmentationMask.paintStroke({ x: 2, y: 3, sliceIndex: 2, brushSize: 1, labelId: 1, erase: false });
    });

    let outcome: unknown;
    act(() => {
      outcome = importDraft();
    });
    expect(outcome).toEqual({ ok: false, reason: 'unsaved-work', openSegmentationName: 'Segmentation' });
    // nothing was touched: same segmentation, painted voxel still there, still dirty
    expect(useSegmentationStore.getState().currentSegmentation).toBe(manual);
    expect(result.current.segmentationMask.getVoxel(2, 3, 2)).toBe(1);
    expect(result.current.hasUnsavedChanges).toBe(true);
  });

  it('rc050 unsaved edits in a SAVED segmentation are protected too; explicit discard replaces them', async () => {
    const buf = new ArrayBuffer(12 + N);
    const dv = new DataView(buf);
    dv.setUint32(0, SHAPE.slices, true);
    dv.setUint32(4, SHAPE.rows, true);
    dv.setUint32(8, SHAPE.columns, true);
    apiGet.mockResolvedValue({ data: buf, headers: {} });
    const { result } = renderHook(() => useSegmentationData({}), { wrapper });
    await act(async () => {
      useSegmentationStore.getState().setCurrentSegmentation({
        segmentation_id: 'saved-7',
        file_id: FILE,
        total_slices: SHAPE.slices,
        metadata: { file_id: FILE, created_at: 'x', modified_at: 'x', labels: [], description: 'Dr. A manual' },
      });
    });
    await act(async () => {
      await Promise.resolve();
    });
    act(() => {
      result.current.segmentationMask.paintStroke({ x: 0, y: 0, sliceIndex: 0, brushSize: 1, labelId: 1, erase: false });
    });

    let outcome: unknown;
    act(() => {
      outcome = importDraft();
    });
    expect(outcome).toEqual({ ok: false, reason: 'unsaved-work', openSegmentationName: 'Dr. A manual' });
    expect(useSegmentationStore.getState().currentSegmentation?.segmentation_id).toBe('saved-7');

    act(() => {
      outcome = importDraft({ discardUnsavedWork: true });
    });
    expect(outcome).toEqual({ ok: true });
    expect(useSegmentationStore.getState().currentSegmentation?.metadata.ai_provenance?.kind).toBe('ai_draft');
  });

  it('rc050 with no unsaved work the draft opens directly', () => {
    renderHook(() => useSegmentationData({}), { wrapper });
    let outcome: unknown;
    act(() => {
      outcome = importDraft();
    });
    expect(outcome).toEqual({ ok: true });
    expect(useSegmentationStore.getState().currentSegmentation?.segmentation_id.startsWith('local-')).toBe(true);
  });
});
