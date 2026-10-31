/**
 * Release 2026-10-25 — film capture of the release build (2026-10-28): the region summary in the sidebar showed
 * "DWM: 1 lesions" (plural with a count of 1), and the report text had the same pattern.
 *
 * A count of exactly one takes the singular in English, Spanish and German (their CLDR "one" category), any other
 * count the plural — in the user's language: the deep-white-matter count of the evaluated DIS card (it was English
 * only) and the lesion count of the lesion table.
 *
 * Written before the correction (fails on 21b0df8).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

const getDISAssessment = vi.fn();
const analyzeLesions = vi.fn();
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    getDISAssessment: (...a: unknown[]) => getDISAssessment(...a),
    analyzeLesions: (...a: unknown[]) => analyzeLesions(...a),
    confirmSegmentationReview: vi.fn(),
    getSegmentation: vi.fn(async () => ({ segmentation_id: 'seg-1', metadata: {} })),
    classifyRegions: vi.fn(),
    annotateLesions: vi.fn(),
    confirmAiReview: vi.fn(),
  },
}));
vi.mock('sonner', () => ({ toast: { loading: vi.fn(), success: vi.fn(), error: vi.fn() } }));

import i18n from '@/i18n/config';
import { LesionDashboard } from './LesionDashboard';
import { useSegmentationStore } from '@/store/useSegmentationStore';

const DIGEST = 'cd'.repeat(32);
const MAGNIMS = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
  { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true },
  { id: 4, name: 'Deep White Matter', color: '#FFD700', opacity: 0.6, visible: true },
];

function analysisOf(n: number) {
  const lesions = Array.from({ length: n }, (_, i) => ({
    id: i + 1, label_id: 1, region: 'Periventricular', voxel_count: 12, volume_mm3: 36, volume_ml: 0.036,
    size_category: 'small', centroid: { z: 3, y: 3, x: 3 }, bounding_box: {},
  }));
  return {
    segmentation_id: 'seg-1', lesions, total_count: n, total_burden_mm3: 36 * n, total_burden_ml: 0.036 * n,
    regions: { Periventricular: { lesion_count: n, total_volume_mm3: 36 * n, total_volume_ml: 0.036 * n } },
    size_distribution: { small: n, medium: 0, large: 0 }, unique_labels: [1],
  };
}

function evaluated(dwm: number) {
  return {
    segmentation_id: 'seg-1', evaluation_status: 'evaluated', dis_met_brain: true, dis_met: true,
    dis_criteria_version: 'McDonald 2024', brain_regions_with_lesions: 2, brain_regions_evaluated: 3,
    total_dis_regions: 5, total_topographies_involved: 2, dis_met_full: true, dit_waiver_supported: false,
    supportive_specificity_markers: { central_vein_sign: null, paramagnetic_rim_lesion: null, csf_specific: null },
    specificity_marker_present: false, external_evidence_provided: false, decision_support_note: '', note: '',
    region_details: { Periventricular: { label_id: 1, present: true, voxel_count: 12, qualifying_lesion_count: 1 } },
    dwm_lesion_count: dwm, dwm_voxels: 12 * dwm, has_active_lesions: false, has_black_holes: false, active_voxels: 0,
    black_hole_voxels: 0,
    segmentation_review: { status: 'confirmed', source: 'origin_not_recorded', reviewed_by: 'dr_rev',
      reviewed_at: 'x', reviewed_mask_sha256: DIGEST, current_mask_sha256: DIGEST },
    regions: { classified: true, label_scheme: 'magnims' },
  };
}

function seedOpen(n: number) {
  useSegmentationStore.setState({
    currentSegmentation: {
      segmentation_id: 'seg-1', file_id: 'f.nii.gz', total_slices: 10,
      metadata: { file_id: 'f.nii.gz', created_at: 'T0', modified_at: 'T1', labels: MAGNIMS,
        analysis_data: { lesion_analysis: analysisOf(n) } },
    } as any,
    activeSegmentation: { id: 'seg-1', labels: MAGNIMS } as any,
    labelVisibility: { 0: false, 1: true, 4: true },
    isOverlayVisible: true,
    lesionOpacity: 0.6,
    maskDigestCallback: vi.fn().mockResolvedValue(DIGEST),
    maskValuesCallback: vi.fn(() => [1, 4]),
    hasUnsavedMaskChanges: false,
    reloadMaskCallback: vi.fn(async () => true),
  } as never);
}

// [language, count, deep-white-matter text of the DIS card, lesion count of the lesion table]
const CASES: Array<[string, number, string, string]> = [
  ['en', 1, 'DWM: 1 lesion (not a DIS region)', '1 lesion · 0.04 mL'],
  ['en', 2, 'DWM: 2 lesions (not a DIS region)', '2 lesions · 0.07 mL'],
  ['es', 1, 'DWM: 1 lesión (no es una región de la DIS)', '1 lesión · 0.04 mL'],
  ['es', 2, 'DWM: 2 lesiones (no es una región de la DIS)', '2 lesiones · 0.07 mL'],
  ['de', 1, 'DWM: 1 Läsion (keine DIS-Region)', '1 Läsion · 0.04 mL'],
  ['de', 2, 'DWM: 2 Läsionen (keine DIS-Region)', '2 Läsionen · 0.07 mL'],
];

beforeEach(() => {
  getDISAssessment.mockReset();
  analyzeLesions.mockReset();
});

afterEach(async () => {
  cleanup();
  await i18n.changeLanguage('en');
});

describe('film capture: a count of one is singular, in the user\'s language', () => {
  it.each(CASES)('rc070 release plural %s, count %d', async (lng, n, dwmText, tableText) => {
    await i18n.changeLanguage(lng);
    seedOpen(n);
    getDISAssessment.mockResolvedValue(evaluated(n));
    analyzeLesions.mockResolvedValue(analysisOf(n));
    render(<LesionDashboard segmentationId="seg-1" />);

    expect(await screen.findByText(dwmText)).toBeInTheDocument();
    expect(await screen.findByText(tableText)).toBeInTheDocument();
    expect(document.body.textContent ?? '').not.toMatch(/\b1 (lesions|lesiones|Läsionen)\b/);
  });
});
