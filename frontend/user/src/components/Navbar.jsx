import React from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { Shirt, Heart, ShoppingBag, Search, Moon, Sun, Package, Shield, LogOut, LogIn, UserPlus, User } from 'lucide-react';
import { useCart } from '../context/CartContext';
import { useWishlist } from '../context/WishlistContext';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { getCustomerSession } from '../services/api';

export const Navbar = ({ searchQuery, setSearchQuery, selectedGender, setSelectedGender }) => {
  const { totalItems } = useCart();
  const { totalWishlist } = useWishlist();
  const { theme, toggleTheme } = useTheme();
  const { customer: authCustomer, admin, logout, adminLogout, isCustomerAuthenticated, isAdminAuthenticated } = useAuth();
  const storedCustomer = getCustomerSession();
  const customer = authCustomer || storedCustomer;
  const isLoggedIn = Boolean(isCustomerAuthenticated || customer?.email || customer?.token);
  const navigate = useNavigate();
  const location = useLocation();

  if (location.pathname === '/admin') {
    return null;
  }

  const handleGenderClick = (gender) => {
    setSelectedGender && setSelectedGender(gender);
    if (location.pathname !== '/') {
      navigate('/');
    }
  };

  const handleLogout = () => {
    if (isCustomerAuthenticated) logout();
    if (isAdminAuthenticated) adminLogout();
    navigate('/login');
  };

  return (
    <header style={{
      position: 'sticky',
      top: 0,
      zIndex: 50,
      background: 'var(--panel-bg)',
      backdropFilter: 'var(--backdrop-blur)',
      borderBottom: '1px solid var(--panel-border)',
      padding: '16px 40px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '24px'
    }}>
      {/* 1. Lead Magnet Logo Branding */}
      <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        <div style={{
          width: '42px',
          height: '42px',
          borderRadius: '12px',
          background: 'linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          boxShadow: '0 4px 14px rgba(79, 70, 229, 0.3)'
        }}>
          <Shirt size={22} />
        </div>
        <div>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.35rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.02em', lineHeight: 1.1 }}>
            Lead Magnet
          </h1>
          <span style={{ fontSize: '0.78rem', color: 'var(--accent-indigo)', fontWeight: 700 }}>
            PREMIUM CLOTHING STORE
          </span>
        </div>
      </Link>

      {/* 2. Wider Search Bar */}
      <div style={{ flex: 1, maxWidth: '650px' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          background: 'var(--panel-solid)',
          border: '1px solid var(--panel-border)',
          padding: '10px 18px',
          borderRadius: 'var(--radius-full)',
          boxShadow: '0 2px 6px rgba(0,0,0,0.02)'
        }}>
          <Search size={18} style={{ color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Search shirts, hoodies, dresses, Levi's, Zara..."
            value={searchQuery || ''}
            onChange={(e) => setSearchQuery && setSearchQuery(e.target.value)}
            style={{
              border: 'none',
              background: 'transparent',
              outline: 'none',
              width: '100%',
              fontSize: '0.88rem',
              color: 'var(--text-primary)'
            }}
          />
        </div>
      </div>

      {/* 3. Action Controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        {/* Wishlist Link */}
        <Link
          to="/wishlist"
          className="btn btn-secondary"
          style={{ padding: '9px 14px', borderRadius: 'var(--radius-full)', position: 'relative' }}
          title="Wishlist"
        >
          <Heart size={18} style={{ color: 'var(--accent-rose)' }} />
          <span style={{ fontSize: '0.85rem' }}>Wishlist</span>
          {totalWishlist > 0 && (
            <span style={{
              background: 'var(--accent-rose)',
              color: 'white',
              fontSize: '0.7rem',
              fontWeight: 800,
              padding: '2px 6px',
              borderRadius: 'var(--radius-full)'
            }}>
              {totalWishlist}
            </span>
          )}
        </Link>

        {/* Shopping Cart Link */}
        <Link
          to="/cart"
          // className="btn btn-primary" 
          className="btn btn-secondary"
          style={{ padding: '9px 16px', borderRadius: 'var(--radius-full)', position: 'relative' }}
          title="Shopping Cart"
        >
          <ShoppingBag size={18} />
          <span style={{ fontSize: '0.85rem' }}>Cart</span>
          {totalItems > 0 && (
            <span style={{
              background: 'white',
              color: 'var(--accent-indigo)',
              fontSize: '0.7rem',
              fontWeight: 800,
              padding: '2px 6px',
              borderRadius: 'var(--radius-full)'
            }}>
              {totalItems}
            </span>
          )}
        </Link>

        {/* Orders Link */}
        <Link
          to="/orders"
          className="btn btn-secondary"
          style={{ padding: '9px 14px', borderRadius: 'var(--radius-full)' }}
          title="My Orders"
        >
          <Package size={18} style={{ color: 'var(--accent-indigo)' }} />
          <span style={{ fontSize: '0.85rem' }}>Orders</span>
        </Link>

        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          className="btn btn-ghost"
          style={{ padding: '9px', borderRadius: '50%' }}
          title="Toggle Theme"
        >
          {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
        </button>

        {/* Auth / Profile Area */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', paddingLeft: '8px', borderLeft: '1px solid var(--panel-border)' }}>
          {isLoggedIn ? (
            <>
              <Link
                to="/account"
                style={{
                  display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 14px',
                  borderRadius: 'var(--radius-full)', background: 'rgba(79, 70, 229, 0.1)',
                  border: '1px solid var(--accent-indigo)', transition: 'transform 0.15s ease'
                }}
                title="View Profile & Settings"
              >
                <img
                  src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(customer?.email || 'customer')}`}
                  alt="Customer Avatar"
                  style={{ width: '28px', height: '28px', borderRadius: '50%', background: '#e2e8f0', border: '2px solid var(--accent-indigo)' }}
                />
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {customer?.full_name ? customer.full_name.split(' ')[0] : customer?.username || 'Account'}
                </span>
              </Link>
              <button onClick={handleLogout} className="btn btn-ghost" style={{ padding: '6px 10px', color: 'var(--accent-rose)', fontSize: '0.82rem', gap: '4px' }} title="Logout">
                <LogOut size={16} />
                <span>Logout</span>
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="btn btn-ghost" style={{ padding: '7px 12px', fontSize: '0.84rem', gap: '6px' }} title="Account Settings">
                <User size={16} />
                <span>Account</span>
              </Link>
              <Link to="/login" className="btn btn-ghost" style={{ padding: '7px 14px', fontSize: '0.84rem', gap: '6px' }}>
                <LogIn size={16} />
                <span>Login</span>
              </Link>
              <Link to="/signup" className="btn btn-primary" style={{ padding: '7px 16px', fontSize: '0.84rem', borderRadius: 'var(--radius-full)', gap: '6px' }}>
                <UserPlus size={16} />
                <span>Register</span>
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
};
