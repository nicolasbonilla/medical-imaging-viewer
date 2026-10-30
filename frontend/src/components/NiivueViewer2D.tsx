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
 *   - PRB-004 review of PR #71:
 *       M1  the mask is requested aligned to the image shown (`?ref_file_id=`): a mask saved before RC-031
 *           that lies on this image's grid comes back realigned, with the marker, and is drawn;
 *       M2  this view draws the SAVED mask only: a segmentation not saved yet, or unsaved edits, are
 *           announced on screen, never silently missing;
 *       m3  niivue's own keyboard, wheel and double-click controls (view type, clip plane, slice, drag
 *           mode, contrast reset) never act: they bypassed the store, so the view could show another slice
 *           or window than the one the app reports. The wheel steps the store's slice instead;
 *       m5  the notice sits at the bottom, clear of the identity block and the orientation banner;
 *       m6  the mask is drawn in its label colours (MAGNIMS regions: the shared mapping), not all red.
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
import { fetchWithSession } from '@/services/session';
import {
  voxelGridOf, placeAsStandardView, maskMatchesImageGrid, niftiNameFor, LABEL_MASK_DISPLAY_RANGE,
  segmentationNiftiPath, type MaskGridCheck, type VolumeLike,
} from '@/utils/niivueVoxelGrid';
import { maskLabelColormap } from '@/utils/maskLabelColormap';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function fetchBuffer(url: string): Promise<ArrayBuffer> {
  // CAPA-015 RC-069: bearer token + silent refresh / re-login on 401 (never a lost session).
  const res = await fetchWithSession(url);
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
const MASK_NOT_SHOWN_REASON: Record<Exclude<MaskGridCheck, { ok: true }>['reason'] | 'load' | 'unsaved', [string, string]> = {
  grid: ['viewer.gpuMaskNotShownGrid', 'its voxel grid differs from this image'],
  position: ['viewer.gpuMaskNotShownPosition', "it is not placed on this image's voxel grid"],
  order: ['viewer.gpuMaskNotShownOrder', 'it is stored in an older voxel order'],
  load: ['viewer.gpuMaskNotShownLoad', 'it could not be loaded'],
  unsaved: ['viewer.gpuMaskNotShownUnsaved', 'it is not saved yet'],
};
type MaskNotShown = keyof typeof MASK_NOT_SHOWN_REASON;
/** Review m9: the Standard view is offered only where it shows the mask correctly (it draws a mask voxel for
 *  voxel on the image it is shown with, so not for a mask on another grid or another position). */
const STANDARD_VIEW_SHOWS_IT: ReadonlySet<MaskNotShown> = new Set<MaskNotShown>(['order', 'load', 'unsaved']);

const NIIVUE_HOTKEYS_OFF = { viewModeHotKey: '', clipPlaneHotKey: '', cycleClipPlaneHotKey: '' } as const;

export interface NiivueViewer2DProps {
  /** Review M2: the segmentation shown has edits not saved yet (this view draws the saved mask only). */
  hasUnsavedEdits?: boolean;
}

export function NiivueViewer2D({ hasUnsavedEdits = false }: NiivueViewer2DProps = {}) {
  const { t } = useTranslation();
  const rootRef = useRef<HTMLDivElement>(null);
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
  const [maskLoadProblem, setMaskLoadProblem] = useState<Exclude<MaskNotShown, 'unsaved'> | null>(null);

  const segId = currentSegmentation?.segmentation_id;
  const segIsLocal = !!segId && segId.startsWith('local-');
  const overlaySegId = segId && !segIsLocal ? segId : null;
  // Review M2: a segmentation that exists only in this browser is never silently absent here.
  const maskNotShown: MaskNotShown | null = segIsLocal ? 'unsaved' : maskLoadProblem;
  const showEditsNotice = hasUnsavedEdits && !!overlaySegId && maskNotShown === null;
  // Review m6: the label table the mask was saved with (colours by label value).
  const savedLabels = currentSegmentation?.metadata?.labels;
  const labelsRef = useRef(savedLabels);
  labelsRef.current = savedLabels;
  // A changed label table (e.g. after region classification) reloads the mask with its new colours.
  const labelsKey = (savedLabels ?? []).map((l) => `${l.id}${l.color}`).join(',');

  // Load base volume (+ view-only mask overlay) whenever the study OR shown mask changes.
  // The canvas is keyed on the same pair, so each load gets a FRESH canvas+GL context.
  useEffect(() => {
    if (!fileId || !canvasRef.current) return;
    let cancelled = false;
    readyRef.current = false;

    const init = async () => {
      setLoading(true);
      setError(null);
      setMaskLoadProblem(null);
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
          // Review m3: niivue's own view-type / clip-plane keys off (see also the guard below).
          ...NIIVUE_HOTKEYS_OFF,
        });
        await nv.attachToCanvas(canvasRef.current!);
        // Review m3: niivue makes its canvas focusable to take keys (slice Ctrl+U/D, drag mode M,
        // view type V) that bypass the store. Not focusable: keys go to the app's own shortcuts.
        canvasRef.current?.removeAttribute('tabindex');
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
            // Review M1: aligned to this image by the server when it lies on this image's grid.
            const segBuf = await fetchBuffer(`${API_BASE_URL}${segmentationNiftiPath(overlaySegId, fileId)}`);
            if (cancelled) return;
            const segName = niftiNameFor(segBuf, 'mask');
            // Review m6: label colours (regions: the shared mapping); one colour when there is no table.
            const labelCm = maskLabelColormap(labelsRef.current);
            if (labelCm) nv.addColormap(labelCm.name, labelCm.colormap);
            const segVol = await NVImage.loadFromUrl({
              url: segName, name: segName, buffer: segBuf,
              ...(labelCm
                ? { colormap: labelCm.name, cal_min: labelCm.cal_min, cal_max: labelCm.cal_max }
                : { colormap: 'red', ...LABEL_MASK_DISPLAY_RANGE }), // PRB-006: never the MRI window
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
              setMaskLoadProblem(check.reason);
            }
          } catch {
            // The base image still shows; the clinician is told the mask is not drawn here.
            if (!cancelled) setMaskLoadProblem('load');
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
  }, [fileId, overlaySegId, labelsKey]);

  // Review m3: niivue's canvas listeners (keys, wheel, double-click) never run. They changed the slice,
  // the view type, the clip plane, the drag mode or the contrast behind the store's back. Stopped in the
  // capture phase on this wrapper, before they reach the canvas. The wheel steps the store's slice, as
  // the standard view does (Ctrl/Cmd + wheel does nothing here: zoom is not part of this view).
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const onCanvas = (e: Event) => e.target instanceof HTMLCanvasElement;
    const block = (e: Event) => { if (onCanvas(e)) e.stopPropagation(); };
    const wheel = (e: WheelEvent) => {
      if (!onCanvas(e)) return;
      e.stopPropagation();
      e.preventDefault();
      if (e.ctrlKey || e.metaKey || e.deltaY === 0) return;
      const { currentSliceIndex: k, currentSeries, setCurrentSliceIndex } = useViewerStore.getState();
      const last = Math.max(0, (currentSeries?.total_slices ?? 1) - 1);
      setCurrentSliceIndex(Math.max(0, Math.min(last, k + (e.deltaY > 0 ? 1 : -1))));
    };
    const types = ['keydown', 'keyup', 'keypress', 'dblclick'] as const;
    types.forEach((type) => root.addEventListener(type, block, true));
    root.addEventListener('wheel', wheel, { capture: true, passive: false });
    return () => {
      types.forEach((type) => root.removeEventListener(type, block, true));
      root.removeEventListener('wheel', wheel, { capture: true });
    };
  }, []);

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

  // Review m5: bottom centre, above the standing laterality caveat (bottom-2; two lines in a narrow view) —
  // clear of the patient identity block (top left) and the orientation banner (top right) of the safety
  // overlay. Measured in a real browser (NiivueViewer2D.prb004.layout.test.tsx).
  const noticeClass = 'pointer-events-none absolute bottom-14 left-1/2 z-10 max-w-md -translate-x-1/2 rounded border border-amber-600/60 bg-amber-950/85 px-2 py-1 text-[11px] text-amber-100';

  return (
    <div ref={rootRef} className="relative h-full w-full bg-black">
      <canvas key={`${fileId ?? 'x'}:${overlaySegId ?? 'x'}:${labelsKey}`} ref={canvasRef} className="h-full w-full" />
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
        <div data-testid="niivue-mask-not-shown" role="status" className={noticeClass}>
          {t('viewer.gpuMaskNotShown', 'The segmentation is not drawn in this view')}
          {': '}
          {t(...MASK_NOT_SHOWN_REASON[maskNotShown])}
          {'.'}
          {STANDARD_VIEW_SHOWS_IT.has(maskNotShown) && (
            <> {t('viewer.gpuMaskNotShownUseStandard', 'Use the Standard view to see it.')}</>
          )}
        </div>
      )}
      {showEditsNotice && (
        <div data-testid="niivue-mask-not-shown" role="status" className={noticeClass}>
          {t('viewer.gpuMaskUnsavedEdits', 'Unsaved edits are not shown in this view: it draws the last saved segmentation.')}
          {' '}
          {t('viewer.gpuMaskUnsavedEditsUseStandard', 'Use the Standard view to see them.')}
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
