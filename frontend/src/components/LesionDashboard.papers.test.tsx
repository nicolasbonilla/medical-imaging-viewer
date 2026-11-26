/**
 * Findings of papers 1 and 2 in the dashboard (SRS/RMF Addendum E, DRAFT — PENDING owner approval;
 * trace: docs/research/papers-in-app.md).
 *
 * RC-134 (REQ-SAFE-061, HAZ-008): a met brain-DIS result is shown with what it does not mean, in an attention colour
 * (amber), never as a success (green). PRB-033: "most older adults" rests on CC0 data; "can be met" in
 * vascular white matter disease is from the literature (RMF Addendum H).
 * RC-133 (REQ-FUNC-121): lesions under 3 mm in largest extent do not count toward DIS; their number is shown and the
 * per-region count is described accurately (MAGNIMS 2021 size, not "size/location criteria").
 *
 * These tests drive the real dashboard with mocked API calls; they fail on main @ c6acd79.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import fs from 'node:fs';
import path from 'node:path';

const getDISAssessment = vi.fn();
const analyzeLesions = vi.fn();
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    getDISAssessment: (...a: unknown[]) => getDISAssessment(...a),
    analyzeLesions: (...a: unknown[]) => analyzeLesions(...a),
    confirmSegmentationReview: vi.fn(),
    getSegmentation: vi.fn(async () => ({ segmentation_id: 'seg-1', metadata: { analysis_data: null } })),
    classifyRegions: vi.fn(),
    annotateLesions: vi.fn(),
    confirmAiReview: vi.fn(),
  },
}));
vi.mock('sonner', () => ({ toast: { loading: vi.fn(), success: vi.fn(), error: vi.fn() } }));

import { LesionDashboard, DIS_INTERPRETATION_EN, QUALIFYING_TOOLTIP_EN, BELOW_SIZE_EN } from './LesionDashboard';
import { useSegmentationStore } from '@/store/useSegmentationStore';

const DIGEST = 'cd'.repeat(32);
const ANALYSIS = {
  segmentation_id: 'seg-1',
  lesions: [
    { id: 1, label_id: 1, region: 'Periventricular', voxel_count: 12, volume_mm3: 36, volume_ml: 0.036,
      size_category: 'small', centroid: { z: 3, y: 3, x: 3 }, bounding_box: {} },
    { id: 2, label_id: 2, region: 'Juxtacortical', voxel_count: 12, volume_mm3: 36, volume_ml: 0.036,
      size_category: 'small', centroid: { z: 7, y: 13, x: 13 }, bounding_box: {} },
  ],
  total_count: 2, total_burden_mm3: 72, total_burden_ml: 0.072, regions: {},
  size_distribution: { small: 2, medium: 0, large: 0 }, unique_labels: [1, 2],
};

const evaluated = (met: boolean, belowSize = 0) => ({
  segmentation_id: 'seg-1', evaluation_status: 'evaluated', dis_met_brain: met, dis_met: met,
  dis_criteria_version: 'McDonald 2024 (Montalban et al., Lancet Neurology 2025)',
  brain_regions_with_lesions: met ? 2 : 1, brain_regions_evaluated: 3, total_dis_regions: 5,
  total_topographies_involved: met ? 2 : 1, dis_met_full: met, dit_waiver_supported: false,
  supportive_specificity_markers: { central_vein_sign: null, paramagnetic_rim_lesion: null, csf_specific: null },
  specificity_marker_present: false, external_evidence_provided: false,
  decision_support_note: 'Radiological decision support only — NOT a diagnosis.', note: 'Brain MRI: 3 of 5.',
  region_details: {
    Periventricular: { label_id: 1, present: met, voxel_count: 12, qualifying_lesion_count: met ? 1 : 0,
                       below_size_lesion_count: belowSize },
    Juxtacortical: { label_id: 2, present: true, voxel_count: 12, qualifying_lesion_count: 1, below_size_lesion_count: 0 },
    Infratentorial: { label_id: 3, present: false, voxel_count: 0, qualifying_lesion_count: 0, below_size_lesion_count: 0 },
  },
  lesion_size_rule: { min_largest_extent_mm: 3, min_volume_mm3: 3, largest_extent: 'x', source: 'MAGNIMS 2021' },
  below_size_lesion_count: belowSize,
  dwm_lesion_count: 0, dwm_voxels: 0, has_active_lesions: false, has_black_holes: false,
  active_voxels: 0, black_hole_voxels: 0,
  segmentation_review: { status: 'confirmed', source: 'origin_not_recorded', reviewed_by: 'dr_rev',
                         reviewed_at: '2026-11-21T10:00:00Z', reviewed_mask_sha256: DIGEST, current_mask_sha256: DIGEST },
});

function seedStore() {
  useSegmentationStore.setState({
    currentSegmentation: {
      segmentation_id: 'seg-1', file_id: 'f.nii.gz', total_slices: 10,
      metadata: { file_id: 'f.nii.gz', created_at: 'T0', modified_at: 'T1', labels: [], analysis_data: null },
    } as never,
    maskDigestCallback: vi.fn().mockResolvedValue(DIGEST),
    hasUnsavedMaskChanges: false,
  } as never);
}

async function showResult(block: Record<string, unknown>) {
  seedStore();
  analyzeLesions.mockResolvedValue(ANALYSIS);
  getDISAssessment.mockResolvedValue(block);
  render(<LesionDashboard segmentationId="seg-1" />);
  fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
  return screen.findByTestId('dis-result');
}

beforeEach(() => {
  getDISAssessment.mockReset();
  analyzeLesions.mockReset();
});

describe('RC-134 what a met DIS result does not mean (papers 1 and 2)', () => {
  it('rc134 a met result carries the interpretation, in amber and not as a success', async () => {
    const box = await showResult(evaluated(true));
    expect(screen.getByText(/Criterion Met/)).toBeInTheDocument();
    expect(screen.getByTestId('dis-interpretation')).toHaveTextContent(DIS_INTERPRETATION_EN);
    expect(box.className).toMatch(/amber/);
    expect(box.innerHTML).not.toMatch(/green/);       // nothing of the met result is drawn as a success
  });

  it('rc134 a not-met result has no interpretation line and a neutral colour', async () => {
    const box = await showResult(evaluated(false));
    expect(screen.getByText(/Not Met/)).toBeInTheDocument();
    expect(screen.queryByTestId('dis-interpretation')).not.toBeInTheDocument();
    expect(box.className).not.toMatch(/red|green/);
  });

  it('rc134 the interpretation names what the rule ignores and who also meets it', () => {
    for (const part of [/location/, /not the full diagnostic criteria/, /age and vascular risk/, /older adults/,
                        /can be met in people with vascular white matter disease/, /not evidence of multiple sclerosis/, /case as a whole/]) {
      expect(DIS_INTERPRETATION_EN).toMatch(part);
    }
    expect(DIS_INTERPRETATION_EN).not.toMatch(/\d|McDonald/);
  });
});

describe('RC-133 lesions under 3 mm do not count toward DIS (paper 1)', () => {
  it('rc133 the number of lesions below the size is shown', async () => {
    await showResult(evaluated(false, 2));
    expect(screen.getByTestId('dis-below-size')).toHaveTextContent(
      BELOW_SIZE_EN.replace('{{count}}', '2'));
  });

  it('rc133 no below-size line when every lesion counts', async () => {
    await showResult(evaluated(true, 0));
    expect(screen.queryByTestId('dis-below-size')).not.toBeInTheDocument();
  });

  it('rc133 the per-region count is described by the MAGNIMS size, not "size/location criteria"', async () => {
    await showResult(evaluated(true));
    const counts = screen.getAllByTitle(QUALIFYING_TOOLTIP_EN);
    expect(counts.length).toBeGreaterThan(0);
    expect(QUALIFYING_TOOLTIP_EN).toMatch(/3 mm in their largest extent, measured between voxel centres/);
    expect(QUALIFYING_TOOLTIP_EN).not.toMatch(/size\/location criteria/);
  });
});

describe('the three languages hold the texts', () => {
  const dir = path.resolve(__dirname, '../i18n/locales');
  const read = (lang: string) => JSON.parse(fs.readFileSync(path.join(dir, `${lang}.json`), 'utf8'));

  it('en equals the component defaults; es and de have every key, the count placeholder and no digit in the statement', () => {
    const en = read('en').lesions;
    expect(en.disInterpretation).toBe(DIS_INTERPRETATION_EN);
    expect(en.qualifyingLesionsTooltip).toBe(QUALIFYING_TOOLTIP_EN);
    expect(en.belowSizeNotCounted).toBe(BELOW_SIZE_EN);
    for (const lang of ['es', 'de']) {
      const l = read(lang).lesions;
      expect(l.disInterpretation, lang).toBeTruthy();
      expect(l.disInterpretation, lang).not.toMatch(/\d/);
      expect(l.qualifyingLesionsTooltip, lang).toMatch(/3 mm/);
      expect(l.belowSizeNotCounted, lang).toContain('{{count}}');
    }
  });
});
