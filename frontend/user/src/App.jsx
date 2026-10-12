import React, { useState } from 'react';
import { HashRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import { CartProvider } from './context/CartContext';
import { WishlistProvider } from './context/WishlistContext';
import { UserTrackingProvider } from './context/UserTrackingContext';

import { Navbar } from './components/Navbar';
import ParticleDrift from './components/ParticleDrift';
import { UserDashboard } from './pages/UserDashboard';
import { ProductDetails } from './pages/ProductDetails';
import { Cart } from './pages/Cart';
import { Wishlist } from './pages/Wishlist';
import { Orders } from './pages/Orders';
import Login from './pages/Login';
import Signup from './pages/Signup';
import AdminDashboard from './pages/AdminDashboard';
import { Profile } from './pages/Profile';
import { Account } from './pages/Account';

import { getAdminSession, getCustomerSession } from './services/api';

function ProtectedAdminRoute({ children }) {
  const { isAdminAuthenticated, admin } = useAuth();
  const storedAdmin = getAdminSession();
  const hasToken = Boolean(isAdminAuthenticated || admin?.token || storedAdmin?.token);
  if (!hasToken) {
    return <Navigate to="/login?mode=admin" replace />;
  }
  return children;
}

function ProtectedCustomerRoute({ children }) {
  const { isCustomerAuthenticated, isAuthenticated, customer } = useAuth();
  const storedCustomer = getCustomerSession();
  const hasToken = Boolean(isCustomerAuthenticated || isAuthenticated || customer?.token || customer?.email || storedCustomer?.token || storedCustomer?.email);
  if (!hasToken) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export function App() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedGender, setSelectedGender] = useState('all');

  return (
    <ThemeProvider>
      <AuthProvider>
        <CartProvider>
          <WishlistProvider>
            <UserTrackingProvider>
              <Router>
                <div className="app-container" style={{ position: 'relative', minHeight: '100vh' }}>
                  {/* Global Animated Particle Drift Background */}
                  <div
                    className="particle-drift-background-container"
                    style={{
                      position: 'fixed',
                      top: 0,
                      left: 0,
                      width: '100vw',
                      height: '100vh',
                      zIndex: 0,
                      pointerEvents: 'none',
                      overflow: 'hidden'
                    }}
                  >
                    <ParticleDrift
                      background="transparent"
                      baseColor="#A7A7A7"
                      accentColor="#CC5500"
                      density={120}
                      dotSize={3.5}
                      speed={20}
                      hover={200}
                    />
                  </div>

                  <Navbar 
                    searchQuery={searchQuery}
                    setSearchQuery={setSearchQuery}
                    selectedGender={selectedGender}
                    setSelectedGender={setSelectedGender}
                  />

                  <main className="content-body" style={{ position: 'relative', zIndex: 1 }}>
                    <Routes>
                      <Route 
                        path="/" 
                        element={
                          <UserDashboard 
                            searchQuery={searchQuery}
                            selectedGender={selectedGender}
                            setSelectedGender={setSelectedGender}
                          />
                        } 
                      />
                      <Route 
                        path="/dashboard" 
                        element={
                          <UserDashboard 
                            searchQuery={searchQuery}
                            selectedGender={selectedGender}
                            setSelectedGender={setSelectedGender}
                          />
                        } 
                      />
                      <Route path="/login" element={<Login />} />
                      <Route path="/signup" element={<Signup />} />
                      <Route 
                        path="/admin" 
                        element={
                          <ProtectedAdminRoute>
                            <AdminDashboard />
                          </ProtectedAdminRoute>
                        } 
                      />
                      <Route path="/product/:id" element={<ProductDetails />} />
                      <Route path="/cart" element={<Cart />} />
                      <Route path="/wishlist" element={<Wishlist />} />
                      <Route 
                        path="/orders" 
                        element={
                          <ProtectedCustomerRoute>
                            <Orders />
                          </ProtectedCustomerRoute>
                        } 
                      />
                      <Route 
                        path="/profile" 
                        element={
                          <ProtectedCustomerRoute>
                            <Profile />
                          </ProtectedCustomerRoute>
                        } 
                      />
                      <Route 
                        path="/account" 
                        element={
                          <ProtectedCustomerRoute>
                            <Account />
                          </ProtectedCustomerRoute>
                        } 
                      />
                    </Routes>
                  </main>
                </div>
              </Router>
            </UserTrackingProvider>
          </WishlistProvider>
        </CartProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
