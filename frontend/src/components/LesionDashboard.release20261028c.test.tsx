/**
 * Release 2026-10-25 — second independent review of PR #69 (6d1fde2..dd22708), viewer side of M1, m1, m2, m4, m5, m7.
 *
 *  - M1: the F09 notice and the confirm dialog take the removal from the server's DIS state of THIS dashboard's
 *    segmentation; a dashboard never reads or writes the analysis data of another (open) segmentation.
 *  - m1: a failed mask reload after the classification is shown, and the confirmation is refused until a reload works.
 *  - m2: classification only on the open segmentation without unsaved changes (it reloads the open mask).
 *  - m4: "evaluated" in the viewer needs a yes/no conclusion too.
 *  - m5 / m7: when the confirmation was recorded but the DIS result could not be read, the card says so, never "No
 *    radiologist has confirmed", and offers no second confirmation; a refused confirmation never says "recorded".
 *
 * Written before the corrections (they fail on ebf39c3; the passing cases are positive controls).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

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
const METLIKE = /Criterion Met|Not Met/;
const ANALYSIS = {
  segmentation_id: 'seg-1',
  lesions: [{ id: 1, label_id: 1, region: 'Periventricular', voxel_count: 12, volume_mm3: 36, volume_ml: 0.036,
    size_category: 'small', centroid: { z: 3, y: 3, x: 3 }, bounding_box: {} }],
  total_count: 1, total_burden_mm3: 36, total_burden_ml: 0.036,
  regions: { Periventricular: { lesion_count: 1, total_volume_mm3: 36, total_volume_ml: 0.036 } },
  size_distribution: { small: 1, medium: 0, large: 0 }, unique_labels: [1],
};
const REMOVED = (n: number) => ({ components: n, voxels: n * 2, volume_mm3: n * 2, min_lesion_volume_mm3: 3,
  reason: 'below the minimum lesion size' });
const notConfirmed = (sid: string, removed: unknown = null) => ({
  segmentation_id: sid, evaluation_status: 'not_evaluated', not_evaluated_reason: 'segmentation_not_confirmed',
  message: 'Not evaluated: requires clinician review of the segmentation.', dis_criteria_version: 'McDonald 2024',
  segmentation_review: { status: 'unconfirmed', source: 'origin_not_recorded', reviewed_by: null, reviewed_at: null,
    reviewed_mask_sha256: null, current_mask_sha256: DIGEST },
  regions: { classified: true, label_scheme: 'magnims', removed_small_components: removed,
    stored_labels: [{ id: 1, name: 'Periventricular', color: '#FF0000' }, { id: 2, name: 'Juxtacortical', color: '#00CC00' },
    { id: 3, name: 'Infratentorial', color: '#0066FF' }, { id: 4, name: 'Deep White Matter', color: '#FFD700' }] },   // final check of #69 (R2): the stored label table
});
const MAGNIMS = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
  { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true },
  { id: 2, name: 'Juxtacortical', color: '#00CC00', opacity: 0.6, visible: true },
];
const CLASSIFICATION = {
  segmentation_id: 'seg-1', method: 'geometric', lesions: [], total_classified: 1, classification_summary: {},
  thresholds_mm: {}, processing_time_ms: 5, mask_updated: true, labels_updated: true, labels: MAGNIMS,
  removed_small_components: REMOVED(0),
};

/** Segmentation "seg-1" is open; its analysis data carries `analysis`. */
function seedOpen(analysis: Record<string, unknown> | null, over: Record<string, unknown> = {}) {
  useSegmentationStore.setState({
    currentSegmentation: {
      segmentation_id: 'seg-1', file_id: 'f.nii.gz', total_slices: 10,
      metadata: { file_id: 'f.nii.gz', created_at: 'T0', modified_at: 'T1', labels: MAGNIMS, analysis_data: analysis },
    } as any,
    activeSegmentation: { id: 'seg-1', labels: MAGNIMS } as any,
    labelVisibility: { 0: false, 1: true, 2: true },
    isOverlayVisible: true,
    lesionOpacity: 0.6,
    maskDigestCallback: vi.fn().mockResolvedValue(DIGEST),
    // Release 2026-10-25 (final check of #69, R1): the standard 2D view on screen draws the open segmentation.
    overlayOnScreen: 'seg-1',
    maskValuesCallback: vi.fn(() => [1, 2]),
    hasUnsavedMaskChanges: false,
    reloadMaskCallback: vi.fn(async () => true),
    ...over,
  } as never);
}

beforeEach(() => {
  for (const f of [getDISAssessment, analyzeLesions, confirmSegmentationReview, getSegmentation, classifyRegions]) f.mockReset();
  analyzeLesions.mockResolvedValue(ANALYSIS);
  getSegmentation.mockResolvedValue({ segmentation_id: 'seg-1', metadata: {} });
  getDISAssessment.mockImplementation(async (sid: string) => notConfirmed(sid));
  vi.restoreAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('M1: the removal notice belongs to the dashboard\'s own segmentation', () => {
  it('rc070 release2 m1 another segmentation\'s removal is never shown in this dashboard', async () => {
    // seg-1 is open and its classification removed 5 components; the dashboard shows seg-2 (expanded, not open)
    seedOpen({ lesion_analysis: ANALYSIS, classification: { ...CLASSIFICATION, removed_small_components: REMOVED(5) } });
    render(<LesionDashboard segmentationId="seg-2" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    await screen.findByTestId('dis-not-evaluated');
    expect(screen.queryByTestId('dis-removed-components')).not.toBeInTheDocument();
    expect(screen.queryByTestId('classification-removed-components')).not.toBeInTheDocument();
  });

  it('rc070 release2 m1 the notice and the confirm dialog take the removal from the server state of this segmentation', async () => {
    seedOpen({ lesion_analysis: ANALYSIS, classification: CLASSIFICATION });           // nothing stored locally
    getDISAssessment.mockImplementation(async (sid: string) => notConfirmed(sid, REMOVED(4)));
    render(<LesionDashboard segmentationId="seg-1" />);
    expect(await screen.findByTestId('dis-removed-components')).toHaveTextContent(/4 lesion component\(s\)/);
    fireEvent.click(await screen.findByRole('button', { name: /confirm this segmentation/ }));
    await waitFor(() => expect(window.confirm).toHaveBeenCalled());
    expect((window.confirm as unknown as { mock: { calls: string[][] } }).mock.calls[0][0]).toMatch(/4 lesion component\(s\)/);
  });

  it('rc070 release2 m1 a dashboard never writes its results into the open segmentation of another', async () => {
    const own = { lesion_analysis: { ...ANALYSIS, segmentation_id: 'seg-1' } };
    seedOpen(own);
    analyzeLesions.mockResolvedValue({ ...ANALYSIS, segmentation_id: 'seg-2', total_count: 9 });
    render(<LesionDashboard segmentationId="seg-2" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    await waitFor(() => expect(analyzeLesions).toHaveBeenCalledWith('seg-2'));
    await screen.findByTestId('dis-not-evaluated');
    expect(useSegmentationStore.getState().currentSegmentation?.metadata?.analysis_data).toEqual(own);
  });
});

describe('m2: the classification runs on the open, saved segmentation only', () => {
  it('rc070 release2 m2 not offered on a segmentation that is not open', async () => {
    seedOpen(null);
    render(<LesionDashboard segmentationId="seg-2" />);
    expect(screen.getByRole('button', { name: /Auto-Classify Regions/ })).toBeDisabled();
    expect(screen.getByTestId('classify-needs-open-saved')).toBeInTheDocument();
  });

  it('rc070 release2 m2 not offered while the open mask has unsaved changes', async () => {
    seedOpen(null, { hasUnsavedMaskChanges: true });
    render(<LesionDashboard segmentationId="seg-1" />);
    expect(screen.getByRole('button', { name: /Auto-Classify Regions/ })).toBeDisabled();
    expect(screen.getByTestId('classify-needs-open-saved')).toBeInTheDocument();
  });
});

describe('m1: a failed mask reload after the classification', () => {
  it('rc071 release2 m1 is shown, and the confirmation is refused until the mask is reloaded', async () => {
    seedOpen(null, { reloadMaskCallback: vi.fn(async () => false) });
    classifyRegions.mockResolvedValue(CLASSIFICATION);
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: /Auto-Classify Regions/ }));
    expect(await screen.findByText(/could not be reloaded/)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: /confirm this segmentation/ }));
    expect(await screen.findByTestId('dis-confirm-refused')).toHaveTextContent(/could not be reloaded/);
    expect(confirmSegmentationReview).not.toHaveBeenCalled();
  });
});

describe('m4: "evaluated" needs a yes/no conclusion in the viewer too', () => {
  it('rc070 release2 m4 an evaluated block without a conclusion is shown as not evaluated', async () => {
    seedOpen(null);
    getDISAssessment.mockResolvedValue({ ...notConfirmed('seg-1'), evaluation_status: 'evaluated',
      not_evaluated_reason: undefined, dis_met: undefined });
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    expect(await screen.findByTestId('dis-not-evaluated')).toBeInTheDocument();
    expect(screen.queryByText(METLIKE)).not.toBeInTheDocument();
  });
});

describe('m5 / m7: the failure paths of the confirmation', () => {
  it('rc071 release2 m5 recorded but not read back: no "No radiologist has confirmed", no second confirmation', async () => {
    seedOpen({ lesion_analysis: ANALYSIS, classification: CLASSIFICATION });
    confirmSegmentationReview.mockResolvedValue({ reviewed_by: 'dr_rev', reviewed_at: 'x', reviewed_mask_sha256: DIGEST });
    render(<LesionDashboard segmentationId="seg-1" />);
    const button = await screen.findByRole('button', { name: /confirm this segmentation/ });
    getDISAssessment.mockRejectedValue(new Error('network'));
    fireEvent.click(button);
    expect(await screen.findByTestId('dis-confirmed-unread')).toHaveTextContent(/confirmation was recorded/);
    expect(screen.queryByText('No radiologist has confirmed this segmentation.')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /confirm this segmentation/ })).not.toBeInTheDocument();
  });

  it('rc071 release2 m7 a refused confirmation never says "recorded" (positive control of F10)', async () => {
    seedOpen({ lesion_analysis: ANALYSIS, classification: CLASSIFICATION });
    confirmSegmentationReview.mockRejectedValue({ response: { status: 409, data: { error: { message: 'stale mask' } } } });
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(await screen.findByRole('button', { name: /confirm this segmentation/ }));
    expect(await screen.findByText('stale mask')).toBeInTheDocument();
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryByText(/Confirmation recorded/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('dis-confirmed-unread')).not.toBeInTheDocument();
  });
});
