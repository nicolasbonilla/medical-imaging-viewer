/**
 * Tenth independent review of PR #78, I16 (DRAFT, PENDING owner approval): the report panel maps the server's error
 * CODES to its own messages — never a message prefix, never the generic "no measurements" for another 422. This test
 * reads the SAME fixture as the backend (backend/tests/fixtures/report_error_codes.json): every code the route can
 * return has its own message, in en, es and de; an implausible measurement is named, said to come from the
 * segmentation analysis, and the physician is asked to re-run the analysis or check the segmentation.
 *
 * Written failing first on 0a6b1c4.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { readFileSync } from 'fs';
import { resolve, join } from 'path';

const generateReport = vi.fn();
vi.mock('@/api/aiReport', () => ({
  aiReportAPI: {
    generateReport: (...a: unknown[]) => generateReport(...a),
    listTemplates: vi.fn(async () => [{ id: 'general', name: 'General', description: '' }]),
  },
}));
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    analyzeLesions: vi.fn(async () => ({ total_count: 3 })),
    getDISAssessment: vi.fn(async () => ({ evaluation_status: 'not_evaluated' })),
  },
}));

import i18n from '@/i18n/config';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { AIReportPanel } from './AIReportPanel';

type Code = { code: string; status: number; key: string; en: string; details?: Record<string, unknown> };
// (vitest runs from frontend/: the backend fixture is one level up)
const FIXTURE = JSON.parse(readFileSync(resolve(process.cwd(), '../backend/tests/fixtures/report_error_codes.json'),
  'utf-8')) as { codes: Code[]; fields: Record<string, string>; unknown_field: string };
const LOCALES = join(__dirname, '..', 'i18n', 'locales');
const locale = (l: string) => JSON.parse(readFileSync(join(LOCALES, `${l}.json`), 'utf-8'));
const at = (obj: any, key: string) => key.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);

function serverError(c: { code: string; status: number; details?: Record<string, unknown> }) {
  // the server's own text is deliberately unlike the panel's: the panel must read the code, not the message
  return Object.assign(new Error(`Request failed with status code ${c.status}`), {
    response: { status: c.status, data: { error: { code: c.code, message: 'server text', details: c.details ?? {} } } },
  });
}

async function shown(c: { code: string; status: number; details?: Record<string, unknown> }) {
  generateReport.mockRejectedValue(serverError(c));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={qc}><AIReportPanel /></QueryClientProvider>);
  fireEvent.click(screen.getByTestId('report-generate-button'));
  const box = await screen.findByTestId('report-error');
  return box.textContent ?? '';
}

beforeEach(async () => {
  generateReport.mockReset();
  useSegmentationStore.getState().setCurrentSegmentation({ segmentation_id: 'seg-10' } as any);
  await act(async () => { await i18n.changeLanguage('en'); });
});
afterEach(async () => {
  cleanup();
  useSegmentationStore.getState().setCurrentSegmentation(null);
  await act(async () => { await i18n.changeLanguage('en'); });
});

describe('the report panel maps every server error code to its own message (tenth review, I16)', () => {
  it('reads the shared fixture', () => {
    expect(FIXTURE.codes.length).toBeGreaterThanOrEqual(12);
  });

  for (const c of FIXTURE.codes) {
    it(`i16 ${c.code} (${c.status}) shows its own message`, async () => {
      const text = await shown(c);
      expect(text).toBe(c.en);
    });
  }

  it('i16 every code has a distinct message', () => {
    const texts = FIXTURE.codes.map((c) => c.en);
    expect(new Set(texts).size).toBe(texts.length);
  });

  for (const lng of ['es', 'de']) {
    it(`i16 every code's message exists in ${lng} and is translated`, () => {
      for (const c of FIXTURE.codes) {
        const own = at(locale(lng), c.key);
        expect(typeof own === 'string' && own.length > 20, `${lng} ${c.key}`).toBe(true);
        expect(own).not.toBe(at(locale('en'), c.key));
      }
      for (const field of Object.keys(FIXTURE.fields)) {
        expect(at(locale(lng), `report.measurementNames.${field}`), `${lng} ${field}`).toBeTruthy();
      }
    });
  }

  it('i16 an implausible measurement names it and says it comes from the segmentation analysis (every field)',
    async () => {
      for (const [field, label] of Object.entries(FIXTURE.fields)) {
        const text = await shown({ code: 'implausible_measurement', status: 422, details: { field } });
        expect(text, field).toContain(label);
        expect(text).toContain('segmentation analysis');
        expect(text).toMatch(/Re-run the analysis or check the segmentation/);
        expect(text.toLowerCase()).not.toContain('correct');
        expect(text).not.toContain('No measurements are available');
        cleanup();
      }
      const unknown = await shown({ code: 'implausible_measurement', status: 422, details: { field: 'zzz' } });
      expect(unknown).toContain(FIXTURE.unknown_field);
    });

  it('i16 the panel never decides by a message prefix or by the status alone', () => {
    const src = readFileSync(join(__dirname, 'AIReportPanel.tsx'), 'utf-8');
    expect(src).not.toMatch(/startsWith\(/);
    expect(src).not.toMatch(/status === 422/);
  });
});
