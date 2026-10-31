/**
 * Release 2026-10-30 — merge of #69 and #71, viewer side of the drawn-label check (R2).
 *
 * A segmentation classified before #71 stores red / green / blue / gold; opened through the store's real path
 * (`setActiveSegmentation`, #71's `withRegionColors`) it is DRAWN in the shared region colours. With the DIS state
 * serving the stored table as drawn (the merged server), the confirmation goes ahead and states the table drawn; with
 * a table in colours the viewer does not draw, it is refused.
 *
 * Contract test of the merged tree (the viewer code is unchanged by the integration decision; the server side is
 * test_release_2026_10_30_merge.py).
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
import { regionHex } from '@/utils/regionColors';

const DIGEST = 'ab'.repeat(32);
const STORED_BEFORE_71 = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
  { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true },
  { id: 2, name: 'Juxtacortical', color: '#00CC00', opacity: 0.6, visible: true },
  { id: 3, name: 'Infratentorial', color: '#0066FF', opacity: 0.6, visible: true },
  { id: 4, name: 'Deep White Matter', color: '#FFD700', opacity: 0.6, visible: true },
];
const AS_DRAWN = STORED_BEFORE_71.filter((l) => l.id !== 0)
  .map(({ id, name }) => ({ id, name, color: regionHex(name)!.toUpperCase() }));
const AS_STORED = STORED_BEFORE_71.filter((l) => l.id !== 0).map(({ id, name, color }) => ({ id, name, color }));
const ANALYSIS = {
  segmentation_id: 'seg-1',
  lesions: [{ id: 1, label_id: 1, region: 'Periventricular', voxel_count: 12, volume_mm3: 36, volume_ml: 0.036,
    size_category: 'small', centroid: { z: 3, y: 3, x: 3 }, bounding_box: {} }],
  total_count: 1, total_burden_mm3: 36, total_burden_ml: 0.036,
  regions: { Periventricular: { lesion_count: 1, total_volume_mm3: 36, total_volume_ml: 0.036 } },
  size_distribution: { small: 1, medium: 0, large: 0 }, unique_labels: [1],
};
const notConfirmed = (storedLabels: unknown) => ({
  segmentation_id: 'seg-1', evaluation_status: 'not_evaluated', not_evaluated_reason: 'segmentation_not_confirmed',
  message: 'Not evaluated: requires clinician review of the segmentation.', dis_criteria_version: 'McDonald 2024',
  segmentation_review: { status: 'unconfirmed', source: 'origin_not_recorded', reviewed_by: null, reviewed_at: null,
    reviewed_mask_sha256: null, current_mask_sha256: DIGEST },
  regions: { classified: true, label_scheme: 'magnims', removed_small_components: null, stored_labels: storedLabels },
});

function openClassifiedBefore71() {
  const store = useSegmentationStore.getState();
  store.setCurrentSegmentation({
    segmentation_id: 'seg-1', file_id: 'f.nii.gz', total_slices: 10,
    metadata: { file_id: 'f.nii.gz', created_at: 'T0', modified_at: 'T1', labels: STORED_BEFORE_71,
      analysis_data: { lesion_analysis: ANALYSIS } },
  } as never);
  store.setActiveSegmentation({ id: 'seg-1', labels: STORED_BEFORE_71 } as never);   // #71: drawn in region colours
  useSegmentationStore.setState({
    isOverlayVisible: true, lesionOpacity: 0.6, hasUnsavedMaskChanges: false, overlayOnScreen: 'seg-1',
    overlayImageOnScreen: { segmentationId: 'seg-1', imageFileId: 'f.nii.gz', image: { width: 20, height: 20, depth: 10 }, mask: { width: 20, height: 20, depth: 10 } },   // next safety round, PRB-030: over an image on the mask grid
    maskDigestCallback: vi.fn().mockResolvedValue(DIGEST), maskValuesCallback: vi.fn(() => [1, 2, 3, 4]),
    reloadMaskCallback: vi.fn(async () => true),
  } as never);
}

beforeEach(() => {
  for (const f of [getDISAssessment, analyzeLesions, confirmSegmentationReview]) f.mockReset();
  analyzeLesions.mockResolvedValue(ANALYSIS);
  confirmSegmentationReview.mockResolvedValue({ reviewed_by: 'dr_rev', reviewed_at: 'x', reviewed_mask_sha256: DIGEST });
  vi.restoreAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('merge of #69 and #71: a segmentation classified before #71', () => {
  it('rc071 release 1030 is drawn in the region colours and confirmed against the table as drawn', async () => {
    openClassifiedBefore71();
    const drawn = useSegmentationStore.getState().activeSegmentation!.labels;
    expect(drawn.filter((l) => l.id !== 0).map(({ id, name, color }) => ({ id, name, color: color.toUpperCase() })))
      .toEqual(AS_DRAWN);
    getDISAssessment.mockResolvedValue(notConfirmed(AS_DRAWN));
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(await screen.findByRole('button', { name: /confirm this segmentation/ }));
    await waitFor(() => expect(confirmSegmentationReview).toHaveBeenCalledWith('seg-1', DIGEST, null, drawn,
      { geometricRegionsReviewedSha256: null, displayedImageFileId: 'f.nii.gz' }));
    expect(screen.queryByTestId('dis-confirm-refused')).not.toBeInTheDocument();
  });

  it('rc071 release 1030 a table in colours the viewer does not draw is refused', async () => {
    openClassifiedBefore71();
    getDISAssessment.mockResolvedValue(notConfirmed(AS_STORED));
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(await screen.findByRole('button', { name: /confirm this segmentation/ }));
    expect(await screen.findByTestId('dis-confirm-refused')).toHaveTextContent(/value 1 is drawn as "Periventricular"/);
    expect(confirmSegmentationReview).not.toHaveBeenCalled();
  });
});
