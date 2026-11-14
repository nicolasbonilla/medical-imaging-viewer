/**
 * RC-130 (REQ-SAFE-060; HAZ-003, HAZ-017) — DRAFT, PENDING owner approval.
 *
 * Research stage (owner decision 2026-11-13): the AI comments of the verified report are switched on with
 * claude-sonnet-5-5 BEFORE the registered measurement of that model. Every report whose draft holds text a model
 * wrote must therefore say, above that text, that the comments are in testing, which model wrote them, that
 * MSTool-AI has not validated it in its registered study, and that the prototype is not for clinical use. A draft
 * no model wrote (measurements only, withheld, unavailable) must not carry the notice: it would name a model that
 * wrote nothing. Written before the change.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, act, cleanup } from '@testing-library/react';
import fs from 'node:fs';
import path from 'node:path';

import i18n from '@/i18n/config';
import { ReportViewerModal } from './ReportViewerModal';

const LOCALES = path.join(__dirname, '..', 'i18n', 'locales');
const locale = (l: string) => JSON.parse(fs.readFileSync(path.join(LOCALES, `${l}.json`), 'utf-8'));
const BASE = { report_id: 'r130', content: 'body', template_type: 'general', processing_time_ms: 1 };
const AI_TEXT = 'AI-WRITTEN-COMMENT-MARKER';

function verification(interpretive_text: string, outcome: string, reason: string | null, attempts = 0) {
  return { flow: 'verified-report-1', outcome, interpretive_text, reason, attempts, rules_failed_last_attempt: [],
           not_included: [] };
}

async function show(lng: string, report: Record<string, unknown>) {
  await act(async () => { await i18n.changeLanguage(lng); });
  render(<ReportViewerModal isOpen onClose={() => {}} report={{ ...BASE, language: lng, ...report } as any} />);
}

afterEach(async () => {
  cleanup();
  await act(async () => { await i18n.changeLanguage('en'); });
});

describe('RC-130 — the AI comments are labelled as in testing (research stage)', () => {
  for (const lng of ['en', 'es', 'de']) {
    it(`rc130 shows the in-testing notice, naming the model, when its comments are in the draft (${lng})`, async () => {
      await show(lng, { model: 'claude-sonnet-5-5', ai_text: AI_TEXT, tokens_used: { input: 9, output: 9 },
                        verification: verification('delivered', 'passed_0', null, 1) });
      const notice = screen.getByTestId('report-ai-in-testing');
      const expected = String(locale(lng).reportViewer.aiInTesting).replace('{{model}}', 'claude-sonnet-5-5');
      expect(notice.textContent).toBe(expected);
      expect(notice.textContent).not.toMatch(/\{\{|\}\}/);
    });

    it(`rc130 puts the notice above the text the model wrote (${lng})`, async () => {
      await show(lng, { model: 'claude-sonnet-5-5', ai_text: AI_TEXT,
                        verification: verification('delivered', 'passed_0', null, 1) });
      const notice = screen.getByTestId('report-ai-in-testing');
      const body = document.body.textContent ?? '';
      expect(body.indexOf(notice.textContent ?? '')).toBeLessThan(body.indexOf(AI_TEXT));
    });

    it(`rc130 shows no in-testing notice for a draft no model wrote (${lng})`, async () => {
      const cases = [
        { model: null, verification: verification('not_requested', 'not_requested', 'llm_switched_off') },
        { model: 'claude-sonnet-5-5', verification: verification('withheld', 'blocked', 'failed_check', 3) },
        { model: 'claude-sonnet-5-5', verification: verification('withheld', 'withheld', 'timeout', 1) },
        { model: undefined },
      ];
      for (const c of cases) {
        await show(lng, { ai_text: '', ...c });
        expect(screen.queryByTestId('report-ai-in-testing')).toBeNull();
        cleanup();
      }
    });
  }

  it('rc130 a legacy report a model wrote (no verification record) is labelled too', async () => {
    await show('en', { model: 'claude-sonnet-5-5', content: 'legacy body' });
    expect(screen.getByTestId('report-ai-in-testing').textContent).toContain('claude-sonnet-5-5');
  });

  // Review of PR #82 (finding 2): the notice says "the AI comments below" — it must not sit above the clinician's own
  // entry or the notes the code wrote, or it attributes them to the model.
  it('rc130 sits after the clinician entry and the code-written notes, right before the model text', async () => {
    await show('en', {
      model: 'claude-sonnet-5-5', verification: verification('delivered', 'passed_0', null, 1),
      disclaimer: 'DISCLAIMER-MARKER',
      clinician_entry: { heading: 'Clinician', fields: [{ key: 'h', label: 'History', text: 'CLINICIAN-MARKER', truncated: false }] },
      ai_draft_heading: 'Draft',
      app_notes: [{ kind: 'placeholder', heading: null, text: 'APPNOTE-MARKER', lines: [] }],
      ai_text: AI_TEXT,
    });
    const body = document.body.textContent ?? '';
    const at = body.indexOf(screen.getByTestId('report-ai-in-testing').textContent ?? '');
    for (const before of ['DISCLAIMER-MARKER', 'CLINICIAN-MARKER', 'APPNOTE-MARKER']) {
      expect(body.indexOf(before)).toBeLessThan(at);
    }
    expect(at).toBeLessThan(body.indexOf(AI_TEXT));
  });

  // Review of PR #82 (finding 7): a report written in German keeps a German notice with the interface in English.
  it('rc130 words the notice in the report language, not the interface language', async () => {
    await act(async () => { await i18n.changeLanguage('en'); });
    render(<ReportViewerModal isOpen onClose={() => {}} report={{ ...BASE, language: 'de', model: 'claude-sonnet-5-5',
      ai_text: AI_TEXT, verification: verification('delivered', 'passed_0', null, 1) } as any} />);
    const expected = String(locale('de').reportViewer.aiInTesting).replace('{{model}}', 'claude-sonnet-5-5');
    expect(screen.getByTestId('report-ai-in-testing').textContent).toBe(expected);
  });

  // Review of PR #82 (finding 1): the text the model wrote must not leave the app without the label.
  it('rc130 the viewer Copy button puts the notice first', async () => {
    let copied = '';
    Object.assign(navigator, { clipboard: { writeText: async (s: string) => { copied = s; } } });
    await show('es', { model: 'claude-sonnet-5-5', content: 'CONTENT-MARKER', ai_text: AI_TEXT,
                       verification: verification('delivered', 'passed_0', null, 1) });
    const notice = String(locale('es').reportViewer.aiInTesting).replace('{{model}}', 'claude-sonnet-5-5');
    const copyButton = screen.getAllByRole('button').find((b) => /copi|copy|kopier/i.test(b.textContent ?? ''));
    expect(copyButton).toBeTruthy();
    await act(async () => { copyButton!.click(); });
    expect(copied.startsWith(notice)).toBe(true);
    expect(copied).toContain('CONTENT-MARKER');
  });

  it('rc130 the wording says in testing, not validated, research prototype, not for clinical use (en/es/de)', () => {
    const words: Record<string, RegExp[]> = {
      en: [/in testing/i, /not yet validated/i, /research prototype/i, /not for clinical use/i],
      es: [/en pruebas/i, /todavía no ha validado/i, /prototipo de investigación/i, /no apto para uso clínico/i],
      de: [/in Erprobung/i, /noch nicht validiert/i, /Forschungsprototyp/i, /nicht für den klinischen Einsatz/i],
    };
    for (const [lng, patterns] of Object.entries(words)) {
      const text = String(locale(lng).reportViewer.aiInTesting);
      for (const p of patterns) expect(text).toMatch(p);
      expect(text).toContain('{{model}}');
    }
  });
});
