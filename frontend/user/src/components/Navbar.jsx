import React from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import { useWishlist } from '../context/WishlistContext';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { getCustomerSession } from '../services/api';
import { UserLoginButton } from './UserLoginButton';
import { NavPillButton } from './NavPillButton';

export const Navbar = ({ searchQuery, setSearchQuery, selectedGender, setSelectedGender }) => {
  const { totalItems } = useCart();
  const { totalWishlist } = useWishlist();
  const { theme, toggleTheme } = useTheme();
  const { customer: authCustomer, logout, adminLogout, isCustomerAuthenticated, isAdminAuthenticated } = useAuth();
  const storedCustomer = getCustomerSession();
  const customer = authCustomer || storedCustomer;
  const isLoggedIn = Boolean(isCustomerAuthenticated || customer?.email || customer?.token);
  const navigate = useNavigate();
  const location = useLocation();

  if (location.pathname === '/admin') {
    return null;
  }

  const handleLogout = () => {
    if (isCustomerAuthenticated) logout();
    if (isAdminAuthenticated) adminLogout();
    navigate('/login');
  };

  return (
    <header className="navbar-container" style={{
      position: 'sticky',
      top: 0,
      zIndex: 50,
      background: 'var(--panel-solid, #ffffff)',
      borderBottom: '1px solid var(--panel-border)',
      padding: '10px 24px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '14px'
    }}>
      {/* 1. Logo Branding */}
      <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
        <div style={{
          width: '34px',
          height: '34px',
          borderRadius: '6px',
          background: 'var(--color-primary, #9CAF88)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#1a2016',
          fontWeight: 800,
          fontSize: '0.95rem'
        }}>
          LM
        </div>
        <div>
          <h1 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.1 }}>
            Lead Magnet
          </h1>
          <span style={{ fontSize: '0.68rem', color: 'var(--color-primary-dark, #6f805e)', fontWeight: 600 }}>
            CLOTHING STORE
          </span>
        </div>
      </Link>

      {/* 2. Search Bar - Uiverse.io by boryanakrasteva */}
      <div className="navbar-search input-container" style={{ flex: 1, maxWidth: '460px' }}>
        <input
          type="text"
          className="input"
          placeholder="SEARCH CLOTHING..."
          value={searchQuery || ''}
          onChange={(e) => setSearchQuery && setSearchQuery(e.target.value)}
        />
        <svg className="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.3-4.3" />
        </svg>
      </div>

      {/* 3. Action Controls */}
      <div className="navbar-actions" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'nowrap' }}>
        {/* Wishlist Link */}
        <NavPillButton
          to="/wishlist"
          variant="wishlist"
          icon={
            <svg width="16" height="16" viewBox="0 0 24 24" fill="#CC5500" style={{ display: 'block' }}>
              <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
            </svg>
          }
          label="Wishlist"
          badge={totalWishlist}
          title="Wishlist"
        />

        {/* Shopping Cart Link */}
        <NavPillButton
          to="/cart"
          variant="cart"
          icon={
            <img
              width="16"
              height="16"
              src="https://img.icons8.com/material-outlined/24/shopping-cart--v1.png"
              alt="Cart"
            />
          }
          label="Cart"
          badge={totalItems}
          title="Shopping Cart"
        />

        {/* Orders Link */}
        <NavPillButton
          to="/orders"
          variant="orders"
          icon={
            <img
              width="16"
              height="16"
              src="https://img.icons8.com/material-outlined/24/box--v1.png"
              alt="Orders"
            />
          }
          label="Orders"
          title="My Orders"
        />

        {/* Dark Mode Toggle */}
        <NavPillButton
          onClick={toggleTheme}
          variant="theme"
          icon={
            <span style={{ fontSize: '15px', lineHeight: 1 }}>
              {theme === 'light' ? '☾' : '☼'}
            </span>
          }
          title="Toggle Dark Mode"
          ariaLabel="Toggle Dark Mode"
        />

        {/* Auth Area */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', paddingLeft: '4px', borderLeft: '1px solid var(--panel-border)' }}>
          {isLoggedIn ? (
            <>
              <NavPillButton
                to="/account"
                variant="account"
                avatar={`https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(customer?.email || 'customer')}`}
                label={customer?.full_name ? customer.full_name.split(' ')[0] : customer?.username || 'Account'}
                title="View Profile & Settings"
              />
              <NavPillButton
                onClick={handleLogout}
                variant="logout"
                label="Logout"
                title="Logout"
              />
            </>
          ) : (
            <>
              <UserLoginButton to="/login" label="Log In" />
              <NavPillButton
                to="/signup"
                variant="register"
                icon={
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="#9CAF88" style={{ display: 'block' }}>
                    <path d="M15 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm-9-2V7H4v3H1v2h3v3h2v-3h3v-2H6zm9 4c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                  </svg>
                }
                label="Register"
                title="Create an Account"
              />
            </>
          )}
        </div>
      </div>
    </header>
  );
};

export default Navbar;
