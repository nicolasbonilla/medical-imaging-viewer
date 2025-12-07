/**
 * Web Worker for Binary Protocol Deserialization.
 *
 * Offloads CPU-intensive binary deserialization to background thread,
 * keeping the main thread responsive for smooth UI interactions.
 *
 * Features:
 * - Binary protocol deserialization
 * - Window/level adjustments
 * - Histogram calculation
 * - Transferable objects for zero-copy
 * - Error handling and logging
 *
 * @module workers/binaryProtocol.worker
 */

import {
  BinaryDeserializer,
  MessageType,
  type DeserializedMessage,
  type SliceDataPayload,
} from '../services/binaryProtocol';

/**
 * Worker message types.
 */
enum WorkerMessageType {
  DESERIALIZE = 'DESERIALIZE',
  APPLY_WINDOW_LEVEL = 'APPLY_WINDOW_LEVEL',
  CALCULATE_HISTOGRAM = 'CALCULATE_HISTOGRAM',
  COMPUTE_MIN_MAX = 'COMPUTE_MIN_MAX',
}

/**
 * Worker request message.
 */
interface WorkerRequest {
  id: string;
  type: WorkerMessageType;
  data: any;
}

/**
 * Worker response message.
 */
interface WorkerResponse {
  id: string;
  type: WorkerMessageType;
  success: boolean;
  data?: any;
  error?: string;
}

/**
 * Window/level adjustment parameters.
 */
interface WindowLevelParams {
  pixels: Uint16Array | Int16Array | Float32Array;
  windowCenter: number;
  windowWidth: number;
  outputMin?: number;
  outputMax?: number;
}

/**
 * Histogram calculation parameters.
 */
interface HistogramParams {
  pixels: Uint16Array | Int16Array;
  bins?: number;
}

// Initialize deserializer
const deserializer = new BinaryDeserializer();

/**
 * Log debug message.
 */
function log(message: string, ...args: any[]) {
  console.log(`[BinaryWorker] ${message}`, ...args);
}

/**
 * Handle DESERIALIZE request.
 *
 * Deserializes binary protocol message and returns result with
 * transferable ArrayBuffer for zero-copy.
 *
 * @param data - Binary message as ArrayBuffer
 * @returns Deserialized message
 */
function handleDeserialize(data: ArrayBuffer): DeserializedMessage {
  const startTime = performance.now();

  const message = deserializer.deserialize(data);

  const elapsed = performance.now() - startTime;
  log(`Deserialized ${MessageType[message.header.messageType]} in ${elapsed.toFixed(2)}ms`);

  return message;
}

/**
 * Apply window/level adjustment to pixel data.
 *
 * Maps pixel values from [center - width/2, center + width/2] to [outputMin, outputMax].
 * Optimized for medical imaging (CT, MRI).
 *
 * @param params - Window/level parameters
 * @returns Adjusted pixel data (Uint8ClampedArray for Canvas)
 */
function handleApplyWindowLevel(params: WindowLevelParams): Uint8ClampedArray {
  const { pixels, windowCenter, windowWidth, outputMin = 0, outputMax = 255 } = params;

  const startTime = performance.now();

  const result = new Uint8ClampedArray(pixels.length);

  const windowMin = windowCenter - windowWidth / 2;
  const windowMax = windowCenter + windowWidth / 2;
  const scale = (outputMax - outputMin) / windowWidth;

  for (let i = 0; i < pixels.length; i++) {
    const value = pixels[i];

    if (value <= windowMin) {
      result[i] = outputMin;
    } else if (value >= windowMax) {
      result[i] = outputMax;
    } else {
      result[i] = Math.round((value - windowMin) * scale + outputMin);
    }
  }

  const elapsed = performance.now() - startTime;
  log(`Applied window/level to ${pixels.length} pixels in ${elapsed.toFixed(2)}ms`);

  return result;
}

/**
 * Calculate histogram of pixel values.
 *
 * @param params - Histogram parameters
 * @returns Histogram bins
 */
function handleCalculateHistogram(params: HistogramParams): { bins: number[]; min: number; max: number } {
  const { pixels, bins: numBins = 256 } = params;

  const startTime = performance.now();

  // Find min/max
  let min = Infinity;
  let max = -Infinity;

  for (let i = 0; i < pixels.length; i++) {
    const value = pixels[i];
    if (value < min) min = value;
    if (value > max) max = value;
  }

  // Calculate histogram
  const bins = new Array(numBins).fill(0);
  const binSize = (max - min) / numBins;

  for (let i = 0; i < pixels.length; i++) {
    const value = pixels[i];
    const binIndex = Math.min(
      Math.floor((value - min) / binSize),
      numBins - 1
    );
    bins[binIndex]++;
  }

  const elapsed = performance.now() - startTime;
  log(`Calculated histogram for ${pixels.length} pixels in ${elapsed.toFixed(2)}ms`);

  return { bins, min, max };
}

/**
 * Compute min/max values from pixel data.
 *
 * @param pixels - Pixel data
 * @returns Min and max values
 */
function handleComputeMinMax(pixels: TypedArray): { min: number; max: number } {
  const startTime = performance.now();

  let min = Infinity;
  let max = -Infinity;

  for (let i = 0; i < pixels.length; i++) {
    const value = pixels[i];
    if (value < min) min = value;
    if (value > max) max = value;
  }

  const elapsed = performance.now() - startTime;
  log(`Computed min/max for ${pixels.length} pixels in ${elapsed.toFixed(2)}ms`);

  return { min, max };
}

/**
 * Type alias for TypedArray.
 */
type TypedArray = Uint8Array | Uint16Array | Int16Array | Float32Array | Float64Array;

/**
 * Handle incoming worker messages.
 */
self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const request = event.data;

  try {
    let result: any;
    let transferables: Transferable[] = [];

    switch (request.type) {
      case WorkerMessageType.DESERIALIZE:
        result = handleDeserialize(request.data);

        // Transfer ArrayBuffer if it's slice data
        if (
          result.header.messageType === MessageType.SLICE_DATA &&
          result.payload.data
        ) {
          const slicePayload = result.payload as SliceDataPayload;
          transferables = [slicePayload.data.buffer];
        }
        break;

      case WorkerMessageType.APPLY_WINDOW_LEVEL:
        result = handleApplyWindowLevel(request.data);
        transferables = [result.buffer];
        break;

      case WorkerMessageType.CALCULATE_HISTOGRAM:
        result = handleCalculateHistogram(request.data);
        break;

      case WorkerMessageType.COMPUTE_MIN_MAX:
        result = handleComputeMinMax(request.data);
        break;

      default:
        throw new Error(`Unknown message type: ${request.type}`);
    }

    const response: WorkerResponse = {
      id: request.id,
      type: request.type,
      success: true,
      data: result,
    };

    self.postMessage(response, transferables);
  } catch (error: any) {
    const response: WorkerResponse = {
      id: request.id,
      type: request.type,
      success: false,
      error: error.message || 'Unknown error',
    };

    self.postMessage(response);
  }
};

// Notify main thread that worker is ready
log('Worker initialized and ready');
