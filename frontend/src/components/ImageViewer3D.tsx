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
import { AlertCircle, Box, ZoomIn, ZoomOut, Eye } from 'lucide-react';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { createBoundingBoxMZ3 } from '@/utils/boundingBoxMesh';
import { COLORMAPS_3D } from '@/utils/colormaps3d';
import { MAGNIMS_ZONE_RGB } from '@/utils/clinicalPalette';
import { DISPLAY_CONVENTION } from '@/volume/sliceGeometry';
import { maskZYXToVoxel } from '@/volume/maskPlane';
import { voxelToWorld } from '@/volume/nifti';
import { ViewportSafetyOverlay } from './ViewportSafetyOverlay';

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

  // Zone colours from the shared clinical palette (Okabe-Ito) so the 3D layer
  // matches the 2D overlay and every legend. value v -> indices of band v.
  const bands: Array<[number, number, number]> = [[32, 96, 1], [96, 160, 2], [160, 224, 3], [224, 256, 4]];
  for (const [from, to, zone] of bands) {
    const [r, g, b] = MAGNIMS_ZONE_RGB[zone];
    for (let i = from; i < to; i++) { R[i] = r; G[i] = g; B[i] = b; A[i] = 255; }
  }

  nv.addColormap('magnims_zones', { R, G, B, A, I });
}

/** Create a NiiVue instance for a specific slice type */
function createNvInstance(sliceType: number): Niivue {
  const nv = new Niivue({
    backColor: [0, 0, 0, 1],
    show3Dcrosshair: sliceType === SLICE_TYPE.RENDER,
    // Same display convention as the 2D in-browser viewer (volume/sliceGeometry).
    isRadiologicalConvention: DISPLAY_CONVENTION === 'radiological',
    sliceType,
    multiplanarShowRender: SHOW_RENDER.NEVER,
    isColorbar: sliceType === SLICE_TYPE.RENDER,
    // RC-023 / CAPA-004 CA-4.3 open: no L/R/A/P glyphs (orientation cube or edge text)
    // while laterality labelling is unverified — same stance as ViewportSafetyOverlay
    // and NiivueViewer2D. The orientation is reported, as text, by the safety overlay.
    isOrientCube: false,
    isOrientationTextVisible: false,
    crosshairWidth: 1,
    crosshairColor: [1, 0, 0, 1],
    textHeight: 0.03,
    clipPlaneColor: [1, 1, 1, 0.5],
    loadingText: '',
  });
  return nv;
}

interface ImageViewer3DProps {
  /** RC-016: patient identity annotated on the 3D viewport too. */
  patientName?: string;
  patientMRN?: string;
  studyDescription?: string;
}

export default function ImageViewer3D({ patientName, patientMRN, studyDescription }: ImageViewer3DProps = {}) {
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
  // v3: the 3-D cursor shared with the in-browser 2D viewer (null on the server path).
  const cursorVoxel = useViewerStore((s) => s.cursorVoxel);

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
        await nv.loadVolumes([{ url: mainUrl, name: 'volume.nii', colormap: colormap3D, opacity: 1 }]);
        nv.setRenderAzimuthElevation(0, 15);

        // Load segmentation overlay if available
        if (segBuffer) {
          const segUrl = URL.createObjectURL(new Blob([segBuffer]));
          blobUrls.push(segUrl);
          const segVol = await NVImage.loadFromUrl({ url: segUrl, name: 'overlay.nii', colormap: 'red', opacity: 0.5 });
          nv.addVolume(segVol);
        }

        // Load zone map overlay if buffer available
        if (zoneMapBuffer) {
          registerZoneMapColormap(nv);
          const zmUrl = URL.createObjectURL(new Blob([zoneMapBuffer]));
          blobUrls.push(zmUrl);
          const zmVol = await NVImage.loadFromUrl({
            url: zmUrl,
            name: 'overlay.nii',
            colormap: 'magnims_zones',
            cal_min: 0,
            cal_max: 4,
            opacity: zoneMapVisible ? zoneMapOpacity : 0,
          });
          nv.addVolume(zmVol);
        }

        // Load longitudinal TP1 overlay (blue). NOTE: niivue composites by each volume's
        // own affine — there is NO spatial registration between TP1 and TP2, so overlap is
        // NOT verified alignment (Class C: treat any apparent change as a candidate).
        if (longTp1Buffer && longitudinalVisible) {
          const tp1Url = URL.createObjectURL(new Blob([longTp1Buffer]));
          blobUrls.push(tp1Url);
          const tp1Vol = await NVImage.loadFromUrl({ url: tp1Url, name: 'overlay.nii', colormap: 'blue', opacity: 0.5 });
          nv.addVolume(tp1Vol);
        }

        // Load longitudinal TP2 overlay (hot). NO TP2->TP1 registration is performed (the
        // load URL passes no ref_file_id); niivue only affine-composites. Change is a candidate.
        if (longTp2Buffer && longitudinalVisible) {
          const tp2Url = URL.createObjectURL(new Blob([longTp2Buffer]));
          blobUrls.push(tp2Url);
          const tp2Vol = await NVImage.loadFromUrl({ url: tp2Url, name: 'overlay.nii', colormap: 'hot', opacity: 0.5 });
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
          await nvInstances[i].loadVolumes([{ url, name: 'volume.nii', colormap: colormap3D, opacity: 1 }]);

          // Load segmentation overlay
          if (segBuffer) {
            const segUrl = URL.createObjectURL(new Blob([segBuffer]));
            blobUrls.push(segUrl);
            const segVol = await NVImage.loadFromUrl({
              url: segUrl,
              name: 'overlay.nii',
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
              name: 'overlay.nii',
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
            const tp1Vol = await NVImage.loadFromUrl({ url: tp1Url, name: 'overlay.nii', colormap: 'blue', opacity: i === 0 ? 0.5 : 0.3 });
            nvInstances[i].addVolume(tp1Vol);
          }

          // Load longitudinal TP2 overlay (red) — backend aligns via ref_file_id
          if (longTp2Buffer && longitudinalVisible) {
            const tp2Url = URL.createObjectURL(new Blob([longTp2Buffer]));
            blobUrls.push(tp2Url);
            const tp2Vol = await NVImage.loadFromUrl({ url: tp2Url, name: 'overlay.nii', colormap: 'hot', opacity: i === 0 ? 0.5 : 0.3 });
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

    // Lesion analysis reports (z, y, x) on the internal (k, a0, a1) mask, i.e.
    // voxel (i, j, k) = (y, x, z). Using (x, y, z) here drew the 3D crosshair
    // transposed in-plane (wrong location on any non-square slice).
    const [vx, vy, vz] = maskZYXToVoxel(
      { layout: 'kij', dims: [0, 0, 0] },
      selectedLesion.centroid.z, selectedLesion.centroid.y, selectedLesion.centroid.x,
    );
    const vol = nv.volumes[0];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const va = vol as any;
    const dims = vol.dims;
    const affine: number[][] | undefined = va.hdr?.affine;

    // Convert file voxel coords → mm via affine, then mm → frac via NiiVue
    let frac: [number, number, number];
    if (affine) {
      const mm: [number, number, number] = [
        affine[0][0] * vx + affine[0][1] * vy + affine[0][2] * vz + affine[0][3],
        affine[1][0] * vx + affine[1][1] * vy + affine[1][2] * vz + affine[1][3],
        affine[2][0] * vx + affine[2][1] * vy + affine[2][2] * vz + affine[2][3],
      ];
      frac = nv.mm2frac(mm, 0) as [number, number, number];
    } else if (dims && dims.length >= 4) {
      frac = [
        vx / Math.max(1, dims[1] - 1),
        vy / Math.max(1, dims[2] - 1),
        vz / Math.max(1, dims[3] - 1),
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

    // v3: with the in-browser 2D viewer the full 3-D cursor (i, j, k) is known — place
    // the crosshair at exactly that voxel through the affine, for every plane.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const affine: number[][] | undefined = (nv.volumes[0] as any).hdr?.affine;
    if (cursorVoxel && affine) {
      const frac = nv.mm2frac(voxelToWorld(affine, ...cursorVoxel), 0) as [number, number, number];
      const place = (nvInst: Niivue | null) => {
        if (!nvInst || nvInst.volumes.length === 0) return;
        nvInst.scene.crosshairPos = [...frac] as [number, number, number];
        nvInst.drawScene();
      };
      if (render3DMode === 'volume') place(nv); else mpNvRefs.current.forEach(place);
      return;
    }

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
  }, [currentSliceIndex, cursorVoxel, selectedLesion, render3DMode, volumeReady, mpReady]);

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
      <div className="flex h-full items-center justify-center bg-black">
        <div className="text-center text-ink-muted">
          <Box className="mx-auto mb-4 h-14 w-14 opacity-40" aria-hidden />
          <p className="text-sm">{t('viewer.selectImageFor3D', 'Select an image for 3D viewing')}</p>
        </div>
      </div>
    );
  }

  if (!fileId) {
    return (
      <div className="flex h-full items-center justify-center bg-black">
        <div className="text-center text-ink-muted">
          <AlertCircle className="mx-auto mb-4 h-14 w-14 opacity-40" aria-hidden />
          <p className="text-sm">{t('viewer.noFileId', 'No file available for 3D rendering')}</p>
        </div>
      </div>
    );
  }

  const isReady = render3DMode === 'volume' ? volumeReady : mpReady;

  return (
    <div className="relative h-full bg-black">
      {/* RC-016 + RC-023: identity and orientation state on the 3D viewport too —
          rendered first and unconditionally, above every canvas. */}
      <ViewportSafetyOverlay
        patientName={patientName}
        patientMRN={patientMRN}
        studyDescription={studyDescription}
        anatomicalOrientation={currentSeries?.metadata?.anatomical_orientation}
      />
      {/* Class C: the TP1/TP2 overlays are composited by niivue's per-volume affine with
          NO spatial registration — apparent overlap/change is a candidate, not a finding. */}
      {longitudinalVisible && (longTp1Buffer || longTp2Buffer) && (
        <div className="pointer-events-none absolute left-1/2 top-12 z-30 -translate-x-1/2 rounded-lg border border-clinical-warn/40 bg-surface-void/85 px-3 py-1 text-xs text-clinical-warn">
          {t('longitudinal.overlayCaveat', 'TP1/TP2 overlay — NOT spatially registered; apparent change is a candidate.')}
        </div>
      )}
      <div ref={containerRef} className="absolute inset-0">
        {/* Volume mode: single canvas */}
        {render3DMode === 'volume' && (
          <div className="group/vol relative h-full w-full">
            <canvas
              ref={volumeCanvasRef}
              width={containerSize.width}
              height={containerSize.height}
              style={{ width: '100%', height: '100%', display: 'block' }}
            />
            {volumeReady && (
              <div className="absolute bottom-10 right-3 z-10 flex items-center gap-2 rounded-lg border border-surface-border bg-surface-void/80 px-2.5 py-1.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover/vol:opacity-100">
                <Eye className="h-3.5 w-3.5 shrink-0 text-ink-muted" aria-hidden />
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
                  className="h-1 w-24 cursor-pointer accent-brand-500"
                  aria-label={t('viewer3.volumeOpacity', 'Volume opacity')}
                  title={`Opacity ${Math.round(panelOpacity[0] * 100)}%`}
                />
                <span className="w-9 text-right text-xs tabular-nums text-ink-soft">{Math.round(panelOpacity[0] * 100)}%</span>
              </div>
            )}
          </div>
        )}

        {/* Multiplanar mode: 2x2 grid */}
        {render3DMode === 'multiplanar' && (
          <div className="grid h-full w-full grid-cols-2 grid-rows-2 gap-px bg-surface-border">
            {PANEL_CONFIG.map((panel, i) => (
              <div key={panel.key} className="group/panel relative overflow-hidden bg-black">
                <canvas
                  ref={setMpCanvasRef(i)}
                  width={Math.floor(containerSize.width / 2)}
                  height={Math.floor(containerSize.height / 2)}
                  style={{ width: '100%', height: '100%', display: 'block' }}
                />
                {/* Panel label — bottom-left, clear of the identity / orientation corners */}
                <div className="pointer-events-none absolute bottom-2 left-2 rounded bg-black/60 px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-ink-soft">
                  {panel.label}
                </div>
                {/* Per-panel controls */}
                {mpReady && (
                  <div className="absolute bottom-2 right-2 z-10 flex items-center gap-2 rounded-lg border border-surface-border bg-surface-void/80 px-2 py-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover/panel:opacity-100">
                    <Eye className="h-3.5 w-3.5 shrink-0 text-ink-muted" aria-hidden />
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={panelOpacity[i]}
                      onChange={(e) => handlePanelOpacity(i, parseFloat(e.target.value))}
                      className="h-1 w-16 cursor-pointer accent-brand-500"
                      aria-label={`${panel.label} — ${t('viewer3.volumeOpacity', 'Volume opacity')}`}
                      title={`Opacity ${Math.round(panelOpacity[i] * 100)}%`}
                    />
                    <span className="w-9 text-right text-xs tabular-nums text-ink-soft">{Math.round(panelOpacity[i] * 100)}%</span>
                    <button
                      type="button"
                      onClick={() => handlePanelZoom(i, -0.25)}
                      className="rounded p-0.5 text-ink-muted hover:bg-surface-hover hover:text-ink-base focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
                      title={t('viewer.zoomOut', 'Zoom out')}
                      aria-label={`${panel.label} — ${t('viewer.zoomOut', 'Zoom out')}`}
                    >
                      <ZoomOut className="h-3.5 w-3.5" aria-hidden />
                    </button>
                    <span className="w-10 text-center text-xs tabular-nums text-ink-soft">{Math.round(panelZoom[i] * 100)}%</span>
                    <button
                      type="button"
                      onClick={() => handlePanelZoom(i, 0.25)}
                      className="rounded p-0.5 text-ink-muted hover:bg-surface-hover hover:text-ink-base focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
                      title={t('viewer.zoomIn', 'Zoom in')}
                      aria-label={`${panel.label} — ${t('viewer.zoomIn', 'Zoom in')}`}
                    >
                      <ZoomIn className="h-3.5 w-3.5" aria-hidden />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/80" role="status" aria-live="polite">
          <div className="flex w-72 flex-col items-center gap-3">
            <p className="text-sm font-medium text-ink-base">
              {t('viewer.loading3D', 'Loading 3D volume...')}
            </p>
            <div className="w-full">
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-hover">
                {loadProgress >= 0 ? (
                  <div className="h-full rounded-full bg-brand-500 transition-all duration-200" style={{ width: `${loadProgress}%` }} />
                ) : (
                  <div className="h-full w-full animate-pulse rounded-full bg-brand-500 opacity-40" />
                )}
              </div>
              <div className="mt-1.5 flex justify-between text-xs tabular-nums text-ink-muted">
                <span>{loadProgress >= 0 ? `${loadProgress}%` : t('viewer.downloading', 'Downloading...')}</span>
                {totalMB > 0 && <span>{loadedMB.toFixed(1)} / {totalMB.toFixed(1)} MB</span>}
              </div>
            </div>
            <p className="text-center text-xs text-ink-faint">
              {loadProgress === 100
                ? t('viewer.rendering3D', 'Initializing WebGL renderer...')
                : t('viewer.loading3DDesc', 'Downloading NIfTI file for WebGL rendering')}
            </p>
          </div>
        </div>
      )}

      {/* Error overlay */}
      {error && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/80" role="alert">
          <div className="max-w-sm p-6 text-center">
            <AlertCircle className="mx-auto mb-3 h-10 w-10 text-clinical-crit" aria-hidden />
            <p className="font-medium text-clinical-crit">{t('viewer.error3D', '3D rendering failed')}</p>
            <p className="mt-2 break-words text-sm text-ink-muted">{error}</p>
          </div>
        </div>
      )}

      {/* Instructions (volume mode only) */}
      {isReady && !isLoading && render3DMode === 'volume' && (
        <div className="pointer-events-none absolute bottom-10 left-3 z-10 space-y-0.5 rounded-lg border border-surface-border bg-surface-void/70 px-3 py-2 text-xs text-ink-muted">
          <div>{t('viewer.3d.dragRotate', 'Left-click drag: Rotate')}</div>
          <div>{t('viewer.3d.scrollZoom', 'Scroll: Zoom')}</div>
          <div>{t('viewer.3d.rightPan', 'Right-click drag: Pan')}</div>
        </div>
      )}
    </div>
  );
}

// Re-exported for existing importers; the list lives in utils/colormaps3d.
export { COLORMAPS_3D };
