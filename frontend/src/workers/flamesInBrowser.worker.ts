/**
 * FLAMeS MS-lesion segmentation INSIDE THE BROWSER (PROTOTYPE, feature flag VITE_ENABLE_BROWSER_FLAMES, default OFF).
 *
 * Separate from the Class C edgeAI.worker.ts on purpose (that file is untouched). Runs:
 *   read NIfTI -> nnU-Net preprocessing -> ONNX Runtime Web (WebGPU, else WebAssembly) sliding window
 *   -> nnU-Net postprocessing -> binary mask in the app's (k, i, j) order.
 *
 * Fail-closed contract: a job ends with ONE message, either 'result' (complete, gated mask) or 'error'.
 * If WebGPU fails at any point (exception, non-finite or constant scores) the WHOLE job restarts on
 * WebAssembly; patches from two backends are never mixed.
 * No image data leaves the browser; the only network request is the pinned model download.
 */
import * as ort from 'onnxruntime-web/webgpu';
import wasmUrl from 'onnxruntime-web/ort-wasm-simd-threaded.asyncify.wasm?url';
import wasmModuleUrl from 'onnxruntime-web/ort-wasm-simd-threaded.asyncify.mjs?url';
import { readNifti } from '@/services/flames/nifti';
import { FlamesInputError, segmentFlairVolume } from '@/services/flames/pipeline';
import { FLAMES_PIPELINE_VERSION, FLAMES_PLAN } from '@/services/flames/plan';
import { loadVerifiedModel, ModelIntegrityError } from '@/services/flames/modelStore';
import type { FlamesBackend, FlamesWorkerRequest, FlamesWorkerResponse, FlamesStage } from '@/services/flames/protocol';

ort.env.wasm.wasmPaths = { wasm: wasmUrl, mjs: wasmModuleUrl };
ort.env.wasm.proxy = false;
const THREADS = self.crossOriginIsolated ? Math.max(1, Math.min(8, navigator.hardwareConcurrency || 1)) : 1;
ort.env.wasm.numThreads = THREADS;

const post = (msg: FlamesWorkerResponse, transfer: Transferable[] = []) =>
  (self as unknown as Worker).postMessage(msg, transfer);

async function webgpuUsable(): Promise<boolean> {
  try {
    const gpu = (navigator as unknown as { gpu?: { requestAdapter: () => Promise<unknown> } }).gpu;
    return Boolean(gpu && (await gpu.requestAdapter()));
  } catch {
    return false;
  }
}

async function createSession(model: Uint8Array, backend: FlamesBackend): Promise<ort.InferenceSession> {
  return ort.InferenceSession.create(model, {
    executionProviders: [backend],
    graphOptimizationLevel: 'all',
  });
}

self.onmessage = async (event: MessageEvent<FlamesWorkerRequest>) => {
  const job = event.data;
  if (job.type !== 'segment') return;
  const { jobId } = job;
  const progress = (stage: FlamesStage, fraction: number, message: string) =>
    post({ type: 'progress', jobId, stage, fraction, message });
  const log = (message: string) => post({ type: 'log', jobId, message });
  const started = performance.now();
  let session: ort.InferenceSession | null = null;

  try {
    progress('model', 0, 'Loading the FLAMeS model…');
    const modelBytes = await loadVerifiedModel(job.model, (f) => progress('model', f, 'Downloading the FLAMeS model…'));

    progress('read', 0, 'Reading the FLAIR…');
    const flair = await readNifti(job.nifti);
    progress('read', 1, `FLAIR ${flair.dims.join(' × ')} voxels, ${flair.spacing.map((s) => s.toFixed(2)).join(' × ')} mm`);

    const attempt = async (backend: FlamesBackend) => {
      session = await createSession(modelBytes, backend);
      const s = session;
      const inputName = s.inputNames[0];
      const outputName = s.outputNames[0];
      return segmentFlairVolume(
        { data: flair.data, dims: flair.dims, spacing: flair.spacing },
        {
          mirrorAxes: job.mirror ? FLAMES_PLAN.mirrorAxes : [],
          runPatch: async (tile) => {
            const input = new ort.Tensor('float32', tile, [1, 1, ...FLAMES_PLAN.patchSize]);
            let outputs: ort.InferenceSession.OnnxValueMapType | undefined;
            try {
              outputs = await s.run({ [inputName]: input });
              const data = (await outputs[outputName].getData()) as Float32Array;
              return data.slice();
            } finally {
              input.dispose();
              if (outputs) for (const v of Object.values(outputs)) v.dispose();
            }
          },
          onProgress: (stage, fraction) => {
            const label =
              stage === 'inference'
                ? `Segmenting lesions (${backend === 'webgpu' ? 'WebGPU' : `WebAssembly, ${THREADS} thread${THREADS > 1 ? 's' : ''}`})…`
                : stage === 'preprocess'
                  ? 'Preparing the image (nnU-Net preprocessing)…'
                  : 'Finishing…';
            progress(stage as FlamesStage, fraction, label);
          },
        },
      );
    };

    let backend: FlamesBackend = job.preferWebGPU && (await webgpuUsable()) ? 'webgpu' : 'wasm';
    let fallbackReason: string | undefined;
    let result;
    try {
      result = await attempt(backend);
    } catch (error) {
      if (backend !== 'webgpu' || error instanceof FlamesInputError) throw error;
      fallbackReason = error instanceof Error ? error.message : String(error);
      log(`WebGPU failed (${fallbackReason}); restarting the whole job on WebAssembly.`);
      const previous = session as ort.InferenceSession | null;
      session = null;
      await previous?.release();
      backend = 'wasm';
      result = await attempt(backend);
    }

    const seconds = Math.round((performance.now() - started) / 100) / 10;
    post(
      {
        type: 'result',
        jobId,
        maskApp: result.maskApp,
        dims: [...result.dims] as [number, number, number],
        spacing: [...result.spacing] as [number, number, number],
        summary: result.summary,
        provenance: {
          pipeline: FLAMES_PIPELINE_VERSION,
          model: `FLAMeS fold ${job.model.fold} (Zenodo 10.5281/zenodo.17955359 v2.0, CC BY 4.0)`,
          modelSha256: job.model.sha256,
          sourceCheckpointSha256: job.model.sourceCheckpointSha256,
          backend,
          threads: backend === 'wasm' ? THREADS : 0,
          onnxRuntimeWeb: ort.env.versions?.web ?? 'unknown',
          mirror: job.mirror,
          windows: result.diagnostics.windows,
          networkCalls: result.diagnostics.networkCalls,
          resampledShape: result.diagnostics.resampledShape,
          seconds,
          fallbackReason,
          generatedAt: new Date().toISOString(),
        },
      },
      [result.maskApp.buffer],
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const kind = error instanceof FlamesInputError ? 'input' : error instanceof ModelIntegrityError ? 'model' : 'runtime';
    post({ type: 'error', jobId, kind, message });
  } finally {
    const s = session as ort.InferenceSession | null;
    session = null;
    try {
      await s?.release();
    } catch {
      /* ignore */
    }
  }
};
