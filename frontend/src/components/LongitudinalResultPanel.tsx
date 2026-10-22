/**
 * Longitudinal comparison — result panel (CAPA-013; RC-060, RC-061, RC-062; REQ-SAFE-037; HAZ-007).
 *
 * Measured (paper C pilot, PR #60): against expert change masks the device's new/enlarging rule
 * proposed >= 1 false candidate in 20/20 patients, about 9 per patient. So:
 * - RC-060: new/enlarging results are "unconfirmed change candidates", never activity,
 *   dissemination in time or NEDA. A radiologist confirms or rejects each one (stored server-side
 *   with the reader and the time, bound to the masks compared). The word "activity" appears only
 *   in the reader-confirmed box, which the backend sends only after a confirmation.
 * - RC-061: the measured false-candidate rate is rendered from the response
 *   (`false_candidate_evidence`, a versioned backend asset) — no figure lives in this file. The
 *   FLAIR subtraction is a signal, never a confirmation. Every text is in en/es/de.
 * - RC-062: when the acquisition of the two visits differs or cannot be established the backend
 *   abstains; the panel shows why and which metadata were compared, no count, and keeps the overlay.
 *
 * @module components/LongitudinalResultPanel
 */
import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ChevronDown, ChevronUp, ArrowUpRight, ArrowDownRight, Plus, Minus, Equal,
} from 'lucide-react';
import { segmentationAPI } from '@/api/segmentation';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type { LongitudinalResult, LesionChange, LongitudinalAcquisitionCheck } from '@/types';

const REGION_CODES: Record<string, string> = {
  Periventricular: 'pv',
  Juxtacortical: 'jc',
  Infratentorial: 'it',
  'Deep White Matter': 'dwm',
  Unassigned: 'unassigned',
};
const REGION_ID_CODES: Record<number, string> = { 1: 'pv', 2: 'jc', 3: 'it', 4: 'dwm' };

function statusIcon(status: string) {
  switch (status) {
    case 'new': return <Plus className="w-3 h-3 text-blue-400" />;
    case 'resolved': return <Minus className="w-3 h-3 text-green-400" />;
    case 'enlarged': return <ArrowUpRight className="w-3 h-3 text-red-400" />;
    case 'shrunk': return <ArrowDownRight className="w-3 h-3 text-teal-400" />;
    case 'stable': return <Equal className="w-3 h-3 text-gray-400" />;
    default: return null;
  }
}

function statusColor(status: string): string {
  switch (status) {
    case 'new': return 'text-blue-400';
    case 'resolved': return 'text-green-400';
    case 'enlarged': return 'text-red-400';
    case 'shrunk': return 'text-teal-400';
    default: return 'text-gray-400';
  }
}

function statusBg(status: string): string {
  switch (status) {
    case 'new': return 'bg-blue-500';
    case 'resolved': return 'bg-green-500';
    case 'enlarged': return 'bg-red-500';
    case 'shrunk': return 'bg-teal-500';
    default: return 'bg-gray-500';
  }
}

interface LongitudinalResultPanelProps {
  result: LongitudinalResult;
  tp1SegId: string;
  tp2SegId: string;
  onNavigateToSlice?: (sliceIndex: number) => void;
  /** Called after a decision was recorded: the parent compares again (the server applies it). */
  onReviewed: () => void;
}

export function LongitudinalResultPanel({
  result, tp1SegId, tp2SegId, onNavigateToSlice, onReviewed,
}: LongitudinalResultPanelProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language || 'en';
  const subVisible = useSegmentationStore((s) => s.longitudinalSubtractionVisible);
  const [expanded, setExpanded] = useState(true);
  const [busy, setBusy] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const num = useCallback(
    (n: number | null | undefined, digits = 1) =>
      typeof n === 'number' && Number.isFinite(n)
        ? new Intl.NumberFormat(lang, { maximumFractionDigits: digits }).format(n)
        : '—',
    [lang],
  );
  const dateTime = useCallback((iso: string | null | undefined) => {
    if (!iso) return '—';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(lang);
  }, [lang]);

  const abstained = result.abstained === true;
  const cc = result.change_candidates;
  const evidence = result.false_candidate_evidence;
  const confirmedBox = result.reader_confirmed_activity;

  const sendDecision = useCallback(async (change: LesionChange, decision: 'confirmed' | 'rejected') => {
    if (!result.review_binding || !change.candidate_key) return;
    setBusy(true);
    setReviewError(null);
    try {
      await segmentationAPI.reviewLongitudinalCandidates({
        tp1: { type: 'segmentation', id: tp1SegId },
        tp2: { type: 'segmentation', id: tp2SegId },
        review_binding: result.review_binding,
        decisions: [{ candidate_key: change.candidate_key, decision }],
      });
      onReviewed();
    } catch (err: any) {
      const status = err?.response?.status;
      setReviewError(
        status === 403 ? t('longitudinal.reviewForbidden')
          : status === 409 ? t('longitudinal.reviewStale')
            : t('longitudinal.reviewFailed', { detail: err?.response?.data?.detail || err?.message || '' }),
      );
    } finally {
      setBusy(false);
    }
  }, [result.review_binding, tp1SegId, tp2SegId, onReviewed, t]);

  const fieldValue = (v: unknown) => (Array.isArray(v) ? v.map((x) => num(Number(x), 2)).join(' × ')
    : typeof v === 'number' ? num(v, 2) : String(v ?? '—'));
  const visitLabel = (tp: string) => (tp === 'tp1' ? t('longitudinal.visit1') : t('longitudinal.visit2'));

  const abstentionBox = (check: LongitudinalAcquisitionCheck | undefined) => (
    <div
      data-testid="longitudinal-abstained"
      className="rounded border border-orange-500/50 bg-orange-500/10 px-2 py-1.5 text-[10px] leading-snug text-orange-800 dark:text-orange-200 space-y-1"
    >
      <p className="font-semibold">{t('longitudinal.abstainedTitle')}</p>
      {check?.status === 'differs' ? (
        <>
          <p>{t('longitudinal.abstainedDiffers')}</p>
          <ul className="list-disc pl-4">
            {check.differing.map((d) => (
              <li key={d.field}>
                {t(`longitudinal.field.${d.field}`)}: {visitLabel('tp1')} {fieldValue(d.tp1)} → {visitLabel('tp2')} {fieldValue(d.tp2)}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          <p>{t('longitudinal.abstainedUnknown')}</p>
          <ul className="list-disc pl-4">
            {(check?.missing ?? []).map((m) => (
              <li key={m.field}>
                {t(`longitudinal.field.${m.field}`)} ({m.timepoints.map(visitLabel).join(', ')})
              </li>
            ))}
          </ul>
        </>
      )}
      <p>{t('longitudinal.abstainedWhy')}</p>
      <p className="text-[9px]">{t('longitudinal.abstainedFieldsUsed')}</p>
      <p className="font-medium">{t('longitudinal.abstainedAction')}</p>
    </div>
  );

  return (
    <>
      {/* Lesion burden of each visit (a property of each segmentation). The change is shown only
          when the comparison did not abstain (RC-062). */}
      <div className="bg-gray-100 dark:bg-gray-900/50 rounded-lg p-2 space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-gray-500 dark:text-gray-400">{t('longitudinal.burden')}</span>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-gray-400 dark:text-gray-500">{num(result.burden_tp1_ml, 2)} mL</span>
            <span className="text-[10px] text-gray-400">&rarr;</span>
            <span className="text-xs font-mono font-bold text-gray-800 dark:text-white">{num(result.burden_tp2_ml, 2)} mL</span>
          </div>
        </div>
        {!abstained && typeof result.burden_delta_percent === 'number' && (
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-gray-500 dark:text-gray-400">{t('longitudinal.change')}</span>
            <span className="text-xs font-mono font-bold text-gray-500 dark:text-gray-300">
              {result.burden_delta_percent > 0 ? '+' : ''}{num(result.burden_delta_percent, 1)}%
            </span>
          </div>
        )}
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-gray-500 dark:text-gray-400">{t('longitudinal.lesionCount')}</span>
          <span className="text-[10px] text-gray-600 dark:text-gray-300">
            {result.total_lesions_tp1} &rarr; {result.total_lesions_tp2}
          </span>
        </div>
      </div>

      {/* Standing caveat, localised (the backend's English caveat is for API consumers). */}
      {result.registration_verified ? (
        <div className="rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-1.5 text-[10px] leading-snug text-emerald-700 dark:text-emerald-300">
          {t('longitudinal.registrationVerified')}
        </div>
      ) : (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-[10px] leading-snug text-amber-700 dark:text-amber-300">
          {t('longitudinal.candidateCaveat')}
        </div>
      )}
      {result.spacing_resolved === false && (
        <div className="rounded border border-orange-500/40 bg-orange-500/10 px-2 py-1 text-[10px] leading-snug text-orange-700 dark:text-orange-300">
          {t('longitudinal.spacingFallback')}
        </div>
      )}
      <div className="flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-gray-400">
        <span className={`w-1.5 h-1.5 rounded-full ${result.registration_applied ? 'bg-sky-500' : 'bg-gray-400'}`} />
        {result.registration_applied ? (
          <span>
            {t('longitudinal.coregistered')}
            {typeof result.registration_advisory_qc?.translation_mm === 'number' &&
              ` · ${num(result.registration_advisory_qc.translation_mm, 1)} mm, ${num(result.registration_advisory_qc.rotation_deg ?? 0, 1)}°`}
          </span>
        ) : (
          <span>{t('longitudinal.indexAligned')}</span>
        )}
      </div>

      {abstained ? abstentionBox(result.acquisition_check) : (
        <>
          {/* RC-060 + RC-061: unconfirmed candidates, the review state and the measured rate. */}
          <div
            data-testid="longitudinal-candidates"
            className="rounded border border-amber-500/50 bg-amber-500/10 px-2 py-1.5 text-[10px] leading-snug text-amber-800 dark:text-amber-200 space-y-1"
          >
            <p className="font-semibold">
              {t('longitudinal.candidatesSummary', {
                total: cc?.total ?? 0, n: cc?.new ?? 0, e: cc?.enlarging ?? 0, d: result.new_lesion_min_diameter_mm ?? 3,
              })}
            </p>
            <p>
              {t('longitudinal.candidatesReview', {
                awaiting: cc?.awaiting_review ?? 0, confirmed: cc?.confirmed ?? 0, rejected: cc?.rejected ?? 0,
              })}
            </p>
            <p>{t('longitudinal.candidatesNoStatement')}</p>
            {cc?.earlier_decisions_voided && <p>{t('longitudinal.decisionsVoided')}</p>}
            {!result.review_binding && <p>{t('longitudinal.reviewUnavailable')}</p>}
            <p data-testid="longitudinal-evidence" className="text-[9px] text-amber-900/80 dark:text-amber-100/80">
              {evidence
                ? t('longitudinal.evidence', {
                  patients: evidence.patients,
                  segmenter: evidence.segmenter,
                  mean: num(evidence.false_candidates_per_patient, 1),
                  lo: num(evidence.false_candidates_per_patient_ci95?.[0], 1),
                  hi: num(evidence.false_candidates_per_patient_ci95?.[1], 1),
                  meanSub: num(evidence.after_subtraction_per_patient, 1),
                  source: evidence.source,
                  date: evidence.measured_on,
                })
                : t('longitudinal.evidenceMissing')}
            </p>
          </div>

          {/* RC-060 (c): only after a radiologist's confirmation — the backend sends this block
              only then; it is the only place where the word "activity" may appear. */}
          {confirmedBox && (
            <div
              data-testid="longitudinal-reader-confirmed"
              className="rounded border border-purple-500/40 bg-purple-500/10 px-2 py-1.5 text-[10px] leading-snug text-purple-800 dark:text-purple-200"
            >
              <p className="font-semibold">
                {t('longitudinal.readerConfirmed', {
                  n: confirmedBox.confirmed_new, e: confirmedBox.confirmed_enlarging,
                  who: confirmedBox.confirmed_by.join(', '), when: dateTime(confirmedBox.last_confirmed_at),
                })}
              </p>
              <p>{t('longitudinal.readerConfirmedRule')}</p>
            </div>
          )}

          {result.subtraction_available && result.subtraction_summary && result.subtraction_summary.new_total > 0 && (
            <div className="flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-gray-400">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-500" />
              <span>
                {t('longitudinal.subSummary', {
                  c: result.subtraction_summary.new_subtraction_confirmed, n: result.subtraction_summary.new_total,
                })}
              </span>
            </div>
          )}
        </>
      )}

      {/* FLAIR subtraction heatmap — a visual aid for the reader, kept in every case. */}
      {result.subtraction_volume_b64 && (
        <button
          type="button"
          onClick={() => useSegmentationStore.getState().toggleLongitudinalSubtraction()}
          className={`flex w-full items-center justify-between rounded border px-2 py-1 text-[10px] transition-colors ${
            subVisible
              ? 'border-sky-500/50 bg-sky-500/10 text-sky-700 dark:text-sky-300'
              : 'border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
          }`}
        >
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-4 rounded-sm bg-gradient-to-r from-blue-500 via-transparent to-red-500" />
            {t('longitudinal.subOverlayToggle')}
          </span>
          <span className="font-semibold">{subVisible ? t('longitudinal.overlayShown') : t('longitudinal.overlayHidden')}</span>
        </button>
      )}
      {result.subtraction_volume_omitted && (
        <div className="text-[9px] text-gray-400">{t('longitudinal.subOmitted')}</div>
      )}

      {!abstained && result.region_stratification && (() => {
        const rows = Object.entries(result.region_stratification).filter(([, v]) => v.new > 0 || v.enlarging > 0);
        if (rows.length === 0) return null;
        return (
          <div className="rounded border border-gray-200 dark:border-gray-800 px-2 py-1.5">
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
              {t('longitudinal.byRegion')}
            </div>
            {result.region_atlas_note && (
              <div className="mb-1 text-[9px] leading-snug text-gray-400">{t('longitudinal.regionAtlasNote')}</div>
            )}
            <div className="flex flex-col gap-0.5">
              {rows.map(([region, v]) => (
                <div key={region} className="flex items-center justify-between text-[10px]">
                  <span className="text-gray-600 dark:text-gray-300">
                    {t(`longitudinal.region.${REGION_CODES[region] ?? 'unassigned'}`)}
                  </span>
                  <span className="font-mono text-gray-500 dark:text-gray-400">
                    {v.new > 0 && <span className="text-blue-500">{t('longitudinal.regionNew', { n: v.new })}</span>}
                    {v.new > 0 && v.enlarging > 0 && ' · '}
                    {v.enlarging > 0 && <span className="text-red-500">{t('longitudinal.regionEnlarging', { e: v.enlarging })}</span>}
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {!abstained && result.status_counts && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(result.status_counts).map(([status, count]) => (
            count > 0 && (
              <span key={status} className="flex items-center gap-1 px-1.5 py-0.5 bg-gray-100 dark:bg-gray-900/60 rounded text-[9px]">
                <span className={`w-1.5 h-1.5 rounded-full ${statusBg(status)}`} />
                <span className={statusColor(status)}>
                  {count} {t(`longitudinal.status.${status}`)} ({t('longitudinal.unconfirmedShort')})
                </span>
              </span>
            )
          ))}
        </div>
      )}

      {/* Legend of the fused overlay on the 2D viewport (SegmentationCanvasLocal). Kept when the
          comparison abstains: the overlay is what the reader compares visually. */}
      <div data-testid="longitudinal-legend" className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[9px] text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm" style={{ background: 'rgb(65,135,245)' }} />
          {t('longitudinal.legendTp1')}
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm" style={{ background: 'rgb(50,205,50)' }} />
          {t('longitudinal.legendBoth')}
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm" style={{ background: 'rgb(245,70,70)' }} />
          {t('longitudinal.legendTp2')}
        </span>
      </div>

      {!abstained && (
        <>
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-200 transition-colors"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {t('longitudinal.changeTable')} ({result.changes.length})
          </button>
          {reviewError && (
            <div data-testid="longitudinal-review-error" className="text-[10px] text-red-500">{reviewError}</div>
          )}
          {expanded && result.changes.length > 0 && (
            <div className="max-h-56 overflow-y-auto">
              <table className="w-full text-[9px]">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-300 dark:border-gray-700">
                    <th className="text-center py-0.5 px-1">{t('longitudinal.statusCol')}</th>
                    <th className="text-right py-0.5 px-1">{t('longitudinal.colTp1')}</th>
                    <th className="text-right py-0.5 px-1">{t('longitudinal.colTp2')}</th>
                    <th className="text-right py-0.5 px-1">&Delta;%</th>
                    <th className="text-center py-0.5 px-1">{t('longitudinal.colDecision')}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.changes.map((change, i) => {
                    const regionCode = change.region_id != null ? REGION_ID_CODES[change.region_id] : undefined;
                    return (
                      <tr
                        key={change.candidate_key ?? i}
                        onClick={() => onNavigateToSlice?.(Math.round(change.centroid_z))}
                        className="cursor-pointer border-b border-gray-200 dark:border-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
                      >
                        <td className="py-0.5 px-1 text-center">
                          <span className="flex items-center justify-center gap-0.5">
                            {statusIcon(change.status)}
                            <span className={statusColor(change.status)}>{t(`longitudinal.status.${change.status}`)}</span>
                            {regionCode && (
                              <span
                                title={t(`longitudinal.region.${regionCode}`)}
                                className="ml-0.5 rounded bg-indigo-400/15 px-1 text-[8px] font-medium text-indigo-600 dark:text-indigo-300"
                              >{t(`longitudinal.regionShort.${regionCode}`)}</span>
                            )}
                            {change.status === 'new' && change.clinically_significant === false && (
                              <span
                                title={t('longitudinal.subthresholdTip', { d: result.new_lesion_min_diameter_mm ?? 3 })}
                                className="ml-0.5 rounded bg-gray-400/15 px-1 text-[8px] font-medium text-gray-500 dark:text-gray-400"
                              >{t('longitudinal.belowSizeGate', { d: result.new_lesion_min_diameter_mm ?? 3 })}</span>
                            )}
                            {change.status === 'new' && change.subtraction_confirmed === true && (
                              <span
                                title={t('longitudinal.subBrighterTip', { s: num(change.subtraction_signal ?? 0, 1) })}
                                className="ml-0.5 rounded bg-sky-500/15 px-1 text-[8px] font-semibold text-sky-600 dark:text-sky-300"
                              >{t('longitudinal.subBadgeBrighter')}</span>
                            )}
                            {change.status === 'new' && change.subtraction_confirmed === false && (
                              <span
                                title={t('longitudinal.subNotBrighterTip')}
                                className="ml-0.5 rounded bg-gray-400/15 px-1 text-[8px] font-semibold text-gray-500 dark:text-gray-400"
                              >{t('longitudinal.subBadgeNotBrighter')}</span>
                            )}
                            {change.status === 'new' && change.subtraction_confirmed == null &&
                              result.subtraction_available && change.subtraction_note === 'border' && (
                              <span
                                title={t('longitudinal.subWithheldTip')}
                                className="ml-0.5 rounded bg-amber-400/15 px-1 text-[8px] font-semibold text-amber-600 dark:text-amber-400"
                              >{t('longitudinal.subBadgeWithheld')}</span>
                            )}
                          </span>
                        </td>
                        <td className="py-0.5 px-1 text-right font-mono text-gray-600 dark:text-gray-300">
                          {change.volume_tp1_ml > 0 ? num(change.volume_tp1_ml, 3) : '—'}
                        </td>
                        <td className="py-0.5 px-1 text-right font-mono text-gray-800 dark:text-white">
                          {change.volume_tp2_ml > 0 ? num(change.volume_tp2_ml, 3) : '—'}
                        </td>
                        <td className={`py-0.5 px-1 text-right font-mono ${statusColor(change.status)}`}>
                          {change.status === 'new' ? t('longitudinal.deltaNew')
                            : change.status === 'resolved' ? t('longitudinal.deltaGone')
                              : `${change.change_percent > 0 ? '+' : ''}${num(change.change_percent, 1)}%`}
                        </td>
                        <td className="py-0.5 px-1 text-center whitespace-nowrap">
                          {change.candidate_key && (
                            <span className="inline-flex items-center gap-0.5">
                              {change.reader_review && (
                                <span className={change.reader_review.decision === 'confirmed' ? 'text-purple-500' : 'text-gray-500'}>
                                  {change.reader_review.decision === 'confirmed'
                                    ? t('longitudinal.decisionConfirmed', { who: change.reader_review.reviewed_by ?? '' })
                                    : t('longitudinal.decisionRejected', { who: change.reader_review.reviewed_by ?? '' })}
                                </span>
                              )}
                              {result.review_binding && (
                                <>
                                  <button
                                    type="button"
                                    disabled={busy}
                                    title={t('longitudinal.confirmTip')}
                                    onClick={(e) => { e.stopPropagation(); void sendDecision(change, 'confirmed'); }}
                                    className="rounded border border-purple-500/50 px-1 text-[8px] text-purple-600 dark:text-purple-300 hover:bg-purple-500/10 disabled:opacity-40"
                                  >{t('longitudinal.confirmCandidate')}</button>
                                  <button
                                    type="button"
                                    disabled={busy}
                                    title={t('longitudinal.rejectTip')}
                                    onClick={(e) => { e.stopPropagation(); void sendDecision(change, 'rejected'); }}
                                    className="rounded border border-gray-400/50 px-1 text-[8px] text-gray-600 dark:text-gray-300 hover:bg-gray-500/10 disabled:opacity-40"
                                  >{t('longitudinal.rejectCandidate')}</button>
                                </>
                              )}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}

export default LongitudinalResultPanel;
