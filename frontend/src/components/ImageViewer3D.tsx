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
import { Loader2, AlertCircle, Box, ZoomIn, ZoomOut, Eye } from 'lucide-react';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { createBoundingBoxMZ3 } from '@/utils/boundingBoxMesh';

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

/**
 * Register a discrete MAGNIMS zone colormap on a NiiVue instance.
 * Uses addColormap (custom colormap) instead of colormapLabel which
 * doesn't render colors in 3D volume mode.
 *
 * With cal_min=0, cal_max=4 the value→index mapping is:
 *   value 0 → idx 0 (transparent), value 1 → idx ~64 (PV),
 *   value 2 → idx ~128 (JC), value 3 → idx ~191 (IT), value 4 → idx 255 (DWM)
 */
function registerZoneMapColormap(nv: Niivue): void {
  const R = new Array(256).fill(0);
  const G = new Array(256).fill(0);
  const B = new Array(256).fill(0);
  const A = new Array(256).fill(0); // transparent by default (background)
  const I = new Array(256).fill(0);
  for (let i = 0; i < 256; i++) I[i] = i;

  // PV: Red [255, 0, 0] — indices 32-95
  for (let i = 32; i < 96; i++) { R[i] = 255; A[i] = 255; }
  // JC: Green [0, 204, 0] — indices 96-159
  for (let i = 96; i < 160; i++) { G[i] = 204; A[i] = 255; }
  // IT: Blue [0, 102, 255] — indices 160-223
  for (let i = 160; i < 224; i++) { G[i] = 102; B[i] = 255; A[i] = 255; }
  // DWM: Yellow [255, 215, 0] — indices 224-255
  for (let i = 224; i < 256; i++) { R[i] = 255; G[i] = 215; A[i] = 255; }

  nv.addColormap('magnims_zones', { R, G, B, A, I });
}

/** Create a NiiVue instance for a specific slice type */
function createNvInstance(sliceType: number): Niivue {
  const nv = new Niivue({
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
  return nv;
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
  const selectedLesion = useSegmentationStore((s) => s.selectedLesion);
  const zoneMapSegId = useSegmentationStore((s) => s.zoneMapSegId);
  const zoneMapVisible = useSegmentationStore((s) => s.zoneMapVisible);
  const zoneMapOpacity = useSegmentationStore((s) => s.zoneMapOpacity);
  const currentSliceIndex = useViewerStore((s) => s.currentSliceIndex);

  // Longitudinal overlay state
  const longTp1SegId = useSegmentationStore((s) => s.longitudinalTp1SegId);
  const longTp2SegId = useSegmentationStore((s) => s.longitudinalTp2SegId);
  const longitudinalVisible = useSegmentationStore((s) => s.longitudinalVisible);

  // Downloaded NIfTI data (persists across mode switches)
  const [niftiBuffer, setNiftiBuffer] = useState<ArrayBuffer | null>(null);
  const [segBuffer, setSegBuffer] = useState<ArrayBuffer | null>(null);
  const [zoneMapBuffer, setZoneMapBuffer] = useState<ArrayBuffer | null>(null);
  const [longTp1Buffer, setLongTp1Buffer] = useState<ArrayBuffer | null>(null);
  const [longTp2Buffer, setLongTp2Buffer] = useState<ArrayBuffer | null>(null);

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
  const bboxMeshUrlRef = useRef<string | null>(null);

  // Multiplanar mode: 4 instances
  const mpCanvasRefs = useRef<(HTMLCanvasElement | null)[]>([null, null, null, null]);
  const mpNvRefs = useRef<(Niivue | null)[]>([null, null, null, null]);
  const [mpReady, setMpReady] = useState(false);

  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  // Per-panel controls
  const [panelOpacity, setPanelOpacity] = useState([1, 1, 1, 1]);
  const [panelZoom, setPanelZoom] = useState([1, 1, 1, 1]);

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

  const zoneMapNiftiUrl = useMemo(() => {
    if (!zoneMapSegId || zoneMapSegId.startsWith('local-')) return null;
    return `${API_BASE_URL}/api/v1/segmentation/${zoneMapSegId}/nifti`;
  }, [zoneMapSegId]);

  // Callback ref setter for multiplanar canvases
  const setMpCanvasRef = useCallback((index: number) => (el: HTMLCanvasElement | null) => {
    mpCanvasRefs.current[index] = el;
  }, []);

  const handlePanelOpacity = useCallback((index: number, value: number) => {
    const nv = mpNvRefs.current[index];
    if (nv && nv.volumes.length > 0) {
      nv.setOpacity(0, value);
    }
    setPanelOpacity((prev) => { const next = [...prev]; next[index] = value; return next; });
  }, []);

  const handlePanelZoom = useCallback((index: number, delta: number) => {
    const nv = mpNvRefs.current[index];
    if (!nv) return;
    setPanelZoom((prev) => {
      const next = [...prev];
      next[index] = Math.max(0.5, Math.min(4, prev[index] + delta));
      if (index === 0) {
        nv.setScale(next[index]);
      } else {
        const pan = nv.scene.pan2Dxyzmm;
        nv.setPan2Dxyzmm([pan[0], pan[1], pan[2], next[index]]);
      }
      return next;
    });
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
        const buffer = await fetchWithProgress(niftiUrl, headers, (pct, loaded, total) => {
          if (cancelled) return;
          setLoadProgress(pct);
          setLoadedMB(loaded);
          setTotalMB(total);
        });
        if (cancelled) return;
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

  // ─── EFFECT 1c: Download zone map NIfTI ───
  useEffect(() => {
    if (!zoneMapNiftiUrl) { setZoneMapBuffer(null); return; }
    let cancelled = false;
    fetchWithProgress(zoneMapNiftiUrl, getAuthHeaders(), () => {})
      .then(buffer => { if (!cancelled) setZoneMapBuffer(buffer); })
      .catch(err => console.error('[3D] Zone map download failed:', err));
    return () => { cancelled = true; };
  }, [zoneMapNiftiUrl]);

  // ─── EFFECT 1d: Download longitudinal TP1 NIfTI (normalized orientation) ───
  useEffect(() => {
    if (!longTp1SegId || longTp1SegId.startsWith('local-')) { setLongTp1Buffer(null); return; }
    let cancelled = false;
    const url = `${API_BASE_URL}/api/v1/segmentation/${longTp1SegId}/nifti`;
    fetchWithProgress(url, getAuthHeaders(), () => {})
      .then(buffer => { if (!cancelled) setLongTp1Buffer(buffer); })
      .catch(err => console.error('[3D] Long TP1 download failed:', err));
    return () => { cancelled = true; };
  }, [longTp1SegId, fileId]);

  // ─── EFFECT 1e: Download longitudinal TP2 NIfTI (aligned to current MRI) ───
  useEffect(() => {
    if (!longTp2SegId || longTp2SegId.startsWith('local-')) { setLongTp2Buffer(null); return; }
    let cancelled = false;
    // Use ref_file_id to align TP2's axes and affine to the current MRI
    const url = `${API_BASE_URL}/api/v1/segmentation/${longTp2SegId}/nifti`;
    fetchWithProgress(url, getAuthHeaders(), () => {})
      .then(buffer => { if (!cancelled) setLongTp2Buffer(buffer); })
      .catch(err => console.error('[3D] Long TP2 download failed:', err));
    return () => { cancelled = true; };
  }, [longTp2SegId, fileId]);

  // ─── EFFECT 2: Volume mode — single NiiVue instance ───
  useEffect(() => {
    if (render3DMode !== 'volume' || !niftiBuffer || !volumeCanvasRef.current || containerSize.width === 0) return;

    const blobUrls: string[] = [];

    const init = async () => {
      try {
        const nv = createNvInstance(SLICE_TYPE.RENDER);
        await nv.attachToCanvas(volumeCanvasRef.current!);
        volumeNvRef.current = nv;

        const mainUrl = URL.createObjectURL(new Blob([niftiBuffer]));
        blobUrls.push(mainUrl);
        await nv.loadVolumes([{ url: mainUrl, colormap: colormap3D, opacity: 1 }]);
        nv.setRenderAzimuthElevation(0, 15);

        // Load segmentation overlay if available
        if (segBuffer) {
          const segUrl = URL.createObjectURL(new Blob([segBuffer]));
          blobUrls.push(segUrl);
          const segVol = await NVImage.loadFromUrl({ url: segUrl, colormap: 'red', opacity: 0.5 });
          nv.addVolume(segVol);
        }

        // Load zone map overlay if buffer available
        if (zoneMapBuffer) {
          registerZoneMapColormap(nv);
          const zmUrl = URL.createObjectURL(new Blob([zoneMapBuffer]));
          blobUrls.push(zmUrl);
          const zmVol = await NVImage.loadFromUrl({
            url: zmUrl,
            colormap: 'magnims_zones',
            cal_min: 0,
            cal_max: 4,
            opacity: zoneMapVisible ? zoneMapOpacity : 0,
          });
          nv.addVolume(zmVol);
        }

        // Load longitudinal TP1 overlay (blue) — original NIfTI, already aligned
        if (longTp1Buffer && longitudinalVisible) {
          const tp1Url = URL.createObjectURL(new Blob([longTp1Buffer]));
          blobUrls.push(tp1Url);
          const tp1Vol = await NVImage.loadFromUrl({ url: tp1Url, colormap: 'blue', opacity: 0.5 });
          nv.addVolume(tp1Vol);
        }

        // Load longitudinal TP2 overlay (red) — backend aligns to current MRI via ref_file_id
        if (longTp2Buffer && longitudinalVisible) {
          const tp2Url = URL.createObjectURL(new Blob([longTp2Buffer]));
          blobUrls.push(tp2Url);
          const tp2Vol = await NVImage.loadFromUrl({ url: tp2Url, colormap: 'hot', opacity: 0.5 });
          nv.addVolume(tp2Vol);
        }

        // Clip overlays along with MRI only when zone map is loaded
        // Only clip zone map with brain; longitudinal overlays stay visible through clip plane
        nv.backgroundMasksOverlays = (zoneMapBuffer && !longTp1Buffer) ? 1 : 0;

        setVolumeReady(true);
      } catch (err) {
        console.error('[3D] Volume init failed:', err);
        setError(err instanceof Error ? err.message : 'Volume init failed');
      }
    };

    init();

    return () => {
      bboxMeshUrlRef.current = null;
      volumeNvRef.current = null;
      setVolumeReady(false);
      blobUrls.forEach(url => URL.revokeObjectURL(url));
    };
  }, [render3DMode, niftiBuffer, segBuffer, zoneMapBuffer, longTp1Buffer, longTp2Buffer, longitudinalVisible, containerSize.width]);

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
          await nv.attachToCanvas(canvases[i]!);
          mpNvRefs.current[i] = nv;
          nvInstances.push(nv);
        }

        // Load volume into all 4 from blob URLs
        for (let i = 0; i < 4; i++) {
          const url = URL.createObjectURL(new Blob([niftiBuffer]));
          blobUrls.push(url);
          await nvInstances[i].loadVolumes([{ url, colormap: colormap3D, opacity: 1 }]);

          // Load segmentation overlay
          if (segBuffer) {
            const segUrl = URL.createObjectURL(new Blob([segBuffer]));
            blobUrls.push(segUrl);
            const segVol = await NVImage.loadFromUrl({
              url: segUrl,
              colormap: 'red',
              opacity: i === 0 ? 0.5 : 0.3,
            });
            nvInstances[i].addVolume(segVol);
          }

          // Load zone map overlay (opacity 0 if hidden; Effect 10 handles reactively)
          if (zoneMapBuffer) {
            registerZoneMapColormap(nvInstances[i]);
            const zmUrl = URL.createObjectURL(new Blob([zoneMapBuffer]));
            blobUrls.push(zmUrl);
            const initOpacity = zoneMapVisible ? zoneMapOpacity : 0;
            const zmVol = await NVImage.loadFromUrl({
              url: zmUrl,
              colormap: 'magnims_zones',
              cal_min: 0,
              cal_max: 4,
              opacity: i === 0 ? initOpacity : initOpacity * 0.7,
            });
            nvInstances[i].addVolume(zmVol);
          }

          // Load longitudinal TP1 overlay (blue)
          if (longTp1Buffer && longitudinalVisible) {
            const tp1Url = URL.createObjectURL(new Blob([longTp1Buffer]));
            blobUrls.push(tp1Url);
            const tp1Vol = await NVImage.loadFromUrl({ url: tp1Url, colormap: 'blue', opacity: i === 0 ? 0.5 : 0.3 });
            nvInstances[i].addVolume(tp1Vol);
          }

          // Load longitudinal TP2 overlay (red) — backend aligns via ref_file_id
          if (longTp2Buffer && longitudinalVisible) {
            const tp2Url = URL.createObjectURL(new Blob([longTp2Buffer]));
            blobUrls.push(tp2Url);
            const tp2Vol = await NVImage.loadFromUrl({ url: tp2Url, colormap: 'hot', opacity: i === 0 ? 0.5 : 0.3 });
            nvInstances[i].addVolume(tp2Vol);
          }
        }

        if (cancelled) return;

        // Clip overlays along with MRI when clip plane is active
        for (const nvInst of nvInstances) {
          nvInst.backgroundMasksOverlays = (zoneMapBuffer && !longTp1Buffer) ? 1 : 0;
        }

        // Set 3D panel view angle
        nvInstances[0].setRenderAzimuthElevation(0, 15);

        // Bidirectional sync: each instance broadcasts to all others
        for (let i = 0; i < 4; i++) {
          const others = nvInstances.filter((_, j) => j !== i);
          nvInstances[i].broadcastTo(others, { '2d': true, '3d': true });
        }

        setMpReady(true);
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
      bboxMeshUrlRef.current = null;
      mpNvRefs.current = [null, null, null, null];
      setMpReady(false);
      blobUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [render3DMode, niftiBuffer, segBuffer, zoneMapBuffer, longTp1Buffer, longTp2Buffer, longitudinalVisible, containerSize.width]);

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

  // ─── EFFECT 5: Update clip plane + sync crosshair to clip position ───
  useEffect(() => {
    // Get ALL active NiiVue instances (volume mode: 1, multiplanar: up to 4)
    const nvInstances: Niivue[] = render3DMode === 'volume'
      ? (volumeNvRef.current ? [volumeNvRef.current] : [])
      : mpNvRefs.current.filter((nv): nv is Niivue => nv !== null);
    const ready = render3DMode === 'volume' ? volumeReady : mpReady;

    if (nvInstances.length === 0 || !ready) return;

    if (clipPlaneEnabled) {
      const depthByAxis: Record<string, number> = {
        axial:    clipPlanePosition - 0.5,
        coronal:  0.5 - clipPlanePosition,
        sagittal: 0.5 - clipPlanePosition,
      };
      const depth = depthByAxis[clipPlaneAxis];
      const axisAngles: Record<string, number[]> = {
        axial:    [depth, 0, 90],
        coronal:  [depth, 0, 0],
        sagittal: [depth, 270, 0],
      };
      const clipParams = axisAngles[clipPlaneAxis];

      // Apply to ALL NiiVue instances (not just the 3D panel)
      for (const nv of nvInstances) {
        nv.setClipPlane(clipParams);
      }

      // Sync crosshair in multiplanar
      if (render3DMode === 'multiplanar') {
        const axisIndex = { axial: 2, coronal: 1, sagittal: 0 }[clipPlaneAxis];
        for (const nv of nvInstances) {
          if (nv.volumes.length > 0) {
            nv.scene.crosshairPos[axisIndex] = clipPlanePosition;
            nv.drawScene();
          }
        }
      }
    } else {
      for (const nv of nvInstances) {
        nv.setClipPlane([2, 0, 0]);
      }
      // Clip plane disabled
    }
  }, [clipPlaneEnabled, clipPlanePosition, clipPlaneAxis, volumeReady, mpReady, render3DMode]);

  // ─── EFFECT 6: Mouse wheel on 3D canvas → move clip plane ───
  useEffect(() => {
    if (!clipPlaneEnabled) return;
    const canvas = render3DMode === 'volume' ? volumeCanvasRef.current : mpCanvasRefs.current[0];
    const ready = render3DMode === 'volume' ? volumeReady : mpReady;
    if (!canvas || !ready) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? 0.02 : -0.02;
      const store = useViewerStore.getState();
      const newPos = Math.max(0, Math.min(1, store.clipPlanePosition + delta));
      store.setClipPlane(true, newPos);
    };

    canvas.addEventListener('wheel', handleWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', handleWheel);
  }, [clipPlaneEnabled, render3DMode, volumeReady, mpReady]);

  // ─── EFFECT 7: Navigate crosshair to selected lesion centroid ───
  useEffect(() => {
    if (!selectedLesion) return;
    const nv = render3DMode === 'volume' ? volumeNvRef.current : mpNvRefs.current[0];
    const ready = render3DMode === 'volume' ? volumeReady : mpReady;
    if (!nv || !ready || nv.volumes.length === 0) return;

    const { x, y, z } = selectedLesion.centroid;
    const vol = nv.volumes[0];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const va = vol as any;
    const dims = vol.dims;
    const affine: number[][] | undefined = va.hdr?.affine;

    // Convert file voxel coords → mm via affine, then mm → frac via NiiVue
    let frac: [number, number, number];
    if (affine) {
      const mm: [number, number, number] = [
        affine[0][0] * x + affine[0][1] * y + affine[0][2] * z + affine[0][3],
        affine[1][0] * x + affine[1][1] * y + affine[1][2] * z + affine[1][3],
        affine[2][0] * x + affine[2][1] * y + affine[2][2] * z + affine[2][3],
      ];
      frac = nv.mm2frac(mm, 0) as [number, number, number];
    } else if (dims && dims.length >= 4) {
      frac = [
        x / Math.max(1, dims[1] - 1),
        y / Math.max(1, dims[2] - 1),
        z / Math.max(1, dims[3] - 1),
      ];
    } else {
      return;
    }

    const setCrosshair = (nvInst: Niivue | null) => {
      if (!nvInst || nvInst.volumes.length === 0) return;
      nvInst.scene.crosshairPos = [...frac] as [number, number, number];
      nvInst.drawScene();
    };

    if (render3DMode === 'volume') {
      setCrosshair(nv);
    } else {
      mpNvRefs.current.forEach(setCrosshair);
    }
  }, [selectedLesion, render3DMode, volumeReady, mpReady]);

  // ─── EFFECT 8: Navigate crosshair from slice index (LongitudinalCompare, ComparisonMetrics) ───
  useEffect(() => {
    // Only react when no selectedLesion — selectedLesion takes priority via Effect 8
    if (selectedLesion) return;
    const nv = render3DMode === 'volume' ? volumeNvRef.current : mpNvRefs.current[0];
    const ready = render3DMode === 'volume' ? volumeReady : mpReady;
    if (!nv || !ready || nv.volumes.length === 0) return;

    const dims = nv.volumes[0].dims;
    const totalSlices = dims ? dims[3] : 0;
    if (totalSlices <= 1) return;

    const zFrac = currentSliceIndex / Math.max(1, totalSlices - 1);

    const updateCrosshair = (nvInst: Niivue | null) => {
      if (!nvInst || nvInst.volumes.length === 0) return;
      nvInst.scene.crosshairPos[2] = zFrac;
      nvInst.drawScene();
    };

    if (render3DMode === 'volume') {
      updateCrosshair(nv);
    } else {
      mpNvRefs.current.forEach(updateCrosshair);
    }
  }, [currentSliceIndex, selectedLesion, render3DMode, volumeReady, mpReady]);

  // ─── EFFECT 9: 3D bounding box mesh for selected lesion ───
  useEffect(() => {
    const ready = render3DMode === 'volume' ? volumeReady : mpReady;

    // Collect all active NiiVue instances
    const getNvInstances = (): Niivue[] => {
      if (render3DMode === 'volume') {
        return volumeNvRef.current ? [volumeNvRef.current] : [];
      }
      return mpNvRefs.current.filter((nv): nv is Niivue => nv !== null);
    };

    // Remove previous bounding box mesh from all instances
    if (bboxMeshUrlRef.current) {
      for (const nv of getNvInstances()) {
        try { nv.removeMeshByUrl(bboxMeshUrlRef.current); } catch { /* already removed */ }
        nv.opts.meshXRay = 0;
        nv.opts.meshThicknessOn2D = Infinity;
        nv.drawScene();
      }
      bboxMeshUrlRef.current = null;
    }

    if (!selectedLesion || !ready) return;

    const nvInstances = getNvInstances();
    if (nvInstances.length === 0 || nvInstances[0].volumes.length === 0) return;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const affine: number[][] | undefined = (nvInstances[0].volumes[0] as any).hdr?.affine;
    if (!affine) return;

    const mz3 = createBoundingBoxMZ3(selectedLesion.bounding_box, affine, 0.3);
    const meshUrl = `bbox-${selectedLesion.id}.mz3`;

    // Set rendering options BEFORE adding mesh so first drawScene uses them
    for (const nv of nvInstances) {
      nv.opts.meshXRay = 0.5;
      nv.opts.meshThicknessOn2D = 500; // large slab to project full bbox outline on 2D slices
    }

    // Add mesh to all NiiVue instances (3D + slice panels), each gets its own buffer copy
    const loadPromises = nvInstances.map(nv =>
      nv.addMeshFromUrl({
        url: meshUrl,
        buffer: mz3.slice(0),
        rgba255: [255, 215, 0, 255],
        opacity: 0.8,
      }).catch(err => console.error('[3D] bbox mesh error:', err))
    );

    Promise.all(loadPromises).then(() => {
      bboxMeshUrlRef.current = meshUrl;
    });

    return () => {
      if (bboxMeshUrlRef.current) {
        for (const nv of getNvInstances()) {
          try { nv.removeMeshByUrl(bboxMeshUrlRef.current); } catch { /* already removed */ }
          nv.opts.meshXRay = 0;
          nv.opts.meshThicknessOn2D = Infinity;
        }
        bboxMeshUrlRef.current = null;
      }
    };
  }, [selectedLesion, render3DMode, volumeReady, mpReady]);

  // ─── EFFECT 10: Reactive zone map visibility/opacity ───
  useEffect(() => {
    const ready = render3DMode === 'volume' ? volumeReady : mpReady;
    if (!ready || !zoneMapBuffer) return;

    const nvInstances = render3DMode === 'volume'
      ? (volumeNvRef.current ? [volumeNvRef.current] : [])
      : mpNvRefs.current.filter((nv): nv is Niivue => nv !== null);

    for (const nv of nvInstances) {
      // Toggle clip-plane masking: overlays clip with MRI only when zone map is visible
      nv.backgroundMasksOverlays = zoneMapVisible ? 1 : 0;

      // Find the zone map volume (uses magnims_zones colormap)
      for (let idx = 1; idx < nv.volumes.length; idx++) {
        if (nv.volumes[idx].colormap !== 'magnims_zones') continue;
        nv.setOpacity(idx, zoneMapVisible ? zoneMapOpacity : 0);
        break;
      }
      nv.drawScene();
    }
  }, [zoneMapVisible, zoneMapOpacity, render3DMode, volumeReady, mpReady, zoneMapBuffer]);

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
          <div className="relative w-full h-full group/vol">
            <canvas
              ref={volumeCanvasRef}
              width={containerSize.width}
              height={containerSize.height}
              style={{ width: '100%', height: '100%', display: 'block' }}
            />
            {volumeReady && (
              <div className="absolute bottom-3 left-3 flex items-center gap-2 px-2 py-1 bg-black/60 rounded-lg opacity-0 group-hover/vol:opacity-100 transition-opacity z-10">
                <Eye className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={panelOpacity[0]}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    const nv = volumeNvRef.current;
                    if (nv && nv.volumes.length > 0) nv.setOpacity(0, val);
                    setPanelOpacity((prev) => { const next = [...prev]; next[0] = val; return next; });
                  }}
                  className="w-20 h-1 accent-blue-500 cursor-pointer"
                  title={`Opacity ${Math.round(panelOpacity[0] * 100)}%`}
                />
                <span className="text-[10px] text-gray-400 w-8 text-right">{Math.round(panelOpacity[0] * 100)}%</span>
              </div>
            )}
          </div>
        )}

        {/* Multiplanar mode: 2x2 grid */}
        {render3DMode === 'multiplanar' && (
          <div className="grid grid-cols-2 grid-rows-2 w-full h-full gap-px bg-gray-800">
            {PANEL_CONFIG.map((panel, i) => (
              <div key={panel.key} className="relative bg-black overflow-hidden group/panel">
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
                {/* Per-panel controls */}
                {mpReady && (
                  <div className="absolute bottom-0 left-0 right-0 flex items-center gap-2 px-2 py-1 bg-black/60 opacity-0 group-hover/panel:opacity-100 transition-opacity z-10">
                    <Eye className="w-3 h-3 text-gray-400 shrink-0" />
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={panelOpacity[i]}
                      onChange={(e) => handlePanelOpacity(i, parseFloat(e.target.value))}
                      className="w-16 h-1 accent-blue-500 cursor-pointer"
                      title={`Opacity ${Math.round(panelOpacity[i] * 100)}%`}
                    />
                    <span className="text-[9px] text-gray-400 w-7 text-right">{Math.round(panelOpacity[i] * 100)}%</span>
                    <div className="ml-auto flex items-center gap-1">
                      <button
                        onClick={() => handlePanelZoom(i, -0.25)}
                        className="p-0.5 text-gray-400 hover:text-white rounded hover:bg-white/10"
                        title="Zoom out"
                      >
                        <ZoomOut className="w-3 h-3" />
                      </button>
                      <span className="text-[9px] text-gray-400 w-8 text-center">{Math.round(panelZoom[i] * 100)}%</span>
                      <button
                        onClick={() => handlePanelZoom(i, 0.25)}
                        className="p-0.5 text-gray-400 hover:text-white rounded hover:bg-white/10"
                        title="Zoom in"
                      >
                        <ZoomIn className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                )}
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
