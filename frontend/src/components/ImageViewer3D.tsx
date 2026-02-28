/**
 * 3D Brain MRI Viewer using NiiVue volume rendering.
 *
 * Downloads NIfTI files with auth + progress tracking, then loads
 * into NiiVue's WebGL2 ray-casting volume renderer. Supports:
 * - Volume rendering (3D) with rotation, zoom, pan
 * - Multiplanar view (axial + coronal + sagittal + 3D)
 * - Colormaps, clip planes, orientation cube
 * - Segmentation overlay in 3D
 * - Download progress with percentage
 *
 * @module components/ImageViewer3D
 */

import { useEffect, useRef, useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Niivue, NVImage, SLICE_TYPE, SHOW_RENDER } from '@niivue/niivue';
import { Loader2, AlertCircle, Box } from 'lucide-react';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/** Get auth token from localStorage */
function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Fetch a file with progress tracking via ReadableStream.
 * Returns an ArrayBuffer of the downloaded content.
 */
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

  // If no content-length or no body stream, fall back to simple arrayBuffer()
  if (!total || !response.body) {
    onProgress(-1, 0, 0); // indeterminate
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
    const percent = Math.round((received / total) * 100);
    onProgress(percent, received / 1048576, total / 1048576);
  }

  // Merge chunks into single ArrayBuffer
  const merged = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }

  return merged.buffer;
}

/** Available colormaps for 3D rendering */
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

export default function ImageViewer3D() {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const nvRef = useRef<Niivue | null>(null);

  const currentSeries = useViewerStore((s) => s.currentSeries);
  const render3DMode = useViewerStore((s) => s.render3DMode);
  const colormap3D = useViewerStore((s) => s.colormap3D);
  const clipPlaneEnabled = useViewerStore((s) => s.clipPlaneEnabled);
  const clipPlanePosition = useViewerStore((s) => s.clipPlanePosition);
  const clipPlaneAxis = useViewerStore((s) => s.clipPlaneAxis);
  const currentSegmentation = useSegmentationStore((s) => s.currentSegmentation);

  // Reactive flag so load-volume effect re-runs when NiiVue is ready
  const [nvReady, setNvReady] = useState(false);

  const [isLoading, setIsLoading] = useState(false);
  const [loadProgress, setLoadProgress] = useState(0); // 0-100, -1 = indeterminate
  const [loadedMB, setLoadedMB] = useState(0);
  const [totalMB, setTotalMB] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [volumeLoaded, setVolumeLoaded] = useState(false);
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });

  const fileId = currentSeries?.file_id;

  // Build NIfTI URL
  const niftiUrl = useMemo(() => {
    if (!fileId) return null;
    return `${API_BASE_URL}/api/v1/imaging/nifti/${fileId}`;
  }, [fileId]);

  // Build segmentation NIfTI URL
  const segNiftiUrl = useMemo(() => {
    const segId = currentSegmentation?.segmentation_id;
    if (!segId || segId.startsWith('local-')) return null;
    return `${API_BASE_URL}/api/v1/segmentation/${segId}/nifti`;
  }, [currentSegmentation?.segmentation_id]);

  // Track container size
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const updateSize = () => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w > 0 && h > 0) setCanvasSize({ width: w, height: h });
    };

    updateSize();
    const ro = new ResizeObserver(updateSize);
    ro.observe(container);
    return () => ro.disconnect();
  }, []);

  // Initialize NiiVue once canvas has dimensions
  useEffect(() => {
    if (!canvasRef.current || canvasSize.width === 0 || canvasSize.height === 0) return;
    if (nvRef.current) return; // already initialized

    try {
      const nv = new Niivue({
        backColor: [0, 0, 0, 1],
        show3Dcrosshair: true,
        isRadiologicalConvention: false,
        sliceType: SLICE_TYPE.RENDER,
        multiplanarShowRender: SHOW_RENDER.ALWAYS,
        isColorbar: true,
        isOrientCube: true,
        crosshairWidth: 1,
        textHeight: 0.03,
        clipPlaneColor: [1, 1, 1, 0.5],
        loadingText: '',
      });

      nv.attachToCanvas(canvasRef.current);
      nvRef.current = nv;
      setNvReady(true); // <-- triggers load-volume effect
      console.log('[ImageViewer3D] NiiVue initialized, canvas:', canvasSize.width, 'x', canvasSize.height);
    } catch (err) {
      console.error('[ImageViewer3D] NiiVue init failed:', err);
      setError(err instanceof Error ? err.message : 'WebGL initialization failed');
    }

    return () => {
      nvRef.current = null;
      setNvReady(false);
    };
  }, [canvasSize.width, canvasSize.height]);

  // Redraw on resize
  useEffect(() => {
    if (!nvRef.current || canvasSize.width === 0) return;
    nvRef.current.drawScene();
  }, [canvasSize.width, canvasSize.height]);

  // Load volume: fetch ourselves with progress, then give blob URL to NiiVue
  // Depends on BOTH niftiUrl AND nvReady to avoid race condition
  useEffect(() => {
    if (!nvReady || !niftiUrl) {
      console.log('[ImageViewer3D] Waiting...', { nvReady, hasUrl: !!niftiUrl });
      return;
    }

    let cancelled = false;
    let blobUrl: string | null = null;

    const loadVolume = async () => {
      const nv = nvRef.current;
      if (!nv) return;

      setIsLoading(true);
      setError(null);
      setVolumeLoaded(false);
      setLoadProgress(0);
      setLoadedMB(0);
      setTotalMB(0);

      try {
        // Step 1: Download NIfTI with progress tracking
        const headers = getAuthHeaders();
        console.log('[ImageViewer3D] Fetching NIfTI:', niftiUrl);

        const buffer = await fetchWithProgress(niftiUrl, headers, (percent, loaded, total) => {
          if (cancelled) return;
          setLoadProgress(percent);
          setLoadedMB(loaded);
          setTotalMB(total);
        });

        if (cancelled) return;
        console.log('[ImageViewer3D] Downloaded:', (buffer.byteLength / 1048576).toFixed(1), 'MB');

        // Step 2: Create blob URL so NiiVue loads from local memory
        const blob = new Blob([buffer]);
        blobUrl = URL.createObjectURL(blob);

        // Step 3: Load into NiiVue from blob URL
        setLoadProgress(100);
        console.log('[ImageViewer3D] Loading into NiiVue...');
        await nv.loadVolumes([{
          url: blobUrl,
          colormap: colormap3D,
          opacity: 1,
        }]);

        if (cancelled) return;
        console.log('[ImageViewer3D] Volume loaded, volumes:', nv.volumes.length);

        // Default view: front (coronal) so top-to-bottom clip makes sense
        nv.setRenderAzimuthElevation(0, 15);

        setVolumeLoaded(true);
        setIsLoading(false);
      } catch (err) {
        if (cancelled) return;
        console.error('[ImageViewer3D] Failed to load NIfTI:', err);
        setError(err instanceof Error ? err.message : 'Failed to load volume');
        setIsLoading(false);
      }
    };

    loadVolume();

    return () => {
      cancelled = true;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [niftiUrl, nvReady]);

  // Load segmentation overlay (also with our own fetch)
  useEffect(() => {
    if (!nvReady || !volumeLoaded || !segNiftiUrl) return;

    let cancelled = false;
    let blobUrl: string | null = null;

    const loadSegOverlay = async () => {
      const nv = nvRef.current;
      if (!nv) return;

      try {
        // Remove existing overlays (keep main volume at index 0)
        while (nv.volumes.length > 1) {
          nv.removeVolume(nv.volumes[1]);
        }

        const headers = getAuthHeaders();
        const buffer = await fetchWithProgress(segNiftiUrl, headers, () => {});

        if (cancelled) return;

        const blob = new Blob([buffer]);
        blobUrl = URL.createObjectURL(blob);

        const segVolume = await NVImage.loadFromUrl({
          url: blobUrl,
          colormap: 'red',
          opacity: 0.5,
        });

        if (cancelled) return;
        nv.addVolume(segVolume);
        console.log('[ImageViewer3D] Segmentation overlay loaded');
      } catch (err) {
        console.error('[ImageViewer3D] Failed to load segmentation overlay:', err);
      }
    };

    loadSegOverlay();

    return () => {
      cancelled = true;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [segNiftiUrl, volumeLoaded, nvReady]);

  // Update render mode
  useEffect(() => {
    if (!nvRef.current || !volumeLoaded) return;

    if (render3DMode === 'multiplanar') {
      nvRef.current.setSliceType(SLICE_TYPE.MULTIPLANAR);
    } else {
      nvRef.current.setSliceType(SLICE_TYPE.RENDER);
    }
  }, [render3DMode, volumeLoaded]);

  // Update colormap
  useEffect(() => {
    if (!nvRef.current || !volumeLoaded || nvRef.current.volumes.length === 0) return;

    nvRef.current.volumes[0].colormap = colormap3D;
    nvRef.current.updateGLVolume();
  }, [colormap3D, volumeLoaded]);

  // Update clip plane
  useEffect(() => {
    if (!nvRef.current || !volumeLoaded) return;

    if (clipPlaneEnabled) {
      const depth = clipPlanePosition * 1.73;
      // Axis angles: [depth, azimuth, elevation]
      const axisAngles = {
        axial:    [depth, 0, 90],    // XY plane, top-to-bottom
        coronal:  [depth, 0, 0],     // XZ plane, front-to-back
        sagittal: [depth, 270, 0],   // YZ plane, left-to-right
      };
      nvRef.current.setClipPlane(axisAngles[clipPlaneAxis]);
    } else {
      nvRef.current.setClipPlane([3, 0, 0]);
    }
  }, [clipPlaneEnabled, clipPlanePosition, clipPlaneAxis, volumeLoaded]);

  // No image loaded
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

  return (
    <div className="relative h-full bg-black">
      {/* Canvas container */}
      <div ref={containerRef} className="absolute inset-0">
        <canvas
          ref={canvasRef}
          width={canvasSize.width}
          height={canvasSize.height}
          style={{ width: '100%', height: '100%', display: 'block' }}
        />
      </div>

      {/* Loading overlay with progress */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/80 z-10">
          <div className="flex flex-col items-center gap-4 w-72">
            <Loader2 className="w-10 h-10 text-blue-500 animate-spin" />
            <p className="text-white text-sm font-medium">
              {t('viewer.loading3D', 'Loading 3D volume...')}
            </p>

            {/* Progress bar */}
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

      {/* Instructions overlay (bottom-left, subtle) */}
      {volumeLoaded && !isLoading && (
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
