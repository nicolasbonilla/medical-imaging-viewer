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

export type HeaderVerdict = 'contradicts' | 'supports' | 'none';

export interface HeaderEvidence {
  verdict: HeaderVerdict;
  reasons: string[];
  inversionTimeMs?: number;
}

/** FLAIR inversion times are ~1600-2800 ms (1.5-3 T, 2D and 3D); T1 IR / MPRAGE ~400-1200, STIR ~150-250. */
export const MIN_FLAIR_TI_MS = 1400;

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
