/**
 * F3 (fifth review of PR #81; RC-126, RC-127): over the per-user limit of real evaluations the backend answers 429 with
 * the seconds to wait; the browser shows that specific reason ("too many checks, wait N s"), never "unavailable", and
 * the AI does not run (fail closed). DRAFT, PENDING owner approval.
 */
import { createElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

const post = vi.fn();
vi.mock('@/services/apiClient', () => ({ apiClient: { post: (...a: unknown[]) => post(...a) } }));

import i18n from '@/i18n/config';
import { QualityGatePanel } from '@/components/QualityGatePanel';
import { requestQualityGate } from './api';
import { confirmServerDecision } from './gate';

afterEach(() => { cleanup(); post.mockReset(); });

const limited = (seconds: number) => ({ response: { status: 429, headers: { 'retry-after': String(seconds) },
  data: { error: { code: 'HTTP_429', message: 'Too many', details: { code: 'gate_rate_limited', retry_after_s: seconds } } } } });

describe('F3: too many checks', () => {
  it('rc126 a 429 is the rate-limit reason with its seconds, never unavailable', async () => {
    post.mockRejectedValue(limited(42));
    const r = await requestQualityGate('file-1', false);
    expect(r.codes).toEqual(['gate_rate_limited']);
    expect(r.checks[0].params.seconds).toBe(42);
    expect(r.ai_may_run).toBe(false);
    expect(r.ai_output_allowed).toBe(false);
    expect(r.subject?.file_id).toBe('file-1');
    expect(confirmServerDecision(r, 'stripped').codes).toEqual(['gate_rate_limited']);   // final: same reason, no output
  });

  it('rc126 any other failure is still unavailable', async () => {
    post.mockRejectedValue({ response: { status: 500, data: {} } });
    expect((await requestQualityGate('file-1', false)).codes).toEqual(['gate_unavailable']);
  });

  it.each(['en', 'es', 'de'])('rc127 the panel says how long to wait in %s', async (lng) => {
    await i18n.changeLanguage(lng);
    post.mockRejectedValue(limited(17));
    render(createElement(QualityGatePanel, { result: await requestQualityGate('file-1', false) }));
    const check = screen.getByTestId('quality-gate-panel-check');
    expect(check).toHaveAttribute('data-code', 'gate_rate_limited');
    expect(check.textContent).toContain('17');
    expect(check.textContent).not.toContain('{{');
    await i18n.changeLanguage('en');
  });
});
