import type { LabelInfo } from '@/types';

export type DetectedLabelPreset = 'default' | 'magnims' | 'custom';

/**
 * Reverse-detect which label preset a segmentation's foreground labels match,
 * for driving the preset `<select>`. Returns `'custom'` when the labels don't
 * match a known preset. Foreground = labels with `id !== 0`.
 *
 * Extracted from an inline IIFE in ViewerApp's JSX (Fase 2.2) so the heuristic
 * is a pure, unit-tested function rather than untested logic in render.
 */
export function detectLabelPreset(
  labels: ReadonlyArray<Pick<LabelInfo, 'id' | 'name'>> | null | undefined,
): DetectedLabelPreset {
  const names = (labels ?? []).filter((l) => l.id !== 0).map((l) => l.name);
  if (names.length === 6 && names[0] === 'Periventricular') return 'magnims';
  if (names.length === 4 && names[0] === 'MS Lesion (Active)') return 'default';
  return 'custom';
}
