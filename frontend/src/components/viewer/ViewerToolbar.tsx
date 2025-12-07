/**
 * Toolbar component with zoom and view reset controls.
 * Displays buttons for zoom in, zoom out, and reset view.
 */

import { useTranslation } from 'react-i18next';
import { ZoomIn, ZoomOut, RotateCw } from 'lucide-react';

interface ViewerToolbarProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onResetView: () => void;
}

export function ViewerToolbar({ onZoomIn, onZoomOut, onResetView }: ViewerToolbarProps) {
  const { t } = useTranslation();

  return (
    <div className="absolute top-4 right-4 bg-gray-900 bg-opacity-90 rounded-lg p-2 space-y-2">
      <button
        onClick={onZoomIn}
        className="block p-2 hover:bg-gray-800 rounded transition-colors"
        title={t('viewer.zoomIn')}
      >
        <ZoomIn className="w-5 h-5 text-white" />
      </button>
      <button
        onClick={onZoomOut}
        className="block p-2 hover:bg-gray-800 rounded transition-colors"
        title={t('viewer.zoomOut')}
      >
        <ZoomOut className="w-5 h-5 text-white" />
      </button>
      <button
        onClick={onResetView}
        className="block p-2 hover:bg-gray-800 rounded transition-colors"
        title={t('viewer.resetView')}
      >
        <RotateCw className="w-5 h-5 text-white" />
      </button>
    </div>
  );
}
