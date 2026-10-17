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
import { ChevronDown, Loader2 } from 'lucide-react';
import { aiSegmentationAPI } from '@/api/aiSegmentation';
import { Badge, Button } from '@/components/ui';
import type { VolumetryResult, BrainStructureVolume, VolumetryRequest } from '@/types';

interface BrainVolumetryPanelProps {
  segmentationId?: string;
  voxelSpacing?: [number, number, number];
  patientAge?: number;
  patientSex?: 'M' | 'F';
}

/** Get color based on normative percentile */
function getPercentileColor(percentile: number | undefined, isVentricular: boolean): string {
  if (percentile === undefined) return 'bg-ink-faint';

  if (isVentricular) {
    // Ventricles: high percentile = bad (enlargement)
    if (percentile > 90) return 'bg-clinical-crit';
    if (percentile > 75) return 'bg-clinical-warn';
    return 'bg-clinical-good';
  } else {
    // Parenchyma: low percentile = bad (atrophy)
    if (percentile < 10) return 'bg-clinical-crit';
    if (percentile < 25) return 'bg-clinical-warn';
    return 'bg-clinical-good';
  }
}

/** Get text color for abnormality status */
function getAbnormalityBadge(structure: BrainStructureVolume, t: (key: string, defaultValue: string) => string): React.ReactNode {
  if (!structure.is_abnormal) return null;

  const isAtrophy = structure.abnormality_type === 'atrophy';
  return (
    <Badge tone={isAtrophy ? 'crit' : 'warn'} className="px-1.5 text-xs">
      {isAtrophy ? t('volumetry.atrophy', 'Atrophy') : t('volumetry.enlarged', 'Enlarged')}
    </Badge>
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
    <div className="rounded-lg border border-surface-border bg-surface-raised">
      {/* Header */}
      <div
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        className={`flex items-center justify-between p-3 cursor-pointer transition-colors hover:bg-surface-hover/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500/60 ${
          expanded ? 'rounded-t-lg' : 'rounded-lg'
        }`}
        onClick={() => setExpanded(!expanded)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setExpanded(!expanded);
          }
        }}
      >
        <h3 className="text-sm font-semibold text-ink-base flex items-center gap-2">
          <svg className="w-4 h-4 text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          {t('volumetry.title', 'Lesion Volumetry')}
          {abnormalCount > 0 && (
            <Badge tone="crit" className="ml-1 px-1.5 text-xs tabular-nums">
              {abnormalCount}
            </Badge>
          )}
        </h3>
        <ChevronDown
          className={`h-4 w-4 text-ink-muted transition-transform duration-150 ${expanded ? '' : '-rotate-90'}`}
          aria-hidden
        />
      </div>

      {expanded && (
        <div className="p-3 space-y-3 border-t border-surface-border">
          {/* Compute button */}
          {!result && (
            <div className="text-center py-4">
              <Button
                variant="primary"
                size="sm"
                onClick={handleCompute}
                disabled={!segmentationId || computeMutation.isPending}
                aria-busy={computeMutation.isPending || undefined}
                className="mx-auto"
                leftIcon={computeMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                )}
              >
                {computeMutation.isPending
                  ? t('volumetry.computing', 'Computing...')
                  : t('volumetry.compute', 'Compute Volumes')}
              </Button>
              {!segmentationId && (
                <p className="text-xs text-ink-faint mt-2">
                  {t('volumetry.needSegmentation', 'Load an MS lesion segmentation first')}
                </p>
              )}
            </div>
          )}

          {/* Error */}
          {computeMutation.isError && (
            <div className="p-2 rounded-md border border-clinical-crit/30 bg-clinical-crit/10 text-xs text-clinical-crit">
              {(computeMutation.error as Error)?.message || t('volumetry.computeError', 'Volumetry computation failed')}
            </div>
          )}

          {/* Results */}
          {result && (
            <>
              {/* Summary cards */}
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg border border-surface-border bg-surface-base/60 p-2 text-center">
                  <p className="text-xs text-ink-muted">{t('volumetry.totalBrain', 'Total Brain')}</p>
                  <p className="font-display text-lg font-semibold tabular-nums text-ink-base">
                    {result.total_brain_volume_ml?.toFixed(1)}
                    <span className="font-sans text-xs font-normal text-ink-muted ml-1">mL</span>
                  </p>
                </div>
                <div className="rounded-lg border border-surface-border bg-surface-base/60 p-2 text-center">
                  <p className="text-xs text-ink-muted">{t('volumetry.icv', 'ICV')}</p>
                  <p className="font-display text-lg font-semibold tabular-nums text-ink-base">
                    {result.intracranial_volume_ml?.toFixed(1)}
                    <span className="font-sans text-xs font-normal text-ink-muted ml-1">mL</span>
                  </p>
                </div>
              </div>

              {/* Brain Parenchymal Fraction — head-size-normalized atrophy metric
                  (MS standard: SIENAX / icobrain / NeuroQuant). */}
              {result.brain_parenchymal_fraction != null && (
                <div
                  className="rounded-lg border border-clinical-info/30 bg-clinical-info/10 p-2 flex items-center justify-between gap-2"
                  title={t(
                    'volumetry.bpfTip',
                    'Brain Parenchymal Fraction = brain parenchyma / intracranial volume. Head-size-normalized atrophy metric.',
                  )}
                >
                  <span className="text-xs text-clinical-info">
                    {t('volumetry.bpf', 'Brain Parenchymal Fraction (BPF)')}
                  </span>
                  <span className="font-display text-lg font-semibold tabular-nums text-ink-base">
                    {result.brain_parenchymal_fraction.toFixed(3)}
                  </span>
                </div>
              )}

              {/* Sort controls */}
              <div className="flex gap-1 rounded-lg border border-surface-border bg-surface-base p-1">
                {(['volume', 'name', 'percentile'] as const).map((s) => (
                  <button
                    key={s}
                    onClick={() => setSortBy(s)}
                    aria-pressed={sortBy === s}
                    className={`flex-1 px-2 py-1 rounded-md border text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 ${
                      sortBy === s
                        ? 'border-brand-500/30 bg-brand-950 text-brand-400'
                        : 'border-transparent text-ink-muted hover:bg-surface-hover hover:text-ink-base'
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
              <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
                {sortedStructures.map((structure) => {
                  const isVentricular = VENTRICULAR_LABELS.has(structure.label_id);
                  const barWidth = (structure.volume_ml / maxVolume) * 100;
                  const barColor = getPercentileColor(structure.normative_percentile, isVentricular);

                  return (
                    <div key={structure.label_id} className="group">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-ink-soft truncate flex-1 mr-2">
                          {structure.structure_name}
                        </span>
                        <div className="flex items-center gap-1">
                          {getAbnormalityBadge(structure, t)}
                          <span className="text-ink-base font-mono tabular-nums whitespace-nowrap">
                            {structure.volume_ml.toFixed(1)} mL
                          </span>
                        </div>
                      </div>
                      {/* Volume bar */}
                      <div className="h-1.5 bg-surface-hover rounded-full overflow-hidden mt-1">
                        <div
                          className={`h-full ${barColor} transition-all duration-300 rounded-full`}
                          style={{ width: `${barWidth}%` }}
                        />
                      </div>
                      {/* Percentile on hover */}
                      {structure.normative_percentile !== undefined && (
                        <p className="text-xs text-ink-faint tabular-nums hidden group-hover:block">
                          {t('volumetry.percentile', 'Percentile')}: {structure.normative_percentile}%
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Processing time */}
              {result.processing_time_ms !== undefined && (
                <p className="text-xs text-ink-faint text-right tabular-nums">
                  {t('volumetry.computeTime', 'Computed in')} {result.processing_time_ms}ms
                </p>
              )}

              {/* Recompute button */}
              <Button
                variant="secondary"
                size="sm"
                fullWidth
                onClick={() => setResult(null)}
              >
                {t('volumetry.reset', 'Reset')}
              </Button>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default BrainVolumetryPanel;
