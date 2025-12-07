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
}

function ImageViewer2D({ viewerControls, segmentationControls, createSegmentationRef }: ImageViewer2DProps) {
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

  const { createSegmentationMutation, paintStrokeMutation } = useSegmentationData({
    currentSegmentation,
    setCurrentSegmentation,
  });

  useSliceNavigation({ scrollableRef });

  useCanvasRendering({ canvasRef, containerRef, renderMode });

  // Debug: log renderMode changes
  useEffect(() => {
    console.log('🔄 RENDER MODE CHANGED TO:', renderMode);
  }, [renderMode]);

  // Segmentation handlers - assign to ref so App can call it
  useEffect(() => {
    createSegmentationRef.current = () => {
      if (currentSeries) {
        createSegmentationMutation.mutate({
          fileId: currentSeries.file_id!,
          imageShape: {
            rows: currentSeries.metadata.rows!,
            columns: currentSeries.metadata.columns!,
            slices: currentSeries.metadata.slices!,
          },
        });
      }
    };
  }, [currentSeries, createSegmentationMutation.mutate, createSegmentationRef]);

  // Matplotlib image state for segmentation overlay
  const [, setMatplotlibImageSize] = useState<{ width: number; height: number } | null>(null);
  const [matplotlibBbox, setMatplotlibBbox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);

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
            <div className="relative">
              <img
                ref={matplotlibImageRef}
                src={matplotlibData.image}
                alt="Matplotlib 2D Slice"
                className="max-w-full max-h-full object-contain"
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
                  renderSegmentationOverlay={false}
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

      {/* Controls (for standard mode and segmentation mode) */}
      {(renderMode === 'standard' || segmentationMode) && (
        <ViewerToolbar
          onZoomIn={panZoomHandlers.handleZoomIn}
          onZoomOut={panZoomHandlers.handleZoomOut}
          onResetView={panZoomHandlers.handleResetView}
        />
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
      <MetadataPanel metadata={currentSeries.metadata} />
    </div>
  );
}

export default memo(ImageViewer2D);
