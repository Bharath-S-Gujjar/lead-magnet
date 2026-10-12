import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { NavPillButton } from '../NavPillButton';

const FALLBACK_NOTIFICATIONS = [
  { id: 1, type: 'user', text: 'We got 6 new registered clothing customers today.', time: 'Just now', unread: true },
  { id: 2, type: 'mail', text: 'Automated sales campaign: 16 marketing emails sent to active leads', time: '10m ago', unread: true },
  { id: 3, type: 'sms', text: 'SMS campaign: "20% OFF Clothing Offer" sent to 5 VIP shoppers', time: '25m ago', unread: true },
  { id: 4, type: 'order', text: 'New Order Placed: ₹1,939 Cotton Dress order by customer', time: '1h ago', unread: false },
];

function NotificationBell({ notifications }) {
  const [isOpen, setIsOpen] = useState(false);
  const [items, setItems] = useState(FALLBACK_NOTIFICATIONS);

  useEffect(() => {
    if (Array.isArray(notifications) && notifications.length > 0) {
      setItems(notifications.map((n, i) => ({
        id: n.id || `notif-${i}`,
        type: n.type || 'user',
        text: n.text || '',
        time: n.time || 'Recent',
        unread: n.unread !== false,
      })));
    }
  }, [notifications]);

  const unreadCount = items.filter(i => i.unread).length;

  const markAllRead = () => {
    setItems(items.map(i => ({ ...i, unread: false })));
  };

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="btn btn-secondary"
        style={{ padding: '9px 12px', borderRadius: '4px', position: 'relative' }}
        title="Admin Notifications"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unreadCount > 0 && (
          <span style={{
            position: 'absolute', top: '-4px', right: '-4px',
            background: 'var(--brand-tertiary)', color: '#ffffff',
            fontSize: '0.68rem', fontWeight: 800, padding: '1px 5px',
            borderRadius: '4px'
          }}>
            {unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div style={{
          position: 'absolute', top: '48px', right: '0', zIndex: 100,
          width: '360px', background: 'var(--panel-solid)',
          border: '1px solid var(--panel-border)', borderRadius: '4px',
          padding: '16px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', paddingBottom: '10px', borderBottom: '1px solid var(--panel-border)' }}>
            <div style={{ fontWeight: 800, fontSize: '0.92rem', color: 'var(--text-primary)' }}>
              Activity Notifications
            </div>
            {unreadCount > 0 && (
              <button onClick={markAllRead} style={{ border: 'none', background: 'transparent', color: 'var(--brand-tertiary)', fontSize: '0.75rem', fontWeight: 700, cursor: 'pointer' }}>
                Mark all read
              </button>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '300px', overflowY: 'auto' }}>
            {items.map((item) => (
              <div key={item.id} style={{
                display: 'flex', gap: '12px', alignItems: 'flex-start',
                padding: '10px 12px', borderRadius: '4px',
                background: item.unread ? 'var(--bg-app)' : 'var(--panel-solid)',
                border: item.unread ? '1px solid var(--brand-primary)' : '1px solid var(--panel-border)'
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-primary)', fontWeight: item.unread ? 700 : 500, lineHeight: 1.4 }}>
                    {item.text}
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                    {item.time}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export const AdminTopbar = ({ searchQuery, setSearchQuery, notifications }) => {
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
      padding: '18px 40px',
      background: 'var(--panel-solid)',
      borderBottom: '1px solid var(--panel-border)',
      position: 'sticky',
      top: 0,
      zIndex: 40
    }}>
      {/* 1. Company Logo & Dashboard Title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{
          width: '38px',
          height: '38px',
          borderRadius: '4px',
          background: 'var(--brand-primary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#1a1d18',
          fontWeight: 800
        }}>
          LM
        </div>
        <div>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1.1 }}>
            Lead Magnet
          </h1>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>
            Customer Intelligence Dashboard
          </span>
        </div>
      </div>

      {/* 2. Search Customer Bar - Uiverse.io style */}
      <div className="input-container navbar-search" style={{ flex: 1, maxWidth: '420px', margin: '0 24px' }}>
        <input
          type="text"
          className="input"
          placeholder="SEARCH CUSTOMERS, SEGMENTS..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        <svg className="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.3-4.3" />
        </svg>
      </div>

      {/* 3. Actions: Go to Store Button, Theme Toggle, Notification Bell & Admin Profile */}
      <div className="navbar-actions" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <NavPillButton
          to="/"
          variant="register"
          icon={
            <svg width="16" height="16" viewBox="0 0 24 24" fill="#9CAF88" style={{ display: 'block' }}>
              <path d="M20 4H4v2h16V4zm1 10v-2l-1-5H4l-1 5v2h1v6h10v-6h4v6h2v-6h1zm-9 4H6v-4h6v4z" />
            </svg>
          }
          label="Storefront"
          title="Navigate to Clothing Store"
        />

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

        <NotificationBell notifications={notifications} />

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', paddingLeft: '8px', borderLeft: '1px solid var(--panel-border)' }}>
          <NavPillButton
            variant="account"
            avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=Admin"
            label="Admin"
            title="Administrator Account"
          />
          <NavPillButton
            onClick={handleLogout}
            variant="logout"
            label="Logout"
            title="Log Out Admin"
          />
        </div>
      </div>
    </header>
  );
};
