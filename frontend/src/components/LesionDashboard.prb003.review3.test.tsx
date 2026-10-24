/**
 * PRB-003 — finding m-1 of the third independent review of PR #68 at 2e20b8a, on the viewer side (written BEFORE the
 * correction; they fail on 2e20b8a). The lists of the DIS card name lesions as the lesion table does (its number and
 * slice); a component below the lesion-size floor, which the table leaves out, is named "Small component (N voxels,
 * slice S)"; a lesion carrying two labels is listed part by part.
 */
import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

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

import { LesionDashboard } from './LesionDashboard';
import { useSegmentationStore } from '@/store/useSegmentationStore';

const DIGEST = 'ab'.repeat(32);
const ANALYSIS = {
  segmentation_id: 'seg-1',
  lesions: [
    { id: 1, label_id: 1, region: 'Periventricular', voxel_count: 16, volume_mm3: 16, volume_ml: 0.016,
      size_category: 'small', centroid: { z: 5.4, y: 11, x: 11 }, bounding_box: {} },
    { id: 2, label_id: 4, region: 'Deep White Matter', voxel_count: 8, volume_mm3: 8, volume_ml: 0.008,
      size_category: 'small', centroid: { z: 1.5, y: 1.5, x: 1.5 }, bounding_box: {} },
  ],
  total_count: 2, total_burden_mm3: 26, total_burden_ml: 0.026,
  regions: {}, size_distribution: { small: 2, medium: 0, large: 0 }, unique_labels: [1, 2, 4],
};

const notEvaluated = (reason: string, regions: Record<string, unknown>) => ({
  segmentation_id: 'seg-1', evaluation_status: 'not_evaluated', not_evaluated_reason: reason,
  message: 'Not evaluated: requires clinician review of the segmentation.', dis_criteria_version: 'McDonald 2024',
  segmentation_review: { status: 'unconfirmed', source: 'origin_not_recorded', reviewed_by: null, reviewed_at: null,
                         reviewed_mask_sha256: null, current_mask_sha256: DIGEST },
  regions: { classified: true, label_scheme: 'magnims', lesion_count: 2, lesions_valid: true, invalid_lesions: [],
             invalid_lesion_count: 0, corrections: [], correction_count: 0, corrections_sha256: 'ee'.repeat(32),
             edited_after_classification: true, ...regions },
});

function seed() {
  useSegmentationStore.setState({
    currentSegmentation: {
      segmentation_id: 'seg-1', file_id: 'f.nii.gz', total_slices: 10,
      metadata: { file_id: 'f.nii.gz', created_at: 'T0', modified_at: 'T1', labels: [], analysis_data: null },
    } as any,
    maskDigestCallback: vi.fn().mockResolvedValue(DIGEST),
    hasUnsavedMaskChanges: false,
  });
}

async function analyze() {
  fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
  return screen.findByTestId('dis-not-evaluated');
}

beforeEach(() => {
  getDISAssessment.mockReset();
  analyzeLesions.mockReset();
  analyzeLesions.mockResolvedValue(ANALYSIS);
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('m-1: the DIS card names lesions as the lesion table does', () => {
  it('rc070 review3 a lesion with two labels is listed part by part, with the table number and small components', async () => {
    seed();
    getDISAssessment.mockResolvedValue(notEvaluated('lesion_labels_invalid', {
      lesions_valid: false, invalid_lesion_count: 1,
      invalid_lesions: [{
        lesion: 1, slice: 5, first_voxel: [5, 10, 10], voxels: 18, labels: [1, 2],
        label_names: ['Periventricular', 'Juxtacortical'],
        parts: [
          { lesion: 1, small_component: false, label: 1, label_name: 'Periventricular', voxels: 16, slice: 5 },
          { lesion: null, small_component: true, label: 2, label_name: 'Juxtacortical', voxels: 2, slice: 6 },
        ],
      }],
    }));
    render(<LesionDashboard segmentationId="seg-1" />);
    await analyze();
    const parts = screen.getAllByTestId('dis-invalid-lesion-part').map((el) => el.textContent);
    expect(parts).toEqual([
      'Lesion 1 (slice 6, 16 voxels): Periventricular',
      'Small component (2 voxels, slice 7): Juxtacortical',
    ]);
  });

  it('rc071 review3 a correction of a small component says so', async () => {
    seed();
    getDISAssessment.mockResolvedValue(notEvaluated('segmentation_not_confirmed', {
      correction_count: 1, corrections_sha256: 'cd'.repeat(32),
      corrections: [{ lesion: null, small_component: true, slice: 6, first_voxel: [6, 3, 3], voxels: 2,
                      classified_region: 2, classified_region_name: 'Juxtacortical', current_region: 1,
                      current_region_name: 'Periventricular' }],
    }));
    render(<LesionDashboard segmentationId="seg-1" />);
    await analyze();
    expect(screen.getByTestId('dis-region-correction'))
      .toHaveTextContent('Small component (2 voxels, slice 7): Juxtacortical → Periventricular');
  });
});
