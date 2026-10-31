/**
 * nnU-Net v2 sliding-window inference (predict_sliding_window_return_logits) for FLAMeS.
 *
 * Faithful to nnunetv2 2.8.1 (Apache-2.0):
 *  - pad_nd_image(..., 'constant', value 0) to at least the patch size, split floor/ceil;
 *  - compute_steps_for_sliding_window with tile_step_size 0.5 and numpy half-to-even rounding;
 *  - compute_gaussian(sigma_scale 1/8): scipy gaussian_filter of a centred delta (truncate 4.0),
 *    normalised to its maximum, zeros replaced by the smallest non-zero value;
 *  - logits accumulated as sum(logit * gaussian) / sum(gaussian);
 *  - optional mirroring TTA over the given network axes (all non-empty axis combinations).
 *
 * Deliberate, documented deviation (DESIGN.md §3.5): nnU-Net 2.8.1 accumulates in float16 to save
 * GPU memory; we accumulate in float32. Only the 2-class LOGIT DIFFERENCE (lesion - background)
 * is kept, which is sufficient for both argmax and the softmax probability.
 *
 * Structure of predictLogitDifference (inject runPatch, two-class difference accumulation) follows
 * Neurodesk webapps packages/white-matter-lesions/src/pipeline.js (Apache-2.0); see NOTICE.md.
 */

import { product, roundHalfEven, type Shape3 } from './preprocess';

/** nnunetv2 compute_steps_for_sliding_window. */
export function computeSteps(imageSize: readonly number[], tileSize: readonly number[], tileStepSize: number): number[][] {
  return tileSize.map((tile, dim) => {
    const size = imageSize[dim];
    if (size < tile) throw new Error('Image must be padded to at least the patch size before tiling.');
    const target = tile * tileStepSize;
    const numSteps = Math.ceil((size - tile) / target) + 1;
    const maxStep = size - tile;
    const actual = numSteps > 1 ? maxStep / (numSteps - 1) : 99999999999;
    return Array.from({ length: numSteps }, (_, i) => roundHalfEven(actual * i));
  });
}

/** One axis of scipy gaussian_filter applied to a delta at floor(n/2) (truncate = 4.0). */
function gaussianAxis(n: number, sigmaScale: number): Float64Array {
  const sigma = n * sigmaScale;
  const radius = Math.floor(4.0 * sigma + 0.5);
  const centre = Math.floor(n / 2);
  let sum = 0;
  for (let x = -radius; x <= radius; x++) sum += Math.exp((-0.5 * x * x) / (sigma * sigma));
  const out = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const x = i - centre;
    out[i] = Math.abs(x) <= radius ? Math.exp((-0.5 * x * x) / (sigma * sigma)) / sum : 0;
  }
  return out;
}

/** nnunetv2 compute_gaussian, normalised so that the maximum is 1 (the scale cancels in the weighted mean). */
export function gaussianImportanceMap(patch: readonly number[], sigmaScale = 1 / 8): Float32Array {
  const [g0, g1, g2] = patch.map((n) => gaussianAxis(n, sigmaScale));
  const out = new Float32Array(product(patch));
  let max = 0;
  let o = 0;
  for (let a = 0; a < patch[0]; a++) {
    for (let b = 0; b < patch[1]; b++) {
      for (let c = 0; c < patch[2]; c++, o++) {
        const v = g0[a] * g1[b] * g2[c];
        out[o] = v;
        if (v > max) max = v;
      }
    }
  }
  let minNonZero = Infinity;
  for (let i = 0; i < out.length; i++) {
    out[i] /= max;
    if (out[i] > 0 && out[i] < minNonZero) minNonZero = out[i];
  }
  for (let i = 0; i < out.length; i++) if (out[i] === 0) out[i] = minNonZero;
  return out;
}

export interface Padded {
  image: Float32Array;
  shape: Shape3;
  before: Shape3;
}

/** acvl_utils pad_nd_image(image, patch, 'constant', value 0): pad below = diff // 2, above = the rest. */
export function padToAtLeast(image: Float32Array, shape: Shape3, minimum: readonly number[]): Padded {
  const padded: Shape3 = [0, 1, 2].map((a) => Math.max(shape[a], minimum[a])) as Shape3;
  const before: Shape3 = [0, 1, 2].map((a) => Math.floor((padded[a] - shape[a]) / 2)) as Shape3;
  if (padded[0] === shape[0] && padded[1] === shape[1] && padded[2] === shape[2]) return { image, shape, before };
  const out = new Float32Array(product(padded));
  for (let x = 0; x < shape[0]; x++) {
    for (let y = 0; y < shape[1]; y++) {
      const src = (x * shape[1] + y) * shape[2];
      const dst = ((x + before[0]) * padded[1] + y + before[1]) * padded[2] + before[2];
      out.set(image.subarray(src, src + shape[2]), dst);
    }
  }
  return { image: out, shape: padded, before };
}

/** Flip a C-order patch along a set of axes (returns a new array). */
export function flipAxes(data: Float32Array, shape: readonly number[], axes: readonly number[], channels = 1): Float32Array {
  if (axes.length === 0) return data;
  const [n0, n1, n2] = shape;
  const vox = n0 * n1 * n2;
  const f0 = axes.includes(0);
  const f1 = axes.includes(1);
  const f2 = axes.includes(2);
  const out = new Float32Array(data.length);
  for (let ch = 0; ch < channels; ch++) {
    const base = ch * vox;
    for (let a = 0; a < n0; a++) {
      const sa = f0 ? n0 - 1 - a : a;
      for (let b = 0; b < n1; b++) {
        const sb = f1 ? n1 - 1 - b : b;
        const dstRow = base + (a * n1 + b) * n2;
        const srcRow = base + (sa * n1 + sb) * n2;
        if (f2) for (let c = 0; c < n2; c++) out[dstRow + c] = data[srcRow + n2 - 1 - c];
        else out.set(data.subarray(srcRow, srcRow + n2), dstRow);
      }
    }
  }
  return out;
}

/** itertools.combinations over mirror axes, all sizes 1..n, in nnU-Net order. */
export function mirrorCombinations(axes: readonly number[]): number[][] {
  const out: number[][] = [];
  const rec = (start: number, size: number, acc: number[]) => {
    if (acc.length === size) {
      out.push([...acc]);
      return;
    }
    for (let i = start; i < axes.length; i++) rec(i + 1, size, [...acc, axes[i]]);
  };
  for (let size = 1; size <= axes.length; size++) rec(0, size, []);
  return out;
}

/** A network never gives every voxel the same score; some virtual GPUs return all zeros. Fail closed. */
export function checkLogits(logits: Float32Array): void {
  const first = logits[0];
  let varies = false;
  for (let i = 0; i < logits.length; i++) {
    const v = logits[i];
    if (!Number.isFinite(v)) throw new Error('The network returned non-finite scores.');
    if (v !== first) varies = true;
  }
  if (!varies) throw new Error('The network returned the same score for every voxel.');
}

export type RunPatch = (tile: Float32Array) => Promise<Float32Array>;

export interface SlidingWindowOptions {
  image: Float32Array;
  shape: Shape3;
  patch: readonly number[];
  runPatch: RunPatch;
  tileStepSize?: number;
  sigmaScale?: number;
  /** network axes for mirroring TTA; [] (default) = no TTA */
  mirrorAxes?: readonly number[];
  onPatch?: (done: number, total: number) => void;
  signal?: AbortSignal;
}

export interface SlidingWindowResult {
  /** lesion-minus-background logit, on the (unpadded) input grid */
  logitDiff: Float32Array;
  windows: number;
  networkCalls: number;
}

export async function predictLogitDifference(opts: SlidingWindowOptions): Promise<SlidingWindowResult> {
  const { shape, patch, runPatch, signal } = opts;
  const tileStepSize = opts.tileStepSize ?? 0.5;
  const mirrorAxes = opts.mirrorAxes ?? [];
  const combos = mirrorCombinations(mirrorAxes);
  const padded = padToAtLeast(opts.image, shape, patch);
  const weights = gaussianImportanceMap(patch, opts.sigmaScale ?? 1 / 8);
  const steps = computeSteps(padded.shape, patch, tileStepSize);
  const origins: Shape3[] = [];
  for (const a of steps[0]) for (const b of steps[1]) for (const c of steps[2]) origins.push([a, b, c]);
  const voxels = product(patch);
  const sum = new Float32Array(product(padded.shape));
  const weight = new Float32Array(sum.length);
  const tile = new Float32Array(voxels);
  const diff = new Float32Array(voxels);
  let calls = 0;

  const runDiff = async (input: Float32Array, axes: number[]) => {
    signal?.throwIfAborted();
    const logits = await runPatch(axes.length ? flipAxes(input, patch, axes) : input);
    signal?.throwIfAborted();
    calls++;
    if (logits.length !== 2 * voxels) {
      throw new Error(`Unexpected network output size ${logits.length} (expected ${2 * voxels}).`);
    }
    checkLogits(logits);
    const back = axes.length ? flipAxes(logits, patch, axes, 2) : logits;
    for (let t = 0; t < voxels; t++) diff[t] += back[voxels + t] - back[t];
  };

  for (let n = 0; n < origins.length; n++) {
    const [x0, y0, z0] = origins[n];
    let t = 0;
    for (let x = 0; x < patch[0]; x++) {
      for (let y = 0; y < patch[1]; y++) {
        const start = ((x0 + x) * padded.shape[1] + y0 + y) * padded.shape[2] + z0;
        tile.set(padded.image.subarray(start, start + patch[2]), t);
        t += patch[2];
      }
    }
    diff.fill(0);
    await runDiff(tile, []);
    for (const axes of combos) await runDiff(tile, axes);
    const scale = 1 / (combos.length + 1);
    t = 0;
    for (let x = 0; x < patch[0]; x++) {
      for (let y = 0; y < patch[1]; y++) {
        const row = ((x0 + x) * padded.shape[1] + y0 + y) * padded.shape[2] + z0;
        for (let z = 0; z < patch[2]; z++, t++) {
          sum[row + z] += diff[t] * scale * weights[t];
          weight[row + z] += weights[t];
        }
      }
    }
    opts.onPatch?.(n + 1, origins.length);
  }

  const logitDiff = new Float32Array(product(shape));
  let o = 0;
  for (let x = 0; x < shape[0]; x++) {
    for (let y = 0; y < shape[1]; y++) {
      const row = ((x + padded.before[0]) * padded.shape[1] + y + padded.before[1]) * padded.shape[2] + padded.before[2];
      for (let z = 0; z < shape[2]; z++, o++) {
        const w = weight[row + z];
        if (!(w > 0)) throw new Error('Sliding window left a voxel without any prediction.');
        logitDiff[o] = sum[row + z] / w;
      }
    }
  }
  return { logitDiff, windows: origins.length, networkCalls: calls };
}
