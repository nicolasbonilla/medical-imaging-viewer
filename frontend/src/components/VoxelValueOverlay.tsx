/**
 * VoxelValueOverlay — shows numeric intensity values on each voxel
 * when zoomed in past 1400%.
 *
 * RENDERING APPROACH: The canvas is placed OUTSIDE the CSS-scaled container
 * and draws text at 1:1 screen pixel ratio. This ensures crisp, sharp text
 * regardless of zoom level. Pixel screen positions are computed from the
 * image element's bounding rect (which accounts for all CSS transforms).
 */

import { useRef, useEffect, memo, useCallback } from 'react';

/** Minimum screen pixels per image pixel to show values */
const MIN_PIXEL_SIZE = 25;

interface VoxelValueOverlayProps {
  /** Base64 PNG of the grayscale slice (from currentSeries.slices) */
  sliceImageData: string;
  /** Native image width in pixels */
  imageWidth: number;
  /** Native image height in pixels */
  imageHeight: number;
  /** The scrollable container ref (viewport for the overlay) */
  scrollableRef: React.RefObject<HTMLDivElement>;
  /** The rendered image element (to get screen position via getBoundingClientRect) */
  imageElementRef: React.RefObject<HTMLImageElement | HTMLCanvasElement>;
  /** Current zoom level (to trigger redraws) */
  zoomLevel: number;
  /** Current pan offset (to trigger redraws) */
  panOffset: { x: number; y: number };
}

export const VoxelValueOverlay = memo(function VoxelValueOverlay({
  sliceImageData,
  imageWidth,
  imageHeight,
  scrollableRef,
  imageElementRef,
  zoomLevel,
  panOffset,
}: VoxelValueOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pixelDataRef = useRef<Uint8ClampedArray | null>(null);

  // Extract pixel values when slice changes
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      const offscreen = document.createElement('canvas');
      offscreen.width = imageWidth;
      offscreen.height = imageHeight;
      const offCtx = offscreen.getContext('2d');
      if (!offCtx) return;
      offCtx.drawImage(img, 0, 0, imageWidth, imageHeight);
      pixelDataRef.current = offCtx.getImageData(0, 0, imageWidth, imageHeight).data;
    };
    img.src = `data:image/png;base64,${sliceImageData}`;
  }, [sliceImageData, imageWidth, imageHeight]);

  const drawValues = useCallback(() => {
    const canvas = canvasRef.current;
    const container = scrollableRef.current;
    const imgEl = imageElementRef.current;
    const pixels = pixelDataRef.current;
    if (!canvas || !container || !imgEl || !pixels) return;

    const containerRect = container.getBoundingClientRect();
    const imgRect = imgEl.getBoundingClientRect();

    // Each image pixel's screen size
    const pixelW = imgRect.width / imageWidth;
    const pixelH = imgRect.height / imageHeight;

    // Don't render if pixels are too small on screen
    if (pixelW < MIN_PIXEL_SIZE) {
      const ctx = canvas.getContext('2d');
      if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }

    // Size canvas to match viewport at device pixel ratio for crisp text
    const dpr = window.devicePixelRatio || 1;
    const viewW = containerRect.width;
    const viewH = containerRect.height;

    if (canvas.width !== Math.round(viewW * dpr) || canvas.height !== Math.round(viewH * dpr)) {
      canvas.width = Math.round(viewW * dpr);
      canvas.height = Math.round(viewH * dpr);
      canvas.style.width = `${viewW}px`;
      canvas.style.height = `${viewH}px`;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, viewW, viewH);

    // Image position relative to scrollable container
    const imgLeft = imgRect.left - containerRect.left;
    const imgTop = imgRect.top - containerRect.top;

    // Font: scale with pixel size, cap at 16px for readability
    const fontSize = Math.max(8, Math.min(pixelW * 0.55, 16));
    ctx.font = `bold ${fontSize}px monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    // Calculate visible pixel range to avoid iterating all pixels
    const xStart = Math.max(0, Math.floor(-imgLeft / pixelW));
    const xEnd = Math.min(imageWidth, Math.ceil((viewW - imgLeft) / pixelW));
    const yStart = Math.max(0, Math.floor(-imgTop / pixelH));
    const yEnd = Math.min(imageHeight, Math.ceil((viewH - imgTop) / pixelH));

    for (let iy = yStart; iy < yEnd; iy++) {
      for (let ix = xStart; ix < xEnd; ix++) {
        const idx = (iy * imageWidth + ix) * 4;
        const value = pixels[idx]; // R channel (grayscale)

        if (value === 0) continue;

        const sx = imgLeft + (ix + 0.5) * pixelW;
        const sy = imgTop + (iy + 0.5) * pixelH;

        // Text with outline for contrast
        ctx.fillStyle = value > 128 ? 'rgba(0,0,0,0.9)' : 'rgba(255,255,255,0.9)';
        ctx.strokeStyle = value > 128 ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.4)';
        ctx.lineWidth = 2;
        ctx.strokeText(String(value), sx, sy);
        ctx.fillText(String(value), sx, sy);
      }
    }
  }, [imageWidth, imageHeight, scrollableRef, imageElementRef, zoomLevel, panOffset]);

  // Redraw when zoom/pan/data changes
  useEffect(() => {
    // Small delay to let layout settle after zoom/pan
    const rafId = requestAnimationFrame(drawValues);
    return () => cancelAnimationFrame(rafId);
  }, [drawValues, sliceImageData]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        pointerEvents: 'none',
        zIndex: 30,
      }}
    />
  );
});
