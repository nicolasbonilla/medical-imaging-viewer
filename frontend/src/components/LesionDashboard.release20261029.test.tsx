/**
 * Release 2026-10-25 — final check of PR #69 (dd22708..39d9730), majors R1 and R2 of the confirmation guard.
 *
 *  - R1: the guard read the 2D canvas settings, not the view on screen. With "Segmentation mode" off, in the
 *    multi-panel, 3D, NiiVue or matplotlib views nothing (or plain red, or a pre-classification mask) is drawn, and
 *    Confirm was still accepted. Now the confirmation needs the standard 2D view, in segmentation mode, drawing THIS
 *    segmentation (`overlayOnScreen`, published by that view) — otherwise it is refused, saying how to get there.
 *  - R2: switching the label preset to "Default" redrew the MAGNIMS values with other names and colours (juxtacortical
 *    lesions gold as "MS Lesion (Chronic)") and Confirm was still accepted. On a classified segmentation every value
 *    present must be drawn with the label the server stored for it (same id, name and colour: `regions.stored_labels`
 *    of the DIS state); the confirmation sends the drawn label table, which the server checks too.
 *
 * Written before the corrections (they fail on 39d9730; the positive control too: the call now carries the drawn
 * label table).
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
const ANALYSIS = {
  segmentation_id: 'seg-1',
  lesions: [{ id: 1, label_id: 1, region: 'Periventricular', voxel_count: 12, volume_mm3: 36, volume_ml: 0.036,
    size_category: 'small', centroid: { z: 3, y: 3, x: 3 }, bounding_box: {} }],
  total_count: 1, total_burden_mm3: 36, total_burden_ml: 0.036,
  regions: { Periventricular: { lesion_count: 1, total_volume_mm3: 36, total_volume_ml: 0.036 } },
  size_distribution: { small: 1, medium: 0, large: 0 }, unique_labels: [1],
};
const STORED = MAGNIMS_LESION_LABELS.filter((l) => l.id !== 0).map(({ id, name, color }) => ({ id, name, color }));
const notConfirmed = (storedLabels: unknown = STORED) => ({
  segmentation_id: 'seg-1', evaluation_status: 'not_evaluated', not_evaluated_reason: 'segmentation_not_confirmed',
  message: 'Not evaluated: requires clinician review of the segmentation.', dis_criteria_version: 'McDonald 2024',
  segmentation_review: { status: 'unconfirmed', source: 'origin_not_recorded', reviewed_by: null, reviewed_at: null,
    reviewed_mask_sha256: null, current_mask_sha256: DIGEST },
  regions: { classified: true, label_scheme: 'magnims', removed_small_components: null,
    ...(storedLabels === undefined ? {} : { stored_labels: storedLabels }) },
});

/** Segmentation "seg-1" is open, drawn with its MAGNIMS labels in the standard 2D view (unless overridden). */
function seedOpen(over: Record<string, unknown> = {}) {
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
    maskValuesCallback: vi.fn(() => [1, 2, 3, 4]),
    hasUnsavedMaskChanges: false,
    reloadMaskCallback: vi.fn(async () => true),
    overlayOnScreen: 'seg-1',
    ...over,
  } as never);
}

async function pressConfirm() {
  render(<LesionDashboard segmentationId="seg-1" />);
  fireEvent.click(await screen.findByRole('button', { name: /confirm this segmentation/ }));
}

beforeEach(() => {
  for (const f of [getDISAssessment, analyzeLesions, confirmSegmentationReview]) f.mockReset();
  getDISAssessment.mockResolvedValue(notConfirmed());
  analyzeLesions.mockResolvedValue(ANALYSIS);
  confirmSegmentationReview.mockResolvedValue({ reviewed_by: 'dr_rev', reviewed_at: 'x', reviewed_mask_sha256: DIGEST });
  vi.restoreAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('R1: Confirm only while the view on screen draws this segmentation with its region labels', () => {
  it.each([
    ['segmentation mode off, multi-panel, 3D, NiiVue or matplotlib view (nothing published)', null],
    ['the standard view draws another segmentation', 'seg-2'],
  ])('rc071 release final r1 refused: %s', async (_name, onScreen) => {
    seedOpen({ overlayOnScreen: onScreen });
    await pressConfirm();
    expect(await screen.findByTestId('dis-confirm-refused'))
      .toHaveTextContent(/Switch to the Standard view .*Segmentation mode on to confirm/);
    expect(window.confirm).not.toHaveBeenCalled();
    expect(confirmSegmentationReview).not.toHaveBeenCalled();
  });
});

describe('R2: each value present is drawn with the label the server stored for it', () => {
  it('rc071 release final r2 refused after switching the label preset to Default', async () => {
    seedOpen();
    useSegmentationStore.getState().setLabelPreset('default');                // the reviewer's path
    useSegmentationStore.setState({ hasUnsavedMaskChanges: false } as never);
    await pressConfirm();
    const refusal = await screen.findByTestId('dis-confirm-refused');
    expect(refusal).toHaveTextContent(/value 2 is drawn as "MS Lesion \(Chronic\)".*"Juxtacortical"/);
    expect(window.confirm).not.toHaveBeenCalled();
    expect(confirmSegmentationReview).not.toHaveBeenCalled();
  });

  it('rc071 release final r2 refused when one colour differs from the stored label', async () => {
    seedOpen({ activeSegmentation: { id: 'seg-1', labels: MAGNIMS_LESION_LABELS.map((l) => (l.id === 3 ? { ...l, color: '#FFD700' } : l)) } });
    await pressConfirm();
    expect(await screen.findByTestId('dis-confirm-refused')).toHaveTextContent(/value 3 is drawn as "Infratentorial"/);
    expect(confirmSegmentationReview).not.toHaveBeenCalled();
  });

  it('rc071 release final r2 refused when the stored labels could not be read', async () => {
    getDISAssessment.mockResolvedValue(notConfirmed(undefined));
    seedOpen();
    await pressConfirm();
    expect(await screen.findByTestId('dis-confirm-refused')).toHaveTextContent(/stored for this segmentation could not be read/);
    expect(confirmSegmentationReview).not.toHaveBeenCalled();
  });

  it('rc071 release final drawn with the stored labels in the standard view: confirmed, with the drawn table (positive control)', async () => {
    seedOpen();
    await pressConfirm();
    await waitFor(() => expect(confirmSegmentationReview).toHaveBeenCalledWith('seg-1', DIGEST, null, MAGNIMS_LESION_LABELS));
    expect(screen.queryByTestId('dis-confirm-refused')).not.toBeInTheDocument();
  });
});
