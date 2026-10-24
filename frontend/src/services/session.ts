/**
 * Session continuation — CAPA-015, RC-068 / RC-069 (REQ-SEC-025, REQ-SEC-026; HAZ-010, HAZ-001).
 *
 * Found (main @ 70cc5c7): one 60-minute access token and no refresh route. After an hour every
 * request failed with 401; saving a segmentation failed, and the only way back — signing in again —
 * left the page and discarded the mask held in memory. A 401 on the global axios instance sent the
 * browser to /login at once.
 *
 * Now:
 * - the access token is short-lived (15 min) and is renewed SILENTLY about two minutes before the
 *   EARLIER of its own expiry and the end of the refresh session (review M1), through
 *   `POST /api/v1/auth/refresh` on the app's OWN origin (Firebase Hosting forwards
 *   /api/v1/auth/** to the API), so the HttpOnly, Secure, SameSite=Strict refresh cookie is sent.
 *   The refresh token is never visible to page scripts;
 * - a request refused with 401 triggers ONE refresh (shared by concurrent requests and, through
 *   the Web Locks API, by other tabs; given up after 15 s so the lock is never held forever,
 *   review m13) and is retried with the new token;
 * - if the session cannot be continued — refresh refused (401/403), or the refresh endpoint absent
 *   (404/405, e.g. during a deployment, review M4) — nothing is discarded: the page stays, the work
 *   stays in memory, the re-login dialog opens, and the refused requests WAIT and are retried after
 *   the same user signs in again (a 401 means the server did not act on them);
 * - several tabs (review M2): the token is shared through localStorage, but each tab remembers
 *   WHOSE work it shows (`setSessionUser`). A token cleared by another tab (logout, expiry) or
 *   written for ANOTHER user is never used here: this tab opens the dialog instead of losing its
 *   work, and never navigates away. A new token for the same user written by another tab
 *   (refresh, re-login) resumes this tab and closes its dialog.
 */
import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';

export const ACCESS_TOKEN_KEY = 'access_token';
export const ACCESS_EXPIRES_KEY = 'access_token_expires_at';
export const SESSION_EXPIRES_KEY = 'refresh_session_expires_at';
export const ACTIVITY_KEY = 'mstool_last_activity';
const LEGACY_REFRESH_KEY = 'refresh_token';
const REFRESH_LEAD_MS = 120_000;       // renew this long before the earlier deadline
const MIN_DELAY_MS = 5_000;
const NETWORK_RETRY_MS = 30_000;
export const REFRESH_TIMEOUT_MS = 15_000;
const LOCK_NAME = 'mstool-auth-refresh';

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/** Origin serving /api/v1/auth: the app's own origin (hosting rewrite / dev proxy) unless overridden. */
export function authOrigin(): string {
  const explicit = import.meta.env.VITE_AUTH_BASE_URL as string | undefined;
  if (explicit) return explicit.replace(/\/+$/, '');
  if (typeof window !== 'undefined' && window.location?.origin && window.location.origin !== 'null') {
    return window.location.origin;
  }
  return API_BASE_URL;
}

export function authUrl(path: string): string {
  return `${authOrigin()}/api/v1/auth${path}`;
}

/** Axios instance for /auth calls: same origin, cookies included, no retry interceptors, bounded. */
export const authClient: AxiosInstance = axios.create({
  withCredentials: true,
  timeout: REFRESH_TIMEOUT_MS,
  headers: { 'Content-Type': 'application/json' },
});

export class SessionExpiredError extends Error {
  constructor(message = 'Session expired') {
    super(message);
    this.name = 'SessionExpiredError';
  }
}

type SessionStatus = 'active' | 'expired';
let status: SessionStatus = 'active';
const listeners = new Set<() => void>();
let waiters: Array<{ resolve: (token: string) => void; reject: (e: unknown) => void }> = [];
let inflight: Promise<string> | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;
let myUserId: string | null = null;          // whose work this tab shows
let expiredWithToken: string | null = null;  // the shared token when this tab's session ended

function notify(): void {
  listeners.forEach((l) => {
    try { l(); } catch { /* a listener must not break the others */ }
  });
}

export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function getSessionStatus(): SessionStatus {
  return status;
}

/** The user whose work this tab shows (null when signed out). */
export function setSessionUser(userId: string | null): void {
  myUserId = userId;
}

export function getSessionUser(): string | null {
  return myUserId;
}

/** The `user_id` claim of a JWT (no verification: only to tell whose token it is). */
export function tokenUserId(token: string | null | undefined): string | null {
  if (!token) return null;
  const part = token.split('.')[1];
  if (!part) return null;
  try {
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((part.length + 3) % 4));
    const claims = JSON.parse(json);
    return typeof claims?.user_id === 'string' ? claims.user_id : null;
  } catch {
    return null;
  }
}

function readSharedToken(): string | null {
  try { return localStorage.getItem(ACCESS_TOKEN_KEY); } catch { return null; }
}

function belongsToThisTab(token: string | null): boolean {
  if (!token) return false;
  const owner = tokenUserId(token);
  return !myUserId || !owner || owner === myUserId;
}

/** The shared token — only if it belongs to the user whose work this tab shows. */
export function getAccessToken(): string | null {
  const token = readSharedToken();
  return belongsToThisTab(token) ? token : null;
}

function readTime(key: string): number | null {
  try {
    const v = Number(localStorage.getItem(key));
    return Number.isFinite(v) && v > 0 ? v : null;
  } catch { return null; }
}

export function getAccessTokenExpiry(): number | null {
  return readTime(ACCESS_EXPIRES_KEY);
}

export function storeSession(accessToken: string, expiresInSec?: number, refreshExpiresInSec?: number | null): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.removeItem(LEGACY_REFRESH_KEY);
  if (expiresInSec && expiresInSec > 0) {
    localStorage.setItem(ACCESS_EXPIRES_KEY, String(Date.now() + expiresInSec * 1000));
  } else {
    localStorage.removeItem(ACCESS_EXPIRES_KEY);
  }
  if (refreshExpiresInSec && refreshExpiresInSec > 0) {
    localStorage.setItem(SESSION_EXPIRES_KEY, String(Date.now() + refreshExpiresInSec * 1000));
  } else if (refreshExpiresInSec === null || refreshExpiresInSec === 0) {
    localStorage.removeItem(SESSION_EXPIRES_KEY);
  }
  notify();
}

export function clearSession(): void {
  cancelProactiveRefresh();
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(ACCESS_EXPIRES_KEY);
  localStorage.removeItem(SESSION_EXPIRES_KEY);
  localStorage.removeItem(LEGACY_REFRESH_KEY);
  notify();
}

/** The session cannot be continued silently: ask the user to sign in again, keep everything else. */
export function markSessionExpired(): void {
  if (status === 'expired') return;
  status = 'expired';
  expiredWithToken = readSharedToken();
  cancelProactiveRefresh();
  notify();
}

export function waitForReauthentication(): Promise<string> {
  return new Promise((resolve, reject) => { waiters.push({ resolve, reject }); });
}

function resumeWith(accessToken: string): void {
  status = 'active';
  expiredWithToken = null;
  const pending = waiters;
  waiters = [];
  pending.forEach((w) => w.resolve(accessToken));
  scheduleProactiveRefresh();
  notify();
}

/** The same user signed in again (in this tab): store the token, resume every waiting request. */
export function completeReauthentication(accessToken: string, expiresInSec?: number, refreshExpiresInSec?: number | null): void {
  storeSession(accessToken, expiresInSec, refreshExpiresInSec);
  resumeWith(accessToken);
}

/**
 * Another tab may already have signed the same user in again (this tab missed its event): if the
 * shared token now belongs to this tab's user and is not the one this tab's session ended with,
 * resume with it. Used before "sign out" in a possibly stale dialog (review M2).
 */
export function tryResumeFromSharedSession(): boolean {
  const token = readSharedToken();
  if (status !== 'expired' || !token || token === expiredWithToken || !belongsToThisTab(token)) return false;
  const exp = getAccessTokenExpiry();
  if (exp !== null && exp <= Date.now()) return false;
  resumeWith(token);
  return true;
}

/** The user chose to sign out instead: the waiting requests fail. */
export function abandonReauthentication(): void {
  const pending = waiters;
  waiters = [];
  pending.forEach((w) => w.reject(new SessionExpiredError('Signed out')));
  status = 'active';
  expiredWithToken = null;
  notify();
}

async function withRefreshLock<T>(fn: () => Promise<T>): Promise<T> {
  const locks = typeof navigator !== 'undefined' ? (navigator as any).locks : undefined;
  if (locks && typeof locks.request === 'function') return locks.request(LOCK_NAME, fn);
  return fn();
}

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error('refresh timed out')), ms);
    p.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}

/** Statuses that mean "this session cannot be continued" (404/405: endpoint absent, review M4). */
const ENDED = new Set([401, 403, 404, 405]);

/** One refresh at a time (this tab and, with Web Locks, every tab). Throws SessionExpiredError when ended. */
export function refreshAccessToken(): Promise<string> {
  if (inflight) return inflight;
  const startedWith = readSharedToken();
  inflight = withRefreshLock(async () => {
    // Another tab may have refreshed while this one waited for the lock: reuse its token.
    const current = readSharedToken();
    const exp = getAccessTokenExpiry();
    if (current && current !== startedWith && belongsToThisTab(current) && exp && exp - Date.now() > REFRESH_LEAD_MS) {
      return current;
    }
    try {
      const res = await withTimeout(authClient.post(authUrl('/refresh'), null), REFRESH_TIMEOUT_MS);
      const tok = res.data?.token;
      if (!tok?.access_token) throw new SessionExpiredError('No token in the refresh response');
      const owner = res.data?.user?.id ?? tokenUserId(tok.access_token);
      if (myUserId && owner && owner !== myUserId) {
        // the browser's refresh cookie now belongs to another user (signed in in another tab)
        throw new SessionExpiredError('The session belongs to another user');
      }
      storeSession(tok.access_token, tok.expires_in, tok.refresh_expires_in ?? null);
      if (res.data?.user) localStorage.setItem('user', JSON.stringify(res.data.user));
      scheduleProactiveRefresh();
      return tok.access_token as string;
    } catch (e) {
      const st = (e as AxiosError)?.response?.status;
      if (e instanceof SessionExpiredError || (st !== undefined && ENDED.has(st))) throw new SessionExpiredError();
      throw e;
    }
  }).finally(() => { inflight = null; });
  return inflight;
}

/** A request was refused with 401: refresh silently, or wait until the user signs in again. */
export async function recoverFromUnauthorized(): Promise<string> {
  if (status === 'expired') return waitForReauthentication();
  try {
    return await refreshAccessToken();
  } catch (e) {
    if (e instanceof SessionExpiredError) {
      markSessionExpired();
      return waitForReauthentication();
    }
    throw e;
  }
}

export function cancelProactiveRefresh(): void {
  if (timer) clearTimeout(timer);
  timer = null;
}

/** Renew about two minutes before the earlier of the access token's and the refresh session's end. */
export function scheduleProactiveRefresh(): void {
  cancelProactiveRefresh();
  const accessExp = getAccessTokenExpiry();
  const sessionExp = readTime(SESSION_EXPIRES_KEY);
  const deadline = accessExp && sessionExp ? Math.min(accessExp, sessionExp) : accessExp;
  if (!deadline || !getAccessToken() || status === 'expired') return;
  const delay = Math.max(MIN_DELAY_MS, deadline - Date.now() - REFRESH_LEAD_MS);
  timer = setTimeout(async () => {
    timer = null;
    if (status === 'expired') return;
    try {
      await refreshAccessToken();
    } catch (e) {
      if (e instanceof SessionExpiredError) markSessionExpired();
      else timer = setTimeout(() => scheduleProactiveRefresh(), NETWORK_RETRY_MS);   // offline: try again soon
    }
  }, delay);
}

/**
 * Another tab changed the shared session (review M2). Never navigates; at worst opens the dialog.
 * - token removed (logout or expiry there) or written for another user -> dialog here;
 * - new token for this tab's user (refresh or re-login there) -> resume here / reschedule.
 */
function onSharedTokenChanged(): void {
  if (!myUserId) { notify(); return; }          // nobody signed in here: nothing to protect
  const token = readSharedToken();
  if (!token || !belongsToThisTab(token)) {
    markSessionExpired();
    return;
  }
  if (status === 'expired') {
    if (token !== expiredWithToken) resumeWith(token);
    return;
  }
  scheduleProactiveRefresh();
  notify();
}

/** Other tabs renew the shared token; a tab coming back to the foreground catches up. */
export function installSessionListeners(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const onStorage = (e: StorageEvent) => {
    if (e.key === ACCESS_TOKEN_KEY || e.key === null) onSharedTokenChanged();
    else if (e.key === ACCESS_EXPIRES_KEY || e.key === SESSION_EXPIRES_KEY) {
      if (status !== 'expired') scheduleProactiveRefresh();
    }
  };
  const onVisible = () => {
    if (document.visibilityState !== 'visible' || status === 'expired' || !getAccessToken()) return;
    const exp = getAccessTokenExpiry();
    if (exp && exp - Date.now() <= REFRESH_LEAD_MS) {
      refreshAccessToken().catch((e) => { if (e instanceof SessionExpiredError) markSessionExpired(); });
    } else {
      scheduleProactiveRefresh();
    }
  };
  window.addEventListener('storage', onStorage);
  document.addEventListener('visibilitychange', onVisible);
  return () => {
    window.removeEventListener('storage', onStorage);
    document.removeEventListener('visibilitychange', onVisible);
  };
}

const AUTH_ENDPOINT = /\/api\/v1\/auth\/(login|refresh|logout|register|captcha|webauthn\/login)/;

function absoluteUrl(config: InternalAxiosRequestConfig): string {
  const url = config.url ?? '';
  if (/^https?:\/\//i.test(url)) return url;
  return `${(config.baseURL ?? '').replace(/\/+$/, '')}${url.startsWith('/') ? '' : '/'}${url}`;
}

/** Only our own API ever receives the bearer token. */
function targetsOurApi(config: InternalAxiosRequestConfig): boolean {
  const url = absoluteUrl(config);
  if (!/^https?:\/\//i.test(url)) return true;            // relative to the app itself
  return url.startsWith(API_BASE_URL) || url.startsWith(authOrigin());
}

/** True while this tab holds a session (its own token, or a session that ended and awaits re-login). */
function tabHasSession(): boolean {
  return Boolean(getAccessToken() || myUserId || status === 'expired');
}

/** Bearer token on every request to our API; silent refresh + retry on 401; never a redirect. */
export function installAuthInterceptors(instance: AxiosInstance): () => void {
  const req = instance.interceptors.request.use((config) => {
    const token = getAccessToken();
    if (token && targetsOurApi(config)) {
      config.headers = config.headers ?? ({} as any);
      (config.headers as any).Authorization = `Bearer ${token}`;
    } else if (config.headers && targetsOurApi(config)) {
      delete (config.headers as any).Authorization;      // never another user's (or a stale) token
    }
    return config;
  });
  const res = instance.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const config = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;
      if (!config || error.response?.status !== 401 || config._retry
          || AUTH_ENDPOINT.test(config.url ?? '') || !targetsOurApi(config) || !tabHasSession()) {
        return Promise.reject(error);
      }
      config._retry = true;
      let token: string;
      try {
        token = await recoverFromUnauthorized();
      } catch {
        return Promise.reject(error);
      }
      (config.headers as any).Authorization = `Bearer ${token}`;
      return instance(config);
    },
  );
  return () => {
    instance.interceptors.request.eject(req);
    instance.interceptors.response.eject(res);
  };
}

/** fetch() with the bearer token and the same 401 recovery (volumes, exports). Any Authorization
 *  header the caller passed is dropped (re-review N3): only this tab's own token is ever sent. */
export async function fetchWithSession(url: string, init: RequestInit = {}): Promise<Response> {
  const raw = init.headers;
  const entries: Array<[string, string]> = typeof Headers !== 'undefined' && raw instanceof Headers
    ? Array.from(raw.entries())
    : Array.isArray(raw) ? (raw as Array<[string, string]>) : Object.entries((raw as Record<string, string>) ?? {});
  const callerHeaders: Record<string, string> = {};
  for (const [k, v] of entries) {
    if (k.toLowerCase() !== 'authorization') callerHeaders[k] = v;
  }
  const send = (token: string | null) => fetch(url, {
    ...init,
    headers: { ...callerHeaders, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });
  const first = await send(getAccessToken());
  if (first.status !== 401 || !tabHasSession()) return first;
  try {
    return await send(await recoverFromUnauthorized());
  } catch {
    return first;
  }
}
