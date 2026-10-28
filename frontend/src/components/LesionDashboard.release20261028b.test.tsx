/**
 * Release 2026-10-25 — independent review of PR #69 (6d1fde2..dd22708): B1 (blocker) and M3 (major), the confirmation
 * side.
 *
 *  - B1 (1): after the region classification the sidebar list caches (['segmentations', ...]) are refreshed, so no
 *    later open can seed the drawn labels from the list fetched before the classification.
 *  - B1 (4) / M3: a radiologist can never confirm a mask with lesions that are not drawn. Confirm refuses, with a clear
 *    message and without asking the server, while any value present in the open mask has no entry in the label table,
 *    is hidden (eye toggle), is too faint, while the overlay is switched off, or while the lesion opacity is below a
 *    visible minimum; and when the open mask cannot be read.
 *
 * Written before the correction (fails on dd22708; the "everything drawn" case is a positive control).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getDISAssessment = vi.fn();
const analyzeLesions = vi.fn();
const confirmSegmentationReview = vi.fn();
const getSegmentation = vi.fn();
const classifyRegions = vi.fn();
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    getDISAssessment: (...a: unknown[]) => getDISAssessment(...a),
    analyzeLesions: (...a: unknown[]) => analyzeLesions(...a),
    confirmSegmentationReview: (...a: unknown[]) => confirmSegmentationReview(...a),
    getSegmentation: (...a: unknown[]) => getSegmentation(...a),
    classifyRegions: (...a: unknown[]) => classifyRegions(...a),
    annotateLesions: vi.fn(),
    confirmAiReview: vi.fn(),
  },
}));
vi.mock('sonner', () => ({ toast: { loading: vi.fn(), success: vi.fn(), error: vi.fn() } }));

import { LesionDashboard } from './LesionDashboard';
import { useSegmentationStore } from '@/store/useSegmentationStore';

const DIGEST = 'ab'.repeat(32);
const ANALYSIS = {
  segmentation_id: 'seg-1',
  lesions: [{ id: 1, label_id: 1, region: 'Periventricular', voxel_count: 12, volume_mm3: 36, volume_ml: 0.036,
    size_category: 'small', centroid: { z: 3, y: 3, x: 3 }, bounding_box: {} }],
  total_count: 1, total_burden_mm3: 36, total_burden_ml: 0.036,
  regions: { Periventricular: { lesion_count: 1, total_volume_mm3: 36, total_volume_ml: 0.036 } },
  size_distribution: { small: 1, medium: 0, large: 0 }, unique_labels: [1],
};
const NOT_CONFIRMED = {
  segmentation_id: 'seg-1', evaluation_status: 'not_evaluated', not_evaluated_reason: 'segmentation_not_confirmed',
  message: 'Not evaluated: requires clinician review of the segmentation.', dis_criteria_version: 'McDonald 2024',
  segmentation_review: { status: 'unconfirmed', source: 'origin_not_recorded', reviewed_by: null, reviewed_at: null,
    reviewed_mask_sha256: null, current_mask_sha256: DIGEST },
  regions: { classified: true, label_scheme: 'magnims' },
};
const MAGNIMS = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0.0, visible: false },
  { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true },
  { id: 2, name: 'Juxtacortical', color: '#00CC00', opacity: 0.6, visible: true },
  { id: 3, name: 'Infratentorial', color: '#0066FF', opacity: 0.6, visible: true },
  { id: 4, name: 'Deep White Matter', color: '#FFD700', opacity: 0.6, visible: true },
];
const CLASSIFICATION = {
  segmentation_id: 'seg-1', method: 'geometric', lesions: [], total_classified: 1, classification_summary: {},
  thresholds_mm: {}, processing_time_ms: 5, mask_updated: true, labels_updated: true, labels: MAGNIMS,
  removed_small_components: { components: 0, voxels: 0, volume_mm3: 0, min_lesion_volume_mm3: 3, reason: '' },
};

function seed(over: Record<string, unknown> = {}, labels = MAGNIMS) {
  useSegmentationStore.setState({
    currentSegmentation: {
      segmentation_id: 'seg-1', file_id: 'f.nii.gz', total_slices: 10,
      metadata: { file_id: 'f.nii.gz', created_at: 'T0', modified_at: 'T1', labels,
        analysis_data: { lesion_analysis: ANALYSIS, classification: CLASSIFICATION } },
    } as any,
    activeSegmentation: {
      id: 'seg-1', patient_id: '', study_id: '', series_id: '', file_id: 'f.nii.gz', name: 'S',
      segmentation_type: 'manual', status: 'in_progress', progress_percentage: 0, slices_annotated: 0,
      total_slices: 10, created_by: 'u', created_at: 'T0', modified_at: 'T1', labels,
    } as any,
    labelVisibility: Object.fromEntries(labels.map((l) => [l.id, l.visible])),
    isOverlayVisible: true,
    lesionOpacity: 0.6,
    isDirty: false,
    maskDigestCallback: vi.fn().mockResolvedValue(DIGEST),
    maskValuesCallback: vi.fn(() => [1, 2, 3, 4]),
    hasUnsavedMaskChanges: false,
    ...over,
  } as never);
}

async function clickConfirm() {
  fireEvent.click(await screen.findByRole('button', { name: /confirm this segmentation/ }));
}

beforeEach(() => {
  for (const f of [getDISAssessment, analyzeLesions, confirmSegmentationReview, getSegmentation, classifyRegions]) f.mockReset();
  analyzeLesions.mockResolvedValue(ANALYSIS);
  getSegmentation.mockResolvedValue({ segmentation_id: 'seg-1', metadata: {} });
  getDISAssessment.mockResolvedValue(NOT_CONFIRMED);
  confirmSegmentationReview.mockResolvedValue({ reviewed_by: 'dr_rev', reviewed_at: 'x', reviewed_mask_sha256: DIGEST });
  vi.restoreAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('B1 (1): the sidebar list caches are refreshed after the classification', () => {
  it('rc070 release b1 the classification invalidates every segmentation list cache', async () => {
    seed();
    useSegmentationStore.setState({ reloadMaskCallback: vi.fn(async () => true) } as never);
    classifyRegions.mockResolvedValue(CLASSIFICATION);
    const qc = new QueryClient();
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    render(<QueryClientProvider client={qc}><LesionDashboard segmentationId="seg-1" /></QueryClientProvider>);
    fireEvent.click(screen.getByRole('button', { name: /Auto-Classify Regions/ }));
    await waitFor(() => expect(analyzeLesions).toHaveBeenCalled());
    const keys = invalidate.mock.calls.map((c) => (c[0] as { queryKey?: unknown[] })?.queryKey);
    expect(keys).toContainEqual(['segmentations']);          // prefix: the study list and the per-file lists
  });
});

describe('B1 (4) / M3: confirm refuses while any lesion of the mask is not drawn', () => {
  it('rc071 release m3 everything drawn: the confirmation goes ahead (positive control)', async () => {
    seed();
    render(<LesionDashboard segmentationId="seg-1" />);
    await clickConfirm();
    await waitFor(() => expect(confirmSegmentationReview).toHaveBeenCalledTimes(1));
  });

  const REFUSALS: Array<[string, Record<string, unknown>, RegExp, typeof MAGNIMS?]> = [
    ['a label switched off with its eye toggle', { labelVisibility: { 0: false, 1: true, 2: true, 3: false, 4: true } }, /Infratentorial.*hidden/],
    ['the overlay switched off', { isOverlayVisible: false }, /overlay is switched off/],
    ['the lesion opacity below the visible minimum', { lesionOpacity: 0.05 }, /opacity/],
    ['a mask value with no entry in the label table', {}, /value 3.*no label/i, MAGNIMS.filter((l) => l.id !== 3)],
    ['a mask that cannot be read', { maskValuesCallback: vi.fn(() => null) }, /could not be read/],
  ];
  it.each(REFUSALS)('rc071 release m3 refused: %s', async (_name, over, message, labels) => {
    seed(over, labels ?? MAGNIMS);
    render(<LesionDashboard segmentationId="seg-1" />);
    await clickConfirm();
    const refusal = await screen.findByTestId('dis-confirm-refused');
    expect(refusal).toHaveTextContent(/every lesion must be drawn/i);
    expect(refusal).toHaveTextContent(message);
    expect(window.confirm).not.toHaveBeenCalled();
    expect(confirmSegmentationReview).not.toHaveBeenCalled();
  });
});
