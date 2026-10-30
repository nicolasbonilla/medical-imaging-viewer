/**
 * PRB-008 — the slice an image opens on (rule in utils/sliceOnOpen.ts). The behaviour on the real
 * viewer page is tested in ViewerApp.prb007.test.tsx; these pin the rule itself.
 */
import { describe, it, expect } from 'vitest';
import { middleSliceIndex, sliceCount, sliceIndexOnOpen } from './sliceOnOpen';

const vol = (n: number) => ({ total_slices: n });

describe('PRB-008 — slice on open', () => {
  it('prb008 middle slice: floor((n - 1) / 2)', () => {
    expect(middleSliceIndex(182)).toBe(90); // shown as 91/182
    expect(middleSliceIndex(181)).toBe(90); // the exact centre of an odd volume
    expect(middleSliceIndex(7)).toBe(3);
    expect(middleSliceIndex(2)).toBe(0);
    expect(middleSliceIndex(1)).toBe(0);
    expect(middleSliceIndex(0)).toBe(0);
    expect(middleSliceIndex(NaN)).toBe(0);
  });

  it('prb008 the first image opens on its middle slice, never slice 0 of a volume', () => {
    expect(sliceIndexOnOpen(vol(182), null, 0, false)).toBe(90);
    expect(sliceIndexOnOpen(vol(182), null, 0, true)).toBe(90);
  });

  it('prb008 same study, same size: the slice is kept', () => {
    expect(sliceIndexOnOpen(vol(182), vol(182), 120, true)).toBe(120);
    expect(sliceIndexOnOpen(vol(182), vol(182), 0, true)).toBe(0);
  });

  it('prb008 another size, or another study: the middle slice', () => {
    expect(sliceIndexOnOpen(vol(60), vol(182), 120, true)).toBe(29);
    expect(sliceIndexOnOpen(vol(182), vol(176), 100, true)).toBe(90);
    expect(sliceIndexOnOpen(vol(182), vol(182), 120, false)).toBe(90);
  });

  it('prb008 a kept index is never outside the new image', () => {
    expect(sliceIndexOnOpen(vol(5), vol(5), 9, true)).toBe(2);
    expect(sliceIndexOnOpen(vol(5), vol(5), -1, true)).toBe(2);
  });

  it('prb008 slice count from total_slices, else from the slices list; unknown is 0', () => {
    expect(sliceCount({ total_slices: 9 })).toBe(9);
    expect(sliceCount({ slices: [1, 2, 3] })).toBe(3);
    expect(sliceCount(null)).toBe(0);
    expect(sliceIndexOnOpen({}, null, 4, false)).toBe(0);
  });
});
