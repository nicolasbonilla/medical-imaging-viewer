/**
 * nnU-Net v2 preprocessing for FLAMeS, re-implemented in TypeScript (PROTOTYPE).
 *
 * Mirrors, step by step, nnunetv2 DefaultPreprocessor.run_case_npy for the FLAMeS plans:
 *   transpose (done by the caller, see axes.ts) -> crop_to_nonzero (nonzero mask with
 *   3D hole filling) -> ZScoreNormalization(use_mask_for_norm) -> resample_data_or_seg_to_shape
 *   (order 3, order_z 0, anisotropy threshold 3).
 *
 * Provenance / attribution: the cubic B-spline resampling kernels below are a TypeScript
 * port of `packages/white-matter-lesions/src/pipeline.js` from Neurodesk webapps
 * (https://github.com/neurodesk/webapps, Apache-2.0, (c) Neurodesk contributors), which itself
 * re-implements nnunetv2 (Apache-2.0, DKFZ), skimage.transform.resize and scipy.ndimage.zoom.
 * Changes by MSTool-AI: TypeScript types; Python-style half-to-even rounding (np.round /
 * round()) instead of Math.round; nonzero mask with 3D hole filling as nnU-Net's
 * create_nonzero_mask; normalisation leaves outside-mask voxels untouched as nnU-Net does.
 * See NOTICE.md in this folder.
 *
 * All arrays here are C-order in NETWORK axis order (see axes.ts).
 */

export type Shape3 = [number, number, number];

export const product = (s: readonly number[]): number => s[0] * s[1] * s[2];

/** Python round() / numpy.round(): round half to even. */
export function roundHalfEven(x: number): number {
  const f = Math.floor(x);
  const diff = x - f;
  if (diff > 0.5) return f + 1;
  if (diff < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

// ---------------------------------------------------------------------------
// crop_to_nonzero
// ---------------------------------------------------------------------------

/**
 * nnU-Net create_nonzero_mask: (data != 0) followed by scipy binary_fill_holes
 * (default 6-connected structure): any background voxel NOT 6-connected to the
 * array border through background becomes foreground.
 */
export function nonzeroMaskFilled(data: Float32Array, shape: Shape3): Uint8Array {
  const [a, b, c] = shape;
  const n = data.length;
  const fg = new Uint8Array(n);
  for (let i = 0; i < n; i++) fg[i] = data[i] !== 0 ? 1 : 0;
  // 0 = background not yet reached, 1 = foreground, 2 = background reached from border
  const state = fg;
  const queue = new Int32Array(n);
  let head = 0;
  let tail = 0;
  const seed = (idx: number) => {
    if (state[idx] === 0) {
      state[idx] = 2;
      queue[tail++] = idx;
    }
  };
  for (let x = 0; x < a; x++) {
    for (let y = 0; y < b; y++) {
      for (let z = 0; z < c; z++) {
        if (x === 0 || y === 0 || z === 0 || x === a - 1 || y === b - 1 || z === c - 1) seed((x * b + y) * c + z);
      }
    }
  }
  const sb = b * c;
  while (head < tail) {
    const idx = queue[head++];
    const x = Math.floor(idx / sb);
    const rem = idx - x * sb;
    const y = Math.floor(rem / c);
    const z = rem - y * c;
    if (x > 0) seed(idx - sb);
    if (x < a - 1) seed(idx + sb);
    if (y > 0) seed(idx - c);
    if (y < b - 1) seed(idx + c);
    if (z > 0) seed(idx - 1);
    if (z < c - 1) seed(idx + 1);
  }
  const out = new Uint8Array(n);
  for (let i = 0; i < n; i++) out[i] = state[i] === 2 ? 0 : 1;
  return out;
}

export interface BoundingBox {
  lo: Shape3;
  /** exclusive */
  hi: Shape3;
  shape: Shape3;
}

/** nnU-Net get_bbox_from_mask: [min, max+1) per axis. Throws on an empty mask (fail closed). */
export function boundingBox(mask: Uint8Array, shape: Shape3): BoundingBox {
  const lo: Shape3 = [shape[0], shape[1], shape[2]];
  const hi: Shape3 = [-1, -1, -1];
  let i = 0;
  for (let x = 0; x < shape[0]; x++) {
    for (let y = 0; y < shape[1]; y++) {
      for (let z = 0; z < shape[2]; z++, i++) {
        if (!mask[i]) continue;
        if (x < lo[0]) lo[0] = x;
        if (y < lo[1]) lo[1] = y;
        if (z < lo[2]) lo[2] = z;
        if (x + 1 > hi[0]) hi[0] = x + 1;
        if (y + 1 > hi[1]) hi[1] = y + 1;
        if (z + 1 > hi[2]) hi[2] = z + 1;
      }
    }
  }
  if (hi[0] < 0) throw new Error('The image is empty (no nonzero voxels).');
  return { lo, hi, shape: [hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]] };
}

export function cropTo<T extends Float32Array | Uint8Array>(data: T, shape: Shape3, box: BoundingBox): T {
  const out = new (data.constructor as { new (n: number): T })(product(box.shape));
  let o = 0;
  for (let x = box.lo[0]; x < box.hi[0]; x++) {
    for (let y = box.lo[1]; y < box.hi[1]; y++) {
      const start = (x * shape[1] + y) * shape[2];
      out.set(data.subarray(start + box.lo[2], start + box.hi[2]) as never, o);
      o += box.shape[2];
    }
  }
  return out;
}

/** Inverse of cropTo: paste `cropped` into a zero-filled array of `shape`. */
export function uncrop<T extends Float32Array | Uint8Array>(cropped: T, shape: Shape3, box: BoundingBox): T {
  const out = new (cropped.constructor as { new (n: number): T })(product(shape));
  let o = 0;
  for (let x = box.lo[0]; x < box.hi[0]; x++) {
    for (let y = box.lo[1]; y < box.hi[1]; y++) {
      out.set(cropped.subarray(o, o + box.shape[2]) as never, (x * shape[1] + y) * shape[2] + box.lo[2]);
      o += box.shape[2];
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// ZScoreNormalization(use_mask_for_norm=True)
// ---------------------------------------------------------------------------

export interface ZScoreStats {
  mean: number;
  std: number;
  count: number;
}

/**
 * image[mask] = (image[mask] - mean) / max(std, 1e-8); voxels outside the mask are left
 * as they are (they are 0 by construction of the nonzero mask). Population std (ddof=0).
 */
export function zscoreInMask(image: Float32Array, mask: Uint8Array): { image: Float32Array; stats: ZScoreStats } {
  let count = 0;
  let sum = 0;
  for (let i = 0; i < image.length; i++) {
    if (mask[i]) {
      count++;
      sum += image[i];
    }
  }
  if (count === 0) throw new Error('Normalisation mask is empty.');
  const mean = sum / count;
  let sq = 0;
  for (let i = 0; i < image.length; i++) {
    if (mask[i]) {
      const d = image[i] - mean;
      sq += d * d;
    }
  }
  const std = Math.sqrt(sq / count);
  const denom = Math.max(std, 1e-8);
  const out = new Float32Array(image.length);
  for (let i = 0; i < image.length; i++) out[i] = mask[i] ? (image[i] - mean) / denom : image[i];
  return { image: out, stats: { mean, std, count } };
}

// ---------------------------------------------------------------------------
// resample_data_or_seg_to_shape (is_seg = False)
// ---------------------------------------------------------------------------

/** nnU-Net compute_new_shape: int(round(old_spacing / new_spacing * old_shape)). */
export function computeNewShape(shape: Shape3, spacing: readonly number[], newSpacing: readonly number[]): Shape3 {
  return [0, 1, 2].map((a) => roundHalfEven((spacing[a] / newSpacing[a]) * shape[a])) as Shape3;
}

const POLE = Math.sqrt(3) - 2;
/** scipy.ndimage _prepad_for_spline_filter pads 12 voxels in 'nearest' mode before spline_filter. */
const PAD = 12;

/** Cubic B-spline coefficients of a line, as scipy spline_filter1d after edge padding by 12. */
function splineCoefficients(line: Float64Array): Float64Array {
  const n = line.length + 2 * PAD;
  const c = new Float64Array(n);
  const last = line.length - 1;
  for (let i = 0; i < n; i++) c[i] = 6 * line[Math.min(Math.max(i - PAD, 0), last)];
  if (n === 1) return c;
  const zn = POLE ** (n - 1);
  let z = POLE;
  let first = c[0] + zn * c[n - 1];
  for (let i = 1; i < n - 1; i++) {
    first += z * (c[i] + zn * c[n - 1 - i]);
    z *= POLE;
  }
  c[0] = first / (1 - zn * zn);
  for (let i = 1; i < n; i++) c[i] += POLE * c[i - 1];
  c[n - 1] = ((POLE * c[n - 2] + c[n - 1]) * POLE) / (POLE * POLE - 1);
  for (let i = n - 2; i >= 0; i--) c[i] = POLE * (c[i + 1] - c[i]);
  return c;
}

type LineKernel = (line: Float64Array, out: Float64Array) => void;

/** skimage resize == scipy zoom(grid_mode=True, mode='nearest'): x_in = (o + 0.5) * in/out - 0.5. */
const cubicKernel: LineKernel = (line, out) => {
  const c = splineCoefficients(line);
  const scale = line.length / out.length;
  const lastC = c.length - 1;
  for (let o = 0; o < out.length; o++) {
    const x = (o + 0.5) * scale - 0.5 + PAD;
    const f = Math.floor(x);
    const t = x - f;
    const w0 = (1 - t) ** 3 / 6;
    const w1 = (4 - 6 * t * t + 3 * t ** 3) / 6;
    const w2 = (1 + 3 * t + 3 * t * t - 3 * t ** 3) / 6;
    const w3 = t ** 3 / 6;
    const at = (k: number) => c[Math.min(Math.max(k, 0), lastC)];
    out[o] = w0 * at(f - 1) + w1 * at(f) + w2 * at(f + 1) + w3 * at(f + 2);
  }
};

const linearKernel: LineKernel = (line, out) => {
  const scale = line.length / out.length;
  const last = line.length - 1;
  for (let o = 0; o < out.length; o++) {
    const x = Math.min(Math.max((o + 0.5) * scale - 0.5, 0), last);
    const f = Math.floor(x);
    const t = x - f;
    out[o] = line[f] * (1 - t) + line[Math.min(f + 1, last)] * t;
  }
};

/** scipy map_coordinates(order=0, mode='nearest') on c = (o + 0.5) * scale - 0.5. */
const nearestKernel: LineKernel = (line, out) => {
  const scale = line.length / out.length;
  const last = line.length - 1;
  for (let o = 0; o < out.length; o++) {
    const x = (o + 0.5) * scale - 0.5;
    out[o] = line[Math.min(Math.max(Math.floor(x + 0.5), 0), last)];
  }
};

function strides(s: Shape3): Shape3 {
  return [s[1] * s[2], s[2], 1];
}

function resampleAxis(data: Float32Array, shape: Shape3, axis: number, size: number, kernel: LineKernel) {
  if (shape[axis] === size) return { data, shape };
  const next: Shape3 = [shape[0], shape[1], shape[2]];
  next[axis] = size;
  const out = new Float32Array(product(next));
  const inS = strides(shape);
  const outS = strides(next);
  const [p, q] = [0, 1, 2].filter((a) => a !== axis);
  const line = new Float64Array(shape[axis]);
  const result = new Float64Array(size);
  for (let i = 0; i < shape[p]; i++) {
    for (let j = 0; j < shape[q]; j++) {
      const inBase = i * inS[p] + j * inS[q];
      const outBase = i * outS[p] + j * outS[q];
      for (let k = 0; k < shape[axis]; k++) line[k] = data[inBase + k * inS[axis]];
      kernel(line, result);
      for (let k = 0; k < size; k++) out[outBase + k * outS[axis]] = result[k];
    }
  }
  return { data: out, shape: next };
}

/**
 * nnU-Net get_do_separate_z + get_lowres_axis: the single coarsest axis when
 * max/min spacing > 3, else null (also null when two or three axes tie for coarsest).
 */
export function anisotropicAxis(spacing: readonly number[], threshold = 3): number | null {
  const max = Math.max(...spacing);
  const min = Math.min(...spacing);
  if (!(max / min > threshold)) return null;
  const axes = [0, 1, 2].filter((a) => spacing[a] === max);
  return axes.length === 1 ? axes[0] : null;
}

/**
 * resample_data_or_seg_to_shape(data, new_shape, current_spacing, new_spacing,
 *   is_seg=False, order, order_z=0, force_separate_z=None) for ONE channel.
 * order 3 -> cubic spline (images); order 1 -> linear (logits).
 * Output is clipped to the input range (skimage resize clip=True), per slice when separate-z.
 */
export function resampleToShape(
  data: Float32Array,
  shape: Shape3,
  newShape: Shape3,
  spacing: readonly number[],
  newSpacing: readonly number[],
  order: 1 | 3,
): Float32Array {
  if (shape[0] === newShape[0] && shape[1] === newShape[1] && shape[2] === newShape[2]) return data;
  const kernel = order === 3 ? cubicKernel : linearKernel;
  const axis = anisotropicAxis(spacing) ?? anisotropicAxis(newSpacing);
  let vol = { data, shape };
  for (const a of [0, 1, 2]) {
    if (a !== axis) vol = resampleAxis(vol.data, vol.shape, a, newShape[a], kernel);
  }
  if (axis === null) {
    let min = Infinity;
    let max = -Infinity;
    for (let i = 0; i < data.length; i++) {
      if (data[i] < min) min = data[i];
      if (data[i] > max) max = data[i];
    }
    const out = vol.data === data ? new Float32Array(data) : vol.data;
    for (let i = 0; i < out.length; i++) out[i] = Math.min(Math.max(out[i], min), max);
    return out;
  }
  // separate-z: clip each in-plane-resampled slice to its own input slice range, then nearest along `axis`
  const inS = strides(shape);
  const midS = strides(vol.shape);
  const [p, q] = [0, 1, 2].filter((a) => a !== axis);
  const out = vol.data === data ? new Float32Array(data) : vol.data;
  for (let k = 0; k < shape[axis]; k++) {
    let min = Infinity;
    let max = -Infinity;
    for (let i = 0; i < shape[p]; i++) {
      for (let j = 0; j < shape[q]; j++) {
        const v = data[k * inS[axis] + i * inS[p] + j * inS[q]];
        if (v < min) min = v;
        if (v > max) max = v;
      }
    }
    for (let i = 0; i < vol.shape[p]; i++) {
      for (let j = 0; j < vol.shape[q]; j++) {
        const idx = k * midS[axis] + i * midS[p] + j * midS[q];
        out[idx] = Math.min(Math.max(out[idx], min), max);
      }
    }
  }
  return resampleAxis(out, vol.shape, axis, newShape[axis], nearestKernel).data;
}
