/**
 * Release 2026-10-25 — independent integration review of PR #69, item 6.
 *
 * With PR #68 the server derives the lesion table of the report's segmentation itself; when the source image's
 * voxel geometry cannot be read it answers 422 "The image geometry could not be read; report not generated …".
 * The panel showed CAPA-008's "No measurements are available" for every 422. It must say what happened instead,
 * in the user's language, and keep CAPA-008's message for a request without measurements.
 *
 * Written before the correction (fails on 6d1fde2).
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
    getDISAssessment: vi.fn(async () => ({ evaluation_status: 'not_evaluated' })),
  },
}));

import i18n from '@/i18n/config';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { AIReportPanel } from './AIReportPanel';

const LOCALES = path.join(__dirname, '..', 'i18n', 'locales');
const locale = (l: string) => JSON.parse(fs.readFileSync(path.join(LOCALES, `${l}.json`), 'utf-8'));

function http422(message: string) {
  return Object.assign(new Error('Request failed with status code 422'), {
    response: { status: 422, data: { error: { code: 'HTTP_422', message, details: {} } } },
  });
}

const GEOMETRY = 'The image geometry could not be read; report not generated: the lesion measurements of segmentation '
  + 'seg-7 could not be computed on the server (the source image or its voxel geometry could not be read). '
  + 'Nothing was sent.';
const NO_MEASUREMENT = 'No measurement was supplied (lesion analysis, DIS assessment, longitudinal comparison, zone '
  + 'statistics or volumetry).';

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
  useSegmentationStore.getState().setCurrentSegmentation({ segmentation_id: 'seg-7' } as any);
  await act(async () => { await i18n.changeLanguage('en'); });
});
afterEach(async () => {
  cleanup();
  useSegmentationStore.getState().setCurrentSegmentation(null);
  await act(async () => { await i18n.changeLanguage('en'); });
});

describe('Release 2026-10-25: the report panel names an unreadable image geometry', () => {
  it.each(['en', 'es', 'de'])('rc070 release r6 a geometry 422 shows its own message, not "no measurements" (%s)',
    async (lng) => {
      await act(async () => { await i18n.changeLanguage(lng); });
      generateReport.mockRejectedValue(http422(GEOMETRY));
      renderPanel();
      fireEvent.click(screen.getByTestId('report-generate-button'));
      const own: string = locale(lng).report?.geometryUnreadable ?? '';
      expect(own.length).toBeGreaterThan(40);
      if (lng !== 'en') expect(own).not.toBe(locale('en').report.geometryUnreadable);
      await waitFor(() => expect(screen.getByText(own)).toBeTruthy());
      expect(screen.queryByText(locale(lng).report.noMeasurements)).toBeNull();
    });

  it('rc070 release r6 a 422 without measurements still shows the CAPA-008 message', async () => {
    generateReport.mockRejectedValue(http422(NO_MEASUREMENT));
    renderPanel();
    fireEvent.click(screen.getByTestId('report-generate-button'));
    await waitFor(() => expect(screen.getByText(locale('en').report.noMeasurements)).toBeTruthy());
    expect(screen.queryByText(locale('en').report.geometryUnreadable ?? '\u0000none')).toBeNull();
  });
});
