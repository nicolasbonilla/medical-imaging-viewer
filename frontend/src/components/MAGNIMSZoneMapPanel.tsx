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
import { Button } from '@/components/ui';
import { MAGNIMS_ZONE_NAMES, MAGNIMS_ZONE_RGB, regionRgb, rgbCss } from '@/utils/clinicalPalette';
import type { ZoneMapResult } from '@/types';

// Zone colours come from the shared clinical palette (Okabe-Ito) — the same table the
// image overlay paints with — so this legend can never disagree with the picture or
// with the lesion dashboard. (It used to be red/green/blue/yellow here while the
// dashboard used Okabe-Ito: the same region read as two different colours.)
function zoneColor(region: string): string | undefined {
  const rgb = regionRgb(region);
  return rgb ? rgbCss(rgb) : undefined;
}

const ZONE_LABEL_NAMES: Record<number, string> = {
  1: 'Periventricular',
  2: 'Juxtacortical',
  3: 'Infratentorial',
  4: 'Deep White Matter',
};

/** Selected state for the icon toggles (tinted brand selection, design-system v2). */
const TOGGLE_ON = 'border-brand-500/30 bg-brand-950 text-brand-400 hover:bg-brand-950 hover:text-brand-400';
const TOGGLE_OFF = 'text-ink-muted hover:text-ink-soft';

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
    <div className="space-y-2.5 rounded-lg border border-surface-border bg-surface-raised p-3">
      <div className="flex items-center gap-2">
        <Map className="h-4 w-4 shrink-0 text-brand-400" aria-hidden="true" />
        <span className="text-sm font-semibold text-ink-base">
          {t('zoneMap.title', 'MAGNIMS Zone Map')}
        </span>
        {isGenerated && (
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-clinical-good" />
        )}
      </div>

      {!isGenerated && (
        <p className="text-xs leading-relaxed text-ink-muted">
          {t('zoneMap.description',
            'Visualize anatomical zone boundaries (PV, JC, IT, DWM) as a semi-transparent background overlay. Requires brain parcellation (SynthSeg).'
          )}
        </p>
      )}

      {error && (
        <div className="flex items-start gap-1.5 rounded-md border border-clinical-crit/30 bg-clinical-crit/10 px-2 py-1.5 text-xs text-clinical-crit">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="min-w-0 break-words">{error}</span>
        </div>
      )}

      <div className="flex gap-1.5">
        {/* Generate / Regenerate */}
        <Button
          variant={isGenerated ? 'secondary' : 'primary'}
          size="sm"
          className="flex-1"
          onClick={handleGenerate}
          disabled={isGenerating || !fileId}
          aria-busy={isGenerating || undefined}
          leftIcon={isGenerating
            ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            : <Map className="h-3.5 w-3.5" aria-hidden="true" />}
        >
          {isGenerating
            ? t('zoneMap.generating', 'Generating...')
            : isGenerated ? t('zoneMap.regenerate', 'Regenerate') : t('zoneMap.generate', 'Generate')}
        </Button>

        {/* Toggle overlay visibility */}
        {isGenerated && (
          <Button
            variant="secondary"
            size="sm"
            onClick={handleToggleVisibility}
            className={`w-8 px-0 ${zoneMapVisible ? TOGGLE_ON : TOGGLE_OFF}`}
            title={zoneMapVisible ? t('zoneMap.hide', 'Hide zones') : t('zoneMap.show', 'Show zones')}
            aria-label={zoneMapVisible ? t('zoneMap.hide', 'Hide zones') : t('zoneMap.show', 'Show zones')}
          >
            {zoneMapVisible ? <Eye className="h-3.5 w-3.5" aria-hidden="true" /> : <EyeOff className="h-3.5 w-3.5" aria-hidden="true" />}
          </Button>
        )}

        {/* Toggle zone colorization */}
        {isGenerated && (
          <Button
            variant="secondary"
            size="sm"
            onClick={handleToggleColorize}
            className={`w-8 px-0 ${zoneColorizeEnabled ? TOGGLE_ON : TOGGLE_OFF}`}
            title={zoneColorizeEnabled
              ? t('zoneMap.colorizeOff', 'Normal label colors')
              : t('zoneMap.colorizeOn', 'Colorize lesions by zone')
            }
            aria-label={zoneColorizeEnabled
              ? t('zoneMap.colorizeOff', 'Normal label colors')
              : t('zoneMap.colorizeOn', 'Colorize lesions by zone')
            }
          >
            <Palette className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        )}
      </div>

      {/* Zone colorization legend — same palette as the image overlay */}
      {isGenerated && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-soft">
          {Object.entries(MAGNIMS_ZONE_NAMES).map(([id, zone]) => (
            <span key={id} className="flex items-center gap-1">
              <span
                aria-hidden="true"
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: rgbCss(MAGNIMS_ZONE_RGB[Number(id)]) }}
              />
              {zone.abbrev}
            </span>
          ))}
        </div>
      )}

      {/* Zone map opacity */}
      {isGenerated && zoneMapVisible && (
        <div>
          <div className="mb-1 flex items-center justify-between">
            <label className="text-xs text-ink-muted">{t('segmentation.zoneMapOpacity', 'Zone map opacity')}</label>
            <span className="text-xs tabular-nums text-ink-soft">{Math.round(zoneMapOpacity * 100)}%</span>
          </div>
          <input
            type="range"
            min="0"
            max="100"
            value={Math.round(zoneMapOpacity * 100)}
            onChange={(e) => setZoneMapOpacity(Number(e.target.value) / 100)}
            aria-label={t('segmentation.zoneMapOpacity', 'Zone map opacity')}
            className="h-1 w-full cursor-pointer appearance-none rounded-full bg-surface-hover accent-brand-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
          />
        </div>
      )}

      {/* Zone map stats */}
      {computedStats && (
        <div className="space-y-1.5 border-t border-surface-border pt-2">
          <div className="flex items-center justify-between text-xs tabular-nums text-ink-muted">
            {computedStats.processing_time_ms > 0 && (
              <span>{computedStats.processing_time_ms}ms</span>
            )}
            <span>{computedStats.total_brain_voxels.toLocaleString()} {t('zoneMap.brainVoxels', 'brain voxels')}</span>
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {Object.entries(computedStats.zone_stats).map(([region, stat]) => (
              <span key={region} className="flex items-center gap-1.5 text-xs">
                <span
                  aria-hidden="true"
                  className="h-2 w-2 shrink-0 rounded-full bg-ink-faint"
                  style={zoneColor(region) ? { backgroundColor: zoneColor(region) } : undefined}
                />
                <span
                  className="tabular-nums text-ink-soft"
                  style={zoneColor(region) ? { color: zoneColor(region) } : undefined}
                >
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
