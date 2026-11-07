import { describe, expect, it } from 'vitest';
import { friendlyImageName } from './sequenceDetection';

describe('friendlyImageName', () => {
  it.each([
    ['sub-MS011_ses-01_FLAIR.nii.gz', 'FLAIR'],
    ['sub-MS011_ses-01_acq-MPRAGE_T1w.nii.gz', 'T1'],
    ['sub-MS011_ses-01_T2w.nii.gz', 'T2'],
    ['sub-MS011_ses-01_PDw.nii.gz', 'PD'],
    ['sub-MS011_ses-01_desc-preproc_FLAIR.nii', 'FLAIR (preprocessed)'],
    ['sub-MS011_ses-01_label-lesion_rater-2_mask.nii.gz', 'Expert lesions 2'],
    ['sub-MS011_ses-01_label-lesion_mask.nii.gz', 'Expert lesions'],
  ])('%s reads as %s', (file, name) => expect(friendlyImageName(file)).toBe(name));

  it('never gives a sequence to a name that does not say one', () => {
    expect(friendlyImageName('scan_0042.nii.gz')).toBe('scan_0042.nii.gz');
  });
});
