import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import {
  User,
  Phone,
  Mail,
  Calendar,
  Activity,
  FileText,
  Image,
  Edit,
  Trash2,
  ChevronRight
} from 'lucide-react';
import type { Patient, MedicalHistory } from '@/types';

interface PatientCardProps {
  patient: Patient;
  medicalHistory?: MedicalHistory[];
  onEdit?: () => void;
  onDelete?: () => void;
  onSelect?: () => void;
  onViewStudies?: () => void;
  onViewDocuments?: () => void;
  compact?: boolean;
  isDeleting?: boolean;
}

// Calculate age from birth date
const calculateAge = (birthDate: string): number => {
  if (!birthDate) return 0;
  const birth = new Date(birthDate);
  if (isNaN(birth.getTime())) return 0;
  const today = new Date();
  let age = today.getFullYear() - birth.getFullYear();
  const monthDiff = today.getMonth() - birth.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
    age--;
  }
  return age;
};

// Get initials from full_name or given_name/family_name
const getInitials = (patient: Patient): string => {
  if (patient.given_name && patient.family_name) {
    return `${patient.given_name[0]}${patient.family_name[0]}`.toUpperCase();
  }
  if (patient.full_name) {
    const parts = patient.full_name.trim().split(/\s+/);
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
    }
    return patient.full_name.substring(0, 2).toUpperCase();
  }
  return '??';
};

// Get display name
const getDisplayName = (patient: Patient): string => {
  if (patient.full_name) return patient.full_name;
  if (patient.given_name && patient.family_name) {
    return `${patient.given_name} ${patient.family_name}`;
  }
  return 'Paciente';
};

export default function PatientCard({
  patient,
  medicalHistory = [],
  onEdit,
  onDelete,
  onSelect,
  onViewStudies,
  onViewDocuments,
  compact = false,
  isDeleting = false
}: PatientCardProps) {
  const { t } = useTranslation();

  const patientAge = patient.age ?? calculateAge(patient.birth_date);
  const initials = getInitials(patient);
  const displayName = getDisplayName(patient);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400';
      case 'inactive':
        return 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400';
      case 'deceased':
        return 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300';
      default:
        return 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400';
    }
  };

  const getGenderSymbol = (gender: string) => {
    switch (gender) {
      case 'male': return '♂';
      case 'female': return '♀';
      default: return '';
    }
  };

  const activeConditions = medicalHistory.filter(h => h.is_active);

  // ==================== COMPACT/LIST VIEW ====================
  if (compact) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        onClick={onSelect}
        className={`
          group relative bg-white dark:bg-slate-800
          rounded-xl border border-slate-200 dark:border-slate-700
          p-4 hover:shadow-lg hover:border-slate-300 dark:hover:border-slate-600
          transition-all duration-200
          ${onSelect ? 'cursor-pointer' : ''}
          ${isDeleting ? 'opacity-50 pointer-events-none' : ''}
        `}
      >
        <div className="flex items-center gap-4">
          {/* Avatar */}
          <div className="w-12 h-12 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-semibold text-sm shadow-md flex-shrink-0">
            {initials}
          </div>

          {/* Patient Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-semibold text-slate-900 dark:text-white truncate">
                {displayName}
              </h3>
              {patient.gender && (
                <span className="text-blue-500 dark:text-blue-400 text-sm">
                  {getGenderSymbol(patient.gender)}
                </span>
              )}
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(patient.status)}`}>
                {t(`patient.status.${patient.status}`)}
              </span>
            </div>
            <div className="flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400 mt-1">
              <span className="font-mono text-xs bg-slate-100 dark:bg-slate-700 px-2 py-0.5 rounded">
                {patient.mrn}
              </span>
              {patientAge > 0 && (
                <>
                  <span className="text-slate-300 dark:text-slate-600">•</span>
                  <span>{patientAge} {t('patient.years')}</span>
                </>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            {onEdit && (
              <button
                onClick={(e) => { e.stopPropagation(); onEdit(); }}
                className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
                title={t('common.edit')}
              >
                <Edit className="w-4 h-4 text-slate-500 dark:text-slate-400" />
              </button>
            )}
            {onDelete && (
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(); }}
                className="p-2 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                title={t('common.delete')}
              >
                <Trash2 className="w-4 h-4 text-slate-500 hover:text-red-500 dark:text-slate-400 dark:hover:text-red-400" />
              </button>
            )}
          </div>

          <ChevronRight className="w-5 h-5 text-slate-400 dark:text-slate-500 flex-shrink-0" />
        </div>
      </motion.div>
    );
  }

  // ==================== GRID/CARD VIEW ====================
  return (
    <motion.div
      data-component="patient-card-v2"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      onClick={onSelect}
      className={`
        group relative bg-white dark:bg-slate-800
        rounded-2xl border border-slate-200 dark:border-slate-700
        shadow-sm hover:shadow-xl
        transition-all duration-300 overflow-hidden
        ${onSelect ? 'cursor-pointer' : ''}
        ${isDeleting ? 'opacity-50 pointer-events-none' : ''}
      `}
    >
      {/* Header with gradient */}
      <div className="relative bg-gradient-to-r from-blue-500 to-indigo-600 px-5 py-4">
        {/* Action buttons - top right */}
        <div className="absolute top-3 right-3 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {onEdit && (
            <button
              onClick={(e) => { e.stopPropagation(); onEdit(); }}
              className="p-1.5 bg-white/20 hover:bg-white/30 rounded-lg transition-colors backdrop-blur-sm"
              title={t('common.edit')}
            >
              <Edit className="w-4 h-4 text-white" />
            </button>
          )}
          {onDelete && (
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              className="p-1.5 bg-white/20 hover:bg-red-500/60 rounded-lg transition-colors backdrop-blur-sm"
              title={t('common.delete')}
            >
              <Trash2 className="w-4 h-4 text-white" />
            </button>
          )}
        </div>

        {/* Patient identity */}
        <div className="flex items-center gap-4">
          {/* Avatar */}
          <div className="w-14 h-14 rounded-xl bg-white/20 backdrop-blur-sm flex items-center justify-center text-white text-lg font-bold shadow-lg flex-shrink-0">
            {initials}
          </div>

          {/* Name and MRN */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white truncate">{displayName}</h2>
              {patient.gender && (
                <span className="text-white/80 text-base flex-shrink-0">
                  {getGenderSymbol(patient.gender)}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className="font-mono text-xs bg-white/20 text-white/90 px-2 py-0.5 rounded">
                {patient.mrn}
              </span>
              {patientAge > 0 && (
                <>
                  <span className="text-white/60">•</span>
                  <span className="text-white/90 text-sm">{patientAge} {t('patient.years')}</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Status badge */}
        <div className="mt-3">
          <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${getStatusColor(patient.status)}`}>
            <Activity className="w-3 h-3 mr-1" />
            {t(`patient.status.${patient.status}`)}
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="p-5">
        {/* Stats Grid */}
        <div className="grid grid-cols-2 gap-3">
          {/* Studies */}
          <button
            onClick={(e) => { e.stopPropagation(); onViewStudies?.(); }}
            disabled={!onViewStudies}
            className={`
              flex items-center gap-3 p-3 rounded-xl
              bg-blue-50 dark:bg-blue-900/20
              border border-blue-100 dark:border-blue-800/50
              ${onViewStudies ? 'hover:bg-blue-100 dark:hover:bg-blue-900/30 cursor-pointer' : 'cursor-default'}
              transition-colors
            `}
          >
            <div className="w-10 h-10 rounded-lg bg-blue-500/10 dark:bg-blue-500/20 flex items-center justify-center">
              <Image className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div className="text-left">
              <div className="text-xl font-bold text-blue-700 dark:text-blue-300">
                {patient.study_count ?? 0}
              </div>
              <div className="text-xs text-blue-600/80 dark:text-blue-400/80">
                {t('patient.studies')}
              </div>
            </div>
          </button>

          {/* Documents */}
          <button
            onClick={(e) => { e.stopPropagation(); onViewDocuments?.(); }}
            disabled={!onViewDocuments}
            className={`
              flex items-center gap-3 p-3 rounded-xl
              bg-violet-50 dark:bg-violet-900/20
              border border-violet-100 dark:border-violet-800/50
              ${onViewDocuments ? 'hover:bg-violet-100 dark:hover:bg-violet-900/30 cursor-pointer' : 'cursor-default'}
              transition-colors
            `}
          >
            <div className="w-10 h-10 rounded-lg bg-violet-500/10 dark:bg-violet-500/20 flex items-center justify-center">
              <FileText className="w-5 h-5 text-violet-600 dark:text-violet-400" />
            </div>
            <div className="text-left">
              <div className="text-xl font-bold text-violet-700 dark:text-violet-300">
                {patient.document_count ?? 0}
              </div>
              <div className="text-xs text-violet-600/80 dark:text-violet-400/80">
                {t('patient.documents')}
              </div>
            </div>
          </button>
        </div>

        {/* Contact Info - only if available */}
        {(patient.phone_mobile || patient.email) && (
          <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-700 space-y-2">
            {patient.phone_mobile && (
              <a
                href={`tel:${patient.phone_mobile}`}
                onClick={(e) => e.stopPropagation()}
                className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                <Phone className="w-4 h-4" />
                <span>{patient.phone_mobile}</span>
              </a>
            )}
            {patient.email && (
              <a
                href={`mailto:${patient.email}`}
                onClick={(e) => e.stopPropagation()}
                className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors truncate"
              >
                <Mail className="w-4 h-4 flex-shrink-0" />
                <span className="truncate">{patient.email}</span>
              </a>
            )}
          </div>
        )}

        {/* Active conditions badge - only if there are any */}
        {activeConditions.length > 0 && (
          <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-700">
            <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
              <Activity className="w-4 h-4" />
              <span className="text-sm font-medium">
                {activeConditions.length} {t('patient.activeConditions')}
              </span>
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
