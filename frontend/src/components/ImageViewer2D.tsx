import { useEffect, useRef, useState, memo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Maximize2 } from 'lucide-react';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { usePanZoom } from '@/hooks/usePanZoom';
import { useMatplotlibVisualization } from '@/hooks/useMatplotlibVisualization';
import { useSegmentationData } from '@/hooks/useSegmentationData';
import { useSliceNavigation } from '@/hooks/useSliceNavigation';
import { useCanvasRendering } from '@/hooks/useCanvasRendering';
import { useSegmentationShortcuts } from '@/hooks/useSegmentationShortcuts';
import { ViewerToolbar } from './viewer/ViewerToolbar';
import { SliceInfo } from './viewer/SliceInfo';
import { SliceSlider } from './viewer/SliceSlider';
import { MetadataPanel } from './viewer/MetadataPanel';
import { SegmentationCanvasLocal, type SegmentationCanvasLocalRef } from './SegmentationCanvasLocal';
import { useAISegmentation } from '@/hooks/useAISegmentation';
import { QuickScreenBadge } from './QuickScreenBadge';
import { VoxelValueOverlay } from './VoxelValueOverlay';

interface ImageViewer2DProps {
  viewerControls: ReturnType<typeof import('../hooks/useViewerControls').useViewerControls>;
  createSegmentationRef: React.MutableRefObject<(() => void) | null>;
  patientName?: string;
  studyDescription?: string;
  studyModality?: string;
  /** Expert annotation masks for contour overlay rendering */
  expertMasks?: Map<string, import('@/types').ExpertMaskData>;
}

function ImageViewer2D({ viewerControls, createSegmentationRef, patientName, studyDescription, studyModality, expertMasks }: ImageViewer2DProps) {
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
    colormap,
    segmentationMode,
    appliedXMin,
    appliedXMax,
    appliedYMin,
    appliedYMax,
  } = viewerControls;

  // Segmentation: which segmentation is active (from Zustand — single source of truth)
  const currentSegmentation = useSegmentationStore((s) => s.currentSegmentation);
  const setCurrentSegmentation = useSegmentationStore((s) => s.setCurrentSegmentation);

  // Paint settings from Zustand store (single source of truth, shared with SegmentationPanel)
  const paintTool = useSegmentationStore((s) => s.paintTool);
  const activeLabel = useSegmentationStore((s) => s.activeLabel);
  const isOverlayVisible = useSegmentationStore((s) => s.isOverlayVisible);
  const lesionOpacity = useSegmentationStore((s) => s.lesionOpacity);
  const isPaintMode = useSegmentationStore((s) => s.isPaintMode);
  const setIsPaintMode = useSegmentationStore((s) => s.setIsPaintMode);
  const selectedLesion = useSegmentationStore((s) => s.selectedLesion);

  // Derived values — same names so JSX props don't need changes
  const brushSize = paintTool.brushSize;
  const eraseMode = paintTool.tool === 'eraser';
  const selectedLabelId = activeLabel;
  const showOverlay = isOverlayVisible;

  // Store state
  const { currentSeries, currentSliceIndex, setCurrentSliceIndex, zoomLevel, panOffset, brightness, contrast, setCursorInfo } = useViewerStore();

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

  // Check if any expert masks are visible (to show canvas even without segmentation mode)
  const hasVisibleExperts = expertMasks ? Array.from(expertMasks.values()).some(m => m.visible && m.mask) : false;

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

  // Matplotlib image state for segmentation overlay
  const [, setMatplotlibImageSize] = useState<{ width: number; height: number } | null>(null);
  const [matplotlibBbox, setMatplotlibBbox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);

  // Calculated render dimensions (same formula as useCanvasRendering for consistency)
  const [renderDimensions, setRenderDimensions] = useState<{ width: number; height: number } | null>(null);

  // Calculate render dimensions to match Standard mode exactly
  useEffect(() => {
    if (!containerRef.current || !currentSeries) {
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
  }, [currentSeries]);

  // Capture matplotlib image dimensions and bbox when it loads
  useEffect(() => {
    const imgElement = matplotlibImageRef.current;
    if (!imgElement || renderMode !== 'matplotlib') {
      setMatplotlibImageSize(null);
      setMatplotlibBbox(null);
      return;
    }

    const updateSize = () => {
      const actualWidth = imgElement.offsetWidth;
      const actualHeight = imgElement.offsetHeight;
      const naturalWidth = imgElement.naturalWidth;
      const naturalHeight = imgElement.naturalHeight;

      setMatplotlibImageSize({ width: actualWidth, height: actualHeight });

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

  // CSS filter for brightness/contrast adjustments
  const imageFilter = brightness !== 100 || contrast !== 100
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

  if (!currentSeries) {
    return (
      <div className="flex items-center justify-center h-full bg-black">
        <div className="text-center text-gray-400">
          <Maximize2 className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>{t('viewer.selectImageToView')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full bg-black" ref={containerRef}>
      {/* Canvas or Matplotlib Image */}
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
                  so hide the local canvas (avoid double overlay). Show it for editing, expert masks,
                  selected lesion bounding box, or as fallback when backend overlay fails. */}
              {((segmentationMode && currentSegmentation && (!matplotlibSegId || useLocalOverlayFallback)) || hasVisibleExperts || selectedLesion) && currentSeries && (
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
                  expertMasks={expertMasks}
                />
              )}
            </div>
          ) : renderMode === 'matplotlib' && matplotlibLoading ? (
            <div className="text-white">{t('viewer.loadingMatplotlib')}</div>
          ) : renderMode === 'standard' ? (
            <div className="relative">
              <canvas ref={canvasRef} style={{ filter: imageFilter }} />
              {/* Interactive segmentation canvas - same size as canvas */}
              {((segmentationMode && currentSegmentation) || hasVisibleExperts) && currentSeries && (
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
                  expertMasks={expertMasks}
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

      {/* Segmentation Mode Indicator - positioned top center to not overlap controls */}
      {segmentationMode && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2">
          {isCreatingSegmentation ? (
            <div className="flex items-center gap-2 bg-yellow-500 text-black px-3 py-1.5 rounded-lg text-sm font-medium shadow-lg">
              <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
              {t('viewer.creatingSegmentation', 'Creating segmentation...')}
            </div>
          ) : currentSegmentation ? (
            <>
              {/* View/Edit mode indicator */}
              {isPaintMode ? (
                <div className="flex items-center gap-2 bg-green-500 text-white px-3 py-1.5 rounded-lg text-sm font-medium shadow-lg">
                  <div className="w-2 h-2 bg-white rounded-full animate-pulse" />
                  {t('viewer.editingSegmentation', 'Editing')}
                </div>
              ) : (
                <div className="flex items-center gap-2 bg-blue-500 text-white px-3 py-1.5 rounded-lg text-sm font-medium shadow-lg">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                  {t('viewer.viewingSegmentation', 'Viewing')}
                </div>
              )}
              {/* Edit toggle button */}
              <button
                onClick={() => setIsPaintMode(!isPaintMode)}
                className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium shadow-lg transition-colors ${
                  isPaintMode
                    ? 'bg-yellow-500 hover:bg-yellow-600 text-black'
                    : 'bg-green-600 hover:bg-green-700 text-white'
                }`}
                title={isPaintMode ? t('viewer.switchToView', 'Switch to view mode') : t('viewer.switchToEdit', 'Switch to edit mode')}
              >
                {isPaintMode ? (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                    {t('viewer.viewMode', 'View')}
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                    </svg>
                    {t('viewer.editMode', 'Edit')}
                  </>
                )}
              </button>
              {/* Save button - only visible in edit mode */}
              {isPaintMode && (
                <button
                  onClick={saveSegmentation}
                  disabled={isSaving}
                  className="flex items-center gap-1 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white px-3 py-1.5 rounded-lg text-sm font-medium shadow-lg transition-colors"
                  title={t('viewer.saveSegmentation', 'Save segmentation')}
                >
                  {isSaving ? (
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                    </svg>
                  )}
                  {t('viewer.save', 'Save')}
                </button>
              )}
              {/* Save status indicator */}
              {saveStatus === 'saving' && (
                <div className="flex items-center gap-1 bg-yellow-500 text-black px-2 py-1 rounded text-xs font-medium shadow-lg animate-pulse">
                  <div className="w-3 h-3 border-2 border-black border-t-transparent rounded-full animate-spin" />
                  {t('viewer.autoSaving', 'Saving...')}
                </div>
              )}
              {saveStatus === 'saved' && (
                <div className="flex items-center gap-1 bg-green-600 text-white px-2 py-1 rounded text-xs font-medium shadow-lg">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  {t('viewer.saved', 'Saved')}
                </div>
              )}
              {saveStatus === 'error' && (
                <div className="flex items-center gap-1 bg-red-600 text-white px-2 py-1 rounded text-xs font-medium shadow-lg">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  {t('viewer.saveError', 'Save error')}
                </div>
              )}
            </>
          ) : (
            <div className="flex items-center gap-2 bg-red-500 text-white px-3 py-1.5 rounded-lg text-sm font-medium shadow-lg">
              {t('viewer.noSegmentation', 'No segmentation')}
            </div>
          )}
        </div>
      )}

      {/* Controls (for both Standard and Matplotlib modes, and segmentation mode) */}
      <ViewerToolbar
        onZoomIn={panZoomHandlers.handleZoomIn}
        onZoomOut={panZoomHandlers.handleZoomOut}
        onResetView={panZoomHandlers.handleResetView}
      />

      {/* Edge AI Quick Screen — bottom right above slice slider */}
      {currentSeries?.slices?.[currentSliceIndex]?.image_data && (
        <div className="absolute bottom-20 right-4 z-20">
          <QuickScreenBadge
            currentSliceBase64={`data:image/png;base64,${currentSeries.slices[currentSliceIndex].image_data}`}
            imageWidth={currentSeries.metadata.columns ?? 256}
            imageHeight={currentSeries.metadata.rows ?? 256}
          />
        </div>
      )}

      {/* Slice Info */}
      <SliceInfo
        currentSliceIndex={currentSliceIndex}
        totalSlices={currentSeries.total_slices}
        zoomLevel={zoomLevel}
        renderMode={renderMode}
      />

      {/* Slice Slider */}
      <SliceSlider
        currentSliceIndex={currentSliceIndex}
        totalSlices={currentSeries.total_slices}
        onChange={setCurrentSliceIndex}
      />

      {/* Metadata */}
      <MetadataPanel
        metadata={currentSeries.metadata}
        patientName={patientName}
        studyDescription={studyDescription}
        modality={studyModality}
      />
    </div>
  );
}

export default memo(ImageViewer2D);
