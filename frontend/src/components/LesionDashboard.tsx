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
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
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
  AlertTriangle,
} from 'lucide-react';
import { segmentationAPI } from '@/api/segmentation';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { Badge, Button, SkeletonRows } from '@/components/ui';
import { regionRgb, rgbCss } from '@/utils/clinicalPalette';
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
import { regionEvidence, REGION_ABBREV } from '../utils/regionEvidence';


interface LesionDashboardProps {
  segmentationId: string;
  onNavigateToSlice?: (sliceIndex: number) => void;
  /** Called after auto-classify updates the mask on the server — parent should reload mask */
  onMaskUpdated?: () => void;
}

// MAGNIMS region colours come from the shared clinical palette (Okabe-Ito, colour-blind
// safe) — the SAME colours the image overlay and the zone-map legend use, so a region
// never reads as one colour in the table and another on the picture. The previous
// red(Periventricular)/green(Juxtacortical) pairing was indistinguishable for the ~8% of
// males with red-green deficiency — a clinical-safety defect.
function regionColor(region: string): string | undefined {
  const rgb = regionRgb(region);
  return rgb ? rgbCss(rgb) : undefined;
}

/** Legend dot for a MAGNIMS region (data colour); unknown regions get a neutral dot. */
function RegionDot({ region, className = 'h-2 w-2' }: { region: string; className?: string }) {
  const color = regionColor(region);
  return (
    <span
      aria-hidden="true"
      className={`shrink-0 rounded-full bg-ink-faint ${className}`}
      style={color ? { backgroundColor: color } : undefined}
    />
  );
}

/** Region name / value tinted with the region's data colour. */
function RegionText({ region, className = '', children }: { region: string; className?: string; children: ReactNode }) {
  const color = regionColor(region);
  return (
    <span className={`text-ink-soft ${className}`} style={color ? { color } : undefined}>
      {children}
    </span>
  );
}

function sizeColor(cat: string): string {
  if (cat === 'large') return 'text-clinical-crit';
  if (cat === 'medium') return 'text-clinical-warn';
  return 'text-ink-muted';
}

function regionBarWidth(vol: number, maxVol: number): string {
  if (maxVol === 0) return '0%';
  return `${Math.max(4, (vol / maxVol) * 100)}%`;
}

/** Shared class strings (design-system v2). */
const CARD = 'rounded-lg border border-surface-border bg-surface-base';
const OVERLINE = 'text-xs font-medium uppercase tracking-wide text-ink-faint';
const FOCUS_RING = 'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60';
const WARN_BOX =
  'flex items-start gap-1.5 rounded-md border border-clinical-warn/30 bg-clinical-warn/10 px-2 py-1.5 text-xs leading-snug text-clinical-warn';


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
    <div className="flex flex-col gap-3 rounded-lg border border-surface-border bg-surface-raised p-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Activity className="h-4 w-4 shrink-0 text-brand-400" aria-hidden="true" />
          <span className="truncate text-sm font-semibold text-ink-base">
            {t('lesions.title', 'Lesion Analysis')}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {isAnalysisStale && (
            <Badge tone="warn" className="text-xs" title="Mask was edited since last analysis">
              <AlertCircle className="h-3 w-3" aria-hidden="true" /> Outdated
            </Badge>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={handleAnalyze}
            loading={isLoading}
          >
            {t('lesions.analyze', 'Analyze')}
          </Button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-1.5 rounded-md border border-clinical-crit/30 bg-clinical-crit/10 px-2 py-1.5 text-xs text-clinical-crit">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="min-w-0 break-words">{error}</span>
        </div>
      )}

      {/* First analysis in flight: table-shaped placeholder instead of a blank gap */}
      {isLoading && !analysis && (
        <div className={`${CARD} p-2.5`}>
          <SkeletonRows rows={4} cols={4} />
        </div>
      )}

      {/* ================================================================ */}
      {/* LESION TABLE — Primary view, always visible when analysis exists */}
      {/* ================================================================ */}
      {analysis && analysis.lesions.length > 0 && (
        <div className={`${CARD} p-2.5`}>
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className={OVERLINE}>
              {t('lesions.lesionTable', 'Lesion Table')}
            </span>
            <span className="text-xs tabular-nums text-ink-muted">
              {analysis.total_count} {t('lesions.totalCount', 'lesions')} &middot; {analysis.total_burden_ml.toFixed(2)} mL
            </span>
          </div>
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 z-10 bg-surface-base">
                <tr className="border-b border-surface-border text-ink-faint">
                  <th className="px-1 py-1.5 text-left font-medium">#</th>
                  <th className="px-1 py-1.5 text-left font-medium">{t('lesions.region', 'Region')}</th>
                  <th className="px-1 py-1.5 text-right font-medium">mm&sup3;</th>
                  <th className="px-1 py-1.5 text-right font-medium">mL</th>
                  <th className="px-1 py-1.5 text-center font-medium">{t('lesions.size', 'Size')}</th>
                </tr>
              </thead>
              <tbody>
                {analysis.lesions.map((lesion) => (
                  <tr
                    key={lesion.id}
                    data-lesion-row
                    tabIndex={0}
                    aria-current={highlightedLesion === lesion.id ? 'true' : undefined}
                    onClick={() => handleLesionClick(lesion)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        handleLesionClick(lesion);
                      }
                    }}
                    className={`cursor-pointer border-b border-surface-border/60 transition-colors focus:outline-none focus-visible:bg-surface-hover focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500/60 ${
                      highlightedLesion === lesion.id
                        ? 'bg-brand-950'
                        : 'hover:bg-surface-hover'
                    }`}
                  >
                    <td className={`px-1 py-1 tabular-nums ${highlightedLesion === lesion.id ? 'font-medium text-brand-400' : 'text-ink-muted'}`}>
                      {lesion.id}
                    </td>
                    <td className="px-1 py-1">
                      <span className="flex items-center gap-1.5">
                        <RegionDot region={lesion.region} />
                        <span className="text-ink-soft">{lesion.region}</span>
                      </span>
                    </td>
                    <td className="px-1 py-1 text-right tabular-nums text-ink-soft">
                      {lesion.volume_mm3.toLocaleString()}
                    </td>
                    <td className="px-1 py-1 text-right font-medium tabular-nums text-ink-base">
                      {lesion.volume_ml.toFixed(3)}
                    </td>
                    <td className={`px-1 py-1 text-center font-medium ${sizeColor(lesion.size_category)}`}>
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
      <div className={`${CARD} space-y-2.5 p-3`}>
        <div className="flex items-center gap-2">
          <MapPin className="h-3.5 w-3.5 shrink-0 text-ink-muted" aria-hidden="true" />
          <span className="text-xs font-semibold text-ink-base">
            {t('classify.title', 'MAGNIMS Region Classification')}
          </span>
        </div>
        <p className="text-xs leading-relaxed text-ink-muted">
          {t('classify.description',
            'Classify lesions into Periventricular, Juxtacortical, Infratentorial and Deep WM regions (MAGNIMS contact rule). The method used is shown with the result; verify every region before using it for DIS.'
          )}
        </p>

        {/* Method selector */}
        <div
          className="flex gap-0.5 rounded-lg border border-surface-border bg-surface-raised p-0.5"
          role="group"
          aria-label={t('classify.method', 'Method')}
        >
          {(['auto', 'msmask', 'geometric'] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setClassifyMethod(m)}
              aria-pressed={classifyMethod === m}
              className={`flex-1 rounded-md border px-1.5 py-1 text-xs font-medium transition-colors ${FOCUS_RING} ${
                classifyMethod === m
                  ? 'border-brand-500/30 bg-brand-950 text-brand-400'
                  : 'border-transparent text-ink-muted hover:bg-surface-hover hover:text-ink-soft'
              }`}
            >
              {m === 'auto'
                ? t('classify.methodAuto', 'Auto')
                : m === 'msmask'
                ? t('classify.methodMSMask', 'MSMask')
                : t('classify.methodGeometric', 'Geometric')}
            </button>
          ))}
        </div>

        <Button
          variant="primary"
          size="sm"
          fullWidth
          onClick={handleClassifyRegions}
          disabled={isClassifying}
          aria-busy={isClassifying || undefined}
          leftIcon={isClassifying
            ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            : <Zap className="h-3.5 w-3.5" aria-hidden="true" />}
        >
          {isClassifying
            ? t('classify.classifying', 'Classifying...')
            : t('classify.classify', 'Auto-Classify Regions')}
        </Button>

        {classification && (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="text-ink-muted">
                {t('classify.method', 'Method')}: <span className="font-medium text-ink-base">{classification.method}</span>
              </span>
              <span className="tabular-nums text-ink-faint">
                {classification.processing_time_ms}ms
              </span>
            </div>
            {classification.atlas_unavailable_reason && (
              <div
                className={WARN_BOX}
                role="alert"
                data-testid="atlas-unavailable"
              >
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>
                  {t('classify.atlasUnavailable', 'Atlas regions not used: this image is not in MNI space, so the geometric fallback (coordinate rules, not anatomical landmarks) was applied. Verify every region before using it for DIS.')}
                </span>
              </div>
            )}
            {classification.atlas_error && (
              <div
                className={WARN_BOX}
                role="alert"
                data-testid="atlas-error"
              >
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>
                  {t('classify.atlasError', 'Atlas regions could not be computed (internal error), so the geometric fallback was applied. Verify every region before using it for DIS.')}
                </span>
              </div>
            )}
            {classification.method === 'geometric' && !classification.atlas_unavailable_reason && !classification.atlas_error && (
              <div
                className={WARN_BOX}
                role="alert"
                data-testid="geometric-warning"
              >
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>
                  {t('classify.geometricWarning', 'Geometric heuristics: coordinate rules, not anatomical landmarks; their accuracy has not been measured. Verify every region before using it for DIS.')}
                </span>
              </div>
            )}
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {Object.entries(classification.classification_summary).map(([region, count]) => (
                <span key={region} className="flex items-center gap-1.5 text-xs">
                  <RegionDot region={region} />
                  <RegionText region={region} className="tabular-nums">
                    {region}: {count}
                  </RegionText>
                </span>
              ))}
            </div>
            {classification.lesions.length > 0 && (
              <div className="text-xs text-ink-muted" data-testid="classify-no-confidence">
                {t('classify.noConfidence', 'Regions follow a deterministic MAGNIMS rule; no per-lesion confidence is reported.')}
              </div>
            )}
          </div>
        )}
      </div>

      {/* DIS Badge — McDonald 2024 */}
      {dis ? (
        <div className={`flex items-start gap-2 rounded-lg border p-2.5 ${
          (dis.dis_met_brain ?? dis.dis_met) ? 'border-clinical-good/30 bg-clinical-good/10' : 'border-clinical-crit/30 bg-clinical-crit/10'
        }`}>
          {(dis.dis_met_brain ?? dis.dis_met) ? (
            <CheckCircle2 className="mt-px h-4 w-4 shrink-0 text-clinical-good" aria-hidden="true" />
          ) : (
            <XCircle className="mt-px h-4 w-4 shrink-0 text-clinical-crit" aria-hidden="true" />
          )}
          <div className="min-w-0 flex-1">
            <div className={`text-xs font-semibold tabular-nums ${(dis.dis_met_brain ?? dis.dis_met) ? 'text-clinical-good' : 'text-clinical-crit'}`}>
              DIS (Brain MRI): {dis.brain_regions_with_lesions ?? dis.regions_with_lesions}/{dis.brain_regions_evaluated ?? 3} {t('lesions.regions', 'regions')}
              {(dis.dis_met_brain ?? dis.dis_met) ? ` \u2014 ${t('lesions.criterionMet', 'Criterion Met')}` : ` \u2014 ${t('lesions.criterionNotMet', 'Not Met')}`}
            </div>
            <div className="mt-1.5 flex flex-wrap gap-x-2.5 gap-y-1">
              {Object.entries(dis.region_details).map(([name, detail]) => (
                <span key={name} className="flex items-center gap-1 text-xs">
                  {detail.present ? (
                    <CheckCircle2 className="h-3 w-3 shrink-0 text-clinical-good" aria-hidden="true" />
                  ) : (
                    <XCircle className="h-3 w-3 shrink-0 text-ink-faint" aria-hidden="true" />
                  )}
                  <span className={detail.present ? 'text-clinical-good' : 'text-ink-muted'}>{name}</span>
                  {typeof detail.qualifying_lesion_count === 'number' && (
                    <span
                      className={`tabular-nums ${detail.present ? 'text-clinical-good/80' : 'text-ink-muted'}`}
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
              <div className="mt-1.5 text-xs italic leading-snug text-ink-muted">{dis.note}</div>
            )}
            {dis.dis_criteria_version && (
              <div className="mt-1 text-xs text-ink-faint">{dis.dis_criteria_version}</div>
            )}
          </div>
        </div>
      ) : !classification && analysis && (
        <div className={`${CARD} flex items-center gap-2 p-2.5`}>
          <Info className="h-4 w-4 shrink-0 text-ink-faint" aria-hidden="true" />
          <span className="text-xs text-ink-muted">
            {t('lesions.classifyFirst', 'Classify regions first to evaluate DIS criteria')}
          </span>
        </div>
      )}

      {/* McDonald 2024: five-topography integration + external evidence.
          Decision support only — never a diagnosis (CMSC guidance). */}
      {dis && (
        <div className={`${CARD} flex flex-col gap-2.5 p-3`}>
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold text-ink-base">
              {t('lesions.mcdonald2024', 'McDonald 2024 · 5 topographies')}
            </span>
            <span className="font-display text-sm font-semibold tabular-nums text-ink-base">
              {dis.total_topographies_involved}/5
              {disEvidenceLoading && <span className="ml-1 animate-pulse text-brand-400">…</span>}
            </span>
          </div>

          {dis.dit_waiver_supported && (
            <div className="rounded-md border border-clinical-good/30 bg-clinical-good/10 px-2 py-1.5 text-xs leading-snug text-clinical-good">
              {t(
                'lesions.ditWaiver',
                '≥4 of 5 topographies — dissemination in time may be waived (2024). Clinical correlation required.',
              )}
            </div>
          )}

          {/* External evidence the brain MRI can't supply */}
          <div className="flex flex-wrap gap-x-3 gap-y-1.5">
            {([
              ['optic_nerve_involved', t('lesions.opticNerve', 'Optic nerve')],
              ['spinal_cord_involved', t('lesions.spinalCord', 'Spinal cord')],
              ['cvs_positive', t('lesions.cvs', 'Central vein sign')],
              ['prl_present', t('lesions.prl', 'Paramagnetic rim')],
              ['csf_specific', t('lesions.csf', 'CSF-specific (OCB/kFLC)')],
            ] as [keyof DISExternalEvidence, string][]).map(([key, label]) => (
              <label
                key={key}
                className="flex cursor-pointer select-none items-center gap-1.5 text-xs text-ink-soft has-[:disabled]:cursor-wait has-[:disabled]:opacity-60"
              >
                <input
                  type="checkbox"
                  className={`h-3.5 w-3.5 cursor-pointer rounded accent-brand-500 ${FOCUS_RING}`}
                  checked={!!disEvidence[key]}
                  disabled={disEvidenceLoading}
                  onChange={() => toggleDisEvidence(key)}
                />
                {label}
              </label>
            ))}
          </div>

          {dis.specificity_marker_present && (
            <div className="text-xs text-clinical-info">
              {t('lesions.specificityPresent', 'Supportive specificity marker present (adds diagnostic specificity).')}
            </div>
          )}

          <div className="border-t border-surface-border pt-2 text-xs italic leading-snug text-ink-muted">
            {t(
              'lesions.decisionSupport',
              'Radiological decision support only — not a diagnosis. Requires clinical correlation by a neurologist.',
            )}
          </div>
        </div>
      )}

      {/* Additional badges (DWM, active, black holes) */}
      {dis && (dis.dwm_lesion_count > 0 || dis.has_active_lesions || dis.has_black_holes) && (
        <div className="flex flex-wrap gap-1.5">
          {dis.dwm_lesion_count > 0 && (
            <Badge tone="warn" className="text-xs tabular-nums">
              DWM: {dis.dwm_lesion_count} lesions (not a DIS region)
            </Badge>
          )}
          {dis.has_active_lesions && (
            <Badge tone="crit" className="text-xs">
              Gd+ {t('lesions.active', 'Active')}
            </Badge>
          )}
          {dis.has_black_holes && (
            <Badge tone="neutral" className="text-xs">
              T1 {t('lesions.blackHoles', 'Black Holes')}
            </Badge>
          )}
        </div>
      )}

      {/* Clinician CVS/PRL readings — McDonald 2024 supportive markers (CAPA-008: counts only) */}
      {(cvsSummary || prlSummary) && (
        <div className={`${CARD} space-y-2 p-3`} data-testid="cvs-prl-readings">
          <div className="flex items-center gap-2">
            <Activity className="h-3.5 w-3.5 shrink-0 text-ink-muted" aria-hidden="true" />
            <span className="text-xs font-semibold text-ink-base">
              {t('lesions.markerReadingsTitle', 'CVS / PRL readings (clinician)')}
            </span>
          </div>
          <div className="text-xs leading-relaxed text-ink-muted">
            {t('lesions.markerReadingsNote', 'Read on susceptibility-sensitive MRI. McDonald 2024 uses them as supportive evidence only in specific situations; these are counts, not a criterion.')}
          </div>

          {cvsSummary && (
            <div className="space-y-1">
              <span className="block text-xs font-medium text-ink-muted">
                CVS (Central Vein Sign)
              </span>
              <div className="flex flex-wrap gap-1.5">
                <Badge tone={cvsSummary.meets_select6 ? 'good' : 'neutral'} className="text-xs tabular-nums">
                  {cvsSummary.meets_select6 ? <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> : <XCircle className="h-3 w-3" aria-hidden="true" />}
                  Select 6: {cvsSummary.cvs_positive}/{cvsSummary.total_evaluated} CVS+
                </Badge>
                <Badge tone="neutral" className="text-xs tabular-nums">
                  {t('lesions.cvsPosNeg', 'CVS+ {{pos}} · CVS− {{neg}}', { pos: cvsSummary.cvs_positive, neg: cvsSummary.cvs_negative })}
                </Badge>
              </div>
            </div>
          )}

          {prlSummary && (
            <div className="space-y-1">
              <span className="block text-xs font-medium text-ink-muted">
                PRL (Paramagnetic Rim Lesions)
              </span>
              <div>
                {/* CAPA-008: neutral count — ">=1 PRL" is not, by itself, a criterion met. */}
                <Badge tone="neutral" className="text-xs tabular-nums">
                  PRL: {prlSummary.prl_positive}/{prlSummary.total_evaluated} positive
                </Badge>
              </div>
            </div>
          )}

          <div className="text-xs text-ink-faint">
            Montalban et al., Lancet Neurology 2025; 24(10): 850-865
          </div>
        </div>
      )}

      {analysis && (
        <>
          {/* Total Burden + Size Distribution */}
          <div className={`${CARD} p-3`}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xs text-ink-muted">
                {t('lesions.totalBurden', 'T2 Lesion Load')}
              </span>
              <span className="font-display text-lg font-semibold tabular-nums text-ink-base">
                {analysis.total_burden_ml.toFixed(2)} <span className="text-xs font-normal text-ink-muted">mL</span>
              </span>
            </div>
            <div className="mt-1 flex items-baseline justify-between gap-2">
              <span className="text-xs text-ink-muted">
                {t('lesions.totalCount', 'Total Lesions')}
              </span>
              <span className="text-sm font-medium tabular-nums text-ink-base">
                {analysis.total_count}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 border-t border-surface-border pt-2 text-xs tabular-nums">
              <span className="text-ink-muted">
                {t('lesions.small', 'Small')}: <span className="text-ink-soft">{analysis.size_distribution.small}</span>
              </span>
              <span className="text-clinical-warn">
                {t('lesions.medium', 'Medium')}: <span className="font-medium">{analysis.size_distribution.medium}</span>
              </span>
              <span className="text-clinical-crit">
                {t('lesions.large', 'Large')}: <span className="font-medium">{analysis.size_distribution.large}</span>
              </span>
            </div>
          </div>

          {/* Region Summary Bars */}
          <div className="space-y-1.5">
            <label className={`block ${OVERLINE}`}>
              {t('lesions.byRegion', 'By Region')}
            </label>
            {Object.entries(analysis.regions).map(([name, region]) => (
              <div key={name} className="space-y-1">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="flex min-w-0 items-center gap-1.5">
                    <RegionDot region={name} />
                    <span className="truncate text-ink-soft">{name}</span>
                  </span>
                  <span className="shrink-0 tabular-nums text-ink-muted">
                    {region.lesion_count} {'\u2014'} {region.total_volume_ml.toFixed(2)} mL
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-hover">
                  <div
                    className="h-full rounded-full bg-ink-muted transition-all"
                    style={{ width: regionBarWidth(region.total_volume_mm3, maxRegionVol), backgroundColor: regionColor(name) }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* Classification details (expandable) */}
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
            className={`flex items-center gap-1 rounded text-xs text-ink-muted transition-colors hover:text-ink-soft ${FOCUS_RING}`}
          >
            {expanded ? <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />}
            {t('classify.distanceDetails', 'Classification Distances')} (<span className="tabular-nums">{analysis.total_count}</span>)
          </button>

          {classification && classification.lesions.length > 0 && expanded && (
            <div>
              <label className={`mb-1.5 block ${OVERLINE}`}>
                {t('classify.distanceDetails', 'Classification Distances (mm)')}
              </label>
              <div className={`${CARD} max-h-48 overflow-auto`}>
                <table className="w-full text-xs">
                  <thead className="sticky top-0 z-10 bg-surface-base">
                    <tr className="border-b border-surface-border text-ink-faint">
                      <th className="whitespace-nowrap px-1.5 py-1.5 text-left font-medium">#</th>
                      <th className="whitespace-nowrap px-1.5 py-1.5 text-left font-medium">{t('classify.region', 'Region')}</th>
                      <th className="whitespace-nowrap px-1.5 py-1.5 text-right font-medium">PV</th>
                      <th className="whitespace-nowrap px-1.5 py-1.5 text-right font-medium">JC</th>
                      <th className="whitespace-nowrap px-1.5 py-1.5 text-right font-medium">IT</th>
                      <th
                        className="whitespace-nowrap px-1.5 py-1.5 text-center font-medium"
                        title={t('classify.inZoneTooltip', 'Fraction of the lesion inside the assigned MAGNIMS zone (MSMask). Descriptive, not a probability.')}
                      >
                        {t('classify.inZone', 'Lesion % in zone')}
                      </th>
                      <th className="whitespace-nowrap px-1.5 py-1.5 text-center font-medium">CVS</th>
                      <th className="whitespace-nowrap px-1.5 py-1.5 text-center font-medium">PRL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {classification.lesions.map((cl) => (
                      <tr key={cl.lesion_id} className="border-b border-surface-border/60 last:border-b-0">
                        <td className="px-1.5 py-1 tabular-nums text-ink-muted">{cl.lesion_id}</td>
                        <td className="px-1.5 py-1">
                          <span className="flex items-center gap-1.5 whitespace-nowrap">
                            <RegionDot region={cl.region} />
                            <RegionText region={cl.region}>
                              {cl.region}
                            </RegionText>
                          </span>
                        </td>
                        <td className="px-1.5 py-1 text-right tabular-nums text-ink-muted">
                          {cl.distances_mm?.to_ventricle?.toFixed(1) ?? '-'}
                        </td>
                        <td className="px-1.5 py-1 text-right tabular-nums text-ink-muted">
                          {cl.distances_mm?.to_cortex?.toFixed(1) ?? '-'}
                        </td>
                        <td className="px-1.5 py-1 text-right tabular-nums text-ink-muted">
                          {cl.distances_mm?.to_infratentorial?.toFixed(1) ?? '-'}
                        </td>
                        <td className="px-1.5 py-1 text-center">
                          {(() => {
                            // RC-010 (amended): evidence, never a confidence (HAZ-005).
                            const ev = regionEvidence(cl);
                            if (ev.kind === 'outsideZones') {
                              return (
                                <span
                                  className="inline-flex items-center gap-1 whitespace-nowrap text-xs text-clinical-warn"
                                  title={t('classify.outsideZonesTooltip', 'No voxel of this lesion lies in any MSMask white-matter zone (it may be cortical, intraventricular, or the atlas may be misaligned). Deep White Matter was assigned by default, not by the MAGNIMS rule. Verify the location before using it for DIS.')}
                                  data-testid="region-evidence"
                                >
                                  <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
                                  {t('classify.outsideZones', 'No WM zone — DWM by default')}
                                </span>
                              );
                            }
                            if (ev.kind === 'overlap') {
                              return (
                                <span
                                  className="whitespace-nowrap text-xs tabular-nums text-ink-muted"
                                  title={t('classify.inZoneTooltip', 'Fraction of the lesion inside the assigned MAGNIMS zone (MSMask). Descriptive, not a probability.')}
                                  data-testid="region-evidence"
                                >
                                  {t('classify.inZoneValue', '{{pct}}% in {{zone}}', {
                                    pct: Math.round(ev.value * 100),
                                    zone: REGION_ABBREV[cl.region] ?? cl.region,
                                  })}
                                </span>
                              );
                            }
                            return <span className="text-xs text-ink-faint" data-testid="region-evidence">{'\u2014'}</span>;
                          })()}
                        </td>
                        <td className="px-1.5 py-1 text-center">
                          <select
                            value={lesionAnnotations[cl.lesion_id]?.cvs_status ?? ''}
                            onChange={(e) => handleAnnotationChange(cl.lesion_id, 'cvs_status', e.target.value || null)}
                            aria-label={`CVS #${cl.lesion_id}`}
                            className={`w-12 rounded border border-surface-border bg-surface-raised px-1 py-0.5 text-xs text-ink-soft ${FOCUS_RING}`}
                          >
                            <option value="">{'\u2014'}</option>
                            <option value="positive">+</option>
                            <option value="negative">{'\u2212'}</option>
                            <option value="indeterminate">?</option>
                          </select>
                        </td>
                        <td className="px-1.5 py-1 text-center">
                          <select
                            value={lesionAnnotations[cl.lesion_id]?.prl_status ?? ''}
                            onChange={(e) => handleAnnotationChange(cl.lesion_id, 'prl_status', e.target.value || null)}
                            aria-label={`PRL #${cl.lesion_id}`}
                            className={`w-12 rounded border border-surface-border bg-surface-raised px-1 py-0.5 text-xs text-ink-soft ${FOCUS_RING}`}
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

          {/* Export CSV / DICOM-SEG */}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleExportCSV}
              leftIcon={<Download className="h-3.5 w-3.5" aria-hidden="true" />}
            >
              {t('lesions.exportCSV', 'Export CSV')}
            </Button>

            {/* Export DICOM-SEG */}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                const url = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/api/v1/segmentation/${segmentationId}/export/dicom-seg`;
                const token = localStorage.getItem('access_token');
                const toastId = toast.loading(t('lesions.exportingSeg', 'Exporting DICOM-SEG…'));
                fetch(url, { headers: { Authorization: `Bearer ${token}` } })
                  .then(res => {
                    if (!res.ok) throw new Error(`Export failed (${res.status})`);
                    return res.blob();
                  })
                  .then(blob => {
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = `${segmentationId}_seg.dcm`;
                    a.click();
                    URL.revokeObjectURL(a.href);
                    toast.success(t('lesions.exportSegOk', 'DICOM-SEG exported'), { id: toastId });
                  })
                  // A clinical data export must NEVER fail silently (Class C): surface it.
                  .catch((e) => toast.error(
                    t('lesions.exportSegFail', 'DICOM-SEG export failed') +
                    (e?.message ? `: ${e.message}` : ''), { id: toastId }));
              }}
              leftIcon={<Download className="h-3.5 w-3.5" aria-hidden="true" />}
            >
              DICOM-SEG
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
