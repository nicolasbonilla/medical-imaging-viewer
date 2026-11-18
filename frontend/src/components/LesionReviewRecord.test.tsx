/**
 * RC-131 (REQ-FUNC-119) and RC-132 (REQ-FUNC-120), HAZ-001 cause (m): the reader goes along with the AI draft.
 *
 *  - after a confirmed review, the banner says what the reviewer did with the draft's lesions and how many lesions the
 *    reviewer added (the model's misses); a record that could not be made is said, never left out;
 *  - the original draft is sent in the mask upload's binary format, to its own write-once route;
 *  - on an image of the reader-study set read without the draft first, the in-browser AI is held back until the
 *    reader recorded their own reading; recording it sends the digest of the saved mask on screen.
 */
import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const readerStudyAssignment = vi.fn();
const recordUnaidedReading = vi.fn();
vi.mock('@/api/segmentation', async () => {
  const real = await vi.importActual<typeof import('@/api/segmentation')>('@/api/segmentation');
  return {
    segmentationAPI: {
      storeAiDraftOriginal: real.segmentationAPI.storeAiDraftOriginal,
      readerStudyAssignment: (...a: unknown[]) => readerStudyAssignment(...a),
      recordUnaidedReading: (...a: unknown[]) => recordUnaidedReading(...a),
      confirmAiReview: vi.fn(),
      getSegmentation: vi.fn(),
    },
  };
});
const put = vi.fn().mockResolvedValue({ data: {} });
vi.mock('@/services/apiClient', () => ({ apiClient: { put: (...a: unknown[]) => put(...a), get: vi.fn(), post: vi.fn() } }));

import i18n from '@/i18n/config';
import { AiDraftBanner } from './AiDraftBanner';
import { ReaderStudyGate, UnaidedReadingCard } from './LesionReviewRecord';
import { segmentationAPI } from '@/api/segmentation';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type { AIProvenance, ReaderStudyAssignment } from '@/types';

const DIGEST = 'cd'.repeat(32);
const CONFIRMED: AIProvenance = {
  kind: 'ai_draft', model_name: 'FLAMeS', model_version: 'Zenodo 10.5281/zenodo.17955359 v2.0 (Dataset004_WML)',
  model_sha256: '2a10bb9d72dc33381a3f44dd6a59ec612dfd87534e02f15488b426ae127176ae', fold: 0,
  source_checkpoint_sha256: '4fc7db24e7c1541b59023df2a2f498a964eb629fe38f4eaec763297dd3fdf861',
  pipeline_version: 'mstool-flames-browser/0.3.0-prototype', runtime: 'onnxruntime-web 1.24.1 wasm x1',
  generated_at: '2026-11-18T10:00:00.000Z', lesion_count: 3, annotated_voxels: 24, review_status: 'confirmed',
  reviewed_by: 'dr_rev', reviewed_at: '2026-11-18T11:00:00Z', reviewed_mask_sha256: DIGEST,
  sequence_evidence: 'clinician',
};

const assignment = (over: Partial<ReaderStudyAssignment> = {}): ReaderStudyAssignment => ({
  study_on: true, unaided_first: true, reading_recorded: false, reading_segmentation_ids: [], own_draft_saved: false,
  ...over,
});

function withQuery(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(async () => {
  await i18n.changeLanguage('en');
  readerStudyAssignment.mockReset();
  recordUnaidedReading.mockReset();
  put.mockClear();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  useSegmentationStore.setState({ maskDigestCallback: vi.fn().mockResolvedValue(DIGEST) });
});

describe('RC-131 lesion-by-lesion record of the AI review', () => {
  it('rc131 a confirmed review says what the reviewer did with each lesion and how many were added', () => {
    const p = { ...CONFIRMED, review_record_summary: { available: true, draft_lesions: 3, final_lesions: 3, kept: 1,
                                                       corrected: 1, removed: 1, added: 1 } };
    render(<AiDraftBanner provenance={p} segmentationId="seg-1" />);
    expect(screen.getByTestId('review-record').textContent).toContain(
      'of its 3 lesions, 1 kept, 1 corrected, 1 removed; 1 added by the reviewer');
    expect(screen.queryByTestId('review-record-unaided')).toBeNull();
  });

  it('rc131 the counts are in the interface language, with the reading before the draft when there is one', async () => {
    await i18n.changeLanguage('es');
    const p = { ...CONFIRMED, review_record_summary: {
      available: true, draft_lesions: 3, final_lesions: 4, kept: 1, corrected: 1, removed: 1, added: 2,
      unaided: { reader_lesions: 2, reader_and_draft: 1, reader_only: 1, adopted_from_draft: 1, added_later: 1,
                 dropped_after_draft: 0 } } };
    render(<AiDraftBanner provenance={p} segmentationId="seg-1" />);
    expect(screen.getByTestId('review-record').textContent).toContain('2 añadidas por quien revisó');
    expect(screen.getByTestId('review-record-unaided').textContent).toContain('1 solo por quien revisó');
  });

  it('rc131 a record that could not be made is said, never left out', () => {
    const p = { ...CONFIRMED, review_record_summary: { available: false, reason: 'original_not_stored' } };
    render(<AiDraftBanner provenance={p} segmentationId="seg-1" />);
    expect(screen.getByTestId('review-record-unavailable')).toBeInTheDocument();
  });

  it('rc131 an unreviewed draft shows no counts', () => {
    const p = { ...CONFIRMED, review_status: 'unreviewed' as const, reviewed_by: null, reviewed_at: null,
                reviewed_mask_sha256: null, review_record_summary: { available: true, kept: 9 } };
    render(<AiDraftBanner provenance={p} segmentationId="seg-1" />);
    expect(screen.queryByTestId('review-record')).toBeNull();
  });

  it('rc131 the original draft goes to its own route in the mask upload format', async () => {
    const mask = new Uint8Array([0, 1, 1, 0, 0, 0]);
    await segmentationAPI.storeAiDraftOriginal('seg-9', mask, { depth: 1, height: 2, width: 3 });
    const [url, buffer] = put.mock.calls[0] as [string, ArrayBuffer];
    expect(url).toMatch(/\/segmentation\/seg-9\/ai-draft\/original$/);
    const view = new DataView(buffer);
    expect([view.getUint32(0, true), view.getUint32(4, true), view.getUint32(8, true)]).toEqual([1, 2, 3]);
    expect(Array.from(new Uint8Array(buffer, 12))).toEqual([0, 1, 1, 0, 0, 0]);
  });
});

describe('RC-132 reading before the AI draft (reader study)', () => {
  it('rc132 on an image of the study set the AI is held back until the reader recorded a reading', async () => {
    readerStudyAssignment.mockResolvedValue(assignment());
    withQuery(<ReaderStudyGate fileId="f-1"><p>AI card</p></ReaderStudyGate>);
    expect(await screen.findByTestId('reader-study-gate')).toBeInTheDocument();
    expect(screen.queryByText('AI card')).toBeNull();
  });

  it('rc132 once the reading is recorded, or outside the set, the AI is offered', async () => {
    readerStudyAssignment.mockResolvedValue(assignment({ reading_recorded: true, reading_segmentation_ids: ['s-1'] }));
    const first = withQuery(<ReaderStudyGate fileId="f-1"><p>AI card</p></ReaderStudyGate>);
    expect(await screen.findByText('AI card')).toBeInTheDocument();
    first.unmount();
    readerStudyAssignment.mockResolvedValue(assignment({ study_on: false, unaided_first: false }));
    withQuery(<ReaderStudyGate fileId="f-2"><p>AI card</p></ReaderStudyGate>);
    expect(await screen.findByText('AI card')).toBeInTheDocument();
  });

  it('rc132 if the study state cannot be read, the AI is held back with a retry', async () => {
    readerStudyAssignment.mockRejectedValueOnce(new Error('network'));
    readerStudyAssignment.mockRejectedValueOnce(new Error('network'));          // the one automatic retry too
    readerStudyAssignment.mockResolvedValueOnce(assignment({ study_on: false, unaided_first: false }));
    withQuery(<ReaderStudyGate fileId="f-1"><p>AI card</p></ReaderStudyGate>);
    expect(await screen.findByTestId('reader-study-unknown', {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByText('AI card')).toBeNull();
    fireEvent.click(screen.getByRole('button'));
    expect(await screen.findByText('AI card')).toBeInTheDocument();
  });

  it('rc132 recording the reading sends the digest of the saved mask on screen', async () => {
    readerStudyAssignment.mockResolvedValue(assignment());
    recordUnaidedReading.mockResolvedValue({ segmentation_id: 's-1', at: '2026-11-18T10:00:00Z' });
    withQuery(<UnaidedReadingCard fileId="f-1" segmentationId="s-1" recordable />);
    fireEvent.click(await screen.findByRole('button'));
    await waitFor(() => expect(recordUnaidedReading).toHaveBeenCalledWith('s-1', DIGEST));
  });

  it('rc132 nothing to record outside the set or on a segmentation that cannot be a reading', async () => {
    readerStudyAssignment.mockResolvedValue(assignment({ study_on: false, unaided_first: false }));
    const first = withQuery(<UnaidedReadingCard fileId="f-1" segmentationId="s-1" recordable />);
    await waitFor(() => expect(readerStudyAssignment).toHaveBeenCalled());
    expect(screen.queryByTestId('unaided-reading-card')).toBeNull();
    first.unmount();
    readerStudyAssignment.mockResolvedValue(assignment());
    withQuery(<UnaidedReadingCard fileId="f-3" segmentationId="s-1" recordable={false} />);
    await waitFor(() => expect(readerStudyAssignment).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId('unaided-reading-card')).toBeNull();
  });
});
