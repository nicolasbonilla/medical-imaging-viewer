/**
 * Independent review of PR #74 (290e407), m1 — "Colorize by zone" is a drawing mode the shared confirmation check did
 * not see. Showing the zone map switches it on (and the palette button can switch it on alone). With it on the 2D
 * overlay keeps only the values 1-4 on a slice that has any (a value 5 "Active (Gd+)" or 6 is not drawn), draws other
 * slices' lesions only inside a zone, and paints 1-4 in the region palette whatever the stored label. So an AI draft
 * ("Lesion", value 1) is drawn periventricular orange, and a value-5 lesion can vanish — and Confirm was accepted.
 *
 * Now both confirmations are refused while zone colouring is drawn, unless every value present is a MAGNIMS region id
 * (1-4) drawn with that region's label — the one case where zone colouring draws exactly the stored labels (a
 * classified segmentation for the DIS confirmation: positive control).
 *
 * Written before the correction (the refusals fail on 290e407).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const confirmAiReview = vi.fn();
const getSegmentation = vi.fn();
const getDISAssessment = vi.fn();
const confirmSegmentationReview = vi.fn();
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    confirmAiReview: (...a: unknown[]) => confirmAiReview(...a),
    getSegmentation: (...a: unknown[]) => getSegmentation(...a),
    getDISAssessment: (...a: unknown[]) => getDISAssessment(...a),
    confirmSegmentationReview: (...a: unknown[]) => confirmSegmentationReview(...a),
    analyzeLesions: vi.fn(),
    classifyRegions: vi.fn(),
    annotateLesions: vi.fn(),
  },
}));
vi.mock('sonner', () => ({ toast: { loading: vi.fn(), success: vi.fn(), error: vi.fn() } }));

import { AiDraftBanner } from './AiDraftBanner';
import { LesionDashboard } from './LesionDashboard';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { MAGNIMS_LESION_LABELS } from '@/types/segmentation';
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
const LESION = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
  { id: 1, name: 'Lesion', color: '#FF8C00', opacity: 0.6, visible: true },
];
const GRID = { width: 4, height: 4, depth: 2 };
const ZONES = new Uint8Array(4 * 4 * 2).fill(1);

/** Segmentation "seg-1" drawn on screen with `labels`, the zone map shown at 30 % with zone colouring `colorize`. */
function seed(labels: typeof LESION, values: number[], colorize: boolean) {
  useSegmentationStore.setState({
    activeSegmentation: { id: 'seg-1', labels } as never,
    labelVisibility: Object.fromEntries(labels.map((l) => [l.id, l.id !== 0])),
    isOverlayVisible: true, lesionOpacity: 0.6,
    maskDigestCallback: vi.fn().mockResolvedValue(DIGEST), maskValuesCallback: vi.fn(() => values),
    hasUnsavedMaskChanges: false, overlayOnScreen: 'seg-1',
    overlayImageOnScreen: { segmentationId: 'seg-1', imageFileId: 'f.nii.gz', image: GRID, mask: GRID },
    zoneMapVisible: true, zoneMapOpacity: 0.3, zoneMapMask: ZONES, zoneMapDims: GRID, zoneColorizeEnabled: colorize,
    longitudinalVisible: false, longitudinalSubtractionVisible: false, conformalVisible: false,
  } as never);
}

async function pressAiConfirm(labels: typeof LESION) {
  getSegmentation.mockResolvedValue({ segmentation_id: 'seg-1', metadata: { labels } });
  render(<AiDraftBanner provenance={UNREVIEWED} segmentationId="seg-1" hasUnsavedChanges={false} />);
  fireEvent.click(screen.getByRole('button', { name: /I have reviewed this AI draft/ }));
}

beforeEach(() => {
  for (const f of [confirmAiReview, getSegmentation, getDISAssessment, confirmSegmentationReview]) f.mockReset();
  confirmAiReview.mockResolvedValue({ ...UNREVIEWED, review_status: 'confirmed', reviewed_by: 'dr_rev' });
  confirmSegmentationReview.mockResolvedValue({ reviewed_by: 'dr_rev', reviewed_at: 'x', reviewed_mask_sha256: DIGEST });
  vi.restoreAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('review m1: zone colouring draws the lesions in other colours (or not at all)', () => {
  it('rc091 review m1 an AI draft ("Lesion", value 1) drawn in zone colours is refused', async () => {
    seed(LESION, [1], true);
    await pressAiConfirm(LESION);
    expect(await screen.findByTestId('ai-draft-confirm-refused')).toHaveTextContent(/coloured by MAGNIMS zone/);
    expect(confirmAiReview).not.toHaveBeenCalled();
  });

  it('rc091 review m1 a value-5 (Active Gd+) lesion, which zone colouring does not draw, is refused', async () => {
    seed(MAGNIMS_LESION_LABELS as never, [1, 5], true);
    await pressAiConfirm(MAGNIMS_LESION_LABELS as never);
    expect(await screen.findByTestId('ai-draft-confirm-refused')).toHaveTextContent(/coloured by MAGNIMS zone/);
    expect(confirmAiReview).not.toHaveBeenCalled();
  });

  it('rc091 review m1 the same draft with zone colouring off is confirmed (positive control)', async () => {
    seed(LESION, [1], false);
    await pressAiConfirm(LESION);
    await waitFor(() => expect(confirmAiReview).toHaveBeenCalled());
  });

  it('rc093 review m1 a classified segmentation (regions 1-4 with their region labels) in zone colours is confirmed (positive control)', async () => {
    seed(MAGNIMS_LESION_LABELS as never, [1, 2, 3, 4], true);
    const stored = MAGNIMS_LESION_LABELS.filter((l) => l.id !== 0).map(({ id, name, color }) => ({ id, name, color }));
    useSegmentationStore.setState({
      currentSegmentation: { segmentation_id: 'seg-1', file_id: 'f.nii.gz', total_slices: 2,
        metadata: { file_id: 'f.nii.gz', created_at: 'T0', modified_at: 'T1', labels: MAGNIMS_LESION_LABELS,
          analysis_data: { lesion_analysis: { segmentation_id: 'seg-1', lesions: [], total_count: 0, total_burden_mm3: 0,
            total_burden_ml: 0, regions: {}, size_distribution: { small: 0, medium: 0, large: 0 }, unique_labels: [] } } } },
      reloadMaskCallback: vi.fn(async () => true),
    } as never);
    getDISAssessment.mockResolvedValue({
      segmentation_id: 'seg-1', evaluation_status: 'not_evaluated', not_evaluated_reason: 'segmentation_not_confirmed',
      message: 'Not evaluated', dis_criteria_version: 'McDonald 2024',
      segmentation_review: { status: 'unconfirmed', source: 'origin_not_recorded', reviewed_by: null, reviewed_at: null,
        reviewed_mask_sha256: null, current_mask_sha256: DIGEST },
      regions: { classified: true, label_scheme: 'magnims', method: 'msmask', geometric_region_count: 0,
        geometric_regions: [], removed_small_components: null, stored_labels: stored },
    });
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(await screen.findByRole('button', { name: /confirm this segmentation/ }));
    await waitFor(() => expect(confirmSegmentationReview).toHaveBeenCalled());
    expect(screen.queryByTestId('dis-confirm-refused')).not.toBeInTheDocument();
  });
});
