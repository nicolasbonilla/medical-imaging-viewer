/**
 * FLAIR contrast gate, part 2 — image content (RC-049, HAZ-001 cause "wrong input contrast").
 *
 * Why: FLAMeS was trained on FLAIR only. A skull-stripped T1 (or T2) loaded by mistake passes every
 * geometric gate and can yield an empty or wrong "lesion" mask (reviewer finding: a T1 of a patient with
 * 34 expert lesions gave "0 lesions"). The file name is never trusted.
 *
 * Physics used (all measured inside the brain, independent of the file name and of scanner scaling):
 *  - GM/WM ordering (T1 rule): on T1, white matter is clearly brighter than the cortex; on FLAIR, cortex is
 *    as bright as or brighter than white matter. Measured as `deepOverCortex` = median intensity of tissue
 *    far from CSF (> 6 mm, white matter) / 75th percentile of tissue next to CSF (1.5-3 mm, cortex), after
 *    dividing by a 15 mm local tissue mean so that smooth bias fields (common on 3 T FLAIR) cancel.
 *  - CSF brightness (T2/PD rule): on T2/PD, CSF is the brightest structure; on FLAIR it is suppressed.
 *    Measured as the share of brain voxels brighter than 1.6x the dominant tissue intensity.
 *  - Grey-matter class (second T1 rule): on T1 the cortex forms a large darker class (0.45-0.8 x the tissue mode).
 * Fixed thresholds (FLAIR_GATE). Leave-one-dataset-out validation (FLAIR-GATE-VALIDATION.md) shows content alone
 * lets T1/T2 volumes of an unseen scanner through, so the content check can only REFUSE: acceptance also needs
 * positive evidence (header, or explicit clinician confirmation). A refused FLAIR is a safe failure.
 */
import type { Dims3 } from './axes';
import { MIN_FLAIR_TI_MS, type HeaderEvidence } from './headerEvidence';
import { nonzeroMaskFilled } from './preprocess';

export interface ContrastFeatures {
  /** skull clue: share of very dark voxels inside the head/brain region (headDarkFraction) */
  darkFraction: number;
  /** skull clue: share of voxels brighter than 1.5x the tissue mode within 6 mm of the region boundary (scalp fat) */
  rimBrightFraction: number;
  /** dominant (upper) tissue intensity mode */
  tissueMode: number;
  uOverMedian: number;
  /** median(deep) / median(near), raw intensities */
  rawDeepOverNear: number;
  /** median(deep) / median(near) of locally normalised intensities */
  locDeepOverNear: number;
  /** median(deep) / p75(near), locally normalised */
  locDeepOverNearP75: number;
  /** median(deep) / p90(near), locally normalised */
  locDeepOverNearP90: number;
  /** p75(deep) / p75(near), locally normalised */
  locDeepP75OverNearP75: number;
  q99OverMode: number;
  fracAbove1p6: number;
  frac45to80: number;
  nearVoxels: number;
  deepVoxels: number;
  /** grid the features were computed on (after optional block averaging) */
  workingSpacing: [number, number, number];
}

export class FlamesContrastError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'FlamesContrastError';
  }
}

// ---------------------------------------------------------------------------------------------
// small numerical helpers (NIfTI storage order: index = i + nx * (j + ny * k))
// ---------------------------------------------------------------------------------------------

function percentileSorted(sorted: Float32Array, p: number): number {
  if (sorted.length === 0) return NaN;
  const pos = (p / 100) * (sorted.length - 1);
  const lo = Math.floor(pos);
  const hi = Math.min(sorted.length - 1, lo + 1);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

function collectSorted(values: Float32Array, mask: Uint8Array): Float32Array {
  let n = 0;
  for (let v = 0; v < mask.length; v++) if (mask[v]) n++;
  const out = new Float32Array(n);
  for (let v = 0, o = 0; v < mask.length; v++) if (mask[v]) out[o++] = values[v];
  return out.sort();
}

/** Block-average to a working grid of >= ~0.9 mm (keeps the cost bounded on 0.5 mm 3D FLAIRs). */
export function downsampleForGate(
  data: Float32Array,
  dims: Dims3,
  spacing: Dims3,
): { data: Float32Array; dims: [number, number, number]; spacing: [number, number, number] } {
  const f = spacing.map((s) => Math.max(1, Math.round(0.9 / s))) as [number, number, number];
  if (f[0] === 1 && f[1] === 1 && f[2] === 1) return { data, dims: [...dims] as [number, number, number], spacing: [...spacing] as [number, number, number] };
  const [nx, ny, nz] = dims;
  const ox = Math.floor(nx / f[0]);
  const oy = Math.floor(ny / f[1]);
  const oz = Math.floor(nz / f[2]);
  const out = new Float32Array(ox * oy * oz);
  const cnt = f[0] * f[1] * f[2];
  for (let k = 0; k < oz; k++)
    for (let j = 0; j < oy; j++)
      for (let i = 0; i < ox; i++) {
        let s = 0;
        let nzc = 0;
        for (let c = 0; c < f[2]; c++)
          for (let b = 0; b < f[1]; b++)
            for (let a = 0; a < f[0]; a++) {
              const v = data[i * f[0] + a + nx * (j * f[1] + b + ny * (k * f[2] + c))];
              s += v;
              if (v !== 0) nzc++;
            }
        // a block is inside the brain only if most of it is nonzero (keeps the boundary sharp)
        out[i + ox * (j + oy * k)] = nzc * 2 >= cnt ? s / cnt : 0;
      }
  return { data: out, dims: [ox, oy, oz], spacing: [spacing[0] * f[0], spacing[1] * f[1], spacing[2] * f[2]] };
}

/** Upper tissue mode: argmax of a smoothed 200-bin histogram over [0, p99.5], restricted to >= median. */
export function upperTissueMode(sortedValues: Float32Array): number {
  const hi = percentileSorted(sortedValues, 99.5);
  const med = percentileSorted(sortedValues, 50);
  const bins = 200;
  const h = new Float64Array(bins);
  const w = hi / bins;
  if (!(w > 0)) return med;
  for (let n = 0; n < sortedValues.length; n++) {
    const v = sortedValues[n];
    if (v < 0 || v > hi) continue;
    h[Math.min(bins - 1, Math.floor(v / w))]++;
  }
  const sigma = 2;
  const radius = 8;
  const kernel: number[] = [];
  for (let t = -radius; t <= radius; t++) kernel.push(Math.exp((-t * t) / (2 * sigma * sigma)));
  let best = -1;
  let arg = -1;
  for (let b = 0; b < bins; b++) {
    let s = 0;
    for (let t = -radius; t <= radius; t++) {
      let q = b + t;
      if (q < 0) q = -q - 1; // reflect
      if (q >= bins) q = 2 * bins - q - 1;
      s += h[q] * kernel[t + radius];
    }
    const centre = (b + 0.5) * w;
    if (centre >= med && s > best) {
      best = s;
      arg = b;
    }
  }
  return arg < 0 ? med : (arg + 0.5) * w;
}

/** Exact squared Euclidean distance transform along one line (Felzenszwalb & Huttenlocher). */
function edt1d(f: Float64Array, n: number, w2: number, d: Float64Array, v: Int32Array, z: Float64Array): void {
  let k = 0;
  v[0] = 0;
  z[0] = -Infinity;
  z[1] = Infinity;
  for (let q = 1; q < n; q++) {
    if (f[q] === Infinity) continue;
    if (f[v[k]] === Infinity) {
      v[k] = q;
      continue;
    }
    let s = (f[q] + w2 * q * q - (f[v[k]] + w2 * v[k] * v[k])) / (2 * w2 * (q - v[k]));
    while (s <= z[k]) {
      k--;
      s = (f[q] + w2 * q * q - (f[v[k]] + w2 * v[k] * v[k])) / (2 * w2 * (q - v[k]));
    }
    k++;
    v[k] = q;
    z[k] = s;
    z[k + 1] = Infinity;
  }
  k = 0;
  for (let q = 0; q < n; q++) {
    while (z[k + 1] < q) k++;
    const dq = q - v[k];
    d[q] = f[v[k]] === Infinity ? Infinity : w2 * dq * dq + f[v[k]];
  }
}

/**
 * Distance (mm) from each foreground voxel to the nearest background voxel, treating everything
 * outside the array as background (scipy distance_transform_edt on the 1-voxel zero-padded mask).
 */
export function distanceToBackgroundMm(mask: Uint8Array, dims: Dims3, spacing: Dims3): Float32Array {
  const [nx, ny, nz] = dims;
  const px = nx + 2;
  const py = ny + 2;
  const pz = nz + 2;
  const g = new Float64Array(px * py * pz).fill(0);
  for (let k = 0; k < nz; k++)
    for (let j = 0; j < ny; j++)
      for (let i = 0; i < nx; i++) g[i + 1 + px * (j + 1 + py * (k + 1))] = mask[i + nx * (j + ny * k)] ? Infinity : 0;
  const maxN = Math.max(px, py, pz);
  const f = new Float64Array(maxN);
  const d = new Float64Array(maxN);
  const v = new Int32Array(maxN);
  const z = new Float64Array(maxN + 1);
  const pass = (len: number, stride: number, count: number, base: (c: number) => number, w2: number) => {
    for (let c = 0; c < count; c++) {
      const o = base(c);
      for (let q = 0; q < len; q++) f[q] = g[o + q * stride];
      edt1d(f, len, w2, d, v, z);
      for (let q = 0; q < len; q++) g[o + q * stride] = d[q];
    }
  };
  pass(px, 1, py * pz, (c) => c * px, spacing[0] * spacing[0]);
  pass(py, px, px * pz, (c) => (c % px) + px * py * Math.floor(c / px), spacing[1] * spacing[1]);
  pass(pz, px * py, px * py, (c) => c, spacing[2] * spacing[2]);
  const out = new Float32Array(nx * ny * nz);
  for (let k = 0; k < nz; k++)
    for (let j = 0; j < ny; j++)
      for (let i = 0; i < nx; i++) out[i + nx * (j + ny * k)] = Math.sqrt(g[i + 1 + px * (j + 1 + py * (k + 1))]);
  return out;
}

/** Three successive box filters per axis (~Gaussian of the given sigma in mm), zero outside the array. */
export function approxGaussian(data: Float32Array, dims: Dims3, spacing: Dims3, sigmaMm: number): Float32Array {
  const [nx, ny, nz] = dims;
  let cur = Float32Array.from(data);
  let tmp = new Float32Array(cur.length);
  const strides = [1, nx, nx * ny];
  const lens = [nx, ny, nz];
  for (let axis = 0; axis < 3; axis++) {
    const sigma = sigmaMm / spacing[axis];
    const r = Math.max(0, Math.round((Math.sqrt(4 * sigma * sigma + 1) - 1) / 2));
    if (r === 0) continue;
    const len = lens[axis];
    const stride = strides[axis];
    const width = 2 * r + 1;
    const line = new Float64Array(len);
    for (let rep = 0; rep < 3; rep++) {
      for (let base = 0; base < cur.length; base++) {
        // iterate only over line starts
        const coord = axis === 0 ? base % nx : axis === 1 ? Math.floor(base / nx) % ny : Math.floor(base / (nx * ny));
        if (coord !== 0) continue;
        for (let q = 0; q < len; q++) line[q] = cur[base + q * stride];
        let acc = 0;
        for (let q = 0; q <= Math.min(r, len - 1); q++) acc += line[q];
        for (let q = 0; q < len; q++) {
          tmp[base + q * stride] = acc / width;
          const add = q + r + 1;
          const sub = q - r;
          if (add < len) acc += line[add];
          if (sub >= 0) acc -= line[sub];
        }
      }
      const sw = cur;
      cur = tmp;
      tmp = sw;
    }
  }
  return cur;
}

/**
 * Skull clue (RC-043): share of very dark voxels (< 0.25 x tissue mode) inside the region the model would
 * see — the hole-filled nonzero mask (nnU-Net crop_to_nonzero). Bone is dark in every sequence (and so is
 * CSF on FLAIR): an image that still contains the skull has a thick dark layer inside that region, also
 * when its background was set to zero (the zero gap between scalp and brain is enclosed, hence filled);
 * a skull-stripped brain has only its CSF.
 */
export function headDarkFraction(data: Float32Array, region: Uint8Array, mode: number): number {
  let inside = 0;
  let dark = 0;
  const hi = 0.25 * mode;
  for (let v = 0; v < data.length; v++) {
    if (!region[v]) continue;
    inside++;
    if (data[v] < hi) dark++;
  }
  return inside ? dark / inside : 0;
}

/**
 * Skull clue 2 (RC-043): share of voxels brighter than 1.5 x the tissue mode within 6 mm of the boundary of the
 * hole-filled nonzero region. Scalp and subcutaneous fat are bright on FLAIR and lie at the edge of a head that
 * still has its skull — also when the background was set to zero — while the edge of a skull-stripped brain is
 * cortex and CSF (validated in FLAIR-GATE-VALIDATION.md).
 */
export function rimBrightFraction(data: Float32Array, region: Uint8Array, dims: Dims3, spacing: Dims3, mode: number): number {
  const d = distanceToBackgroundMm(region, dims, spacing);
  let rim = 0;
  let bright = 0;
  const hi = 1.5 * mode;
  for (let v = 0; v < data.length; v++) {
    if (!region[v] || d[v] > 6) continue;
    rim++;
    if (data[v] > hi) bright++;
  }
  return rim ? bright / rim : 0;
}

export function computeContrastFeatures(data0: Float32Array, dims0: Dims3, spacing0: Dims3): ContrastFeatures {
  const { data, dims, spacing } = downsampleForGate(data0, dims0, spacing0);
  const n = data.length;
  // nnU-Net crop_to_nonzero mask (hole-filled), C-order shape (k, j, i) of the NIfTI storage order
  const m = nonzeroMaskFilled(data, [dims[2], dims[1], dims[0]]);
  const brainVals = collectSorted(data, m);
  if (brainVals.length < 1000) throw new FlamesContrastError('Too few brain voxels to check the image contrast.');
  const U = upperTissueMode(brainVals);
  const med = percentileSorted(brainVals, 50);
  const tissue = new Uint8Array(n);
  const tissueVals = new Float32Array(n);
  for (let v = 0; v < n; v++) {
    if (m[v] && data[v] > 0.45 * U) {
      tissue[v] = 1;
      tissueVals[v] = data[v];
    }
  }
  const dist = distanceToBackgroundMm(tissue, dims, spacing);
  const num = approxGaussian(tissueVals, dims, spacing, 15);
  const den = approxGaussian(Float32Array.from(tissue), dims, spacing, 15);
  const inorm = new Float32Array(n);
  const near = new Uint8Array(n);
  const deep = new Uint8Array(n);
  for (let v = 0; v < n; v++) {
    if (!tissue[v]) continue;
    const local = den[v] > 1e-3 ? num[v] / den[v] : 0;
    inorm[v] = local > 0 ? data[v] / local : 0;
    if (dist[v] > 1.5 && dist[v] <= 3) near[v] = 1;
    else if (dist[v] > 6) deep[v] = 1;
  }
  const nearRaw = collectSorted(data, near);
  const deepRaw = collectSorted(data, deep);
  const nearLoc = collectSorted(inorm, near);
  const deepLoc = collectSorted(inorm, deep);
  let above16 = 0;
  let mid = 0;
  for (let q = 0; q < brainVals.length; q++) {
    const r = brainVals[q] / U;
    if (r > 1.6) above16++;
    if (r >= 0.45 && r < 0.8) mid++;
  }
  const p = percentileSorted;
  return {
    darkFraction: headDarkFraction(data, m, U),
    rimBrightFraction: rimBrightFraction(data, m, dims, spacing, U),
    tissueMode: U,
    uOverMedian: U / med,
    rawDeepOverNear: p(deepRaw, 50) / p(nearRaw, 50),
    locDeepOverNear: p(deepLoc, 50) / p(nearLoc, 50),
    locDeepOverNearP75: p(deepLoc, 50) / p(nearLoc, 75),
    locDeepOverNearP90: p(deepLoc, 50) / p(nearLoc, 90),
    locDeepP75OverNearP75: p(deepLoc, 75) / p(nearLoc, 75),
    q99OverMode: p(brainVals, 99) / U,
    fracAbove1p6: above16 / brainVals.length,
    frac45to80: mid / brainVals.length,
    nearVoxels: nearRaw.length,
    deepVoxels: deepRaw.length,
    workingSpacing: spacing,
  };
}

/**
 * Content thresholds, fitted on ALL local public data (MSLesSeg, open_ms_data, ISBI-2015) for 100 % refusal of the
 * T1 / T1-post / T2 volumes (specificity first; FLAIR-GATE-VALIDATION.md). Leave-one-dataset-out validation shows
 * that content alone does NOT guarantee this on an unseen scanner, so a FLAIR is accepted only with POSITIVE
 * evidence as well (header, or an explicit clinician confirmation recorded with the draft) — fail closed.
 *   content says FLAIR  <=>  deepOverCortex <= 0.915 AND frac45to80 <= 0.27 AND fracAbove1p6 <= 0.025
 */
export const FLAIR_GATE = Object.freeze({
  version: 'flair-gate/2',
  /** T1 rule 1: white matter clearly brighter than cortex (locally normalised) => not FLAIR */
  maxDeepOverCortex: 0.915,
  /** T1 rule 2: a large darker grey-matter class (0.45-0.8 x the tissue mode), as on T1-weighted images */
  maxGreyClassFraction: 0.27,
  /** T2/PD rule: too many voxels brighter than 1.6x the tissue mode (bright CSF) => not FLAIR */
  maxBrightFraction: 0.025,
  /** minimum voxels in each band for the measurement to count */
  minBandVoxels: 500,
});

/** The T1-rule statistic (reported as the gate "score"; lower = more FLAIR-like). */
export function flairScore(f: ContrastFeatures): number {
  return f.locDeepOverNearP75;
}

export type SequenceEvidence = 'header' | 'clinician';

export interface ContrastAssessment {
  ok: boolean;
  score: number;
  threshold: number;
  header: HeaderEvidence;
  features: ContrastFeatures | null;
  /** positive evidence that made the input acceptable (only when ok) */
  sequenceEvidence?: SequenceEvidence;
  reason?: string;
}

/**
 * True only when the file itself proves an inversion-recovery FLAIR: an inversion time >= MIN_FLAIR_TI_MS and
 * nothing in the header naming another sequence. A free-text label such as "flair" alone is NOT proof (any
 * converter or user can write it); it is kept as supporting information only.
 */
export function headerProvesFlair(header: HeaderEvidence): boolean {
  return (
    header.verdict === 'supports' &&
    header.inversionTimeMs !== undefined &&
    Number.isFinite(header.inversionTimeMs) &&
    header.inversionTimeMs >= MIN_FLAIR_TI_MS
  );
}

/**
 * RC-049 (flair-gate/2). Header evidence that contradicts FLAIR refuses. The image content must look like a FLAIR,
 * but content is REFUSAL-ONLY: leave-one-dataset-out validation showed that no content threshold keeps every T1/T2
 * of an unseen scanner out. Acceptance therefore also needs POSITIVE evidence, fail closed: the clinician explicitly
 * confirmed the sequence of this file before the run (recorded with the draft, with the confirming user), or the
 * file proves an inversion-recovery FLAIR (long inversion time). Neither => refused.
 */
export function decideFlairContrast(
  features: ContrastFeatures,
  header: HeaderEvidence,
  opts: { clinicianConfirmedFlair?: boolean } = {},
): ContrastAssessment {
  const score = flairScore(features);
  const base = { score, threshold: FLAIR_GATE.maxDeepOverCortex, header, features };
  if (header.verdict === 'contradicts') {
    return {
      ok: false,
      ...base,
      reason: `The image header indicates this is not a FLAIR (${header.reasons.join('; ')}). No segmentation was produced.`,
    };
  }
  const measurable =
    Number.isFinite(score) &&
    Number.isFinite(features.fracAbove1p6) &&
    Number.isFinite(features.frac45to80) &&
    features.nearVoxels >= FLAIR_GATE.minBandVoxels &&
    features.deepVoxels >= FLAIR_GATE.minBandVoxels;
  if (!measurable) {
    return {
      ok: false,
      ...base,
      reason: 'The image contrast could not be measured (too little brain tissue at this resolution), so it cannot be ' +
        'confirmed as a FLAIR. No segmentation was produced.',
    };
  }
  if (score > FLAIR_GATE.maxDeepOverCortex) {
    return {
      ok: false,
      ...base,
      reason: 'The image does not look like a FLAIR: white matter is brighter than the cortex, as on a T1-weighted ' +
        'image. FLAMeS works only on FLAIR; no segmentation was produced.',
    };
  }
  if (features.frac45to80 > FLAIR_GATE.maxGreyClassFraction) {
    return {
      ok: false,
      ...base,
      reason: 'The image does not look like a FLAIR: it has a large, darker grey-matter class, as on a T1-weighted ' +
        'image. FLAMeS works only on FLAIR; no segmentation was produced.',
    };
  }
  if (features.fracAbove1p6 > FLAIR_GATE.maxBrightFraction) {
    return {
      ok: false,
      ...base,
      reason: 'The image does not look like a FLAIR: fluid (CSF) is bright, as on a T2-weighted or PD image. ' +
        'FLAMeS works only on FLAIR; no segmentation was produced.',
    };
  }
  // The clinician's confirmation is recorded first (it names a person); the header alone suffices only with a
  // long inversion time.
  const sequenceEvidence: SequenceEvidence | undefined =
    opts.clinicianConfirmedFlair === true ? 'clinician' : headerProvesFlair(header) ? 'header' : undefined;
  if (!sequenceEvidence) {
    return {
      ok: false,
      ...base,
      reason: 'The sequence is not confirmed as FLAIR: the file does not prove it (no FLAIR inversion time) and the image ' +
        'content alone cannot prove it. Confirm that the selected image is a skull-stripped T2-FLAIR, then run again. ' +
        'No segmentation was produced.',
    };
  }
  return { ok: true, ...base, sequenceEvidence };
}

export function assessFlairContrast(
  data: Float32Array,
  dims: Dims3,
  spacing: Dims3,
  header: HeaderEvidence,
  opts: { clinicianConfirmedFlair?: boolean } = {},
): ContrastAssessment {
  return decideFlairContrast(computeContrastFeatures(data, dims, spacing), header, opts);
}
