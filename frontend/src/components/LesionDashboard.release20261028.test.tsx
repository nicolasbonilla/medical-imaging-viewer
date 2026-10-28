/**
 * Release 2026-10-25 — browser capture session of the release build (2026-10-28): findings F08, F09, F10, F04.
 *
 *  - F08 (clinical safety): after "Auto-Classify Regions", lesions labelled 2-4 (juxtacortical, infratentorial, deep
 *    white matter) were not drawn until the study was reopened. The viewer draws from activeSegmentation.labels, but
 *    the classification only replaced currentSegmentation.metadata.labels (and after reloading the mask). The labels
 *    the server stored must reach both, with every region visible, BEFORE the mask is reloaded.
 *  - F09: the region classification removes lesion components smaller than 3 mm³; the classification card and the
 *    confirmation (card and dialog) must state how many components and voxels were removed, and why.
 *  - F10: after "confirm", the card kept saying "No radiologist has confirmed this segmentation" for 6-12 s with no
 *    progress; the pending state must show until the refreshed DIS state is read.
 *  - F04: the per-region rows printed a literal "—".
 *
 * Written before the corrections (they fail on c7a06cf).
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
const EVALUATED = {
  segmentation_id: 'seg-1', evaluation_status: 'evaluated', dis_met_brain: true, dis_met: true,
  dis_criteria_version: 'McDonald 2024', brain_regions_with_lesions: 2, brain_regions_evaluated: 3,
  total_dis_regions: 5, total_topographies_involved: 2, dis_met_full: true, dit_waiver_supported: false,
  supportive_specificity_markers: { central_vein_sign: null, paramagnetic_rim_lesion: null, csf_specific: null },
  specificity_marker_present: false, external_evidence_provided: false, decision_support_note: '', note: '',
  region_details: { Periventricular: { label_id: 1, present: true, voxel_count: 12, qualifying_lesion_count: 1 } },
  dwm_lesion_count: 0, dwm_voxels: 0, has_active_lesions: false, has_black_holes: false, active_voxels: 0,
  black_hole_voxels: 0,
  segmentation_review: { status: 'confirmed', source: 'origin_not_recorded', reviewed_by: 'dr_rev', reviewed_at: 'x',
    reviewed_mask_sha256: DIGEST, current_mask_sha256: DIGEST },
  regions: { classified: true, label_scheme: 'magnims' },
};
// The labels the server stores with a classified mask (segmentation_regions.py).
const SERVER_LABELS = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0.0, visible: false },
  { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true },
  { id: 2, name: 'Juxtacortical', color: '#00CC00', opacity: 0.6, visible: true },
  { id: 3, name: 'Infratentorial', color: '#0066FF', opacity: 0.6, visible: true },
  { id: 4, name: 'Deep White Matter', color: '#FFD700', opacity: 0.6, visible: true },
  { id: 5, name: 'Active (Gd+)', color: '#FF00FF', opacity: 0.6, visible: true },
  { id: 6, name: 'Black Hole (T1)', color: '#9932CC', opacity: 0.5, visible: true },
];
const REMOVED = { components: 8, voxels: 11, volume_mm3: 11.0, min_lesion_volume_mm3: 3.0,
  reason: 'Lesion components smaller than 3 mm³ are below the minimum lesion size; they are not classified and were removed from the mask.' };
const CLASSIFICATION = {
  segmentation_id: 'seg-1', method: 'geometric', lesions: [], total_classified: 1, classification_summary: { Periventricular: 1 },
  thresholds_mm: {}, processing_time_ms: 5, mask_updated: true, labels_updated: true,
};

// Release 2026-10-25 (review of PR #69, B1/M3): the label table of the open mask that the confirm tests confirm.
const DRAWN_LABELS = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
  { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true },
  { id: 2, name: 'Juxtacortical', color: '#00CC00', opacity: 0.6, visible: true },
];

function seed(analysisData: Record<string, unknown> | null = null) {
  useSegmentationStore.setState({
    currentSegmentation: {
      segmentation_id: 'seg-1', file_id: 'f.nii.gz', total_slices: 10,
      metadata: { file_id: 'f.nii.gz', created_at: 'T0', modified_at: 'T1',
        labels: [{ id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
                 { id: 1, name: 'Lesion', color: '#FF0000', opacity: 0.5, visible: true }],
        analysis_data: analysisData },
    } as any,
    activeSegmentation: {
      id: 'seg-1', patient_id: '', study_id: '', series_id: '', file_id: 'f.nii.gz', name: 'S',
      segmentation_type: 'manual', status: 'in_progress', progress_percentage: 0, slices_annotated: 0,
      total_slices: 10, created_by: 'u', created_at: 'T0', modified_at: 'T1',
      labels: [{ id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
               { id: 1, name: 'Lesion', color: '#FF0000', opacity: 0.5, visible: true }],
    } as any,
    labelVisibility: { 0: false, 1: true },
    activeLabel: 1,
    isDirty: false,
    maskDigestCallback: vi.fn().mockResolvedValue(DIGEST),
    // Release 2026-10-25 (review of PR #69, B1/M3): the open mask that is confirmed is drawn (its value 1, Lesion, visible).
    maskValuesCallback: vi.fn(() => [1]),
    isOverlayVisible: true,
    lesionOpacity: 0.6,
    hasUnsavedMaskChanges: false,
  } as never);
}

beforeEach(() => {
  for (const f of [getDISAssessment, analyzeLesions, confirmSegmentationReview, getSegmentation, classifyRegions]) f.mockReset();
  analyzeLesions.mockResolvedValue(ANALYSIS);
  getSegmentation.mockResolvedValue({ segmentation_id: 'seg-1', metadata: {} });
  getDISAssessment.mockResolvedValue(NOT_CONFIRMED);
  vi.restoreAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('F08: every region is drawn right after the classification', () => {
  it('rc070 release f08 the labels the server stored reach the viewer, every region visible, before the mask reload', async () => {
    seed();
    let labelsAtReload: number[] = [];
    useSegmentationStore.setState({
      reloadMaskCallback: vi.fn(async () => {
        labelsAtReload = (useSegmentationStore.getState().activeSegmentation?.labels ?? []).map((l) => l.id);
      }),
    });
    classifyRegions.mockResolvedValue({ ...CLASSIFICATION, labels: SERVER_LABELS });
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: /Auto-Classify Regions/ }));
    await waitFor(() => expect(analyzeLesions).toHaveBeenCalled());
    const s = useSegmentationStore.getState();
    expect(s.activeSegmentation?.labels).toEqual(SERVER_LABELS);           // what the 2D canvas draws from
    expect(s.currentSegmentation?.metadata?.labels).toEqual(SERVER_LABELS);
    for (const id of [1, 2, 3, 4]) expect(s.labelVisibility[id]).toBe(true);
    expect(labelsAtReload).toEqual(expect.arrayContaining([1, 2, 3, 4]));  // applied before the mask reload
    expect(s.isDirty).toBe(false);                                          // the server stored them: nothing to save
  });
});

describe('F09: small components removed by the classification are stated before the confirmation', () => {
  it('rc070 release f09 the classification card and the confirmation state how many components and voxels were removed', async () => {
    seed({ lesion_analysis: ANALYSIS, classification: { ...CLASSIFICATION, removed_small_components: REMOVED } });
    // Contract changed by the second review of PR #69 (M1): the DIS card and the confirm dialog take the removal from
    // the server's DIS state of this segmentation (regions.removed_small_components), not from the open
    // segmentation's stored classification; the server serves it here as it does for these lesions.
    getDISAssessment.mockResolvedValue({ ...NOT_CONFIRMED, regions: { ...NOT_CONFIRMED.regions, removed_small_components: REMOVED } });
    render(<LesionDashboard segmentationId="seg-1" />);
    const removed = await screen.findByTestId('classification-removed-components');
    expect(removed).toHaveTextContent(/removed 8 lesion component\(s\) smaller than 3 mm³/);
    expect(removed).toHaveTextContent(/11 voxels/);
    const inCard = await screen.findByTestId('dis-removed-components');
    expect(inCard).toHaveTextContent(/8 lesion component\(s\)/);
    fireEvent.click(await screen.findByRole('button', { name: /confirm this segmentation/ }));
    await waitFor(() => expect(window.confirm).toHaveBeenCalled());
    const question = (window.confirm as unknown as { mock: { calls: string[][] } }).mock.calls[0][0];
    expect(question).toMatch(/8 lesion component\(s\)/);
    expect(question).toMatch(/11 voxels/);
  });

  it('rc070 release f09 nothing is said when nothing was removed', async () => {
    seed({ lesion_analysis: ANALYSIS, classification: { ...CLASSIFICATION,
      removed_small_components: { ...REMOVED, components: 0, voxels: 0, volume_mm3: 0 } } });
    render(<LesionDashboard segmentationId="seg-1" />);
    await screen.findByTestId('dis-not-evaluated');
    expect(screen.queryByTestId('classification-removed-components')).not.toBeInTheDocument();
    expect(screen.queryByTestId('dis-removed-components')).not.toBeInTheDocument();
  });
});

describe('F10: the pending state after confirming', () => {
  it('rc071 release f10 the card shows the confirmation pending until the refreshed DIS state is read', async () => {
    seed({ lesion_analysis: ANALYSIS, classification: CLASSIFICATION });
    let releaseDis: (v: unknown) => void = () => undefined;
    let releasePost: (v: unknown) => void = () => undefined;
    confirmSegmentationReview.mockImplementation(() => new Promise((resolve) => { releasePost = resolve; }));
    render(<LesionDashboard segmentationId="seg-1" />);
    const button = await screen.findByRole('button', { name: /confirm this segmentation/ });
    getDISAssessment.mockImplementation(() => new Promise((resolve) => { releaseDis = resolve; }));
    fireEvent.click(button);
    expect(await screen.findByTestId('dis-confirm-pending')).toHaveTextContent(/Recording your confirmation/);
    expect(screen.queryByText('No radiologist has confirmed this segmentation.')).not.toBeInTheDocument();
    await act(async () => { releasePost({ reviewed_by: 'dr_rev', reviewed_at: 'x', reviewed_mask_sha256: DIGEST }); });
    expect(screen.getByTestId('dis-confirm-pending')).toHaveTextContent(/Confirmation recorded/);
    expect(screen.queryByText('No radiologist has confirmed this segmentation.')).not.toBeInTheDocument();
    await act(async () => { releaseDis(EVALUATED); });
    expect(await screen.findByText(/Criterion Met/)).toBeInTheDocument();
    expect(screen.queryByTestId('dis-confirm-pending')).not.toBeInTheDocument();
  });
});

describe('F04: per-region rows', () => {
  it('rc070 release f04 the by-region rows show a dash, never the escape text', async () => {
    seed();
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    expect(await screen.findByText('1 — 0.04 mL')).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('\\u2014');
  });
});
