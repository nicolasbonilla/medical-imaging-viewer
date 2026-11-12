/**
 * G26 (fifth review of PR #81), surface (a): with VITE_ENABLE_QUALITY_GATE off, the RC-049 header evidence of the
 * in-browser AI answers byte-identically to the base of PR #81 (5ee06b7) — verdict AND reasons — on the GENERATED
 * corpus of frontend/src/config/qualityGate.flags_off_snapshot.v1.json (scripts/safety/quality_gate_flags_off_snapshot.py).
 * With the gate ON, RC-049 takes the class the server returned (sixth review, G27: one implementation); the G19
 * extension (no base FLAIR acceptance lost) is checked on the server, backend/tests/unit/test_rc122_flags_off_identity.py.
 * DRAFT, PENDING owner approval.
 */
import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';

import { FEATURES } from '@/config/features';
import SNAP from '@/config/qualityGate.flags_off_snapshot.v1.json';
import { headerContrastEvidence } from '../headerEvidence';

interface Entry { text: string; inversion_time_ms: number | null; sequence_name: string | null }
const CORPUS = SNAP.corpus as Entry[];
const BASE = SNAP.rc049 as [string, string][];

const digest = (reasons: string[]) => createHash('sha256').update(JSON.stringify(reasons), 'utf8').digest('hex').slice(0, 16);
const dicomOf = (c: Entry) => ({
  ...(c.inversion_time_ms ? { inversionTimeMs: c.inversion_time_ms } : {}),
  ...(c.sequence_name ? { sequenceName: c.sequence_name } : {}),
});

describe('G26 (a): flag off = the base RC-049 header evidence', () => {
  it('rc122 the flag is off in the tests, as in production today', () => {
    expect(FEATURES.QUALITY_GATE).toBe(false);
  });

  it('rc122 every generated entry: same verdict and same reasons as the base', () => {
    expect(CORPUS.length).toBeGreaterThanOrEqual(2000);
    const bad = CORPUS.map((c, i) => [c, headerContrastEvidence([c.text], dicomOf(c), null), BASE[i]] as const)
      .filter(([, e, base]) => e.verdict !== base[0] || digest(e.reasons) !== base[1])
      .map(([c, e, base]) => [c.text, e.verdict, base[0]]);
    expect(bad.length, JSON.stringify(bad.slice(0, 6))).toBe(0);
  });

  it('rc122 the reviewer cases support, as on the base', () => {
    for (const text of ['AX FLAIR CAL', 'FLAIR loc', 'sag_flair_dir-AP']) {
      expect(headerContrastEvidence([text], {}, null).verdict, text).toBe('supports');
    }
  });

  it('rc122 with the flag off, the evidence carries no gate class (the base shape)', () => {
    expect(headerContrastEvidence(['AX T2 FLAIR'], {}, null)).not.toHaveProperty('sequenceClass');
  });
});

describe('G27 (sixth review): with the gate on, RC-049 takes the class the SERVER returned', () => {
  it('rc122 the verdict follows the server class, never a local reading of the header text', () => {
    const on = (text: string, cls: string) => headerContrastEvidence([text], {}, null, { qualityGate: true, serverSequenceClass: cls });
    expect(on('Sag T1 MPRAGE', 'FLAIR').verdict).toBe('supports');
    expect(on('AX T2 FLAIR', 'T1').verdict).toBe('contradicts');
    expect(on('AX T2 FLAIR', 'other').verdict).toBe('contradicts');
    expect(on('AX T2 FLAIR', 'unknown').verdict).toBe('none');
    expect(on('AX T2 FLAIR', 'FLAIR').sequenceClass).toBe('FLAIR');
    expect(on('AX T2 FLAIR', 'T1').reasons.some((r) => r.includes('names another sequence'))).toBe(false);
  });
});
