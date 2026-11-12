/**
 * Single quality gate in the browser — DISPLAY AND REQUEST ONLY (REQ-FUNC-117/118, REQ-SAFE-052e; HAZ-025;
 * RC-122..RC-127). DRAFT, PENDING owner approval. Design: docs/iec62304/agent_platform/Quality_Gate_Design.md.
 *
 * Sixth review of PR #81 (G27, server-authoritative): the rule, the policy and the sequence classifier exist ONLY on
 * the server (backend/app/services/quality_gate.py). The browser sends its inputs — the file, the physician's
 * attestation, the skull outcome the worker reports — and shows the server's answer as it is: the decision, the
 * checks, the visits that may be attested and the action of each code all come in the answer. Nothing here
 * classifies, evaluates or re-evaluates. When there is no usable answer the browser fails closed (unavailable).
 */

export type GateDecision = 'abstain' | 'pending' | 'proceed_with_warnings' | 'proceed';
export type GateStatus = 'pass' | 'warn' | 'pending' | 'abstain';
export type GateCheckName = 'input' | 'platform' | 'sequence' | 'thickness' | 'scanner' | 'skull';
export type GateVisitLabel = 'study' | 'tp1' | 'tp2';

export interface GateParams {
  /** F3: the seconds to wait after a refused consultation (gate_rate_limited) */
  seconds?: number;
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
  /** G27: the visits whose FLAIR the physician may attest in this answer's mode (from the server's policy) */
  attestable_visits?: GateVisitLabel[];
  /** G27 / G14: the i18n action key of each code in this answer's mode (from the server's policy) */
  actions?: Record<string, string>;
  trace_id?: string | null;
}

export interface GatePlatform {
  allowed: boolean;
  code: string | null;
}

/** What the backend's POST /clinical/quality-gate returns. */
export interface ServerGateResponse extends GateResult {
  inputs?: { mode?: string; visits?: { sequence?: string }[] };
  platform?: GatePlatform;
  /** G18: the file the answer was made for, and its version on the server (null when unknown) */
  subject?: { file_id: string; version: string | null };
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

/** A fixed answer that stops the AI (fail closed), with its code — built by the browser only when it has no answer. */
function stopped(code: string, params: GateParams = {}): GateResult {
  return {
    gate_version: 'quality-gate/1', policy_version: null, mode: null, decision: 'abstain', ai_may_run: false,
    ai_output_allowed: false, codes: [code], checks: [{ check: 'platform', visit: null, status: 'abstain', code, params }],
    attestable_visits: [], actions: {},
  };
}

/** The backend could not be reached or answered something else: fail closed (G6). */
export function gateUnavailable(): GateResult {
  return stopped('gate_unavailable');
}

/** F3: the backend refused a consultation over the per-user limit; abstain with the seconds to wait. */
export function gateRateLimited(seconds: unknown): GateResult {
  const s = typeof seconds === 'number' && Number.isFinite(seconds) && seconds > 0 ? Math.min(60, Math.ceil(seconds)) : 60;
  return stopped('gate_rate_limited', { seconds: s });
}

/** U2 (sixth review): an answer the browser retries by itself, and after how many seconds; null for a decision. */
export function retryAfterSeconds(r: GateResult | null | undefined): number | null {
  if (!r || r.ai_may_run || r.codes.length !== 1) return null;
  if (r.codes[0] === 'gate_rate_limited') return r.checks[0]?.params?.seconds ?? 60;
  if (r.codes[0] === 'gate_unavailable') return UNAVAILABLE_RETRY_SECONDS;
  return null;
}
export const UNAVAILABLE_RETRY_SECONDS = 10;

export function isGateResult(v: unknown): v is GateResult {
  return isObj(v) && typeof v.decision === 'string' && Array.isArray(v.checks) && Array.isArray(v.codes)
    && typeof v.ai_may_run === 'boolean' && typeof v.ai_output_allowed === 'boolean';
}

/** G14 / G27: the action the answer names for a code, else the default action. */
export function actionOf(r: GateResult, code: string): string {
  const key = isObj(r.actions) ? r.actions[code] : undefined;
  return typeof key === 'string' && /^action(_[a-z]+)?$/.test(key) ? key : 'action';
}

/** The sequence class the SERVER derived for the single study (RC-049 with the gate on takes it as it is). */
export function serverSequenceClass(r: ServerGateResponse | null | undefined): string | null {
  const v = r?.inputs?.visits?.[0]?.sequence;
  return typeof v === 'string' ? v : null;
}

/** RC-125 input: what the worker says the model read — the file after the skull gates passed, or after the app
 *  removed the skull; anything else is unknown. The browser REPORTS it; the server decides with it. */
export function skullFromProvenance(provenance: { inputPreparation?: unknown } | null | undefined): 'stripped' | 'unknown' {
  const prep = provenance?.inputPreparation;
  return prep === 'as-uploaded' || prep === 'skull-removed' ? 'stripped' : 'unknown';
}
