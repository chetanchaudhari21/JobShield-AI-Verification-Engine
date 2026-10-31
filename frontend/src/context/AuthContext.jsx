import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api, setAuthToken } from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchCurrentUser = useCallback(async () => {
    try {
      const profile = await api.getMe();
      if (profile && profile.id) {
        setUser(profile);
      } else {
        setUser(null);
      }
    } catch {
      setUser(null);
      setAuthToken(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Check if session is active via HttpOnly cookies or active token
    fetchCurrentUser();
  }, [fetchCurrentUser]);

  const login = async (email, password) => {
    const res = await api.login({ email, password });
    if (res && res.user) {
      setUser(res.user);
    } else {
      await fetchCurrentUser();
    }
    return res;
  };

  const register = async (email, password, fullName = '') => {
    return api.register({
      email,
      password,
      full_name: fullName,
    });
  };

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      // Ignore logout errors
    } finally {
      setUser(null);
      setAuthToken(null);
    }
  };

  const role = user?.role || 'VISITOR';
  const isAuthenticated = !!user;

  const value = {
    user,
    role,
    isAuthenticated,
    loading,
    login,
    register,
    logout,
    refreshProfile: fetchCurrentUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export default AuthContext;
