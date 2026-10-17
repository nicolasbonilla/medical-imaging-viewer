/**
 * Inline overlay controls for the active segmentation (moved out of ViewerApp, v3):
 * visibility, opacity, label preset and per-label visibility. Same store actions as
 * before — presentation only.
 */
import { useTranslation } from 'react-i18next';
import { Eye, EyeOff } from 'lucide-react';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { detectLabelPreset } from '@/utils/labelPresets';
import { Switch } from '../ui';

export function OverlayControls() {
  const { t } = useTranslation();
  const isOverlayVisible = useSegmentationStore((s) => s.isOverlayVisible);
  const setIsOverlayVisible = useSegmentationStore((s) => s.setIsOverlayVisible);
  const lesionOpacity = useSegmentationStore((s) => s.lesionOpacity);
  const setLesionOpacity = useSegmentationStore((s) => s.setLesionOpacity);
  const labels = useSegmentationStore((s) => s.activeSegmentation?.labels);
  const labelVisibility = useSegmentationStore((s) => s.labelVisibility);
  const toggleLabelVisibility = useSegmentationStore((s) => s.toggleLabelVisibility);
  const fg = (labels ?? []).filter((l) => l.id !== 0);

  return (
    <div className="space-y-3 rounded-lg border border-surface-border bg-surface-base p-3">
      <Switch
        checked={isOverlayVisible}
        onChange={setIsOverlayVisible}
        label={t('segmentation.showOverlay', 'Show Overlay')}
      />
      {isOverlayVisible && (
        <>
          <div>
            <div className="mb-1 flex items-center justify-between">
              <label htmlFor="lesion-opacity" className="text-xs text-ink-muted">
                {t('segmentation.lesionOpacity', 'Lesion opacity')}
              </label>
              <span className="text-xs tabular-nums text-ink-soft">{Math.round(lesionOpacity * 100)}%</span>
            </div>
            <input
              id="lesion-opacity"
              type="range"
              min="0"
              max="100"
              value={Math.round(lesionOpacity * 100)}
              onChange={(e) => setLesionOpacity(Number(e.target.value) / 100)}
              className="h-1 w-full cursor-pointer appearance-none rounded-full bg-surface-hover accent-brand-500"
            />
          </div>
          {fg.length > 0 && (
            <>
              <select
                aria-label={t('viewer3.labelPreset', 'Label preset')}
                value={detectLabelPreset(labels)}
                onChange={(e) => {
                  const preset = e.target.value;
                  if (preset === 'default' || preset === 'magnims') {
                    useSegmentationStore.getState().setLabelPreset(preset as 'default' | 'magnims');
                  }
                }}
                className="h-8 w-full rounded-md border border-surface-border bg-surface-raised px-2 text-xs text-ink-base focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
              >
                <option value="default">Default</option>
                <option value="magnims">MAGNIMS Regional</option>
                <option value="custom" disabled>Custom</option>
              </select>
              <ul className="max-h-32 space-y-0.5 overflow-y-auto">
                {fg.map((label) => {
                  const visible = labelVisibility[label.id] !== false;
                  return (
                    <li key={label.id}>
                      <button
                        type="button"
                        onClick={() => toggleLabelVisibility(label.id)}
                        aria-pressed={visible}
                        aria-label={`${label.name}: ${visible ? t('viewer3.visible', 'visible') : t('viewer3.hidden', 'hidden')}`}
                        className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
                      >
                        <span
                          aria-hidden
                          className="h-3 w-3 shrink-0 rounded-sm border border-surface-border"
                          style={{ backgroundColor: visible ? label.color : 'transparent' }}
                        />
                        <span className={`flex-1 truncate text-xs ${visible ? 'text-ink-soft' : 'text-ink-faint line-through'}`}>
                          {label.name}
                        </span>
                        {visible
                          ? <Eye className="h-3.5 w-3.5 shrink-0 text-brand-400" aria-hidden />
                          : <EyeOff className="h-3.5 w-3.5 shrink-0 text-ink-faint" aria-hidden />}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  );
}

export default OverlayControls;
