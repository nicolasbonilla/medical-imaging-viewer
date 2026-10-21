/**
 * FLAMeS in-browser inference plan (PROTOTYPE, behind VITE_ENABLE_BROWSER_FLAMES).
 *
 * Every value below is transcribed from the trained model's own nnU-Net v2 files,
 * NOT re-tuned: Zenodo record 17955359 v2.0 ("FLAMeS: FLAIR Lesion Analysis in
 * Multiple Sclerosis", CC BY 4.0), archive Dataset004_WML.zip
 * (md5 8b90b789d6ceca1886f42fa1724a08cc), folder
 * nnUNetTrainer_8000epochs__nnUNetPlans__3d_fullres/{plans.json,dataset.json,fold_0/debug.json}.
 * See docs/research/flames-in-browser/DESIGN.md §3 for the derivation and
 * research/flames_in_browser/ for the scripts that read them.
 *
 * Axis convention used throughout this module ("network order"):
 *   nnU-Net reads the NIfTI with SimpleITK -> C-order array (k, j, i) (no reorientation),
 *   then applies plans.transpose_forward = [2, 0, 1] -> (i, k, j).
 *   So network axis 0 = NIfTI i (dim[1]), axis 1 = NIfTI k (dim[3]), axis 2 = NIfTI j (dim[2]).
 *   targetSpacing and patchSize are expressed in THIS order.
 */

export const FLAMES_PLAN = Object.freeze({
  datasetName: 'Dataset004_WML',
  trainer: 'nnUNetTrainer_8000epochs__nnUNetPlans__3d_fullres',
  /** dataset.json overwrite_image_reader_writer */
  imageReader: 'SimpleITKIO',
  /** plans.json transpose_forward / transpose_backward */
  transposeForward: Object.freeze([2, 0, 1]) as readonly [number, number, number],
  transposeBackward: Object.freeze([1, 2, 0]) as readonly [number, number, number],
  /** configurations.3d_fullres.spacing (network order, mm). Kept at float32 precision as in plans.json. */
  targetSpacing: Object.freeze([1.0, 0.9000000059604645, 0.9000000059604645]) as readonly [number, number, number],
  /** configurations.3d_fullres.patch_size (network order, voxels) */
  patchSize: Object.freeze([112, 128, 160]) as readonly [number, number, number],
  /** nnUNetPredictor default tile_step_size */
  tileStepSize: 0.5,
  /** nnU-Net compute_gaussian sigma_scale */
  gaussianSigmaScale: 1 / 8,
  /** ZScoreNormalization with use_mask_for_norm = true */
  normalization: 'ZScoreNormalization',
  useMaskForNorm: true,
  /** resampling_fn_data_kwargs: order 3, order_z 0, force_separate_z null */
  dataResampleOrder: 3,
  /** resampling_fn_probabilities_kwargs: order 1, order_z 0 */
  logitResampleOrder: 1,
  resampleOrderZ: 0,
  /** nnU-Net ANISO_THRESHOLD */
  anisotropyThreshold: 3,
  /** labels: background 0, Lesion 1 */
  numClasses: 2,
  /** debug.json inference_allowed_mirroring_axes (network order). TTA is OFF by default here. */
  mirrorAxes: Object.freeze([0, 1, 2]) as readonly number[],
});

/**
 * Pinned model artefact. The ONNX file is NOT committed to git (61.6 MB); it is
 * produced by research/flames_in_browser/export_onnx.py from the Zenodo fold-0
 * checkpoint (sha256 4fc7db24…3fdf861) and hosted next to the app (DESIGN.md §6).
 * The worker refuses to run a model whose SHA-256 differs from this value.
 */
export interface FlamesModelAsset {
  url: string;
  sha256: string;
  bytes: number;
  fold: number;
  sourceCheckpointSha256: string;
  inputName: string;
  outputName: string;
}

export const FLAMES_FOLD0_CHECKPOINT_SHA256 =
  '4fc7db24e7c1541b59023df2a2f498a964eb629fe38f4eaec763297dd3fdf861';

/**
 * Fold 0 exported on 2026-10-17 by research/flames_in_browser/export_onnx.py (torch 2.14.1, opset 17).
 * Its logits are bit-identical to Neurodesk's independently published flames-fold0.onnx
 * (sha256 fe21c420…, differs only in the producer-version metadata), see DESIGN.md §5.
 * Default URL: same-origin Firebase Hosting path, content-addressed so it can be cached immutably.
 */
export const FLAMES_FOLD0_MODEL: FlamesModelAsset = Object.freeze({
  url: '/models/flames/flames-fold0-2a10bb9d.onnx',
  sha256: '2a10bb9d72dc33381a3f44dd6a59ec612dfd87534e02f15488b426ae127176ae',
  bytes: 61642305,
  fold: 0,
  sourceCheckpointSha256: FLAMES_FOLD0_CHECKPOINT_SHA256,
  inputName: 'input',
  outputName: 'logits',
});

/** Bumped whenever pipeline arithmetic changes; stored in every result's provenance. */
export const FLAMES_PIPELINE_VERSION = 'mstool-flames-browser/0.1.0-prototype';
