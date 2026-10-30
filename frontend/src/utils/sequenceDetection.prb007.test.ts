/**
 * PRB-007 — filling the multi-panel grid from the images a study has.
 *
 * autoAssignPanels picked one image per sequence (FLAIR, T1w, T2w, PDw) and filled the rest only with
 * images of unknown sequence. A study with T1w and T1w-after-contrast (both "T1w") left a panel empty
 * although an image was available. Required: the grid takes one image per sequence first, in the
 * usual order, then the remaining images in study order, up to the number of panels.
 */
import { describe, it, expect } from 'vitest';
import { autoAssignPanels } from './sequenceDetection';
import type { ImagingInstance } from '@/types';

const inst = (id: string, name: string) => ({ id, original_filename: name }) as unknown as ImagingInstance;

describe('PRB-007 — autoAssignPanels fills every panel it can', () => {
  it('prb007 four images, two of them T1-weighted: four panels, sequences first', () => {
    const got = autoAssignPanels([
      inst('t1ce', 'sub-13_ce-gad_desc-preproc_T1w.nii.gz'),
      inst('flair', 'sub-13_desc-preproc_FLAIR.nii.gz'),
      inst('t1', 'sub-13_desc-preproc_T1w.nii.gz'),
      inst('t2', 'sub-13_desc-preproc_T2w.nii.gz'),
    ]);
    expect(got.map((a) => a.instance.id)).toEqual(['flair', 't1ce', 't2', 't1']);
    expect(got.map((a) => a.sequence)).toEqual(['FLAIR', 'T1w', 'T2w', 'T1w']);
  });

  it('prb007 never more than four, never the same image twice', () => {
    const got = autoAssignPanels([
      inst('a', 'x_FLAIR.nii.gz'), inst('b', 'y_FLAIR.nii.gz'), inst('c', 'z_FLAIR.nii.gz'),
      inst('d', 'w_FLAIR.nii.gz'), inst('e', 'v_FLAIR.nii.gz'),
    ]);
    expect(got.map((a) => a.instance.id)).toEqual(['a', 'b', 'c', 'd']);
  });

  it('prb007 guard: one image per sequence keeps the canonical order, unknowns last', () => {
    const got = autoAssignPanels([
      inst('u', 'scan.nii.gz'), inst('t2', 'a_T2w.nii.gz'), inst('fl', 'a_FLAIR.nii.gz'), inst('t1', 'a_T1w.nii.gz'),
    ]);
    expect(got.map((a) => a.instance.id)).toEqual(['fl', 't1', 't2', 'u']);
  });
});
