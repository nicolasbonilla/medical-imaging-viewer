/**
 * CAPA-015 — session continuation without losing unsaved work (RC-069, REQ-SEC-026; HAZ-010,
 * HAZ-001) and the administrator's audit-trail indicator (RC-067, REQ-SEC-024).
 *
 * Found (code of main @ 70cc5c7): the backend issued one 60-minute access token and had no
 * `/auth/refresh`; the API client posted a `refresh_token` from localStorage that never existed,
 * so after an hour every request failed with 401. Saving a segmentation then failed, and the only
 * way back was to sign in again — leaving the page and discarding the mask held in memory. Any
 * 401 seen by the global axios instance sent the browser to /login at once (`window.location`),
 * and the frontend never told the server about a logout.
 *
 * These tests drive the real API client, session service, AuthProvider and dialogs with a fake
 * network (axios adapters). They were written before the fix and fail on main @ 70cc5c7
 * (record: docs/iec62304/records/risk_verification/CAPA-015_tests_on_base_2026-10-24.json).
 */
import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, waitFor, act, cleanup } from '@testing-library/react';
import fs from 'node:fs';
import path from 'node:path';
import i18n from '@/i18n/config';

const USER = {
  id: 'u-rad', username: 'dr_rad', email: 'dr_rad@clinic.example', full_name: 'Dr Rad', role: 'radiologist',
  is_active: true, is_locked: false, failed_login_attempts: 0, last_login: null,
  created_at: '2026-10-24T08:00:00', updated_at: '2026-10-24T08:00:00',
};
const ADMIN = { ...USER, id: 'u-admin', username: 'admin_ops', role: 'admin' };
const OTHER = { ...USER, id: 'u-other', username: 'someone_else' };

// Modules added by the fix are loaded by a computed name, so that on the code before the fix each
// test fails on its own (module missing) instead of the whole file failing to compile.
const SESSION = './session';
const DIALOG = '../components/SessionExpiredDialog';
const BANNER = '../components/AuditStatusBanner';
const load = (name: string): Promise<any> => import(/* @vite-ignore */ name);

type Out = { status: number; data?: unknown; headers?: Record<string, string> };
type Route = (cfg: any) => Out | undefined;
let calls: any[] = [];

async function makeAdapter(routes: Route[]) {
  const { AxiosError } = await import('axios');
  return async (config: any) => {
    calls.push(config);
    for (const r of routes) {
      const out = r(config);
      if (!out) continue;
      const response = { data: out.data ?? {}, status: out.status, statusText: String(out.status),
        headers: out.headers ?? {}, config, request: {} };
      if (out.status >= 400) {
        throw new AxiosError(`Request failed with status code ${out.status}`, 'ERR_BAD_REQUEST', config, {}, response as any);
      }
      return response;
    }
    throw new Error(`unrouted ${config.method} ${config.url}`);
  };
}

function bearerOf(cfg: any): string | undefined {
  const h = cfg.headers ?? {};
  const v = typeof h.get === 'function' ? h.get('Authorization') : h.Authorization ?? h.authorization;
  return v ? String(v) : undefined;
}

/** Installs the same fake network on every axios instance the app may use. */
async function network(routes: Route[]) {
  const adapter = await makeAdapter(routes);
  const axios = (await import('axios')).default;
  axios.defaults.adapter = adapter as any;
  const { apiClient } = await import('@/services/apiClient');
  apiClient.defaults.adapter = adapter as any;
  try {
    const session: any = await load(SESSION);
    if (session.authClient) session.authClient.defaults.adapter = adapter as any;
  } catch { /* module absent before the fix */ }
  return { axios, apiClient };
}

const ok = (data: unknown): Out => ({ status: 200, data });
const tokenResponse = (access: string, user = USER) => ok({ token: { access_token: access, token_type: 'bearer', expires_in: 900 }, user });

let hrefSet: Mock<(v: string) => void>;
const realLocation = window.location;

beforeEach(async () => {
  vi.resetModules();
  calls = [];
  localStorage.clear();
  hrefSet = vi.fn<(v: string) => void>();
  const origin = realLocation.origin;
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      origin, protocol: realLocation.protocol, host: realLocation.host, hostname: realLocation.hostname,
      port: realLocation.port, pathname: '/app/viewer', search: '', hash: '',
      get href() { return `${origin}/app/viewer`; },
      set href(v: string) { hrefSet(v); },
      assign: (v: string) => hrefSet(v), replace: (v: string) => hrefSet(v), reload: () => hrefSet('reload'),
    },
  });
  await i18n.changeLanguage('en');
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  Object.defineProperty(window, 'location', { configurable: true, value: realLocation });
});

function signedIn(user = USER, token = 'old-token') {
  localStorage.setItem('access_token', token);
  localStorage.setItem('user', JSON.stringify(user));
}

describe('RC-069 — the session continues silently; when it cannot, unsaved work is kept', () => {
  it('rc069 refreshes once on 401 through the same-origin auth endpoint with the cookie, then retries', async () => {
    signedIn();
    const { apiClient } = await network([
      (c) => (c.url?.endsWith('/api/v1/auth/refresh') ? tokenResponse('new-token') : undefined),
      (c) => (c.url?.includes('/api/v1/segmentation/list')
        ? (bearerOf(c) === 'Bearer new-token' ? ok(['seg']) : { status: 401, data: { detail: 'expired' } })
        : undefined),
    ]);
    const res = await apiClient.get('/api/v1/segmentation/list');
    expect(res.data).toEqual(['seg']);
    const refresh = calls.filter((c) => c.url?.endsWith('/api/v1/auth/refresh'));
    expect(refresh).toHaveLength(1);
    expect(refresh[0].url.startsWith(window.location.origin)).toBe(true);
    expect(refresh[0].withCredentials).toBe(true);
    expect(JSON.stringify(refresh[0].data ?? '')).not.toContain('refresh_token');
    expect(localStorage.getItem('access_token')).toBe('new-token');
    expect(localStorage.getItem('refresh_token')).toBeNull();
  });

  it('rc069 concurrent 401s trigger a single refresh', async () => {
    signedIn();
    const { apiClient } = await network([
      (c) => (c.url?.endsWith('/api/v1/auth/refresh') ? tokenResponse('new-token') : undefined),
      (c) => (bearerOf(c) === 'Bearer new-token' ? ok({ fine: true }) : { status: 401 }),
    ]);
    await Promise.all([apiClient.get('/api/v1/a'), apiClient.get('/api/v1/b'), apiClient.get('/api/v1/c')]);
    expect(calls.filter((c) => c.url?.endsWith('/api/v1/auth/refresh'))).toHaveLength(1);
  });

  it('rc069 refresh failure keeps the page and the unsaved work, asks to sign in, then retries the save', async () => {
    signedIn();
    const { useSegmentationStore } = await import('@/store/useSegmentationStore');
    useSegmentationStore.getState().setHasUnsavedMaskChanges(true);
    let fresh = false;
    const { apiClient } = await network([
      (c) => (c.url?.endsWith('/api/v1/auth/refresh') ? { status: 401, data: { detail: 'Session expired' } } : undefined),
      (c) => (c.url?.includes('/mask/binary')
        ? (bearerOf(c) === 'Bearer fresh-token' ? ok({ success: true }) : { status: 401 })
        : undefined),
    ]);
    const save = apiClient.put('/api/v1/segmentation/s1/mask/binary', new Uint8Array([1, 2, 3]).buffer)
      .then((r) => { fresh = true; return r; });
    const session: any = await load(SESSION);
    await waitFor(() => expect(session.getSessionStatus()).toBe('expired'));
    expect(hrefSet).not.toHaveBeenCalled();
    expect(useSegmentationStore.getState().hasUnsavedMaskChanges).toBe(true);
    expect(localStorage.getItem('user')).not.toBeNull();
    expect(fresh).toBe(false);
    act(() => session.completeReauthentication('fresh-token', 900));
    await expect(save).resolves.toMatchObject({ status: 200 });
    expect(session.getSessionStatus()).toBe('active');
  });

  it('rc069 refreshes proactively before the access token expires', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    vi.setSystemTime(new Date('2026-10-24T08:00:00Z'));
    signedIn(USER, 't1');
    await network([(c) => (c.url?.endsWith('/api/v1/auth/refresh') ? tokenResponse('t2') : undefined)]);
    const session: any = await load(SESSION);
    session.storeSession('t1', 900);
    session.scheduleProactiveRefresh();
    await vi.advanceTimersByTimeAsync(12 * 60 * 1000);
    expect(calls.filter((c) => c.url?.endsWith('/api/v1/auth/refresh'))).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(2 * 60 * 1000);
    expect(calls.filter((c) => c.url?.endsWith('/api/v1/auth/refresh'))).toHaveLength(1);
    expect(localStorage.getItem('access_token')).toBe('t2');
    session.cancelProactiveRefresh();
  });

  it('rc069 a 401 seen by the global axios instance no longer sends the browser to /login', async () => {
    signedIn();
    await network([
      (c) => (c.url?.endsWith('/api/v1/auth/me') ? ok(USER) : undefined),
      (c) => (c.url?.endsWith('/api/v1/auth/refresh') ? { status: 401 } : undefined),
      (c) => (c.url?.includes('/api/v1/patients') ? { status: 401 } : undefined),
    ]);
    const { AuthProvider } = await import('@/contexts/AuthContext');
    const axios = (await import('axios')).default;
    render(<AuthProvider><div>app</div></AuthProvider>);
    await waitFor(() => expect(calls.some((c) => c.url?.endsWith('/api/v1/auth/me'))).toBe(true));
    const pending = axios.get(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/api/v1/patients`).catch(() => null);
    const session: any = await load(SESSION);
    await waitFor(() => expect(session.getSessionStatus()).toBe('expired'));
    expect(hrefSet).not.toHaveBeenCalled();
    expect(localStorage.getItem('user')).not.toBeNull();
    void pending;
  });

  it('rc069 the re-login dialog keeps the work, accepts only the same user, then resumes', async () => {
    signedIn();
    const { useSegmentationStore } = await import('@/store/useSegmentationStore');
    useSegmentationStore.getState().setHasUnsavedMaskChanges(true);
    let loginAs = OTHER;
    await network([
      (c) => (c.url?.endsWith('/api/v1/auth/me') ? ok(USER) : undefined),
      (c) => (c.url?.endsWith('/api/v1/auth/login') ? tokenResponse(loginAs === USER ? 'mine' : 'theirs', loginAs) : undefined),
      (c) => (c.url?.endsWith('/api/v1/auth/logout') ? { status: 204 } : undefined),
    ]);
    const { AuthProvider } = await import('@/contexts/AuthContext');
    const { SessionExpiredDialog } = await load(DIALOG);
    render(<AuthProvider><SessionExpiredDialog /></AuthProvider>);
    await waitFor(() => expect(calls.some((c) => c.url?.endsWith('/api/v1/auth/me'))).toBe(true));
    const session: any = await load(SESSION);
    act(() => session.markSessionExpired());
    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toMatch(/unsaved/i);
    expect(screen.getByTestId('reauth-unsaved')).toBeTruthy();   // the unsaved segmentation is named
    expect(dialog.textContent).toContain('dr_rad');

    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'whatever-123' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    await screen.findByTestId('reauth-error');
    expect(session.getSessionStatus()).toBe('expired');
    const loggedOut = calls.find((c) => c.url?.endsWith('/api/v1/auth/logout'));
    expect(loggedOut && bearerOf(loggedOut)).toBe('Bearer theirs');   // the other person's new session is closed

    loginAs = USER;
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(session.getSessionStatus()).toBe('active');
    expect(localStorage.getItem('access_token')).toBe('mine');
    expect(useSegmentationStore.getState().hasUnsavedMaskChanges).toBe(true);
    expect(hrefSet).not.toHaveBeenCalled();
  });

  it('rc069 fetch-based downloads (volumes, DICOM-SEG export) recover from 401 the same way', async () => {
    signedIn();
    await network([(c) => (c.url?.endsWith('/api/v1/auth/refresh') ? tokenResponse('new-token') : undefined)]);
    const seen: string[] = [];
    const realFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (_url: any, init: any) => {
      const auth = String(init?.headers?.Authorization ?? '');
      seen.push(auth);
      return new Response(auth === 'Bearer new-token' ? 'volume' : 'expired', { status: auth === 'Bearer new-token' ? 200 : 401 });
    }) as any;
    try {
      const session: any = await load(SESSION);
      const res = await session.fetchWithSession('http://localhost:8000/api/v1/imaging/nifti/x');
      expect(res.status).toBe(200);
      expect(await res.text()).toBe('volume');
      expect(seen).toEqual(['Bearer old-token', 'Bearer new-token']);
    } finally {
      globalThis.fetch = realFetch;
    }
  });

  it('rc069 logout tells the server, so the refresh cookie is revoked', async () => {
    signedIn();
    await network([
      (c) => (c.url?.endsWith('/api/v1/auth/me') ? ok(USER) : undefined),
      (c) => (c.url?.endsWith('/api/v1/auth/logout') ? { status: 204 } : undefined),
    ]);
    const { AuthProvider, useAuth } = await import('@/contexts/AuthContext');
    function Out() {
      const { logout } = useAuth();
      return <button onClick={() => logout()}>out</button>;
    }
    render(<AuthProvider><Out /></AuthProvider>);
    await waitFor(() => expect(calls.some((c) => c.url?.endsWith('/api/v1/auth/me'))).toBe(true));
    fireEvent.click(screen.getByText('out'));
    await waitFor(() => expect(calls.some((c) => c.url?.endsWith('/api/v1/auth/logout'))).toBe(true));
    const call = calls.find((c) => c.url?.endsWith('/api/v1/auth/logout'));
    expect(call.method).toBe('post');
    expect(call.url.startsWith(window.location.origin)).toBe(true);
    expect(call.withCredentials).toBe(true);
    expect(localStorage.getItem('access_token')).toBeNull();
  });
});

describe('RC-067 — administrators see when the audit trail cannot be written', () => {
  const STATUS = { state: 'failing', queue_depth: 3, consecutive_failures: 5, dropped_total: 0,
    last_error: 'ConnectionError', last_failure_at: '2026-10-24T08:00:00Z', backend: 'firestore' };

  it('rc067 shows a banner to an administrator when audit writing is failing', async () => {
    signedIn(ADMIN);
    await network([
      (c) => (c.url?.endsWith('/api/v1/auth/me') ? ok(ADMIN) : undefined),
      (c) => (c.url?.endsWith('/api/v1/auth/audit-status') ? ok(STATUS) : undefined),
    ]);
    const { AuthProvider } = await import('@/contexts/AuthContext');
    const { AuditStatusBanner } = await load(BANNER);
    render(<AuthProvider><AuditStatusBanner /></AuthProvider>);
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/audit/i);
    expect(alert.textContent).toContain('3');
  });

  it('rc067 shows nothing to a non-administrator and nothing when writing works', async () => {
    signedIn(USER);
    await network([
      (c) => (c.url?.endsWith('/api/v1/auth/me') ? ok(USER) : undefined),
      (c) => (c.url?.endsWith('/api/v1/auth/audit-status') ? ok({ ...STATUS, state: 'ok' }) : undefined),
    ]);
    const { AuthProvider } = await import('@/contexts/AuthContext');
    const { AuditStatusBanner } = await load(BANNER);
    render(<AuthProvider><AuditStatusBanner /></AuthProvider>);
    await waitFor(() => expect(calls.some((c) => c.url?.endsWith('/api/v1/auth/me'))).toBe(true));
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(calls.some((c) => c.url?.endsWith('/api/v1/auth/audit-status'))).toBe(false);
  });
});

describe('RC-067 / RC-069 — every new text exists in English, Spanish and German', () => {
  const KEYS = ['session.reauthTitle', 'session.reauthMessage', 'session.reauthUnsaved', 'session.reauthPassword',
    'session.reauthSubmit', 'session.reauthPasskey', 'session.reauthSignOut', 'session.reauthWrongUser',
    'session.reauthFailed', 'audit.statusTitle', 'audit.statusFailing', 'audit.statusDegraded', 'audit.statusNotDurable'];
  const locale = (lng: string) => JSON.parse(fs.readFileSync(path.resolve(__dirname, `../i18n/locales/${lng}.json`), 'utf-8'));
  const get = (o: any, k: string) => k.split('.').reduce((a, p) => (a ? a[p] : undefined), o);

  it('rc069 the dialog and banner texts are translated', () => {
    const en = locale('en'); const es = locale('es'); const de = locale('de');
    for (const k of KEYS) {
      expect(typeof get(en, k), `en ${k}`).toBe('string');
      expect(typeof get(es, k), `es ${k}`).toBe('string');
      expect(typeof get(de, k), `de ${k}`).toBe('string');
      expect(get(es, k), `es ${k} is English`).not.toBe(get(en, k));
      expect(get(de, k), `de ${k} is English`).not.toBe(get(en, k));
    }
  });
});
