/**
 * Post-processing for the in-browser FLAMeS draft.
 *
 * The MASK itself is exactly nnU-Net's: argmax of the two resampled logits, i.e.
 * (lesion - background) > 0. No connected-component removal is applied, because
 * FLAMeS' published validation used the raw nnU-Net output (DESIGN.md §3.6).
 * The functions below only DESCRIBE the mask (count, volume) for the UI.
 */

import type { Dims3 } from './axes';

export function thresholdLogitDiff(logitDiff: Float32Array): Uint8Array {
  const out = new Uint8Array(logitDiff.length);
  for (let i = 0; i < logitDiff.length; i++) out[i] = logitDiff[i] > 0 ? 1 : 0;
  return out;
}

/** softmax over 2 classes == sigmoid of the logit difference */
export function probabilityFromLogitDiff(logitDiff: Float32Array): Float32Array {
  const out = new Float32Array(logitDiff.length);
  for (let i = 0; i < logitDiff.length; i++) out[i] = 1 / (1 + Math.exp(-logitDiff[i]));
  return out;
}

export interface LesionSummary {
  lesionCount: number;
  lesionVoxels: number;
  lesionVolumeMl: number;
  /** volumes of each 26-connected component, largest first (mL) */
  componentVolumesMl: number[];
}

/**
 * 26-connected components of a binary mask stored in NIfTI order (i fastest).
 * Connectivity is the same as the app's lesion analysis (scipy label with a full 3x3x3 structure).
 */
export function summariseLesions(mask: Uint8Array, dims: Dims3, spacing: Dims3): LesionSummary {
  const [nx, ny, nz] = dims;
  const voxelMl = (spacing[0] * spacing[1] * spacing[2]) / 1000;
  const seen = new Uint8Array(mask.length);
  const queue = new Int32Array(mask.length);
  const sizes: number[] = [];
  let total = 0;
  for (let seed = 0; seed < mask.length; seed++) {
    if (!mask[seed] || seen[seed]) continue;
    let head = 0;
    let tail = 0;
    queue[tail++] = seed;
    seen[seed] = 1;
    while (head < tail) {
      const v = queue[head++];
      const x = v % nx;
      const y = Math.floor(v / nx) % ny;
      const z = Math.floor(v / (nx * ny));
      for (let dz = -1; dz <= 1; dz++) {
        const zz = z + dz;
        if (zz < 0 || zz >= nz) continue;
        for (let dy = -1; dy <= 1; dy++) {
          const yy = y + dy;
          if (yy < 0 || yy >= ny) continue;
          for (let dx = -1; dx <= 1; dx++) {
            const xx = x + dx;
            if (xx < 0 || xx >= nx) continue;
            const w = xx + nx * (yy + ny * zz);
            if (mask[w] && !seen[w]) {
              seen[w] = 1;
              queue[tail++] = w;
            }
          }
        }
      }
    }
    sizes.push(tail);
    total += tail;
  }
  sizes.sort((a, b) => b - a);
  return {
    lesionCount: sizes.length,
    lesionVoxels: total,
    lesionVolumeMl: total * voxelMl,
    componentVolumesMl: sizes.map((s) => s * voxelMl),
  };
}

export function dice(a: Uint8Array, b: Uint8Array): number {
  if (a.length !== b.length) throw new Error('Dice: size mismatch');
  let sa = 0;
  let sb = 0;
  let both = 0;
  for (let i = 0; i < a.length; i++) {
    const x = a[i] ? 1 : 0;
    const y = b[i] ? 1 : 0;
    sa += x;
    sb += y;
    both += x & y;
  }
  return sa + sb === 0 ? 1 : (2 * both) / (sa + sb);
}
