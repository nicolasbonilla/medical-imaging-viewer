/**
 * Longitudinal Comparison Panel
 *
 * Picks two visits (study + lesion segmentation each), compares them and shows the result in
 * LongitudinalResultPanel: unconfirmed change candidates with the radiologist's decisions, the
 * measured false-candidate rate, or an abstention when the acquisition differs (CAPA-013,
 * RC-060/061/062, HAZ-007). Every text is localised (en/es/de).
 *
 * @module components/LongitudinalCompare
 */

import { useState, useCallback, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { TrendingUp, Loader2, AlertCircle } from 'lucide-react';
import { segmentationAPI } from '@/api/segmentation';
import { studyAPI } from '@/api/study';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type { LongitudinalResult, StudySummary, SegmentationResponse, SELResult } from '@/types';
import { LongitudinalResultPanel } from './LongitudinalResultPanel';

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

function formatStudyDate(dateStr: string, lang: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString(lang || 'en', { month: 'short', day: 'numeric', year: 'numeric' });
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
  const { t, i18n } = useTranslation();
  const lang = i18n.language || 'en';
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

  // SEL (slowly-expanding lesion) on-demand detection state
  const [selResult, setSelResult] = useState<SELResult | null>(null);
  const [selLoading, setSelLoading] = useState(false);

  const handleDetectSELs = useCallback(async () => {
    if (!tp1SegId || !tp2SegId) return;
    setSelLoading(true);
    setSelResult(null);
    try {
      const r = await segmentationAPI.detectSELs(
        { type: 'segmentation', id: tp1SegId },
        { type: 'segmentation', id: tp2SegId },
      );
      setSelResult(r);
    } catch (err: any) {
      setSelResult({ ok: false, reason: err?.response?.data?.detail || err?.message || t('longitudinal.selFailed'),
        sels: [], n_existing: 0, n_sel: 0 });
    } finally {
      setSelLoading(false);
    }
  }, [tp1SegId, tp2SegId, t]);

  // Invalidate a stale result: clearing the selection must also drop the on-canvas
  // overlays (fused masks + subtraction heatmap), so a heatmap can never outlive the
  // comparison it came from or persist after its toggle button disappears (Class C —
  // no stale/misleading overlay over a now-different selection).
  const invalidate = useCallback(() => {
    setResult(null);
    setSelResult(null);
    useSegmentationStore.getState().clearLongitudinalOverlay();
  }, []);
  // Also clear the overlays when this panel unmounts.
  useEffect(() => () => useSegmentationStore.getState().clearLongitudinalOverlay(), []);

  // Fetch file_ids and segmentations for each selected study
  const { data: tp1FileIds = [] } = useStudyFileIds(tp1StudyId || null);
  const { data: tp2FileIds = [] } = useStudyFileIds(tp2StudyId || null);
  const { data: tp1Segs = [] } = useStudyLesionSegs(tp1FileIds, tp1StudyId || null);
  const { data: tp2Segs = [] } = useStudyLesionSegs(tp2FileIds, tp2StudyId || null);

  // Review of PR #63: visit 2 must be a different, later visit than visit 1 (the backend refuses
  // otherwise; here the Compare button stays disabled and says why).
  const visitOrderProblem = useMemo(() => {
    if (!tp1StudyId || !tp2StudyId) return null;
    if (tp1StudyId === tp2StudyId) return 'visitSame';
    const d1 = new Date(sortedStudies.find((s) => s.id === tp1StudyId)?.study_date ?? '').getTime();
    const d2 = new Date(sortedStudies.find((s) => s.id === tp2StudyId)?.study_date ?? '').getTime();
    return Number.isFinite(d1) && Number.isFinite(d2) && d2 > d1 ? null : 'visitOrder';
  }, [tp1StudyId, tp2StudyId, sortedStudies]);
  const canCompare = Boolean(tp1SegId && tp2SegId && !visitOrderProblem);

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

      // Decode the FLAIR subtraction heatmap (co-registered TP1 grid) for the overlay.
      if (data.subtraction_volume_b64 && data.subtraction_shape) {
        try {
          const bin = atob(data.subtraction_volume_b64);
          const vol = new Uint8Array(bin.length);
          for (let i = 0; i < bin.length; i++) vol[i] = bin.charCodeAt(i);
          const [depth, height, width] = data.subtraction_shape;
          useSegmentationStore.getState().setLongitudinalSubtraction({
            volume: vol, dims: { depth, height, width }, clipSd: data.subtraction_clip_sd ?? 3,
          });
        } catch {
          useSegmentationStore.getState().setLongitudinalSubtraction(null);
        }
      } else {
        useSegmentationStore.getState().setLongitudinalSubtraction(null);
      }

      setResult(data);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.response?.data?.error?.message || err?.message || String(err);
      setError(detail);
    } finally {
      setIsLoading(false);
    }
  }, [tp1SegId, tp2SegId, canCompare]);

  if (sortedStudies.length < 2) {
    return null;
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <TrendingUp className="w-3.5 h-3.5 text-indigo-400" />
        <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          {t('longitudinal.title')}
        </span>
      </div>

      {/* TP1: Study + Segmentation */}
      <div className="space-y-1">
        <label className="text-[9px] text-gray-500 block font-medium">
          {t('longitudinal.tp1')}
        </label>
        <select
          value={tp1StudyId}
          onChange={(e) => { setTp1StudyId(e.target.value); setTp1SegId(''); invalidate(); }}
          className="w-full px-1.5 py-1 bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-white rounded text-[10px] border border-gray-200 dark:border-gray-600"
        >
          <option value="">{t('longitudinal.selectStudy')}</option>
          {sortedStudies.map((s) => (
            <option key={s.id} value={s.id}>
              {formatStudyDate(s.study_date, lang)} — {s.study_description || s.modality}
              {s.id === currentStudyId ? ` (${t('longitudinal.current')})` : ''}
            </option>
          ))}
        </select>
        {tp1StudyId && tp1Segs.length > 0 && (
          <select
            value={tp1SegId}
            onChange={(e) => { setTp1SegId(e.target.value); invalidate(); }}
            className="w-full px-1.5 py-1 bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-white rounded text-[10px] border border-gray-200 dark:border-gray-600"
          >
            <option value="">{t('longitudinal.selectSegmentation')}</option>
            {tp1Segs.map((s) => (
              <option key={s.segmentation_id} value={s.segmentation_id}>
                {s.metadata?.description || s.segmentation_id.slice(0, 8)}
              </option>
            ))}
          </select>
        )}
        {tp1StudyId && tp1Segs.length === 0 && tp1FileIds.length > 0 && (
          <p className="text-[9px] text-gray-500 italic">{t('longitudinal.noLesionSegs')}</p>
        )}
      </div>

      {/* TP2: Study + Segmentation */}
      <div className="space-y-1">
        <label className="text-[9px] text-gray-500 block font-medium">
          {t('longitudinal.tp2')}
        </label>
        <select
          value={tp2StudyId}
          onChange={(e) => { setTp2StudyId(e.target.value); setTp2SegId(''); invalidate(); }}
          className="w-full px-1.5 py-1 bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-white rounded text-[10px] border border-gray-200 dark:border-gray-600"
        >
          <option value="">{t('longitudinal.selectStudy')}</option>
          {sortedStudies.map((s) => (
            <option key={s.id} value={s.id}>
              {formatStudyDate(s.study_date, lang)} — {s.study_description || s.modality}
              {s.id === currentStudyId ? ` (${t('longitudinal.current')})` : ''}
            </option>
          ))}
        </select>
        {tp2StudyId && tp2Segs.length > 0 && (
          <select
            value={tp2SegId}
            onChange={(e) => { setTp2SegId(e.target.value); invalidate(); }}
            className="w-full px-1.5 py-1 bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-white rounded text-[10px] border border-gray-200 dark:border-gray-600"
          >
            <option value="">{t('longitudinal.selectSegmentation')}</option>
            {tp2Segs.map((s) => (
              <option key={s.segmentation_id} value={s.segmentation_id}>
                {s.metadata?.description || s.segmentation_id.slice(0, 8)}
              </option>
            ))}
          </select>
        )}
        {tp2StudyId && tp2Segs.length === 0 && tp2FileIds.length > 0 && (
          <p className="text-[9px] text-gray-500 italic">{t('longitudinal.noLesionSegs')}</p>
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
          t('longitudinal.compare')
        )}
      </button>

      {visitOrderProblem && (
        <p data-testid="longitudinal-visit-order" className="text-[10px] text-orange-600 dark:text-orange-300">
          {t(`longitudinal.${visitOrderProblem}`)}
        </p>
      )}

      {error && (
        <div className="flex items-center gap-1 text-red-400 text-[10px]">
          <AlertCircle className="w-3 h-3" />
          <span className="truncate">{error}</span>
        </div>
      )}

      {result && (
        <>
          <LongitudinalResultPanel
            result={result}
            tp1SegId={tp1SegId}
            tp2SegId={tp2SegId}
            onNavigateToSlice={onNavigateToSlice}
            onReviewed={handleCompare}
          />

          {/* SEL (slowly-expanding lesion) detection — vanguard smoldering-disease
              biomarker, on-demand (deformable registration). CANDIDATE, single-interval.
              Not offered when the comparison abstains (review of PR #63). */}
          {!result.abstained && (
          <div className="rounded border border-fuchsia-500/30 bg-fuchsia-500/5 px-2 py-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold text-fuchsia-700 dark:text-fuchsia-300">
                {t('longitudinal.selTitle')}
              </span>
              <button
                type="button"
                onClick={handleDetectSELs}
                disabled={selLoading}
                className="rounded bg-fuchsia-600 px-2 py-0.5 text-[10px] font-medium text-white hover:bg-fuchsia-500 disabled:opacity-50"
              >
                {selLoading ? t('longitudinal.selRunning') : t('longitudinal.selDetect')}
              </button>
            </div>
            {selResult && (
              <div className="mt-1 text-[10px] leading-snug">
                {!selResult.ok ? (
                  <span className="text-gray-500 dark:text-gray-400">
                    {t('longitudinal.selUnavailable', { r: selResult.reason })}
                  </span>
                ) : (
                  <>
                    <span className="text-fuchsia-700 dark:text-fuchsia-300">
                      {t('longitudinal.selSummary',
                        { s: selResult.n_sel, e: selResult.n_existing,
                          bg: Math.round((selResult.background_expanding_fraction ?? 0) * 100) })}
                    </span>
                    {selResult.sels.length > 0 && (
                      <div className="mt-0.5 flex flex-col gap-0.5">
                        {selResult.sels.map((s, i) => (
                          <button
                            key={i}
                            type="button"
                            onClick={() => onNavigateToSlice?.(Math.round(s.centroid_z))}
                            className="flex items-center justify-between rounded px-1 py-0.5 text-left hover:bg-fuchsia-500/10"
                          >
                            <span className="text-gray-600 dark:text-gray-300">
                              {new Intl.NumberFormat(lang, { maximumFractionDigits: 3 }).format(s.baseline_volume_mm3 / 1000)} mL {t('longitudinal.selBaseline')}
                            </span>
                            <span className="font-mono text-fuchsia-600 dark:text-fuchsia-400">
                              {Math.round(s.expanding_fraction * 100)}% {t('longitudinal.selExpanding')}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                    <div className="mt-0.5 text-[9px] text-gray-400">
                      {t('longitudinal.selCaveat')}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
          )}
        </>
      )}
    </div>
  );
}
