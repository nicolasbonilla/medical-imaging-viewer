/**
 * Lesion Dashboard
 *
 * Displays connected-component lesion statistics, DIS criteria badge,
 * region summary bars, size distribution, total burden, CSV export,
 * and MAGNIMS auto-classification (SynthSeg + EDT / geometric).
 * Click on a lesion row to navigate to its centroid slice.
 *
 * @module components/LesionDashboard
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Activity,
  Loader2,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Download,
  ChevronDown,
  ChevronUp,
  MapPin,
  Zap,
  Info,
} from 'lucide-react';
import { segmentationAPI } from '@/api/segmentation';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import {
  MAGNIMS_LESION_LABELS,
  type LesionAnalysisResult,
  type DISAssessment,
  type DISExternalEvidence,
  type LesionInfo,
  type RegionClassificationResult,
  type ClassificationMethod,
  type LesionAnnotation,
  type CVSSummary,
  type PRLSummary,
} from '@/types';


interface LesionDashboardProps {
  segmentationId: string;
  onNavigateToSlice?: (sliceIndex: number) => void;
  /** Called after auto-classify updates the mask on the server — parent should reload mask */
  onMaskUpdated?: () => void;
}

const REGION_COLORS: Record<string, string> = {
  Periventricular: 'bg-red-500',
  Juxtacortical: 'bg-green-500',
  Infratentorial: 'bg-blue-500',
  'Deep White Matter': 'bg-yellow-500',
};

const REGION_TEXT_COLORS: Record<string, string> = {
  Periventricular: 'text-red-400',
  Juxtacortical: 'text-green-400',
  Infratentorial: 'text-blue-400',
  'Deep White Matter': 'text-yellow-400',
};

function sizeColor(cat: string): string {
  if (cat === 'large') return 'text-red-400';
  if (cat === 'medium') return 'text-yellow-400';
  return 'text-gray-400';
}

function regionBarWidth(vol: number, maxVol: number): string {
  if (maxVol === 0) return '0%';
  return `${Math.max(4, (vol / maxVol) * 100)}%`;
}

function confidenceBadge(confidence: number): string {
  if (confidence >= 0.85) return 'bg-green-900/40 text-green-300 border-green-700/50';
  if (confidence >= 0.70) return 'bg-yellow-900/40 text-yellow-300 border-yellow-700/50';
  return 'bg-red-900/40 text-red-300 border-red-700/50';
}

export function LesionDashboard({ segmentationId, onNavigateToSlice, onMaskUpdated }: LesionDashboardProps) {
  const { t } = useTranslation();
  const reloadMaskCallback = useSegmentationStore((s) => s.reloadMaskCallback);
  const currentSegmentation = useSegmentationStore((s) => s.currentSegmentation);
  const [analysis, setAnalysis] = useState<LesionAnalysisResult | null>(null);
  const [dis, setDis] = useState<DISAssessment | null>(null);
  const [classification, setClassification] = useState<RegionClassificationResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isClassifying, setIsClassifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [highlightedLesion, setHighlightedLesion] = useState<number | null>(null);
  const [classifyMethod, setClassifyMethod] = useState<ClassificationMethod>('auto');
  const [lesionAnnotations, setLesionAnnotations] = useState<Record<number, Partial<LesionAnnotation>>>({});
  const [cvsSummary, setCvsSummary] = useState<CVSSummary | null>(null);
  const [prlSummary, setPrlSummary] = useState<PRLSummary | null>(null);
  const annotationDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // McDonald 2024 external evidence the brain MRI can't supply (spinal cord /
  // optic nerve) + supportive specificity markers. A checked box = present (true);
  // unchecked = not provided. Changing it re-queries the DIS endpoint.
  const [disEvidence, setDisEvidence] = useState<DISExternalEvidence>({});
  const [disEvidenceLoading, setDisEvidenceLoading] = useState(false);

  const applyDisEvidence = useCallback(
    async (next: DISExternalEvidence) => {
      setDisEvidence(next);
      setDisEvidenceLoading(true);
      try {
        const r = await segmentationAPI.getDISAssessment(segmentationId, next);
        setDis(r);
      } catch (e) {
        console.error('[LesionDashboard] DIS re-eval failed:', e);
      } finally {
        setDisEvidenceLoading(false);
      }
    },
    [segmentationId],
  );

  const toggleDisEvidence = useCallback(
    (key: keyof DISExternalEvidence) =>
      applyDisEvidence({ ...disEvidence, [key]: disEvidence[key] ? undefined : true }),
    [disEvidence, applyDisEvidence],
  );

  // Auto-populate from persisted analysis_data
  useEffect(() => {
    const cached = currentSegmentation?.metadata?.analysis_data;
    if (!cached) {
      setAnalysis(null);
      setDis(null);
      setClassification(null);
      setExpanded(false);
      return;
    }
    if (cached.lesion_analysis) {
      setAnalysis(cached.lesion_analysis);
      setExpanded(true);
    }
    if (cached.dis_assessment) setDis(cached.dis_assessment);
    if (cached.classification) setClassification(cached.classification);
    if (cached.lesion_annotations) {
      const map: Record<number, Partial<LesionAnnotation>> = {};
      for (const ann of cached.lesion_annotations) {
        map[ann.lesion_id] = ann;
      }
      setLesionAnnotations(map);
    }
    if (cached.cvs_summary) setCvsSummary(cached.cvs_summary);
    if (cached.prl_summary) setPrlSummary(cached.prl_summary);
  }, [segmentationId, currentSegmentation?.metadata?.analysis_data]);

  // Stale check: mask was edited after analysis was computed
  const isAnalysisStale = !!(
    analysis &&
    currentSegmentation?.metadata?.modified_at &&
    currentSegmentation?.metadata?.analysis_data?.analysis_mask_modified_at &&
    currentSegmentation.metadata.modified_at !== currentSegmentation.metadata.analysis_data.analysis_mask_modified_at
  );

  // Helper: patch Zustand currentSegmentation with updated analysis_data
  const patchAnalysisData = useCallback((patch: Record<string, unknown>) => {
    const store = useSegmentationStore.getState();
    const cur = store.currentSegmentation;
    if (!cur) return;
    store.setCurrentSegmentation({
      ...cur,
      metadata: {
        ...cur.metadata,
        analysis_data: {
          ...(cur.metadata?.analysis_data || {}),
          ...patch,
          analysis_mask_modified_at: cur.metadata.modified_at,
        },
      },
    });
  }, []);

  const handleAnalyze = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [analysisResult, disResult] = await Promise.all([
        segmentationAPI.analyzeLesions(segmentationId),
        segmentationAPI.getDISAssessment(segmentationId),
      ]);
      setAnalysis(analysisResult);
      setDis(disResult);
      setExpanded(true);
      patchAnalysisData({ lesion_analysis: analysisResult, dis_assessment: disResult });
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || String(err));
    } finally {
      setIsLoading(false);
    }
  }, [segmentationId, patchAnalysisData]);

  const handleClassifyRegions = useCallback(async () => {
    setIsClassifying(true);
    setError(null);
    try {
      const result = await segmentationAPI.classifyRegions(segmentationId, {
        method: classifyMethod,
      });
      setClassification(result);

      if (result.mask_updated) {
        await reloadMaskCallback?.();
        onMaskUpdated?.();
      }

      if (result.labels_updated) {
        const store = useSegmentationStore.getState();
        const curSeg = store.currentSegmentation;
        if (curSeg) {
          store.setCurrentSegmentation({
            ...curSeg,
            metadata: { ...curSeg.metadata, labels: MAGNIMS_LESION_LABELS },
          });
        }
      }

      const [analysisResult, disResult] = await Promise.all([
        segmentationAPI.analyzeLesions(segmentationId),
        segmentationAPI.getDISAssessment(segmentationId),
      ]);
      setAnalysis(analysisResult);
      setDis(disResult);
      setExpanded(true);

      patchAnalysisData({
        classification: result,
        lesion_analysis: analysisResult,
        dis_assessment: disResult,
      });
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || String(err));
    } finally {
      setIsClassifying(false);
    }
  }, [segmentationId, classifyMethod, onMaskUpdated, reloadMaskCallback, patchAnalysisData]);

  const handleLesionClick = useCallback((lesion: LesionInfo) => {
    const current = useSegmentationStore.getState().selectedLesion;
    if (current && current.id === lesion.id) {
      setHighlightedLesion(null);
      useSegmentationStore.getState().setSelectedLesion(null);
      return;
    }
    setHighlightedLesion(lesion.id);
    onNavigateToSlice?.(Math.round(lesion.centroid.z));
    useSegmentationStore.getState().setSelectedLesion(lesion);
  }, [onNavigateToSlice]);

  const handleExportCSV = useCallback(() => {
    if (!analysis) return;
    const headers = ['#', 'Region', 'Volume (mm\u00b3)', 'Volume (mL)', 'Size', 'Centroid Z', 'Centroid Y', 'Centroid X'];
    const quote = (v: string | number) => typeof v === 'string' && v.includes(',') ? `"${v}"` : String(v);
    const rows = analysis.lesions.map((l) => [
      l.id, l.region, l.volume_mm3, l.volume_ml, l.size_category,
      l.centroid.z, l.centroid.y, l.centroid.x,
    ]);
    const csv = [headers.join(','), ...rows.map((r) => r.map(quote).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `lesion_analysis_${segmentationId}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [analysis, segmentationId]);

  /** Save CVS/PRL annotation change (debounced 1s) */
  const handleAnnotationChange = useCallback((
    lesionId: number,
    field: 'cvs_status' | 'prl_status',
    value: string | null,
  ) => {
    setLesionAnnotations((prev) => ({
      ...prev,
      [lesionId]: {
        ...prev[lesionId],
        lesion_id: lesionId,
        [field]: value,
        annotated_by: 'manual',
      },
    }));
    if (annotationDebounceRef.current) clearTimeout(annotationDebounceRef.current);
    annotationDebounceRef.current = setTimeout(async () => {
      try {
        const allAnnotations = Object.values({
          ...lesionAnnotations,
          [lesionId]: {
            ...lesionAnnotations[lesionId],
            lesion_id: lesionId,
            [field]: value,
            annotated_by: 'manual',
          },
        });
        const result = await segmentationAPI.annotateLesions(segmentationId, allAnnotations);
        setCvsSummary(result.cvs_summary);
        setPrlSummary(result.prl_summary);
        patchAnalysisData({
          lesion_annotations: allAnnotations,
          cvs_summary: result.cvs_summary,
          prl_summary: result.prl_summary,
        });
      } catch (err: any) {
        console.error('[LesionDashboard] Failed to save annotations:', err?.message || err);
      }
    }, 1000);
  }, [segmentationId, lesionAnnotations, patchAnalysisData]);

  const maxRegionVol = analysis
    ? Math.max(...Object.values(analysis.regions).map((r) => r.total_volume_mm3), 1)
    : 1;

  return (
    <div style={{ background: '#1F2937', borderRadius: 8, padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-amber-400" />
          <span className="text-sm font-semibold text-white">
            {t('lesions.title', 'Lesion Analysis')}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {isAnalysisStale && (
            <span className="flex items-center gap-0.5 text-[9px] text-amber-400" title="Mask was edited since last analysis">
              <AlertCircle className="w-3 h-3" /> Outdated
            </span>
          )}
          <button
            onClick={handleAnalyze}
            disabled={isLoading}
            className="px-2 py-1 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-xs text-white transition-colors"
          >
            {isLoading ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              t('lesions.analyze', 'Analyze')
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-1 text-red-400 text-xs">
          <AlertCircle className="w-3 h-3" />
          <span>{error}</span>
        </div>
      )}

      {/* ================================================================ */}
      {/* LESION TABLE — Primary view, always visible when analysis exists */}
      {/* ================================================================ */}
      {analysis && analysis.lesions.length > 0 && (
        <div className="bg-gray-900/60 rounded-lg p-2.5 border border-gray-700/50">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-semibold text-white">
              {t('lesions.lesionTable', 'Lesion Table')}
            </span>
            <span className="text-[10px] text-gray-400 font-mono">
              {analysis.total_count} {t('lesions.totalCount', 'lesions')} &middot; {analysis.total_burden_ml.toFixed(2)} mL
            </span>
          </div>
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-[10px]">
              <thead className="sticky top-0 bg-gray-900/95 z-10">
                <tr className="text-gray-400 border-b border-gray-600">
                  <th className="text-left py-1 px-1.5">#</th>
                  <th className="text-left py-1 px-1.5">{t('lesions.region', 'Region')}</th>
                  <th className="text-right py-1 px-1.5">mm&sup3;</th>
                  <th className="text-right py-1 px-1.5">mL</th>
                  <th className="text-center py-1 px-1.5">{t('lesions.size', 'Size')}</th>
                </tr>
              </thead>
              <tbody>
                {analysis.lesions.map((lesion) => (
                  <tr
                    key={lesion.id}
                    onClick={() => handleLesionClick(lesion)}
                    className={`cursor-pointer border-b border-gray-800 transition-colors ${
                      highlightedLesion === lesion.id
                        ? 'bg-amber-900/40'
                        : 'hover:bg-gray-700/50'
                    }`}
                  >
                    <td className="py-1 px-1.5 text-gray-400">{lesion.id}</td>
                    <td className="py-1 px-1.5">
                      <span className="flex items-center gap-1">
                        <span className={`w-2 h-2 rounded-full ${REGION_COLORS[lesion.region] ?? 'bg-gray-500'}`} />
                        <span className="text-gray-200">{lesion.region}</span>
                      </span>
                    </td>
                    <td className="py-1 px-1.5 text-right font-mono text-gray-300">
                      {lesion.volume_mm3.toLocaleString()}
                    </td>
                    <td className="py-1 px-1.5 text-right font-mono text-white font-medium">
                      {lesion.volume_ml.toFixed(3)}
                    </td>
                    <td className={`py-1 px-1.5 text-center font-medium ${sizeColor(lesion.size_category)}`}>
                      {lesion.size_category === 'small' ? 'S' : lesion.size_category === 'medium' ? 'M' : 'L'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ================================================================ */}
      {/* Auto-Classify Regions (MAGNIMS) */}
      {/* ================================================================ */}
      <div className="bg-gray-900/60 rounded-lg p-2 space-y-2 border border-gray-700/50">
        <div className="flex items-center gap-1.5">
          <MapPin className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-xs font-semibold text-white">
            {t('classify.title', 'MAGNIMS Region Classification')}
          </span>
        </div>
        <p className="text-[9px] text-gray-400 leading-relaxed">
          {t('classify.description',
            'Auto-classify lesions into Periventricular, Juxtacortical, Infratentorial, and Deep WM regions using brain parcellation (SynthSeg) + distance transform analysis.'
          )}
        </p>

        {/* Method selector */}
        <div className="flex gap-1">
          {(['auto', 'msmask', 'geometric'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setClassifyMethod(m)}
              className={`flex-1 px-1.5 py-1 rounded text-[10px] transition-colors ${
                classifyMethod === m
                  ? 'bg-cyan-600 text-white'
                  : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
              }`}
            >
              {m === 'auto'
                ? t('classify.methodAuto', 'Auto (best)')
                : m === 'msmask'
                ? t('classify.methodMSMask', 'MSMask')
                : t('classify.methodGeometric', 'Geometric')}
            </button>
          ))}
        </div>

        <button
          onClick={handleClassifyRegions}
          disabled={isClassifying}
          className="w-full flex items-center justify-center gap-1.5 px-2 py-1.5 bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-xs text-white font-medium transition-colors"
        >
          {isClassifying ? (
            <>
              <Loader2 className="w-3 h-3 animate-spin" />
              {t('classify.classifying', 'Classifying...')}
            </>
          ) : (
            <>
              <Zap className="w-3 h-3" />
              {t('classify.classify', 'Auto-Classify Regions')}
            </>
          )}
        </button>

        {classification && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[9px]">
              <span className="text-gray-400">
                {t('classify.method', 'Method')}: <span className="text-cyan-300 font-medium">{classification.method}</span>
              </span>
              <span className="text-gray-400">
                {classification.processing_time_ms}ms
              </span>
            </div>
            <div className="flex flex-wrap gap-x-2 gap-y-1">
              {Object.entries(classification.classification_summary).map(([region, count]) => (
                <span key={region} className="flex items-center gap-1 text-[9px]">
                  <span className={`w-2 h-2 rounded-full ${REGION_COLORS[region] ?? 'bg-gray-500'}`} />
                  <span className={REGION_TEXT_COLORS[region] ?? 'text-gray-300'}>
                    {region}: {count}
                  </span>
                </span>
              ))}
            </div>
            {classification.lesions.length > 0 && (
              <div className="text-[9px] text-gray-400">
                {t('classify.avgConfidence', 'Avg confidence')}:{' '}
                <span className="text-white font-mono">
                  {(() => {
                    const withConf = classification.lesions.filter(l => l.confidence != null);
                    return withConf.length > 0
                      ? `${(withConf.reduce((sum, l) => sum + (l.confidence ?? 0), 0) / withConf.length * 100).toFixed(0)}%`
                      : 'N/A';
                  })()}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* DIS Badge — McDonald 2024 */}
      {dis ? (
        <div className={`flex items-center gap-2 p-2 rounded-lg ${
          (dis.dis_met_brain ?? dis.dis_met) ? 'bg-green-900/30 border border-green-700/50' : 'bg-red-900/30 border border-red-700/50'
        }`}>
          {(dis.dis_met_brain ?? dis.dis_met) ? (
            <CheckCircle2 className="w-4 h-4 text-green-400 shrink-0" />
          ) : (
            <XCircle className="w-4 h-4 text-red-400 shrink-0" />
          )}
          <div className="flex-1 min-w-0">
            <div className={`text-xs font-bold ${(dis.dis_met_brain ?? dis.dis_met) ? 'text-green-300' : 'text-red-300'}`}>
              DIS (Brain MRI): {dis.brain_regions_with_lesions ?? dis.regions_with_lesions}/{dis.brain_regions_evaluated ?? 3} {t('lesions.regions', 'regions')}
              {(dis.dis_met_brain ?? dis.dis_met) ? ` \u2014 ${t('lesions.criterionMet', 'Criterion Met')}` : ` \u2014 ${t('lesions.criterionNotMet', 'Not Met')}`}
            </div>
            <div className="flex flex-wrap gap-x-2 gap-y-0.5 mt-1">
              {Object.entries(dis.region_details).map(([name, detail]) => (
                <span key={name} className="flex items-center gap-0.5 text-[9px]">
                  {detail.present ? (
                    <CheckCircle2 className="w-2.5 h-2.5 text-green-400" />
                  ) : (
                    <XCircle className="w-2.5 h-2.5 text-gray-600" />
                  )}
                  <span className={detail.present ? 'text-green-300' : 'text-gray-500'}>{name}</span>
                  {typeof detail.qualifying_lesion_count === 'number' && (
                    <span
                      className={detail.present ? 'text-green-400/80' : 'text-gray-600'}
                      title={t(
                        'lesions.qualifyingLesionsTooltip',
                        'Lesions in this region meeting the MAGNIMS size/location criteria; a region counts toward DIS when this is ≥ 1',
                      )}
                    >
                      ({detail.qualifying_lesion_count})
                    </span>
                  )}
                </span>
              ))}
            </div>
            {dis.note && (
              <div className="text-[8px] text-gray-500 mt-1 italic">{dis.note}</div>
            )}
            {dis.dis_criteria_version && (
              <div className="text-[7px] text-gray-600 mt-0.5">{dis.dis_criteria_version}</div>
            )}
          </div>
        </div>
      ) : !classification && analysis && (
        <div className="flex items-center gap-2 p-2 rounded-lg bg-gray-800/50 border border-gray-700/50">
          <Info className="w-4 h-4 text-gray-500 shrink-0" />
          <span className="text-[10px] text-gray-400">
            {t('lesions.classifyFirst', 'Classify regions first to evaluate DIS criteria')}
          </span>
        </div>
      )}

      {/* McDonald 2024: five-topography integration + external evidence.
          Decision support only — never a diagnosis (CMSC guidance). */}
      {dis && (
        <div className="p-2 rounded-lg bg-indigo-950/30 border border-indigo-800/40 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold text-indigo-200">
              {t('lesions.mcdonald2024', 'McDonald 2024 · 5 topographies')}
            </span>
            <span className="text-[10px] text-indigo-100 font-bold">
              {dis.total_topographies_involved}/5
              {disEvidenceLoading && <span className="ml-1 text-indigo-400 animate-pulse">…</span>}
            </span>
          </div>

          {dis.dit_waiver_supported && (
            <div className="text-[9px] text-emerald-300 bg-emerald-900/20 border border-emerald-800/40 rounded px-1.5 py-1">
              {t(
                'lesions.ditWaiver',
                '≥4 of 5 topographies — dissemination in time may be waived (2024). Clinical correlation required.',
              )}
            </div>
          )}

          {/* External evidence the brain MRI can't supply */}
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {([
              ['optic_nerve_involved', t('lesions.opticNerve', 'Optic nerve')],
              ['spinal_cord_involved', t('lesions.spinalCord', 'Spinal cord')],
              ['cvs_positive', t('lesions.cvs', 'Central vein sign')],
              ['prl_present', t('lesions.prl', 'Paramagnetic rim')],
              ['csf_specific', t('lesions.csf', 'CSF-specific (OCB/kFLC)')],
            ] as [keyof DISExternalEvidence, string][]).map(([key, label]) => (
              <label key={key} className="flex items-center gap-1 text-[9px] text-gray-300 cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="w-3 h-3 accent-indigo-500"
                  checked={!!disEvidence[key]}
                  disabled={disEvidenceLoading}
                  onChange={() => toggleDisEvidence(key)}
                />
                {label}
              </label>
            ))}
          </div>

          {dis.specificity_marker_present && (
            <div className="text-[9px] text-indigo-300">
              {t('lesions.specificityPresent', 'Supportive specificity marker present (adds diagnostic specificity).')}
            </div>
          )}

          <div className="text-[8px] text-gray-500 italic">
            {t(
              'lesions.decisionSupport',
              'Radiological decision support only — not a diagnosis. Requires clinical correlation by a neurologist.',
            )}
          </div>
        </div>
      )}

      {/* Additional badges (DWM, active, black holes) */}
      {dis && (dis.dwm_lesion_count > 0 || dis.has_active_lesions || dis.has_black_holes) && (
        <div className="flex flex-wrap gap-2">
          {dis.dwm_lesion_count > 0 && (
            <span className="px-1.5 py-0.5 bg-yellow-900/40 border border-yellow-700/50 rounded text-[9px] text-yellow-300">
              DWM: {dis.dwm_lesion_count} lesions (not a DIS region)
            </span>
          )}
          {dis.has_active_lesions && (
            <span className="px-1.5 py-0.5 bg-fuchsia-900/40 border border-fuchsia-700/50 rounded text-[9px] text-fuchsia-300">
              Gd+ {t('lesions.active', 'Active')}
            </span>
          )}
          {dis.has_black_holes && (
            <span className="px-1.5 py-0.5 bg-purple-900/40 border border-purple-700/50 rounded text-[9px] text-purple-300">
              T1 {t('lesions.blackHoles', 'Black Holes')}
            </span>
          )}
        </div>
      )}

      {/* McDonald 2024 Biomarkers — CVS + PRL */}
      {(cvsSummary || prlSummary) && (
        <div className="bg-gray-900/60 rounded-lg p-2 space-y-1.5 border border-indigo-700/40">
          <div className="flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-xs font-semibold text-white">McDonald 2024 Biomarkers</span>
          </div>

          {cvsSummary && (
            <div className="space-y-1">
              <span className="text-[9px] text-gray-400 font-medium">
                CVS (Central Vein Sign)
              </span>
              <div className="flex flex-wrap gap-1.5">
                <span className={`px-1.5 py-0.5 rounded border text-[9px] font-medium ${
                  cvsSummary.meets_select6
                    ? 'bg-green-900/40 text-green-300 border-green-700/50'
                    : 'bg-gray-800 text-gray-400 border-gray-700/50'
                }`}>
                  {cvsSummary.meets_select6 ? <CheckCircle2 className="w-2.5 h-2.5 inline mr-0.5" /> : <XCircle className="w-2.5 h-2.5 inline mr-0.5" />}
                  Select 6: {cvsSummary.cvs_positive}/{cvsSummary.total_evaluated} CVS+
                </span>
                <span className={`px-1.5 py-0.5 rounded border text-[9px] font-medium ${
                  cvsSummary.meets_40pct
                    ? 'bg-green-900/40 text-green-300 border-green-700/50'
                    : 'bg-gray-800 text-gray-400 border-gray-700/50'
                }`}>
                  {cvsSummary.meets_40pct ? <CheckCircle2 className="w-2.5 h-2.5 inline mr-0.5" /> : <XCircle className="w-2.5 h-2.5 inline mr-0.5" />}
                  40% rule: {cvsSummary.total_evaluated > 0 ? `${Math.round(cvsSummary.cvs_positive / cvsSummary.total_evaluated * 100)}%` : '0%'}
                </span>
              </div>
            </div>
          )}

          {prlSummary && (
            <div className="space-y-1">
              <span className="text-[9px] text-gray-400 font-medium">
                PRL (Paramagnetic Rim Lesions)
              </span>
              <div>
                <span className={`px-1.5 py-0.5 rounded border text-[9px] font-medium ${
                  prlSummary.meets_criteria
                    ? 'bg-green-900/40 text-green-300 border-green-700/50'
                    : 'bg-gray-800 text-gray-400 border-gray-700/50'
                }`}>
                  {prlSummary.meets_criteria ? <CheckCircle2 className="w-2.5 h-2.5 inline mr-0.5" /> : <XCircle className="w-2.5 h-2.5 inline mr-0.5" />}
                  PRL: {prlSummary.prl_positive}/{prlSummary.total_evaluated} positive
                </span>
              </div>
            </div>
          )}

          <div className="text-[7px] text-gray-600">
            Montalban et al., Lancet Neurology 2025; 24(10): 850-865
          </div>
        </div>
      )}

      {analysis && (
        <>
          {/* Total Burden + Size Distribution */}
          <div className="bg-gray-900/50 rounded-lg p-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-400">
                {t('lesions.totalBurden', 'T2 Lesion Load')}
              </span>
              <span className="text-sm font-mono font-bold text-white">
                {analysis.total_burden_ml.toFixed(2)} mL
              </span>
            </div>
            <div className="flex items-center justify-between mt-1">
              <span className="text-[10px] text-gray-400">
                {t('lesions.totalCount', 'Total Lesions')}
              </span>
              <span className="text-xs font-mono text-white">
                {analysis.total_count}
              </span>
            </div>
            <div className="flex gap-2 text-[10px] mt-1.5 pt-1.5 border-t border-gray-700/50">
              <span className="text-gray-400">
                {t('lesions.small', 'Small')}: <span className="text-gray-300">{analysis.size_distribution.small}</span>
              </span>
              <span className="text-yellow-400">
                {t('lesions.medium', 'Medium')}: <span className="text-yellow-300">{analysis.size_distribution.medium}</span>
              </span>
              <span className="text-red-400">
                {t('lesions.large', 'Large')}: <span className="text-red-300">{analysis.size_distribution.large}</span>
              </span>
            </div>
          </div>

          {/* Region Summary Bars */}
          <div className="space-y-1">
            <label className="text-[10px] text-gray-400 block">
              {t('lesions.byRegion', 'By Region')}
            </label>
            {Object.entries(analysis.regions).map(([name, region]) => (
              <div key={name} className="space-y-0.5">
                <div className="flex items-center justify-between text-[9px]">
                  <span className="flex items-center gap-1">
                    <span className={`w-1.5 h-1.5 rounded-full ${REGION_COLORS[name] ?? 'bg-gray-500'}`} />
                    <span className="text-gray-300">{name}</span>
                  </span>
                  <span className="text-gray-400">
                    {region.lesion_count} \u2014 {region.total_volume_ml.toFixed(2)} mL
                  </span>
                </div>
                <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-amber-500 rounded-full transition-all"
                    style={{ width: regionBarWidth(region.total_volume_mm3, maxRegionVol) }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* Classification details (expandable) */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-200 transition-colors"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {t('classify.distanceDetails', 'Classification Distances')} ({analysis.total_count})
          </button>

          {classification && classification.lesions.length > 0 && expanded && (
            <div className="mt-2">
              <label className="text-[10px] text-gray-400 block mb-1">
                {t('classify.distanceDetails', 'Classification Distances (mm)')}
              </label>
              <div className="max-h-36 overflow-y-auto">
                <table className="w-full text-[9px]">
                  <thead>
                    <tr className="text-gray-500 border-b border-gray-700">
                      <th className="text-left py-0.5 px-1">#</th>
                      <th className="text-left py-0.5 px-1">{t('classify.region', 'Region')}</th>
                      <th className="text-right py-0.5 px-1">PV</th>
                      <th className="text-right py-0.5 px-1">JC</th>
                      <th className="text-right py-0.5 px-1">IT</th>
                      <th className="text-center py-0.5 px-1">Conf.</th>
                      <th className="text-center py-0.5 px-1">CVS</th>
                      <th className="text-center py-0.5 px-1">PRL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {classification.lesions.map((cl) => (
                      <tr key={cl.lesion_id} className="border-b border-gray-800">
                        <td className="py-0.5 px-1 text-gray-400">{cl.lesion_id}</td>
                        <td className="py-0.5 px-1">
                          <span className="flex items-center gap-1">
                            <span className={`w-1.5 h-1.5 rounded-full ${REGION_COLORS[cl.region] ?? 'bg-gray-500'}`} />
                            <span className={REGION_TEXT_COLORS[cl.region] ?? 'text-gray-300'}>
                              {cl.region}
                            </span>
                          </span>
                        </td>
                        <td className="py-0.5 px-1 text-right font-mono text-gray-400">
                          {cl.distances_mm?.to_ventricle?.toFixed(1) ?? '-'}
                        </td>
                        <td className="py-0.5 px-1 text-right font-mono text-gray-400">
                          {cl.distances_mm?.to_cortex?.toFixed(1) ?? '-'}
                        </td>
                        <td className="py-0.5 px-1 text-right font-mono text-gray-400">
                          {cl.distances_mm?.to_infratentorial?.toFixed(1) ?? '-'}
                        </td>
                        <td className="py-0.5 px-1 text-center">
                          {cl.confidence != null ? (
                            <span className={`px-1 py-0.5 rounded border text-[8px] font-mono ${confidenceBadge(cl.confidence)}`}>
                              {(cl.confidence * 100).toFixed(0)}%
                            </span>
                          ) : (
                            <span className="text-[8px] text-gray-600">N/A</span>
                          )}
                        </td>
                        <td className="py-0.5 px-1 text-center">
                          <select
                            value={lesionAnnotations[cl.lesion_id]?.cvs_status ?? ''}
                            onChange={(e) => handleAnnotationChange(cl.lesion_id, 'cvs_status', e.target.value || null)}
                            className="bg-gray-800 text-[8px] text-gray-300 border border-gray-700 rounded px-0.5 py-0 w-10"
                          >
                            <option value="">{'\u2014'}</option>
                            <option value="positive">+</option>
                            <option value="negative">{'\u2212'}</option>
                            <option value="indeterminate">?</option>
                          </select>
                        </td>
                        <td className="py-0.5 px-1 text-center">
                          <select
                            value={lesionAnnotations[cl.lesion_id]?.prl_status ?? ''}
                            onChange={(e) => handleAnnotationChange(cl.lesion_id, 'prl_status', e.target.value || null)}
                            className="bg-gray-800 text-[8px] text-gray-300 border border-gray-700 rounded px-0.5 py-0 w-10"
                          >
                            <option value="">{'\u2014'}</option>
                            <option value="positive">+</option>
                            <option value="negative">{'\u2212'}</option>
                            <option value="indeterminate">?</option>
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Export CSV */}
          <button
            onClick={handleExportCSV}
            className="flex items-center gap-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-[10px] text-gray-300 transition-colors"
          >
            <Download className="w-3 h-3" />
            {t('lesions.exportCSV', 'Export CSV')}
          </button>

          {/* Export DICOM-SEG */}
          <button
            onClick={() => {
              const url = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/api/v1/segmentation/${segmentationId}/export/dicom-seg`;
              const token = localStorage.getItem('access_token');
              fetch(url, { headers: { Authorization: `Bearer ${token}` } })
                .then(res => {
                  if (!res.ok) throw new Error('Export failed');
                  return res.blob();
                })
                .then(blob => {
                  const a = document.createElement('a');
                  a.href = URL.createObjectURL(blob);
                  a.download = `${segmentationId}_seg.dcm`;
                  a.click();
                  URL.revokeObjectURL(a.href);
                })
                .catch(() => {/* silent */});
            }}
            className="flex items-center gap-1 px-2 py-1 bg-blue-700/50 hover:bg-blue-600/50 rounded text-[10px] text-blue-300 transition-colors"
          >
            <Download className="w-3 h-3" />
            DICOM-SEG
          </button>
        </>
      )}
    </div>
  );
}
