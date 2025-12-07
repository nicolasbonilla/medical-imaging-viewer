/**
 * Segmentation panel component - ITK-SNAP style
 * Enhanced with tabbed interface for creating new or loading existing segmentations
 */

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type {
  LabelInfo,
  SegmentationResponse,
  SegmentationListItem,
} from '../types/segmentation';
import { SegmentationList } from './SegmentationList';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

type TabType = 'load' | 'new';

interface SegmentationPanelProps {
  // Current segmentation state
  currentSegmentation: SegmentationResponse | null;
  selectedLabelId: number;
  brushSize: number;
  eraseMode: boolean;
  showOverlay: boolean;

  // Segmentation list
  segmentations?: SegmentationListItem[];
  isLoadingList?: boolean;
  isLoadingSegmentation?: boolean;
  isDeletingSegmentation?: boolean;

  // Actions
  onCreateSegmentation: () => void;
  onLoadSegmentation?: (segmentationId: string) => void;
  onDeleteSegmentation?: (segmentationId: string) => void;
  onSelectLabel: (labelId: number) => void;
  onBrushSizeChange: (size: number) => void;
  onEraseModeChange: (erase: boolean) => void;
  onShowOverlayChange: (show: boolean) => void;
  onCloseSegmentation?: () => void;
}

export const SegmentationPanel: React.FC<SegmentationPanelProps> = ({
  currentSegmentation,
  selectedLabelId,
  brushSize,
  eraseMode,
  showOverlay,
  segmentations = [],
  isLoadingList = false,
  isLoadingSegmentation = false,
  isDeletingSegmentation = false,
  onCreateSegmentation,
  onLoadSegmentation,
  onDeleteSegmentation,
  onSelectLabel,
  onBrushSizeChange,
  onEraseModeChange,
  onShowOverlayChange,
  onCloseSegmentation,
}) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(true);
  const [activeTab, setActiveTab] = useState<TabType>('load');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!currentSegmentation) return;

    setSaving(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/segmentation/${currentSegmentation.segmentation_id}/save`,
        { method: 'POST' }
      );

      if (!response.ok) {
        throw new Error('Failed to save segmentation');
      }

      const data = await response.json();
      alert(
        `${t('segmentation.savedSuccessfully')}:\n${data.output_path || data.dicom_directory}`
      );
    } catch (error) {
      console.error('Error saving segmentation:', error);
      alert(t('segmentation.errorSaving'));
    } finally {
      setSaving(false);
    }
  };

  const handleLoadSegmentation = (segmentationId: string) => {
    if (onLoadSegmentation) {
      onLoadSegmentation(segmentationId);
    }
  };

  const handleDeleteSegmentation = (segmentationId: string) => {
    if (onDeleteSegmentation) {
      onDeleteSegmentation(segmentationId);
    }
  };

  return (
    <div className="bg-gray-800 rounded-lg shadow-lg">
      {/* Header */}
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-700 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <span className="text-lg">🎨</span>
          {t('segmentation.manualSegmentation')}
        </h3>
        <span className="text-gray-400 text-sm">{expanded ? '▼' : '▶'}</span>
      </div>

      {expanded && (
        <div className="p-3 space-y-3 border-t border-gray-700">
          {/* No segmentation active - show tabs */}
          {!currentSegmentation && (
            <>
              {/* Tab Headers */}
              <div className="flex gap-1 bg-gray-900 p-1 rounded">
                <button
                  onClick={() => setActiveTab('load')}
                  className={`flex-1 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                    activeTab === 'load'
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-gray-700'
                  }`}
                >
                  {t('segmentation.open')} ({segmentations.length})
                </button>
                <button
                  onClick={() => setActiveTab('new')}
                  className={`flex-1 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                    activeTab === 'new'
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-gray-700'
                  }`}
                >
                  {t('segmentation.new')}
                </button>
              </div>

              {/* Tab Content */}
              <div className="min-h-[200px]">
                {activeTab === 'load' && (
                  <SegmentationList
                    segmentations={segmentations}
                    onLoad={handleLoadSegmentation}
                    onDelete={handleDeleteSegmentation}
                    isLoading={isLoadingList || isLoadingSegmentation}
                    isDeleting={isDeletingSegmentation}
                  />
                )}

                {activeTab === 'new' && (
                  <div className="py-8">
                    <button
                      onClick={onCreateSegmentation}
                      disabled={isLoadingSegmentation}
                      className="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-sm font-medium transition-colors flex items-center justify-center gap-2"
                    >
                      {isLoadingSegmentation ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                          <span>{t('segmentation.creating')}</span>
                        </>
                      ) : (
                        <>
                          <span>+</span>
                          <span>{t('segmentation.newSegmentation')}</span>
                        </>
                      )}
                    </button>
                    <p className="text-xs text-gray-400 text-center mt-3">
                      {t('segmentation.createNewEmpty')}
                    </p>
                  </div>
                )}
              </div>
            </>
          )}

          {/* Active segmentation - show controls */}
          {currentSegmentation && (
            <>
              {/* Segmentation info header */}
              <div className="bg-gray-700/50 rounded p-2 border border-gray-600">
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-white truncate">
                      {currentSegmentation.metadata.description ||
                        t('segmentation.activeSegmentation')}
                    </p>
                    <p className="text-xs text-gray-400">
                      {t('segmentation.id')}: {currentSegmentation.segmentation_id.substring(0, 8)}
                      ...
                    </p>
                  </div>
                  {onCloseSegmentation && (
                    <button
                      onClick={onCloseSegmentation}
                      className="ml-2 px-2 py-1 text-xs text-gray-400 hover:text-white hover:bg-gray-600 rounded transition-colors"
                      title={t('segmentation.closeSegmentation')}
                    >
                      ✕
                    </button>
                  )}
                </div>
              </div>

              {/* Show Overlay Toggle */}
              <div className="flex items-center justify-between">
                <label className="text-xs text-gray-300">{t('segmentation.showOverlay')}</label>
                <input
                  type="checkbox"
                  checked={showOverlay}
                  onChange={(e) => onShowOverlayChange(e.target.checked)}
                  className="w-4 h-4 rounded"
                />
              </div>

              {/* Labels List */}
              <div>
                <label className="block text-xs text-gray-300 mb-2">
                  {t('segmentation.labels')}
                </label>
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {currentSegmentation.metadata.labels
                    .filter((label) => label.id !== 0) // Skip background
                    .map((label) => (
                      <div
                        key={label.id}
                        onClick={() => onSelectLabel(label.id)}
                        className={`
                          flex items-center gap-2 p-2 rounded cursor-pointer transition-colors
                          ${
                            selectedLabelId === label.id
                              ? 'bg-blue-600 text-white'
                              : 'bg-gray-700 hover:bg-gray-600 text-gray-200'
                          }
                        `}
                      >
                        <div
                          className="w-4 h-4 rounded border border-gray-500"
                          style={{ backgroundColor: label.color }}
                        />
                        <span className="text-xs flex-1">{label.name}</span>
                        <span className="text-xs opacity-70">
                          {t('segmentation.id')}: {label.id}
                        </span>
                      </div>
                    ))}
                </div>
              </div>

              {/* Brush Size */}
              <div>
                <label className="block text-xs text-gray-300 mb-1">
                  {t('segmentation.brushSize')}: {brushSize}×{brushSize} {t('segmentation.voxels')}
                </label>
                <input
                  type="range"
                  min="1"
                  max="20"
                  value={brushSize}
                  onChange={(e) => onBrushSizeChange(Number(e.target.value))}
                  className="w-full"
                />
              </div>

              {/* Erase Mode Toggle */}
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="eraseMode"
                  checked={eraseMode}
                  onChange={(e) => onEraseModeChange(e.target.checked)}
                  className="w-4 h-4 rounded"
                />
                <label
                  htmlFor="eraseMode"
                  className="text-xs text-gray-300 cursor-pointer"
                >
                  {t('segmentation.eraseMode')}
                </label>
              </div>

              {/* Save Button */}
              <button
                onClick={handleSave}
                disabled={saving}
                className="w-full px-3 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-sm font-medium transition-colors"
              >
                {saving ? t('segmentation.saving') : `💾 ${t('segmentation.saveSegmentation')}`}
              </button>

              {/* Instructions */}
              <div className="pt-2 border-t border-gray-700">
                <p className="text-xs text-gray-400">
                  <strong>{t('segmentation.instructions.title')}</strong>
                  <br />
                  • {t('segmentation.instructions.clickDrag')}
                  <br />
                  • {t('segmentation.instructions.selectLabel')}
                  <br />
                  • {t('segmentation.instructions.adjustBrush')}
                  <br />• {t('segmentation.instructions.eraseMode')}
                </p>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};
