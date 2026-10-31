/**
 * PRB-029 — the AI-draft review confirmation (AiDraftBanner, RC-047) had no drawn-lesion check.
 *
 * The AI report stays on in production (owner decision), and the AI draft's review is the first of the two
 * confirmations a radiologist gives. The DIS confirmation is refused unless every lesion is drawn on screen; the AI
 * draft's review was accepted whatever the view showed (segmentation mode off, the 3D view, the overlay off, a label
 * hidden, another label preset). It now runs the SAME check, from the same shared code: the standard 2D view (one
 * panel) in segmentation mode drawing this segmentation, every value of the mask drawn with the label stored on the
 * server (read when Confirm is pressed), visible, not too faint, overlay on, lesion opacity above the minimum — and
 * the checks of PRB-030 (image under the mask on its grid) and PRB-031 (no underlay above 30 %). The request carries
 * the drawn label table and the image under the mask, which the server checks.
 *
 * Written before the correction (fails on ca600c2).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const confirmAiReview = vi.fn();
const getSegmentation = vi.fn();
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    confirmAiReview: (...a: unknown[]) => confirmAiReview(...a),
    getSegmentation: (...a: unknown[]) => getSegmentation(...a),
  },
}));

import { AiDraftBanner } from './AiDraftBanner';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type { AIProvenance } from '@/types';

const DIGEST = 'ab'.repeat(32);
const UNREVIEWED: AIProvenance = {
  kind: 'ai_draft', model_name: 'FLAMeS', model_version: 'Zenodo 10.5281/zenodo.17955359 v2.0 (Dataset004_WML)',
  model_sha256: '2a10bb9d72dc33381a3f44dd6a59ec612dfd87534e02f15488b426ae127176ae', fold: 0,
  source_checkpoint_sha256: '4fc7db24e7c1541b59023df2a2f498a964eb629fe38f4eaec763297dd3fdf861',
  pipeline_version: 'mstool-flames-browser/0.2.0-prototype', runtime: 'onnxruntime-web 1.24.1 wasm x1',
  generated_at: '2026-10-17T20:00:00.000Z', lesion_count: 1, annotated_voxels: 2, review_status: 'unreviewed',
  reviewed_by: null, reviewed_at: null, reviewed_mask_sha256: null, sequence_evidence: 'clinician',
};
const LABELS = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
  { id: 1, name: 'Lesion', color: '#FF8C00', opacity: 0.6, visible: true },
];
const GRID = { width: 182, height: 218, depth: 182 };

/** The AI draft "seg-1" is open and drawn with its stored labels in the standard 2D view, over its own image. */
function seedOpen(over: Record<string, unknown> = {}) {
  useSegmentationStore.setState({
    activeSegmentation: { id: 'seg-1', labels: LABELS } as never,
    labelVisibility: { 0: false, 1: true },
    isOverlayVisible: true,
    lesionOpacity: 0.6,
    maskDigestCallback: vi.fn().mockResolvedValue(DIGEST),
    maskValuesCallback: vi.fn(() => [1]),
    overlayOnScreen: 'seg-1',
    overlayImageOnScreen: { segmentationId: 'seg-1', imageFileId: 'f.nii.gz', image: GRID, mask: GRID },
    zoneMapVisible: false, zoneMapOpacity: 0.3, longitudinalVisible: false, longitudinalSubtractionVisible: false,
    conformalVisible: false,
    ...over,
  } as never);
}

async function pressConfirm() {
  render(<AiDraftBanner provenance={UNREVIEWED} segmentationId="seg-1" hasUnsavedChanges={false} />);
  fireEvent.click(screen.getByRole('button', { name: /I have reviewed this AI draft/ }));
}

const refusal = () => screen.findByTestId('ai-draft-confirm-refused');

beforeEach(() => {
  confirmAiReview.mockReset();
  getSegmentation.mockReset();
  getSegmentation.mockResolvedValue({ segmentation_id: 'seg-1', metadata: { labels: LABELS } });
  confirmAiReview.mockResolvedValue({ ...UNREVIEWED, review_status: 'confirmed', reviewed_by: 'dr_rev' });
  vi.restoreAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('PRB-029: the AI-draft review is confirmed only while every lesion is drawn on screen', () => {
  it.each([
    ['segmentation mode off, NiiVue, matplotlib, multi-panel or 3D (nothing published)', { overlayOnScreen: null }, /Switch to the Standard view/],
    ['the overlay is switched off', { isOverlayVisible: false }, /overlay is switched off/],
    ['the lesion label is hidden with its eye toggle', { labelVisibility: { 0: false, 1: false } }, /"Lesion" \(value 1\) is hidden/],
    ['the lesion opacity is below the visible minimum', { lesionOpacity: 0.1 }, /below the visible minimum/],
    ['a mask value has no label', { maskValuesCallback: vi.fn(() => [1, 7]) }, /value 7 has no label/],
    ['the label is drawn in another colour than the stored one',
      { activeSegmentation: { id: 'seg-1', labels: [LABELS[0], { ...LABELS[1], color: '#00FF00' }] } }, /value 1 is drawn as "Lesion" \(#00FF00\)/],
  ])('rc091 prb029 refused: %s', async (_name, over, text) => {
    seedOpen(over);
    await pressConfirm();
    expect(await refusal()).toHaveTextContent(text);
    expect(window.confirm).not.toHaveBeenCalled();
    expect(confirmAiReview).not.toHaveBeenCalled();
  });

  it('rc091 prb029 refused when the labels stored on the server cannot be read', async () => {
    getSegmentation.mockRejectedValue(new Error('network'));
    seedOpen();
    await pressConfirm();
    expect(await refusal()).toHaveTextContent(/could not be read/);
    expect(confirmAiReview).not.toHaveBeenCalled();
  });

  it('rc091 prb029 refused while the mask is drawn over an image of another grid (PRB-030)', async () => {
    seedOpen({ overlayImageOnScreen: { segmentationId: 'seg-1', imageFileId: 'orig.nii.gz',
      image: { width: 256, height: 256, depth: 182 }, mask: GRID } });
    await pressConfirm();
    expect(await refusal()).toHaveTextContent(/grid/);
    expect(confirmAiReview).not.toHaveBeenCalled();
  });

  it('rc091 prb029 refused while the zone map is drawn above 30 % (PRB-031)', async () => {
    seedOpen({ zoneMapVisible: true, zoneMapOpacity: 0.9, zoneMapMask: new Uint8Array(8),
      zoneMapDims: { width: 2, height: 2, depth: 2 } });
    await pressConfirm();
    expect(await refusal()).toHaveTextContent(/zone map .*90 %/);
    expect(confirmAiReview).not.toHaveBeenCalled();
  });

  it('rc091 prb029 drawn on screen with the stored labels: confirmed with the drawn table and the image under the mask', async () => {
    const onConfirmed = vi.fn();
    seedOpen();
    render(<AiDraftBanner provenance={UNREVIEWED} segmentationId="seg-1" hasUnsavedChanges={false} onConfirmed={onConfirmed} />);
    fireEvent.click(screen.getByRole('button', { name: /I have reviewed this AI draft/ }));
    await waitFor(() => expect(onConfirmed).toHaveBeenCalled());
    expect(confirmAiReview).toHaveBeenCalledWith('seg-1', DIGEST, expect.objectContaining({
      displayedImageFileId: 'f.nii.gz', drawnLabels: LABELS }));
    expect(getSegmentation).toHaveBeenCalledWith('seg-1');
    expect(screen.queryByTestId('ai-draft-confirm-refused')).not.toBeInTheDocument();
  });
});
