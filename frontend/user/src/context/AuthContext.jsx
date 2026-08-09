import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { ADMIN_SESSION_KEY, CUSTOMER_SESSION_KEY, CUSTOMER_USERS_KEY, readStorage, removeStorage, writeStorage } from '../utils/auth';
import { API_BASE_URL, endCustomerSession, getAdminSession, parseJsonResponse, saveCustomerSession, startCustomerSession } from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [customer, setCustomer] = useState(() => readStorage(CUSTOMER_SESSION_KEY, null));
  const [customers, setCustomers] = useState(() => readStorage(CUSTOMER_USERS_KEY, []));
  const [admin, setAdmin] = useState(() => {
    const session = getAdminSession();
    return session?.token && session?.role === 'admin' ? session : null;
  });

  useEffect(() => {
    if (customer) {
      writeStorage(CUSTOMER_SESSION_KEY, customer);
    } else {
      removeStorage(CUSTOMER_SESSION_KEY);
    }
  }, [customer]);

  useEffect(() => {
    if (admin?.token && admin?.role === 'admin') {
      writeStorage(ADMIN_SESSION_KEY, admin);
    } else {
      removeStorage(ADMIN_SESSION_KEY);
    }
  }, [admin]);

  const signup = useCallback((profile) => {
    return fetch(`${API_BASE_URL}/api/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    })
      .then((response) => parseJsonResponse(response).then((payload) => ({ response, payload })))
      .then(({ response, payload }) => {
        if (!response.ok || !payload.success) {
          return { success: false, message: payload.message || 'Unable to create account.' };
        }
        return { success: true, message: payload.message, user: payload.data };
      })
      .catch(() => ({ success: false, message: 'Unable to connect to signup service.' }));
  }, []);

  const login = useCallback(async (identifier, password) => {
    if (!identifier || !password) {
      return { success: false, message: 'Please enter both credentials.' };
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: identifier.trim(),
          password,
        }),
      });
      const payload = await parseJsonResponse(response);

      if (!response.ok || !payload.success) {
        return { success: false, message: payload.message || 'Invalid Email or Password' };
      }

      const customerSession = {
        email: payload.data.email,
        role: payload.data.role,
        token: payload.data.token,
        user_id: payload.data.user_id,
      };
      const sessionData = await startCustomerSession(customerSession);
      customerSession.session_id = sessionData.session_id;
      customerSession.visitor_id = sessionData.visitor_id;
      customerSession.anonymous_id = sessionData.anonymous_id;

      setCustomer(customerSession);
      saveCustomerSession(customerSession);
      return { success: true, message: 'Signed in successfully.', user: customerSession };
    } catch (error) {
      return { success: false, message: 'Unable to connect to login service.' };
    }
  }, []);

  const adminLogin = useCallback(async (name, password) => {
    if (!name || !password) {
      return { success: false, message: 'Please enter administrator name and password.' };
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/admin/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: name.trim(),
          password,
        }),
      });
      const payload = await parseJsonResponse(response);

      if (!response.ok || !payload.success) {
        return { success: false, message: payload.message || 'Invalid Administrator Credentials' };
      }

      const adminSession = {
        token: payload.data.token,
        role: payload.data.role,
        username: name.trim(),
        loggedInAt: new Date().toISOString()
      };

      setAdmin(adminSession);
      localStorage.setItem(ADMIN_SESSION_KEY, JSON.stringify(adminSession));
      return { success: true, message: 'Administrator access granted.', admin: adminSession };
    } catch (error) {
      return { success: false, message: 'Unable to connect to admin login service.' };
    }
  }, []);

  const logout = useCallback(() => {
    endCustomerSession();
    setCustomer(null);
    removeStorage(CUSTOMER_SESSION_KEY);
  }, []);

  const adminLogout = useCallback(() => {
    setAdmin(null);
    removeStorage(ADMIN_SESSION_KEY);
  }, []);

  const updateProfile = useCallback((updatedFields) => {
    if (!customer) return { success: false, message: 'No active user session found.' };

    const updatedUser = {
      ...customer,
      ...updatedFields,
    };

    setCustomer(updatedUser);
    writeStorage(CUSTOMER_SESSION_KEY, updatedUser);

    // Update in customers array list as well
    const rawList = customers && customers.length > 0 ? customers : readStorage(CUSTOMER_USERS_KEY, []);
    const currentList = Array.isArray(rawList) ? rawList : [];
    const nextCustomers = currentList.map((c) => (c && (c.id === customer.id || c.email === customer.email)) ? updatedUser : c);
    setCustomers(nextCustomers);
    writeStorage(CUSTOMER_USERS_KEY, nextCustomers);

    return { success: true, message: 'Profile updated successfully!', user: updatedUser };
  }, [customer, customers]);

  const value = useMemo(() => ({
    customer,
    customers: Array.isArray(customers) ? customers : [],
    admin,
    isCustomerAuthenticated: Boolean(customer),
    isAdminAuthenticated: Boolean(admin?.token && admin?.role === 'admin'),
    signup,
    login,
    adminLogin,
    logout,
    adminLogout,
    updateProfile,
  }), [admin, adminLogin, adminLogout, customer, customers, login, logout, signup, updateProfile]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
