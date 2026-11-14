/**
 * Fifth independent review of PR #78, item V2 (CAPA-013, RC-060; DRAFT, PENDING owner approval): the draft, the
 * CAPA-013 notice and the review screen state ONE candidate figure — the reviewable candidates of
 * `change_candidates` (new lesions of at least the minimum size, and enlarging lesions), never the count of every new
 * component in `status_counts`. The backend half is tests/unit/test_verified_report_review5.py (same numbers).
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, act, cleanup } from '@testing-library/react';

vi.mock('@/api/segmentation', () => ({ segmentationAPI: { reviewLongitudinalCandidates: vi.fn() } }));

import i18n from '@/i18n/config';
import { LongitudinalResultPanel } from './LongitudinalResultPanel';

// the same numbers as the backend test: 5 new components (status_counts), 2 reviewable new candidates
const RESULT = {
  changes: [], total_lesions_tp1: 3, total_lesions_tp2: 9, burden_tp1_mm3: 1000, burden_tp2_mm3: 1400,
  burden_tp1_ml: 1.0, burden_tp2_ml: 1.4, burden_delta_mm3: 400, burden_delta_percent: 40.0,
  status_counts: { new: 5, resolved: 0, enlarged: 2, shrunk: 0, stable: 3 },
  change_candidates: { new: 2, enlarging: 1, total: 3, confirmed: 0, rejected: 0, awaiting_review: 3 },
  new_lesion_min_diameter_mm: 3, abstained: false, review_binding: null,
};

afterEach(async () => {
  cleanup();
  await act(async () => { await i18n.changeLanguage('en'); });
});

describe('the review screen states the reviewable candidates (fifth review, V2)', () => {
  for (const lng of ['en', 'es', 'de']) {
    it(`states 2 new and 1 enlarging candidates, as the draft and the notice (${lng})`, async () => {
      await act(async () => { await i18n.changeLanguage(lng); });
      render(<LongitudinalResultPanel result={RESULT as any} tp1SegId="s1" tp2SegId="s2" onReviewed={() => {}} />);
      const summary = screen.getByTestId('longitudinal-candidates').querySelector('p')!.textContent;
      expect(summary).toBe(i18n.t('longitudinal.candidatesSummary', { total: 3, n: 2, e: 1, d: 3 }));
    });
  }
});
