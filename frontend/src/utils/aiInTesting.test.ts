/**
 * RC-130 (REQ-SAFE-060; HAZ-003, HAZ-017) — DRAFT, PENDING owner approval. Review of PR #82, findings 1 and 7:
 * the clipboard carries the in-testing notice first, in the report's language, and no Copy button of a report
 * bypasses it.
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

import { aiInTestingNotice, modelWroteText, textToCopy } from './aiInTesting';

const LOCALES = path.join(__dirname, '..', 'i18n', 'locales');
const locale = (l: string) => JSON.parse(fs.readFileSync(path.join(LOCALES, `${l}.json`), 'utf-8'));
const delivered = { flow: 'verified-report-1', outcome: 'passed_0', interpretive_text: 'delivered', reason: null,
                    attempts: 1 };

describe('RC-130 — one rule for the notice, the viewer and the clipboard', () => {
  for (const lng of ['en', 'es', 'de']) {
    it(`rc130 textToCopy puts the notice first, in the report language (${lng})`, () => {
      const r = { content: 'BODY', language: lng, model: 'claude-sonnet-5-5', verification: delivered };
      const notice = String(locale(lng).reportViewer.aiInTesting).replace('{{model}}', 'claude-sonnet-5-5');
      expect(aiInTestingNotice(r)).toBe(notice);
      expect(textToCopy(r)).toBe(`${notice}\n\nBODY`);
    });
  }

  it('rc130 textToCopy is the content unchanged when no model wrote text', () => {
    const cases = [
      { model: null, verification: { ...delivered, interpretive_text: 'not_requested' } },
      { model: 'claude-sonnet-5-5', verification: { ...delivered, interpretive_text: 'withheld' } },
      { model: undefined, verification: null },
    ];
    for (const c of cases) {
      const r = { content: 'BODY', language: 'en', ...c };
      expect(modelWroteText(r as any)).toBe(false);
      expect(aiInTestingNotice(r as any)).toBeNull();
      expect(textToCopy(r as any)).toBe('BODY');
    }
  });

  it('rc130 no Copy button of a report writes the raw content to the clipboard', () => {
    const dir = path.join(__dirname, '..', 'components');
    const offenders: string[] = [];
    for (const f of fs.readdirSync(dir)) {
      if (!/\.tsx$/.test(f) || /\.test\.tsx$/.test(f)) continue;
      const src = fs.readFileSync(path.join(dir, f), 'utf-8');
      if (/writeText\(\s*report\.content\s*\)|\.value\s*=\s*report\.content\b/.test(src)) offenders.push(f);
    }
    expect(offenders).toEqual([]);
  });
});
