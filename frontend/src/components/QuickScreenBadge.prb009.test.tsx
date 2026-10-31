/**
 * PRB-009 — the in-browser "Quick Screen" when its model file is absent.
 *
 * The model (`/models/brain_screening.onnx`) is not shipped with the app. Every opening of the viewer
 * requested it; on a static file server (vite preview, a hospital nginx) the request failed in the
 * console each time, and the "Quick Screen" button was shown while the check was still running.
 * With the screening switched on at build time but the model absent, required: no button, ever; the
 * model is looked for once per page, not at each viewer opening; nothing is written to the console.
 * (Switched off — the default — the viewer does not mount the badge at all: ViewerApp.prb007.test.tsx.)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';

let probes: string[] = [];
function serveModel(present: boolean) {
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    if (url.includes('brain_screening.onnx')) probes.push(`${init?.method ?? 'GET'} ${url}`);
    return present
      ? { ok: true, status: 200, headers: { get: () => 'application/octet-stream' } }
      : { ok: false, status: 404, headers: { get: () => 'text/plain' } };
  }));
}

async function freshBadge() {
  vi.resetModules();
  return (await import('./QuickScreenBadge')).QuickScreenBadge;
}

const SLICE = 'data:image/png;base64,AAAA';

beforeEach(() => {
  probes = [];
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('PRB-009 — screening switched on, model file absent', () => {
  it('rc075 no Quick Screen button is shown, not even while the model is being looked for', async () => {
    serveModel(false);
    const QuickScreenBadge = await freshBadge();
    render(<QuickScreenBadge currentSliceBase64={SLICE} imageWidth={4} imageHeight={4} />);
    expect(screen.queryByRole('button', { name: /Quick Screen/i })).not.toBeInTheDocument();
    await waitFor(() => expect(probes.length).toBe(1));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole('button', { name: /Quick Screen/i })).not.toBeInTheDocument();
  });

  it('rc075 the model is looked for once per page, not at every viewer opening', async () => {
    serveModel(false);
    const QuickScreenBadge = await freshBadge();
    for (let opening = 0; opening < 3; opening++) {
      render(<QuickScreenBadge currentSliceBase64={SLICE} imageWidth={4} imageHeight={4} />);
      await new Promise((r) => setTimeout(r, 20));
      cleanup();
    }
    expect(probes).toEqual(['HEAD /models/brain_screening.onnx']);
  });

  it('rc075 an absent model writes nothing to the console', async () => {
    serveModel(false);
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
    const warns = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const QuickScreenBadge = await freshBadge();
    render(<QuickScreenBadge currentSliceBase64={SLICE} imageWidth={4} imageHeight={4} />);
    await waitFor(() => expect(probes.length).toBe(1));
    await new Promise((r) => setTimeout(r, 20));
    expect(errors).not.toHaveBeenCalled();
    expect(warns).not.toHaveBeenCalled();
  });

  it('rc075 guard: with the model present the button is shown', async () => {
    serveModel(true);
    const QuickScreenBadge = await freshBadge();
    render(<QuickScreenBadge currentSliceBase64={SLICE} imageWidth={4} imageHeight={4} />);
    expect(await screen.findByRole('button', { name: /Quick Screen/i })).toBeInTheDocument();
  });
});
