/**
 * Release 2026-10-30 — merge of #69 and #71: ONE colour for a mask value its label table does not list.
 *
 * #69 (B1) defined `UNLABELLED_FALLBACK_COLOR` for the 2D canvas in utils/drawnLabels.ts; #71 defined the same cyan
 * for the GPU and 3D views in utils/regionColors.ts. Two definitions can drift apart (the 2D view and the GPU view
 * would then show an unlabelled value in different colours). One definition, in regionColors.ts, re-exported by
 * drawnLabels.ts.
 *
 * Written before the unification (fails on b0aae45).
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { UNLABELLED_FALLBACK_COLOR as FROM_DRAWN } from './drawnLabels';
import { UNLABELLED_FALLBACK_COLOR as FROM_REGIONS } from './regionColors';

const definitions = (file: string) =>
  (fs.readFileSync(path.join(__dirname, file), 'utf-8').match(/export const UNLABELLED_FALLBACK_COLOR\b/g) ?? []).length;

describe('merge of #69 and #71: one fallback colour', () => {
  it('rc070 release 1030 the 2D canvas and the GPU / 3D views use the same constant', () => {
    expect(FROM_DRAWN).toBe(FROM_REGIONS);
    expect(FROM_REGIONS.toUpperCase()).toBe('#00FFFF');
  });

  it('rc070 release 1030 it is defined once, in regionColors.ts', () => {
    expect(definitions('regionColors.ts')).toBe(1);
    expect(definitions('drawnLabels.ts')).toBe(0);
  });
});
