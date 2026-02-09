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

interface ImageViewer2DProps {
  viewerControls: ReturnType<typeof import('../hooks/useViewerControls').useViewerControls>;
  createSegmentationRef: React.MutableRefObject<(() => void) | null>;
  patientName?: string;
  studyDescription?: string;
  studyModality?: string;
}

function ImageViewer2D({ viewerControls, createSegmentationRef, patientName, studyDescription, studyModality }: ImageViewer2DProps) {
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

  // Derived values — same names so JSX props don't need changes
  const brushSize = paintTool.brushSize;
  const eraseMode = paintTool.tool === 'eraser';
  const selectedLabelId = activeLabel;
  const showOverlay = isOverlayVisible;

  // Store state
  const { currentSeries, currentSliceIndex, setCurrentSliceIndex, zoomLevel, panOffset } = useViewerStore();

  // Custom hooks
  const panZoomHandlers = usePanZoom();

  const { matplotlibData, matplotlibLoading } = useMatplotlibVisualization({
    colormap,
    appliedXMin,
    appliedXMax,
    appliedYMin,
    appliedYMax,
  });

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
          if (!segmentationMode) panZoomHandlers.handleMouseDown(e);
        }}
        onMouseMove={(e) => {
          if (!segmentationMode) panZoomHandlers.handleMouseMove(e);
        }}
        onMouseUp={() => {
          if (!segmentationMode) panZoomHandlers.handleMouseUp();
        }}
        onMouseLeave={() => {
          if (!segmentationMode) panZoomHandlers.handleMouseUp();
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
                  objectFit: 'fill', // Fill exact dimensions to match Standard mode voxel-by-voxel
                  imageRendering: 'pixelated', // Preserve sharp pixels
                } : undefined}
                className={renderDimensions ? '' : 'max-w-full max-h-full object-contain'}
              />
              {/* Interactive segmentation canvas - covers full image in minimal mode, or bbox area */}
              {segmentationMode && currentSegmentation && currentSeries && (
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
            <div className="text-white">{t('viewer.loadingMatplotlib')}</div>
          ) : renderMode === 'standard' ? (
            <div className="relative">
              <canvas ref={canvasRef} />
              {/* Interactive segmentation canvas - same size as canvas */}
              {segmentationMode && currentSegmentation && currentSeries && (
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
            </div>
          ) : null}
        </div>
      </div>

      {/* Segmentation Mode Indicator - positioned top center to not overlap controls */}
      {segmentationMode && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2">
          {isCreatingSegmentation ? (
            <div className="flex items-center gap-2 bg-yellow-500 text-black px-3 py-1.5 rounded-lg text-sm font-medium shadow-lg">
              <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
              {t('viewer.creatingSegmentation', 'Creando segmentación...')}
            </div>
          ) : currentSegmentation ? (
            <>
              <div className="flex items-center gap-2 bg-green-500 text-white px-3 py-1.5 rounded-lg text-sm font-medium shadow-lg">
                <div className="w-2 h-2 bg-white rounded-full animate-pulse" />
                {t('viewer.segmentationActive', 'Segmentación activa')}
              </div>
              <button
                onClick={saveSegmentation}
                disabled={isSaving}
                className="flex items-center gap-1 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white px-3 py-1.5 rounded-lg text-sm font-medium shadow-lg transition-colors"
                title={t('viewer.saveSegmentation', 'Guardar segmentación')}
              >
                {isSaving ? (
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                  </svg>
                )}
                {t('viewer.save', 'Guardar')}
              </button>
              {/* Save status indicator */}
              {saveStatus === 'saving' && (
                <div className="flex items-center gap-1 bg-yellow-500 text-black px-2 py-1 rounded text-xs font-medium shadow-lg animate-pulse">
                  <div className="w-3 h-3 border-2 border-black border-t-transparent rounded-full animate-spin" />
                  {t('viewer.autoSaving', 'Guardando...')}
                </div>
              )}
              {saveStatus === 'saved' && (
                <div className="flex items-center gap-1 bg-green-600 text-white px-2 py-1 rounded text-xs font-medium shadow-lg">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  {t('viewer.saved', 'Guardado')}
                </div>
              )}
              {saveStatus === 'error' && (
                <div className="flex items-center gap-1 bg-red-600 text-white px-2 py-1 rounded text-xs font-medium shadow-lg">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  {t('viewer.saveError', 'Error al guardar')}
                </div>
              )}
            </>
          ) : (
            <div className="flex items-center gap-2 bg-red-500 text-white px-3 py-1.5 rounded-lg text-sm font-medium shadow-lg">
              {t('viewer.noSegmentation', 'Sin segmentación')}
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
