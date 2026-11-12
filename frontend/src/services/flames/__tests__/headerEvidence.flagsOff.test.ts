/**
 * G26 (fifth review of PR #81), surface (a): with VITE_ENABLE_QUALITY_GATE off, the RC-049 header evidence of the
 * in-browser AI answers byte-identically to the base of PR #81 (5ee06b7) — verdict AND reasons — on the GENERATED
 * corpus of frontend/src/config/qualityGate.flags_off_snapshot.v1.json (scripts/safety/quality_gate_flags_off_snapshot.py).
 * Also the G19 extension: with the gate ON, no base FLAIR acceptance of that corpus is lost except the documented
 * decisions (D-QG-7, D-QG-12, S2). Backend twin: backend/tests/unit/test_rc122_flags_off_identity.py.
 * DRAFT, PENDING owner approval.
 */
import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';

import { FEATURES } from '@/config/features';
import SNAP from '@/config/qualityGate.flags_off_snapshot.v1.json';
import { classifyFields, QUALITY_GATE_POLICY, sequenceTokens } from '@/services/qualityGate/gate';
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
  it('the flag is off in the tests, as in production today', () => {
    expect(FEATURES.QUALITY_GATE).toBe(false);
  });

  it('every generated entry: same verdict and same reasons as the base', () => {
    expect(CORPUS.length).toBeGreaterThanOrEqual(2000);
    const bad = CORPUS.map((c, i) => [c, headerContrastEvidence([c.text], dicomOf(c), null), BASE[i]] as const)
      .filter(([, e, base]) => e.verdict !== base[0] || digest(e.reasons) !== base[1])
      .map(([c, e, base]) => [c.text, e.verdict, base[0]]);
    expect(bad.length, JSON.stringify(bad.slice(0, 6))).toBe(0);
  });

  it('the reviewer cases support, as on the base', () => {
    for (const text of ['AX FLAIR CAL', 'FLAIR loc', 'sag_flair_dir-AP']) {
      expect(headerContrastEvidence([text], {}, null).verdict, text).toBe('supports');
    }
  });

  it('with the flag off, the evidence carries no gate class (the base shape)', () => {
    expect(headerContrastEvidence(['AX T2 FLAIR'], {}, null)).not.toHaveProperty('sequenceClass');
  });
});

// The documented decisions under which a base FLAIR acceptance may be lost with the gate ON (Quality_Gate_Design.md).
const D_QG_7 = ['post', 'postcontrast', 'gd', 'gad', 'gado', 'contrast', 'ce', 'mpr', 'mip', 'minip', 'mpvr', 'reformat',
  'derived', 'subtraction'];
const WEAK = ['cal', 'loc', 'dir', 'mag'];
const S2_CODES = ['tfl', 'tfe'];

function documentedLoss(c: Entry): string {
  const v = QUALITY_GATE_POLICY.sequence.vocabulary;
  const tokens = sequenceTokens(c.text);
  const strip = (t: string) => t.replace(/[0-9]+$/, '');
  if (tokens.some((t) => D_QG_7.includes(t) || D_QG_7.includes(strip(t)))) return 'D-QG-7';
  if (tokens.some((t) => /^t1[a-z]*$/.test(t) || v.t1_words.includes(t) || (t.includes('flair') && t.replace('flair', '').includes('t1')))) return 'S2';
  const code = (c.sequence_name ?? '').toLowerCase().replace(/^\*/, '').match(/^[a-z]*/)?.[0] ?? '';
  if (S2_CODES.includes(code)) return 'S2';
  const strong = v.other_words.filter((w) => !WEAK.includes(w) && !D_QG_7.includes(w));
  if (tokens.some((t) => strong.includes(t) || strong.includes(strip(t)))) return 'D-QG-12';
  if (code && code in v.sequence_name_codes) return 'D-QG-12';
  const flairName = tokens.some((t) => t.includes(v.flair_substring) || v.flair_words.includes(t) || v.flair_compounds.includes(t))
    || tokens.some((t, i) => v.flair_pairs.some(([a, b]) => t === a && tokens[i + 1] === b));
  // a weak word that is the only name of the image: never a FLAIR on its inversion time alone
  if (!flairName && tokens.some((t) => WEAK.includes(t) || WEAK.includes(strip(t)))) return 'D-QG-12';
  return '';
}

describe('G19 extension: gate ON keeps every base FLAIR acceptance except the documented decisions', () => {
  it('no undocumented loss on the generated corpus', () => {
    const lost = CORPUS.filter((c, i) => BASE[i][0] === 'supports')
      .filter((c) => ['other', 'T1', 'T2'].includes(headerContrastEvidence([c.text], dicomOf(c), null, { qualityGate: true }).sequenceClass ?? ''))
      .filter((c) => !documentedLoss(c))
      .map((c) => c.text);
    expect(lost.length, JSON.stringify(lost.slice(0, 8))).toBe(0);
  });

  it('a weak word alone never turns a FLAIR into other; without a FLAIR name it still does', () => {
    for (const text of ['AX FLAIR CAL', 'FLAIR loc', 'sag_flair_dir-AP', 'FLAIR mag', 'AX_FLAIR_LOC', 'T2-FLAIR dir-PA']) {
      expect(classifyFields({ description: text }).class, text).toBe('FLAIR');
      expect(headerContrastEvidence([text], {}, null, { qualityGate: true }).verdict, text).toBe('supports');
    }
    for (const text of ['cal', 'loc', 'dir', 'mag', 'AX LOC', '3D DIR SAG', 'SWI mag']) {
      expect(classifyFields({ description: text }).class, text).toBe('other');
    }
  });

  it('F5: a text is reported by its words alone; a short inversion time has its own reason', () => {
    for (const ti of [900, 150]) {
      const e = headerContrastEvidence(['AX T2 FLAIR'], { inversionTimeMs: ti }, null, { qualityGate: true });
      expect(e.verdict).toBe('contradicts');
      expect(e.reasons).toContain('header says "AX T2 FLAIR"');
      expect(e.reasons.some((r) => r.includes('names another sequence'))).toBe(false);
      expect(e.reasons.some((r) => r.startsWith(`inversion time ${ti} ms is too short`))).toBe(true);
    }
    const inText = headerContrastEvidence(['FLAIR TI=900'], {}, null, { qualityGate: true });
    expect(inText.reasons.some((r) => r.includes('names another sequence'))).toBe(false);
    expect(inText.verdict).toBe('contradicts');
  });

  it('every word of the other list has a documented decision', () => {
    const v = QUALITY_GATE_POLICY.sequence.vocabulary as { other_words: string[]; weak_other_words?: string[] };
    expect([...(v.weak_other_words ?? [])].sort()).toEqual([...WEAK].sort());
  });
});
