/**
 * BrowserFlamesCard — what the clinician SEES (CP-FLAMES-BROWSER-001):
 *  - an empty result is an explicit warning, never a silent "0 lesions" (REQ-FUNC-036, RC-051);
 *  - opening the draft over unsaved work asks first and touches nothing until an explicit choice
 *    (REQ-SAFE-032, RC-050);
 *  - the draft is handed over WITH its AI provenance (REQ-SAFE-030);
 *  - the expected duration is stated before the run;
 *  - licence and attribution notices are reachable (FLAMeS CC BY 4.0, Neurodesk/nnU-Net Apache-2.0).
 */
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

const flamesState: Record<string, unknown> = {};
vi.mock('@/hooks/useBrowserFlames', () => ({ useBrowserFlames: () => flamesState }));

import { BrowserFlamesCard } from './BrowserFlamesCard';
import { useViewerStore } from '@/store/useViewerStore';
import { useSegmentationStore, type ImportDraftResult } from '@/store/useSegmentationStore';
import { FLAMES_FOLD0_MODEL } from '@/services/flames/plan';

const FILE = 'patients/p/studies/s/flair.nii.gz';
const provenance = {
  pipeline: 'mstool-flames-browser/0.2.0-prototype',
  model: 'FLAMeS fold 0',
  modelSha256: FLAMES_FOLD0_MODEL.sha256,
  sourceCheckpointSha256: FLAMES_FOLD0_MODEL.sourceCheckpointSha256,
  backend: 'wasm',
  threads: 1,
  onnxRuntimeWeb: '1.24.1',
  mirror: false,
  windows: 1,
  networkCalls: 1,
  resampledShape: [1, 1, 1],
  seconds: 1200,
  generatedAt: '2026-10-17T20:00:00.000Z',
};

function setResult(lesionCount: number, lesionVoxels: number) {
  Object.assign(flamesState, {
    status: 'done',
    fraction: 1,
    message: '',
    error: null,
    startedAt: null,
    run: vi.fn(),
    cancel: vi.fn(),
    reset: vi.fn(),
    result: {
      fileId: FILE,
      maskApp: new Uint8Array(4 * 3 * 2),
      dims: [3, 2, 4],
      spacing: [1, 1, 1],
      summary: { lesionCount, lesionVoxels, lesionVolumeMl: lesionVoxels / 1000, componentVolumesMl: [] },
      provenance,
    },
  });
}

beforeEach(() => {
  for (const k of Object.keys(flamesState)) delete flamesState[k];
  useViewerStore.setState({
    currentSeries: { id: 's', name: 'flair', format: 'nifti', file_id: FILE, total_slices: 4, metadata: { rows: 3, columns: 2 } },
  } as never);
});

describe('empty result (REQ-FUNC-036)', () => {
  it('rc051 shows an explicit warning and blocks opening until the clinician acknowledges it', () => {
    setResult(0, 0);
    const importDraft = vi.fn((): ImportDraftResult => ({ ok: true }));
    useSegmentationStore.setState({ importDraftCallback: importDraft });
    render(<BrowserFlamesCard flairFileId={FILE} />);

    expect(screen.getByTestId('browser-flames-empty')).toHaveTextContent(/does NOT show that the scan is free of lesions/);
    expect(screen.queryByText(/AI draft ready/)).not.toBeInTheDocument();
    const open = screen.getByRole('button', { name: /Open as AI draft/ });
    expect(open).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    expect(open).toBeEnabled();
    fireEvent.click(open);
    expect(importDraft).toHaveBeenCalledTimes(1);
    const meta = (importDraft.mock.calls[0] as unknown[])[3] as { description: string; aiProvenance: { annotated_voxels: number } };
    expect(meta.description).toMatch(/EMPTY RESULT/);
    expect(meta.aiProvenance.annotated_voxels).toBe(0);
  });

  it('a non-empty result is summarised normally', () => {
    setResult(3, 120);
    useSegmentationStore.setState({ importDraftCallback: vi.fn((): ImportDraftResult => ({ ok: true })) });
    render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(screen.queryByTestId('browser-flames-empty')).not.toBeInTheDocument();
    expect(screen.getByText(/AI draft ready/)).toBeInTheDocument();
  });
});

describe('unsaved work (REQ-SAFE-032)', () => {
  it('rc050 asks before replacing unsaved work and only discards after an explicit choice', () => {
    setResult(3, 120);
    const importDraft = vi
      .fn()
      .mockReturnValueOnce({ ok: false, reason: 'unsaved-work', openSegmentationName: 'Dr. A manual' })
      .mockReturnValueOnce({ ok: false, reason: 'unsaved-work', openSegmentationName: 'Dr. A manual' })
      .mockReturnValueOnce({ ok: true });
    useSegmentationStore.setState({ importDraftCallback: importDraft });
    render(<BrowserFlamesCard flairFileId={FILE} />);

    fireEvent.click(screen.getByRole('button', { name: /Open as AI draft/ }));
    expect(importDraft.mock.calls[0][4]).toEqual({ discardUnsavedWork: false });
    expect(screen.getByTestId('browser-flames-unsaved')).toHaveTextContent('Dr. A manual');

    fireEvent.click(screen.getByRole('button', { name: /Keep my work/ }));
    expect(screen.queryByTestId('browser-flames-unsaved')).not.toBeInTheDocument();
    expect(importDraft).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: /Open as AI draft/ }));
    fireEvent.click(screen.getByRole('button', { name: /Discard my unsaved changes/ }));
    expect(importDraft).toHaveBeenCalledTimes(3);
    expect(importDraft.mock.calls[2][4]).toEqual({ discardUnsavedWork: true });
    expect(screen.getByText(/never saved automatically/)).toBeInTheDocument();
  });

  it('rc047 hands the draft over with its AI provenance (model, version, SHA-256, fold, unreviewed)', () => {
    setResult(3, 120);
    const importDraft = vi.fn((): ImportDraftResult => ({ ok: true }));
    useSegmentationStore.setState({ importDraftCallback: importDraft });
    render(<BrowserFlamesCard flairFileId={FILE} />);
    fireEvent.click(screen.getByRole('button', { name: /Open as AI draft/ }));
    const meta = (importDraft.mock.calls[0] as unknown[])[3] as { aiProvenance: Record<string, unknown>; labels: { name: string }[] };
    expect(meta.aiProvenance).toMatchObject({
      kind: 'ai_draft',
      model_name: 'FLAMeS',
      model_sha256: FLAMES_FOLD0_MODEL.sha256,
      fold: 0,
      review_status: 'unreviewed',
    });
    expect(String(meta.aiProvenance.model_version)).toMatch(/17955359 v2\.0/);
    expect(meta.labels[1].name).toMatch(/AI draft, unreviewed/);
  });
});

describe('duration and licences', () => {
  it('states the expected duration before the run', () => {
    Object.assign(flamesState, { status: 'idle', result: null, run: vi.fn(), cancel: vi.fn() });
    render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(screen.getByTestId('browser-flames-estimate')).toHaveTextContent(/minutes/);
    expect(screen.getByTestId('browser-flames-estimate')).toHaveTextContent(/never changes your segmentation/);
  });

  it('licence and attribution notices are reachable in the card, with the licence texts shipped', () => {
    Object.assign(flamesState, { status: 'idle', result: null, run: vi.fn(), cancel: vi.fn() });
    render(<BrowserFlamesCard flairFileId={FILE} />);
    const panel = screen.getByTestId('browser-flames-licences');
    expect(panel).toHaveTextContent('CC BY 4.0');
    expect(panel).toHaveTextContent('10.5281/zenodo.17955359');
    expect(panel).toHaveTextContent('Apache-2.0');
    expect(panel).toHaveTextContent(/neurodesk/i);
    const links = Array.from(panel.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(links).toContain('https://creativecommons.org/licenses/by/4.0/');
    expect(links).toContain('/licenses/Apache-2.0.txt');
    const pub = join(__dirname, '..', '..', 'public', 'licenses');
    expect(readFileSync(join(pub, 'Apache-2.0.txt'), 'utf-8')).toMatch(/Apache License[\s\S]*Version 2\.0/);
    expect(existsSync(join(pub, 'onnxruntime-web-MIT.txt'))).toBe(true);
    expect(readFileSync(join(pub, 'flames-NOTICE.txt'), 'utf-8')).toMatch(/CC BY 4\.0/);
  });
});
