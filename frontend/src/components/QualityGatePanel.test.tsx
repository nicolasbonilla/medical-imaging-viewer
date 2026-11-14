/**
 * QualityGatePanel — the physician reads WHY, in plain words, with what to do (REQ-FUNC-118; RC-127, G2).
 * Every code of the server's policy renders a message and an action in en, es and de, with no key or placeholder left.
 * Sixth review (G27): the answers are built here exactly as the server sends them; the browser evaluates nothing.
 * DRAFT, PENDING owner approval.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import i18n from '@/i18n/config';
import { QualityGatePanel } from './QualityGatePanel';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { GateCheck, GateDecision, GateResult, GateStatus } from '@/services/qualityGate/gate';

// G27: the browser holds no policy; the test reads the server's policy file (test data) for the list of codes
const POLICY = JSON.parse(readFileSync(join(__dirname, '..', '..', '..', 'backend', 'app', 'services',
  'quality_gate_policy.json'), 'utf-8')) as { codes: Record<string, GateStatus> };
const DECISION: Record<GateStatus, GateDecision> = { abstain: 'abstain', warn: 'proceed_with_warnings', pending: 'pending', pass: 'proceed' };
/** An answer as the server sends it. */
const answer = (decision: GateDecision, checks: GateCheck[], mode: string | null = 'single', actions: Record<string, string> = {}): GateResult => ({
  gate_version: 'quality-gate/1', policy_version: 'p', mode, decision, ai_may_run: decision !== 'abstain',
  ai_output_allowed: decision === 'proceed' || decision === 'proceed_with_warnings',
  codes: checks.filter((c) => c.code).map((c) => c.code as string), checks, actions,
});

afterEach(async () => {
  cleanup();
  await i18n.changeLanguage('en');
});

describe('QualityGatePanel (REQ-FUNC-118, RC-127)', () => {
  it('rc127 every code has a plain message and an action in en, es and de, with nothing left untranslated', async () => {
    const seen: Record<string, string> = {};
    for (const lng of ['en', 'es', 'de']) {
      await i18n.changeLanguage(lng);
      for (const [code, status] of Object.entries(POLICY.codes)) {
        const result = answer(DECISION[status], [{ check: 'scanner', visit: 'tp2', status, code,
          params: { band: 'B3', fields: ['manufacturer', 'magnetic_field_strength_t'], sequence: 'T1', seconds: 9 } }]);
        const { container, unmount } = render(<QualityGatePanel result={result} />);
        const text = container.textContent ?? '';
        expect(text, `${lng}:${code}`).not.toMatch(/qualityGate\.|\{\{|undefined/);
        expect(screen.getByTestId('quality-gate-panel-check').getAttribute('data-code')).toBe(code);
        if (lng !== 'en') expect(text, `${lng}:${code} equals English`).not.toBe(seen[code]);
        else seen[code] = text;
        unmount();
      }
    }
  });

  it('rc127 a scanner change is explained with the changed fields, in Spanish', async () => {
    await i18n.changeLanguage('es');
    const result = answer('abstain', [{ check: 'scanner', visit: null, status: 'abstain', code: 'scanner_changed',
      params: { fields: ['manufacturer'] } }], 'comparison');
    render(<QualityGatePanel result={result} />);
    const panel = screen.getByTestId('quality-gate-panel');
    expect(panel.getAttribute('data-decision')).toBe('abstain');
    expect(panel.getAttribute('role')).toBe('alert');
    expect(panel.textContent).toContain('equipos distintos (cambió: fabricante)');
    expect(panel.textContent).toContain('La IA no se ejecuta en este paso');
  });

  it('rc127 G14 each mode points to the confirmation it offers (single: the card; comparison: the per-visit box)', () => {
    const unknown = (visit: 'tp2' | 'study'): GateCheck => ({ check: 'sequence', visit, status: 'abstain', code: 'sequence_unknown', params: {} });
    const { unmount } = render(<QualityGatePanel result={answer('abstain', [unknown('tp2')], 'comparison',
      { sequence_unknown: 'action_comparison' })} />);
    expect(screen.getByTestId('quality-gate-panel').textContent).toMatch(/confirmation box below and compare again/);
    unmount();
    render(<QualityGatePanel result={answer('abstain', [unknown('study')], 'single', { sequence_unknown: 'action' })} />);
    expect(screen.getByTestId('quality-gate-panel').textContent).toMatch(/confirmation box/);
  });

  it('rc127 a thick acquisition warns with its band; a passing gate lists no reason', () => {
    const thick = answer('proceed_with_warnings', [{ check: 'thickness', visit: 'study', status: 'warn', code: 'thickness_thick',
      params: { band: 'B3', mm: 5 } }]);
    const { unmount } = render(<QualityGatePanel result={thick} />);
    expect(screen.getByTestId('quality-gate-panel').textContent).toContain('4.5–6.5 mm');
    unmount();
    render(<QualityGatePanel result={answer('proceed', [{ check: 'platform', visit: null, status: 'pass', code: null, params: {} }])} />);
    expect(screen.queryByTestId('quality-gate-panel-check')).not.toBeInTheDocument();
    expect(screen.getByTestId('quality-gate-panel-decision').textContent).toBe('All checks passed');
  });
});

describe('G27 (sixth review): what to do comes from the server answer, not from a policy in the browser', () => {
  it('rc127 the action named by the answer is shown', async () => {
    await i18n.changeLanguage('en');
    const result = {
      gate_version: 'quality-gate/1', policy_version: 'x', mode: null, decision: 'abstain', ai_may_run: false,
      ai_output_allowed: false, codes: ['sequence_unknown'], actions: { sequence_unknown: 'action_comparison' },
      checks: [{ check: 'sequence', visit: 'tp1', status: 'abstain', code: 'sequence_unknown', params: {} }],
    } as unknown as GateResult;
    render(<QualityGatePanel result={result} />);
    expect(screen.getByTestId('quality-gate-panel-check').textContent)
      .toContain(i18n.t('qualityGate.codes.sequence_unknown.action_comparison'));
  });
});
