/**
 * Single quality gate — the browser decides exactly as the backend (G4; RC-127, REQ-SAFE-054), on the SHARED
 * fixture that backend/tests/unit/test_quality_gate_matrix.py also reads: the 3 200-case matrix (enumerated
 * here the same way as there, compared by SHA-256) and every explicit sample. Plus the browser-only parts:
 * fail closed when the backend does not answer (G6), the v3 thickness hook (G7), the skull outcome (RC-125).
 * DRAFT, PENDING owner approval.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { describe, it, expect } from 'vitest';
import {
  canonicalGate,
  evaluateGate,
  finalBrowserGate,
  gateUnavailable,
  QUALITY_GATE_POLICY,
  skullFromProvenance,
  type GatePolicy,
  type ServerGateResponse,
} from './gate';

const ROOT = join(__dirname, '..', '..', '..', '..');
const read = (p: string) => JSON.parse(readFileSync(join(ROOT, p), 'utf-8'));
const FIXTURE = read('frontend/src/config/qualityGate.cases.v1.json');
type Patch = Record<string, unknown>;
type Dimension = [string, Record<string, Patch>];

/** The same enumeration as build_cases() in test_quality_gate_matrix.py. */
function buildCases(matrix: { base_visit: Patch; dimensions: Dimension[] }) {
  const names = matrix.dimensions.map((d) => d[0]);
  const tables = matrix.dimensions.map((d) => Object.entries(d[1]));
  const out: { key: string; input: Patch }[] = [];
  const walk = (i: number, combo: [string, Patch][]) => {
    if (i === tables.length) {
      const parts: Record<string, Patch> = {};
      names.forEach((n, j) => { parts[n] = combo[j][1]; });
      const patch = { ...parts.sequence, ...parts.confirmed, ...parts.thickness, ...parts.skull };
      const variant = parts.variant as { mode: string; affected: string[] };
      const base = JSON.parse(JSON.stringify(matrix.base_visit));
      const visits = variant.mode === 'single'
        ? [{ ...base, ...patch, ...parts.scanner }]
        : [{ ...base, ...(variant.affected.includes('tp1') ? patch : {}) },
          { ...base, ...(variant.affected.includes('tp2') ? patch : {}), ...parts.scanner }];
      out.push({ key: combo.map(([v]) => v).join('|'),
        input: { mode: variant.mode, visits: JSON.parse(JSON.stringify(visits)), platform: { allowed: true, code: null } } });
      return;
    }
    for (const entry of tables[i]) walk(i + 1, [...combo, entry]);
  };
  walk(0, []);
  return out;
}

describe('G4: one decision, backend and browser', () => {
  it('rc127 the browser policy is the backend policy', () => {
    expect(QUALITY_GATE_POLICY).toEqual(read('backend/app/services/quality_gate_policy.json'));
    expect(FIXTURE.policy_version).toBe(QUALITY_GATE_POLICY.policy_version);
  });

  it('rc127 every explicit sample of the shared fixture gets the same decision', () => {
    const bad = FIXTURE.samples.filter((s: { input: unknown; expected: string }) =>
      canonicalGate(evaluateGate(s.input)) !== s.expected).map((s: { key: string }) => s.key);
    expect(FIXTURE.samples.length).toBeGreaterThan(60);
    expect(bad).toEqual([]);
  });

  it('rc127 the whole 3 200-case matrix gives the backend digest', () => {
    const cases = buildCases(FIXTURE.matrix);
    expect(cases.length).toBe(FIXTURE.matrix_cases);
    expect(cases.length).toBe(3200);
    const lines = cases.map((c) => `${c.key}=${canonicalGate(evaluateGate(c.input))}`).join('\n');
    expect(createHash('sha256').update(lines, 'utf8').digest('hex')).toBe(FIXTURE.matrix_sha256);
  });
});

describe('G1 / G3 in the browser', () => {
  const base = FIXTURE.matrix.base_visit;
  const on = { allowed: true, code: null };
  it('rc122 never runs on another sequence, an unknown one without confirmation, or odd values', () => {
    for (const sequence of ['T1', 'T2', 'other', 'unknown', 'missing', 'flair', 7, null]) {
      const out = evaluateGate({ mode: 'single', visits: [{ ...base, sequence }], platform: on });
      expect(out.ai_may_run).toBe(false);
    }
    const confirmed = evaluateGate({ mode: 'single', visits: [{ ...base, sequence: 'missing', physician_confirmed_flair: true }], platform: on });
    expect(confirmed.codes).toContain('sequence_confirmed_by_physician');
    const notReally = evaluateGate({ mode: 'single', visits: [{ ...base, sequence: 'missing', physician_confirmed_flair: 'true' }], platform: on });
    expect(notReally.ai_may_run).toBe(false);
  });
});

describe('G6: fail closed in the browser', () => {
  it('rc126 no answer from the backend means no AI step, with a reason', () => {
    const out = gateUnavailable();
    expect(out.ai_may_run).toBe(false);
    expect(out.codes).toEqual(['gate_unavailable']);
    for (const server of [null, undefined, {} as ServerGateResponse, { decision: 'proceed' } as ServerGateResponse]) {
      expect(finalBrowserGate(server, { inputPreparation: 'skull-removed' }).ai_output_allowed).toBe(false);
    }
  });
});

describe('RC-125: the skull outcome decides whether the output is shown', () => {
  const server = (allowed: boolean): ServerGateResponse => ({
    ...evaluateGate({ mode: 'single', visits: [{ ...FIXTURE.matrix.base_visit, skull: 'pending' }], platform: { allowed: true, code: null } }),
    inputs: { mode: 'single', visits: [{ ...FIXTURE.matrix.base_visit, skull: 'pending' }] },
    platform: { allowed, code: allowed ? null : 'agent_switched_off' },
  });
  it('rc125 skull-removed or skull-free passes; anything else is unknown', () => {
    expect(skullFromProvenance({ inputPreparation: 'skull-removed' })).toBe('stripped');
    expect(skullFromProvenance({ inputPreparation: 'as-uploaded' })).toBe('stripped');
    for (const p of [undefined, null, {}, { inputPreparation: 'raw' }]) expect(skullFromProvenance(p as never)).toBe('unknown');
    expect(finalBrowserGate(server(true), { inputPreparation: 'skull-removed' }).decision).toBe('proceed');
    expect(finalBrowserGate(server(true), {}).codes).toEqual(['skull_unknown']);
    expect(server(true).ai_output_allowed).toBe(false);          // before the run: pending, no output
  });
  it('rc126 a switch turned off during the run hides the output', () => {
    const out = finalBrowserGate(server(false), { inputPreparation: 'skull-removed' });
    expect(out.ai_output_allowed).toBe(false);
    expect(out.codes).toEqual(['gate_switched_off']);
  });
});

describe('G7: the data rule for the thickness', () => {
  const thick = { mode: 'single', platform: { allowed: true, code: null },
    visits: [{ ...FIXTURE.matrix.base_visit, thickness: { state: 'native', effective_mm: 7 } }] };
  const withAsset = (licence: unknown): GatePolicy => {
    const p = JSON.parse(JSON.stringify(QUALITY_GATE_POLICY));
    p.thickness.evidence_asset = { asset_id: 't', version: '3.0.0', sha256: '0'.repeat(64), licence, abstain_band_ids: ['B4'] };
    return p;
  };
  it('rc124 warns without evidence; only a commercial licence may make a band abstain', () => {
    expect(QUALITY_GATE_POLICY.thickness.evidence_asset).toBeNull();
    expect(evaluateGate(thick).codes).toEqual(['thickness_thick']);
    expect(evaluateGate(thick).ai_may_run).toBe(true);
    expect(evaluateGate(thick, withAsset('CC-BY-4.0')).codes).toEqual(['thickness_out_of_range']);
    expect(evaluateGate(thick, withAsset('CC0-1.0')).ai_may_run).toBe(false);
    for (const licence of ['CC-BY-NC-4.0', 'CC-BY-NC-SA-4.0', null, '', ['CC0-1.0']]) {
      expect(evaluateGate(thick, withAsset(licence)).codes).toEqual(['thickness_thick']);
    }
  });
});
