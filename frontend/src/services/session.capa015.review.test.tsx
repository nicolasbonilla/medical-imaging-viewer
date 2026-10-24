/**
 * CAPA-015 — independent adversarial review of PR #65 (2026-10-24): frontend findings (RC-069).
 *
 * M1  the client renewed only before the ACCESS token expired; if the refresh session's idle
 *     limit ends first, the renewal must happen before that.
 * M2  another tab could wipe this tab's unsaved work: a logout there cleared the shared token,
 *     this tab's state lost its token and React Router's <Navigate to="/login"> unmounted the
 *     viewer (a soft redirect — window.location was never touched). Another user's token written
 *     by another tab was used here. A re-login in one tab did not resume the others; "Sign out" in
 *     a dialog made stale by another tab's recovery logged everybody out; each tab's inactivity
 *     timer logged out on its own while the user worked in another tab.
 * M4  a 404/405 from /refresh (hosting rewrite or backend not yet deployed) was not treated as an
 *     ended session: the request failed and the dialog never opened.
 * m13 a hanging refresh held the cross-tab lock forever.
 *
 * Two tabs are simulated the way a browser does it: the other tab writes localStorage and this
 * tab receives a `storage` event. Written before the fixes; they fail on the PR #65 head (2c618ec).
 */
import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, waitFor, act, cleanup, renderHook } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import i18n from '@/i18n/config';

const USER = {
  id: 'u-rad', username: 'dr_rad', email: 'dr_rad@clinic.example', full_name: 'Dr Rad', role: 'radiologist',
  is_active: true, is_locked: false, failed_login_attempts: 0, last_login: null,
  created_at: '2026-10-24T08:00:00', updated_at: '2026-10-24T08:00:00',
};
const OTHER = { ...USER, id: 'u-other', username: 'someone_else' };

const b64 = (o: unknown) => btoa(JSON.stringify(o)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
/** A JWT-shaped token carrying the user id (signature irrelevant for the client). */
const jwt = (userId: string, v = '1') => `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64({ user_id: userId, v, type: 'access' })}.sig${v}`;

type Out = { status: number; data?: unknown };
type Route_ = (cfg: any) => Out | Promise<Out> | undefined;
let calls: any[] = [];

async function makeAdapter(routes: Route_[]) {
  const { AxiosError } = await import('axios');
  return async (config: any) => {
    calls.push(config);
    for (const r of routes) {
      const out = await r(config);
      if (!out) continue;
      const response = { data: out.data ?? {}, status: out.status, statusText: String(out.status), headers: {}, config, request: {} };
      if (out.status >= 400) throw new AxiosError(`Request failed with status code ${out.status}`, 'ERR_BAD_REQUEST', config, {}, response as any);
      return response;
    }
    throw new Error(`unrouted ${config.method} ${config.url}`);
  };
}
const bearerOf = (cfg: any): string | undefined => {
  const h = cfg.headers ?? {};
  const v = typeof h.get === 'function' ? h.get('Authorization') : h.Authorization ?? h.authorization;
  return v ? String(v) : undefined;
};
async function network(routes: Route_[]) {
  const adapter = await makeAdapter(routes);
  const axios = (await import('axios')).default;
  axios.defaults.adapter = adapter as any;
  const { apiClient } = await import('@/services/apiClient');
  apiClient.defaults.adapter = adapter as any;
  const session: any = await import('@/services/session');
  session.authClient.defaults.adapter = adapter as any;
  return { apiClient, session };
}
const ok = (data: unknown): Out => ({ status: 200, data });

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
      port: realLocation.port, pathname: '/viewer', search: '', hash: '',
      get href() { return `${origin}/viewer`; }, set href(v: string) { hrefSet(v); },
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

function signedIn(user = USER, token = jwt(USER.id)) {
  localStorage.setItem('access_token', token);
  localStorage.setItem('user', JSON.stringify(user));
}
/** What a browser does in THIS tab when ANOTHER tab writes localStorage. */
function otherTabWrites(key: string, value: string | null) {
  const oldValue = localStorage.getItem(key);
  if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value);
  window.dispatchEvent(new StorageEvent('storage', { key, oldValue, newValue: value }));
}

async function renderViewerTab() {
  const { AuthProvider } = await import('@/contexts/AuthContext');
  const { SessionExpiredDialog } = await import('@/components/SessionExpiredDialog');
  const ProtectedRoute = (await import('@/components/ProtectedRoute')).default;
  render(
    <MemoryRouter initialEntries={['/viewer']}>
      <AuthProvider>
        <Routes>
          <Route path="/viewer" element={<ProtectedRoute><div>unsaved-segmentation</div></ProtectedRoute>} />
          <Route path="/login" element={<div>login-page</div>} />
        </Routes>
        <SessionExpiredDialog />
      </AuthProvider>
    </MemoryRouter>,
  );
  await screen.findByText('unsaved-segmentation');
}

describe('RC-069 review — renewal before the refresh session ends (M1)', () => {
  it('rc069 renews before the refresh idle limit when it ends before the access token', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    vi.setSystemTime(new Date('2026-10-24T08:00:00Z'));
    signedIn(USER, 't1');
    const { session } = await network([(c) => (c.url?.endsWith('/api/v1/auth/refresh')
      ? ok({ token: { access_token: 't2', token_type: 'bearer', expires_in: 900, refresh_expires_in: 1800 }, user: USER }) : undefined)]);
    session.storeSession('t1', 900, 300);          // access 15 min, refresh session ends in 5 min
    session.scheduleProactiveRefresh();
    await vi.advanceTimersByTimeAsync(170 * 1000);
    expect(calls.filter((c) => c.url?.endsWith('/auth/refresh'))).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(20 * 1000);
    expect(calls.filter((c) => c.url?.endsWith('/auth/refresh'))).toHaveLength(1);
    session.cancelProactiveRefresh();
  });
});

describe('RC-069 review — another tab never wipes this tab (M2)', () => {
  it('rc069 a logout in another tab opens the dialog here and never navigates away (React Router)', async () => {
    signedIn();
    await network([(c) => (c.url?.endsWith('/api/v1/auth/me') ? ok(USER) : undefined)]);
    await renderViewerTab();
    act(() => {
      otherTabWrites('access_token', null);
      otherTabWrites('access_token_expires_at', null);
      otherTabWrites('user', null);
    });
    await screen.findByRole('dialog');
    expect(screen.getByText('unsaved-segmentation')).toBeTruthy();
    expect(screen.queryByText('login-page')).toBeNull();
    expect(hrefSet).not.toHaveBeenCalled();
  });

  it("rc069 another user's token written by another tab is never used here and opens the dialog", async () => {
    signedIn();
    const { apiClient } = await network([
      (c) => (c.url?.endsWith('/api/v1/auth/me') ? ok(USER) : undefined),
      (c) => (c.url?.endsWith('/api/v1/auth/refresh') ? { status: 401 } : undefined),
      (c) => (c.url?.includes('/api/v1/segmentation') ? (bearerOf(c) === `Bearer ${jwt(USER.id, '9')}` ? ok({}) : { status: 401 }) : undefined),
    ]);
    await renderViewerTab();
    act(() => otherTabWrites('access_token', jwt(OTHER.id)));
    await screen.findByRole('dialog');
    const pending = apiClient.put('/api/v1/segmentation/s1/mask/binary', new Uint8Array([1]).buffer);
    await new Promise((r) => setTimeout(r, 30));
    expect(calls.some((c) => bearerOf(c) === `Bearer ${jwt(OTHER.id)}`)).toBe(false);
    expect(screen.getByText('unsaved-segmentation')).toBeTruthy();
    void pending.catch(() => null);
  });

  it('rc069 a re-login in another tab resumes this tab, closes its dialog and completes the waiting save', async () => {
    signedIn();
    const fresh = jwt(USER.id, '2');
    const { apiClient } = await network([
      (c) => (c.url?.endsWith('/api/v1/auth/me') ? ok(USER) : undefined),
      (c) => (c.url?.endsWith('/api/v1/auth/refresh') ? { status: 401 } : undefined),
      (c) => (c.url?.includes('/mask/binary') ? (bearerOf(c) === `Bearer ${fresh}` ? ok({ saved: true }) : { status: 401 }) : undefined),
    ]);
    await renderViewerTab();
    const save = apiClient.put('/api/v1/segmentation/s1/mask/binary', new Uint8Array([1]).buffer);
    await screen.findByRole('dialog');
    act(() => {
      otherTabWrites('access_token_expires_at', String(Date.now() + 900_000));
      otherTabWrites('access_token', fresh);
    });
    await expect(save).resolves.toMatchObject({ status: 200 });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByText('unsaved-segmentation')).toBeTruthy();
  });

  it('rc069 "sign out" in a dialog made stale by another tab\'s recovery does not log anybody out', async () => {
    signedIn();
    const recovered = jwt(USER.id, '3');
    const { session } = await network([
      (c) => (c.url?.endsWith('/api/v1/auth/me') ? ok(USER) : undefined),
      (c) => (c.url?.endsWith('/api/v1/auth/logout') ? { status: 204 } : undefined),
    ]);
    await renderViewerTab();
    act(() => session.markSessionExpired());
    await screen.findByRole('dialog');
    // another tab signed in again, but this tab missed the event
    localStorage.setItem('access_token', recovered);
    localStorage.setItem('access_token_expires_at', String(Date.now() + 900_000));
    fireEvent.click(screen.getByRole('button', { name: /^sign out$/i }));
    fireEvent.click(screen.getByRole('button', { name: /discard changes and sign out/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(calls.some((c) => c.url?.endsWith('/api/v1/auth/logout'))).toBe(false);
    expect(localStorage.getItem('access_token')).toBe(recovered);
    expect(screen.getByText('unsaved-segmentation')).toBeTruthy();
  });

  it('rc069 the inactivity log-off waits while the user is active in another tab', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
    vi.setSystemTime(new Date('2026-10-24T08:00:00Z'));
    const { useSessionTimeout } = await import('@/hooks/useSessionTimeout');
    const onTimeout = vi.fn();
    renderHook(() => useSessionTimeout({ timeoutDuration: 15 * 60_000, warningDuration: 2 * 60_000, onTimeout, enabled: true }));
    // this tab's own activity is shared with the others
    expect(Number(localStorage.getItem('mstool_last_activity'))).toBe(Date.now());
    for (let i = 0; i < 5; i++) {                   // 20 minutes of work in another tab
      await act(async () => { await vi.advanceTimersByTimeAsync(4 * 60_000); });
      act(() => otherTabWrites('mstool_last_activity', String(Date.now())));
    }
    expect(onTimeout).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(16 * 60_000); });   // now nobody works anywhere
    expect(onTimeout).toHaveBeenCalledTimes(1);
  });
});

describe('RC-069 review — deploy window and hanging refresh (M4, m13)', () => {
  for (const status of [404, 405]) {
    it(`rc069 a ${status} from the refresh endpoint ends the session and keeps the waiting work`, async () => {
      signedIn(USER, 'old');
      const { apiClient, session } = await network([
        (c) => (c.url?.endsWith('/api/v1/auth/refresh') ? { status } : undefined),
        (c) => (c.url?.includes('/mask/binary') ? (bearerOf(c) === 'Bearer back' ? ok({}) : { status: 401 }) : undefined),
      ]);
      const save = apiClient.put('/api/v1/segmentation/s1/mask/binary', new Uint8Array([1]).buffer);
      await waitFor(() => expect(session.getSessionStatus()).toBe('expired'));
      act(() => session.completeReauthentication('back', 900));
      await expect(save).resolves.toMatchObject({ status: 200 });
    });
  }

  it('rc069 a refresh that hangs gives up and frees the cross-tab lock', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    signedIn(USER, 'old');
    const { session } = await network([(c) => (c.url?.endsWith('/api/v1/auth/refresh') ? new Promise<Out>(() => undefined) : undefined)]);
    let settled = false;
    session.refreshAccessToken().then(() => { settled = true; }, () => { settled = true; });
    await vi.advanceTimersByTimeAsync(16_000);
    expect(settled).toBe(true);
    session.refreshAccessToken().catch(() => undefined);
    await vi.advanceTimersByTimeAsync(1);
    expect(calls.filter((c) => c.url?.endsWith('/auth/refresh'))).toHaveLength(2);
  });
});
