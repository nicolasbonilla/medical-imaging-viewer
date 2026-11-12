/**
 * F1 / F2 (fifth review of PR #81; RC-122, RC-123, RC-127). DRAFT, PENDING owner approval.
 * F1: the physician's per-visit FLAIR attestation is kept for its pair — the refresh after a radiologist decision sends
 *     it again — and dropped when the pair changes.
 * F2: the SEL search sends the pair's attestation, and a gate result in the SEL answer is shown with QualityGatePanel in
 *     the reader's language, never as the backend's English reason.
 * Drives the real panel (pickers, Compare, the result panel's attestation and decision buttons) with mocked API calls.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const compareLongitudinal = vi.fn();
const reviewLongitudinalCandidates = vi.fn();
const detectSELs = vi.fn();
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    listSegmentationsByFileIds: vi.fn(async (fileIds: string[]) =>
      fileIds[0] === 'file-ser-st1'
        ? [{ segmentation_id: 'seg1', metadata: { description: 'Lesions visit 1' } },
          { segmentation_id: 'seg1b', metadata: { description: 'Lesions visit 1, second reader' } }]
        : [{ segmentation_id: 'seg2', metadata: { description: 'Lesions visit 2' } }]),
    loadZoneMapMask: vi.fn(async () => ({ mask: new Uint8Array(8), depth: 2, height: 2, width: 2 })),
    compareLongitudinal: (...a: unknown[]) => compareLongitudinal(...a),
    reviewLongitudinalCandidates: (...a: unknown[]) => reviewLongitudinalCandidates(...a),
    detectSELs: (...a: unknown[]) => detectSELs(...a),
  },
}));
vi.mock('@/api/study', () => ({
  studyAPI: {
    listSeries: vi.fn(async (studyId: string) => [{ id: `ser-${studyId}` }]),
    listInstances: vi.fn(async (seriesId: string) => [{ gcs_object_name: `file-${seriesId}` }]),
  },
}));

import i18n from '@/i18n/config';
import { LongitudinalCompare } from './LongitudinalCompare';
import type { GateResult } from '@/services/qualityGate/gate';

const STUDIES = [
  { id: 'st1', study_date: '2024-01-10', study_description: 'Brain MRI', modality: 'MR' },
  { id: 'st2', study_date: '2025-01-12', study_description: 'Brain MRI', modality: 'MR' },
] as any[];
const BINDING = { tp1_mask_sha256: 'a'.repeat(64), tp2_mask_sha256: 'b'.repeat(64) };
const ACQ_SAME = { status: 'same', required_fields: [], fields_compared: [], differing: [], missing: [] };
const ATTESTED = { tp1: true, tp2: false };
const COMPARE = /^(compare visits|comparar visitas|untersuchungen vergleichen)$/i;

const gate = (allowed: boolean, code: string | null, visit: 'tp1' | 'tp2' | null = 'tp1'): GateResult => ({
  gate_version: 'quality-gate/1', policy_version: 'p', mode: 'comparison',
  decision: allowed ? (code ? 'proceed_with_warnings' : 'proceed') : 'abstain', ai_may_run: allowed,
  ai_output_allowed: allowed, codes: code ? [code] : [],
  checks: code ? [{ check: code.split('_')[0] as never, visit, status: allowed ? 'warn' : 'abstain', code, params: {} }] : [],
  // G27: the server names the attestable visits
  attestable_visits: !allowed && visit && (code === 'sequence_missing' || code === 'sequence_unknown') ? [visit] : [],
});
const STOPPED = {
  changes: [], abstained: true, total_lesions_tp1: null, total_lesions_tp2: null, burden_tp1_mm3: null, burden_tp2_mm3: null,
  burden_tp1_ml: null, burden_tp2_ml: null, burden_delta_mm3: null, burden_delta_percent: null, status_counts: null,
  change_candidates: null, registration_verified: false, adjudication_required: true,
  caveat: 'Quality gate: no automatic comparison for this pair.', quality_gate: gate(false, 'sequence_missing'),
};
const ALLOWED = {
  changes: [{ centroid_z: 7, centroid_y: 16, centroid_x: 16, volume_tp1_mm3: 0, volume_tp2_mm3: 27, volume_tp1_ml: 0,
    volume_tp2_ml: 0.027, change_mm3: 27, change_percent: 100, iou: 0, region_id: null, region_name: null, status: 'new',
    clinically_significant: true, subtraction_confirmed: false, subtraction_signal: 0.1, candidate_key: 'c_00000000000000a1' }],
  total_lesions_tp1: 1, total_lesions_tp2: 2, burden_tp1_mm3: 20, burden_tp2_mm3: 47, burden_tp1_ml: 0.02, burden_tp2_ml: 0.047,
  burden_delta_mm3: 27, burden_delta_percent: 135, status_counts: { new: 1, resolved: 0, enlarged: 0, shrunk: 0, stable: 0 },
  new_lesion_min_diameter_mm: 3, change_candidates: { new: 1, enlarging: 0, total: 1, confirmed: 0, rejected: 0, awaiting_review: 1 },
  registration_verified: false, adjudication_required: true, spacing_resolved: true, caveat: 'Unconfirmed candidates.',
  subtraction_available: false, abstained: false, acquisition_check: ACQ_SAME, false_candidate_evidence: null,
  review_binding: BINDING, quality_gate: gate(true, 'sequence_confirmed_by_physician'),
};

async function pick(seg1 = 'seg1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><LongitudinalCompare studies={STUDIES} /></QueryClientProvider>);
  fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'st1' } });
  await waitFor(() => expect(screen.getAllByRole('combobox')).toHaveLength(3));
  fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: seg1 } });
  fireEvent.change(screen.getAllByRole('combobox')[2], { target: { value: 'st2' } });
  await waitFor(() => expect(screen.getAllByRole('combobox')).toHaveLength(4));
  fireEvent.change(screen.getAllByRole('combobox')[3], { target: { value: 'seg2' } });
}

/** Compare (stopped by the gate), tick visit 1, compare again with the attestation (allowed). */
async function compareThenAttest() {
  compareLongitudinal.mockResolvedValueOnce(STOPPED).mockResolvedValue(ALLOWED);
  await pick();
  fireEvent.click(screen.getByRole('button', { name: COMPARE }));
  await waitFor(() => expect(screen.getByTestId('quality-gate-attest-tp1')).toBeInTheDocument());
  fireEvent.click(screen.getByTestId('quality-gate-attest-tp1').querySelector('input') as HTMLInputElement);
  fireEvent.click(screen.getByTestId('quality-gate-attest-again'));
  await waitFor(() => expect(compareLongitudinal).toHaveBeenCalledTimes(2));
  expect(compareLongitudinal.mock.calls[1][2]).toEqual(ATTESTED);
  await waitFor(() => expect(screen.getByTestId('longitudinal-candidates')).toBeInTheDocument());
}

beforeEach(async () => {
  compareLongitudinal.mockReset();
  reviewLongitudinalCandidates.mockReset();
  detectSELs.mockReset();
  await act(async () => { await i18n.changeLanguage('en'); });
});
afterEach(cleanup);

describe('F1: the attestation is kept for its pair', () => {
  it('rc122 the refresh after a radiologist decision sends the attestation again', async () => {
    reviewLongitudinalCandidates.mockResolvedValue({ success: true, recorded: 1, review_binding: BINDING });
    await compareThenAttest();
    const toggle = screen.queryByRole('button', { name: /change table|candidat/i });
    if (toggle && !screen.queryByRole('table')) fireEvent.click(toggle);
    fireEvent.click(screen.getAllByRole('button', { name: /confirm/i })[0]);
    await waitFor(() => expect(reviewLongitudinalCandidates).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(compareLongitudinal).toHaveBeenCalledTimes(3));
    expect(compareLongitudinal.mock.calls[2][2]).toEqual(ATTESTED);
  });

  it('rc122 the Compare button keeps it for the same pair, and it is dropped when the pair changes', async () => {
    await compareThenAttest();
    fireEvent.click(screen.getByRole('button', { name: COMPARE }));
    await waitFor(() => expect(compareLongitudinal).toHaveBeenCalledTimes(3));
    expect(compareLongitudinal.mock.calls[2][2]).toEqual(ATTESTED);
    fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: 'seg1b' } });
    fireEvent.click(screen.getByRole('button', { name: COMPARE }));
    await waitFor(() => expect(compareLongitudinal).toHaveBeenCalledTimes(4));
    expect(compareLongitudinal.mock.calls[3][2]).toBeUndefined();
  });
});

describe('F2: the SEL search and the gate', () => {
  it('rc123 the SEL search sends the pair\'s attestation', async () => {
    detectSELs.mockResolvedValue({ ok: true, reason: '', sels: [], n_existing: 1, n_sel: 0, background_expanding_fraction: 0,
      quality_gate: gate(true, 'sequence_confirmed_by_physician') });
    await compareThenAttest();
    fireEvent.click(screen.getByRole('button', { name: /SEL/ }));
    await waitFor(() => expect(detectSELs).toHaveBeenCalledTimes(1));
    expect(detectSELs.mock.calls[0][2]).toEqual(ATTESTED);
    await waitFor(() => expect(screen.getByTestId('sel-quality-gate')).toBeInTheDocument());
  });

  it.each(['en', 'es', 'de'])('rc127 a gate stop in the SEL answer is shown by the panel in %s, never the English reason', async (lng) => {
    await act(async () => { await i18n.changeLanguage(lng); });
    const reason = 'Quality gate: the platform switched the gate off. ENGLISH BACKEND REASON';
    detectSELs.mockResolvedValue({ ok: false, abstained: true, reason, sels: [], n_existing: 0, n_sel: 0,
      quality_gate: gate(false, 'gate_switched_off', null) });
    compareLongitudinal.mockResolvedValue(ALLOWED);
    await pick();
    fireEvent.click(screen.getByRole('button', { name: COMPARE }));
    await waitFor(() => expect(compareLongitudinal).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole('button', { name: /SEL/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /SEL/ }));
    const panel = await screen.findByTestId('sel-quality-gate');
    expect(panel).toHaveAttribute('data-decision', 'abstain');
    expect(screen.getByTestId('sel-quality-gate-check')).toHaveAttribute('data-code', 'gate_switched_off');
    expect(document.body.textContent).not.toContain('ENGLISH BACKEND REASON');
    expect(panel.textContent).toContain(i18n.t('qualityGate.codes.gate_switched_off.message'));
  });
});

describe('U1 (sixth review): the attestations given for a pair add up', () => {
  it('rc122 tp1 then tp2: both visits are attested', async () => {
    const stopTp1 = { ...STOPPED, quality_gate: { ...gate(false, 'sequence_missing', 'tp1'), attestable_visits: ['tp1'] } };
    const stopTp2 = { ...STOPPED, quality_gate: { ...gate(false, 'sequence_unknown', 'tp2'), attestable_visits: ['tp2'] } };
    compareLongitudinal.mockResolvedValueOnce(stopTp1).mockResolvedValueOnce(stopTp2).mockResolvedValue(ALLOWED);
    await pick();
    fireEvent.click(screen.getByRole('button', { name: COMPARE }));
    await waitFor(() => expect(screen.getByTestId('quality-gate-attest-tp1')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('quality-gate-attest-tp1').querySelector('input') as HTMLInputElement);
    fireEvent.click(screen.getByTestId('quality-gate-attest-again'));
    await waitFor(() => expect(compareLongitudinal).toHaveBeenCalledTimes(2));
    expect(compareLongitudinal.mock.calls[1][2]).toEqual({ tp1: true, tp2: false });
    await waitFor(() => expect(screen.getByTestId('quality-gate-attest-tp2')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('quality-gate-attest-tp2').querySelector('input') as HTMLInputElement);
    fireEvent.click(screen.getByTestId('quality-gate-attest-again'));
    await waitFor(() => expect(compareLongitudinal).toHaveBeenCalledTimes(3));
    expect(compareLongitudinal.mock.calls[2][2]).toEqual({ tp1: true, tp2: true });
  });
});
