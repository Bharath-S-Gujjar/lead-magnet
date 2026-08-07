import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { adminCredentials } from '../data/adminCredentials';
import { ADMIN_SESSION_KEY, CUSTOMER_SESSION_KEY, CUSTOMER_USERS_KEY, readStorage, removeStorage, writeStorage } from '../utils/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [customer, setCustomer] = useState(() => readStorage(CUSTOMER_SESSION_KEY, null));
  const [customers, setCustomers] = useState(() => readStorage(CUSTOMER_USERS_KEY, []));
  const [admin, setAdmin] = useState(() => readStorage(ADMIN_SESSION_KEY, null));

  useEffect(() => {
    if (customer) {
      writeStorage(CUSTOMER_SESSION_KEY, customer);
    } else {
      removeStorage(CUSTOMER_SESSION_KEY);
    }
  }, [customer]);

  useEffect(() => {
    if (admin) {
      writeStorage(ADMIN_SESSION_KEY, admin);
    } else {
      removeStorage(ADMIN_SESSION_KEY);
    }
  }, [admin]);

  const signup = useCallback((profile) => {
    const normalizedEmail = (profile.email || '').trim().toLowerCase();
    const rawUsername = profile.username || profile.fullName || '';
    const username = rawUsername.trim().toLowerCase().replace(/\s+/g, '');
    const phone = (profile.phone || '').trim();

    // Check if user already exists in current state or fresh storage
    const currentList = customers.length > 0 ? customers : readStorage(CUSTOMER_USERS_KEY, []);
    const existingUser = currentList.some((entry) => {
      const sameEmail = entry.email && entry.email.toLowerCase() === normalizedEmail;
      const sameUser = entry.username && entry.username.toLowerCase() === username;
      const samePhone = phone && entry.phone && entry.phone === phone;
      return sameEmail || sameUser || samePhone;
    });

    if (existingUser) {
      return { success: false, message: 'An account with this email, username, or phone number already exists.' };
    }

    const nextUser = {
      id: typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `usr-${Date.now()}`,
      ...profile,
      username,
      email: normalizedEmail,
      createdAt: new Date().toISOString(),
    };

    const nextCustomers = [nextUser, ...currentList];
    setCustomers(nextCustomers);
    writeStorage(CUSTOMER_USERS_KEY, nextCustomers);
    return { success: true, message: 'Account created successfully.', user: nextUser };
  }, [customers]);

  const login = useCallback((identifier, password) => {
    if (!identifier || !password) {
      return { success: false, message: 'Please enter both credentials.' };
    }

    const normalizedIdentifier = identifier.trim().toLowerCase();
    const currentList = customers.length > 0 ? customers : readStorage(CUSTOMER_USERS_KEY, []);

    const matchingUser = currentList.find((entry) => {
      const sameEmail = entry.email?.toLowerCase() === normalizedIdentifier;
      const sameUsername = (entry.username || '').toLowerCase() === normalizedIdentifier;
      const sameFullName = (entry.fullName || '').toLowerCase() === normalizedIdentifier;
      const samePhone = (entry.phone || '').toLowerCase() === normalizedIdentifier;
      return (sameEmail || sameUsername || sameFullName || samePhone) && entry.password === password;
    });

    if (!matchingUser) {
      return { success: false, message: 'Invalid Email or Password' };
    }

    setCustomer(matchingUser);
    writeStorage(CUSTOMER_SESSION_KEY, matchingUser);
    return { success: true, message: 'Signed in successfully.', user: matchingUser };
  }, [customers]);

  const adminLogin = useCallback((name, password) => {
    if (!name || !password) {
      return { success: false, message: 'Please enter administrator name and password.' };
    }

    const match = adminCredentials.find(
      (entry) => entry.name.toLowerCase() === name.trim().toLowerCase() && entry.password === password
    );

    if (!match) {
      return { success: false, message: 'Invalid Administrator Credentials' };
    }

    setAdmin(match);
    writeStorage(ADMIN_SESSION_KEY, match);
    return { success: true, message: 'Administrator access granted.', admin: match };
  }, []);

  const logout = useCallback(() => {
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
    isAdminAuthenticated: Boolean(admin),
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
