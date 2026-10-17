/**
 * BrowserFlamesCard — "Segment in this browser" entry point for the FLAMeS prototype.
 * Rendered ONLY when FEATURES.BROWSER_FLAMES (VITE_ENABLE_BROWSER_FLAMES=true); default OFF.
 *
 * Safety behaviour (CP-FLAMES-BROWSER-001):
 *  - honest duration estimate before the run, elapsed time during it, Cancel never touches the
 *    clinician's segmentation (RC-053 / COOP-COEP analysis);
 *  - an empty result is an explicit warning, never a silent "0 lesions" (REQ-FUNC-036);
 *  - the draft opens as a LOCAL, unsaved, orange "AI draft, unreviewed" segmentation over the exact
 *    FLAIR it was computed from (grid-checked), and NEVER discards unsaved work without an explicit
 *    choice (REQ-SAFE-032); only an explicit Save persists it, with its AI provenance (REQ-SAFE-030);
 *  - licence and attribution notices are reachable here (FLAMeS CC BY 4.0, Neurodesk/nnU-Net Apache-2.0).
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useBrowserFlames } from '@/hooks/useBrowserFlames';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import {
  buildAiProvenance,
  checkDraftGrid,
  draftDescription,
  DRAFT_LABELS,
  EMPTY_RESULT_WARNING,
  isEmptyResult,
} from '@/services/flames/draft';
import { FLAMES_FOLD0_MODEL } from '@/services/flames/plan';
import { FLAMES_NOTICES } from '@/services/flames/notices';
import { currentEnvironment, estimateDuration, formatElapsed } from '@/services/flames/runtimeEstimate';

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
  const [pendingDiscard, setPendingDiscard] = useState<string | null>(null);
  const [emptyAcknowledged, setEmptyAcknowledged] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const running = flames.status === 'running';
  const estimate = useMemo(() => estimateDuration(currentEnvironment()), []);
  const grid = flames.result ? checkDraftGrid(flames.result.fileId, flames.result.dims, currentSeries) : null;
  const empty = flames.result ? isEmptyResult(flames.result.summary) : false;

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running]);

  const handleRun = () => {
    setOpened(false);
    setOpenError(null);
    setPendingDiscard(null);
    setEmptyAcknowledged(false);
    // Header evidence for the FLAIR gate: the series description the app holds for THIS file only.
    const seriesDescription =
      currentSeries?.file_id === flairFileId ? currentSeries?.metadata?.series_description ?? null : null;
    void flames.run(flairFileId, { seriesDescription });
  };

  const openDraft = (discardUnsavedWork: boolean) => {
    const r = flames.result;
    if (!r || !grid || !grid.ok) return;
    if (empty && !emptyAcknowledged) return;
    if (!importDraft) {
      setOpenError(t('clinical.browserFlames.noViewer', 'The 2D viewer is not ready; open the image first.'));
      return;
    }
    const outcome = importDraft(
      r.fileId,
      grid.shape,
      r.maskApp,
      {
        description: draftDescription(r.provenance, r.summary),
        labels: DRAFT_LABELS,
        aiProvenance: buildAiProvenance(r.provenance, r.summary, FLAMES_FOLD0_MODEL.fold),
      },
      { discardUnsavedWork },
    );
    if (outcome.ok) {
      setOpened(true);
      setPendingDiscard(null);
    } else if (outcome.reason === 'unsaved-work') {
      setPendingDiscard(outcome.openSegmentationName);
    } else {
      setOpenError(t('clinical.browserFlames.importFailed', 'The draft does not match the image grid and was not opened.'));
    }
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
          'Runs FLAMeS on this computer; the image never leaves the browser. Needs a skull-stripped FLAIR (other sequences are refused). The first run downloads a 62 MB model. Result = unreviewed AI draft.',
        )}
      </p>

      {!running && (
        <>
          <p className="text-[9px] text-amber-200/90" data-testid="browser-flames-estimate">
            {t('clinical.browserFlames.expected', 'Expected duration')}: {estimate.text}{' '}
            {t('clinical.browserFlames.keepWorking', 'You can keep working and cancel at any time; cancelling never changes your segmentation.')}
          </p>
          <button
            onClick={handleRun}
            disabled={!flairFileId}
            className="w-full px-3 py-1.5 bg-amber-700 hover:bg-amber-600 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-[11px] font-medium transition-colors"
          >
            {t('clinical.browserFlames.run', 'Segment in this browser')}
          </button>
        </>
      )}

      {running && (
        <div className="space-y-1" role="status" aria-live="polite">
          <div className="w-full bg-gray-700 rounded-full h-1.5">
            <div className="h-1.5 rounded-full bg-amber-500 transition-all" style={{ width: `${Math.max(2, flames.fraction * 100)}%` }} />
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-[9px] text-amber-200 truncate">{flames.message}</span>
            <button onClick={flames.cancel} className="text-[9px] text-gray-300 underline hover:text-white">
              {t('clinical.browserFlames.cancel', 'Cancel (your segmentation is not affected)')}
            </button>
          </div>
          <p className="text-[9px] text-gray-400" data-testid="browser-flames-elapsed">
            {t('clinical.browserFlames.elapsed', 'Elapsed')}: {formatElapsed(flames.startedAt ? now - flames.startedAt : 0)} ·{' '}
            {t('clinical.browserFlames.expectedShort', 'expected')} {estimate.lowMinutes}-{estimate.highMinutes} min
          </p>
        </div>
      )}

      {flames.status === 'error' && flames.error && (
        <p className="text-[10px] text-red-300 bg-red-900/30 rounded p-1.5 break-words" role="alert">
          {t('clinical.browserFlames.failed', 'No segmentation was produced')}: {flames.error}
        </p>
      )}

      {flames.status === 'done' && flames.result && (
        <div className="space-y-1">
          {empty ? (
            <div className="text-[10px] text-red-200 bg-red-900/40 border border-red-500/50 rounded p-1.5" role="alert" data-testid="browser-flames-empty">
              <p className="font-semibold">{t('clinical.browserFlames.emptyTitle', 'Empty result — no lesion found (0 voxels)')}</p>
              <p>{t('clinical.browserFlames.emptyText', EMPTY_RESULT_WARNING)}</p>
              <label className="flex items-center gap-1 mt-1">
                <input type="checkbox" checked={emptyAcknowledged} onChange={(e) => setEmptyAcknowledged(e.target.checked)} />
                {t('clinical.browserFlames.emptyAck', 'I understand that this empty draft is not a lesion-free result.')}
              </label>
            </div>
          ) : (
            <p className="text-[10px] text-amber-100">
              {t('clinical.browserFlames.summary', 'AI draft ready')}: {flames.result.summary.lesionCount}{' '}
              {t('clinical.browserFlames.lesions', 'lesions')}, {flames.result.summary.lesionVolumeMl.toFixed(1)} mL ·{' '}
              {flames.result.provenance.seconds.toFixed(0)} s ·{' '}
              {flames.result.provenance.backend === 'webgpu' ? 'WebGPU' : `WebAssembly ×${flames.result.provenance.threads}`}
            </p>
          )}
          {grid && !grid.ok && <p className="text-[9px] text-amber-300">{grid.reason}</p>}
          {pendingDiscard !== null && (
            <div className="text-[10px] text-amber-100 bg-amber-900/40 border border-amber-500/50 rounded p-1.5 space-y-1" role="alertdialog" data-testid="browser-flames-unsaved">
              <p>
                {t('clinical.browserFlames.unsavedWork', 'The open segmentation has unsaved changes')}: “{pendingDiscard}”.{' '}
                {t('clinical.browserFlames.unsavedHint', 'Press Save first to keep them. Nothing has been changed.')}
              </p>
              <div className="flex gap-1">
                <button onClick={() => setPendingDiscard(null)} className="flex-1 px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-white">
                  {t('clinical.browserFlames.keepMine', 'Keep my work (do not open)')}
                </button>
                <button onClick={() => openDraft(true)} className="flex-1 px-2 py-1 rounded bg-red-800 hover:bg-red-700 text-white">
                  {t('clinical.browserFlames.discardAndOpen', 'Discard my unsaved changes and open the draft')}
                </button>
              </div>
            </div>
          )}
          {!opened ? (
            pendingDiscard === null && (
              <button
                onClick={() => openDraft(false)}
                disabled={!grid?.ok || (empty && !emptyAcknowledged)}
                className="w-full px-3 py-1.5 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed text-amber-100 rounded text-[11px] border border-amber-600/50"
              >
                {t('clinical.browserFlames.open', 'Open as AI draft for review')}
              </button>
            )
          ) : (
            <p className="text-[9px] text-amber-200">
              {t(
                'clinical.browserFlames.opened',
                'Draft opened in orange. Review and correct it; it is never saved automatically — only when you press Save, and then as an unreviewed AI draft.',
              )}
            </p>
          )}
          {openError && <p className="text-[9px] text-red-300">{openError}</p>}
        </div>
      )}

      <details className="text-[9px] text-gray-400" data-testid="browser-flames-licences">
        <summary className="cursor-pointer text-gray-300">{t('clinical.browserFlames.licences', 'Licences and attribution')}</summary>
        <ul className="mt-1 space-y-1">
          {FLAMES_NOTICES.map((n) => (
            <li key={n.component}>
              <span className="text-gray-200">{n.component}</span> —{' '}
              <a href={n.licenceUrl} target="_blank" rel="noreferrer" className="underline">
                {n.licence}
              </a>
              . {n.attribution}
              {n.changes ? ` Changes: ${n.changes}` : ''}
            </li>
          ))}
          <li>
            <a href="/licenses/flames-NOTICE.txt" target="_blank" rel="noreferrer" className="underline">
              {t('clinical.browserFlames.fullNotice', 'Full notice')}
            </a>
          </li>
        </ul>
      </details>
    </div>
  );
};

export default BrowserFlamesCard;
