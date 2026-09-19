import React, { useState, useEffect } from 'react';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { getAdminNotifications } from '../../services/api';
import { Bell, CheckCircle2, Flame, Clock } from 'lucide-react';

export const AdminNotificationsList = () => {
  const { admin } = useAdminAuth();
  const [notifications, setNotifications] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    async function loadNotifications() {
      setIsLoading(true);
      try {
        const res = await getAdminNotifications({ token: admin?.token, page: 1, limit: 5 });
        if (isMounted) setNotifications(res.items || []);
      } catch (err) {
        if (isMounted) setNotifications([]);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }
    loadNotifications();
    return () => { isMounted = false; };
  }, [admin?.token]);

  if (isLoading) return null;
  if (notifications.length === 0) return null;

  return (
    <div className="glass-card" style={{ padding: '20px 24px', marginBottom: '28px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
        <Bell size={18} style={{ color: 'var(--accent-indigo)' }} />
        <h4 className="heading-md" style={{ color: 'var(--text-primary)' }}>Internal Admin Notifications</h4>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {notifications.map((n, idx) => (
          <div
            key={idx}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 14px',
              background: 'var(--table-header-bg)',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.85rem'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              {n.type === 'lead_qualified' ? (
                <Flame size={16} style={{ color: '#ef4444' }} />
              ) : (
                <CheckCircle2 size={16} style={{ color: '#10b981' }} />
              )}
              <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{n.message}</span>
            </div>

            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Clock size={12} />
              <span>{n.created_at ? new Date(n.created_at).toLocaleTimeString() : 'Recently'}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
