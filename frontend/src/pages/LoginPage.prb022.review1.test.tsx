/**
 * Review of PR #70 — m7 (PRB-022): the sign-in page kept a badge "IEC 62304 · Class C" in the same style as the removed
 * certification badges (HIPAA, ISO 27001). No conformity assessment exists; REQ-REG-011 forbids an unverified compliance
 * claim. The badge is removed (the subtitle wording is an open owner decision, PRB-022 row 13).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import i18n from '@/i18n/config';

const get = vi.fn();
vi.mock('axios', () => {
  const api = { get: (...a: unknown[]) => get(...a), post: vi.fn() };
  return { default: { ...api, create: () => api }, ...api };
});
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ login: vi.fn(), loginWithPasskey: vi.fn(), register: vi.fn(), isAuthenticated: false }),
}));

import LoginPage from './LoginPage';

describe('PRB-022 sign-in page badges', () => {
  beforeEach(async () => {
    get.mockReset();
    get.mockResolvedValue({ data: { self_registration_enabled: false, account_creation: 'administrator' } });
    await i18n.changeLanguage('en');
  });

  it('rc086 prb022 the subtitle says research prototype, not medical device or Class C (en, es, de)', async () => {
    // Coordinator finding after the re-review: "AI-Powered Brain MRI Analysis · IEC 62304 Class C Medical Device" claimed
    // a medical device (no CE marking) and called a software safety class a device class.
    for (const [lang, text] of [['en', 'Brain MRI research prototype'], ['es', 'Prototipo de investigación de RM cerebral'],
      ['de', 'Forschungsprototyp für Gehirn-MRT']] as const) {
      await i18n.changeLanguage(lang);
      const { container, unmount } = render(<MemoryRouter><LoginPage /></MemoryRouter>);
      await new Promise((r) => setTimeout(r, 0));
      expect(screen.getByText(text)).toBeInTheDocument();
      expect(container.textContent || '').not.toMatch(/medical device|medizinprodukt|dispositivo m[eé]dico|class c|klasse c|clase c/i);
      unmount();
    }
  });

  it('rc086 prb022 no standard is shown as a badge', async () => {
    render(<MemoryRouter><LoginPage /></MemoryRouter>);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByText('IEC 62304', { exact: true })).toBeNull();
    expect(screen.queryByText('Class C', { exact: true })).toBeNull();
  });
});
