/**
 * Component displaying current slice information and zoom level.
 * Shows slice number, total slices, zoom percentage, and render mode.
 */

import { useTranslation } from 'react-i18next';
import type { RenderMode } from '@/hooks/useViewerControls';

interface SliceInfoProps {
  currentSliceIndex: number;
  totalSlices: number;
  zoomLevel: number;
  renderMode: RenderMode;
}

export function SliceInfo({ currentSliceIndex, totalSlices, zoomLevel, renderMode }: SliceInfoProps) {
  const { t } = useTranslation();

  return (
    <div className="absolute bottom-4 left-4 bg-gray-900 bg-opacity-90 rounded-lg px-4 py-2">
      <div className="text-sm text-white">
        {t('viewer.slice')}: {currentSliceIndex + 1} / {totalSlices}
      </div>
      {(renderMode === 'standard' || renderMode === 'niivue') && (
        <div className="text-xs text-gray-400 mt-1">
          {t('viewer.zoom')}: {(zoomLevel * 100).toFixed(0)}%
        </div>
      )}
      {renderMode === 'matplotlib' && (
        <div className="text-xs text-blue-400 mt-1">
          {t('viewer.matplotlibStatic')}
        </div>
      )}
      {renderMode === 'niivue' && (
        <div className="text-xs text-green-400 mt-1">
          WebGL2 NIfTI
        </div>
      )}
    </div>
  );
}
