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
import React, { useEffect, useMemo, useRef, useState } from 'react';
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
import { AutomaticMarkingNotice } from './AutomaticMarkingNotice';
import { currentEnvironment, estimateDuration, formatElapsed } from '@/services/flames/runtimeEstimate';
import { FEATURES } from '@/config/features';
import { QualityGatePanel } from './QualityGatePanel';
import { requestQualityGate } from '@/services/qualityGate/api';
import {
  gateUnavailable, isGateResult, retryAfterSeconds, serverSequenceClass, skullFromProvenance,
  type GateResult, type ServerGateResponse,
} from '@/services/qualityGate/gate';
import { useGateConsultation } from '@/hooks/useGateConsultation';

/** G29 / U1: an answer the physician may ask again for once no automatic retry is left (rate limited or unavailable). */
const askable = (r: GateResult): boolean =>
  retryAfterSeconds(r) !== null || (r.codes.length === 1 && r.codes[0] === 'gate_unavailable');

interface BrowserFlamesCardProps {
  flairFileId: string;
  /** the name the file was uploaded with */
  flairName?: string;
}

export const BrowserFlamesCard: React.FC<BrowserFlamesCardProps> = ({ flairFileId, flairName }) => {
  const { t } = useTranslation();
  const flames = useBrowserFlames();
  const currentSeries = useViewerStore((s) => s.currentSeries);
  const importDraft = useSegmentationStore((s) => s.importDraftCallback);
  const [opened, setOpened] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);
  const [pendingDiscard, setPendingDiscard] = useState<string | null>(null);
  const [emptyAcknowledged, setEmptyAcknowledged] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  // RC-049: the clinician must confirm the sequence of THIS file before each run (positive evidence, recorded).
  const [sequenceConfirmed, setSequenceConfirmed] = useState(false);
  useEffect(() => setSequenceConfirmed(false), [flairFileId]);

  // Single quality gate (REQ-FUNC-117/118, RC-122..RC-127; DRAFT, behind VITE_ENABLE_QUALITY_GATE). Sixth review of
  // PR #81 (G27): the SERVER decides; the card sends its inputs (the file, the physician's attestation, the worker's
  // skull outcome) and shows the server's answer as it is — before the run (skull still pending) and before the
  // result (with the skull outcome). Until the final answer for THIS run arrives, nothing of the result is shown.
  // E1: ONE (debounced) consultation per file; the attestation is sent only on Run, and the server decides with it.
  // S3 / G13: the attestation is its own control, offered only when the answer names the study as attestable,
  // unticked by default, reset on every file change, never implied by the run checkbox.
  const gateOn = FEATURES.QUALITY_GATE;
  const [attested, setAttested] = useState(false);
  const attestedAtRun = useRef(false);
  const doneResult = flames.status === 'done' ? flames.result : null;
  // G18: every answer and every run carries the file it was made for; an answer for a file that is no longer the
  // selected one never acts. One request at a time: Run is disabled while it is in flight.
  const currentFile = useRef(flairFileId);
  currentFile.current = flairFileId;
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const runVersion = useRef<string | null>(null);
  useEffect(() => setAttested(false), [flairFileId]);
  // E1: ONE (debounced) consultation per file before the run. U1 (tenth review): its automatic retries are state —
  // one timer per rate-limited answer, none while in flight, at most 3 (G29), "Check again" after the last answer.
  const before = useGateConsultation<ServerGateResponse>(
    gateOn && flairFileId ? flairFileId : null,
    () => requestQualityGate(flairFileId, false).then((r) => (r.subject?.file_id === currentFile.current ? r : null)),
    retryAfterSeconds, 250);
  const preflight = before.answer;
  const preflightStuck = gateOn && preflight !== null && before.settled && askable(preflight);
  const canAttest = gateOn && (preflight?.attestable_visits ?? []).includes('study');
  const gateBefore: GateResult | null = preflight;
  // U3: the final decision belongs to the RUN (its result object), never to the file: a re-run of the same file never
  // shows the previous run's decision, not even on its first render. G17: the server decides (and audits) the
  // releasing decision with the skull outcome reported here. G27: the server's answer is shown as it is; no answer of
  // the right shape, or a file changed since the run, is unavailable (and a changed file is not asked again).
  const final = useGateConsultation<{ gate: GateResult; retry: boolean }>(
    gateOn && doneResult && doneResult.fileId === flairFileId ? doneResult : null,
    () => {
      const run = doneResult as NonNullable<typeof doneResult>;
      return requestQualityGate(run.fileId, attestedAtRun.current, skullFromProvenance(run.provenance)).then((r) => {
        if (r.subject?.file_id !== run.fileId || run.fileId !== currentFile.current) return null;
        const changed = runVersion.current !== null && r.subject?.version != null && r.subject.version !== runVersion.current;
        return { gate: !changed && isGateResult(r) ? r : gateUnavailable(), retry: !changed };
      });
    },
    (f) => (f.retry ? retryAfterSeconds(f.gate) : null));
  const finalGate = final.answer ? final.answer.gate : null;
  const finalStuck = final.answer !== null && final.settled && final.answer.retry && askable(final.answer.gate);
  const gateAllowsRun = !gateOn || preflight?.ai_may_run === true || (canAttest && attested);
  const gateAllowsOutput = !gateOn || (finalGate?.ai_output_allowed === true && doneResult?.fileId === flairFileId);

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
    if (!sequenceConfirmed || !gateAllowsRun) return;
    if (!gateOn) {
      void flames.run(flairFileId, { seriesDescription, clinicianConfirmedFlair: true });
      return;
    }
    if (inFlight.current) return;                                    // G18: one request per click
    inFlight.current = true;
    setBusy(true);
    // The attestation reaches the backend (and its audit, with the clinician) only now, deliberately.
    const attestation = canAttest && attested;
    const fileAtClick = flairFileId;
    void requestQualityGate(fileAtClick, attestation).then((fresh) => {
      inFlight.current = false;
      setBusy(false);
      if (currentFile.current !== fileAtClick || fresh.subject?.file_id !== fileAtClick) return;   // stale: never runs
      if (!fresh.ai_may_run) {
        before.show(fresh);
        return;
      }
      attestedAtRun.current = attestation;
      runVersion.current = fresh.subject?.version ?? null;
      // G27: RC-049 in the worker takes the sequence class the server derived for this file
      void flames.run(fileAtClick, { seriesDescription, clinicianConfirmedFlair: true, qualityGate: true,
        gateSequenceClass: serverSequenceClass(fresh) });
    });
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
          'Runs FLAMeS on this computer. Needs a T2-FLAIR (other sequences are refused). If the image still has its skull, the server of the app removes it first. The first run downloads a 62 MB model. Result = unreviewed AI draft.',
        )}
      </p>

      {!running && (
        <>
          <p className="text-[9px] text-amber-200/90" data-testid="browser-flames-estimate">
            {t('clinical.browserFlames.expected', 'Expected duration')}: {estimate.text}{' '}
            {t('clinical.browserFlames.keepWorking', 'You can keep working and cancel at any time; cancelling never changes your segmentation.')}
          </p>
          <label className="flex items-start gap-1 text-[9px] text-amber-100" data-testid="browser-flames-confirm-sequence">
            <input
              type="checkbox"
              checked={sequenceConfirmed}
              onChange={(e) => setSequenceConfirmed(e.target.checked)}
              disabled={!flairFileId}
            />
            <span>
              {t(
                'clinical.browserFlames.confirmSequence',
                'I confirm that the selected image is a T2-FLAIR (not T1, T2, PD or post-contrast). This confirmation is recorded with the result.',
              )}{' '}
              <span className="text-gray-400 break-all">{flairFileId ? `(${flairName ?? flairFileId.split('/').pop()})` : ''}</span>
            </span>
          </label>
          {gateOn && (gateBefore ? <QualityGatePanel result={gateBefore} testId="quality-gate-before" />
            : <p className="text-[9px] text-gray-400" data-testid="quality-gate-checking">{t('qualityGate.checking')}</p>)}
          {gateOn && before.left !== null && (
            <p className="text-[9px] text-sky-200" role="status" data-testid="quality-gate-retry">
              {t('qualityGate.retrying', { seconds: before.left })}
            </p>
          )}
          {preflightStuck && (
            <button type="button" onClick={before.again} data-testid="quality-gate-check-again"
              className="text-[9px] text-sky-200 underline hover:text-white">{t('qualityGate.checkAgain')}</button>
          )}
          {gateOn && canAttest && (
            <label className="flex items-start gap-1 text-[9px] text-sky-100" data-testid="quality-gate-attest">
              <input type="checkbox" checked={attested} onChange={(e) => setAttested(e.target.checked)} />
              <span>{t('qualityGate.attest')}</span>
            </label>
          )}
          <button
            onClick={handleRun}
            disabled={!flairFileId || !sequenceConfirmed || !gateAllowsRun || busy}
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

      {gateOn && flames.status === 'done' && flames.result && (
        finalGate ? <QualityGatePanel result={finalGate} testId="quality-gate-after" />
          : <p className="text-[9px] text-gray-400" data-testid="quality-gate-checking">{t('qualityGate.checking')}</p>
      )}
      {gateOn && flames.status === 'done' && flames.result && finalGate && !finalGate.ai_output_allowed && (
        <p className="text-[10px] text-red-200" role="alert" data-testid="quality-gate-output-hidden">{t('qualityGate.aiHidden')}</p>
      )}
      {gateOn && flames.status === 'done' && flames.result && final.left !== null && (
        <p className="text-[9px] text-sky-200" role="status" data-testid="quality-gate-retry">
          {t('qualityGate.retrying', { seconds: final.left })}
        </p>
      )}
      {gateOn && flames.status === 'done' && flames.result && finalStuck && (
        <button type="button" onClick={final.again} data-testid="quality-gate-check-again-final"
          className="text-[9px] text-sky-200 underline hover:text-white">{t('qualityGate.checkAgain')}</button>
      )}

      {flames.status === 'done' && flames.result && gateAllowsOutput && (
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
          {/* PRB-003 (RC-072; review of PR #68, finding 9): with every in-browser lesion result. */}
          <AutomaticMarkingNotice />
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
