/**
 * useEdgeAI — Hook for browser-based brain MRI screening with ONNX Runtime Web.
 *
 * Manages the Web Worker lifecycle, model loading, and classification.
 * The model runs entirely in the browser — no data leaves the device.
 *
 * Usage:
 *   const { classify, isModelLoaded, isClassifying, result, error } = useEdgeAI();
 *   // classify takes a grayscale pixel array + dimensions
 *   await classify(pixelData, width, height);
 *
 * @module hooks/useEdgeAI
 */

import { useCallback, useEffect, useRef, useState } from 'react';

const MODEL_URL = '/models/brain_screening.onnx';

export interface ScreeningResult {
  normal: number;
  abnormal: number;
  inferenceTimeMs: number;
  label: 'normal' | 'abnormal';
  confidence: number;
}

interface UseEdgeAIReturn {
  /** Classify a grayscale image slice. */
  classify: (pixelData: Float32Array, width: number, height: number) => void;
  /** Load the ONNX model (called lazily on first classify if not loaded). */
  loadModel: () => void;
  /** Whether the ONNX model is loaded and ready. */
  isModelLoaded: boolean;
  /** Whether the model is currently loading. */
  isModelLoading: boolean;
  /** Whether classification is in progress. */
  isClassifying: boolean;
  /** Latest screening result. */
  result: ScreeningResult | null;
  /** Error message if something went wrong. */
  error: string | null;
  /** Whether the model file exists and is available. */
  isModelAvailable: boolean | null;
  /** Reset result and error. */
  reset: () => void;
}

export function useEdgeAI(): UseEdgeAIReturn {
  const workerRef = useRef<Worker | null>(null);
  const [isModelLoaded, setIsModelLoaded] = useState(false);
  const [isModelLoading, setIsModelLoading] = useState(false);
  const [isClassifying, setIsClassifying] = useState(false);
  const [result, setResult] = useState<ScreeningResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isModelAvailable, setIsModelAvailable] = useState<boolean | null>(null);

  // Track pending classify request while model loads
  const pendingClassifyRef = useRef<{ pixelData: Float32Array; width: number; height: number } | null>(null);

  // Check model availability on mount.
  // Firebase Hosting SPA rewrite returns 200 + index.html for ANY path
  // (including /models/brain_screening.onnx when file doesn't exist).
  // Must verify content-type is NOT text/html to avoid ONNX parsing HTML.
  useEffect(() => {
    fetch(MODEL_URL, { method: 'HEAD' })
      .then((res) => {
        const ct = res.headers.get('content-type') || '';
        setIsModelAvailable(res.ok && !ct.includes('text/html'));
      })
      .catch(() => setIsModelAvailable(false));
  }, []);

  // Create worker
  const getWorker = useCallback(() => {
    if (!workerRef.current) {
      workerRef.current = new Worker(
        new URL('../workers/edgeAI.worker.ts', import.meta.url),
        { type: 'module' },
      );

      workerRef.current.onmessage = (event) => {
        const msg = event.data;
        switch (msg.type) {
          case 'loaded':
            setIsModelLoaded(true);
            setIsModelLoading(false);
            // If there's a pending classify, fire it now
            if (pendingClassifyRef.current) {
              const { pixelData, width, height } = pendingClassifyRef.current;
              pendingClassifyRef.current = null;
              workerRef.current?.postMessage(
                { type: 'classify', imageData: pixelData, width, height },
                [pixelData.buffer],
              );
            }
            break;
          case 'result': {
            const { normal, abnormal, inferenceTimeMs } = msg.payload;
            const label = abnormal > normal ? 'abnormal' : 'normal';
            const confidence = Math.max(normal, abnormal);
            setResult({ normal, abnormal, inferenceTimeMs, label, confidence });
            setIsClassifying(false);
            break;
          }
          case 'error':
            setError(msg.payload);
            setIsModelLoading(false);
            setIsClassifying(false);
            break;
          case 'progress':
            // Could show progress, for now just a status update
            break;
        }
      };
    }
    return workerRef.current;
  }, []);

  // Cleanup worker on unmount
  useEffect(() => {
    return () => {
      workerRef.current?.terminate();
      workerRef.current = null;
    };
  }, []);

  const loadModel = useCallback(() => {
    if (isModelLoaded || isModelLoading) return;
    setIsModelLoading(true);
    setError(null);
    const worker = getWorker();
    worker.postMessage({ type: 'load', modelUrl: MODEL_URL, useGPU: true });
  }, [isModelLoaded, isModelLoading, getWorker]);

  const classify = useCallback(
    (pixelData: Float32Array, width: number, height: number) => {
      setError(null);
      setIsClassifying(true);
      setResult(null);

      const worker = getWorker();

      if (!isModelLoaded) {
        // Store request and load model first
        pendingClassifyRef.current = { pixelData, width, height };
        if (!isModelLoading) {
          setIsModelLoading(true);
          worker.postMessage({ type: 'load', modelUrl: MODEL_URL, useGPU: true });
        }
        return;
      }

      // Model is loaded — classify immediately, transferring the buffer
      worker.postMessage(
        { type: 'classify', imageData: pixelData, width, height },
        [pixelData.buffer],
      );
    },
    [isModelLoaded, isModelLoading, getWorker],
  );

  const reset = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  return {
    classify,
    loadModel,
    isModelLoaded,
    isModelLoading,
    isClassifying,
    result,
    error,
    isModelAvailable,
    reset,
  };
}
