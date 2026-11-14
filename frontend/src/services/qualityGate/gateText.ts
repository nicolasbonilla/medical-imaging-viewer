/**
 * K4 (fourteenth review of PR #81; RC-127; DRAFT, PENDING owner approval): the ONE place a gate code becomes the words a
 * clinician reads. Every display path (the gate panel — in the browser card and the comparison — and the comparison's
 * warnings under RC-062) calls formatGateMessage; nothing else translates a gate code. Each placeholder gets its value
 * — a band, the changed fields, a sequence name, the seconds to wait — or, when the value is missing or unknown, the
 * defined fallback (qualityGate.paramMissing): never a raw "{{band}}", an empty slot or an i18n key.
 */
import type { TFunction } from 'i18next';
import i18n from '@/i18n/config';
import type { GateParams } from './gate';

const word = (t: TFunction, key: string): string | null => (i18n.exists(key) ? String(t(key)) : null);

/** The value of every placeholder a gate text may hold, for these params (fallback for a missing or unknown one). */
export function gateParams(t: TFunction, params?: GateParams | null): Record<string, string> {
  const fallback = String(t('qualityGate.paramMissing'));
  const p = params ?? {};
  const band = typeof p.band === 'string' ? word(t, `qualityGate.band.${p.band}`) : null;
  const sequence = typeof p.sequence === 'string' ? word(t, `qualityGate.sequenceName.${p.sequence}`) : null;
  const fields = (Array.isArray(p.fields) ? p.fields : [])
    .map((f) => (typeof f === 'string' ? word(t, `qualityGate.field.${f}`) : null))
    .filter((f): f is string => !!f);
  const s = p.seconds;
  const seconds = typeof s === 'number' && Number.isFinite(s) && s > 0 ? String(Math.ceil(s)) : null;
  return { band: band ?? fallback, sequence: sequence ?? fallback, fields: fields.length ? fields.join(', ') : fallback,
    seconds: seconds ?? fallback };
}

/** The text of one part ('message', 'action', 'action_comparison') of a gate code, with its params filled in. */
export function formatGateMessage(t: TFunction, code: string, part: string, params?: GateParams | null): string {
  const key = `qualityGate.codes.${code}.${part}`;
  const known = i18n.exists(key) ? key : `qualityGate.codes.${code}.message`;
  if (!i18n.exists(known)) return String(t('qualityGate.paramMissing'));
  return String(t(known, gateParams(t, params)));
}
