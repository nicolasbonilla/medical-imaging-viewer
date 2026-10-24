/**
 * PRB-003 — findings of the independent review of PR #68 at 4c601f2, on the viewer side (written BEFORE the
 * corrections; they fail on 4c601f2).
 *
 *  - blocker 1: the confirm button was offered before the regions were classified (a binary mask confirmed
 *    gave a confirmed NOT MET); now only after the classification, and the card says what is missing;
 *  - finding 3: regions of an unconfirmed segmentation were shown without saying they are not a DIS result;
 *  - finding 7: the button was offered on any expanded segmentation, although the SHA-256 sent is that of the
 *    OPEN mask;
 *  - finding 8: a late reply of an older DIS request could overwrite a newer one;
 *  - finding 9: the healthy-brain notice belongs to lesion-detection tools (FLAMeS card, tool result card);
 *  - finding 2 (c): the report request names its segmentation;
 *  - finding 10: the lesion panel sits inside an error boundary.
 */
import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import fs from 'node:fs';
import path from 'node:path';

const getDISAssessment = vi.fn();
const analyzeLesions = vi.fn();
const confirmSegmentationReview = vi.fn();
const getSegmentation = vi.fn();
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    getDISAssessment: (...a: unknown[]) => getDISAssessment(...a),
    analyzeLesions: (...a: unknown[]) => analyzeLesions(...a),
    confirmSegmentationReview: (...a: unknown[]) => confirmSegmentationReview(...a),
    getSegmentation: (...a: unknown[]) => getSegmentation(...a),
    classifyRegions: vi.fn(),
    annotateLesions: vi.fn(),
    confirmAiReview: vi.fn(),
  },
}));
const generateReport = vi.fn();
vi.mock('@/api/aiReport', () => ({
  aiReportAPI: {
    generateReport: (...a: unknown[]) => generateReport(...a),
    listTemplates: vi.fn(async () => []),
  },
}));
const flamesState: Record<string, unknown> = {};
vi.mock('@/hooks/useBrowserFlames', () => ({ useBrowserFlames: () => flamesState }));
vi.mock('sonner', () => ({ toast: { loading: vi.fn(), success: vi.fn(), error: vi.fn() } }));

import { LesionDashboard } from './LesionDashboard';
import { AiDraftBanner } from './AiDraftBanner';
import { AIReportPanel } from './AIReportPanel';
import { BrowserFlamesCard } from './BrowserFlamesCard';
import { TaskProgress } from './ClinicalToolsPanel';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import { useViewerStore } from '@/store/useViewerStore';
import { FLAMES_FOLD0_MODEL } from '@/services/flames/plan';
import type { AIProvenance } from '@/types';

const DIGEST = 'ab'.repeat(32);
const METLIKE = /Criterion Met|Not Met/;
const NOTICE = /Automatic lesion marking also marks spots in most healthy brains/;

const ANALYSIS = {
  segmentation_id: 'seg-1',
  lesions: [
    { id: 1, label_id: 1, region: 'Periventricular', voxel_count: 12, volume_mm3: 36, volume_ml: 0.036,
      size_category: 'small', centroid: { z: 3, y: 3, x: 3 }, bounding_box: {} },
  ],
  total_count: 1,
  total_burden_mm3: 36,
  total_burden_ml: 0.036,
  regions: { Periventricular: { lesion_count: 1, total_volume_mm3: 36, total_volume_ml: 0.036 } },
  size_distribution: { small: 1, medium: 0, large: 0 },
  unique_labels: [1],
};

const notEvaluated = (reason: string, source = 'origin_not_recorded') => ({
  segmentation_id: 'seg-1',
  evaluation_status: 'not_evaluated',
  not_evaluated_reason: reason,
  message: 'Not evaluated: requires clinician review of the segmentation.',
  dis_criteria_version: 'McDonald 2024',
  segmentation_review: { status: 'unconfirmed', source, reviewed_by: null, reviewed_at: null,
                         reviewed_mask_sha256: null, current_mask_sha256: DIGEST },
  regions: { classified: reason !== 'regions_not_classified', label_scheme: 'magnims' },
});

const EVALUATED = {
  segmentation_id: 'seg-1', evaluation_status: 'evaluated', dis_met_brain: true, dis_met: true,
  dis_criteria_version: 'McDonald 2024', brain_regions_with_lesions: 2, brain_regions_evaluated: 3,
  total_dis_regions: 5, total_topographies_involved: 2, dis_met_full: true, dit_waiver_supported: false,
  supportive_specificity_markers: { central_vein_sign: null, paramagnetic_rim_lesion: null, csf_specific: null },
  specificity_marker_present: false, external_evidence_provided: false, decision_support_note: '', note: '',
  region_details: { Periventricular: { label_id: 1, present: true, voxel_count: 12, qualifying_lesion_count: 1 } },
  dwm_lesion_count: 0, dwm_voxels: 0, has_active_lesions: false, has_black_holes: false, active_voxels: 0,
  black_hole_voxels: 0,
  segmentation_review: { status: 'confirmed', source: 'origin_not_recorded', reviewed_by: 'dr_rev',
                         reviewed_at: 'x', reviewed_mask_sha256: DIGEST, current_mask_sha256: DIGEST },
  regions: { classified: true, label_scheme: 'magnims' },
};

function seed(openId = 'seg-1', analysisData: Record<string, unknown> | null = null) {
  useSegmentationStore.setState({
    currentSegmentation: {
      segmentation_id: openId, file_id: 'f.nii.gz', total_slices: 10,
      metadata: { file_id: 'f.nii.gz', created_at: 'T0', modified_at: 'T1', labels: [], analysis_data: analysisData },
    } as any,
    maskDigestCallback: vi.fn().mockResolvedValue(DIGEST),
    hasUnsavedMaskChanges: false,
  });
}

async function analyze() {
  fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
  return screen.findByTestId('dis-not-evaluated');
}

beforeEach(() => {
  for (const f of [getDISAssessment, analyzeLesions, confirmSegmentationReview, getSegmentation, generateReport]) f.mockReset();
  analyzeLesions.mockResolvedValue(ANALYSIS);
  getSegmentation.mockResolvedValue({ segmentation_id: 'seg-1', metadata: {} });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('blocker 1 / findings 7-8: the DIS card', () => {
  it('rc071 review1 regions not classified: the card asks for the classification and offers no confirmation', async () => {
    seed();
    getDISAssessment.mockResolvedValue(notEvaluated('regions_not_classified'));
    render(<LesionDashboard segmentationId="seg-1" />);
    const card = await analyze();
    expect(card).toHaveTextContent(/Run the MAGNIMS region classification/);
    expect(screen.queryByRole('button', { name: /confirm this segmentation/ })).not.toBeInTheDocument();
  });

  it('rc071 review1 an AI draft without its own review: the card says so and offers no confirmation', async () => {
    seed();
    getDISAssessment.mockResolvedValue(notEvaluated('ai_review_missing', 'ai_draft'));
    render(<LesionDashboard segmentationId="seg-1" />);
    const card = await analyze();
    expect(card).toHaveTextContent(/confirm its own review/);
    expect(screen.queryByRole('button', { name: /confirm this segmentation/ })).not.toBeInTheDocument();
  });

  it('rc071 review1 the confirmation is offered only on the open segmentation (its mask is the one hashed)', async () => {
    seed('seg-OTHER');
    getDISAssessment.mockResolvedValue(notEvaluated('segmentation_not_confirmed'));
    render(<LesionDashboard segmentationId="seg-1" />);
    const card = await analyze();
    expect(screen.queryByRole('button', { name: /confirm this segmentation/ })).not.toBeInTheDocument();
    expect(card).toHaveTextContent(/Open this segmentation to confirm it/);
    expect(confirmSegmentationReview).not.toHaveBeenCalled();
  });

  it('rc071 review1 the confirmation is offered after the classification, on the open segmentation', async () => {
    seed('seg-1');
    getDISAssessment.mockResolvedValue(notEvaluated('segmentation_not_confirmed'));
    render(<LesionDashboard segmentationId="seg-1" />);
    await analyze();
    expect(screen.getByRole('button', { name: /confirm this segmentation/ })).toBeInTheDocument();
  });

  it('rc070 review1 a late reply of an older request never overwrites a newer one', async () => {
    seed('seg-1', { lesion_analysis: ANALYSIS });
    let releaseOld: (v: unknown) => void = () => undefined;
    getDISAssessment
      .mockImplementationOnce(() => new Promise((resolve) => { releaseOld = resolve; }))   // on open: slow
      .mockResolvedValue(notEvaluated('segmentation_not_confirmed'));                        // after Analyze
    render(<LesionDashboard segmentationId="seg-1" />);
    await waitFor(() => expect(getDISAssessment).toHaveBeenCalledTimes(1));
    await analyze();
    await act(async () => { releaseOld(EVALUATED); });
    expect(screen.getByTestId('dis-not-evaluated')).toBeInTheDocument();
    expect(screen.queryByText(METLIKE)).not.toBeInTheDocument();
  });
});

describe('finding 3: regions of an unconfirmed segmentation', () => {
  it('rc070 review1 the lesion table and region bars say the regions are not confirmed and not a DIS assessment', async () => {
    seed();
    getDISAssessment.mockResolvedValue(notEvaluated('segmentation_not_confirmed'));
    render(<LesionDashboard segmentationId="seg-1" />);
    await analyze();
    expect(screen.getByTestId('regions-not-confirmed')).toHaveTextContent(/not a DIS assessment/);
  });

  it('rc070 review1 a confirmed, evaluated segmentation carries no such caveat', async () => {
    seed();
    getDISAssessment.mockResolvedValue(EVALUATED);
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    expect(await screen.findByText(/Criterion Met/)).toBeInTheDocument();
    expect(screen.queryByTestId('regions-not-confirmed')).not.toBeInTheDocument();
  });
});

describe('finding 9: the healthy-brain notice for lesion-detection tools', () => {
  const PROV: AIProvenance = {
    kind: 'ai_draft', model_name: 'FLAMeS', model_version: 'v2.0', model_sha256: 'a'.repeat(64), fold: 0,
    source_checkpoint_sha256: 'b'.repeat(64), pipeline_version: 'p', runtime: 'r', generated_at: 'g',
    lesion_count: 2, annotated_voxels: 24, review_status: 'unreviewed', reviewed_by: null, reviewed_at: null,
    reviewed_mask_sha256: null, sequence_evidence: 'clinician',
  };

  it('rc072 review1 the AI draft banner names automatic LESION marking', () => {
    render(<AiDraftBanner provenance={PROV} segmentationId="seg-1" />);
    expect(screen.getByTestId('automatic-marking-notice')).toHaveTextContent(NOTICE);
  });

  it('rc072 review1 a completed lesion tool shows the notice; a structure parcellation does not', () => {
    const color = () => 'text-green-400';
    const label = () => 'Completed';
    const { rerender } = render(<TaskProgress task={{ task_id: 't', status: 'completed', progress: 1,
      segmentation_id: 'seg-9', validation_source: 'lst-ai-v1.0.3' } as any} getStatusColor={color} getStatusLabel={label} />);
    expect(screen.getByTestId('automatic-marking-notice')).toHaveTextContent(NOTICE);
    rerender(<TaskProgress task={{ task_id: 't', status: 'completed', progress: 1, segmentation_id: 'seg-9',
      validation_source: 'synthseg-v2.0' } as any} getStatusColor={color} getStatusLabel={label} />);
    expect(screen.queryByTestId('automatic-marking-notice')).not.toBeInTheDocument();
  });

  it('rc072 review1 the in-browser FLAMeS result carries the notice', () => {
    const FILE = 'patients/p/studies/s/flair.nii.gz';
    Object.assign(flamesState, {
      status: 'done', fraction: 1, message: '', error: null, startedAt: null, run: vi.fn(), cancel: vi.fn(), reset: vi.fn(),
      result: {
        fileId: FILE, maskApp: new Uint8Array(24), dims: [3, 2, 4], spacing: [1, 1, 1],
        summary: { lesionCount: 2, lesionVoxels: 10, lesionVolumeMl: 0.01, componentVolumesMl: [] },
        provenance: { pipeline: 'p', model: 'FLAMeS fold 0', modelSha256: FLAMES_FOLD0_MODEL.sha256,
          sourceCheckpointSha256: FLAMES_FOLD0_MODEL.sourceCheckpointSha256, backend: 'wasm', threads: 1,
          onnxRuntimeWeb: '1.24.1', mirror: false, windows: 1, networkCalls: 1, resampledShape: [1, 1, 1],
          seconds: 10, generatedAt: 'g', sequenceEvidence: 'clinician' },
      },
    });
    useViewerStore.setState({
      currentSeries: { id: 's', name: 'flair', format: 'nifti', file_id: FILE, total_slices: 4, metadata: { rows: 3, columns: 2 } },
    } as never);
    render(<BrowserFlamesCard flairFileId={FILE} />);
    expect(screen.getByTestId('automatic-marking-notice')).toHaveTextContent(NOTICE);
  });
});

describe('finding 2 (c) and 10', () => {
  it('rc070 review1 the report request names the segmentation its measurements come from', async () => {
    seed('seg-1');
    getDISAssessment.mockResolvedValue(notEvaluated('segmentation_not_confirmed'));
    generateReport.mockResolvedValue({ report_id: 'r', content: 'draft', template_type: 'general', language: 'en',
                                       processing_time_ms: 1 });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><AIReportPanel /></QueryClientProvider>);
    fireEvent.click(screen.getByRole('button', { name: /Generate Report/ }));
    await waitFor(() => expect(generateReport).toHaveBeenCalled());
    expect(generateReport.mock.calls[0][0].segmentation_id).toBe('seg-1');
  });

  it('rc070 review1 the lesion panel is rendered inside an error boundary', () => {
    const src = fs.readFileSync(path.resolve(__dirname, '../ViewerApp.tsx'), 'utf-8');
    expect(src).toMatch(/<ErrorBoundary name="LesionDashboard">\s*<LesionDashboard/);
  });
});
