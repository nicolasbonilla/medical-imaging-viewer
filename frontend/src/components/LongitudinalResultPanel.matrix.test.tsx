/**
 * Eighth independent review of PR #78, I11 (CAPA-013, RC-060; DRAFT, PENDING owner approval): the review screen and
 * the draft apply ONE rule. This test reads the SAME fixture as the backend scenario matrix
 * (backend/tests/fixtures/longitudinal_cases.json) and checks the panel's numbers and its "not computed" state.
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, act, cleanup } from '@testing-library/react';

vi.mock('@/api/segmentation', () => ({ segmentationAPI: { reviewLongitudinalCandidates: vi.fn() } }));

import i18n from '@/i18n/config';
import { LongitudinalResultPanel } from './LongitudinalResultPanel';

type Case = {
  name: string;
  longitudinal: Record<string, unknown>;
  expected: { computed: boolean; new: number | null; enlarging: number | null; abstained?: boolean };
};
// (vitest runs from frontend/: the backend fixture is one level up)
const FIXTURE = JSON.parse(readFileSync(resolve(process.cwd(), '../backend/tests/fixtures/longitudinal_cases.json'),
  'utf-8')) as { cases: Case[] };

const BASE = {
  changes: [], total_lesions_tp1: 3, total_lesions_tp2: 9, burden_tp1_mm3: 1000, burden_tp2_mm3: 1400,
  burden_tp1_ml: 1.0, burden_tp2_ml: 1.4, burden_delta_mm3: 400, burden_delta_percent: 40.0,
  new_lesion_min_diameter_mm: 3, abstained: false, review_binding: null,
};

afterEach(async () => {
  cleanup();
  await act(async () => { await i18n.changeLanguage('en'); });
});

describe('the review screen follows the draft\'s rule on every longitudinal case (eighth review, I11)', () => {
  it('reads the shared fixture', () => {
    expect(FIXTURE.cases.length).toBeGreaterThanOrEqual(8);
  });
  for (const c of FIXTURE.cases) {
    it(c.name, () => {
      render(<LongitudinalResultPanel result={{ ...BASE, ...c.longitudinal } as any} tp1SegId="s1" tp2SegId="s2"
        onReviewed={() => {}} />);
      if (c.expected.abstained) {
        expect(screen.queryByTestId('longitudinal-candidates')).toBeNull();
        return;
      }
      const summary = screen.getByTestId('longitudinal-candidates').querySelector('p')!.textContent;
      if (!c.expected.computed) {
        expect(summary).toBe(i18n.t('longitudinal.candidatesNotComputed'));
      } else {
        expect(summary).toBe(i18n.t('longitudinal.candidatesSummary', {
          total: (c.expected.new as number) + (c.expected.enlarging as number), n: c.expected.new,
          e: c.expected.enlarging, d: 3,
        }));
      }
    });
  }
});
