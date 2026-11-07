/**
 * REQ-FUNC-115 (RC-101): the file is read as it is first; only a skull refusal sends it to the server, and a server failure is said
 * as such (review of the skull-strip branch, M3 and M6).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

const { post, get, workers } = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn(), workers: [] as FakeWorkerShape[] }));
interface FakeWorkerShape { sent: Record<string, unknown>[]; onmessage: ((e: { data: unknown }) => unknown) | null; terminated: boolean }
vi.mock('@/services/apiClient', () => ({ apiClient: { post, get } }));

import { STRIP_UNAVAILABLE, useBrowserFlames } from './useBrowserFlames';

class FakeWorker implements FakeWorkerShape {
  sent: Record<string, unknown>[] = [];
  onmessage: ((e: { data: unknown }) => unknown) | null = null;
  onerror = null;
  terminated = false;
  constructor() { workers.push(this); }
  postMessage(message: Record<string, unknown>) { this.sent.push(message); }
  terminate() { this.terminated = true; }
}

beforeEach(() => {
  post.mockReset();
  get.mockReset();
  workers.length = 0;
  vi.stubGlobal('Worker', FakeWorker);
  get.mockResolvedValue({ data: new ArrayBuffer(4) });
});

async function started() {
  const hook = renderHook(() => useBrowserFlames());
  await act(async () => { await hook.result.current.run('patients/p/flair.nii.gz', { clinicianConfirmedFlair: true }); });
  return hook;
}

const refuse = async (w: FakeWorkerShape, kind: string, message: string) => {
  const job = w.sent[0].jobId;
  await act(async () => { await w.onmessage?.({ data: { type: 'error', jobId: job, kind, message } }); });
};

describe('the image the model reads', () => {
  it('reads the file as it is first and never sends an image without a skull to the server', async () => {
    await started();
    expect(get).toHaveBeenCalledTimes(1);
    expect(post).not.toHaveBeenCalled();
    expect(workers[0].sent[0]).toMatchObject({ strippedByApp: false });
  });

  it('sends it to the server only when the skull gates refuse it, and runs the stripped image', async () => {
    const brain = new ArrayBuffer(8);
    post.mockResolvedValue({ data: brain, headers: { 'x-strip-model': '37417f802196' } });
    await started();
    await refuse(workers[0], 'skull', 'This image does not look skull-stripped.');
    expect(post).toHaveBeenCalledWith('/api/v1/clinical/skull-strip', { file_id: 'patients/p/flair.nii.gz' }, expect.objectContaining({ responseType: 'arraybuffer' }));
    expect(workers[0].terminated).toBe(true);
    expect(workers[1].sent[0]).toMatchObject({ strippedByApp: true, stripModel: '37417f802196' });
    expect(workers[1].sent[0].nifti).toBe(brain);
  });

  it('a refusal for any other reason is final', async () => {
    const { result } = await started();
    await refuse(workers[0], 'input', 'The image does not look like a FLAIR.');
    expect(post).not.toHaveBeenCalled();
    expect(result.current.status).toBe('error');
  });

  it('a stripped image refused again is final: no second trip to the server', async () => {
    post.mockResolvedValue({ data: new ArrayBuffer(8), headers: {} });
    const { result } = await started();
    await refuse(workers[0], 'skull', 'skull');
    await refuse(workers[1], 'skull', 'still not stripped');
    expect(post).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBe('still not stripped');
  });

  it('a server without the service keeps the image reason and says why', async () => {
    post.mockRejectedValue({ response: { status: 503 } });
    const { result } = await started();
    await refuse(workers[0], 'skull', 'This image does not look skull-stripped.');
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.error).toBe(`This image does not look skull-stripped. ${STRIP_UNAVAILABLE}`);
  });

  it('a failing server is named as the cause, never the image', async () => {
    post.mockRejectedValue({ response: { status: 502 } });
    const { result } = await started();
    await refuse(workers[0], 'skull', 'This image does not look skull-stripped.');
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.error).toMatch(/could not be removed on the server \(error 502\)/);
    expect(result.current.error).not.toMatch(/does not look skull-stripped/);
  });

  it('cancelling aborts the skull removal in flight', async () => {
    let signal: AbortSignal | undefined;
    post.mockImplementation((_u: string, _b: unknown, config: { signal: AbortSignal }) => { signal = config.signal; return new Promise(() => undefined); });
    const { result } = await started();
    void refuse(workers[0], 'skull', 'skull');
    await waitFor(() => expect(signal).toBeDefined());
    act(() => result.current.cancel());
    expect(signal?.aborted).toBe(true);
  });
});
