/**
 * ClientSliceViewport — v3 2D viewer that renders slices IN THE BROWSER from the
 * NIfTI the 3D view already downloads (no per-slice PNG round-trip, full bit depth
 * window/level, instant scrolling, axial / coronal / sagittal).
 *
 * Class C design (see docs/research/viewer-v3/PARITY.md):
 *  - Image, segmentation, zone map, conformal tiers, longitudinal overlays, lesion
 *    box, AI points, brush footprint, painting and the cursor read-out ALL go through
 *    one SliceView (volume/sliceGeometry) and one ViewportTransform
 *    (volume/viewportTransform). They cannot drift apart; tests prove it on
 *    asymmetric data in every plane.
 *  - Fail closed: if the browser's reading of the file disagrees with the server's
 *    metadata (grid / spacing) the viewer hands over to the server PNG path
 *    (`onFallback`). An overlay whose grid does not match is hidden with a notice,
 *    never stretched. Anatomical plane names / reorientation only when the
 *    orientation is determinate AND agrees with the server (else voxel order).
 *  - Laterality is never labelled here (RC-023); patient identity and orientation
 *    state are drawn by ViewportSafetyOverlay above this component (RC-016).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, EyeOff } from 'lucide-react';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { useClientVolume } from '@/hooks/useClientVolume';
import type { UseSegmentationMaskReturn } from '@/hooks/useSegmentationMask';
import type { ClickPoint3D } from '@/types';
import { checkClientVolume, viewsFor, type ClientVolume } from '@/volume/clientVolume';
import { clampSlice, displayOf, voxelOf, type PlaneName, type SliceView } from '@/volume/sliceGeometry';
import {
  autoWindow, renderSliceRGBA, sliceHistogram, windowBounds, type WindowLevel,
} from '@/volume/windowing';
import { valueAt, voxelToWorld } from '@/volume/nifti';
import {
  brushOffsets, gatherPlane, maskIndex, maskZYXToVoxel, resolveMaskGrid, type BrushShape, type MaskGrid,
} from '@/volume/maskPlane';
import {
  computeTransform, imageToScreen, linePixels, screenToImage, screenToPixel, zoomAroundPoint,
  type ViewportTransform,
} from '@/volume/viewportTransform';
import {
  conformalColorTable, labelColorTable, longitudinalRGBA, paintTable, subtractionRGBA,
  zoneColorTable, zoneColorizedPlane,
} from '@/volume/overlayPaint';
import MeasurementOverlay from '../MeasurementOverlay';
import { Skeleton } from '../ui';

export interface ClientViewportStatus {
  volume: ClientVolume | null;
  anatomical: boolean;
  views: Record<PlaneName, SliceView> | null;
  notes: string[];
}

interface ClientSliceViewportProps {
  segmentationMask: UseSegmentationMaskReturn;
  /** Segmentation overlay/edit context is active (sidebar "segmentation mode"). */
  segmentationMode: boolean;
  aiClickPoints?: ClickPoint3D[];
  aiInteractiveMode?: boolean;
  onAIClick?: (x: number, y: number, isPositive: boolean) => void;
  /** Called once when the browser must not render this image (server PNG fallback). */
  onFallback: (reason: string) => void;
  /** Volume / views published for sibling UI (toolbar, side panels). */
  onStatus?: (status: ClientViewportStatus) => void;
}

type Drag =
  | { kind: 'pan'; x0: number; y0: number; panX: number; panY: number }
  | { kind: 'wl'; x0: number; y0: number; wl: WindowLevel; perPx: number }
  | { kind: 'paint'; last: { r: number; c: number } }
  | null;

function putPlane(canvas: HTMLCanvasElement, rgba: Uint8ClampedArray, cols: number, rows: number): HTMLCanvasElement {
  if (canvas.width !== cols || canvas.height !== rows) { canvas.width = cols; canvas.height = rows; }
  const ctx = canvas.getContext('2d');
  if (ctx) ctx.putImageData(new ImageData(rgba as Uint8ClampedArray<ArrayBuffer>, cols, rows), 0, 0);
  return canvas;
}

export function ClientSliceViewport({
  segmentationMask, segmentationMode, aiClickPoints, aiInteractiveMode, onAIClick, onFallback, onStatus,
}: ClientSliceViewportProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const baseRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const sliceCanvas = useRef<HTMLCanvasElement | null>(null);
  const layerCanvas = useRef<HTMLCanvasElement | null>(null);
  const dragRef = useRef<Drag>(null);
  const fellBackRef = useRef(false);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [hover, setHover] = useState<{ r: number; c: number } | null>(null);

  // ---- store state ------------------------------------------------------------
  const currentSeries = useViewerStore((s) => s.currentSeries);
  const fileId = currentSeries?.file_id;
  const slicePlane = useViewerStore((s) => s.slicePlane);
  const cursorVoxel = useViewerStore((s) => s.cursorVoxel);
  const orientationMode = useViewerStore((s) => s.orientationMode);
  const smoothDisplay = useViewerStore((s) => s.smoothDisplay);
  const zoomLevel = useViewerStore((s) => s.zoomLevel);
  const panOffset = useViewerStore((s) => s.panOffset);
  const windowCenter = useViewerStore((s) => s.windowCenter);
  const windowWidth = useViewerStore((s) => s.windowWidth);
  const measurementTool = useViewerStore((s) => s.measurementTool);
  const focusRequest = useViewerStore((s) => s.focusRequest);

  const currentSegmentation = useSegmentationStore((s) => s.currentSegmentation);
  const isOverlayVisible = useSegmentationStore((s) => s.isOverlayVisible);
  const lesionOpacity = useSegmentationStore((s) => s.lesionOpacity);
  const labels = useSegmentationStore((s) => s.activeSegmentation?.labels);
  const labelVisibility = useSegmentationStore((s) => s.labelVisibility);
  const isPaintMode = useSegmentationStore((s) => s.isPaintMode);
  const paintTool = useSegmentationStore((s) => s.paintTool);
  const activeLabel = useSegmentationStore((s) => s.activeLabel);
  const drawOverMode = useSegmentationStore((s) => s.drawOverMode);
  const selectedLesion = useSegmentationStore((s) => s.selectedLesion);
  const zoneMapMask = useSegmentationStore((s) => s.zoneMapMask);
  const zoneMapDims = useSegmentationStore((s) => s.zoneMapDims);
  const zoneMapVisible = useSegmentationStore((s) => s.zoneMapVisible);
  const zoneMapOpacity = useSegmentationStore((s) => s.zoneMapOpacity);
  const zoneColorizeEnabled = useSegmentationStore((s) => s.zoneColorizeEnabled);
  const conformalStatusMask = useSegmentationStore((s) => s.conformalStatusMask);
  const conformalDims = useSegmentationStore((s) => s.conformalDims);
  const conformalVisible = useSegmentationStore((s) => s.conformalVisible);
  const longTp1Mask = useSegmentationStore((s) => s.longitudinalTp1Mask);
  const longTp1Dims = useSegmentationStore((s) => s.longitudinalTp1Dims);
  const longTp2Mask = useSegmentationStore((s) => s.longitudinalTp2Mask);
  const longTp2Dims = useSegmentationStore((s) => s.longitudinalTp2Dims);
  const longVisible = useSegmentationStore((s) => s.longitudinalVisible);
  const longSubVol = useSegmentationStore((s) => s.longitudinalSubtractionVolume);
  const longSubDims = useSegmentationStore((s) => s.longitudinalSubtractionDims);
  const longSubVisible = useSegmentationStore((s) => s.longitudinalSubtractionVisible);

  // ---- volume + safety checks -------------------------------------------------
  const volState = useClientVolume(fileId, true);
  const volume = volState.status === 'ready' ? volState.volume : null;
  const check = useMemo(
    () => (volume ? checkClientVolume(volume, currentSeries?.metadata) : null),
    [volume, currentSeries?.metadata],
  );

  useEffect(() => {
    if (fellBackRef.current) return;
    if (volState.status === 'error') {
      fellBackRef.current = true;
      onFallback(volState.error);
    } else if (check && !check.renderable) {
      fellBackRef.current = true;
      onFallback(check.problems.join('; '));
    }
  }, [volState, check, onFallback]);
  useEffect(() => { fellBackRef.current = false; }, [fileId]);

  const anatomical = !!check?.anatomical && orientationMode === 'anatomical';
  const views = useMemo(() => (volume && check?.renderable ? viewsFor(volume, anatomical) : null), [volume, check, anatomical]);
  const view = views?.[slicePlane] ?? null;

  useEffect(() => {
    onStatus?.({ volume, anatomical, views, notes: check?.notes ?? [] });
  }, [volume, anatomical, views, check, onStatus]);

  // New image: start at the centre of the volume with the automatic window.
  useEffect(() => {
    if (!volume) return;
    const st = useViewerStore.getState();
    if (!st.cursorVoxel) {
      const [n0, n1, n2] = volume.nifti.dims;
      st.setCursorVoxel([Math.floor(n0 / 2), Math.floor(n1 / 2), Math.floor(n2 / 2)]);
    }
    st.setWindowLevel(0, 0);
  }, [volume]);

  // Publish the active view geometry (slider range, wheel, keyboard). A hover pixel of
  // the previous view means nothing in the new one — drop it (no stale brush outline).
  useEffect(() => {
    if (view) useViewerStore.getState().setActiveSliceGeometry(view.normal, view.depth);
    setHover(null);
    useViewerStore.getState().setCursorInfo(null);
  }, [view]);

  const slice = view && cursorVoxel ? clampSlice(view, cursorVoxel[view.normal]) : 0;
  const wl: WindowLevel | null = volume
    ? (windowWidth > 0 ? { center: windowCenter, width: windowWidth } : autoWindow(volume.stats))
    : null;

  // ---- masks on this grid -------------------------------------------------------
  const maskDims = segmentationMask.state.dimensions;
  const lesionGrid: MaskGrid | null = useMemo(
    () => (volume ? resolveMaskGrid(maskDims, volume.nifti.dims) : null),
    [volume, maskDims],
  );
  const maskLoaded = segmentationMask.isLoaded && !!segmentationMask.getMaskArray();
  const lesionOffGrid = segmentationMode && !!currentSegmentation && maskLoaded && !!volume && !lesionGrid;
  const canPaint = segmentationMode && isPaintMode && !!currentSegmentation && !!lesionGrid && maskLoaded;

  // Lesion focus (dashboard row click / navigation request) — all three coordinates.
  useEffect(() => {
    if (!selectedLesion || !lesionGrid) return;
    const { x, y, z } = selectedLesion.centroid;
    useViewerStore.getState().setCursorVoxel(maskZYXToVoxel(lesionGrid, Math.round(z), Math.round(y), Math.round(x)));
  }, [selectedLesion, lesionGrid]);
  useEffect(() => {
    if (!focusRequest || !volume) return;
    const st = useViewerStore.getState();
    const cur = st.cursorVoxel ?? [0, 0, 0];
    const grid = lesionGrid ?? { layout: 'kij' as const, dims: volume.nifti.dims };
    const [i, j, k] = maskZYXToVoxel(grid, focusRequest.z, focusRequest.y ?? -1, focusRequest.x ?? -1);
    st.setCursorVoxel([focusRequest.y != null ? i : cur[0], focusRequest.x != null ? j : cur[1], k]);
  }, [focusRequest]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- size --------------------------------------------------------------------
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const transform: ViewportTransform | null = useMemo(
    () => (view && size.w > 0 && size.h > 0 ? computeTransform(size.w, size.h, view, zoomLevel, panOffset) : null),
    [view, size, zoomLevel, panOffset],
  );

  // ---- render: grey slice -------------------------------------------------------
  const sliceKey = volume && view && wl ? `${volume.fileId}|${slicePlane}|${anatomical}|${slice}|${wl.center}|${wl.width}` : '';
  const renderedKey = useRef('');

  // Histogram of the displayed slice for the side panel.
  useEffect(() => {
    if (!volume || !view) return;
    const id = window.setTimeout(() => {
      useViewerStore.getState().setSliceHistogram(sliceHistogram(volume.nifti, view, slice, volume.stats));
    }, 60);
    return () => window.clearTimeout(id);
  }, [volume, view, slice]);

  const drawBase = useCallback(() => {
    const canvas = baseRef.current;
    if (!canvas || !transform || !view || !volume || !wl) return;
    // Re-window the slice only when slice / plane / window actually changed.
    if (renderedKey.current !== sliceKey || !sliceCanvas.current) {
      if (!sliceCanvas.current) sliceCanvas.current = document.createElement('canvas');
      putPlane(sliceCanvas.current, renderSliceRGBA(volume.nifti, view, slice, wl, volume.stats), view.cols, view.rows);
      renderedKey.current = sliceKey;
    }
    const dpr = window.devicePixelRatio || 1;
    const W = Math.round(size.w * dpr), H = Math.round(size.h * dpr);
    if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, W, H);
    ctx.setTransform(dpr * transform.scaleX, 0, 0, dpr * transform.scaleY, dpr * transform.originX, dpr * transform.originY);
    ctx.imageSmoothingEnabled = smoothDisplay && !isPaintMode;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(sliceCanvas.current, 0, 0);
  }, [transform, view, volume, wl, slice, sliceKey, size, smoothDisplay, isPaintMode]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- render: overlays ---------------------------------------------------------
  const drawOverlay = useCallback(() => {
    const canvas = overlayRef.current;
    if (!canvas || !transform || !view || !volume) return;
    const dpr = window.devicePixelRatio || 1;
    const W = Math.round(size.w * dpr), H = Math.round(size.h * dpr);
    if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, W, H);
    if (!layerCanvas.current) layerCanvas.current = document.createElement('canvas');
    const layer = layerCanvas.current;
    const { rows, cols } = view;
    const dims = volume.nifti.dims;
    const blit = (rgba: Uint8ClampedArray) => {
      putPlane(layer, rgba, cols, rows);
      ctx.setTransform(dpr * transform.scaleX, 0, 0, dpr * transform.scaleY, dpr * transform.originX, dpr * transform.originY);
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(layer, 0, 0);
    };
    const planeOf = (mask: Uint8Array | null, d: { depth: number; height: number; width: number } | null) => {
      if (!mask || !d) return null;
      const grid = resolveMaskGrid(d, dims);
      if (!grid || mask.length !== d.depth * d.height * d.width) return null;
      return gatherPlane(mask, grid, view, slice);
    };

    if (zoneMapVisible) {
      const zp = planeOf(zoneMapMask, zoneMapDims);
      if (zp) blit(paintTable(zp, zoneColorTable(Math.round(zoneMapOpacity * 255))));
    }
    if (conformalVisible) {
      const cp = planeOf(conformalStatusMask, conformalDims);
      if (cp) blit(paintTable(cp, conformalColorTable()));
    }
    if (longVisible && longTp1Dims && longTp2Dims
      && longTp1Dims.depth === longTp2Dims.depth && longTp1Dims.height === longTp2Dims.height
      && longTp1Dims.width === longTp2Dims.width) {
      const p1 = planeOf(longTp1Mask, longTp1Dims);
      const p2 = planeOf(longTp2Mask, longTp2Dims);
      if (p1 && p2) blit(longitudinalRGBA(p1, p2));
    }
    if (longSubVisible) {
      const sp = planeOf(longSubVol, longSubDims);
      if (sp) blit(subtractionRGBA(sp));
    }
    const mask = segmentationMask.getMaskArray();
    if (segmentationMode && currentSegmentation && isOverlayVisible && mask && lesionGrid) {
      const lp = gatherPlane(mask, lesionGrid, view, slice);
      const zp = zoneColorizeEnabled ? planeOf(zoneMapMask, zoneMapDims) : null;
      if (zp) {
        blit(paintTable(zoneColorizedPlane(lp, zp), zoneColorTable(Math.round(153 * lesionOpacity))));
      } else {
        blit(paintTable(lp, labelColorTable(labels, labelVisibility, lesionOpacity)));
      }
    }

    // ---- vector annotations in screen space (crisp at any zoom) ----
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const toScreen = (r: number, c: number) => imageToScreen(transform, c, r);

    if (selectedLesion && lesionGrid) {
      const bb = selectedLesion.bounding_box;
      const a = maskZYXToVoxel(lesionGrid, bb.z_min, bb.y_min, bb.x_min);
      const b = maskZYXToVoxel(lesionGrid, bb.z_max, bb.y_max, bb.x_max);
      const lo = [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.min(a[2], b[2])];
      const hi = [Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.max(a[2], b[2])];
      if (slice >= lo[view.normal] && slice <= hi[view.normal]) {
        const d1 = displayOf(view, lo as [number, number, number]);
        const d2 = displayOf(view, hi as [number, number, number]);
        const p = toScreen(Math.min(d1.r, d2.r), Math.min(d1.c, d2.c));
        const q = toScreen(Math.max(d1.r, d2.r) + 1, Math.max(d1.c, d2.c) + 1);
        ctx.save();
        ctx.strokeStyle = '#F0E442';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([6, 3]);
        ctx.strokeRect(p.x, p.y, q.x - p.x, q.y - p.y);
        ctx.restore();
        const cv = maskZYXToVoxel(lesionGrid, Math.round(selectedLesion.centroid.z),
          Math.round(selectedLesion.centroid.y), Math.round(selectedLesion.centroid.x));
        const cd = displayOf(view, cv);
        if (Math.abs(cd.slice - slice) <= 1) {
          const cp = toScreen(cd.r + 0.5, cd.c + 0.5);
          ctx.save();
          ctx.strokeStyle = '#F0E442';
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(cp.x - 9, cp.y); ctx.lineTo(cp.x - 3, cp.y);
          ctx.moveTo(cp.x + 3, cp.y); ctx.lineTo(cp.x + 9, cp.y);
          ctx.moveTo(cp.x, cp.y - 9); ctx.lineTo(cp.x, cp.y - 3);
          ctx.moveTo(cp.x, cp.y + 3); ctx.lineTo(cp.x, cp.y + 9);
          ctx.stroke();
          ctx.restore();
        }
      }
    }

    if (aiClickPoints?.length && view.normal === 2) {
      for (const pt of aiClickPoints) {
        if (pt.z !== slice) continue;
        // AI points are (x = axis 1, y = axis 0, z = axis 2) on the image grid.
        const d = displayOf(view, [pt.y, pt.x, pt.z]);
        const p = toScreen(d.r + 0.5, d.c + 0.5);
        const pos = pt.label === 'positive';
        ctx.beginPath();
        ctx.arc(p.x, p.y, 7, 0, Math.PI * 2);
        ctx.fillStyle = pos ? 'rgba(0, 158, 115, 0.8)' : 'rgba(213, 94, 0, 0.8)';
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(p.x - 3.5, p.y); ctx.lineTo(p.x + 3.5, p.y);
        if (pos) { ctx.moveTo(p.x, p.y - 3.5); ctx.lineTo(p.x, p.y + 3.5); }
        ctx.stroke();
      }
    }

    // Exact brush footprint (the voxels a click will paint), not an approximation.
    if (canPaint && hover) {
      const shape: BrushShape = paintTool.brushShape === 'square' ? 'square' : 'circle';
      const erase = paintTool.tool === 'eraser';
      ctx.save();
      ctx.fillStyle = erase ? 'rgba(244, 120, 91, 0.28)' : 'rgba(87, 199, 212, 0.28)';
      for (const [dr, dc] of brushOffsets(paintTool.brushSize, shape)) {
        const r = hover.r + dr, c = hover.c + dc;
        if (r < 0 || c < 0 || r >= rows || c >= cols) continue;
        const p = toScreen(r, c);
        ctx.fillRect(p.x, p.y, transform.scaleX, transform.scaleY);
      }
      const p = toScreen(hover.r, hover.c);
      ctx.strokeStyle = erase ? '#F4785B' : '#57C7D4';
      ctx.lineWidth = 1;
      ctx.strokeRect(p.x + 0.5, p.y + 0.5, transform.scaleX - 1, transform.scaleY - 1);
      ctx.restore();
    }
  }, [
    transform, view, volume, size, slice, segmentationMask, segmentationMode, currentSegmentation, isOverlayVisible,
    lesionGrid, labels, labelVisibility, lesionOpacity, zoneMapVisible, zoneMapMask, zoneMapDims, zoneMapOpacity,
    zoneColorizeEnabled, conformalVisible, conformalStatusMask, conformalDims, longVisible, longTp1Mask, longTp1Dims,
    longTp2Mask, longTp2Dims, longSubVisible, longSubVol, longSubDims, selectedLesion, aiClickPoints, canPaint, hover,
    paintTool,
  ]);

  useEffect(() => {
    const id = requestAnimationFrame(() => { drawBase(); drawOverlay(); });
    return () => cancelAnimationFrame(id);
  }, [drawBase, drawOverlay, sliceKey, segmentationMask.revision]);

  // ---- interaction --------------------------------------------------------------
  const localPoint = (e: { clientX: number; clientY: number }) => {
    const rect = containerRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const updateCursorInfo = useCallback((px: { r: number; c: number } | null) => {
    const st = useViewerStore.getState();
    if (!px || !view || !volume) { st.setCursorInfo(null); return; }
    const ijk = voxelOf(view, slice, px.r, px.c);
    const value = valueAt(volume.nifti, ...ijk);
    const span = volume.stats.max - volume.stats.min;
    const mask = segmentationMask.getMaskArray();
    st.setCursorInfo({
      x: px.c, y: px.r, z: slice,
      intensity: span > 0 && Number.isFinite(value) ? Math.round(((value - volume.stats.min) / span) * 255) : null,
      voxel: ijk,
      world: voxelToWorld(volume.nifti.affine, ...ijk),
      value: Number.isFinite(value) ? value : null,
      label: mask && lesionGrid ? mask[maskIndex(lesionGrid, ...ijk)] : undefined,
    });
  }, [view, volume, slice, segmentationMask, lesionGrid]);

  const paintAt = useCallback((px: { r: number; c: number }) => {
    if (!view || !lesionGrid) return;
    segmentationMask.paintPlane({
      grid: lesionGrid, view, sliceIndex: slice, r: px.r, c: px.c,
      brushSize: paintTool.brushSize,
      brushShape: paintTool.brushShape === 'square' ? 'square' : 'circle',
      labelId: activeLabel, erase: paintTool.tool === 'eraser',
      drawOverMode, drawOverLabel: activeLabel,
    });
  }, [view, lesionGrid, slice, paintTool, activeLabel, drawOverMode, segmentationMask]);

  const onMouseDown = (e: React.MouseEvent) => {
    if (!transform || !view || !volume || !wl) return;
    const p = localPoint(e);
    const px = screenToPixel(transform, view, p.x, p.y);
    if (aiInteractiveMode && onAIClick && (e.button === 0 || e.button === 2)) {
      if (px && view.normal === 2) {
        const [i, j] = voxelOf(view, slice, px.r, px.c);
        onAIClick(j, i, e.button === 0);
      }
      return;
    }
    if (e.button === 0 && canPaint) {
      if (!px) return;
      segmentationMask.beginPlaneStroke(lesionGrid!, view, slice);
      paintAt(px);
      dragRef.current = { kind: 'paint', last: px };
      return;
    }
    if (e.button === 2) {
      const [lo, hi] = windowBounds(wl, volume.stats);
      dragRef.current = {
        kind: 'wl', x0: e.clientX, y0: e.clientY,
        wl: { center: (lo + hi) / 2, width: hi - lo },
        perPx: Math.max((volume.stats.max - volume.stats.min) / 600, 1e-9),
      };
      return;
    }
    dragRef.current = { kind: 'pan', x0: e.clientX, y0: e.clientY, panX: panOffset.x, panY: panOffset.y };
  };

  const onMouseMove = (e: React.MouseEvent) => {
    if (!transform || !view) return;
    const p = localPoint(e);
    const px = screenToPixel(transform, view, p.x, p.y);
    setHover(px);
    updateCursorInfo(px);
    const d = dragRef.current;
    if (!d) return;
    if (d.kind === 'pan') {
      useViewerStore.getState().setPanOffset({ x: d.panX + e.clientX - d.x0, y: d.panY + e.clientY - d.y0 });
    } else if (d.kind === 'wl') {
      const width = Math.max(d.wl.width + (e.clientX - d.x0) * d.perPx, d.perPx);
      const center = d.wl.center - (e.clientY - d.y0) * d.perPx;
      useViewerStore.getState().setWindowLevel(center, width);
    } else if (d.kind === 'paint' && px) {
      for (const q of linePixels(d.last, px).slice(1)) paintAt(q);
      d.last = px;
      drawOverlay();
    }
  };

  const endDrag = () => {
    if (dragRef.current?.kind === 'paint') segmentationMask.endStroke();
    dragRef.current = null;
  };

  // Wheel: slice; Ctrl/⌘ + wheel: zoom around the pointer (non-passive listener).
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const st = useViewerStore.getState();
      if (!view) return;
      if (e.ctrlKey || e.metaKey) {
        const rect = el.getBoundingClientRect();
        const next = Math.max(0.25, Math.min(20, st.zoomLevel * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
        st.setPanOffset(zoomAroundPoint(rect.width, rect.height, view, st.zoomLevel, st.panOffset, next,
          e.clientX - rect.left, e.clientY - rect.top));
        st.setZoomLevel(next);
      } else {
        const step = e.deltaY > 0 ? 1 : -1;
        st.setCurrentSliceIndex(Math.max(0, Math.min(view.depth - 1, st.currentSliceIndex + step)));
      }
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [view]);

  // ---- UI ----------------------------------------------------------------------
  const loading = volState.status === 'loading' || (volState.status === 'idle' && !!fileId);
  const cursorStyle = canPaint ? 'none' : aiInteractiveMode ? 'crosshair' : dragRef.current?.kind === 'pan' ? 'grabbing' : 'default';

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 select-none overflow-hidden bg-black"
      style={{ cursor: cursorStyle }}
      data-testid="client-slice-viewport"
      data-plane={slicePlane}
      data-slice={slice}
      data-ready={volume && view ? '1' : '0'}
      data-transform={import.meta.env.DEV && transform ? JSON.stringify(transform) : undefined}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={endDrag}
      onMouseLeave={() => { endDrag(); setHover(null); updateCursorInfo(null); }}
      onDoubleClick={() => { useViewerStore.getState().setZoomLevel(1); useViewerStore.getState().setPanOffset({ x: 0, y: 0 }); }}
      onContextMenu={(e) => e.preventDefault()}
    >
      <canvas ref={baseRef} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden />
      <canvas ref={overlayRef} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden />

      {view && transform && (
        <MeasurementOverlay
          imageWidth={view.cols}
          imageHeight={view.rows}
          canvasWidth={size.w}
          canvasHeight={size.h}
          sliceIndex={slice}
          planeKey={`${slicePlane}:${anatomical}`}
          zoomLevel={zoomLevel}
          panOffset={panOffset}
          mapping={transform}
          // Real spacing of the DISPLAYED axes [row, col] mm (anisotropic-safe).
          pixelSpacing={[view.rowSpacing, view.colSpacing]}
        />
      )}

      {loading && (
        <div className="absolute inset-0 grid place-items-center" role="status" aria-live="polite">
          <div className="flex w-72 flex-col items-center gap-3">
            <Skeleton className="aspect-square w-56 rounded-2xl" />
            <div className="h-1 w-56 overflow-hidden rounded-full bg-surface-raised">
              <div
                className="h-full bg-brand-500 transition-[width] duration-200"
                style={{ width: `${volState.status === 'loading' && volState.progress != null ? volState.progress : 35}%` }}
              />
            </div>
            <p className="text-xs text-ink-muted">
              {t('viewer3.loadingVolume', 'Loading volume in the browser…')}
            </p>
          </div>
        </div>
      )}

      {(lesionOffGrid || (measurementTool && !view)) && (
        <div className="pointer-events-none absolute bottom-10 left-1/2 z-10 -translate-x-1/2">
          <div className="flex items-center gap-2 rounded-lg border border-clinical-warn/40 bg-surface-void/85 px-3 py-1.5 text-xs text-clinical-warn">
            <EyeOff className="h-3.5 w-3.5" aria-hidden />
            {t('viewer3.maskOffGrid', 'Segmentation hidden: its grid does not match this image')}
          </div>
        </div>
      )}
      {check && !check.anatomical && volume && (
        <div className="pointer-events-none absolute left-1/2 top-12 z-10 -translate-x-1/2">
          <div className="flex items-center gap-2 rounded-lg border border-clinical-warn/40 bg-surface-void/85 px-3 py-1.5 text-xs text-clinical-warn">
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
            {t('viewer3.voxelOrder', 'Shown in voxel order — anatomical orientation not established')}
          </div>
        </div>
      )}
    </div>
  );
}

export default ClientSliceViewport;
