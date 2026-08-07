import React from 'react';
import { Search, Bell, Shirt, Sun, Moon, ShoppingBag, LogOut } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';

export const AdminTopbar = ({ searchQuery, setSearchQuery }) => {
  const { theme, toggleTheme } = useTheme();
  const { adminLogout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    adminLogout();
    navigate('/login?mode=admin');
  };

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

      {/* 3. Actions: Go to Store Button, Theme Toggle, Notification Bell & Admin Profile */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {/* Go to Store Button */}
        <Link 
          to="/" 
          className="btn btn-primary"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '9px 16px',
            borderRadius: 'var(--radius-md)',
            fontWeight: 700,
            fontSize: '0.85rem'
          }}
        >
          <ShoppingBag size={16} />
          <span>Go to Store</span>
        </Link>

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

        {/* Admin Profile & Logout */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', paddingLeft: '8px', borderLeft: '1px solid var(--panel-border)' }}>
          <img 
            src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80" 
            alt="Admin Avatar"
            style={{ width: '38px', height: '38px', borderRadius: '50%', objectFit: 'cover', border: '2px solid var(--accent-indigo)' }}
          />
          <div>
            <div style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-primary)' }}>Sarah Jenkins</div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Store Admin</div>
          </div>
          <button 
            onClick={handleLogout}
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
