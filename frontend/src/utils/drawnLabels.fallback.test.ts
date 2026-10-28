/**
 * Release 2026-10-25 — re-review of PR #71 (2026-10-29): the B1 fallback colour of the 2D canvas was MAGENTA
 * (#FF00FF), which is the MAGNIMS "Active (Gd+)" label colour, so a mask value without a label looked exactly like an
 * active (gadolinium-enhancing) lesion. It must be a colour no preset label and no region colour uses — cyan
 * (#00FFFF), the colour PR #71 uses for the same purpose in the GPU and 3D views (`UNLISTED_LABEL_HEX`) — and the
 * warnings must name it.
 *
 * Written before the correction (fails on d3104c3).
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { UNLABELLED_FALLBACK_COLOR } from './drawnLabels';
import { DEFAULT_LABEL_PRESETS } from '@/types/segmentation';

const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const distance = (a: string, b: string) => {
  const [x, y] = [rgb(a), rgb(b)];
  return Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]);
};

/** Every foreground colour a preset label can have, and the MAGNIMS zone colours of the 2D canvas. */
const PRESET_COLOURS: Array<[string, string]> = [
  ...Object.entries(DEFAULT_LABEL_PRESETS).flatMap(([preset, labels]) =>
    labels.filter((l) => l.id !== 0).map((l): [string, string] => [`${preset} ${l.id} ${l.name}`, l.color])),
  ['zone PV', '#FF0000'], ['zone JC', '#00CC00'], ['zone IT', '#0066FF'], ['zone DWM', '#FFD700'],
];

const LOCALES = path.join(__dirname, '..', 'i18n', 'locales');
const locale = (l: string) => JSON.parse(fs.readFileSync(path.join(LOCALES, `${l}.json`), 'utf-8'));
const COLOUR_WORD: Record<string, RegExp> = { en: /\bcyan\b/, es: /\bcian\b/, de: /\bCyan\b/ };

describe('PR #71 re-review: the fallback colour is not a lesion colour', () => {
  it('rc070 release b1 fallback is the cyan of PR #71', () => {
    expect(UNLABELLED_FALLBACK_COLOR.toUpperCase()).toBe('#00FFFF');
  });

  it.each(PRESET_COLOURS)('rc070 release b1 fallback is clearly apart from %s (%s)', (_name, colour) => {
    expect(distance(UNLABELLED_FALLBACK_COLOR, colour)).toBeGreaterThan(100);
  });

  it.each(['en', 'es', 'de'])('rc070 release b1 the %s warnings name the fallback colour, never magenta', (lng) => {
    const l = locale(lng);
    for (const text of [l.segmentation.unlabelledValues, l.disReview.undrawnNoLabel] as string[]) {
      expect(text).toMatch(COLOUR_WORD[lng]);
      expect(text.toLowerCase()).not.toContain('magenta');
    }
  });
});
