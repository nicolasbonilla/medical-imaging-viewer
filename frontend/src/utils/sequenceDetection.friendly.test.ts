import { describe, expect, it } from 'vitest';
import { distinctImageNames, friendlyImageName } from './sequenceDetection';

describe('friendlyImageName (review of the skull-strip branch, B3 and M1)', () => {
  it.each([
    ['sub-MS011_ses-01_FLAIR.nii.gz', 'FLAIR'],
    ['sub-MS011_ses-01_acq-MPRAGE_T1w.nii.gz', 'T1 · MPRAGE'],
    ['sub-MS011_ses-01_T2w.nii.gz', 'T2'],
    ['sub-MS011_ses-01_PDw.nii.gz', 'PD'],
    ['sub-13_ce-gad_T1w.nii.gz', 'T1 · after contrast (gad)'],
    ['sub-13_space-MNI_ce-gad_desc-preproc_T1w.nii.gz', 'T1 · after contrast (gad) · MNI space (preprocessed)'],
    ['sub-13_space-MNI_desc-preproc_T1w.nii.gz', 'T1 · MNI space (preprocessed)'],
    ['sub-01_ses-01_label-lesion_rater-2_mask.nii.gz', 'Expert lesions 2'],
  ])('%s reads as %s', (file, name) => expect(friendlyImageName(file)).toBe(name));

  it.each([
    'sub-01_space-FLAIR_T1w.nii.gz',
    'sub-01_T1w_to_FLAIR.nii.gz',
    'sub-01_T2w_in_FLAIR_space.nii.gz',
  ])('never calls %s a FLAIR', (file) => expect(friendlyImageName(file)).not.toMatch(/^FLAIR/));

  it.each([
    'sub-01_FLAIR_mask.nii.gz', 'sub-01_T1w_brainmask.nii.gz', 'sub-01_lesion_mask_lst-ai.nii.gz', 'ai_lesion_mask.nii.gz',
    'sub-01_flames_lesion_seg.nii.gz', 'lesion_mask_20240115.nii.gz', 'sub-01_ses-01_label-lesion_mask1.nii.gz', 'scan_0042.nii.gz',
    'test01_flair_pp.nii',
  ])('shows %s as it is: no sequence or author the name does not state', (file) => expect(friendlyImageName(file)).toBe(file));

  it('two images that would read the same show their full names', () => {
    expect(distinctImageNames(['sub-01_ses-01_FLAIR.nii.gz', 'sub-01_ses-02_FLAIR.nii.gz', 'sub-01_T2w.nii.gz']))
      .toEqual(['sub-01_ses-01_FLAIR.nii.gz', 'sub-01_ses-02_FLAIR.nii.gz', 'T2']);
  });
});
