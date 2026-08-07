import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { DUMMY_ADMIN_ACCOUNTS } from '../data/adminCredentials';

const AdminAuthContext = createContext(null);
const ADMIN_STORAGE_KEY = 'lead_magnet_admin_session';

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

  const adminLogin = useCallback((email, password) => {
    if (!email || !password) {
      return { success: false, message: 'Please enter both admin email and password.' };
    }

    const normalizedEmail = email.trim().toLowerCase();
    const match = DUMMY_ADMIN_ACCOUNTS.find(
      (acc) => acc.email.toLowerCase() === normalizedEmail && acc.password === password
    );

    if (match) {
      setAdmin(match);
      localStorage.setItem(ADMIN_STORAGE_KEY, JSON.stringify(match));
      return { success: true, message: 'Welcome back, Administrator.', admin: match };
    }

    // Strictly enforce official admin credentials
    if (normalizedEmail === 'admin@leadmagnet.com' && password === 'admin123') {
      const defaultAdmin = {
        id: 'admin-1',
        email: 'admin@leadmagnet.com',
        name: 'Store Admin',
        role: 'Administrator',
        avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80',
      };
      setAdmin(defaultAdmin);
      localStorage.setItem(ADMIN_STORAGE_KEY, JSON.stringify(defaultAdmin));
      return { success: true, message: 'Welcome back, Administrator.', admin: defaultAdmin };
    }

    return { success: false, message: 'Invalid administrator email or password.' };
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
