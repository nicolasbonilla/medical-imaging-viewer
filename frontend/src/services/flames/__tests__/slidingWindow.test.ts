// @vitest-environment node
/**
 * Sliding-window stitching of the in-browser FLAMeS port.
 * Steps and Gaussian come from nnunetv2 itself (fixtures); stitching is checked with fake networks
 * whose correct stitched output is known in closed form.
 */
import { describe, expect, it } from 'vitest';
import fx from './fixtures/nnunet_reference.json';
import {
  checkLogits,
  computeSteps,
  flipAxes,
  gaussianImportanceMap,
  mirrorCombinations,
  padToAtLeast,
  predictLogitDifference,
  type RunPatch,
} from '../slidingWindow';
import type { Shape3 } from '../preprocess';

const F = fx as any;

describe('compute_steps_for_sliding_window', () => {
  for (const c of F.steps) {
    it(`${c.image_size}`, () => {
      expect(computeSteps(c.image_size, c.tile, c.step)).toEqual(c.expected);
    });
  }
});

describe('compute_gaussian', () => {
  it('small patch equals nnU-Net (normalised to max 1)', () => {
    const g = gaussianImportanceMap(F.gaussian.small_patch);
    let worst = 0;
    F.gaussian.small.forEach((v: number, i: number) => (worst = Math.max(worst, Math.abs(g[i] - v))));
    expect(worst).toBeLessThan(1e-6);
  });
  it('FLAMeS patch 112x128x160 at probe voxels', () => {
    const p = F.gaussian.full_patch;
    const g = gaussianImportanceMap(p);
    for (const { at, value } of F.gaussian.full_probes) {
      expect(Math.abs(g[(at[0] * p[1] + at[1]) * p[2] + at[2]] - value)).toBeLessThan(1e-6);
    }
  });
});

describe('helpers', () => {
  it('pads floor/ceil like pad_nd_image', () => {
    const img = Float32Array.from({ length: 2 * 3 * 4 }, (_, i) => i + 1);
    const p = padToAtLeast(img, [2, 3, 4], [5, 3, 7]);
    expect(p.shape).toEqual([5, 3, 7]);
    expect(p.before).toEqual([1, 0, 1]);
    expect(p.image[((1 + 0) * 3 + 0) * 7 + 1]).toBe(1);
    expect(p.image[((1 + 1) * 3 + 2) * 7 + 1 + 3]).toBe(24);
    expect(p.image.reduce((s, v) => s + v, 0)).toBe(300);
  });
  it('mirror combinations follow itertools.combinations order', () => {
    expect(mirrorCombinations([0, 1, 2])).toEqual([[0], [1], [2], [0, 1], [0, 2], [1, 2], [0, 1, 2]]);
    expect(mirrorCombinations([])).toEqual([]);
  });
  it('flip is an involution and flips the right axis', () => {
    const shape = [2, 3, 4];
    const d = Float32Array.from({ length: 24 }, (_, i) => i);
    for (const axes of mirrorCombinations([0, 1, 2])) expect(Array.from(flipAxes(flipAxes(d, shape, axes), shape, axes))).toEqual(Array.from(d));
    const f2 = flipAxes(d, shape, [2]);
    expect(f2[0]).toBe(3);
    const f0 = flipAxes(d, shape, [0]);
    expect(f0[0]).toBe(12);
  });
  it('rc044 checkLogits rejects constant and non-finite outputs (fail closed)', () => {
    expect(() => checkLogits(new Float32Array(10))).toThrow(/same score/);
    expect(() => checkLogits(Float32Array.from([1, 2, NaN]))).toThrow(/non-finite/);
    expect(() => checkLogits(Float32Array.from([1, 2, 3]))).not.toThrow();
  });
});

const patch = [8, 10, 12] as const;
const vox = patch[0] * patch[1] * patch[2];

/** identity network: background logit 0, lesion logit = input. Stitched logit difference must equal the input. */
const identity: RunPatch = async (tile) => {
  const out = new Float32Array(2 * vox);
  out.set(tile, vox);
  return out;
};

function ramp(shape: Shape3): Float32Array {
  return Float32Array.from({ length: shape[0] * shape[1] * shape[2] }, (_, i) => Math.sin(i * 0.37) + (i % 11) * 0.1);
}

describe('predictLogitDifference', () => {
  it('identity network reproduces the input exactly (overlaps + padding)', async () => {
    for (const shape of [
      [8, 10, 12],
      [21, 17, 30],
      [5, 23, 9],
    ] as Shape3[]) {
      const img = ramp(shape);
      const r = await predictLogitDifference({ image: img, shape, patch, runPatch: identity });
      let worst = 0;
      for (let i = 0; i < img.length; i++) worst = Math.max(worst, Math.abs(r.logitDiff[i] - img[i]));
      expect(worst).toBeLessThan(1e-5);
    }
  });

  it('mirroring with an equivariant network still reproduces the input, 8 calls per window', async () => {
    const shape: Shape3 = [13, 10, 20];
    const img = ramp(shape);
    const r = await predictLogitDifference({ image: img, shape, patch, runPatch: identity, mirrorAxes: [0, 1, 2] });
    expect(r.networkCalls).toBe(8 * r.windows);
    let worst = 0;
    for (let i = 0; i < img.length; i++) worst = Math.max(worst, Math.abs(r.logitDiff[i] - img[i]));
    expect(worst).toBeLessThan(1e-5);
  });

  it('rc041 position-dependent network: equals a brute-force Gaussian-weighted average', async () => {
    const shape: Shape3 = [13, 15, 20];
    const img = ramp(shape);
    // output depends on the position inside the patch, so stitching weights matter
    const positional: RunPatch = async (tile) => {
      const out = new Float32Array(2 * vox);
      for (let t = 0; t < vox; t++) {
        out[t] = -0.5 * (t % 7);
        out[vox + t] = tile[t] + 0.25 * (t % 5);
      }
      return out;
    };
    const r = await predictLogitDifference({ image: img, shape, patch, runPatch: positional });
    const g = gaussianImportanceMap(patch);
    const steps = computeSteps(shape, patch, 0.5);
    const num = new Float64Array(img.length);
    const den = new Float64Array(img.length);
    for (const a of steps[0]) for (const b of steps[1]) for (const c of steps[2]) {
      for (let x = 0; x < patch[0]; x++) for (let y = 0; y < patch[1]; y++) for (let z = 0; z < patch[2]; z++) {
        const t = (x * patch[1] + y) * patch[2] + z;
        const idx = ((a + x) * shape[1] + b + y) * shape[2] + c + z;
        const diff = img[idx] + 0.25 * (t % 5) + 0.5 * (t % 7);
        num[idx] += diff * g[t];
        den[idx] += g[t];
      }
    }
    let worst = 0;
    for (let i = 0; i < img.length; i++) worst = Math.max(worst, Math.abs(r.logitDiff[i] - num[i] / den[i]));
    expect(worst).toBeLessThan(1e-4);
  });

  it('rejects a wrong-size network output and honours abort', async () => {
    const bad: RunPatch = async () => Float32Array.from({ length: 5 }, (_, i) => i);
    await expect(predictLogitDifference({ image: ramp([8, 10, 12]), shape: [8, 10, 12], patch, runPatch: bad })).rejects.toThrow(
      /Unexpected network output size/,
    );
    const ac = new AbortController();
    ac.abort();
    await expect(
      predictLogitDifference({ image: ramp([8, 10, 12]), shape: [8, 10, 12], patch, runPatch: identity, signal: ac.signal }),
    ).rejects.toThrow();
  });
});
