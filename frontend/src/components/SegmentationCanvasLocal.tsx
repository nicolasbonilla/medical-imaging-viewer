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
import type { ClickPoint3D } from '@/types';

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

/** MAGNIMS zone colors at lesion opacity (60%) for zone-colorized rendering */
const MAGNIMS_ZONE_COLORS_LESION: Record<number, ParsedColor> = {
  1: { r: 255, g: 0,   b: 0,   a: 153 },  // PV - red
  2: { r: 0,   g: 204, b: 0,   a: 153 },  // JC - green
  3: { r: 0,   g: 102, b: 255, a: 153 },  // IT - blue
  4: { r: 255, g: 215, b: 0,   a: 153 },  // DWM - yellow
};

/**
 * Create a composite slice for MAGNIMS zone colorization.
 *
 * If the lesion mask already has MAGNIMS labels (1-4) from classification,
 * use those directly (coherent with per-lesion classification results).
 * Otherwise, fall back to zone map per-voxel colorization (visual reference only).
 */
function createZoneColorizedSlice(
  lesionSlice: Uint8Array,
  zoneSlice: Uint8Array,
  length: number,
): Uint8Array {
  const composite = new Uint8Array(length);

  // Check if mask already has MAGNIMS classification labels (1-4)
  let hasClassifiedLabels = false;
  for (let i = 0; i < length; i++) {
    if (lesionSlice[i] >= 1 && lesionSlice[i] <= 4) {
      hasClassifiedLabels = true;
      break;
    }
  }

  if (hasClassifiedLabels) {
    // Classified mask: use each lesion's own MAGNIMS label (coherent with table)
    for (let i = 0; i < length; i++) {
      if (lesionSlice[i] >= 1 && lesionSlice[i] <= 4) {
        composite[i] = lesionSlice[i];
      }
    }
  } else {
    // Unclassified mask: use zone map as visual reference (per-voxel)
    for (let i = 0; i < length; i++) {
      if (lesionSlice[i] > 0 && zoneSlice[i] > 0) {
        composite[i] = zoneSlice[i];
      }
    }
  }
  return composite;
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
      const c = labelColors[labelId];
      if (c) {
        data[pixelIndex] = c.r;
        data[pixelIndex + 1] = c.g;
        data[pixelIndex + 2] = c.b;
        data[pixelIndex + 3] = c.a;
      }
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
  const labelVisibility = useSegmentationStore((s) => s.labelVisibility);

  // Paint mode: controls whether painting is allowed (view-only vs edit mode)
  const isPaintMode = useSegmentationStore((s) => s.isPaintMode);

  // Zone map background overlay
  const zoneMapMask = useSegmentationStore((s) => s.zoneMapMask);
  const zoneMapDims = useSegmentationStore((s) => s.zoneMapDims);
  const zoneMapVisible = useSegmentationStore((s) => s.zoneMapVisible);
  const zoneColorizeEnabled = useSegmentationStore((s) => s.zoneColorizeEnabled);

  // Opacity controls
  const lesionOpacity = useSegmentationStore((s) => s.lesionOpacity);
  const zoneMapOpacity = useSegmentationStore((s) => s.zoneMapOpacity);

  // Selected lesion for bounding box + centroid rendering
  const selectedLesion = useSegmentationStore((s) => s.selectedLesion);

  // Longitudinal overlay (dual mask comparison)
  const longTp1Mask = useSegmentationStore((s) => s.longitudinalTp1Mask);
  const longTp1Dims = useSegmentationStore((s) => s.longitudinalTp1Dims);
  const longTp2Mask = useSegmentationStore((s) => s.longitudinalTp2Mask);
  const longTp2Dims = useSegmentationStore((s) => s.longitudinalTp2Dims);
  const longVisible = useSegmentationStore((s) => s.longitudinalVisible);

  // State
  const [isPainting, setIsPainting] = useState(false);
  const [cursorPosition, setCursorPosition] = useState<{ x: number; y: number } | null>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });
  const [renderVersion, setRenderVersion] = useState(0);

  // Expose refresh method
  useImperativeHandle(ref, () => ({
    refresh: () => setRenderVersion(prev => prev + 1),
  }), []);

  // Calculate canvas size — uses ResizeObserver to stay in sync with container changes
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
      if (containerWidth === 0 || containerHeight === 0) return;

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

    // ResizeObserver detects container size changes (sidebar toggle, panel resize, etc.)
    // that window 'resize' event does NOT catch.
    const observer = new ResizeObserver(calculateSize);
    observer.observe(containerRef.current);
    window.addEventListener('resize', calculateSize);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', calculateSize);
    };
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

  // In matplotlib mode, CSS transform: scale(zoom) on the parent stretches the canvas
  // bitmap, making strokes blurry. Compensate by rendering at higher resolution.
  // Cap at 4x to avoid excessive memory usage.
  const bufferScale = matplotlibBbox ? Math.min(Math.max(1, Math.ceil(zoomLevel)), 4) : 1;

  // Render base layer
  const renderBaseLayer = useCallback(() => {
    const canvas = baseCanvasRef.current;
    const img = baseImageRef.current;
    if (!canvas || !img || canvasSize.width === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

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
      // Matplotlib mode: scale context to match higher-res buffer
      ctx.save();
      ctx.scale(bufferScale, bufferScale);
      ctx.drawImage(img, 0, 0, canvasSize.width, canvasSize.height);
      ctx.restore();
    }
  }, [canvasSize, zoomLevel, panOffset, matplotlibBbox, bufferScale]);

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

    // Clear overlay (use buffer dimensions, not display dimensions)
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const isMatplotlibMode = !!matplotlibBbox;

    if (!isMatplotlibMode) {
      // Standard mode: Apply transformations
      ctx.save();
      const centerX = canvasSize.width / 2;
      const centerY = canvasSize.height / 2;
      ctx.translate(centerX + panOffset.x, centerY + panOffset.y);
      ctx.scale(zoomLevel, zoomLevel);
      ctx.translate(-centerX, -centerY);
    } else if (bufferScale > 1) {
      // Matplotlib mode: scale context to match higher-res buffer for crisp strokes
      ctx.save();
      ctx.scale(bufferScale, bufferScale);
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

        // Use MAGNIMS colors with user-controlled opacity for background visualization
        const zmAlpha = Math.round(zoneMapOpacity * 255);
        const zoneColors: Record<number, ParsedColor> = {
          1: { r: 255, g: 0, b: 0, a: zmAlpha },      // PV - red
          2: { r: 0, g: 204, b: 0, a: zmAlpha },       // JC - green
          3: { r: 0, g: 102, b: 255, a: zmAlpha },     // IT - blue
          4: { r: 255, g: 215, b: 0, a: zmAlpha },     // DWM - yellow
        };
        renderMaskToCanvas(
          ctx, zmSlice,
          zmRenderW, zmRenderH,
          canvasSize.width, canvasSize.height,
          zoneColors,
        );
      }
    }

    // Draw longitudinal overlay (TP1=blue, TP2=red, overlap=green)
    if (longVisible && longTp1Mask && longTp1Dims && longTp2Mask && longTp2Dims) {
      const tp1SliceSize = longTp1Dims.width * longTp1Dims.height;
      const tp1Offset = sliceIndex * tp1SliceSize;
      const tp2SliceSize = longTp2Dims.width * longTp2Dims.height;
      const tp2Offset = sliceIndex * tp2SliceSize;

      if (tp1Offset + tp1SliceSize <= longTp1Mask.length &&
          tp2Offset + tp2SliceSize <= longTp2Mask.length) {
        let tp1Slice = longTp1Mask.subarray(tp1Offset, tp1Offset + tp1SliceSize);
        let tp2Slice = longTp2Mask.subarray(tp2Offset, tp2Offset + tp2SliceSize);
        let w1 = longTp1Dims.width, h1 = longTp1Dims.height;
        let w2 = longTp2Dims.width, h2 = longTp2Dims.height;

        // Auto-fix axis mismatch
        if (w1 !== imageWidth && h1 === imageWidth && w1 === imageHeight) {
          tp1Slice = transposeSlice(tp1Slice, h1, w1);
          w1 = imageWidth; h1 = imageHeight;
        }
        if (w2 !== imageWidth && h2 === imageWidth && w2 === imageHeight) {
          tp2Slice = transposeSlice(tp2Slice, h2, w2);
          w2 = imageWidth; h2 = imageHeight;
        }

        const longImgData = ctx.createImageData(imageWidth, imageHeight);
        const ld = longImgData.data;
        const opacity = Math.round(0.55 * 255);
        for (let i = 0; i < imageWidth * imageHeight; i++) {
          const inTp1 = tp1Slice[i] > 0;
          const inTp2 = tp2Slice[i] > 0;
          const pi = i * 4;
          if (inTp1 && inTp2) {
            // Overlap (persistent) = green
            ld[pi] = 50; ld[pi+1] = 205; ld[pi+2] = 50; ld[pi+3] = opacity;
          } else if (inTp1) {
            // TP1 only (resolved) = blue
            ld[pi] = 65; ld[pi+1] = 135; ld[pi+2] = 245; ld[pi+3] = opacity;
          } else if (inTp2) {
            // TP2 only (new) = red
            ld[pi] = 245; ld[pi+1] = 70; ld[pi+2] = 70; ld[pi+3] = opacity;
          }
        }
        const tmpC = document.createElement('canvas');
        tmpC.width = imageWidth; tmpC.height = imageHeight;
        const tmpCtx = tmpC.getContext('2d');
        if (tmpCtx) {
          tmpCtx.putImageData(longImgData, 0, 0);
          ctx.imageSmoothingEnabled = false;
          ctx.drawImage(tmpC, 0, 0, canvasSize.width, canvasSize.height);
        }
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
          // Build standard label colors scaled by lesionOpacity slider
          const labelColors: Record<number, ParsedColor> = {};
          if (storeLabels) {
            for (const label of storeLabels) {
              if (label.id !== 0 && labelVisibility[label.id] !== false) {
                const c = parseColor(label.color, label.opacity);
                labelColors[label.id] = { ...c, a: Math.round(c.a * lesionOpacity) };
              }
            }
          }

          let sliceToRender = renderSlice;
          let colorsToUse: Record<number, ParsedColor> = labelColors;

          // Zone colorization: override lesion colors with MAGNIMS zone colors
          if (zoneColorizeEnabled && zoneMapMask && zoneMapDims) {
            const zmSliceSize = zoneMapDims.width * zoneMapDims.height;
            const zmSliceOffset = sliceIndex * zmSliceSize;
            if (zmSliceOffset + zmSliceSize <= zoneMapMask.length) {
              let zmSlice = zoneMapMask.subarray(zmSliceOffset, zmSliceOffset + zmSliceSize);
              let zmW = zoneMapDims.width;
              let zmH = zoneMapDims.height;
              // Auto-fix axis mismatch (same logic as zone map background)
              if (zmW !== imageWidth && zmH === imageWidth && zmW === imageHeight) {
                zmSlice = transposeSlice(zmSlice, zoneMapDims.height, zoneMapDims.width);
                zmW = imageWidth;
                zmH = imageHeight;
              }
              if (zmW === imageWidth && zmH === imageHeight && renderSlice.length === zmSlice.length) {
                sliceToRender = createZoneColorizedSlice(renderSlice, zmSlice, renderSlice.length);
                // Apply lesionOpacity to zone-colorized lesion colors
                const scaledZoneColors: Record<number, ParsedColor> = {};
                for (const [k, v] of Object.entries(MAGNIMS_ZONE_COLORS_LESION)) {
                  scaledZoneColors[Number(k)] = { ...v, a: Math.round(v.a * lesionOpacity) };
                }
                colorsToUse = scaledZoneColors;
              }
            }
          }

          renderMaskToCanvas(
            ctx,
            sliceToRender,
            imageWidth,
            imageHeight,
            canvasSize.width,
            canvasSize.height,
            colorsToUse,
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

    // Draw selected lesion bounding box + centroid
    // Backend np.argwhere returns (z, y, x) in mask's (D, H, W) space.
    // Empirically confirmed: backend y maps to display X, backend x maps to display Y.
    if (selectedLesion) {
      const bb = selectedLesion.bounding_box;
      const centroid = selectedLesion.centroid;
      const isSliceInRange = sliceIndex >= bb.z_min && sliceIndex <= bb.z_max;

      if (isSliceInRange) {
        const pixelsPerVoxelX = canvasSize.width / imageWidth;
        const pixelsPerVoxelY = canvasSize.height / imageHeight;

        // RC-031: the lesion bbox/centroid come from analyze_lesions run on the
        // SAME (D,H,W) mask that is displayed — y = height axis (i), x = width
        // axis (j) — so the correct display mapping is x→X, y→Y. But the overlay
        // slice is only transposed for display when the mask dims are swapped vs
        // the image (the `needsTranspose` condition used above). The bbox MUST
        // follow that SAME transpose or it renders mirrored across the diagonal.
        // The previous code swapped UNCONDITIONALLY (y→X, x→Y) — correct only for
        // the transposed case, wrong for every correctly-oriented mask (all
        // painted masks, square slices, and post-RC-031 tool masks).
        const md = segmentationMask.state.dimensions;
        const swap = !!(md && md.width !== imageWidth && md.height === imageWidth && md.width === imageHeight);
        const bxMin = swap ? bb.y_min : bb.x_min;
        const byMin = swap ? bb.x_min : bb.y_min;
        const bxMax = swap ? bb.y_max : bb.x_max;
        const byMax = swap ? bb.x_max : bb.y_max;
        const bx = bxMin * pixelsPerVoxelX;
        const by = byMin * pixelsPerVoxelY;
        const bw = (bxMax - bxMin + 1) * pixelsPerVoxelX;
        const bh = (byMax - byMin + 1) * pixelsPerVoxelY;

        // Dashed yellow bounding box
        ctx.save();
        ctx.strokeStyle = '#FFD700';
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 3]);
        ctx.strokeRect(bx, by, bw, bh);
        ctx.setLineDash([]);
        ctx.restore();

        // Centroid crosshair (show on centroid's z slice ± 1)
        if (Math.abs(sliceIndex - Math.round(centroid.z)) <= 1) {
          const cx = ((swap ? centroid.y : centroid.x) + 0.5) * pixelsPerVoxelX;
          const cy = ((swap ? centroid.x : centroid.y) + 0.5) * pixelsPerVoxelY;
          const armLen = 8;

          ctx.save();
          ctx.strokeStyle = '#FF4444';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(cx - armLen, cy); ctx.lineTo(cx + armLen, cy);
          ctx.moveTo(cx, cy - armLen); ctx.lineTo(cx, cy + armLen);
          ctx.stroke();

          ctx.beginPath();
          ctx.arc(cx, cy, 3, 0, Math.PI * 2);
          ctx.fillStyle = '#FF4444';
          ctx.fill();
          ctx.strokeStyle = '#FFFFFF';
          ctx.lineWidth = 1;
          ctx.stroke();
          ctx.restore();
        }
      }
    }

    // Draw cursor — only in edit mode (isPaintMode), not view-only
    if (cursorPosition && enabled && isPaintMode) {
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

    if (!isMatplotlibMode || bufferScale > 1) {
      ctx.restore();
    }
  }, [
    canvasSize, imageWidth, imageHeight, cursorPosition, enabled, isPaintMode,
    brushSize, brushShape, eraseMode, showOverlay, zoomLevel, panOffset,
    matplotlibBbox, bufferScale, segmentationMask, sliceIndex, renderVersion, storeLabels, labelVisibility,
    aiClickPoints, heatmapMode,
    zoneMapMask, zoneMapDims, zoneMapVisible, zoneColorizeEnabled,
    lesionOpacity, zoneMapOpacity, selectedLesion,
    longTp1Mask, longTp1Dims, longTp2Mask, longTp2Dims, longVisible,
  ]);

  // Re-render overlay when mask or slice changes
  useEffect(() => {
    renderOverlayLayer();
  }, [renderOverlayLayer, sliceIndex, segmentationMask.state.isDirty]);

  // Get mouse position in image coordinates.
  // Uses the canvas DOM element's actual dimensions (canvas.width/height) and
  // getBoundingClientRect() to reliably convert screen → canvas → image coords.
  // This is robust against canvasSize state being stale or CSS scaling the canvas.
  const getMousePos = useCallback(
    (e: React.MouseEvent<HTMLDivElement>): { x: number; y: number } => {
      const canvas = overlayCanvasRef.current;
      if (!canvas) return { x: 0, y: 0 };

      const rect = canvas.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return { x: 0, y: 0 };

      // Step 1: Mouse position in CSS pixels relative to the canvas element
      const cssX = e.clientX - rect.left;
      const cssY = e.clientY - rect.top;

      // Step 2: Convert CSS pixels → canvas logical pixels.
      // Handles any mismatch between CSS display size (rect) and canvas drawing buffer (canvas.width).
      // Normally these are equal, but CSS scaling could make them differ.
      const logicalW = canvas.width;
      const logicalH = canvas.height;
      let logicalX = (cssX / rect.width) * logicalW;
      let logicalY = (cssY / rect.height) * logicalH;

      // Step 3: Apply inverse zoom/pan transform.
      // Forward (in renderOverlayLayer): translate(center+pan) → scale(zoom) → translate(-center)
      //   screenPt = (canvasPt - center) * zoom + center + pan
      // Inverse:
      //   canvasPt = (screenPt - center - pan) / zoom + center
      if (!matplotlibBbox) {
        const centerX = logicalW / 2;
        const centerY = logicalH / 2;
        logicalX = (logicalX - centerX - panOffset.x) / zoomLevel + centerX;
        logicalY = (logicalY - centerY - panOffset.y) / zoomLevel + centerY;
      }

      // Step 4: Canvas logical pixels → image pixel coordinates
      const imageX = Math.floor((logicalX / logicalW) * imageWidth);
      const imageY = Math.floor((logicalY / logicalH) * imageHeight);

      return {
        x: Math.max(0, Math.min(imageWidth - 1, imageX)),
        y: Math.max(0, Math.min(imageHeight - 1, imageY)),
      };
    },
    [imageWidth, imageHeight, matplotlibBbox, zoomLevel, panOffset]
  );

  // Check if mask dimensions are transposed relative to display dimensions.
  // When true, the rendering transposes slices to align with the image,
  // so painting coordinates must also be swapped to match the mask layout.
  const maskDims = segmentationMask.state.dimensions;
  const maskDimsTransposed = (() => {
    if (!maskDims) return false;
    if (maskDims.width === imageWidth && maskDims.height === imageHeight) return false;
    if (maskDims.width === imageHeight && maskDims.height === imageWidth) return true;
    return false;
  })();

  // Apply paint stroke (LOCAL - instant!)
  const applyPaintStroke = useCallback((pos: { x: number; y: number }) => {
    // When the mask dimensions are transposed relative to the display,
    // swap x/y so the paint goes to the correct position in the mask array
    const paintX = maskDimsTransposed ? pos.y : pos.x;
    const paintY = maskDimsTransposed ? pos.x : pos.y;

    segmentationMask.paintStroke({
      x: paintX,
      y: paintY,
      sliceIndex,
      brushSize,
      labelId: selectedLabelId,
      erase: eraseMode,
      drawOverMode,
      drawOverLabel: selectedLabelId,
    });

    renderOverlayLayer();

    onPaintStroke({
      x: paintX,
      y: paintY,
      label_id: selectedLabelId,
      brush_size: brushSize,
      erase: eraseMode,
    });
  }, [segmentationMask, sliceIndex, brushSize, selectedLabelId, eraseMode, drawOverMode, onPaintStroke, renderOverlayLayer, maskDimsTransposed]);

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

  // Position style — pointerEvents only active when painting is enabled (isPaintMode).
  // In view-only mode (enabled but !isPaintMode), clicks pass through to pan/zoom handlers.
  const canInteract = enabled && isPaintMode;
  const positionStyle = matplotlibBbox ? {
    position: 'absolute' as const,
    left: matplotlibBbox.left,
    top: matplotlibBbox.top,
    width: canvasSize.width,
    height: canvasSize.height,
    pointerEvents: canInteract ? 'auto' as const : 'none' as const
  } : {
    position: 'absolute' as const,
    top: 0,
    left: 0,
    width: canvasSize.width,
    height: canvasSize.height,
    pointerEvents: canInteract ? 'auto' as const : 'none' as const
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
          width={canvasSize.width * bufferScale}
          height={canvasSize.height * bufferScale}
          className="absolute top-0 left-0"
          style={{ pointerEvents: 'none', width: canvasSize.width, height: canvasSize.height, imageRendering: 'pixelated' }}
        />
      )}

      {/* Overlay layer: Mask + Cursor */}
      <canvas
        ref={overlayCanvasRef}
        width={canvasSize.width * bufferScale}
        height={canvasSize.height * bufferScale}
        className="absolute top-0 left-0"
        style={{ pointerEvents: 'none', width: canvasSize.width, height: canvasSize.height, imageRendering: 'pixelated' }}
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
