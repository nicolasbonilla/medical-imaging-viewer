/**
 * A-2 optimistic-concurrency behaviour of useSegmentationMask (frontend half).
 *
 * Pins the safety contract the reconcile UI depends on:
 *  - the mask's GCS generation (X-Mask-Generation) is captured at load and
 *    round-tripped as `If-Match` on save;
 *  - a successful save refreshes the baseline from the response so the client's
 *    OWN next sequential save matches instead of false-conflicting;
 *  - a 409 sets state.conflict and PRESERVES the local mask + isDirty (never a
 *    silent last-writer-wins loss);
 *  - overwriteSave() sends X-Overwrite (deliberate keep-mine);
 *  - discardAndReload() reloads from the server and clears the conflict.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const get = vi.fn();
const put = vi.fn();
vi.mock('@/services/apiClient', () => ({
  apiClient: { get: (...a: any[]) => get(...a), put: (...a: any[]) => put(...a) },
}));

import { useSegmentationMask } from './useSegmentationMask';

/** A load response body: 12-byte little-endian header + D*H*W mask bytes. */
function loadBuffer(depth: number, height: number, width: number, fill = 0): ArrayBuffer {
  const buf = new ArrayBuffer(12 + depth * height * width);
  const dv = new DataView(buf);
  dv.setUint32(0, depth, true);
  dv.setUint32(4, height, true);
  dv.setUint32(8, width, true);
  new Uint8Array(buf, 12).fill(fill);
  return buf;
}

function lastPutHeaders(): Record<string, string> {
  return put.mock.calls[put.mock.calls.length - 1][2].headers;
}

describe('useSegmentationMask A-2 concurrency', () => {
  beforeEach(() => {
    get.mockReset();
    put.mockReset();
  });

  it('captures the generation on load and sends it as If-Match on save', async () => {
    get.mockResolvedValue({ data: loadBuffer(1, 1, 1), headers: { 'x-mask-generation': '5' } });
    put.mockResolvedValue({ data: { durable: true, generation: 6 } });

    const { result } = renderHook(() => useSegmentationMask());
    await act(async () => { await result.current.loadMask('seg1'); });
    await act(async () => { await result.current.saveMask(); });

    expect(lastPutHeaders()['If-Match']).toBe('5');
    expect(lastPutHeaders()['X-Overwrite']).toBeUndefined();
  });

  it('refreshes the baseline from the save response so the next save matches', async () => {
    get.mockResolvedValue({ data: loadBuffer(1, 1, 1), headers: { 'x-mask-generation': '5' } });
    put.mockResolvedValueOnce({ data: { durable: true, generation: 6 } })
       .mockResolvedValueOnce({ data: { durable: true, generation: 7 } });

    const { result } = renderHook(() => useSegmentationMask());
    await act(async () => { await result.current.loadMask('seg1'); });
    await act(async () => { await result.current.saveMask(); });
    await act(async () => { await result.current.saveMask(); });

    expect(lastPutHeaders()['If-Match']).toBe('6'); // advanced, not the stale '5'
  });

  it('on 409 sets conflict and preserves the local edits (no silent loss)', async () => {
    get.mockResolvedValue({ data: loadBuffer(1, 1, 1), headers: { 'x-mask-generation': '5' } });
    put.mockRejectedValue({ response: { status: 409, data: { detail: 'modified elsewhere' } } });

    const { result } = renderHook(() => useSegmentationMask());
    await act(async () => { await result.current.loadMask('seg1'); });
    act(() => { result.current.paintStroke({ x: 0, y: 0, sliceIndex: 0, brushSize: 1, labelId: 1, erase: false }); });

    let ok: boolean = true;
    await act(async () => { ok = await result.current.saveMask(); });

    expect(ok).toBe(false);
    expect(result.current.state.conflict).toBe('modified elsewhere');
    expect(result.current.state.isDirty).toBe(true);      // edit kept, not cleared
    expect(result.current.getVoxel(0, 0, 0)).toBe(1);      // painted voxel survives
  });

  it('overwriteSave sends X-Overwrite and clears the conflict', async () => {
    get.mockResolvedValue({ data: loadBuffer(1, 1, 1), headers: { 'x-mask-generation': '5' } });
    put.mockRejectedValueOnce({ response: { status: 409, data: { detail: 'conflict' } } })
       .mockResolvedValueOnce({ data: { durable: true, generation: 9 } });

    const { result } = renderHook(() => useSegmentationMask());
    await act(async () => { await result.current.loadMask('seg1'); });
    await act(async () => { await result.current.saveMask(); });
    expect(result.current.state.conflict).toBe('conflict');

    await act(async () => { await result.current.overwriteSave(); });
    expect(lastPutHeaders()['X-Overwrite']).toBe('true');
    expect(result.current.state.conflict).toBeNull();
  });

  it('discardAndReload reloads from the server and clears the conflict', async () => {
    get.mockResolvedValue({ data: loadBuffer(1, 1, 1), headers: { 'x-mask-generation': '5' } });
    put.mockRejectedValue({ response: { status: 409, data: { detail: 'conflict' } } });

    const { result } = renderHook(() => useSegmentationMask());
    await act(async () => { await result.current.loadMask('seg1'); });
    await act(async () => { await result.current.saveMask(); });
    expect(result.current.state.conflict).toBe('conflict');

    get.mockResolvedValue({ data: loadBuffer(1, 1, 1, 0), headers: { 'x-mask-generation': '9' } });
    await act(async () => { await result.current.discardAndReload(); });

    expect(get).toHaveBeenCalledTimes(2);              // reloaded
    expect(result.current.state.conflict).toBeNull();
    expect(result.current.state.isDirty).toBe(false);  // reconciled to server state
  });
});
