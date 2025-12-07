import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const API_V1_URL = `${API_URL}/api/v1`;

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

// Auth context type
interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string, captchaId?: string, captchaResponse?: string) => Promise<void>;
  register: (userData: RegisterData) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
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

// Auth Provider Component
interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Initialize auth state from localStorage
  useEffect(() => {
    const initializeAuth = async () => {
      const storedToken = localStorage.getItem('access_token');
      const storedUser = localStorage.getItem('user');

      if (storedToken && storedUser) {
        try {
          setToken(storedToken);
          setUser(JSON.parse(storedUser));

          // Configure axios defaults
          axios.defaults.headers.common['Authorization'] = `Bearer ${storedToken}`;

          // Verify token is still valid by fetching current user
          const response = await axios.get(`${API_V1_URL}/auth/me`);
          setUser(response.data);
          localStorage.setItem('user', JSON.stringify(response.data));
        } catch (error) {
          console.error('Token validation failed:', error);
          // Clear invalid token
          localStorage.removeItem('access_token');
          localStorage.removeItem('user');
          setToken(null);
          setUser(null);
          delete axios.defaults.headers.common['Authorization'];
        }
      }

      setIsLoading(false);
    };

    initializeAuth();
  }, []);

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

      const response = await axios.post(`${API_V1_URL}/auth/login`, payload);

      const { token: tokenData, user: userData } = response.data;

      // Store token and user
      localStorage.setItem('access_token', tokenData.access_token);
      localStorage.setItem('user', JSON.stringify(userData));

      setToken(tokenData.access_token);
      setUser(userData);

      // Configure axios for future requests
      axios.defaults.headers.common['Authorization'] = `Bearer ${tokenData.access_token}`;
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    }
  };

  // Register function
  const register = async (userData: RegisterData): Promise<void> => {
    try {
      const response = await axios.post(`${API_V1_URL}/auth/register`, userData);

      // Auto-login after registration
      await login(userData.username, userData.password);
    } catch (error) {
      console.error('Registration failed:', error);
      throw error;
    }
  };

  // Logout function
  const logout = (): void => {
    // Clear storage
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');

    // Clear state
    setToken(null);
    setUser(null);

    // Clear axios default authorization
    delete axios.defaults.headers.common['Authorization'];
  };

  // Refresh user data
  const refreshUser = async (): Promise<void> => {
    if (!token) return;

    try {
      const response = await axios.get(`${API_V1_URL}/auth/me`);
      setUser(response.data);
      localStorage.setItem('user', JSON.stringify(response.data));
    } catch (error) {
      console.error('Failed to refresh user:', error);
      // If refresh fails, logout
      logout();
    }
  };

  const value: AuthContextType = {
    user,
    token,
    isAuthenticated: !!user && !!token,
    isLoading,
    login,
    register,
    logout,
    refreshUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
