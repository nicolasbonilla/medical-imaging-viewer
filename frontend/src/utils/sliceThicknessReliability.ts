/**
 * Reliability by slice thickness — pure logic (CP-SLICE-THICKNESS-001, DRAFT, PENDING owner
 * approval; feature flag OFF by default).
 *
 * Paper A v0.3 (PR #54): automatic MS-lesion detection depends on the slice thickness of the
 * ORIGINAL acquisition, and a 1-mm grid is not evidence of a thin acquisition. This module
 * turns the backend's acquisition geometry (RC-054) into what the reliability card may say:
 *
 *  - RC-055 `parseGeometry` / `resolveThickness`: the thickness is read only from
 *    `metadata.acquisition_geometry` (never from the legacy `slice_thickness`, which is 1.0 mm
 *    by default), strictly validated, for the segmentation's own image — or, for a processed
 *    image, from the study's single original FLAIR (named on the card). Anything else is
 *    "not determinable"; when two sources disagree the thicker one wins.
 *  - RC-056 `assessReliability().falseLesionFigure`: no false-lesion figure is ever shown in
 *    this version (thick or unknown: not reliable without a >= 10-patient site calibration,
 *    none exists; thin: no calibration for the deployed segmenter).
 *  - RC-057: detection figures come only from the versioned asset
 *    `config/sliceThicknessReliability.v1.json` (bound to its source record); the smallest
 *    size "found 8 times in 10" is computed, worst case over every evidence row of the band
 *    (and, for a lower bound, of every thicker band).
 *
 * @module utils/sliceThicknessReliability
 */
import ASSET_JSON from '../config/sliceThicknessReliability.v1.json';
import { isPreprocessedInstance } from './instanceClassification';
import { detectSequence } from './sequenceDetection';

// ─── Asset ────────────────────────────────────────────────────────────────────────────

export type Lang = 'en' | 'es' | 'de';
type Localised = Record<Lang, string>;

export interface EvidenceRow {
  record_key: string;
  scans: number;
  patients: number;
  sites: number;
  post_hoc: boolean;
  detection: number[];
  lesions: number[];
  label: Localised;
}

export interface Band {
  id: string;
  min_mm: number;
  max_mm: number;
  thick: boolean;
  rows: string[];
  label: Localised;
}

export interface ReliabilityAsset {
  asset_id: string;
  asset_version: string;
  source: { commit: string; pull_request: number; records: { path: string; sha256: string; post_hoc: boolean }[] };
  thin_limit_mm: number;
  plausible_max_mm: number;
  reliable_fraction: number;
  half_fraction: number;
  size_bins: { min_mm3: number; max_mm3: number | null; min_diameter_mm: number; max_diameter_mm: number | null }[];
  evidence_rows: Record<string, EvidenceRow>;
  bands: Band[];
  false_lesion_figure: { shown: boolean; site_calibration: unknown; min_site_calibration_patients: number };
  messages: Record<Lang, Record<string, unknown> & { reasons: Record<string, string> }>;
}

export const ASSET = ASSET_JSON as unknown as ReliabilityAsset;

/**
 * Structural checks on the evidence asset. The card refuses to show any figure from an asset
 * that fails them (it shows the "not available" state instead of a possibly wrong number).
 * Returns the list of problems (empty = valid).
 */
export function validateAsset(a: ReliabilityAsset): string[] {
  const problems: string[] = [];
  const nBins = a.size_bins?.length ?? 0;
  if (nBins !== 5) problems.push('size_bins must have 5 bins');
  if (!(a.reliable_fraction > a.half_fraction && a.half_fraction > 0 && a.reliable_fraction <= 1)) {
    problems.push('fractions out of order');
  }
  if (a.false_lesion_figure?.shown !== false) problems.push('false_lesion_figure.shown must be false');
  if (a.false_lesion_figure?.site_calibration !== null) {
    problems.push('site_calibration must be null: displaying a calibrated figure is not implemented');
  }
  if (!(a.false_lesion_figure?.min_site_calibration_patients >= 10)) problems.push('min site calibration < 10');
  for (const [id, row] of Object.entries(a.evidence_rows ?? {})) {
    if (row.detection?.length !== nBins || row.lesions?.length !== nBins) problems.push(`${id}: bin count`);
    if (!row.detection?.every((d) => Number.isFinite(d) && d >= 0 && d <= 1)) problems.push(`${id}: detection range`);
    if (!(row.scans > 0 && row.patients > 0 && row.sites > 0)) problems.push(`${id}: evidence size`);
    for (const lang of ['en', 'es', 'de'] as Lang[]) if (!row.label?.[lang]) problems.push(`${id}: label ${lang}`);
  }
  const bands = a.bands ?? [];
  if (!bands.length || bands[0].min_mm !== 0) problems.push('bands must start at 0');
  bands.forEach((b, i) => {
    if (!(b.max_mm > b.min_mm)) problems.push(`${b.id}: empty band`);
    if (i > 0 && b.min_mm !== bands[i - 1].max_mm) problems.push(`${b.id}: gap or overlap`);
    if (b.thick !== b.min_mm >= a.thin_limit_mm) problems.push(`${b.id}: thick flag disagrees with thin limit`);
    if (!b.rows.length || b.rows.some((r) => !a.evidence_rows[r])) problems.push(`${b.id}: rows`);
  });
  if (bands.length && bands[bands.length - 1].max_mm !== a.plausible_max_mm) problems.push('last band must end at plausible max');
  for (const lang of ['en', 'es', 'de'] as Lang[]) if (!a.messages?.[lang]?.reasons) problems.push(`messages ${lang}`);
  return problems;
}

// ─── RC-055: parse the backend geometry strictly ───────────────────────────────────────

export type GeometryState = 'native' | 'at_least' | 'not_determinable';

export interface ParsedGeometry {
  state: GeometryState;
  mm: number | null;
  reason: string | null;
}

const ND = (reason: string): ParsedGeometry => ({ state: 'not_determinable', mm: null, reason });

/**
 * Accept only a well-formed `acquisition_geometry`. A `native` value must come from a DICOM
 * header; an `at_least` value must be thick (a lower bound at or below the thin limit says
 * nothing). Any other shape, an unknown state, or a missing object -> not determinable.
 * Deliberately ignores every other metadata field (in particular `slice_thickness`).
 */
export function parseGeometry(raw: unknown, a: ReliabilityAsset = ASSET): ParsedGeometry {
  if (!raw || typeof raw !== 'object') return ND('malformed');
  const g = raw as Record<string, unknown>;
  const mm = typeof g.effective_mm === 'number' && Number.isFinite(g.effective_mm) ? g.effective_mm : null;
  const plausible = mm !== null && mm > 0 && mm <= a.plausible_max_mm;
  if (g.state === 'native') {
    if (!plausible || g.source !== 'dicom_header') return ND('malformed');
    return { state: 'native', mm, reason: null };
  }
  if (g.state === 'at_least') {
    if (!plausible || (mm as number) <= a.thin_limit_mm) return ND('malformed');
    return { state: 'at_least', mm, reason: typeof g.reason === 'string' ? g.reason : null };
  }
  if (g.state === 'not_determinable') {
    const reason = typeof g.reason === 'string' && g.reason in a.messages.en.reasons ? g.reason : 'unreadable';
    return ND(reason);
  }
  return ND('malformed');
}

// ─── RC-055: which image's thickness ──────────────────────────────────────────────────

export interface StudyInstanceLike {
  gcs_object_name: string;
  original_filename?: string;
}

export type OriginalLookup =
  | { kind: 'not_needed' }
  | { kind: 'missing' }
  | { kind: 'ambiguous'; count: number }
  | { kind: 'found'; fileId: string; filename: string };

const NOT_AN_IMAGE = /(mask|seg|label|lesion|roi|zonemap|probab)/i;

function basename(path: string): string {
  return path.split('/').pop() || path;
}

/**
 * Where the analysed image came from. For an ORIGINAL image: itself. For a processed image
 * (`_pp`, `desc-preproc`, ...): the study's single original FLAIR, by the same filename
 * conventions the viewer uses to list "Original" and "Preprocessed" images. Zero or several
 * candidates -> no guess.
 */
export function locateSource(
  sourceFileId: string | undefined,
  instances: ReadonlyArray<StudyInstanceLike> | undefined,
): { ownFilename: string; ownIsProcessed: boolean; original: OriginalLookup } {
  const list = instances ?? [];
  const own = list.find((i) => i.gcs_object_name === sourceFileId);
  const ownFilename = own?.original_filename || (sourceFileId ? basename(sourceFileId) : '');
  const ownIsProcessed = isPreprocessedInstance(ownFilename);
  if (!ownIsProcessed) return { ownFilename, ownIsProcessed, original: { kind: 'not_needed' } };
  const originals = list.filter((i) => {
    const name = i.original_filename || '';
    return (
      i.gcs_object_name !== sourceFileId &&
      !isPreprocessedInstance(name) &&
      !NOT_AN_IMAGE.test(name) &&
      detectSequence(name) === 'FLAIR'
    );
  });
  if (originals.length === 0) return { ownFilename, ownIsProcessed, original: { kind: 'missing' } };
  if (originals.length > 1) return { ownFilename, ownIsProcessed, original: { kind: 'ambiguous', count: originals.length } };
  return {
    ownFilename,
    ownIsProcessed,
    original: { kind: 'found', fileId: originals[0].gcs_object_name, filename: originals[0].original_filename || basename(originals[0].gcs_object_name) },
  };
}

export type Resolution =
  | { kind: 'band'; basis: 'native' | 'at_least'; mm: number; file: string; viaOriginal: boolean }
  | { kind: 'not_determinable'; reasons: string[] };

/**
 * Combine the analysed image's own geometry with its original FLAIR's (when it is a processed
 * image). A native value is used only from a DICOM header; every known lower bound is applied
 * too, so the result is never thinner than any source shows (the thicker one wins).
 */
export function resolveThickness(input: {
  own: ParsedGeometry;
  ownFilename: string;
  ownIsProcessed: boolean;
  original: OriginalLookup;
  originalGeometry: ParsedGeometry | null;
}): Resolution {
  const { own, ownFilename, ownIsProcessed, original, originalGeometry } = input;
  type Cand = { basis: 'native' | 'at_least'; mm: number; file: string; viaOriginal: boolean };
  const known: Cand[] = [];
  const reasons: string[] = [];

  const take = (g: ParsedGeometry, file: string, viaOriginal: boolean) => {
    if ((g.state === 'native' || g.state === 'at_least') && g.mm !== null) {
      known.push({ basis: g.state, mm: g.mm, file, viaOriginal });
    } else if (g.reason) {
      reasons.push(g.reason);
    }
  };

  take(own, ownFilename, false);
  if (ownIsProcessed) {
    if (original.kind === 'found') {
      take(originalGeometry ?? ND('unreadable'), original.filename, true);
    } else if (original.kind === 'missing') {
      reasons.push('original_missing');
    } else if (original.kind === 'ambiguous') {
      reasons.push('original_ambiguous');
    }
  }

  if (!known.length) {
    return { kind: 'not_determinable', reasons: reasons.length ? Array.from(new Set(reasons)) : ['unreadable'] };
  }
  // The thickest known value wins; on a tie a native value is preferred (same number, better source).
  const chosen = known.reduce((m, c) => (c.mm > m.mm || (c.mm === m.mm && c.basis === 'native') ? c : m));
  return { kind: 'band', ...chosen };
}

// ─── RC-057: detection figures from the asset, worst case ─────────────────────────────

/** Smallest bin index i such that bin i AND every larger bin reach `fraction`; null = never. */
export function smallestBinFrom(detection: ReadonlyArray<number>, fraction: number): number | null {
  let from: number | null = null;
  for (let i = detection.length - 1; i >= 0; i--) {
    if (detection[i] >= fraction) from = i;
    else break;
  }
  return from;
}

function worstCase(rowIds: string[], fraction: number, a: ReliabilityAsset): number | null {
  let worst = -1;
  for (const id of rowIds) {
    const bin = smallestBinFrom(a.evidence_rows[id].detection, fraction);
    if (bin === null) return null;
    worst = Math.max(worst, bin);
  }
  return worst < 0 ? null : worst;
}

export type FalseLesionReason = 'thick_or_unknown' | 'no_calibration_for_deployed_segmenter';

export interface ReliabilityView {
  kind: 'band' | 'not_determinable' | 'unavailable';
  /** Thick-slice guidance applies (thick, lower bound, unknown, unavailable). */
  thick: boolean;
  basis: 'native' | 'at_least' | null;
  mm: number | null;
  file: string | null;
  viaOriginal: boolean;
  bands: Band[];
  rows: string[];
  reliableBin: number | null;
  halfBin: number | null;
  reasons: string[];
  /** RC-056: never shown in this version. */
  falseLesionFigure: { shown: false; reason: FalseLesionReason };
}

export function assessReliability(res: Resolution, a: ReliabilityAsset = ASSET): ReliabilityView {
  const empty = {
    basis: null, mm: null, file: null, viaOriginal: false, bands: [] as Band[], rows: [] as string[],
    reliableBin: null, halfBin: null,
  };
  if (validateAsset(a).length) {
    return { kind: 'unavailable', thick: true, ...empty, reasons: ['unreadable'], falseLesionFigure: { shown: false, reason: 'thick_or_unknown' } };
  }
  if (res.kind === 'not_determinable') {
    return { kind: 'not_determinable', thick: true, ...empty, reasons: res.reasons, falseLesionFigure: { shown: false, reason: 'thick_or_unknown' } };
  }
  const bands =
    res.basis === 'native'
      ? a.bands.filter((b) => res.mm > b.min_mm && res.mm <= b.max_mm)
      : a.bands.filter((b) => b.max_mm >= res.mm && b.min_mm >= a.thin_limit_mm);
  if (!bands.length) {
    return { kind: 'not_determinable', thick: true, ...empty, reasons: ['invalid'], falseLesionFigure: { shown: false, reason: 'thick_or_unknown' } };
  }
  const rows = Array.from(new Set(bands.flatMap((b) => b.rows)));
  const thick = res.basis === 'at_least' || bands.some((b) => b.thick);
  return {
    kind: 'band',
    thick,
    basis: res.basis,
    mm: res.mm,
    file: res.file,
    viaOriginal: res.viaOriginal,
    bands,
    rows,
    reliableBin: worstCase(rows, a.reliable_fraction, a),
    halfBin: worstCase(rows, a.half_fraction, a),
    reasons: [],
    falseLesionFigure: { shown: false, reason: thick ? 'thick_or_unknown' : 'no_calibration_for_deployed_segmenter' },
  };
}

export function pickLang(language: string | undefined): Lang {
  const two = (language || 'en').slice(0, 2).toLowerCase();
  return two === 'es' || two === 'de' ? two : 'en';
}

export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (m, k) => (k in values ? String(values[k]) : m));
}
