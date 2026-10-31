/**
 * Independent review of PR #74 (290e407), m2 and m5 — the per-lesion ticks of the geometric-fallback regions.
 *
 *  - m2: the ticks were live on any expanded card, also when its segmentation was not open (another one on screen) or
 *    not drawn, and they survived opening another segmentation; a tick needed no look at the lesion. Now a tick can be
 *    given only while THIS segmentation is open and drawn in the standard view, and only after its "open slice" was
 *    pressed; the ticks (and the opened slices) are cleared when the segmentation is closed or another one is opened.
 *  - m5: the reset of the ticks when the served list changes (a region corrected, the classification run again) had no
 *    test. Ticks are now keyed by first voxel AND region, and a changed list clears every tick.
 *
 * Written before the correction (the m2 cases fail on 290e407; the m5 case is a regression test of the existing reset,
 * bound to a new negative control).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

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
  segmentation_id: 'seg-1', lesions: [], total_count: 2, total_burden_mm3: 108, total_burden_ml: 0.108,
  regions: {}, size_distribution: { small: 2, medium: 0, large: 0 }, unique_labels: [1, 2],
};
const STORED = MAGNIMS_LESION_LABELS.filter((l) => l.id !== 0).map(({ id, name, color }) => ({ id, name, color }));
const LESION1 = { lesion: 1, small_component: false, slice: 2, first_voxel: [2, 2, 2], voxels: 18, region: 1, region_name: 'Periventricular' };
const LESION2 = { lesion: 2, small_component: false, slice: 6, first_voxel: [6, 12, 12], voxels: 18, region: 2, region_name: 'Juxtacortical' };

const dis = (list: unknown[], digest: string) => ({
  segmentation_id: 'seg-1', evaluation_status: 'not_evaluated', not_evaluated_reason: 'segmentation_not_confirmed',
  message: 'Not evaluated', dis_criteria_version: 'McDonald 2024',
  segmentation_review: { status: 'unconfirmed', source: 'origin_not_recorded', reviewed_by: null, reviewed_at: null,
    reviewed_mask_sha256: null, current_mask_sha256: DIGEST },
  regions: { classified: true, label_scheme: 'magnims', lesion_count: 2, lesions_valid: true, invalid_lesions: [],
    invalid_lesion_count: 0, corrections: [], correction_count: 0, corrections_sha256: 'ee'.repeat(32),
    listed_limit: 100, removed_small_components: null, stored_labels: STORED, method: 'geometric',
    geometric_fallback: true, geometric_regions: list, geometric_region_count: list.length, geometric_regions_sha256: digest },
});

const segmentation = (id: string, modifiedAt = 'T1') => ({
  segmentation_id: id, file_id: 'f.nii.gz', total_slices: 10,
  metadata: { file_id: 'f.nii.gz', created_at: 'T0', modified_at: modifiedAt, labels: MAGNIMS_LESION_LABELS,
    analysis_data: { lesion_analysis: { ...ANALYSIS, segmentation_id: id } } },
});

function seed(openId: string, onScreen: string | null, modifiedAt = 'T1') {
  useSegmentationStore.setState({
    currentSegmentation: segmentation(openId, modifiedAt) as never,
    activeSegmentation: { id: openId, labels: MAGNIMS_LESION_LABELS } as never,
    labelVisibility: Object.fromEntries(MAGNIMS_LESION_LABELS.map((l) => [l.id, l.id !== 0])),
    isOverlayVisible: true, lesionOpacity: 0.6,
    maskDigestCallback: vi.fn().mockResolvedValue(DIGEST), maskValuesCallback: vi.fn(() => [1, 2]),
    hasUnsavedMaskChanges: false, reloadMaskCallback: vi.fn(async () => true),
    overlayOnScreen: onScreen,
    overlayImageOnScreen: onScreen ? { segmentationId: onScreen, imageFileId: 'f.nii.gz',
      image: { width: 20, height: 20, depth: 10 }, mask: { width: 20, height: 20, depth: 10 } } : null,
    zoneMapVisible: false, zoneColorizeEnabled: false, longitudinalVisible: false,
    longitudinalSubtractionVisible: false, conformalVisible: false,
  } as never);
}

const ticks = () => screen.findAllByRole('checkbox', { name: /checked the region of lesion/i });
const confirmButton = () => screen.findByRole('button', { name: /confirm this segmentation/ });

async function openAndTickAll() {
  for (const button of await screen.findAllByRole('button', { name: /open slice/i })) fireEvent.click(button);
  for (const tick of await ticks()) fireEvent.click(tick);
}

beforeEach(() => {
  for (const f of [getDISAssessment, analyzeLesions, confirmSegmentationReview]) f.mockReset();
  getDISAssessment.mockResolvedValue(dis([LESION1, LESION2], '9e'.repeat(32)));
  confirmSegmentationReview.mockResolvedValue({ reviewed_by: 'dr_rev', reviewed_at: 'x', reviewed_mask_sha256: DIGEST });
  vi.restoreAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('review m2: a tick only while this segmentation is open and drawn, after opening its slice', () => {
  it('rc090 review m2 the card of a segmentation that is not open offers no tick', async () => {
    seed('seg-2', 'seg-2');                                     // segmentation B on screen, the card is A's
    render(<LesionDashboard segmentationId="seg-1" onNavigateToSlice={vi.fn()} />);
    for (const tick of await ticks()) expect(tick).toBeDisabled();
  });

  it('rc090 review m2 no tick while the open segmentation is not drawn in the standard view', async () => {
    seed('seg-1', null);
    render(<LesionDashboard segmentationId="seg-1" onNavigateToSlice={vi.fn()} />);
    for (const button of await screen.findAllByRole('button', { name: /open slice/i })) fireEvent.click(button);
    for (const tick of await ticks()) expect(tick).toBeDisabled();
  });

  it('rc090 review m2 a tick is given only after its "open slice" was pressed', async () => {
    seed('seg-1', 'seg-1');
    const navigate = vi.fn();
    render(<LesionDashboard segmentationId="seg-1" onNavigateToSlice={navigate} />);
    const [first, second] = await ticks();
    expect(first).toBeDisabled();
    expect(second).toBeDisabled();
    fireEvent.click(screen.getAllByRole('button', { name: /open slice 3/i })[0]);
    expect(navigate).toHaveBeenCalledWith(2);
    expect((await ticks())[0]).not.toBeDisabled();
    expect((await ticks())[1]).toBeDisabled();
  });

  it('rc090 review m2 another segmentation opened: no tick on this card, and the ticks are gone when it is opened again', async () => {
    seed('seg-1', 'seg-1');
    render(<LesionDashboard segmentationId="seg-1" onNavigateToSlice={vi.fn()} />);
    await openAndTickAll();
    await waitFor(async () => expect(await confirmButton()).not.toBeDisabled());
    act(() => { seed('seg-2', 'seg-2', 'T9'); });              // B opened: A's card stays expanded (its list re-read)
    await waitFor(async () => expect((await ticks()).length).toBe(2));
    for (const tick of await ticks()) {
      expect(tick).not.toBeChecked();
      expect(tick).toBeDisabled();
    }
    act(() => { seed('seg-1', 'seg-1'); });                    // A opened again
    await waitFor(async () => expect((await ticks()).length).toBe(2));
    for (const tick of await ticks()) expect(tick).not.toBeChecked();
    expect(await confirmButton()).toBeDisabled();
  });
});

describe('review m5: a changed list clears every tick', () => {
  it('rc090 review m5 a re-served list (lesion 1 corrected to another region) clears the ticks of every lesion', async () => {
    seed('seg-1', 'seg-1');
    render(<LesionDashboard segmentationId="seg-1" onNavigateToSlice={vi.fn()} />);
    await openAndTickAll();
    await waitFor(async () => expect(await confirmButton()).not.toBeDisabled());
    getDISAssessment.mockResolvedValue(dis([{ ...LESION1, region: 4, region_name: 'Deep White Matter' }, LESION2], '7c'.repeat(32)));
    act(() => {                                               // the mask was saved again: the DIS state is re-read
      useSegmentationStore.setState({ currentSegmentation: segmentation('seg-1', 'T2') as never } as never);
    });
    await waitFor(async () => expect(screen.getByText(/Lesion 1 \(slice 3, 18 voxels\): Deep White Matter/)).toBeInTheDocument());
    for (const tick of await ticks()) expect(tick).not.toBeChecked();
    expect(await confirmButton()).toBeDisabled();
  });
});
