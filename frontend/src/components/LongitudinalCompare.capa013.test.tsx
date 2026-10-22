/**
 * CAPA-013 — longitudinal comparison view (RC-060, RC-061, RC-062; REQ-SAFE-037; HAZ-007).
 *
 * Measured (paper C pilot, PR #60): against expert change masks the device's new/enlarging rule
 * proposed >= 1 false candidate in 20/20 patients, about 9 per patient (about 5 after its own
 * subtraction check). The view showed those counts under "Active-disease CANDIDATE", a
 * "NEDA-3 ... activity CANDIDATE" badge and "confirmed brighter at follow-up", in English in every
 * language, and recorded no reader decision.
 *
 * These tests drive the real panel (study and segmentation pickers, Compare button) with mocked
 * API calls. They were written before the fix and fail on the code of PR #62.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import fs from 'node:fs';
import path from 'node:path';

const compareLongitudinal = vi.fn();
const reviewLongitudinalCandidates = vi.fn();
vi.mock('@/api/segmentation', () => ({
  segmentationAPI: {
    listSegmentationsByFileIds: vi.fn(async (fileIds: string[]) =>
      fileIds[0] === 'file-ser-st1'
        ? [{ segmentation_id: 'seg1', metadata: { description: 'Lesions visit 1' } }]
        : [{ segmentation_id: 'seg2', metadata: { description: 'Lesions visit 2' } }]),
    loadZoneMapMask: vi.fn(async () => ({ mask: new Uint8Array(8), depth: 2, height: 2, width: 2 })),
    compareLongitudinal: (...a: unknown[]) => compareLongitudinal(...a),
    reviewLongitudinalCandidates: (...a: unknown[]) => reviewLongitudinalCandidates(...a),
    detectSELs: vi.fn(),
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

const ACTIVITY = /activ|aktiv/i;
const STUDIES = [
  { id: 'st1', study_date: '2024-01-10', study_description: 'Brain MRI', modality: 'MR' },
  { id: 'st2', study_date: '2025-01-12', study_description: 'Brain MRI', modality: 'MR' },
] as any[];
const BINDING = { tp1_mask_sha256: 'a'.repeat(64), tp2_mask_sha256: 'b'.repeat(64) };
const EVIDENCE = {
  asset: 'LONG-FCE',
  version: '1.0.0',
  measured_on: '2026-10-22',
  dataset: 'open_ms longitudinal (public), expert-marked change masks',
  segmenter: 'FLAMeS 5-fold ensemble',
  patients: 20,
  stable_patients: 0,
  patients_with_false_candidate: 20,
  false_candidates_per_patient: 8.9,
  false_candidates_per_patient_ci95: [5.8, 12.6],
  after_subtraction_per_patient: 5.4,
  after_subtraction_per_patient_ci95: [3.45, 7.7],
  source: 'Paper C pilot, arm A4 (PR #60)',
};
const ACQ_SAME = {
  status: 'same',
  required_fields: ['manufacturer', 'manufacturer_model_name', 'magnetic_field_strength_t', 'mr_acquisition_type', 'slice_thickness_mm'],
  fields_compared: ['manufacturer', 'manufacturer_model_name', 'magnetic_field_strength_t', 'mr_acquisition_type',
    'slice_thickness_mm', 'voxel_spacing_mm', 'repetition_time_ms', 'echo_time_ms', 'inversion_time_ms', 'spacing_between_slices_mm'],
  differing: [],
  missing: [],
};

function change(over: Record<string, unknown>) {
  return {
    centroid_z: 7, centroid_y: 16, centroid_x: 16, volume_tp1_mm3: 0, volume_tp2_mm3: 27,
    volume_tp1_ml: 0, volume_tp2_ml: 0.027, change_mm3: 27, change_percent: 100, iou: 0,
    region_id: null, region_name: null, ...over,
  };
}

/** A response as the backend of PR #62 sends it PLUS the CAPA-013 fields: the legacy flags are
 *  kept on purpose — the view must not turn them into an activity statement. */
function result(over: Record<string, unknown> = {}) {
  return {
    changes: [
      change({ status: 'new', clinically_significant: true, subtraction_confirmed: true, subtraction_signal: 1.2,
        candidate_key: 'c_00000000000000a1' }),
      change({ status: 'new', clinically_significant: true, subtraction_confirmed: false, subtraction_signal: 0.1,
        centroid_z: 3, candidate_key: 'c_00000000000000a2' }),
      change({ status: 'enlarged', volume_tp1_mm3: 20, volume_tp2_mm3: 30, change_percent: 50, centroid_z: 5,
        candidate_key: 'c_00000000000000a3' }),
      change({ status: 'stable', volume_tp1_mm3: 27, change_percent: 0, centroid_z: 2 }),
    ],
    total_lesions_tp1: 2, total_lesions_tp2: 4,
    burden_tp1_mm3: 47, burden_tp2_mm3: 111, burden_tp1_ml: 0.047, burden_tp2_ml: 0.111,
    burden_delta_mm3: 64, burden_delta_percent: 136.2,
    status_counts: { new: 2, resolved: 0, enlarged: 1, shrunk: 0, stable: 1 },
    new_lesion_min_diameter_mm: 3,
    // legacy flags (PR #62 backend)
    new_clinically_significant_count: 2, enlarging_count: 1, dit_candidate: true, activity_candidate: true,
    change_candidates: { new: 2, enlarging: 1, total: 3, confirmed: 0, rejected: 0, awaiting_review: 3 },
    registration_verified: false, adjudication_required: true, spacing_resolved: true,
    registration_applied: true, registration_advisory_qc: { translation_mm: 1.2, rotation_deg: 0.4 },
    caveat: 'New/enlarging/resolved counts are UNADJUDICATED CANDIDATES. Backend English caveat.',
    subtraction_available: true,
    subtraction_summary: { new_total: 2, new_subtraction_confirmed: 1, min_signal_sd: 0.5 },
    abstained: false, acquisition_check: ACQ_SAME,
    false_candidate_evidence: EVIDENCE,
    review_binding: BINDING,
    ...over,
  };
}

const ABSTAINED = (status: 'differs' | 'not_established') => result({
  abstained: true,
  acquisition_check: {
    ...ACQ_SAME, status,
    differing: status === 'differs' ? [{ field: 'manufacturer', tp1: 'SIEMENS', tp2: 'Philips' }] : [],
    missing: status === 'not_established' ? [{ field: 'magnetic_field_strength_t', timepoints: ['tp2'] }] : [],
  },
  changes: [], status_counts: null, change_candidates: null, burden_delta_mm3: null, burden_delta_percent: null,
  region_stratification: null, subtraction_summary: null, review_binding: null,
  new_clinically_significant_count: undefined, enlarging_count: undefined, dit_candidate: undefined, activity_candidate: undefined,
});

async function renderAndCompare(payload: unknown) {
  compareLongitudinal.mockResolvedValue(payload);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <LongitudinalCompare studies={STUDIES} />
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'st1' } });
  await waitFor(() => expect(screen.getAllByRole('combobox')).toHaveLength(3));
  fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: 'seg1' } });
  fireEvent.change(screen.getAllByRole('combobox')[2], { target: { value: 'st2' } });
  await waitFor(() => expect(screen.getAllByRole('combobox')).toHaveLength(4));
  fireEvent.change(screen.getAllByRole('combobox')[3], { target: { value: 'seg2' } });
  fireEvent.click(screen.getByRole('button', { name: /compare|comparar|vergleichen/i }));
  await waitFor(() => expect(compareLongitudinal).toHaveBeenCalled());
  await waitFor(() => expect(view.container.textContent).toMatch(/\bmL\b/));
  return view;
}

/** English three-word phrases of the view's English texts: none may appear in Spanish or German
 *  (catches a text left partly in English). Placeholders are ignored; proper names are allowed. */
const ALLOWED_SHARED = new Set(['msmask mni152 atlas']);
const LOCALES = path.join(__dirname, '..', 'i18n', 'locales');
const longitudinalTexts = (l: string): [string, string][] => {
  const flat = (o: any, p = ''): [string, string][] =>
    Object.entries(o).flatMap(([k, v]) => (typeof v === 'object' ? flat(v, `${p}${k}.`) : [[`${p}${k}`, String(v)]]));
  return flat(JSON.parse(fs.readFileSync(path.join(LOCALES, `${l}.json`), 'utf-8')).longitudinal);
};
function trigrams(s: string): Set<string> {
  const w = s.replace(/\{\{[^}]+\}\}/g, ' ').split(/[\s,.;:()—–-]+/).filter((x) => /[A-Za-z]{2,}/.test(x));
  const out = new Set<string>();
  for (let i = 0; i + 2 < w.length; i++) out.add(w.slice(i, i + 3).join(' ').toLowerCase());
  return out;
}
function englishPhrasesIn(text: string): string[] {
  const english = new Set(longitudinalTexts('en').flatMap(([, v]) => [...trigrams(v)]));
  return [...trigrams(text)].filter((x) => english.has(x) && !ALLOWED_SHARED.has(x));
}

/** All text a reader can see, including tooltips. */
function visibleText(container: HTMLElement): string {
  const titles = Array.from(container.querySelectorAll('[title]')).map((e) => e.getAttribute('title'));
  return `${container.textContent} ${titles.join(' ')}`;
}

function expandTable() {
  const toggle = screen.queryByRole('button', { name: /change table|tabla de cambios|änderungstabelle|candidat|kandidat/i });
  if (toggle && !screen.queryByRole('table')) fireEvent.click(toggle);
}

beforeEach(async () => {
  compareLongitudinal.mockReset();
  reviewLongitudinalCandidates.mockReset();
  await act(async () => { await i18n.changeLanguage('en'); });
});
afterEach(async () => {
  await act(async () => { await i18n.changeLanguage('en'); });
});

describe('CAPA-013 — unconfirmed candidates are never activity (RC-060)', () => {
  it('rc060 unconfirmed candidates are shown as such, never as activity, DIT or NEDA', async () => {
    const { container } = await renderAndCompare(result());
    expandTable();
    const text = visibleText(container);
    expect(text).not.toMatch(ACTIVITY);
    expect(text).not.toMatch(/NEDA|dissemination|MAGNIMS 2021/i);
    expect(screen.getByTestId('longitudinal-candidates')).toHaveTextContent(/3 unconfirmed change candidates/);
    expect(screen.getByTestId('longitudinal-candidates')).toHaveTextContent(/2 new .*1 enlarging/);
    expect(screen.getByTestId('longitudinal-candidates')).toHaveTextContent(/radiologist/);
    expect(screen.queryByTestId('longitudinal-reader-confirmed')).not.toBeInTheDocument();
  });

  it('rc060 the word activity appears only with a radiologist confirmation, naming who and when', async () => {
    const confirmed = result({
      change_candidates: { new: 2, enlarging: 1, total: 3, confirmed: 1, rejected: 1, awaiting_review: 1 },
      reader_confirmed_activity: {
        rule: 'MAGNIMS-CMSC-NAIMS 2021: >= 1 new or enlarging T2 lesion',
        confirmed_new: 1, confirmed_enlarging: 0, confirmed_by: ['dr_rev'],
        first_confirmed_at: '2026-10-22T09:00:00Z', last_confirmed_at: '2026-10-22T09:00:00Z',
      },
    });
    await renderAndCompare(confirmed);
    const box = screen.getByTestId('longitudinal-reader-confirmed');
    expect(box).toHaveTextContent(/activity/i);
    expect(box).toHaveTextContent(/dr_rev/);
    expect(box).toHaveTextContent(/2026/);
    expect(box).toHaveTextContent(/1 new/);
    // the unconfirmed remainder is still not called activity
    expect(screen.getByTestId('longitudinal-candidates').textContent).not.toMatch(ACTIVITY);
  });

  it('rc060 a radiologist decision is sent bound to the compared masks, then the comparison is refreshed', async () => {
    reviewLongitudinalCandidates.mockResolvedValue({ success: true, recorded: 1, review_binding: BINDING });
    await renderAndCompare(result());
    expandTable();
    fireEvent.click(screen.getAllByRole('button', { name: /confirm/i })[0]);
    await waitFor(() => expect(reviewLongitudinalCandidates).toHaveBeenCalledTimes(1));
    expect(reviewLongitudinalCandidates).toHaveBeenCalledWith({
      tp1: { type: 'segmentation', id: 'seg1' },
      tp2: { type: 'segmentation', id: 'seg2' },
      review_binding: BINDING,
      decisions: [{ candidate_key: 'c_00000000000000a1', decision: 'confirmed' }],
    });
    await waitFor(() => expect(compareLongitudinal).toHaveBeenCalledTimes(2));
  });

  it('rc060 a refused decision is shown and nothing is recorded as confirmed', async () => {
    reviewLongitudinalCandidates.mockRejectedValue({ response: { status: 403, data: { detail: 'Only a radiologist can confirm or reject a change candidate.' } } });
    const { container } = await renderAndCompare(result());
    expandTable();
    fireEvent.click(screen.getAllByRole('button', { name: /reject/i })[0]);
    await waitFor(() => expect(screen.getByTestId('longitudinal-review-error')).toHaveTextContent(/radiologist/));
    expect(compareLongitudinal).toHaveBeenCalledTimes(1);
    expect(visibleText(container)).not.toMatch(ACTIVITY);
  });
});

describe('CAPA-013 — measured false-candidate rate, in the reader language (RC-061)', () => {
  it('rc061 the measured false-candidate rate is shown from the response, with its source and date', async () => {
    await renderAndCompare(result());
    const ev = screen.getByTestId('longitudinal-evidence');
    expect(ev).toHaveTextContent(/8\.9/);
    expect(ev).toHaveTextContent(/20 patients/);
    expect(ev).toHaveTextContent(/5\.4/);
    expect(ev).toHaveTextContent(/Paper C pilot, arm A4 \(PR #60\)/);
    expect(ev).toHaveTextContent(/2026-10-22/);
    expect(ev).toHaveTextContent(/most candidates may be false/i);
  });

  it('rc061 the figures come from the configuration asset, not from the component', async () => {
    await renderAndCompare(result({ false_candidate_evidence: { ...EVIDENCE, false_candidates_per_patient: 3.3, patients: 31 } }));
    const ev = screen.getByTestId('longitudinal-evidence');
    expect(ev).toHaveTextContent(/3\.3/);
    expect(ev).toHaveTextContent(/31 patients/);
    expect(ev.textContent).not.toMatch(/8\.9/);
  });

  it('rc061 without a measured rate the panel says so and still treats every candidate as unconfirmed', async () => {
    await renderAndCompare(result({ false_candidate_evidence: null }));
    expect(screen.getByTestId('longitudinal-evidence')).toHaveTextContent(/no measured false-candidate rate/i);
  });

  it('rc061 the subtraction is worded as a signal, never as a confirmation', async () => {
    const { container } = await renderAndCompare(result());
    expandTable();
    const text = visibleText(container);
    expect(text).not.toMatch(/confirmed brighter|supports a genuine new lesion|✓sub/i);
    expect(text).toMatch(/brighter at follow-up/i);
    expect(text).toMatch(/not a confirmation|does not confirm/i);
  });

  it('rc061 every text of the view exists in en, es and de', () => {
    const src = ['LongitudinalCompare.tsx', 'LongitudinalResultPanel.tsx']
      .map((f) => path.join(__dirname, f))
      .filter((p) => fs.existsSync(p))
      .map((p) => fs.readFileSync(p, 'utf-8'))
      .join('\n');
    const keys = new Set(Array.from(src.matchAll(/t\(\s*'(longitudinal\.[A-Za-z0-9_.]+)'/g)).map((m) => m[1]));
    // keys built at run time
    for (const s of ['new', 'resolved', 'enlarged', 'shrunk', 'stable']) keys.add(`longitudinal.status.${s}`);
    for (const f of ['manufacturer', 'manufacturer_model_name', 'magnetic_field_strength_t', 'mr_acquisition_type',
      'slice_thickness_mm', 'voxel_spacing_mm', 'repetition_time_ms', 'echo_time_ms', 'inversion_time_ms',
      'spacing_between_slices_mm']) keys.add(`longitudinal.field.${f}`);
    for (const r of ['pv', 'jc', 'it', 'dwm', 'unassigned']) keys.add(`longitudinal.region.${r}`);
    for (const r of ['pv', 'jc', 'it', 'dwm']) keys.add(`longitudinal.regionShort.${r}`);
    expect(keys.size).toBeGreaterThan(40);
    const loc = (l: string) => JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'i18n', 'locales', `${l}.json`), 'utf-8'));
    const get = (o: any, k: string) => k.split('.').reduce((a, p) => (a == null ? a : a[p]), o);
    const [en, es, de] = ['en', 'es', 'de'].map(loc);
    const missing: string[] = [];
    for (const k of keys) for (const [l, d] of [['en', en], ['es', es], ['de', de]] as const) {
      const v = get(d, k);
      if (typeof v !== 'string' || !v.trim()) missing.push(`${l}:${k}`);
    }
    expect(missing).toEqual([]);
    // the safety texts are translated, not copied
    for (const k of ['longitudinal.candidatesSummary', 'longitudinal.evidence', 'longitudinal.candidateCaveat',
      'longitudinal.abstainedDiffers', 'longitudinal.subSummary', 'longitudinal.readerConfirmed']) {
      expect(get(es, k)).not.toBe(get(en, k));
      expect(get(de, k)).not.toBe(get(en, k));
    }
    // ... and not left partly in English
    const partlyEnglish = ['es', 'de'].flatMap((l) => longitudinalTexts(l)
      .map(([k, v]) => [l, k, englishPhrasesIn(v)] as const)
      .filter(([, , hits]) => hits.length > 0)
      .map(([lg, k, hits]) => `${lg}:${k} ${hits.join(' | ')}`));
    expect(partlyEnglish).toEqual([]);
  });

  it.each([
    ['es', /candidatos de cambio sin confirmar/, /pacientes/],
    ['de', /unbestätigte Veränderungskandidaten/, /Patienten/],
  ])('rc061 in %s the safety texts are shown in that language', async (lng, summary, evidence) => {
    await act(async () => { await i18n.changeLanguage(lng as string); });
    const { container } = await renderAndCompare(result());
    expandTable();
    expect(screen.getByTestId('longitudinal-candidates')).toHaveTextContent(summary as RegExp);
    expect(screen.getByTestId('longitudinal-evidence')).toHaveTextContent(evidence as RegExp);
    const text = visibleText(container);
    expect(text).not.toMatch(/unconfirmed|UNADJUDICATED|radiologist must|Backend English caveat|brighter at follow-up|Change Table/);
    expect(englishPhrasesIn(text)).toEqual([]);
    expect(text).not.toMatch(ACTIVITY);
  });
});

describe('CAPA-013 — abstention on a scanner or protocol change (RC-062)', () => {
  it('rc062 a scanner or protocol change shows no counts, the reason and the metadata compared', async () => {
    const { container } = await renderAndCompare(ABSTAINED('differs'));
    const box = screen.getByTestId('longitudinal-abstained');
    expect(box).toHaveTextContent(/no automatic change candidates/i);
    expect(box).toHaveTextContent(/manufacturer.*SIEMENS.*Philips/i);
    expect(box).toHaveTextContent(/field strength/i);
    expect(box).toHaveTextContent(/compare the images visually/i);
    expect(screen.queryByTestId('longitudinal-candidates')).not.toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/136[.,]2/);           // no burden change either
    expect(visibleText(container)).not.toMatch(ACTIVITY);
    expect(screen.getByTestId('longitudinal-legend')).toBeInTheDocument();  // overlay kept for visual review
  });

  it('rc062 when the acquisition cannot be established the comparison abstains and names the missing data', async () => {
    await renderAndCompare(ABSTAINED('not_established'));
    const box = screen.getByTestId('longitudinal-abstained');
    expect(box).toHaveTextContent(/could not be established/i);
    expect(box).toHaveTextContent(/field strength.*visit 2/i);
    expect(screen.queryByTestId('longitudinal-candidates')).not.toBeInTheDocument();
  });
});
