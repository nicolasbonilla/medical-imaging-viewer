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

import { useState, useCallback } from 'react';
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
  Map,
  Eye,
  EyeOff,
} from 'lucide-react';
import { segmentationAPI } from '@/api/segmentation';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import {
  MAGNIMS_LESION_LABELS,
  type LesionAnalysisResult,
  type DISAssessment,
  type LesionInfo,
  type RegionClassificationResult,
  type ClassificationMethod,
  type ZoneMapResult,
} from '@/types';
import { apiClient } from '@/services/apiClient';

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
  const currentFileId = useSegmentationStore((s) => s.currentSegmentation?.file_id);
  const zoneMapSegId = useSegmentationStore((s) => s.zoneMapSegId);
  const zoneMapVisible = useSegmentationStore((s) => s.zoneMapVisible);
  const [analysis, setAnalysis] = useState<LesionAnalysisResult | null>(null);
  const [dis, setDis] = useState<DISAssessment | null>(null);
  const [classification, setClassification] = useState<RegionClassificationResult | null>(null);
  const [zoneMapStats, setZoneMapStats] = useState<ZoneMapResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isClassifying, setIsClassifying] = useState(false);
  const [isGeneratingZoneMap, setIsGeneratingZoneMap] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [highlightedLesion, setHighlightedLesion] = useState<number | null>(null);
  const [classifyMethod, setClassifyMethod] = useState<ClassificationMethod>('auto');

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
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || String(err));
    } finally {
      setIsLoading(false);
    }
  }, [segmentationId]);

  const handleClassifyRegions = useCallback(async () => {
    setIsClassifying(true);
    setError(null);
    try {
      const result = await segmentationAPI.classifyRegions(segmentationId, {
        method: classifyMethod,
      });
      setClassification(result);

      // The mask has been reclassified on the server — reload from server
      if (result.mask_updated) {
        await reloadMaskCallback?.();
        onMaskUpdated?.();
      }

      // Sync MAGNIMS labels into Zustand so the canvas renders correct colors
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

      // Re-run analysis to reflect the new MAGNIMS labels
      const [analysisResult, disResult] = await Promise.all([
        segmentationAPI.analyzeLesions(segmentationId),
        segmentationAPI.getDISAssessment(segmentationId),
      ]);
      setAnalysis(analysisResult);
      setDis(disResult);
      setExpanded(true);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || String(err));
    } finally {
      setIsClassifying(false);
    }
  }, [segmentationId, classifyMethod, onMaskUpdated, reloadMaskCallback]);

  const handleGenerateZoneMap = useCallback(async () => {
    if (!currentFileId) return;
    setIsGeneratingZoneMap(true);
    setError(null);
    try {
      // 1. Generate zone map on server (creates a new segmentation)
      const result = await segmentationAPI.generateZoneMap(currentFileId);
      setZoneMapStats(result);

      // 2. Download the binary zone mask
      const response = await apiClient.get(
        `/api/v1/segmentation/${result.segmentation_id}/mask/binary`,
        { responseType: 'arraybuffer' },
      );
      const buffer = response.data as ArrayBuffer;
      if (buffer.byteLength < 12) throw new Error('Invalid zone map data');

      const headerView = new DataView(buffer, 0, 12);
      const depth = headerView.getUint32(0, true);
      const height = headerView.getUint32(4, true);
      const width = headerView.getUint32(8, true);
      const maskData = new Uint8Array(buffer, 12);

      // 3. Store in Zustand for rendering
      useSegmentationStore.getState().setZoneMap(
        result.segmentation_id,
        maskData,
        { depth, height, width },
      );
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || String(err);
      setError(detail);
    } finally {
      setIsGeneratingZoneMap(false);
    }
  }, [currentFileId]);

  const handleToggleZoneMap = useCallback(() => {
    useSegmentationStore.getState().toggleZoneMapVisibility();
  }, []);

  const handleLesionClick = useCallback((lesion: LesionInfo) => {
    setHighlightedLesion(lesion.id);
    onNavigateToSlice?.(Math.round(lesion.centroid.z));
    setTimeout(() => setHighlightedLesion(null), 2000);
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

  const maxRegionVol = analysis
    ? Math.max(...Object.values(analysis.regions).map((r) => r.total_volume_mm3), 1)
    : 1;

  return (
    <div className="bg-gray-800/80 rounded-xl p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-amber-400" />
          <span className="text-sm font-semibold text-white">
            {t('lesions.title', 'Lesion Analysis')}
          </span>
        </div>
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

      {error && (
        <div className="flex items-center gap-1 text-red-400 text-xs">
          <AlertCircle className="w-3 h-3" />
          <span>{error}</span>
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
          {(['auto', 'geometric'] as const).map((m) => (
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
                : t('classify.methodGeometric', 'Geometric')}
            </button>
          ))}
        </div>

        {/* Classify button */}
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

        {/* Classification result badge */}
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

            {/* Region breakdown with colored dots */}
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

            {/* Confidence info */}
            {classification.lesions.length > 0 && (
              <div className="text-[9px] text-gray-400">
                {t('classify.avgConfidence', 'Avg confidence')}:{' '}
                <span className="text-white font-mono">
                  {(classification.lesions.reduce((sum, l) => sum + l.confidence, 0) / classification.lesions.length * 100).toFixed(0)}%
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ================================================================ */}
      {/* MAGNIMS Zone Map */}
      {/* ================================================================ */}
      <div className="bg-gray-900/60 rounded-lg p-2 space-y-2 border border-gray-700/50">
        <div className="flex items-center gap-1.5">
          <Map className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-xs font-semibold text-white">
            {t('zoneMap.title', 'MAGNIMS Zone Map')}
          </span>
        </div>
        <p className="text-[9px] text-gray-400 leading-relaxed">
          {t('zoneMap.description',
            'Visualize anatomical zone boundaries (PV, JC, IT, DWM) as a semi-transparent background overlay. Requires brain parcellation (SynthSeg).'
          )}
        </p>

        <div className="flex gap-1.5">
          {/* Generate button */}
          <button
            onClick={handleGenerateZoneMap}
            disabled={isGeneratingZoneMap || !currentFileId}
            className="flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-xs text-white font-medium transition-colors"
          >
            {isGeneratingZoneMap ? (
              <>
                <Loader2 className="w-3 h-3 animate-spin" />
                {t('zoneMap.generating', 'Generating...')}
              </>
            ) : (
              <>
                <Map className="w-3 h-3" />
                {t('zoneMap.generate', 'Generate')}
              </>
            )}
          </button>

          {/* Toggle visibility (only when zone map exists) */}
          {zoneMapSegId && (
            <button
              onClick={handleToggleZoneMap}
              className={`px-2 py-1.5 rounded text-xs font-medium transition-colors ${
                zoneMapVisible
                  ? 'bg-emerald-600 text-white'
                  : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
              }`}
              title={zoneMapVisible ? t('zoneMap.hide', 'Hide zones') : t('zoneMap.show', 'Show zones')}
            >
              {zoneMapVisible ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
            </button>
          )}
        </div>

        {/* Zone map stats */}
        {zoneMapStats && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[9px] text-gray-400">
              <span>{zoneMapStats.processing_time_ms}ms</span>
              <span>{zoneMapStats.total_brain_voxels.toLocaleString()} {t('zoneMap.brainVoxels', 'brain voxels')}</span>
            </div>
            <div className="flex flex-wrap gap-x-2 gap-y-1">
              {Object.entries(zoneMapStats.zone_stats).map(([region, stat]) => (
                <span key={region} className="flex items-center gap-1 text-[9px]">
                  <span className={`w-2 h-2 rounded-full ${REGION_COLORS[region] ?? 'bg-gray-500'}`} />
                  <span className={REGION_TEXT_COLORS[region] ?? 'text-gray-300'}>
                    {region}: {stat.percentage}%
                  </span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* DIS Badge */}
      {dis && (
        <div className={`flex items-center gap-2 p-2 rounded-lg ${
          dis.dis_met ? 'bg-green-900/30 border border-green-700/50' : 'bg-red-900/30 border border-red-700/50'
        }`}>
          {dis.dis_met ? (
            <CheckCircle2 className="w-4 h-4 text-green-400 shrink-0" />
          ) : (
            <XCircle className="w-4 h-4 text-red-400 shrink-0" />
          )}
          <div className="flex-1 min-w-0">
            <div className={`text-xs font-bold ${dis.dis_met ? 'text-green-300' : 'text-red-300'}`}>
              DIS: {dis.regions_with_lesions}/{dis.total_dis_regions} {t('lesions.regions', 'regions')}
              {dis.dis_met ? ` \u2014 ${t('lesions.criterionMet', 'Criterion Met')}` : ` \u2014 ${t('lesions.criterionNotMet', 'Not Met')}`}
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
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Additional DIS badges */}
      {dis && (dis.has_active_lesions || dis.has_black_holes) && (
        <div className="flex gap-2">
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

      {analysis && (
        <>
          {/* Total Burden */}
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
          </div>

          {/* Size Distribution */}
          <div className="flex gap-2 text-[10px]">
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

          {/* Expandable Lesion Table */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-200 transition-colors"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {t('lesions.lesionTable', 'Lesion Table')} ({analysis.total_count})
          </button>

          {expanded && analysis.lesions.length > 0 && (
            <div className="max-h-48 overflow-y-auto">
              <table className="w-full text-[9px]">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-700">
                    <th className="text-left py-0.5 px-1">#</th>
                    <th className="text-left py-0.5 px-1">{t('lesions.region', 'Region')}</th>
                    <th className="text-right py-0.5 px-1">mm\u00b3</th>
                    <th className="text-right py-0.5 px-1">mL</th>
                    <th className="text-center py-0.5 px-1">{t('lesions.size', 'Size')}</th>
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
                      <td className="py-0.5 px-1 text-gray-400">{lesion.id}</td>
                      <td className="py-0.5 px-1">
                        <span className="flex items-center gap-1">
                          <span className={`w-1.5 h-1.5 rounded-full ${REGION_COLORS[lesion.region] ?? 'bg-gray-500'}`} />
                          <span className="text-gray-200">{lesion.region}</span>
                        </span>
                      </td>
                      <td className="py-0.5 px-1 text-right font-mono text-gray-300">
                        {lesion.volume_mm3.toLocaleString()}
                      </td>
                      <td className="py-0.5 px-1 text-right font-mono text-white">
                        {lesion.volume_ml.toFixed(3)}
                      </td>
                      <td className={`py-0.5 px-1 text-center ${sizeColor(lesion.size_category)}`}>
                        {lesion.size_category === 'small' ? 'S' : lesion.size_category === 'medium' ? 'M' : 'L'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Classification detail table (shows distances when available) */}
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
                          {cl.distances_mm.to_ventricle.toFixed(1)}
                        </td>
                        <td className="py-0.5 px-1 text-right font-mono text-gray-400">
                          {cl.distances_mm.to_cortex.toFixed(1)}
                        </td>
                        <td className="py-0.5 px-1 text-right font-mono text-gray-400">
                          {cl.distances_mm.to_infratentorial.toFixed(1)}
                        </td>
                        <td className="py-0.5 px-1 text-center">
                          <span className={`px-1 py-0.5 rounded border text-[8px] font-mono ${confidenceBadge(cl.confidence)}`}>
                            {(cl.confidence * 100).toFixed(0)}%
                          </span>
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
        </>
      )}
    </div>
  );
}
