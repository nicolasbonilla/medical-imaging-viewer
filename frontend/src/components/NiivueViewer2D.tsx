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
 *   - The segmentation mask is shown only as a niivue overlay, never edited.
 *   - PRB-004 (HAZ-006): the image and the mask are laid out EXACTLY as the standard view
 *     draws them — storage voxel (i, j) of slice k at row i, column j — not by the scanner
 *     affine (which showed every slice rotated by 90 degrees against the standard view, and a
 *     slider position between two slices). See utils/niivueVoxelGrid.ts. The mask gets the
 *     image's layout, so it is drawn only when it is stored on the image's own voxel grid in
 *     the image's voxel order (RC-031 marker); otherwise it is not drawn and the view says so.
 *   - PRB-005: every volume is handed to niivue as a buffer with an explicit NIfTI name — niivue
 *     cannot derive a file type from a blob URL on a host name without a dot.
 *   - PRB-006: the mask's display range is fixed (0 transparent, labels >= 1 full colour),
 *     never the MRI window its header may have copied.
 *   - Opt-in, never the default.
 *
 * A fresh canvas+instance is mounted per (study, segmentation) via the canvas `key`, so a GL
 * context is never reused/lost.
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Niivue, NVImage, SLICE_TYPE, SHOW_RENDER } from '@niivue/niivue';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { windowLevelToCalRange, sliceIndexToVoxelCentreFraction } from '@/utils/niivueWindowLevel';
import {
  voxelGridOf, placeAsStandardView, maskMatchesImageGrid, niftiNameFor, LABEL_MASK_DISPLAY_RANGE,
  type MaskGridCheck, type VolumeLike,
} from '@/utils/niivueVoxelGrid';

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

/** Store slice index → the same storage slice k the standard view shows (PRB-004). With the
 *  standard-view layout, niivue's axial axis IS the storage k axis, increasing with k, so the
 *  crosshair is set at the centre of voxel slice k: (k + 0.5) / depth. */
function applySlice(nv: Niivue) {
  const vol = nv.volumes?.[0];
  if (!vol) return;
  const depth = vol.dimsRAS?.[3] ?? vol.dims?.[3] ?? 0;
  const frac = sliceIndexToVoxelCentreFraction(useViewerStore.getState().currentSliceIndex, depth);
  if (frac !== null && nv.scene?.crosshairPos) {
    nv.scene.crosshairPos = [0.5, 0.5, frac];
    nv.drawScene?.();
  }
}

/** Why a mask is not drawn in this view (PRB-004), for the on-screen notice. */
const MASK_NOT_SHOWN_REASON: Record<Exclude<MaskGridCheck, { ok: true }>['reason'], [string, string]> = {
  grid: ['viewer.gpuMaskNotShownGrid', 'its voxel grid differs from this image'],
  position: ['viewer.gpuMaskNotShownPosition', "it is not placed on this image's voxel grid"],
  order: ['viewer.gpuMaskNotShownOrder', 'it is stored in an older voxel order'],
};

export function NiivueViewer2D() {
  const { t } = useTranslation();
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
  // PRB-004: a mask that cannot be drawn voxel for voxel on this image is not drawn — and said so.
  const [maskNotShown, setMaskNotShown] = useState<keyof typeof MASK_NOT_SHOWN_REASON | 'load' | null>(null);

  const segId = currentSegmentation?.segmentation_id;
  const segIsLocal = !!segId && segId.startsWith('local-');
  const overlaySegId = segId && !segIsLocal ? segId : null;

  // Load base volume (+ view-only mask overlay) whenever the study OR shown mask changes.
  // The canvas is keyed on the same pair, so each load gets a FRESH canvas+GL context.
  useEffect(() => {
    if (!fileId || !canvasRef.current) return;
    let cancelled = false;
    readyRef.current = false;

    const init = async () => {
      setLoading(true);
      setError(null);
      setMaskNotShown(null);
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
          // PRB-004: the standard-view layout (utils/niivueVoxelGrid) assumes niivue's axial
          // screen is +x right, +y up; the radiological flip would mirror it. Stated, not defaulted.
          isRadiologicalConvention: false,
        });
        await nv.attachToCanvas(canvasRef.current!);
        if (cancelled) { nv.cleanup?.(); return; }
        nvRef.current = nv;

        // PRB-005: the buffer itself, with an explicit NIfTI name — no blob URL whose missing
        // "extension" niivue would try to parse.
        const baseName = niftiNameFor(buffer, 'image');
        const base = await NVImage.loadFromUrl({ url: baseName, name: baseName, buffer, colormap: 'gray', opacity: 1 });
        if (cancelled) return;
        // PRB-004: the image grid as stored, read BEFORE the display transform replaces the affine.
        const imageGrid = voxelGridOf(base as unknown as VolumeLike);
        placeAsStandardView(base as unknown as VolumeLike, imageGrid);
        nv.addVolume(base);

        if (overlaySegId) {
          try {
            const segBuf = await fetchBuffer(`${API_BASE_URL}/api/v1/segmentation/${overlaySegId}/nifti`);
            if (cancelled) return;
            const segName = niftiNameFor(segBuf, 'mask');
            const segVol = await NVImage.loadFromUrl({
              url: segName, name: segName, buffer: segBuf, colormap: 'red',
              ...LABEL_MASK_DISPLAY_RANGE, // PRB-006
              opacity: useSegmentationStore.getState().isOverlayVisible
                ? useSegmentationStore.getState().lesionOpacity : 0,
            });
            if (cancelled) return;
            const seg = segVol as unknown as VolumeLike;
            const check = maskMatchesImageGrid(voxelGridOf(seg), seg.hdr.description, imageGrid);
            if (check.ok) {
              placeAsStandardView(seg, imageGrid); // the IMAGE's layout: voxel for voxel
              nv.addVolume(segVol);
            } else {
              setMaskNotShown(check.reason);
            }
          } catch {
            // The base image still shows; the clinician is told the mask is not drawn here.
            if (!cancelled) setMaskNotShown('load');
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
      {maskNotShown && (
        <div
          data-testid="niivue-mask-not-shown"
          role="status"
          className="pointer-events-none absolute left-1/2 top-12 z-10 max-w-md -translate-x-1/2 rounded border border-amber-600/60 bg-amber-950/85 px-2 py-1 text-[11px] text-amber-100"
        >
          {t('viewer.gpuMaskNotShown', 'The segmentation is not drawn in this view')}
          {': '}
          {maskNotShown === 'load'
            ? t('viewer.gpuMaskNotShownLoad', 'it could not be loaded')
            : t(...MASK_NOT_SHOWN_REASON[maskNotShown])}
          {'. '}
          {t('viewer.gpuMaskNotShownUseStandard', 'Use the Standard view to see it.')}
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
