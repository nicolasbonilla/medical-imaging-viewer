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
  type GateParams, type GateResult, type ServerGateResponse,
} from '@/services/qualityGate/gate';
import { useGateConsultation } from '@/hooks/useGateConsultation';
import { formatGateMessage } from '@/services/qualityGate/gateText';

/** G29 / U1: an answer the physician may ask again for once no automatic retry is left (rate limited or unavailable;
 *  K3, fourteenth review: or the file's version could not be established — a later check can establish it). */
const askable = (r: GateResult): boolean =>
  retryAfterSeconds(r) !== null || (r.codes.length === 1 && r.codes[0] === 'gate_unavailable')
  || r.codes.includes('version_not_established');

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
  // S4 (fifteenth review): ONE consultation for the CURRENT inputs — the file and the attestation in effect: ticking or
  // unticking the attestation asks again (debounced), and every request, automatic retries included, carries the
  // inputs in effect at send time; the panel shows only the decision for the current inputs.
  // S3 / G13: the attestation is its own control, offered only when the server names the study as attestable,
  // unticked by default, reset on every file change, never implied by the run checkbox.
  const gateOn = FEATURES.QUALITY_GATE;
  const [attested, setAttested] = useState(false);
  const doneResult = flames.status === 'done' ? flames.result : null;
  // G18: every answer and every run carries the file it was made for; an answer for a file that is no longer the
  // selected one never acts. One request at a time: Run is disabled while it is in flight.
  const currentFile = useRef(flairFileId);
  currentFile.current = flairFileId;
  const attestedNow = useRef(false);                          // the attestation in effect at the last render
  const selection = useRef(0);                                // M1: bumped on every file change
  const [busy, setBusy] = useState(false);                   // O5 (twelfth review): the one "request in flight" state
  // M1 (thirteenth review): what a run follows is held per RUN — its attestation, the version and the run token of the
  // decision that allowed it; a run token is used by ONE run only; the newest version the server named, per file
  const runOf = useRef<{ attested: boolean; version: string | null; token: string | null }>({ attested: false, version: null, token: null });
  const usedTokens = useRef(new Set<string>());
  const requests = useRef(0);
  const newest = useRef<Record<string, { seq: number; version: string }>>({});
  const [, setVersionsSeen] = useState(0);                   // re-render when a newer version is named
  // P5 / S4: whether the server named this file's study as attestable — from its last decision WITHOUT the attestation
  // (an attested decision does not say it), so the box stays offered while the attested consultation is asked
  const [attestable, setAttestable] = useState<{ file: string; yes: boolean } | null>(null);
  // K3 (fourteenth review, P7): a Run click that does not start a run says why — never a silent no-op
  const [runNotice, setRunNotice] = useState<{ kind: 'notStarted' | 'inputsChanged'; code: string | null;
    params?: GateParams | null } | null>(null);
  useEffect(() => { setAttested(false); setRunNotice(null); selection.current += 1; }, [flairFileId]);
  /** Every consultation goes through here: the answer is stamped with the time it was ASKED (its run token was issued
   *  later, so its lifetime is counted from no later than its real start), and the version the server names is kept
   *  when the request is the newest for its file (a late answer never lowers it). */
  const ask = (file: string, attestation: boolean, skull?: 'pending' | 'stripped' | 'unknown', token?: string | null) => {
    const seq = (requests.current += 1);
    const askedAt = Date.now();
    return requestQualityGate(file, attestation, skull, token).then((r) => {
      const f = r.subject?.file_id;
      const v = r.subject?.version;
      if (typeof f === 'string' && typeof v === 'string' && seq > (newest.current[f]?.seq ?? -1)) {
        if (newest.current[f]?.version !== v) setVersionsSeen((n) => n + 1);
        newest.current[f] = { seq, version: v };
      }
      return { ...r, asked_at: askedAt };
    });
  };
  /** P1 / P2: a decision a run may start from — for this file, its newest version and this attestation, with a run token
   *  no run has used and that has not expired (one minute of margin). */
  const startable = (r: ServerGateResponse | null, file: string, attestation: boolean): r is ServerGateResponse =>
    !!r && r.ai_may_run === true && r.subject?.file_id === file && typeof r.subject?.version === 'string'
    && r.subject.version === newest.current[file]?.version
    && (r.inputs?.visits?.[0]?.physician_confirmed_flair === true) === attestation
    && typeof r.run_token === 'string' && !usedTokens.current.has(r.run_token)
    && Date.now() < (r.asked_at ?? 0) + (r.run_token_ttl_s ?? 0) * 1000 - 60_000;
  // P5: the attestation is offered when the server says the file is attestable — also after an attested run
  const canAttest = gateOn && attestable?.file === flairFileId && attestable.yes;
  // P1 / P3: the ONE attestation in effect — ticked AND offered; it is what every request before the run sends (P8)
  const attestationOn = canAttest && attested;
  attestedNow.current = attestationOn;
  // S4: the subject of the consultation is the inputs in effect; a new subject asks again, an answer is exposed only for
  // the subject it was asked for. U1 (tenth review): its automatic retries are state — one timer per rate-limited
  // answer, none while in flight, at most 3 (G29) — and re-ask with the SAME inputs.
  const inputsNow = useMemo(() => (gateOn && flairFileId ? { file: flairFileId, attested: attestationOn } : null),
    [gateOn, flairFileId, attestationOn]);
  const before = useGateConsultation<ServerGateResponse>(
    inputsNow,
    (subject) => {
      const inputs = subject as { file: string; attested: boolean };
      return ask(inputs.file, inputs.attested).then((r) => (r.subject?.file_id === currentFile.current ? r : null));
    },
    retryAfterSeconds, 250);
  const preflight = before.answer;
  const preflightStuck = gateOn && preflight !== null && before.settled && askable(preflight);
  useEffect(() => {
    const a = before.answer;
    if (a && a.inputs && a.subject?.file_id === flairFileId && a.inputs.visits?.[0]?.physician_confirmed_flair !== true) {
      setAttestable({ file: flairFileId, yes: (a.attestable_visits ?? []).includes('study') });
    }
  }, [before.answer, flairFileId]);
  // P3 / P9: never a decision for an older version than the newest the server named (it is asked again instead)
  const newestVersion = newest.current[flairFileId]?.version;
  const preflightStale = !!preflight && typeof preflight.subject?.version === 'string' && newestVersion !== undefined
    && preflight.subject.version !== newestVersion;
  const shownBefore = preflightStale ? null : preflight;
  const refresh = before.again;
  useEffect(() => { if (gateOn && preflightStale) refresh(); }, [gateOn, preflightStale, refresh]);
  // U3: the final decision belongs to the RUN (its result object), never to the file: a re-run of the same file never
  // shows the previous run's decision, not even on its first render. G17: the server decides (and audits) the
  // releasing decision with the skull outcome reported here. G27: the server's answer is shown as it is; no answer of
  // the right shape, or a file changed since the run, is unavailable (and a changed file is not asked again).
  const final = useGateConsultation<{ gate: GateResult; retry: boolean }>(
    gateOn && doneResult && doneResult.fileId === flairFileId ? doneResult : null,
    (subject) => {
      const run = subject as NonNullable<typeof doneResult>;           // the run this request is for (M1)
      const of = runOf.current;
      return ask(run.fileId, of.attested, skullFromProvenance(run.provenance), of.token).then((r) => {
        if (r.subject?.file_id !== run.fileId || run.fileId !== currentFile.current) return null;
        const changed = of.version !== null && r.subject?.version != null && r.subject.version !== of.version;
        return { gate: !changed && isGateResult(r) ? r : gateUnavailable(), retry: !changed };
      });
    },
    (f) => (f.retry ? retryAfterSeconds(f.gate) : null));
  const finalGate = final.answer ? final.answer.gate : null;
  const finalStuck = final.answer !== null && final.settled && final.answer.retry && askable(final.answer.gate);
  const gateAllowsRun = !gateOn || preflight?.ai_may_run === true;
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
    setRunNotice(null);
    // Header evidence for the FLAIR gate: the series description the app holds for THIS file only.
    const seriesDescription =
      currentSeries?.file_id === flairFileId ? currentSeries?.metadata?.series_description ?? null : null;
    if (!sequenceConfirmed || !gateAllowsRun) return;
    if (!gateOn) {
      void flames.run(flairFileId, { seriesDescription, clinicianConfirmedFlair: true });
      return;
    }
    if (busy) return;                                                // G18: one request per click
    const attestation = attestationOn;                 // the inputs in effect at the click (S4)
    const fileAtClick = flairFileId;
    const selectionAtClick = selection.current;
    const start = (decision: ServerGateResponse) => {
      runOf.current = { attested: attestation, version: decision.subject?.version ?? null, token: decision.run_token ?? null };
      if (decision.run_token) usedTokens.current.add(decision.run_token);       // P2: never used by a second run
      // G27: RC-049 in the worker takes the sequence class the server derived for this file
      void flames.run(fileAtClick, { seriesDescription, clinicianConfirmedFlair: true, qualityGate: true,
        gateSequenceClass: serverSequenceClass(decision) });
    };
    // I6 (eleventh review): the decision already held for EXACTLY these inputs, with an unused, unexpired run token,
    // starts the run — two consultations per run; anything else (a re-run, an expired or used token, a newer version,
    // a changed attestation) asks the server again (M1, thirteenth review)
    const held = preflight;
    if (startable(held, fileAtClick, attestation)) {
      start(held);
      return;
    }
    setBusy(true);
    void ask(fileAtClick, attestation).then((fresh) => {
      setBusy(false);
      // P1 / P3: an answer for inputs that are no longer the current ones never acts (file, selection, attestation);
      // another file shows its own state, a changed attestation is SAID (P7)
      if (selection.current !== selectionAtClick || currentFile.current !== fileAtClick
        || fresh.subject?.file_id !== fileAtClick) return;
      if (attestedNow.current !== attestation) {
        setRunNotice({ kind: 'inputsChanged', code: null });
        return;
      }
      before.show(fresh);              // O3: the "before" panel shows the decision the run follows (same inputs)
      const answer: ServerGateResponse = fresh;      // (the type guard below narrows `fresh` only)
      if (startable(fresh, fileAtClick, attestation)) {
        start(fresh);
        return;
      }
      // P7 (fourteenth review): not started — ALWAYS said, with the server's reason (the panel may show another
      // consultation later, e.g. the automatic retry of a rate-limited one): never a silent no-op
      const stop = (answer.checks ?? []).find((c) => c.status === 'abstain' && c.code);
      setRunNotice({ kind: 'notStarted', code: stop?.code ?? null, params: stop?.params ?? null });
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
          {gateOn && (shownBefore ? <QualityGatePanel result={shownBefore} testId="quality-gate-before" />
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
          {gateOn && runNotice && (
            <p className="text-[9px] text-amber-200" role="alert" data-testid="quality-gate-run-not-started">
              {t(runNotice.kind === 'inputsChanged' ? 'qualityGate.inputsChanged' : 'qualityGate.runNotStarted')}
              {runNotice.code ? ` ${formatGateMessage(t, runNotice.code, 'message', runNotice.params)}` : ''}
            </p>
          )}
          {gateOn && canAttest && (
            <label className="flex items-start gap-1 text-[9px] text-sky-100" data-testid="quality-gate-attest">
              {/* S4: a change of the attestation is a change of the inputs — the decision for the new inputs is asked */}
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
