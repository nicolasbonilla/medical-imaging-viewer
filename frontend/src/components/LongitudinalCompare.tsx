/**
 * Longitudinal Comparison Panel
 *
 * Compares lesion masks between two timepoints. Shows:
 * - Burden delta summary (TP1 vs TP2)
 * - Status counts (new, resolved, enlarged, shrunk, stable)
 * - Per-lesion change table with click-to-navigate
 *
 * @module components/LongitudinalCompare
 */

import { useState, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import {
  TrendingUp,
  Loader2,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  ArrowUpRight,
  ArrowDownRight,
  Plus,
  Minus,
  Equal,
} from 'lucide-react';
import { segmentationAPI } from '@/api/segmentation';
import { studyAPI } from '@/api/study';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type { LongitudinalResult, LesionChange, StudySummary, SegmentationResponse } from '@/types';

/** Names that indicate non-lesion segmentations (excluded from dropdowns) */
const EXCLUDED_DESCRIPTIONS = ['magnims zone map', 'brain extraction', 'brain mask', 'synthseg', 'parcellation'];

function isLesionSegmentation(seg: SegmentationResponse): boolean {
  const desc = (seg.metadata?.description || '').toLowerCase();
  return !EXCLUDED_DESCRIPTIONS.some((ex) => desc.includes(ex));
}

interface LongitudinalCompareProps {
  onNavigateToSlice?: (sliceIndex: number) => void;
  studies?: StudySummary[];
}

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
    case 'stable': return 'text-gray-400';
    default: return 'text-gray-400';
  }
}

function statusBg(status: string): string {
  switch (status) {
    case 'new': return 'bg-blue-500';
    case 'resolved': return 'bg-green-500';
    case 'enlarged': return 'bg-red-500';
    case 'shrunk': return 'bg-teal-500';
    case 'stable': return 'bg-gray-500';
    default: return 'bg-gray-500';
  }
}

function formatStudyDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return dateStr; }
}

/** Hook to fetch file_ids for a study (series → instances → gcs_object_name) */
function useStudyFileIds(studyId: string | null) {
  return useQuery({
    queryKey: ['study-file-ids', studyId],
    queryFn: async () => {
      if (!studyId) return [];
      const series = await studyAPI.listSeries(studyId);
      const allInstances = await Promise.all(series.map((s) => studyAPI.listInstances(s.id)));
      return allInstances.flat().map((inst) => inst.gcs_object_name).filter(Boolean);
    },
    enabled: !!studyId,
    staleTime: 5 * 60 * 1000,
  });
}

/** Hook to fetch lesion segmentations for a set of file_ids */
function useStudyLesionSegs(fileIds: string[], studyId: string | null) {
  return useQuery({
    queryKey: ['segmentations-lesion', studyId],
    queryFn: async () => {
      if (fileIds.length === 0) return [];
      const segs = await segmentationAPI.listSegmentationsByFileIds(fileIds);
      return segs.filter((s) => s.segmentation_id && isLesionSegmentation(s));
    },
    enabled: fileIds.length > 0,
    staleTime: 5 * 60 * 1000,
  });
}

export function LongitudinalCompare({
  onNavigateToSlice,
  studies = [],
}: LongitudinalCompareProps) {
  const { t } = useTranslation();
  const currentStudyId = useViewerStore((s) => s.currentStudyId);

  // Sort studies oldest first (TP1 = earlier, TP2 = later)
  const sortedStudies = useMemo(() =>
    [...studies].sort((a, b) => new Date(a.study_date).getTime() - new Date(b.study_date).getTime()),
    [studies]
  );

  // Study selection state
  const [tp1StudyId, setTp1StudyId] = useState<string>('');
  const [tp2StudyId, setTp2StudyId] = useState<string>('');

  // Segmentation selection state
  const [tp1SegId, setTp1SegId] = useState<string>('');
  const [tp2SegId, setTp2SegId] = useState<string>('');

  // Result state
  const [result, setResult] = useState<LongitudinalResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  // Fetch file_ids and segmentations for each selected study
  const { data: tp1FileIds = [] } = useStudyFileIds(tp1StudyId || null);
  const { data: tp2FileIds = [] } = useStudyFileIds(tp2StudyId || null);
  const { data: tp1Segs = [] } = useStudyLesionSegs(tp1FileIds, tp1StudyId || null);
  const { data: tp2Segs = [] } = useStudyLesionSegs(tp2FileIds, tp2StudyId || null);

  // Auto-select first segmentation when list loads
  const canCompare = tp1SegId && tp2SegId;

  const handleCompare = useCallback(async () => {
    if (!canCompare) return;
    setIsLoading(true);
    setError(null);
    try {
      // Load both masks for visual overlay (parallel)
      const [tp1MaskData, tp2MaskData, data] = await Promise.all([
        segmentationAPI.loadZoneMapMask(tp1SegId),
        segmentationAPI.loadZoneMapMask(tp2SegId),
        segmentationAPI.compareLongitudinal(
          { type: 'segmentation', id: tp1SegId },
          { type: 'segmentation', id: tp2SegId },
        ),
      ]);

      // Store masks in Zustand for canvas rendering
      useSegmentationStore.getState().setLongitudinalOverlay(
        { mask: tp1MaskData.mask, dims: { depth: tp1MaskData.depth, height: tp1MaskData.height, width: tp1MaskData.width }, segId: tp1SegId },
        { mask: tp2MaskData.mask, dims: { depth: tp2MaskData.depth, height: tp2MaskData.height, width: tp2MaskData.width }, segId: tp2SegId },
      );

      setResult(data);
      setExpanded(true);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.response?.data?.error?.message || err?.message || String(err);
      setError(detail);
    } finally {
      setIsLoading(false);
    }
  }, [tp1SegId, tp2SegId, canCompare]);

  const handleLesionClick = useCallback((change: LesionChange) => {
    onNavigateToSlice?.(Math.round(change.centroid_z));
  }, [onNavigateToSlice]);

  if (sortedStudies.length < 2) {
    return null;
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <TrendingUp className="w-3.5 h-3.5 text-indigo-400" />
        <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          {t('longitudinal.title', 'Longitudinal Tracking')}
        </span>
      </div>

      {/* TP1: Study + Segmentation */}
      <div className="space-y-1">
        <label className="text-[9px] text-gray-500 block font-medium">
          {t('longitudinal.tp1', 'TP1 (Earlier)')}
        </label>
        <select
          value={tp1StudyId}
          onChange={(e) => { setTp1StudyId(e.target.value); setTp1SegId(''); setResult(null); }}
          className="w-full px-1.5 py-1 bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-white rounded text-[10px] border border-gray-200 dark:border-gray-600"
        >
          <option value="">Select study...</option>
          {sortedStudies.map((s) => (
            <option key={s.id} value={s.id}>
              {formatStudyDate(s.study_date)} — {s.study_description || s.modality}
              {s.id === currentStudyId ? ' (current)' : ''}
            </option>
          ))}
        </select>
        {tp1StudyId && tp1Segs.length > 0 && (
          <select
            value={tp1SegId}
            onChange={(e) => { setTp1SegId(e.target.value); setResult(null); }}
            className="w-full px-1.5 py-1 bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-white rounded text-[10px] border border-gray-200 dark:border-gray-600"
          >
            <option value="">Select segmentation...</option>
            {tp1Segs.map((s) => (
              <option key={s.segmentation_id} value={s.segmentation_id}>
                {s.metadata?.description || s.segmentation_id.slice(0, 8)}
              </option>
            ))}
          </select>
        )}
        {tp1StudyId && tp1Segs.length === 0 && tp1FileIds.length > 0 && (
          <p className="text-[9px] text-gray-500 italic">No lesion segmentations found</p>
        )}
      </div>

      {/* TP2: Study + Segmentation */}
      <div className="space-y-1">
        <label className="text-[9px] text-gray-500 block font-medium">
          {t('longitudinal.tp2', 'TP2 (Later)')}
        </label>
        <select
          value={tp2StudyId}
          onChange={(e) => { setTp2StudyId(e.target.value); setTp2SegId(''); setResult(null); }}
          className="w-full px-1.5 py-1 bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-white rounded text-[10px] border border-gray-200 dark:border-gray-600"
        >
          <option value="">Select study...</option>
          {sortedStudies.map((s) => (
            <option key={s.id} value={s.id}>
              {formatStudyDate(s.study_date)} — {s.study_description || s.modality}
              {s.id === currentStudyId ? ' (current)' : ''}
            </option>
          ))}
        </select>
        {tp2StudyId && tp2Segs.length > 0 && (
          <select
            value={tp2SegId}
            onChange={(e) => { setTp2SegId(e.target.value); setResult(null); }}
            className="w-full px-1.5 py-1 bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-white rounded text-[10px] border border-gray-200 dark:border-gray-600"
          >
            <option value="">Select segmentation...</option>
            {tp2Segs.map((s) => (
              <option key={s.segmentation_id} value={s.segmentation_id}>
                {s.metadata?.description || s.segmentation_id.slice(0, 8)}
              </option>
            ))}
          </select>
        )}
        {tp2StudyId && tp2Segs.length === 0 && tp2FileIds.length > 0 && (
          <p className="text-[9px] text-gray-500 italic">No lesion segmentations found</p>
        )}
      </div>

      {/* Compare Button */}
      <button
        onClick={handleCompare}
        disabled={!canCompare || isLoading}
        className="w-full flex items-center justify-center border border-blue-500 text-blue-400 hover:bg-blue-900/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        style={{ height: 28, borderRadius: 6, fontSize: 12, fontWeight: 500 }}
      >
        {isLoading ? (
          <Loader2 className="w-3 h-3 animate-spin mx-auto" />
        ) : (
          t('longitudinal.compare', 'Compare Timepoints')
        )}
      </button>

      {error && (
        <div className="flex items-center gap-1 text-red-400 text-[10px]">
          <AlertCircle className="w-3 h-3" />
          <span className="truncate">{error}</span>
        </div>
      )}

      {result && (
        <>
          {/* Burden Summary */}
          <div className="bg-gray-100 dark:bg-gray-900/50 rounded-lg p-2 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-500 dark:text-gray-400">
                {t('longitudinal.burden', 'Lesion Burden')}
              </span>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-gray-400 dark:text-gray-500">{result.burden_tp1_ml.toFixed(2)} mL</span>
                <span className="text-[10px] text-gray-400">&rarr;</span>
                <span className="text-xs font-mono font-bold text-gray-800 dark:text-white">{result.burden_tp2_ml.toFixed(2)} mL</span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-500 dark:text-gray-400">{t('longitudinal.change', 'Change')}</span>
              <span className={`text-xs font-mono font-bold ${
                result.burden_delta_percent > 5 ? 'text-red-400' :
                result.burden_delta_percent < -5 ? 'text-green-400' : 'text-gray-500 dark:text-gray-300'
              }`}>
                {result.burden_delta_percent > 0 ? '+' : ''}{result.burden_delta_percent.toFixed(1)}%
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-500 dark:text-gray-400">{t('longitudinal.lesionCount', 'Lesion Count')}</span>
              <span className="text-[10px] text-gray-600 dark:text-gray-300">
                {result.total_lesions_tp1} &rarr; {result.total_lesions_tp2}
              </span>
            </div>
          </div>

          {/* Safety caveat (Class C) — DRIVEN by the backend's registration flag, not
              hardcoded: until TP2 is spatially co-registered to TP1, every count is an
              UNADJUDICATED CANDIDATE (equal array dimensions are not voxel alignment), so
              counts can include misregistration artefacts. Prefer the backend's authoritative
              `caveat` string. registration_verified is currently always false. */}
          {result.registration_verified ? (
            <div className="rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-1.5 text-[10px] leading-snug text-emerald-700 dark:text-emerald-300">
              {t('longitudinal.registrationVerified',
                'Timepoints spatially co-registered — changes are spatially valid (still review before diagnosis).')}
            </div>
          ) : (
            <div className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-[10px] leading-snug text-amber-700 dark:text-amber-300">
              {result.caveat || t('longitudinal.candidateCaveat',
                'Unadjudicated change candidates — spatial registration NOT verified. Two timepoints with equal dimensions are not necessarily aligned; a radiologist must review each candidate before it informs a diagnosis.')}
            </div>
          )}
          {result.spacing_resolved === false && (
            <div className="rounded border border-orange-500/40 bg-orange-500/10 px-2 py-1 text-[10px] leading-snug text-orange-700 dark:text-orange-300">
              {t('longitudinal.spacingFallback',
                'Voxel spacing could not be resolved — volumes (mL) are approximate.')}
            </div>
          )}
          {/* Co-registration status (advisory). Rigid registration removes head-pose
              misregistration false positives; it is NOT lesion-scale certification
              (registration_verified stays false). Transparent method disclosure — a
              gap most commercial tools leave as a black box. */}
          <div className="flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-gray-400">
            <span className={`w-1.5 h-1.5 rounded-full ${result.registration_applied ? 'bg-sky-500' : 'bg-gray-400'}`} />
            {result.registration_applied ? (
              <span>
                {t('longitudinal.coregistered', 'Rigidly co-registered (TP2→TP1, advisory)')}
                {typeof result.registration_advisory_qc?.translation_mm === 'number' &&
                  ` · ${result.registration_advisory_qc.translation_mm.toFixed(1)} mm, ${(result.registration_advisory_qc.rotation_deg ?? 0).toFixed(1)}°`}
              </span>
            ) : (
              <span>{t('longitudinal.indexAligned', 'Index-aligned (no source image to register)')}</span>
            )}
          </div>
          {/* FLAIR subtraction confirmation summary (advisory new-lesion filter). */}
          {result.subtraction_available && result.subtraction_summary && result.subtraction_summary.new_total > 0 && (
            <div className="flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-gray-400">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-500" />
              <span>
                {t('longitudinal.subSummary',
                  'FLAIR subtraction: {{c}} of {{n}} new candidates confirmed brighter at follow-up',
                  { c: result.subtraction_summary.new_subtraction_confirmed, n: result.subtraction_summary.new_total })}
              </span>
            </div>
          )}

          {/* Status Counts (candidates) */}
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(result.status_counts).map(([status, count]) => (
              count > 0 && (
                <span
                  key={status}
                  className="flex items-center gap-1 px-1.5 py-0.5 bg-gray-100 dark:bg-gray-900/60 rounded text-[9px]"
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${statusBg(status)}`} />
                  <span className={statusColor(status)}>
                    {count} {t(`longitudinal.${status}`, status)}
                    {!result.registration_verified ? ` ${t('longitudinal.candidateSuffix', 'cand.')}` : ''}
                  </span>
                </span>
              )
            ))}
          </div>

          {/* Legend for the fused TP1/TP2 overlay painted on the 2D viewport
              (SegmentationCanvasLocal) — colors match the canvas exactly so the change map
              is readable. Red = TP2-only = NEW lesion candidate. */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[9px] text-gray-500 dark:text-gray-400">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-sm" style={{ background: 'rgb(65,135,245)' }} />
              {t('longitudinal.legendTp1', 'TP1 only (resolved cand.)')}
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-sm" style={{ background: 'rgb(50,205,50)' }} />
              {t('longitudinal.legendBoth', 'Both (stable)')}
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-sm" style={{ background: 'rgb(245,70,70)' }} />
              {t('longitudinal.legendTp2', 'TP2 only (NEW cand.)')}
            </span>
          </div>

          {/* Expandable Table */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-200 transition-colors"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {t('longitudinal.changeTable', 'Change Table')} ({result.changes.length})
          </button>

          {expanded && result.changes.length > 0 && (
            <div className="max-h-48 overflow-y-auto">
              <table className="w-full text-[9px]">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-300 dark:border-gray-700">
                    <th className="text-center py-0.5 px-1">{t('longitudinal.statusCol', 'Status')}</th>
                    <th className="text-right py-0.5 px-1">TP1</th>
                    <th className="text-right py-0.5 px-1">TP2</th>
                    <th className="text-right py-0.5 px-1">&Delta;%</th>
                  </tr>
                </thead>
                <tbody>
                  {result.changes.map((change, i) => (
                    <tr
                      key={i}
                      onClick={() => handleLesionClick(change)}
                      className="cursor-pointer border-b border-gray-200 dark:border-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
                    >
                      <td className="py-0.5 px-1 text-center">
                        <span className="flex items-center justify-center gap-0.5">
                          {statusIcon(change.status)}
                          <span className={statusColor(change.status)}>
                            {t(`longitudinal.${change.status}`, change.status)}
                          </span>
                          {/* FLAIR-subtraction confirmation badge (new candidates only) */}
                          {change.status === 'new' && change.subtraction_confirmed === true && (
                            <span
                              title={t('longitudinal.subConfirmedTip', 'FLAIR brighter at follow-up (signal {{s}} SD) — supports a genuine new lesion', { s: (change.subtraction_signal ?? 0).toFixed(1) })}
                              className="ml-0.5 rounded bg-sky-500/15 px-1 text-[8px] font-semibold text-sky-600 dark:text-sky-300"
                            >✓sub</span>
                          )}
                          {change.status === 'new' && change.subtraction_confirmed === false && (
                            <span
                              title={t('longitudinal.subUnconfirmedTip', 'No follow-up brightening on FLAIR subtraction — review for artifact')}
                              className="ml-0.5 rounded bg-gray-400/15 px-1 text-[8px] font-semibold text-gray-500 dark:text-gray-400"
                            >○sub</span>
                          )}
                        </span>
                      </td>
                      <td className="py-0.5 px-1 text-right font-mono text-gray-600 dark:text-gray-300">
                        {change.volume_tp1_ml > 0 ? `${change.volume_tp1_ml.toFixed(3)}` : '\u2014'}
                      </td>
                      <td className="py-0.5 px-1 text-right font-mono text-gray-800 dark:text-white">
                        {change.volume_tp2_ml > 0 ? `${change.volume_tp2_ml.toFixed(3)}` : '\u2014'}
                      </td>
                      <td className={`py-0.5 px-1 text-right font-mono ${statusColor(change.status)}`}>
                        {change.status === 'new' ? '+new' :
                         change.status === 'resolved' ? 'gone' :
                         `${change.change_percent > 0 ? '+' : ''}${change.change_percent.toFixed(1)}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
