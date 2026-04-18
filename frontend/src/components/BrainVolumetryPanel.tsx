/**
 * BrainVolumetryPanel - MS Lesion Volumetry Dashboard.
 *
 * Displays per-structure/lesion volumes computed from AI segmentation masks.
 * Features:
 * - Bar chart showing volume per lesion type vs normative data
 * - Color coding: green (normal), yellow (borderline), red (abnormal)
 * - Total lesion volume and intracranial volume
 * - Lesion burden flags
 *
 * @module components/BrainVolumetryPanel
 */

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation } from '@tanstack/react-query';
import { aiSegmentationAPI } from '@/api/aiSegmentation';
import type { VolumetryResult, BrainStructureVolume, VolumetryRequest } from '@/types';

interface BrainVolumetryPanelProps {
  segmentationId?: string;
  voxelSpacing?: [number, number, number];
  patientAge?: number;
  patientSex?: 'M' | 'F';
}

/** Get color based on normative percentile */
function getPercentileColor(percentile: number | undefined, isVentricular: boolean): string {
  if (percentile === undefined) return 'bg-gray-600';

  if (isVentricular) {
    // Ventricles: high percentile = bad (enlargement)
    if (percentile > 90) return 'bg-red-500';
    if (percentile > 75) return 'bg-yellow-500';
    return 'bg-green-500';
  } else {
    // Parenchyma: low percentile = bad (atrophy)
    if (percentile < 10) return 'bg-red-500';
    if (percentile < 25) return 'bg-yellow-500';
    return 'bg-green-500';
  }
}

/** Get text color for abnormality status */
function getAbnormalityBadge(structure: BrainStructureVolume, t: (key: string, defaultValue: string) => string): React.ReactNode {
  if (!structure.is_abnormal) return null;

  const isAtrophy = structure.abnormality_type === 'atrophy';
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded ${
      isAtrophy ? 'bg-red-900/50 text-red-300' : 'bg-orange-900/50 text-orange-300'
    }`}>
      {isAtrophy ? t('volumetry.atrophy', 'Atrophy') : t('volumetry.enlarged', 'Enlarged')}
    </span>
  );
}

const VENTRICULAR_LABELS = new Set([4, 43, 5, 44, 14, 15]);

export const BrainVolumetryPanel: React.FC<BrainVolumetryPanelProps> = ({
  segmentationId,
  voxelSpacing = [1, 1, 1],
  patientAge,
  patientSex,
}) => {
  const { t } = useTranslation();
  const [result, setResult] = useState<VolumetryResult | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [sortBy, setSortBy] = useState<'name' | 'volume' | 'percentile'>('volume');

  const computeMutation = useMutation({
    mutationFn: (req: VolumetryRequest) => aiSegmentationAPI.computeVolumetry(req),
    onSuccess: (data) => setResult(data),
  });

  const handleCompute = () => {
    if (!segmentationId) return;
    computeMutation.mutate({
      segmentation_id: segmentationId,
      voxel_spacing: voxelSpacing,
      patient_age: patientAge,
      patient_sex: patientSex,
    });
  };

  // Sort structures
  const sortedStructures = result?.structures
    ? [...result.structures].sort((a, b) => {
        if (sortBy === 'name') return a.structure_name.localeCompare(b.structure_name);
        if (sortBy === 'volume') return b.volume_ml - a.volume_ml;
        if (sortBy === 'percentile') {
          return (b.normative_percentile ?? 50) - (a.normative_percentile ?? 50);
        }
        return 0;
      })
    : [];

  // Find max volume for bar scaling
  const maxVolume = sortedStructures.length > 0
    ? Math.max(...sortedStructures.map((s) => s.volume_ml))
    : 1;

  // Count abnormalities
  const abnormalCount = result?.structures.filter((s) => s.is_abnormal).length ?? 0;

  return (
    <div style={{ background: '#1F2937', borderRadius: 8 }}>
      {/* Header */}
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-700 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          {t('volumetry.title', 'Lesion Volumetry')}
          {abnormalCount > 0 && (
            <span className="ml-1 px-1.5 py-0.5 bg-red-600 rounded-full text-xs">
              {abnormalCount}
            </span>
          )}
        </h3>
        <span className="text-gray-400 text-sm">{expanded ? '\u25BC' : '\u25B6'}</span>
      </div>

      {expanded && (
        <div className="p-3 space-y-3 border-t border-gray-700">
          {/* Compute button */}
          {!result && (
            <div className="text-center py-4">
              <button
                onClick={handleCompute}
                disabled={!segmentationId || computeMutation.isPending}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-sm font-medium transition-colors flex items-center justify-center gap-2 mx-auto"
              >
                {computeMutation.isPending ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                    <span>{t('volumetry.computing', 'Computing...')}</span>
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                    <span>{t('volumetry.compute', 'Compute Volumes')}</span>
                  </>
                )}
              </button>
              {!segmentationId && (
                <p className="text-xs text-gray-500 mt-2">
                  {t('volumetry.needSegmentation', 'Load an MS lesion segmentation first')}
                </p>
              )}
            </div>
          )}

          {/* Error */}
          {computeMutation.isError && (
            <div className="p-2 bg-red-900/30 border border-red-800 rounded text-xs text-red-300">
              {(computeMutation.error as Error)?.message || t('volumetry.computeError', 'Volumetry computation failed')}
            </div>
          )}

          {/* Results */}
          {result && (
            <>
              {/* Summary cards */}
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-gray-700/50 rounded p-2 text-center">
                  <p className="text-xs text-gray-400">{t('volumetry.totalBrain', 'Total Brain')}</p>
                  <p className="text-lg font-bold text-white">
                    {result.total_brain_volume_ml?.toFixed(1)}
                    <span className="text-xs text-gray-400 ml-1">mL</span>
                  </p>
                </div>
                <div className="bg-gray-700/50 rounded p-2 text-center">
                  <p className="text-xs text-gray-400">{t('volumetry.icv', 'ICV')}</p>
                  <p className="text-lg font-bold text-white">
                    {result.intracranial_volume_ml?.toFixed(1)}
                    <span className="text-xs text-gray-400 ml-1">mL</span>
                  </p>
                </div>
              </div>

              {/* Sort controls */}
              <div className="flex gap-1">
                {(['volume', 'name', 'percentile'] as const).map((s) => (
                  <button
                    key={s}
                    onClick={() => setSortBy(s)}
                    className={`flex-1 px-2 py-1 rounded text-xs transition-colors ${
                      sortBy === s
                        ? 'bg-purple-600 text-white'
                        : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                    }`}
                  >
                    {s === 'volume'
                      ? t('volumetry.sortVolume', 'Volume')
                      : s === 'name'
                        ? t('volumetry.sortName', 'Name')
                        : t('volumetry.sortPercentile', '%ile')}
                  </button>
                ))}
              </div>

              {/* Structure list with bars */}
              <div className="space-y-1 max-h-64 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-600 scrollbar-track-gray-800">
                {sortedStructures.map((structure) => {
                  const isVentricular = VENTRICULAR_LABELS.has(structure.label_id);
                  const barWidth = (structure.volume_ml / maxVolume) * 100;
                  const barColor = getPercentileColor(structure.normative_percentile, isVentricular);

                  return (
                    <div key={structure.label_id} className="group">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-gray-300 truncate flex-1 mr-2">
                          {structure.structure_name}
                        </span>
                        <div className="flex items-center gap-1">
                          {getAbnormalityBadge(structure, t)}
                          <span className="text-white font-mono whitespace-nowrap">
                            {structure.volume_ml.toFixed(1)} mL
                          </span>
                        </div>
                      </div>
                      {/* Volume bar */}
                      <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden mt-0.5">
                        <div
                          className={`h-full ${barColor} transition-all duration-300 rounded-full`}
                          style={{ width: `${barWidth}%` }}
                        />
                      </div>
                      {/* Percentile on hover */}
                      {structure.normative_percentile !== undefined && (
                        <p className="text-xs text-gray-500 hidden group-hover:block">
                          {t('volumetry.percentile', 'Percentile')}: {structure.normative_percentile}%
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Processing time */}
              {result.processing_time_ms !== undefined && (
                <p className="text-xs text-gray-500 text-right">
                  {t('volumetry.computeTime', 'Computed in')} {result.processing_time_ms}ms
                </p>
              )}

              {/* Recompute button */}
              <button
                onClick={() => setResult(null)}
                className="w-full px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs transition-colors"
              >
                {t('volumetry.reset', 'Reset')}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default BrainVolumetryPanel;
