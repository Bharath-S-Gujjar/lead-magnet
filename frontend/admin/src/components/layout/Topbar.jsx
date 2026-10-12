import React from 'react';
import { useTheme } from '../../context/ThemeContext';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { NotificationBell } from './NotificationBell';
import { NavPillButton } from './NavPillButton';

export const Topbar = ({ searchQuery, setSearchQuery, onSelectCustomer }) => {
  const { theme, toggleTheme } = useTheme();
  const { admin, adminLogout } = useAdminAuth();

  const adminName = admin?.name || 'Administrator';
  const adminRole = admin?.role || 'Store Manager';

  return (
    <header className="navbar-container">
      {/* 1. Logo Branding matching main store */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
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
          fontSize: '0.95rem',
          boxShadow: '0 2px 8px rgba(156, 175, 136, 0.4)'
        }}>
          LM
        </div>
        <div>
          <h1 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.1 }}>
            Lead Magnet
          </h1>
          <span style={{ fontSize: '0.68rem', color: 'var(--color-primary-dark, #6f805e)', fontWeight: 700, letterSpacing: '0.04em' }}>
            CUSTOMER INTELLIGENCE
          </span>
        </div>
      </div>

      {/* 2. Search Customer Bar - Uiverse.io style */}
      <div className="navbar-search input-container" style={{ flex: 1, maxWidth: '440px' }}>
        <input
          type="text"
          className="input"
          placeholder="SEARCH CUSTOMERS, PSYCHOGRAPHICS..."
          value={searchQuery || ''}
          onChange={(e) => setSearchQuery && setSearchQuery(e.target.value)}
        />
        <svg className="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.3-4.3" />
        </svg>
      </div>

      {/* 3. Action Controls matching main navbar */}
      <div className="navbar-actions" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'nowrap' }}>
        {/* Back to Store Button */}
        <NavPillButton
          href="http://localhost:3001"
          variant="register"
          icon={
            <svg width="16" height="16" viewBox="0 0 24 24" fill="#9CAF88" style={{ display: 'block' }}>
              <path d="M20 4H4v2h16V4zm1 10v-2l-1-5H4l-1 5v2h1v6h10v-6h4v6h2v-6h1zm-9 4H6v-4h6v4z" />
            </svg>
          }
          label="Back to Store"
          title="Navigate to Clothing Store"
        />

        {/* Theme Toggle Button */}
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

        {/* Notification Bell */}
        <NotificationBell onSelectCustomer={onSelectCustomer} />

        {/* Admin Profile Box */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', paddingLeft: '8px', borderLeft: '1px solid var(--panel-border)' }}>
          <NavPillButton
            variant="account"
            avatar={`https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(adminName)}`}
            label={adminName.split(' ')[0]}
            title={`Logged in as ${adminName} (${adminRole})`}
          />
          <NavPillButton
            onClick={adminLogout}
            variant="logout"
            label="Logout"
            title="Log Out Admin"
          />
        </div>
      </div>
    </header>
  );
};

export default Topbar;
