import { describe, it, expect } from 'vitest';
import { detectLabelPreset } from './labelPresets';

const lbl = (id: number, name: string) => ({ id, name });

describe('detectLabelPreset', () => {
  it('detects magnims: 6 foreground labels with Periventricular first', () => {
    const labels = [
      lbl(0, 'Background'),
      lbl(1, 'Periventricular'), lbl(2, 'Juxtacortical'), lbl(3, 'Infratentorial'),
      lbl(4, 'Deep White Matter'), lbl(5, 'Active (Gd+)'), lbl(6, 'Black Hole (T1)'),
    ];
    expect(detectLabelPreset(labels)).toBe('magnims');
  });

  it('detects default: 4 foreground labels with "MS Lesion (Active)" first', () => {
    const labels = [
      lbl(0, 'Background'),
      lbl(1, 'MS Lesion (Active)'), lbl(2, 'MS Lesion (Chronic)'),
      lbl(3, 'MS Lesion (Enhancing)'), lbl(4, 'Other'),
    ];
    expect(detectLabelPreset(labels)).toBe('default');
  });

  it('returns custom when labels do not match a known preset', () => {
    expect(detectLabelPreset([lbl(0, 'Background'), lbl(1, 'Something')])).toBe('custom');
    // right count, wrong first name:
    expect(detectLabelPreset([lbl(0, 'BG'), lbl(1, 'X'), lbl(2, 'Y'), lbl(3, 'Z'), lbl(4, 'W')])).toBe('custom');
  });

  it('handles empty / null / undefined as custom', () => {
    expect(detectLabelPreset([])).toBe('custom');
    expect(detectLabelPreset(null)).toBe('custom');
    expect(detectLabelPreset(undefined)).toBe('custom');
  });
});
