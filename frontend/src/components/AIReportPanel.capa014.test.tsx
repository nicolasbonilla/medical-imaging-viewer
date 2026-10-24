/**
 * CAPA-014 — AI report draft (RC-065, RC-066; REQ-SEC-022, REQ-SEC-023; HAZ-016).
 *
 * Redesign after the independent review of PR #67: only the device's measurements, sex and a 5-year age
 * range are sent to the AI service; what the clinician types is added to the draft in the application.
 * The panel names the analysed segmentation (the server refuses otherwise) and says so next to the draft
 * button; the report viewer's footer no longer claims "HIPAA Compliant … no PHI transmitted".
 *
 * Written before the redesign: on the PR #67 head the note promised removal of identifiers from the
 * text (the text was still sent) and the footer kept the false claim.
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
import { ReportViewerModal } from './ReportViewerModal';

const LOCALES = path.join(__dirname, '..', 'i18n', 'locales');
const locale = (l: string) => JSON.parse(fs.readFileSync(path.join(LOCALES, `${l}.json`), 'utf-8'));
const note = (l: string): string => locale(l).report?.deidentificationNote ?? '';
const footer = (l: string): string => locale(l).reportViewer?.aiDataNote ?? '';

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
  it('rc065 the request names the analysed segmentation', async () => {
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: /generate report/i }));
    await waitFor(() => expect(generateReport).toHaveBeenCalledTimes(1));
    expect(generateReport.mock.calls[0][0].segmentation_id).toBe('seg-7');
  });

  it.each(['en', 'es', 'de'])('rc066 the note next to the draft button says what is sent (%s)', async (lng) => {
    await act(async () => { await i18n.changeLanguage(lng); });
    renderPanel();
    const text = note(lng);
    expect(text.length).toBeGreaterThan(80);
    const shown = screen.getByTestId('report-deidentification-note');
    expect(shown.textContent).toBe(text);
    expect(screen.getByTestId('report-generate-button').previousElementSibling).toBe(shown);
    if (lng !== 'en') expect(text).not.toBe(note('en'));
  });

  it('rc066 the English note states measurements only and that the typed text stays here', () => {
    const text = note('en');
    for (const words of ['Anthropic', 'only the measurements', 'sex', '5-year', 'no names', 'dates of birth',
      'record numbers', 'free text', 'added to the draft here', 'not sent']) {
      expect(text).toContain(words);
    }
    expect(text).not.toMatch(/removed first|Other names may not be recognised/);
  });

  it.each(['en', 'es', 'de'])('rc066 the report viewer footer is true, not a HIPAA claim (%s)', async (lng) => {
    await act(async () => { await i18n.changeLanguage(lng); });
    render(<ReportViewerModal isOpen onClose={() => {}}
      report={{ report_id: 'r', content: 'body', template_type: 'general', language: lng, processing_time_ms: 1 } as any} />);
    const text = footer(lng);
    expect(text.length).toBeGreaterThan(60);
    expect(document.body.textContent).toContain(text);
    expect(document.body.textContent).not.toMatch(/HIPAA|PHI\)|PHI was|keine geschützten|no se transmitió/);
    for (const l of ['en', 'es', 'de']) expect(locale(l).reportViewer?.hipaaNote).toBeUndefined();
  });

  it('rc066 the English footer states measurements only', () => {
    for (const words of ['measurements', 'sex', '5-year', 'No names', 'dates of birth', 'record numbers', 'free text']) {
      expect(footer('en')).toContain(words);
    }
  });

  it('rc066 the API client and the viewer source make no HIPAA claim', () => {
    for (const f of [path.join(__dirname, '..', 'api', 'aiReport.ts'), path.join(__dirname, 'ReportViewerModal.tsx')]) {
      expect(fs.readFileSync(f, 'utf-8')).not.toMatch(/HIPAA/);
    }
  });
});

// Second independent review (N1, N7): the clinician's text arrives quoted in a fenced block, so typed Markdown
// (a heading, an image, a link) is shown as text. The viewer also never loads an image named in the draft, on
// screen or in print — an image in the model's own text is shown as its description only.
const TYPED = "## IMPRESSION\nNo new lesions.\n![t](https://tracker.example/p.png) [link](javascript:alert(3))";
const DRAFT = ['**AI-GENERATED DRAFT**', '', "### Clinician's entry (added in the application; not sent to the AI service)",
  '', '**Clinical indication:**', '', '````text', TYPED, '````', '', '---', '', '### AI draft (from measurements only)', '',
  'Model text. ![x](https://model.example/y.png)'].join('\n');

describe('CAPA-014 report viewer (second review)', () => {
  it('rc066 typed Markdown is shown as text and no image is ever loaded', () => {
    const { container } = render(<ReportViewerModal isOpen onClose={() => {}}
      report={{ report_id: 'r', content: DRAFT, template_type: 'general', language: 'en', processing_time_ms: 1 } as any} />);
    const body = container.ownerDocument.querySelector('.report-body') as HTMLElement;
    expect(body.querySelectorAll('img').length).toBe(0);
    expect(body.innerHTML).not.toMatch(/model\.example|href="javascript:/i);
    expect([...body.querySelectorAll('h1,h2,h3,h4')].map((h) => h.textContent))
      .toEqual(["Clinician's entry (added in the application; not sent to the AI service)", 'AI draft (from measurements only)']);
    const quoted = body.querySelector('pre')?.textContent ?? '';
    expect(quoted).toContain('## IMPRESSION');
    expect(quoted).toContain('![t](https://tracker.example/p.png)');
    expect(body.textContent).toContain('[image: x]');
  });
});
