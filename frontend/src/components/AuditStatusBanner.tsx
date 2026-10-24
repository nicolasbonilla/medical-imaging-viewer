/**
 * AuditStatusBanner — CAPA-015, RC-067 (REQ-SEC-024; HAZ-010).
 *
 * Administrators see, on every page, when the server cannot write the audit trail to its
 * durable store (Firestore `audit_logs`): records are then queued and retried, and kept in the
 * server log, but the trail an auditor reads is incomplete until it recovers. The status is per
 * server instance; polling every minute samples whichever instance answers. Nothing is shown to
 * other roles, and nothing when writing works.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ShieldAlert } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { apiClient } from '@/services/apiClient';

interface AuditStatus {
  state: 'ok' | 'degraded' | 'failing' | 'not_durable' | 'off';
  queue_depth: number;
  last_error?: string | null;
}

const POLL_MS = 60_000;

export function AuditStatusBanner() {
  const { t } = useTranslation();
  const { user, isAuthenticated } = useAuth();
  const isAdmin = String(user?.role ?? '').toLowerCase() === 'admin';
  const [status, setStatus] = useState<AuditStatus | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !isAdmin) {
      setStatus(null);
      return undefined;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await apiClient.get('/api/v1/auth/audit-status');
        if (!cancelled) setStatus(res.data);
      } catch { /* keep the last known status */ }
    };
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [isAuthenticated, isAdmin]);

  if (!isAdmin || !status || status.state === 'ok') return null;

  const message = status.state === 'failing'
    ? t('audit.statusFailing', { count: status.queue_depth })
    : status.state === 'degraded'
      ? t('audit.statusDegraded', { count: status.queue_depth })
      : t('audit.statusNotDurable');

  return (
    <div
      role="alert"
      data-testid="audit-status-banner"
      className="fixed inset-x-0 top-0 z-[90] flex items-start gap-2 border-b border-red-500/50 bg-red-950/95 px-4 py-2 text-sm text-red-100"
    >
      <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <p>
        <strong>{t('audit.statusTitle')}: </strong>
        {message}
        {status.last_error ? ` ${t('audit.statusLastError', { error: status.last_error })}` : ''}
      </p>
    </div>
  );
}

export default AuditStatusBanner;
