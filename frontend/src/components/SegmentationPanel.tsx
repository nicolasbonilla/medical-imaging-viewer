/**
 * SegmentationPanel - ITK-SNAP Style Segmentation Panel.
 *
 * Enhanced with:
 * - Hierarchical patient/study/series context
 * - Zustand state management integration
 * - React Query for data fetching
 * - Multi-expert workflow support
 * - Tabbed interface for create/load
 *
 * @module components/SegmentationPanel
 */

import React, { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { SegmentationList } from './SegmentationList';
import { useSegmentationStore, type PaintTool, type BrushShape } from '@/store/useSegmentationStore';
import {
  useSegmentationsBySeries,
  useSegmentation,
  useCreateSegmentation,
  useDeleteSegmentation,
  useSaveSegmentation,
  useUnloadSegmentationFromMemory,
} from '@/hooks/useSegmentations';
import type { LabelInfo, SegmentationCreate, Segmentation, SegmentationSummary } from '@/types';
import { DEFAULT_LABEL_PRESETS } from '@/types';

// ============================================================================
// Types
// ============================================================================

type TabType = 'load' | 'new';

interface SegmentationPanelProps {
  /** Patient ID for hierarchical context */
  patientId?: string;
  /** Study ID for hierarchical context */
  studyId?: string;
  /** Series ID for the current image series */
  seriesId?: string;
  /** Total slices in the series (for new segmentations) */
  totalSlices?: number;
  /** Image dimensions [width, height] for new segmentations */
  dimensions?: [number, number];
  /** Callback when overlay visibility changes */
  onOverlayVisibilityChange?: (visible: boolean) => void;
  /** Callback when active label changes */
  onActiveLabelChange?: (labelId: number) => void;
  /** Callback when brush size changes */
  onBrushSizeChange?: (size: number) => void;
  /** Callback when paint tool changes */
  onPaintToolChange?: (tool: PaintTool) => void;
  /** External loading state */
  isLoading?: boolean;
}

// ============================================================================
// Sub-Components
// ============================================================================

interface LabelPaletteProps {
  labels: LabelInfo[];
  activeLabel: number;
  labelVisibility: Record<number, boolean>;
  onSelectLabel: (id: number) => void;
  onToggleVisibility: (id: number) => void;
}

const LabelPalette: React.FC<LabelPaletteProps> = ({
  labels,
  activeLabel,
  labelVisibility,
  onSelectLabel,
  onToggleVisibility,
}) => {
  const { t } = useTranslation();

  return (
    <div className="space-y-1 max-h-40 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-600 scrollbar-track-gray-800">
      {labels
        .filter((label) => label.id !== 0) // Skip background
        .map((label) => {
          const isVisible = labelVisibility[label.id] !== false;
          return (
            <div
              key={label.id}
              onClick={() => onSelectLabel(label.id)}
              className={`
                flex items-center gap-2 p-2 rounded cursor-pointer transition-colors group
                ${
                  activeLabel === label.id
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-700 hover:bg-gray-600 text-gray-200'
                }
              `}
            >
              {/* Color swatch */}
              <div
                className="w-4 h-4 rounded border border-gray-500 flex-shrink-0"
                style={{
                  backgroundColor: label.color,
                  opacity: label.opacity,
                }}
              />

              {/* Label name */}
              <span className="text-xs flex-1 truncate">{label.name}</span>

              {/* Visibility toggle */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleVisibility(label.id);
                }}
                className={`
                  p-1 rounded transition-opacity
                  ${isVisible ? 'opacity-100' : 'opacity-50'}
                  ${activeLabel === label.id ? 'hover:bg-blue-700' : 'hover:bg-gray-500'}
                `}
                title={isVisible ? t('segmentation.hideLabel') : t('segmentation.showLabel')}
              >
                {isVisible ? (
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                ) : (
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                  </svg>
                )}
              </button>

              {/* Label ID */}
              <span className="text-xs opacity-70 hidden group-hover:inline">#{label.id}</span>
            </div>
          );
        })}
    </div>
  );
};

interface PaintToolbarProps {
  paintTool: PaintTool;
  brushSize: number;
  brushShape: BrushShape;
  onToolChange: (tool: PaintTool) => void;
  onBrushSizeChange: (size: number) => void;
  onBrushShapeChange: (shape: BrushShape) => void;
}

const PaintToolbar: React.FC<PaintToolbarProps> = ({
  paintTool,
  brushSize,
  brushShape,
  onToolChange,
  onBrushSizeChange,
  onBrushShapeChange,
}) => {
  const { t } = useTranslation();

  const tools: { id: PaintTool; icon: React.ReactNode; label: string }[] = [
    {
      id: 'brush',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
        </svg>
      ),
      label: t('segmentation.tools.brush'),
    },
    {
      id: 'eraser',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>
      ),
      label: t('segmentation.tools.eraser'),
    },
    {
      id: 'fill',
      icon: (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
          <path d="M19 11h-6V5h-2v6H5v2h6v6h2v-6h6z" />
        </svg>
      ),
      label: t('segmentation.tools.fill'),
    },
  ];

  return (
    <div className="space-y-3">
      {/* Tool buttons */}
      <div className="flex gap-1">
        {tools.map((tool) => (
          <button
            key={tool.id}
            onClick={() => onToolChange(tool.id)}
            className={`
              flex-1 px-2 py-1.5 rounded text-xs font-medium transition-colors flex items-center justify-center gap-1
              ${
                paintTool === tool.id
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
              }
            `}
            title={tool.label}
          >
            {tool.icon}
          </button>
        ))}
      </div>

      {/* Brush size */}
      <div>
        <label className="block text-xs text-gray-300 mb-1">
          {t('segmentation.brushSize')}: {brushSize}×{brushSize} {t('segmentation.voxels')}
        </label>
        <input
          type="range"
          min="1"
          max="30"
          value={brushSize}
          onChange={(e) => onBrushSizeChange(Number(e.target.value))}
          className="w-full h-1.5 bg-gray-700 rounded-full appearance-none cursor-pointer accent-blue-500"
        />
      </div>

      {/* Brush shape */}
      <div className="flex gap-1">
        <button
          onClick={() => onBrushShapeChange('circle')}
          className={`
            flex-1 px-2 py-1 rounded text-xs transition-colors
            ${brushShape === 'circle' ? 'bg-blue-600 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}
          `}
        >
          ○ {t('segmentation.circle')}
        </button>
        <button
          onClick={() => onBrushShapeChange('square')}
          className={`
            flex-1 px-2 py-1 rounded text-xs transition-colors
            ${brushShape === 'square' ? 'bg-blue-600 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}
          `}
        >
          □ {t('segmentation.square')}
        </button>
      </div>
    </div>
  );
};

// ============================================================================
// Main Component
// ============================================================================

export const SegmentationPanel: React.FC<SegmentationPanelProps> = ({
  patientId,
  studyId,
  seriesId,
  totalSlices = 1,
  dimensions = [256, 256],
  onOverlayVisibilityChange,
  onActiveLabelChange,
  onBrushSizeChange,
  onPaintToolChange,
  isLoading: externalLoading = false,
}) => {
  const { t } = useTranslation();

  // Local state
  const [expanded, setExpanded] = useState(true);
  const [activeTab, setActiveTab] = useState<TabType>('load');
  const [newSegmentationName, setNewSegmentationName] = useState('');

  // Zustand store
  const {
    activeSegmentation,
    activeLabel,
    labelVisibility,
    paintTool,
    isOverlayVisible,
    isDirty,
    isSaving,
    setActiveLabel,
    toggleLabelVisibility,
    setPaintTool,
    setBrushSize,
    setBrushShape,
    setIsOverlayVisible,
    setActiveSegmentation,
    reset,
  } = useSegmentationStore();

  // React Query hooks
  const {
    data: segmentationListData,
    isLoading: isLoadingList,
  } = useSegmentationsBySeries(patientId, studyId, seriesId);

  const createSegmentation = useCreateSegmentation();
  const deleteSegmentation = useDeleteSegmentation();
  const saveSegmentation = useSaveSegmentation();
  const unloadSegmentation = useUnloadSegmentationFromMemory();

  const segmentations = segmentationListData?.items ?? [];

  // Sync overlay visibility with parent
  useEffect(() => {
    onOverlayVisibilityChange?.(isOverlayVisible);
  }, [isOverlayVisible, onOverlayVisibilityChange]);

  // Sync active label with parent
  useEffect(() => {
    onActiveLabelChange?.(activeLabel);
  }, [activeLabel, onActiveLabelChange]);

  // Sync brush size with parent
  useEffect(() => {
    onBrushSizeChange?.(paintTool.brushSize);
  }, [paintTool.brushSize, onBrushSizeChange]);

  // Sync paint tool with parent
  useEffect(() => {
    onPaintToolChange?.(paintTool.tool);
  }, [paintTool.tool, onPaintToolChange]);

  // Handlers
  const handleCreateSegmentation = useCallback(async () => {
    if (!patientId || !studyId || !seriesId) return;

    const name = newSegmentationName.trim() || `Segmentation ${new Date().toLocaleDateString()}`;

    const createData: SegmentationCreate = {
      series_id: seriesId,
      name,
      description: '',
      labels: DEFAULT_LABEL_PRESETS.BRATS,
    };

    try {
      await createSegmentation.mutateAsync({
        patientId,
        studyId,
        seriesId,
        data: createData,
      });
      setNewSegmentationName('');
      setActiveTab('load');
    } catch (error) {
      console.error('Failed to create segmentation:', error);
    }
  }, [patientId, studyId, seriesId, newSegmentationName, totalSlices, dimensions, createSegmentation]);

  const handleLoadSegmentation = useCallback((segmentationId: string) => {
    // The useSegmentation hook will update the store
    // We just need to trigger a fetch here
    // For now, we'll use the data from the list
    const seg = segmentations.find((s: SegmentationSummary) => s.id === segmentationId);
    if (seg) {
      // Load full segmentation data (this would typically be a separate API call)
      // For now, we create a mock Segmentation from the summary
      // In production, this would be handled by useSegmentation hook
    }
  }, [segmentations]);

  const handleDeleteSegmentation = useCallback(async (segmentationId: string) => {
    try {
      await deleteSegmentation.mutateAsync(segmentationId);
    } catch (error) {
      console.error('Failed to delete segmentation:', error);
    }
  }, [deleteSegmentation]);

  const handleSaveSegmentation = useCallback(async () => {
    if (!activeSegmentation) return;
    try {
      await saveSegmentation.mutateAsync(activeSegmentation.id);
    } catch (error) {
      console.error('Failed to save segmentation:', error);
    }
  }, [activeSegmentation, saveSegmentation]);

  const handleCloseSegmentation = useCallback(async () => {
    if (!activeSegmentation) return;

    // Warn about unsaved changes
    if (isDirty) {
      const shouldSave = window.confirm(t('segmentation.unsavedChanges'));
      if (shouldSave) {
        await handleSaveSegmentation();
      }
    }

    try {
      await unloadSegmentation.mutateAsync(activeSegmentation.id);
    } catch (error) {
      console.error('Failed to close segmentation:', error);
      // Reset anyway
      reset();
      setActiveSegmentation(null);
    }
  }, [activeSegmentation, isDirty, handleSaveSegmentation, unloadSegmentation, reset, setActiveSegmentation, t]);

  // Derived state
  const isLoading = externalLoading || isLoadingList || createSegmentation.isPending;
  const hasContext = !!patientId && !!studyId && !!seriesId;

  return (
    <div className="bg-gray-800 rounded-lg shadow-lg">
      {/* Header */}
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-700 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
          </svg>
          {t('segmentation.manualSegmentation')}
          {segmentations.length > 0 && (
            <span className="ml-1 px-1.5 py-0.5 bg-blue-600 rounded-full text-xs">
              {segmentations.length}
            </span>
          )}
        </h3>
        <span className="text-gray-400 text-sm">{expanded ? '▼' : '▶'}</span>
      </div>

      {expanded && (
        <div className="p-3 space-y-3 border-t border-gray-700">
          {/* No context warning */}
          {!hasContext && (
            <div className="text-center py-4 text-gray-400">
              <svg
                className="w-8 h-8 mx-auto mb-2 text-gray-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <p className="text-xs">{t('segmentation.selectImageFirst')}</p>
            </div>
          )}

          {/* No segmentation active - show tabs */}
          {hasContext && !activeSegmentation && (
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
                    activeSegmentationId={(activeSegmentation as Segmentation | null)?.id}
                    isLoading={isLoading}
                    isDeleting={deleteSegmentation.isPending}
                  />
                )}

                {activeTab === 'new' && (
                  <div className="py-4 space-y-4">
                    {/* Name input */}
                    <div>
                      <label className="block text-xs text-gray-300 mb-1">
                        {t('segmentation.name')}
                      </label>
                      <input
                        type="text"
                        value={newSegmentationName}
                        onChange={(e) => setNewSegmentationName(e.target.value)}
                        placeholder={t('segmentation.namePlaceholder')}
                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white placeholder-gray-400 focus:outline-none focus:border-blue-500"
                      />
                    </div>

                    {/* Create button */}
                    <button
                      onClick={handleCreateSegmentation}
                      disabled={createSegmentation.isPending}
                      className="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-sm font-medium transition-colors flex items-center justify-center gap-2"
                    >
                      {createSegmentation.isPending ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                          <span>{t('segmentation.creating')}</span>
                        </>
                      ) : (
                        <>
                          <span>+</span>
                          <span>{t('segmentation.newSegmentation')}</span>
                        </>
                      )}
                    </button>

                    <p className="text-xs text-gray-400 text-center">
                      {t('segmentation.createNewEmpty')}
                    </p>
                  </div>
                )}
              </div>
            </>
          )}

          {/* Active segmentation - show controls */}
          {activeSegmentation && (
            <>
              {/* Segmentation info header */}
              <div className="bg-gray-700/50 rounded p-2 border border-gray-600">
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-xs font-medium text-white truncate">
                        {activeSegmentation.name}
                      </p>
                      {isDirty && (
                        <span className="text-xs text-yellow-400" title={t('segmentation.unsavedChanges')}>
                          •
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400 flex items-center gap-1">
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                      {activeSegmentation.created_by_name || activeSegmentation.created_by}
                    </p>
                  </div>
                  <button
                    onClick={handleCloseSegmentation}
                    className="ml-2 px-2 py-1 text-xs text-gray-400 hover:text-white hover:bg-gray-600 rounded transition-colors"
                    title={t('segmentation.closeSegmentation')}
                  >
                    ✕
                  </button>
                </div>

                {/* Progress bar */}
                <div className="mt-2">
                  <div className="flex justify-between text-xs text-gray-400 mb-1">
                    <span>{t('segmentation.progress.annotated')}</span>
                    <span>
                      {activeSegmentation.slices_annotated}/{activeSegmentation.total_slices} (
                      {activeSegmentation.progress_percentage}%)
                    </span>
                  </div>
                  <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-blue-500 to-blue-400 transition-all duration-300"
                      style={{ width: `${activeSegmentation.progress_percentage}%` }}
                    />
                  </div>
                </div>
              </div>

              {/* Show Overlay Toggle */}
              <div className="flex items-center justify-between">
                <label className="text-xs text-gray-300">{t('segmentation.showOverlay')}</label>
                <button
                  onClick={() => setIsOverlayVisible(!isOverlayVisible)}
                  className={`
                    relative w-10 h-5 rounded-full transition-colors
                    ${isOverlayVisible ? 'bg-blue-600' : 'bg-gray-600'}
                  `}
                >
                  <span
                    className={`
                      absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform
                      ${isOverlayVisible ? 'translate-x-5' : 'translate-x-0'}
                    `}
                  />
                </button>
              </div>

              {/* Labels List */}
              <div>
                <label className="block text-xs text-gray-300 mb-2">
                  {t('segmentation.labels')} ({activeSegmentation.labels.filter((l) => l.id !== 0).length})
                </label>
                <LabelPalette
                  labels={activeSegmentation.labels}
                  activeLabel={activeLabel}
                  labelVisibility={labelVisibility}
                  onSelectLabel={setActiveLabel}
                  onToggleVisibility={toggleLabelVisibility}
                />
              </div>

              {/* Paint Tools */}
              <div className="border-t border-gray-700 pt-3">
                <label className="block text-xs text-gray-300 mb-2">{t('segmentation.paintTools')}</label>
                <PaintToolbar
                  paintTool={paintTool.tool}
                  brushSize={paintTool.brushSize}
                  brushShape={paintTool.brushShape}
                  onToolChange={setPaintTool}
                  onBrushSizeChange={setBrushSize}
                  onBrushShapeChange={setBrushShape}
                />
              </div>

              {/* Save Button */}
              <button
                onClick={handleSaveSegmentation}
                disabled={isSaving || !isDirty}
                className="w-full px-3 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-sm font-medium transition-colors flex items-center justify-center gap-2"
              >
                {isSaving ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                    <span>{t('segmentation.saving')}</span>
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                    </svg>
                    <span>{t('segmentation.saveSegmentation')}</span>
                  </>
                )}
              </button>

              {/* Instructions */}
              <div className="pt-2 border-t border-gray-700">
                <p className="text-xs text-gray-400">
                  <strong>{t('segmentation.instructions.title')}</strong>
                  <br />• {t('segmentation.instructions.clickDrag')}
                  <br />• {t('segmentation.instructions.selectLabel')}
                  <br />• {t('segmentation.instructions.adjustBrush')}
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

export default SegmentationPanel;
