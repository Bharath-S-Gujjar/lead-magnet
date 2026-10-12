import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Bell, Flame, User, ShoppingBag, CheckCheck, X, Sparkles, ExternalLink } from 'lucide-react';
import { io } from 'socket.io-client';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { getAdminNotifications, markNotificationRead, markAllNotificationsRead } from '../../services/api';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000';

function formatRelativeTime(ts) {
  if (!ts) return 'Just now';
  const now = Date.now();
  const past = new Date(ts).getTime();
  if (isNaN(past)) return 'Just now';
  const diffSec = Math.floor((now - past) / 1000);
  if (diffSec < 45) return 'Just now';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

function getNotificationVisuals(type) {
  switch (type) {
    case 'lead_qualified':
      return {
        icon: Flame,
        color: '#f97316',
        bg: 'rgba(249, 115, 22, 0.12)',
        border: 'rgba(249, 115, 22, 0.25)',
        badge: '🔥 Hot Lead',
      };
    case 'new_customer':
      return {
        icon: User,
        color: '#3b82f6',
        bg: 'rgba(59, 130, 246, 0.12)',
        border: 'rgba(59, 130, 246, 0.25)',
        badge: '👤 Customer',
      };
    case 'order_placed':
      return {
        icon: ShoppingBag,
        color: '#10b981',
        bg: 'rgba(16, 185, 129, 0.12)',
        border: 'rgba(16, 185, 129, 0.25)',
        badge: '🛍️ Order',
      };
    default:
      return {
        icon: Bell,
        color: '#8b5cf6',
        bg: 'rgba(139, 92, 246, 0.12)',
        border: 'rgba(139, 92, 246, 0.25)',
        badge: '🔔 Alert',
      };
  }
}

export const NotificationBell = ({ onSelectCustomer }) => {
  const { admin } = useAdminAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [toasts, setToasts] = useState([]);

  const dropdownRef = useRef(null);
  const socketRef = useRef(null);

  // ── 1. Toast dismissal helper ──
  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((notif) => {
    const id = notif.id || notif._id || `toast-${Date.now()}`;
    const toastItem = { ...notif, id };
    setToasts((prev) => [toastItem, ...prev.filter((t) => t.id !== id)].slice(0, 3));
    setTimeout(() => {
      removeToast(id);
    }, 5000);
  }, [removeToast]);

  // ── 2. Initial Fetch from API ──
  const loadNotifications = useCallback(async () => {
    if (!admin?.token) return;
    setLoading(true);
    try {
      const res = await getAdminNotifications({ token: admin.token, page: 1, limit: 20 });
      if (res && res.items) {
        const normalized = res.items.map((it) => ({
          ...it,
          id: it.id || it._id,
        }));
        setNotifications(normalized);
        const count = typeof res.unread_count === 'number'
          ? res.unread_count
          : normalized.filter((n) => !n.read).length;
        setUnreadCount(count);
      }
    } catch (err) {
      console.error('Failed to load notifications:', err);
    } finally {
      setLoading(false);
    }
  }, [admin?.token]);

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);

  // ── 3. Real-Time Socket.IO Listener ──
  useEffect(() => {
    const socket = io(API_BASE, {
      transports: ['websocket', 'polling'],
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
    });
    socketRef.current = socket;

    socket.on('admin_notification', (data) => {
      if (!data) return;
      const notifId = data.id || data._id;
      if (!notifId) return;

      const normalized = {
        ...data,
        id: notifId,
        read: false,
        created_at: data.created_at || new Date().toISOString(),
      };

      setNotifications((prev) => {
        const exists = prev.some((n) => (n.id || n._id) === notifId);
        if (exists) return prev;
        return [normalized, ...prev].slice(0, 20);
      });

      setUnreadCount((prev) => prev + 1);
      addToast(normalized);
    });

    return () => {
      socket.disconnect();
    };
  }, [addToast]);

  // ── 4. Click outside to close dropdown ──
  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // ── 5. Action: Click single notification ──
  const handleNotificationClick = async (notif) => {
    const notifId = notif.id || notif._id;
    if (!notif.read) {
      // Optimistic update
      setNotifications((prev) =>
        prev.map((n) => ((n.id || n._id) === notifId ? { ...n, read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));

      try {
        await markNotificationRead(notifId, admin?.token);
      } catch (err) {
        console.error('Failed to mark notification read:', err);
      }
    }

    if (notif.customer_id && onSelectCustomer) {
      onSelectCustomer(notif.customer_id);
      setIsOpen(false);
    }
  };

  // ── 6. Action: Mark all as read ──
  const handleMarkAllRead = async () => {
    if (unreadCount === 0) return;

    // Optimistic update
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    setUnreadCount(0);

    try {
      await markAllNotificationsRead(admin?.token);
    } catch (err) {
      console.error('Failed to mark all notifications read:', err);
    }
  };

  return (
    <div style={{ position: 'relative' }} ref={dropdownRef}>
      {/* ── Bell Icon Button ── */}
      <button
        id="admin-notification-bell-btn"
        onClick={() => setIsOpen((prev) => !prev)}
        className="btn btn-secondary"
        style={{
          position: 'relative',
          padding: '9px',
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          background: isOpen ? 'var(--accent-indigo)' : 'var(--panel-solid)',
          color: isOpen ? '#ffffff' : 'var(--text-primary)',
          border: '1px solid var(--panel-border)',
          transition: 'all 0.2s ease',
        }}
        title="Admin Notifications"
        aria-label="Admin Notifications"
      >
        <Bell size={19} />

        {/* Unread Badge */}
        {unreadCount > 0 && (
          <span
            id="admin-notification-badge"
            style={{
              position: 'absolute',
              top: '-4px',
              right: '-4px',
              minWidth: '18px',
              height: '18px',
              padding: '0 5px',
              background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
              color: '#ffffff',
              borderRadius: '9999px',
              fontSize: '0.70rem',
              fontWeight: 800,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '2px solid var(--panel-bg)',
              boxShadow: '0 2px 6px rgba(239, 68, 68, 0.4)',
              animation: 'pulse 2s infinite',
            }}
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* ── Dropdown Panel ── */}
      {isOpen && (
        <div
          id="admin-notification-dropdown"
          style={{
            position: 'absolute',
            top: 'calc(100% + 10px)',
            right: 0,
            width: '380px',
            maxHeight: '480px',
            display: 'flex',
            flexDirection: 'column',
            background: 'var(--panel-solid)',
            backdropFilter: 'blur(16px)',
            border: '1px solid var(--panel-border)',
            borderRadius: '16px',
            boxShadow: '0 16px 40px rgba(0, 0, 0, 0.24)',
            zIndex: 100,
            overflow: 'hidden',
            animation: 'fadeIn 0.15s ease-out',
          }}
        >
          {/* Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '16px 20px',
              borderBottom: '1px solid var(--panel-border)',
              background: 'var(--panel-bg)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontWeight: 800, fontSize: '0.95rem', color: 'var(--text-primary)' }}>
                Notifications
              </span>
              {unreadCount > 0 && (
                <span
                  style={{
                    background: 'rgba(239, 68, 68, 0.12)',
                    color: 'var(--accent-rose)',
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    padding: '2px 8px',
                    borderRadius: '12px',
                  }}
                >
                  {unreadCount} unread
                </span>
              )}
            </div>

            {unreadCount > 0 && (
              <button
                id="admin-notification-mark-all-btn"
                onClick={handleMarkAllRead}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--accent-indigo)',
                  fontSize: '0.78rem',
                  fontWeight: 700,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  cursor: 'pointer',
                  padding: '4px 8px',
                  borderRadius: '6px',
                  transition: 'background 0.15s ease',
                }}
                title="Mark all notifications as read"
              >
                <CheckCheck size={14} />
                <span>Mark all as read</span>
              </button>
            )}
          </div>

          {/* Notification List */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '8px 0',
            }}
          >
            {loading && notifications.length === 0 ? (
              <div style={{ padding: '32px 20px', textAlign: 'center', color: 'var(--text-muted)' }}>
                <span style={{ fontSize: '0.85rem' }}>Loading notifications...</span>
              </div>
            ) : notifications.length === 0 ? (
              <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--text-muted)' }}>
                <Bell size={28} style={{ opacity: 0.35, marginBottom: '8px' }} />
                <div style={{ fontSize: '0.88rem', fontWeight: 600 }}>No notifications yet</div>
                <div style={{ fontSize: '0.76rem', marginTop: '4px' }}>
                  Live customer and lead updates will appear here
                </div>
              </div>
            ) : (
              notifications.map((notif) => {
                const visuals = getNotificationVisuals(notif.type);
                const IconComponent = visuals.icon;
                const isUnread = !notif.read;

                return (
                  <div
                    key={notif.id || notif._id}
                    onClick={() => handleNotificationClick(notif)}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '12px',
                      padding: '12px 18px',
                      borderBottom: '1px solid var(--panel-border)',
                      background: isUnread ? 'rgba(79, 70, 229, 0.05)' : 'transparent',
                      cursor: 'pointer',
                      transition: 'background 0.15s ease',
                      position: 'relative',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = isUnread
                        ? 'rgba(79, 70, 229, 0.09)'
                        : 'rgba(255, 255, 255, 0.03)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = isUnread
                        ? 'rgba(79, 70, 229, 0.05)'
                        : 'transparent';
                    }}
                  >
                    {/* Icon Container */}
                    <div
                      style={{
                        width: '36px',
                        height: '36px',
                        borderRadius: '10px',
                        background: visuals.bg,
                        border: `1px solid ${visuals.border}`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: visuals.color,
                        flexShrink: 0,
                        marginTop: '2px',
                      }}
                    >
                      <IconComponent size={18} />
                    </div>

                    {/* Content */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '6px',
                          marginBottom: '2px',
                        }}
                      >
                        <span
                          style={{
                            fontWeight: isUnread ? 800 : 600,
                            fontSize: '0.84rem',
                            color: 'var(--text-primary)',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                        >
                          {notif.title || visuals.badge}
                        </span>
                        <span
                          style={{
                            fontSize: '0.72rem',
                            color: 'var(--text-muted)',
                            flexShrink: 0,
                          }}
                        >
                          {formatRelativeTime(notif.created_at)}
                        </span>
                      </div>

                      <p
                        style={{
                          margin: 0,
                          fontSize: '0.78rem',
                          color: 'var(--text-muted)',
                          lineHeight: 1.35,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                        }}
                      >
                        {notif.message || notif.body || 'New notification update'}
                      </p>

                      {notif.customer_id && (
                        <div
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            marginTop: '4px',
                            fontSize: '0.70rem',
                            fontWeight: 700,
                            color: 'var(--accent-indigo)',
                          }}
                        >
                          <span>View Customer 360</span>
                          <ExternalLink size={10} />
                        </div>
                      )}
                    </div>

                    {/* Unread Glowing Dot */}
                    {isUnread && (
                      <span
                        style={{
                          width: '8px',
                          height: '8px',
                          borderRadius: '50%',
                          background: 'var(--accent-indigo)',
                          boxShadow: '0 0 6px var(--accent-indigo)',
                          flexShrink: 0,
                          marginTop: '6px',
                        }}
                      />
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* ── Real-Time Toast Popups ── */}
      {toasts.length > 0 && (
        <div
          style={{
            position: 'fixed',
            top: '78px',
            right: '24px',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
            zIndex: 9999,
            pointerEvents: 'none',
          }}
        >
          {toasts.map((t) => {
            const visuals = getNotificationVisuals(t.type);
            const IconComponent = visuals.icon;

            return (
              <div
                key={t.id}
                onClick={() => {
                  handleNotificationClick(t);
                  removeToast(t.id);
                }}
                style={{
                  pointerEvents: 'auto',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '12px',
                  width: '320px',
                  padding: '14px 16px',
                  background: 'var(--panel-solid)',
                  backdropFilter: 'blur(16px)',
                  border: `1px solid ${visuals.border}`,
                  borderRadius: '12px',
                  boxShadow: '0 12px 30px rgba(0, 0, 0, 0.28)',
                  cursor: 'pointer',
                  animation: 'slideInRight 0.25s ease-out',
                  transition: 'transform 0.15s ease',
                }}
              >
                <div
                  style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '8px',
                    background: visuals.bg,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: visuals.color,
                    flexShrink: 0,
                  }}
                >
                  <IconComponent size={16} />
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontWeight: 800,
                      fontSize: '0.84rem',
                      color: 'var(--text-primary)',
                      marginBottom: '2px',
                    }}
                  >
                    {t.title || visuals.badge}
                  </div>
                  <div
                    style={{
                      fontSize: '0.78rem',
                      color: 'var(--text-muted)',
                      lineHeight: 1.3,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {t.message || t.body || 'New live update'}
                  </div>
                </div>

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeToast(t.id);
                  }}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--text-muted)',
                    cursor: 'pointer',
                    padding: '2px',
                  }}
                >
                  <X size={14} />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
