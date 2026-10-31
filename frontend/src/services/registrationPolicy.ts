/**
 * Whether the sign-in page may offer self-registration — PRB-020 (REQ-SEC-031; HAZ-010).
 *
 * The server decides (GET /api/v1/auth/registration, public): self-registration is OFF by default and
 * never on in production. The page shows its "Register" tab only when the server answers exactly
 * `self_registration_enabled: true`; any other answer, an error or no answer keeps it hidden (fail closed).
 * The server refuses POST /auth/register on its own anyway — hiding the tab only keeps the page truthful.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
export const REGISTRATION_STATUS_URL = `${BASE_URL}/api/v1/auth/registration`;

export async function fetchSelfRegistrationEnabled(): Promise<boolean> {
  try {
    const response = await axios.get(REGISTRATION_STATUS_URL, { timeout: 10000 });
    return response?.data?.self_registration_enabled === true;
  } catch {
    return false;
  }
}

/** React hook: false until the server has said yes; false on any error. */
export function useSelfRegistrationEnabled(): boolean {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    let alive = true;
    fetchSelfRegistrationEnabled().then((on) => {
      if (alive) setEnabled(on);
    });
    return () => {
      alive = false;
    };
  }, []);
  return enabled;
}
