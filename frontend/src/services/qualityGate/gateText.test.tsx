/**
 * K4 (fourteenth review of PR #81; RC-127; DRAFT, PENDING owner approval): a clinician never sees a raw "{{band}}" or an
 * empty slot. EVERY registered gate code, in every locale, through EVERY display path that shows a gate code (the gate
 * panel — used by the browser card and the comparison — and the comparison's warnings under RC-062), with real params,
 * with missing params and with unknown param values: no "{{", no "}}", no raw i18n key, and each placeholder shows its
 * value or the defined fallback. Static: no direct t(`qualityGate.codes...`) outside the ONE helper (gateText.ts).
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import i18n from '@/i18n/config';
import { QualityGatePanel } from '@/components/QualityGatePanel';
import { LongitudinalResultPanel } from '@/components/LongitudinalResultPanel';
import type { GateResult } from './gate';

afterEach(cleanup);

type Texts = { qualityGate: Record<string, any> };  // eslint-disable-line @typescript-eslint/no-explicit-any
const read = (loc: string): Texts => JSON.parse(readFileSync(join(__dirname, '..', '..', 'i18n', 'locales', `${loc}.json`), 'utf-8'));
const LOCALES = { en: read('en'), es: read('es'), de: read('de') };
const REAL = { band: 'B3', fields: ['manufacturer', 'magnetic_field_strength_t'], sequence: 'T1', seconds: 30 };
const UNKNOWN = { band: 'B9', fields: ['not_a_field'], sequence: 'not_a_sequence', seconds: Number.NaN };

/** What a placeholder must show for these params in this locale: the value, or the defined fallback. */
function expected(texts: Texts, name: string, params: Record<string, unknown>): string {
  const q = texts.qualityGate;
  const fallback = String(q.paramMissing ?? '\u0000no fallback defined');
  const v = params[name];
  if (name === 'band') return typeof v === 'string' && q.band[v] ? q.band[v] : fallback;
  if (name === 'sequence') return typeof v === 'string' && q.sequenceName[v] ? q.sequenceName[v] : fallback;
  if (name === 'fields') {
    const known = Array.isArray(v) ? v.filter((f) => typeof f === 'string' && q.field[f]).map((f) => q.field[f]) : [];
    return known.length ? known.join(', ') : fallback;
  }
  if (name === 'seconds') return typeof v === 'number' && Number.isFinite(v) && v > 0 ? String(Math.ceil(v)) : fallback;
  return fallback;
}

const gate = (code: string, params: Record<string, unknown>, mode: string, action: string, status = 'warn'): GateResult => ({
  gate_version: 'quality-gate/1', policy_version: 'p', mode, decision: 'proceed_with_warnings', ai_may_run: true,
  ai_output_allowed: true, codes: [code], actions: { [code]: action },
  checks: [{ check: 'thickness', visit: null, status, code, params }],
} as never);

const ABSTAINED_RC062 = {
  changes: [], abstained: true, total_lesions_tp1: null, total_lesions_tp2: null, burden_tp1_mm3: null,
  burden_tp2_mm3: null, burden_tp1_ml: null, burden_tp2_ml: null, burden_delta_mm3: null, burden_delta_percent: null,
  status_counts: null, change_candidates: null, registration_verified: false, adjudication_required: true,
  caveat: 'No automatic change candidates for this pair.',
  acquisition_check: { status: 'differs', comparable: false, required_fields: [], fields_compared: [],
    differing: [{ field: 'manufacturer', tp1: 'SIEMENS', tp2: 'GE' }], missing: [], tolerances: {}, source: '' },
};

/** The display paths: each renders the code and returns the text the clinician reads for it. */
const PATHS: Record<string, (code: string, params: Record<string, unknown>, part: string) => string[]> = {
  panel: (code, params, part) => {
    const mode = part === 'action_comparison' ? 'comparison' : 'single';
    render(<QualityGatePanel result={gate(code, params, mode, part)} testId="g" />);
    return screen.getAllByTestId('g-check').map((n) => n.textContent ?? '');
  },
  comparisonWarnings: (code, params) => {
    render(<LongitudinalResultPanel result={{ ...ABSTAINED_RC062, quality_gate: gate(code, params, 'comparison', 'action_comparison') } as never}
      tp1SegId="s1" tp2SegId="s2" onReviewed={() => undefined} />);
    return screen.getAllByTestId('longitudinal-quality-gate-warning').map((n) => n.textContent ?? '');
  },
};

describe('K4: no placeholder ever reaches the clinician', () => {
  it('rc127 every code, locale, display path and param shape renders a complete sentence', async () => {
    const bad: string[] = [];
    for (const [loc, texts] of Object.entries(LOCALES)) {
      await i18n.changeLanguage(loc);
      for (const [code, parts] of Object.entries(texts.qualityGate.codes as Record<string, Record<string, string>>)) {
        for (const [part, template] of Object.entries(parts)) {
          const names = [...template.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]);
          for (const [shape, params] of Object.entries({ real: REAL, missing: {}, unknown: UNKNOWN })) {
            for (const [path, show] of Object.entries(PATHS)) {
              if (path === 'comparisonWarnings' && part !== 'message') continue;   // that path shows the message only
              const out = show(code, params, part).join(' | ');
              cleanup();
              const missing = names.filter((n) => !out.includes(expected(texts, n, params)));
              if (/\{\{|\}\}/.test(out) || /qualityGate\./.test(out) || missing.length) {
                bad.push(`${loc} ${path} ${code}.${part} (${shape}): ${missing.join(',')} :: ${out.slice(0, 160)}`);
              }
            }
          }
        }
      }
    }
    await i18n.changeLanguage('en');
    expect({ failing: bad.length, first: bad.slice(0, 12) }).toEqual({ failing: 0, first: [] });
  });

  it('rc127 no display path translates a gate code except through the one helper', () => {
    const root = join(__dirname, '..', '..');
    const files: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name);
        if (statSync(p).isDirectory()) walk(p);
        else if (/\.(ts|tsx)$/.test(name) && !/\.test\./.test(name)) files.push(p);
      }
    };
    walk(root);
    const direct = files.filter((f) => !/gateText\.ts$/.test(f) && /qualityGate\.codes/.test(readFileSync(f, 'utf-8')))
      .map((f) => f.slice(root.length + 1));
    expect(direct).toEqual([]);
    expect(files.some((f) => /qualityGate[\\/]gateText\.ts$/.test(f))).toBe(true);
  });
});
