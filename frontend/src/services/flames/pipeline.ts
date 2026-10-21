/**
 * In-browser FLAMeS pipeline (PROTOTYPE — feature flag VITE_ENABLE_BROWSER_FLAMES, default OFF).
 *
 * Pure function of (FLAIR voxels, geometry, injected network runner). No DOM, no ONNX import,
 * so it runs unchanged in a Web Worker, in vitest and in the Node parity harness.
 *
 * Steps (DESIGN.md §3; every step mirrors nnunetv2 2.8.1 with the FLAMeS plans):
 *   0. input gates (geometry, skull-stripped plausibility)            — fail closed
 *   1. NIfTI order -> network order (transpose_forward [2, 0, 1])
 *   2. crop_to_nonzero (nonzero mask, 3D hole filling, bbox)
 *   3. ZScoreNormalization inside the nonzero mask
 *   4. resample to 1.0 x 0.9 x 0.9 mm (order 3, separate-z when anisotropic > 3)
 *   5. sliding window 112x128x160, step 0.5, Gaussian weighting, optional mirroring
 *   6. resample the logits back to the cropped grid (order 1)
 *   7. argmax (lesion logit > background logit), paste into the bbox
 *   8. network order -> NIfTI order and -> app order (k, i, j) (RC-031)
 *   9. output gates (finite logits were checked per patch; plausible lesion burden) — fail closed
 */

import { FLAMES_PLAN } from './plan';
import { networkShape, networkSpacing, networkToApp, networkToNifti, niftiToNetwork, type Dims3 } from './axes';
import {
  boundingBox,
  computeNewShape,
  cropTo,
  nonzeroMaskFilled,
  product,
  resampleToShape,
  uncrop,
  zscoreInMask,
  type BoundingBox,
  type Shape3,
  type ZScoreStats,
} from './preprocess';
import { predictLogitDifference, type RunPatch } from './slidingWindow';
import { computeContrastFeatures, decideFlairContrast, type ContrastAssessment, type ContrastFeatures } from './contrastGate';
import type { HeaderEvidence } from './headerEvidence';
import { probabilityFromLogitDiff, summariseLesions, thresholdLogitDiff, type LesionSummary } from './postprocess';

/** Gate thresholds. Heuristics, documented as such in CHANGE-PROPOSAL.md (RC-042/RC-043); to be validated. */
export const GATES = Object.freeze({
  minSpacingMm: 0.1,
  maxSpacingMm: 6.0,
  minDim: 16,
  /** filled nonzero region of a skull-stripped adult brain, mL */
  minBrainMl: 500,
  maxBrainMl: 2600,
  /** fraction of voxels on the six faces of the FOV allowed to be nonzero (a stripped brain does not touch the FOV) */
  maxBorderNonzeroFraction: 0.02,
  /**
   * RC-043 skull clues (validated on public data, FLAIR-GATE-VALIDATION.md):
   * max share of very dark voxels (< 0.25 x tissue mode) inside the hole-filled nonzero region (headDarkFraction) …
   */
  maxHeadDarkFraction: 0.2,
  /** … and max share of very bright voxels (> 1.5 x tissue mode) within 6 mm of its edge (rimBrightFraction, scalp fat) */
  maxRimBrightFraction: 0.01,
  /** a lesion mask covering more than this fraction of the brain is treated as a failure, not a result */
  maxLesionFractionOfBrain: 0.25,
});

export class FlamesInputError extends Error {
  /** the contrast-gate measurements, when the refusal came from (or after) that gate */
  readonly contrast?: ContrastAssessment;
  constructor(message: string, contrast?: ContrastAssessment) {
    super(message);
    this.name = 'FlamesInputError';
    this.contrast = contrast;
  }
}

export interface FlamesVolume {
  /** NIfTI storage order (i fastest) */
  data: Float32Array;
  dims: Dims3;
  /** pixdim (mm) of i, j, k */
  spacing: Dims3;
}

export interface FlamesPipelineOptions {
  runPatch: RunPatch;
  /** optional brain mask in NIfTI order; voxels outside are set to 0 before nnU-Net's own cropping */
  brainMask?: Uint8Array;
  /** network axes for mirroring TTA. Default [] (no TTA, 8x faster). FLAMES_PLAN.mirrorAxes = nnU-Net default. */
  mirrorAxes?: readonly number[];
  /** enforce the skull-stripped plausibility gate (default true). Only unit tests on synthetic data disable it. */
  skullStripGate?: boolean;
  /** enforce the FLAIR contrast gate (default true). Only unit tests on synthetic data disable it. */
  contrastGate?: boolean;
  /** header evidence about the sequence (headerEvidence.ts); refuses, or counts as positive evidence */
  headerEvidence?: HeaderEvidence;
  /** RC-049 positive evidence: explicit clinician confirmation that the input is a skull-stripped T2-FLAIR */
  clinicianConfirmedFlair?: boolean;
  returnProbability?: boolean;
  onProgress?: (stage: string, fraction: number) => void;
  signal?: AbortSignal;
}

export interface FlamesPipelineResult {
  dims: Dims3;
  spacing: Dims3;
  /** binary lesion mask, NIfTI storage order */
  maskNifti: Uint8Array;
  /** binary lesion mask, app order (depth=k, height=i, width=j) — RC-031 internal convention */
  maskApp: Uint8Array;
  /** P(lesion), NIfTI order, only when returnProbability */
  probabilityNifti?: Float32Array;
  summary: LesionSummary;
  diagnostics: {
    networkShape: Shape3;
    networkSpacing: Shape3;
    bbox: BoundingBox;
    resampledShape: Shape3;
    windows: number;
    networkCalls: number;
    zscore: ZScoreStats;
    brainVolumeMl: number;
    borderNonzeroFraction: number;
    mirrorAxes: number[];
  };
}

export function borderNonzeroFraction(data: Float32Array, dims: Dims3): number {
  const [nx, ny, nz] = dims;
  let total = 0;
  let nonzero = 0;
  for (let k = 0; k < nz; k++) {
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        if (i !== 0 && j !== 0 && k !== 0 && i !== nx - 1 && j !== ny - 1 && k !== nz - 1) continue;
        total++;
        if (data[i + nx * (j + ny * k)] !== 0) nonzero++;
      }
    }
  }
  return total ? nonzero / total : 0;
}

export interface InputGateReport {
  borderNonzeroFraction: number;
  brainVolumeMl: number;
  contrast: ContrastAssessment | null;
}

/**
 * Input gates (fail closed, run BEFORE any inference): skull-stripped plausibility (RC-043) and the
 * FLAIR gate (RC-049, flair-gate/2: header and image content can only refuse; acceptance needs positive evidence).
 * Throws FlamesInputError with a user-readable reason; returns the measurements otherwise.
 */
export function checkInputGates(
  vol: FlamesVolume,
  opts: {
    skullStripGate?: boolean;
    contrastGate?: boolean;
    headerEvidence?: HeaderEvidence;
    /** RC-049 positive evidence: the clinician explicitly confirmed this file is a skull-stripped T2-FLAIR */
    clinicianConfirmedFlair?: boolean;
  } = {},
): InputGateReport {
  const { dims, spacing, data } = vol;
  const border = borderNonzeroFraction(data, dims);
  const nonzero = nonzeroMaskFilled(data, [dims[2], dims[1], dims[0]]);
  let brainVoxels = 0;
  for (let i = 0; i < nonzero.length; i++) brainVoxels += nonzero[i];
  const brainVolumeMl = (brainVoxels * spacing[0] * spacing[1] * spacing[2]) / 1000;

  if (opts.skullStripGate !== false) {
    if (border > GATES.maxBorderNonzeroFraction) {
      throw new FlamesInputError(
        `This image does not look skull-stripped: ${(border * 100).toFixed(1)}% of the image border is nonzero. ` +
          'FLAMeS requires a skull-stripped FLAIR; no segmentation was produced.',
      );
    }
    if (brainVolumeMl < GATES.minBrainMl || brainVolumeMl > GATES.maxBrainMl) {
      throw new FlamesInputError(
        `The nonzero region measures ${brainVolumeMl.toFixed(0)} mL, outside the plausible range for a ` +
          `skull-stripped adult brain (${GATES.minBrainMl}-${GATES.maxBrainMl} mL). No segmentation was produced.`,
      );
    }
  }

  let contrast: ContrastAssessment | null = null;
  if (opts.contrastGate !== false || opts.skullStripGate !== false) {
    const header = opts.headerEvidence ?? { verdict: 'none' as const, reasons: [] };
    let features: ContrastFeatures;
    try {
      features = computeContrastFeatures(data, dims, spacing);
    } catch (e) {
      throw new FlamesInputError(
        `The image could not be checked (${e instanceof Error ? e.message : String(e)}). No segmentation was produced.`,
      );
    }
    contrast = decideFlairContrast(features, header, { clinicianConfirmedFlair: opts.clinicianConfirmedFlair });
    const reasons: string[] = [];
    // RC-043: skull clues that also work when the background was set to zero and the head fits the
    // border/volume limits above: bright scalp fat at the edge of the region, or a large dark share
    // (bone, air, background noise enclosed by the head).
    if (opts.skullStripGate !== false) {
      if (features.rimBrightFraction > GATES.maxRimBrightFraction) {
        reasons.push(
          `This image does not look skull-stripped: ${(100 * features.rimBrightFraction).toFixed(1)}% of its outer 6 mm is ` +
            'very bright (scalp fat), as when the skull and scalp are still present.',
        );
      }
      if (features.darkFraction > GATES.maxHeadDarkFraction) {
        reasons.push(
          `This image does not look skull-stripped: ${(100 * features.darkFraction).toFixed(0)}% of the head region is ` +
            'very dark (bone, air or background).',
        );
      }
    }
    if (opts.contrastGate !== false && !contrast.ok) reasons.push(contrast.reason ?? 'The image does not look like a FLAIR.');
    if (reasons.length) {
      const tail = reasons.some((r) => /skull-stripped/.test(r)) ? ' FLAMeS requires a skull-stripped FLAIR.' : '';
      throw new FlamesInputError(
        `${reasons.join(' ')}${tail}${/no segmentation was produced/i.test(reasons.join(' ')) ? '' : ' No segmentation was produced.'}`,
        contrast,
      );
    }
  }
  return { borderNonzeroFraction: border, brainVolumeMl, contrast };
}

export function validateGeometry(vol: FlamesVolume): void {
  const { dims, spacing, data } = vol;
  if (data.length !== product(dims)) throw new FlamesInputError('Voxel count does not match the image dimensions.');
  if (dims.some((d) => d < GATES.minDim)) {
    throw new FlamesInputError(`Image too small for FLAMeS (${dims.join('x')}); a 3D FLAIR volume is required.`);
  }
  if (spacing.some((s) => !(s >= GATES.minSpacingMm && s <= GATES.maxSpacingMm))) {
    throw new FlamesInputError(
      `Voxel spacing ${spacing.map((s) => s.toFixed(2)).join(' x ')} mm is outside the supported range ` +
        `(${GATES.minSpacingMm}-${GATES.maxSpacingMm} mm).`,
    );
  }
}

export async function segmentFlairVolume(vol: FlamesVolume, opts: FlamesPipelineOptions): Promise<FlamesPipelineResult> {
  const progress = opts.onProgress ?? (() => {});
  const { dims, spacing } = vol;
  validateGeometry(vol);
  opts.signal?.throwIfAborted();

  let data = vol.data;
  if (opts.brainMask) {
    if (opts.brainMask.length !== data.length) throw new FlamesInputError('Brain mask does not match the image grid.');
    data = Float32Array.from(data, (v, i) => (opts.brainMask![i] ? v : 0));
  }

  progress('preprocess', 0);
  // Fail closed BEFORE any inference: skull-stripped plausibility (RC-043) + FLAIR contrast (RC-049).
  const gates = checkInputGates(
    { data, dims, spacing },
    {
      skullStripGate: opts.skullStripGate,
      contrastGate: opts.contrastGate,
      headerEvidence: opts.headerEvidence,
      clinicianConfirmedFlair: opts.clinicianConfirmedFlair,
    },
  );
  const border = gates.borderNonzeroFraction;
  const brainVolumeMl = gates.brainVolumeMl;
  opts.signal?.throwIfAborted();
  const netShape = networkShape(dims) as Shape3;
  const netSpacing = networkSpacing(spacing) as Shape3;
  const net = niftiToNetwork(data, dims);
  const nonzero = nonzeroMaskFilled(net, netShape);
  let brainVoxels = 0;
  for (let i = 0; i < nonzero.length; i++) brainVoxels += nonzero[i];

  const box = boundingBox(nonzero, netShape);
  const cropped = cropTo(net, netShape, box);
  const insideMask = cropTo(nonzero, netShape, box);
  const { image: normalized, stats: zscore } = zscoreInMask(cropped, insideMask);
  const target = FLAMES_PLAN.targetSpacing;
  const resampledShape = computeNewShape(box.shape, netSpacing, target);
  const resampled = resampleToShape(normalized, box.shape, resampledShape, netSpacing, target, 3);
  progress('preprocess', 1);
  opts.signal?.throwIfAborted();

  const mirrorAxes = [...(opts.mirrorAxes ?? [])];
  const sw = await predictLogitDifference({
    image: resampled,
    shape: resampledShape,
    patch: FLAMES_PLAN.patchSize,
    runPatch: opts.runPatch,
    tileStepSize: FLAMES_PLAN.tileStepSize,
    sigmaScale: FLAMES_PLAN.gaussianSigmaScale,
    mirrorAxes,
    onPatch: (done, total) => progress('inference', done / total),
    signal: opts.signal,
  });

  progress('postprocess', 0);
  const logitsCropped = resampleToShape(sw.logitDiff, resampledShape, box.shape, target, netSpacing, 1);
  const maskCropped = thresholdLogitDiff(logitsCropped);
  const maskNet = uncrop(maskCropped, netShape, box);
  const maskNifti = networkToNifti(maskNet, dims);
  const maskApp = networkToApp(maskNet, dims);
  const summary = summariseLesions(maskNifti, dims, spacing);

  if (brainVoxels > 0 && summary.lesionVoxels / brainVoxels > GATES.maxLesionFractionOfBrain) {
    throw new FlamesInputError(
      `Implausible output: lesions would cover ${((100 * summary.lesionVoxels) / brainVoxels).toFixed(0)}% of the brain. ` +
        'The result was discarded.',
    );
  }

  let probabilityNifti: Float32Array | undefined;
  if (opts.returnProbability) {
    probabilityNifti = networkToNifti(uncrop(probabilityFromLogitDiff(logitsCropped), netShape, box), dims);
  }
  progress('postprocess', 1);

  return {
    dims,
    spacing,
    maskNifti,
    maskApp,
    probabilityNifti,
    summary,
    diagnostics: {
      networkShape: netShape,
      networkSpacing: netSpacing,
      bbox: box,
      resampledShape,
      windows: sw.windows,
      networkCalls: sw.networkCalls,
      zscore,
      brainVolumeMl,
      borderNonzeroFraction: border,
      mirrorAxes,
    },
  };
}
