/**
 * PRB-028 — regions from the geometric fallback are checked by the radiologist lesion by lesion before Confirm.
 *
 * When the MNI atlas cannot be used, the region classification falls back to the "geometric" heuristics (coordinate
 * rules, not anatomy). On MSLesSeg P51 (film capture 2026-10-28) they labelled 42 of 45 lesions periventricular and
 * agreed with the atlas on 11 of 45; the card only said "accuracy not measured" and one Confirm covered every region.
 *
 * Now the DIS card lists every lesion whose region comes from the geometric fallback (served by the DIS state:
 * `regions.geometric_regions`), each with its region, a button that opens its slice and a tick. Confirm stays off until
 * every listed lesion is ticked; the confirmation then sends the digest of the list (`geometric_regions_reviewed_sha256`),
 * which the server checks. A lesion corrected by hand is a region correction (acknowledged as before). More lesions
 * than the list can hold cannot be checked here: no Confirm. An atlas classification needs no tick (positive control).
 *
 * Written before the correction (fails on ca600c2, except the positive control).
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
const GEO = '9e'.repeat(32);
const ANALYSIS = {
  segmentation_id: 'seg-1',
  lesions: [{ id: 1, label_id: 1, region: 'Periventricular', voxel_count: 18, volume_mm3: 54, volume_ml: 0.054,
    size_category: 'small', centroid: { z: 3, y: 3, x: 3 }, bounding_box: {} }],
  total_count: 2, total_burden_mm3: 108, total_burden_ml: 0.108,
  regions: { Periventricular: { lesion_count: 1, total_volume_mm3: 54, total_volume_ml: 0.054 } },
  size_distribution: { small: 2, medium: 0, large: 0 }, unique_labels: [1, 2],
};
const STORED = MAGNIMS_LESION_LABELS.filter((l) => l.id !== 0).map(({ id, name, color }) => ({ id, name, color }));
const GEOMETRIC_REGIONS = [
  { lesion: 1, small_component: false, slice: 2, first_voxel: [2, 2, 2], voxels: 18, region: 1, region_name: 'Periventricular' },
  { lesion: 2, small_component: false, slice: 6, first_voxel: [6, 12, 12], voxels: 18, region: 2, region_name: 'Juxtacortical' },
];

const dis = (regions: Record<string, unknown>, reason = 'segmentation_not_confirmed') => ({
  segmentation_id: 'seg-1', evaluation_status: 'not_evaluated', not_evaluated_reason: reason,
  message: 'Not evaluated: requires clinician review of the segmentation.', dis_criteria_version: 'McDonald 2024',
  segmentation_review: { status: reason === 'segmentation_not_confirmed' ? 'unconfirmed' : 'outdated',
    source: 'origin_not_recorded', reviewed_by: null, reviewed_at: null, reviewed_mask_sha256: null,
    current_mask_sha256: DIGEST },
  regions: { classified: true, label_scheme: 'magnims', lesion_count: 2, lesions_valid: true, invalid_lesions: [],
    invalid_lesion_count: 0, corrections: [], correction_count: 0, corrections_sha256: 'ee'.repeat(32),
    listed_limit: 100, removed_small_components: null, stored_labels: STORED, ...regions },
});
const GEOMETRIC = { method: 'geometric', geometric_fallback: true, geometric_regions: GEOMETRIC_REGIONS,
  geometric_region_count: 2, geometric_regions_sha256: GEO };
const ATLAS = { method: 'msmask', geometric_fallback: false, geometric_regions: [], geometric_region_count: 0,
  geometric_regions_sha256: 'aa'.repeat(32) };

/** Segmentation "seg-1" is open and drawn with its stored labels in the standard 2D view, over its own image. */
function seedOpen() {
  useSegmentationStore.setState({
    currentSegmentation: {
      segmentation_id: 'seg-1', file_id: 'f.nii.gz', total_slices: 10,
      metadata: { file_id: 'f.nii.gz', created_at: 'T0', modified_at: 'T1', labels: MAGNIMS_LESION_LABELS,
        analysis_data: { lesion_analysis: ANALYSIS } },
    } as any,
    activeSegmentation: { id: 'seg-1', labels: MAGNIMS_LESION_LABELS } as any,
    labelVisibility: Object.fromEntries(MAGNIMS_LESION_LABELS.map((l) => [l.id, l.id !== 0])),
    isOverlayVisible: true,
    lesionOpacity: 0.6,
    maskDigestCallback: vi.fn().mockResolvedValue(DIGEST),
    maskValuesCallback: vi.fn(() => [1, 2]),
    hasUnsavedMaskChanges: false,
    reloadMaskCallback: vi.fn(async () => true),
    overlayOnScreen: 'seg-1',
    // PRB-030: the image the standard view draws under the mask, on the mask's grid
    overlayImageOnScreen: { segmentationId: 'seg-1', imageFileId: 'f.nii.gz',
      image: { width: 20, height: 20, depth: 10 }, mask: { width: 20, height: 20, depth: 10 } },
    zoneMapVisible: false, longitudinalVisible: false, longitudinalSubtractionVisible: false, conformalVisible: false,
  } as never);
}

const confirmButton = () => screen.findByRole('button', { name: /confirm this segmentation/ });

beforeEach(() => {
  for (const f of [getDISAssessment, analyzeLesions, confirmSegmentationReview]) f.mockReset();
  analyzeLesions.mockResolvedValue(ANALYSIS);
  confirmSegmentationReview.mockResolvedValue({ reviewed_by: 'dr_rev', reviewed_at: 'x', reviewed_mask_sha256: DIGEST });
  vi.restoreAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  seedOpen();
});

describe('PRB-028: geometric-fallback regions are checked lesion by lesion before Confirm', () => {
  it('rc090 prb028 every geometric-fallback lesion is listed with its region, a tick and its slice', async () => {
    getDISAssessment.mockResolvedValue(dis(GEOMETRIC));
    const onNavigateToSlice = vi.fn();
    render(<LesionDashboard segmentationId="seg-1" onNavigateToSlice={onNavigateToSlice} />);
    const rows = await screen.findAllByTestId('dis-geometric-region');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent(/Lesion 1 \(slice 3, 18 voxels\): Periventricular/);
    expect(rows[1]).toHaveTextContent(/Lesion 2 \(slice 7, 18 voxels\): Juxtacortical/);
    expect(screen.getByTestId('dis-geometric-regions')).toHaveTextContent(/geometric fallback/i);
    fireEvent.click(screen.getAllByRole('button', { name: /open slice 7/i })[0]);
    expect(onNavigateToSlice).toHaveBeenCalledWith(6);
  });

  it('rc090 prb028 Confirm stays off until every listed lesion is ticked', async () => {
    getDISAssessment.mockResolvedValue(dis(GEOMETRIC));
    render(<LesionDashboard segmentationId="seg-1" />);
    const ticks = await screen.findAllByRole('checkbox', { name: /checked the region of lesion/i });
    expect(ticks).toHaveLength(2);
    expect(await confirmButton()).toBeDisabled();
    fireEvent.click(ticks[0]);
    expect(await confirmButton()).toBeDisabled();
    fireEvent.click(await confirmButton());
    expect(confirmSegmentationReview).not.toHaveBeenCalled();
  });

  it('rc090 prb028 with every lesion ticked the confirmation sends the digest of the checked list', async () => {
    getDISAssessment.mockResolvedValue(dis(GEOMETRIC));
    render(<LesionDashboard segmentationId="seg-1" />);
    for (const tick of await screen.findAllByRole('checkbox', { name: /checked the region of lesion/i })) {
      fireEvent.click(tick);
    }
    fireEvent.click(await confirmButton());
    await waitFor(() => expect(confirmSegmentationReview).toHaveBeenCalled());
    expect(confirmSegmentationReview.mock.calls[0][4]).toEqual(expect.objectContaining({ geometricRegionsReviewedSha256: GEO }));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringMatching(/region of each of these 2 lesions one by one/));
  });

  it('rc090 prb028 more geometric-fallback lesions than the list holds: no Confirm here', async () => {
    getDISAssessment.mockResolvedValue(dis({ ...GEOMETRIC, geometric_region_count: 150 }));
    render(<LesionDashboard segmentationId="seg-1" />);
    expect(await screen.findByTestId('dis-geometric-too-many')).toHaveTextContent(/150/);
    expect(screen.queryByRole('button', { name: /confirm this segmentation/ })).not.toBeInTheDocument();
  });

  it('rc090 prb028 a confirmation recorded without the per-lesion check is explained and can be redone', async () => {
    getDISAssessment.mockResolvedValue(dis(GEOMETRIC, 'geometric_regions_not_reviewed'));
    render(<LesionDashboard segmentationId="seg-1" />);
    expect(await screen.findByTestId('dis-reason-geometric')).toHaveTextContent(/one by one/);
    expect(await screen.findAllByTestId('dis-geometric-region')).toHaveLength(2);
    expect(await confirmButton()).toBeDisabled();
  });

  it('rc090 prb028 the classification card says each geometric region must be checked one by one', async () => {
    getDISAssessment.mockResolvedValue(dis(GEOMETRIC));
    useSegmentationStore.setState({
      currentSegmentation: { ...useSegmentationStore.getState().currentSegmentation!, metadata: {
        ...useSegmentationStore.getState().currentSegmentation!.metadata,
        analysis_data: { lesion_analysis: ANALYSIS, classification: { segmentation_id: 'seg-1', method: 'geometric',
          lesions: [], total_classified: 2, classification_summary: { Periventricular: 1, Juxtacortical: 1 } } } } },
    } as never);
    render(<LesionDashboard segmentationId="seg-1" />);
    expect(await screen.findByTestId('geometric-warning')).toHaveTextContent(/one by one/);
  });

  it('rc090 prb028 an atlas classification needs no tick (positive control)', async () => {
    getDISAssessment.mockResolvedValue(dis(ATLAS));
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(await confirmButton());
    await waitFor(() => expect(confirmSegmentationReview).toHaveBeenCalled());
    expect(screen.queryByTestId('dis-geometric-region')).not.toBeInTheDocument();
  });
});
