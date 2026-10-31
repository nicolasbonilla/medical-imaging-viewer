/**
 * Legend of the fused longitudinal overlay of the 2D view (SegmentationCanvasLocal), shown with the comparison result
 * (LongitudinalResultPanel) — also when the comparison abstains: the overlay is what the reader compares visually.
 *
 * Independent review of PR #74 (m6): the legend hard-coded the former colours (blue / green / red). After PRB-031
 * changed the overlay to the shared colour-blind-safe palette, the legend no longer matched the image. It now takes its
 * colours from LONGITUDINAL_OVERLAY_COLORS, the constant the canvas draws with, so the two cannot disagree. The words
 * stay the neutral ones of CAPA-013 ("only at visit 1 / at both visits / only at visit 2": a candidate, not activity).
 */
import { useTranslation } from 'react-i18next';
import { LONGITUDINAL_OVERLAY_COLORS } from '@/utils/regionColors';

const ITEMS = [
  ['resolved', 'longitudinal.legendTp1', 'Only at visit 1'],
  ['persistent', 'longitudinal.legendBoth', 'At both visits'],
  ['new', 'longitudinal.legendTp2', 'Only at visit 2'],
] as const;

export function LongitudinalOverlayLegend() {
  const { t } = useTranslation();
  return (
    <div data-testid="longitudinal-legend"
         className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[9px] text-gray-500 dark:text-gray-400">
      {ITEMS.map(([key, i18nKey, text]) => (
        <span key={key} className="flex items-center gap-1" data-testid={`longitudinal-legend-${key}`}>
          <span data-swatch className="inline-block h-2 w-2 rounded-sm"
                style={{ backgroundColor: LONGITUDINAL_OVERLAY_COLORS[key] }} />
          {t(i18nKey, text)}
        </span>
      ))}
    </div>
  );
}

export default LongitudinalOverlayLegend;
