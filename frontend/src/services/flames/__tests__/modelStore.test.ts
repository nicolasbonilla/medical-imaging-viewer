// @vitest-environment node
/**
 * RC-040 (REQ-SAFE-031): the browser executes only the model whose size and SHA-256 equal the pinned
 * values — on DOWNLOAD and when served from the browser's Cache Storage.
 *
 * These tests drive loadVerifiedModel (the function the worker calls), not only verifyModel, so removing
 * either SHA-256 check from loadVerifiedModel fails a test (negative controls I1/I2 in
 * docs/research/flames-in-browser/evidence/handoff-negative-controls.json).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadVerifiedModel, ModelIntegrityError, MODEL_CACHE_NAME, sha256Hex } from '../modelStore';
import { FLAMES_FOLD0_MODEL, type FlamesModelAsset } from '../plan';

const GOOD = new TextEncoder().encode('pinned model bytes for the integrity test — not a real network');

async function assetFor(bytes: Uint8Array): Promise<FlamesModelAsset> {
  return { ...FLAMES_FOLD0_MODEL, url: '/models/flames/test.onnx', bytes: bytes.length, sha256: await sha256Hex(bytes) };
}

/** Same length, one bit flipped: only the SHA-256 (not the size check) can catch it. */
function tampered(bytes: Uint8Array): Uint8Array<ArrayBuffer> {
  const t = bytes.slice() as Uint8Array<ArrayBuffer>;
  t[10] ^= 0x01;
  return t;
}

class FakeCache {
  store = new Map<string, Uint8Array>();
  deleted: string[] = [];
  puts: string[] = [];
  async match(url: string) {
    const b = this.store.get(url);
    return b ? new Response(b.slice()) : undefined;
  }
  async put(url: string, response: Response) {
    this.puts.push(url);
    this.store.set(url, new Uint8Array(await response.arrayBuffer()));
  }
  async delete(url: string) {
    this.deleted.push(url);
    return this.store.delete(url);
  }
}

let cache: FakeCache;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  cache = new FakeCache();
  vi.stubGlobal('caches', { open: async (name: string) => (name === MODEL_CACHE_NAME ? cache : null) });
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('loadVerifiedModel — download path', () => {
  it('rc040 refuses downloaded bytes whose SHA-256 differs from the pin, and does not cache them', async () => {
    const asset = await assetFor(GOOD);
    fetchMock.mockResolvedValue(new Response(tampered(GOOD) as Uint8Array<ArrayBuffer>));
    await expect(loadVerifiedModel(asset)).rejects.toBeInstanceOf(ModelIntegrityError);
    expect(cache.puts).toEqual([]);
  });

  it('rc040 refuses a truncated download (size pin)', async () => {
    const asset = await assetFor(GOOD);
    fetchMock.mockResolvedValue(new Response(GOOD.slice(0, GOOD.length - 3) as Uint8Array<ArrayBuffer>));
    await expect(loadVerifiedModel(asset)).rejects.toThrow(/size/);
  });

  it('rc040 accepts the pinned bytes and caches them', async () => {
    const asset = await assetFor(GOOD);
    fetchMock.mockResolvedValue(new Response(GOOD.slice()));
    const bytes = await loadVerifiedModel(asset);
    expect(Array.from(bytes)).toEqual(Array.from(GOOD));
    expect(cache.puts).toEqual([asset.url]);
  });
});

describe('loadVerifiedModel — browser cache path', () => {
  it('rc040 never returns a cached copy whose SHA-256 differs: it is deleted and the model re-downloaded', async () => {
    const asset = await assetFor(GOOD);
    cache.store.set(asset.url, tampered(GOOD)); // corrupted / swapped cache entry, same size
    fetchMock.mockResolvedValue(new Response(GOOD.slice()));
    const bytes = await loadVerifiedModel(asset);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(cache.deleted).toEqual([asset.url]);
    expect(Array.from(bytes)).toEqual(Array.from(GOOD));
  });

  it('rc040 fails closed when both the cached copy and the download are wrong', async () => {
    const asset = await assetFor(GOOD);
    cache.store.set(asset.url, tampered(GOOD));
    fetchMock.mockResolvedValue(new Response(tampered(GOOD) as Uint8Array<ArrayBuffer>));
    await expect(loadVerifiedModel(asset)).rejects.toBeInstanceOf(ModelIntegrityError);
  });

  it('rc040 serves a verified cached copy without downloading', async () => {
    const asset = await assetFor(GOOD);
    cache.store.set(asset.url, GOOD.slice());
    const bytes = await loadVerifiedModel(asset);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(Array.from(bytes)).toEqual(Array.from(GOOD));
  });
});
