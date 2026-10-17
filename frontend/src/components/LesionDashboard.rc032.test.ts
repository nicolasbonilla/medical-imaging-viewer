/**
 * RC-032 — risk control for HAZ-005; implements REQ-SAFE-021.
 * The MNI-space MSMask atlas is refused for images that are not in MNI space. In `auto` mode the
 * backend then falls back to the geometric heuristics and returns `atlas_unavailable_reason`; the
 * table must say so, or a clinician sees "Geometric" regions with no hint that the atlas was
 * skipped for a reason that also makes every region less reliable.
 *
 * Negative controls: executed one mutation at a time against the final code; results and failing
 * test names in docs/iec62304/records/risk_verification/RC-032_negative_controls_2026-09-28.json.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect } from 'vitest';

const code = readFileSync(join(__dirname, 'LesionDashboard.tsx'), 'utf-8')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/(^|[^:])\/\/.*$/gm, '$1');
const locale = (lng: string) =>
  JSON.parse(readFileSync(join(__dirname, '..', 'i18n', 'locales', `${lng}.json`), 'utf-8'));

describe('RC-032 — the user is told when the atlas was not used', () => {
  it('rc032 renders an alert whenever the response carries atlas_unavailable_reason', () => {
    const block = code.match(/classification\.atlas_unavailable_reason\s*&&\s*\([\s\S]*?\n\s*\)\}/);
    expect(block).not.toBeNull();
    expect(block![0]).toMatch(/role="alert"/);
    expect(block![0]).toMatch(/data-testid="atlas-unavailable"/);
    expect(block![0]).toMatch(/classify\.atlasUnavailable/);
  });

  it('rc032 the warning is translated in every shipped locale and names MNI space', () => {
    for (const lng of ['en', 'es', 'de']) {
      const text: string = locale(lng).classify?.atlasUnavailable;
      expect(text, lng).toBeTruthy();
      expect(text, lng).toMatch(/MNI/);
    }
  });

  it('rc032 geometric regions always carry a least-accurate warning', () => {
    const block = code.match(/classification\.method === 'geometric'[^\n]*&&\s*\([\s\S]*?\n\s*\)\}/);
    expect(block).not.toBeNull();
    expect(block![0]).toMatch(/role="alert"/);
    expect(block![0]).toMatch(/classify\.geometricWarning/);
    for (const lng of ['en', 'es', 'de']) {
      expect(locale(lng).classify?.geometricWarning, lng).toBeTruthy();
    }
  });

  it('rc032 an atlas FAULT is shown separately from a refusal', () => {
    const block = code.match(/classification\.atlas_error\s*&&\s*\([\s\S]*?\n\s*\)\}/);
    expect(block).not.toBeNull();
    expect(block![0]).toMatch(/role="alert"/);
    expect(block![0]).toMatch(/classify\.atlasError/);
    for (const lng of ['en', 'es', 'de']) {
      expect(locale(lng).classify?.atlasError, lng).toBeTruthy();
    }
  });

  it('rc032 no warning claims an unmeasured comparative accuracy', () => {
    for (const lng of ['en', 'es', 'de']) {
      const c = locale(lng).classify;
      for (const key of ['atlasUnavailable', 'geometricWarning', 'atlasError']) {
        expect(c[key], `${lng}.${key}`).not.toMatch(/least accurate|menos preciso|ungenaueste/i);
      }
    }
  });

  it('rc032 the panel no longer promises SynthSeg or a "best" automatic method', () => {
    for (const lng of ['en', 'es', 'de']) {
      const c = locale(lng).classify;
      expect(c.description, lng).not.toMatch(/SynthSeg/);
      expect(c.methodAuto, lng).not.toMatch(/best|mejor|beste/i);
    }
  });
});
