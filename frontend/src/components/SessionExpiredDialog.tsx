/**
 * SessionExpiredDialog — CAPA-015, RC-069 (REQ-SEC-026; HAZ-001, HAZ-010).
 *
 * Shown when the session cannot be continued silently (refresh refused: idle or absolute limit,
 * logout elsewhere, password change, reuse detected, account disabled). The page underneath is
 * NOT left: unsaved segmentation work stays in memory and the requests that were refused wait,
 * then run once the user signs in again.
 *
 * Only the user whose work is on screen may continue (the user name is fixed): if another person
 * authenticates here, their new session is closed at once and an explanation is shown — work must
 * never be saved under someone else's name. "Sign out" is offered, with a warning, because it
 * discards the unsaved changes.
 */
import { FormEvent, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { LockKeyhole } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { authClient, authUrl } from '@/services/session';

interface Captcha {
  challenge_id: string;
  challenge_text: string;
}

function errorDetail(err: any): string {
  return String(err?.response?.data?.detail ?? err?.response?.data?.error?.message ?? '');
}

export function SessionExpiredDialog() {
  const { t } = useTranslation();
  const { user, sessionExpired, reauthenticate, reauthenticateWithPasskey, signOutFromDialog } = useAuth();
  const hasUnsaved = useSegmentationStore((s) => s.hasUnsavedMaskChanges);
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [captcha, setCaptcha] = useState<Captcha | null>(null);
  const [captchaAnswer, setCaptchaAnswer] = useState('');
  const [confirmSignOut, setConfirmSignOut] = useState(false);
  const passwordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (sessionExpired) passwordRef.current?.focus();
    if (!sessionExpired) {
      setPassword('');
      setError(null);
      setCaptcha(null);
      setCaptchaAnswer('');
      setConfirmSignOut(false);
    }
  }, [sessionExpired]);

  if (!sessionExpired || !user) return null;

  const fail = async (err: any) => {
    if (err?.name === 'WrongUserError') {
      setError(t('session.reauthWrongUser', { username: user.username }));
    } else if (err?.response?.status === 400 && /captcha/i.test(errorDetail(err))) {
      try {
        const res = await authClient.post(authUrl('/captcha'), { difficulty: 'medium' });
        setCaptcha(res.data);
        setCaptchaAnswer('');
      } catch { /* the message below still explains */ }
      setError(t('session.reauthCaptcha'));
    } else {
      setError(t('session.reauthFailed'));
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!password || busy) return;
    setBusy(true);
    setError(null);
    try {
      await reauthenticate(password, captcha ? { id: captcha.challenge_id, response: captchaAnswer } : undefined);
    } catch (err) {
      await fail(err);
    } finally {
      setBusy(false);
    }
  };

  const withPasskey = async () => {
    setBusy(true);
    setError(null);
    try {
      await reauthenticateWithPasskey();
    } catch (err: any) {
      if (err?.name !== 'NotAllowedError') await fail(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/70 p-4">
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="reauth-title"
        aria-describedby="reauth-message"
        onSubmit={submit}
        className="w-full max-w-md rounded-2xl border border-white/10 bg-[#11141A] p-6 text-gray-100 shadow-2xl"
      >
        <div className="mb-3 flex items-center gap-2">
          <LockKeyhole className="h-5 w-5 text-amber-400" aria-hidden />
          <h2 id="reauth-title" className="text-lg font-semibold">{t('session.reauthTitle')}</h2>
        </div>
        <p id="reauth-message" className="mb-2 text-sm text-gray-300">{t('session.reauthMessage')}</p>
        {hasUnsaved && (
          <p data-testid="reauth-unsaved" className="mb-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-sm text-amber-200">
            {t('session.reauthUnsaved')}
          </p>
        )}
        <p className="mb-4 text-xs text-gray-400">{t('session.reauthSignedInAs', { username: user.username })}</p>

        <label htmlFor="reauth-password" className="mb-1 block text-xs font-medium text-gray-300">
          {t('session.reauthPassword')}
        </label>
        <input
          id="reauth-password"
          ref={passwordRef}
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mb-3 w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-cyan-400"
        />

        {captcha && (
          <div className="mb-3">
            <label htmlFor="reauth-captcha" className="mb-1 block text-xs font-medium text-gray-300">
              {t('session.reauthCaptchaLabel')}
            </label>
            <p className="mb-1 text-center font-mono text-xl tracking-widest">{captcha.challenge_text}</p>
            <input
              id="reauth-captcha"
              type="text"
              autoComplete="off"
              value={captchaAnswer}
              onChange={(e) => setCaptchaAnswer(e.target.value)}
              className="w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm outline-none focus:border-cyan-400"
            />
          </div>
        )}

        {error && (
          <p role="alert" data-testid="reauth-error" className="mb-3 text-sm text-red-300">{error}</p>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="submit"
            disabled={busy || !password}
            className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {t('session.reauthSubmit')}
          </button>
          <button
            type="button"
            onClick={withPasskey}
            disabled={busy}
            className="rounded-lg border border-white/15 px-4 py-2 text-sm"
          >
            {t('session.reauthPasskey')}
          </button>
          <button
            type="button"
            onClick={() => setConfirmSignOut(true)}
            className="ml-auto text-xs text-gray-400 underline"
          >
            {t('session.reauthSignOut')}
          </button>
        </div>

        {confirmSignOut && (
          <div className="mt-4 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm">
            <p className="mb-2 text-red-200">{t('session.reauthSignOutWarning')}</p>
            <div className="flex gap-2">
              <button type="button" onClick={() => signOutFromDialog()} className="rounded-md bg-red-600 px-3 py-1.5 text-xs text-white">
                {t('session.reauthSignOutConfirm')}
              </button>
              <button type="button" onClick={() => setConfirmSignOut(false)} className="rounded-md border border-white/15 px-3 py-1.5 text-xs">
                {t('session.reauthCancel')}
              </button>
            </div>
          </div>
        )}
      </form>
    </div>
  );
}

export default SessionExpiredDialog;
