// @vitest-environment node
/**
 * End-to-end behaviour of the in-browser FLAMeS pipeline with a FAKE network on synthetic volumes:
 * a bright blob placed at a known, asymmetric NIfTI location must come back at that location
 * (HAZ-006), in both NIfTI and app (RC-031) order, through anisotropic resampling; and every
 * fail-closed gate must throw instead of returning a partial mask (HAZ-001).
 */
import { describe, expect, it } from 'vitest';
import { niftiToApp, type Dims3 } from '../axes';
import { FlamesInputError, segmentFlairVolume, type FlamesVolume } from '../pipeline';
import { FLAMES_PLAN } from '../plan';
import type { RunPatch } from '../slidingWindow';
import { makePhantom } from './phantoms';

const PATCH_VOX = FLAMES_PLAN.patchSize[0] * FLAMES_PLAN.patchSize[1] * FLAMES_PLAN.patchSize[2];

/** lesion logit = normalised intensity - 2, background logit = 0 */
const thresholdNet: RunPatch = async (tile) => {
  const out = new Float32Array(2 * PATCH_VOX);
  for (let t = 0; t < PATCH_VOX; t++) out[PATCH_VOX + t] = tile[t] - 2;
  return out;
};

function brainWithBlob(dims: Dims3, radii: Dims3, blob: Dims3, blobRadius: number): Float32Array {
  const [nx, ny, nz] = dims;
  const c = [nx / 2, ny / 2, nz / 2];
  const out = new Float32Array(nx * ny * nz);
  for (let k = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
    const e = ((i - c[0]) / radii[0]) ** 2 + ((j - c[1]) / radii[1]) ** 2 + ((k - c[2]) / radii[2]) ** 2;
    if (e > 1) continue;
    const d2 = (i - blob[0]) ** 2 + (j - blob[1]) ** 2 + (k - blob[2]) ** 2;
    out[i + nx * (j + ny * k)] = d2 <= blobRadius * blobRadius ? 300 : 100 + ((i * 7 + j * 3 + k) % 5);
  }
  return out;
}

function centroid(mask: Uint8Array, dims: Dims3): number[] {
  const [nx, ny] = dims;
  let n = 0;
  const s = [0, 0, 0];
  for (let v = 0; v < mask.length; v++) {
    if (!mask[v]) continue;
    n++;
    s[0] += v % nx;
    s[1] += Math.floor(v / nx) % ny;
    s[2] += Math.floor(v / (nx * ny));
  }
  return s.map((x) => x / n);
}

describe('segmentFlairVolume (fake network)', () => {
  it('rc042 returns the blob at its NIfTI location through anisotropic (separate-z) resampling', async () => {
    const dims: Dims3 = [40, 36, 24];
    const blob: Dims3 = [27, 12, 15];
    const vol: FlamesVolume = { dims, spacing: [1.1, 1.0, 3.5], data: brainWithBlob(dims, [16, 14, 10], blob, 3) };
    const r = await segmentFlairVolume(vol, { runPatch: thresholdNet, skullStripGate: false, contrastGate: false });
    expect(r.summary.lesionCount).toBe(1);
    const cen = centroid(r.maskNifti, dims);
    expect(Math.abs(cen[0] - blob[0])).toBeLessThan(1);
    expect(Math.abs(cen[1] - blob[1])).toBeLessThan(1);
    expect(Math.abs(cen[2] - blob[2])).toBeLessThan(1);
    expect(Array.from(r.maskApp)).toEqual(Array.from(niftiToApp(r.maskNifti, dims)));
    expect(r.diagnostics.networkSpacing).toEqual([1.1, 3.5, 1.0]);
    expect(r.diagnostics.windows).toBe(1);
  });

  it('rc041 isotropic input, asymmetric blob near a corner of the brain', async () => {
    const dims: Dims3 = [30, 34, 28];
    const blob: Dims3 = [8, 22, 19];
    const vol: FlamesVolume = { dims, spacing: [1, 1, 1], data: brainWithBlob(dims, [13, 15, 12], blob, 2.5) };
    const r = await segmentFlairVolume(vol, { runPatch: thresholdNet, skullStripGate: false, contrastGate: false, returnProbability: true });
    const cen = centroid(r.maskNifti, dims);
    [0, 1, 2].forEach((a) => expect(Math.abs(cen[a] - blob[a])).toBeLessThan(1));
    expect(r.probabilityNifti!.length).toBe(r.maskNifti.length);
  });
});

describe('fail-closed gates', () => {
  it('rc043 refuses a FLAIR that is not skull-stripped (nonzero border)', async () => {
    const dims: Dims3 = [32, 32, 32];
    const data = Float32Array.from({ length: 32 ** 3 }, (_, i) => 50 + (i % 13));
    await expect(segmentFlairVolume({ dims, spacing: [4, 4, 4], data }, { runPatch: thresholdNet })).rejects.toThrow(
      /skull-stripped/,
    );
  });

  it('refuses an implausible brain volume', async () => {
    const dims: Dims3 = [32, 32, 32];
    const data = brainWithBlob(dims, [6, 6, 6], [16, 16, 16], 1);
    await expect(segmentFlairVolume({ dims, spacing: [1, 1, 1], data }, { runPatch: thresholdNet })).rejects.toBeInstanceOf(
      FlamesInputError,
    );
  });

  it('accepts a plausible stripped brain and runs', async () => {
    const dims: Dims3 = [36, 40, 32];
    const data = brainWithBlob(dims, [14, 16, 12], [20, 30, 16], 1.5);
    // 4 mm synthetic blob: no cortex band to measure, so only the skull-strip gate is exercised here
    const r = await segmentFlairVolume({ dims, spacing: [4, 4, 4], data }, { runPatch: thresholdNet, contrastGate: false });
    expect(r.diagnostics.brainVolumeMl).toBeGreaterThan(500);
  });

  it('rc049 runs a FLAIR-like brain through every gate, and refuses a T1-like one before any network call', async () => {
    let calls = 0;
    const counting: RunPatch = async (tile) => {
      calls++;
      return thresholdNet(tile);
    };
    const flair = makePhantom({ contrast: 'FLAIR', spacing: 3 });
    const r = await segmentFlairVolume(flair, { runPatch: counting, clinicianConfirmedFlair: true });
    expect(calls).toBeGreaterThan(0);
    expect(r.maskNifti.length).toBe(flair.data.length);
    calls = 0;
    await expect(
      segmentFlairVolume(makePhantom({ contrast: 'T1', spacing: 3 }), { runPatch: counting, clinicianConfirmedFlair: true }),
    ).rejects.toThrow(
      /white matter is brighter than the cortex/,
    );
    expect(calls).toBe(0);
  });

  it('rc044 discards an implausible output instead of returning it', async () => {
    const everything: RunPatch = async (tile) => {
      const out = new Float32Array(2 * PATCH_VOX);
      for (let t = 0; t < PATCH_VOX; t++) out[PATCH_VOX + t] = 5 + 0.001 * (t % 3) + 0 * tile[t];
      return out;
    };
    const dims: Dims3 = [36, 40, 32];
    const data = brainWithBlob(dims, [14, 16, 12], [20, 30, 16], 1.5);
    await expect(
      segmentFlairVolume({ dims, spacing: [4, 4, 4], data }, { runPatch: everything, contrastGate: false }),
    ).rejects.toThrow(/Implausible output/);
  });

  it('refuses unsupported geometry', async () => {
    const dims: Dims3 = [20, 20, 20];
    const data = new Float32Array(8000);
    await expect(segmentFlairVolume({ dims, spacing: [1, 1, 8], data }, { runPatch: thresholdNet })).rejects.toThrow(/spacing/);
    await expect(segmentFlairVolume({ dims: [8, 20, 20], spacing: [1, 1, 1], data }, { runPatch: thresholdNet })).rejects.toThrow();
  });
});
