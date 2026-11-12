/**
 * QualityGatePanel — the physician reads WHY, in plain words, with what to do (REQ-FUNC-118; RC-127, G2).
 * Every code of the policy renders a message and an action in en, es and de, with no key or placeholder left.
 * DRAFT, PENDING owner approval.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import i18n from '@/i18n/config';
import { QualityGatePanel } from './QualityGatePanel';
import { evaluateGate, QUALITY_GATE_POLICY, type GateDecision, type GateResult, type GateStatus } from '@/services/qualityGate/gate';

const BASE = {
  sequence: 'FLAIR', physician_confirmed_flair: false, thickness: { state: 'native', effective_mm: 1 },
  scanner: { manufacturer: 'SIEMENS', manufacturer_model_name: 'Prisma', magnetic_field_strength_t: 3 }, skull: 'stripped',
};
const ON = { allowed: true, code: null };
const DECISION: Record<GateStatus, GateDecision> = { abstain: 'abstain', warn: 'proceed_with_warnings', pending: 'pending', pass: 'proceed' };

afterEach(async () => {
  cleanup();
  await i18n.changeLanguage('en');
});

describe('QualityGatePanel (REQ-FUNC-118, RC-127)', () => {
  it('rc127 every code has a plain message and an action in en, es and de, with nothing left untranslated', async () => {
    const seen: Record<string, string> = {};
    for (const lng of ['en', 'es', 'de']) {
      await i18n.changeLanguage(lng);
      for (const [code, status] of Object.entries(QUALITY_GATE_POLICY.codes)) {
        const result: GateResult = {
          ...evaluateGate({ mode: 'single', visits: [BASE], platform: ON }),
          decision: DECISION[status],
          codes: [code],
          checks: [{ check: 'scanner', visit: 'tp2', status, code,
            params: { band: 'B3', fields: ['manufacturer', 'magnetic_field_strength_t'], sequence: 'T1' } }],
        };
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
    const result = evaluateGate({ mode: 'comparison', platform: ON,
      visits: [BASE, { ...BASE, scanner: { ...BASE.scanner, manufacturer: 'GE MEDICAL SYSTEMS' } }] });
    render(<QualityGatePanel result={result} />);
    const panel = screen.getByTestId('quality-gate-panel');
    expect(panel.getAttribute('data-decision')).toBe('abstain');
    expect(panel.getAttribute('role')).toBe('alert');
    expect(panel.textContent).toContain('equipos distintos (cambió: fabricante)');
    expect(panel.textContent).toContain('La IA no se ejecuta en este paso');
  });

  it('rc127 G14 a comparison never asks for a confirmation it cannot take', () => {
    const unknown = { ...BASE, sequence: 'unknown' };
    const { unmount } = render(<QualityGatePanel result={evaluateGate({ mode: 'comparison', platform: ON, visits: [BASE, unknown] })} />);
    expect(screen.getByTestId('quality-gate-panel').textContent).not.toMatch(/confirmation box/);
    unmount();
    render(<QualityGatePanel result={evaluateGate({ mode: 'single', platform: ON, visits: [unknown] })} />);
    expect(screen.getByTestId('quality-gate-panel').textContent).toMatch(/confirmation box/);
  });

  it('rc127 a thick acquisition warns with its band; a passing gate lists no reason', () => {
    const thick = evaluateGate({ mode: 'single', platform: ON, visits: [{ ...BASE, thickness: { state: 'native', effective_mm: 5 } }] });
    const { unmount } = render(<QualityGatePanel result={thick} />);
    expect(screen.getByTestId('quality-gate-panel').textContent).toContain('4.5–6.5 mm');
    unmount();
    render(<QualityGatePanel result={evaluateGate({ mode: 'single', platform: ON, visits: [BASE] })} />);
    expect(screen.queryByTestId('quality-gate-panel-check')).not.toBeInTheDocument();
    expect(screen.getByTestId('quality-gate-panel-decision').textContent).toBe('All checks passed');
  });
});
