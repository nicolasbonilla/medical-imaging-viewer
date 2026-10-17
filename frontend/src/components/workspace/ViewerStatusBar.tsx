/**
 * ViewerStatusBar — the quiet clinical read-out under the image: where the cursor is
 * (voxel, scanner mm), what is there (full-precision value, segmentation label), and
 * how it is shown (plane, slice thickness, window, zoom, render path). Tabular numerals.
 */
import { useTranslation } from 'react-i18next';
import { useViewerStore } from '@/store/useViewerStore';
import type { RenderMode } from '@/hooks/useViewerControls';
import type { ClientViewportStatus } from '../viewer2d/ClientSliceViewport';
import { effectiveWindow, formatIntensity } from './windowPresets';

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <span className="flex items-baseline gap-1.5 whitespace-nowrap">
      <span className="text-ink-faint">{label}</span>
      <span className="tabular-nums text-ink-soft">{children}</span>
    </span>
  );
}

export function ViewerStatusBar({
  renderMode, clientStatus, viewMode,
}: { renderMode: RenderMode; clientStatus: ClientViewportStatus | null; viewMode: '2d' | '3d' }) {
  const { t } = useTranslation();
  const cursor = useViewerStore((s) => s.cursorInfo);
  const zoom = useViewerStore((s) => s.zoomLevel);
  const plane = useViewerStore((s) => s.slicePlane);
  const wc = useViewerStore((s) => s.windowCenter);
  const ww = useViewerStore((s) => s.windowWidth);
  const series = useViewerStore((s) => s.currentSeries);
  const isClient = renderMode === 'client' && viewMode === '2d';
  const view = isClient ? clientStatus?.views?.[plane] : null;
  const stats = clientStatus?.volume?.stats;
  const wl = isClient && stats ? effectiveWindow(wc, ww, stats) : null;

  const pathLabel = viewMode === '3d'
    ? t('viewer3.path.3d', '3D · GPU (niivue)')
    : renderMode === 'client'
      ? t('viewer3.path.client', 'In-browser · full bit depth')
      : renderMode === 'standard'
        ? t('viewer3.path.standard', 'Server images · 8-bit')
        : renderMode === 'matplotlib'
          ? t('viewer3.path.matplotlib', 'Server render')
          : t('viewer3.path.niivue', 'GPU · view only');

  const spacing = view
    ? `${view.colSpacing.toFixed(2)} × ${view.rowSpacing.toFixed(2)} · ${view.sliceSpacing.toFixed(2)} mm`
    : Array.isArray(series?.metadata?.pixel_spacing) && series?.metadata?.pixel_spacing.length
      ? `${series.metadata.pixel_spacing.map((v) => v.toFixed(2)).join(' × ')} mm`
      : null;

  return (
    <div
      className="flex h-8 shrink-0 items-center gap-5 overflow-hidden border-t border-surface-border bg-surface-base px-3 text-xs"
      aria-label={t('viewer3.statusBar', 'Image read-out')}
    >
      {viewMode === '2d' && cursor ? (
        <>
          {cursor.voxel ? (
            <Item label={t('viewer3.voxel', 'Voxel')}>{cursor.voxel.join(', ')}</Item>
          ) : (
            <Item label="x, y, z">{`${cursor.x}, ${cursor.y}, ${cursor.z}`}</Item>
          )}
          {cursor.world && (
            <Item label="mm">{cursor.world.map((v) => v.toFixed(1)).join(', ')}</Item>
          )}
          <Item label={t('viewer3.value', 'Value')}>
            {cursor.value !== undefined ? formatIntensity(cursor.value) : (cursor.intensity ?? '—')}
          </Item>
          {cursor.label !== undefined && (
            <Item label={t('viewer3.label', 'Label')}>{cursor.label === 0 ? '—' : cursor.label}</Item>
          )}
        </>
      ) : (
        <span className="min-w-0 truncate text-ink-faint">
          {viewMode === '2d'
            ? t('viewer3.hoverHint', 'Wheel: slice · Ctrl+wheel: zoom · right-drag: window')
            : t('viewer3.hint3d', 'Drag to rotate · wheel to zoom · right-drag to pan')}
        </span>
      )}
      <span className="ml-auto flex shrink-0 items-center gap-5">
        {wl && <Item label="W/L">{`${formatIntensity(wl.width)} / ${formatIntensity(wl.center)}`}</Item>}
        {viewMode === '2d' && <Item label={t('viewer3.zoom', 'Zoom')}>{`${Math.round(zoom * 100)}%`}</Item>}
        {spacing && <Item label={t('viewer3.spacing', 'Voxel')}>{spacing}</Item>}
        <span className="flex items-center gap-1.5 whitespace-nowrap text-ink-muted">
          <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${renderMode === 'client' || viewMode === '3d' ? 'bg-clinical-good' : 'bg-clinical-warn'}`} />
          {pathLabel}
        </span>
      </span>
    </div>
  );
}

export default ViewerStatusBar;
