/**
 * Multi-Panel Viewer for side-by-side MRI sequence comparison.
 *
 * Renders a CSS grid of 1-4 panels, each showing a different MRI sequence
 * of the same patient/timepoint. Supports synchronized slice navigation
 * and shared segmentation/expert mask overlays.
 *
 * @module components/MultiPanelViewer
 */

import { useEffect, useRef, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { imagingAPI } from '@/api/imaging';
import { useMultiViewerStore, getPanelCount, type PanelState } from '@/store/useMultiViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { SEQUENCE_INFO } from '@/utils/sequenceDetection';
import type { ImagingInstance } from '@/types';

interface MultiPanelViewerProps {
  instances: ImagingInstance[];
  /** Segmentation mask from useSegmentationMask (shared across panels) */
  segmentationMask?: {
    mask: Uint8Array | null;
    depth: number;
    height: number;
    width: number;
  };
}

/**
 * Single panel that loads and renders one MRI sequence independently.
 */
function ViewerPanel({
  panel,
  isActive,
  onActivate,
  segmentationMask,
}: {
  panel: PanelState;
  isActive: boolean;
  onActivate: () => void;
  segmentationMask?: { mask: Uint8Array | null; depth: number; height: number; width: number };
}) {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const setSliceIndex = useMultiViewerStore((s) => s.setSliceIndex);
  const syncSlice = useMultiViewerStore((s) => s.syncSlice);
  const isOverlayVisible = useSegmentationStore((s) => s.isOverlayVisible);

  // Find instance data to get gcs_object_name
  const instanceGcsPath = panel.instanceId;

  // Load image data for this panel
  const { data: imageData, isLoading } = useQuery({
    queryKey: ['multi-panel-image', panel.instanceId],
    queryFn: async () => {
      if (!panel.instanceId) return null;
      // panel.instanceId here is actually the instance ID, we need gcs_object_name
      // This will be set by the parent component via the instances prop
      return null;
    },
    enabled: false, // Loaded externally
  });

  // Render canvas when image data or slice changes
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !panel.imageData || !panel.metadata) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      // Size canvas to container
      const container = containerRef.current;
      if (!container) return;

      const containerWidth = container.clientWidth;
      const containerHeight = container.clientHeight;
      const imageAspect = panel.metadata!.columns / panel.metadata!.rows;
      const containerAspect = containerWidth / containerHeight;

      let renderWidth: number, renderHeight: number;
      if (imageAspect > containerAspect) {
        renderWidth = containerWidth;
        renderHeight = renderWidth / imageAspect;
      } else {
        renderHeight = containerHeight;
        renderWidth = renderHeight * imageAspect;
      }

      canvas.width = renderWidth;
      canvas.height = renderHeight;
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(img, 0, 0, renderWidth, renderHeight);

      // Render segmentation overlay
      if (segmentationMask?.mask && isOverlayVisible) {
        const sliceSize = segmentationMask.width * segmentationMask.height;
        const sliceOffset = panel.sliceIndex * sliceSize;
        if (sliceOffset + sliceSize <= segmentationMask.mask.length) {
          const segSlice = segmentationMask.mask.subarray(sliceOffset, sliceOffset + sliceSize);
          renderSegOverlayOnCtx(ctx, segSlice, segmentationMask.width, segmentationMask.height, renderWidth, renderHeight);
        }
      }
    };
    img.src = panel.imageData;
  }, [panel.imageData, panel.sliceIndex, panel.metadata, segmentationMask, isOverlayVisible]);

  // Mouse wheel for slice navigation
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    if (!panel.metadata) return;
    const delta = e.deltaY > 0 ? 1 : -1;
    const newIndex = Math.max(0, Math.min(panel.metadata.slices - 1, panel.sliceIndex + delta));
    setSliceIndex(panel.id, newIndex);
  }, [panel.id, panel.sliceIndex, panel.metadata, setSliceIndex]);

  const seqInfo = SEQUENCE_INFO[panel.sequence];

  return (
    <div
      ref={containerRef}
      className={`relative flex items-center justify-center bg-black overflow-hidden cursor-pointer ${
        isActive ? 'ring-2 ring-blue-500' : 'ring-1 ring-gray-700'
      }`}
      onClick={onActivate}
      onWheel={handleWheel}
    >
      {/* Sequence badge */}
      <div className="absolute top-2 left-2 z-10 flex items-center gap-1.5">
        <span
          className="px-2 py-0.5 rounded text-xs font-bold text-white shadow"
          style={{ backgroundColor: seqInfo.color }}
        >
          {seqInfo.shortLabel}
        </span>
        {panel.metadata && (
          <span className="text-[10px] text-gray-400">
            {panel.sliceIndex + 1}/{panel.metadata.slices}
          </span>
        )}
      </div>

      {/* Loading state */}
      {panel.isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/50 z-20">
          <Loader2 className="w-8 h-8 text-blue-400 animate-spin" />
        </div>
      )}

      {/* Empty state */}
      {!panel.instanceId && !panel.isLoading && (
        <div className="text-gray-500 text-sm">
          {t('layout.emptyPanel', 'No image assigned')}
        </div>
      )}

      {/* Canvas */}
      <canvas ref={canvasRef} className="max-w-full max-h-full" />
    </div>
  );
}

/**
 * Render contour overlay on a canvas context (simplified version for multi-panel).
 */
/**
 * Render segmentation mask overlay on a canvas context (simplified for multi-panel).
 */
function renderSegOverlayOnCtx(
  ctx: CanvasRenderingContext2D,
  maskSlice: Uint8Array,
  maskW: number,
  maskH: number,
  canvasW: number,
  canvasH: number,
) {
  const imageData = ctx.createImageData(maskW, maskH);
  const data = imageData.data;

  for (let y = 0; y < maskH; y++) {
    for (let x = 0; x < maskW; x++) {
      const idx = y * maskW + x;
      const val = maskSlice[idx];
      if (val === 0) continue;
      // Simple color by label value
      const pi = idx * 4;
      data[pi] = (val * 67) % 256;
      data[pi + 1] = (val * 137) % 256;
      data[pi + 2] = (val * 211) % 256;
      data[pi + 3] = 128;
    }
  }

  const tmp = document.createElement('canvas');
  tmp.width = maskW; tmp.height = maskH;
  const tmpCtx = tmp.getContext('2d');
  if (!tmpCtx) return;
  tmpCtx.putImageData(imageData, 0, 0);

  ctx.save();
  ctx.globalAlpha = 0.5;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(tmp, 0, 0, canvasW, canvasH);
  ctx.restore();
}

/**
 * Main multi-panel viewer component.
 * Renders a CSS grid of ViewerPanel components.
 */
export function MultiPanelViewer({ instances, segmentationMask }: MultiPanelViewerProps) {
  const { t } = useTranslation();
  const layout = useMultiViewerStore((s) => s.layout);
  const panels = useMultiViewerStore((s) => s.panels);
  const activePanelId = useMultiViewerStore((s) => s.activePanelId);
  const setActivePanelId = useMultiViewerStore((s) => s.setActivePanelId);
  const setPanelImageData = useMultiViewerStore((s) => s.setPanelImageData);
  const setPanelLoading = useMultiViewerStore((s) => s.setPanelLoading);

  const panelCount = getPanelCount(layout);
  const activePanels = useMemo(() => panels.slice(0, panelCount), [panels, panelCount]);

  // Store all slices per panel for slice navigation
  const panelSlicesRef = useRef<Map<string, Array<{ image_data: string }>>>(new Map());
  // Track which panel+instance combos have been requested to prevent infinite re-fetch loops
  const loadRequestedRef = useRef<Set<string>>(new Set());

  // Clear load tracking when layout changes (allows re-loading for new assignments)
  useEffect(() => {
    loadRequestedRef.current.clear();
    panelSlicesRef.current.clear();
  }, [layout]);

  // Load image data for each panel that has an instanceId
  useEffect(() => {
    for (const panel of activePanels) {
      if (!panel.instanceId || panel.imageData) continue;

      // Prevent duplicate loads — this breaks the infinite loop caused by
      // setPanelLoading updating the store → activePanels recomputing → useEffect re-firing
      const loadKey = `${panel.id}:${panel.instanceId}`;
      if (loadRequestedRef.current.has(loadKey)) continue;
      loadRequestedRef.current.add(loadKey);

      // Find instance to get gcs_object_name
      const inst = instances.find((i) => i.id === panel.instanceId);
      if (!inst) continue;

      setPanelLoading(panel.id, true);
      imagingAPI.processImage(inst.gcs_object_name, 0, 500)
        .then((result) => {
          const sliceData = result.slices?.[0]?.image_data;
          if (sliceData) {
            setPanelImageData(panel.id, `data:image/png;base64,${sliceData}`, {
              rows: result.metadata.rows ?? 0,
              columns: result.metadata.columns ?? 0,
              slices: result.metadata.slices ?? 0,
            });
          }
          panelSlicesRef.current.set(panel.id, result.slices || []);
        })
        .catch((err) => {
          console.error(`[MultiPanel] Failed to load panel ${panel.id}:`, err);
          setPanelLoading(panel.id, false);
        });
    }
  }, [activePanels, instances, setPanelImageData, setPanelLoading]);

  // Update panel image when slice changes
  useEffect(() => {
    for (const panel of activePanels) {
      const slices = panelSlicesRef.current.get(panel.id);
      if (!slices || !panel.metadata) continue;

      const slice = slices[panel.sliceIndex];
      if (slice) {
        const newImage = `data:image/png;base64,${slice.image_data}`;
        if (newImage !== panel.imageData) {
          setPanelImageData(panel.id, newImage, panel.metadata);
        }
      }
    }
  }, [activePanels.map(p => p.sliceIndex).join(',')]); // eslint-disable-line react-hooks/exhaustive-deps

  // Grid class based on layout
  const gridClass = useMemo(() => {
    switch (layout) {
      case '1x2': return 'grid-cols-2 grid-rows-1';
      case '2x2': return 'grid-cols-2 grid-rows-2';
      default: return 'grid-cols-1 grid-rows-1';
    }
  }, [layout]);

  return (
    <div className={`w-full h-full grid ${gridClass} gap-1 bg-gray-900`}>
      {activePanels.map((panel) => (
        <ViewerPanel
          key={panel.id}
          panel={panel}
          isActive={panel.id === activePanelId}
          onActivate={() => setActivePanelId(panel.id)}
          segmentationMask={segmentationMask}
        />
      ))}
    </div>
  );
}

export default MultiPanelViewer;
