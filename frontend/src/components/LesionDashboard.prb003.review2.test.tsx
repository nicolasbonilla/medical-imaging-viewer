/**
 * PRB-003 — findings of the second independent review of PR #68 at 29abe29, on the viewer side (written BEFORE the
 * corrections; they fail on 29abe29).
 *
 *  - N1: a region changed by hand after the classification was trusted silently (`edited_after_classification` was
 *    computed but never shown). The card now lists the lesions that carry no region or more than one, lists the
 *    region corrections, and the confirmation requires an explicit acknowledgement of exactly these corrections
 *    (checkbox in the card, listed again in the confirm dialog, their digest sent with the confirmation);
 *  - N5: for a role that does not see who confirmed, the card says "confirmed by a radiologist".
 */
import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const getDISAssessment = vi.fn();
const analyzeLesions = vi.fn();
const confirmSegmentationReview = vi.fn();
const getSegmentation = vi.fn();
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    getDISAssessment: (...a: unknown[]) => getDISAssessment(...a),
    analyzeLesions: (...a: unknown[]) => analyzeLesions(...a),
    confirmSegmentationReview: (...a: unknown[]) => confirmSegmentationReview(...a),
    getSegmentation: (...a: unknown[]) => getSegmentation(...a),
    classifyRegions: vi.fn(),
    annotateLesions: vi.fn(),
    confirmAiReview: vi.fn(),
  },
}));
vi.mock('sonner', () => ({ toast: { loading: vi.fn(), success: vi.fn(), error: vi.fn() } }));

import { LesionDashboard } from './LesionDashboard';
import { useSegmentationStore } from '@/store/useSegmentationStore';

const DIGEST = 'ab'.repeat(32);
const CORRECTIONS = 'cd'.repeat(32);

const ANALYSIS = {
  segmentation_id: 'seg-1',
  lesions: [
    { id: 1, label_id: 1, region: 'Periventricular', voxel_count: 12, volume_mm3: 36, volume_ml: 0.036,
      size_category: 'small', centroid: { z: 3, y: 3, x: 3 }, bounding_box: {} },
  ],
  total_count: 1, total_burden_mm3: 36, total_burden_ml: 0.036,
  regions: { Periventricular: { lesion_count: 1, total_volume_mm3: 36, total_volume_ml: 0.036 } },
  size_distribution: { small: 1, medium: 0, large: 0 }, unique_labels: [1],
};

const REGIONS_BASE = { classified: true, label_scheme: 'magnims', method: 'geometric', lesion_count: 2,
  lesions_valid: true, invalid_lesions: [], invalid_lesion_count: 0, corrections: [], correction_count: 0,
  corrections_sha256: 'ee'.repeat(32), listed_limit: 100, edited_after_classification: false };

const CORRECTION = { lesion: 2, slice: 6, first_voxel: [6, 12, 12], voxels: 18, classified_region: 2,
  classified_region_name: 'Juxtacortical', current_region: 1, current_region_name: 'Periventricular' };

const notEvaluated = (reason: string, regions: Record<string, unknown>) => ({
  segmentation_id: 'seg-1', evaluation_status: 'not_evaluated', not_evaluated_reason: reason,
  message: 'Not evaluated: requires clinician review of the segmentation.', dis_criteria_version: 'McDonald 2024',
  segmentation_review: { status: 'unconfirmed', source: 'origin_not_recorded', reviewed_by: null, reviewed_at: null,
                         reviewed_mask_sha256: null, current_mask_sha256: DIGEST },
  regions: { ...REGIONS_BASE, ...regions },
});

const WITH_CORRECTION = notEvaluated('segmentation_not_confirmed', {
  edited_after_classification: true, corrections: [CORRECTION], correction_count: 1, corrections_sha256: CORRECTIONS });

const evaluated = (reviewedBy: string | null, corrections = 0) => ({
  segmentation_id: 'seg-1', evaluation_status: 'evaluated', dis_met_brain: true, dis_met: true,
  dis_criteria_version: 'McDonald 2024', brain_regions_with_lesions: 2, brain_regions_evaluated: 3,
  total_dis_regions: 5, total_topographies_involved: 2, dis_met_full: true, dit_waiver_supported: false,
  supportive_specificity_markers: { central_vein_sign: null, paramagnetic_rim_lesion: null, csf_specific: null },
  specificity_marker_present: false, external_evidence_provided: false, decision_support_note: '', note: '',
  region_details: { Periventricular: { label_id: 1, present: true, voxel_count: 12, qualifying_lesion_count: 1 } },
  dwm_lesion_count: 0, dwm_voxels: 0, has_active_lesions: false, has_black_holes: false, active_voxels: 0,
  black_hole_voxels: 0,
  segmentation_review: { status: 'confirmed', source: 'origin_not_recorded', reviewed_by: reviewedBy,
                         reviewed_by_role: 'radiologist', reviewed_at: '2026-10-24T10:00:00Z',
                         reviewed_mask_sha256: DIGEST, current_mask_sha256: DIGEST },
  regions: { ...REGIONS_BASE, correction_count: corrections, corrections: corrections ? [CORRECTION] : [] },
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
  for (const f of [getDISAssessment, analyzeLesions, confirmSegmentationReview, getSegmentation]) f.mockReset();
  analyzeLesions.mockResolvedValue(ANALYSIS);
  getSegmentation.mockResolvedValue({ segmentation_id: 'seg-1', metadata: {} });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('N1: one region per lesion; region corrections are listed and acknowledged', () => {
  it('rc070 review2 a lesion with no region or two regions is listed and no confirmation is offered', async () => {
    seed();
    getDISAssessment.mockResolvedValue(notEvaluated('lesion_labels_invalid', {
      lesions_valid: false, invalid_lesion_count: 1, edited_after_classification: true,
      invalid_lesions: [{ lesion: 1, slice: 2, first_voxel: [2, 2, 2], voxels: 144, labels: [1, 2],
                          label_names: ['Periventricular', 'Juxtacortical'] }] }));
    render(<LesionDashboard segmentationId="seg-1" />);
    const card = await analyze();
    expect(screen.getByTestId('dis-lesion-labels-invalid')).toHaveTextContent(/exactly one region/);
    expect(screen.getByTestId('dis-invalid-lesion')).toHaveTextContent('Lesion 1 (slice 3, 144 voxels): Periventricular + Juxtacortical');
    expect(card).toHaveTextContent(/changed by hand after the region classification/);
    expect(screen.queryByRole('button', { name: /confirm this segmentation/ })).not.toBeInTheDocument();
  });

  it('rc071 review2 the corrections are listed and the confirmation waits for their acknowledgement', async () => {
    seed();
    getDISAssessment.mockResolvedValue(WITH_CORRECTION);
    render(<LesionDashboard segmentationId="seg-1" />);
    await analyze();
    expect(screen.getByTestId('dis-edited-after-classification')).toBeInTheDocument();
    expect(screen.getByTestId('dis-region-correction')).toHaveTextContent('Lesion 2 (slice 7, 18 voxels): Juxtacortical → Periventricular');
    const button = screen.getByRole('button', { name: /confirm this segmentation/ });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(confirmSegmentationReview).not.toHaveBeenCalled();
  });

  it('rc071 review2 acknowledged corrections are listed in the dialog and their digest is sent', async () => {
    seed();
    getDISAssessment.mockResolvedValue(WITH_CORRECTION);
    confirmSegmentationReview.mockResolvedValue({ reviewed_by: 'dr_rev', reviewed_at: 'x', reviewed_mask_sha256: DIGEST });
    render(<LesionDashboard segmentationId="seg-1" />);
    await analyze();
    fireEvent.click(screen.getByTestId('dis-ack-corrections'));
    const button = screen.getByRole('button', { name: /confirm this segmentation/ });
    expect(button).not.toBeDisabled();
    fireEvent.click(button);
    await waitFor(() => expect(confirmSegmentationReview).toHaveBeenCalledWith('seg-1', DIGEST, CORRECTIONS));
    expect(window.confirm).toHaveBeenCalledWith(
      expect.stringMatching(/region correction\(s\)[\s\S]*Lesion 2 \(slice 7, 18 voxels\): Juxtacortical → Periventricular/));
  });

  it('rc070 review2 an evaluated result says it includes acknowledged corrections', async () => {
    seed();
    getDISAssessment.mockResolvedValue(evaluated('dr_rev', 1));
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    expect(await screen.findByTestId('dis-confirmed-corrections')).toHaveTextContent(/1 region correction/);
  });
});

describe('N5: who confirmed', () => {
  it('rc071 review2 without the confirmer name (other roles) the card says a radiologist confirmed', async () => {
    seed();
    getDISAssessment.mockResolvedValue(evaluated(null));
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    expect(await screen.findByTestId('dis-confirmed-by')).toHaveTextContent('Segmentation confirmed by a radiologist');
  });
});
