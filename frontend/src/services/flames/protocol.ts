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
  | { type: 'error'; jobId: string; kind: 'input' | 'model' | 'runtime'; message: string };
