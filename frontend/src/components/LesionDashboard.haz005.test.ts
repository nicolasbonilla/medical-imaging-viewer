/**
 * RC-010 (amended) — risk control for HAZ-005; implements REQ-SAFE-010 (amended 2026-09-28).
 * MAGNIMS region classification shows EVIDENCE, never a "confidence".
 *
 * Audit #8: the parcellation path returned a distance linearly mapped onto 0.70-0.95 and the
 * MSMask path a fixed 0.50 outside the atlas; the table rendered them as green/yellow/red
 * percentages plus an "Avg confidence", which a clinician reads as certainty. The backend now
 * returns confidence = null on every path; these tests pin that the UI cannot resurrect it, and that
 * a default-DWM assignment (no white-matter zone) is surfaced as a warning, not hidden.
 *
 * Negative control (EXECUTED 2026-09-28; counts recorded in rc_test_manifest.json, RC-010):
 *   - restore a `{(cl.confidence * 100).toFixed(0)}%` cell        -> 1 failed, 6 passed (source guard)
 *   - make regionEvidence return the confidence when present      -> 1 failed, 6 passed (behaviour)
 *   Restored: 7 passed.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect } from 'vitest';
import { regionEvidence } from '../utils/regionEvidence';

const code = readFileSync(join(__dirname, 'LesionDashboard.tsx'), 'utf-8')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/(^|[^:])\/\/.*$/gm, '$1');

describe('RC-010 — region evidence, never confidence', () => {
  it('rc010 shows the MSMask in-zone fraction as evidence', () => {
    expect(regionEvidence({ region_overlap_fraction: 0.2, atlas_coverage: true })).toEqual({ kind: 'overlap', value: 0.2 });
  });

  it('rc010 flags a default-DWM lesion (no white-matter zone) instead of inventing a value', () => {
    expect(regionEvidence({ region_overlap_fraction: null, atlas_coverage: false })).toEqual({ kind: 'outsideZones' });
  });

  it('rc010 shows nothing for paths without zone evidence (parcellation distances are separate columns)', () => {
    expect(regionEvidence({})).toEqual({ kind: 'none' });
  });

  it('rc010 ignores a confidence even if a stale backend or persisted result sends one', () => {
    expect(regionEvidence({ confidence: 0.92 })).toEqual({ kind: 'none' });
    expect(regionEvidence({ confidence: 0.92, region_overlap_fraction: 0.4 })).toEqual({ kind: 'overlap', value: 0.4 });
  });

  it('rc010 the table never reads a lesion confidence', () => {
    expect(code).not.toMatch(/(\?\.|\.)\s*confidence\b/);
    expect(code).not.toMatch(/\[\s*['"`]confidence['"`]\s*\]/);
    expect(code).not.toMatch(/[{,]\s*confidence\s*[,}:=]/);
    expect(code).not.toMatch(/confidenceBadge/);
  });

  it('rc010 the summary states that no confidence is reported and computes no average', () => {
    expect(code).not.toMatch(/avgConfidence/);
    expect(code).toMatch(/classify\.noConfidence/);
  });

  it('rc010 the default-DWM warning is rendered with its own translated label', () => {
    expect(code).toMatch(/classify\.outsideZones/);
    expect(code).toMatch(/classify\.outsideZonesTooltip/);
  });
});
