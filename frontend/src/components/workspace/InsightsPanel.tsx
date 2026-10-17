/**
 * InsightsPanel — right side of the viewer workspace (v3), replacing ControlPanel and
 * the "MS Report" drop-down. Three tabs:
 *   Image    — window/level (real units on the browser path), histogram with the window
 *              band, 3D options, image facts incl. the browser/server agreement check;
 *   Analysis — longitudinal comparison and segmentation agreement (unchanged panels);
 *   Report   — the MS report generator (unchanged panel).
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, AlertTriangle, Scissors } from 'lucide-react';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { useViewerStore } from '@/store/useViewerStore';
import { studyAPI } from '@/api/study';
import type { StudySummary } from '@/types';
import type { RenderMode } from '@/hooks/useViewerControls';
import type { ReportResponse } from '@/types';
import { COLORMAPS_3D } from '@/utils/colormaps3d';
import { datatypeName } from '@/volume/nifti';
import { windowBounds } from '@/volume/windowing';
import { LongitudinalCompare } from '../LongitudinalCompare';
import { SegmentationComparison } from '../SegmentationComparison';
import { AIReportPanel } from '../AIReportPanel';
import type { ClientViewportStatus } from '../viewer2d/ClientSliceViewport';
import { Badge, Button, SegmentedControl, Switch, TabPanel, Tabs } from '../ui';
import { IntensityHistogram } from './IntensityHistogram';
import { clientPresets, effectiveWindow, formatIntensity } from './windowPresets';

type Tab = 'image' | 'annotate' | 'analysis' | 'report';

function Card({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-surface-border bg-surface-base p-3">
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <h3 className="text-xs font-medium uppercase tracking-wide text-ink-faint">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="text-right text-xs tabular-nums text-ink-base">{value}</dd>
    </div>
  );
}

function NumberField({ label, value, onCommit, min }: { label: string; value: number; onCommit: (v: number) => void; min?: number }) {
  const [draft, setDraft] = useState<string | null>(null);
  const shown = draft ?? formatIntensity(value);
  const commit = () => {
    if (draft == null) return;
    const v = parseFloat(draft);
    if (Number.isFinite(v) && (min == null || v > min)) onCommit(v);
    setDraft(null);
  };
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-ink-muted">{label}</span>
      <input
        type="number"
        inputMode="decimal"
        value={shown}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setDraft(null); }}
        className="h-8 w-full rounded-md border border-surface-border bg-surface-raised px-2 text-xs tabular-nums text-ink-base focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
      />
    </label>
  );
}

function ImageTab({ renderMode, clientStatus }: { renderMode: RenderMode; clientStatus: ClientViewportStatus | null }) {
  const { t } = useTranslation();
  const viewMode = useViewerStore((s) => s.viewMode);
  const series = useViewerStore((s) => s.currentSeries);
  const wc = useViewerStore((s) => s.windowCenter);
  const ww = useViewerStore((s) => s.windowWidth);
  const setWindowLevel = useViewerStore((s) => s.setWindowLevel);
  const histogram = useViewerStore((s) => s.sliceHistogram);
  const cursor = useViewerStore((s) => s.cursorInfo);
  const render3DMode = useViewerStore((s) => s.render3DMode);
  const setRender3DMode = useViewerStore((s) => s.setRender3DMode);
  const colormap3D = useViewerStore((s) => s.colormap3D);
  const setColormap3D = useViewerStore((s) => s.setColormap3D);
  const clipPlaneEnabled = useViewerStore((s) => s.clipPlaneEnabled);
  const clipPlanePosition = useViewerStore((s) => s.clipPlanePosition);
  const setClipPlane = useViewerStore((s) => s.setClipPlane);
  const clipPlaneAxis = useViewerStore((s) => s.clipPlaneAxis);
  const setClipPlaneAxis = useViewerStore((s) => s.setClipPlaneAxis);

  const meta = series?.metadata;
  const vol = clientStatus?.volume ?? null;
  const stats = vol?.stats ?? null;
  const isClient = renderMode === 'client' && !!stats;
  const wl = stats ? effectiveWindow(wc, ww, stats) : null;
  const bounds = stats && wl ? windowBounds(wl, stats) : null;
  const seed = { center: meta?.window_center, width: meta?.window_width };
  const presets = stats ? clientPresets(stats, seed) : [];

  return (
    <div className="space-y-3 p-3">
      {viewMode === '3d' ? (
        <Card title={t('viewer3.volume3d', '3D volume')}>
          <div className="space-y-3">
            <SegmentedControl
              ariaLabel={t('viewer.renderMode', 'Render Mode')}
              value={render3DMode}
              onChange={setRender3DMode}
              className="w-full"
              options={[
                { value: 'volume', label: t('viewer.volumeRender', 'Volume') },
                { value: 'multiplanar', label: t('viewer.multiplanar', 'Multiplanar') },
              ]}
            />
            <label className="block">
              <span className="mb-1 block text-xs text-ink-muted">{t('viewer.colormap', 'Colormap')}</span>
              <select
                value={colormap3D}
                onChange={(e) => setColormap3D(e.target.value)}
                className="h-8 w-full rounded-md border border-surface-border bg-surface-raised px-2 text-xs text-ink-base focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
              >
                {COLORMAPS_3D.map((cm) => <option key={cm.id} value={cm.id}>{cm.label}</option>)}
              </select>
            </label>
            <div className="space-y-2">
              <Switch
                checked={clipPlaneEnabled}
                onChange={(on) => setClipPlane(on)}
                label={<span className="inline-flex items-center gap-1.5"><Scissors className="h-3.5 w-3.5" aria-hidden />{t('viewer.clipPlane', 'Clip Plane')}</span>}
              />
              {clipPlaneEnabled && (
                <>
                  <SegmentedControl
                    size="sm"
                    ariaLabel={t('viewer3.clipAxis', 'Clip axis')}
                    value={clipPlaneAxis}
                    onChange={setClipPlaneAxis}
                    className="w-full"
                    options={(['axial', 'coronal', 'sagittal'] as const).map((a) => ({
                      value: a, label: t(`viewer.clipAxis.${a}`, a.charAt(0).toUpperCase() + a.slice(1)),
                    }))}
                  />
                  <div className="flex items-center gap-2">
                    <input
                      type="range" min="0" max="100"
                      value={Math.round(clipPlanePosition * 100)}
                      onChange={(e) => setClipPlane(true, parseInt(e.target.value, 10) / 100)}
                      aria-label={t('viewer3.clipDepth', 'Clip depth')}
                      className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-surface-hover accent-brand-500"
                    />
                    <span className="w-10 text-right text-xs tabular-nums text-ink-soft">{Math.round(clipPlanePosition * 100)}%</span>
                  </div>
                </>
              )}
            </div>
          </div>
        </Card>
      ) : (
        <Card
          title={t('viewer.windowLevel', 'Window / Level')}
          aside={isClient ? <Badge tone="brand">{t('viewer3.fullDepth', 'Full bit depth')}</Badge> : undefined}
        >
          {isClient && wl ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <NumberField label={t('viewer3.wl.level', 'Level (C)')} value={wl.center}
                  onCommit={(c) => setWindowLevel(c, wl.width)} />
                <NumberField label={t('viewer3.wl.width', 'Width (W)')} value={wl.width} min={0}
                  onCommit={(w) => setWindowLevel(wl.center, w)} />
              </div>
              <div className="flex flex-wrap gap-1.5">
                {presets.map((p) => (
                  <Button key={p.id} size="sm" variant={
                    p.id === 'auto' ? (ww <= 0 ? 'primary' : 'secondary')
                      : ww > 0 && Math.abs(wc - p.wl.center) < 1e-9 && Math.abs(ww - p.wl.width) < 1e-9 ? 'primary' : 'secondary'
                  }
                    className="h-7"
                    onClick={() => (p.id === 'auto' ? setWindowLevel(0, 0) : setWindowLevel(p.wl.center, p.wl.width))}>
                    {p.id === 'auto' ? t('viewer3.wl.autoShort', 'Auto') : p.id === 'full' ? t('viewer3.wl.fullShort', 'Full range') : t('viewer3.wl.serverShort', 'Server 2–98 %')}
                  </Button>
                ))}
              </div>
              {histogram && stats && (
                <IntensityHistogram
                  histogram={histogram}
                  range={[stats.min, stats.max]}
                  window={bounds}
                  cursor={cursor?.value ?? null}
                  ariaLabel={t('viewer3.histogramAria', 'Intensity histogram of the displayed slice with the active window')}
                />
              )}
              <p className="text-xs leading-relaxed text-ink-muted">
                {t('viewer3.wl.realUnits', 'Values are the image’s own stored intensities (after header scaling), not 8-bit display levels.')}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-xs leading-relaxed text-ink-muted">
                {renderMode === 'standard'
                  ? t('viewer3.wl.legacy', 'Server images are 8-bit and pre-windowed; switch to in-browser rendering for full window/level.')
                  : t('viewer3.wl.legacyServer', 'Window/level is applied by the server for this render path.')}
              </p>
              {(renderMode === 'matplotlib' || renderMode === 'niivue') && (() => {
                // Same semantics as the previous ViewerControls block: never fabricate a
                // width; a centre alone pairs with the active width, else the seed.
                const seedC = meta?.window_center, seedW = meta?.window_width;
                const active = ww > 0;
                const hasSeed = seedC != null && seedW != null && seedW > 0;
                return (
                  <div className="grid grid-cols-2 gap-2">
                    <NumberField label={t('viewer.wlCenter', 'Window center')} value={active ? wc : (seedC ?? 0)}
                      onCommit={(c) => { const w = active ? ww : (hasSeed ? (seedW as number) : null); if (w != null && w > 0) setWindowLevel(c, w); }} />
                    <NumberField label={t('viewer.wlWidth', 'Window width')} value={active ? ww : (seedW ?? 0)} min={0}
                      onCommit={(w) => setWindowLevel(active ? wc : (seedC ?? 0), w)} />
                  </div>
                );
              })()}
              {histogram && (
                <IntensityHistogram histogram={histogram} range={[0, 255]} cursor={cursor?.intensity ?? null}
                  ariaLabel={t('viewer3.histogramAria8', 'Histogram of the 8-bit display image')} />
              )}
            </div>
          )}
        </Card>
      )}

      <Card title={t('viewer.imageInformation', 'Image information')}>
        <dl className="divide-y divide-surface-border/60">
          <Fact label={t('viewer.format', 'Format')} value={(series?.format ?? '—').toUpperCase()} />
          <Fact label={t('viewer.dimensions', 'Dimensions')} value={meta ? `${meta.rows} × ${meta.columns} × ${meta.slices}` : '—'} />
          {Array.isArray(meta?.pixel_spacing) && meta.pixel_spacing.length >= 2 && (
            <Fact label={t('viewer.pixelSpacing', 'Pixel spacing')} value={`${meta.pixel_spacing[0].toFixed(2)} × ${meta.pixel_spacing[1].toFixed(2)} mm`} />
          )}
          {meta?.slice_thickness != null && (
            <Fact label={t('viewer.sliceThickness', 'Thickness')} value={`${meta.slice_thickness.toFixed(2)} mm`} />
          )}
          <Fact label={t('viewer3.orientationCodes', 'Orientation (affine)')} value={meta?.anatomical_orientation ?? 'UNKNOWN'} />
          {vol && (
            <>
              <Fact label={t('viewer3.datatype', 'Stored as')} value={`${datatypeName(vol.nifti.datatype)}${vol.nifti.scaled ? ` · ×${vol.nifti.slope} + ${vol.nifti.inter}` : ''}`} />
              <Fact label={t('viewer3.range', 'Intensity range')} value={`${formatIntensity(vol.stats.min)} … ${formatIntensity(vol.stats.max)}`} />
            </>
          )}
        </dl>
        {renderMode === 'client' && vol && (
          <div className="mt-2.5 flex items-start gap-2 rounded-md border border-clinical-good/25 bg-clinical-good/5 p-2 text-xs text-ink-soft">
            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-clinical-good" aria-hidden />
            <span>
              {clientStatus?.anatomical
                ? t('viewer3.verifiedOriented', 'Browser reading matches the server (grid, voxel size and orientation) — shown from the original data.')
                : t('viewer3.verifiedGrid', 'Browser reading matches the server (grid and voxel size) — shown from the original data in voxel order.')}
            </span>
          </div>
        )}
        {clientStatus?.notes?.length ? (
          <div className="mt-2 flex items-start gap-2 rounded-md border border-clinical-warn/30 bg-clinical-warn/10 p-2 text-xs text-clinical-warn">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            <span>{clientStatus.notes.join(' · ')}</span>
          </div>
        ) : null}
      </Card>
    </div>
  );
}

export function InsightsPanel({
  renderMode, clientStatus, onReportGenerated, annotate, segmentationMode,
}: {
  renderMode: RenderMode;
  clientStatus: ClientViewportStatus | null;
  onReportGenerated: (report: ReportResponse) => void;
  /** Segmentation editing tools (ViewerControls). */
  annotate: React.ReactNode;
  /** Segmentation editing context is on (sidebar row opened, Create, Edit). */
  segmentationMode: boolean;
}) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('image');
  // Bring the tools forward when the user starts editing (Create / Edit in the image).
  const isPaintMode = useSegmentationStore((s) => s.isPaintMode);
  const wasPainting = useRef(isPaintMode);
  useEffect(() => {
    if (isPaintMode && !wasPainting.current) setTab('annotate');
    wasPainting.current = isPaintMode;
  }, [isPaintMode]);
  const currentPatientId = useViewerStore((s) => s.currentPatientId);

  const { data: patientStudies } = useQuery({
    queryKey: ['studies', 'patient', currentPatientId],
    queryFn: async () => {
      if (!currentPatientId) return [] as StudySummary[];
      const result = await studyAPI.listByPatient(currentPatientId);
      return result.items;
    },
    enabled: !!currentPatientId,
  });
  const sortedStudies = useMemo(
    () => [...(patientStudies ?? [])].sort((a, b) => new Date(b.study_date).getTime() - new Date(a.study_date).getTime()),
    [patientStudies],
  );

  return (
    <div className="flex h-full flex-col">
      <Tabs
        idPrefix="insights"
        ariaLabel={t('viewer3.insights', 'Image and analysis')}
        value={tab}
        onChange={setTab}
        className="shrink-0 border-b border-surface-border px-1"
        items={[
          { value: 'image', label: t('viewer3.tab.image', 'Image') },
          {
            value: 'annotate',
            label: t('viewer3.tab.annotate', 'Annotate'),
            // Dot = segmentation editing context is on.
            icon: segmentationMode ? <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-brand-400" /> : undefined,
          },
          { value: 'analysis', label: t('viewer3.tab.analysis', 'Analysis') },
          { value: 'report', label: t('viewer3.tab.report', 'Report') },
        ]}
      />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <TabPanel idPrefix="insights" value="image" current={tab}>
          <ImageTab renderMode={renderMode} clientStatus={clientStatus} />
        </TabPanel>
        <TabPanel idPrefix="insights" value="annotate" current={tab} className="p-3">
          {annotate}
        </TabPanel>
        <TabPanel idPrefix="insights" value="analysis" current={tab} className="space-y-3 p-3">
          {sortedStudies.length > 1 && (
            <section className="rounded-lg border border-surface-border bg-surface-base p-3">
              <LongitudinalCompare studies={sortedStudies} />
            </section>
          )}
          <section className="rounded-lg border border-surface-border bg-surface-base p-3">
            {/* Self-hides unless the study has ≥ 2 segmentations to compare. */}
            <SegmentationComparison />
          </section>
          {sortedStudies.length <= 1 && (
            <p className="px-1 text-xs leading-relaxed text-ink-muted">
              {t('viewer3.noLongitudinal', 'Longitudinal comparison appears when this patient has more than one study.')}
            </p>
          )}
        </TabPanel>
        <TabPanel idPrefix="insights" value="report" current={tab} className="p-3">
          <AIReportPanel onReportGenerated={onReportGenerated} />
        </TabPanel>
      </div>
    </div>
  );
}

export default InsightsPanel;
