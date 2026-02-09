/**
 * Edge AI Web Worker — Brain MRI Screening Classification.
 *
 * Runs ONNX Runtime Web inside a Web Worker so inference never blocks the UI.
 * The model is a lightweight (<5MB) binary classifier:
 *   Input:  224×224 grayscale brain MRI slice (axial)
 *   Output: { normal: probability, abnormal: probability }
 *
 * Supports WebGPU execution provider with automatic WASM fallback.
 * All data stays in the browser — nothing is sent to a server.
 *
 * @module workers/edgeAI
 */

import * as ort from 'onnxruntime-web';

// --------------------------------------------------------------------------
// Message types
// --------------------------------------------------------------------------

interface LoadModelMessage {
  type: 'load';
  modelUrl: string;
  useGPU: boolean;
}

interface ClassifyMessage {
  type: 'classify';
  imageData: Float32Array;
  width: number;
  height: number;
}

type WorkerMessage = LoadModelMessage | ClassifyMessage;

interface WorkerResponse {
  type: 'loaded' | 'result' | 'error' | 'progress';
  payload?: any;
}

// --------------------------------------------------------------------------
// State
// --------------------------------------------------------------------------

let session: ort.InferenceSession | null = null;

// --------------------------------------------------------------------------
// Preprocessing — resize + normalize to [1, 1, 224, 224]
// --------------------------------------------------------------------------

function preprocessSlice(
  data: Float32Array,
  srcWidth: number,
  srcHeight: number,
): Float32Array {
  const targetSize = 224;
  const output = new Float32Array(targetSize * targetSize);

  const scaleX = srcWidth / targetSize;
  const scaleY = srcHeight / targetSize;

  // Bilinear interpolation resize
  for (let y = 0; y < targetSize; y++) {
    for (let x = 0; x < targetSize; x++) {
      const srcX = x * scaleX;
      const srcY = y * scaleY;
      const x0 = Math.floor(srcX);
      const y0 = Math.floor(srcY);
      const x1 = Math.min(x0 + 1, srcWidth - 1);
      const y1 = Math.min(y0 + 1, srcHeight - 1);
      const dx = srcX - x0;
      const dy = srcY - y0;

      const v00 = data[y0 * srcWidth + x0] || 0;
      const v10 = data[y0 * srcWidth + x1] || 0;
      const v01 = data[y1 * srcWidth + x0] || 0;
      const v11 = data[y1 * srcWidth + x1] || 0;

      const value =
        v00 * (1 - dx) * (1 - dy) +
        v10 * dx * (1 - dy) +
        v01 * (1 - dx) * dy +
        v11 * dx * dy;

      output[y * targetSize + x] = value;
    }
  }

  // Normalize to [0, 1] based on min/max
  let min = Infinity;
  let max = -Infinity;
  for (let i = 0; i < output.length; i++) {
    if (output[i] < min) min = output[i];
    if (output[i] > max) max = output[i];
  }
  const range = max - min || 1;
  for (let i = 0; i < output.length; i++) {
    output[i] = (output[i] - min) / range;
  }

  return output;
}

// --------------------------------------------------------------------------
// Model loading
// --------------------------------------------------------------------------

async function loadModel(modelUrl: string, useGPU: boolean): Promise<void> {
  const options: ort.InferenceSession.SessionOptions = {
    graphOptimizationLevel: 'all',
  };

  // Try WebGPU first, then fall back to WASM
  if (useGPU) {
    try {
      options.executionProviders = [{ name: 'webgpu' }];
      session = await ort.InferenceSession.create(modelUrl, options);
      return;
    } catch {
      // WebGPU not available — fall back
    }
  }

  options.executionProviders = [{ name: 'wasm' }];
  session = await ort.InferenceSession.create(modelUrl, options);
}

// --------------------------------------------------------------------------
// Inference
// --------------------------------------------------------------------------

async function classify(
  imageData: Float32Array,
  width: number,
  height: number,
): Promise<{ normal: number; abnormal: number; inferenceTimeMs: number }> {
  if (!session) {
    throw new Error('Model not loaded');
  }

  const preprocessed = preprocessSlice(imageData, width, height);

  // Shape: [batch=1, channels=1, height=224, width=224]
  const tensor = new ort.Tensor('float32', preprocessed, [1, 1, 224, 224]);

  const start = performance.now();
  const results = await session.run({ input: tensor });
  const inferenceTimeMs = Math.round(performance.now() - start);

  // Get output — expected shape [1, 2] with logits or probabilities
  const outputKey = session.outputNames[0];
  const outputData = results[outputKey].data as Float32Array;

  // Apply softmax if output looks like logits (values outside [0,1])
  let normal: number;
  let abnormal: number;

  if (outputData[0] < 0 || outputData[0] > 1 || outputData[1] < 0 || outputData[1] > 1) {
    // Softmax
    const maxVal = Math.max(outputData[0], outputData[1]);
    const exp0 = Math.exp(outputData[0] - maxVal);
    const exp1 = Math.exp(outputData[1] - maxVal);
    const sum = exp0 + exp1;
    normal = exp0 / sum;
    abnormal = exp1 / sum;
  } else {
    normal = outputData[0];
    abnormal = outputData[1];
  }

  return { normal, abnormal, inferenceTimeMs };
}

// --------------------------------------------------------------------------
// Message handler
// --------------------------------------------------------------------------

self.onmessage = async (event: MessageEvent<WorkerMessage>) => {
  const msg = event.data;

  try {
    switch (msg.type) {
      case 'load': {
        self.postMessage({ type: 'progress', payload: 'Downloading model...' } as WorkerResponse);
        await loadModel(msg.modelUrl, msg.useGPU);
        self.postMessage({ type: 'loaded' } as WorkerResponse);
        break;
      }
      case 'classify': {
        const result = await classify(msg.imageData, msg.width, msg.height);
        self.postMessage({ type: 'result', payload: result } as WorkerResponse);
        break;
      }
    }
  } catch (err: any) {
    self.postMessage({ type: 'error', payload: err.message || String(err) } as WorkerResponse);
  }
};
