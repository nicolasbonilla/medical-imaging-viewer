/**
 * SegmentationCanvasLocal - ITK-SNAP Style Local-First Segmentation Canvas
 *
 * KEY DIFFERENCES FROM OLD SegmentationCanvas:
 * - Renders from LOCAL MEMORY (instant, no network)
 * - Paint strokes modify local array directly
 * - No API calls during painting
 * - Slice navigation is instant (just reads different slice from array)
 *
 * This component should be used with useSegmentationMask hook.
 *
 * @module components/SegmentationCanvasLocal
 */

import React, { useRef, useEffect, useState, useCallback, forwardRef, useImperativeHandle } from 'react';
import { useTranslation } from 'react-i18next';
import type { UseSegmentationMaskReturn } from '@/hooks/useSegmentationMask';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type { ClickPoint3D, ExpertMaskData } from '@/types';

/** Methods exposed via ref for external control */
export interface SegmentationCanvasLocalRef {
  /** Force re-render the overlay */
  refresh: () => void;
}

interface SegmentationCanvasLocalProps {
  /** Segmentation mask hook return */
  segmentationMask: UseSegmentationMaskReturn;
  /** Current slice index */
  sliceIndex: number;
  /** Image dimensions */
  imageWidth: number;
  imageHeight: number;
  /** Container ref for size calculation */
  containerRef: React.RefObject<HTMLDivElement>;
  /** Callback when paint stroke is applied */
  onPaintStroke: (stroke: { x: number; y: number; label_id: number; brush_size: number; erase: boolean }) => void;
  /** Selected label ID for painting */
  selectedLabelId: number;
  /** Brush size in voxels */
  brushSize: number;
  /** Whether to erase */
  eraseMode: boolean;
  /** Whether overlay is visible */
  showOverlay: boolean;
  /** Whether painting is enabled */
  enabled: boolean;
  /** Base64 MRI image (for base layer) */
  baseImageData: string;
  /** Zoom level */
  zoomLevel: number;
  /** Pan offset */
  panOffset: { x: number; y: number };
  /** Whether to show base image */
  showBaseImage?: boolean;
  /** Rendered image size for matplotlib mode */
  renderedImageSize?: { width: number; height: number } | null;
  /** Bounding box for matplotlib mode */
  matplotlibBbox?: { left: number; top: number; width: number; height: number } | null;
  /** AI click points to render on the canvas (for interactive AI segmentation) */
  aiClickPoints?: ClickPoint3D[];
  /** Whether AI interactive mode is active (enables click-to-add-point) */
  aiInteractiveMode?: boolean;
  /** Callback when AI click point is added */
  onAIClick?: (x: number, y: number, isPositive: boolean) => void;
  /** Render mask as heatmap (for anomaly detection probability maps) */
  heatmapMode?: boolean;
  /** Expert annotation masks for contour overlay rendering */
  expertMasks?: Map<string, ExpertMaskData>;
}

/** Parsed RGBA color for fast pixel filling */
interface ParsedColor { r: number; g: number; b: number; a: number }

/** Parse hex color + opacity into RGBA components */
function parseColor(hex: string, opacity: number): ParsedColor {
  return {
    r: parseInt(hex.slice(1, 3), 16),
    g: parseInt(hex.slice(3, 5), 16),
    b: parseInt(hex.slice(5, 7), 16),
    a: Math.round(opacity * 255),
  };
}

/**
 * Transpose a 2D mask slice from (srcH × srcW) to (srcW × srcH) layout.
 * Used to fix axis ordering mismatch between backend mask format and MRI display.
 */
function transposeSlice(src: Uint8Array, srcH: number, srcW: number): Uint8Array {
  const dst = new Uint8Array(src.length);
  for (let h = 0; h < srcH; h++) {
    for (let w = 0; w < srcW; w++) {
      dst[w * srcH + h] = src[h * srcW + w];
    }
  }
  return dst;
}

/**
 * Render mask slice to canvas with per-label colors.
 * Each non-zero voxel is colored according to its label ID.
 */
function renderMaskToCanvas(
  ctx: CanvasRenderingContext2D,
  maskSlice: Uint8Array | null,
  width: number,
  height: number,
  canvasWidth: number,
  canvasHeight: number,
  labelColors: Record<number, ParsedColor>,
  fallbackColor: ParsedColor = { r: 255, g: 0, b: 0, a: 128 },
): void {
  if (!maskSlice) return;

  // Create ImageData for the mask
  const imageData = ctx.createImageData(width, height);
  const data = imageData.data;

  // Fill ImageData from mask — each voxel gets its label's color
  for (let i = 0; i < maskSlice.length; i++) {
    const labelId = maskSlice[i];
    const pixelIndex = i * 4;
    if (labelId > 0) {
      const c = labelColors[labelId] || fallbackColor;
      data[pixelIndex] = c.r;
      data[pixelIndex + 1] = c.g;
      data[pixelIndex + 2] = c.b;
      data[pixelIndex + 3] = c.a;
    }
    // else: all zeros (transparent) — default for new ImageData
  }

  // Create temporary canvas at mask resolution
  const tempCanvas = document.createElement('canvas');
  tempCanvas.width = width;
  tempCanvas.height = height;
  const tempCtx = tempCanvas.getContext('2d');
  if (!tempCtx) return;

  tempCtx.putImageData(imageData, 0, 0);

  // Disable smoothing so each voxel renders as a crisp square
  ctx.imageSmoothingEnabled = false;

  // Draw scaled to canvas
  ctx.drawImage(tempCanvas, 0, 0, canvasWidth, canvasHeight);
}

/**
 * Render heatmap (anomaly probability) to canvas.
 * Values 0-255 are mapped to a hot colormap (black→red→yellow→white)
 * with opacity proportional to confidence.
 */
function renderHeatmapToCanvas(
  ctx: CanvasRenderingContext2D,
  maskSlice: Uint8Array | null,
  width: number,
  height: number,
  canvasWidth: number,
  canvasHeight: number,
): void {
  if (!maskSlice) return;

  const imageData = ctx.createImageData(width, height);
  const data = imageData.data;

  for (let i = 0; i < maskSlice.length; i++) {
    const val = maskSlice[i]; // 0-255 confidence
    if (val === 0) continue;

    const pixelIndex = i * 4;
    const t = val / 255.0;

    // Hot colormap: black → red → yellow → white
    let r: number, g: number, b: number;
    if (t < 0.33) {
      const s = t / 0.33;
      r = Math.round(s * 255);
      g = 0;
      b = 0;
    } else if (t < 0.66) {
      const s = (t - 0.33) / 0.33;
      r = 255;
      g = Math.round(s * 255);
      b = 0;
    } else {
      const s = (t - 0.66) / 0.34;
      r = 255;
      g = 255;
      b = Math.round(s * 255);
    }

    data[pixelIndex] = r;
    data[pixelIndex + 1] = g;
    data[pixelIndex + 2] = b;
    data[pixelIndex + 3] = Math.round(t * 200); // opacity scales with confidence
  }

  const tempCanvas = document.createElement('canvas');
  tempCanvas.width = width;
  tempCanvas.height = height;
  const tempCtx = tempCanvas.getContext('2d');
  if (!tempCtx) return;

  tempCtx.putImageData(imageData, 0, 0);
  ctx.imageSmoothingEnabled = true; // smooth for heatmap
  ctx.drawImage(tempCanvas, 0, 0, canvasWidth, canvasHeight);
}

/**
 * Render a binary mask as colored contour lines on canvas.
 * Edge detection: a voxel is a border if it's non-zero and any 4-neighbor is zero.
 * Used for expert annotation overlays (read-only contour display).
 */
function renderContourToCanvas(
  ctx: CanvasRenderingContext2D,
  maskSlice: Uint8Array,
  width: number,
  height: number,
  canvasWidth: number,
  canvasHeight: number,
  color: string,
  thickness: number = 2,
): void {
  const imageData = ctx.createImageData(width, height);
  const data = imageData.data;

  // Parse color
  const r = parseInt(color.slice(1, 3), 16);
  const g = parseInt(color.slice(3, 5), 16);
  const b = parseInt(color.slice(5, 7), 16);

  // Edge detection with configurable thickness
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = y * width + x;
      if (maskSlice[idx] === 0) continue;

      // Check if this voxel is near a border (within thickness distance)
      let isBorder = false;
      for (let dy = -thickness; dy <= thickness && !isBorder; dy++) {
        for (let dx = -thickness; dx <= thickness && !isBorder; dx++) {
          if (dx === 0 && dy === 0) continue;
          const ny = y + dy;
          const nx = x + dx;
          if (ny < 0 || ny >= height || nx < 0 || nx >= width) {
            isBorder = true; // Edge of image counts as border
          } else if (maskSlice[ny * width + nx] === 0) {
            isBorder = true;
          }
        }
      }

      if (isBorder) {
        const pixelIndex = idx * 4;
        data[pixelIndex] = r;
        data[pixelIndex + 1] = g;
        data[pixelIndex + 2] = b;
        data[pixelIndex + 3] = 220; // High opacity for contours
      }
    }
  }

  const tempCanvas = document.createElement('canvas');
  tempCanvas.width = width;
  tempCanvas.height = height;
  const tempCtx = tempCanvas.getContext('2d');
  if (!tempCtx) return;

  tempCtx.putImageData(imageData, 0, 0);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(tempCanvas, 0, 0, canvasWidth, canvasHeight);
}

export const SegmentationCanvasLocal = forwardRef<SegmentationCanvasLocalRef, SegmentationCanvasLocalProps>(({
  segmentationMask,
  sliceIndex,
  imageWidth,
  imageHeight,
  containerRef,
  onPaintStroke,
  selectedLabelId,
  brushSize,
  eraseMode,
  showOverlay,
  enabled,
  baseImageData,
  zoomLevel,
  panOffset,
  showBaseImage = true,
  renderedImageSize = null,
  matplotlibBbox = null,
  aiClickPoints = [],
  aiInteractiveMode = false,
  onAIClick,
  heatmapMode = false,
  expertMasks,
}, ref) => {
  const { t } = useTranslation();

  // Canvas refs
  const baseCanvasRef = useRef<HTMLCanvasElement>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
  const baseImageRef = useRef<HTMLImageElement | null>(null);

  // Read draw-over, brush shape, and label colors from Zustand (single source of truth)
  const drawOverMode = useSegmentationStore((s) => s.drawOverMode);
  const brushShape = useSegmentationStore((s) => s.paintTool.brushShape);
  const storeLabels = useSegmentationStore((s) => s.activeSegmentation?.labels);

  // Zone map background overlay
  const zoneMapMask = useSegmentationStore((s) => s.zoneMapMask);
  const zoneMapDims = useSegmentationStore((s) => s.zoneMapDims);
  const zoneMapVisible = useSegmentationStore((s) => s.zoneMapVisible);

  // State
  const [isPainting, setIsPainting] = useState(false);
  const [cursorPosition, setCursorPosition] = useState<{ x: number; y: number } | null>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });
  const [renderVersion, setRenderVersion] = useState(0);

  // Expose refresh method
  useImperativeHandle(ref, () => ({
    refresh: () => setRenderVersion(prev => prev + 1),
  }), []);

  // Calculate canvas size
  useEffect(() => {
    if (!containerRef.current) return;

    const calculateSize = () => {
      const container = containerRef.current;
      if (!container) return;

      // In matplotlib mode with bbox, use the bbox dimensions
      if (matplotlibBbox) {
        setCanvasSize({
          width: Math.floor(matplotlibBbox.width),
          height: Math.floor(matplotlibBbox.height)
        });
        return;
      }

      // In matplotlib mode without bbox, use full image size
      if (renderedImageSize) {
        setCanvasSize({
          width: Math.floor(renderedImageSize.width),
          height: Math.floor(renderedImageSize.height)
        });
        return;
      }

      // Calculate based on container (standard mode)
      const containerWidth = container.clientWidth;
      const containerHeight = container.clientHeight;
      const imageAspect = imageWidth / imageHeight;
      const containerAspect = containerWidth / containerHeight;

      let renderWidth, renderHeight;
      if (imageAspect > containerAspect) {
        renderWidth = containerWidth * 0.9;
        renderHeight = renderWidth / imageAspect;
      } else {
        renderHeight = containerHeight * 0.9;
        renderWidth = renderHeight * imageAspect;
      }

      setCanvasSize({ width: Math.floor(renderWidth), height: Math.floor(renderHeight) });
    };

    calculateSize();
    window.addEventListener('resize', calculateSize);
    return () => window.removeEventListener('resize', calculateSize);
  }, [containerRef, imageWidth, imageHeight, renderedImageSize, matplotlibBbox]);

  // Load base image
  useEffect(() => {
    if (!baseImageData || !showBaseImage) return;

    const img = new Image();
    img.onload = () => {
      baseImageRef.current = img;
      renderBaseLayer();
    };
    img.src = baseImageData;

    return () => {
      img.onload = null;
      img.src = '';
    };
  }, [baseImageData, showBaseImage]);

  // Render base layer
  const renderBaseLayer = useCallback(() => {
    const canvas = baseCanvasRef.current;
    const img = baseImageRef.current;
    if (!canvas || !img || canvasSize.width === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvasSize.width, canvasSize.height);

    if (!matplotlibBbox) {
      // Standard mode: Apply transformations
      ctx.save();
      const centerX = canvasSize.width / 2;
      const centerY = canvasSize.height / 2;
      ctx.translate(centerX + panOffset.x, centerY + panOffset.y);
      ctx.scale(zoomLevel, zoomLevel);
      ctx.translate(-centerX, -centerY);
      ctx.drawImage(img, 0, 0, canvasSize.width, canvasSize.height);
      ctx.restore();
    } else {
      // Matplotlib mode: No transformations
      ctx.drawImage(img, 0, 0, canvasSize.width, canvasSize.height);
    }
  }, [canvasSize, zoomLevel, panOffset, matplotlibBbox]);

  // Re-render base when params change
  useEffect(() => {
    if (showBaseImage && baseImageRef.current) {
      renderBaseLayer();
    }
  }, [canvasSize, showBaseImage, renderBaseLayer, zoomLevel, panOffset]);

  // Render overlay layer (mask + cursor)
  const renderOverlayLayer = useCallback(() => {
    const canvas = overlayCanvasRef.current;
    if (!canvas || canvasSize.width === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear overlay
    ctx.clearRect(0, 0, canvasSize.width, canvasSize.height);

    const isMatplotlibMode = !!matplotlibBbox;

    if (!isMatplotlibMode) {
      // Standard mode: Apply transformations
      ctx.save();
      const centerX = canvasSize.width / 2;
      const centerY = canvasSize.height / 2;
      ctx.translate(centerX + panOffset.x, centerY + panOffset.y);
      ctx.scale(zoomLevel, zoomLevel);
      ctx.translate(-centerX, -centerY);
    }

    // Draw MAGNIMS zone map as semi-transparent background (before lesion mask)
    if (zoneMapVisible && zoneMapMask && zoneMapDims) {
      const zmSliceSize = zoneMapDims.width * zoneMapDims.height;
      const zmSliceOffset = sliceIndex * zmSliceSize;
      if (zmSliceOffset + zmSliceSize <= zoneMapMask.length) {
        let zmSlice: Uint8Array = zoneMapMask.subarray(zmSliceOffset, zmSliceOffset + zmSliceSize);
        let zmRenderW = zoneMapDims.width;
        let zmRenderH = zoneMapDims.height;

        // Auto-fix axis mismatch: if zone map dims are swapped relative to MRI,
        // transpose the slice so it aligns with the displayed image.
        if (zmRenderW !== imageWidth && zmRenderH === imageWidth && zmRenderW === imageHeight) {
          zmSlice = transposeSlice(zmSlice, zoneMapDims.height, zoneMapDims.width);
          zmRenderW = imageWidth;
          zmRenderH = imageHeight;
        }

        // Use MAGNIMS colors at low opacity for background visualization
        // Alpha is in 0-255 range (ImageData format): 40 ≈ 16% opacity
        const zoneColors: Record<number, ParsedColor> = {
          1: { r: 255, g: 0, b: 0, a: 40 },      // PV - red
          2: { r: 0, g: 204, b: 0, a: 40 },       // JC - green
          3: { r: 0, g: 102, b: 255, a: 40 },     // IT - blue
          4: { r: 255, g: 215, b: 0, a: 40 },     // DWM - yellow
        };
        renderMaskToCanvas(
          ctx, zmSlice,
          zmRenderW, zmRenderH,
          canvasSize.width, canvasSize.height,
          zoneColors,
        );
      }
    }

    // Draw mask from LOCAL MEMORY (instant!)
    if (showOverlay && segmentationMask.isLoaded) {
      const maskSlice = segmentationMask.getSliceMask(sliceIndex);
      if (maskSlice) {
        // Auto-fix axis mismatch: if mask dims are swapped relative to MRI display,
        // transpose the slice on the fly. This handles backend-generated masks
        // (zone maps, AI results) that were stored with (k,j,i) instead of (k,i,j).
        let renderSlice = maskSlice;
        const maskDims = segmentationMask.state.dimensions;
        const needsTranspose = maskDims
          && maskDims.width !== imageWidth
          && maskDims.height === imageWidth
          && maskDims.width === imageHeight;
        if (needsTranspose && maskDims) {
          renderSlice = transposeSlice(maskSlice, maskDims.height, maskDims.width);
        }

        if (heatmapMode) {
          // Heatmap mode: values = confidence (0-255), rendered as hot colormap
          renderHeatmapToCanvas(
            ctx,
            renderSlice,
            imageWidth,
            imageHeight,
            canvasSize.width,
            canvasSize.height,
          );
        } else {
          // Label mode: each voxel colored by label ID
          const labelColors: Record<number, ParsedColor> = {};
          if (storeLabels) {
            for (const label of storeLabels) {
              if (label.id !== 0) {
                labelColors[label.id] = parseColor(label.color, label.opacity);
              }
            }
          }

          renderMaskToCanvas(
            ctx,
            renderSlice,
            imageWidth,
            imageHeight,
            canvasSize.width,
            canvasSize.height,
            labelColors,
          );
        }
      }
    }

    // Draw AI click points (markers on current slice)
    if (aiClickPoints && aiClickPoints.length > 0) {
      const pixelsPerVoxelX = canvasSize.width / imageWidth;
      const pixelsPerVoxelY = canvasSize.height / imageHeight;
      for (const pt of aiClickPoints) {
        if (pt.z !== sliceIndex) continue; // Only show points on current slice
        const px = (pt.x + 0.5) * pixelsPerVoxelX;
        const py = (pt.y + 0.5) * pixelsPerVoxelY;
        const isPositive = pt.label === 'positive';

        // Outer circle
        ctx.beginPath();
        ctx.arc(px, py, 8, 0, Math.PI * 2);
        ctx.fillStyle = isPositive ? 'rgba(34, 197, 94, 0.7)' : 'rgba(239, 68, 68, 0.7)';
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();

        // Cross mark
        ctx.beginPath();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        if (isPositive) {
          // Plus sign
          ctx.moveTo(px - 4, py); ctx.lineTo(px + 4, py);
          ctx.moveTo(px, py - 4); ctx.lineTo(px, py + 4);
        } else {
          // Minus sign
          ctx.moveTo(px - 4, py); ctx.lineTo(px + 4, py);
        }
        ctx.stroke();
      }
    }

    // Draw expert annotation masks as contours
    if (expertMasks && expertMasks.size > 0) {
      for (const [, maskData] of expertMasks) {
        if (!maskData.visible || !maskData.mask || maskData.loading) continue;

        // Extract the current slice from the expert mask
        const sliceSize = maskData.width * maskData.height;
        const sliceOffset = sliceIndex * sliceSize;
        if (sliceOffset + sliceSize > maskData.mask.length) continue;

        const expertSlice = maskData.mask.subarray(sliceOffset, sliceOffset + sliceSize);

        // Check if this slice has any non-zero voxels
        let hasData = false;
        for (let i = 0; i < expertSlice.length; i++) {
          if (expertSlice[i] > 0) { hasData = true; break; }
        }
        if (!hasData) continue;

        renderContourToCanvas(
          ctx,
          expertSlice,
          maskData.width,
          maskData.height,
          canvasSize.width,
          canvasSize.height,
          maskData.color,
          2, // thickness
        );
      }
    }

    // Draw cursor
    if (cursorPosition && enabled) {
      const canvasX = (cursorPosition.x / imageWidth) * canvasSize.width;
      const canvasY = (cursorPosition.y / imageHeight) * canvasSize.height;

      const pixelsPerVoxelX = canvasSize.width / imageWidth;
      const pixelsPerVoxelY = canvasSize.height / imageHeight;

      ctx.strokeStyle = eraseMode ? '#ff0000' : '#00ff00';
      ctx.lineWidth = 2;

      if (brushShape === 'circle') {
        const radiusX = (brushSize / 2) * pixelsPerVoxelX;
        const radiusY = (brushSize / 2) * pixelsPerVoxelY;
        ctx.beginPath();
        ctx.ellipse(canvasX, canvasY, radiusX, radiusY, 0, 0, Math.PI * 2);
        ctx.stroke();
      } else {
        const halfSize = Math.floor(brushSize / 2);
        const x1 = canvasX - halfSize * pixelsPerVoxelX;
        const y1 = canvasY - halfSize * pixelsPerVoxelY;
        ctx.strokeRect(x1, y1, brushSize * pixelsPerVoxelX, brushSize * pixelsPerVoxelY);
      }
    }

    if (!isMatplotlibMode) {
      ctx.restore();
    }
  }, [
    canvasSize, imageWidth, imageHeight, cursorPosition, enabled,
    brushSize, brushShape, eraseMode, showOverlay, zoomLevel, panOffset,
    matplotlibBbox, segmentationMask, sliceIndex, renderVersion, storeLabels,
    aiClickPoints, heatmapMode, expertMasks,
    zoneMapMask, zoneMapDims, zoneMapVisible,
  ]);

  // Re-render overlay when mask or slice changes
  useEffect(() => {
    renderOverlayLayer();
  }, [renderOverlayLayer, sliceIndex, segmentationMask.state.isDirty]);

  // Get mouse position in image coordinates
  // Must apply inverse of the canvas zoom/pan transform used in renderOverlayLayer
  const getMousePos = useCallback(
    (e: React.MouseEvent<HTMLDivElement>): { x: number; y: number } => {
      const canvas = overlayCanvasRef.current;
      if (!canvas) return { x: 0, y: 0 };

      const rect = canvas.getBoundingClientRect();
      let canvasX = e.clientX - rect.left;
      let canvasY = e.clientY - rect.top;

      // In standard mode, inverse-transform to account for zoom/pan applied in the canvas context
      // Forward transform: translate(center+pan) → scale(zoom) → translate(-center)
      // Inverse: P_image = (P_screen - center - pan) / zoom + center
      if (!matplotlibBbox) {
        const centerX = canvasSize.width / 2;
        const centerY = canvasSize.height / 2;
        canvasX = (canvasX - centerX - panOffset.x) / zoomLevel + centerX;
        canvasY = (canvasY - centerY - panOffset.y) / zoomLevel + centerY;
      }

      const imageX = Math.floor((canvasX / canvasSize.width) * imageWidth);
      const imageY = Math.floor((canvasY / canvasSize.height) * imageHeight);

      const clampedX = Math.max(0, Math.min(imageWidth - 1, imageX));
      const clampedY = Math.max(0, Math.min(imageHeight - 1, imageY));

      return { x: clampedX, y: clampedY };
    },
    [canvasSize, imageWidth, imageHeight, matplotlibBbox, zoomLevel, panOffset]
  );

  // Apply paint stroke (LOCAL - instant!)
  const applyPaintStroke = useCallback((pos: { x: number; y: number }) => {
    segmentationMask.paintStroke({
      x: pos.x,
      y: pos.y,
      sliceIndex,
      brushSize,
      labelId: selectedLabelId,
      erase: eraseMode,
      drawOverMode,
      drawOverLabel: selectedLabelId,
    });

    renderOverlayLayer();

    onPaintStroke({
      x: pos.x,
      y: pos.y,
      label_id: selectedLabelId,
      brush_size: brushSize,
      erase: eraseMode,
    });
  }, [segmentationMask, sliceIndex, brushSize, selectedLabelId, eraseMode, drawOverMode, onPaintStroke, renderOverlayLayer]);

  // Mouse handlers — beginStroke/endStroke bracket each drag for undo
  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!enabled) return;

    // AI interactive mode: add click points instead of painting
    if (aiInteractiveMode && onAIClick) {
      const pos = getMousePos(e);
      const isPositive = e.button === 0; // Left = positive, right = negative
      onAIClick(pos.x, pos.y, isPositive);
      return;
    }

    segmentationMask.beginStroke(sliceIndex);
    setIsPainting(true);
    const pos = getMousePos(e);
    applyPaintStroke(pos);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const pos = getMousePos(e);
    setCursorPosition(pos);

    if (!enabled || !isPainting) return;
    applyPaintStroke(pos);
  };

  const handleMouseUp = () => {
    if (isPainting) segmentationMask.endStroke();
    setIsPainting(false);
  };

  const handleMouseLeave = () => {
    if (isPainting) segmentationMask.endStroke();
    setIsPainting(false);
    setCursorPosition(null);
  };

  if (canvasSize.width === 0) {
    return <div className="text-white">{t('segmentation.loadingCanvas', 'Loading canvas...')}</div>;
  }

  // Position style
  const positionStyle = matplotlibBbox ? {
    position: 'absolute' as const,
    left: matplotlibBbox.left,
    top: matplotlibBbox.top,
    width: canvasSize.width,
    height: canvasSize.height,
    pointerEvents: enabled ? 'auto' as const : 'none' as const
  } : {
    position: 'absolute' as const,
    top: 0,
    left: 0,
    width: canvasSize.width,
    height: canvasSize.height,
    pointerEvents: enabled ? 'auto' as const : 'none' as const
  };

  return (
    <div
      className="relative"
      style={positionStyle}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseLeave}
      onContextMenu={aiInteractiveMode ? (e) => e.preventDefault() : undefined}
    >
      {/* Base layer: MRI image */}
      {showBaseImage && (
        <canvas
          ref={baseCanvasRef}
          width={canvasSize.width}
          height={canvasSize.height}
          className="absolute top-0 left-0"
          style={{ pointerEvents: 'none' }}
        />
      )}

      {/* Overlay layer: Mask + Cursor */}
      <canvas
        ref={overlayCanvasRef}
        width={canvasSize.width}
        height={canvasSize.height}
        className="absolute top-0 left-0"
        style={{ pointerEvents: 'none' }}
      />

      {/* Loading indicator */}
      {segmentationMask.state.isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50">
          <div className="text-white">{t('segmentation.loadingMask', 'Loading mask...')}</div>
        </div>
      )}
    </div>
  );
});

SegmentationCanvasLocal.displayName = 'SegmentationCanvasLocal';

export default SegmentationCanvasLocal;
