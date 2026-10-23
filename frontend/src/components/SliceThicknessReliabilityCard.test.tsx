/**
 * CP-SLICE-THICKNESS-001 (DRAFT, PENDING owner approval) — what the doctor sees on the
 * "reliability by slice thickness" card (RC-055, RC-056, RC-057), rendered.
 *
 * Negative controls: scripts/safety/slice_thickness_negative_controls.py.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ImageSeriesResponse } from '@/types';

const lang = vi.hoisted(() => ({ value: 'en' }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, d?: string) => d ?? k, i18n: { language: lang.value } }),
}));

const getMetadata = vi.hoisted(() => vi.fn());
vi.mock('@/api/imaging', () => ({ imagingAPI: { getMetadata } }));

import SliceThicknessReliabilityCard from './SliceThicknessReliabilityCard';
import { useViewerStore } from '@/store/useViewerStore';

const PROC = 'patients/p/studies/s/series/a/proc.gz';
const ORIG = 'patients/p/studies/s/series/b/orig.gz';
const OTHER = 'patients/p/studies/s/series/c/other.gz';
const INSTANCES = [
  { gcs_object_name: PROC, original_filename: 'sub-01_desc-preproc_FLAIR.nii.gz' },
  { gcs_object_name: ORIG, original_filename: 'sub-01_FLAIR.nii.gz' },
];

function series(fileId: string, metadata: Record<string, unknown>): ImageSeriesResponse {
  return { id: fileId, name: fileId, format: 'nifti', total_slices: 10, metadata, file_id: fileId } as unknown as ImageSeriesResponse;
}

const dicomNative = (mm: number) => ({ state: 'native', effective_mm: mm, source: 'dicom_header', slice_thickness_mm: mm });

function renderCard(props: { sourceFileId?: string; studyInstances?: typeof INSTANCES }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SliceThicknessReliabilityCard {...props} />
    </QueryClientProvider>,
  );
}

async function card() {
  await waitFor(() => expect(screen.queryByTestId('stc-loading')).toBeNull());
  return screen.getByTestId('stc-card');
}

beforeEach(() => {
  lang.value = 'en';
  getMetadata.mockReset();
  useViewerStore.setState({ currentSeries: null });
});
afterEach(() => useViewerStore.setState({ currentSeries: null }));

describe('RC-055 — the thickness shown is that of the segmentation\'s own acquisition', () => {
  it('rc055 the loaded image is used only when it is the segmentation\'s image', async () => {
    // The viewer shows another file (natively thin); the segmentation's image is unknown.
    useViewerStore.setState({ currentSeries: series(OTHER, { acquisition_geometry: dicomNative(1) }) });
    getMetadata.mockResolvedValue({ metadata: { acquisition_geometry: { state: 'not_determinable', reason: 'missing' } } });
    renderCard({ sourceFileId: ORIG, studyInstances: INSTANCES });
    await card();
    expect(getMetadata).toHaveBeenCalledWith(ORIG);
    expect(screen.getByTestId('stc-thickness').dataset.state).toBe('not_determinable');
    expect(screen.queryByTestId('stc-band')).toBeNull();
  });

  it('rc055 the legacy slice_thickness (1.0 mm default) is never shown as the thickness', async () => {
    useViewerStore.setState({ currentSeries: series(ORIG, { slice_thickness: 1.0, pixel_spacing: [1, 1] }) });
    renderCard({ sourceFileId: ORIG, studyInstances: INSTANCES });
    await card();
    expect(getMetadata).not.toHaveBeenCalled();
    expect(screen.getByTestId('stc-thickness').dataset.state).toBe('not_determinable');
    expect(screen.getByTestId('stc-thickness').textContent).not.toMatch(/1\s*mm/);
  });

  it('rc055 a processed 1-mm image reads the original FLAIR of the study and names it', async () => {
    useViewerStore.setState({ currentSeries: series(PROC, { acquisition_geometry: { state: 'not_determinable', reason: 'template_grid', source: 'nifti_grid' } }) });
    getMetadata.mockResolvedValue({ metadata: { acquisition_geometry: dicomNative(6) } });
    renderCard({ sourceFileId: PROC, studyInstances: INSTANCES });
    await card();
    expect(getMetadata).toHaveBeenCalledWith(ORIG);
    const thickness = screen.getByTestId('stc-thickness');
    expect(thickness.dataset.state).toBe('native');
    expect(thickness.textContent).toContain('6 mm');
    expect(thickness.textContent).toContain('sub-01_FLAIR.nii.gz');
    expect(screen.getByTestId('stc-band').textContent).toBe('4.5-6.5 mm');
  });

  it('rc055 a processed image without a single original FLAIR is not determinable, with the reason', async () => {
    useViewerStore.setState({ currentSeries: series(PROC, { acquisition_geometry: { state: 'not_determinable', reason: 'template_grid' } }) });
    renderCard({ sourceFileId: PROC, studyInstances: [INSTANCES[0]] });
    await card();
    expect(getMetadata).not.toHaveBeenCalled();
    expect(screen.getByTestId('stc-thickness').dataset.state).toBe('not_determinable');
    expect(screen.getByTestId('stc-reasons').textContent).toMatch(/template grid/);
    expect(screen.getByTestId('stc-reasons').textContent).toMatch(/no original FLAIR/);
  });

  it('rc055 a request failure is not determinable, never a guess', async () => {
    getMetadata.mockRejectedValue(new Error('network'));
    renderCard({ sourceFileId: ORIG, studyInstances: INSTANCES });
    await card();
    expect(screen.getByTestId('stc-thickness').dataset.state).toBe('not_determinable');
    expect(screen.getByTestId('stc-reasons').textContent).toMatch(/could not be read/);
  });
});

describe('RC-056 — no false-lesion rate on the card', () => {
  it('rc056 thick slices: false-lesion rate not shown, with the >= 10 site-patient condition', async () => {
    useViewerStore.setState({ currentSeries: series(ORIG, { acquisition_geometry: dicomNative(5) }) });
    renderCard({ sourceFileId: ORIG, studyInstances: INSTANCES });
    await card();
    const fl = screen.getByTestId('stc-false-lesion').textContent ?? '';
    expect(fl).toMatch(/not shown/);
    expect(fl).toMatch(/at least 10 patients from this site/);
    expect(fl).not.toMatch(/%/);
  });

  it('rc056 thin slices and unknown thickness: still no false-lesion rate', async () => {
    useViewerStore.setState({ currentSeries: series(ORIG, { acquisition_geometry: dicomNative(1) }) });
    const { unmount } = renderCard({ sourceFileId: ORIG, studyInstances: INSTANCES });
    await card();
    expect(screen.getByTestId('stc-false-lesion').textContent).toMatch(/not shown/);
    expect(screen.getByTestId('stc-false-lesion').textContent).not.toMatch(/%/);
    unmount();
    useViewerStore.setState({ currentSeries: series(ORIG, {}) });
    renderCard({ sourceFileId: ORIG, studyInstances: INSTANCES });
    await card();
    expect(screen.getByTestId('stc-false-lesion').textContent).toMatch(/not shown/);
    expect(screen.getByTestId('stc-false-lesion').textContent).not.toMatch(/%/);
  });

  it('rc056 no word on the card pairs "false" with a percentage', async () => {
    useViewerStore.setState({ currentSeries: series(ORIG, { acquisition_geometry: dicomNative(7.2) }) });
    renderCard({ sourceFileId: ORIG, studyInstances: INSTANCES });
    const text = (await card()).textContent ?? '';
    expect(text).not.toMatch(/false[^.]*\d+\s*%/i);
  });
});

describe('RC-057 — detection note from the versioned evidence', () => {
  it('rc057 thick native slices: no size found 8 in 10, half from 50 mm³, evidence and guidance', async () => {
    useViewerStore.setState({ currentSeries: series(ORIG, { acquisition_geometry: dicomNative(5) }) });
    renderCard({ sourceFileId: ORIG, studyInstances: INSTANCES });
    await card();
    expect(screen.getByTestId('stc-reliable').textContent).toMatch(/no lesion size is found 8 times in 10/);
    expect(screen.getByTestId('stc-half').textContent).toMatch(/50 mm³ or more/);
    // Evidence rows of the 4.5-6.5 mm band, with their size and the post-hoc marker.
    expect(screen.getByTestId('stc-row-B3').textContent).toMatch(/76 scans, 76 patients, 2 site/);
    expect(screen.getByTestId('stc-row-B3').textContent).toContain('13 %');
    expect(screen.getByTestId('stc-row-MSL_45').textContent).toMatch(/after the results were seen/);
    expect(screen.getByTestId('stc-guidance').textContent).toMatch(/does not mean that there are no lesions/);
    expect(screen.getByTestId('stc-recommend-3d').textContent).toMatch(/3D FLAIR/);
    expect(screen.getByTestId('stc-provenance').textContent).toMatch(/v1\.0\.0.*PR #54 cabb99d/);
    expect(screen.getByTestId('stc-card').textContent).toMatch(/not validated for this site/);
  });

  it('rc057 a lower bound reads "at least" and uses every thicker band', async () => {
    useViewerStore.setState({ currentSeries: series(ORIG, { acquisition_geometry: { state: 'at_least', effective_mm: 3, source: 'nifti_grid' } }) });
    renderCard({ sourceFileId: ORIG, studyInstances: INSTANCES });
    await card();
    expect(screen.getByTestId('stc-thickness').dataset.state).toBe('at_least');
    expect(screen.getByTestId('stc-thickness').textContent).toMatch(/at least 3 mm/);
    expect(screen.getByTestId('stc-band').textContent).toBe('2.5-3.5 mm or thicker');
    expect(screen.getByTestId('stc-reliable').textContent).toMatch(/no lesion size/);
    expect(screen.getByTestId('stc-row-B4')).toBeTruthy();
    expect(screen.getByTestId('stc-recommend-3d')).toBeTruthy();
  });

  it('rc057 natively thin: from 50 mm³ (about 4.6 mm), no 3D recommendation, empty-list warning kept', async () => {
    useViewerStore.setState({ currentSeries: series(ORIG, { acquisition_geometry: dicomNative(1) }) });
    renderCard({ sourceFileId: ORIG, studyInstances: INSTANCES });
    await card();
    expect(screen.getByTestId('stc-reliable').textContent).toMatch(/50 mm³ or more \(about 4.6 mm across\)/);
    expect(screen.getByTestId('stc-row-B1_grid').textContent).toMatch(/only 10 of 125 natively thin/);
    expect(screen.queryByTestId('stc-recommend-3d')).toBeNull();
    expect(screen.getByTestId('stc-guidance').textContent).toMatch(/does not mean that there are no lesions/);
  });

  it('rc057 not determinable: the reason, the conservative guidance, and no figures', async () => {
    useViewerStore.setState({ currentSeries: series(ORIG, { acquisition_geometry: { state: 'not_determinable', reason: 'fine_grid_no_acquisition_metadata' } }) });
    renderCard({ sourceFileId: ORIG, studyInstances: INSTANCES });
    await card();
    expect(screen.getByTestId('stc-thickness').textContent).toMatch(/Not determinable/);
    expect(screen.getByTestId('stc-reasons').textContent).toMatch(/may have been resampled/);
    expect(screen.getByTestId('stc-guidance').textContent).toMatch(/as if the scan had thick slices/);
    expect(screen.getByTestId('stc-recommend-3d')).toBeTruthy();
    expect(screen.queryByTestId('stc-table')).toBeNull();
    expect(screen.queryByTestId('stc-reliable')).toBeNull();
  });

  it('rc057 Spanish wording when the interface is in Spanish', async () => {
    lang.value = 'es';
    useViewerStore.setState({ currentSeries: series(ORIG, { acquisition_geometry: dicomNative(7.2) }) });
    renderCard({ sourceFileId: ORIG, studyInstances: INSTANCES });
    await card();
    expect(screen.getByTestId('stc-thickness').textContent).toContain('7,2 mm');
    expect(screen.getByTestId('stc-reliable').textContent).toMatch(/ningún tamaño de lesión/);
    expect(screen.getByTestId('stc-guidance').textContent).toMatch(/no significa que no haya lesiones/);
    expect(screen.getByTestId('stc-false-lesion').textContent).toMatch(/no se muestra/);
  });
});
