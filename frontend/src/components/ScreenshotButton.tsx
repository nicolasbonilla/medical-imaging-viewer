/**
 * Screenshot Export Button.
 *
 * Captures the current viewer state (image + overlays) as a PNG file.
 *
 * @module components/ScreenshotButton
 */

import { useCallback } from 'react';
import { Camera } from 'lucide-react';

interface ScreenshotButtonProps {
  containerRef: React.RefObject<HTMLDivElement>;
}

export default function ScreenshotButton({ containerRef }: ScreenshotButtonProps) {
  const handleScreenshot = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    // Find all canvases in the viewer container
    const canvases = container.querySelectorAll('canvas');
    if (canvases.length === 0) return;

    // Use the largest canvas as the base
    let mainCanvas = canvases[0];
    for (const c of canvases) {
      if (c.width * c.height > mainCanvas.width * mainCanvas.height) {
        mainCanvas = c;
      }
    }

    // Create composite canvas
    const composite = document.createElement('canvas');
    composite.width = mainCanvas.width;
    composite.height = mainCanvas.height;
    const ctx = composite.getContext('2d');
    if (!ctx) return;

    // Draw all canvases in order (base image + overlays)
    for (const c of canvases) {
      ctx.drawImage(c, 0, 0, composite.width, composite.height);
    }

    // Also capture SVG overlays (measurements)
    const svgs = container.querySelectorAll('svg');
    for (const svg of svgs) {
      const svgData = new XMLSerializer().serializeToString(svg);
      const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(svgBlob);
      const img = new Image();
      img.onload = () => {
        ctx.drawImage(img, 0, 0, composite.width, composite.height);
        URL.revokeObjectURL(url);
      };
      img.src = url;
    }

    // Download after a short delay (for SVG rendering)
    setTimeout(() => {
      composite.toBlob((blob) => {
        if (!blob) return;
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `mstool-ai-screenshot-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.png`;
        a.click();
        URL.revokeObjectURL(url);
      }, 'image/png');
    }, 100);
  }, [containerRef]);

  return (
    <button
      onClick={handleScreenshot}
      title="Export screenshot (PNG)"
      className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
    >
      <Camera className="w-4 h-4" />
    </button>
  );
}
