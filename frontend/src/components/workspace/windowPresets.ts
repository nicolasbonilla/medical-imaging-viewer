/**
 * Window/level presets for the workspace toolbar and image panel (v3).
 *
 * Client path (browser rendering): C/W are in REAL voxel units; 0/0 means "Auto"
 * (robust 0.5–99.5 % of the non-background voxels). The server's metadata seed is
 * computed on its 0–255 normalised copy (global min–max), so it is mapped back to real
 * units exactly: real = min + v · (max − min) / 255.
 */
import type { IntensityStats, WindowLevel } from '@/volume/windowing';
import { autoWindow, fullRangeWindow } from '@/volume/windowing';

export type PresetId = 'auto' | 'full' | 'server';

export interface WindowPreset {
  id: PresetId;
  wl: WindowLevel;
}

export function serverSeedToReal(
  seed: { center?: number | null; width?: number | null },
  stats: Pick<IntensityStats, 'min' | 'max'>,
): WindowLevel | null {
  if (seed.center == null || seed.width == null || !(seed.width > 0)) return null;
  const k = (stats.max - stats.min) / 255;
  if (!(k > 0)) return null;
  return { center: stats.min + seed.center * k, width: seed.width * k };
}

export function clientPresets(
  stats: IntensityStats,
  seed: { center?: number | null; width?: number | null },
): WindowPreset[] {
  const out: WindowPreset[] = [
    { id: 'auto', wl: autoWindow(stats) },
    { id: 'full', wl: fullRangeWindow(stats) },
  ];
  const s = serverSeedToReal(seed, stats);
  if (s) out.push({ id: 'server', wl: s });
  return out;
}

/** Effective window shown for a store value (0/0 = auto). */
export function effectiveWindow(center: number, width: number, stats: IntensityStats): WindowLevel {
  return width > 0 ? { center, width } : autoWindow(stats);
}

/** Compact number for clinical read-outs: integers stay integers, small ranges keep decimals. */
export function formatIntensity(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1000) return Math.round(v).toString();
  if (a >= 100) return v.toFixed(0);
  if (a >= 10) return v.toFixed(1);
  return v.toFixed(2);
}
