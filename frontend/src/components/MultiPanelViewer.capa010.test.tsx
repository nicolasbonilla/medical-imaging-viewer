/**
 * CAPA-010 — the multi-panel viewer (two or four sequences side by side).
 *
 *   RC-016 (HAZ-009): every panel carries the patient identity, so a panel copied or
 *          shown on its own is still attributed to its patient.
 *   RC-023 (HAZ-006): every panel reports the orientation of ITS OWN image (panels can
 *          hold differently stored series) and the standing laterality caveat.
 *
 * Rendered for real; only the image request is answered locally.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';

vi.mock('@/api/imaging', () => ({
  imagingAPI: {
    processImage: vi.fn(async (fileId: string) => ({
      id: fileId, name: fileId, format: 'nifti', total_slices: 2,
      metadata: {
        rows: 218, columns: 182, slices: 2,
        anatomical_orientation: fileId.includes('flair') ? 'LAS' : 'RAS',
      },
      slices: [0, 1].map((i) => ({ slice_index: i, image_data: `AAA${i}`, format: 'nifti', width: 182, height: 218 })),
    })),
  },
}));

import { MultiPanelViewer } from './MultiPanelViewer';
import { useMultiViewerStore } from '@/store/useMultiViewerStore';
import type { ImagingInstance } from '@/types';

const instance = (id: string, file: string, name: string): ImagingInstance => ({
  id, series_id: 'se1', sop_instance_uid: id, gcs_object_name: file, original_filename: name,
  content_type: 'application/gzip', file_size_bytes: 1, created_at: '2026-01-01T00:00:00Z',
});
const INSTANCES = [
  instance('i-flair', 'patients/p/studies/s/series/se1/flair.nii.gz', 'sub-01_FLAIR.nii.gz'),
  instance('i-t1', 'patients/p/studies/s/series/se1/t1.nii.gz', 'sub-01_T1w.nii.gz'),
];

const render = (ui: ReactElement) =>
  rtlRender(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

beforeEach(() => {
  useMultiViewerStore.getState().reset();
  useMultiViewerStore.getState().setLayout('1x2');
  useMultiViewerStore.getState().autoAssign([
    { instanceId: 'i-flair', sequence: 'FLAIR' },
    { instanceId: 'i-t1', sequence: 'T1w' },
  ]);
});

describe('RC-016 — patient identity in every multi-panel cell', () => {
  it('rc016 every panel renders the patient name and MRN', async () => {
    render(<MultiPanelViewer instances={INSTANCES} patientName="Ana Torres" patientMRN="MRN-99120" />);

    await waitFor(() => expect(screen.getAllByTestId('viewport-safety-overlay')).toHaveLength(2));
    const identities = screen.getAllByTestId('viewport-patient-identity');
    expect(identities).toHaveLength(2);
    for (const identity of identities) {
      expect(identity).toHaveTextContent('Ana Torres');
      expect(identity).toHaveTextContent('MRN-99120');
    }
  });

  it('rc016 every panel warns when the patient identity is absent', async () => {
    render(<MultiPanelViewer instances={INSTANCES} />);

    await waitFor(() => expect(screen.getAllByTestId('viewport-identity-missing')).toHaveLength(2));
  });
});

describe('RC-023 — each panel reports its own orientation and the caveat', () => {
  it('rc023 each panel shows the orientation of its own image, read from the server metadata', async () => {
    render(<MultiPanelViewer instances={INSTANCES} patientName="Ana Torres" patientMRN="MRN-99120" />);

    await waitFor(() => {
      const badges = screen.getAllByTestId('viewport-orientation').map((b) => b.textContent ?? '');
      expect(badges).toHaveLength(2);
      expect(badges[0]).toMatch(/^LAS/);
      expect(badges[1]).toMatch(/^RAS/);
    });
  });

  it('rc023 every panel carries the standing laterality caveat', async () => {
    render(<MultiPanelViewer instances={INSTANCES} patientName="Ana Torres" />);

    await waitFor(() => expect(screen.getAllByTestId('viewport-safety-overlay')).toHaveLength(2));
    for (const overlay of screen.getAllByTestId('viewport-safety-overlay')) {
      expect(within(overlay).getByText(/confirm side against the source study/i)).toBeInTheDocument();
    }
  });
});

describe('RC-023 — a panel only ever shows the orientation of the image it holds', () => {
  it('rc023 a panel keeps its orientation when the slice changes', async () => {
    render(<MultiPanelViewer instances={INSTANCES} patientName="Ana Torres" />);
    await waitFor(() => expect(screen.getAllByTestId('viewport-orientation')).toHaveLength(2));

    useMultiViewerStore.getState().setSliceIndex('panel-0', 1); // synchronised: both panels
    await waitFor(() => expect(useMultiViewerStore.getState().panels[0].imageData).toBe('data:image/png;base64,AAA1'));
    const badges = screen.getAllByTestId('viewport-orientation').map((b) => b.textContent ?? '');
    expect(badges[0]).toMatch(/^LAS/);
    expect(badges[1]).toMatch(/^RAS/);
  });

  it('rc023 reassigning a panel clears the previous image orientation until the new image reports its own', () => {
    const store = useMultiViewerStore.getState();
    store.setPanelImageData('panel-0', 'data:x', { rows: 1, columns: 1, slices: 1 }, 'LAS');
    expect(useMultiViewerStore.getState().panels[0].orientation).toBe('LAS');

    store.assignInstance('panel-0', 'i-t1', 'T1w');
    expect(useMultiViewerStore.getState().panels[0].orientation).toBeUndefined();

    // Auto-assignment: the reassigned panel AND the panels it empties forget the old orientation.
    store.setPanelImageData('panel-0', 'data:x', { rows: 1, columns: 1, slices: 1 }, 'LAS');
    store.setPanelImageData('panel-1', 'data:y', { rows: 1, columns: 1, slices: 1 }, 'RAS');
    store.autoAssign([{ instanceId: 'i-t1', sequence: 'T1w' }]);
    expect(useMultiViewerStore.getState().panels[0].orientation).toBeUndefined();
    expect(useMultiViewerStore.getState().panels[1].orientation).toBeUndefined();
  });
});
