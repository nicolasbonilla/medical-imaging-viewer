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
} from 'lucide-react';
import type { Document, DocumentSummary, DocumentCategory, DocumentStatus } from '@/types';
import { documentAPI } from '@/services/documentApi';

// Category colors — inline, dark-first
const categoryColors: Record<DocumentCategory, { bg: string; color: string }> = {
  'clinical-note': { bg: 'rgba(139,92,246,0.15)', color: '#A78BFA' },
  'radiology-report': { bg: 'rgba(6,182,212,0.15)', color: '#22D3EE' },
  'ms-assessment': { bg: 'rgba(59,130,246,0.15)', color: '#60A5FA' },
  'other': { bg: 'rgba(107,114,128,0.15)', color: '#9CA3AF' },
};

const statusColors: Record<DocumentStatus, { bg: string; color: string }> = {
  'current': { bg: 'rgba(16,185,129,0.12)', color: '#34D399' },
  'superseded': { bg: 'rgba(234,179,8,0.12)', color: '#FACC15' },
  'entered-in-error': { bg: 'rgba(239,68,68,0.12)', color: '#F87171' },
};

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
  const cat = categoryColors[document.category] || categoryColors['other'];
  const stat = statusColors[document.status] || statusColors['current'];

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  };

  const CategoryIcon = () => {
    if (document.category === 'radiology-report') return <FileImage style={{ width: 16, height: 16 }} />;
    if (document.category === 'other') return <File style={{ width: 16, height: 16 }} />;
    return <FileText style={{ width: 16, height: 16 }} />;
  };

  // ==================== COMPACT / LIST VIEW ====================
  if (compact) {
    return (
      <motion.div
        layout
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        onClick={onView}
        className="group border border-gray-700 hover:border-gray-600 transition-colors"
        style={{ background: '#1F2937', borderRadius: 8, padding: 12, cursor: onView ? 'pointer' : 'default', display: 'flex', alignItems: 'center', gap: 12 }}
      >
        {/* Category icon — 36×36 */}
        <div className="flex-shrink-0 flex items-center justify-center"
          style={{ width: 36, height: 36, borderRadius: 6, background: cat.bg, color: cat.color }}>
          <CategoryIcon />
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center" style={{ gap: 6 }}>
            <span className="truncate" style={{ fontSize: 14, fontWeight: 600, color: '#F9FAFB' }}>
              {document.title}
            </span>
            <span style={{ fontSize: 11, fontWeight: 500, padding: '1px 6px', borderRadius: 4, background: stat.bg, color: stat.color, flexShrink: 0 }}>
              {t(`document.status.${document.status}`)}
            </span>
          </div>
          <div className="flex items-center" style={{ gap: 8, marginTop: 2 }}>
            <span className="flex items-center" style={{ gap: 4, fontSize: 12, color: '#9CA3AF' }}>
              <Clock style={{ width: 12, height: 12 }} />
              {formatDate(document.document_date)}
            </span>
            <span style={{ color: '#374151' }}>·</span>
            <span style={{ fontSize: 12, color: '#9CA3AF' }}>{documentAPI.formatFileSize(document.file_size_bytes)}</span>
            {document.version > 1 && (
              <>
                <span style={{ color: '#374151' }}>·</span>
                <span style={{ fontSize: 12, color: '#9CA3AF' }}>v{document.version}</span>
              </>
            )}
          </div>
        </div>

        {/* Actions — 28×28 */}
        <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity" style={{ gap: 4 }}>
          {onDownload && (
            <button onClick={(e) => { e.stopPropagation(); onDownload(); }}
              className="flex items-center justify-center hover:bg-gray-700 transition-colors"
              style={{ width: 28, height: 28, borderRadius: 6 }} title={t('common.download')}>
              <Download style={{ width: 14, height: 14, color: '#9CA3AF' }} />
            </button>
          )}
          {onEdit && (
            <button onClick={(e) => { e.stopPropagation(); onEdit(); }}
              className="flex items-center justify-center hover:bg-gray-700 transition-colors"
              style={{ width: 28, height: 28, borderRadius: 6 }} title={t('common.edit')}>
              <Edit2 style={{ width: 14, height: 14, color: '#9CA3AF' }} />
            </button>
          )}
          {onDelete && (
            <button onClick={(e) => { e.stopPropagation(); onDelete(); }}
              className="flex items-center justify-center hover:bg-red-900/30 transition-colors"
              style={{ width: 28, height: 28, borderRadius: 6 }} title={t('common.delete')}>
              <Trash2 style={{ width: 14, height: 14, color: '#9CA3AF' }} />
            </button>
          )}
        </div>
      </motion.div>
    );
  }

  // ==================== GRID / CARD VIEW ====================
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className="group border border-gray-700 hover:border-gray-600 transition-colors overflow-hidden"
      style={{ background: '#1F2937', borderRadius: 8 }}
    >
      {/* Header — category icon + title + status */}
      <div style={{ padding: 12 }}>
        <div className="flex items-start justify-between" style={{ gap: 8 }}>
          <div className="flex items-center min-w-0" style={{ gap: 8 }}>
            <div className="flex-shrink-0 flex items-center justify-center"
              style={{ width: 36, height: 36, borderRadius: 6, background: cat.bg, color: cat.color }}>
              <CategoryIcon />
            </div>
            <div className="min-w-0">
              <h3 className="truncate" style={{ fontSize: 14, fontWeight: 600, color: '#F9FAFB', margin: 0 }}>
                {document.title}
              </h3>
              <div className="flex items-center" style={{ gap: 6, marginTop: 2 }}>
                <span style={{ fontSize: 11, fontWeight: 500, padding: '1px 6px', borderRadius: 4, background: stat.bg, color: stat.color }}>
                  {t(`document.status.${document.status}`)}
                </span>
                <span style={{ fontSize: 11, fontWeight: 500, padding: '1px 6px', borderRadius: 4, background: cat.bg, color: cat.color }}>
                  {t(`document.categories.${document.category}`)}
                </span>
              </div>
            </div>
          </div>

          {/* Actions — 28×28 */}
          <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity" style={{ gap: 2 }}>
            {onEdit && (
              <button onClick={onEdit}
                className="flex items-center justify-center hover:bg-gray-700 transition-colors"
                style={{ width: 28, height: 28, borderRadius: 6 }} title={t('common.edit')}>
                <Edit2 style={{ width: 14, height: 14, color: '#9CA3AF' }} />
              </button>
            )}
            {onDelete && (
              <button onClick={onDelete}
                className="flex items-center justify-center hover:bg-red-900/30 transition-colors"
                style={{ width: 28, height: 28, borderRadius: 6 }} title={t('common.delete')}>
                <Trash2 style={{ width: 14, height: 14, color: '#9CA3AF' }} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Stats — same label/value pattern */}
      <div className="border-t border-gray-700 grid grid-cols-3" style={{ padding: '8px 12px', gap: 8 }}>
        <div>
          <div style={{ fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
            {t('document.date', 'Date')}
          </div>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#E5E7EB' }}>{formatDate(document.document_date)}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
            {t('document.size', 'Size')}
          </div>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#E5E7EB' }}>{documentAPI.formatFileSize(document.file_size_bytes)}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
            {t('document.version', 'Version')}
          </div>
          <div style={{ fontSize: 17, fontWeight: 700, color: '#E5E7EB' }}>{document.version}</div>
        </div>
      </div>

      {/* Footer — View Document */}
      {onView && (
        <div className="border-t border-gray-700" style={{ padding: 8 }}>
          <button onClick={onView}
            className="w-full flex items-center justify-center border border-gray-600 hover:bg-gray-700 transition-colors"
            style={{ height: 36, gap: 6, borderRadius: 6, fontSize: 13, fontWeight: 500, color: '#E5E7EB' }}>
            <Eye style={{ width: 16, height: 16 }} />
            {t('common.view')}
          </button>
        </div>
      )}
    </motion.div>
  );
};

export default DocumentCard;
