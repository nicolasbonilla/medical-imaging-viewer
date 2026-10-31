/**
 * PRB-007 — independent review of PR #71 (m10): a segmentation derivative (`desc-segfrompreproc`, `_dseg`,
 * `_mask`) is classified "preprocessed" for the sidebar but is a mask, not an image: the grid must not show it
 * as a grey image.
 */
import { describe, it, expect } from 'vitest';
import { multiPanelImages } from './instanceClassification';

const inst = (name: string) => ({ id: name, original_filename: name });

describe('PRB-007 review — no masks in the grid', () => {
  it('prb007 segmentation derivatives are left out of the grid images', () => {
    const pre = [inst('sub-01_desc-preproc_FLAIR.nii.gz'), inst('sub-01_desc-segfrompreproc_dseg.nii.gz'),
      inst('sub-01_desc-preproc_T1w.nii.gz'), inst('sub-01_FLAIR_lesion_mask.nii.gz')];
    const { instances } = multiPanelImages('preprocessed', [], pre);
    expect(instances.map((i) => i.id)).toEqual(['sub-01_desc-preproc_FLAIR.nii.gz', 'sub-01_desc-preproc_T1w.nii.gz']);
  });
});
