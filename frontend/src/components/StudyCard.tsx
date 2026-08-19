import React from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import {
  Calendar,
  User,
  FileImage,
  Layers,
  HardDrive,
  Eye,
  Download,
  Trash2,
  Edit,
  Clock,
  Activity,
  Building2,
  Brain,
  Scan,
  Puzzle,
} from 'lucide-react';
import type { ImagingStudy, StudySummary } from '@/types';

// Modality colors — inline styles, no Tailwind light-mode classes
const modalityColors: Record<string, { bg: string; color: string }> = {
  CT: { bg: 'rgba(59,130,246,0.15)', color: '#60A5FA' },
  MR: { bg: 'rgba(139,92,246,0.15)', color: '#A78BFA' },
  US: { bg: 'rgba(34,197,94,0.15)', color: '#4ADE80' },
  XR: { bg: 'rgba(249,115,22,0.15)', color: '#FB923C' },
  MG: { bg: 'rgba(236,72,153,0.15)', color: '#F472B6' },
  NM: { bg: 'rgba(234,179,8,0.15)', color: '#FACC15' },
  PT: { bg: 'rgba(239,68,68,0.15)', color: '#F87171' },
  CR: { bg: 'rgba(6,182,212,0.15)', color: '#22D3EE' },
  DX: { bg: 'rgba(99,102,241,0.15)', color: '#818CF8' },
  OT: { bg: 'rgba(107,114,128,0.15)', color: '#96A0B0' },
};

const statusColors: Record<string, { bg: string; color: string }> = {
  registered: { bg: 'rgba(59,130,246,0.12)', color: '#60A5FA' },
  available: { bg: 'rgba(16,185,129,0.12)', color: '#34D399' },
  cancelled: { bg: 'rgba(239,68,68,0.12)', color: '#F87171' },
  'entered-in-error': { bg: 'rgba(249,115,22,0.12)', color: '#FB923C' },
};

interface StudyCardProps {
  study: ImagingStudy | StudySummary;
  onView?: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
  onDownload?: () => void;
  compact?: boolean;
  showPatientInfo?: boolean;
}

export const StudyCard: React.FC<StudyCardProps> = ({
  study,
  onView,
  onEdit,
  onDelete,
  onDownload,
  compact = false,
}) => {
  const { t, i18n } = useTranslation();

  const segmentationInfo = undefined as { count: number; has_approved: boolean; has_in_progress: boolean } | undefined;

  const mod = modalityColors[study.modality] || modalityColors.OT;
  const stat = statusColors[study.status] || statusColors.registered;

  const formatDate = (dateString: string) => {
    // Use the active UI language so dates match the session locale rather than
    // the OS locale (avoids a Spanish "12 de jul de 2026" in an English UI).
    return new Date(dateString).toLocaleDateString(i18n.language, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const formatSize = (bytes: number | undefined | null) => {
    if (bytes === undefined || bytes === null || isNaN(bytes) || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const isFullStudy = (s: ImagingStudy | StudySummary): s is ImagingStudy => {
    return 'study_instance_uid' in s;
  };

  const ModalityIcon = ({ size = 16 }: { size?: number }) => {
    if (study.modality === 'MR') return <Brain style={{ width: size, height: size }} />;
    if (study.modality === 'CT') return <Scan style={{ width: size, height: size }} />;
    return <span style={{ fontSize: size * 0.7, fontWeight: 700 }}>{study.modality}</span>;
  };

  // ==================== COMPACT / LIST VIEW ====================
  if (compact) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        onClick={onView}
        className="group border border-gray-700 hover:border-gray-600 transition-colors"
        style={{ background: '#161922', borderRadius: 8, padding: 12, cursor: onView ? 'pointer' : 'default', display: 'flex', alignItems: 'center', gap: 12 }}
      >
        {/* Modality — 36×36 */}
        <div className="flex-shrink-0 flex items-center justify-center"
          style={{ width: 36, height: 36, borderRadius: 6, background: mod.bg, color: mod.color }}>
          <ModalityIcon />
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center" style={{ gap: 6 }}>
            <span className="truncate" style={{ fontSize: 14, fontWeight: 500, color: '#E7EBF2' }}>
              {study.study_description || t('study.noDescription')}
            </span>
            <span style={{ fontSize: 11, fontWeight: 500, padding: '1px 6px', borderRadius: 4, background: stat.bg, color: stat.color, flexShrink: 0 }}>
              {t(`study.status.${study.status}`)}
            </span>
          </div>
          <div className="flex items-center" style={{ gap: 8, marginTop: 2 }}>
            <span className="flex items-center" style={{ gap: 4, fontSize: 12, color: '#96A0B0' }}>
              <Calendar style={{ width: 12, height: 12 }} />
              {formatDate(study.study_date)}
            </span>
            <span style={{ color: '#232833' }}>·</span>
            <span style={{ fontSize: 12, color: '#96A0B0' }}>{study.series_count ?? 0} series</span>
            <span style={{ color: '#232833' }}>·</span>
            <span style={{ fontSize: 12, color: '#96A0B0' }}>{study.instance_count ?? 0} images</span>
          </div>
        </div>

        {/* Actions — 28×28 (sm) */}
        <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity" style={{ gap: 4 }}>
          {onDownload && (
            <button onClick={(e) => { e.stopPropagation(); onDownload(); }}
              className="flex items-center justify-center hover:bg-gray-700 transition-colors"
              style={{ width: 28, height: 28, borderRadius: 6 }} title={t('common.download')}>
              <Download style={{ width: 14, height: 14, color: '#96A0B0' }} />
            </button>
          )}
          {onView && (
            <button onClick={(e) => { e.stopPropagation(); onView(); }}
              className="flex items-center justify-center hover:bg-gray-700 transition-colors"
              style={{ width: 28, height: 28, borderRadius: 6 }} title={t('common.view')}>
              <Eye style={{ width: 14, height: 14, color: '#96A0B0' }} />
            </button>
          )}
        </div>
      </motion.div>
    );
  }

  // ==================== GRID / CARD VIEW ====================
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="group border border-gray-700 hover:border-gray-600 transition-colors overflow-hidden"
      style={{ background: '#161922', borderRadius: 8 }}
    >
      {/* Header — modality + title + status + date */}
      <div style={{ padding: 12 }}>
        <div className="flex items-start justify-between" style={{ gap: 8 }}>
          <div className="flex items-center min-w-0" style={{ gap: 8 }}>
            {/* Modality badge — 36×36, radius 6 */}
            <div className="flex-shrink-0 flex items-center justify-center"
              style={{ width: 36, height: 36, borderRadius: 6, background: mod.bg, color: mod.color }}>
              <ModalityIcon />
            </div>
            <div className="min-w-0">
              <h3 className="truncate" style={{ fontSize: 14, fontWeight: 600, color: '#F9FAFB', margin: 0 }}>
                {study.study_description || t('study.noDescription')}
              </h3>
              <div className="flex items-center" style={{ gap: 6, marginTop: 2 }}>
                <span style={{ fontSize: 11, fontWeight: 500, padding: '1px 6px', borderRadius: 4, background: stat.bg, color: stat.color }}>
                  {t(`study.status.${study.status}`)}
                </span>
                <span className="flex items-center" style={{ gap: 4, fontSize: 11, color: '#767E8E' }}>
                  <Calendar style={{ width: 10, height: 10 }} />
                  {formatDate(study.study_date)}
                </span>
              </div>
            </div>
          </div>

          {/* Actions — 28×28 (sm), show on hover */}
          <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity" style={{ gap: 2 }}>
            {onEdit && (
              <button onClick={onEdit}
                className="flex items-center justify-center hover:bg-gray-700 transition-colors"
                style={{ width: 28, height: 28, borderRadius: 6 }} title={t('common.edit')}>
                <Edit style={{ width: 14, height: 14, color: '#96A0B0' }} />
              </button>
            )}
            {onDelete && (
              <button onClick={onDelete}
                className="flex items-center justify-center hover:bg-red-900/30 transition-colors"
                style={{ width: 28, height: 28, borderRadius: 6 }} title={t('common.delete')}>
                <Trash2 style={{ width: 14, height: 14, color: '#96A0B0' }} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Stats — horizontal row, compact, labeled with UPPERCASE 11px */}
      <div className="border-t border-gray-700 grid grid-cols-4" style={{ padding: '8px 12px', gap: 8 }}>
        <div>
          <div style={{ fontSize: 11, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
            {t('study.series', { count: study.series_count ?? 0 })}
          </div>
          <div style={{ fontSize: 17, fontWeight: 700, color: '#E7EBF2' }}>{study.series_count ?? 0}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
            {t('study.images', { count: study.instance_count ?? 0 })}
          </div>
          <div style={{ fontSize: 17, fontWeight: 700, color: '#E7EBF2' }}>{study.instance_count ?? 0}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
            {t('study.totalSize')}
          </div>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#96A0B0' }}>{formatSize(study.total_size_bytes)}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
            Segm.
          </div>
          <div style={{ fontSize: 17, fontWeight: 700, color: '#E7EBF2' }}>{segmentationInfo?.count ?? 0}</div>
        </div>
      </div>

      {/* Footer — View Study, 36px, subtle border-top style */}
      {onView && (
        <div className="border-t border-gray-700" style={{ padding: 8 }}>
          <button onClick={onView}
            className="w-full flex items-center justify-center border border-gray-600 hover:bg-gray-700 transition-colors"
            style={{ height: 36, gap: 6, borderRadius: 6, fontSize: 13, fontWeight: 500, color: '#E7EBF2' }}>
            <Eye style={{ width: 16, height: 16 }} />
            {t('study.viewStudy')}
          </button>
        </div>
      )}
    </motion.div>
  );
};

export default StudyCard;
