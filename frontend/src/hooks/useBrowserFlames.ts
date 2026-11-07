/**
 * useBrowserFlames — runs the in-browser FLAMeS worker for one FLAIR file (PROTOTYPE, feature-flagged).
 *
 * One worker per attempt, terminated when it ends or is cancelled, so the WebAssembly heap (up to ~3-4 GB during inference) is
 * returned to the OS immediately. A job yields either a complete result or an error — never a partial mask.
 *
 * REQ-FUNC-115 (RC-101): the file is read as it is first, through every input gate. Only when the skull gates refuse it is the
 * image sent to the app's server to remove the skull, and the stripped image is run once more with those two gates off. An image
 * that already has no skull never leaves the browser. A failure of the server is said as such, never as a fault of the image.
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

type Options = { mirror?: boolean; webgpu?: boolean; seriesDescription?: string | null; clinicianConfirmedFlair?: boolean };
type Prepared = { nifti: ArrayBuffer; strippedByApp: boolean; stripModel?: string };

export const STRIP_UNAVAILABLE = 'Skull removal is not available on this server.';

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
  const abortRef = useRef<AbortController | null>(null);

  const terminate = useCallback(() => {
    workerRef.current?.terminate();
    workerRef.current = null;
    abortRef.current?.abort();
    abortRef.current = null;
    jobRef.current = null;
  }, []);

  useEffect(() => terminate, [terminate]);

  const run = useCallback(
    async (fileId: string, options: Options = {}) => {
      terminate();
      const jobId = crypto.randomUUID();
      jobRef.current = jobId;
      const abort = new AbortController();
      abortRef.current = abort;
      setStartedAt(Date.now());
      setStatus('running');
      setResult(null);
      setError(null);
      setStage('read');
      setFraction(0);
      setMessage('Downloading the FLAIR from the study…');
      const current = () => jobRef.current === jobId;
      const fail = (msg: string) => {
        if (!current()) return;
        terminate();
        setError(msg);
        setStatus('error');
      };

      const stripOnServer = async (refusal: string): Promise<Prepared | null> => {
        setStage('read');
        setFraction(0);
        setMessage('The image has its skull: removing it on the server…');
        try {
          const response = await apiClient.post('/api/v1/clinical/skull-strip', { file_id: fileId },
            { responseType: 'arraybuffer', timeout: 240000, signal: abort.signal });
          const model = String(response.headers?.['x-strip-model'] ?? '');
          return { nifti: response.data as ArrayBuffer, strippedByApp: true, stripModel: /^[0-9a-f]{12}$/.test(model) ? model : undefined };
        } catch (e) {
          if (!current()) return null;
          const code = (e as { response?: { status?: number } })?.response?.status;
          fail(code === 503 ? `${refusal} ${STRIP_UNAVAILABLE}`
            : `The skull could not be removed on the server${code ? ` (error ${code})` : ''}. No segmentation was produced; try again later.`);
          return null;
        }
      };

      const start = (prepared: Prepared) => {
        const worker = new Worker(new URL('../workers/flamesInBrowser.worker.ts', import.meta.url), { type: 'module' });
        workerRef.current = worker;
        const envUrl = import.meta.env.VITE_FLAMES_MODEL_URL as string | undefined;
        const model = { ...FLAMES_FOLD0_MODEL, url: envUrl || FLAMES_FOLD0_MODEL.url };
        worker.onmessage = async (event: MessageEvent<FlamesWorkerResponse>) => {
          const m = event.data;
          if (m.jobId !== jobRef.current) return;
          if (m.type === 'progress') {
            setStage(m.stage);
            setFraction(m.fraction);
            setMessage(m.message);
          } else if (m.type === 'log') {
            console.info('[BrowserFLAMeS]', m.message);
          } else if (m.type === 'result') {
            workerRef.current?.terminate();
            workerRef.current = null;
            jobRef.current = null;
            setResult({ fileId, maskApp: m.maskApp, dims: m.dims, spacing: m.spacing, summary: m.summary, provenance: m.provenance });
            setStatus('done');
          } else if (m.type === 'error') {
            if (m.kind === 'skull' && !prepared.strippedByApp) {
              worker.terminate();
              workerRef.current = null;
              const stripped = await stripOnServer(m.message);
              if (stripped && current()) start(stripped);
              return;
            }
            fail(m.message);
          }
        };
        worker.onerror = (e) => fail(e.message || 'The segmentation worker stopped unexpectedly.');
        // WebGPU is NOT attempted by default: ONNX Runtime Web 1.24.1 (the app's SOUP version) rejects 3D convolutions on WebGPU,
        // and with 1.29 an integrated GPU lost the device (DESIGN.md §7.1).
        worker.postMessage(
          {
            type: 'segment',
            jobId,
            nifti: prepared.nifti,
            model,
            preferWebGPU: Boolean(options.webgpu),
            mirror: Boolean(options.mirror),
            seriesDescription: options.seriesDescription ?? null,
            clinicianConfirmedFlair: options.clinicianConfirmedFlair === true,
            strippedByApp: prepared.strippedByApp,
            stripModel: prepared.stripModel,
          },
          [prepared.nifti],
        );
      };

      try {
        const { data } = await apiClient.get(`/api/v1/imaging/nifti/${fileId}`, { responseType: 'arraybuffer', signal: abort.signal });
        if (!current()) return;
        start({ nifti: data as ArrayBuffer, strippedByApp: false });
      } catch (err) {
        fail(err instanceof Error ? err.message : String(err));
      }
    },
    [terminate],
  );

  /**
   * Cancel: terminates the worker, aborts a skull removal in flight and forgets the job. It never touches the segmentation store,
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
