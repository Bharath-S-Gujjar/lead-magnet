import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';

const AdminAuthContext = createContext(null);
const ADMIN_STORAGE_KEY = 'lead_magnet_admin_session';
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000').replace(/\/$/, '');

export function AdminAuthProvider({ children }) {
  const [admin, setAdmin] = useState(() => {
    try {
      const stored = localStorage.getItem(ADMIN_STORAGE_KEY);
      return stored ? JSON.parse(stored) : null;
    } catch (e) {
      return null;
    }
  });

  useEffect(() => {
    if (admin) {
      localStorage.setItem(ADMIN_STORAGE_KEY, JSON.stringify(admin));
    } else {
      localStorage.removeItem(ADMIN_STORAGE_KEY);
    }
  }, [admin]);

  const adminLogin = useCallback(async (username, password) => {
    if (!username || !password) {
      return { success: false, message: 'Please enter both admin username and password.' };
    }

    const inputVal = username.trim();

    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/admin/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: inputVal,
          password,
        }),
      });
      const data = await res.json();
      if (res.ok && data.success && data.data?.token) {
        const adminSession = {
          id: 'admin-live',
          username: inputVal,
          token: data.data.token,
          role: 'admin',
          avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80',
        };
        setAdmin(adminSession);
        localStorage.setItem(ADMIN_STORAGE_KEY, JSON.stringify(adminSession));
        return { success: true, message: 'Welcome back, Administrator.', admin: adminSession };
      }
      return { success: false, message: data.message || 'Invalid administrator credentials.' };
    } catch (err) {
      return { success: false, message: 'Unable to connect to admin login service.' };
    }
  }, []);

  const adminLogout = useCallback(() => {
    setAdmin(null);
    localStorage.removeItem(ADMIN_STORAGE_KEY);
  }, []);

  const value = useMemo(() => ({
    admin,
    isAdminAuthenticated: Boolean(admin),
    adminLogin,
    adminLogout,
  }), [admin, adminLogin, adminLogout]);

  return <AdminAuthContext.Provider value={value}>{children}</AdminAuthContext.Provider>;
}

export function useAdminAuth() {
  const context = useContext(AdminAuthContext);
  if (!context) {
    throw new Error('useAdminAuth must be used within an AdminAuthProvider');
  }
  return context;
}
