/**
 * U1 (tenth review of PR #81; RC-126): the automatic retries of a rate-limited answer are STATE, never derived during
 * render from a mutable ref — exactly 3 retries, one timer per rate-limited answer, nothing scheduled and no countdown
 * while a request is in flight, and "Check again" only after the last answer arrived. Before the run and for the final
 * consultation. Fake timers; every answer is held until the test releases it. DRAFT, PENDING owner approval.
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
const limited = (seconds: number) => ({
  gate_version: 'quality-gate/1', policy_version: null, mode: null, decision: 'abstain', ai_may_run: false,
  ai_output_allowed: false, codes: ['gate_rate_limited'],
  checks: [{ check: 'platform', visit: null, status: 'abstain', code: 'gate_rate_limited', params: { seconds } }],
  attestable_visits: [], actions: {}, subject: { file_id: FILE, version: null },
});
const unavailable = () => ({ ...limited(1), codes: ['gate_unavailable'],
  checks: [{ check: 'platform', visit: null, status: 'abstain', code: 'gate_unavailable', params: {} }] });
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
const advance = async (ms: number) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); };

beforeEach(() => {
  vi.useFakeTimers();
  for (const k of Object.keys(h.flames)) delete h.flames[k];
  h.calls.length = 0;
  useViewerStore.setState({
    currentSeries: { id: 's', name: 'flair', format: 'nifti', file_id: FILE, total_slices: 4, metadata: { rows: 3, columns: 2 } },
  } as never);
});
afterEach(() => { vi.useRealTimers(); });

/** Drive one consultation that is always rate limited; each answer is held until released. */
async function exactlyThreeRetries(counted: (calls: string[]) => number, againId: string) {
  const held: Array<(v: unknown) => void> = [];
  const base = h.answer;
  h.answer = (f, c, skull) => (counted([skull]) ? new Promise((resolve) => held.push(resolve)) : base(f, c, skull));
  render(<BrowserFlamesCard flairFileId={FILE} />);
  await advance(300);
  for (let i = 0; i < 4; i += 1) {
    expect(counted(h.calls)).toBe(i + 1);
    // in flight: however long it takes, nothing else is asked, no countdown runs, no "Check again"
    await advance(120_000);
    expect(counted(h.calls)).toBe(i + 1);
    expect(screen.queryByTestId(againId)).not.toBeInTheDocument();
    expect(screen.queryByTestId('quality-gate-retry')).not.toBeInTheDocument();
    await act(async () => { held[i](limited(2)); await Promise.resolve(); });
    if (i < 3) {
      // ONE timer for this answer: the next request after the wait (with backoff), and only one. React renders the
      // retry when the step that fired the timer ends, so the request (after its debounce) comes in the next step.
      await advance(2000 * 2 ** i);
      await advance(400);
      expect(counted(h.calls)).toBe(i + 2);
    }
  }
  await advance(600_000);
  expect(counted(h.calls)).toBe(4);                                   // exactly 3 automatic retries
  expect(screen.getByTestId(againId)).toBeInTheDocument();            // only after the last answer arrived
}

describe('U1: automatic retries are state, one timer per rate-limited answer', () => {
  it('rc126 before the run: exactly 3 retries, no overlapping timers, "Check again" only after the last answer', async () => {
    flames('idle');
    await exactlyThreeRetries((calls) => calls.filter((s) => s === 'pending').length, 'quality-gate-check-again');
  });

  it('rc126 the final consultation: exactly 3 retries, no overlapping timers, "Check again" only after the last answer', async () => {
    flames('done');
    h.answer = () => Promise.resolve(unavailable());
    await exactlyThreeRetries((calls) => calls.filter((s) => s !== 'pending').length, 'quality-gate-check-again-final');
  });
});
