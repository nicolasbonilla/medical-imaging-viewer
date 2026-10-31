/**
 * PRB-026 (F06) — every segmentation showed "current_user" as its author: the viewer filled the author with
 * that placeholder (`useSegmentationData.ts:128`, `SegmentationPanel.tsx:333`) and the server never stored
 * who created a segmentation. Wanted: the author the server recorded (`metadata.created_by`, the
 * authenticated user at creation); "Author not recorded" for older segmentations — never a placeholder and
 * never the name of whoever happens to be signed in.
 */
import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import i18n from '@/i18n/config';

const apiGet = vi.fn();
vi.mock('@/services/apiClient', () => ({
  apiClient: { get: (...a: unknown[]) => apiGet(...a), put: vi.fn(), post: vi.fn() },
}));
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    createSegmentation: vi.fn(),
    deleteSegmentation: vi.fn(),
    getSegmentation: vi.fn(),
    listSegmentationsByFileIds: vi.fn().mockResolvedValue([]),
  },
}));

import { useSegmentationData } from './useSegmentationData';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { useViewerStore } from '@/store/useViewerStore';
import { SegmentationList } from '@/components/SegmentationList';

const helper = import.meta.glob('../utils/segmentationAuthor.ts', { eager: true }) as Record<
  string, { recordedAuthor?: (m: unknown) => string }>;
function recordedAuthor(m: unknown): string {
  const fn = Object.values(helper)[0]?.recordedAuthor;
  if (!fn) throw new Error('no recorded-author rule (utils/segmentationAuthor.ts::recordedAuthor)');
  return fn(m);
}

const FILE = 'patients/p1/studies/s1/series/x/flair.nii.gz';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function openSaved(metadata: Record<string, unknown>) {
  useSegmentationStore.setState({
    currentSegmentation: {
      segmentation_id: 'server-1', file_id: FILE, total_slices: 3,
      metadata: { file_id: FILE, created_at: 'x', modified_at: 'x', labels: [], description: 'Expert Rater 1', ...metadata },
    } as never,
  });
}

describe('PRB-026 segmentation author', () => {
  beforeEach(async () => {
    apiGet.mockReset();
    apiGet.mockRejectedValue(new Error('mask not needed in this test'));
    useSegmentationStore.getState().reset?.();
    useSegmentationStore.setState({ currentSegmentation: null, activeSegmentation: null });
    useViewerStore.setState({ currentStudyId: 's1', allFileIds: [], currentSeries: null });
    await i18n.changeLanguage('en');
  });

  it('rc088 prb026 the open segmentation carries the author the server recorded', async () => {
    openSaved({ created_by: 'dr_demo' });
    renderHook(() => useSegmentationData({}), { wrapper });
    await waitFor(() => expect(useSegmentationStore.getState().activeSegmentation).not.toBeNull());
    expect(useSegmentationStore.getState().activeSegmentation!.created_by).toBe('dr_demo');
  });

  it('rc088 prb026 a segmentation without a recorded author is never given the placeholder', async () => {
    openSaved({});
    renderHook(() => useSegmentationData({}), { wrapper });
    await waitFor(() => expect(useSegmentationStore.getState().activeSegmentation).not.toBeNull());
    expect(useSegmentationStore.getState().activeSegmentation!.created_by).toBe('');
  });

  it('rc088 prb026 the recorded-author rule reads metadata.created_by only', () => {
    expect(recordedAuthor({ created_by: 'dr_demo' })).toBe('dr_demo');
    expect(recordedAuthor({ created_by: '  ' })).toBe('');
    expect(recordedAuthor({})).toBe('');
    expect(recordedAuthor(null)).toBe('');
  });

  it('rc088 prb026 the list says "Author not recorded" when no author was stored', () => {
    const seg = { id: 's', name: 'Expert Rater 1', status: 'saved', progress_percentage: 0, slices_annotated: 0,
      total_slices: 3, created_by: '', created_at: '2026-10-28T10:00:00', modified_at: '2026-10-28T10:00:00',
      label_count: 1, primary_label_color: '#FF0000' };
    render(<SegmentationList segmentations={[seg as never, { ...seg, id: 't', created_by: 'dr_demo' } as never]}
      onLoad={() => {}} onDelete={() => {}} />);
    expect(screen.getByText('Author not recorded')).toBeInTheDocument();
    expect(screen.getByText('dr_demo')).toBeInTheDocument();
    expect(screen.queryByText('current_user')).toBeNull();
  });

  it('rc088 prb026 no source file fills an author with a placeholder', () => {
    const files = import.meta.glob(['../**/*.ts', '../**/*.tsx', '!../**/*.test.*'], { eager: true, query: '?raw', import: 'default' });
    const offenders = Object.entries(files).filter(([, raw]) => /created_by:\s*['"]current_user['"]/.test(String(raw)));
    expect(offenders.map(([f]) => f)).toEqual([]);
  });
});
