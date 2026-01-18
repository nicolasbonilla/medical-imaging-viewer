/**
 * SessionTimeoutWarning - HIPAA Compliant Session Warning Modal
 *
 * Displays a warning to users before automatic logout due to inactivity.
 * Follows healthcare UX patterns from Epic, Cerner, and other major EHR systems.
 *
 * Features:
 * - Clear countdown timer
 * - Option to extend session
 * - WCAG 2.1 AA accessible
 * - Urgent but not alarming visual design
 */

import { useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { Clock, LogOut, RefreshCw, AlertTriangle } from 'lucide-react';

interface SessionTimeoutWarningProps {
  /** Whether to show the warning modal */
  isOpen: boolean;
  /** Seconds remaining before logout */
  remainingSeconds: number;
  /** Handler when user clicks "Stay Logged In" */
  onExtend: () => void;
  /** Handler when user clicks "Log Out Now" */
  onLogout: () => void;
}

/**
 * Format seconds into MM:SS display
 */
function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Get urgency level based on remaining time
 */
function getUrgencyLevel(seconds: number): 'normal' | 'warning' | 'critical' {
  if (seconds <= 30) return 'critical';
  if (seconds <= 60) return 'warning';
  return 'normal';
}

export function SessionTimeoutWarning({
  isOpen,
  remainingSeconds,
  onExtend,
  onLogout,
}: SessionTimeoutWarningProps) {
  const { t } = useTranslation();
  const extendButtonRef = useRef<HTMLButtonElement>(null);
  const urgency = getUrgencyLevel(remainingSeconds);

  // Focus the extend button when modal opens (accessibility)
  useEffect(() => {
    if (isOpen && extendButtonRef.current) {
      extendButtonRef.current.focus();
    }
  }, [isOpen]);

  // Handle keyboard events
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      // Enter extends session
      if (e.key === 'Enter') {
        e.preventDefault();
        onExtend();
      }
      // Escape logs out
      if (e.key === 'Escape') {
        e.preventDefault();
        onLogout();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onExtend, onLogout]);

  // Get colors based on urgency
  const urgencyColors = {
    normal: {
      bg: 'bg-amber-50 dark:bg-amber-900/20',
      border: 'border-amber-300 dark:border-amber-700',
      text: 'text-amber-800 dark:text-amber-200',
      icon: 'text-amber-600 dark:text-amber-400',
      timer: 'text-amber-700 dark:text-amber-300',
    },
    warning: {
      bg: 'bg-orange-50 dark:bg-orange-900/20',
      border: 'border-orange-300 dark:border-orange-700',
      text: 'text-orange-800 dark:text-orange-200',
      icon: 'text-orange-600 dark:text-orange-400',
      timer: 'text-orange-700 dark:text-orange-300',
    },
    critical: {
      bg: 'bg-red-50 dark:bg-red-900/20',
      border: 'border-red-300 dark:border-red-700',
      text: 'text-red-800 dark:text-red-200',
      icon: 'text-red-600 dark:text-red-400',
      timer: 'text-red-700 dark:text-red-300',
    },
  };

  const colors = urgencyColors[urgency];

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm"
            aria-hidden="true"
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -20 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="fixed inset-0 z-[101] flex items-center justify-center p-4"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="session-timeout-title"
            aria-describedby="session-timeout-description"
          >
            <div
              className={`
                w-full max-w-md rounded-2xl shadow-2xl
                bg-white dark:bg-gray-900
                border-2 ${colors.border}
                overflow-hidden
              `}
            >
              {/* Header with warning indicator */}
              <div className={`px-6 py-4 ${colors.bg} border-b ${colors.border}`}>
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-full ${colors.bg}`}>
                    <AlertTriangle className={`w-6 h-6 ${colors.icon} ${urgency === 'critical' ? 'animate-pulse' : ''}`} />
                  </div>
                  <h2
                    id="session-timeout-title"
                    className={`text-lg font-bold ${colors.text}`}
                  >
                    {t('session.timeoutWarning', 'Session Expiring')}
                  </h2>
                </div>
              </div>

              {/* Content */}
              <div className="px-6 py-6">
                <p
                  id="session-timeout-description"
                  className="text-gray-600 dark:text-gray-300 mb-6"
                >
                  {t(
                    'session.timeoutMessage',
                    'Your session will expire due to inactivity. Click "Stay Logged In" to continue working.'
                  )}
                </p>

                {/* Timer Display */}
                <div className="flex flex-col items-center mb-6">
                  <div
                    className={`
                      flex items-center gap-2 px-6 py-3 rounded-xl
                      ${colors.bg} border ${colors.border}
                      ${urgency === 'critical' ? 'animate-pulse' : ''}
                    `}
                  >
                    <Clock className={`w-5 h-5 ${colors.icon}`} />
                    <span
                      className={`text-3xl font-mono font-bold ${colors.timer}`}
                      aria-live="polite"
                      aria-atomic="true"
                    >
                      {formatTime(remainingSeconds)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                    {t('session.timeRemaining', 'Time remaining')}
                  </p>
                </div>

                {/* HIPAA Notice */}
                <div className="mb-6 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                  <p className="text-xs text-gray-500 dark:text-gray-400 text-center">
                    {t(
                      'session.hipaaNotice',
                      'For security of patient health information (PHI), sessions automatically end after 15 minutes of inactivity.'
                    )}
                  </p>
                </div>

                {/* Actions */}
                <div className="flex gap-3">
                  <button
                    onClick={onLogout}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl
                      bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700
                      text-gray-700 dark:text-gray-300 font-medium
                      border border-gray-300 dark:border-gray-600
                      transition-colors duration-200"
                  >
                    <LogOut className="w-4 h-4" />
                    {t('session.logoutNow', 'Log Out Now')}
                  </button>

                  <button
                    ref={extendButtonRef}
                    onClick={onExtend}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl
                      bg-primary-500 hover:bg-primary-600
                      text-white font-bold
                      shadow-lg shadow-primary-500/20
                      transition-colors duration-200
                      focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
                  >
                    <RefreshCw className="w-4 h-4" />
                    {t('session.stayLoggedIn', 'Stay Logged In')}
                  </button>
                </div>

                {/* Keyboard hints */}
                <p className="mt-4 text-xs text-center text-gray-400 dark:text-gray-500">
                  {t(
                    'session.keyboardHint',
                    'Press Enter to stay logged in, or Escape to log out'
                  )}
                </p>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

export default SessionTimeoutWarning;
