/**
 * Third independent review of PR #78, item 4 (REQ-FUNC-116; RC-103, RC-104; DRAFT, PENDING owner approval).
 *
 * The viewer wrote "Model: Claude" for every report — also for one no model wrote (model = null: the measurements
 * only, the AI comments switched off, not configured, withheld or not available) — and did not show how the draft was
 * obtained. The model is named only when a model wrote text in the draft, and the verification state of the new
 * `verification` field is shown in the reader's language. Written before the correction.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, act, cleanup } from '@testing-library/react';
import fs from 'node:fs';
import path from 'node:path';

import i18n from '@/i18n/config';
import { ReportViewerModal } from './ReportViewerModal';

const LOCALES = path.join(__dirname, '..', 'i18n', 'locales');
const locale = (l: string) => JSON.parse(fs.readFileSync(path.join(LOCALES, `${l}.json`), 'utf-8'));
const BASE = { report_id: 'r3', content: 'body', template_type: 'general', processing_time_ms: 1 };

function verification(interpretive_text: string, outcome: string, reason: string | null, attempts = 0) {
  return { flow: 'verified-report-1', outcome, interpretive_text, reason, attempts, rules_failed_last_attempt: [],
           not_included: [] };
}

async function show(lng: string, report: Record<string, unknown>) {
  await act(async () => { await i18n.changeLanguage(lng); });
  render(<ReportViewerModal isOpen onClose={() => {}} report={{ ...BASE, language: lng, ...report } as any} />);
  return document.body.textContent ?? '';
}

afterEach(async () => {
  cleanup();
  await act(async () => { await i18n.changeLanguage('en'); });
});

describe('verified report — the viewer says who wrote what (third review, item 4)', () => {
  for (const lng of ['en', 'es', 'de']) {
    it(`names no model for a measurements-only draft (${lng})`, async () => {
      const text = await show(lng, { model: null, tokens_used: null,
                                     verification: verification('not_requested', 'not_requested', 'llm_switched_off') });
      expect(text).not.toMatch(/Claude/);
      expect(screen.queryByTestId('report-model')).toBeNull();
      expect(screen.getByTestId('report-verification-state').textContent)
        .toBe(locale(lng).reportViewer.verification.notRequested);
    });

    it(`says the interpretive text was withheld by the check, and names no model (${lng})`, async () => {
      const text = await show(lng, { model: 'claude-sonnet-5-5', tokens_used: { input: 9, output: 9 },
                                     verification: verification('withheld', 'blocked', 'failed_check', 3) });
      expect(screen.queryByTestId('report-model')).toBeNull();
      expect(text).not.toMatch(/claude-sonnet-5-5|Claude/);
      expect(screen.getByTestId('report-verification-state').textContent)
        .toBe(locale(lng).reportViewer.verification.withheldCheck);
    });

    it(`says the AI service gave no text when it failed after being asked (${lng})`, async () => {
      await show(lng, { model: 'claude-sonnet-5-5', verification: verification('withheld', 'withheld', 'timeout', 1) });
      expect(screen.queryByTestId('report-model')).toBeNull();
      expect(screen.getByTestId('report-verification-state').textContent)
        .toBe(locale(lng).reportViewer.verification.withheldUnavailable);
    });

    it(`names the model when its checked comments are in the draft (${lng})`, async () => {
      await show(lng, { model: 'claude-sonnet-5-5', tokens_used: { input: 9, output: 9 },
                        verification: verification('delivered', 'passed_0', null, 1) });
      expect(screen.getByTestId('report-model').textContent).toContain('claude-sonnet-5-5');
      expect(screen.getByTestId('report-verification-state').textContent)
        .toBe(locale(lng).reportViewer.verification.delivered);
    });
  }

  it('never names a default model for a report without a model', async () => {
    const text = await show('en', { model: undefined });
    expect(text).not.toMatch(/Claude/);
    expect(screen.queryByTestId('report-model')).toBeNull();
  });

  it('the Spanish wording is the one the owner reads', () => {
    const v = locale('es').reportViewer.verification;
    expect(v.withheldCheck.toLowerCase()).toContain('texto interpretativo retenido por la comprobación');
    expect(v.notRequested.toLowerCase()).toContain('solo mediciones');
    for (const l of ['en', 'de']) {
      expect(Object.keys(locale(l).reportViewer.verification).sort()).toEqual(Object.keys(v).sort());
    }
  });
});
