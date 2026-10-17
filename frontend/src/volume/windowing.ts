/**
 * Full-bit-depth window/level for the client 2D viewer.
 *
 * The legacy path reduced each volume to 8 bits on the server (global min–max) and
 * re-requested a PNG for every window change. Here the window is applied in the
 * browser to the ORIGINAL scaled voxel values (float64 math on the stored data), so a
 * W/L change is a local repaint and no contrast is thrown away beforehand.
 *
 * Mapping (same as niivue's cal_min/cal_max, so the same C/W numbers look the same in
 * the 2D view and in the 3D panels):   lo = C - W/2, hi = C + W/2,
 *                                       grey = clamp(round((v - lo) / (hi - lo) * 255))
 *
 * `parityUint8` reproduces the server's `normalize_to_uint8` bit-for-bit (truncation,
 * global min–max) — used only to prove parity and to feed consumers that were
 * designed around the server's 8-bit slice (the Edge-AI quick screen).
 */
import { valueAtIndex, type NiftiVolume } from './nifti';
import { volumeStrides, type SliceView } from './sliceGeometry';

export interface WindowLevel {
  center: number;
  width: number;
}

export interface IntensityStats {
  min: number;
  max: number;
  /** Robust display range: 0.5th / 99.5th percentile of the non-background voxels. */
  robustLow: number;
  robustHigh: number;
  /** 256-bin histogram of finite voxels over [min, max]. */
  histogram: Uint32Array;
  finiteCount: number;
  nonFiniteCount: number;
}

/** Global statistics over the first volume (scaled values, NaN/Inf ignored). */
export function computeStats(vol: NiftiVolume): IntensityStats {
  const n = vol.raw.length;
  let min = Infinity, max = -Infinity, nonFinite = 0;
  for (let i = 0; i < n; i++) {
    const v = valueAtIndex(vol, i);
    if (!Number.isFinite(v)) { nonFinite++; continue; }
    if (v < min) min = v;
    if (v > max) max = v;
  }
  const histogram = new Uint32Array(256);
  const finiteCount = n - nonFinite;
  if (finiteCount === 0) {
    return { min: 0, max: 0, robustLow: 0, robustHigh: 0, histogram, finiteCount, nonFiniteCount: nonFinite };
  }
  // Fine histogram (4096 bins) for percentiles, coarse (256) for display.
  const FINE = 4096;
  const fine = new Uint32Array(FINE);
  const span = max - min;
  let zeroCount = 0;
  for (let i = 0; i < n; i++) {
    const v = valueAtIndex(vol, i);
    if (!Number.isFinite(v)) continue;
    if (v === 0) zeroCount++;
    const t = span > 0 ? (v - min) / span : 0;
    fine[Math.min(FINE - 1, Math.floor(t * FINE))]++;
    histogram[Math.min(255, Math.floor(t * 256))]++;
  }
  // Ignore the background (exact zeros) for the robust range when it dominates —
  // skull-stripped / registered volumes are mostly zeros and would pin the window.
  const ignoreZeros = zeroCount > 0.2 * finiteCount && finiteCount - zeroCount > 0.01 * finiteCount;
  const zeroBin = span > 0 ? Math.min(FINE - 1, Math.floor(((0 - min) / span) * FINE)) : 0;
  const counted = ignoreZeros ? finiteCount - zeroCount : finiteCount;
  const pct = (p: number) => {
    const target = p * counted;
    let acc = 0;
    for (let b = 0; b < FINE; b++) {
      acc += fine[b] - (ignoreZeros && b === zeroBin && min <= 0 && max >= 0 ? zeroCount : 0);
      if (acc >= target) return min + ((b + 0.5) / FINE) * span;
    }
    return max;
  };
  let robustLow = pct(0.005);
  let robustHigh = pct(0.995);
  if (!(robustHigh > robustLow)) { robustLow = min; robustHigh = max; }
  return { min, max, robustLow, robustHigh, histogram, finiteCount, nonFiniteCount: nonFinite };
}

export function windowFromRange(lo: number, hi: number): WindowLevel {
  return { center: (lo + hi) / 2, width: Math.max(hi - lo, Number.MIN_VALUE) };
}

/** "Auto" window — robust range (what the viewer opens with). */
export function autoWindow(stats: IntensityStats): WindowLevel {
  return windowFromRange(stats.robustLow, stats.robustHigh);
}

/** Full data range — the same contrast the legacy server PNG showed. */
export function fullRangeWindow(stats: IntensityStats): WindowLevel {
  return windowFromRange(stats.min, stats.max);
}

/** Effective [lo, hi]; a non-positive width never blanks the slice (falls back to data range). */
export function windowBounds(wl: WindowLevel, stats: IntensityStats): [number, number] {
  if (!(wl.width > 0) || !Number.isFinite(wl.center)) return [stats.min, stats.max];
  const lo = wl.center - wl.width / 2;
  let hi = wl.center + wl.width / 2;
  if (!(hi > lo)) hi = lo + 1e-6;
  return [lo, hi];
}

/** Grey level 0..255 for one value under [lo, hi]. Non-finite values render black. */
export function greyLevel(v: number, lo: number, hi: number): number {
  if (!Number.isFinite(v)) return 0;
  const t = (v - lo) / (hi - lo);
  if (t <= 0) return 0;
  if (t >= 1) return 255;
  return Math.round(t * 255);
}

/**
 * Fill `out` (RGBA, rows*cols*4) with the windowed slice in display order.
 * Returns the buffer for chaining.
 */
export function renderSliceRGBA(
  vol: NiftiVolume, view: SliceView, slice: number, wl: WindowLevel, stats: IntensityStats,
  out?: Uint8ClampedArray,
): Uint8ClampedArray {
  const { rows, cols } = view;
  const buf = out && out.length === rows * cols * 4 ? out : new Uint8ClampedArray(rows * cols * 4);
  const [lo, hi] = windowBounds(wl, stats);
  const { base, rowStep, colStep } = volumeStrides(view, vol.dims, slice);
  const scale = 255 / (hi - lo);
  const { raw, scaled, slope, inter } = vol;
  let p = 0;
  for (let r = 0; r < rows; r++) {
    let idx = base + r * rowStep;
    for (let c = 0; c < cols; c++, idx += colStep, p += 4) {
      const rv = raw[idx];
      const v = scaled ? rv * slope + inter : rv;
      let g: number;
      if (!Number.isFinite(v)) g = 0;
      else {
        const t = (v - lo) * scale;
        g = t <= 0 ? 0 : t >= 255 ? 255 : Math.round(t);
      }
      buf[p] = g; buf[p + 1] = g; buf[p + 2] = g; buf[p + 3] = 255;
    }
  }
  return buf;
}

/**
 * Server-parity 8-bit slice: numpy `((a - min) / (max - min) * 255).astype(uint8)`
 * over the GLOBAL min/max (backend image_utils.normalize_to_uint8), in display order.
 */
export function parityUint8Slice(vol: NiftiVolume, view: SliceView, slice: number, stats: IntensityStats): Uint8Array {
  const { rows, cols } = view;
  const out = new Uint8Array(rows * cols);
  const { min, max } = stats;
  const span = max - min;
  const { base, rowStep, colStep } = volumeStrides(view, vol.dims, slice);
  let p = 0;
  for (let r = 0; r < rows; r++) {
    let idx = base + r * rowStep;
    for (let c = 0; c < cols; c++, idx += colStep) {
      const v = valueAtIndex(vol, idx);
      out[p++] = span > 0 ? (((v - min) / span) * 255.0) | 0 : 0;
    }
  }
  return out;
}

/** Histogram (256 bins over [min, max]) of one displayed slice, for the side panel. */
export function sliceHistogram(vol: NiftiVolume, view: SliceView, slice: number, stats: IntensityStats): number[] {
  const hist = new Array<number>(256).fill(0);
  const span = stats.max - stats.min;
  const { base, rowStep, colStep } = volumeStrides(view, vol.dims, slice);
  for (let r = 0; r < view.rows; r++) {
    let idx = base + r * rowStep;
    for (let c = 0; c < view.cols; c++, idx += colStep) {
      const v = valueAtIndex(vol, idx);
      if (!Number.isFinite(v)) continue;
      const t = span > 0 ? (v - stats.min) / span : 0;
      hist[Math.min(255, Math.max(0, Math.floor(t * 256)))]++;
    }
  }
  return hist;
}
