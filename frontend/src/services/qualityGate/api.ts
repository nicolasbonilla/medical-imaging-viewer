/**
 * The backend's single-study quality gate (POST /api/v1/clinical/quality-gate; REQ-FUNC-117, RC-126). DRAFT.
 * Any failure — network, status, an answer of another shape — is the gate being unavailable: fail closed (G6).
 */
import { apiClient } from '@/services/apiClient';
import { gateUnavailable, isGateResult, type ServerGateResponse } from './gate';

export async function requestQualityGate(fileId: string, physicianConfirmedFlair: boolean): Promise<ServerGateResponse> {
  try {
    const { data } = await apiClient.post('/api/v1/clinical/quality-gate', {
      file_id: fileId,
      physician_confirmed_flair: physicianConfirmedFlair === true,
    });
    return isGateResult(data) ? (data as ServerGateResponse) : gateUnavailable();
  } catch {
    return gateUnavailable();
  }
}
