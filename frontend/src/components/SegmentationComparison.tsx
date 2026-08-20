/**
 * Segmentation Comparison
 *
 * Compares two saved segmentations of the current study on TWO distinct quality
 * axes:
 *   - Dice (voxel overlap) + Hausdorff + volume difference, and
 *   - lesion-WISE detection: sensitivity (LTPR), precision (LPPV) and lesion F1,
 *     the ISBI-2015 / MSSEG-2016 challenge standard, computed with the shared
 *     18-connectivity convention (RC-030).
 *
 * Directionality is explicit: the FIRST mask is the prediction under test (A),
 * the SECOND is the reference / ground truth (B) — e.g. compare an AI or a
 * trainee segmentation (A) against an expert one (B).
 *
 * Activates the previously UI-less `segmentation/compare` endpoint.
 *
 * @module components/SegmentationComparison
 */
import { useMemo, useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { GitCompare, Loader2, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { segmentationAPI, type PairwiseComparison } from '@/api/segmentation';
import { studyAPI } from '@/api/study';
import { useViewerStore } from '@/store/useViewerStore';
import { classifySegOrigin } from '@/utils/segmentationList';
import type { SegmentationResponse } from '@/types';

/** Fetch all image file_ids for a study (mirrors LongitudinalCompare). */
function useStudyFileIds(studyId: string | null) {
  return useQuery({
    queryKey: ['study-file-ids', studyId],
    queryFn: async () => {
      if (!studyId) return [] as string[];
      const series = await studyAPI.listSeries(studyId);
      const allInstances = await Promise.all(series.map((s) => studyAPI.listInstances(s.id)));
      return allInstances.flat().map((inst) => inst.gcs_object_name).filter(Boolean) as string[];
    },
    enabled: !!studyId,
    staleTime: 5 * 60 * 1000,
  });
}

function useStudySegs(fileIds: string[], studyId: string | null) {
  return useQuery({
    queryKey: ['segmentations-compare', studyId],
    queryFn: async () => {
      if (fileIds.length === 0) return [] as SegmentationResponse[];
      const segs = await segmentationAPI.listSegmentationsByFileIds(fileIds);
      return segs.filter((s) => s.segmentation_id);
    },
    enabled: fileIds.length > 0,
    staleTime: 5 * 60 * 1000,
  });
}

function pct(x: number): string {
  return `${(x * 100).toFixed(1)}%`;
}

export function SegmentationComparison() {
  const { t } = useTranslation();
  const currentStudyId = useViewerStore((s) => s.currentStudyId);

  const [predId, setPredId] = useState<string>('');
  const [refId, setRefId] = useState<string>('');
  const [result, setResult] = useState<PairwiseComparison | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const { data: fileIds = [] } = useStudyFileIds(currentStudyId || null);
  const { data: segs = [] } = useStudySegs(fileIds, currentStudyId || null);

  const options = useMemo(
    () =>
      segs.map((s) => ({
        id: s.segmentation_id,
        name: s.metadata?.description || t('segmentation.defaultName', 'Segmentation'),
      })),
    [segs, t],
  );

  const nameFor = useCallback(
    (id: string) => options.find((o) => o.id === id)?.name || id,
    [options],
  );

  // Provenance-aware default (reuses the Tier-0 origin classifier): when the study has
  // both a human EXPERT mask and an AI mask, pre-select Expert = reference (B) and AI =
  // prediction (A). Then the metrics read as "how does the AI compare to the human ground
  // truth" — directly surfacing the project's core finding (legacy AI over-segments:
  // low precision / high LFPR). The user can still change either selection.
  useEffect(() => {
    if (predId || refId || segs.length < 2) return;
    const tagged = segs.map((s) => ({
      id: s.segmentation_id,
      origin: classifySegOrigin(s.metadata?.description || ''),
    }));
    const expert = tagged.find((x) => x.origin === 'expert');
    const ai = tagged.find((x) => x.origin === 'ai' || x.origin === 'ai-legacy');
    if (expert && ai && expert.id !== ai.id) {
      setRefId(expert.id);   // reference = human ground truth
      setPredId(ai.id);      // prediction = AI under test
    }
  }, [segs, predId, refId]);

  const canCompare = predId && refId && predId !== refId;

  const handleCompare = useCallback(async () => {
    if (!canCompare) return;
    setIsLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await segmentationAPI.compareMasks([
        { type: 'segmentation', id: predId, label: nameFor(predId) },
        { type: 'segmentation', id: refId, label: nameFor(refId) },
      ]);
      setResult(res.comparisons?.[0] ?? null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || String(err));
    } finally {
      setIsLoading(false);
    }
  }, [canCompare, predId, refId, nameFor]);

  // Only meaningful when the study has at least two segmentations to compare.
  if (options.length < 2) return null;

  const ld = result?.lesion_detection;

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center justify-between text-left"
      >
        <span className="flex items-center gap-1.5 text-xs font-semibold text-gray-200">
          <GitCompare className="w-3.5 h-3.5 text-indigo-400" />
          {t('comparison.title', 'Compare segmentations')}
        </span>
        {expanded ? (
          <ChevronUp className="w-3.5 h-3.5 text-gray-400" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
        )}
      </button>

      {expanded && (
        <div className="mt-2 flex flex-col gap-2">
          <label className="text-[10px] text-gray-400">
            {t('comparison.prediction', 'Prediction (A)')}
            <select
              value={predId}
              onChange={(e) => setPredId(e.target.value)}
              className="mt-0.5 w-full bg-gray-800 border border-gray-700 rounded text-[11px] text-gray-200 px-1.5 py-1"
            >
              <option value="">{t('comparison.select', 'Select…')}</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
            </select>
          </label>

          <label className="text-[10px] text-gray-400">
            {t('comparison.reference', 'Reference (B)')}
            <select
              value={refId}
              onChange={(e) => setRefId(e.target.value)}
              className="mt-0.5 w-full bg-gray-800 border border-gray-700 rounded text-[11px] text-gray-200 px-1.5 py-1"
            >
              <option value="">{t('comparison.select', 'Select…')}</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
            </select>
          </label>

          {predId && refId && predId === refId && (
            <div className="text-[10px] text-amber-400">
              {t('comparison.sameMask', 'Pick two different segmentations.')}
            </div>
          )}

          <button
            type="button"
            onClick={handleCompare}
            disabled={!canCompare || isLoading}
            className="flex items-center justify-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed rounded text-[11px] text-white py-1"
          >
            {isLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <GitCompare className="w-3 h-3" />}
            {t('comparison.compare', 'Compare')}
          </button>

          {error && (
            <div className="flex items-start gap-1 text-[10px] text-red-400">
              <AlertCircle className="w-3 h-3 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {result && (
            <div className="mt-1 flex flex-col gap-2 p-2 rounded-lg bg-gray-800/60 border border-gray-700/50">
              {/* Overlap axis */}
              <div>
                <div className="text-[9px] uppercase tracking-wide text-gray-500 mb-0.5">
                  {t('comparison.overlap', 'Overlap')}
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-gray-200">
                  <span title={t('comparison.diceTip', 'Voxel overlap (Sørensen–Dice)')}>
                    Dice <b className="text-white">{result.dice.toFixed(3)}</b>
                  </span>
                  {result.ndsc != null && (
                    <span title={t('comparison.ndscTip', 'Normalised Dice (Shifts) — load-corrected, comparable across lesion loads')}>
                      nDSC <b className="text-white">{result.ndsc.toFixed(3)}</b>
                    </span>
                  )}
                  {result.hausdorff_mm != null && (
                    <span title={t('comparison.hd95Tip', '95th-percentile surface distance (worst-case)')}>
                      HD95 <b className="text-white">{result.hausdorff_mm.toFixed(1)} mm</b>
                    </span>
                  )}
                  {result.assd_mm != null && (
                    <span title={t('comparison.assdTip', 'Average symmetric surface distance (mean boundary)')}>
                      ASSD <b className="text-white">{result.assd_mm.toFixed(1)} mm</b>
                    </span>
                  )}
                  <span>
                    Δvol <b className="text-white">{result.volume.diff_percent.toFixed(1)}%</b>
                  </span>
                  {result.avd != null && (
                    <span title={t('comparison.avdTip', 'Absolute volume difference vs reference (MSSEG/ISBI), unsigned')}>
                      AVD <b className="text-white">{pct(result.avd)}</b>
                    </span>
                  )}
                </div>
              </div>

              {/* Detection axis */}
              {ld && (
                <div>
                  <div className="text-[9px] uppercase tracking-wide text-gray-500 mb-0.5">
                    {t('comparison.detection', 'Lesion detection')}{' '}
                    <span className="text-gray-600 normal-case">(18-conn, ISBI/MSSEG)</span>
                  </div>
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-gray-200">
                    <span title={t('comparison.f1Tip', 'Harmonic mean of sensitivity and precision')}>
                      F1 <b className="text-indigo-300">{ld.lesion_f1.toFixed(3)}</b>
                    </span>
                    <span title={t('comparison.sensTip', 'Reference lesions detected / reference lesions')}>
                      {t('comparison.sensitivity', 'Sens')} <b className="text-white">{pct(ld.sensitivity_ltpr)}</b>
                    </span>
                    <span title={t('comparison.precTip', 'Predicted lesions that are real / predicted lesions')}>
                      {t('comparison.precision', 'Prec')} <b className="text-white">{pct(ld.precision_lppv)}</b>
                    </span>
                    {ld.false_positive_rate_lfpr != null && (
                      <span title={t('comparison.lfprTip', 'False-positive predicted lesions / predicted lesions (= 1 − precision)')}>
                        LFPR <b className="text-white">{pct(ld.false_positive_rate_lfpr)}</b>
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5 text-[10px] text-gray-400">
                    <span className="text-green-400">TP {ld.true_positives}</span>
                    <span className="text-red-400">FP {ld.false_positives}</span>
                    <span className="text-amber-400">FN {ld.false_negatives}</span>
                    <span className="text-gray-500">
                      {t('comparison.counts', 'A={{a}} · B={{b}} lesions', {
                        a: ld.pred_lesion_count,
                        b: ld.ref_lesion_count,
                      })}
                    </span>
                  </div>

                  {/* Detection sensitivity by lesion SIZE — exposes the small-lesion gap a
                      single LTPR hides (small lesions are systematically missed). */}
                  {ld.size_stratified_sensitivity && ld.size_stratified_sensitivity.buckets.some((b) => b.n_ref > 0) && (
                    <div className="mt-1">
                      <div className="text-[9px] uppercase tracking-wide text-gray-500 mb-0.5">
                        {t('comparison.bySize', 'Detection by lesion size')}{' '}
                        <span className="text-gray-600 normal-case">({ld.size_stratified_sensitivity.unit})</span>
                      </div>
                      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-gray-300">
                        {ld.size_stratified_sensitivity.buckets
                          .filter((b) => b.n_ref > 0)
                          .map((b) => (
                            <span key={b.bucket} title={`${b.detected}/${b.n_ref} ${t('comparison.detected', 'detected')}`}>
                              {b.bucket}{' '}
                              <b className={b.sensitivity_ltpr != null && b.sensitivity_ltpr < 0.5 ? 'text-amber-300' : 'text-white'}>
                                {b.sensitivity_ltpr != null ? pct(b.sensitivity_ltpr) : '—'}
                              </b>
                            </span>
                          ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Honest framing: these are evaluation-vs-reference metrics, not clinical accuracy. */}
              <div className="text-[9px] text-gray-500 italic">
                {t('comparison.caveat', 'Evaluation metrics vs the reference mask (B) — not a measure of clinical accuracy.')}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
