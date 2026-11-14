/**
 * Sixth independent review of PR #78, item W1 (CAPA-013, RC-060; DRAFT, PENDING owner approval): a null or missing
 * candidate count is "not computed" on the review screen, as in the draft and its notice — never an invented 0.
 * The backend half is tests/unit/test_verified_report_review6.py (same cases).
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, act, cleanup } from '@testing-library/react';

vi.mock('@/api/segmentation', () => ({ segmentationAPI: { reviewLongitudinalCandidates: vi.fn() } }));

import i18n from '@/i18n/config';
import { LongitudinalResultPanel } from './LongitudinalResultPanel';

const BASE = {
  changes: [], total_lesions_tp1: 3, total_lesions_tp2: 9, burden_tp1_mm3: 1000, burden_tp2_mm3: 1400,
  burden_tp1_ml: 1.0, burden_tp2_ml: 1.4, burden_delta_mm3: 400, burden_delta_percent: 40.0,
  status_counts: { new: 5, resolved: 0, enlarged: 2, shrunk: 0, stable: 3 },
  new_lesion_min_diameter_mm: 3, abstained: false, review_binding: null,
};

afterEach(async () => {
  cleanup();
  await act(async () => { await i18n.changeLanguage('en'); });
});

describe('a null or missing candidate count is "not computed" (sixth review, W1)', () => {
  const cases: Array<[string, Record<string, unknown>]> = [
    ['new is null', { new: null, enlarging: 3, total: 3, confirmed: 0, rejected: 0, awaiting_review: 3 }],
    ['new is missing', { enlarging: 3, total: 3, confirmed: 0, rejected: 0, awaiting_review: 3 }],
  ];
  for (const lng of ['en', 'es', 'de']) {
    for (const [name, cc] of cases) {
      it(`${name} (${lng})`, async () => {
        await act(async () => { await i18n.changeLanguage(lng); });
        render(<LongitudinalResultPanel result={{ ...BASE, change_candidates: cc } as any} tp1SegId="s1" tp2SegId="s2"
          onReviewed={() => {}} />);
        const summary = screen.getByTestId('longitudinal-candidates').querySelector('p')!.textContent;
        expect(summary).toBe(i18n.t('longitudinal.candidatesNotComputed'));
        expect(i18n.exists('longitudinal.candidatesNotComputed')).toBe(true);
      });
    }
  }
});
