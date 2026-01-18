import { useEffect, useRef, useState, memo } from 'react';
import { useTranslation } from 'react-i18next';
import { Maximize2 } from 'lucide-react';
import { useViewerStore } from '@/store/useViewerStore';
import { usePanZoom } from '@/hooks/usePanZoom';
import { useMatplotlibVisualization } from '@/hooks/useMatplotlibVisualization';
import { useSegmentationData } from '@/hooks/useSegmentationData';
import { useSliceNavigation } from '@/hooks/useSliceNavigation';
import { useCanvasRendering } from '@/hooks/useCanvasRendering';
import { ViewerToolbar } from './viewer/ViewerToolbar';
import { SliceInfo } from './viewer/SliceInfo';
import { SliceSlider } from './viewer/SliceSlider';
import { MetadataPanel } from './viewer/MetadataPanel';
import { SegmentationCanvas } from './SegmentationCanvas';

interface ImageViewer2DProps {
  viewerControls: ReturnType<typeof import('../hooks/useViewerControls').useViewerControls>;
  segmentationControls: ReturnType<typeof import('../hooks/useSegmentationControls').useSegmentationControls>;
  createSegmentationRef: React.MutableRefObject<(() => void) | null>;
  patientName?: string;
  studyDescription?: string;
  studyModality?: string;
}

function ImageViewer2D({ viewerControls, segmentationControls, createSegmentationRef, patientName, studyDescription, studyModality }: ImageViewer2DProps) {
  const { t } = useTranslation();
  console.log('🔄 ImageViewer2D COMPONENT RENDER', {
    renderMode: viewerControls.renderMode,
    segmentationMode: viewerControls.segmentationMode,
  });

  // Refs
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollableRef = useRef<HTMLDivElement>(null);
  const matplotlibImageRef = useRef<HTMLImageElement>(null);

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

  // Segmentation controls from props
  const {
    currentSegmentation,
    setCurrentSegmentation,
    showOverlay,
    selectedLabelId,
    brushSize,
    eraseMode,
  } = segmentationControls;

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

  const { createSegmentation, paintStrokeMutation, isCreatingSegmentation, saveSegmentation, isSaving, saveStatus, lastSaveTime } = useSegmentationData({
    currentSegmentation,
    setCurrentSegmentation,
  });

  useSliceNavigation({ scrollableRef });

  useCanvasRendering({ canvasRef, containerRef, renderMode });

  // Debug: log renderMode changes
  useEffect(() => {
    console.log('🔄 RENDER MODE CHANGED TO:', renderMode);
  }, [renderMode]);

  // Debug: log segmentation state changes
  useEffect(() => {
    console.log('🎨 SEGMENTATION STATE:', {
      segmentationMode,
      currentSegmentation: currentSegmentation ? {
        id: currentSegmentation.segmentation_id,
        fileId: currentSegmentation.file_id,
      } : null,
      showOverlay,
      brushSize,
      eraseMode,
    });
  }, [segmentationMode, currentSegmentation, showOverlay, brushSize, eraseMode]);

  // Segmentation handlers - assign to ref so App can call it
  // Using useCallback-based createSegmentation for stable reference
  useEffect(() => {
    createSegmentationRef.current = () => {
      console.log('🎯 createSegmentationRef called, currentSeries:', currentSeries);
      if (currentSeries) {
        const fileId = currentSeries.file_id;
        const imageShape = {
          rows: currentSeries.metadata.rows!,
          columns: currentSeries.metadata.columns!,
          slices: currentSeries.metadata.slices!,
        };
        console.log('🎯 Calling createSegmentation with:', { fileId, imageShape });
        createSegmentation(fileId!, imageShape);
      } else {
        console.warn('⚠️ No currentSeries available for segmentation creation');
      }
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

      console.log('📏 MATPLOTLIB IMAGE SIZE:', {
        actual: `${actualWidth}x${actualHeight}`,
        natural: `${naturalWidth}x${naturalHeight}`
      });

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

        console.log('📦 BBOX SCALED:', {
          original: matplotlibData.bbox,
          scale: `${scaleX.toFixed(3)}x${scaleY.toFixed(3)}`,
          scaled: scaledBbox
        });

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

  // Removed unused handlePaintStroke function (kept paintStrokeMutation for future use)

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
              {/* Interactive segmentation canvas - positioned at scaled bbox */}
              {segmentationMode && currentSegmentation && currentSeries && matplotlibBbox && (
                <SegmentationCanvas
                  segmentationId={currentSegmentation.segmentation_id}
                  sliceIndex={currentSliceIndex}
                  totalSlices={currentSeries.total_slices}
                  imageWidth={currentSeries.metadata.columns!}
                  imageHeight={currentSeries.metadata.rows!}
                  containerRef={containerRef}
                  onPaintStroke={(stroke) => {
                    paintStrokeMutation.mutate({
                      ...stroke,
                      slice_index: currentSliceIndex,
                    });
                  }}
                  onSliceChange={setCurrentSliceIndex}
                  selectedLabelId={selectedLabelId}
                  brushSize={brushSize}
                  eraseMode={eraseMode}
                  showOverlay={showOverlay}
                  enabled={segmentationMode}
                  colormap={colormap}
                  baseImageData={`data:image/png;base64,${currentSeries.slices?.[currentSliceIndex]?.image_data || ''}`}
                  zoomLevel={zoomLevel}
                  panOffset={panOffset}
                  showBaseImage={false}
                  renderedImageSize={matplotlibImageRef.current ? {
                    width: matplotlibImageRef.current.offsetWidth,
                    height: matplotlibImageRef.current.offsetHeight
                  } : null}
                  matplotlibBbox={matplotlibBbox}
                  renderSegmentationOverlay={true}
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
                <SegmentationCanvas
                  segmentationId={currentSegmentation.segmentation_id}
                  sliceIndex={currentSliceIndex}
                  totalSlices={currentSeries.total_slices}
                  imageWidth={currentSeries.metadata.columns!}
                  imageHeight={currentSeries.metadata.rows!}
                  containerRef={containerRef}
                  onPaintStroke={(stroke) => {
                    paintStrokeMutation.mutate({
                      ...stroke,
                      slice_index: currentSliceIndex,
                    });
                  }}
                  onSliceChange={setCurrentSliceIndex}
                  selectedLabelId={selectedLabelId}
                  brushSize={brushSize}
                  eraseMode={eraseMode}
                  showOverlay={showOverlay}
                  enabled={segmentationMode}
                  colormap={colormap}
                  baseImageData={`data:image/png;base64,${currentSeries.slices?.[currentSliceIndex]?.image_data || ''}`}
                  zoomLevel={zoomLevel}
                  panOffset={panOffset}
                  showBaseImage={false}
                  renderSegmentationOverlay={true}
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
