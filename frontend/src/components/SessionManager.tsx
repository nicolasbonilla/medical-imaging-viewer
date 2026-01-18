/**
 * SessionManager - Global Session Timeout Management
 *
 * Integrates session timeout functionality at the application level.
 * This component should wrap the main app content inside AuthProvider.
 *
 * HIPAA Security Rule Compliance:
 * - § 164.312(a)(2)(iii): Automatic logoff
 * - 15-minute timeout standard for healthcare applications
 */

import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/contexts/AuthContext';
import { useSessionTimeout } from '@/hooks/useSessionTimeout';
import { SessionTimeoutWarning } from '@/components/SessionTimeoutWarning';

interface SessionManagerProps {
  children: React.ReactNode;
  /** Custom timeout in minutes (default: 15) */
  timeoutMinutes?: number;
  /** Custom warning time before logout in minutes (default: 2) */
  warningMinutes?: number;
}

export function SessionManager({
  children,
  timeoutMinutes = 15,
  warningMinutes = 2,
}: SessionManagerProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { isAuthenticated, logout } = useAuth();

  // Handle session timeout
  const handleTimeout = useCallback(() => {
    logout();
    toast.error(t('session.expired'));
    navigate('/login', { replace: true });
  }, [logout, navigate, t]);

  // Use the session timeout hook
  const {
    showWarning,
    remainingSeconds,
    extendSession,
  } = useSessionTimeout({
    timeoutDuration: timeoutMinutes * 60 * 1000,
    warningDuration: warningMinutes * 60 * 1000,
    onTimeout: handleTimeout,
    enabled: isAuthenticated,
  });

  // Handle user extending session
  const handleExtend = useCallback(() => {
    extendSession();
    toast.success(t('session.extendedSuccess'));
  }, [extendSession, t]);

  // Handle user choosing to logout
  const handleLogoutNow = useCallback(() => {
    logout();
    navigate('/login', { replace: true });
  }, [logout, navigate]);

  return (
    <>
      {children}

      {/* Session Timeout Warning Modal */}
      <SessionTimeoutWarning
        isOpen={showWarning && isAuthenticated}
        remainingSeconds={remainingSeconds}
        onExtend={handleExtend}
        onLogout={handleLogoutNow}
      />
    </>
  );
}

export default SessionManager;
