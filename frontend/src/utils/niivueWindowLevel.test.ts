import { describe, it, expect } from 'vitest';
import { windowLevelToCalRange, sliceIndexToFraction } from './niivueWindowLevel';

describe('windowLevelToCalRange (DICOM VOI-LUT → niivue cal range)', () => {
  it('maps an active window to center ± width/2', () => {
    expect(windowLevelToCalRange(40, 80, 0, 100, 0, 100)).toEqual({ calMin: 0, calMax: 80 });
    expect(windowLevelToCalRange(600, 1600, 0, 4000, 0, 4000)).toEqual({ calMin: -200, calMax: 1400 });
  });

  it('handles negative centers (signed intensities)', () => {
    expect(windowLevelToCalRange(-20, 100, -500, 500, -500, 500)).toEqual({ calMin: -70, calMax: 30 });
  });

  it('never produces a degenerate range when a window is active (min < max)', () => {
    // includes the pathological float64 collapse (huge center + tiny width)
    for (const [c, w] of [[0, 1], [1000, 0.001], [-3, 6], [50, 4000], [1e10, 1e-6]] as const) {
      const { calMin, calMax } = windowLevelToCalRange(c, w, undefined, undefined, 0, 1);
      expect(calMin).toBeLessThan(calMax);
    }
  });

  it('falls back to the volume global range when no window is active (width <= 0)', () => {
    expect(windowLevelToCalRange(0, 0, 12, 987, 0, 1)).toEqual({ calMin: 12, calMax: 987 });
    expect(windowLevelToCalRange(500, -5, 12, 987, 0, 1)).toEqual({ calMin: 12, calMax: 987 });
  });

  it('falls back to the current cal range when global range is undefined', () => {
    expect(windowLevelToCalRange(0, 0, undefined, undefined, 3, 44)).toEqual({ calMin: 3, calMax: 44 });
    // partial: only one global defined -> the defined one wins, the other falls back
    expect(windowLevelToCalRange(0, 0, undefined, 900, 3, 44)).toEqual({ calMin: 3, calMax: 900 });
  });
});

describe('sliceIndexToFraction (store index → niivue axial depth fraction)', () => {
  it('maps first/last slice to the [0, 0.999] extent', () => {
    expect(sliceIndexToFraction(0, 182)).toBe(0);
    expect(sliceIndexToFraction(181, 182)).toBe(0.999); // last slice clamped inside the volume
  });

  it('maps a mid slice proportionally', () => {
    expect(sliceIndexToFraction(90, 181)).toBeCloseTo(0.5, 5);
  });

  it('clamps out-of-range indices into [0, 0.999]', () => {
    expect(sliceIndexToFraction(-5, 100)).toBe(0);
    expect(sliceIndexToFraction(999, 100)).toBe(0.999);
  });

  it('returns null for a non-navigable volume (depth <= 1 or non-finite)', () => {
    expect(sliceIndexToFraction(0, 1)).toBeNull();
    expect(sliceIndexToFraction(0, 0)).toBeNull();
    expect(sliceIndexToFraction(0, NaN)).toBeNull();
    expect(sliceIndexToFraction(0, undefined as unknown as number)).toBeNull();
  });
});
