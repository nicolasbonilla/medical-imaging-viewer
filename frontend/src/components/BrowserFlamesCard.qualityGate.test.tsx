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
  answer: (() => Promise.resolve(null)) as (fileId: string, confirmed: boolean) => Promise<unknown>,
  calls: [] as [string, boolean][],
}));
vi.mock('@/hooks/useBrowserFlames', () => ({ useBrowserFlames: () => h.flames }));
vi.mock('@/services/qualityGate/api', () => ({
  requestQualityGate: (fileId: string, confirmed: boolean) => { h.calls.push([fileId, confirmed]); return h.answer(fileId, confirmed); },
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
const server = (visit: Record<string, unknown>, platform: GatePlatform) => {
  const inputs = { mode: 'single', visits: [{ ...visit, skull: 'pending' }] };
  return { ...evaluateGate({ ...inputs, platform }), inputs, platform };
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
    expect(h.calls[h.calls.length - 1]).toEqual([FILE, true]);
  });

  it('rc126 the agent switched off: the run stays disabled and the reason is shown', async () => {
    idle();
    h.answer = () => Promise.resolve(server(VISIT, { allowed: false, code: 'agent_switched_off' }));
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
    h.answer = () => Promise.resolve(server(VISIT, { allowed: false, code: 'agent_switched_off' }));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(await screen.findByTestId('quality-gate-output-hidden')).toBeInTheDocument();
    expect(screen.getByTestId('quality-gate-after').getAttribute('data-decision')).toBe('abstain');
    expect(screen.queryByText(/AI draft ready/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Open as AI draft/ })).not.toBeInTheDocument();
  });

  it('rc125 an unknown skull outcome hides the result', async () => {
    done(undefined);
    h.answer = () => Promise.resolve(server(VISIT, ON));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(await screen.findByTestId('quality-gate-output-hidden')).toBeInTheDocument();
    expect(screen.getByTestId('quality-gate-after').textContent).toMatch(/cannot confirm that the skull was removed/);
    expect(screen.queryByText(/AI draft ready/)).not.toBeInTheDocument();
  });

  it('rc127 the final check allows it: the result appears after the panel', async () => {
    done('skull-removed');
    h.answer = () => Promise.resolve(server(VISIT, ON));
    render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(await screen.findByText(/AI draft ready/)).toBeInTheDocument();
    expect(screen.getByTestId('quality-gate-after').getAttribute('data-decision')).toBe('proceed');
    expect(screen.queryByTestId('quality-gate-output-hidden')).not.toBeInTheDocument();
  });
});
