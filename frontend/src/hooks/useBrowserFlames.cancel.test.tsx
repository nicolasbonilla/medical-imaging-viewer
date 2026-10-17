/**
 * In-browser FLAMeS run: cancellable at any time WITHOUT losing work (COOP-COEP-IMPACT.md §4),
 * and the expected duration is stated honestly before the run (runtimeEstimate.ts).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const apiGet = vi.fn();
vi.mock('@/services/apiClient', () => ({ apiClient: { get: (...a: unknown[]) => apiGet(...a) } }));

import { useBrowserFlames } from './useBrowserFlames';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { estimateDuration, expectedThreads, formatElapsed } from '@/services/flames/runtimeEstimate';

class FakeWorker {
  static last: FakeWorker | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: ErrorEvent) => void) | null = null;
  posted: unknown[] = [];
  terminated = false;
  constructor() {
    FakeWorker.last = this;
  }
  postMessage(m: unknown) {
    this.posted.push(m);
  }
  terminate() {
    this.terminated = true;
  }
}

describe('useBrowserFlames cancel', () => {
  beforeEach(() => {
    FakeWorker.last = null;
    vi.stubGlobal('Worker', FakeWorker);
    apiGet.mockResolvedValue({ data: new ArrayBuffer(8) });
  });

  it('rc045 cancel terminates the worker, ignores late results and never touches the open segmentation', async () => {
    const open = {
      segmentation_id: 'saved-1',
      file_id: 'f',
      total_slices: 1,
      metadata: { file_id: 'f', created_at: 'x', modified_at: 'x', labels: [], description: 'my work' },
    };
    useSegmentationStore.setState({ currentSegmentation: open });
    const importSpy = vi.fn();
    useSegmentationStore.setState({ importDraftCallback: importSpy });

    const { result } = renderHook(() => useBrowserFlames());
    await act(async () => {
      await result.current.run('f', { seriesDescription: 'Ax T2 FLAIR' });
    });
    const worker = FakeWorker.last!;
    expect(result.current.status).toBe('running');
    expect((worker.posted[0] as { seriesDescription: string }).seriesDescription).toBe('Ax T2 FLAIR');

    act(() => result.current.cancel());
    expect(worker.terminated).toBe(true);
    expect(result.current.status).toBe('idle');

    // a result that was already in flight is ignored
    const jobId = (worker.posted[0] as { jobId: string }).jobId;
    act(() => {
      worker.onmessage?.({ data: { type: 'result', jobId, maskApp: new Uint8Array(1), dims: [1, 1, 1], spacing: [1, 1, 1], summary: {}, provenance: {} } } as MessageEvent);
    });
    expect(result.current.result).toBeNull();
    expect(useSegmentationStore.getState().currentSegmentation).toBe(open);
    expect(importSpy).not.toHaveBeenCalled();
  });
});

describe('runtime estimate', () => {
  it('a page that is not cross-origin isolated is told it runs on ONE thread, about 20-42 minutes', () => {
    const e = estimateDuration({ crossOriginIsolated: false, hardwareConcurrency: 16 });
    expect(e.threads).toBe(1);
    expect(e.lowMinutes).toBeGreaterThanOrEqual(15);
    expect(e.highMinutes).toBeGreaterThanOrEqual(35);
    expect(e.text).toMatch(/only 1 processor thread/);
    expect(e.measured).toBe(false);
  });

  it('an isolated 8-core page gets the measured 8-thread range (a few minutes)', () => {
    const e = estimateDuration({ crossOriginIsolated: true, hardwareConcurrency: 16 });
    expect(expectedThreads({ crossOriginIsolated: true, hardwareConcurrency: 16 })).toBe(8);
    expect(e.lowMinutes).toBeLessThanOrEqual(4);
    expect(e.highMinutes).toBeLessThanOrEqual(8);
    expect(e.measured).toBe(true);
  });

  it('formats elapsed time', () => {
    expect(formatElapsed(65_000)).toBe('1:05');
  });
});
