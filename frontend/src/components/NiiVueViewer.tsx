/**
 * NiiVue-based NIfTI viewer component.
 * Renders NIfTI files directly using WebGL2 without PNG conversion.
 * Supports segmentation overlays with proper voxel alignment.
 */

import { useEffect, useRef, useState, useCallback, memo } from 'react';
import { Niivue, NVImage, SLICE_TYPE } from '@niivue/niivue';
import { useViewerStore } from '@/store/useViewerStore';
import type { SegmentationResponse, PaintStroke } from '../types/segmentation';

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const _API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// Extended Niivue type to include methods not in default types
interface NiivueExtended extends Niivue {
  moveCrosshairInVox: (x: number, y: number, z: number) => void;
}

interface NiiVueViewerProps {
  fileUrl: string;
  segmentation?: SegmentationResponse | null;
  segmentationUrl?: string | null;
  onSliceChange?: (sliceIndex: number) => void;
  onPaintStroke?: (stroke: PaintStroke) => void;
  colormap?: string;
  showOverlay?: boolean;
  segmentationMode?: boolean;
  brushSize?: number;
  eraseMode?: boolean;
  selectedLabelId?: number;
}

function NiiVueViewerComponent({
  fileUrl,
  segmentation,
  segmentationUrl,
  onSliceChange,
  onPaintStroke,
  colormap = 'gray',
  showOverlay = true,
  segmentationMode = false,
  brushSize = 3,
  eraseMode = false,
  selectedLabelId = 1,
}: NiiVueViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nvRef = useRef<Niivue | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const { currentSliceIndex, setCurrentSliceIndex, zoomLevel } = useViewerStore();
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [volumeLoaded, setVolumeLoaded] = useState(false);
  const [isPainting, setIsPainting] = useState(false);

  // Initialize NiiVue
  useEffect(() => {
    if (!canvasRef.current) return;

    const nv = new Niivue({
      backColor: [0, 0, 0, 1], // Black background
      show3Dcrosshair: false,
      isRadiologicalConvention: false,
      sliceType: SLICE_TYPE.AXIAL,
      multiplanarForceRender: false,
      isColorbar: false,
      isOrientCube: false,
      crosshairWidth: 0,
      textHeight: 0,
    });

    nv.attachToCanvas(canvasRef.current);
    nvRef.current = nv;

    // Handle slice change events
    nv.onLocationChange = (data: unknown) => {
      const locationData = data as { vox?: number[] };
      if (locationData.vox && locationData.vox.length >= 3) {
        const newSlice = Math.round(locationData.vox[2]);
        if (newSlice !== currentSliceIndex) {
          setCurrentSliceIndex(newSlice);
          onSliceChange?.(newSlice);
        }
      }
    };

    return () => {
      nvRef.current = null;
    };
  }, []);

  // Load volume when URL changes
  useEffect(() => {
    const loadVolume = async () => {
      if (!nvRef.current || !fileUrl) return;

      setIsLoading(true);
      setError(null);
      setVolumeLoaded(false);

      try {
        // Clear existing volumes
        await nvRef.current.loadVolumes([]);

        // Load the main volume
        const volumeList = [{
          url: fileUrl,
          colormap: colormap,
          opacity: 1,
          visible: true,
        }];

        await nvRef.current.loadVolumes(volumeList);
        setVolumeLoaded(true);

        // Set initial slice using moveCrosshairInVox
        if (nvRef.current.volumes.length > 0) {
          const vol = nvRef.current.volumes[0];
          const dims = vol.dims;
          if (dims && dims.length >= 4) {
            // dims[3] is the number of slices in Z
            const totalSlices = dims[3];
            const initialSlice = Math.floor(totalSlices / 2);
            const nv = nvRef.current as NiivueExtended;
            // Move crosshair to center of volume at initial slice
            nv.moveCrosshairInVox(dims[1] / 2, dims[2] / 2, initialSlice);
          }
        }

        setIsLoading(false);
      } catch (err) {
        console.error('Failed to load NIfTI volume:', err);
        setError(err instanceof Error ? err.message : 'Failed to load volume');
        setIsLoading(false);
      }
    };

    loadVolume();
  }, [fileUrl, colormap]);

  // Load segmentation overlay when available
  useEffect(() => {
    const loadSegmentation = async () => {
      if (!nvRef.current || !volumeLoaded || !segmentationUrl || !showOverlay) return;

      try {
        // Remove existing overlays (keep first volume which is the main image)
        while (nvRef.current.volumes.length > 1) {
          nvRef.current.removeVolume(nvRef.current.volumes[1]);
        }

        // Add segmentation as overlay
        const segVolume = await NVImage.loadFromUrl({
          url: segmentationUrl,
          colormap: 'red', // Segmentation color
          opacity: 0.5,
        });

        nvRef.current.addVolume(segVolume);
      } catch (err) {
        console.error('Failed to load segmentation overlay:', err);
      }
    };

    loadSegmentation();
  }, [segmentationUrl, volumeLoaded, showOverlay]);

  // Update zoom level
  useEffect(() => {
    if (!nvRef.current || !volumeLoaded) return;
    // NiiVue uses setScale for zoom
    nvRef.current.setScale(zoomLevel);
  }, [zoomLevel, volumeLoaded]);

  // Sync slice index from store
  useEffect(() => {
    if (!nvRef.current || !volumeLoaded || nvRef.current.volumes.length === 0) return;

    const vol = nvRef.current.volumes[0];
    const dims = vol.dims;
    if (!dims || dims.length < 4) return;

    const nv = nvRef.current as NiivueExtended;
    // Move crosshair to center of XY at the requested Z slice
    nv.moveCrosshairInVox(dims[1] / 2, dims[2] / 2, currentSliceIndex);
  }, [currentSliceIndex, volumeLoaded]);

  // Handle painting in segmentation mode
  const handleCanvasMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!segmentationMode || !onPaintStroke || !nvRef.current) return;

    setIsPainting(true);

    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Convert canvas coordinates to voxel coordinates
    // NiiVue provides canvasPos2frac for this
    const frac = nvRef.current.canvasPos2frac([x, y]);
    if (frac && nvRef.current.volumes.length > 0) {
      const vol = nvRef.current.volumes[0];
      const dims = vol.dims;
      if (dims && dims.length >= 4) {
        const voxelX = Math.round(frac[0] * dims[1]);
        const voxelY = Math.round(frac[1] * dims[2]);

        onPaintStroke({
          slice_index: currentSliceIndex,
          label_id: selectedLabelId,
          x: voxelX,
          y: voxelY,
          brush_size: brushSize,
          erase: eraseMode,
        });
      }
    }
  }, [segmentationMode, onPaintStroke, currentSliceIndex, selectedLabelId, brushSize, eraseMode]);

  const handleCanvasMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!segmentationMode || !isPainting || !onPaintStroke || !nvRef.current) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const frac = nvRef.current.canvasPos2frac([x, y]);
    if (frac && nvRef.current.volumes.length > 0) {
      const vol = nvRef.current.volumes[0];
      const dims = vol.dims;
      if (dims && dims.length >= 4) {
        const voxelX = Math.round(frac[0] * dims[1]);
        const voxelY = Math.round(frac[1] * dims[2]);

        onPaintStroke({
          slice_index: currentSliceIndex,
          label_id: selectedLabelId,
          x: voxelX,
          y: voxelY,
          brush_size: brushSize,
          erase: eraseMode,
        });
      }
    }
  }, [segmentationMode, isPainting, onPaintStroke, currentSliceIndex, selectedLabelId, brushSize, eraseMode]);

  const handleCanvasMouseUp = useCallback(() => {
    setIsPainting(false);
  }, []);

  const handleCanvasMouseLeave = useCallback(() => {
    setIsPainting(false);
  }, []);

  // Handle scroll for slice navigation
  const handleWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();

    if (!nvRef.current || nvRef.current.volumes.length === 0) return;

    const vol = nvRef.current.volumes[0];
    const dims = vol.dims;
    if (!dims || dims.length < 4) return;

    const totalSlices = dims[3];
    const delta = e.deltaY > 0 ? 1 : -1;
    const newSlice = Math.max(0, Math.min(totalSlices - 1, currentSliceIndex + delta));

    if (newSlice !== currentSliceIndex) {
      setCurrentSliceIndex(newSlice);
      onSliceChange?.(newSlice);
    }
  }, [currentSliceIndex, setCurrentSliceIndex, onSliceChange]);

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full bg-black"
    >
      <canvas
        ref={canvasRef}
        className="w-full h-full"
        style={{
          cursor: segmentationMode ? 'crosshair' : 'default',
        }}
        onMouseDown={handleCanvasMouseDown}
        onMouseMove={handleCanvasMouseMove}
        onMouseUp={handleCanvasMouseUp}
        onMouseLeave={handleCanvasMouseLeave}
        onWheel={handleWheel}
      />

      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/50">
          <div className="flex flex-col items-center gap-2">
            <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-white text-sm">Cargando NIfTI...</span>
          </div>
        </div>
      )}

      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/80">
          <div className="text-red-500 text-center p-4">
            <p className="font-bold">Error al cargar el archivo</p>
            <p className="text-sm mt-2">{error}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export const NiiVueViewer = memo(NiiVueViewerComponent);
