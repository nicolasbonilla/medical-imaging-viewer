/**
 * Multi-Panel Viewer for side-by-side MRI sequence comparison.
 *
 * Renders a grid of 1-4 panels, each showing a different MRI sequence of the same
 * patient/timepoint, with synchronised slice navigation.
 *
 * v3: on the in-browser path each panel renders from its own NIfTI (same parser,
 * geometry and fail-closed check as the main viewer, view only) in the active plane;
 * a panel the browser must not render falls back to the server PNG for that panel.
 * Every panel carries the RC-016/RC-023 safety annotation (identity + orientation).
 *
 * @module components/MultiPanelViewer
 */

import { useEffect, useRef, useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { imagingAPI } from '@/api/imaging';
import { useMultiViewerStore, getPanelCount, type PanelState } from '@/store/useMultiViewerStore';
import { SEQUENCE_INFO } from '@/utils/sequenceDetection';
import type { ImagingInstance } from '@/types';
import type { RenderMode } from '@/hooks/useViewerControls';
import { ViewportSafetyOverlay } from './ViewportSafetyOverlay';
import { ClientPanelView, type ClientPanelInfo } from './viewer2d/ClientPanelView';
import { Skeleton } from './ui';

interface MultiPanelViewerProps {
  instances: ImagingInstance[];
  /** v3: 'client' renders panels in the browser; anything else uses server PNGs. */
  renderMode?: RenderMode;
  patientName?: string;
  patientMRN?: string;
  studyDescription?: string;
}

interface PanelProps {
  panel: PanelState;
  instance: ImagingInstance | undefined;
  isActive: boolean;
  onActivate: () => void;
  useClient: boolean;
  patientName?: string;
  patientMRN?: string;
  studyDescription?: string;
}

/** Single panel: in-browser view, or the legacy server PNG of the current slice. */
function ViewerPanel({ panel, instance, isActive, onActivate, useClient, patientName, patientMRN, studyDescription }: PanelProps) {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const setSliceIndex = useMultiViewerStore((s) => s.setSliceIndex);
  const setPanelMetadata = useMultiViewerStore((s) => s.setPanelMetadata);
  const [clientInfo, setClientInfo] = useState<ClientPanelInfo | null>(null);
  const [clientFailed, setClientFailed] = useState(false);
  const client = useClient && !clientFailed && !!instance;
  const depth = client ? clientInfo?.depth ?? 0 : panel.metadata?.slices ?? 0;

  const centeredFor = useRef<string | null>(null);
  useEffect(() => { setClientFailed(false); setClientInfo(null); }, [instance?.gcs_object_name]);

  // Publish the active view's depth (toolbar slice range) and, once per image, start
  // in-browser panels in the middle of the stack instead of on the empty first slice.
  const handleReady = useCallback((info: ClientPanelInfo) => {
    setClientInfo(info);
    setPanelMetadata(panel.id, { rows: 0, columns: 0, slices: info.depth }, info.orientation);
    const key = instance?.gcs_object_name ?? null;
    if (centeredFor.current !== key) {
      centeredFor.current = key;
      const current = useMultiViewerStore.getState().panels.find((p) => p.id === panel.id)?.sliceIndex ?? 0;
      if (current === 0 && info.depth > 1) setSliceIndex(panel.id, Math.floor(info.depth / 2));
    }
  }, [panel.id, instance?.gcs_object_name, setSliceIndex, setPanelMetadata]);
  const handleFallback = useCallback(() => setClientFailed(true), []);

  // Legacy path: draw the server PNG.
  useEffect(() => {
    if (client) return;
    const canvas = canvasRef.current;
    if (!canvas || !panel.imageData || !panel.metadata) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const img = new Image();
    img.onload = () => {
      const container = containerRef.current;
      if (!container) return;
      const cw = container.clientWidth, ch = container.clientHeight;
      const imageAspect = panel.metadata!.columns / panel.metadata!.rows;
      let w: number, h: number;
      if (imageAspect > cw / ch) { w = cw; h = w / imageAspect; } else { h = ch; w = h * imageAspect; }
      canvas.width = w;
      canvas.height = h;
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(img, 0, 0, w, h);
    };
    img.src = panel.imageData;
  }, [client, panel.imageData, panel.sliceIndex, panel.metadata]);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    if (!depth) return;
    const delta = e.deltaY > 0 ? 1 : -1;
    setSliceIndex(panel.id, Math.max(0, Math.min(depth - 1, panel.sliceIndex + delta)));
  }, [panel.id, panel.sliceIndex, depth, setSliceIndex]);

  const seqInfo = SEQUENCE_INFO[panel.sequence];
  const label = `${seqInfo.label} — ${t('viewer3.panelActivate', 'click to make this the active panel')}`;

  return (
    <div
      ref={containerRef}
      role="group"
      aria-label={label}
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onActivate(); } }}
      className={`relative flex items-center justify-center overflow-hidden bg-black focus:outline-none ${
        isActive ? 'ring-2 ring-inset ring-brand-500' : 'ring-1 ring-inset ring-surface-border'
      }`}
      onClick={onActivate}
      onWheel={handleWheel}
    >
      {/* RC-016 / RC-023: identity and orientation in every panel, unconditionally. */}
      <ViewportSafetyOverlay
        patientName={patientName}
        patientMRN={patientMRN}
        studyDescription={studyDescription}
        anatomicalOrientation={client ? clientInfo?.orientation : panel.orientation}
      />

      {/* Sequence + slice, bottom-left (clear of the identity / orientation corners) */}
      <div className="pointer-events-none absolute bottom-2 left-2 z-10 flex items-center gap-1.5">
        <span className="rounded px-1.5 py-0.5 text-xs font-semibold text-surface-void" style={{ backgroundColor: seqInfo.color }}>
          {seqInfo.shortLabel}
        </span>
        {depth > 0 && (
          <span className="rounded bg-black/60 px-1.5 py-0.5 text-xs tabular-nums text-ink-soft">
            {Math.min(panel.sliceIndex, depth - 1) + 1}/{depth}
          </span>
        )}
      </div>

      {client && instance ? (
        <ClientPanelView
          fileId={instance.gcs_object_name}
          sliceIndex={panel.sliceIndex}
          onReady={handleReady}
          onFallback={handleFallback}
        />
      ) : (
        <>
          {panel.isLoading && (
            <div className="absolute inset-0 z-10 grid place-items-center bg-black/50">
              <Skeleton className="aspect-square w-1/2 rounded-2xl" />
            </div>
          )}
          {!panel.instanceId && !panel.isLoading && (
            <div className="text-sm text-ink-faint">{t('layout.emptyPanel', 'No image assigned')}</div>
          )}
          <canvas ref={canvasRef} className="max-h-full max-w-full" aria-hidden />
        </>
      )}
    </div>
  );
}

/**
 * Main multi-panel viewer component.
 */
export function MultiPanelViewer({ instances, renderMode = 'standard', patientName, patientMRN, studyDescription }: MultiPanelViewerProps) {
  const layout = useMultiViewerStore((s) => s.layout);
  const panels = useMultiViewerStore((s) => s.panels);
  const activePanelId = useMultiViewerStore((s) => s.activePanelId);
  const setActivePanelId = useMultiViewerStore((s) => s.setActivePanelId);
  const setPanelImageData = useMultiViewerStore((s) => s.setPanelImageData);
  const setPanelLoading = useMultiViewerStore((s) => s.setPanelLoading);
  const useClient = renderMode === 'client';

  const panelCount = getPanelCount(layout);
  const activePanels = useMemo(() => panels.slice(0, panelCount), [panels, panelCount]);

  // Legacy path: all PNG slices per panel for slice navigation
  const panelSlicesRef = useRef<Map<string, Array<{ image_data: string }>>>(new Map());
  // Track which panel+instance combos have been requested to prevent re-fetch loops
  const loadRequestedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    loadRequestedRef.current.clear();
    panelSlicesRef.current.clear();
  }, [layout, useClient]);

  // Legacy path only: load the server PNG series for each assigned panel.
  useEffect(() => {
    if (useClient) return;
    for (const panel of activePanels) {
      if (!panel.instanceId || panel.imageData) continue;
      const loadKey = `${panel.id}:${panel.instanceId}`;
      if (loadRequestedRef.current.has(loadKey)) continue;
      loadRequestedRef.current.add(loadKey);
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
            }, result.metadata.anatomical_orientation);
          }
          panelSlicesRef.current.set(panel.id, result.slices || []);
        })
        .catch((err) => {
          console.error(`[MultiPanel] Failed to load panel ${panel.id}:`, err);
          setPanelLoading(panel.id, false);
        });
    }
  }, [useClient, activePanels, instances, setPanelImageData, setPanelLoading]);

  // Legacy path: update panel image when slice changes
  useEffect(() => {
    if (useClient) return;
    for (const panel of activePanels) {
      const slices = panelSlicesRef.current.get(panel.id);
      if (!slices || !panel.metadata) continue;
      const slice = slices[panel.sliceIndex];
      if (slice) {
        const newImage = `data:image/png;base64,${slice.image_data}`;
        if (newImage !== panel.imageData) setPanelImageData(panel.id, newImage, panel.metadata, panel.orientation);
      }
    }
  }, [activePanels.map((p) => p.sliceIndex).join(','), useClient]); // eslint-disable-line react-hooks/exhaustive-deps

  const gridClass = layout === '1x2' ? 'grid-cols-2 grid-rows-1' : layout === '2x2' ? 'grid-cols-2 grid-rows-2' : 'grid-cols-1 grid-rows-1';

  return (
    <div className={`grid h-full w-full gap-px bg-surface-border ${gridClass}`}>
      {activePanels.map((panel) => (
        <ViewerPanel
          key={panel.id}
          panel={panel}
          instance={instances.find((i) => i.id === panel.instanceId)}
          isActive={panel.id === activePanelId}
          onActivate={() => setActivePanelId(panel.id)}
          useClient={useClient}
          patientName={patientName}
          patientMRN={patientMRN}
          studyDescription={studyDescription}
        />
      ))}
    </div>
  );
}

export default MultiPanelViewer;
