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
  return 'Patient';
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

  /*
   * Design System v2.0 — Minor Third scale (1.2):
   *   12px labels → 14px body → 17px emphasis → 20px heading
   * Proportional elements: avatar 44px (lg touch target), stats icon 36px (md)
   * Spacing: 4px grid — related=8px, groups=16px
   */

  // ==================== COMPACT/LIST VIEW ====================
  // Same pattern as StudyCard compact
  if (compact) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        onClick={onSelect}
        className={`group border transition-colors duration-150
          border-gray-700 hover:border-gray-600
          ${onSelect ? 'cursor-pointer' : ''}
          ${isDeleting ? 'opacity-50 pointer-events-none' : ''}
        `}
        style={{ background: '#161922', borderRadius: 8, padding: 12, display: 'flex', alignItems: 'center', gap: 12 }}
      >
        {/* Avatar — 36×36, radius 6 */}
        <div className="flex-shrink-0 bg-brand-950 border border-brand-500/30 flex items-center justify-center text-white"
          style={{ width: 36, height: 36, borderRadius: 6, fontSize: 14, fontWeight: 700 }}>
          {initials}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center" style={{ gap: 6 }}>
            <h3 className="truncate" style={{ fontSize: 14, fontWeight: 600, color: '#F9FAFB', margin: 0 }}>
              {displayName}
            </h3>
            <span style={{
              fontSize: 11, fontWeight: 500, padding: '1px 6px', borderRadius: 4,
              background: patient.status === 'active' ? 'rgba(16,185,129,0.12)' : 'rgba(148,163,184,0.12)',
              color: patient.status === 'active' ? '#34D399' : '#94A3B8',
            }}>
              {t(`patient.status.${patient.status}`)}
            </span>
          </div>
          <div className="flex items-center" style={{ gap: 8, marginTop: 2 }}>
            <span className="font-mono" style={{ fontSize: 12, color: '#96A0B0' }}>{patient.mrn}</span>
            <span style={{ color: '#232833' }}>·</span>
            {patientAge > 0 && <span style={{ fontSize: 12, color: '#96A0B0' }}>{patientAge} {t('patient.years')}</span>}
            {patient.gender && <><span style={{ color: '#232833' }}>·</span><span style={{ fontSize: 12, color: '#767E8E' }}>{getGenderSymbol(patient.gender)}</span></>}
          </div>
        </div>
        {/* Actions — 28×28 */}
        <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity" style={{ gap: 4 }}>
          {onEdit && (
            <button onClick={(e) => { e.stopPropagation(); onEdit(); }}
              className="flex items-center justify-center hover:bg-gray-700 transition-colors" title={t('common.edit')}
              style={{ width: 28, height: 28, borderRadius: 6 }}>
              <Edit style={{ width: 14, height: 14, color: '#96A0B0' }} />
            </button>
          )}
          {onDelete && (
            <button onClick={(e) => { e.stopPropagation(); onDelete(); }}
              className="flex items-center justify-center hover:bg-red-900/30 transition-colors" title={t('common.delete')}
              style={{ width: 28, height: 28, borderRadius: 6 }}>
              <Trash2 style={{ width: 14, height: 14, color: '#96A0B0' }} />
            </button>
          )}
        </div>
        <ChevronRight style={{ width: 16, height: 16, color: '#767E8E', flexShrink: 0 }} />
      </motion.div>
    );
  }

  // ==================== GRID/CARD VIEW ====================
  // Same pattern as StudyCard: header → data grid → footer
  return (
    <motion.div
      data-component="patient-card-v2"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      onClick={onSelect}
      className={`group relative border overflow-hidden transition-colors duration-150
        border-gray-700 hover:border-gray-600
        ${onSelect ? 'cursor-pointer' : ''}
        ${isDeleting ? 'opacity-50 pointer-events-none' : ''}
      `}
      style={{ background: '#161922', borderRadius: 8 }}
    >
      {/* Header — avatar + name + status (same pattern as StudyCard header) */}
      <div style={{ padding: 12 }}>
        <div className="flex items-start justify-between" style={{ gap: 8 }}>
          <div className="flex items-center min-w-0" style={{ gap: 8 }}>
            {/* Avatar — 36×36, radius 6 (same as modality badge in StudyCard) */}
            <div className="flex-shrink-0 bg-brand-950 border border-brand-500/30 flex items-center justify-center text-white"
              style={{ width: 36, height: 36, borderRadius: 6, fontSize: 14, fontWeight: 700 }}>
              {initials}
            </div>
            <div className="min-w-0">
              <h2 className="truncate" style={{ fontSize: 14, fontWeight: 600, color: '#F9FAFB', margin: 0 }}>
                {displayName}
              </h2>
              <div className="flex items-center" style={{ gap: 6, marginTop: 2 }}>
                <span style={{
                  fontSize: 11, fontWeight: 500, padding: '1px 6px', borderRadius: 4,
                  background: patient.status === 'active' ? 'rgba(16,185,129,0.12)' : 'rgba(148,163,184,0.12)',
                  color: patient.status === 'active' ? '#34D399' : '#94A3B8',
                }}>
                  {t(`patient.status.${patient.status}`)}
                </span>
                {patient.gender && (
                  <span style={{ fontSize: 11, color: '#767E8E' }}>{getGenderSymbol(patient.gender)}</span>
                )}
                {patientAge > 0 && (
                  <span style={{ fontSize: 11, color: '#767E8E' }}>{patientAge} {t('patient.years')}</span>
                )}
              </div>
            </div>
          </div>

          {/* Actions — 28×28 (sm), show on hover */}
          <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity" style={{ gap: 2 }}>
            {onEdit && (
              <button onClick={(e) => { e.stopPropagation(); onEdit(); }}
                className="flex items-center justify-center hover:bg-gray-700 transition-colors" title={t('common.edit')}
                style={{ width: 28, height: 28, borderRadius: 6 }}>
                <Edit style={{ width: 14, height: 14, color: '#96A0B0' }} />
              </button>
            )}
            {onDelete && (
              <button onClick={(e) => { e.stopPropagation(); onDelete(); }}
                className="flex items-center justify-center hover:bg-red-900/30 transition-colors" title={t('common.delete')}
                style={{ width: 28, height: 28, borderRadius: 6 }}>
                <Trash2 style={{ width: 14, height: 14, color: '#96A0B0' }} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Stats — same label/value pattern as StudyCard and PatientDetailPage */}
      <div className="border-t border-gray-700 grid grid-cols-3" style={{ padding: '8px 12px', gap: 8 }}>
        <div>
          <div style={{ fontSize: 11, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>MRN</div>
          <div className="font-mono" style={{ fontSize: 12, fontWeight: 500, color: '#E7EBF2' }}>{patient.mrn}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>{t('patient.studies')}</div>
          <div style={{ fontSize: 17, fontWeight: 700, color: '#E7EBF2' }}>{patient.study_count ?? 0}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: '#767E8E', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>{t('patient.documents')}</div>
          <div style={{ fontSize: 17, fontWeight: 700, color: '#E7EBF2' }}>{patient.document_count ?? 0}</div>
        </div>
      </div>

      {/* Footer — View Patient button (same as View Study in StudyCard) */}
      {onSelect && (
        <div className="border-t border-gray-700" style={{ padding: 8 }}>
          <button onClick={(e) => { e.stopPropagation(); onSelect(); }}
            className="w-full flex items-center justify-center border border-gray-600 hover:bg-gray-700 transition-colors"
            style={{ height: 36, gap: 6, borderRadius: 6, fontSize: 13, fontWeight: 500, color: '#E7EBF2' }}>
            <ChevronRight style={{ width: 16, height: 16 }} />
            {t('patient.viewPatient', 'View Patient')}
          </button>
        </div>
      )}
    </motion.div>
  );
}
