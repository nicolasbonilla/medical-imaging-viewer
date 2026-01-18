/**
 * SegmentationList - ITK-SNAP Style Segmentation List Component.
 *
 * Displays available segmentations with:
 * - Status indicators (draft, in_progress, pending_review, approved)
 * - Multi-expert authorship information
 * - Progress tracking
 * - Label preview colors
 *
 * @module components/SegmentationList
 */

import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { SegmentationSummary, SegmentationStatus } from '@/types';

// ============================================================================
// Types
// ============================================================================

interface SegmentationListProps {
  /** List of segmentation summaries */
  segmentations: SegmentationSummary[];
  /** Callback when a segmentation is selected to load */
  onLoad: (segmentationId: string) => void;
  /** Callback when a segmentation is deleted */
  onDelete: (segmentationId: string) => void;
  /** Currently selected/active segmentation ID */
  activeSegmentationId?: string;
  /** Loading state */
  isLoading?: boolean;
  /** Delete in progress */
  isDeleting?: boolean;
  /** Show compact view */
  compact?: boolean;
}

// ============================================================================
// Status Configuration
// ============================================================================

interface StatusConfig {
  label: string;
  color: string;
  bgColor: string;
  icon: React.ReactNode;
}

const getStatusConfig = (status: SegmentationStatus, t: (key: string) => string): StatusConfig => {
  const configs: Record<SegmentationStatus, StatusConfig> = {
    draft: {
      label: t('segmentation.status.draft'),
      color: 'text-gray-400',
      bgColor: 'bg-gray-500/20',
      icon: (
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
        </svg>
      ),
    },
    in_progress: {
      label: t('segmentation.status.inProgress'),
      color: 'text-blue-400',
      bgColor: 'bg-blue-500/20',
      icon: (
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    pending_review: {
      label: t('segmentation.status.pendingReview'),
      color: 'text-yellow-400',
      bgColor: 'bg-yellow-500/20',
      icon: (
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
        </svg>
      ),
    },
    reviewed: {
      label: t('segmentation.status.reviewed'),
      color: 'text-purple-400',
      bgColor: 'bg-purple-500/20',
      icon: (
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    approved: {
      label: t('segmentation.status.approved'),
      color: 'text-green-400',
      bgColor: 'bg-green-500/20',
      icon: (
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      ),
    },
    archived: {
      label: t('segmentation.status.archived'),
      color: 'text-gray-500',
      bgColor: 'bg-gray-600/20',
      icon: (
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
        </svg>
      ),
    },
  };

  return configs[status] || configs.draft;
};

// ============================================================================
// Sub-Components
// ============================================================================

interface StatusBadgeProps {
  status: SegmentationStatus;
}

const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const { t } = useTranslation();
  const config = getStatusConfig(status, t);

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${config.bgColor} ${config.color}`}
    >
      {config.icon}
      <span>{config.label}</span>
    </span>
  );
};

interface ProgressBarProps {
  percentage: number;
  annotated: number;
  total: number;
}

const ProgressBar: React.FC<ProgressBarProps> = ({ percentage, annotated, total }) => {
  const { t } = useTranslation();

  return (
    <div className="w-full">
      <div className="flex justify-between text-xs text-gray-400 mb-1">
        <span>{t('segmentation.progress.annotated')}</span>
        <span>
          {annotated}/{total} ({percentage}%)
        </span>
      </div>
      <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-blue-500 to-blue-400 transition-all duration-300"
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};

// ============================================================================
// Main Component
// ============================================================================

export const SegmentationList: React.FC<SegmentationListProps> = ({
  segmentations,
  onLoad,
  onDelete,
  activeSegmentationId,
  isLoading = false,
  isDeleting = false,
  compact = false,
}) => {
  const { t, i18n } = useTranslation();

  // Sort segmentations: in_progress first, then by modified date
  const sortedSegmentations = useMemo(() => {
    return [...segmentations].sort((a, b) => {
      // Active first
      if (a.id === activeSegmentationId) return -1;
      if (b.id === activeSegmentationId) return 1;
      // In progress second
      if (a.status === 'in_progress' && b.status !== 'in_progress') return -1;
      if (b.status === 'in_progress' && a.status !== 'in_progress') return 1;
      // Then by modified date
      return new Date(b.modified_at).getTime() - new Date(a.modified_at).getTime();
    });
  }, [segmentations, activeSegmentationId]);

  const formatDate = (dateString: string) => {
    if (!dateString) return t('segmentation.list.unknownDate');

    const date = new Date(dateString);
    if (isNaN(date.getTime())) {
      return t('segmentation.list.invalidDate');
    }

    const localeMap: Record<string, string> = {
      en: 'en-US',
      es: 'es-ES',
      de: 'de-DE',
    };
    const locale = localeMap[i18n.language] || 'en-US';
    return new Intl.DateTimeFormat(locale, {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);
  };

  const formatRelativeTime = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return t('segmentation.time.justNow');
    if (diffMins < 60) return t('segmentation.time.minutesAgo', { count: diffMins });
    if (diffHours < 24) return t('segmentation.time.hoursAgo', { count: diffHours });
    if (diffDays < 7) return t('segmentation.time.daysAgo', { count: diffDays });
    return formatDate(dateString);
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  // Empty state
  if (!segmentations || segmentations.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400">
        <svg
          className="w-12 h-12 mx-auto mb-3 text-gray-600"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
          />
        </svg>
        <p className="text-sm">{t('segmentation.list.noPrevious')}</p>
        <p className="text-xs mt-1 text-gray-500">{t('segmentation.list.createToStart')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-2 max-h-[400px] overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-gray-600 scrollbar-track-gray-800">
      {sortedSegmentations.map((seg) => {
        const isActive = seg.id === activeSegmentationId;

        return (
          <div
            key={seg.id}
            className={`
              rounded-lg p-3 transition-all cursor-pointer group
              ${isActive
                ? 'bg-blue-600/20 border border-blue-500/50 ring-1 ring-blue-500/30'
                : 'bg-gray-700/50 hover:bg-gray-700 border border-transparent'
              }
            `}
            onClick={() => !isActive && onLoad(seg.id)}
          >
            {/* Header Row */}
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex-1 min-w-0">
                <h4 className="text-sm font-medium text-white truncate flex items-center gap-2">
                  {/* Color indicator */}
                  <span
                    className="w-3 h-3 rounded-sm flex-shrink-0 border border-white/20"
                    style={{ backgroundColor: seg.primary_label_color }}
                  />
                  {seg.name}
                </h4>
                <p className="text-xs text-gray-400 mt-0.5 flex items-center gap-1">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                  {seg.created_by_name || seg.created_by}
                </p>
              </div>
              <StatusBadge status={seg.status} />
            </div>

            {/* Progress */}
            {!compact && (
              <div className="mb-3">
                <ProgressBar
                  percentage={seg.progress_percentage}
                  annotated={seg.slices_annotated}
                  total={seg.total_slices}
                />
              </div>
            )}

            {/* Metadata Row */}
            <div className="flex items-center justify-between text-xs text-gray-400">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                  </svg>
                  {seg.label_count} {seg.label_count === 1 ? t('segmentation.list.label') : t('segmentation.list.labels')}
                </span>
                {compact && (
                  <span>{seg.progress_percentage}%</span>
                )}
              </div>
              <span title={formatDate(seg.modified_at)}>
                {formatRelativeTime(seg.modified_at)}
              </span>
            </div>

            {/* Actions (visible on hover or when active) */}
            <div className={`
              mt-3 flex items-center gap-2 transition-opacity
              ${isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}
            `}>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onLoad(seg.id);
                }}
                disabled={isDeleting || isActive}
                className={`
                  flex-1 px-3 py-1.5 rounded text-xs font-medium transition-colors
                  ${isActive
                    ? 'bg-blue-600 text-white cursor-default'
                    : 'bg-blue-600 hover:bg-blue-700 text-white'
                  }
                  disabled:bg-gray-600 disabled:cursor-not-allowed
                `}
              >
                {isActive ? t('segmentation.list.active') : t('segmentation.list.open')}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (window.confirm(t('segmentation.list.confirmDelete'))) {
                    onDelete(seg.id);
                  }
                }}
                disabled={isDeleting}
                className="px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 disabled:bg-gray-600 disabled:cursor-not-allowed text-red-400 hover:text-red-300 rounded text-xs font-medium transition-colors"
                aria-label={t('segmentation.list.delete')}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
};

// ============================================================================
// Compact List Item (for inline display in other components)
// ============================================================================

interface SegmentationListItemCompactProps {
  segmentation: SegmentationSummary;
  onSelect: (id: string) => void;
  isSelected?: boolean;
}

export const SegmentationListItemCompact: React.FC<SegmentationListItemCompactProps> = ({
  segmentation,
  onSelect,
  isSelected = false,
}) => {
  const { t } = useTranslation();
  const statusConfig = getStatusConfig(segmentation.status, t);

  return (
    <button
      onClick={() => onSelect(segmentation.id)}
      className={`
        w-full flex items-center gap-2 px-2 py-1.5 rounded text-left transition-colors
        ${isSelected
          ? 'bg-blue-600/30 text-white'
          : 'hover:bg-gray-700 text-gray-300'
        }
      `}
    >
      <span
        className="w-2 h-2 rounded-full flex-shrink-0"
        style={{ backgroundColor: segmentation.primary_label_color }}
      />
      <span className="flex-1 truncate text-sm">{segmentation.name}</span>
      <span className={`text-xs ${statusConfig.color}`}>
        {segmentation.progress_percentage}%
      </span>
    </button>
  );
};

export default SegmentationList;
