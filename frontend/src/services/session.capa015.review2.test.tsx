/**
 * CAPA-015 — re-review of PR #65 at 09e11e8 (2026-10-24): frontend findings (RC-069).
 *
 * N3  components still read the shared token from localStorage themselves (ImageViewer3D,
 *     ProfilePage) and fetchWithSession kept a caller's Authorization header when this tab had no
 *     token of its own — so another user's token, written by another tab, could still be sent.
 * N5  a logout in another tab left patient data readable behind the re-login dialog: the page must
 *     stay mounted (unsaved work) but be unreadable while the dialog is open.
 *
 * Written before the fixes; they fail on 09e11e8.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, act, cleanup, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import fs from 'node:fs';
import path from 'node:path';
import i18n from '@/i18n/config';

const USER = {
  id: 'u-rad', username: 'dr_rad', email: 'dr_rad@clinic.example', full_name: 'Dr Rad', role: 'radiologist',
  is_active: true, is_locked: false, failed_login_attempts: 0, last_login: null,
  created_at: '2026-10-24T08:00:00', updated_at: '2026-10-24T08:00:00',
};
const b64 = (o: unknown) => btoa(JSON.stringify(o)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
const jwt = (userId: string, v = '1') => `${b64({ alg: 'HS256' })}.${b64({ user_id: userId, v })}.sig${v}`;

beforeEach(async () => {
  vi.resetModules();
  localStorage.clear();
  await i18n.changeLanguage('en');
});
afterEach(() => cleanup());

describe('RC-069 re-review — never another user\'s token (N3)', () => {
  it('rc069 fetchWithSession drops a caller-provided token that is not this tab\'s own', async () => {
    const session: any = await import('@/services/session');
    session.setSessionUser(USER.id);
    localStorage.setItem('access_token', jwt('u-other'));           // written by another tab
    const sent: Array<string | undefined> = [];
    const realFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (_u: any, init: any) => {
      sent.push(init?.headers?.Authorization);
      return new Response('x', { status: 200 });
    }) as any;
    try {
      await session.fetchWithSession('http://localhost:8000/api/v1/imaging/nifti/f', {
        headers: { Authorization: `Bearer ${jwt('u-other')}`, Accept: 'application/octet-stream' },
      });
      expect(sent[0]).toBeUndefined();
      localStorage.setItem('access_token', jwt(USER.id, '2'));       // now this tab's own token
      await session.fetchWithSession('http://localhost:8000/api/v1/imaging/nifti/f', {
        headers: { Authorization: 'Bearer stale-copy' },
      });
      expect(sent[1]).toBe(`Bearer ${jwt(USER.id, '2')}`);
    } finally {
      globalThis.fetch = realFetch;
    }
  });

  it('rc069 no component reads the shared token from storage itself', () => {
    const root = path.resolve(__dirname, '..');
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const name of fs.readdirSync(dir)) {
        const full = path.join(dir, name);
        if (fs.statSync(full).isDirectory()) { walk(full); continue; }
        if (!/\.(ts|tsx)$/.test(name) || /\.test\.(ts|tsx)$/.test(name)) continue;
        if (full.endsWith(path.join('services', 'session.ts'))) continue;
        const text = fs.readFileSync(full, 'utf-8');
        if (/localStorage\.getItem\(\s*['"`]access_token['"`]\s*\)/.test(text) || /getItem\(\s*ACCESS_TOKEN_KEY\s*\)/.test(text)) {
          offenders.push(path.relative(root, full));
        }
      }
    };
    walk(root);
    expect(offenders).toEqual([]);
  });
});

describe('RC-069 re-review — nothing readable behind the re-login dialog (N5)', () => {
  it('rc069 the page stays mounted but is hidden and inert while the dialog is open', async () => {
    localStorage.setItem('access_token', jwt(USER.id));
    localStorage.setItem('user', JSON.stringify(USER));
    const { AxiosError } = await import('axios');
    const session: any = await import('@/services/session');
    session.authClient.defaults.adapter = (async (config: any) => {
      if (config.url?.endsWith('/api/v1/auth/me')) return { data: USER, status: 200, statusText: '200', headers: {}, config };
      throw new AxiosError('unrouted', 'ERR_BAD_REQUEST', config);
    }) as any;
    const { AuthProvider } = await import('@/contexts/AuthContext');
    const { SessionExpiredDialog } = await import('@/components/SessionExpiredDialog');
    const ProtectedRoute = (await import('@/components/ProtectedRoute')).default;
    render(
      <MemoryRouter initialEntries={['/viewer']}>
        <AuthProvider>
          <Routes>
            <Route path="/viewer" element={<ProtectedRoute><div>Patient Mustermann — unsaved lesions</div></ProtectedRoute>} />
          </Routes>
          <SessionExpiredDialog />
        </AuthProvider>
      </MemoryRouter>,
    );
    const content = await screen.findByText(/Patient Mustermann/);
    act(() => session.markSessionExpired());
    await screen.findByRole('dialog');
    let page: HTMLElement | null = content;
    while (page && page.parentElement !== document.body) page = page.parentElement;
    expect(page).not.toBeNull();
    expect(page!.getAttribute('aria-hidden')).toBe('true');
    expect(page!.hasAttribute('inert')).toBe(true);
    expect(page!.style.filter).toMatch(/blur/);
    expect(document.body.contains(content)).toBe(true);           // kept mounted: the work survives
    act(() => session.completeReauthentication(jwt(USER.id, '2'), 900));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(page!.hasAttribute('aria-hidden')).toBe(false);
    expect(page!.hasAttribute('inert')).toBe(false);
    expect(page!.style.filter).toBe('');
  });
});
