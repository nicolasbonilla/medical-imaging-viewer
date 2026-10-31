/**
 * PRB-030 (L1 of the last check of PR #69) — Confirm is refused while the mask is drawn over an image of another grid.
 *
 * The standard 2D view drew the open segmentation over whatever image was selected: another image of the study (the
 * original instead of the MNI-preprocessed one) has another grid, the mask was drawn sheared or cut off, and Confirm
 * was accepted. The view now publishes the image it draws under the mask with both grids (`overlayImageOnScreen`:
 * image columns / rows / slices, mask width / height / depth); the browser refuses Confirm unless they are the same,
 * and sends the image's id so the server checks its header (shape and affine, same study).
 *
 * Written before the correction (fails on ca600c2).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const getDISAssessment = vi.fn();
const analyzeLesions = vi.fn();
const confirmSegmentationReview = vi.fn();
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    getDISAssessment: (...a: unknown[]) => getDISAssessment(...a),
    analyzeLesions: (...a: unknown[]) => analyzeLesions(...a),
    confirmSegmentationReview: (...a: unknown[]) => confirmSegmentationReview(...a),
    getSegmentation: vi.fn(async () => ({ segmentation_id: 'seg-1', metadata: {} })),
    classifyRegions: vi.fn(),
    annotateLesions: vi.fn(),
    confirmAiReview: vi.fn(),
  },
}));
vi.mock('sonner', () => ({ toast: { loading: vi.fn(), success: vi.fn(), error: vi.fn() } }));

import { LesionDashboard } from './LesionDashboard';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { MAGNIMS_LESION_LABELS } from '@/types/segmentation';

const DIGEST = 'ab'.repeat(32);
const ANALYSIS = {
  segmentation_id: 'seg-1',
  lesions: [{ id: 1, label_id: 1, region: 'Periventricular', voxel_count: 12, volume_mm3: 36, volume_ml: 0.036,
    size_category: 'small', centroid: { z: 3, y: 3, x: 3 }, bounding_box: {} }],
  total_count: 1, total_burden_mm3: 36, total_burden_ml: 0.036,
  regions: { Periventricular: { lesion_count: 1, total_volume_mm3: 36, total_volume_ml: 0.036 } },
  size_distribution: { small: 1, medium: 0, large: 0 }, unique_labels: [1],
};
const STORED = MAGNIMS_LESION_LABELS.filter((l) => l.id !== 0).map(({ id, name, color }) => ({ id, name, color }));
const NOT_CONFIRMED = {
  segmentation_id: 'seg-1', evaluation_status: 'not_evaluated', not_evaluated_reason: 'segmentation_not_confirmed',
  message: 'Not evaluated: requires clinician review of the segmentation.', dis_criteria_version: 'McDonald 2024',
  segmentation_review: { status: 'unconfirmed', source: 'origin_not_recorded', reviewed_by: null, reviewed_at: null,
    reviewed_mask_sha256: null, current_mask_sha256: DIGEST },
  regions: { classified: true, label_scheme: 'magnims', method: 'msmask', removed_small_components: null,
    geometric_region_count: 0, geometric_regions: [], stored_labels: STORED },
};
const GRID = { width: 182, height: 218, depth: 182 };

function seedOpen(imageOnScreen: unknown) {
  useSegmentationStore.setState({
    currentSegmentation: {
      segmentation_id: 'seg-1', file_id: 'mni/flair.nii.gz', total_slices: 182,
      metadata: { file_id: 'mni/flair.nii.gz', created_at: 'T0', modified_at: 'T1', labels: MAGNIMS_LESION_LABELS,
        analysis_data: { lesion_analysis: ANALYSIS } },
    } as any,
    activeSegmentation: { id: 'seg-1', labels: MAGNIMS_LESION_LABELS } as any,
    labelVisibility: Object.fromEntries(MAGNIMS_LESION_LABELS.map((l) => [l.id, l.id !== 0])),
    isOverlayVisible: true,
    lesionOpacity: 0.6,
    maskDigestCallback: vi.fn().mockResolvedValue(DIGEST),
    maskValuesCallback: vi.fn(() => [1, 2, 3, 4]),
    hasUnsavedMaskChanges: false,
    reloadMaskCallback: vi.fn(async () => true),
    overlayOnScreen: 'seg-1',
    overlayImageOnScreen: imageOnScreen,
    zoneMapVisible: false, longitudinalVisible: false, longitudinalSubtractionVisible: false, conformalVisible: false,
  } as never);
}

async function pressConfirm() {
  render(<LesionDashboard segmentationId="seg-1" />);
  fireEvent.click(await screen.findByRole('button', { name: /confirm this segmentation/ }));
}

beforeEach(() => {
  for (const f of [getDISAssessment, analyzeLesions, confirmSegmentationReview]) f.mockReset();
  getDISAssessment.mockResolvedValue(NOT_CONFIRMED);
  analyzeLesions.mockResolvedValue(ANALYSIS);
  confirmSegmentationReview.mockResolvedValue({ reviewed_by: 'dr_rev', reviewed_at: 'x', reviewed_mask_sha256: DIGEST });
  vi.restoreAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('PRB-030: Confirm only while the image under the mask is on the mask grid', () => {
  it.each([
    ['the original image (another in-plane size) under the MNI mask', { width: 256, height: 256, depth: 182 }, /256 × 256 × 182.*182 × 218 × 182/],
    ['an image with fewer slices (the mask would be cut off)', { width: 182, height: 218, depth: 60 }, /182 × 218 × 60/],
    ['rows and columns swapped', { width: 218, height: 182, depth: 182 }, /218 × 182 × 182/],
  ])('rc092 prb030 refused: %s', async (_name, image, text) => {
    seedOpen({ segmentationId: 'seg-1', imageFileId: 'orig/flair.nii.gz', image, mask: GRID });
    await pressConfirm();
    const refusal = await screen.findByTestId('dis-confirm-refused');
    expect(refusal).toHaveTextContent(/grid/);
    expect(refusal).toHaveTextContent(text);
    expect(window.confirm).not.toHaveBeenCalled();
    expect(confirmSegmentationReview).not.toHaveBeenCalled();
  });

  it.each([
    ['nothing published about the image under the mask', null],
    ['the image published is under another segmentation', { segmentationId: 'seg-2', imageFileId: 'mni/flair.nii.gz', image: GRID, mask: GRID }],
    ['the mask grid is not known', { segmentationId: 'seg-1', imageFileId: 'mni/flair.nii.gz', image: GRID, mask: null }],
    ['the image has no id the server can check', { segmentationId: 'seg-1', imageFileId: null, image: GRID, mask: GRID }],
  ])('rc092 prb030 refused when it cannot be checked: %s', async (_name, onScreen) => {
    seedOpen(onScreen);
    await pressConfirm();
    expect(await screen.findByTestId('dis-confirm-refused')).toHaveTextContent(/image under the segmentation/);
    expect(confirmSegmentationReview).not.toHaveBeenCalled();
  });

  it('rc092 prb030 the image on the mask grid: confirmed, and the server is told which image it was', async () => {
    seedOpen({ segmentationId: 'seg-1', imageFileId: 'mni/t1.nii.gz', image: GRID, mask: GRID });
    await pressConfirm();
    await waitFor(() => expect(confirmSegmentationReview).toHaveBeenCalled());
    expect(confirmSegmentationReview.mock.calls[0][4]).toEqual(expect.objectContaining({ displayedImageFileId: 'mni/t1.nii.gz' }));
    expect(screen.queryByTestId('dis-confirm-refused')).not.toBeInTheDocument();
  });
});
