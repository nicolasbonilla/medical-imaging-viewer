/**
 * Multi-Panel Viewer for side-by-side MRI sequence comparison.
 *
 * Renders a CSS grid of 1-4 panels, each showing a different MRI sequence
 * of the same patient/timepoint. Supports synchronized slice navigation.
 *
 * No segmentation is drawn here (SRS REQ-SAFE-041, PRB-004 review of PR #71, m7): the panels show
 * sequences that may lie on different voxel grids, and a mask can be placed voxel for voxel only on the
 * image it was drawn on. A mask-overlay path that no caller used (no grid check, label colours of its own)
 * was removed, so that wiring a mask in later cannot bring that hazard back unnoticed.
 *
 * @module components/MultiPanelViewer
 */

import { useEffect, useRef, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { imagingAPI } from '@/api/imaging';
import { useMultiViewerStore, getPanelCount, type PanelState } from '@/store/useMultiViewerStore';
import { SEQUENCE_INFO } from '@/utils/sequenceDetection';
import { middleSliceIndex } from '@/utils/sliceOnOpen';
import type { ImagingInstance } from '@/types';
import { ViewportSafetyOverlay } from './ViewportSafetyOverlay';

/** RC-016 (CAPA-010): patient identity shown on every panel. */
interface PatientIdentity {
  patientName?: string;
  patientMRN?: string;
  studyDescription?: string;
}

interface MultiPanelViewerProps extends PatientIdentity {
  instances: ImagingInstance[];
}

/**
 * Single panel that loads and renders one MRI sequence independently.
 */
function ViewerPanel({
  panel,
  isActive,
  onActivate,
  identity,
}: {
  panel: PanelState;
  isActive: boolean;
  onActivate: () => void;
  identity: PatientIdentity;
}) {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const setSliceIndex = useMultiViewerStore((s) => s.setSliceIndex);
  const syncSlice = useMultiViewerStore((s) => s.syncSlice);

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
    };
    img.src = panel.imageData;
  }, [panel.imageData, panel.sliceIndex, panel.metadata]);

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
      {/* RC-016 + RC-023 (CAPA-010): identity, this panel's own orientation and the
          standing laterality caveat on EVERY panel — rendered first and unconditionally. */}
      <ViewportSafetyOverlay
        patientName={identity.patientName}
        patientMRN={identity.patientMRN}
        studyDescription={identity.studyDescription}
        anatomicalOrientation={panel.orientation}
      />

      {/* Sequence badge — bottom-left, above the caveat, clear of the identity corner */}
      <div className="absolute bottom-8 left-2 z-10 flex items-center gap-1.5">
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
 * Main multi-panel viewer component.
 * Renders a CSS grid of ViewerPanel components.
 */
export function MultiPanelViewer({ instances, patientName, patientMRN, studyDescription }: MultiPanelViewerProps) {
  const { t } = useTranslation();
  const layout = useMultiViewerStore((s) => s.layout);
  const panels = useMultiViewerStore((s) => s.panels);
  const activePanelId = useMultiViewerStore((s) => s.activePanelId);
  const setActivePanelId = useMultiViewerStore((s) => s.setActivePanelId);
  const setPanelImageData = useMultiViewerStore((s) => s.setPanelImageData);
  const setPanelLoading = useMultiViewerStore((s) => s.setPanelLoading);
  const setPanelSliceIndex = useMultiViewerStore((s) => s.setPanelSliceIndex);

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
          const slices = result.slices || [];
          panelSlicesRef.current.set(panel.id, slices);
          // PRB-008: open on the middle slice of this panel's image (it opened on slice 1, a
          // blank image); a position the panel already has (synchronised scrolling) is kept.
          const current = useMultiViewerStore.getState().panels.find((p) => p.id === panel.id)?.sliceIndex ?? 0;
          const start = current > 0 && current < slices.length ? current : middleSliceIndex(slices.length);
          const sliceData = slices[start]?.image_data;
          if (sliceData) {
            setPanelSliceIndex(panel.id, start);
            setPanelImageData(panel.id, `data:image/png;base64,${sliceData}`, {
              rows: result.metadata.rows ?? 0,
              columns: result.metadata.columns ?? 0,
              slices: result.metadata.slices ?? 0,
            }, result.metadata.anatomical_orientation); // RC-023: this panel's own image
          }
        })
        .catch((err) => {
          console.error(`[MultiPanel] Failed to load panel ${panel.id}:`, err);
          setPanelLoading(panel.id, false);
        });
    }
  }, [activePanels, instances, setPanelImageData, setPanelLoading, setPanelSliceIndex]);

  // Update panel image when slice changes
  useEffect(() => {
    for (const panel of activePanels) {
      const slices = panelSlicesRef.current.get(panel.id);
      if (!slices || !panel.metadata) continue;

      const slice = slices[panel.sliceIndex];
      if (slice) {
        const newImage = `data:image/png;base64,${slice.image_data}`;
        if (newImage !== panel.imageData) {
          setPanelImageData(panel.id, newImage, panel.metadata, panel.orientation);
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
          identity={{ patientName, patientMRN, studyDescription }}
        />
      ))}
    </div>
  );
}

export default MultiPanelViewer;
