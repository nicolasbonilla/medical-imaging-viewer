/**
 * The backend's single-study quality gate (POST /api/v1/clinical/quality-gate; REQ-FUNC-117, RC-126). DRAFT.
 * Any failure — network, status, an answer of another shape — is the gate being unavailable: fail closed (G6).
 */
import { apiClient } from '@/services/apiClient';
import { gateUnavailable, isGateResult, type ServerGateResponse } from './gate';

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
  } catch {
    return unavailable();
  }
}
