/**
 * Download + integrity check + persistent caching of the FLAMeS ONNX model in the browser.
 *
 * - The model is pinned by SHA-256 and byte length (plan.ts). Any mismatch FAILS CLOSED:
 *   the bytes are discarded and the job ends with an error (RC-040 in CHANGE-PROPOSAL.md).
 * - The verified bytes are kept in Cache Storage (per origin, survives reloads) so a workstation
 *   downloads the 62 MB model once per model version. A cached copy is re-verified on every use.
 * - Works in a Web Worker (caches, fetch and crypto.subtle are available there).
 */
import type { FlamesModelAsset } from './plan';

export const MODEL_CACHE_NAME = 'mstool-flames-models-v1';

export async function sha256Hex(bytes: ArrayBuffer | Uint8Array): Promise<string> {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const digest = await crypto.subtle.digest('SHA-256', view as unknown as ArrayBuffer);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

export class ModelIntegrityError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ModelIntegrityError';
  }
}

export async function verifyModel(bytes: Uint8Array, asset: FlamesModelAsset): Promise<void> {
  if (bytes.byteLength !== asset.bytes) {
    throw new ModelIntegrityError(`Model size ${bytes.byteLength} B differs from the pinned ${asset.bytes} B; refusing to run.`);
  }
  const digest = await sha256Hex(bytes);
  if (digest !== asset.sha256) {
    throw new ModelIntegrityError(`Model SHA-256 ${digest.slice(0, 12)}… differs from the pinned ${asset.sha256.slice(0, 12)}…; refusing to run.`);
  }
}

async function openCache(): Promise<Cache | null> {
  try {
    return typeof caches === 'undefined' ? null : await caches.open(MODEL_CACHE_NAME);
  } catch {
    return null; // private windows / disabled storage: still works, just re-downloads
  }
}

async function readWithProgress(response: Response, expected: number, onProgress?: (f: number) => void): Promise<Uint8Array> {
  if (!response.body) return new Uint8Array(await response.arrayBuffer());
  const out = new Uint8Array(expected);
  const reader = response.body.getReader();
  let offset = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (offset + value.byteLength > expected) {
      await reader.cancel();
      throw new ModelIntegrityError('Model download is larger than the pinned size; refusing to run.');
    }
    out.set(value, offset);
    offset += value.byteLength;
    onProgress?.(offset / expected);
  }
  return offset === expected ? out : out.subarray(0, offset);
}

/** Returns verified model bytes, from Cache Storage when possible. Throws on any failure. */
export async function loadVerifiedModel(asset: FlamesModelAsset, onProgress?: (fraction: number) => void): Promise<Uint8Array> {
  const cache = await openCache();
  if (cache) {
    const hit = await cache.match(asset.url);
    if (hit) {
      const bytes = new Uint8Array(await hit.arrayBuffer());
      try {
        await verifyModel(bytes, asset);
        onProgress?.(1);
        return bytes;
      } catch {
        await cache.delete(asset.url); // corrupted or stale cache entry: drop it and download again
      }
    }
  }
  const response = await fetch(asset.url);
  if (!response.ok) throw new Error(`Model download failed (HTTP ${response.status}).`);
  const bytes = await readWithProgress(response, asset.bytes, onProgress);
  await verifyModel(bytes, asset);
  if (cache) {
    try {
      await cache.put(asset.url, new Response(bytes.slice().buffer, { headers: { 'Content-Type': 'application/octet-stream' } }));
    } catch {
      // quota exceeded: run anyway, the next run downloads again
    }
  }
  return bytes;
}
