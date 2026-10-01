import React, { useState, useEffect } from 'react';
import { Search, Bell, Shirt, Sun, Moon, ShoppingBag, LogOut, CheckCircle2, Mail, MessageSquare, UserPlus, Package } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';

const ICON_MAP = { user: UserPlus, mail: Mail, sms: MessageSquare, order: Package };

const FALLBACK_NOTIFICATIONS = [
  { id: 1, type: 'user', text: 'We got 6 new registered clothing customers today!', time: 'Just now', unread: true },
  { id: 2, type: 'mail', text: 'Automated sales campaign: 16 marketing emails sent to active leads', time: '10m ago', unread: true },
  { id: 3, type: 'sms', text: 'SMS campaign: "20% OFF Clothing Offer" sent to 5 VIP shoppers', time: '25m ago', unread: true },
  { id: 4, type: 'order', text: 'New Order Placed: ₹1,939 Cotton Dress order by e2etest@example.com', time: '1h ago', unread: false },
];

function NotificationBell({ notifications }) {
  const [isOpen, setIsOpen] = useState(false);
  const [items, setItems] = useState(FALLBACK_NOTIFICATIONS);

  // Sync live notifications from backend when they arrive
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
        style={{ padding: '9px', borderRadius: '50%', position: 'relative' }}
        title="Admin Notifications"
      >
        <Bell size={19} />
        {unreadCount > 0 && (
          <span style={{
            position: 'absolute', top: '0px', right: '0px',
            background: 'var(--accent-rose)', color: 'white',
            fontSize: '0.68rem', fontWeight: 800, padding: '2px 6px',
            borderRadius: 'var(--radius-full)'
          }}>
            {unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div style={{
          position: 'absolute', top: '48px', right: '0', zIndex: 100,
          width: '360px', background: 'var(--panel-solid)',
          border: '1px solid var(--panel-border)', borderRadius: 'var(--radius-lg)',
          boxShadow: '0 12px 32px rgba(0,0,0,0.3)', padding: '16px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', paddingBottom: '10px', borderBottom: '1px solid var(--panel-border)' }}>
            <div style={{ fontWeight: 800, fontSize: '0.92rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Bell size={16} style={{ color: 'var(--accent-indigo)' }} />
              <span>Activity Notifications</span>
            </div>
            {unreadCount > 0 && (
              <button onClick={markAllRead} style={{ border: 'none', background: 'transparent', color: 'var(--accent-indigo)', fontSize: '0.75rem', fontWeight: 700, cursor: 'pointer' }}>
                Mark all read
              </button>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '300px', overflowY: 'auto' }}>
            {items.map((item) => {
              const Icon = ICON_MAP[item.type] || Bell;
              return (
                <div key={item.id} style={{
                  display: 'flex', gap: '12px', alignItems: 'flex-start',
                  padding: '10px 12px', borderRadius: 'var(--radius-md)',
                  background: item.unread ? 'rgba(79, 70, 229, 0.08)' : 'var(--table-header-bg)',
                  border: item.unread ? '1px solid rgba(79, 70, 229, 0.2)' : '1px solid var(--panel-border)'
                }}>
                  <div style={{ padding: '6px', borderRadius: '50%', background: 'rgba(79, 70, 229, 0.15)', color: 'var(--accent-indigo)', marginTop: '2px' }}>
                    <Icon size={16} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '0.82rem', color: 'var(--text-primary)', fontWeight: item.unread ? 700 : 500, lineHeight: 1.4 }}>
                      {item.text}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                      {item.time}
                    </div>
                  </div>
                </div>
              );
            })}
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
        <NotificationBell notifications={notifications} />

        {/* Admin Profile & Logout */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', paddingLeft: '8px', borderLeft: '1px solid var(--panel-border)' }}>
          <img 
            src="https://api.dicebear.com/7.x/avataaars/svg?seed=BharatiBhat" 
            alt="Bharati Bhat"
            style={{ width: '38px', height: '38px', borderRadius: '50%', objectFit: 'cover', border: '2px solid var(--accent-indigo)', background: 'rgba(79, 70, 229, 0.1)' }}
          />
          <div>
            <div style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-primary)' }}>Bharati Bhat</div>
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
