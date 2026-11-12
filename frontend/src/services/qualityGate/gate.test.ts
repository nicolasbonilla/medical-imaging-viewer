/**
 * The browser side of the single quality gate after the sixth review of PR #81 (G27): display and request only.
 * The rule, the policy and the classifier are tested on the server (backend/tests/unit/test_quality_gate_matrix.py,
 * test_rc122_one_gate.py); here: what the browser does with an answer, and that it holds nothing else.
 * DRAFT, PENDING owner approval.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect } from 'vitest';
import * as gate from './gate';

const SOURCE = readFileSync(join(__dirname, 'gate.ts'), 'utf-8');

describe('G27: the browser holds no rule', () => {
  it('rc127 gate.ts exports only display and request helpers', () => {
    const functions = Object.entries(gate).filter(([, v]) => typeof v === 'function').map(([k]) => k).sort();
    expect(functions).toEqual(['actionOf', 'gateNoAccess', 'gateNotEnabled', 'gateRateLimited', 'gateUnavailable', 'isGateResult',
      'retryAfterSeconds', 'serverSequenceClass', 'skullFromProvenance']);
    expect(SOURCE).not.toMatch(/\.json'|other_words|min_flair_inversion_time_ms|confirmation_modes|evaluateGate|classify/);
  });
});

describe('fail closed and say why (G6, F3)', () => {
  it('rc126 without an answer the AI never runs and nothing is shown', () => {
    const u = gate.gateUnavailable();
    expect([u.ai_may_run, u.ai_output_allowed, u.codes]).toEqual([false, false, ['gate_unavailable']]);
    const r = gate.gateRateLimited(17.2);
    expect([r.ai_may_run, r.ai_output_allowed, r.codes, r.checks[0].params.seconds]).toEqual([false, false, ['gate_rate_limited'], 18]);
    expect(gate.gateRateLimited('x').checks[0].params.seconds).toBe(60);
  });

  it('rc126 G29 only a rate-limited answer is retried, after its wait; unavailable and not enabled never are', () => {
    expect(gate.retryAfterSeconds(gate.gateRateLimited(5))).toBe(5);
    expect(gate.retryAfterSeconds(gate.gateUnavailable())).toBeNull();
    expect(gate.retryAfterSeconds(gate.gateNotEnabled())).toBeNull();
    expect(gate.MAX_AUTOMATIC_RETRIES).toBe(3);
    const decided = { ...gate.gateUnavailable(), codes: ['sequence_not_flair'] };
    expect(gate.retryAfterSeconds(decided)).toBeNull();
    expect(gate.retryAfterSeconds({ ...gate.gateUnavailable(), ai_may_run: true })).toBeNull();
    expect(gate.retryAfterSeconds(null)).toBeNull();
  });
});

describe('what the answer says is what is shown', () => {
  it('rc127 the action of a code comes from the answer, else the default action', () => {
    const r = { ...gate.gateUnavailable(), actions: { sequence_unknown: 'action_comparison', x: 'not a key' } };
    expect(gate.actionOf(r, 'sequence_unknown')).toBe('action_comparison');
    expect(gate.actionOf(r, 'x')).toBe('action');
    expect(gate.actionOf(gate.gateUnavailable(), 'gate_unavailable')).toBe('action');
  });

  it('rc122 the sequence class RC-049 takes is the one the server derived', () => {
    expect(gate.serverSequenceClass({ ...gate.gateUnavailable(), inputs: { mode: 'single', visits: [{ sequence: 'FLAIR' }] } })).toBe('FLAIR');
    expect(gate.serverSequenceClass(gate.gateUnavailable())).toBeNull();
  });

  it('rc125 the skull outcome the browser reports', () => {
    expect(gate.skullFromProvenance({ inputPreparation: 'skull-removed' })).toBe('stripped');
    expect(gate.skullFromProvenance({ inputPreparation: 'as-uploaded' })).toBe('stripped');
    expect(gate.skullFromProvenance({})).toBe('unknown');
    expect(gate.skullFromProvenance(null)).toBe('unknown');
  });

  it('rc126 only an answer of the right shape is a decision', () => {
    expect(gate.isGateResult(gate.gateUnavailable())).toBe(true);
    expect(gate.isGateResult({ decision: 'proceed' })).toBe(false);
    expect(gate.isGateResult(null)).toBe(false);
  });
});
