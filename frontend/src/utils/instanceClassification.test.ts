import { describe, it, expect } from 'vitest';
import { isPreprocessedInstance } from './instanceClassification';

describe('isPreprocessedInstance', () => {
  it('detects the legacy _pp suffix', () => {
    expect(isPreprocessedInstance('test01_01_flair_pp.nii')).toBe(true);
    expect(isPreprocessedInstance('test01_01_flair_pp.nii.gz')).toBe(true);
  });

  it('detects BIDS preproc derivatives', () => {
    expect(isPreprocessedInstance('sub-MS001_ses-01_desc-preproc_FLAIR.nii.gz')).toBe(true);
    expect(isPreprocessedInstance('sub-MS001_desc-segfrompreproc_dseg.nii.gz')).toBe(true);
  });

  it('is case-insensitive', () => {
    expect(isPreprocessedInstance('SUB_DESC-PREPROC_FLAIR.NII.GZ')).toBe(true);
    expect(isPreprocessedInstance('SCAN_PP.NII')).toBe(true);
  });

  it('returns false for original / non-preprocessed images', () => {
    expect(isPreprocessedInstance('sub-MS001_ses-01_FLAIR.nii.gz')).toBe(false);
    expect(isPreprocessedInstance('test01_01_flair.nii')).toBe(false);
    expect(isPreprocessedInstance('report_pp.pdf')).toBe(false); // _pp but not .nii
    expect(isPreprocessedInstance('')).toBe(false);
  });
});
