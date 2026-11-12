/**
 * G16 (second review of PR #81; RC-127, REQ-FUNC-118): when the single quality gate stops a comparison, the panel
 * shows the gate's reason only — never RC-062's "change of scanner or protocol" box, which belongs to genuine RC-062
 * abstentions. Every abstaining gate code of the policy, including gate_not_approved and gate_switched_off.
 * DRAFT, PENDING owner approval.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import '@/i18n/config';
import { LongitudinalResultPanel } from './LongitudinalResultPanel';
import { QUALITY_GATE_POLICY, type GateCheckName, type GateResult } from '@/services/qualityGate/gate';

afterEach(cleanup);

const ABSTAINED = {
  changes: [], abstained: true, total_lesions_tp1: null, total_lesions_tp2: null, burden_tp1_mm3: null,
  burden_tp2_mm3: null, burden_tp1_ml: null, burden_tp2_ml: null, burden_delta_mm3: null, burden_delta_percent: null,
  status_counts: null, change_candidates: null, registration_verified: false, adjudication_required: true,
  caveat: 'No automatic change candidates for this pair.',
};
const checkOf = (code: string): GateCheckName => (code === 'gate_input_invalid' ? 'input'
  : code.startsWith('gate_') ? 'platform' : (code.split('_')[0] as GateCheckName));
const gateFor = (code: string, allowed = false): GateResult => ({
  gate_version: 'quality-gate/1', policy_version: QUALITY_GATE_POLICY.policy_version, mode: 'comparison',
  decision: allowed ? 'proceed_with_warnings' : 'abstain', ai_may_run: allowed, ai_output_allowed: allowed, codes: [code],
  checks: [{ check: checkOf(code), visit: null, status: allowed ? 'warn' : 'abstain', code, params: {} }],
});
const show = (result: Record<string, unknown>) =>
  render(<LongitudinalResultPanel result={result as never} tp1SegId="s1" tp2SegId="s2" onReviewed={() => undefined} />);

describe('G16: the reason shown is the gate\'s reason', () => {
  const codes = Object.entries(QUALITY_GATE_POLICY.codes).filter(([, st]) => st === 'abstain').map(([c]) => c);
  it('rc127 every abstaining gate code shows the gate panel and never the RC-062 box', () => {
    expect(codes).toEqual(expect.arrayContaining(['gate_not_approved', 'gate_switched_off', 'scanner_changed']));
    const bad: string[] = [];
    for (const code of codes) {
      const { unmount } = show({ ...ABSTAINED, quality_gate: gateFor(code) });
      const check = screen.queryByTestId('longitudinal-quality-gate-check');
      if (screen.queryByTestId('longitudinal-abstained') || check?.getAttribute('data-code') !== code) bad.push(code);
      unmount();
    }
    expect(bad).toEqual([]);
  });

  it('rc127 a genuine RC-062 abstention keeps its box, with or without an allowing gate', () => {
    const rc062 = { ...ABSTAINED, acquisition_check: { status: 'differs', comparable: false, required_fields: [], fields_compared: [],
      differing: [{ field: 'manufacturer', tp1: 'SIEMENS', tp2: 'GE' }], missing: [], tolerances: {}, source: '' } };
    const { unmount } = show(rc062);
    expect(screen.getByTestId('longitudinal-abstained')).toBeInTheDocument();
    unmount();
    show({ ...rc062, quality_gate: gateFor('thickness_unknown', true) });
    expect(screen.getByTestId('longitudinal-abstained')).toBeInTheDocument();
  });
});

const UI_STATES = JSON.parse(readFileSync(join(__dirname, '..', 'config', 'qualityGate.ui_states.v1.json'), 'utf-8'));

describe('G21: one coherent verdict per gate decision x RC-062 status', () => {
  it('rc127 every state of the shared fixture shows exactly its one verdict', () => {
    const bad: string[] = [];
    for (const st of UI_STATES.states as { name: string; result: Record<string, unknown>; expect: Record<string, boolean> }[]) {
      const { unmount } = show(st.result);
      const seen = {
        gate_panel: Boolean(screen.queryByTestId('longitudinal-quality-gate')),
        rc062_box: Boolean(screen.queryByTestId('longitudinal-abstained')),
        governed: Boolean(screen.queryByTestId('longitudinal-quality-gate-governed')),
      };
      if (JSON.stringify(seen) !== JSON.stringify(st.expect) || (seen.gate_panel && seen.rc062_box)) bad.push(`${st.name}: ${JSON.stringify(seen)}`);
      unmount();
    }
    expect(bad).toEqual([]);
  });
});

describe('F1: the per-visit FLAIR attestation of a comparison', () => {
  const stopped = (checks: { visit: string; code: string }[]) => ({
    ...ABSTAINED,
    quality_gate: { ...gateFor('sequence_missing'), codes: checks.map((c) => c.code),
      checks: checks.map((c) => ({ check: 'sequence', visit: c.visit, status: 'abstain', code: c.code, params: {} })) },
  });
  it('rc122 offered per visit only for unknown or missing, unticked, sent only on purpose', () => {
    const onAttest = vi.fn();
    render(<LongitudinalResultPanel result={stopped([{ visit: 'tp1', code: 'sequence_missing' }, { visit: 'tp2', code: 'sequence_not_flair' }]) as never}
      tp1SegId="s1" tp2SegId="s2" onReviewed={() => undefined} onAttest={onAttest} />);
    const tp1 = screen.getByTestId('quality-gate-attest-tp1').querySelector('input') as HTMLInputElement;
    expect(tp1.checked).toBe(false);
    expect(screen.queryByTestId('quality-gate-attest-tp2')).not.toBeInTheDocument();      // never for another sequence
    const again = screen.getByTestId('quality-gate-attest-again');
    expect(again).toBeDisabled();
    fireEvent.click(tp1);
    fireEvent.click(again);
    expect(onAttest).toHaveBeenCalledWith({ tp1: true, tp2: false });
  });
  it('rc122 reset when the compared pair changes', () => {
    const r = stopped([{ visit: 'tp1', code: 'sequence_unknown' }, { visit: 'tp2', code: 'sequence_missing' }]) as never;
    const { rerender } = render(<LongitudinalResultPanel result={r} tp1SegId="s1" tp2SegId="s2" onReviewed={() => undefined} onAttest={vi.fn()} />);
    fireEvent.click(screen.getByTestId('quality-gate-attest-tp1').querySelector('input') as HTMLInputElement);
    rerender(<LongitudinalResultPanel result={r} tp1SegId="s1" tp2SegId="s3" onReviewed={() => undefined} onAttest={vi.fn()} />);
    expect((screen.getByTestId('quality-gate-attest-tp1').querySelector('input') as HTMLInputElement).checked).toBe(false);
  });
});
