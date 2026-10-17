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
import { Button } from '@/components/ui';
import type { SegmentationResponse } from '@/types';

/** Shared control styles (design-system v2 tokens). */
const SELECT_CLS =
  'mt-1 h-8 w-full rounded-lg border border-surface-border bg-surface-base px-2 text-xs text-ink-base ' +
  'transition-colors hover:border-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60';
const OVERLINE = 'mb-1 text-xs font-medium uppercase tracking-wide text-ink-faint';
/** A metric's numeric value: tabular figures so columns of results do not jitter. */
const VALUE = 'font-semibold tabular-nums text-ink-base';

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
        aria-expanded={expanded}
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center justify-between rounded text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-ink-base">
          <GitCompare className="h-4 w-4 text-brand-400" aria-hidden />
          {t('comparison.title', 'Compare segmentations')}
        </span>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-ink-muted" aria-hidden />
        ) : (
          <ChevronDown className="h-4 w-4 text-ink-muted" aria-hidden />
        )}
      </button>

      {expanded && (
        <div className="mt-2.5 flex flex-col gap-2.5">
          <label className="block text-xs font-medium text-ink-muted">
            {t('comparison.prediction', 'Prediction (A)')}
            <select
              value={predId}
              onChange={(e) => setPredId(e.target.value)}
              className={SELECT_CLS}
            >
              <option value="">{t('comparison.select', 'Select…')}</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
            </select>
          </label>

          <label className="block text-xs font-medium text-ink-muted">
            {t('comparison.reference', 'Reference (B)')}
            <select
              value={refId}
              onChange={(e) => setRefId(e.target.value)}
              className={SELECT_CLS}
            >
              <option value="">{t('comparison.select', 'Select…')}</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
            </select>
          </label>

          {predId && refId && predId === refId && (
            <div className="text-xs text-clinical-warn">
              {t('comparison.sameMask', 'Pick two different segmentations.')}
            </div>
          )}

          <Button
            variant="primary"
            size="sm"
            fullWidth
            onClick={handleCompare}
            disabled={!canCompare || isLoading}
            aria-busy={isLoading || undefined}
            leftIcon={isLoading
              ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              : <GitCompare className="h-3.5 w-3.5" aria-hidden />}
          >
            {t('comparison.compare', 'Compare')}
          </Button>

          {error && (
            <div className="flex items-start gap-1.5 text-xs text-clinical-crit">
              <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
              <span className="min-w-0 break-words">{error}</span>
            </div>
          )}

          {result && (
            <div className="flex flex-col gap-2.5 rounded-lg border border-surface-border bg-surface-raised p-2.5">
              {/* Overlap axis */}
              <div>
                <div className={OVERLINE}>
                  {t('comparison.overlap', 'Overlap')}
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-muted">
                  <span title={t('comparison.diceTip', 'Voxel overlap (Sørensen–Dice)')}>
                    Dice <b className={VALUE}>{result.dice.toFixed(3)}</b>
                  </span>
                  {result.ndsc != null && (
                    <span title={t('comparison.ndscTip', 'Normalised Dice (Shifts) — load-corrected, comparable across lesion loads')}>
                      nDSC <b className={VALUE}>{result.ndsc.toFixed(3)}</b>
                    </span>
                  )}
                  {result.hausdorff_mm != null && (
                    <span title={t('comparison.hd95Tip', '95th-percentile surface distance (worst-case)')}>
                      HD95 <b className={VALUE}>{result.hausdorff_mm.toFixed(1)} mm</b>
                    </span>
                  )}
                  {result.assd_mm != null && (
                    <span title={t('comparison.assdTip', 'Average symmetric surface distance (mean boundary)')}>
                      ASSD <b className={VALUE}>{result.assd_mm.toFixed(1)} mm</b>
                    </span>
                  )}
                  <span>
                    Δvol <b className={VALUE}>{result.volume.diff_percent.toFixed(1)}%</b>
                  </span>
                  {result.avd != null && (
                    <span title={t('comparison.avdTip', 'Absolute volume difference vs reference (MSSEG/ISBI), unsigned')}>
                      AVD <b className={VALUE}>{pct(result.avd)}</b>
                    </span>
                  )}
                </div>
              </div>

              {/* Detection axis */}
              {ld && (
                <div className="border-t border-surface-border pt-2.5">
                  <div className={OVERLINE}>
                    {t('comparison.detection', 'Lesion detection')}{' '}
                    <span className="font-normal normal-case tracking-normal">(18-conn, ISBI/MSSEG)</span>
                  </div>
                  <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-muted">
                    <span title={t('comparison.f1Tip', 'Harmonic mean of sensitivity and precision')}>
                      F1 <b className="font-semibold tabular-nums text-brand-400">{ld.lesion_f1.toFixed(3)}</b>
                    </span>
                    <span title={t('comparison.sensTip', 'Reference lesions detected / reference lesions')}>
                      {t('comparison.sensitivity', 'Sens')} <b className={VALUE}>{pct(ld.sensitivity_ltpr)}</b>
                    </span>
                    <span title={t('comparison.precTip', 'Predicted lesions that are real / predicted lesions')}>
                      {t('comparison.precision', 'Prec')} <b className={VALUE}>{pct(ld.precision_lppv)}</b>
                    </span>
                    {ld.false_positive_rate_lfpr != null && (
                      <span title={t('comparison.lfprTip', 'False-positive predicted lesions / predicted lesions (= 1 − precision)')}>
                        LFPR <b className={VALUE}>{pct(ld.false_positive_rate_lfpr)}</b>
                      </span>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs tabular-nums text-ink-muted">
                    <span className="text-clinical-good">TP {ld.true_positives}</span>
                    <span className="text-clinical-crit">FP {ld.false_positives}</span>
                    <span className="text-clinical-warn">FN {ld.false_negatives}</span>
                    <span className="text-ink-muted">
                      {t('comparison.counts', 'A={{a}} · B={{b}} lesions', {
                        a: ld.pred_lesion_count,
                        b: ld.ref_lesion_count,
                      })}
                    </span>
                  </div>

                  {/* Detection sensitivity by lesion SIZE — exposes the small-lesion gap a
                      single LTPR hides (small lesions are systematically missed). */}
                  {ld.size_stratified_sensitivity && ld.size_stratified_sensitivity.buckets.some((b) => b.n_ref > 0) && (
                    <div className="mt-2.5">
                      <div className={OVERLINE}>
                        {t('comparison.bySize', 'Detection by lesion size')}{' '}
                        <span className="font-normal normal-case tracking-normal">({ld.size_stratified_sensitivity.unit})</span>
                      </div>
                      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs tabular-nums text-ink-soft">
                        {ld.size_stratified_sensitivity.buckets
                          .filter((b) => b.n_ref > 0)
                          .map((b) => (
                            <span key={b.bucket} title={`${b.detected}/${b.n_ref} ${t('comparison.detected', 'detected')}`}>
                              {b.bucket}{' '}
                              <b className={b.sensitivity_ltpr != null && b.sensitivity_ltpr < 0.5
                                ? 'font-semibold text-clinical-warn'
                                : 'font-semibold text-ink-base'}>
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
              <div className="border-t border-surface-border pt-2 text-xs italic leading-snug text-ink-muted">
                {t('comparison.caveat', 'Evaluation metrics vs the reference mask (B) — not a measure of clinical accuracy.')}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
