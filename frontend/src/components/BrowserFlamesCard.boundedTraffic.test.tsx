/**
 * G29 (seventh review of PR #81; RC-126): no unbounded traffic. Only a rate-limited answer is asked again — after its
 * wait, with backoff, at most 3 times; an unavailable answer and the flag mismatch (browser gate on, server gate
 * off: 404) are shown, never retried. Fake timers over 10 minutes. DRAFT, PENDING owner approval.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import '@/i18n/config';

const h = vi.hoisted(() => ({
  flames: {} as Record<string, unknown>,
  answer: (() => Promise.resolve(null)) as (fileId: string, confirmed: boolean, skull: string) => Promise<unknown>,
  calls: [] as string[],
}));
vi.mock('@/hooks/useBrowserFlames', () => ({ useBrowserFlames: () => h.flames }));
vi.mock('@/services/qualityGate/api', () => ({
  requestQualityGate: (fileId: string, confirmed: boolean, skull = 'pending') => {
    h.calls.push(skull);
    return h.answer(fileId, confirmed, skull);
  },
}));
vi.mock('@/config/features', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/config/features')>();
  return { ...mod, FEATURES: { ...mod.FEATURES, QUALITY_GATE: true } };
});

import { BrowserFlamesCard } from './BrowserFlamesCard';
import { useViewerStore } from '@/store/useViewerStore';

const FILE = 'patients/p/studies/s/flair.nii.gz';
const stopped = (code: string, params: Record<string, unknown> = {}) => ({
  gate_version: 'quality-gate/1', policy_version: null, mode: null, decision: 'abstain', ai_may_run: false,
  ai_output_allowed: false, codes: [code], checks: [{ check: 'platform', visit: null, status: 'abstain', code, params }],
  attestable_visits: [], actions: {}, subject: { file_id: FILE, version: null },
});
const result = {
  fileId: FILE, maskApp: new Uint8Array(24), dims: [3, 2, 4], spacing: [1, 1, 1],
  summary: { lesionCount: 2, lesionVoxels: 10, lesionVolumeMl: 0.01, componentVolumesMl: [] },
  provenance: { pipeline: 'p', model: 'm', modelSha256: 'x', sourceCheckpointSha256: 'y', backend: 'wasm', threads: 1,
    onnxRuntimeWeb: '1.24.1', mirror: false, windows: 1, networkCalls: 1, resampledShape: [1, 1, 1], seconds: 60,
    generatedAt: '2026-11-12T00:00:00.000Z', sequenceEvidence: 'clinician', inputPreparation: 'skull-removed' },
};
const flames = (status: string) => Object.assign(h.flames, {
  status, fraction: 0, message: '', error: null, startedAt: null, result: status === 'done' ? result : null,
  run: vi.fn(), cancel: vi.fn(), reset: vi.fn(),
});
const tenMinutes = async () => {
  for (let s = 0; s < 600; s += 5) await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
};

beforeEach(() => {
  vi.useFakeTimers();
  for (const k of Object.keys(h.flames)) delete h.flames[k];
  h.calls.length = 0;
  useViewerStore.setState({
    currentSeries: { id: 's', name: 'flair', format: 'nifti', file_id: FILE, total_slices: 4, metadata: { rows: 3, columns: 2 } },
  } as never);
});
afterEach(() => { vi.useRealTimers(); });

describe('G29: the number of requests stays bounded', () => {
  it('rc126 a rate limit that never lifts: at most 1 + 3 consultations in 10 minutes', async () => {
    flames('idle');
    h.answer = () => Promise.resolve(stopped('gate_rate_limited', { seconds: 2 }));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    await tenMinutes();
    expect(h.calls.length).toBeLessThanOrEqual(4);
    expect(h.calls.length).toBeGreaterThan(1);                 // it was retried, then it stopped
    expect(screen.getByTestId('quality-gate-before')).toBeInTheDocument();
  });

  it('rc126 an unavailable answer is shown and never retried', async () => {
    flames('idle');
    h.answer = () => Promise.resolve(stopped('gate_unavailable'));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    await tenMinutes();
    expect(h.calls.length).toBe(1);
    expect(screen.getByTestId('quality-gate-before-check').getAttribute('data-code')).toBe('gate_unavailable');
    expect(screen.queryByTestId('quality-gate-retry')).not.toBeInTheDocument();
  });

  it('rc126 browser gate on, server gate off: "not enabled on the server", never retried', async () => {
    flames('idle');
    h.answer = () => Promise.resolve(stopped('gate_not_enabled'));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    await tenMinutes();
    expect(h.calls.length).toBe(1);
    expect(screen.getByTestId('quality-gate-before-check').getAttribute('data-code')).toBe('gate_not_enabled');
  });

  it('rc126 a finished result: the final consultation is bounded too', async () => {
    flames('done');
    h.answer = (_f, _c, skull) => Promise.resolve(skull === 'pending' ? stopped('gate_unavailable')
      : stopped('gate_rate_limited', { seconds: 2 }));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    await tenMinutes();
    expect(h.calls.filter((s) => s !== 'pending').length).toBeLessThanOrEqual(4);
    expect(h.calls.filter((s) => s === 'pending').length).toBe(1);
  });
});
