/**
 * PRB-003 — dissemination in space (DIS) only on a segmentation a clinician has confirmed
 * (RC-070, RC-071, RC-072; REQ-SAFE-038..040; HAZ-008, HAZ-005).
 *
 * Paper A (100 public healthy controls): the device's brain-DIS rule, applied to the raw automatic FLAMeS
 * segmentation, returned "DIS met" in 19 of 100 healthy brains; 85 of 100 got at least one marked spot.
 * The dashboard showed "DIS (Brain MRI): Criterion Met" for any loaded segmentation, including a DIS block
 * stored in the segmentation's metadata, and offered no way to confirm a segmentation without AI provenance.
 *
 * These tests drive the real dashboard and banner with mocked API calls. They were written before the
 * fix and fail on `main` @ 70cc5c7.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
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
vi.mock('sonner', () => ({ toast: { loading: vi.fn(), success: vi.fn(), error: vi.fn() } }));

import { LesionDashboard } from './LesionDashboard';
import { AiDraftBanner } from './AiDraftBanner';
import { useSegmentationStore } from '@/store/useSegmentationStore';
import type { AIProvenance } from '@/types';

const DIGEST = 'ab'.repeat(32);
const NOTICE_EN = /also marks spots in most healthy brains/;
const METLIKE = /Criterion Met|Not Met|Cumplido|erfüllt/;

const ANALYSIS = {
  segmentation_id: 'seg-1',
  lesions: [
    { id: 1, label_id: 1, region: 'Periventricular', voxel_count: 12, volume_mm3: 36, volume_ml: 0.036,
      size_category: 'small', centroid: { z: 3, y: 3, x: 3 }, bounding_box: {} },
    { id: 2, label_id: 2, region: 'Juxtacortical', voxel_count: 12, volume_mm3: 36, volume_ml: 0.036,
      size_category: 'small', centroid: { z: 7, y: 13, x: 13 }, bounding_box: {} },
  ],
  total_count: 2,
  total_burden_mm3: 72,
  total_burden_ml: 0.072,
  regions: {},
  size_distribution: { small: 2, medium: 0, large: 0 },
  unique_labels: [1, 2],
};

const notEvaluated = (source: string, status = 'unconfirmed') => ({
  segmentation_id: 'seg-1',
  evaluation_status: 'not_evaluated',
  not_evaluated_reason: status === 'outdated' ? 'confirmation_outdated' : 'segmentation_not_confirmed',
  message: 'Not evaluated: requires clinician review of the segmentation.',
  dis_criteria_version: 'McDonald 2024 (Montalban et al., Lancet Neurology 2025)',
  segmentation_review: { status, source, reviewed_by: null, reviewed_at: null, reviewed_mask_sha256: null,
                         current_mask_sha256: DIGEST },
  ...(source === 'origin_not_recorded' ? {} : { information_for_safety: 'automatic marking notice' }),
});

const EVALUATED = {
  segmentation_id: 'seg-1',
  evaluation_status: 'evaluated',
  dis_met_brain: true,
  dis_met: true,
  dis_criteria_version: 'McDonald 2024 (Montalban et al., Lancet Neurology 2025)',
  brain_regions_with_lesions: 2,
  brain_regions_evaluated: 3,
  total_dis_regions: 5,
  total_topographies_involved: 2,
  dis_met_full: true,
  dit_waiver_supported: false,
  supportive_specificity_markers: { central_vein_sign: null, paramagnetic_rim_lesion: null, csf_specific: null },
  specificity_marker_present: false,
  external_evidence_provided: false,
  decision_support_note: 'Radiological decision support only — NOT a diagnosis.',
  note: 'Brain MRI supplies up to 3 of the 5 McDonald 2024 topographies.',
  region_details: {
    Periventricular: { label_id: 1, present: true, voxel_count: 12, qualifying_lesion_count: 1 },
    Juxtacortical: { label_id: 2, present: true, voxel_count: 12, qualifying_lesion_count: 1 },
    Infratentorial: { label_id: 3, present: false, voxel_count: 0, qualifying_lesion_count: 0 },
  },
  dwm_lesion_count: 0, dwm_voxels: 0, has_active_lesions: false, has_black_holes: false,
  active_voxels: 0, black_hole_voxels: 0,
  segmentation_review: { status: 'confirmed', source: 'origin_not_recorded', reviewed_by: 'dr_rev',
                         reviewed_at: '2026-10-24T10:00:00Z', reviewed_mask_sha256: DIGEST,
                         current_mask_sha256: DIGEST },
};

const STORED_MET = { ...EVALUATED, evaluation_status: undefined, segmentation_review: undefined };

// Release 2026-10-25 (review of PR #69, B1/M3): the label table of the open mask that the confirm tests confirm.
const DRAWN_LABELS = [
  { id: 0, name: 'Background', color: '#000000', opacity: 0, visible: false },
  { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true },
  { id: 2, name: 'Juxtacortical', color: '#00CC00', opacity: 0.6, visible: true },
];

function seedStore(analysisData: Record<string, unknown> | null, extra: Record<string, unknown> = {}) {
  useSegmentationStore.setState({
    currentSegmentation: {
      segmentation_id: 'seg-1',
      file_id: 'f.nii.gz',
      total_slices: 10,
      metadata: {
        file_id: 'f.nii.gz',
        created_at: 'T0',
        modified_at: 'T1',
        labels: [],
        analysis_data: analysisData,
        ...extra,
      },
    } as any,
    maskDigestCallback: vi.fn().mockResolvedValue(DIGEST),
    // Release 2026-10-25 (review of PR #69, B1/M3): the open mask that is confirmed is drawn — its values 1-2 have
    // visible labels, the overlay is on and the opacity is visible (the confirmation checks this first).
    activeSegmentation: { id: 'seg-1', labels: DRAWN_LABELS } as any,
    labelVisibility: { 0: false, 1: true, 2: true },
    isOverlayVisible: true,
    lesionOpacity: 0.6,
    // Release 2026-10-25 (final check of #69, R1): the standard 2D view on screen draws the open segmentation.
    overlayOnScreen: 'seg-1',
    overlayImageOnScreen: { segmentationId: 'seg-1', imageFileId: 'f.nii.gz', image: { width: 20, height: 20, depth: 10 }, mask: { width: 20, height: 20, depth: 10 } },   // next safety round, PRB-030: over an image on the mask grid
    maskValuesCallback: vi.fn(() => [1, 2]),
    hasUnsavedMaskChanges: false,
  } as never);
}

beforeEach(() => {
  getDISAssessment.mockReset();
  analyzeLesions.mockReset();
  confirmSegmentationReview.mockReset();
  getSegmentation.mockReset();
  getSegmentation.mockResolvedValue({ segmentation_id: 'seg-1', metadata: { analysis_data: null } });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('RC-070 the dashboard shows DIS only for a confirmed segmentation', () => {
  it('rc070 a DIS conclusion stored in the metadata is never shown; the gated route decides', async () => {
    seedStore({ lesion_analysis: ANALYSIS, dis_assessment: STORED_MET, analysis_mask_modified_at: 'T1' });
    getDISAssessment.mockResolvedValue(notEvaluated('ai_draft'));
    render(<LesionDashboard segmentationId="seg-1" />);
    expect(await screen.findByTestId('dis-not-evaluated')).toBeInTheDocument();
    expect(getDISAssessment).toHaveBeenCalledWith('seg-1');
    expect(screen.queryByText(METLIKE)).not.toBeInTheDocument();
  });

  it('rc070 after Analyze an unconfirmed segmentation reads "not evaluated", never met / not met', async () => {
    seedStore(null);
    analyzeLesions.mockResolvedValue(ANALYSIS);
    getDISAssessment.mockResolvedValue(notEvaluated('automatic_tool'));
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    const card = await screen.findByTestId('dis-not-evaluated');
    expect(card).toHaveTextContent(/requires clinician review of the segmentation/);
    expect(screen.queryByText(METLIKE)).not.toBeInTheDocument();
    expect(screen.queryByText(/5 topographies/)).not.toBeInTheDocument();
    expect(screen.queryByText(/dissemination in time may be waived/)).not.toBeInTheDocument();
  });

  it('rc070 a block without the "evaluated" state (an older backend) is never shown as met / not met', async () => {
    seedStore(null);
    analyzeLesions.mockResolvedValue(ANALYSIS);
    getDISAssessment.mockResolvedValue(STORED_MET);
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    expect(await screen.findByTestId('dis-not-evaluated')).toBeInTheDocument();
    expect(screen.queryByText(METLIKE)).not.toBeInTheDocument();
  });

  it('rc070 an evaluated result is withheld while the mask on screen has unsaved changes, and re-read after saving', async () => {
    seedStore(null);
    analyzeLesions.mockResolvedValue(ANALYSIS);
    getDISAssessment.mockResolvedValueOnce(EVALUATED).mockResolvedValue(notEvaluated('origin_not_recorded'));
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    expect(await screen.findByText(/Criterion Met/)).toBeInTheDocument();
    act(() => useSegmentationStore.setState({ hasUnsavedMaskChanges: true }));   // the radiologist edits the mask
    expect(await screen.findByTestId('dis-unsaved-changes')).toBeInTheDocument();
    expect(screen.queryByText(METLIKE)).not.toBeInTheDocument();
    act(() => useSegmentationStore.setState({ hasUnsavedMaskChanges: false }));  // saved: the server voided it
    await waitFor(() => expect(getDISAssessment).toHaveBeenCalledTimes(2));
    expect(await screen.findByTestId('dis-not-evaluated')).toHaveTextContent(/No radiologist has confirmed/);
    expect(screen.queryByText(METLIKE)).not.toBeInTheDocument();
  });

  it('rc070 a confirmed segmentation shows the result and who confirmed it', async () => {
    seedStore(null);
    analyzeLesions.mockResolvedValue(ANALYSIS);
    getDISAssessment.mockResolvedValue(EVALUATED);
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    expect(await screen.findByText(/Criterion Met/)).toBeInTheDocument();
    expect(screen.getByTestId('dis-confirmed-by')).toHaveTextContent('dr_rev');
    expect(screen.queryByTestId('dis-not-evaluated')).not.toBeInTheDocument();
  });
});

describe('RC-071 confirming a segmentation without AI provenance', () => {
  it('rc071 the radiologist confirms the saved mask (its SHA-256 is sent) and DIS is evaluated', async () => {
    seedStore(null);
    analyzeLesions.mockResolvedValue(ANALYSIS);
    getDISAssessment.mockResolvedValueOnce(notEvaluated('origin_not_recorded')).mockResolvedValue(EVALUATED);
    confirmSegmentationReview.mockResolvedValue({ reviewed_by: 'dr_rev', reviewed_at: 'x', reviewed_mask_sha256: DIGEST });
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    fireEvent.click(await screen.findByRole('button', { name: /confirm this segmentation/ }));
    // final check of #69 (R2): the call also carries the label table the mask was drawn with
    await waitFor(() => expect(confirmSegmentationReview).toHaveBeenCalledWith('seg-1', DIGEST, null, DRAWN_LABELS,
      { geometricRegionsReviewedSha256: null, displayedImageFileId: 'f.nii.gz' }));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringMatching(/any later change of the mask cancels/));
    expect(await screen.findByText(/Criterion Met/)).toBeInTheDocument();
  });

  it('rc071 with unsaved changes there is no confirm button, only "save first"', async () => {
    seedStore(null);
    useSegmentationStore.setState({ hasUnsavedMaskChanges: true });
    analyzeLesions.mockResolvedValue(ANALYSIS);
    getDISAssessment.mockResolvedValue(notEvaluated('origin_not_recorded'));
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    expect(await screen.findByTestId('dis-save-first')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /confirm this segmentation/ })).not.toBeInTheDocument();
  });

  it('rc071 an AI draft without its own review is not confirmed here: the card points to the AI draft review', async () => {
    // Changed after the review of PR #68: an AI draft is DIS-confirmed here once its own review (RC-047) is
    // confirmed; until then the server says `ai_review_missing` and no confirmation is offered.
    seedStore(null);
    analyzeLesions.mockResolvedValue(ANALYSIS);
    getDISAssessment.mockResolvedValue({ ...notEvaluated('ai_draft'), not_evaluated_reason: 'ai_review_missing' });
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    const card = await screen.findByTestId('dis-not-evaluated');
    expect(card).toHaveTextContent(/AI draft/);
    expect(screen.queryByRole('button', { name: /confirm this segmentation/ })).not.toBeInTheDocument();
  });
});

describe('RC-072 information for safety on automatic marking', () => {
  const PROV: AIProvenance = {
    kind: 'ai_draft', model_name: 'FLAMeS', model_version: 'v2.0', model_sha256: 'a'.repeat(64), fold: 0,
    source_checkpoint_sha256: 'b'.repeat(64), pipeline_version: 'p', runtime: 'r', generated_at: 'g',
    lesion_count: 2, annotated_voxels: 24, review_status: 'unreviewed', reviewed_by: null, reviewed_at: null,
    reviewed_mask_sha256: null, sequence_evidence: 'clinician',
  };

  it('rc072 the AI draft banner carries the notice', () => {
    useSegmentationStore.setState({ maskDigestCallback: vi.fn().mockResolvedValue(DIGEST) });
    render(<AiDraftBanner provenance={PROV} segmentationId="seg-1" />);
    expect(screen.getByTestId('automatic-marking-notice')).toHaveTextContent(NOTICE_EN);
    expect(screen.getByTestId('automatic-marking-notice')).toHaveTextContent(/not evidence of multiple sclerosis/);
  });

  it('rc072 the "not evaluated" card of an automatic segmentation carries the notice', async () => {
    seedStore(null);
    analyzeLesions.mockResolvedValue(ANALYSIS);
    getDISAssessment.mockResolvedValue(notEvaluated('automatic_tool'));
    render(<LesionDashboard segmentationId="seg-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    const card = await screen.findByTestId('dis-not-evaluated');
    expect(card).toHaveTextContent(NOTICE_EN);
  });

  it('rc072 every new text exists in en, es and de, translated', () => {
    const dir = path.resolve(__dirname, '../i18n/locales');
    const read = (l: string) => JSON.parse(fs.readFileSync(path.join(dir, `${l}.json`), 'utf-8'));
    const [en, es, de] = ['en', 'es', 'de'].map(read);
    const keys = Object.keys(en.disReview ?? {});
    expect(keys.length).toBeGreaterThanOrEqual(8);
    for (const k of keys) {
      expect(typeof es.disReview?.[k]).toBe('string');
      expect(typeof de.disReview?.[k]).toBe('string');
      expect(es.disReview[k]).not.toBe(en.disReview[k]);
      expect(de.disReview[k]).not.toBe(en.disReview[k]);
    }
    expect(en.disReview.automaticMarkingNotice).toMatch(NOTICE_EN);
    expect(es.disReview.automaticMarkingNotice).toMatch(/cerebros sanos/);
    expect(de.disReview.automaticMarkingNotice).toMatch(/gesunden Gehirnen/);
  });

  // The segmentation panel's notice (server-tool LESION output only) is tested through the real panel in
  // SegmentationPanel.prb003.test.tsx — it replaces a source-text check (review of PR #68).
});
