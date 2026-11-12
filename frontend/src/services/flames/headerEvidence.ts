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
 */
import type { DicomEvidence } from './nifti';

import { QUALITY_GATE_POLICY, sequenceFromHeader, textInversionTimeMs } from '@/services/qualityGate/gate';

export type HeaderVerdict = 'contradicts' | 'supports' | 'none';

export interface HeaderEvidence {
  verdict: HeaderVerdict;
  reasons: string[];
  inversionTimeMs?: number;
  /** G15: the class of the ONE sequence classifier of the product (the single quality gate's) */
  sequenceClass?: string;
}

/** FLAIR inversion times are ~1600-2800 ms (1.5-3 T, 2D and 3D); T1 IR / MPRAGE ~400-1200, STIR ~150-250. */
export const MIN_FLAIR_TI_MS = QUALITY_GATE_POLICY.sequence.min_flair_inversion_time_ms;

const NOT_FLAIR = new Set(['other', 'T1', 'T2']);

/**
 * Second review of PR #81 (G15): ROUTED to the single quality gate's classifier (gate.ts sequenceFromHeader, the same
 * rules as the backend's quality_gate.classify_sequence). A text whose class is other, T1 or T2 contradicts; a FLAIR
 * name, or an inversion time compatible with a FLAIR, supports; anything else says nothing.
 */
export function headerContrastEvidence(
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
    reasons.push(ti < MIN_FLAIR_TI_MS
      ? `inversion time ${ti.toFixed(0)} ms is too short for a FLAIR (>= ${MIN_FLAIR_TI_MS} ms)`
      : `inversion time ${ti.toFixed(0)} ms is compatible with a FLAIR`);
  }

  const classes = texts.map((raw) => [raw, sequenceFromHeader(raw, ti ?? null)] as const);
  for (const [raw, cls] of classes) {
    if (cls === 'FLAIR') reasons.push(`header says "${raw.slice(0, 60)}"`);
    else if (NOT_FLAIR.has(cls)) reasons.push(`header names another sequence: "${raw.slice(0, 60)}"`);
  }
  const contradicting = classes.find(([, cls]) => NOT_FLAIR.has(cls));
  const sequenceClass = contradicting ? contradicting[1]
    : classes.some(([, cls]) => cls === 'FLAIR') ? 'FLAIR'
      : classes.some(([, cls]) => cls === 'unknown') ? 'unknown' : sequenceFromHeader(null, ti ?? null);
  const verdict: HeaderVerdict = NOT_FLAIR.has(sequenceClass) ? 'contradicts'
    : sequenceClass === 'FLAIR' || (ti !== undefined && ti >= MIN_FLAIR_TI_MS) ? 'supports' : 'none';
  return { verdict, reasons, inversionTimeMs: ti, sequenceClass };
}
