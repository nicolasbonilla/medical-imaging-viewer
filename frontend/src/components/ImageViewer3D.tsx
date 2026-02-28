/**
 * 3D Brain MRI Viewer using NiiVue volume rendering.
 *
 * Two modes:
 * - Volume: single NiiVue canvas with 3D ray-casting (rotate, zoom, pan)
 * - Multiplanar: 2x2 grid — 3D + Axial + Coronal + Sagittal, all synced
 *
 * Downloads NIfTI once with progress tracking, then loads into NiiVue
 * from a blob URL (no repeated network calls on mode switch).
 *
 * @module components/ImageViewer3D
 */

import { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Niivue, NVImage, SLICE_TYPE, SHOW_RENDER } from '@niivue/niivue';
import { Loader2, AlertCircle, Box } from 'lucide-react';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchWithProgress(
  url: string,
  headers: Record<string, string>,
  onProgress: (percent: number, loadedMB: number, totalMB: number) => void,
): Promise<ArrayBuffer> {
  const response = await fetch(url, { headers });
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`HTTP ${response.status}: ${text.slice(0, 200) || response.statusText}`);
  }
  const contentLength = response.headers.get('content-length');
  const total = contentLength ? parseInt(contentLength, 10) : 0;
  if (!total || !response.body) {
    onProgress(-1, 0, 0);
    const buffer = await response.arrayBuffer();
    onProgress(100, buffer.byteLength / 1048576, buffer.byteLength / 1048576);
    return buffer;
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.length;
    onProgress(Math.round((received / total) * 100), received / 1048576, total / 1048576);
  }
  const merged = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged.buffer;
}

const COLORMAPS_3D = [
  { id: 'gray', label: 'Gray' },
  { id: 'hot', label: 'Hot' },
  { id: 'bone', label: 'Bone' },
  { id: 'winter', label: 'Winter' },
  { id: 'viridis', label: 'Viridis' },
  { id: 'cool', label: 'Cool' },
  { id: 'ge_color', label: 'GE Color' },
  { id: 'inferno', label: 'Inferno' },
] as const;

/** Panel labels for 2x2 grid */
const PANEL_CONFIG = [
  { key: '3d', sliceType: SLICE_TYPE.RENDER, label: '3D' },
  { key: 'axial', sliceType: SLICE_TYPE.AXIAL, label: 'Axial' },
  { key: 'coronal', sliceType: SLICE_TYPE.CORONAL, label: 'Coronal' },
  { key: 'sagittal', sliceType: SLICE_TYPE.SAGITTAL, label: 'Sagittal' },
] as const;

/** Create a NiiVue instance for a specific slice type */
function createNvInstance(sliceType: number): Niivue {
  return new Niivue({
    backColor: [0, 0, 0, 1],
    show3Dcrosshair: sliceType === SLICE_TYPE.RENDER,
    isRadiologicalConvention: false,
    sliceType,
    multiplanarShowRender: SHOW_RENDER.NEVER,
    isColorbar: sliceType === SLICE_TYPE.RENDER,
    isOrientCube: sliceType === SLICE_TYPE.RENDER,
    crosshairWidth: 1,
    crosshairColor: [1, 0, 0, 1],
    textHeight: 0.03,
    clipPlaneColor: [1, 1, 1, 0.5],
    loadingText: '',
  });
}

export default function ImageViewer3D() {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);

  const currentSeries = useViewerStore((s) => s.currentSeries);
  const render3DMode = useViewerStore((s) => s.render3DMode);
  const colormap3D = useViewerStore((s) => s.colormap3D);
  const clipPlaneEnabled = useViewerStore((s) => s.clipPlaneEnabled);
  const clipPlanePosition = useViewerStore((s) => s.clipPlanePosition);
  const clipPlaneAxis = useViewerStore((s) => s.clipPlaneAxis);
  const currentSegmentation = useSegmentationStore((s) => s.currentSegmentation);

  // Downloaded NIfTI data (persists across mode switches)
  const [niftiBuffer, setNiftiBuffer] = useState<ArrayBuffer | null>(null);
  const [segBuffer, setSegBuffer] = useState<ArrayBuffer | null>(null);

  // Loading state
  const [isLoading, setIsLoading] = useState(false);
  const [loadProgress, setLoadProgress] = useState(0);
  const [loadedMB, setLoadedMB] = useState(0);
  const [totalMB, setTotalMB] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Volume mode: single instance
  const volumeCanvasRef = useRef<HTMLCanvasElement>(null);
  const volumeNvRef = useRef<Niivue | null>(null);
  const [volumeReady, setVolumeReady] = useState(false);

  // Multiplanar mode: 4 instances
  const mpCanvasRefs = useRef<(HTMLCanvasElement | null)[]>([null, null, null, null]);
  const mpNvRefs = useRef<(Niivue | null)[]>([null, null, null, null]);
  const [mpReady, setMpReady] = useState(false);

  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  const fileId = currentSeries?.file_id;

  const niftiUrl = useMemo(() => {
    if (!fileId) return null;
    return `${API_BASE_URL}/api/v1/imaging/nifti/${fileId}`;
  }, [fileId]);

  const segNiftiUrl = useMemo(() => {
    const segId = currentSegmentation?.segmentation_id;
    if (!segId || segId.startsWith('local-')) return null;
    return `${API_BASE_URL}/api/v1/segmentation/${segId}/nifti`;
  }, [currentSegmentation?.segmentation_id]);

  // Callback ref setter for multiplanar canvases
  const setMpCanvasRef = useCallback((index: number) => (el: HTMLCanvasElement | null) => {
    mpCanvasRefs.current[index] = el;
  }, []);

  // Track container size
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const updateSize = () => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w > 0 && h > 0) setContainerSize({ width: w, height: h });
    };
    updateSize();
    const ro = new ResizeObserver(updateSize);
    ro.observe(container);
    return () => ro.disconnect();
  }, []);

  // ─── EFFECT 1: Download NIfTI data ───
  useEffect(() => {
    if (!niftiUrl) return;
    let cancelled = false;

    const download = async () => {
      setIsLoading(true);
      setError(null);
      setNiftiBuffer(null);
      setLoadProgress(0);
      setLoadedMB(0);
      setTotalMB(0);

      try {
        const headers = getAuthHeaders();
        console.log('[3D] Fetching NIfTI:', niftiUrl);
        const buffer = await fetchWithProgress(niftiUrl, headers, (pct, loaded, total) => {
          if (cancelled) return;
          setLoadProgress(pct);
          setLoadedMB(loaded);
          setTotalMB(total);
        });
        if (cancelled) return;
        console.log('[3D] Downloaded:', (buffer.byteLength / 1048576).toFixed(1), 'MB');
        setNiftiBuffer(buffer);
        setLoadProgress(100);
        setIsLoading(false);
      } catch (err) {
        if (cancelled) return;
        console.error('[3D] Download failed:', err);
        setError(err instanceof Error ? err.message : 'Download failed');
        setIsLoading(false);
      }
    };

    download();
    return () => { cancelled = true; };
  }, [niftiUrl]);

  // ─── EFFECT 1b: Download segmentation NIfTI ───
  useEffect(() => {
    if (!segNiftiUrl) { setSegBuffer(null); return; }
    let cancelled = false;
    const download = async () => {
      try {
        const headers = getAuthHeaders();
        const buffer = await fetchWithProgress(segNiftiUrl, headers, () => {});
        if (!cancelled) setSegBuffer(buffer);
      } catch (err) {
        console.error('[3D] Seg download failed:', err);
      }
    };
    download();
    return () => { cancelled = true; };
  }, [segNiftiUrl]);

  // ─── EFFECT 2: Volume mode — single NiiVue instance ───
  useEffect(() => {
    if (render3DMode !== 'volume' || !niftiBuffer || !volumeCanvasRef.current || containerSize.width === 0) return;

    let blobUrl: string | null = null;
    let segBlobUrl: string | null = null;

    const init = async () => {
      try {
        const nv = createNvInstance(SLICE_TYPE.RENDER);
        nv.attachToCanvas(volumeCanvasRef.current!);
        volumeNvRef.current = nv;

        blobUrl = URL.createObjectURL(new Blob([niftiBuffer]));
        await nv.loadVolumes([{ url: blobUrl, colormap: colormap3D, opacity: 1 }]);
        nv.setRenderAzimuthElevation(0, 15);

        // Load segmentation overlay if available
        if (segBuffer) {
          segBlobUrl = URL.createObjectURL(new Blob([segBuffer]));
          const segVol = await NVImage.loadFromUrl({ url: segBlobUrl, colormap: 'red', opacity: 0.5 });
          nv.addVolume(segVol);
        }

        setVolumeReady(true);
        console.log('[3D] Volume mode ready');
      } catch (err) {
        console.error('[3D] Volume init failed:', err);
        setError(err instanceof Error ? err.message : 'Volume init failed');
      }
    };

    init();

    return () => {
      volumeNvRef.current = null;
      setVolumeReady(false);
      if (blobUrl) URL.revokeObjectURL(blobUrl);
      if (segBlobUrl) URL.revokeObjectURL(segBlobUrl);
    };
  }, [render3DMode, niftiBuffer, segBuffer, containerSize.width]);

  // ─── EFFECT 3: Multiplanar mode — 4 NiiVue instances with sync ───
  useEffect(() => {
    if (render3DMode !== 'multiplanar' || !niftiBuffer || containerSize.width === 0) return;

    // Wait for all 4 canvases to be mounted
    const canvases = mpCanvasRefs.current;
    if (!canvases[0] || !canvases[1] || !canvases[2] || !canvases[3]) return;

    const blobUrls: string[] = [];
    let cancelled = false;

    const init = async () => {
      try {
        const nvInstances: Niivue[] = [];

        // Create 4 NiiVue instances
        for (let i = 0; i < 4; i++) {
          const nv = createNvInstance(PANEL_CONFIG[i].sliceType);
          nv.attachToCanvas(canvases[i]!);
          mpNvRefs.current[i] = nv;
          nvInstances.push(nv);
        }

        // Load volume into all 4 from blob URLs
        for (let i = 0; i < 4; i++) {
          const url = URL.createObjectURL(new Blob([niftiBuffer]));
          blobUrls.push(url);
          await nvInstances[i].loadVolumes([{ url, colormap: colormap3D, opacity: 1 }]);

          // Load segmentation overlay into each
          if (segBuffer) {
            const segUrl = URL.createObjectURL(new Blob([segBuffer]));
            blobUrls.push(segUrl);
            const segVol = await NVImage.loadFromUrl({
              url: segUrl,
              colormap: 'red',
              opacity: i === 0 ? 0.5 : 0.3, // Less opaque on slice views
            });
            nvInstances[i].addVolume(segVol);
          }
        }

        if (cancelled) return;

        // Set 3D panel view angle
        nvInstances[0].setRenderAzimuthElevation(0, 15);

        // Bidirectional sync: each instance broadcasts to all others
        for (let i = 0; i < 4; i++) {
          const others = nvInstances.filter((_, j) => j !== i);
          nvInstances[i].broadcastTo(others, { '2d': true, '3d': true });
        }

        setMpReady(true);
        console.log('[3D] Multiplanar mode ready, 4 instances synced');
      } catch (err) {
        console.error('[3D] Multiplanar init failed:', err);
        setError(err instanceof Error ? err.message : 'Multiplanar init failed');
      }
    };

    // Small delay to ensure canvases have dimensions after mount
    const timer = setTimeout(init, 50);

    return () => {
      cancelled = true;
      clearTimeout(timer);
      mpNvRefs.current = [null, null, null, null];
      setMpReady(false);
      blobUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [render3DMode, niftiBuffer, segBuffer, containerSize.width]);

  // ─── EFFECT 4: Update colormap ───
  useEffect(() => {
    if (render3DMode === 'volume' && volumeReady && volumeNvRef.current) {
      const nv = volumeNvRef.current;
      if (nv.volumes.length > 0) {
        nv.volumes[0].colormap = colormap3D;
        nv.updateGLVolume();
      }
    } else if (render3DMode === 'multiplanar' && mpReady) {
      mpNvRefs.current.forEach((nv) => {
        if (nv && nv.volumes.length > 0) {
          nv.volumes[0].colormap = colormap3D;
          nv.updateGLVolume();
        }
      });
    }
  }, [colormap3D, volumeReady, mpReady, render3DMode]);

  // ─── EFFECT 5: Update clip plane (applies to 3D panel only) ───
  useEffect(() => {
    // Get the 3D NiiVue instance
    const nv3d = render3DMode === 'volume' ? volumeNvRef.current : mpNvRefs.current[0];
    const ready = render3DMode === 'volume' ? volumeReady : mpReady;
    if (!nv3d || !ready) return;

    if (clipPlaneEnabled) {
      const depth = clipPlanePosition * 1.73;
      const axisAngles = {
        axial:    [depth, 0, 90],
        coronal:  [depth, 0, 0],
        sagittal: [depth, 270, 0],
      };
      nv3d.setClipPlane(axisAngles[clipPlaneAxis]);
    } else {
      nv3d.setClipPlane([3, 0, 0]);
    }
  }, [clipPlaneEnabled, clipPlanePosition, clipPlaneAxis, volumeReady, mpReady, render3DMode]);

  // ─── Early returns for missing data ───
  if (!currentSeries) {
    return (
      <div className="flex items-center justify-center h-full bg-black">
        <div className="text-center text-gray-400">
          <Box className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>{t('viewer.selectImageFor3D', 'Select an image for 3D viewing')}</p>
        </div>
      </div>
    );
  }

  if (!fileId) {
    return (
      <div className="flex items-center justify-center h-full bg-black">
        <div className="text-center text-gray-400">
          <AlertCircle className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>{t('viewer.noFileId', 'No file available for 3D rendering')}</p>
        </div>
      </div>
    );
  }

  const isReady = render3DMode === 'volume' ? volumeReady : mpReady;

  return (
    <div className="relative h-full bg-black">
      <div ref={containerRef} className="absolute inset-0">
        {/* Volume mode: single canvas */}
        {render3DMode === 'volume' && (
          <canvas
            ref={volumeCanvasRef}
            width={containerSize.width}
            height={containerSize.height}
            style={{ width: '100%', height: '100%', display: 'block' }}
          />
        )}

        {/* Multiplanar mode: 2x2 grid */}
        {render3DMode === 'multiplanar' && (
          <div className="grid grid-cols-2 grid-rows-2 w-full h-full gap-px bg-gray-800">
            {PANEL_CONFIG.map((panel, i) => (
              <div key={panel.key} className="relative bg-black overflow-hidden">
                <canvas
                  ref={setMpCanvasRef(i)}
                  width={Math.floor(containerSize.width / 2)}
                  height={Math.floor(containerSize.height / 2)}
                  style={{ width: '100%', height: '100%', display: 'block' }}
                />
                {/* Panel label */}
                <div className="absolute top-1 left-2 text-[10px] font-bold text-gray-400 pointer-events-none uppercase tracking-wider">
                  {panel.label}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/80 z-10">
          <div className="flex flex-col items-center gap-4 w-72">
            <Loader2 className="w-10 h-10 text-blue-500 animate-spin" />
            <p className="text-white text-sm font-medium">
              {t('viewer.loading3D', 'Loading 3D volume...')}
            </p>
            <div className="w-full">
              <div className="w-full h-2.5 bg-gray-700 rounded-full overflow-hidden">
                {loadProgress >= 0 ? (
                  <div
                    className="h-full bg-blue-500 rounded-full transition-all duration-200"
                    style={{ width: `${loadProgress}%` }}
                  />
                ) : (
                  <div className="h-full bg-blue-500 rounded-full animate-pulse w-full opacity-40" />
                )}
              </div>
              <div className="flex justify-between mt-1.5">
                <span className="text-gray-400 text-xs">
                  {loadProgress >= 0 ? `${loadProgress}%` : t('viewer.downloading', 'Downloading...')}
                </span>
                {totalMB > 0 && (
                  <span className="text-gray-400 text-xs">
                    {loadedMB.toFixed(1)} / {totalMB.toFixed(1)} MB
                  </span>
                )}
              </div>
            </div>
            <p className="text-gray-500 text-xs text-center">
              {loadProgress === 100
                ? t('viewer.rendering3D', 'Initializing WebGL renderer...')
                : t('viewer.loading3DDesc', 'Downloading NIfTI file for WebGL rendering')}
            </p>
          </div>
        </div>
      )}

      {/* Error overlay */}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/80 z-10">
          <div className="text-center p-6 max-w-sm">
            <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-3" />
            <p className="text-red-400 font-medium">{t('viewer.error3D', '3D rendering failed')}</p>
            <p className="text-gray-400 text-sm mt-2 break-words">{error}</p>
          </div>
        </div>
      )}

      {/* Instructions (volume mode only) */}
      {isReady && !isLoading && render3DMode === 'volume' && (
        <div className="absolute bottom-3 left-3 bg-black/60 backdrop-blur-sm rounded-lg px-3 py-2 text-[10px] text-gray-400 space-y-0.5 z-10 pointer-events-none">
          <div>{t('viewer.3d.dragRotate', 'Left-click drag: Rotate')}</div>
          <div>{t('viewer.3d.scrollZoom', 'Scroll: Zoom')}</div>
          <div>{t('viewer.3d.rightPan', 'Right-click drag: Pan')}</div>
        </div>
      )}
    </div>
  );
}

export { COLORMAPS_3D };
