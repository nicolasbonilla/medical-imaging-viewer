/**
 * ViewerControls — the annotation dock at the bottom of the study rail (v3).
 * Segmentation editing on/off, the paint-tool panel and (parcellations only) brain
 * volumetry. Render path and window/level moved to the workspace toolbar / image
 * panel; the matplotlib-only colour-map and axis-limit options stay here, shown only
 * when that server render path is active. Props unchanged.
 */
import { useTranslation } from 'react-i18next';
import { PenTool } from 'lucide-react';
import { SegmentationPanel } from './SegmentationPanel';
import { BrainVolumetryPanel } from './BrainVolumetryPanel';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { useViewerStore } from '@/store/useViewerStore';
import type { RenderMode } from '@/hooks/useViewerControls';
import { Button, Switch } from './ui';

interface ViewerControlsProps {
  renderMode: RenderMode;
  setRenderMode: (mode: RenderMode) => void;
  colormap: string;
  setColormap: (colormap: string) => void;
  segmentationMode: boolean;
  setSegmentationMode: (mode: boolean) => void;
  xMin: string;
  setXMin: (val: string) => void;
  xMax: string;
  setXMax: (val: string) => void;
  yMin: string;
  setYMin: (val: string) => void;
  yMax: string;
  setYMax: (val: string) => void;
  appliedXMin: string;
  setAppliedXMin: (val: string) => void;
  appliedXMax: string;
  setAppliedXMax: (val: string) => void;
  appliedYMin: string;
  setAppliedYMin: (val: string) => void;
  appliedYMax: string;
  setAppliedYMax: (val: string) => void;
  onNavigateToSlice?: (sliceIndex: number) => void;
  /** Current view mode — controls which sections are visible */
  viewMode?: '2d' | '3d';
}

const fieldCls =
  'h-8 w-full rounded-md border border-surface-border bg-surface-raised px-2 text-xs tabular-nums text-ink-base ' +
  'placeholder-ink-faint focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60';

export default function ViewerControls({
  renderMode,
  colormap,
  setColormap,
  segmentationMode,
  setSegmentationMode,
  xMin, setXMin, xMax, setXMax, yMin, setYMin, yMax, setYMax,
  setAppliedXMin, setAppliedXMax, setAppliedYMin, setAppliedYMax,
  viewMode = '2d',
}: ViewerControlsProps) {
  const { t } = useTranslation();
  const currentSeries = useViewerStore((s) => s.currentSeries);
  const activeSegmentation = useSegmentationStore((s) => s.activeSegmentation);

  if (!currentSeries) return null;

  // Only show volumetry for parcellations (FreeSurfer labels have IDs > 6);
  // lesion / MAGNIMS masks use labels 0-6 only.
  const hasFreeSurferLabels = !!activeSegmentation?.labels?.some((l) => l.id > 6);

  return (
    <div className="space-y-3">
      {viewMode === '2d' && renderMode === 'matplotlib' && (
        <section className="space-y-2.5 rounded-lg border border-surface-border bg-surface-base p-3">
          <h3 className="text-xs font-medium uppercase tracking-wide text-ink-faint">
            {t('viewer3.serverRender', 'Server render options')}
          </h3>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-muted">{t('viewer.colormap', 'Colormap')}</span>
            <select value={colormap} onChange={(e) => setColormap(e.target.value)} className={fieldCls}>
              <option value="gray">{t('viewer.gray')}</option>
              <option value="viridis">{t('viewer.viridis')}</option>
              <option value="plasma">{t('viewer.plasma')}</option>
              <option value="inferno">{t('viewer.inferno')}</option>
              <option value="magma">{t('viewer.magma')}</option>
              <option value="hot">{t('viewer.hot')}</option>
              <option value="cool">{t('viewer.cool')}</option>
              <option value="jet">{t('viewer.jet')}</option>
            </select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <input type="number" aria-label={`${t('viewer.xAxis')} ${t('viewer.min')}`} placeholder={`${t('viewer.xAxis')} ${t('viewer.min')}`} value={xMin} onChange={(e) => setXMin(e.target.value)} className={fieldCls} />
            <input type="number" aria-label={`${t('viewer.xAxis')} ${t('viewer.max')}`} placeholder={`${t('viewer.xAxis')} ${t('viewer.max')}`} value={xMax} onChange={(e) => setXMax(e.target.value)} className={fieldCls} />
            <input type="number" aria-label={`${t('viewer.yAxis')} ${t('viewer.min')}`} placeholder={`${t('viewer.yAxis')} ${t('viewer.min')}`} value={yMin} onChange={(e) => setYMin(e.target.value)} className={fieldCls} />
            <input type="number" aria-label={`${t('viewer.yAxis')} ${t('viewer.max')}`} placeholder={`${t('viewer.yAxis')} ${t('viewer.max')}`} value={yMax} onChange={(e) => setYMax(e.target.value)} className={fieldCls} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Button size="sm" variant="primary"
              onClick={() => { setAppliedXMin(xMin); setAppliedXMax(xMax); setAppliedYMin(yMin); setAppliedYMax(yMax); }}>
              {t('viewer.apply')}
            </Button>
            <Button size="sm" variant="secondary"
              onClick={() => { setXMin(''); setXMax(''); setYMin(''); setYMax(''); setAppliedXMin(''); setAppliedXMax(''); setAppliedYMin(''); setAppliedYMax(''); }}>
              {t('viewer.reset')}
            </Button>
          </div>
        </section>
      )}

      <div className="rounded-lg border border-surface-border bg-surface-base px-3 py-2.5">
        <Switch
          checked={segmentationMode}
          onChange={setSegmentationMode}
          label={
            <span className="inline-flex items-center gap-2 text-xs font-medium text-ink-base">
              <PenTool className="h-3.5 w-3.5 text-ink-muted" aria-hidden />
              {segmentationMode ? t('viewer.segmentationMode') : t('viewer.activateSegmentation')}
            </span>
          }
        />
      </div>

      {segmentationMode && <SegmentationPanel />}

      {segmentationMode && activeSegmentation && hasFreeSurferLabels && (
        <BrainVolumetryPanel segmentationId={activeSegmentation.id} />
      )}
    </div>
  );
}
