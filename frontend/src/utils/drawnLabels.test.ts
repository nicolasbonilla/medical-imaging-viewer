/**
 * Release 2026-10-25 — independent review of PR #69, B1 (3) and M3: what the 2D canvas draws, and the check that the
 * confirmation runs. Written before the module existed (fails on dd22708: no module).
 */
import { describe, it, expect } from 'vitest';
import {
  distinctMaskValues, idsWithoutLabel, undrawnMaskValues, MIN_VISIBLE_LESION_OPACITY, UNLABELLED_FALLBACK_COLOR,
} from './drawnLabels';

const LABELS = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
  { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true },
  { id: 2, name: 'Juxtacortical', color: '#00CC00', opacity: 0.6, visible: true },
];

describe('B1 (3): every value of the mask gets a colour', () => {
  it('rc070 release b1 values the label table does not name are listed for the fallback colour', () => {
    const ids = idsWithoutLabel(LABELS);
    expect(ids).toContain(3);
    expect(ids).toContain(255);
    expect(ids).not.toContain(0);
    expect(ids).not.toContain(1);
    expect(ids).not.toContain(2);
    expect(UNLABELLED_FALLBACK_COLOR).toMatch(/^#[0-9A-F]{6}$/i);
  });

  it('rc070 release b1 the distinct non-zero values of a mask', () => {
    expect(distinctMaskValues(new Uint8Array([0, 0, 1, 3, 3, 4, 0, 1]))).toEqual([1, 3, 4]);
    expect(distinctMaskValues(new Uint8Array([0, 0]))).toEqual([]);
  });
});

describe('M3: the check before a confirmation', () => {
  const base = { values: [1, 2], labels: LABELS, labelVisibility: { 0: false, 1: true, 2: true },
                 isOverlayVisible: true, lesionOpacity: 0.6 };

  it('rc071 release m3 nothing to report when every value is drawn', () => {
    expect(undrawnMaskValues(base)).toEqual([]);
  });

  it('rc071 release m3 a value without label, a hidden label, the overlay off and a low opacity are each reported', () => {
    expect(undrawnMaskValues({ ...base, values: [1, 2, 7] })).toEqual([{ kind: 'no_label', value: 7 }]);
    expect(undrawnMaskValues({ ...base, labelVisibility: { 1: true, 2: false } }))
      .toEqual([{ kind: 'hidden', value: 2, name: 'Juxtacortical' }]);
    expect(undrawnMaskValues({ ...base, isOverlayVisible: false })).toEqual([{ kind: 'overlay_off' }]);
    expect(undrawnMaskValues({ ...base, lesionOpacity: MIN_VISIBLE_LESION_OPACITY - 0.01 })[0].kind).toBe('opacity_low');
    expect(undrawnMaskValues({ ...base, labels: [LABELS[0], { ...LABELS[1], opacity: 0 }, LABELS[2]] }))
      .toEqual([{ kind: 'faint', value: 1, name: 'Periventricular' }]);
  });
});
