// @vitest-environment node
/**
 * PRB-010 — re-review of PR #71 (R6): periventricular (orange) and deep white matter (vermillion) are the closest region
 * pair as drawn, and the pair that matters for DIS. A non-colour cue on the image: the label under the cursor is named
 * (the cursor readout of the sidebar), as the lesion rows and the legends already name the regions.
 */
import { describe, it, expect } from 'vitest';
import { labelUnderCursor } from './labelUnderCursor';

const LABELS = [
  { id: 0, name: 'Background', color: '#000000' },
  { id: 1, name: 'Periventricular', color: '#E69F00' },
  { id: 4, name: 'Deep White Matter', color: '#D55E00' },
];
// a 2-row x 3-column slice, internal order (row a0, column a1): row 0 = [1, 0, 4], row 1 = [0, 9, 1]
const SLICE = Uint8Array.from([1, 0, 4, 0, 9, 1]);

describe('PRB-010 R6 — the label under the cursor, by name', () => {
  it('rc076 R6 names the label at (column x, row y) of the slice', () => {
    expect(labelUnderCursor(SLICE, 3, 2, 0, 0, LABELS)).toEqual({ value: 1, name: 'Periventricular' });
    expect(labelUnderCursor(SLICE, 3, 2, 2, 0, LABELS)).toEqual({ value: 4, name: 'Deep White Matter' });
    expect(labelUnderCursor(SLICE, 3, 2, 2, 1, LABELS)).toEqual({ value: 1, name: 'Periventricular' });
  });
  it('rc076 R6 background, outside the slice or no mask: nothing', () => {
    expect(labelUnderCursor(SLICE, 3, 2, 1, 0, LABELS)).toBeNull();
    expect(labelUnderCursor(SLICE, 3, 2, 3, 0, LABELS)).toBeNull();
    expect(labelUnderCursor(SLICE, 3, 2, 0, 2, LABELS)).toBeNull();
    expect(labelUnderCursor(null, 3, 2, 0, 0, LABELS)).toBeNull();
    expect(labelUnderCursor(SLICE, 4, 2, 0, 0, LABELS)).toBeNull();   // dimensions that do not match the slice
  });
  it('rc076 R6 a value missing from the label table is reported with no name', () => {
    expect(labelUnderCursor(SLICE, 3, 2, 1, 1, LABELS)).toEqual({ value: 9, name: null });
  });
});
