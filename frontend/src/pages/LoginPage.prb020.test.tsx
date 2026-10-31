/**
 * PRB-020 (open self-registration) and PRB-022 (false security claims) — the sign-in page.
 *
 * Found in the browser capture of the release candidate (2026-10-28; F21, F15):
 *  - the page offers a "Register" tab to anyone, and the server creates a VIEWER account for anyone
 *    (EU MDR "making available" risk for a device that is not CE-marked; HAZ-010);
 *  - the footer says "MFA enforced · NIST SP 800-63B AAL2 · Data never leaves your jurisdiction" and
 *    shows HIPAA / ISO 27001 / TLS 1.3 badges, although sign-in is password-only and none of these is
 *    verified or certified.
 *
 * Wanted: the tab and form are shown ONLY when the server says self-registration is on
 * (GET /api/v1/auth/registration); hidden when it is off or cannot be read (fail closed); the page
 * says accounts are created by an administrator; no security claim the device cannot back.
 * Negative controls: scripts/safety/prb020_negative_controls.py.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import i18n from '@/i18n/config';

const get = vi.fn();
const post = vi.fn();
vi.mock('axios', () => {
  const api = { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) };
  return { default: { ...api, create: () => api }, ...api };
});
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ login: vi.fn(), loginWithPasskey: vi.fn(), register: vi.fn(), isAuthenticated: false }),
}));

import LoginPage from './LoginPage';

function renderPage() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
}

const registerTab = () => screen.queryByRole('button', { name: 'Register' });

describe('PRB-020 sign-in page: self-registration only when the server allows it', () => {
  beforeEach(async () => {
    get.mockReset();
    post.mockReset();
    await i18n.changeLanguage('en');
  });

  it('rc080 prb020 asks the server whether self-registration is on', async () => {
    get.mockResolvedValue({ data: { self_registration_enabled: false, account_creation: 'administrator' } });
    renderPage();
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(String(get.mock.calls[0][0])).toMatch(/\/api\/v1\/auth\/registration$/);
  });

  it('rc080 prb020 hides the Register tab and says an administrator creates accounts when it is off', async () => {
    get.mockResolvedValue({ data: { self_registration_enabled: false, account_creation: 'administrator' } });
    renderPage();
    await waitFor(() => expect(screen.getByText(/created by an administrator/i)).toBeInTheDocument());
    expect(registerTab()).toBeNull();
    expect(screen.queryByText('Create Account')).toBeNull();
  });

  it('rc080 prb020 hides the Register tab when the server cannot be asked (fail closed)', async () => {
    get.mockRejectedValue(new Error('network down'));
    renderPage();
    await waitFor(() => expect(get).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(registerTab()).toBeNull();
  });

  it('rc080 prb020 shows the Register tab and form only when the server says it is on', async () => {
    get.mockResolvedValue({ data: { self_registration_enabled: true, account_creation: 'self' } });
    renderPage();
    const tab = await screen.findByRole('button', { name: 'Register' });
    fireEvent.click(tab);
    expect(await screen.findByText('Create Account')).toBeInTheDocument();
  });
});

describe('PRB-022 sign-in page: no security or compliance claim the device cannot back', () => {
  beforeEach(async () => {
    get.mockReset();
    get.mockResolvedValue({ data: { self_registration_enabled: false, account_creation: 'administrator' } });
    await i18n.changeLanguage('en');
  });

  it('rc086 prb022 makes no MFA, AAL2, data-residency, HIPAA, ISO 27001 or TLS 1.3 claim', async () => {
    const { container } = renderPage();
    await new Promise((r) => setTimeout(r, 0));
    const text = container.textContent || '';
    for (const claim of [/MFA/i, /multi-factor/i, /AAL2/i, /800-63/i, /jurisdiction/i, /HIPAA/i, /ISO 27001/i, /TLS 1\.3/i]) {
      expect(text).not.toMatch(claim);
    }
  });

  it('rc086 prb022 keeps the claims out of the translations too (unused keys could be reused)', async () => {
    // The report's "HIPAA Compliant … no PHI transmitted" note (reportViewer.hipaaNote) is removed by CAPA-014
    // (PR #67), which owns that text; it is not repeated here to avoid a conflicting change.
    const files = import.meta.glob('../i18n/locales/*.json', { eager: true, query: '?raw', import: 'default' });
    expect(Object.keys(files)).toHaveLength(3);
    for (const [file, raw] of Object.entries(files)) {
      expect(String(raw), file).not.toMatch(/ISO 27001:2022|HIPAA Secure|Seguro HIPAA|HIPAA Sicher/);
    }
  });
});
