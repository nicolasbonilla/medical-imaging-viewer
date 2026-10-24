/**
 * Session continuation — CAPA-015, RC-068 / RC-069 (REQ-SEC-025, REQ-SEC-026; HAZ-010, HAZ-001).
 *
 * Found (main @ 70cc5c7): one 60-minute access token and no refresh route. After an hour every
 * request failed with 401; saving a segmentation failed, and the only way back — signing in again —
 * left the page and discarded the mask held in memory. A 401 on the global axios instance sent the
 * browser to /login at once.
 *
 * Now:
 * - the access token is short-lived (15 min) and is renewed SILENTLY about two minutes before it
 *   expires, through `POST /api/v1/auth/refresh` on the app's OWN origin (Firebase Hosting
 *   forwards /api/v1/auth/** to the API), so the HttpOnly, Secure, SameSite=Strict refresh cookie
 *   is sent. The refresh token is never visible to page scripts;
 * - a request refused with 401 triggers ONE refresh (shared by concurrent requests and, through
 *   the Web Locks API, by other tabs) and is retried with the new token;
 * - if the session cannot be continued, nothing is discarded: the page stays, the work stays in
 *   memory, the re-login dialog opens, and the refused requests WAIT and are retried after the
 *   same user signs in again (a 401 means the server did not act on them).
 */
import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';

export const ACCESS_TOKEN_KEY = 'access_token';
export const ACCESS_EXPIRES_KEY = 'access_token_expires_at';
const LEGACY_REFRESH_KEY = 'refresh_token';
const REFRESH_LEAD_MS = 120_000;       // renew this long before expiry
const MIN_DELAY_MS = 5_000;
const NETWORK_RETRY_MS = 30_000;
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

/** Axios instance for /auth calls: same origin, cookies included, no retry interceptors. */
export const authClient: AxiosInstance = axios.create({
  withCredentials: true,
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

export function getAccessToken(): string | null {
  try { return localStorage.getItem(ACCESS_TOKEN_KEY); } catch { return null; }
}

export function getAccessTokenExpiry(): number | null {
  try {
    const v = Number(localStorage.getItem(ACCESS_EXPIRES_KEY));
    return Number.isFinite(v) && v > 0 ? v : null;
  } catch { return null; }
}

export function storeSession(accessToken: string, expiresInSec?: number): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.removeItem(LEGACY_REFRESH_KEY);
  if (expiresInSec && expiresInSec > 0) {
    localStorage.setItem(ACCESS_EXPIRES_KEY, String(Date.now() + expiresInSec * 1000));
  } else {
    localStorage.removeItem(ACCESS_EXPIRES_KEY);
  }
  notify();
}

export function clearSession(): void {
  cancelProactiveRefresh();
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(ACCESS_EXPIRES_KEY);
  localStorage.removeItem(LEGACY_REFRESH_KEY);
  notify();
}

/** The session cannot be continued silently: ask the user to sign in again, keep everything else. */
export function markSessionExpired(): void {
  if (status === 'expired') return;
  status = 'expired';
  cancelProactiveRefresh();
  notify();
}

export function waitForReauthentication(): Promise<string> {
  return new Promise((resolve, reject) => { waiters.push({ resolve, reject }); });
}

/** The same user signed in again: store the token, resume every waiting request. */
export function completeReauthentication(accessToken: string, expiresInSec?: number): void {
  storeSession(accessToken, expiresInSec);
  status = 'active';
  const pending = waiters;
  waiters = [];
  pending.forEach((w) => w.resolve(accessToken));
  scheduleProactiveRefresh();
  notify();
}

/** The user chose to sign out instead: the waiting requests fail. */
export function abandonReauthentication(): void {
  const pending = waiters;
  waiters = [];
  pending.forEach((w) => w.reject(new SessionExpiredError('Signed out')));
  status = 'active';
  notify();
}

async function withRefreshLock<T>(fn: () => Promise<T>): Promise<T> {
  const locks = typeof navigator !== 'undefined' ? (navigator as any).locks : undefined;
  if (locks && typeof locks.request === 'function') return locks.request(LOCK_NAME, fn);
  return fn();
}

/** One refresh at a time (this tab and, with Web Locks, every tab). Throws SessionExpiredError on 401/403. */
export function refreshAccessToken(): Promise<string> {
  if (inflight) return inflight;
  const startedWith = getAccessToken();
  inflight = withRefreshLock(async () => {
    // Another tab may have refreshed while this one waited for the lock: reuse its token.
    const current = getAccessToken();
    const exp = getAccessTokenExpiry();
    if (current && current !== startedWith && exp && exp - Date.now() > REFRESH_LEAD_MS) return current;
    try {
      const res = await authClient.post(authUrl('/refresh'), null);
      const tok = res.data?.token;
      if (!tok?.access_token) throw new SessionExpiredError('No token in the refresh response');
      storeSession(tok.access_token, tok.expires_in);
      if (res.data?.user) localStorage.setItem('user', JSON.stringify(res.data.user));
      scheduleProactiveRefresh();
      return tok.access_token as string;
    } catch (e) {
      const st = (e as AxiosError)?.response?.status;
      if (e instanceof SessionExpiredError || st === 401 || st === 403) throw new SessionExpiredError();
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

/** Renew the access token about two minutes before it expires. */
export function scheduleProactiveRefresh(): void {
  cancelProactiveRefresh();
  const exp = getAccessTokenExpiry();
  if (!exp || !getAccessToken() || status === 'expired') return;
  const delay = Math.max(MIN_DELAY_MS, exp - Date.now() - REFRESH_LEAD_MS);
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

/** Other tabs renew the shared token; a tab coming back to the foreground catches up. */
export function installSessionListeners(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const onStorage = (e: StorageEvent) => {
    if (e.key === ACCESS_EXPIRES_KEY || e.key === ACCESS_TOKEN_KEY) {
      scheduleProactiveRefresh();
      notify();
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

/** Bearer token on every request to our API; silent refresh + retry on 401; never a redirect. */
export function installAuthInterceptors(instance: AxiosInstance): () => void {
  const req = instance.interceptors.request.use((config) => {
    const token = getAccessToken();
    if (token && targetsOurApi(config)) {
      config.headers = config.headers ?? ({} as any);
      (config.headers as any).Authorization = `Bearer ${token}`;
    }
    return config;
  });
  const res = instance.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const config = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;
      if (!config || error.response?.status !== 401 || config._retry
          || AUTH_ENDPOINT.test(config.url ?? '') || !targetsOurApi(config) || !getAccessToken()) {
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

/** fetch() with the bearer token and the same 401 recovery (volumes, exports). */
export async function fetchWithSession(url: string, init: RequestInit = {}): Promise<Response> {
  const send = (token: string | null) => fetch(url, {
    ...init,
    headers: { ...(init.headers as Record<string, string> | undefined), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });
  const first = await send(getAccessToken());
  if (first.status !== 401 || !getAccessToken()) return first;
  try {
    return await send(await recoverFromUnauthorized());
  } catch {
    return first;
  }
}
