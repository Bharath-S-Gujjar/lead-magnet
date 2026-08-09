import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { ADMIN_SESSION_KEY, CUSTOMER_SESSION_KEY, CUSTOMER_USERS_KEY, readStorage, removeStorage, writeStorage } from '../utils/auth';
import { API_BASE_URL, endCustomerSession, getAdminSession, parseJsonResponse, saveCustomerSession, startCustomerSession } from '../services/api';

const AuthContext = createContext(null);

export function isSessionExpired(session) {
  if (!session) return true;
  if (session.loggedInAt) {
    const loggedInTime = new Date(session.loggedInAt).getTime();
    if (!isNaN(loggedInTime)) {
      return Date.now() >= loggedInTime + 3600 * 1000;
    }
  }
  if (session.expires_at_timestamp && typeof session.expires_at_timestamp === 'number') {
    return Date.now() >= session.expires_at_timestamp;
  }
  return false;
}

export function AuthProvider({ children }) {
  const [customer, setCustomer] = useState(() => {
    const session = readStorage(CUSTOMER_SESSION_KEY, null);
    if (session) {
      if (isSessionExpired(session)) {
        removeStorage(CUSTOMER_SESSION_KEY);
        return null;
      }
      return session;
    }
    return null;
  });

  const [customers, setCustomers] = useState(() => readStorage(CUSTOMER_USERS_KEY, []));

  const [admin, setAdmin] = useState(() => {
    const session = readStorage(ADMIN_SESSION_KEY, null);
    if (session) {
      if (isSessionExpired(session)) {
        removeStorage(ADMIN_SESSION_KEY);
        return null;
      }
      return session?.token ? session : null;
    }
    return null;
  });

  const logout = useCallback(() => {
    endCustomerSession();
    setCustomer(null);
    removeStorage(CUSTOMER_SESSION_KEY);
  }, []);

  const adminLogout = useCallback(() => {
    setAdmin(null);
    removeStorage(ADMIN_SESSION_KEY);
  }, []);

  useEffect(() => {
    const checkExpiry = () => {
      if (customer && isSessionExpired(customer)) {
        logout();
      }
      if (admin && isSessionExpired(admin)) {
        adminLogout();
      }
    };

    checkExpiry();
    const interval = setInterval(checkExpiry, 60000);
    return () => clearInterval(interval);
  }, [customer, admin, logout, adminLogout]);

  useEffect(() => {
    if (customer) {
      writeStorage(CUSTOMER_SESSION_KEY, customer);
    }
  }, [customer]);

  useEffect(() => {
    if (admin?.token) {
      writeStorage(ADMIN_SESSION_KEY, admin);
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

      const expiresAtTimestamp = payload.data.expires_at_timestamp || (Date.now() + 3600 * 1000);
      const expiresAt = payload.data.expires_at || new Date(expiresAtTimestamp).toISOString();

      const customerSession = {
        email: payload.data.email,
        role: payload.data.role || 'user',
        token: payload.data.token,
        user_id: payload.data.user_id,
        expires_at: expiresAt,
        expires_at_timestamp: expiresAtTimestamp,
        full_name: payload.data.full_name,
        username: payload.data.username,
        phone: payload.data.phone,
        gender: payload.data.gender,
        age: payload.data.age,
        dob: payload.data.dob,
        loggedInAt: new Date().toISOString(),
      };

      try {
        const sessionData = await startCustomerSession(customerSession);
        customerSession.session_id = sessionData.session_id;
        customerSession.visitor_id = sessionData.visitor_id;
        customerSession.anonymous_id = sessionData.anonymous_id;
      } catch (err) {
        // Non-blocking session tracking fallback
      }

      setCustomer(customerSession);
      writeStorage(CUSTOMER_SESSION_KEY, customerSession);
      saveCustomerSession(customerSession);
      return { success: true, message: 'Signed in successfully.', user: customerSession };
    } catch (error) {
      return { success: false, message: 'Unable to connect to login service.' };
    }
  }, []);

  const adminLogin = useCallback(async (name, password) => {
    if (!name || !password) {
      return { success: false, message: 'Please enter administrator username and password.' };
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

      const expiresAtTimestamp = payload.data.expires_at_timestamp || (Date.now() + 3600 * 1000);
      const expiresAt = payload.data.expires_at || new Date(expiresAtTimestamp).toISOString();

      const adminSession = {
        token: payload.data.token,
        role: payload.data.role || 'admin',
        username: name.trim(),
        expires_at: expiresAt,
        expires_at_timestamp: expiresAtTimestamp,
        loggedInAt: new Date().toISOString()
      };

      setAdmin(adminSession);
      writeStorage(ADMIN_SESSION_KEY, adminSession);
      return { success: true, message: 'Administrator access granted.', admin: adminSession };
    } catch (error) {
      return { success: false, message: 'Unable to connect to admin login service.' };
    }
  }, []);

  const updateProfile = useCallback((updatedFields) => {
    if (!customer) return { success: false, message: 'No active user session found.' };

    const updatedUser = {
      ...customer,
      ...updatedFields,
    };

    setCustomer(updatedUser);
    writeStorage(CUSTOMER_SESSION_KEY, updatedUser);

    const rawList = customers && customers.length > 0 ? customers : readStorage(CUSTOMER_USERS_KEY, []);
    const currentList = Array.isArray(rawList) ? rawList : [];
    const nextCustomers = currentList.map((c) => (c && (c.id === customer.id || c.email === customer.email)) ? updatedUser : c);
    setCustomers(nextCustomers);
    writeStorage(CUSTOMER_USERS_KEY, nextCustomers);

    return { success: true, message: 'Profile updated successfully!', user: updatedUser };
  }, [customer, customers]);

  const isCustomerAuth = Boolean(customer && (customer.token || customer.email) && !isSessionExpired(customer));
  const isAdminAuth = Boolean(admin && admin.token && !isSessionExpired(admin));

  const value = useMemo(() => ({
    customer: isCustomerAuth ? customer : null,
    customers: Array.isArray(customers) ? customers : [],
    admin: isAdminAuth ? admin : null,
    isCustomerAuthenticated: isCustomerAuth,
    isAuthenticated: isCustomerAuth,
    isAdminAuthenticated: isAdminAuth,
    signup,
    login,
    adminLogin,
    logout,
    adminLogout,
    updateProfile,
  }), [admin, adminLogin, adminLogout, customer, customers, isCustomerAuth, isAdminAuth, login, logout, signup, updateProfile]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
