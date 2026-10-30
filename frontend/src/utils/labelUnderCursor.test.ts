// @vitest-environment node
/**
 * PRB-010 — re-review of PR #71 (R6): periventricular (orange) and deep white matter (vermillion) are the closest region
 * pair as drawn, and the pair that matters for DIS. A non-colour cue on the image: the label under the cursor is named
 * (the cursor readout of the sidebar), as the lesion rows and the legends already name the regions.
 *
 * Final check (F1): the 2D overlay draws a mask whose rows and columns are swapped against the image (older back-end
 * masks; only visible on a non-square image) transposed. The readout must name the label the overlay DRAWS under the
 * cursor — the same rule from the same function (utils/maskDisplayLayout.ts) — and nothing for a mask the overlay
 * cannot place on the image.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect } from 'vitest';
import { labelUnderCursor } from './labelUnderCursor';
import * as layout from './maskDisplayLayout';

const LABELS = [
  { id: 0, name: 'Background', color: '#000000' },
  { id: 1, name: 'Periventricular', color: '#E69F00' },
  { id: 4, name: 'Deep White Matter', color: '#D55E00' },
];
// a 2-row x 3-column slice, internal order (row a0, column a1): row 0 = [1, 0, 4], row 1 = [0, 9, 1]
const SLICE = Uint8Array.from([1, 0, 4, 0, 9, 1]);
const SAME = { width: 3, height: 2 };   // the image: 3 columns, 2 rows

describe('PRB-010 R6 — the label under the cursor, by name', () => {
  it('rc076 R6 names the label at (column x, row y) of the slice', () => {
    expect(labelUnderCursor(SLICE, SAME, 3, 2, 0, 0, LABELS)).toEqual({ value: 1, name: 'Periventricular' });
    expect(labelUnderCursor(SLICE, SAME, 3, 2, 2, 0, LABELS)).toEqual({ value: 4, name: 'Deep White Matter' });
    expect(labelUnderCursor(SLICE, SAME, 3, 2, 2, 1, LABELS)).toEqual({ value: 1, name: 'Periventricular' });
  });
  it('rc076 R6 background, outside the slice or no mask: nothing', () => {
    expect(labelUnderCursor(SLICE, SAME, 3, 2, 1, 0, LABELS)).toBeNull();
    expect(labelUnderCursor(SLICE, SAME, 3, 2, 3, 0, LABELS)).toBeNull();
    expect(labelUnderCursor(SLICE, SAME, 3, 2, 0, 2, LABELS)).toBeNull();
    expect(labelUnderCursor(null, SAME, 3, 2, 0, 0, LABELS)).toBeNull();
  });
  it('rc076 R6 a value missing from the label table is reported with no name', () => {
    expect(labelUnderCursor(SLICE, SAME, 3, 2, 1, 1, LABELS)).toEqual({ value: 9, name: null });
  });

  it('rc076 F1 a mask stored with rows and columns swapped (non-square image): the label the overlay draws there', () => {
    // The mask is stored 3 rows x 2 columns for a 3-column x 2-row image: the overlay transposes it for display.
    const stored = Uint8Array.from([1, 0, 0, 9, 4, 1]);   // 3 x 2, row-major
    const dims = { width: 2, height: 3 };
    expect(layout.maskDisplayLayout(dims, 3, 2)).toBe('transposed');
    const drawn = layout.transposeSlice(stored, dims.height, dims.width);   // what the overlay draws, 2 rows x 3 columns
    for (let y = 0; y < 2; y++) {
      for (let x = 0; x < 3; x++) {
        const v = drawn[y * 3 + x];
        expect(labelUnderCursor(stored, dims, 3, 2, x, y, LABELS), `column ${x}, row ${y}`)
          .toEqual(v ? { value: v, name: LABELS.find((l) => l.id === v)?.name ?? null } : null);
      }
    }
    // the voxel stored at row 2, column 0 (deep white matter) is drawn at column 2, row 0
    expect(labelUnderCursor(stored, dims, 3, 2, 2, 0, LABELS)).toEqual({ value: 4, name: 'Deep White Matter' });
    // the voxel stored at row 2, column 1 (periventricular) is drawn at column 2, row 1
    expect(labelUnderCursor(stored, dims, 3, 2, 2, 1, LABELS)).toEqual({ value: 1, name: 'Periventricular' });
  });

  it('rc076 F1 a mask the overlay cannot place on the image (another grid): no label', () => {
    const other = new Uint8Array(4 * 5).fill(1);
    expect(layout.maskDisplayLayout({ width: 4, height: 5 }, 3, 2)).toBe('other');
    expect(labelUnderCursor(other, { width: 4, height: 5 }, 3, 2, 0, 0, LABELS)).toBeNull();
  });

  it('rc076 F1 the overlay and the readout use the same layout rule (one function, no copy)', () => {
    const canvas = readFileSync(join(__dirname, '..', 'components', 'SegmentationCanvasLocal.tsx'), 'utf-8');
    expect(canvas).toMatch(/from '@\/utils\/maskDisplayLayout'/);
    expect(canvas).not.toMatch(/function transposeSlice\(/);
    expect(canvas).not.toMatch(/\.width !== imageWidth && \w+\.height === imageWidth/);
    const cursor = readFileSync(join(__dirname, 'labelUnderCursor.ts'), 'utf-8');
    expect(cursor).toMatch(/from '\.\/maskDisplayLayout'/);
  });
});
