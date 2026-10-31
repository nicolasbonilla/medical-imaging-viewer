/**
 * PRB-003 (RC-072; review of PR #68, finding 9) — the healthy-brain notice in the segmentation panel, driven
 * through the real panel (it replaces a source-text check). Written before the correction: on 4c601f2 the
 * notice was shown for every 'automatic' segmentation, structure parcellations included, and said
 * "automatic marking" rather than automatic LESION marking.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    listSegmentationsByFileIds: vi.fn(async () => []),
    listSegmentations: vi.fn(async () => []),
    getSegmentation: vi.fn(),
    deleteSegmentation: vi.fn(),
  },
}));
vi.mock('./ClinicalToolsPanel', () => ({ ClinicalToolsPanel: () => null }));
vi.mock('./ConformalPanel', () => ({ ConformalPanel: () => null }));
vi.mock('./SegmentationList', () => ({ SegmentationList: () => null }));

import { SegmentationPanel } from './SegmentationPanel';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { useViewerStore } from '@/store/useViewerStore';

const NOTICE = /Automatic lesion marking also marks spots in most healthy brains/;

function open(segmentationType: string | null, validationSource: string | null) {
  useViewerStore.setState({ currentSeries: { id: 's', file_id: 'f.nii.gz' }, allFileIds: ['f.nii.gz'] } as never);
  useSegmentationStore.setState({
    activeSegmentation: {
      id: 'seg-1', patient_id: '', study_id: '', series_id: '', name: 'Lesions', segmentation_type: 'manual',
      ai_provenance: null, status: 'in_progress', progress_percentage: 0, slices_annotated: 0, total_slices: 10,
      created_by: 'u', labels: [{ id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false }],
      created_at: 'T0', modified_at: 'T1',
    } as never,
    currentSegmentation: {
      segmentation_id: 'seg-1', file_id: 'f.nii.gz', total_slices: 10,
      metadata: { file_id: 'f.nii.gz', created_at: 'T0', modified_at: 'T1', labels: [],
                  segmentation_type: segmentationType, validation_source: validationSource },
    } as never,
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><SegmentationPanel /></QueryClientProvider>);
  fireEvent.click(screen.getByRole('button', { name: /Edit/ }));
}

describe('RC-072 healthy-brain notice in the segmentation panel', () => {
  it.each([
    ['automatic', 'lst-ai-v1.0.3', true],
    ['automatic', 'flames-v1.0', true],
    ['automatic', 'synthseg-v2.0', false],
    ['automatic', 'mindglide-v1.0-structures', false],
    [null, null, false],
  ])('rc072 review1 %s / %s -> notice %s', (type, source, shown) => {
    open(type, source);
    const notice = screen.queryByTestId('automatic-marking-notice');
    if (shown) expect(notice).toHaveTextContent(NOTICE);
    else expect(notice).not.toBeInTheDocument();
  });
});
