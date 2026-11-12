/**
 * The backend's single-study quality gate (POST /api/v1/clinical/quality-gate; REQ-FUNC-117, RC-126). DRAFT.
 * Any failure — network, status, an answer of another shape — is the gate being unavailable: fail closed (G6).
 */
import { apiClient } from '@/services/apiClient';
import { gateNotEnabled, gateRateLimited, gateUnavailable, isGateResult, type ServerGateResponse } from './gate';

export type ReportedSkull = 'pending' | 'stripped' | 'unknown';

/** G18: the answer always names the file it was made for; an answer for another file is unavailable. */
export async function requestQualityGate(fileId: string, physicianConfirmedFlair: boolean,
  skull: ReportedSkull = 'pending'): Promise<ServerGateResponse> {
  const unavailable = (): ServerGateResponse => ({ ...gateUnavailable(), subject: { file_id: fileId, version: null } });
  try {
    const { data } = await apiClient.post('/api/v1/clinical/quality-gate', {
      file_id: fileId,
      physician_confirmed_flair: physicianConfirmedFlair === true,
      skull,
    });
    const answer = data as ServerGateResponse;
    return isGateResult(answer) && answer.subject?.file_id === fileId ? answer : unavailable();
  } catch (err: unknown) {
    // F3 (fifth review of PR #81): over the per-user limit the answer says how long to wait (never "unavailable")
    const response = (err as { response?: { status?: number; data?: unknown; headers?: Record<string, unknown> } })?.response;
    // G29: the browser gate is on while the server's is off (the route is not enabled): said as such, never retried
    if (response?.status === 404) return { ...gateNotEnabled(), subject: { file_id: fileId, version: null } };
    if (response?.status === 429) {
      const details = (response.data as { error?: { details?: { retry_after_s?: unknown } } } | undefined)?.error?.details;
      const header = Number(response.headers?.['retry-after']);
      const seconds = typeof details?.retry_after_s === 'number' ? details.retry_after_s : header;
      return { ...gateRateLimited(seconds), subject: { file_id: fileId, version: null } };
    }
    return unavailable();
  }
}
