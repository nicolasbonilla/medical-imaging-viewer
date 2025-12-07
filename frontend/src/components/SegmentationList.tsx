/**
 * Segmentation list component
 * Displays available segmentations with metadata
 */

import React from 'react';
import { useTranslation } from 'react-i18next';
import type { SegmentationListItem } from '@/types/segmentation';

interface SegmentationListProps {
  segmentations: SegmentationListItem[];
  onLoad: (segmentationId: string) => void;
  onDelete: (segmentationId: string) => void;
  isLoading?: boolean;
  isDeleting?: boolean;
}

export const SegmentationList: React.FC<SegmentationListProps> = ({
  segmentations,
  onLoad,
  onDelete,
  isLoading = false,
  isDeleting = false,
}) => {
  const { t, i18n } = useTranslation();

  const formatDate = (dateString: string) => {
    if (!dateString) return t('segmentation.list.unknownDate');

    const date = new Date(dateString);
    if (isNaN(date.getTime())) {
      return t('segmentation.list.invalidDate');
    }

    // Use current language for date formatting
    const localeMap: Record<string, string> = {
      'en': 'en-US',
      'es': 'es-ES',
      'de': 'de-DE',
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (!segmentations || segmentations.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400 text-sm">
        <p>{t('segmentation.list.noPrevious')}</p>
        <p className="text-xs mt-1">{t('segmentation.list.createToStart')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-2 max-h-64 overflow-y-auto">
      {segmentations.map((seg) => (
        <div
          key={seg.segmentation_id}
          className="bg-gray-700 rounded p-3 hover:bg-gray-600 transition-colors group"
        >
          {/* Header */}
          <div className="flex items-start justify-between mb-2">
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-medium text-white truncate">
                {seg.description || t('segmentation.list.noDescription')}
              </h4>
              <p className="text-xs text-gray-400 mt-0.5">
                {t('segmentation.list.modified')}: {formatDate(seg.modified_at)}
              </p>
            </div>
          </div>

          {/* Metadata */}
          <div className="flex items-center gap-3 text-xs text-gray-300 mb-2">
            <span className="flex items-center gap-1">
              <svg
                className="w-3 h-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"
                />
              </svg>
              {seg.label_count} {seg.label_count === 1 ? t('segmentation.list.label') : t('segmentation.list.labels')}
            </span>
            <span className="flex items-center gap-1">
              <svg
                className="w-3 h-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                />
              </svg>
              {seg.total_slices} {t('segmentation.list.slices')}
            </span>
          </div>

          {/* Labels preview */}
          <div className="flex items-center gap-1 mb-3">
            {seg.labels && Array.isArray(seg.labels) ? (
              <>
                {seg.labels
                  .filter((l) => l.id !== 0)
                  .slice(0, 5)
                  .map((label) => (
                    <div
                      key={label.id}
                      className="w-3 h-3 rounded border border-gray-500"
                      style={{ backgroundColor: label.color }}
                      title={label.name}
                    />
                  ))}
                {seg.label_count > 5 && (
                  <span className="text-xs text-gray-400">
                    +{seg.label_count - 5}
                  </span>
                )}
              </>
            ) : (
              <span className="text-xs text-gray-400">{t('segmentation.list.noLabels')}</span>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => onLoad(seg.segmentation_id)}
              disabled={isDeleting}
              className="flex-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-xs font-medium transition-colors"
            >
              {t('segmentation.list.open')}
            </button>
            <button
              onClick={() => {
                if (
                  window.confirm(
                    t('segmentation.list.confirmDelete')
                  )
                ) {
                  onDelete(seg.segmentation_id);
                }
              }}
              disabled={isDeleting}
              className="px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 disabled:bg-gray-600 disabled:cursor-not-allowed text-red-400 hover:text-red-300 rounded text-xs font-medium transition-colors"
            >
              {t('segmentation.list.delete')}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};
