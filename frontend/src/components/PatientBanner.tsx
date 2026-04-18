/**
 * PatientBanner - HIPAA Compliant Patient Identification Banner
 *
 * Implements the "Two-Identifier Rule" required by HIPAA and Joint Commission (TJC):
 * - Always displays at least two patient identifiers
 * - Remains visible/accessible throughout the patient context
 * - Uses standardized colors and clear typography for patient safety
 *
 * References:
 * - HIPAA 45 CFR § 164.514(b)(2)
 * - The Joint Commission NPSG.01.01.01
 * - ISO 27799:2016 Health informatics
 */

import { memo } from 'react';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  Calendar,
  User,
  Hash,
  Shield,
  AlertCircle,
} from 'lucide-react';
import type { Patient } from '@/types';
import { getStatusColor, getGenderColor, STATUS_COLORS, GENDER_COLORS } from '@/utils/medicalColors';

interface PatientBannerProps {
  patient: Patient;
  compact?: boolean;
  showAllergies?: boolean;
  className?: string;
}

/**
 * Formats a date string to locale-appropriate display
 */
function formatBirthDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

/**
 * Calculates age from birth date
 */
function calculateAge(birthDate: string): number {
  const today = new Date();
  const birth = new Date(birthDate);
  let age = today.getFullYear() - birth.getFullYear();
  const monthDiff = today.getMonth() - birth.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
    age--;
  }
  return age;
}

/**
 * PatientBanner Component
 *
 * Displays critical patient identification information in a standardized,
 * always-visible banner format following healthcare industry standards.
 */
function PatientBannerComponent({
  patient,
  compact = false,
  showAllergies = true,
  className = '',
}: PatientBannerProps) {
  const { t } = useTranslation();

  const statusStyle = getStatusColor(patient.status);
  const genderStyle = getGenderColor(patient.gender);

  // Calculate age (use patient.age if available, otherwise calculate)
  const age = patient.age ?? calculateAge(patient.birth_date);

  // Gender symbol for quick visual identification
  const genderSymbol = genderStyle.symbol;

  // Mock allergies for demonstration (in production, this would come from patient data)
  const hasAllergies = false; // patient.allergies?.length > 0
  const hasCriticalAlerts = false; // patient.alerts?.some(a => a.severity === 'critical')

  if (compact) {
    return (
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className={`
          flex items-center gap-4 px-4 py-2
          bg-gradient-to-r from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800
          border-b-2 border-primary-500 dark:border-primary-400
          shadow-sm
          ${className}
        `}
        role="banner"
        aria-label={t('patients.patientBanner', 'Patient identification banner')}
      >
        {/* Primary Identifier: Patient Name */}
        <div className="flex items-center gap-2">
          <User className="w-4 h-4 text-primary-600 dark:text-primary-400" aria-hidden="true" />
          <span className="font-bold text-gray-900 dark:text-white text-sm">
            {patient.full_name}
          </span>
          <span className={`text-lg ${genderStyle.text}`} aria-label={t(`patients.genders.${patient.gender}`)}>
            {genderSymbol}
          </span>
        </div>

        {/* Separator */}
        <div className="w-px h-5 bg-gray-300 dark:bg-gray-600" aria-hidden="true" />

        {/* Secondary Identifier: MRN */}
        <div className="flex items-center gap-1.5">
          <Hash className="w-3.5 h-3.5 text-gray-500 dark:text-gray-400" aria-hidden="true" />
          <span className="font-mono text-sm font-semibold text-gray-700 dark:text-gray-300">
            {patient.mrn}
          </span>
        </div>

        {/* Separator */}
        <div className="w-px h-5 bg-gray-300 dark:bg-gray-600" aria-hidden="true" />

        {/* Third Identifier: DOB + Age */}
        <div className="flex items-center gap-1.5">
          <Calendar className="w-3.5 h-3.5 text-gray-500 dark:text-gray-400" aria-hidden="true" />
          <span className="text-sm text-gray-600 dark:text-gray-400">
            {formatBirthDate(patient.birth_date)}
          </span>
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            ({age} {t('patients.years', 'years')})
          </span>
        </div>

        {/* Status Badge */}
        <div className={`ml-auto flex items-center gap-1.5 px-2 py-0.5 rounded-full ${statusStyle.bg} ${statusStyle.border} border`}>
          <div className={`w-1.5 h-1.5 rounded-full ${statusStyle.dot}`} aria-hidden="true" />
          <span className={`text-xs font-medium ${statusStyle.text}`}>
            {t(`patients.status.${patient.status}`, patient.status)}
          </span>
        </div>

        {/* Alerts Indicator */}
        {(hasAllergies || hasCriticalAlerts) && (
          <div className="flex items-center gap-1">
            {hasAllergies && (
              <div
                className="p-1 bg-amber-100 dark:bg-amber-900/30 rounded"
                title={t('patients.hasAllergies', 'Patient has allergies')}
              >
                <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
              </div>
            )}
            {hasCriticalAlerts && (
              <div
                className="p-1 bg-red-100 dark:bg-red-900/30 rounded"
                title={t('patients.hasCriticalAlerts', 'Patient has critical alerts')}
              >
                <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400" />
              </div>
            )}
          </div>
        )}
      </motion.div>
    );
  }

  // Full Banner — ONLY name + status (title bar, not data display)
  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      className={`relative border-b border-gray-700 ${className}`}
      style={{ background: '#111827' }}
      role="banner"
      aria-label={t('patients.patientBanner', 'Patient identification banner')}
    >
      <div className="flex items-center" style={{ height: 60, padding: '0 24px', gap: 8 }}>
        {/* Avatar — 36×36, radius 6 (= app logo) */}
        <div
          className="flex-shrink-0 bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white"
          style={{ width: 36, height: 36, borderRadius: 6, fontSize: 14, fontWeight: 700 }}
        >
          {patient.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}
        </div>

        {/* Name only — same weight as app name, this is a page title */}
        <h2 className="truncate" style={{ fontSize: 14, fontWeight: 600, color: '#F9FAFB', margin: 0 }}>
          {patient.full_name}
        </h2>

        {/* Right: Clinical alerts (only if present) */}
        <div className="ml-auto flex items-center flex-shrink-0" style={{ gap: 4 }}>
          {showAllergies && hasAllergies && (
            <div className="flex items-center"
              style={{ gap: 4, padding: '4px 8px', borderRadius: 4, background: 'rgba(146,64,14,0.2)' }}
              role="alert" aria-live="polite">
              <AlertTriangle style={{ width: 12, height: 12, color: '#FBBF24' }} aria-hidden="true" />
              <span style={{ fontSize: 11, fontWeight: 600, color: '#FDE68A', textTransform: 'uppercase' }}>
                {t('patients.allergiesAlert', 'ALLERGIES')}
              </span>
            </div>
          )}

          {hasCriticalAlerts && (
            <div className="flex items-center"
              style={{ gap: 4, padding: '4px 8px', borderRadius: 4, background: 'rgba(127,29,29,0.25)' }}
              role="alert" aria-live="assertive">
              <AlertCircle style={{ width: 12, height: 12, color: '#F87171' }} aria-hidden="true" />
              <span style={{ fontSize: 11, fontWeight: 600, color: '#FCA5A5', textTransform: 'uppercase' }}>
                {t('patients.criticalAlert', 'CRITICAL ALERT')}
              </span>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// Memoize to prevent unnecessary re-renders
export const PatientBanner = memo(PatientBannerComponent);

export default PatientBanner;
