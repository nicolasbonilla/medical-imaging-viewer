/**
 * WorkspaceToolbar — the single control strip above the image (v3 workspace).
 * View (2D/3D) · plane · slice · zoom · window/level · measurement tools · layout ·
 * display options (render path, orientation, interpolation). Every icon-only control
 * has an accessible name (IconButton requires one).
 */
import { useTranslation } from 'react-i18next';
import {
  ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Ruler, Triangle, Circle, Trash2,
  Square, Columns2, LayoutGrid, Link2, Unlink2, SlidersHorizontal, Contrast, ChevronDown,
} from 'lucide-react';
import { useViewerStore } from '@/store/useViewerStore';
import { useActiveSliceInfo } from '@/hooks/useActiveSliceInfo';
import type { RenderMode } from '@/hooks/useViewerControls';
import type { ViewerLayout } from '@/store/useMultiViewerStore';
import type { ClientViewportStatus } from '../viewer2d/ClientSliceViewport';
import type { PlaneName } from '@/volume/sliceGeometry';
import { IconButton, Menu, MenuItem, MenuLabel, MenuSeparator, SegmentedControl, Switch } from '../ui';
import { clientPresets, effectiveWindow, formatIntensity, type PresetId } from './windowPresets';

export interface WorkspaceToolbarProps {
  viewMode: '2d' | '3d';
  onViewModeChange: (mode: '2d' | '3d') => void;
  renderMode: RenderMode;
  onRenderModeChange: (mode: RenderMode) => void;
  clientStatus: ClientViewportStatus | null;
  serverSeed: { center?: number | null; width?: number | null };
  layoutAvailable: boolean;
  layout: ViewerLayout;
  onLayoutChange: (layout: ViewerLayout) => void;
  syncSlice: boolean;
  onSyncChange: (sync: boolean) => void;
}

function Divider() {
  return <span aria-hidden className="mx-0.5 h-5 w-px shrink-0 bg-surface-border" />;
}

export function WorkspaceToolbar({
  viewMode, onViewModeChange, renderMode, onRenderModeChange, clientStatus, serverSeed,
  layoutAvailable, layout, onLayoutChange, syncSlice, onSyncChange,
}: WorkspaceToolbarProps) {
  const { t } = useTranslation();
  const slice = useActiveSliceInfo();
  const slicePlane = useViewerStore((s) => s.slicePlane);
  const setSlicePlane = useViewerStore((s) => s.setSlicePlane);
  const zoomLevel = useViewerStore((s) => s.zoomLevel);
  const setZoomLevel = useViewerStore((s) => s.setZoomLevel);
  const setPanOffset = useViewerStore((s) => s.setPanOffset);
  const measurementTool = useViewerStore((s) => s.measurementTool);
  const setMeasurementTool = useViewerStore((s) => s.setMeasurementTool);
  const triggerMeasurementClear = useViewerStore((s) => s.triggerMeasurementClear);
  const windowCenter = useViewerStore((s) => s.windowCenter);
  const windowWidth = useViewerStore((s) => s.windowWidth);
  const setWindowLevel = useViewerStore((s) => s.setWindowLevel);
  const orientationMode = useViewerStore((s) => s.orientationMode);
  const setOrientationMode = useViewerStore((s) => s.setOrientationMode);
  const smoothDisplay = useViewerStore((s) => s.smoothDisplay);
  const setSmoothDisplay = useViewerStore((s) => s.setSmoothDisplay);

  const is2D = viewMode === '2d';
  const isClient = renderMode === 'client';
  const anatomical = !!clientStatus?.anatomical;
  const stats = clientStatus?.volume?.stats ?? null;
  const isMulti = layout !== 'single';

  const planeLabel = (p: PlaneName) => anatomical
    ? t(`viewer3.plane.${p}`, p.charAt(0).toUpperCase() + p.slice(1))
    : t(`viewer3.voxelAxis.${p}`, { axial: 'k', coronal: 'j', sagittal: 'i' }[p]);

  const presetLabel: Record<PresetId, string> = {
    auto: t('viewer3.wl.auto', 'Auto (robust range)'),
    full: t('viewer3.wl.full', 'Full range (as server image)'),
    server: t('viewer3.wl.server', 'Server window (2–98 %)'),
  };
  const presets = stats ? clientPresets(stats, serverSeed) : [];
  const wl = stats ? effectiveWindow(windowCenter, windowWidth, stats) : null;
  const wlActiveLegacy = !isClient && windowWidth > 0;

  const step = (d: number) => slice.setSliceIndex(Math.max(0, Math.min(slice.totalSlices - 1, slice.sliceIndex + d)));
  const toggleTool = (tool: 'ruler' | 'angle' | 'ellipse') => setMeasurementTool(measurementTool === tool ? null : tool);

  return (
    <div
      role="toolbar"
      aria-label={t('viewer3.toolbar', 'Image tools')}
      className="flex h-12 shrink-0 items-center gap-1.5 overflow-x-auto whitespace-nowrap border-b border-surface-border bg-surface-base px-3"
    >
      <SegmentedControl
        ariaLabel={t('viewer3.viewMode', 'View mode')}
        value={viewMode}
        onChange={onViewModeChange}
        options={[
          { value: '2d', label: '2D' },
          { value: '3d', label: '3D' },
        ]}
      />

      {is2D && isClient && !isMulti && (
        <>
          <Divider />
          <SegmentedControl
            ariaLabel={t('viewer3.plane.label', 'Plane')}
            value={slicePlane}
            onChange={setSlicePlane}
            options={(['axial', 'coronal', 'sagittal'] as PlaneName[]).map((p) => ({
              value: p,
              label: planeLabel(p),
              title: anatomical
                ? t(`viewer3.plane.${p}Title`, `${p} plane`)
                : t('viewer3.voxelAxisTitle', 'Voxel axis — orientation not established, no anatomical claim'),
            }))}
          />
        </>
      )}

      {is2D && (
        <>
          <Divider />
          <div className="flex items-center gap-1" role="group" aria-label={t('viewer3.sliceGroup', 'Slice')}>
            <IconButton size="sm" label={t('viewer3.prevSlice', 'Previous slice')} icon={<ChevronLeft className="h-4 w-4" aria-hidden />}
              onClick={() => step(-1)} disabled={slice.sliceIndex <= 0} />
            <span className="min-w-[4.5rem] text-center text-xs font-medium tabular-nums text-ink-soft" aria-live="polite">
              {slice.totalSlices > 0 ? `${slice.sliceIndex + 1} / ${slice.totalSlices}` : '—'}
            </span>
            <IconButton size="sm" label={t('viewer3.nextSlice', 'Next slice')} icon={<ChevronRight className="h-4 w-4" aria-hidden />}
              onClick={() => step(1)} disabled={slice.sliceIndex >= slice.totalSlices - 1} />
            {/* Long-range navigation: the vertical stack scrollbar on the image edge. */}
          </div>

          <Divider />
          <div className="flex items-center gap-0.5" role="group" aria-label={t('viewer3.zoomGroup', 'Zoom')}>
            <IconButton size="sm" label={t('viewer.zoomOut', 'Zoom out')} icon={<ZoomOut className="h-4 w-4" aria-hidden />}
              onClick={() => setZoomLevel(Math.max(0.25, zoomLevel / 1.2))} />
            <button
              type="button"
              onClick={() => { setZoomLevel(1); setPanOffset({ x: 0, y: 0 }); }}
              aria-label={t('viewer3.fitZoom', 'Zoom {{z}} % — click to fit the image', { z: Math.round(zoomLevel * 100) })}
              title={t('viewer3.fit', 'Fit to window')}
              className="h-7 min-w-[3rem] rounded-md px-1 text-xs tabular-nums text-ink-muted hover:bg-surface-hover hover:text-ink-base focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
            >
              {Math.round(zoomLevel * 100)}%
            </button>
            <IconButton size="sm" label={t('viewer.zoomIn', 'Zoom in')} icon={<ZoomIn className="h-4 w-4" aria-hidden />}
              onClick={() => setZoomLevel(Math.min(20, zoomLevel * 1.2))} />
          </div>

          {(isClient || renderMode === 'matplotlib' || renderMode === 'niivue') && (
            <>
              <Divider />
              <Menu
                trigger={(p) => (
                  <button
                    type="button"
                    {...p}
                    className="inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md px-2 text-xs text-ink-soft transition-colors hover:bg-surface-hover hover:text-ink-base focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
                    aria-label={t('viewer3.wl.menu', 'Window / level')}
                  >
                    <Contrast className="h-4 w-4 text-ink-muted" aria-hidden />
                    <span className="tabular-nums">
                      {isClient && wl
                        ? `C ${formatIntensity(wl.center)} · W ${formatIntensity(wl.width)}`
                        : wlActiveLegacy
                          ? `C ${Math.round(windowCenter)} · W ${Math.round(windowWidth)}`
                          : t('viewer.wlAuto', 'Auto (full range)')}
                    </span>
                    <ChevronDown className="h-3.5 w-3.5 text-ink-faint" aria-hidden />
                  </button>
                )}
              >
                {(close) => (
                  <>
                    <MenuLabel>{t('viewer3.wl.presets', 'Window presets')}</MenuLabel>
                    {isClient ? presets.map((p) => (
                      <MenuItem
                        key={p.id}
                        radio
                        checked={p.id === 'auto' ? windowWidth <= 0 : windowWidth > 0 && Math.abs(windowCenter - p.wl.center) < 1e-9 && Math.abs(windowWidth - p.wl.width) < 1e-9}
                        description={`C ${formatIntensity(p.wl.center)} · W ${formatIntensity(p.wl.width)}`}
                        onSelect={() => { if (p.id === 'auto') setWindowLevel(0, 0); else setWindowLevel(p.wl.center, p.wl.width); close(); }}
                      >
                        {presetLabel[p.id]}
                      </MenuItem>
                    )) : (
                      <>
                        <MenuItem
                          radio
                          checked={wlActiveLegacy && windowCenter === serverSeed.center && windowWidth === serverSeed.width}
                          disabled={serverSeed.center == null || !(serverSeed.width && serverSeed.width > 0)}
                          onSelect={() => { setWindowLevel(serverSeed.center as number, serverSeed.width as number); close(); }}
                        >
                          {t('viewer.wlOptimal', 'Optimal')}
                        </MenuItem>
                        <MenuItem radio checked={!wlActiveLegacy} onSelect={() => { setWindowLevel(0, 0); close(); }}>
                          {t('viewer.wlReset', 'Full range')}
                        </MenuItem>
                      </>
                    )}
                    {isClient && (
                      <p className="px-2.5 pb-1.5 pt-2 text-xs text-ink-muted">
                        {t('viewer3.wl.dragHint', 'Tip: right-drag on the image adjusts the window (horizontal = width, vertical = level).')}
                      </p>
                    )}
                  </>
                )}
              </Menu>
            </>
          )}

          {!isMulti && (
            <>
              <Divider />
              <div className="flex items-center gap-0.5" role="group" aria-label={t('viewer3.measure', 'Measurements')}>
                <IconButton size="sm" label={t('viewer3.ruler', 'Ruler (distance in mm)')} active={measurementTool === 'ruler'}
                  icon={<Ruler className="h-4 w-4" aria-hidden />} onClick={() => toggleTool('ruler')} />
                <IconButton size="sm" label={t('viewer3.angle', 'Angle')} active={measurementTool === 'angle'}
                  icon={<Triangle className="h-4 w-4" aria-hidden />} onClick={() => toggleTool('angle')} />
                <IconButton size="sm" label={t('viewer3.roi', 'Elliptical ROI (area in mm²)')} active={measurementTool === 'ellipse'}
                  icon={<Circle className="h-4 w-4" aria-hidden />} onClick={() => toggleTool('ellipse')} />
                <IconButton size="sm" tone="danger" label={t('viewer.clearMeasurements', 'Clear measurements')}
                  icon={<Trash2 className="h-4 w-4" aria-hidden />} onClick={triggerMeasurementClear} />
              </div>
            </>
          )}

          {layoutAvailable && (
            <>
              <Divider />
              <Menu
                align="end"
                trigger={(p) => (
                  <button
                    type="button"
                    {...p}
                    aria-label={t('viewer3.layout', 'Panel layout')}
                    title={t('viewer3.layout', 'Panel layout')}
                    className="inline-flex h-8 shrink-0 items-center gap-1 rounded-md px-1.5 text-ink-muted hover:bg-surface-hover hover:text-ink-base focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
                  >
                    {layout === '2x2' ? <LayoutGrid className="h-4 w-4" aria-hidden /> : layout === '1x2' ? <Columns2 className="h-4 w-4" aria-hidden /> : <Square className="h-4 w-4" aria-hidden />}
                    <ChevronDown className="h-3.5 w-3.5 text-ink-faint" aria-hidden />
                  </button>
                )}
              >
                {(close) => (
                  <>
                    <MenuLabel>{t('viewer3.layout', 'Panel layout')}</MenuLabel>
                    {([
                      ['single', t('layout.single', 'Single View'), <Square key="s" className="h-4 w-4" aria-hidden />],
                      ['1x2', t('layout.sideBySide', '1x2 Side by Side'), <Columns2 key="c" className="h-4 w-4" aria-hidden />],
                      ['2x2', t('layout.grid', '2x2 Grid'), <LayoutGrid key="g" className="h-4 w-4" aria-hidden />],
                    ] as const).map(([value, label, icon]) => (
                      <MenuItem key={value} radio checked={layout === value} onSelect={() => { onLayoutChange(value); close(); }}>
                        <span className="inline-flex items-center gap-2">{icon}{label}</span>
                      </MenuItem>
                    ))}
                  </>
                )}
              </Menu>
              {isMulti && (
                <IconButton size="sm" active={syncSlice}
                  label={syncSlice ? t('viewer3.syncOn', 'Slices linked — click to unlink') : t('viewer3.syncOff', 'Slices independent — click to link')}
                  icon={syncSlice ? <Link2 className="h-4 w-4" aria-hidden /> : <Unlink2 className="h-4 w-4" aria-hidden />}
                  onClick={() => onSyncChange(!syncSlice)} />
              )}
            </>
          )}
        </>
      )}

      <div className="ml-auto flex items-center">
        <Menu
          align="end"
          trigger={(p) => (
            <IconButton {...p} label={t('viewer3.display', 'Display options')} icon={<SlidersHorizontal className="h-4 w-4" aria-hidden />} />
          )}
        >
          {(close) => (
            <div className="w-72">
              <MenuLabel>{t('viewer3.renderPath', '2D rendering')}</MenuLabel>
              <MenuItem radio checked={renderMode === 'client'} onSelect={() => { onRenderModeChange('client'); close(); }}
                description={t('viewer3.render.clientDesc', 'From the original volume in your browser: full bit depth, instant window/level, three planes.')}>
                {t('viewer3.render.client', 'In-browser (recommended)')}
              </MenuItem>
              <MenuItem radio checked={renderMode === 'standard'} onSelect={() => { onRenderModeChange('standard'); close(); }}
                description={t('viewer3.render.standardDesc', 'Previous server pipeline (8-bit images), kept as fallback.')}>
                {t('viewer3.render.standard', 'Server images (legacy)')}
              </MenuItem>
              <MenuItem radio checked={renderMode === 'matplotlib'} onSelect={() => { onRenderModeChange('matplotlib'); close(); }}
                description={t('viewer3.render.matplotlibDesc', 'Server-rendered slice with colour maps and axis limits.')}>
                {t('viewer3.render.matplotlib', 'Server render (matplotlib)')}
              </MenuItem>
              <MenuItem radio checked={renderMode === 'niivue'} onSelect={() => { onRenderModeChange('niivue'); close(); }}
                description={t('viewer3.render.niivueDesc', 'GPU window/level, axial only, view only.')}>
                {t('viewer3.render.niivue', 'GPU viewer (view only)')}
              </MenuItem>
              {isClient && (
                <>
                  <MenuSeparator />
                  <MenuLabel>{t('viewer3.orientationLabel', 'Orientation')}</MenuLabel>
                  <MenuItem radio checked={orientationMode === 'anatomical' && anatomical} disabled={!clientStatus?.anatomical && orientationMode !== 'anatomical'}
                    onSelect={() => { setOrientationMode('anatomical'); close(); }}
                    description={anatomical || orientationMode !== 'anatomical'
                      ? t('viewer3.orientation.anatomicalDesc', 'Axial / coronal / sagittal from the image affine, same convention as the 3D view.')
                      : t('viewer3.orientation.unavailable', 'Not available: the orientation of this image is not established.')}>
                    {t('viewer3.orientation.anatomical', 'Anatomical')}
                  </MenuItem>
                  <MenuItem radio checked={orientationMode === 'voxel' || !anatomical}
                    onSelect={() => { setOrientationMode('voxel'); close(); }}
                    description={t('viewer3.orientation.voxelDesc', 'Rows and columns exactly as stored — the layout of the server images.')}>
                    {t('viewer3.orientation.voxel', 'Voxel order')}
                  </MenuItem>
                  <MenuSeparator />
                  <div className="px-2.5 py-2">
                    <Switch checked={smoothDisplay} onChange={setSmoothDisplay}
                      label={t('viewer3.smooth', 'Smooth display (overlays stay voxel-exact)')} />
                  </div>
                </>
              )}
            </div>
          )}
        </Menu>
      </div>
    </div>
  );
}

export default WorkspaceToolbar;
