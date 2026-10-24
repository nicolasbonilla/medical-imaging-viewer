import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import axios, { AxiosError } from 'axios';
import {
  abandonReauthentication,
  authClient,
  authUrl,
  clearSession,
  completeReauthentication,
  getAccessToken,
  getAccessTokenExpiry,
  getSessionStatus,
  installAuthInterceptors,
  installSessionListeners,
  refreshAccessToken,
  scheduleProactiveRefresh,
  storeSession,
  subscribeSession,
} from '@/services/session';

/**
 * Authentication state.
 *
 * CAPA-015 (RC-068, RC-069): every /auth call goes to the app's own origin with credentials, so
 * the HttpOnly refresh cookie is set and sent; the access token is short-lived and renewed
 * silently. A 401 no longer clears the session and sends the browser to /login (which discarded
 * unsaved work held in memory): the session service asks the SAME user to sign in again in the
 * re-login dialog and the refused requests are retried. Logout now tells the server, which
 * revokes the refresh session.
 */

// Helper to clear auth data
const clearAuthData = () => {
  clearSession();
  localStorage.removeItem('user');
  delete axios.defaults.headers.common['Authorization'];
};

// User interface matching backend User model
export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: 'VIEWER' | 'TECHNICIAN' | 'RADIOLOGIST' | 'ADMIN';
  is_active: boolean;
  is_locked: boolean;
  failed_login_attempts: number;
  last_login: string | null;
  created_at: string;
  updated_at: string;
}

// Token interface
export interface Token {
  access_token: string;
  token_type: string;
  expires_in: number;
}

/** Raised when someone other than the signed-in user authenticates in the re-login dialog. */
export class WrongUserError extends Error {
  constructor() {
    super('A different user signed in');
    this.name = 'WrongUserError';
  }
}

export interface CaptchaAnswer {
  id: string;
  response: string;
}

// Auth context type
interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** The session could not be continued silently; the re-login dialog is open. */
  sessionExpired: boolean;
  login: (username: string, password: string, captchaId?: string, captchaResponse?: string) => Promise<void>;
  loginWithPasskey: (username: string) => Promise<void>;
  register: (userData: RegisterData) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  /** Re-login of the SAME user from the dialog; unsaved work stays in memory. */
  reauthenticate: (password: string, captcha?: CaptchaAnswer) => Promise<void>;
  reauthenticateWithPasskey: () => Promise<void>;
}

// Registration data interface
export interface RegisterData {
  username: string;
  email: string;
  password: string;
  full_name: string;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Custom hook to use auth context
export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

const bearer = (token: string | null | undefined) => (token ? { Authorization: `Bearer ${token}` } : {});

/** GET /auth/me with the stored token; one silent refresh on 401. */
async function loadMe(): Promise<User> {
  const call = (token: string | null) => authClient.get(authUrl('/me'), { headers: bearer(token) });
  try {
    return (await call(getAccessToken())).data;
  } catch (e) {
    if ((e as AxiosError)?.response?.status === 401) {
      return (await call(await refreshAccessToken())).data;
    }
    throw e;
  }
}

async function passkeyLogin(username: string): Promise<any> {
  const { prepareAuthenticationOptions, serializeAuthenticationCredential } = await import('@/utils/webauthn');
  // Step 1: Get authentication options
  const beginRes = await authClient.post(authUrl('/webauthn/login/begin'), { username });
  const options = prepareAuthenticationOptions(beginRes.data.options);
  // Step 2: Browser prompt (Face ID, Windows Hello, fingerprint)
  const credential = await navigator.credentials.get({ publicKey: options }) as PublicKeyCredential;
  if (!credential) throw new Error('Authentication cancelled');
  // Step 3: Verify on server
  const completeRes = await authClient.post(authUrl('/webauthn/login/complete'), {
    credential: serializeAuthenticationCredential(credential),
    username,
  });
  return completeRes.data;
}

// Auth Provider Component
interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(getSessionStatus() === 'expired');

  // Keep React state in step with the session service (silent refresh, re-login, other tabs).
  useEffect(() => subscribeSession(() => {
    setSessionExpired(getSessionStatus() === 'expired');
    setToken(getAccessToken());
  }), []);

  // Logout function - defined early so other effects can use it
  const performLogout = useCallback(() => {
    clearAuthData();
    setToken(null);
    setUser(null);
  }, []);

  // Global axios instance: bearer token + silent refresh. No automatic logout or redirect on 401
  // (CAPA-015 RC-069): the re-login dialog keeps the page and its unsaved work.
  useEffect(() => installAuthInterceptors(axios), []);
  useEffect(() => installSessionListeners(), []);

  const acceptSession = useCallback((data: { token: Token; user: User }) => {
    const { token: tokenData, user: userData } = data;
    storeSession(tokenData.access_token, tokenData.expires_in);
    localStorage.setItem('user', JSON.stringify(userData));
    setToken(tokenData.access_token);
    setUser(userData);
    scheduleProactiveRefresh();
  }, []);

  // Initialize auth state from localStorage (and the refresh cookie when the token has expired)
  useEffect(() => {
    const initializeAuth = async () => {
      const storedUser = localStorage.getItem('user');
      if (storedUser) {
        try {
          setUser(JSON.parse(storedUser));
          let stored = getAccessToken();
          const exp = getAccessTokenExpiry();
          if (!stored || (exp !== null && exp <= Date.now())) stored = await refreshAccessToken();
          setToken(stored);
          const me = await loadMe();
          setUser(me);
          localStorage.setItem('user', JSON.stringify(me));
          setToken(getAccessToken());
          scheduleProactiveRefresh();
        } catch (error) {
          console.error('Session could not be restored:', error);
          // Nothing is open yet at start-up: a clean sign-in page is the right outcome.
          performLogout();
        }
      }
      setIsLoading(false);
    };

    initializeAuth();
  }, [performLogout]);

  // Login function
  const login = async (
    username: string,
    password: string,
    captchaId?: string,
    captchaResponse?: string
  ): Promise<void> => {
    try {
      const payload: any = {
        username,
        password,
      };

      if (captchaId && captchaResponse) {
        payload.captcha_challenge_id = captchaId;
        payload.captcha_response = captchaResponse;
      }

      const response = await authClient.post(authUrl('/login'), payload);
      acceptSession(response.data);
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    }
  };

  // Login with Passkey (WebAuthn)
  const loginWithPasskey = async (username: string): Promise<void> => {
    acceptSession(await passkeyLogin(username));
  };

  // Register function
  const register = async (userData: RegisterData): Promise<void> => {
    try {
      await authClient.post(authUrl('/register'), userData);

      // Auto-login after registration
      await login(userData.username, userData.password);
    } catch (error) {
      console.error('Registration failed:', error);
      throw error;
    }
  };

  // Logout function (public API): the server revokes the refresh session and clears the cookie.
  const logout = useCallback((): void => {
    const current = getAccessToken();
    authClient.post(authUrl('/logout'), null, { headers: bearer(current) }).catch(() => undefined);
    abandonReauthentication();
    performLogout();
  }, [performLogout]);

  /** Accept a re-login only for the user whose work is on screen. */
  const finishReauthentication = useCallback(async (data: { token: Token; user: User }) => {
    const { token: tokenData, user: userData } = data;
    if (!user || !userData || userData.id !== user.id) {
      // Someone else signed in at this workstation: end THEIR new session at once (this also
      // clears their refresh cookie); the expired user's work stays on screen, unsaved.
      authClient.post(authUrl('/logout'), null, { headers: bearer(tokenData?.access_token) }).catch(() => undefined);
      throw new WrongUserError();
    }
    localStorage.setItem('user', JSON.stringify(userData));
    setUser(userData);
    completeReauthentication(tokenData.access_token, tokenData.expires_in);
    setToken(tokenData.access_token);
  }, [user]);

  const reauthenticate = useCallback(async (password: string, captcha?: CaptchaAnswer) => {
    if (!user) throw new WrongUserError();
    const payload: any = { username: user.username, password };
    if (captcha?.id && captcha.response) {
      payload.captcha_challenge_id = captcha.id;
      payload.captcha_response = captcha.response;
    }
    const response = await authClient.post(authUrl('/login'), payload);
    await finishReauthentication(response.data);
  }, [user, finishReauthentication]);

  const reauthenticateWithPasskey = useCallback(async () => {
    if (!user) throw new WrongUserError();
    await finishReauthentication(await passkeyLogin(user.username));
  }, [user, finishReauthentication]);

  // Refresh user data
  const refreshUser = useCallback(async (): Promise<void> => {
    if (!token) return;

    try {
      const me = await loadMe();
      setUser(me);
      localStorage.setItem('user', JSON.stringify(me));
    } catch (error) {
      console.error('Failed to refresh user:', error);
    }
  }, [token]);

  const value: AuthContextType = {
    user,
    token,
    isAuthenticated: !!user && !!token,
    isLoading,
    sessionExpired,
    login,
    loginWithPasskey,
    register,
    logout,
    refreshUser,
    reauthenticate,
    reauthenticateWithPasskey,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
