import React from 'react';
import { Search, Bell, Shirt, Sun, Moon, LogOut, Store } from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';
import { useAdminAuth } from '../../context/AdminAuthContext';

export const Topbar = ({ searchQuery, setSearchQuery }) => {
  const { theme, toggleTheme } = useTheme();
  const { admin, adminLogout } = useAdminAuth();

  const adminName = admin?.name || 'Administrator';
  const adminRole = admin?.role || 'Store Admin';
  const adminAvatar = admin?.avatar || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80';

  return (
    <header style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '20px 40px',
      background: 'var(--panel-bg)',
      backdropFilter: 'var(--backdrop-blur)',
      borderBottom: '1px solid var(--panel-border)',
      position: 'sticky',
      top: 0,
      zIndex: 40
    }}>
      {/* 1. Company Logo & Dashboard Title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{
          width: '42px',
          height: '42px',
          borderRadius: '12px',
          background: 'linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          boxShadow: '0 4px 12px rgba(79, 70, 229, 0.25)'
        }}>
          <Shirt size={22} />
        </div>
        <div>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.35rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.02em', lineHeight: 1.1 }}>
            Lead Magnet
          </h1>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>
            Clothing Brand Customer Intelligence
          </span>
        </div>
      </div>

      {/* 2. Search Customer Bar */}
      <div style={{ flex: 1, maxWidth: '420px', margin: '0 32px' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          background: 'var(--panel-solid)',
          border: '1px solid var(--panel-border)',
          padding: '10px 16px',
          borderRadius: 'var(--radius-md)',
          boxShadow: '0 2px 6px rgba(0,0,0,0.02)'
        }}>
          <Search size={18} style={{ color: 'var(--text-muted)' }} />
          <input 
            type="text"
            placeholder="Search customer name, psychographic, or cart items..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              border: 'none',
              background: 'transparent',
              outline: 'none',
              width: '100%',
              fontSize: '0.875rem',
              color: 'var(--text-primary)'
            }}
          />
        </div>
      </div>

      {/* 3. Back to Store, Theme Toggle, Notification Bell & Admin Profile */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        {/* Back to App Store Button */}
        <a 
          href="http://localhost:3001" 
          onClick={(e) => {
            e.preventDefault();
            window.location.href = 'http://localhost:3001';
          }}
          className="btn btn-secondary"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '9px 18px',
            borderRadius: 'var(--radius-full)',
            fontSize: '0.85rem',
            fontWeight: 800,
            color: 'var(--accent-indigo)',
            textDecoration: 'none',
            border: '1px solid var(--panel-border)',
            background: 'var(--panel-solid)',
            boxShadow: '0 2px 6px rgba(0,0,0,0.03)',
            cursor: 'pointer',
            transition: 'all 0.2s ease'
          }}
          title="Navigate to Clothing Store"
        >
          <Store size={16} />
          <span>Back to Store</span>
        </a>

        <button 
          onClick={toggleTheme}
          className="btn btn-ghost"
          style={{ padding: '9px', borderRadius: '50%' }}
          title="Toggle Light/Dark Theme"
        >
          {theme === 'light' ? <Moon size={19} /> : <Sun size={19} />}
        </button>

        {/* Notification Bell */}
        <div style={{ position: 'relative' }}>
          <button className="btn btn-secondary" style={{ padding: '9px', borderRadius: '50%' }}>
            <Bell size={19} />
            <span style={{
              position: 'absolute',
              top: '2px',
              right: '2px',
              width: '8px',
              height: '8px',
              background: 'var(--accent-rose)',
              borderRadius: '50%'
            }} />
          </button>
        </div>

        {/* Admin Profile */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', paddingLeft: '8px', borderLeft: '1px solid var(--panel-border)' }}>
          <img 
            src={adminAvatar} 
            alt={adminName}
            style={{ width: '38px', height: '38px', borderRadius: '50%', objectFit: 'cover', border: '2px solid var(--accent-indigo)' }}
          />
          <div>
            <div style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-primary)' }}>{adminName}</div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{adminRole}</div>
          </div>
          <button
            onClick={adminLogout}
            className="btn btn-ghost"
            style={{ padding: '6px', color: 'var(--accent-rose)', marginLeft: '4px' }}
            title="Log Out Admin"
          >
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </header>
  );
};
