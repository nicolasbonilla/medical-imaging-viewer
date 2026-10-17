/**
 * ClientPanelView — view-only in-browser slice for one panel of the multi-panel grid
 * (v3). Same parser, geometry, window and fail-closed agreement check as the main
 * viewport; no painting. If the browser must not render this image it says so and the
 * caller shows the server image instead (`onFallback`).
 */
import { useEffect, useMemo, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { imagingAPI } from '@/api/imaging';
import { useClientVolume } from '@/hooks/useClientVolume';
import { useViewerStore } from '@/store/useViewerStore';
import { checkClientVolume, viewsFor } from '@/volume/clientVolume';
import { clampSlice } from '@/volume/sliceGeometry';
import { autoWindow, renderSliceRGBA } from '@/volume/windowing';
import { computeTransform } from '@/volume/viewportTransform';
import { Skeleton } from '../ui';

export interface ClientPanelInfo {
  depth: number;
  orientation?: string;
}

export function ClientPanelView({
  fileId, sliceIndex, onReady, onFallback,
}: {
  fileId: string;
  sliceIndex: number;
  onReady: (info: ClientPanelInfo) => void;
  onFallback: (reason: string) => void;
}) {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const plane = useViewerStore((s) => s.slicePlane);
  const orientationMode = useViewerStore((s) => s.orientationMode);
  const smooth = useViewerStore((s) => s.smoothDisplay);

  const meta = useQuery({
    queryKey: ['series-metadata', fileId],
    queryFn: () => imagingAPI.getSeriesMetadata(fileId),
    staleTime: 10 * 60 * 1000,
  });
  const vol = useClientVolume(fileId, true);
  const volume = vol.status === 'ready' ? vol.volume : null;
  const check = useMemo(
    () => (volume && meta.data ? checkClientVolume(volume, meta.data.metadata) : null),
    [volume, meta.data],
  );

  useEffect(() => {
    if (vol.status === 'error') onFallback(vol.error);
    else if (meta.isError) onFallback('metadata unavailable');
    else if (check && !check.renderable) onFallback(check.problems.join('; '));
  }, [vol, meta.isError, check, onFallback]);

  const anatomical = !!check?.anatomical && orientationMode === 'anatomical';
  const view = useMemo(() => (volume && check?.renderable ? viewsFor(volume, anatomical)[plane] : null), [volume, check, anatomical, plane]);

  useEffect(() => {
    if (view) onReady({ depth: view.depth, orientation: meta.data?.metadata?.anatomical_orientation });
  }, [view, meta.data, onReady]);

  useEffect(() => {
    const canvas = canvasRef.current, box = boxRef.current;
    if (!canvas || !box || !volume || !view) return;
    const draw = () => {
      const w = box.clientWidth, h = box.clientHeight;
      if (!w || !h) return;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      const off = document.createElement('canvas');
      off.width = view.cols; off.height = view.rows;
      const rgba = renderSliceRGBA(volume.nifti, view, clampSlice(view, sliceIndex), autoWindow(volume.stats), volume.stats);
      off.getContext('2d')?.putImageData(new ImageData(rgba as Uint8ClampedArray<ArrayBuffer>, view.cols, view.rows), 0, 0);
      const tr = computeTransform(w, h, view, 1, { x: 0, y: 0 }, 0.94);
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.setTransform(dpr * tr.scaleX, 0, 0, dpr * tr.scaleY, dpr * tr.originX, dpr * tr.originY);
      ctx.imageSmoothingEnabled = smooth;
      ctx.drawImage(off, 0, 0);
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(box);
    return () => ro.disconnect();
  }, [volume, view, sliceIndex, smooth]);

  return (
    <div ref={boxRef} className="absolute inset-0" data-testid="client-panel-view">
      <canvas ref={canvasRef} className="h-full w-full" aria-hidden />
      {(vol.status === 'loading' || meta.isLoading) && (
        <div className="absolute inset-0 grid place-items-center" role="status" aria-live="polite">
          <Skeleton className="aspect-square w-1/2 rounded-2xl" />
          <span className="sr-only">{t('viewer3.loadingVolume', 'Loading volume in the browser…')}</span>
        </div>
      )}
    </div>
  );
}

export default ClientPanelView;
