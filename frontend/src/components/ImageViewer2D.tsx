import { useEffect, useRef, useState, memo, useCallback, useMemo, lazy, Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Eye, Maximize2, PenLine, Save, Check, X } from 'lucide-react';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { usePanZoom } from '@/hooks/usePanZoom';
import { useMatplotlibVisualization } from '@/hooks/useMatplotlibVisualization';
import { useSegmentationData } from '@/hooks/useSegmentationData';
import { useSliceNavigation } from '@/hooks/useSliceNavigation';
import { useCanvasRendering } from '@/hooks/useCanvasRendering';
import { useSegmentationShortcuts } from '@/hooks/useSegmentationShortcuts';
import { SegmentationCanvasLocal, type SegmentationCanvasLocalRef } from './SegmentationCanvasLocal';
import { ClientSliceViewport, type ClientViewportStatus } from './viewer2d/ClientSliceViewport';
import { useParitySliceDataUrl } from './viewer2d/useParitySliceDataUrl';
// Lazy — niivue (~heavy WebGL lib) loads only when the user opts into the 'niivue'
// fast-W/L mode, keeping the default 2D viewer bundle light.
const NiivueViewer2D = lazy(() =>
  import('./NiivueViewer2D').then((m) => ({ default: m.NiivueViewer2D })));
import { useAISegmentation } from '@/hooks/useAISegmentation';
import { QuickScreenBadge } from './QuickScreenBadge';
import { VoxelValueOverlay } from './VoxelValueOverlay';
import MeasurementOverlay from './MeasurementOverlay';
import { SegmentationConflictDialog } from './SegmentationConflictDialog';
import { ViewportSafetyOverlay } from './ViewportSafetyOverlay';
import { ErrorBoundary } from './ErrorBoundary';
import { Button } from './ui';

interface ImageViewer2DProps {
  viewerControls: ReturnType<typeof import('../hooks/useViewerControls').useViewerControls>;
  createSegmentationRef: React.MutableRefObject<(() => void) | null>;
  patientName?: string;
  patientMRN?: string;
  studyDescription?: string;
  studyModality?: string;
  /** v3: volume / view state of the client viewport, for the surrounding toolbar. */
  onClientStatus?: (status: ClientViewportStatus) => void;
}

function ImageViewer2D({ viewerControls, createSegmentationRef, patientName, patientMRN, studyDescription, onClientStatus }: ImageViewer2DProps) {
  const { t } = useTranslation();

  // Refs
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollableRef = useRef<HTMLDivElement>(null);
  const matplotlibImageRef = useRef<HTMLImageElement>(null);
  // Refs for segmentation canvases (standard and matplotlib modes)
  const segmentationCanvasRef = useRef<SegmentationCanvasLocalRef>(null);
  const segmentationCanvasMatplotlibRef = useRef<SegmentationCanvasLocalRef>(null);

  // Viewer controls from props
  const {
    renderMode,
    setRenderMode,
    colormap,
    segmentationMode,
    appliedXMin,
    appliedXMax,
    appliedYMin,
    appliedYMax,
  } = viewerControls;
  const isClient = renderMode === 'client';

  // Segmentation: which segmentation is active (from Zustand — single source of truth)
  const currentSegmentation = useSegmentationStore((s) => s.currentSegmentation);

  // Paint settings from Zustand store (single source of truth, shared with SegmentationPanel)
  const paintTool = useSegmentationStore((s) => s.paintTool);
  const activeLabel = useSegmentationStore((s) => s.activeLabel);
  const isOverlayVisible = useSegmentationStore((s) => s.isOverlayVisible);
  const lesionOpacity = useSegmentationStore((s) => s.lesionOpacity);
  const isPaintMode = useSegmentationStore((s) => s.isPaintMode);
  const setIsPaintMode = useSegmentationStore((s) => s.setIsPaintMode);
  const selectedLesion = useSegmentationStore((s) => s.selectedLesion);
  const zoneMapVisible = useSegmentationStore((s) => s.zoneMapVisible);
  const longitudinalVisible = useSegmentationStore((s) => s.longitudinalVisible);
  const conformalVisible = useSegmentationStore((s) => s.conformalVisible);

  // Derived values — same names so JSX props don't need changes
  const brushSize = paintTool.brushSize;
  const eraseMode = paintTool.tool === 'eraser';
  const selectedLabelId = activeLabel;
  const showOverlay = isOverlayVisible;

  // Store state
  const { currentSeries, currentSliceIndex, zoomLevel, panOffset, brightness, contrast, setCursorInfo } = useViewerStore();
  const cursorVoxel = useViewerStore((s) => s.cursorVoxel);

  // Custom hooks
  const panZoomHandlers = usePanZoom();

  // In matplotlib view mode, pass segmentationId so backend renders the overlay.
  // Only for saved segmentations (not local-* temp IDs) and only in view mode (not editing).
  const matplotlibSegId = (
    renderMode === 'matplotlib'
    && segmentationMode
    && currentSegmentation
    && !isPaintMode
    && !currentSegmentation.segmentation_id.startsWith('local-')
  ) ? currentSegmentation.segmentation_id : undefined;

  // Effective opacity: 0 when overlay toggle is OFF (hides overlay), slider value when ON.
  const effectiveOverlayOpacity = isOverlayVisible ? lesionOpacity : 0;

  const { matplotlibData, matplotlibLoading, matplotlibError } = useMatplotlibVisualization({
    colormap,
    appliedXMin,
    appliedXMax,
    appliedYMin,
    appliedYMax,
    segmentationId: matplotlibSegId,
    overlayOpacity: effectiveOverlayOpacity,
    enabled: renderMode === 'matplotlib',
  });

  // If matplotlib query with segmentation overlay failed, fall back to local canvas overlay
  const useLocalOverlayFallback = matplotlibError && !!matplotlibSegId;

  // Callback when paint stroke is applied locally - refresh canvas overlay
  const handlePaintComplete = useCallback((_sliceIndex: number) => {
    // Refresh the canvas overlays to show the updated mask
    segmentationCanvasRef.current?.refresh();
    segmentationCanvasMatplotlibRef.current?.refresh();
  }, []);

  const { createSegmentation, paintStrokeMutation, isCreatingSegmentation, saveSegmentation, isSaving, saveStatus, segmentationMask } = useSegmentationData({
    onPaintComplete: handlePaintComplete,
  });

  useSliceNavigation({ scrollableRef });

  useCanvasRendering({ canvasRef, containerRef, renderMode });

  // Reset paint mode when segmentation mode is turned off
  useEffect(() => {
    if (!segmentationMode) {
      setIsPaintMode(false);
    }
  }, [segmentationMode, setIsPaintMode]);

  // Segmentation keyboard shortcuts (Ctrl+Z, E, B, S, +/-, 1-9)
  const handleShortcutRefresh = useCallback(() => {
    segmentationCanvasRef.current?.refresh();
    segmentationCanvasMatplotlibRef.current?.refresh();
  }, []);

  useSegmentationShortcuts({
    enabled: segmentationMode && !!currentSegmentation,
    segmentationMask,
    onRefresh: handleShortcutRefresh,
  });

  // AI segmentation hook
  const aiSeg = useAISegmentation({
    fileId: currentSeries?.file_id,
    currentSliceIndex,
  });

  // Segmentation handlers - assign to ref so App can call it
  // Using useCallback-based createSegmentation for stable reference
  useEffect(() => {
    createSegmentationRef.current = () => {
      if (!currentSeries) {
        console.warn('[ImageViewer2D] No currentSeries available for segmentation creation');
        return;
      }
      const fileId = currentSeries.file_id;
      const rows = currentSeries.metadata.rows;
      const columns = currentSeries.metadata.columns;
      const slices = currentSeries.metadata.slices;
      if (!fileId || !rows || !columns || !slices) {
        console.warn('[ImageViewer2D] Missing image dimensions or file_id for segmentation');
        return;
      }
      createSegmentation(fileId, { rows, columns, slices });
    };
  }, [currentSeries, createSegmentation, createSegmentationRef]);

  // ---- v3 client path ------------------------------------------------------------
  const [clientStatus, setClientStatus] = useState<ClientViewportStatus | null>(null);
  const handleClientStatus = useCallback((s: ClientViewportStatus) => {
    setClientStatus(s);
    onClientStatus?.(s);
  }, [onClientStatus]);

  // Fail closed to the server PNG path, and say so (never a silent switch).
  const handleClientFallback = useCallback((reason: string) => {
    console.warn('[ImageViewer2D] client rendering refused, using server PNG path:', reason);
    toast.warning(t('viewer3.fallbackTitle', 'Showing server-rendered images'), {
      id: 'client-fallback',
      description: t('viewer3.fallbackBody', 'This image could not be verified for in-browser display ({{reason}}). The previous server rendering is used instead.', { reason }),
    });
    setRenderMode('standard');
  }, [setRenderMode, t]);

  // The server paths only have the k plane: restore that geometry when leaving the
  // in-browser path (otherwise a sagittal slice index would be read as a k index).
  useEffect(() => {
    if (!isClient) useViewerStore.getState().resetSliceGeometry();
  }, [isClient]);

  // DICOM series are not read by the browser renderer — straight to the server path.
  useEffect(() => {
    if (isClient && currentSeries && currentSeries.format !== 'nifti') {
      handleClientFallback(t('viewer3.dicomNotClient', 'DICOM series'));
    }
  }, [isClient, currentSeries, handleClientFallback, t]);

  // Edge-AI quick screen keeps receiving exactly what it was designed on: the
  // server-equivalent 8-bit slice of the k plane (bit-identical, see parity tests).
  const clientQuickScreenUrl = useParitySliceDataUrl(
    isClient ? clientStatus?.volume ?? null : null,
    cursorVoxel?.[2] ?? null,
  );

  // ---- legacy server paths (fallback) --------------------------------------------
  // Matplotlib image state for segmentation overlay
  const [matplotlibBbox, setMatplotlibBbox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);

  // Calculated render dimensions (same formula as useCanvasRendering for consistency)
  const [renderDimensions, setRenderDimensions] = useState<{ width: number; height: number } | null>(null);

  // Calculate render dimensions to match Standard mode exactly
  useEffect(() => {
    if (!containerRef.current || !currentSeries || isClient) {
      setRenderDimensions(null);
      return;
    }

    const calculateDimensions = () => {
      const container = containerRef.current;
      if (!container) return;

      const containerWidth = container.clientWidth;
      const containerHeight = container.clientHeight;
      const imageWidth = currentSeries.metadata.columns || 256;
      const imageHeight = currentSeries.metadata.rows || 256;
      const imageAspect = imageWidth / imageHeight;
      const containerAspect = containerWidth / containerHeight;

      let renderWidth, renderHeight;
      if (imageAspect > containerAspect) {
        renderWidth = containerWidth * 0.9; // 90% of container width (same as Standard)
        renderHeight = renderWidth / imageAspect;
      } else {
        renderHeight = containerHeight * 0.9; // 90% of container height (same as Standard)
        renderWidth = renderHeight * imageAspect;
      }

      setRenderDimensions({ width: renderWidth, height: renderHeight });
    };

    calculateDimensions();
    window.addEventListener('resize', calculateDimensions);
    return () => window.removeEventListener('resize', calculateDimensions);
  }, [currentSeries, isClient]);

  // Capture matplotlib image dimensions and bbox when it loads
  useEffect(() => {
    const imgElement = matplotlibImageRef.current;
    if (!imgElement || renderMode !== 'matplotlib') {
      setMatplotlibBbox(null);
      return;
    }

    const updateSize = () => {
      const actualWidth = imgElement.offsetWidth;
      const actualHeight = imgElement.offsetHeight;
      const naturalWidth = imgElement.naturalWidth;
      const naturalHeight = imgElement.naturalHeight;

      // Scale bbox from natural size to actual rendered size
      if (matplotlibData?.bbox && naturalWidth > 0 && naturalHeight > 0) {
        const scaleX = actualWidth / naturalWidth;
        const scaleY = actualHeight / naturalHeight;

        const scaledBbox = {
          left: matplotlibData.bbox.left * scaleX,
          top: matplotlibData.bbox.top * scaleY,
          width: matplotlibData.bbox.width * scaleX,
          height: matplotlibData.bbox.height * scaleY,
          figure_width: actualWidth,
          figure_height: actualHeight
        };

        setMatplotlibBbox(scaledBbox);
      }
    };

    // Update size when image loads
    if (imgElement.complete && imgElement.offsetWidth > 0) {
      updateSize();
    } else {
      imgElement.addEventListener('load', updateSize);
    }

    // Update on window resize
    window.addEventListener('resize', updateSize);

    return () => {
      imgElement.removeEventListener('load', updateSize);
      window.removeEventListener('resize', updateSize);
    };
  }, [matplotlibData?.image, matplotlibData?.bbox, renderMode]);

  // CSS filter for brightness/contrast adjustments. In matplotlib mode the base image
  // already carries a TRUE VOI-LUT window/level (server-rendered from raw intensities),
  // so the cosmetic 8-bit brightness/contrast filter must NOT stack on top of it (double
  // adjustment). It applies only in standard mode, where it is the sole contrast control.
  const imageFilter = renderMode !== 'matplotlib' && (brightness !== 100 || contrast !== 100)
    ? `brightness(${brightness / 100}) contrast(${contrast / 100})`
    : undefined;

  // Track cursor position over the image (zoom/pan aware)
  const handleCursorMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!currentSeries || !containerRef.current) return;

    const canvasEl = canvasRef.current;
    if (!canvasEl) return;

    const rect = canvasEl.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;

    // CSS → canvas logical pixels
    const cssX = e.clientX - rect.left;
    const cssY = e.clientY - rect.top;
    let logicalX = (cssX / rect.width) * canvasEl.width;
    let logicalY = (cssY / rect.height) * canvasEl.height;

    // Apply inverse zoom/pan transform (same as SegmentationCanvasLocal's getMousePos)
    const centerX = canvasEl.width / 2;
    const centerY = canvasEl.height / 2;
    logicalX = (logicalX - centerX - panOffset.x) / zoomLevel + centerX;
    logicalY = (logicalY - centerY - panOffset.y) / zoomLevel + centerY;

    // Convert to image coordinates
    const imgW = currentSeries.metadata.columns ?? 256;
    const imgH = currentSeries.metadata.rows ?? 256;
    const imgX = Math.floor((logicalX / canvasEl.width) * imgW);
    const imgY = Math.floor((logicalY / canvasEl.height) * imgH);

    if (imgX < 0 || imgX >= imgW || imgY < 0 || imgY >= imgH) {
      return;
    }

    // Read pixel intensity from canvas at the screen position (accounts for zoom)
    let intensity: number | null = null;
    try {
      const ctx = canvasEl.getContext('2d');
      if (ctx) {
        const pixel = ctx.getImageData(Math.floor(cssX * (canvasEl.width / rect.width)), Math.floor(cssY * (canvasEl.height / rect.height)), 1, 1).data;
        // Grayscale: R=G=B for medical images
        intensity = pixel[0];
      }
    } catch {
      // Canvas may be tainted
    }

    setCursorInfo({
      x: imgX,
      y: imgY,
      z: currentSliceIndex,
      intensity,
    });
  }, [currentSeries, currentSliceIndex, setCursorInfo, zoomLevel, panOffset]);

  const handleCursorLeave = useCallback(() => {
    setCursorInfo(null);
  }, [setCursorInfo]);

  const legacyQuickScreenUrl = useMemo(() => {
    const data = currentSeries?.slices?.[currentSliceIndex]?.image_data;
    return data ? `data:image/png;base64,${data}` : null;
  }, [currentSeries, currentSliceIndex]);
  const quickScreenUrl = isClient ? clientQuickScreenUrl : legacyQuickScreenUrl;

  if (!currentSeries) {
    return (
      <div className="flex h-full items-center justify-center bg-black">
        <div className="text-center text-ink-muted">
          <Maximize2 className="mx-auto mb-4 h-14 w-14 opacity-40" aria-hidden />
          <p className="text-sm">{t('viewer.selectImageToView')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full bg-black" ref={containerRef}>
      {/* RC-016 + RC-023 (CAPA-004 CA-4.2): patient identity and orientation
          state annotated onto the viewport itself, so they survive a
          screenshot, an export, or a maximised view. Rendered FIRST and
          unconditionally — a conditional safety annotation is not one. */}
      <ViewportSafetyOverlay
        patientName={patientName}
        patientMRN={patientMRN}
        studyDescription={studyDescription}
        anatomicalOrientation={currentSeries?.metadata?.anatomical_orientation}
      />

      {/* v3 default: browser rendering from the NIfTI (full bit depth, 3 planes).
          Sits below the z-20 safety overlay. Any disagreement with the server's
          metadata hands over to the server PNG path below (handleClientFallback). */}
      {isClient && (
        <ErrorBoundary name="ClientSliceViewport">
          <ClientSliceViewport
            segmentationMask={segmentationMask}
            segmentationMode={segmentationMode}
            aiClickPoints={aiSeg.aiMode === 'interactive' ? aiSeg.clickPoints : undefined}
            aiInteractiveMode={aiSeg.aiMode === 'interactive'}
            onAIClick={aiSeg.handleCanvasClick}
            onFallback={handleClientFallback}
            onStatus={handleClientStatus}
          />
        </ErrorBoundary>
      )}

      {/* niivue fast-W/L mode (view-only GPU window/level). Sits below the z-20 safety
          overlay so patient identity stays visible, and above the (empty in this mode)
          standard/matplotlib viewport. Painting is intentionally NOT available here —
          it stays in the standard/matplotlib modes (no wrong-location hazard). */}
      {renderMode === 'niivue' && (
        <div className="absolute inset-0 z-10">
          <Suspense fallback={<div className="flex h-full w-full items-center justify-center text-xs text-ink-muted">Cargando visor GPU…</div>}>
            <NiivueViewer2D />
          </Suspense>
        </div>
      )}
      {/* Legacy server paths: canvas (standard) or matplotlib image */}
      {!isClient && (
      <div
        ref={scrollableRef}
        className="absolute inset-0 overflow-auto cursor-move"
        onMouseDown={(e) => {
          if (!segmentationMode || !isPaintMode) panZoomHandlers.handleMouseDown(e);
        }}
        onMouseMove={(e) => {
          if (!segmentationMode || !isPaintMode) panZoomHandlers.handleMouseMove(e);
          handleCursorMove(e);
        }}
        onMouseUp={() => {
          if (!segmentationMode || !isPaintMode) panZoomHandlers.handleMouseUp();
        }}
        onMouseLeave={() => {
          if (!segmentationMode || !isPaintMode) panZoomHandlers.handleMouseUp();
          handleCursorLeave();
        }}
      >
        <div className="flex items-center justify-center min-h-full min-w-full">
          {/* Base image layer */}
          {renderMode === 'matplotlib' && matplotlibData ? (
            <div
              className="relative"
              style={renderDimensions ? {
                width: `${renderDimensions.width}px`,
                height: `${renderDimensions.height}px`,
                transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoomLevel})`,
                transformOrigin: 'center center',
              } : undefined}
            >
              <img
                ref={matplotlibImageRef}
                src={matplotlibData.image}
                alt="Matplotlib 2D Slice"
                style={renderDimensions ? {
                  width: '100%',
                  height: '100%',
                  objectFit: 'fill',
                  imageRendering: 'pixelated',
                  filter: imageFilter,
                } : { filter: imageFilter }}
                className={renderDimensions ? '' : 'max-w-full max-h-full object-contain'}
              />
              {/* Interactive segmentation canvas - covers full image in minimal mode, or bbox area.
                  When matplotlibSegId is set, backend renders the segmentation in the matplotlib PNG,
                  so hide the local canvas (avoid double overlay). Show it for editing,
                  selected lesion bounding box, or as fallback when backend overlay fails. */}
              {((segmentationMode && currentSegmentation && (!matplotlibSegId || useLocalOverlayFallback)) || selectedLesion || zoneMapVisible || longitudinalVisible || conformalVisible) && currentSeries && (
                <SegmentationCanvasLocal
                  ref={segmentationCanvasMatplotlibRef}
                  segmentationMask={segmentationMask}
                  sliceIndex={currentSliceIndex}
                  imageWidth={currentSeries.metadata.columns ?? 256}
                  imageHeight={currentSeries.metadata.rows ?? 256}
                  containerRef={containerRef}
                  onPaintStroke={(stroke) => {
                    paintStrokeMutation.mutate({
                      ...stroke,
                      slice_index: currentSliceIndex,
                    });
                  }}
                  selectedLabelId={selectedLabelId}
                  brushSize={brushSize}
                  eraseMode={eraseMode}
                  showOverlay={showOverlay}
                  enabled={segmentationMode}
                  baseImageData={`data:image/png;base64,${currentSeries.slices?.[currentSliceIndex]?.image_data || ''}`}
                  zoomLevel={zoomLevel}
                  panOffset={panOffset}
                  showBaseImage={false}
                  renderedImageSize={matplotlibImageRef.current ? {
                    width: matplotlibImageRef.current.offsetWidth,
                    height: matplotlibImageRef.current.offsetHeight
                  } : null}
                  matplotlibBbox={matplotlibBbox || (renderDimensions ? {
                    left: 0,
                    top: 0,
                    width: renderDimensions.width,
                    height: renderDimensions.height,
                  } : null)}
                  aiClickPoints={aiSeg.aiMode === 'interactive' ? aiSeg.clickPoints : undefined}
                  aiInteractiveMode={aiSeg.aiMode === 'interactive'}
                  onAIClick={aiSeg.handleCanvasClick}

                />
              )}
            </div>
          ) : renderMode === 'matplotlib' && matplotlibLoading ? (
            <div className="text-sm text-ink-muted">{t('viewer.loadingMatplotlib')}</div>
          ) : renderMode === 'standard' ? (
            <div className="relative">
              <canvas ref={canvasRef} style={{ filter: imageFilter }} />
              {/* Interactive segmentation canvas - same size as canvas */}
              {((segmentationMode && currentSegmentation) || zoneMapVisible || longitudinalVisible || conformalVisible) && currentSeries && (
                <SegmentationCanvasLocal
                  ref={segmentationCanvasRef}
                  segmentationMask={segmentationMask}
                  sliceIndex={currentSliceIndex}
                  imageWidth={currentSeries.metadata.columns ?? 256}
                  imageHeight={currentSeries.metadata.rows ?? 256}
                  containerRef={containerRef}
                  onPaintStroke={(stroke) => {
                    paintStrokeMutation.mutate({
                      ...stroke,
                      slice_index: currentSliceIndex,
                    });
                  }}
                  selectedLabelId={selectedLabelId}
                  brushSize={brushSize}
                  eraseMode={eraseMode}
                  showOverlay={showOverlay}
                  enabled={segmentationMode}
                  baseImageData={`data:image/png;base64,${currentSeries.slices?.[currentSliceIndex]?.image_data || ''}`}
                  zoomLevel={zoomLevel}
                  panOffset={panOffset}
                  showBaseImage={false}
                  aiClickPoints={aiSeg.aiMode === 'interactive' ? aiSeg.clickPoints : undefined}
                  aiInteractiveMode={aiSeg.aiMode === 'interactive'}
                  onAIClick={aiSeg.handleCanvasClick}

                />
              )}
              {/* Measurement tools overlay */}
              {currentSeries && canvasRef.current && (
                <MeasurementOverlay
                  imageWidth={currentSeries.metadata.columns ?? 256}
                  imageHeight={currentSeries.metadata.rows ?? 256}
                  canvasWidth={canvasRef.current.width || (currentSeries.metadata.columns ?? 256)}
                  canvasHeight={canvasRef.current.height || (currentSeries.metadata.rows ?? 256)}
                  sliceIndex={currentSliceIndex}
                  zoomLevel={zoomLevel}
                  panOffset={panOffset}
                  // Real in-plane voxel spacing [row, col] mm from the image header, so
                  // measurements are correct on ANISOTROPIC data (was hardcoded 1mm — a
                  // Class C safety defect that reported wrong lengths on non-1mm scans).
                  pixelSpacing={
                    Array.isArray(currentSeries.metadata.pixel_spacing) &&
                    currentSeries.metadata.pixel_spacing.length >= 2
                      ? [currentSeries.metadata.pixel_spacing[0], currentSeries.metadata.pixel_spacing[1]]
                      : undefined
                  }
                />
              )}
            </div>
          ) : null}
        </div>
        {/* Voxel value overlay — crisp text at viewport level, outside CSS scale transform */}
        {renderMode === 'matplotlib' && zoomLevel >= 14 && currentSeries?.slices?.[currentSliceIndex]?.image_data && (
          <VoxelValueOverlay
            sliceImageData={currentSeries.slices[currentSliceIndex].image_data}
            imageWidth={currentSeries.metadata.columns ?? 256}
            imageHeight={currentSeries.metadata.rows ?? 256}
            scrollableRef={scrollableRef as React.RefObject<HTMLDivElement>}
            imageElementRef={matplotlibImageRef as React.RefObject<HTMLImageElement>}
            zoomLevel={zoomLevel}
            panOffset={panOffset}
          />
        )}
      </div>
      )}

      {/* Segmentation edit bar — top centre, clear of identity (left) and orientation (right). */}
      {segmentationMode && (
        <div className="absolute left-1/2 top-3 z-30 -translate-x-1/2">
          <div className="flex items-center gap-1.5 rounded-xl border border-surface-border bg-surface-raised/90 p-1 shadow-lg shadow-black/40 backdrop-blur">
            {isCreatingSegmentation ? (
              <span className="flex items-center gap-2 px-2.5 py-1 text-xs font-medium text-clinical-warn">
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-clinical-warn border-t-transparent" aria-hidden />
                {t('viewer.creatingSegmentation', 'Creating segmentation...')}
              </span>
            ) : currentSegmentation ? (
              <>
                <span
                  className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium ${
                    isPaintMode ? 'bg-brand-950 text-brand-400' : 'text-ink-soft'
                  }`}
                  role="status"
                >
                  {isPaintMode ? (
                    <><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-400" aria-hidden />{t('viewer.editingSegmentation', 'Editing')}</>
                  ) : (
                    <><Eye className="h-3.5 w-3.5" aria-hidden />{t('viewer.viewingSegmentation', 'Viewing')}</>
                  )}
                </span>
                <Button
                  size="sm"
                  variant={isPaintMode ? 'ghost' : 'secondary'}
                  onClick={() => setIsPaintMode(!isPaintMode)}
                  leftIcon={isPaintMode ? <Eye className="h-3.5 w-3.5" aria-hidden /> : <PenLine className="h-3.5 w-3.5" aria-hidden />}
                  aria-label={isPaintMode ? t('viewer.switchToView', 'Switch to view mode') : t('viewer.switchToEdit', 'Switch to edit mode')}
                  className="h-7"
                >
                  {isPaintMode ? t('viewer.viewMode', 'View') : t('viewer.editMode', 'Edit')}
                </Button>
                {isPaintMode && (
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={saveSegmentation}
                    loading={isSaving}
                    leftIcon={<Save className="h-3.5 w-3.5" aria-hidden />}
                    className="h-7"
                  >
                    {t('viewer.save', 'Save')}
                  </Button>
                )}
                {saveStatus === 'saving' && (
                  <span className="px-2 text-xs text-clinical-warn" role="status">{t('viewer.autoSaving', 'Saving...')}</span>
                )}
                {saveStatus === 'saved' && (
                  <span className="flex items-center gap-1 px-2 text-xs text-clinical-good" role="status">
                    <Check className="h-3.5 w-3.5" aria-hidden />{t('viewer.saved', 'Saved')}
                  </span>
                )}
                {saveStatus === 'error' && (
                  <span className="flex items-center gap-1 px-2 text-xs text-clinical-crit" role="alert">
                    <X className="h-3.5 w-3.5" aria-hidden />{t('viewer.saveError', 'Save error')}
                  </span>
                )}
              </>
            ) : (
              <span className="px-2.5 py-1 text-xs font-medium text-ink-muted">
                {t('viewer.noSegmentation', 'No segmentation')}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Edge AI Quick Screen — bottom right, above the status corner */}
      {quickScreenUrl && (
        <div className="absolute bottom-12 right-10 z-20">
          <QuickScreenBadge
            currentSliceBase64={quickScreenUrl}
            imageWidth={currentSeries.metadata.columns ?? 256}
            imageHeight={currentSeries.metadata.rows ?? 256}
          />
        </div>
      )}

      {/* A-2: reconcile a concurrent-save conflict without silently losing edits. */}
      <SegmentationConflictDialog
        conflict={segmentationMask.state.conflict}
        busy={segmentationMask.state.isSaving || segmentationMask.state.isLoading}
        onOverwrite={() => { void segmentationMask.overwriteSave(); }}
        onDiscardReload={() => { void segmentationMask.discardAndReload(); }}
        onDismiss={segmentationMask.dismissConflict}
      />

    </div>
  );
}

export default memo(ImageViewer2D);
