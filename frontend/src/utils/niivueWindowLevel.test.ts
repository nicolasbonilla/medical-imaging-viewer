import { describe, it, expect } from 'vitest';
import { windowLevelToCalRange, sliceIndexToVoxelCentreFraction } from './niivueWindowLevel';

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

describe('sliceIndexToVoxelCentreFraction (store index → niivue axial crosshair fraction)', () => {
  // PRB-004: replaces sliceIndexToFraction (index / (depth − 1)), which addressed a position
  // between two voxel slices for most indices and the volume's outer edge for slice 0.
  it('rc073 addresses the centre of the voxel slice: (index + 0.5) / depth', () => {
    expect(sliceIndexToVoxelCentreFraction(0, 182)).toBeCloseTo(0.5 / 182, 12);
    expect(sliceIndexToVoxelCentreFraction(45, 182)).toBeCloseTo(45.5 / 182, 12);
    expect(sliceIndexToVoxelCentreFraction(181, 182)).toBeCloseTo(181.5 / 182, 12);
  });

  it('rc073 niivue reads it back as exactly that voxel slice (f · depth − 0.5 = index)', () => {
    for (const depth of [1, 2, 5, 60, 181, 182]) {
      for (let i = 0; i < depth; i++) {
        const f = sliceIndexToVoxelCentreFraction(i, depth)!;
        expect(f * depth - 0.5).toBeCloseTo(i, 9);
      }
    }
  });

  it('clamps out-of-range indices to the first and last slice', () => {
    expect(sliceIndexToVoxelCentreFraction(-5, 100)).toBeCloseTo(0.5 / 100, 12);
    expect(sliceIndexToVoxelCentreFraction(999, 100)).toBeCloseTo(99.5 / 100, 12);
  });

  it('a single slice is addressed at its centre', () => {
    expect(sliceIndexToVoxelCentreFraction(0, 1)).toBe(0.5);
  });

  it('returns null when the volume has no slices or the depth is not a number', () => {
    expect(sliceIndexToVoxelCentreFraction(0, 0)).toBeNull();
    expect(sliceIndexToVoxelCentreFraction(0, NaN)).toBeNull();
    expect(sliceIndexToVoxelCentreFraction(0, undefined as unknown as number)).toBeNull();
  });
});
