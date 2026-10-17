/**
 * useClientVolume — download the raw NIfTI once (the same file the 3D view uses) and
 * parse it in the browser for the v3 client 2D viewer. Uses the shared apiClient, so
 * the request carries the user's auth and goes through the same object-level
 * authorization on the server (`/imaging/nifti/{file}` → require_imaging_access).
 */
import { useEffect, useState } from 'react';
import { apiClient } from '@/services/apiClient';
import { isUnsupportedNifti, loadClientVolume, type ClientVolume } from '@/volume/clientVolume';

export type ClientVolumeState =
  | { status: 'idle' }
  | { status: 'loading'; progress: number | null }
  | { status: 'ready'; volume: ClientVolume }
  | { status: 'error'; error: string; unsupported: boolean };

const progressListeners = new Map<string, (pct: number | null) => void>();

async function fetchNiftiBuffer(fileId: string): Promise<ArrayBuffer> {
  const { data } = await apiClient.get<ArrayBuffer>(`/api/v1/imaging/nifti/${fileId}`, {
    responseType: 'arraybuffer',
    timeout: 180_000,
    onDownloadProgress: (e) => {
      const pct = e.total ? Math.round((e.loaded / e.total) * 100) : null;
      progressListeners.get(fileId)?.(pct);
    },
  });
  return data;
}

export function useClientVolume(fileId: string | undefined, enabled: boolean): ClientVolumeState {
  const [state, setState] = useState<ClientVolumeState>({ status: 'idle' });

  useEffect(() => {
    if (!enabled || !fileId) {
      setState({ status: 'idle' });
      return;
    }
    let cancelled = false;
    setState({ status: 'loading', progress: null });
    progressListeners.set(fileId, (progress) => {
      if (!cancelled) setState((s) => (s.status === 'loading' ? { status: 'loading', progress } : s));
    });
    loadClientVolume(fileId, fetchNiftiBuffer)
      .then((volume) => { if (!cancelled) setState({ status: 'ready', volume }); })
      .catch((e: unknown) => {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : String(e);
        setState({ status: 'error', error: msg, unsupported: isUnsupportedNifti(e) });
      })
      .finally(() => progressListeners.delete(fileId));
    return () => { cancelled = true; };
  }, [fileId, enabled]);

  return state;
}
