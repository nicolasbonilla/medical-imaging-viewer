/**
 * Licence and attribution notices shown to the end user wherever the in-browser FLAMeS model is used
 * (BrowserFlamesCard "Licences and attribution"). Source of truth for the long form: ./NOTICE.md;
 * full licence texts are served from /licenses/ (public/licenses/).
 */
export interface ThirdPartyNotice {
  component: string;
  licence: string;
  licenceUrl: string;
  attribution: string;
  changes?: string;
}

export const FLAMES_NOTICES: readonly ThirdPartyNotice[] = Object.freeze([
  {
    component: 'FLAMeS model weights, version 2.0 (fold 0)',
    licence: 'CC BY 4.0',
    licenceUrl: 'https://creativecommons.org/licenses/by/4.0/',
    attribution:
      'FLAMeS: FLAIR Lesion Analysis in Multiple Sclerosis, v2.0. La Rosa F. et al. Zenodo, doi:10.5281/zenodo.17955359 ' +
      '(record 17955359). Dereskewicz E, La Rosa F, dos Santos Silva J, et al. J Neuroimaging 2025;35(5):e70085, ' +
      'doi:10.1111/jon.70085.',
    changes:
      'Converted by MSTool-AI from the PyTorch checkpoint to ONNX (transposed convolutions rewritten as 1x1x1 ' +
      'convolution + depth-to-space; weights stored as float16). Not retrained.',
  },
  {
    component: 'Neurodesk webapps — white-matter-lesions (portions ported to TypeScript)',
    licence: 'Apache-2.0',
    licenceUrl: '/licenses/Apache-2.0.txt',
    attribution: 'https://github.com/neurodesk/webapps (packages/white-matter-lesions, apps/white-matter-lesions/scripts/export_model.py).',
    changes:
      'Ported to TypeScript and modified by MSTool-AI (2026-10-17): nnU-Net rounding, hole-filled nonzero mask, logits ' +
      'resampled before argmax, no input pre-downsampling, fail-closed gates.',
  },
  {
    component: 'nnU-Net v2 (algorithm re-implemented; no source shipped)',
    licence: 'Apache-2.0',
    licenceUrl: '/licenses/Apache-2.0.txt',
    attribution: 'Isensee F. et al. Nature Methods 2021;18:203-211. https://github.com/MIC-DKFZ/nnUNet (DKFZ).',
  },
  {
    component: 'ONNX Runtime Web',
    licence: 'MIT',
    licenceUrl: '/licenses/onnxruntime-web-MIT.txt',
    attribution: 'Copyright (c) Microsoft Corporation. https://github.com/microsoft/onnxruntime',
  },
]);
