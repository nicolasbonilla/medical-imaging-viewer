/**
 * Hook for managing canvas rendering in standard mode.
 * Handles drawing the current slice with zoom and pan transformations.
 */

import { useEffect } from 'react';
import { useViewerStore } from '@/store/useViewerStore';
import type { RenderMode } from './useViewerControls';

interface UseCanvasRenderingProps {
  canvasRef: React.RefObject<HTMLCanvasElement>;
  containerRef: React.RefObject<HTMLDivElement>;
  renderMode: RenderMode;
}

export function useCanvasRendering({ canvasRef, containerRef, renderMode }: UseCanvasRenderingProps) {
  const { currentSeries, currentSliceIndex, zoomLevel, panOffset, setSliceHistogram } = useViewerStore();

  useEffect(() => {
    if (renderMode !== 'standard') return;
    if (!currentSeries || !canvasRef.current || !containerRef.current) return;

    const canvas = canvasRef.current;
    const container = containerRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const currentSlice = currentSeries.slices?.[currentSliceIndex];
    if (!currentSlice) return;

    // Create image from base64
    const img = new Image();
    img.onload = () => {
      // Calculate scale to fit container while maintaining aspect ratio
      const containerWidth = container.clientWidth;
      const containerHeight = container.clientHeight;
      const imageAspect = currentSlice.width / currentSlice.height;
      const containerAspect = containerWidth / containerHeight;

      let renderWidth, renderHeight;
      if (imageAspect > containerAspect) {
        renderWidth = containerWidth * 0.9; // 90% of container width
        renderHeight = renderWidth / imageAspect;
      } else {
        renderHeight = containerHeight * 0.9; // 90% of container height
        renderWidth = renderHeight * imageAspect;
      }

      // Set canvas size to scaled dimensions
      canvas.width = renderWidth;
      canvas.height = renderHeight;

      // Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Apply transformations
      ctx.save();

      // Center the zoom
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;

      ctx.translate(centerX + panOffset.x, centerY + panOffset.y);
      ctx.scale(zoomLevel, zoomLevel);
      ctx.translate(-centerX, -centerY);

      // Draw image scaled to canvas size
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

      ctx.restore();

      // Compute histogram from raw image (no zoom/pan)
      const tempCanvas = document.createElement('canvas');
      const tw = Math.min(img.naturalWidth, 256);
      const th = Math.min(img.naturalHeight, 256);
      tempCanvas.width = tw;
      tempCanvas.height = th;
      const tempCtx = tempCanvas.getContext('2d');
      if (tempCtx) {
        tempCtx.drawImage(img, 0, 0, tw, th);
        const pixels = tempCtx.getImageData(0, 0, tw, th).data;
        const hist = new Array(256).fill(0);
        for (let i = 0; i < pixels.length; i += 4) {
          hist[pixels[i]]++; // R channel (grayscale)
        }
        setSliceHistogram(hist);
      }
    };
    img.src = `data:image/png;base64,${currentSlice.image_data}`;

    // Cleanup: prevent memory leak by clearing Image event handlers and src
    return () => {
      img.onload = null;
      img.onerror = null;
      img.src = '';
    };
  }, [currentSeries, currentSliceIndex, zoomLevel, panOffset.x, panOffset.y, renderMode, canvasRef, containerRef]);
}
