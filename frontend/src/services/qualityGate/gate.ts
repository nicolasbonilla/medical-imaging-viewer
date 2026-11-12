/**
 * Single quality gate — the SAME rule as backend/app/services/quality_gate.py (REQ-FUNC-117, REQ-SAFE-052..054;
 * HAZ-025; RC-122..RC-127). DRAFT, PENDING owner approval. Design: docs/iec62304/agent_platform/Quality_Gate_Design.md.
 *
 * One policy file (qualityGatePolicy.v1.json, equal to the backend's) and one shared fixture
 * (qualityGate.cases.v1.json, read by pytest AND vitest) keep both implementations identical (G4).
 * Unknown never passes (G3). Thickness only warns until the v3 evidence asset (commercial licence) is set (G7).
 *
 * In the browser the gate is consulted twice for the in-browser AI: before the run (the backend's decision,
 * skull 'pending'), and before ANY output is shown, with the skull outcome of the worker (RC-125) and the
 * platform state the backend reports at that moment (RC-126). No text here: the panel takes every word from
 * the i18n files by code (RC-127).
 */
import POLICY_JSON from '@/config/qualityGatePolicy.v1.json';

export type GateDecision = 'abstain' | 'pending' | 'proceed_with_warnings' | 'proceed';
export type GateStatus = 'pass' | 'warn' | 'pending' | 'abstain';
export type GateCheckName = 'input' | 'platform' | 'sequence' | 'thickness' | 'scanner' | 'skull';
export type GateVisitLabel = 'study' | 'tp1' | 'tp2';

export interface GateParams {
  band?: string;
  mm?: number;
  fields?: string[];
  sequence?: string;
}

export interface GateCheck {
  check: GateCheckName;
  visit: GateVisitLabel | null;
  status: GateStatus;
  code: string | null;
  params: GateParams;
}

export interface GateResult {
  gate_version: string;
  policy_version: string | null;
  mode: string | null;
  decision: GateDecision;
  ai_may_run: boolean;
  ai_output_allowed: boolean;
  codes: string[];
  checks: GateCheck[];
  trace_id?: string | null;
}

export interface GatePlatform {
  allowed: boolean;
  code: string | null;
}

export interface GateInput {
  mode?: unknown;
  visits?: unknown;
  platform?: unknown;
}

export interface GatePolicy {
  policy_version: string;
  modes: Record<string, { visits: string[]; checks: string[] }>;
  sequence: {
    values: string[];
    accepted: string[];
    confirmable_by_physician: string[];
    confirmation_modes: string[];
    min_flair_inversion_time_ms: number;
    vocabulary: {
      flair_substring: string;
      flair_compounds: string[];
      flair_pairs: [string, string][];
      t1_prefix: string;
      t2_prefix: string;
      t1_words: string[];
      other_words: string[];
    };
  };
  mode_actions?: Record<string, unknown>;
  thickness: {
    thin_limit_mm: number;
    plausible_max_mm: number;
    bands: { id: string; max_mm: number | null }[];
    evidence_asset: unknown;
    commercial_licence_allowlist: string[];
  };
  scanner: { fields: string[]; field_strength_tolerance_t: number };
  skull: { required_in_modes: string[] };
  platform: { codes: Record<string, string>; otherwise: string };
  codes: Record<string, GateStatus>;
}

export const QUALITY_GATE_POLICY = POLICY_JSON as unknown as GatePolicy;
export const GATE_VERSION = 'quality-gate/1';

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const has = (o: object, k: string) => Object.prototype.hasOwnProperty.call(o, k);
/** A finite number that is not a boolean, else null (strict: inputs are normalised). */
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

function mk(check: GateCheckName, visit: GateVisitLabel | null, status: GateStatus, code: string | null = null,
  params: GateParams = {}): GateCheck {
  return { check, visit, status, code, params };
}

function platformCheck(platform: unknown, policy: GatePolicy): GateCheck {
  if (isObj(platform) && platform.allowed === true) return mk('platform', null, 'pass');
  const code = isObj(platform) ? platform.code : undefined;
  const mapped = typeof code === 'string' && has(policy.platform.codes, code) ? policy.platform.codes[code] : policy.platform.otherwise;
  return mk('platform', null, 'abstain', mapped);
}

function sequenceCheck(visit: Obj, label: GateVisitLabel, policy: GatePolicy, mode: string): GateCheck {
  const raw = visit.sequence;
  const seq = raw === undefined || raw === null ? 'missing'
    : typeof raw === 'string' && policy.sequence.values.includes(raw) ? raw : 'unknown';
  if (policy.sequence.accepted.includes(seq)) return mk('sequence', label, 'pass');
  if (policy.sequence.confirmable_by_physician.includes(seq)) {
    // G13: the attestation lifts only unknown / missing, and only where the product offers it (single study)
    if (visit.physician_confirmed_flair === true && policy.sequence.confirmation_modes.includes(mode)) {
      return mk('sequence', label, 'warn', 'sequence_confirmed_by_physician', { sequence: seq });
    }
    return mk('sequence', label, 'abstain', `sequence_${seq}`);
  }
  return mk('sequence', label, 'abstain', 'sequence_not_flair', { sequence: seq });
}

function band(mm: number, policy: GatePolicy): string {
  for (const b of policy.thickness.bands) if (b.max_mm === null || mm <= b.max_mm) return b.id;
  return policy.thickness.bands[policy.thickness.bands.length - 1].id;
}

/** V3 EVIDENCE HOOK (REQ-SAFE-053, RC-124): only an asset with a licence on the commercial allow-list may make a
 *  band abstain. None is set in this release, so the thickness check only warns. */
function evidenceAbstainBands(policy: GatePolicy): string[] {
  const asset = policy.thickness.evidence_asset;
  if (!isObj(asset) || !policy.thickness.commercial_licence_allowlist.includes(asset.licence as string)) return [];
  const bands = asset.abstain_band_ids;
  return Array.isArray(bands) ? bands.filter((b): b is string => typeof b === 'string') : [];
}

function thicknessCheck(visit: Obj, label: GateVisitLabel, policy: GatePolicy): GateCheck {
  const rules = policy.thickness;
  const t = visit.thickness;
  const state = isObj(t) ? t.state : undefined;
  const mm = isObj(t) ? num(t.effective_mm) : null;
  const known = mm !== null && mm > 0 && mm <= rules.plausible_max_mm;
  if (state === 'native' && known && (mm as number) <= rules.thin_limit_mm) return mk('thickness', label, 'pass');
  let code: string;
  if (state === 'native' && known) code = 'thickness_thick';
  else if (state === 'at_least' && known && (mm as number) > rules.thin_limit_mm) code = 'thickness_at_least';
  else return mk('thickness', label, 'warn', 'thickness_unknown');
  const b = band(mm as number, policy);
  if (evidenceAbstainBands(policy).includes(b)) {
    return mk('thickness', label, 'abstain', 'thickness_out_of_range', { band: b, mm: mm as number });
  }
  return mk('thickness', label, 'warn', code, { band: b, mm: mm as number });
}

function skullCheck(visit: Obj, label: GateVisitLabel): GateCheck {
  const s = visit.skull;
  if (s === 'stripped') return mk('skull', label, 'pass');
  if (s === 'pending') return mk('skull', label, 'pending', 'skull_pending');
  if (s === 'not_stripped') return mk('skull', label, 'abstain', 'skull_present');
  return mk('skull', label, 'abstain', 'skull_unknown');
}

/** RC-123, as RC-062's compare_acquisitions: text upper-cased with whitespace collapsed; field strength > 0 within
 *  the tolerance; recorded for one visit only (or neither) = missing. */
function scannerValue(visit: Obj, field: string): string | number | null {
  const s = isObj(visit.scanner) ? visit.scanner : {};
  const v = s[field];
  if (field === 'magnetic_field_strength_t') {
    const x = num(v);
    return x !== null && x > 0 ? x : null;
  }
  if (typeof v !== 'string') return null;
  const text = v.split(/\s+/).filter(Boolean).join(' ');
  return text ? text.toUpperCase() : null;
}

function scannerCheck(visits: Obj[], policy: GatePolicy): GateCheck {
  const differing: string[] = [];
  const missing: string[] = [];
  for (const field of policy.scanner.fields) {
    const a = scannerValue(visits[0], field);
    const b = scannerValue(visits[1], field);
    if (a === null || b === null) missing.push(field);
    else if (typeof a === 'number' && typeof b === 'number'
      ? Math.abs(a - b) > policy.scanner.field_strength_tolerance_t : a !== b) differing.push(field);
  }
  if (differing.length) return mk('scanner', null, 'abstain', 'scanner_changed', { fields: differing });
  if (missing.length) return mk('scanner', null, 'abstain', 'scanner_unknown', { fields: missing });
  return mk('scanner', null, 'pass');
}

function result(checks: GateCheck[], policy: GatePolicy, mode: string | null = null): GateResult {
  const st = new Set(checks.map((c) => c.status));
  const decision: GateDecision = st.has('abstain') || !checks.length ? 'abstain' : st.has('pending') ? 'pending'
    : st.has('warn') ? 'proceed_with_warnings' : 'proceed';
  return {
    gate_version: GATE_VERSION,
    policy_version: policy.policy_version ?? null,
    mode,
    decision,
    ai_may_run: decision !== 'abstain',
    ai_output_allowed: decision === 'proceed' || decision === 'proceed_with_warnings',
    codes: [...new Set(checks.map((c) => c.code).filter((c): c is string => Boolean(c)))].sort(),
    checks,
  };
}

function evaluateUnsafe(inputs: unknown, policy: GatePolicy): GateResult {
  if (!isObj(inputs)) return result([mk('input', null, 'abstain', 'gate_input_invalid')], policy);
  const platform = platformCheck(inputs.platform, policy);
  if (platform.status !== 'pass') return result([platform], policy, typeof inputs.mode === 'string' ? inputs.mode : null);
  const mode = inputs.mode;
  const visits = inputs.visits;
  const spec = typeof mode === 'string' && has(policy.modes, mode) ? policy.modes[mode] : undefined;
  if (!spec || !Array.isArray(visits) || visits.length !== spec.visits.length || !visits.every(isObj)) {
    return result([platform, mk('input', null, 'abstain', 'gate_input_invalid')], policy);
  }
  const checks: GateCheck[] = [platform];
  spec.visits.forEach((label, i) => {
    const visit = visits[i] as Obj;
    checks.push(sequenceCheck(visit, label as GateVisitLabel, policy, mode as string));
    checks.push(thicknessCheck(visit, label as GateVisitLabel, policy));
    if (spec.checks.includes('skull') && policy.skull.required_in_modes.includes(mode as string)) {
      checks.push(skullCheck(visit, label as GateVisitLabel));
    }
  });
  if (spec.checks.includes('scanner')) checks.push(scannerCheck(visits as Obj[], policy));
  return result(checks, policy, mode as string);
}

/** The gate's decision for normalised inputs. Total: never throws (a fault is an abstention). */
export function evaluateGate(inputs: GateInput | unknown, policy: GatePolicy = QUALITY_GATE_POLICY): GateResult {
  try {
    return evaluateUnsafe(inputs, policy);
  } catch {
    return result([mk('input', null, 'abstain', 'gate_input_invalid')], policy);
  }
}

/** The tokens of a series description, as quality_gate.sequence_tokens: camelCase split, '*' read as 'star', '+C'
 *  as 'postcontrast', lower case, split on every non-alphanumeric character (no word-boundary regex; S1). */
export function sequenceTokens(text: string): string[] {
  const s = text.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/\*/g, ' star ').replace(/\+\s*[cC](?![A-Za-z])/g, ' postcontrast ');
  return s.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
}

const weighted = (t: string, prefix: string) => t.startsWith(prefix) && /^[a-z]*$/.test(t.slice(prefix.length));

function classifyTokens(tokens: string[], v: GatePolicy['sequence']['vocabulary']): string {
  const other = new Set(v.other_words);
  const isOther = tokens.some((t) => other.has(t) || other.has(t.replace(/[0-9]+$/, '')));
  const flair = tokens.some((t) => t.includes(v.flair_substring)) || tokens.some((t) => v.flair_compounds.includes(t))
    || tokens.slice(1).some((b, i) => v.flair_pairs.some(([x, y]) => x === tokens[i] && y === b));
  const t1 = tokens.some((t) => weighted(t, v.t1_prefix) || v.t1_words.includes(t))
    || tokens.some((t) => t.includes(v.flair_substring) && t.split(v.flair_substring).join('').includes(v.t1_prefix));
  const t2 = tokens.some((t) => weighted(t, v.t2_prefix));
  if (isOther || (flair && t1)) return 'other';                // a non-FLAIR name, or a T1-weighted FLAIR: ALWAYS abstains
  if (flair) return 'FLAIR';
  return t1 ? 'T1' : t2 ? 'T2' : 'unknown';
}

/** Sequence from a series description and inversion time, as quality_gate.sequence_from_header (G12, G4). */
export function sequenceFromHeader(text: unknown, inversionTimeMs: unknown = null, policy: GatePolicy = QUALITY_GATE_POLICY): string {
  const rules = policy.sequence;
  const tokens = typeof text === 'string' ? sequenceTokens(text) : [];
  const n = num(inversionTimeMs);
  const ti = n !== null && n > 0 ? n : null;
  if (!tokens.length && ti === null) return 'missing';
  if (ti !== null && ti < rules.min_flair_inversion_time_ms) return 'other';
  return tokens.length ? classifyTokens(tokens, rules.vocabulary) : 'unknown';
}

/** The i18n action key a check shows in a mode (G14): only where the attestation is offered may it be asked for. */
export function actionKey(mode: string | null | undefined, code: string, policy: GatePolicy = QUALITY_GATE_POLICY): string {
  const table = mode && isObj(policy.mode_actions) ? policy.mode_actions[mode] : undefined;
  const key = isObj(table) ? table[code] : undefined;
  return typeof key === 'string' ? key : 'action';
}

/** S3: the physician may attest a FLAIR only for a sequence the backend found unknown or missing, in a single study. */
export function attestable(server: ServerGateResponse | null | undefined, policy: GatePolicy = QUALITY_GATE_POLICY): boolean {
  const inputs = server?.inputs;
  if (!isObj(inputs) || !Array.isArray(inputs.visits) || typeof inputs.mode !== 'string') return false;
  if (!policy.sequence.confirmation_modes.includes(inputs.mode)) return false;
  return (inputs.visits as unknown[]).some((v) => isObj(v) && (v.sequence === 'unknown' || v.sequence === 'missing' || v.sequence === null));
}

/** The backend's answer re-evaluated locally with the physician's attestation (no call per toggle; E1). */
export function withAttestation(server: ServerGateResponse | null | undefined, attested: boolean): GateResult | null {
  if (!server) return null;
  if (!isObj(server.inputs) || !Array.isArray(server.inputs.visits) || !isObj(server.platform)) return server;
  const visits = (server.inputs.visits as unknown[]).map((v) => (isObj(v) ? { ...v, physician_confirmed_flair: attested === true } : v));
  return evaluateGate({ mode: server.inputs.mode, visits, platform: server.platform });
}

/** The decision as one line, identical to quality_gate.canonical (G4). */
export function canonicalGate(r: GateResult): string {
  const parts = (r.checks ?? []).map((c) => {
    const p = c.params ?? {};
    const param = p.band || (p.fields && p.fields.length ? p.fields.join('+') : null) || p.sequence || null;
    return `${c.check}@${c.visit || '-'}:${c.status}:${c.code || '-'}${param ? `[${param}]` : ''}`;
  });
  return `${r.decision}|${(r.codes ?? []).join(',')}|${parts.join(';')}`;
}

/** The backend could not be reached or answered something else: fail closed (G6). */
export function gateUnavailable(): GateResult {
  return evaluateGate({ platform: null });
}

/** What the backend's POST /clinical/quality-gate returns. */
export interface ServerGateResponse extends GateResult {
  inputs?: GateInput;
  platform?: GatePlatform;
}

export function isGateResult(v: unknown): v is GateResult {
  return isObj(v) && typeof v.decision === 'string' && Array.isArray(v.checks) && Array.isArray(v.codes)
    && typeof v.ai_may_run === 'boolean' && typeof v.ai_output_allowed === 'boolean';
}

/** RC-125: what the worker says the model read — the file after the skull gates passed, or after the app removed
 *  the skull. Anything else is unknown, and an unknown skull never lets the output through. */
export function skullFromProvenance(provenance: { inputPreparation?: unknown } | null | undefined): 'stripped' | 'unknown' {
  const prep = provenance?.inputPreparation;
  return prep === 'as-uploaded' || prep === 'skull-removed' ? 'stripped' : 'unknown';
}

/** The final consultation before an in-browser AI output is shown: the backend's fresh answer (platform state and
 *  the inputs it derived) re-evaluated with the worker's skull outcome. No answer = unavailable = no output. */
export function finalBrowserGate(server: ServerGateResponse | null | undefined,
  provenance: { inputPreparation?: unknown } | null | undefined): GateResult {
  if (!server || !isGateResult(server) || !isObj(server.inputs) || !Array.isArray(server.inputs.visits)
    || !isObj(server.platform)) {
    return gateUnavailable();
  }
  const skull = skullFromProvenance(provenance);
  const visits = (server.inputs.visits as unknown[]).map((v) => (isObj(v) ? { ...v, skull } : v));
  return evaluateGate({ mode: server.inputs.mode, visits, platform: server.platform });
}
