import React from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import {
  FileText,
  FileImage,
  File,
  Eye,
  Download,
  Edit2,
  Trash2,
  Clock,
  History,
  MoreVertical,
  CheckCircle2,
  XCircle,
  AlertCircle,
} from 'lucide-react';
import type { Document, DocumentSummary, DocumentCategory, DocumentStatus } from '@/types';
import { documentAPI } from '@/services/documentApi';

interface DocumentCardProps {
  document: Document | DocumentSummary;
  compact?: boolean;
  onView?: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
  onDownload?: () => void;
  onViewVersions?: () => void;
  showPatient?: boolean;
}

// Category colors and icons
const getCategoryInfo = (category: DocumentCategory) => {
  const categoryMap: Record<DocumentCategory, { color: string; bgColor: string; icon: React.ReactNode }> = {
    'lab-result': {
      color: 'text-green-600 dark:text-green-400',
      bgColor: 'bg-green-100 dark:bg-green-900/30',
      icon: <FileText className="w-4 h-4" />,
    },
    'prescription': {
      color: 'text-blue-600 dark:text-blue-400',
      bgColor: 'bg-blue-100 dark:bg-blue-900/30',
      icon: <FileText className="w-4 h-4" />,
    },
    'clinical-note': {
      color: 'text-purple-600 dark:text-purple-400',
      bgColor: 'bg-purple-100 dark:bg-purple-900/30',
      icon: <FileText className="w-4 h-4" />,
    },
    'discharge-summary': {
      color: 'text-orange-600 dark:text-orange-400',
      bgColor: 'bg-orange-100 dark:bg-orange-900/30',
      icon: <FileText className="w-4 h-4" />,
    },
    'radiology-report': {
      color: 'text-cyan-600 dark:text-cyan-400',
      bgColor: 'bg-cyan-100 dark:bg-cyan-900/30',
      icon: <FileImage className="w-4 h-4" />,
    },
    'consent-form': {
      color: 'text-yellow-600 dark:text-yellow-400',
      bgColor: 'bg-yellow-100 dark:bg-yellow-900/30',
      icon: <FileText className="w-4 h-4" />,
    },
    'referral': {
      color: 'text-indigo-600 dark:text-indigo-400',
      bgColor: 'bg-indigo-100 dark:bg-indigo-900/30',
      icon: <FileText className="w-4 h-4" />,
    },
    'operative-note': {
      color: 'text-red-600 dark:text-red-400',
      bgColor: 'bg-red-100 dark:bg-red-900/30',
      icon: <FileText className="w-4 h-4" />,
    },
    'pathology-report': {
      color: 'text-pink-600 dark:text-pink-400',
      bgColor: 'bg-pink-100 dark:bg-pink-900/30',
      icon: <FileText className="w-4 h-4" />,
    },
    'other': {
      color: 'text-gray-600 dark:text-gray-400',
      bgColor: 'bg-gray-100 dark:bg-gray-900/30',
      icon: <File className="w-4 h-4" />,
    },
  };
  return categoryMap[category] || categoryMap['other'];
};

// Status badge styles
const getStatusBadge = (status: DocumentStatus) => {
  const statusMap: Record<DocumentStatus, { color: string; bgColor: string; icon: React.ReactNode }> = {
    'current': {
      color: 'text-green-600 dark:text-green-400',
      bgColor: 'bg-green-100 dark:bg-green-900/30',
      icon: <CheckCircle2 className="w-3.5 h-3.5" />,
    },
    'superseded': {
      color: 'text-yellow-600 dark:text-yellow-400',
      bgColor: 'bg-yellow-100 dark:bg-yellow-900/30',
      icon: <AlertCircle className="w-3.5 h-3.5" />,
    },
    'entered-in-error': {
      color: 'text-red-600 dark:text-red-400',
      bgColor: 'bg-red-100 dark:bg-red-900/30',
      icon: <XCircle className="w-3.5 h-3.5" />,
    },
  };
  return statusMap[status] || statusMap['current'];
};

// Get file type icon
const getFileIcon = (contentType: string) => {
  if (contentType.startsWith('image/')) {
    return <FileImage className="w-8 h-8" />;
  }
  if (contentType === 'application/pdf') {
    return <FileText className="w-8 h-8 text-red-500" />;
  }
  if (contentType.includes('word') || contentType.includes('document')) {
    return <FileText className="w-8 h-8 text-blue-500" />;
  }
  return <File className="w-8 h-8" />;
};

export const DocumentCard: React.FC<DocumentCardProps> = ({
  document,
  compact = false,
  onView,
  onEdit,
  onDelete,
  onDownload,
  onViewVersions,
}) => {
  const { t } = useTranslation();
  const [showMenu, setShowMenu] = React.useState(false);
  const menuRef = React.useRef<HTMLDivElement>(null);

  const categoryInfo = getCategoryInfo(document.category);
  const statusBadge = getStatusBadge(document.status);

  // Format date
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  // Close menu when clicking outside
  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowMenu(false);
      }
    };
    window.document.addEventListener('mousedown', handleClickOutside);
    return () => window.document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Compact view (for list mode)
  if (compact) {
    return (
      <motion.div
        layout
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        className="flex items-center gap-4 p-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 hover:shadow-md transition-shadow"
      >
        {/* File icon */}
        <div className={`p-2 rounded-lg ${categoryInfo.bgColor}`}>
          {getFileIcon(document.content_type)}
        </div>

        {/* Document info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-medium text-gray-900 dark:text-gray-100 truncate">
              {document.title}
            </h3>
            <span
              className={`px-2 py-0.5 text-xs font-medium rounded-full ${categoryInfo.bgColor} ${categoryInfo.color}`}
            >
              {t(`document.categories.${document.category}`)}
            </span>
          </div>
          <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
            <span className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" />
              {formatDate(document.document_date)}
            </span>
            <span>{documentAPI.formatFileSize(document.file_size_bytes)}</span>
            {document.version > 1 && (
              <span className="flex items-center gap-1">
                <History className="w-3.5 h-3.5" />
                v{document.version}
              </span>
            )}
          </div>
        </div>

        {/* Status badge */}
        <span
          className={`flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full ${statusBadge.bgColor} ${statusBadge.color}`}
        >
          {statusBadge.icon}
          {t(`document.status.${document.status}`)}
        </span>

        {/* Actions */}
        <div className="flex items-center gap-1">
          {onView && (
            <button
              onClick={onView}
              className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
              title={t('common.view')}
            >
              <Eye className="w-4 h-4" />
            </button>
          )}
          {onDownload && (
            <button
              onClick={onDownload}
              className="p-2 text-gray-500 hover:text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 rounded-lg transition-colors"
              title={t('common.download')}
            >
              <Download className="w-4 h-4" />
            </button>
          )}
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setShowMenu(!showMenu)}
              className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              <MoreVertical className="w-4 h-4" />
            </button>
            {showMenu && (
              <div className="absolute right-0 top-full mt-1 w-48 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1 z-10">
                {onViewVersions && (
                  <button
                    onClick={() => {
                      setShowMenu(false);
                      onViewVersions();
                    }}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                  >
                    <History className="w-4 h-4" />
                    {t('document.viewVersions')}
                  </button>
                )}
                {onEdit && (
                  <button
                    onClick={() => {
                      setShowMenu(false);
                      onEdit();
                    }}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                  >
                    <Edit2 className="w-4 h-4" />
                    {t('common.edit')}
                  </button>
                )}
                {onDelete && (
                  <button
                    onClick={() => {
                      setShowMenu(false);
                      onDelete();
                    }}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                  >
                    <Trash2 className="w-4 h-4" />
                    {t('common.delete')}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </motion.div>
    );
  }

  // Full card view (for grid mode)
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden hover:shadow-lg transition-shadow"
    >
      {/* Header with category badge */}
      <div className={`p-4 ${categoryInfo.bgColor}`}>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-sm">
              {getFileIcon(document.content_type)}
            </div>
            <div>
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-white dark:bg-gray-800 ${categoryInfo.color}`}
              >
                {categoryInfo.icon}
                {t(`document.categories.${document.category}`)}
              </span>
            </div>
          </div>
          <span
            className={`flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full ${statusBadge.bgColor} ${statusBadge.color}`}
          >
            {statusBadge.icon}
            {t(`document.status.${document.status}`)}
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1 truncate">
          {document.title}
        </h3>

        {'description' in document && document.description && (
          <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2 mb-3">
            {document.description}
          </p>
        )}

        {/* Meta info */}
        <div className="space-y-2 text-sm text-gray-500 dark:text-gray-400">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4" />
            <span>{formatDate(document.document_date)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>{documentAPI.formatFileSize(document.file_size_bytes)}</span>
            {document.version > 1 && (
              <span className="flex items-center gap-1 text-blue-600 dark:text-blue-400">
                <History className="w-3.5 h-3.5" />
                v{document.version}
              </span>
            )}
          </div>
        </div>

        {'author_name' in document && document.author_name && (
          <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {t('document.author')}: {document.author_name}
            </span>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800/50 border-t border-gray-100 dark:border-gray-700 flex items-center justify-end gap-2">
        {onViewVersions && document.version > 1 && (
          <button
            onClick={onViewVersions}
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            <History className="w-4 h-4" />
            {t('document.versions')}
          </button>
        )}
        {onDownload && (
          <button
            onClick={onDownload}
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 rounded-lg transition-colors"
          >
            <Download className="w-4 h-4" />
            {t('common.download')}
          </button>
        )}
        {onView && (
          <button
            onClick={onView}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
          >
            <Eye className="w-4 h-4" />
            {t('common.view')}
          </button>
        )}
      </div>
    </motion.div>
  );
};

export default DocumentCard;
