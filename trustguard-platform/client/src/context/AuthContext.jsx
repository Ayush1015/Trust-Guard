import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

const AuthContext = createContext(null);

const API_BASE_URL = (
  import.meta.env.VITE_API_URL ||
  'http://localhost:5000/api/v1'
).replace(/\/+$/, '');

const STORAGE_KEY = 'trustguard_auth_token';

async function apiCall(endpoint, { method = 'GET', body, token } = {}) {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(data?.error?.message || `Request failed (${res.status}).`);
  }
  return data;
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEY) || '');
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refreshMe = useCallback(async (activeToken) => {
    if (!activeToken) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const data = await apiCall('/auth/me', { token: activeToken });
      setUser(data.user);
    } catch {
      // Token expired/invalid — drop it silently and fall back to guest mode.
      localStorage.removeItem(STORAGE_KEY);
      setToken('');
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshMe(token);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const signup = useCallback(async (email, password) => {
    setError('');
    const data = await apiCall('/auth/signup', { method: 'POST', body: { email, password } });
    localStorage.setItem(STORAGE_KEY, data.token);
    setToken(data.token);
    setUser(data.user);
    return data.user;
  }, []);

  const login = useCallback(async (email, password) => {
    setError('');
    const data = await apiCall('/auth/login', { method: 'POST', body: { email, password } });
    localStorage.setItem(STORAGE_KEY, data.token);
    setToken(data.token);
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setToken('');
    setUser(null);
  }, []);

  const updatePreferences = useCallback(
    async (prefs) => {
      if (!token) return;
      await apiCall('/auth/preferences', { method: 'PATCH', body: prefs, token });
      await refreshMe(token);
    },
    [token, refreshMe]
  );

  const fetchHistory = useCallback(async () => {
    if (!token) return [];
    const data = await apiCall('/auth/history', { token });
    return data.history || [];
  }, [token]);

  const value = useMemo(
    () => ({
      token,
      user,
      isAuthenticated: Boolean(user),
      loading,
      error,
      signup,
      login,
      logout,
      updatePreferences,
      fetchHistory,
    }),
    [token, user, loading, error, signup, login, logout, updatePreferences, fetchHistory]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
