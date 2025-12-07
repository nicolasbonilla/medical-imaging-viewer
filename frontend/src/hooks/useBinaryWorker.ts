/**
 * Binary Worker Hook.
 *
 * React hook for managing Web Worker that handles CPU-intensive
 * binary protocol operations in the background.
 *
 * Features:
 * - Promise-based API for async worker calls
 * - Automatic worker lifecycle management
 * - Request timeout handling
 * - Error handling with graceful degradation
 * - TypeScript type safety
 * - Performance monitoring
 *
 * @module hooks/useBinaryWorker
 */

import { useEffect, useRef, useCallback } from 'react';
import type {
  DeserializedMessage,
} from '../services/binaryProtocol';

/**
 * Worker request types.
 */
export enum WorkerMessageType {
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
export interface WindowLevelParams {
  pixels: Uint16Array | Int16Array | Float32Array;
  windowCenter: number;
  windowWidth: number;
  outputMin?: number;
  outputMax?: number;
}

/**
 * Histogram calculation parameters.
 */
export interface HistogramParams {
  pixels: Uint16Array | Int16Array;
  bins?: number;
}

/**
 * Histogram result.
 */
export interface HistogramResult {
  bins: number[];
  min: number;
  max: number;
}

/**
 * Min/Max result.
 */
export interface MinMaxResult {
  min: number;
  max: number;
}

/**
 * Pending request.
 */
interface PendingRequest {
  resolve: (value: any) => void;
  reject: (error: Error) => void;
  timeoutId: number;
  type: WorkerMessageType;
  startTime: number;
}

/**
 * Hook options.
 */
export interface UseBinaryWorkerOptions {
  /**
   * Request timeout in milliseconds.
   * @default 5000
   */
  timeout?: number;

  /**
   * Whether to enable performance logging.
   * @default false
   */
  enableLogging?: boolean;

  /**
   * Fallback to main thread if worker fails.
   * @default true
   */
  enableFallback?: boolean;
}

/**
 * Hook return value.
 */
export interface UseBinaryWorkerReturn {
  /**
   * Deserialize binary protocol message.
   */
  deserialize: (data: ArrayBuffer) => Promise<DeserializedMessage>;

  /**
   * Apply window/level adjustment to pixel data.
   */
  applyWindowLevel: (params: WindowLevelParams) => Promise<Uint8ClampedArray>;

  /**
   * Calculate histogram of pixel values.
   */
  calculateHistogram: (params: HistogramParams) => Promise<HistogramResult>;

  /**
   * Compute min/max values from pixel data.
   */
  computeMinMax: (pixels: TypedArray) => Promise<MinMaxResult>;

  /**
   * Whether worker is ready.
   */
  isReady: boolean;

  /**
   * Whether worker is supported.
   */
  isSupported: boolean;

  /**
   * Terminate worker manually.
   */
  terminate: () => void;
}

/**
 * Type alias for TypedArray.
 */
type TypedArray = Uint8Array | Uint16Array | Int16Array | Float32Array | Float64Array;

/**
 * Generate unique request ID.
 */
let requestIdCounter = 0;
function generateRequestId(): string {
  return `req_${Date.now()}_${++requestIdCounter}`;
}

/**
 * Log debug message.
 */
function log(enableLogging: boolean, message: string, ...args: any[]) {
  if (enableLogging) {
    console.log(`[useBinaryWorker] ${message}`, ...args);
  }
}

/**
 * React hook for binary protocol Web Worker.
 *
 * Manages worker lifecycle, provides promise-based API for worker operations,
 * handles timeouts and errors gracefully.
 *
 * @param options - Hook options
 * @returns Worker API
 *
 * @example
 * ```typescript
 * const { deserialize, applyWindowLevel, isReady } = useBinaryWorker({
 *   timeout: 10000,
 *   enableLogging: true,
 * });
 *
 * // Deserialize binary message
 * const message = await deserialize(arrayBuffer);
 *
 * // Apply window/level adjustment
 * const adjusted = await applyWindowLevel({
 *   pixels: uint16Array,
 *   windowCenter: 50,
 *   windowWidth: 100,
 * });
 * ```
 */
export function useBinaryWorker(
  options: UseBinaryWorkerOptions = {}
): UseBinaryWorkerReturn {
  const {
    timeout = 5000,
    enableLogging = false,
    enableFallback = true,
  } = options;

  // Worker instance
  const workerRef = useRef<Worker | null>(null);

  // Pending requests
  const pendingRequestsRef = useRef<Map<string, PendingRequest>>(new Map());

  // Worker state
  const isReadyRef = useRef<boolean>(false);
  const isSupportedRef = useRef<boolean>(typeof Worker !== 'undefined');

  /**
   * Initialize worker.
   */
  useEffect(() => {
    if (!isSupportedRef.current) {
      log(enableLogging, 'Web Workers not supported');
      return;
    }

    try {
      // Create worker
      const worker = new Worker(
        new URL('../workers/binaryProtocol.worker.ts', import.meta.url),
        { type: 'module' }
      );

      // Handle worker messages
      worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
        const response = event.data;
        const pending = pendingRequestsRef.current.get(response.id);

        if (!pending) {
          log(enableLogging, 'Received response for unknown request:', response.id);
          return;
        }

        // Clear timeout
        clearTimeout(pending.timeoutId);

        // Remove from pending
        pendingRequestsRef.current.delete(response.id);

        // Log performance
        const elapsed = performance.now() - pending.startTime;
        log(
          enableLogging,
          `Worker ${pending.type} completed in ${elapsed.toFixed(2)}ms`
        );

        // Resolve or reject
        if (response.success) {
          pending.resolve(response.data);
        } else {
          pending.reject(new Error(response.error || 'Worker operation failed'));
        }
      };

      // Handle worker errors
      worker.onerror = (error) => {
        console.error('[useBinaryWorker] Worker error:', error);

        // Reject all pending requests
        pendingRequestsRef.current.forEach((pending) => {
          clearTimeout(pending.timeoutId);
          pending.reject(new Error('Worker error'));
        });

        pendingRequestsRef.current.clear();
      };

      workerRef.current = worker;
      isReadyRef.current = true;

      log(enableLogging, 'Worker initialized');
    } catch (error) {
      console.error('[useBinaryWorker] Failed to create worker:', error);
      isSupportedRef.current = false;
    }

    // Cleanup
    return () => {
      if (workerRef.current) {
        log(enableLogging, 'Terminating worker');

        // Cancel all pending requests
        pendingRequestsRef.current.forEach((pending) => {
          clearTimeout(pending.timeoutId);
          pending.reject(new Error('Worker terminated'));
        });

        pendingRequestsRef.current.clear();

        workerRef.current.terminate();
        workerRef.current = null;
        isReadyRef.current = false;
      }
    };
  }, [enableLogging]);

  /**
   * Send request to worker.
   */
  const sendRequest = useCallback(
    <T>(type: WorkerMessageType, data: any, transferables?: Transferable[]): Promise<T> => {
      return new Promise((resolve, reject) => {
        if (!workerRef.current || !isReadyRef.current) {
          reject(new Error('Worker not ready'));
          return;
        }

        const id = generateRequestId();
        const startTime = performance.now();

        // Create timeout
        const timeoutId = window.setTimeout(() => {
          pendingRequestsRef.current.delete(id);
          reject(new Error(`Worker request timeout after ${timeout}ms`));
        }, timeout);

        // Store pending request
        pendingRequestsRef.current.set(id, {
          resolve,
          reject,
          timeoutId,
          type,
          startTime,
        });

        // Send request
        const request: WorkerRequest = { id, type, data };

        if (transferables && transferables.length > 0) {
          workerRef.current.postMessage(request, transferables);
        } else {
          workerRef.current.postMessage(request);
        }

        log(enableLogging, `Sent ${type} request:`, id);
      });
    },
    [timeout, enableLogging]
  );

  /**
   * Deserialize binary protocol message.
   */
  const deserialize = useCallback(
    async (data: ArrayBuffer): Promise<DeserializedMessage> => {
      if (!isSupportedRef.current || !isReadyRef.current) {
        if (enableFallback) {
          log(enableLogging, 'Worker not available, using fallback');
          // Fallback: import and use synchronous deserializer
          const { BinaryDeserializer } = await import('../services/binaryProtocol');
          const deserializer = new BinaryDeserializer();
          return deserializer.deserialize(data);
        } else {
          throw new Error('Worker not available and fallback disabled');
        }
      }

      return sendRequest<DeserializedMessage>(
        WorkerMessageType.DESERIALIZE,
        data,
        [data] // Transfer ArrayBuffer
      );
    },
    [sendRequest, enableLogging, enableFallback]
  );

  /**
   * Apply window/level adjustment.
   */
  const applyWindowLevel = useCallback(
    async (params: WindowLevelParams): Promise<Uint8ClampedArray> => {
      if (!isSupportedRef.current || !isReadyRef.current) {
        if (enableFallback) {
          log(enableLogging, 'Worker not available, using fallback for window/level');
          // Fallback: synchronous implementation
          return applyWindowLevelSync(params);
        } else {
          throw new Error('Worker not available and fallback disabled');
        }
      }

      return sendRequest<Uint8ClampedArray>(
        WorkerMessageType.APPLY_WINDOW_LEVEL,
        params,
        [params.pixels.buffer] // Transfer pixel buffer
      );
    },
    [sendRequest, enableLogging, enableFallback]
  );

  /**
   * Calculate histogram.
   */
  const calculateHistogram = useCallback(
    async (params: HistogramParams): Promise<HistogramResult> => {
      if (!isSupportedRef.current || !isReadyRef.current) {
        if (enableFallback) {
          log(enableLogging, 'Worker not available, using fallback for histogram');
          return calculateHistogramSync(params);
        } else {
          throw new Error('Worker not available and fallback disabled');
        }
      }

      return sendRequest<HistogramResult>(
        WorkerMessageType.CALCULATE_HISTOGRAM,
        params
      );
    },
    [sendRequest, enableLogging, enableFallback]
  );

  /**
   * Compute min/max values.
   */
  const computeMinMax = useCallback(
    async (pixels: TypedArray): Promise<MinMaxResult> => {
      if (!isSupportedRef.current || !isReadyRef.current) {
        if (enableFallback) {
          log(enableLogging, 'Worker not available, using fallback for min/max');
          return computeMinMaxSync(pixels);
        } else {
          throw new Error('Worker not available and fallback disabled');
        }
      }

      return sendRequest<MinMaxResult>(
        WorkerMessageType.COMPUTE_MIN_MAX,
        pixels
      );
    },
    [sendRequest, enableLogging, enableFallback]
  );

  /**
   * Terminate worker manually.
   */
  const terminate = useCallback(() => {
    if (workerRef.current) {
      log(enableLogging, 'Manual worker termination');

      // Cancel all pending requests
      pendingRequestsRef.current.forEach((pending) => {
        clearTimeout(pending.timeoutId);
        pending.reject(new Error('Worker terminated'));
      });

      pendingRequestsRef.current.clear();

      workerRef.current.terminate();
      workerRef.current = null;
      isReadyRef.current = false;
    }
  }, [enableLogging]);

  return {
    deserialize,
    applyWindowLevel,
    calculateHistogram,
    computeMinMax,
    isReady: isReadyRef.current,
    isSupported: isSupportedRef.current,
    terminate,
  };
}

/**
 * Synchronous fallback for window/level adjustment.
 */
function applyWindowLevelSync(params: WindowLevelParams): Uint8ClampedArray {
  const { pixels, windowCenter, windowWidth, outputMin = 0, outputMax = 255 } = params;

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

  return result;
}

/**
 * Synchronous fallback for histogram calculation.
 */
function calculateHistogramSync(params: HistogramParams): HistogramResult {
  const { pixels, bins: numBins = 256 } = params;

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

  return { bins, min, max };
}

/**
 * Synchronous fallback for min/max computation.
 */
function computeMinMaxSync(pixels: TypedArray): MinMaxResult {
  let min = Infinity;
  let max = -Infinity;

  for (let i = 0; i < pixels.length; i++) {
    const value = pixels[i];
    if (value < min) min = value;
    if (value > max) max = value;
  }

  return { min, max };
}
