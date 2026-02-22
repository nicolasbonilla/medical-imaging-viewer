/**
 * Longitudinal Comparison Panel
 *
 * Compares lesion masks between two timepoints. Shows:
 * - Burden delta summary (TP1 vs TP2)
 * - Status counts (new, resolved, enlarged, shrunk, stable)
 * - Per-lesion change table with click-to-navigate
 * - Color coding: green (resolved/stable), yellow (enlarged <20%), red (enlarged >20%), blue (new)
 *
 * @module components/LongitudinalCompare
 */

import { useState, useCallback } from 'react';
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
import { useViewerStore } from '@/store/useViewerStore';
import type { LongitudinalResult, LesionChange } from '@/types';

interface LongitudinalCompareProps {
  onNavigateToSlice?: (sliceIndex: number) => void;
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

export function LongitudinalCompare({
  onNavigateToSlice,
}: LongitudinalCompareProps) {
  const { t } = useTranslation();
  const allFileIds = useViewerStore((s) => s.allFileIds);
  const currentStudyId = useViewerStore((s) => s.currentStudyId);
  const [tp1Id, setTp1Id] = useState<string>('');
  const [tp2Id, setTp2Id] = useState<string>('');
  const [result, setResult] = useState<LongitudinalResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  // Fetch segmentations list for this study
  const { data: segmentations = [] } = useQuery({
    queryKey: ['segmentations', 'study', currentStudyId],
    queryFn: () => allFileIds.length > 0
      ? segmentationAPI.listSegmentationsByFileIds(allFileIds)
      : Promise.resolve([]),
    enabled: allFileIds.length > 0,
  });

  const savedSegs = segmentations.filter((s) => s.segmentation_id);
  const canCompare = tp1Id && tp2Id && tp1Id !== tp2Id;

  const handleCompare = useCallback(async () => {
    if (!canCompare) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await segmentationAPI.compareLongitudinal(
        { type: 'segmentation', id: tp1Id },
        { type: 'segmentation', id: tp2Id },
      );
      setResult(data);
      setExpanded(true);
    } catch (err) {
      setError(String(err));
    } finally {
      setIsLoading(false);
    }
  }, [tp1Id, tp2Id, canCompare]);

  const handleLesionClick = useCallback((change: LesionChange) => {
    onNavigateToSlice?.(Math.round(change.centroid_z));
  }, [onNavigateToSlice]);

  return (
    <div className="bg-gray-800/80 rounded-xl p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <TrendingUp className="w-4 h-4 text-indigo-400" />
        <span className="text-sm font-semibold text-white">
          {t('longitudinal.title', 'Longitudinal Tracking')}
        </span>
      </div>

      {/* Timepoint selectors */}
      {savedSegs.length >= 2 ? (
        <div className="space-y-1.5">
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-[9px] text-gray-500 block mb-0.5">
                {t('longitudinal.tp1', 'TP1 (Earlier)')}
              </label>
              <select
                value={tp1Id}
                onChange={(e) => setTp1Id(e.target.value)}
                className="w-full px-1.5 py-1 bg-gray-700 text-white rounded text-[10px]"
              >
                <option value="">{t('longitudinal.select', 'Select...')}</option>
                {savedSegs.map((s) => (
                  <option key={s.segmentation_id} value={s.segmentation_id}>
                    {s.segmentation_id.slice(0, 8)} — {s.metadata?.description || s.file_id?.split('/').pop()}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex-1">
              <label className="text-[9px] text-gray-500 block mb-0.5">
                {t('longitudinal.tp2', 'TP2 (Later)')}
              </label>
              <select
                value={tp2Id}
                onChange={(e) => setTp2Id(e.target.value)}
                className="w-full px-1.5 py-1 bg-gray-700 text-white rounded text-[10px]"
              >
                <option value="">{t('longitudinal.select', 'Select...')}</option>
                {savedSegs.map((s) => (
                  <option key={s.segmentation_id} value={s.segmentation_id}>
                    {s.segmentation_id.slice(0, 8)} — {s.metadata?.description || s.file_id?.split('/').pop()}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <button
            onClick={handleCompare}
            disabled={!canCompare || isLoading}
            className="w-full px-2 py-1 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-xs text-white transition-colors"
          >
            {isLoading ? (
              <Loader2 className="w-3 h-3 animate-spin mx-auto" />
            ) : (
              t('longitudinal.compare', 'Compare Timepoints')
            )}
          </button>
        </div>
      ) : (
        <p className="text-[10px] text-gray-500">
          {t('longitudinal.needTwo', 'Need 2+ saved segmentations to compare timepoints')}
        </p>
      )}

      {error && (
        <div className="flex items-center gap-1 text-red-400 text-xs">
          <AlertCircle className="w-3 h-3" />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <>
          {/* Burden Summary */}
          <div className="bg-gray-900/50 rounded-lg p-2 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-400">
                {t('longitudinal.burden', 'Lesion Burden')}
              </span>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-gray-500">{result.burden_tp1_ml.toFixed(2)} mL</span>
                <span className="text-[10px] text-gray-500">&rarr;</span>
                <span className="text-xs font-mono font-bold text-white">{result.burden_tp2_ml.toFixed(2)} mL</span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-400">{t('longitudinal.change', 'Change')}</span>
              <span className={`text-xs font-mono font-bold ${
                result.burden_delta_percent > 5 ? 'text-red-400' :
                result.burden_delta_percent < -5 ? 'text-green-400' : 'text-gray-300'
              }`}>
                {result.burden_delta_percent > 0 ? '+' : ''}{result.burden_delta_percent.toFixed(1)}%
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-400">{t('longitudinal.lesionCount', 'Lesion Count')}</span>
              <span className="text-[10px] text-gray-300">
                {result.total_lesions_tp1} &rarr; {result.total_lesions_tp2}
              </span>
            </div>
          </div>

          {/* Status Counts */}
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(result.status_counts).map(([status, count]) => (
              count > 0 && (
                <span
                  key={status}
                  className="flex items-center gap-1 px-1.5 py-0.5 bg-gray-900/60 rounded text-[9px]"
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${statusBg(status)}`} />
                  <span className={statusColor(status)}>
                    {count} {t(`longitudinal.${status}`, status)}
                  </span>
                </span>
              )
            ))}
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
                  <tr className="text-gray-500 border-b border-gray-700">
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
                      className="cursor-pointer border-b border-gray-800 hover:bg-gray-700/50 transition-colors"
                    >
                      <td className="py-0.5 px-1 text-center">
                        <span className="flex items-center justify-center gap-0.5">
                          {statusIcon(change.status)}
                          <span className={statusColor(change.status)}>
                            {t(`longitudinal.${change.status}`, change.status)}
                          </span>
                        </span>
                      </td>
                      <td className="py-0.5 px-1 text-right font-mono text-gray-300">
                        {change.volume_tp1_ml > 0 ? `${change.volume_tp1_ml.toFixed(3)}` : '—'}
                      </td>
                      <td className="py-0.5 px-1 text-right font-mono text-white">
                        {change.volume_tp2_ml > 0 ? `${change.volume_tp2_ml.toFixed(3)}` : '—'}
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
