/**
 * Comparison Metrics Panel
 *
 * Displays pairwise comparison metrics (Dice, Hausdorff, volume diff)
 * between expert masks and user segmentations. Includes per-slice Dice
 * sparkline chart and agreement map toggle.
 *
 * @module components/ComparisonMetricsPanel
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { BarChart3, Loader2, AlertCircle } from 'lucide-react';
import { segmentationAPI, type PairwiseComparison, type ComparisonResult } from '@/api/segmentation';
import type { ExpertMaskData, ImagingInstance } from '@/types';

interface ComparisonMetricsPanelProps {
  /** Expert masks that are loaded and visible */
  expertMasks: Map<string, ExpertMaskData>;
  /** Expert annotation instances (for GCS path resolution) */
  expertInstances?: ImagingInstance[];
  /** Currently active segmentation ID (if user has one) */
  activeSegmentationId?: string | null;
  /** Callback to navigate to a specific slice */
  onNavigateToSlice?: (sliceIndex: number) => void;
}

/**
 * Get Dice quality badge color.
 */
function getDiceColor(dice: number): string {
  if (dice >= 0.7) return 'text-green-400';
  if (dice >= 0.5) return 'text-yellow-400';
  return 'text-red-400';
}

function getDiceBg(dice: number): string {
  if (dice >= 0.7) return 'bg-green-500';
  if (dice >= 0.5) return 'bg-yellow-500';
  return 'bg-red-500';
}

/**
 * Small sparkline canvas showing per-slice Dice values.
 */
function DiceSparkline({
  data,
  onSliceClick,
}: {
  data: number[];
  onSliceClick?: (sliceIndex: number) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || data.length === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    // Background
    ctx.fillStyle = '#1f2937';
    ctx.fillRect(0, 0, w, h);

    // Reference lines
    ctx.strokeStyle = '#374151';
    ctx.lineWidth = 0.5;
    [0.25, 0.5, 0.75].forEach((level) => {
      const y = h - level * h;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    });

    // Dice curve
    const stepX = w / Math.max(data.length - 1, 1);
    ctx.beginPath();
    ctx.strokeStyle = '#3B82F6';
    ctx.lineWidth = 1.5;
    data.forEach((val, i) => {
      const x = i * stepX;
      const y = h - val * h;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Fill under curve
    ctx.lineTo((data.length - 1) * stepX, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    ctx.fillStyle = 'rgba(59, 130, 246, 0.15)';
    ctx.fill();
  }, [data]);

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!onSliceClick || data.length === 0) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const sliceIndex = Math.round((x / rect.width) * (data.length - 1));
      onSliceClick(Math.max(0, Math.min(data.length - 1, sliceIndex)));
    },
    [data, onSliceClick]
  );

  return (
    <canvas
      ref={canvasRef}
      width={200}
      height={40}
      className="w-full h-10 rounded cursor-pointer"
      onClick={handleClick}
      title="Click to navigate to slice"
    />
  );
}

export function ComparisonMetricsPanel({
  expertMasks,
  expertInstances,
  activeSegmentationId,
  onNavigateToSlice,
}: ComparisonMetricsPanelProps) {
  const { t } = useTranslation();
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPair, setSelectedPair] = useState<number>(0);

  // Collect available masks for comparison (include gcs_path for fast backend lookup)
  const availableMasks: { type: 'segmentation' | 'instance'; id: string; label: string; gcs_path?: string }[] =
    Array.from(expertMasks.entries())
      .filter(([, data]) => data.visible && data.mask)
      .map(([id, data]) => {
        const inst = expertInstances?.find(i => i.id === id);
        return {
          type: 'instance' as const,
          id,
          label: data.label,
          gcs_path: inst?.gcs_object_name,
        };
      });

  // Add user segmentation if active
  if (activeSegmentationId && !activeSegmentationId.startsWith('local-')) {
    availableMasks.unshift({
      type: 'segmentation',
      id: activeSegmentationId,
      label: t('comparison.mySegmentation', 'My Segmentation'),
    });
  }

  const canCompare = availableMasks.length >= 2;

  const handleCompare = useCallback(async () => {
    if (!canCompare) return;

    setIsLoading(true);
    setError(null);
    try {
      const data = await segmentationAPI.compareMasks(availableMasks);
      setResult(data);
      setSelectedPair(0);
    } catch (err) {
      setError(String(err));
    } finally {
      setIsLoading(false);
    }
  }, [availableMasks, canCompare]);

  const currentPair: PairwiseComparison | null = result?.comparisons[selectedPair] ?? null;

  return (
    <div className="bg-gray-800/80 rounded-xl p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-semibold text-white">
            {t('comparison.title', 'Comparison Metrics')}
          </span>
        </div>
        <button
          onClick={handleCompare}
          disabled={!canCompare || isLoading}
          className="px-2 py-1 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-xs text-white transition-colors"
        >
          {isLoading ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            t('comparison.compare', 'Compare')
          )}
        </button>
      </div>

      {!canCompare && (
        <p className="text-[10px] text-gray-500">
          {t('comparison.needTwo', 'Enable 2+ expert masks to compare')}
        </p>
      )}

      {error && (
        <div className="flex items-center gap-1 text-red-400 text-xs">
          <AlertCircle className="w-3 h-3" />
          <span>{error}</span>
        </div>
      )}

      {result && result.comparisons.length > 0 && (
        <>
          {/* Pairwise selector (if >1 pair) */}
          {result.comparisons.length > 1 && (
            <div className="flex flex-wrap gap-1">
              {result.comparisons.map((pair, i) => (
                <button
                  key={i}
                  onClick={() => setSelectedPair(i)}
                  className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                    i === selectedPair
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                  }`}
                >
                  {pair.label_a} vs {pair.label_b}
                </button>
              ))}
            </div>
          )}

          {currentPair && (
            <div className="space-y-2">
              {/* Metrics table */}
              <div className="bg-gray-900/50 rounded-lg p-2 space-y-1.5">
                {/* Dice */}
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-gray-400">Dice</span>
                  <div className="flex items-center gap-1.5">
                    <div className="w-16 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${getDiceBg(currentPair.dice)}`}
                        style={{ width: `${currentPair.dice * 100}%` }}
                      />
                    </div>
                    <span className={`text-xs font-mono font-bold ${getDiceColor(currentPair.dice)}`}>
                      {(currentPair.dice * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>

                {/* Hausdorff */}
                {currentPair.hausdorff_mm !== null && (
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-gray-400">HD95</span>
                    <span className="text-xs font-mono text-white">
                      {currentPair.hausdorff_mm.toFixed(1)} mm
                    </span>
                  </div>
                )}

                {/* Volume diff */}
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-gray-400">{t('comparison.volumeDiff', 'Vol Diff')}</span>
                  <span className={`text-xs font-mono ${
                    Math.abs(currentPair.volume.diff_percent) < 10 ? 'text-green-400' : 'text-yellow-400'
                  }`}>
                    {currentPair.volume.diff_percent > 0 ? '+' : ''}{currentPair.volume.diff_percent.toFixed(1)}%
                  </span>
                </div>

                {/* Volume values */}
                <div className="flex items-center justify-between text-[9px] text-gray-500">
                  <span>{currentPair.label_a}: {(currentPair.volume.volume_a_mm3 / 1000).toFixed(2)} mL</span>
                  <span>{currentPair.label_b}: {(currentPair.volume.volume_b_mm3 / 1000).toFixed(2)} mL</span>
                </div>
              </div>

              {/* Per-slice Dice sparkline */}
              {currentPair.per_slice_dice.length > 0 && (
                <div>
                  <label className="text-[10px] text-gray-400 block mb-1">
                    {t('comparison.perSliceDice', 'Dice per Slice')}
                  </label>
                  <DiceSparkline
                    data={currentPair.per_slice_dice}
                    onSliceClick={onNavigateToSlice}
                  />
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
