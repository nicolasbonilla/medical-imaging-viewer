/**
 * CAPA-014 — AI report draft panel (RC-065, RC-066; REQ-SEC-022, REQ-SEC-023; HAZ-016).
 *
 * The server removes the patient's identifiers before anything is sent to the AI provider, using the
 * record of the patient the analysed segmentation belongs to. The panel must therefore name that
 * segmentation in its request (the server refuses otherwise), and it states honestly, next to the
 * draft button and in the reader's language, what is removed and what is still sent.
 *
 * Written before the fix: on main the request carries no segmentation and no note is shown.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import fs from 'node:fs';
import path from 'node:path';

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
    getDISAssessment: vi.fn(async () => ({ dis_met: false })),
  },
}));

import i18n from '@/i18n/config';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { AIReportPanel } from './AIReportPanel';

const LOCALES = path.join(__dirname, '..', 'i18n', 'locales');
const note = (l: string): string =>
  JSON.parse(fs.readFileSync(path.join(LOCALES, `${l}.json`), 'utf-8')).report?.deidentificationNote ?? '';

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AIReportPanel />
    </QueryClientProvider>,
  );
}

beforeEach(async () => {
  generateReport.mockReset();
  generateReport.mockResolvedValue({ report_id: 'r', content: 'x', template_type: 'general', language: 'en',
    processing_time_ms: 1 });
  useSegmentationStore.getState().setCurrentSegmentation({ segmentation_id: 'seg-7' } as any);
  await act(async () => { await i18n.changeLanguage('en'); });
});
afterEach(async () => {
  cleanup();
  useSegmentationStore.getState().setCurrentSegmentation(null);
  await act(async () => { await i18n.changeLanguage('en'); });
});

describe('CAPA-014 report draft panel', () => {
  it('rc065 the request names the analysed segmentation, so the server can remove that patient\'s identifiers', async () => {
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: /generate report/i }));
    await waitFor(() => expect(generateReport).toHaveBeenCalledTimes(1));
    expect(generateReport.mock.calls[0][0].segmentation_id).toBe('seg-7');
  });

  it.each(['en', 'es', 'de'])('rc066 the note next to the draft button says what is removed and what is sent (%s)', async (lng) => {
    await act(async () => { await i18n.changeLanguage(lng); });
    renderPanel();
    const text = note(lng);
    expect(text.length).toBeGreaterThan(80);
    const shown = screen.getByTestId('report-deidentification-note');
    expect(shown.textContent).toBe(text);
    const button = screen.getByTestId('report-generate-button');
    expect(button.previousElementSibling).toBe(shown);       // directly above the draft button
    if (lng !== 'en') expect(text).not.toBe(note('en'));     // translated, not the English text
  });

  it('rc066 the English note is precise about the removal and about what still goes to the provider', () => {
    const text = note('en');
    for (const word of ['Anthropic', 'name', 'record number', 'birth date', 'dates', 'phone', 'e-mail',
      'ID numbers', '5-year', 'measurements', 'sex', 'Other names']) {
      expect(text).toContain(word);
    }
  });

  it('rc066 the API client no longer claims HIPAA compliance', () => {
    const src = fs.readFileSync(path.join(__dirname, '..', 'api', 'aiReport.ts'), 'utf-8');
    expect(src).not.toMatch(/HIPAA/);
  });
});
