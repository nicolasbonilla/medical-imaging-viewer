import axios from 'axios';
import { installAuthInterceptors } from './session';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Axios instance configured for API requests with authentication.
 *
 * CAPA-015 (RC-069): the bearer token and the 401 handling come from the session service —
 * one silent refresh through the app's own origin (HttpOnly cookie), and if the session cannot be
 * continued the request waits for the user to sign in again in the re-login dialog, then is
 * retried. Unsaved work is never discarded and the browser is never sent to /login from here.
 * (Before: it posted a `refresh_token` from localStorage that never existed, to a route that did
 * not exist.)
 */
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

installAuthInterceptors(apiClient);

export default apiClient;
