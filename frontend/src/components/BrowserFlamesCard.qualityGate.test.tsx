/**
 * BrowserFlamesCard with the single quality gate ON (REQ-FUNC-117/118; RC-122, RC-125, RC-126, RC-127). DRAFT.
 *  - before the run: the backend's decision is shown, and an abstention keeps the run button disabled;
 *  - before the result: nothing of it is shown until the final consultation (backend's fresh answer + the
 *    worker's skull outcome) allows it; a switch turned off during the run, or an unknown skull, hides it.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@/i18n/config';

const h = vi.hoisted(() => ({
  flames: {} as Record<string, unknown>,
  answer: (() => Promise.resolve(null)) as (fileId: string, confirmed: boolean, skull: string) => Promise<unknown>,
  calls: [] as [string, boolean][],
  skulls: [] as string[],
}));
vi.mock('@/hooks/useBrowserFlames', () => ({ useBrowserFlames: () => h.flames }));
vi.mock('@/services/qualityGate/api', () => ({
  requestQualityGate: (fileId: string, confirmed: boolean, skull = 'pending') => {
    h.calls.push([fileId, confirmed]);
    h.skulls.push(skull);
    return h.answer(fileId, confirmed, skull);
  },
}));
vi.mock('@/config/features', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/config/features')>();
  return { ...mod, FEATURES: { ...mod.FEATURES, QUALITY_GATE: true } };
});

import { BrowserFlamesCard } from './BrowserFlamesCard';
import { useViewerStore } from '@/store/useViewerStore';
import { evaluateGate, type GatePlatform } from '@/services/qualityGate/gate';

const FILE = 'patients/p/studies/s/flair.nii.gz';
const VISIT = { sequence: 'FLAIR', physician_confirmed_flair: false, thickness: { state: 'native', effective_mm: 1 }, scanner: null };
const ON: GatePlatform = { allowed: true, code: null };
const server = (visit: Record<string, unknown>, platform: GatePlatform, fileId = FILE, skull = 'pending') => {
  const inputs = { mode: 'single', visits: [{ ...visit, skull }] };
  return { ...evaluateGate({ ...inputs, platform }), inputs, platform, subject: { file_id: fileId, version: 'v1' } };
};
const idle = () => Object.assign(h.flames, {
  status: 'idle', fraction: 0, message: '', error: null, startedAt: null, result: null, run: vi.fn(), cancel: vi.fn(), reset: vi.fn(),
});
const done = (inputPreparation?: string) => Object.assign(h.flames, {
  status: 'done', fraction: 1, message: '', error: null, startedAt: null, run: vi.fn(), cancel: vi.fn(), reset: vi.fn(),
  result: {
    fileId: FILE, maskApp: new Uint8Array(24), dims: [3, 2, 4], spacing: [1, 1, 1],
    summary: { lesionCount: 2, lesionVoxels: 10, lesionVolumeMl: 0.01, componentVolumesMl: [] },
    provenance: { pipeline: 'p', model: 'm', modelSha256: 'x', sourceCheckpointSha256: 'y', backend: 'wasm', threads: 1,
      onnxRuntimeWeb: '1.24.1', mirror: false, windows: 1, networkCalls: 1, resampledShape: [1, 1, 1], seconds: 60,
      generatedAt: '2026-11-12T00:00:00.000Z', sequenceEvidence: 'clinician', ...(inputPreparation ? { inputPreparation } : {}) },
  },
});

beforeEach(() => {
  for (const k of Object.keys(h.flames)) delete h.flames[k];
  h.calls.length = 0;
  h.skulls.length = 0;
  useViewerStore.setState({
    currentSeries: { id: 's', name: 'flair', format: 'nifti', file_id: FILE, total_slices: 4, metadata: { rows: 3, columns: 2 } },
  } as never);
});

describe('before the run (RC-122)', () => {
  it('rc122 a T1 image: the reason is shown and the run stays disabled even after the confirmation', async () => {
    idle();
    h.answer = () => Promise.resolve(server({ ...VISIT, sequence: 'T1' }, ON));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    fireEvent.click(screen.getByTestId('browser-flames-confirm-sequence').querySelector('input') as HTMLInputElement);
    const panel = await screen.findByTestId('quality-gate-before');
    await waitFor(() => expect(panel.getAttribute('data-decision')).toBe('abstain'));
    expect(screen.getByRole('button', { name: /Segment in this browser/ })).toBeDisabled();
    expect(h.calls).toEqual([[FILE, false]]);          // one call per file; the run checkbox is no attestation
    expect(screen.queryByTestId('quality-gate-attest')).not.toBeInTheDocument();
  });
});

describe('the physician attestation (S3, G13)', () => {
  const attest = () => screen.getByTestId('quality-gate-attest').querySelector('input') as HTMLInputElement;
  it('rc122 offered only for an unknown or missing sequence, unticked, and never for another sequence', async () => {
    for (const [sequence, offered] of [['missing', true], ['unknown', true], ['other', false], ['T2', false], ['FLAIR', false]] as const) {
      idle();
      h.answer = () => Promise.resolve(server({ ...VISIT, sequence }, ON));
      const { unmount } = render(<BrowserFlamesCard flairFileId={FILE} />);
      await screen.findByTestId('quality-gate-before');
      if (offered) expect(attest().checked).toBe(false);
      else expect(screen.queryByTestId('quality-gate-attest')).not.toBeInTheDocument();
      unmount();
    }
  });

  it('rc122 sent only when ticked, on Run, never on a toggle; reset on a file change', async () => {
    idle();
    h.answer = (f, confirmed) => Promise.resolve(server({ ...VISIT, sequence: 'missing', physician_confirmed_flair: confirmed }, ON, f));
    const { rerender } = render(<BrowserFlamesCard flairFileId={FILE} />);
    await screen.findByTestId('quality-gate-before');
    const run = screen.getByRole('button', { name: /Segment in this browser/ });
    fireEvent.click(screen.getByTestId('browser-flames-confirm-sequence').querySelector('input') as HTMLInputElement);
    expect(run).toBeDisabled();                        // the run confirmation alone does not lift 'missing'
    fireEvent.click(attest());
    fireEvent.click(attest());
    fireEvent.click(attest());
    expect(h.calls).toEqual([[FILE, false]]);          // toggles are evaluated locally, the backend is not called
    await waitFor(() => expect(run).not.toBeDisabled());
    fireEvent.click(run);
    await waitFor(() => expect(h.calls).toEqual([[FILE, false], [FILE, true]]));
    await waitFor(() => expect(h.flames.run).toHaveBeenCalledTimes(1));
    const OTHER = 'patients/p/studies/s/other.nii.gz';
    rerender(<BrowserFlamesCard flairFileId={OTHER} />);
    await waitFor(() => expect(h.calls[h.calls.length - 1]).toEqual([OTHER, false]));
    await waitFor(() => expect(attest().checked).toBe(false));
  });

  it('rc126 the agent switched off: the run stays disabled and the reason is shown', async () => {
    idle();
    h.answer = (f, _c, skull) => Promise.resolve(server(VISIT, { allowed: false, code: 'agent_switched_off' }, f, skull));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    fireEvent.click(screen.getByTestId('browser-flames-confirm-sequence').querySelector('input') as HTMLInputElement);
    await waitFor(() => expect(screen.getByTestId('quality-gate-before').textContent).toMatch(/switched off/));
    expect(screen.getByRole('button', { name: /Segment in this browser/ })).toBeDisabled();
  });
});

describe('before the result (RC-125, RC-126, RC-127)', () => {
  it('rc127 nothing of the result is shown before the final answer', () => {
    done('skull-removed');
    h.answer = () => new Promise(() => undefined);
    render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(screen.getAllByTestId('quality-gate-checking').length).toBeGreaterThan(0);
    expect(screen.queryByText(/AI draft ready/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Open as AI draft/ })).not.toBeInTheDocument();
  });

  it('rc126 a switch turned off during the run hides the result and says why', async () => {
    done('skull-removed');
    h.answer = (f, _c, skull) => Promise.resolve(server(VISIT, { allowed: false, code: 'agent_switched_off' }, f, skull));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(await screen.findByTestId('quality-gate-output-hidden')).toBeInTheDocument();
    expect(screen.getByTestId('quality-gate-after').getAttribute('data-decision')).toBe('abstain');
    expect(screen.queryByText(/AI draft ready/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Open as AI draft/ })).not.toBeInTheDocument();
  });

  it('rc125 an unknown skull outcome hides the result', async () => {
    done(undefined);
    h.answer = (f, _c, skull) => Promise.resolve(server(VISIT, ON, f, skull));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(await screen.findByTestId('quality-gate-output-hidden')).toBeInTheDocument();
    expect(screen.getByTestId('quality-gate-after').textContent).toMatch(/cannot confirm that the skull was removed/);
    expect(screen.queryByText(/AI draft ready/)).not.toBeInTheDocument();
  });

  it('rc127 the final check allows it: the result appears after the panel', async () => {
    done('skull-removed');
    h.answer = (f, _c, skull) => Promise.resolve(server(VISIT, ON, f, skull));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(await screen.findByText(/AI draft ready/)).toBeInTheDocument();
    expect(screen.getByTestId('quality-gate-after').getAttribute('data-decision')).toBe('proceed');
    expect(screen.queryByTestId('quality-gate-output-hidden')).not.toBeInTheDocument();
  });
});

describe('the server decides the output, and no stale answer acts (G17, G18)', () => {
  type Pending = { f: string; skull: string; resolve: (v: unknown) => void };
  const deferred = (queue: Pending[]) => (f: string, _c: boolean, skull: string) =>
    new Promise((resolve) => queue.push({ f, skull, resolve }));

  it('rc126 G17 the final consultation reports the skull outcome and the server decides', async () => {
    done('skull-removed');
    h.answer = (f, _c, skull) => Promise.resolve(server(VISIT, ON, f, skull));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(await screen.findByText(/AI draft ready/)).toBeInTheDocument();
    expect(h.skulls).toContain('stripped');
  });

  it('rc126 G17 an answer that the same rule does not reproduce shows nothing', async () => {
    done('skull-removed');
    const forged = (f: string) => ({ ...server(VISIT, ON, f, 'stripped'), inputs: { mode: 'single', visits: [{ ...VISIT, skull: 'unknown' }] } });
    h.answer = (f) => Promise.resolve(forged(f));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(await screen.findByTestId('quality-gate-output-hidden')).toBeInTheDocument();
    expect(screen.queryByText(/AI draft ready/)).not.toBeInTheDocument();
  });

  it('rc122 G18 the answer for A never applies once B is selected', async () => {
    idle();
    const queue: Pending[] = [];
    h.answer = deferred(queue);
    const B = 'patients/p/studies/s/b.nii.gz';
    const { rerender } = render(<BrowserFlamesCard flairFileId={FILE} />);
    await waitFor(() => expect(queue.length).toBe(1));
    rerender(<BrowserFlamesCard flairFileId={B} />);
    queue[0].resolve(server(VISIT, ON, FILE));
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId('quality-gate-before')).not.toBeInTheDocument();
    await waitFor(() => expect(queue.length).toBe(2));
    queue[1].resolve(server({ ...VISIT, sequence: 'T1' }, ON, B));
    await waitFor(() => expect(screen.getByTestId('quality-gate-before').getAttribute('data-decision')).toBe('abstain'));
  });

  it('rc122 G18 one request per click, Run disabled meanwhile, and no run of A once B is selected', async () => {
    idle();
    const queue: Pending[] = [];
    h.answer = deferred(queue);
    const B = 'patients/p/studies/s/b.nii.gz';
    const { rerender } = render(<BrowserFlamesCard flairFileId={FILE} />);
    await waitFor(() => expect(queue.length).toBe(1));
    queue[0].resolve(server(VISIT, ON, FILE));
    await screen.findByTestId('quality-gate-before');
    fireEvent.click(screen.getByTestId('browser-flames-confirm-sequence').querySelector('input') as HTMLInputElement);
    const run = screen.getByRole('button', { name: /Segment in this browser/ });
    await waitFor(() => expect(run).not.toBeDisabled());
    fireEvent.click(run);
    fireEvent.click(run);
    expect(queue.length).toBe(2);
    expect(run).toBeDisabled();
    rerender(<BrowserFlamesCard flairFileId={B} />);
    queue[1].resolve(server(VISIT, ON, FILE));
    await new Promise((r) => setTimeout(r, 50));
    expect(h.flames.run).not.toHaveBeenCalled();
  });
});

describe('G23: the card always reaches a decided state for the selected file', () => {
  type Pending = { f: string; resolve: (v: unknown) => void };
  it('rc122 A -> B -> A during the final consultation ends decided for A, never stuck on checking', async () => {
    done('skull-removed');
    const queue: Pending[] = [];
    h.answer = (f, _c, skull) => (skull === 'pending' ? Promise.resolve(server(VISIT, ON, f))
      : new Promise((resolve) => queue.push({ f, resolve: (v) => resolve(v ?? server(VISIT, ON, f, skull)) })));
    const B = 'patients/p/studies/s/b.nii.gz';
    const { rerender } = render(<BrowserFlamesCard flairFileId={FILE} />);
    await waitFor(() => expect(queue.length).toBe(1));
    rerender(<BrowserFlamesCard flairFileId={B} />);
    queue[0].resolve(undefined);                       // A's answer arrives while B is selected: discarded
    await new Promise((r) => setTimeout(r, 50));
    rerender(<BrowserFlamesCard flairFileId={FILE} />);
    await waitFor(() => expect(queue.length).toBe(2)); // back on A: consulted again
    queue[1].resolve(undefined);
    expect(await screen.findByTestId('quality-gate-after')).toBeInTheDocument();
    expect(await screen.findByText(/AI draft ready/)).toBeInTheDocument();
  });
});
