/**
 * FLAIR contrast gate, part 1 — header evidence (RC-049, HAZ-001 cause "wrong input contrast").
 *
 * Reads whatever the file says about its acquisition (NIfTI descrip / aux_file / intent_name / db_name,
 * text in NIfTI extensions, DICOM attributes in a DICOM extension, and the series description the app
 * holds for the same file). The file NAME is never used.
 *
 * Header evidence REFUSES an image when it names another contrast, or an inversion time that is not a FLAIR's.
 * It can count as positive evidence (flair-gate/2) only when it carries a FLAIR inversion time
 * (contrastGate.headerProvesFlair); a "FLAIR" label alone is supporting information, not proof. The
 * image-content check (contrastGate.ts) is always run as well, and can still refuse.
 *
 * Fifth review of PR #81 (G26): with VITE_ENABLE_QUALITY_GATE OFF this is the base code path of RC-049, unchanged
 * (baseHeaderContrastEvidence below is the pre-PR function verbatim). Only with the gate ON does RC-049 use the single
 * quality gate's classifier (G15, restated: with the gate on, one classifier).
 */
import type { DicomEvidence } from './nifti';

import { FEATURES } from '@/config/features';
import { classifyFields, classifyText, QUALITY_GATE_POLICY, textInversionTimeMs } from '@/services/qualityGate/gate';

export type HeaderVerdict = 'contradicts' | 'supports' | 'none';

export interface HeaderEvidence {
  verdict: HeaderVerdict;
  reasons: string[];
  inversionTimeMs?: number;
  /** Gate ON only (G15): the class of the single quality gate's sequence classifier */
  sequenceClass?: string;
}

/** FLAIR inversion times are ~1600-2800 ms (1.5-3 T, 2D and 3D); T1 IR / MPRAGE ~400-1200, STIR ~150-250. */
export const MIN_FLAIR_TI_MS = 1400;
/** Gate ON: the policy's limit (equal today; a test pins the two together). */
const GATE_MIN_FLAIR_TI_MS = QUALITY_GATE_POLICY.sequence.min_flair_inversion_time_ms;

// ----------------------------------------------------------------------------- base code path (gate OFF), verbatim
const FLAIR = /(FLAIR|DARK[ _-]?FLUID|DARKFLUID|TIRM|FLUID[ _-]?ATTENUATED)/;
const T1_FLAIR = /(T1[ _-]*W?[ _-]*FLAIR|FLAIR[ _-]*T1\b)/;
const OTHER =
  /\b(T1|T1W|T1-W|T1[ _-]?WEIGHTED|MPRAGE|MP[ _-]?RAGE|SPGR|FSPGR|BRAVO|TFE|T2|T2W|T2[ _-]?WEIGHTED|PD|PDW|PROTON[ _-]?DENSITY|DWI|DTI|ADC|TRACE|SWI|SWAN|T2STAR|T2\*|STIR|DIR|PSIR|MRA|TOF|GD|GADO|POSTGD|POST[ _-]?CONTRAST|LOCALI[SZ]ER|SCOUT)\b/;

function tiFromText(text: string): number | undefined {
  const m = /\bTI\s*[=:]\s*([0-9]+(?:\.[0-9]+)?)/i.exec(text);
  if (!m) return undefined;
  const v = parseFloat(m[1]);
  if (!Number.isFinite(v) || v <= 0) return undefined;
  return v < 10 ? v * 1000 : v; // seconds written as e.g. "TI=2.5"
}

function baseHeaderContrastEvidence(
  headerText: string[],
  dicom: DicomEvidence,
  seriesDescription?: string | null,
): HeaderEvidence {
  const texts = [
    ...headerText,
    dicom.seriesDescription,
    dicom.protocolName,
    dicom.sequenceName,
    seriesDescription ?? undefined,
  ].filter((t): t is string => Boolean(t && t.trim()));
  const reasons: string[] = [];
  let contradicts = false;
  let supports = false;

  let ti = dicom.inversionTimeMs;
  if (ti === undefined) {
    for (const t of texts) {
      ti = tiFromText(t);
      if (ti !== undefined) break;
    }
  }
  if (ti !== undefined && ti > 0) {
    if (ti < MIN_FLAIR_TI_MS) {
      contradicts = true;
      reasons.push(`inversion time ${ti.toFixed(0)} ms is too short for a FLAIR (>= ${MIN_FLAIR_TI_MS} ms)`);
    } else {
      supports = true;
      reasons.push(`inversion time ${ti.toFixed(0)} ms is compatible with a FLAIR`);
    }
  }

  for (const raw of texts) {
    const t = raw.toUpperCase();
    if (T1_FLAIR.test(t)) {
      contradicts = true;
      reasons.push(`header says "${raw.slice(0, 60)}" (a T1-weighted FLAIR is not a T2 FLAIR)`);
    } else if (FLAIR.test(t)) {
      supports = true;
      reasons.push(`header says "${raw.slice(0, 60)}"`);
    } else if (OTHER.test(t)) {
      contradicts = true;
      reasons.push(`header names another sequence: "${raw.slice(0, 60)}"`);
    }
  }
  return { verdict: contradicts ? 'contradicts' : supports ? 'supports' : 'none', reasons, inversionTimeMs: ti };
}

// ----------------------------------------------------------------------------- gate ON: the single classifier
const NOT_FLAIR = new Set(['other', 'T1', 'T2']);

/**
 * Gate ON (G15, G19): the single quality gate's FIELD-AWARE classifier (gate.ts classifyFields, the same rules as the
 * backend's quality_gate.classify_fields): the descriptions by their tokens, the SequenceName by the vendor-code table
 * ('*' is a Siemens prefix there), the ImageType by its own list — never one text blob. F5 (fifth review): each text's
 * reason comes from its WORDS alone; an inversion time has its own reason and never makes a FLAIR text read as
 * "another sequence".
 */
function gatedHeaderContrastEvidence(
  headerText: string[],
  dicom: DicomEvidence,
  seriesDescription?: string | null,
): HeaderEvidence {
  const texts = [
    ...headerText,
    dicom.seriesDescription,
    dicom.protocolName,
    seriesDescription ?? undefined,
  ].filter((t): t is string => Boolean(t && t.trim()));
  const reasons: string[] = [];

  let ti = dicom.inversionTimeMs;
  if (ti === undefined) {
    for (const t of texts) {
      const found = textInversionTimeMs(t);
      if (found !== null) {
        ti = found;
        break;
      }
    }
  }
  if (ti !== undefined && ti > 0) {
    reasons.push(ti < GATE_MIN_FLAIR_TI_MS
      ? `inversion time ${ti.toFixed(0)} ms is too short for a FLAIR (>= ${GATE_MIN_FLAIR_TI_MS} ms)`
      : `inversion time ${ti.toFixed(0)} ms is compatible with a FLAIR`);
  }

  for (const raw of texts) {
    const cls = classifyText(raw);                     // F5: the words alone, never the inversion time
    if (cls === 'FLAIR') reasons.push(`header says "${raw.slice(0, 60)}"`);
    else if (cls !== null && NOT_FLAIR.has(cls)) reasons.push(`header names another sequence: "${raw.slice(0, 60)}"`);
  }
  if (dicom.sequenceName && NOT_FLAIR.has(classifyFields({ sequence_name: dicom.sequenceName }).class)) {
    reasons.push(`sequence code "${dicom.sequenceName.slice(0, 40)}" is another sequence`);
  }
  const sequenceClass = classifyFields({ description: texts, sequence_name: dicom.sequenceName ?? null,
    image_type: dicom.imageType ?? null }, ti ?? null).class;
  const verdict: HeaderVerdict = NOT_FLAIR.has(sequenceClass) ? 'contradicts'
    : sequenceClass === 'FLAIR' || (ti !== undefined && ti >= GATE_MIN_FLAIR_TI_MS) ? 'supports' : 'none';
  return { verdict, reasons, inversionTimeMs: ti, sequenceClass };
}

/**
 * RC-049 header evidence: the base code path while VITE_ENABLE_QUALITY_GATE is off (G26), the single quality gate's
 * classifier while it is on. ``options.qualityGate`` overrides the flag (tests, and the worker's job when it carries it).
 */
export function headerContrastEvidence(
  headerText: string[],
  dicom: DicomEvidence,
  seriesDescription?: string | null,
  options: { qualityGate?: boolean } = {},
): HeaderEvidence {
  return (options.qualityGate ?? FEATURES.QUALITY_GATE)
    ? gatedHeaderContrastEvidence(headerText, dicom, seriesDescription)
    : baseHeaderContrastEvidence(headerText, dicom, seriesDescription);
}
