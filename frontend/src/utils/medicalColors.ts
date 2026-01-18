/**
 * Medical Color Standards Utility
 *
 * Color definitions following healthcare UI standards and safety guidelines.
 *
 * References:
 * - ANSI/ISEA Z535: Safety Color Codes
 * - ISO 3864-4: Safety colours and safety signs
 * - Joint Commission (TJC) best practices
 * - Epic/Cerner/Athenahealth UI patterns
 * - WCAG 2.1 AA contrast requirements (4.5:1 for text)
 *
 * Color Categories:
 * 1. Status Colors - Patient/clinical status indicators
 * 2. Alert Colors - Severity-based alert system
 * 3. Priority Colors - Task/action prioritization
 * 4. Clinical Colors - Medical specialty indicators
 * 5. Safety Colors - ANSI/ISO safety compliance
 */

// ============================================================================
// STATUS COLORS - Patient and clinical status indicators
// ============================================================================

export const STATUS_COLORS = {
  /** Active/healthy - Green indicates normal, stable, or positive status */
  active: {
    bg: 'bg-emerald-50 dark:bg-emerald-900/20',
    bgSolid: 'bg-emerald-500',
    border: 'border-emerald-200 dark:border-emerald-800',
    text: 'text-emerald-700 dark:text-emerald-400',
    dot: 'bg-emerald-500',
    hex: '#10B981', // For charts/graphs
  },
  /** Inactive/discharged - Gray indicates historical or inactive */
  inactive: {
    bg: 'bg-slate-50 dark:bg-slate-800/50',
    bgSolid: 'bg-slate-400',
    border: 'border-slate-200 dark:border-slate-700',
    text: 'text-slate-600 dark:text-slate-400',
    dot: 'bg-slate-400',
    hex: '#94A3B8',
  },
  /** Deceased - Dark gray, respectful tone */
  deceased: {
    bg: 'bg-gray-100 dark:bg-gray-800',
    bgSolid: 'bg-gray-500',
    border: 'border-gray-300 dark:border-gray-600',
    text: 'text-gray-700 dark:text-gray-300',
    dot: 'bg-gray-500',
    hex: '#6B7280',
  },
  /** Pending - Yellow/amber for awaiting action */
  pending: {
    bg: 'bg-amber-50 dark:bg-amber-900/20',
    bgSolid: 'bg-amber-500',
    border: 'border-amber-200 dark:border-amber-700',
    text: 'text-amber-700 dark:text-amber-400',
    dot: 'bg-amber-500',
    hex: '#F59E0B',
  },
  /** In Progress - Blue for ongoing actions */
  inProgress: {
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    bgSolid: 'bg-blue-500',
    border: 'border-blue-200 dark:border-blue-700',
    text: 'text-blue-700 dark:text-blue-400',
    dot: 'bg-blue-500 animate-pulse',
    hex: '#3B82F6',
  },
  /** Completed - Green with check indication */
  completed: {
    bg: 'bg-green-50 dark:bg-green-900/20',
    bgSolid: 'bg-green-500',
    border: 'border-green-200 dark:border-green-700',
    text: 'text-green-700 dark:text-green-400',
    dot: 'bg-green-500',
    hex: '#22C55E',
  },
  /** Cancelled - Neutral gray with strikethrough indication */
  cancelled: {
    bg: 'bg-gray-50 dark:bg-gray-800/50',
    bgSolid: 'bg-gray-400',
    border: 'border-gray-200 dark:border-gray-700',
    text: 'text-gray-500 dark:text-gray-500 line-through',
    dot: 'bg-gray-400',
    hex: '#9CA3AF',
  },
} as const;

// ============================================================================
// ALERT COLORS - Clinical severity levels (based on WHO/triage standards)
// ============================================================================

export const ALERT_COLORS = {
  /**
   * Critical/Immediate - Red
   * Life-threatening conditions requiring immediate intervention
   * Examples: Code Blue, allergic reaction, cardiac arrest
   */
  critical: {
    bg: 'bg-red-50 dark:bg-red-900/30',
    bgSolid: 'bg-red-600',
    border: 'border-red-300 dark:border-red-700',
    text: 'text-red-800 dark:text-red-200',
    icon: 'text-red-600 dark:text-red-400',
    ring: 'ring-red-500',
    hex: '#DC2626',
    animate: 'animate-pulse',
  },
  /**
   * High/Urgent - Orange
   * Requires prompt attention (within 1 hour)
   * Examples: Severe pain, abnormal vital signs
   */
  high: {
    bg: 'bg-orange-50 dark:bg-orange-900/20',
    bgSolid: 'bg-orange-500',
    border: 'border-orange-300 dark:border-orange-700',
    text: 'text-orange-800 dark:text-orange-200',
    icon: 'text-orange-600 dark:text-orange-400',
    ring: 'ring-orange-500',
    hex: '#F97316',
    animate: '',
  },
  /**
   * Medium/Warning - Amber/Yellow
   * Requires attention soon (within 4 hours)
   * Examples: Medication due, follow-up needed
   */
  medium: {
    bg: 'bg-amber-50 dark:bg-amber-900/20',
    bgSolid: 'bg-amber-500',
    border: 'border-amber-300 dark:border-amber-700',
    text: 'text-amber-800 dark:text-amber-200',
    icon: 'text-amber-600 dark:text-amber-400',
    ring: 'ring-amber-500',
    hex: '#F59E0B',
    animate: '',
  },
  /**
   * Low/Informational - Blue
   * Non-urgent, informational
   * Examples: Lab results available, appointment reminder
   */
  low: {
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    bgSolid: 'bg-blue-500',
    border: 'border-blue-200 dark:border-blue-700',
    text: 'text-blue-700 dark:text-blue-300',
    icon: 'text-blue-600 dark:text-blue-400',
    ring: 'ring-blue-500',
    hex: '#3B82F6',
    animate: '',
  },
  /**
   * Success - Green
   * Positive outcomes, completed actions
   */
  success: {
    bg: 'bg-green-50 dark:bg-green-900/20',
    bgSolid: 'bg-green-500',
    border: 'border-green-200 dark:border-green-700',
    text: 'text-green-700 dark:text-green-300',
    icon: 'text-green-600 dark:text-green-400',
    ring: 'ring-green-500',
    hex: '#22C55E',
    animate: '',
  },
} as const;

// ============================================================================
// ALLERGY/SAFETY ALERT COLORS
// ============================================================================

export const ALLERGY_COLORS = {
  /** Drug allergy - Red background, most critical */
  drug: {
    bg: 'bg-red-100 dark:bg-red-900/40',
    bgBanner: 'bg-red-500',
    border: 'border-red-400 dark:border-red-600',
    text: 'text-red-900 dark:text-red-100',
    badge: 'bg-red-600 text-white',
    hex: '#EF4444',
  },
  /** Food allergy - Orange */
  food: {
    bg: 'bg-orange-100 dark:bg-orange-900/40',
    bgBanner: 'bg-orange-500',
    border: 'border-orange-400 dark:border-orange-600',
    text: 'text-orange-900 dark:text-orange-100',
    badge: 'bg-orange-600 text-white',
    hex: '#F97316',
  },
  /** Environmental allergy - Yellow/amber */
  environmental: {
    bg: 'bg-amber-100 dark:bg-amber-900/40',
    bgBanner: 'bg-amber-500',
    border: 'border-amber-400 dark:border-amber-600',
    text: 'text-amber-900 dark:text-amber-100',
    badge: 'bg-amber-600 text-white',
    hex: '#F59E0B',
  },
  /** Other/unknown allergy */
  other: {
    bg: 'bg-purple-100 dark:bg-purple-900/40',
    bgBanner: 'bg-purple-500',
    border: 'border-purple-400 dark:border-purple-600',
    text: 'text-purple-900 dark:text-purple-100',
    badge: 'bg-purple-600 text-white',
    hex: '#8B5CF6',
  },
} as const;

// ============================================================================
// GENDER COLORS - Following common medical UI conventions
// ============================================================================

export const GENDER_COLORS = {
  male: {
    text: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    border: 'border-blue-200 dark:border-blue-800',
    symbol: '♂',
    hex: '#3B82F6',
  },
  female: {
    text: 'text-pink-600 dark:text-pink-400',
    bg: 'bg-pink-50 dark:bg-pink-900/20',
    border: 'border-pink-200 dark:border-pink-800',
    symbol: '♀',
    hex: '#EC4899',
  },
  other: {
    text: 'text-purple-600 dark:text-purple-400',
    bg: 'bg-purple-50 dark:bg-purple-900/20',
    border: 'border-purple-200 dark:border-purple-800',
    symbol: '⚧',
    hex: '#8B5CF6',
  },
  unknown: {
    text: 'text-gray-500 dark:text-gray-400',
    bg: 'bg-gray-50 dark:bg-gray-800',
    border: 'border-gray-200 dark:border-gray-700',
    symbol: '○',
    hex: '#6B7280',
  },
} as const;

// ============================================================================
// MODALITY COLORS - Medical imaging modalities
// ============================================================================

export const MODALITY_COLORS = {
  CT: {
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    bgSolid: 'bg-blue-500',
    text: 'text-blue-700 dark:text-blue-300',
    hex: '#3B82F6',
  },
  MR: {
    bg: 'bg-purple-50 dark:bg-purple-900/20',
    bgSolid: 'bg-purple-500',
    text: 'text-purple-700 dark:text-purple-300',
    hex: '#8B5CF6',
  },
  US: {
    bg: 'bg-cyan-50 dark:bg-cyan-900/20',
    bgSolid: 'bg-cyan-500',
    text: 'text-cyan-700 dark:text-cyan-300',
    hex: '#06B6D4',
  },
  XR: {
    bg: 'bg-slate-50 dark:bg-slate-800/50',
    bgSolid: 'bg-slate-500',
    text: 'text-slate-700 dark:text-slate-300',
    hex: '#64748B',
  },
  MG: {
    bg: 'bg-pink-50 dark:bg-pink-900/20',
    bgSolid: 'bg-pink-500',
    text: 'text-pink-700 dark:text-pink-300',
    hex: '#EC4899',
  },
  NM: {
    bg: 'bg-emerald-50 dark:bg-emerald-900/20',
    bgSolid: 'bg-emerald-500',
    text: 'text-emerald-700 dark:text-emerald-300',
    hex: '#10B981',
  },
  PT: {
    bg: 'bg-orange-50 dark:bg-orange-900/20',
    bgSolid: 'bg-orange-500',
    text: 'text-orange-700 dark:text-orange-300',
    hex: '#F97316',
  },
  CR: {
    bg: 'bg-gray-50 dark:bg-gray-800/50',
    bgSolid: 'bg-gray-500',
    text: 'text-gray-700 dark:text-gray-300',
    hex: '#6B7280',
  },
  DX: {
    bg: 'bg-gray-50 dark:bg-gray-800/50',
    bgSolid: 'bg-gray-500',
    text: 'text-gray-700 dark:text-gray-300',
    hex: '#6B7280',
  },
  OT: {
    bg: 'bg-gray-50 dark:bg-gray-800/50',
    bgSolid: 'bg-gray-400',
    text: 'text-gray-600 dark:text-gray-400',
    hex: '#9CA3AF',
  },
} as const;

// ============================================================================
// DOCUMENT CATEGORY COLORS
// ============================================================================

export const DOCUMENT_CATEGORY_COLORS = {
  'lab-result': {
    bg: 'bg-emerald-50 dark:bg-emerald-900/20',
    icon: 'text-emerald-600 dark:text-emerald-400',
    hex: '#10B981',
  },
  'prescription': {
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    icon: 'text-blue-600 dark:text-blue-400',
    hex: '#3B82F6',
  },
  'clinical-note': {
    bg: 'bg-purple-50 dark:bg-purple-900/20',
    icon: 'text-purple-600 dark:text-purple-400',
    hex: '#8B5CF6',
  },
  'discharge-summary': {
    bg: 'bg-amber-50 dark:bg-amber-900/20',
    icon: 'text-amber-600 dark:text-amber-400',
    hex: '#F59E0B',
  },
  'radiology-report': {
    bg: 'bg-cyan-50 dark:bg-cyan-900/20',
    icon: 'text-cyan-600 dark:text-cyan-400',
    hex: '#06B6D4',
  },
  'consent-form': {
    bg: 'bg-slate-50 dark:bg-slate-800/50',
    icon: 'text-slate-600 dark:text-slate-400',
    hex: '#64748B',
  },
  'referral': {
    bg: 'bg-indigo-50 dark:bg-indigo-900/20',
    icon: 'text-indigo-600 dark:text-indigo-400',
    hex: '#6366F1',
  },
  'operative-note': {
    bg: 'bg-rose-50 dark:bg-rose-900/20',
    icon: 'text-rose-600 dark:text-rose-400',
    hex: '#F43F5E',
  },
  'pathology-report': {
    bg: 'bg-pink-50 dark:bg-pink-900/20',
    icon: 'text-pink-600 dark:text-pink-400',
    hex: '#EC4899',
  },
  'other': {
    bg: 'bg-gray-50 dark:bg-gray-800/50',
    icon: 'text-gray-600 dark:text-gray-400',
    hex: '#6B7280',
  },
} as const;

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Get status color object by status key
 */
export function getStatusColor(status: string) {
  return STATUS_COLORS[status as keyof typeof STATUS_COLORS] || STATUS_COLORS.inactive;
}

/**
 * Get alert color object by severity
 */
export function getAlertColor(severity: string) {
  return ALERT_COLORS[severity as keyof typeof ALERT_COLORS] || ALERT_COLORS.low;
}

/**
 * Get gender color object
 */
export function getGenderColor(gender: string) {
  return GENDER_COLORS[gender as keyof typeof GENDER_COLORS] || GENDER_COLORS.unknown;
}

/**
 * Get modality color object
 */
export function getModalityColor(modality: string) {
  return MODALITY_COLORS[modality as keyof typeof MODALITY_COLORS] || MODALITY_COLORS.OT;
}

/**
 * Get document category color object
 */
export function getDocumentCategoryColor(category: string) {
  return DOCUMENT_CATEGORY_COLORS[category as keyof typeof DOCUMENT_CATEGORY_COLORS] || DOCUMENT_CATEGORY_COLORS.other;
}

// Type exports for TypeScript consumers
export type StatusType = keyof typeof STATUS_COLORS;
export type AlertSeverity = keyof typeof ALERT_COLORS;
export type GenderType = keyof typeof GENDER_COLORS;
export type ModalityType = keyof typeof MODALITY_COLORS;
export type DocumentCategory = keyof typeof DOCUMENT_CATEGORY_COLORS;
