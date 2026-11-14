/**
 * Message protocol between the UI thread and flamesInBrowser.worker.ts.
 * A job ends with exactly ONE terminal message: 'result' (complete mask) or 'error' (nothing usable).
 * There is no partial-result message by design (fail closed, DESIGN.md §8).
 */
import type { FlamesModelAsset } from './plan';
import type { LesionSummary } from './postprocess';

export type FlamesStage = 'model' | 'read' | 'preprocess' | 'inference' | 'postprocess';

export type FlamesBackend = 'webgpu' | 'wasm';

export interface FlamesSegmentRequest {
  type: 'segment';
  jobId: string;
  /** raw .nii / .nii.gz bytes of the FLAIR (transferred) */
  nifti: ArrayBuffer;
  model: FlamesModelAsset;
  preferWebGPU: boolean;
  /** nnU-Net default test-time mirroring (8x slower). Off by default in the prototype. */
  mirror: boolean;
  /** Series description the app holds for this file (header evidence for the FLAIR gate; never the file name). */
  seriesDescription?: string | null;
  /** RC-049: the clinician explicitly confirmed that this file is a T2-FLAIR (positive evidence). */
  clinicianConfirmedFlair: boolean;
  /** RC-101: the nifti comes from the app's skull-removal service. */
  strippedByApp: boolean;
  /** first 12 hex of the SHA-256 of the skull-removal model, as the server reported it */
  stripModel?: string;
  /** G27 (sixth review of PR #81): the quality gate is on, and the sequence class its server derived for this file */
  qualityGate?: boolean;
  gateSequenceClass?: string | null;
}

export type FlamesWorkerRequest = FlamesSegmentRequest;

export interface FlamesProvenance {
  pipeline: string;
  model: string;
  modelSha256: string;
  sourceCheckpointSha256: string;
  backend: FlamesBackend;
  threads: number;
  onnxRuntimeWeb: string;
  mirror: boolean;
  windows: number;
  networkCalls: number;
  resampledShape: [number, number, number];
  seconds: number;
  fallbackReason?: string;
  generatedAt: string;
  /** FLAIR contrast gate outcome (RC-049): header verdict and image-content score. */
  contrastGate?: { header: 'supports' | 'none'; score: number; threshold: number };
  /** RC-049: positive evidence the input was a FLAIR — header, or explicit clinician confirmation */
  sequenceEvidence: 'header' | 'clinician';
  /** RC-101: what the model read — the file as uploaded, or the image after the app removed its skull */
  inputPreparation: 'as-uploaded' | 'skull-removed';
  stripModel?: string;
}

export type FlamesWorkerResponse =
  | { type: 'progress'; jobId: string; stage: FlamesStage; fraction: number; message: string }
  | { type: 'log'; jobId: string; message: string }
  | {
      type: 'result';
      jobId: string;
      /** binary mask in app order (depth=k, height=i, width=j), RC-031 */
      maskApp: Uint8Array;
      /** NIfTI dims (i, j, k) */
      dims: [number, number, number];
      spacing: [number, number, number];
      summary: LesionSummary;
      provenance: FlamesProvenance;
    }
  | { type: 'error'; jobId: string; kind: 'input' | 'skull' | 'model' | 'runtime'; message: string };
