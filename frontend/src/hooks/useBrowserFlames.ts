/**
 * useBrowserFlames — runs the in-browser FLAMeS worker for one FLAIR file (PROTOTYPE, feature-flagged).
 *
 * One worker per job, terminated when the job ends or is cancelled, so the WebAssembly heap
 * (up to ~3-4 GB during inference) is returned to the OS immediately. A job yields either a
 * complete result or an error — never a partial mask.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '@/services/apiClient';
import { FLAMES_FOLD0_MODEL } from '@/services/flames/plan';
import type { FlamesProvenance, FlamesStage, FlamesWorkerResponse } from '@/services/flames/protocol';
import type { LesionSummary } from '@/services/flames/postprocess';

export type BrowserFlamesStatus = 'idle' | 'running' | 'done' | 'error';

export interface BrowserFlamesResult {
  fileId: string;
  maskApp: Uint8Array;
  dims: [number, number, number];
  spacing: [number, number, number];
  summary: LesionSummary;
  provenance: FlamesProvenance;
}

export function useBrowserFlames() {
  const [status, setStatus] = useState<BrowserFlamesStatus>('idle');
  const [stage, setStage] = useState<FlamesStage | null>(null);
  const [fraction, setFraction] = useState(0);
  const [message, setMessage] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BrowserFlamesResult | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const workerRef = useRef<Worker | null>(null);
  const jobRef = useRef<string | null>(null);

  const terminate = useCallback(() => {
    workerRef.current?.terminate();
    workerRef.current = null;
    jobRef.current = null;
  }, []);

  useEffect(() => terminate, [terminate]);

  const run = useCallback(
    async (fileId: string, options: { mirror?: boolean; webgpu?: boolean; seriesDescription?: string | null } = {}) => {
      terminate();
      const jobId = crypto.randomUUID();
      jobRef.current = jobId;
      setStartedAt(Date.now());
      setStatus('running');
      setResult(null);
      setError(null);
      setStage('read');
      setFraction(0);
      setMessage('Downloading the FLAIR from the study…');
      const fail = (msg: string) => {
        if (jobRef.current !== jobId) return;
        terminate();
        setError(msg);
        setStatus('error');
      };
      try {
        const response = await apiClient.get(`/api/v1/imaging/nifti/${fileId}`, { responseType: 'arraybuffer' });
        if (jobRef.current !== jobId) return; // cancelled meanwhile
        const nifti = response.data as ArrayBuffer;
        const worker = new Worker(new URL('../workers/flamesInBrowser.worker.ts', import.meta.url), { type: 'module' });
        workerRef.current = worker;
        const envUrl = import.meta.env.VITE_FLAMES_MODEL_URL as string | undefined;
        const model = { ...FLAMES_FOLD0_MODEL, url: envUrl || FLAMES_FOLD0_MODEL.url };
        worker.onmessage = (event: MessageEvent<FlamesWorkerResponse>) => {
          const m = event.data;
          if (m.jobId !== jobRef.current) return;
          if (m.type === 'progress') {
            setStage(m.stage);
            setFraction(m.fraction);
            setMessage(m.message);
          } else if (m.type === 'log') {
            console.info('[BrowserFLAMeS]', m.message);
          } else if (m.type === 'result') {
            terminate();
            setResult({
              fileId,
              maskApp: m.maskApp,
              dims: m.dims,
              spacing: m.spacing,
              summary: m.summary,
              provenance: m.provenance,
            });
            setStatus('done');
          } else if (m.type === 'error') {
            fail(m.message);
          }
        };
        worker.onerror = (e) => fail(e.message || 'The segmentation worker stopped unexpectedly.');
        // WebGPU is NOT attempted by default: ONNX Runtime Web 1.24.1 (the app's SOUP version) rejects 3D
        // convolutions on WebGPU, and with 1.29 an integrated GPU lost the device (DESIGN.md §7.1). The worker
        // keeps the WebGPU path (with a whole-job WebAssembly restart) for when the SOUP upgrade is approved.
        worker.postMessage(
          {
            type: 'segment',
            jobId,
            nifti,
            model,
            preferWebGPU: Boolean(options.webgpu),
            mirror: Boolean(options.mirror),
            seriesDescription: options.seriesDescription ?? null,
          },
          [nifti],
        );
      } catch (err) {
        fail(err instanceof Error ? err.message : String(err));
      }
    },
    [terminate],
  );

  /**
   * Cancel: terminates the worker and forgets the job. It never touches the segmentation store,
   * so the clinician's open segmentation (saved or not) is unaffected.
   */
  const cancel = useCallback(() => {
    terminate();
    setStatus('idle');
    setStage(null);
    setMessage('');
    setStartedAt(null);
  }, [terminate]);

  const reset = useCallback(() => {
    terminate();
    setStatus('idle');
    setStage(null);
    setMessage('');
    setError(null);
    setResult(null);
  }, [terminate]);

  return { status, stage, fraction, message, error, result, startedAt, run, cancel, reset };
}
