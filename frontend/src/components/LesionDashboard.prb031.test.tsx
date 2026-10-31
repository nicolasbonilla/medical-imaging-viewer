/**
 * PRB-031 (L2 of the last check of PR #69) — the zone map and the longitudinal overlay can camouflage lesions.
 *
 * The zone map is drawn under the lesions in the same MAGNIMS colours, at a user opacity of up to 100 % that is kept
 * across sessions: a periventricular lesion inside the periventricular zone could not be seen, and Confirm was
 * accepted. The longitudinal overlay (fixed 55 %), the FLAIR subtraction heat map (up to 60 %) and the conformal tiers
 * (78 %) are drawn under the lesions the same way. An underlay of opacity a leaves (1 - a) of the image contrast and of
 * the lesion colour's own contrast inside an area of the same colour; at most 30 % (the zone map's default) leaves at
 * least 70 %.
 *
 * Confirm is now refused while an underlay is drawn above 30 %: the zone map above it, or the longitudinal overlay, the
 * subtraction heat map or the conformal tiers at all (their fixed opacities are above it). The zone map at 30 % or
 * hidden does not refuse (positive controls).
 *
 * Written before the correction (the refusals fail on ca600c2).
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
import en from '@/i18n/locales/en.json';
import es from '@/i18n/locales/es.json';
import de from '@/i18n/locales/de.json';

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
const GRID = { width: 4, height: 4, depth: 2 };
const VOLUME = new Uint8Array(4 * 4 * 2);

function seedOpen(over: Record<string, unknown>) {
  useSegmentationStore.setState({
    currentSegmentation: {
      segmentation_id: 'seg-1', file_id: 'f.nii.gz', total_slices: 2,
      metadata: { file_id: 'f.nii.gz', created_at: 'T0', modified_at: 'T1', labels: MAGNIMS_LESION_LABELS,
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
    overlayImageOnScreen: { segmentationId: 'seg-1', imageFileId: 'f.nii.gz', image: GRID, mask: GRID },
    zoneMapVisible: false, zoneMapOpacity: 0.3, zoneMapMask: VOLUME, zoneMapDims: GRID,
    longitudinalVisible: false, longitudinalTp1Mask: VOLUME, longitudinalTp1Dims: GRID,
    longitudinalTp2Mask: VOLUME, longitudinalTp2Dims: GRID,
    longitudinalSubtractionVisible: false, longitudinalSubtractionVolume: VOLUME, longitudinalSubtractionDims: GRID,
    conformalVisible: false, conformalStatusMask: VOLUME, conformalDims: GRID,
    ...over,
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

describe('PRB-031: Confirm refused while an overlay drawn under the lesions can hide them', () => {
  it.each([
    ['the zone map at 100 %', { zoneMapVisible: true, zoneMapOpacity: 1 }, /zone map .*100 %.*30 %/],
    ['the zone map at 31 %', { zoneMapVisible: true, zoneMapOpacity: 0.31 }, /zone map .*31 %.*30 %/],
    ['the longitudinal overlay', { longitudinalVisible: true }, /longitudinal overlay .*55 %.*30 %/],
    ['the FLAIR subtraction heat map', { longitudinalSubtractionVisible: true }, /subtraction .*60 %.*30 %/],
    ['the conformal tiers', { conformalVisible: true }, /conformal .*78 %.*30 %/],
  ])('rc093 prb031 refused while %s is drawn under the lesions', async (_name, over, text) => {
    seedOpen(over);
    await pressConfirm();
    expect(await screen.findByTestId('dis-confirm-refused')).toHaveTextContent(text);
    expect(window.confirm).not.toHaveBeenCalled();
    expect(confirmSegmentationReview).not.toHaveBeenCalled();
  });

  it.each([
    ['the zone map at 30 %', { zoneMapVisible: true, zoneMapOpacity: 0.3 }],
    ['the zone map hidden at 100 %', { zoneMapVisible: false, zoneMapOpacity: 1 }],
    ['no underlay', {}],
  ])('rc093 prb031 accepted with %s (positive control)', async (_name, over) => {
    seedOpen(over);
    await pressConfirm();
    await waitFor(() => expect(confirmSegmentationReview).toHaveBeenCalled());
  });

  it('rc093 prb031 the refusal texts of PRB-028..031 exist in English, Spanish and German', () => {
    const keys = ['undrawnUnderlayOpaque', 'undrawnGridUnknown', 'undrawnGridMismatch', 'geometricRegionsTitle',
      'geometricRegionItem', 'acknowledgeGeometricRegion', 'reasonGeometricNotReviewed', 'geometricTooMany',
      'confirmGeometric'];
    for (const [lang, dict] of [['en', en], ['es', es], ['de', de]] as const) {
      const review = (dict as unknown as { disReview: Record<string, string> }).disReview;
      for (const key of keys) expect(typeof review[key], `${lang} disReview.${key}`).toBe('string');
      const layers = (dict as unknown as { disReview: Record<string, unknown> }).disReview.underlay as Record<string, string>;
      for (const layer of ['zone_map', 'longitudinal', 'subtraction', 'conformal']) {
        expect(typeof layers?.[layer], `${lang} disReview.underlay.${layer}`).toBe('string');
      }
    }
  });
});
