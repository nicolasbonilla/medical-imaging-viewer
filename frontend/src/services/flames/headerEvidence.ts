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
 * (baseHeaderContrastEvidence below is the pre-PR function verbatim). With the gate ON, RC-049 takes the class the
 * quality gate's server returned (sixth review, G27: one implementation, on the server).
 */
import type { DicomEvidence } from './nifti';

import { FEATURES } from '@/config/features';

/** 'no_server_decision' (eighth review of PR #81, S1): the gate is on but no server class reached this call — refuse. */
export type HeaderVerdict = 'contradicts' | 'supports' | 'none' | 'no_server_decision';

export interface HeaderEvidence {
  verdict: HeaderVerdict;
  reasons: string[];
  inversionTimeMs?: number;
  /** Gate ON only (G27): the class the quality gate's SERVER derived for this file */
  sequenceClass?: string;
}

/** FLAIR inversion times are ~1600-2800 ms (1.5-3 T, 2D and 3D); T1 IR / MPRAGE ~400-1200, STIR ~150-250. */
export const MIN_FLAIR_TI_MS = 1400;

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

// ----------------------------------------------------------------------------- gate ON: the server's class
const NOT_FLAIR = new Set(['other', 'T1', 'T2']);

/**
 * Gate ON (sixth review of PR #81, G27): the browser classifies nothing. RC-049 takes the sequence class the SERVER
 * derived for this file in its gate answer (from everything its header says), as it is: another sequence refuses, a
 * FLAIR supports, anything else says nothing. The inversion time of a DICOM extension is passed on as data.
 */
function gatedHeaderContrastEvidence(
  serverSequenceClass: string | null | undefined, headerText: string[], dicom: DicomEvidence,
): HeaderEvidence {
  // the inversion time stays evidence on every path (tiFromText is the base RC-049 reader of a written TI)
  let ti = dicom.inversionTimeMs;
  if (ti === undefined) {
    for (const t of headerText) {
      ti = tiFromText(t);
      if (ti !== undefined) break;
    }
  }
  if (typeof serverSequenceClass !== 'string' || !serverSequenceClass) {
    // S1 (eighth review): FAIL CLOSED — with the gate on, a call without the server's class never runs the AI
    return { verdict: 'no_server_decision', reasons: ["no decision of the quality gate's server reached this run"],
      inversionTimeMs: ti };
  }
  const cls = serverSequenceClass;
  const verdict: HeaderVerdict = NOT_FLAIR.has(cls) ? 'contradicts' : cls === 'FLAIR' ? 'supports' : 'none';
  return { verdict, reasons: [`the quality gate's server classified the image as ${cls}`], inversionTimeMs: ti, sequenceClass: cls };
}

/**
 * RC-049 header evidence: the base code path while the gate is off (G26), the server's class while it is on (G27).
 * ``options.qualityGate`` overrides the flag (the card passes it to the worker with the server's class).
 */
export function headerContrastEvidence(
  headerText: string[],
  dicom: DicomEvidence,
  seriesDescription?: string | null,
  options: { qualityGate?: boolean; serverSequenceClass?: string | null } = {},
): HeaderEvidence {
  return (options.qualityGate ?? FEATURES.QUALITY_GATE)
    ? gatedHeaderContrastEvidence(options.serverSequenceClass, headerText, dicom)
    : baseHeaderContrastEvidence(headerText, dicom, seriesDescription);
}
