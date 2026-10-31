/**
 * PRB-008 — independent review of PR #71 (m4): the slice is kept only for an image on the same grid.
 * Two sequences of one study with the same number of slices but another matrix, voxel size, slice thickness or
 * stored orientation put the same index at another anatomical level: such an image opens on its middle slice.
 */
import { describe, it, expect } from 'vitest';
import { sliceIndexOnOpen } from './sliceOnOpen';

const img = (m: Record<string, unknown> = {}) => ({
  total_slices: 40,
  metadata: { rows: 256, columns: 256, slices: 40, pixel_spacing: [0.9, 0.9], slice_thickness: 3, anatomical_orientation: 'LAS', ...m },
});

describe('PRB-008 review — keep the slice only on the same grid', () => {
  it('prb008 same grid: the slice is kept', () => {
    expect(sliceIndexOnOpen(img(), img(), 30, true)).toBe(30);
  });
  for (const [what, change] of [
    ['matrix', { rows: 240 }],
    ['pixel spacing', { pixel_spacing: [1.0, 1.0] }],
    ['slice thickness', { slice_thickness: 1.5 }],
    ['stored orientation', { anatomical_orientation: 'RAS' }],
  ] as const) {
    it(`prb008 same slice count, other ${what}: the middle slice`, () => {
      expect(sliceIndexOnOpen(img(change as Record<string, unknown>), img(), 30, true)).toBe(19);
    });
  }
});
