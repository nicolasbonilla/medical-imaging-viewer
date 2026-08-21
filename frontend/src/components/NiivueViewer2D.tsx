/**
 * NiivueViewer2D — VIEW-ONLY GPU window/level axial viewer (renderMode 'niivue').
 *
 * WHY THIS EXISTS (the disqualifying viewer invariant): window/level must repaint at
 * monitor refresh with ZERO re-fetch/re-decode. The 'standard' and 'matplotlib' base
 * layers are pre-baked 8-bit images (the backend already threw away the source
 * intensity range), so client-side W/L on them is only a CSS brightness/contrast hack,
 * not a true VOI-LUT. This mode loads the RAW NIfTI into niivue and W/L becomes a GPU
 * cal_min/cal_max shader update — instant, medical-grade.
 *
 * SAFETY — Class C (adversarial review, workflow wf_6522c0de-762 + niivue-API review):
 *   - STRICTLY VIEW-ONLY. Painting is NEVER routed through niivue coordinates. A
 *     misregistered base under a paint overlay would be a wrong-location lesion hazard
 *     ("a rater paints what they see"); we eliminate it by not painting here. To edit a
 *     mask the user switches back to 'standard'/'matplotlib'. dragMode is pan, not a
 *     drawing/windowing mode — the store is the single source of truth for W/L.
 *   - The segmentation mask is shown only as a niivue overlay (affine-aligned by
 *     niivue), never edited.
 *   - Opt-in, never the default, until browser visual-QA confirms slice/orientation
 *     parity with the standard viewer.
 *
 * Reuses the exact niivue lifecycle proven in ImageViewer3D (attach → loadVolumes →
 * cal_min/max → cleanup + revoke blob URLs). A fresh canvas+instance is mounted per
 * (study, segmentation) via the canvas `key`, so a GL context is never reused/lost.
 */
import { useEffect, useRef, useState } from 'react';
import { Niivue, NVImage, SLICE_TYPE, SHOW_RENDER } from '@niivue/niivue';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { windowLevelToCalRange, sliceIndexToFraction } from '@/utils/niivueWindowLevel';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchBuffer(url: string): Promise<ArrayBuffer> {
  const res = await fetch(url, { headers: getAuthHeaders() });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 160) || res.statusText}`);
  }
  return res.arrayBuffer();
}

/** Latest store W/L (read fresh, not from an effect-creation closure, so a change made
 *  during the async load is never dropped). C/W → cal_min/cal_max, instant on the GPU. */
function applyWindowLevel(nv: Niivue) {
  const vol = nv.volumes?.[0];
  if (!vol) return;
  const { windowCenter, windowWidth } = useViewerStore.getState();
  const { calMin, calMax } = windowLevelToCalRange(
    windowCenter, windowWidth, vol.global_min, vol.global_max, vol.cal_min ?? 0, vol.cal_max ?? 1);
  vol.cal_min = calMin;
  vol.cal_max = calMax;
  nv.updateGLVolume();
}

/** Store slice index → niivue axial depth fraction (best-effort; orientation/flip is a
 *  browser-QA item before this mode can become the default). */
function applySlice(nv: Niivue) {
  const vol = nv.volumes?.[0];
  if (!vol) return;
  // crosshairPos[2] addresses niivue's RAS SUPERIOR (axial) axis, whose length is
  // dimsRAS[3] — NOT the raw storage k-axis dims[3] (they coincide only for an axial-RAS
  // volume). Use dimsRAS so a permuted affine still scans the right anatomical axis.
  // (Flip direction — index 0 = inferior vs superior — remains a browser-QA item.)
  const depth = vol.dimsRAS?.[3] ?? vol.dims?.[3] ?? 0;
  const frac = sliceIndexToFraction(useViewerStore.getState().currentSliceIndex, depth);
  if (frac !== null && nv.scene?.crosshairPos) {
    nv.scene.crosshairPos = [0.5, 0.5, frac];
    nv.drawScene?.();
  }
}

export function NiivueViewer2D() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nvRef = useRef<Niivue | null>(null);
  const readyRef = useRef(false);

  const fileId = useViewerStore((s) => s.currentSeries?.file_id);
  const currentSliceIndex = useViewerStore((s) => s.currentSliceIndex);
  const windowCenter = useViewerStore((s) => s.windowCenter);
  const windowWidth = useViewerStore((s) => s.windowWidth);

  const currentSegmentation = useSegmentationStore((s) => s.currentSegmentation);
  const isOverlayVisible = useSegmentationStore((s) => s.isOverlayVisible);
  const lesionOpacity = useSegmentationStore((s) => s.lesionOpacity);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const segId = currentSegmentation?.segmentation_id;
  const segIsLocal = !!segId && segId.startsWith('local-');
  const overlaySegId = segId && !segIsLocal ? segId : null;

  // Load base volume (+ view-only mask overlay) whenever the study OR shown mask changes.
  // The canvas is keyed on the same pair, so each load gets a FRESH canvas+GL context.
  useEffect(() => {
    if (!fileId || !canvasRef.current) return;
    let cancelled = false;
    readyRef.current = false;
    const blobUrls: string[] = [];

    const init = async () => {
      setLoading(true);
      setError(null);
      try {
        const buffer = await fetchBuffer(`${API_BASE_URL}/api/v1/imaging/nifti/${fileId}`);
        if (cancelled) return;

        const nv = new Niivue({
          backColor: [0, 0, 0, 1],
          sliceType: SLICE_TYPE.AXIAL,
          multiplanarShowRender: SHOW_RENDER.NEVER,
          isColorbar: false,
          isOrientCube: false,
          // Class C (RC-023/CAPA-004): the app DELIBERATELY refuses to label laterality
          // (ViewportSafetyOverlay shows "Laterality not labelled — confirm side against the
          // source study"). niivue's orientation text defaults ON and would draw its own L/R
          // from the affine — contradicting that banner. Turn it OFF.
          isOrientationTextVisible: false,
          crosshairWidth: 0,
          loadingText: '',
          dragMode: 3, // DRAG_MODE.pan (NOT 1=contrast) — the store drives W/L, no drag-windowing
        });
        await nv.attachToCanvas(canvasRef.current!);
        if (cancelled) { nv.cleanup?.(); return; }
        nvRef.current = nv;

        const mainUrl = URL.createObjectURL(new Blob([buffer]));
        blobUrls.push(mainUrl);
        await nv.loadVolumes([{ url: mainUrl, colormap: 'gray', opacity: 1 }]);
        if (cancelled) return;

        if (overlaySegId) {
          try {
            const segBuf = await fetchBuffer(`${API_BASE_URL}/api/v1/segmentation/${overlaySegId}/nifti`);
            if (cancelled) return;
            const blob = URL.createObjectURL(new Blob([segBuf]));
            blobUrls.push(blob);
            const segVol = await NVImage.loadFromUrl({
              url: blob, colormap: 'red',
              opacity: useSegmentationStore.getState().isOverlayVisible
                ? useSegmentationStore.getState().lesionOpacity : 0,
            });
            if (cancelled) return;
            nv.addVolume(segVol);
          } catch {
            /* overlay is best-effort; the base image still shows */
          }
        }

        readyRef.current = true;
        applyWindowLevel(nv);
        applySlice(nv);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'No se pudo cargar el volumen');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    init();
    return () => {
      cancelled = true;
      readyRef.current = false;
      // Formal niivue teardown (removes listeners/observers/RAF). Do NOT loseContext —
      // that would strand the canvas with a dead GL context. The keyed canvas is
      // unmounted by React, so its context is released with the node.
      nvRef.current?.cleanup?.();
      nvRef.current = null;
      blobUrls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [fileId, overlaySegId]);

  // GPU window/level (the invariant): re-apply on any C/W change.
  useEffect(() => {
    const nv = nvRef.current;
    if (nv && readyRef.current) applyWindowLevel(nv);
  }, [windowCenter, windowWidth]);

  // Slice sync: store index → niivue axial depth.
  useEffect(() => {
    const nv = nvRef.current;
    if (nv && readyRef.current) applySlice(nv);
  }, [currentSliceIndex]);

  // View-only mask overlay visibility / opacity.
  useEffect(() => {
    const nv = nvRef.current;
    if (!nv || nv.volumes.length < 2) return;
    nv.setOpacity(1, isOverlayVisible ? lesionOpacity : 0);
  }, [isOverlayVisible, lesionOpacity]);

  return (
    <div className="relative h-full w-full bg-black">
      <canvas key={`${fileId ?? 'x'}:${overlaySegId ?? 'x'}`} ref={canvasRef} className="h-full w-full" />
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-gray-300">
          Cargando volumen…
        </div>
      )}
      {error && (
        <div className="absolute inset-x-0 bottom-0 bg-red-900/70 px-2 py-1 text-[11px] text-red-100">
          {error}
        </div>
      )}
      {/* Honest, non-dismissible mode note (bottom-left, clear of the z-20 patient-identity
          safety overlay): this is a fast-W/L viewing mode, not an editor. */}
      <div className="pointer-events-none absolute bottom-2 left-2 rounded bg-black/50 px-1.5 py-0.5 text-[10px] text-gray-300">
        W/L GPU · solo visualización (para pintar, usa el modo estándar)
      </div>
    </div>
  );
}
