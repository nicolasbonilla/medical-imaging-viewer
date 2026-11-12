/**
 * Sixth review of PR #81 (A1, U2, U3; RC-122, RC-126, RC-127). DRAFT, PENDING owner approval.
 * The server is the only place that decides: the card shows the server's answers as they are (built here exactly as the
 * server sends them — no rule in the browser), offers the attestation only when the answer says so, retries a
 * rate-limited or unavailable answer by itself after the server's wait with a countdown, and keys the final decision
 * to the RUN, so a re-run of the same file never shows the previous run's decision.
 */
import type { ReactElement } from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@/i18n/config';

const h = vi.hoisted(() => ({
  flames: {} as Record<string, unknown>,
  answer: (() => Promise.resolve(null)) as (fileId: string, confirmed: boolean, skull: string) => Promise<unknown>,
  calls: [] as [string, boolean, string][],
  panels: [] as string[],
}));
vi.mock('@/hooks/useBrowserFlames', () => ({ useBrowserFlames: () => h.flames }));
vi.mock('@/services/qualityGate/api', () => ({
  requestQualityGate: (fileId: string, confirmed: boolean, skull = 'pending') => {
    h.calls.push([fileId, confirmed, skull]);
    return h.answer(fileId, confirmed, skull);
  },
}));
vi.mock('@/config/features', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/config/features')>();
  return { ...mod, FEATURES: { ...mod.FEATURES, QUALITY_GATE: true } };
});
vi.mock('./QualityGatePanel', async (importOriginal) => {
  const mod = await importOriginal<typeof import('./QualityGatePanel')>();
  const Real = mod.QualityGatePanel as unknown as (p: Record<string, unknown>) => ReactElement;
  const Spy = (props: { result: { decision: string }; testId?: string }) => {
    h.panels.push(`${props.testId}:${props.result.decision}`);
    return <Real {...(props as unknown as Record<string, unknown>)} />;
  };
  return { ...mod, QualityGatePanel: Spy, default: Spy };
});

import { BrowserFlamesCard } from './BrowserFlamesCard';
import { useViewerStore } from '@/store/useViewerStore';

const FILE = 'patients/p/studies/s/flair.nii.gz';
type Answer = Record<string, unknown>;
/** An answer as the server sends it (POST /clinical/quality-gate). */
const answer = (decision: string, codes: string[], extra: Answer = {}, fileId = FILE): Answer => ({
  gate_version: 'quality-gate/1', policy_version: 'p', mode: 'single', decision,
  ai_may_run: decision !== 'abstain', ai_output_allowed: decision === 'proceed' || decision === 'proceed_with_warnings',
  codes, checks: codes.map((code) => ({ check: code.split('_')[0], visit: 'study', status: decision === 'proceed_with_warnings' ? 'warn'
    : decision, code, params: {} })),
  attestable_visits: [], actions: {}, platform: { allowed: true, code: null },
  inputs: { mode: 'single', visits: [{ sequence: 'FLAIR' }] }, subject: { file_id: fileId, version: 'v1' }, ...extra,
});
const limited = (seconds: number) => answer('abstain', ['gate_rate_limited'], {
  checks: [{ check: 'platform', visit: null, status: 'abstain', code: 'gate_rate_limited', params: { seconds } }] });
const result = () => ({
  fileId: FILE, maskApp: new Uint8Array(24), dims: [3, 2, 4], spacing: [1, 1, 1],
  summary: { lesionCount: 2, lesionVoxels: 10, lesionVolumeMl: 0.01, componentVolumesMl: [] },
  provenance: { pipeline: 'p', model: 'm', modelSha256: 'x', sourceCheckpointSha256: 'y', backend: 'wasm', threads: 1,
    onnxRuntimeWeb: '1.24.1', mirror: false, windows: 1, networkCalls: 1, resampledShape: [1, 1, 1], seconds: 60,
    generatedAt: '2026-11-12T00:00:00.000Z', sequenceEvidence: 'clinician', inputPreparation: 'skull-removed' },
});
const flames = (status: string, res: unknown = null) => Object.assign(h.flames, {
  status, fraction: status === 'done' ? 1 : 0, message: '', error: null, startedAt: null, result: res,
  run: vi.fn(), cancel: vi.fn(), reset: vi.fn(),
});

beforeEach(() => {
  for (const k of Object.keys(h.flames)) delete h.flames[k];
  h.calls.length = 0;
  h.panels.length = 0;
  useViewerStore.setState({
    currentSeries: { id: 's', name: 'flair', format: 'nifti', file_id: FILE, total_slices: 4, metadata: { rows: 3, columns: 2 } },
  } as never);
});

describe('A1: the card shows the server answer as it is', () => {
  it('rc122 the attestation is offered when the answer names the visit as attestable, and the server decides on Run', async () => {
    flames('idle');
    h.answer = (f, confirmed) => Promise.resolve(confirmed
      ? answer('pending', ['sequence_confirmed_by_physician', 'skull_pending'], { ai_may_run: true }, f)
      : answer('abstain', ['sequence_missing'], { attestable_visits: ['study'] }, f));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    await screen.findByTestId('quality-gate-before');
    fireEvent.click(screen.getByTestId('browser-flames-confirm-sequence').querySelector('input') as HTMLInputElement);
    const run = screen.getByRole('button', { name: /Segment in this browser/ });
    expect(run).toBeDisabled();
    fireEvent.click(screen.getByTestId('quality-gate-attest').querySelector('input') as HTMLInputElement);
    await waitFor(() => expect(run).not.toBeDisabled());
    fireEvent.click(run);
    await waitFor(() => expect(h.flames.run).toHaveBeenCalledTimes(1));
    expect(h.calls.map((c) => c[1])).toEqual([false, true]);
  });
});

describe('U2: a rate-limited or unavailable answer is retried by itself, with a countdown', () => {
  it('rc126 before the run: the wait is shown, the check is repeated, and Run becomes possible', async () => {
    flames('idle');
    let n = 0;
    h.answer = (f) => Promise.resolve(n++ === 0 ? { ...limited(1), subject: { file_id: f, version: null } } : answer('pending', ['skull_pending'], {}, f));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(await screen.findByTestId('quality-gate-retry')).toHaveTextContent(/1/);
    await waitFor(() => expect(h.calls.length).toBe(2), { timeout: 4000 });
    fireEvent.click(screen.getByTestId('browser-flames-confirm-sequence').querySelector('input') as HTMLInputElement);
    await waitFor(() => expect(screen.getByRole('button', { name: /Segment in this browser/ })).not.toBeDisabled());
    expect(screen.queryByTestId('quality-gate-retry')).not.toBeInTheDocument();
  });

  it('rc127 before the result: a rate-limited final answer is retried and the result is then shown', async () => {
    flames('done', result());
    let finals = 0;
    h.answer = (f, _c, skull) => Promise.resolve(skull === 'pending' ? answer('pending', ['skull_pending'], {}, f)
      : finals++ === 0 ? { ...limited(1), subject: { file_id: f, version: null } } : answer('proceed', [], {}, f));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(await screen.findByTestId('quality-gate-retry')).toBeInTheDocument();
    expect(await screen.findByText(/AI draft ready/, {}, { timeout: 4000 })).toBeInTheDocument();
  });
});

describe('U3: the final decision belongs to the run', () => {
  it('rc126 a re-run of the same file never shows the previous run\'s decision, not even on its first render', async () => {
    flames('done', result());
    h.answer = (f, _c, skull) => (skull === 'pending' ? Promise.resolve(answer('pending', ['skull_pending'], {}, f))
      : h.calls.filter((c) => c[2] !== 'pending').length === 1 ? Promise.resolve(answer('proceed', [], {}, f))
        : new Promise(() => undefined));
    const { rerender } = render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(await screen.findByText(/AI draft ready/)).toBeInTheDocument();
    h.panels.length = 0;
    flames('done', result());                            // a new run of the same file: a new result object
    rerender(<BrowserFlamesCard flairFileId={FILE} />);
    expect(h.panels.filter((p) => p.startsWith('quality-gate-after'))).toEqual([]);
    expect(screen.queryByText(/AI draft ready/)).not.toBeInTheDocument();
  });
});
