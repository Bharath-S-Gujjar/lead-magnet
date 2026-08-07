import React, { useState } from 'react';
import { HashRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import { CartProvider } from './context/CartContext';
import { WishlistProvider } from './context/WishlistContext';
import { UserTrackingProvider } from './context/UserTrackingContext';

import { Navbar } from './components/Navbar';
import { UserDashboard } from './pages/UserDashboard';
import { ProductDetails } from './pages/ProductDetails';
import { Cart } from './pages/Cart';
import { Wishlist } from './pages/Wishlist';
import { Orders } from './pages/Orders';
import Login from './pages/Login';
import Signup from './pages/Signup';
import AdminDashboard from './pages/AdminDashboard';
import { Profile } from './pages/Profile';

function ProtectedAdminRoute({ children }) {
  const { isAdminAuthenticated } = useAuth();
  if (!isAdminAuthenticated) {
    return <Navigate to="/login?mode=admin" replace />;
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
                <div className="app-container">
                  <Navbar 
                    searchQuery={searchQuery}
                    setSearchQuery={setSearchQuery}
                    selectedGender={selectedGender}
                    setSelectedGender={setSelectedGender}
                  />

                  <main className="content-body">
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
                      <Route path="/orders" element={<Orders />} />
                      <Route path="/profile" element={<Profile />} />
                      <Route path="/account" element={<Profile />} />
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
