/** The AI reads the image without its skull; with no skull-removal service it reads the file, and the gates decide (REQ-FUNC-115, RC-101). */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

const { post, get, sent } = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn(), sent: [] as Array<Record<string, unknown>> }));
vi.mock('@/services/apiClient', () => ({ apiClient: { post, get } }));

import { useBrowserFlames } from './useBrowserFlames';

class FakeWorker {
  onmessage = null;
  onerror = null;
  postMessage(message: Record<string, unknown>) { sent.push(message); }
  terminate() {}
}

beforeEach(() => {
  post.mockReset();
  get.mockReset();
  sent.length = 0;
  vi.stubGlobal('Worker', FakeWorker);
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

const run = async () => {
  const { result } = renderHook(() => useBrowserFlames());
  await act(async () => { await result.current.run('patients/p/flair.nii.gz', { clinicianConfirmedFlair: true }); });
};

describe('the image the model reads', () => {
  it('asks the server to remove the skull, and says so to the worker', async () => {
    const brain = new ArrayBuffer(8);
    post.mockResolvedValue({ data: brain });
    await run();
    expect(post).toHaveBeenCalledWith('/api/v1/clinical/skull-strip', { file_id: 'patients/p/flair.nii.gz' }, expect.objectContaining({ responseType: 'arraybuffer' }));
    expect(get).not.toHaveBeenCalled();
    expect(sent[0]).toMatchObject({ strippedByApp: true });
    expect(sent[0].nifti).toBe(brain);
  });

  it('without the service it reads the file and keeps every gate', async () => {
    post.mockRejectedValue(new Error('503'));
    const file = new ArrayBuffer(4);
    get.mockResolvedValue({ data: file });
    await run();
    expect(get).toHaveBeenCalledTimes(1);
    expect(sent[0]).toMatchObject({ strippedByApp: false });
    expect(sent[0].nifti).toBe(file);
  });
});
