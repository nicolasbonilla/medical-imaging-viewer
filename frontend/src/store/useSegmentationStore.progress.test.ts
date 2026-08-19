import { describe, it, expect, beforeEach } from 'vitest';
import { useSegmentationStore } from './useSegmentationStore';
import { DEFAULT_LABEL_PRESETS } from '@/types';
import type { Segmentation, SegmentationResponse } from '@/types';

/**
 * Regression tests for the two data-loss bugs the adversarial design/refute surfaced:
 *  (1) the sync effect re-seeded activeLabel/labelVisibility on every progress re-fire
 *      (after load/save), silently resetting the user's active label + visibility;
 *  (2) a label-preset change lived only on the derived activeSegmentation and was lost
 *      on the next re-sync and never saved (save reads currentSegmentation.metadata.labels).
 */

const seg = (labels = DEFAULT_LABEL_PRESETS.default): Segmentation => ({
  id: 'seg-1',
  patient_id: '',
  study_id: '',
  series_id: '',
  file_id: 'f1',
  name: 'S',
  segmentation_type: 'manual',
  status: 'in_progress',
  progress_percentage: 0,
  slices_annotated: 0,
  total_slices: 10,
  created_by: 'u',
  labels,
  created_at: '',
  modified_at: '',
});

const response = (labels = DEFAULT_LABEL_PRESETS.default): SegmentationResponse => ({
  segmentation_id: 'seg-1',
  file_id: 'f1',
  total_slices: 10,
  masks: null,
  metadata: {
    file_id: 'f1',
    created_at: '',
    modified_at: '',
    labels,
    description: 'S',
  },
} as unknown as SegmentationResponse);

describe('useSegmentationStore — progress update preserves editing state', () => {
  beforeEach(() => {
    useSegmentationStore.setState({
      currentSegmentation: null, activeSegmentation: null,
      activeLabel: 1, labelVisibility: {}, isDirty: false,
    });
  });

  it('updateActiveSegmentationProgress preserves activeLabel / labelVisibility / isDirty', () => {
    const s = useSegmentationStore.getState();
    s.setActiveSegmentation(seg()); // seeds activeLabel + labelVisibility
    // user selects a non-default label, hides one, and dirties the mask
    useSegmentationStore.setState({ activeLabel: 2, labelVisibility: { 0: false, 1: true, 2: false }, isDirty: true });

    useSegmentationStore.getState().updateActiveSegmentationProgress({
      slices_annotated: 5, total_slices: 10, progress_percentage: 50,
    });

    const after = useSegmentationStore.getState();
    expect(after.activeSegmentation?.slices_annotated).toBe(5);
    expect(after.activeSegmentation?.progress_percentage).toBe(50);
    // The whole point: these survive a progress re-fire (setActiveSegmentation would reset them)
    expect(after.activeLabel).toBe(2);
    expect(after.labelVisibility[2]).toBe(false);
    expect(after.isDirty).toBe(true);
  });

  it('setActiveSegmentation (a genuine new-mask seed) DOES reset the active label — contrast', () => {
    useSegmentationStore.setState({ activeLabel: 2, isDirty: true });
    useSegmentationStore.getState().setActiveSegmentation(seg());
    const after = useSegmentationStore.getState();
    expect(after.activeLabel).toBe(1);   // reset to first non-bg label
    expect(after.isDirty).toBe(false);   // fresh seed is clean
  });

  it('setLabelPreset writes the canonical currentSegmentation.metadata.labels (so it saves)', () => {
    useSegmentationStore.setState({
      currentSegmentation: response(DEFAULT_LABEL_PRESETS.default),
      activeSegmentation: seg(DEFAULT_LABEL_PRESETS.default),
    });

    useSegmentationStore.getState().setLabelPreset('magnims');

    const after = useSegmentationStore.getState();
    // canonical metadata now carries the preset — this is what save() reads
    expect(after.currentSegmentation?.metadata?.labels).toEqual(DEFAULT_LABEL_PRESETS.magnims);
    // and the derived active copy agrees
    expect(after.activeSegmentation?.labels).toEqual(DEFAULT_LABEL_PRESETS.magnims);
    expect(after.isDirty).toBe(true);
  });
});
