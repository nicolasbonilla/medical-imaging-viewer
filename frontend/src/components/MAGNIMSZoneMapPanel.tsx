/**
 * MAGNIMS Zone Map Panel
 *
 * Fully independent panel for generating and visualizing MAGNIMS anatomical zone
 * boundaries (PV, JC, IT, DWM) as a semi-transparent background overlay.
 *
 * This component does NOT depend on currentSegmentation — it reads zone map state
 * from its own Zustand fields (zoneMapMask, zoneMapVisible, zoneMapSegId).
 * This ensures the zone map layer is completely independent from lesion segmentations.
 *
 * @module components/MAGNIMSZoneMapPanel
 */

import { useState, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Map,
  Loader2,
  Eye,
  EyeOff,
  Palette,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import { segmentationAPI } from '@/api/segmentation';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type { ZoneMapResult } from '@/types';

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

const ZONE_LABEL_NAMES: Record<number, string> = {
  1: 'Periventricular',
  2: 'Juxtacortical',
  3: 'Infratentorial',
  4: 'Deep White Matter',
};

interface MAGNIMSZoneMapPanelProps {
  fileId: string | undefined;
}

/** Compute zone stats from a Uint8Array mask with labels 1-4 */
function computeStatsFromMask(mask: Uint8Array, segId: string, fileId: string): ZoneMapResult | null {
  const counts: Record<number, number> = { 1: 0, 2: 0, 3: 0, 4: 0 };
  let total = 0;
  for (let i = 0; i < mask.length; i++) {
    const v = mask[i];
    if (v >= 1 && v <= 4) {
      counts[v]++;
      total++;
    }
  }
  if (total === 0) return null;

  const zone_stats: Record<string, { zone_id: number; voxel_count: number; percentage: number }> = {};
  for (const [id, count] of Object.entries(counts)) {
    const name = ZONE_LABEL_NAMES[Number(id)];
    if (name && count > 0) {
      zone_stats[name] = {
        zone_id: Number(id),
        voxel_count: count,
        percentage: Math.round((count / total) * 1000) / 10,
      };
    }
  }

  return {
    segmentation_id: segId,
    file_id: fileId,
    zone_stats,
    total_brain_voxels: total,
    processing_time_ms: 0,
  } as ZoneMapResult;
}

export function MAGNIMSZoneMapPanel({ fileId }: MAGNIMSZoneMapPanelProps) {
  const { t } = useTranslation();
  // Zone map has its own independent state — NOT tied to currentSegmentation
  const zoneMapVisible = useSegmentationStore((s) => s.zoneMapVisible);
  const zoneColorizeEnabled = useSegmentationStore((s) => s.zoneColorizeEnabled);
  const zoneMapMask = useSegmentationStore((s) => s.zoneMapMask);
  const zoneMapSegId = useSegmentationStore((s) => s.zoneMapSegId);
  const zoneMapOpacity = useSegmentationStore((s) => s.zoneMapOpacity);
  const setZoneMapOpacity = useSegmentationStore((s) => s.setZoneMapOpacity);
  const [freshStats, setFreshStats] = useState<ZoneMapResult | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Zone map is "generated" when its mask data is loaded in the store
  const isGenerated = !!zoneMapMask;

  // Compute stats from the zoneMapMask
  const computedStats = useMemo(() => {
    if (freshStats) return freshStats;
    if (zoneMapMask && zoneMapSegId) {
      return computeStatsFromMask(zoneMapMask, zoneMapSegId, fileId ?? '');
    }
    return null;
  }, [freshStats, fileId, zoneMapMask, zoneMapSegId]);

  const handleGenerate = useCallback(async () => {
    if (!fileId) return;
    setIsGenerating(true);
    setError(null);
    try {
      const result = await segmentationAPI.generateZoneMap(fileId);
      setFreshStats(result);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || String(err));
    } finally {
      setIsGenerating(false);
    }
  }, [fileId]);

  // Toggle zone map visibility only (does NOT affect lesion overlays)
  const handleToggleVisibility = useCallback(() => {
    useSegmentationStore.getState().toggleZoneMapVisibility();
  }, []);

  // Toggle zone colorization mode
  const handleToggleColorize = useCallback(() => {
    useSegmentationStore.getState().toggleZoneColorize();
  }, []);

  return (
    <div className="bg-gray-800/80 rounded-xl p-3 space-y-2">
      <div className="flex items-center gap-2">
        <Map className="w-4 h-4 text-emerald-400" />
        <span className="text-sm font-semibold text-white">
          {t('zoneMap.title', 'MAGNIMS Zone Map')}
        </span>
        {isGenerated && (
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
        )}
      </div>

      {!isGenerated && (
        <p className="text-[9px] text-gray-400 leading-relaxed">
          {t('zoneMap.description',
            'Visualize anatomical zone boundaries (PV, JC, IT, DWM) as a semi-transparent background overlay. Requires brain parcellation (SynthSeg).'
          )}
        </p>
      )}

      {error && (
        <div className="flex items-center gap-1 text-red-400 text-[10px]">
          <AlertCircle className="w-3 h-3" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex gap-1.5">
        {/* Generate / Regenerate */}
        <button
          onClick={handleGenerate}
          disabled={isGenerating || !fileId}
          className="flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-xs text-white font-medium transition-colors"
        >
          {isGenerating ? (
            <>
              <Loader2 className="w-3 h-3 animate-spin" />
              {t('zoneMap.generating', 'Generating...')}
            </>
          ) : (
            <>
              <Map className="w-3 h-3" />
              {isGenerated ? t('zoneMap.regenerate', 'Regenerate') : t('zoneMap.generate', 'Generate')}
            </>
          )}
        </button>

        {/* Toggle overlay visibility */}
        {isGenerated && (
          <button
            onClick={handleToggleVisibility}
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

        {/* Toggle zone colorization */}
        {isGenerated && (
          <button
            onClick={handleToggleColorize}
            className={`px-2 py-1.5 rounded text-xs font-medium transition-colors ${
              zoneColorizeEnabled
                ? 'bg-amber-600 text-white'
                : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
            }`}
            title={zoneColorizeEnabled
              ? t('zoneMap.colorizeOff', 'Normal label colors')
              : t('zoneMap.colorizeOn', 'Colorize lesions by zone')
            }
          >
            <Palette className="w-3 h-3" />
          </button>
        )}
      </div>

      {/* Zone colorization legend */}
      {isGenerated && (
        <div className="flex items-center gap-2 text-[9px] text-gray-300">
          <span className="flex items-center gap-0.5"><span className="w-2 h-2 rounded-full bg-red-500" />PV</span>
          <span className="flex items-center gap-0.5"><span className="w-2 h-2 rounded-full bg-green-500" />JC</span>
          <span className="flex items-center gap-0.5"><span className="w-2 h-2 rounded-full bg-blue-500" />IT</span>
          <span className="flex items-center gap-0.5"><span className="w-2 h-2 rounded-full bg-yellow-500" />DWM</span>
        </div>
      )}

      {/* Zone map opacity */}
      {isGenerated && zoneMapVisible && (
        <div>
          <div className="flex items-center justify-between mb-0.5">
            <label className="text-[9px] text-gray-400">{t('segmentation.zoneMapOpacity', 'Zone map opacity')}</label>
            <span className="text-[9px] text-gray-500">{Math.round(zoneMapOpacity * 100)}%</span>
          </div>
          <input
            type="range"
            min="0"
            max="100"
            value={Math.round(zoneMapOpacity * 100)}
            onChange={(e) => setZoneMapOpacity(Number(e.target.value) / 100)}
            className="w-full h-1 bg-gray-700 rounded-full appearance-none cursor-pointer accent-emerald-500"
          />
        </div>
      )}

      {/* Zone map stats */}
      {computedStats && (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[9px] text-gray-400">
            {computedStats.processing_time_ms > 0 && (
              <span>{computedStats.processing_time_ms}ms</span>
            )}
            <span>{computedStats.total_brain_voxels.toLocaleString()} {t('zoneMap.brainVoxels', 'brain voxels')}</span>
          </div>
          <div className="flex flex-wrap gap-x-2 gap-y-1">
            {Object.entries(computedStats.zone_stats).map(([region, stat]) => (
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
  );
}
