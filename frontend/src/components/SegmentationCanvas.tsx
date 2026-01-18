/**
 * Interactive canvas for segmentation painting
 * Two-layer system: Base image (MRI) + Segmentation overlay
 * Similar to ITK-SNAP architecture
 */

import React, { useRef, useEffect, useState, useCallback, forwardRef, useImperativeHandle } from 'react';
import type { PaintStroke } from '../types/segmentation';

/** Methods exposed via ref for external control */
export interface SegmentationCanvasRef {
  /** Clear local paint cache for a specific slice (call when server confirms save) */
  clearLocalPaintsForSlice: (sliceIndex: number) => void;
  /** Force reload segmentation from server */
  reloadFromServer: () => void;
}

interface SegmentationCanvasProps {
  segmentationId: string;
  sliceIndex: number;
  totalSlices: number;
  imageWidth: number;
  imageHeight: number;
  containerRef: React.RefObject<HTMLDivElement>;
  onPaintStroke: (stroke: Omit<PaintStroke, 'slice_index'>) => void;
  onSliceChange: (newSlice: number) => void;
  selectedLabelId: number;
  brushSize: number;
  eraseMode: boolean;
  showOverlay: boolean;
  enabled: boolean;
  colormap: string;
  baseImageData: string; // Base64 MRI image (never changes)
  zoomLevel: number; // Zoom level from parent (1.0 = 100%)
  panOffset: { x: number; y: number }; // Pan offset from parent
  showBaseImage?: boolean; // Whether to render the base image (false in matplotlib mode)
  renderedImageSize?: { width: number; height: number } | null; // Actual rendered size in matplotlib mode
  matplotlibBbox?: { left: number; top: number; width: number; height: number } | null; // Bounding box of image within matplotlib figure
  renderSegmentationOverlay?: boolean; // Whether to render segmentation visually (false in matplotlib mode where backend renders it)
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const SegmentationCanvas = forwardRef<SegmentationCanvasRef, SegmentationCanvasProps>(({
  segmentationId,
  sliceIndex,
  totalSlices,
  imageWidth,
  imageHeight,
  containerRef,
  onPaintStroke,
  onSliceChange,
  selectedLabelId,
  brushSize,
  eraseMode,
  showOverlay,
  enabled,
  colormap,
  baseImageData,
  zoomLevel,
  panOffset,
  showBaseImage = true, // Default to true for backward compatibility
  renderedImageSize = null, // Rendered size for matplotlib mode
  matplotlibBbox = null, // Bounding box for matplotlib mode
  renderSegmentationOverlay = true, // Default to true for backward compatibility
}, ref) => {
  // Two separate canvas refs
  const baseCanvasRef = useRef<HTMLCanvasElement>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null);

  const baseImageRef = useRef<HTMLImageElement | null>(null);
  const segmentationImageRef = useRef<HTMLImageElement | null>(null);

  const [isPainting, setIsPainting] = useState(false);
  const [cursorPosition, setCursorPosition] = useState<{ x: number; y: number } | null>(null);
  const [segmentationVersion, setSegmentationVersion] = useState(0);
  const pendingReloadRef = useRef<NodeJS.Timeout | null>(null);

  // CRITICAL FIX: Store local paints PER SLICE to preserve them when navigating
  // This fixes the issue where paints were lost when changing slices before server confirmed save
  const localPaintsBySliceRef = useRef<Map<number, Array<{ x: number; y: number; size: number; erase: boolean }>>>(new Map());

  // Legacy reference for backward compatibility with existing code
  const localPaintsRef = useRef<Array<{ x: number; y: number; size: number; erase: boolean }>>([]);

  // Sync localPaintsRef with current slice's paints
  const syncLocalPaintsRef = useCallback(() => {
    const currentPaints = localPaintsBySliceRef.current.get(sliceIndex) || [];
    localPaintsRef.current = currentPaints;
  }, [sliceIndex]);

  // Expose methods via ref for external control (e.g., clearing paints when server confirms save)
  useImperativeHandle(ref, () => ({
    clearLocalPaintsForSlice: (targetSlice: number) => {
      const paintsCount = localPaintsBySliceRef.current.get(targetSlice)?.length || 0;
      if (paintsCount > 0) {
        console.log(`🧹 Clearing ${paintsCount} local paints for slice ${targetSlice} (server confirmed save)`);
        localPaintsBySliceRef.current.set(targetSlice, []);
        // If clearing current slice, also update the legacy ref
        if (targetSlice === sliceIndex) {
          localPaintsRef.current = [];
        }
      }
    },
    reloadFromServer: () => {
      console.log('🔄 Force reloading segmentation from server');
      setSegmentationVersion(prev => prev + 1);
    },
  }), [sliceIndex]);

  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });
  const previousSliceRef = useRef<number>(sliceIndex);
  const previousSegIdRef = useRef<string>(segmentationId);

  // When slice or segmentation changes, force reload from server
  // But DON'T clear local paints for other slices - they persist per slice
  useEffect(() => {
    if (previousSliceRef.current !== sliceIndex || previousSegIdRef.current !== segmentationId) {
      console.log('🔄 Slice/segmentation changed', {
        previousSlice: previousSliceRef.current,
        newSlice: sliceIndex,
        hasPaintsForNewSlice: localPaintsBySliceRef.current.has(sliceIndex),
        paintsCount: localPaintsBySliceRef.current.get(sliceIndex)?.length || 0
      });

      // If segmentation changed (not just slice), clear ALL local paints
      if (previousSegIdRef.current !== segmentationId) {
        console.log('🧹 Segmentation changed, clearing all local paints');
        localPaintsBySliceRef.current.clear();
      }

      // Sync the legacy ref with current slice's paints
      syncLocalPaintsRef();

      previousSliceRef.current = sliceIndex;
      previousSegIdRef.current = segmentationId;
      // Force reload from server to get persisted segmentation data
      setSegmentationVersion(prev => prev + 1);
    }
  }, [sliceIndex, segmentationId, syncLocalPaintsRef]);

  // Segmentation overlay URL (separate from base image)
  const segmentationUrl = `${API_BASE_URL}/api/v1/segmentation/${segmentationId}/slice/${sliceIndex}/segmentation-only?t=${segmentationVersion}`;

  // Calculate canvas size
  useEffect(() => {
    if (!containerRef.current) return;

    const calculateSize = () => {
      const container = containerRef.current;
      if (!container) return;

      // In matplotlib mode with bbox, use the bbox dimensions (image area within figure)
      if (renderedImageSize && matplotlibBbox) {
        setCanvasSize({
          width: Math.floor(matplotlibBbox.width),
          height: Math.floor(matplotlibBbox.height)
        });
        return;
      }

      // In matplotlib mode without bbox (fallback), use full image size
      if (renderedImageSize) {
        setCanvasSize({
          width: Math.floor(renderedImageSize.width),
          height: Math.floor(renderedImageSize.height)
        });
        return;
      }

      // Calculate based on container and image dimensions (standard mode)
      // This ensures correct pixel/voxel mapping
      // IMPORTANT: Must match ImageViewer2D canvas calculation exactly
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

      // DO NOT apply zoom level here - it's applied via CSS transform or ctx.scale()
      // to match ImageViewer2D behavior

      setCanvasSize({ width: Math.floor(renderWidth), height: Math.floor(renderHeight) });
    };

    calculateSize();
    window.addEventListener('resize', calculateSize);
    return () => window.removeEventListener('resize', calculateSize);
  }, [containerRef, imageWidth, imageHeight, renderedImageSize, matplotlibBbox]);

  // Render BASE layer (MRI image only)
  const renderBaseLayer = useCallback(() => {
    const canvas = baseCanvasRef.current;
    const img = baseImageRef.current;
    if (!canvas || canvasSize.width === 0 || !img) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvasSize.width, canvasSize.height);

    // Only apply transformations in standard mode (not in matplotlib mode)
    if (!matplotlibBbox) {
      // Standard mode: Apply transformations (same as ImageViewer2D)
      ctx.save();
      const centerX = canvasSize.width / 2;
      const centerY = canvasSize.height / 2;

      // Apply pan offset first, then zoom
      ctx.translate(centerX + panOffset.x, centerY + panOffset.y);
      ctx.scale(zoomLevel, zoomLevel);
      ctx.translate(-centerX, -centerY);

      ctx.drawImage(img, 0, 0, canvasSize.width, canvasSize.height);
      ctx.restore();
    } else {
      // Matplotlib mode: No transformations, direct 1:1 pixel mapping
      ctx.drawImage(img, 0, 0, canvasSize.width, canvasSize.height);
    }
  }, [canvasSize, showBaseImage, zoomLevel, panOffset, matplotlibBbox]);

  // Load BASE image (MRI) - ONLY ONCE, never changes
  useEffect(() => {
    if (!baseImageData || !showBaseImage) return;

    const img = new Image();
    img.onload = () => {
      baseImageRef.current = img;
      renderBaseLayer();
    };
    img.src = baseImageData;

    // Cleanup: prevent memory leak
    return () => {
      img.onload = null;
      img.onerror = null;
      img.src = '';
    };
  }, [baseImageData, showBaseImage, renderBaseLayer]);

  // Re-render base layer when canvas size changes
  useEffect(() => {
    if (showBaseImage && baseImageRef.current) {
      renderBaseLayer();
    }
  }, [canvasSize, showBaseImage, renderBaseLayer]);

  // Load SEGMENTATION overlay - updates when painting
  // When the server responds successfully with segmentation data, we can clear local paints
  // because the server has confirmed it persisted the data
  useEffect(() => {
    const img = new Image();
    img.crossOrigin = 'anonymous';

    img.onload = () => {
      segmentationImageRef.current = img;

      // CRITICAL FIX: Verify the server image actually contains painted data
      // before clearing local paints. The server may return an empty/transparent
      // image if it doesn't have the data (e.g., different Cloud Run instance).
      const currentSlicePaints = localPaintsBySliceRef.current.get(sliceIndex);
      if (currentSlicePaints && currentSlicePaints.length > 0) {
        // Check if the loaded image has any non-transparent pixels
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = img.naturalWidth || img.width;
        tempCanvas.height = img.naturalHeight || img.height;
        const tempCtx = tempCanvas.getContext('2d');

        if (tempCtx && tempCanvas.width > 0 && tempCanvas.height > 0) {
          tempCtx.drawImage(img, 0, 0);
          const imageData = tempCtx.getImageData(0, 0, tempCanvas.width, tempCanvas.height);
          const pixels = imageData.data;

          // Check if any pixel has non-zero alpha (has actual data)
          let hasData = false;
          for (let i = 3; i < pixels.length; i += 4) {
            if (pixels[i] > 0) {
              hasData = true;
              break;
            }
          }

          if (hasData) {
            // Server image has actual painted data - safe to clear local paints
            console.log(`✅ Server image verified with data for slice ${sliceIndex}, clearing ${currentSlicePaints.length} local paints`);
            localPaintsBySliceRef.current.set(sliceIndex, []);
            localPaintsRef.current = [];
          } else {
            // Server returned empty image - KEEP local paints as they are the source of truth
            console.warn(`⚠️ Server returned empty image for slice ${sliceIndex}, keeping ${currentSlicePaints.length} local paints`);
          }
        }
      }

      renderOverlayLayer();
    };

    img.onerror = (e) => {
      console.error('Failed to load segmentation overlay:', e);
      // On error, keep local paints as backup - they represent unsaved work
      console.warn(`⚠️ Keeping ${localPaintsRef.current.length} local paints as backup for slice ${sliceIndex}`);
      renderOverlayLayer();
    };

    img.src = segmentationUrl;

    // Cleanup: prevent memory leak
    return () => {
      img.onload = null;
      img.onerror = null;
      img.src = '';
    };
  }, [segmentationUrl, segmentationVersion, sliceIndex]);

  // Render OVERLAY layer (segmentation + local paints + cursor)
  const renderOverlayLayer = useCallback(() => {
    const canvas = overlayCanvasRef.current;
    if (!canvas || canvasSize.width === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear overlay
    ctx.clearRect(0, 0, canvasSize.width, canvasSize.height);

    // Only apply transformations in standard mode (not in matplotlib mode)
    const isMatplotlibMode = !!matplotlibBbox;

    if (!isMatplotlibMode) {
      // Standard mode: Apply transformations (same as ImageViewer2D and base layer)
      ctx.save();
      const centerX = canvasSize.width / 2;
      const centerY = canvasSize.height / 2;

      // Apply pan offset first, then zoom
      ctx.translate(centerX + panOffset.x, centerY + panOffset.y);
      ctx.scale(zoomLevel, zoomLevel);
      ctx.translate(-centerX, -centerY);
    }

    // Draw segmentation from server (if available) - ONLY in standard mode
    if (renderSegmentationOverlay) {
      const segImg = segmentationImageRef.current;
      if (segImg && segImg.complete && showOverlay) {
        ctx.drawImage(segImg, 0, 0, canvasSize.width, canvasSize.height);
      }
    }

    // Draw local paints as squares (immediate feedback before server updates)
    // Always show these, even in matplotlib mode
    if (showOverlay) {
      const pixelsPerVoxelX = canvasSize.width / imageWidth;
      const pixelsPerVoxelY = canvasSize.height / imageHeight;

      localPaintsRef.current.forEach(paint => {
        const canvasX = (paint.x / imageWidth) * canvasSize.width;
        const canvasY = (paint.y / imageHeight) * canvasSize.height;

        // Draw square brush
        const halfSize = Math.floor(paint.size / 2);
        const x1 = canvasX - halfSize * pixelsPerVoxelX;
        const y1 = canvasY - halfSize * pixelsPerVoxelY;
        const width = paint.size * pixelsPerVoxelX;
        const height = paint.size * pixelsPerVoxelY;

        ctx.fillStyle = paint.erase ? 'rgba(0, 0, 0, 0.3)' : 'rgba(255, 0, 0, 0.5)';
        ctx.fillRect(x1, y1, width, height);
      });
    }

    // Draw square cursor (voxel-by-voxel)
    // Always show cursor, even in matplotlib mode
    if (cursorPosition && enabled) {
      const canvasX = (cursorPosition.x / imageWidth) * canvasSize.width;
      const canvasY = (cursorPosition.y / imageHeight) * canvasSize.height;

      // Calculate pixels per voxel
      const pixelsPerVoxelX = canvasSize.width / imageWidth;
      const pixelsPerVoxelY = canvasSize.height / imageHeight;

      // Draw square brush preview
      // brushSize=1 → 1x1 voxels, brushSize=3 → 3x3 voxels, etc.
      const halfSize = Math.floor(brushSize / 2);

      // Calculate square bounds in canvas coordinates
      const x1 = canvasX - halfSize * pixelsPerVoxelX;
      const y1 = canvasY - halfSize * pixelsPerVoxelY;
      const width = brushSize * pixelsPerVoxelX;
      const height = brushSize * pixelsPerVoxelY;

      ctx.strokeStyle = eraseMode ? '#ff0000' : '#00ff00';
      ctx.lineWidth = 2;
      ctx.strokeRect(x1, y1, width, height);
    }

    // Restore context only if we saved it (standard mode)
    if (!isMatplotlibMode) {
      ctx.restore();
    }
  }, [canvasSize, imageWidth, imageHeight, cursorPosition, enabled, brushSize, eraseMode, showOverlay, renderSegmentationOverlay, showBaseImage, zoomLevel, panOffset, matplotlibBbox]);

  // Re-render overlay when cursor changes
  useEffect(() => {
    renderOverlayLayer();
  }, [renderOverlayLayer]);

  // Get mouse position
  const getMousePos = useCallback(
    (e: React.MouseEvent<HTMLDivElement>): { x: number; y: number } => {
      const canvas = overlayCanvasRef.current;
      if (!canvas) return { x: 0, y: 0 };

      const rect = canvas.getBoundingClientRect();
      const canvasX = e.clientX - rect.left;
      const canvasY = e.clientY - rect.top;

      // Use Math.floor to avoid off-by-one at boundaries, then clamp to valid range
      const imageX = Math.floor((canvasX / canvasSize.width) * imageWidth);
      const imageY = Math.floor((canvasY / canvasSize.height) * imageHeight);

      // Clamp coordinates to valid range [0, width-1] and [0, height-1]
      const clampedX = Math.max(0, Math.min(imageWidth - 1, imageX));
      const clampedY = Math.max(0, Math.min(imageHeight - 1, imageY));

      return { x: clampedX, y: clampedY };
    },
    [canvasSize, imageWidth, imageHeight]
  );

  // Schedule reload from server
  const scheduleReload = useCallback(() => {
    if (pendingReloadRef.current) {
      clearTimeout(pendingReloadRef.current);
    }

    pendingReloadRef.current = setTimeout(() => {
      setSegmentationVersion(prev => prev + 1);
      pendingReloadRef.current = null;
    }, 500);
  }, []);

  // Apply paint stroke
  // CRITICAL FIX: Store paints in the per-slice Map so they persist when navigating
  const applyPaintStroke = useCallback((pos: { x: number; y: number }) => {
    const paintData = {
      x: pos.x,
      y: pos.y,
      size: brushSize,
      erase: eraseMode,
    };

    // Store in per-slice Map for persistence across slice navigation
    if (!localPaintsBySliceRef.current.has(sliceIndex)) {
      localPaintsBySliceRef.current.set(sliceIndex, []);
    }
    localPaintsBySliceRef.current.get(sliceIndex)!.push(paintData);

    // Also update legacy ref for immediate rendering
    localPaintsRef.current.push(paintData);

    renderOverlayLayer();

    onPaintStroke({
      x: pos.x,
      y: pos.y,
      label_id: selectedLabelId,
      brush_size: brushSize,
      erase: eraseMode,
    });
  }, [brushSize, eraseMode, selectedLabelId, onPaintStroke, renderOverlayLayer, sliceIndex]);

  // Mouse handlers
  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!enabled) return;
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
    if (isPainting) {
      setIsPainting(false);
      // Reload from server after painting to sync backend changes
      scheduleReload();
    }
  };

  const handleMouseLeave = () => {
    if (isPainting) {
      setIsPainting(false);
      // Reload from server after painting to sync backend changes
      scheduleReload();
    }
    setCursorPosition(null);
  };

  // NOTE: Wheel events are handled by ImageViewer2D parent component
  // No need to handle wheel events here to avoid conflicts

  if (canvasSize.width === 0) {
    return <div className="text-white">Loading canvas...</div>;
  }

  // Calculate position offset for matplotlib mode (to align with image within figure)
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
    >
      {/* Base layer: MRI image (never changes) - hidden in matplotlib mode */}
      {showBaseImage && (
        <canvas
          ref={baseCanvasRef}
          width={canvasSize.width}
          height={canvasSize.height}
          className="absolute top-0 left-0"
          style={{
            imageRendering: 'pixelated',
            pointerEvents: 'none',
          }}
        />
      )}

      {/* Overlay layer: Segmentation + paints + cursor */}
      <canvas
        ref={overlayCanvasRef}
        width={canvasSize.width}
        height={canvasSize.height}
        className={`absolute top-0 left-0 ${enabled ? 'cursor-crosshair' : 'cursor-default'}`}
        style={{
          imageRendering: 'pixelated',
          pointerEvents: enabled ? 'auto' : 'none', // Allow wheel events to pass through when disabled
        }}
      />
    </div>
  );
});

// Display name for React DevTools
SegmentationCanvas.displayName = 'SegmentationCanvas';
