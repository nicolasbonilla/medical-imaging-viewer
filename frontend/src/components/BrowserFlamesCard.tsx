/**
 * BrowserFlamesCard — "Segment in this browser" entry point for the FLAMeS prototype.
 * Rendered ONLY when FEATURES.BROWSER_FLAMES (VITE_ENABLE_BROWSER_FLAMES=true); default OFF.
 *
 * The result is never shown or saved automatically: the clinician opens it as a LOCAL, unsaved,
 * orange "AI draft" segmentation over the exact FLAIR it was computed from (grid-checked), edits it,
 * and only an explicit Save persists it (with the provenance stamp as description).
 */
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useBrowserFlames } from '@/hooks/useBrowserFlames';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { checkDraftGrid, draftDescription, DRAFT_LABELS } from '@/services/flames/draft';

interface BrowserFlamesCardProps {
  flairFileId: string;
}

export const BrowserFlamesCard: React.FC<BrowserFlamesCardProps> = ({ flairFileId }) => {
  const { t } = useTranslation();
  const flames = useBrowserFlames();
  const currentSeries = useViewerStore((s) => s.currentSeries);
  const importDraft = useSegmentationStore((s) => s.importDraftCallback);
  const [opened, setOpened] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);

  const running = flames.status === 'running';
  const grid = flames.result ? checkDraftGrid(flames.result.fileId, flames.result.dims, currentSeries) : null;

  const handleRun = () => {
    setOpened(false);
    setOpenError(null);
    void flames.run(flairFileId);
  };

  const handleOpenDraft = () => {
    const r = flames.result;
    if (!r || !grid || !grid.ok) return;
    if (!importDraft) {
      setOpenError(t('clinical.browserFlames.noViewer', 'The 2D viewer is not ready; open the image first.'));
      return;
    }
    const ok = importDraft(r.fileId, grid.shape, r.maskApp, {
      description: draftDescription(r.provenance, r.summary),
      labels: DRAFT_LABELS,
    });
    if (ok) setOpened(true);
    else setOpenError(t('clinical.browserFlames.importFailed', 'The draft does not match the image grid and was not opened.'));
  };

  return (
    <div className="mt-2 rounded border border-amber-600/40 bg-amber-950/20 p-2 space-y-1.5" data-testid="browser-flames-card">
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] font-semibold text-amber-200">
          {t('clinical.browserFlames.title', 'Run in this browser')}
        </span>
        <span className="text-[8px] uppercase tracking-wide px-1 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
          {t('clinical.browserFlames.prototype', 'Prototype')}
        </span>
      </div>
      <p className="text-[9px] text-gray-400 leading-snug">
        {t(
          'clinical.browserFlames.desc',
          'Runs FLAMeS on this computer; the image never leaves the browser. Needs a skull-stripped FLAIR. The first run downloads a 62 MB model. Result = unreviewed AI draft.',
        )}
      </p>

      {!running && (
        <button
          onClick={handleRun}
          disabled={!flairFileId}
          className="w-full px-3 py-1.5 bg-amber-700 hover:bg-amber-600 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-[11px] font-medium transition-colors"
        >
          {t('clinical.browserFlames.run', 'Segment in this browser')}
        </button>
      )}

      {running && (
        <div className="space-y-1" role="status" aria-live="polite">
          <div className="w-full bg-gray-700 rounded-full h-1.5">
            <div className="h-1.5 rounded-full bg-amber-500 transition-all" style={{ width: `${Math.max(2, flames.fraction * 100)}%` }} />
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-[9px] text-amber-200 truncate">{flames.message}</span>
            <button onClick={flames.cancel} className="text-[9px] text-gray-300 underline hover:text-white">
              {t('clinical.browserFlames.cancel', 'Cancel')}
            </button>
          </div>
        </div>
      )}

      {flames.status === 'error' && flames.error && (
        <p className="text-[10px] text-red-300 bg-red-900/30 rounded p-1.5 break-words" role="alert">
          {t('clinical.browserFlames.failed', 'No segmentation was produced')}: {flames.error}
        </p>
      )}

      {flames.status === 'done' && flames.result && (
        <div className="space-y-1">
          <p className="text-[10px] text-amber-100">
            {t('clinical.browserFlames.summary', 'AI draft ready')}: {flames.result.summary.lesionCount}{' '}
            {t('clinical.browserFlames.lesions', 'lesions')}, {flames.result.summary.lesionVolumeMl.toFixed(1)} mL ·{' '}
            {flames.result.provenance.seconds.toFixed(0)} s ·{' '}
            {flames.result.provenance.backend === 'webgpu' ? 'WebGPU' : `WebAssembly ×${flames.result.provenance.threads}`}
          </p>
          {grid && !grid.ok && <p className="text-[9px] text-amber-300">{grid.reason}</p>}
          {!opened ? (
            <button
              onClick={handleOpenDraft}
              disabled={!grid?.ok}
              className="w-full px-3 py-1.5 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed text-amber-100 rounded text-[11px] border border-amber-600/50"
            >
              {t('clinical.browserFlames.open', 'Open as AI draft for review')}
            </button>
          ) : (
            <p className="text-[9px] text-amber-200">
              {t(
                'clinical.browserFlames.opened',
                'Draft opened in orange. Review and correct it; nothing is saved until you press Save.',
              )}
            </p>
          )}
          {openError && <p className="text-[9px] text-red-300">{openError}</p>}
        </div>
      )}
    </div>
  );
};

export default BrowserFlamesCard;
