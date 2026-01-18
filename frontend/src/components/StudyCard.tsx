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
import { useSegmentationCountByStudy } from '@/hooks/useSegmentations';

// Modality icons and colors
const modalityConfig: Record<string, { icon: string; color: string; bgColor: string; useIcon?: 'brain' | 'scan' }> = {
  CT: { icon: 'CT', color: 'text-blue-600', bgColor: 'bg-blue-100', useIcon: 'scan' },
  MR: { icon: 'MR', color: 'text-purple-600', bgColor: 'bg-purple-100', useIcon: 'brain' },
  US: { icon: 'US', color: 'text-green-600', bgColor: 'bg-green-100' },
  XR: { icon: 'XR', color: 'text-orange-600', bgColor: 'bg-orange-100' },
  MG: { icon: 'MG', color: 'text-pink-600', bgColor: 'bg-pink-100' },
  NM: { icon: 'NM', color: 'text-yellow-600', bgColor: 'bg-yellow-100' },
  PT: { icon: 'PT', color: 'text-red-600', bgColor: 'bg-red-100' },
  CR: { icon: 'CR', color: 'text-cyan-600', bgColor: 'bg-cyan-100' },
  DX: { icon: 'DX', color: 'text-indigo-600', bgColor: 'bg-indigo-100' },
  OT: { icon: 'OT', color: 'text-gray-600', bgColor: 'bg-gray-100' },
};

const statusConfig: Record<string, { color: string; bgColor: string }> = {
  registered: { color: 'text-blue-600', bgColor: 'bg-blue-100' },
  available: { color: 'text-green-600', bgColor: 'bg-green-100' },
  cancelled: { color: 'text-red-600', bgColor: 'bg-red-100' },
  'entered-in-error': { color: 'text-orange-600', bgColor: 'bg-orange-100' },
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
  showPatientInfo = false,
}) => {
  const { t } = useTranslation();

  // Fetch segmentation count for this study
  const { data: segmentationInfo } = useSegmentationCountByStudy(study.patient_id, study.id);

  // Get modality configuration
  const modality = modalityConfig[study.modality] || modalityConfig.OT;
  const status = statusConfig[study.status] || statusConfig.registered;

  // Format date
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  // Format file size
  const formatSize = (bytes: number | undefined | null) => {
    if (bytes === undefined || bytes === null || isNaN(bytes) || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  // Check if study is full ImagingStudy (has additional fields)
  const isFullStudy = (s: ImagingStudy | StudySummary): s is ImagingStudy => {
    return 'study_instance_uid' in s;
  };

  if (compact) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-4 p-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 hover:shadow-md transition-shadow cursor-pointer"
        onClick={onView}
      >
        {/* Modality Badge */}
        <div
          className={`flex items-center justify-center w-12 h-12 rounded-lg ${modality.bgColor} ${modality.color} font-bold text-lg`}
        >
          {modality.useIcon === 'brain' ? (
            <Brain className="w-6 h-6" />
          ) : modality.useIcon === 'scan' ? (
            <Scan className="w-6 h-6" />
          ) : (
            modality.icon
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-gray-900 dark:text-gray-100 truncate">
              {study.study_description || t('study.noDescription')}
            </span>
            <span
              className={`px-2 py-0.5 rounded-full text-xs font-medium ${status.bgColor} ${status.color}`}
            >
              {t(`study.status.${study.status}`)}
            </span>
          </div>
          <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400 mt-1">
            <span className="flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5" />
              {formatDate(study.study_date)}
            </span>
            <span className="flex items-center gap-1">
              <Layers className="w-3.5 h-3.5" />
              {study.series_count ?? 0} {t('study.series', { count: study.series_count ?? 0 })}
            </span>
            <span className="flex items-center gap-1">
              <FileImage className="w-3.5 h-3.5" />
              {study.instance_count ?? 0} {t('study.images', { count: study.instance_count ?? 0 })}
            </span>
            <span
              className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                segmentationInfo?.has_approved
                  ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                  : segmentationInfo?.has_in_progress
                  ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                  : 'bg-gray-100 text-gray-600 dark:bg-gray-700/50 dark:text-gray-400'
              }`}
              title={t('study.segmentationsTooltip', { count: segmentationInfo?.count ?? 0 })}
            >
              <Puzzle className="w-3 h-3" />
              {segmentationInfo?.count ?? 0}
            </span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1">
          {onDownload && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDownload();
              }}
              className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
              title={t('common.download')}
            >
              <Download className="w-4 h-4" />
            </button>
          )}
          {onView && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onView();
              }}
              className="p-2 text-gray-400 hover:text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 rounded-lg transition-colors"
              title={t('common.view')}
            >
              <Eye className="w-4 h-4" />
            </button>
          )}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-lg transition-shadow overflow-hidden"
    >
      {/* Header */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            {/* Modality Badge */}
            <div
              className={`flex items-center justify-center w-14 h-14 rounded-xl ${modality.bgColor} ${modality.color} font-bold text-xl`}
            >
              {modality.useIcon === 'brain' ? (
                <Brain className="w-7 h-7" />
              ) : modality.useIcon === 'scan' ? (
                <Scan className="w-7 h-7" />
              ) : (
                modality.icon
              )}
            </div>
            <div>
              <h3 className="font-semibold text-lg text-gray-900 dark:text-gray-100">
                {study.study_description || t('study.noDescription')}
              </h3>
              <div className="flex items-center gap-2 mt-1">
                <span
                  className={`px-2 py-0.5 rounded-full text-xs font-medium ${status.bgColor} ${status.color}`}
                >
                  {t(`study.status.${study.status}`)}
                </span>
                {study.accession_number && (
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    #{study.accession_number}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1">
            {onView && (
              <button
                onClick={onView}
                className="p-2 text-gray-400 hover:text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 rounded-lg transition-colors"
                title={t('common.view')}
              >
                <Eye className="w-5 h-5" />
              </button>
            )}
            {onDownload && (
              <button
                onClick={onDownload}
                className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                title={t('common.download')}
              >
                <Download className="w-5 h-5" />
              </button>
            )}
            {onEdit && (
              <button
                onClick={onEdit}
                className="p-2 text-gray-400 hover:text-yellow-600 hover:bg-yellow-50 dark:hover:bg-yellow-900/20 rounded-lg transition-colors"
                title={t('common.edit')}
              >
                <Edit className="w-5 h-5" />
              </button>
            )}
            {onDelete && (
              <button
                onClick={onDelete}
                className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                title={t('common.delete')}
              >
                <Trash2 className="w-5 h-5" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {/* Stats */}
        <div className="grid gap-3 mb-4 grid-cols-2">
          <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <Layers className="w-8 h-8 text-blue-500 flex-shrink-0" />
            <div>
              <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {study.series_count ?? 0}
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400">
                {t('study.series', { count: study.series_count ?? 0 })}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <FileImage className="w-8 h-8 text-green-500 flex-shrink-0" />
            <div>
              <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {study.instance_count ?? 0}
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400">
                {t('study.images', { count: study.instance_count ?? 0 })}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <HardDrive className="w-8 h-8 text-purple-500 flex-shrink-0" />
            <div>
              <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {formatSize(study.total_size_bytes)}
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400">
                {t('study.totalSize')}
              </div>
            </div>
          </div>
          <div
            className={`flex items-center gap-3 p-3 rounded-lg ${
              segmentationInfo?.has_approved
                ? 'bg-green-50 dark:bg-green-900/20'
                : segmentationInfo?.has_in_progress
                ? 'bg-yellow-50 dark:bg-yellow-900/20'
                : 'bg-gray-50 dark:bg-gray-700/50'
            }`}
          >
            <Puzzle
              className={`w-8 h-8 flex-shrink-0 ${
                segmentationInfo?.has_approved
                  ? 'text-green-500'
                  : segmentationInfo?.has_in_progress
                  ? 'text-yellow-500'
                  : 'text-gray-400'
              }`}
            />
            <div>
              <div
                className={`text-lg font-semibold ${
                  segmentationInfo?.has_approved
                    ? 'text-green-700 dark:text-green-400'
                    : segmentationInfo?.has_in_progress
                    ? 'text-yellow-700 dark:text-yellow-400'
                    : 'text-gray-700 dark:text-gray-300'
                }`}
              >
                {segmentationInfo?.count ?? 0}
              </div>
              <div
                className={`text-xs ${
                  segmentationInfo?.has_approved
                    ? 'text-green-600 dark:text-green-500'
                    : segmentationInfo?.has_in_progress
                    ? 'text-yellow-600 dark:text-yellow-500'
                    : 'text-gray-500 dark:text-gray-400'
                }`}
              >
                {t('study.segmentations', { count: segmentationInfo?.count ?? 0 })}
              </div>
            </div>
          </div>
        </div>

        {/* Details */}
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2 text-gray-600 dark:text-gray-300">
            <Calendar className="w-4 h-4 text-gray-400" />
            <span className="font-medium">{t('study.studyDate')}:</span>
            <span>{formatDate(study.study_date)}</span>
          </div>

          {isFullStudy(study) && (
            <>
              {study.body_site && (
                <div className="flex items-center gap-2 text-gray-600 dark:text-gray-300">
                  <Activity className="w-4 h-4 text-gray-400" />
                  <span className="font-medium">{t('study.bodySite')}:</span>
                  <span>{study.body_site}</span>
                </div>
              )}

              {study.referring_physician_name && (
                <div className="flex items-center gap-2 text-gray-600 dark:text-gray-300">
                  <User className="w-4 h-4 text-gray-400" />
                  <span className="font-medium">{t('study.referringPhysician')}:</span>
                  <span>{study.referring_physician_name}</span>
                </div>
              )}

              {study.institution_name && (
                <div className="flex items-center gap-2 text-gray-600 dark:text-gray-300">
                  <Building2 className="w-4 h-4 text-gray-400" />
                  <span className="font-medium">{t('study.institution')}:</span>
                  <span>{study.institution_name}</span>
                </div>
              )}

              {study.reason_for_study && (
                <div className="flex items-start gap-2 text-gray-600 dark:text-gray-300">
                  <FileImage className="w-4 h-4 text-gray-400 mt-0.5" />
                  <span className="font-medium">{t('study.reason')}:</span>
                  <span className="flex-1">{study.reason_for_study}</span>
                </div>
              )}

              <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 text-xs pt-2 border-t border-gray-100 dark:border-gray-700">
                <Clock className="w-3.5 h-3.5" />
                <span>
                  {t('common.createdAt')}: {formatDate(study.created_at)}
                </span>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Footer - View Button */}
      {onView && (
        <div className="px-4 pb-4">
          <button
            onClick={onView}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            <Eye className="w-4 h-4" />
            {t('study.viewStudy')}
          </button>
        </div>
      )}
    </motion.div>
  );
};

export default StudyCard;
