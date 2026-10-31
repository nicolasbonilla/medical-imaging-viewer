/**
 * AiDraftBanner — the clinician's review confirmation is bound to the exact saved mask (REQ-SAFE-030, RC-047).
 *
 *  - while the open mask has unsaved corrections there is NO confirm button (save first);
 *  - the confirmation sends the SHA-256 of the mask on screen; the server refuses it (409) unless it is the
 *    stored mask, and resets the review whenever the mask changes later;
 *  - a confirmed review names the mask it was given for.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const confirmAiReview = vi.fn();
// Next safety round (PRB-029): the banner reads the stored label table before it confirms.
const LABELS = [{ id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
                { id: 1, name: 'Lesion', color: '#FF8C00', opacity: 0.6, visible: true }];
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    confirmAiReview: (...a: unknown[]) => confirmAiReview(...a),
    getSegmentation: async () => ({ segmentation_id: 'seg-1', metadata: { labels: LABELS } }),
  },
}));

import { AiDraftBanner } from './AiDraftBanner';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type { AIProvenance } from '@/types';

const DIGEST = 'ab'.repeat(32);
const UNREVIEWED: AIProvenance = {
  kind: 'ai_draft',
  model_name: 'FLAMeS',
  model_version: 'Zenodo 10.5281/zenodo.17955359 v2.0 (Dataset004_WML)',
  model_sha256: '2a10bb9d72dc33381a3f44dd6a59ec612dfd87534e02f15488b426ae127176ae',
  fold: 0,
  source_checkpoint_sha256: '4fc7db24e7c1541b59023df2a2f498a964eb629fe38f4eaec763297dd3fdf861',
  pipeline_version: 'mstool-flames-browser/0.2.0-prototype',
  runtime: 'onnxruntime-web 1.24.1 wasm x1',
  generated_at: '2026-10-17T20:00:00.000Z',
  lesion_count: 1,
  annotated_voxels: 2,
  review_status: 'unreviewed',
  reviewed_by: null,
  reviewed_at: null,
  reviewed_mask_sha256: null,
  sequence_evidence: 'clinician',
};
const CONFIRMED: AIProvenance = {
  ...UNREVIEWED,
  review_status: 'confirmed',
  reviewed_by: 'dr_rev',
  reviewed_at: '2026-10-18T09:00:00Z',
  reviewed_mask_sha256: DIGEST,
};

beforeEach(() => {
  confirmAiReview.mockReset();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  useSegmentationStore.setState({ maskDigestCallback: vi.fn().mockResolvedValue(DIGEST) });
  // Next safety round (PRB-029..031): the draft is drawn with its stored labels in the standard 2D view, over its own
  // image, with no layer under the lesions — the shared check of the view on screen passes.
  const grid = { width: 5, height: 4, depth: 3 };
  useSegmentationStore.setState({
    activeSegmentation: { id: 'seg-1', labels: LABELS } as never, labelVisibility: { 0: false, 1: true },
    isOverlayVisible: true, lesionOpacity: 0.6, maskValuesCallback: vi.fn(() => [1]), overlayOnScreen: 'seg-1',
    overlayImageOnScreen: { segmentationId: 'seg-1', imageFileId: 'f.nii.gz', image: grid, mask: grid },
    zoneMapVisible: false, longitudinalVisible: false, longitudinalSubtractionVisible: false, conformalVisible: false,
  } as never);
});

describe('AI review confirmation bound to the saved mask (RC-047)', () => {
  it('rc047 with unsaved corrections there is no confirm button — only "save first"', () => {
    render(<AiDraftBanner provenance={UNREVIEWED} segmentationId="seg-1" hasUnsavedChanges />);
    expect(screen.queryByRole('button', { name: /I have reviewed this AI draft/ })).not.toBeInTheDocument();
    expect(screen.getByTestId('ai-draft-save-first')).toHaveTextContent(/save them first/);
    expect(confirmAiReview).not.toHaveBeenCalled();
  });

  it('rc047 on the saved mask the confirmation sends the SHA-256 of the mask on screen', async () => {
    const onConfirmed = vi.fn();
    confirmAiReview.mockResolvedValue(CONFIRMED);
    render(<AiDraftBanner provenance={UNREVIEWED} segmentationId="seg-1" hasUnsavedChanges={false} onConfirmed={onConfirmed} />);
    fireEvent.click(screen.getByRole('button', { name: /I have reviewed this AI draft/ }));
    await waitFor(() => expect(onConfirmed).toHaveBeenCalledWith(CONFIRMED));
    expect(confirmAiReview).toHaveBeenCalledWith('seg-1', DIGEST,
      { drawnLabels: LABELS, displayedImageFileId: 'f.nii.gz' });   // PRB-029 / PRB-030: what was drawn, over which image
    expect(window.confirm).toHaveBeenCalledWith(expect.stringMatching(/any later change of the mask cancels/));
  });

  it('rc047 if the open mask cannot be hashed nothing is sent', async () => {
    useSegmentationStore.setState({ maskDigestCallback: vi.fn().mockResolvedValue(null) });
    render(<AiDraftBanner provenance={UNREVIEWED} segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: /I have reviewed this AI draft/ }));
    expect(await screen.findByText(/could not be read/)).toBeInTheDocument();
    expect(confirmAiReview).not.toHaveBeenCalled();
  });

  it('rc047 a server refusal (mask changed since it was saved) is shown and nothing is confirmed', async () => {
    const onConfirmed = vi.fn();
    confirmAiReview.mockRejectedValue(new Error('The mask on screen is not the saved mask'));
    render(<AiDraftBanner provenance={UNREVIEWED} segmentationId="seg-1" onConfirmed={onConfirmed} />);
    fireEvent.click(screen.getByRole('button', { name: /I have reviewed this AI draft/ }));
    expect(await screen.findByText(/not the saved mask/)).toBeInTheDocument();
    expect(onConfirmed).not.toHaveBeenCalled();
  });

  it('rc047 a confirmed review names the saved mask it covers and warns that saving changes cancels it', () => {
    const { rerender } = render(<AiDraftBanner provenance={CONFIRMED} segmentationId="seg-1" />);
    expect(screen.getByText(/review confirmed by dr_rev/)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`Confirmed for the saved mask ${DIGEST.slice(0, 12)}`))).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    rerender(<AiDraftBanner provenance={CONFIRMED} segmentationId="seg-1" hasUnsavedChanges />);
    expect(screen.getByText(/saving your changes will cancel this confirmation/)).toBeInTheDocument();
  });
});
