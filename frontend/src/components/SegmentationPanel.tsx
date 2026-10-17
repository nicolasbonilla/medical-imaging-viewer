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
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, Loader2, Plus, X } from 'lucide-react';
import { Badge, Button, Input } from '@/components/ui';
import { SegmentationList } from './SegmentationList';
import { useSegmentationStore, type PaintTool, type BrushShape, type DrawOverMode } from '@/store/useSegmentationStore';
import { useViewerStore } from '@/store/useViewerStore';
import { segmentationAPI } from '@/api/segmentation';
import { ClinicalToolsPanel } from './ClinicalToolsPanel';
import { ConformalPanel } from './ConformalPanel';
import type { LabelInfo, Segmentation, SegmentationResponse } from '@/types';

// ============================================================================
// Types
// ============================================================================

type TabType = 'load' | 'new' | 'tools' | 'paint';

// ============================================================================
// Styling (design-system v2 tokens; presentation only)
// ============================================================================

const FOCUS_RING = 'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60';

/** Segmented-control / tool toggle: tinted brand fill when selected. */
const toggleClass = (selected: boolean) =>
  `border transition-colors ${FOCUS_RING} ${
    selected
      ? 'border-brand-500/30 bg-brand-950 text-brand-400'
      : 'border-transparent text-ink-muted hover:bg-surface-hover hover:text-ink-base'
  }`;

const KBD_CLASS =
  'inline-block min-w-[1.25rem] rounded border border-surface-border bg-surface-base px-1 text-center font-mono text-ink-soft';

interface SegmentationPanelProps {
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
    <div className="space-y-1 max-h-40 overflow-y-auto pr-1">
      {labels
        .filter((label) => label.id !== 0) // Skip background
        .map((label) => {
          const isVisible = labelVisibility[label.id] !== false;
          return (
            <div
              key={label.id}
              role="button"
              tabIndex={0}
              aria-pressed={activeLabel === label.id}
              onClick={() => onSelectLabel(label.id)}
              onKeyDown={(e) => {
                // Ignore keys bubbling up from the visibility toggle inside the row.
                if (e.target !== e.currentTarget) return;
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onSelectLabel(label.id);
                }
              }}
              className={`
                flex items-center gap-2 p-2 rounded-md border cursor-pointer transition-colors group ${FOCUS_RING}
                ${
                  activeLabel === label.id
                    ? 'border-brand-500/30 bg-brand-950 text-ink-base'
                    : 'border-transparent bg-surface-base/60 hover:bg-surface-hover text-ink-soft'
                }
              `}
            >
              {/* Color swatch */}
              <div
                className="w-4 h-4 rounded border border-white/20 flex-shrink-0"
                style={{
                  backgroundColor: label.color,
                  opacity: label.opacity,
                }}
                aria-hidden
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
                  p-1 rounded text-ink-muted transition-opacity hover:bg-surface-hover hover:text-ink-base ${FOCUS_RING}
                  ${isVisible ? 'opacity-100' : 'opacity-50'}
                `}
                title={isVisible ? t('segmentation.hideLabel') : t('segmentation.showLabel')}
                aria-label={isVisible ? t('segmentation.hideLabel') : t('segmentation.showLabel')}
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
              <span className="text-xs tabular-nums text-ink-faint hidden group-hover:inline">#{label.id}</span>
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
      <div className="flex gap-1 rounded-lg border border-surface-border bg-surface-base p-1">
        {tools.map((tool) => (
          <button
            key={tool.id}
            onClick={() => onToolChange(tool.id)}
            className={`
              flex-1 h-8 rounded-md text-xs font-medium flex items-center justify-center gap-1
              ${toggleClass(paintTool === tool.id)}
            `}
            title={tool.label}
            aria-label={tool.label}
            aria-pressed={paintTool === tool.id}
          >
            {tool.icon}
          </button>
        ))}
      </div>

      {/* Brush size */}
      <div>
        <label className="flex items-baseline justify-between text-xs text-ink-soft mb-1.5">
          <span>{t('segmentation.brushSize')}:</span>
          <span className="tabular-nums text-ink-base">{brushSize}×{brushSize} {t('segmentation.voxels')}</span>
        </label>
        <input
          type="range"
          min="1"
          max="30"
          value={brushSize}
          onChange={(e) => onBrushSizeChange(Number(e.target.value))}
          aria-label={t('segmentation.brushSize')}
          className={`w-full h-1.5 bg-surface-hover rounded-full appearance-none cursor-pointer accent-brand-500 ${FOCUS_RING}`}
        />
      </div>

      {/* Brush shape */}
      <div className="flex gap-1 rounded-lg border border-surface-border bg-surface-base p-1">
        <button
          onClick={() => onBrushShapeChange('circle')}
          aria-pressed={brushShape === 'circle'}
          className={`
            flex-1 px-2 py-1 rounded-md text-xs font-medium
            ${toggleClass(brushShape === 'circle')}
          `}
        >
          ○ {t('segmentation.circle')}
        </button>
        <button
          onClick={() => onBrushShapeChange('square')}
          aria-pressed={brushShape === 'square'}
          className={`
            flex-1 px-2 py-1 rounded-md text-xs font-medium
            ${toggleClass(brushShape === 'square')}
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
  onOverlayVisibilityChange,
  onActiveLabelChange,
  onBrushSizeChange,
  onPaintToolChange,
  isLoading: externalLoading = false,
}) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  // Local state
  const [expanded, setExpanded] = useState(true);
  const [activeTab, setActiveTab] = useState<TabType>('load');
  const [newSegmentationName, setNewSegmentationName] = useState('');

  // Viewer store (for file_id, image dimensions, and view mode)
  const currentSeries = useViewerStore((s) => s.currentSeries);
  const fileId = currentSeries?.file_id;
  const currentStudyId = useViewerStore((s) => s.currentStudyId);
  const allFileIds = useViewerStore((s) => s.allFileIds);
  const viewMode = useViewerStore((s) => s.viewMode);
  const is3D = viewMode === '3d';

  // Zustand store
  const {
    activeSegmentation,
    activeLabel,
    labelVisibility,
    paintTool,
    isOverlayVisible,
    isDirty,
    isSaving,
    drawOverMode,
    saveCallback,
    createCallback,
    lesionOpacity,
    zoneMapOpacity,
    zoneMapVisible,
    setActiveLabel,
    toggleLabelVisibility,
    setPaintTool,
    setBrushSize,
    setBrushShape,
    setIsOverlayVisible,
    setDrawOverMode,
    setActiveSegmentation,
    setCurrentSegmentation,
    setLesionOpacity,
    setZoneMapOpacity,
    reset,
  } = useSegmentationStore();

  // Fetch segmentations list for ALL images in the study (same cache key as ViewerApp)
  const { data: segmentationsList, isLoading: isLoadingList } = useQuery({
    queryKey: ['segmentations', 'study', currentStudyId],
    queryFn: () => allFileIds.length > 0
      ? segmentationAPI.listSegmentationsByFileIds(allFileIds)
      : Promise.resolve([]),
    enabled: allFileIds.length > 0,
  });

  // Track local creation state for UI feedback
  const [isCreating, setIsCreating] = useState(false);

  // Delete segmentation via flat API
  const deleteSegmentationMutation = useMutation({
    mutationFn: (segmentationId: string) => segmentationAPI.deleteSegmentation(segmentationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['segmentations', 'study', currentStudyId] });
    },
  });

  // Map SegmentationResponse[] to minimal SegmentationSummary-like objects for the list
  const segmentations = (segmentationsList ?? []).map((seg: SegmentationResponse) => ({
    id: seg.segmentation_id,
    name: seg.metadata?.description || t('segmentation.defaultName', 'Segmentation'),
    status: 'saved' as const,
    progress_percentage: 0,
    slices_annotated: 0,
    total_slices: seg.total_slices,
    created_by: 'current_user',
    created_at: seg.metadata?.created_at || new Date().toISOString(),
    modified_at: seg.metadata?.modified_at || new Date().toISOString(),
    label_count: seg.metadata?.labels?.filter(l => l.id !== 0).length ?? 1,
    primary_label_color: seg.metadata?.labels?.find(l => l.id !== 0)?.color ?? '#FF0000',
  }));

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
  const handleCreateSegmentation = useCallback(() => {
    if (!fileId || !currentSeries || !createCallback) return;
    createCallback(fileId, {
      rows: currentSeries.metadata.rows ?? 256,
      columns: currentSeries.metadata.columns ?? 256,
      slices: currentSeries.total_slices ?? 1,
    });
    setNewSegmentationName('');
    setActiveTab('load');
  }, [fileId, currentSeries, createCallback]);

  const handleLoadSegmentation = useCallback(async (segmentationId: string) => {
    // Load segmentation via API and set as current
    try {
      const seg = await segmentationAPI.getSegmentation(segmentationId);
      setCurrentSegmentation(seg);
    } catch (error) {
      console.error('Failed to load segmentation:', error);
    }
  }, [setCurrentSegmentation]);

  const handleDeleteSegmentation = useCallback(async (segmentationId: string) => {
    try {
      await deleteSegmentationMutation.mutateAsync(segmentationId);
    } catch (error) {
      console.error('Failed to delete segmentation:', error);
    }
  }, [deleteSegmentationMutation]);

  const handleSaveSegmentation = useCallback(async () => {
    if (!saveCallback) return;
    try {
      await saveCallback();
    } catch (error) {
      console.error('Failed to save segmentation:', error);
    }
  }, [saveCallback]);

  const handleCloseSegmentation = useCallback(async () => {
    if (!activeSegmentation) return;

    // Warn about unsaved changes
    if (isDirty) {
      const shouldSave = window.confirm(t('segmentation.unsavedChanges'));
      if (shouldSave) {
        await handleSaveSegmentation();
      }
    }

    // Clear current segmentation (useSegmentationData will unload the mask)
    setCurrentSegmentation(null);
    reset();
    setActiveSegmentation(null);
  }, [activeSegmentation, isDirty, handleSaveSegmentation, setCurrentSegmentation, reset, setActiveSegmentation, t]);

  // Keep the active tab valid as the mask comes and goes. When a mask becomes active,
  // move off the Open/New tabs (which hide) to the Paint (edit) tab; when it closes, move
  // off Paint back to Open. 'tools' persists across both states — auto-segmentation is
  // always reachable and we never yank a user out of the Tools panel.
  useEffect(() => {
    if (activeSegmentation) {
      setActiveTab((prev) => (prev === 'load' || prev === 'new') ? 'paint' : prev);
    } else {
      setActiveTab((prev) => (prev === 'paint') ? 'load' : prev);
    }
  }, [activeSegmentation]);

  // Derived state
  const isLoading = externalLoading || isLoadingList || isCreating;
  const hasContext = !!fileId;

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
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
          </svg>
          {t('segmentation.manualSegmentation')}
          {segmentations.length > 0 && (
            <Badge tone="brand" className="ml-1 px-1.5 text-xs tabular-nums">
              {segmentations.length}
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
          {/* No context warning */}
          {!hasContext && (
            <div className="text-center py-4 text-ink-muted">
              <svg
                className="w-8 h-8 mx-auto mb-2 text-ink-faint"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <p className="text-xs">{t('segmentation.selectImageFirst')}</p>
            </div>
          )}

          {/* Tab strip — always visible when a study is loaded. Open/New show only when
              no mask is active; Edit shows only when one is; Tools is ALWAYS available so
              auto-segmentation no longer vanishes the moment a mask becomes active. */}
          {hasContext && (
            <>
              {/* Tab Headers */}
              <div className="flex gap-1 rounded-lg border border-surface-border bg-surface-base p-1">
                {!activeSegmentation && (
                <button
                  onClick={() => setActiveTab('load')}
                  aria-pressed={activeTab === 'load'}
                  className={`flex-1 px-2 py-1.5 rounded-md text-xs font-medium tabular-nums ${toggleClass(activeTab === 'load')}`}
                >
                  {t('segmentation.open')} ({segmentations.length})
                </button>
                )}
                {!activeSegmentation && !is3D && (
                <button
                  onClick={() => setActiveTab('new')}
                  aria-pressed={activeTab === 'new'}
                  className={`flex-1 px-2 py-1.5 rounded-md text-xs font-medium ${toggleClass(activeTab === 'new')}`}
                >
                  {t('segmentation.new')}
                </button>
                )}
                {activeSegmentation && (
                <button
                  onClick={() => setActiveTab('paint')}
                  aria-pressed={activeTab === 'paint'}
                  className={`flex-1 px-2 py-1.5 rounded-md text-xs font-medium ${toggleClass(activeTab === 'paint')}`}
                >
                  {t('segmentation.edit', 'Edit')}
                </button>
                )}
                <button
                  onClick={() => setActiveTab('tools')}
                  aria-pressed={activeTab === 'tools'}
                  className={`flex-1 px-2 py-1.5 rounded-md text-xs font-medium ${toggleClass(activeTab === 'tools')}`}
                >
                  {t('clinical.tools', 'Tools')}
                </button>
              </div>

              {/* Tab Content (load/new/tools; the paint tab renders in the block below,
                  so this container collapses on 'paint' to avoid an empty gap). */}
              <div className={activeTab === 'paint' ? undefined : 'min-h-[200px]'}>
                {!activeSegmentation && activeTab === 'load' && (
                  <SegmentationList
                    segmentations={segmentations}
                    onLoad={handleLoadSegmentation}
                    onDelete={handleDeleteSegmentation}
                    activeSegmentationId={(activeSegmentation as Segmentation | null)?.id}
                    isLoading={isLoading}
                    isDeleting={deleteSegmentationMutation.isPending}
                  />
                )}

                {!activeSegmentation && activeTab === 'new' && (
                  <div className="py-3 space-y-3">
                    {/* Name input */}
                    <Input
                      type="text"
                      label={t('segmentation.name')}
                      value={newSegmentationName}
                      onChange={(e) => setNewSegmentationName(e.target.value)}
                      placeholder={t('segmentation.namePlaceholder')}
                      className="h-8 rounded-md"
                    />

                    {/* Create button */}
                    <Button
                      variant="primary"
                      size="sm"
                      fullWidth
                      onClick={handleCreateSegmentation}
                      disabled={!createCallback}
                      leftIcon={<Plus className="h-4 w-4" aria-hidden />}
                    >
                      {t('segmentation.newSegmentation')}
                    </Button>

                    <p className="text-xs text-ink-muted text-center">
                      {t('segmentation.createNewEmpty')}
                    </p>
                  </div>
                )}

                {activeTab === 'tools' && (
                  <div className="space-y-3">
                    <ClinicalToolsPanel fileId={fileId} />
                    <div className="border-t border-surface-border pt-3">
                      <ConformalPanel />
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {/* Active segmentation - paint/edit controls (the 'paint' tab; the tab strip
              above stays visible so Tools/auto-seg remain reachable while editing) */}
          {activeSegmentation && activeTab === 'paint' && (
            <>
              {/* Segmentation info header */}
              <div className="rounded-lg border border-surface-border bg-surface-base/60 p-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-ink-base truncate">
                        {activeSegmentation.name}
                      </p>
                      {isDirty && (
                        <span className="text-xs text-clinical-warn" title={t('segmentation.unsavedChanges')}>
                          •
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-ink-muted flex items-center gap-1">
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                      {activeSegmentation.created_by_name || activeSegmentation.created_by}
                    </p>
                  </div>
                  <button
                    onClick={handleCloseSegmentation}
                    className={`ml-2 rounded-md p-1 text-ink-muted transition-colors hover:bg-surface-hover hover:text-ink-base ${FOCUS_RING}`}
                    title={t('segmentation.closeSegmentation')}
                    aria-label={t('segmentation.closeSegmentation')}
                  >
                    <X className="h-4 w-4" aria-hidden />
                  </button>
                </div>

                {/* Progress bar */}
                <div className="mt-2">
                  <div className="flex justify-between text-xs text-ink-muted mb-1">
                    <span>{t('segmentation.progress.annotated')}</span>
                    <span className="tabular-nums">
                      {activeSegmentation.slices_annotated}/{activeSegmentation.total_slices} (
                      {activeSegmentation.progress_percentage}%)
                    </span>
                  </div>
                  <div className="h-1.5 bg-surface-hover rounded-full overflow-hidden">
                    <div
                      className="h-full bg-brand-500 transition-all duration-300"
                      style={{ width: `${activeSegmentation.progress_percentage}%` }}
                    />
                  </div>
                  {activeSegmentation.slices_annotated === 0 && activeSegmentation.total_slices > 0 && !activeSegmentation.id.startsWith('local-') && (
                    <p className="text-xs text-clinical-warn mt-1.5">
                      {t('segmentation.emptyMask', 'Mask is empty — no annotated voxels found')}
                    </p>
                  )}
                </div>
              </div>

              {/* Labels and preset are shown inline in the segmentation list item (OverlayControls) */}

              {/* Paint Tools — 2D only (painting not supported in 3D) */}
              {!is3D && (
              <div className="border-t border-surface-border pt-3">
                <label className="block text-xs font-medium uppercase tracking-wide text-ink-faint mb-2">{t('segmentation.paintTools')}</label>
                <PaintToolbar
                  paintTool={paintTool.tool}
                  brushSize={paintTool.brushSize}
                  brushShape={paintTool.brushShape}
                  onToolChange={setPaintTool}
                  onBrushSizeChange={setBrushSize}
                  onBrushShapeChange={setBrushShape}
                />
              </div>
              )}

              {/* Draw-Over Mode — 2D only */}
              {!is3D && (
              <div>
                <label className="block text-xs text-ink-soft mb-1">
                  {t('segmentation.drawOver', 'Draw Over')}
                </label>
                <select
                  value={drawOverMode}
                  onChange={(e) => setDrawOverMode(e.target.value as DrawOverMode)}
                  aria-label={t('segmentation.drawOver', 'Draw Over')}
                  className={`w-full h-8 px-2 rounded-md border border-surface-border bg-surface-base text-xs text-ink-base transition-colors hover:border-surface-hover ${FOCUS_RING}`}
                >
                  <option value="all">{t('segmentation.drawOverAll', 'All labels')}</option>
                  <option value="emptyOnly">{t('segmentation.drawOverEmpty', 'Empty only')}</option>
                  <option value="activeLabel">{t('segmentation.drawOverActive', 'Active label only')}</option>
                </select>
              </div>
              )}

              {/* Save Button — 2D only */}
              {!is3D && (
              <Button
                variant="primary"
                size="sm"
                fullWidth
                onClick={handleSaveSegmentation}
                disabled={isSaving || !isDirty}
                aria-busy={isSaving || undefined}
                leftIcon={isSaving ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                  </svg>
                )}
              >
                {isSaving ? t('segmentation.saving') : t('segmentation.saveSegmentation')}
              </Button>
              )}

              {/* Instructions & Shortcuts — 2D only */}
              {!is3D && (
              <div className="pt-3 border-t border-surface-border space-y-2">
                <p className="text-xs leading-relaxed text-ink-muted">
                  <strong className="font-medium text-ink-soft">{t('segmentation.instructions.title')}</strong>
                  <br />• {t('segmentation.instructions.clickDrag')}
                  <br />• {t('segmentation.instructions.selectLabel')}
                  <br />• {t('segmentation.instructions.adjustBrush')}
                  <br />• {t('segmentation.instructions.eraseMode')}
                </p>
                <details className="text-xs text-ink-muted">
                  <summary className={`cursor-pointer rounded font-medium hover:text-ink-soft ${FOCUS_RING}`}>
                    {t('segmentation.shortcuts.title', 'Keyboard shortcuts')}
                  </summary>
                  <div className="mt-1.5 space-y-1 pl-2">
                    <p><kbd className={KBD_CLASS}>Ctrl+Z</kbd> {t('segmentation.shortcuts.undo', 'Undo')}</p>
                    <p><kbd className={KBD_CLASS}>Ctrl+Y</kbd> {t('segmentation.shortcuts.redo', 'Redo')}</p>
                    <p><kbd className={KBD_CLASS}>E</kbd> {t('segmentation.shortcuts.toggleEraser', 'Toggle eraser')}</p>
                    <p><kbd className={KBD_CLASS}>B</kbd> {t('segmentation.shortcuts.brush', 'Brush')}</p>
                    <p><kbd className={KBD_CLASS}>S</kbd> {t('segmentation.shortcuts.toggleOverlay', 'Toggle overlay')}</p>
                    <p><kbd className={KBD_CLASS}>+</kbd> / <kbd className={KBD_CLASS}>-</kbd> {t('segmentation.shortcuts.brushSize', 'Brush size')}</p>
                    <p><kbd className={KBD_CLASS}>1-9</kbd> {t('segmentation.shortcuts.selectLabel', 'Select label')}</p>
                  </div>
                </details>
              </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default SegmentationPanel;
