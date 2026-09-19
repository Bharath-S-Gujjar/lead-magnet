import React, { useState, useEffect } from 'react';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { getAdminMarketingActivity } from '../../services/api';
import { Mail, MessageSquare, Send, AlertCircle, Clock, ChevronLeft, ChevronRight } from 'lucide-react';

export const MarketingActivityFeed = () => {
  const { admin } = useAdminAuth();
  const [activity, setActivity] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(1);

  const loadActivity = async (targetPage = 1) => {
    setIsLoading(true);
    try {
      const data = await getAdminMarketingActivity({ token: admin?.token, page: targetPage, limit: 5 });
      setActivity(data);
      setPage(targetPage);
    } catch (err) {
      setActivity(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadActivity(1);
  }, [admin?.token]);

  const items = activity?.items || [];
  const totalPages = activity?.pages || 0;

  const getChannelIcon = (channel) => {
    if (channel === 'email') return <Mail size={15} style={{ color: '#3b82f6' }} />;
    if (channel === 'sms') return <Send size={15} style={{ color: '#10b981' }} />;
    if (channel === 'whatsapp') return <MessageSquare size={15} style={{ color: '#25d366' }} />;
    return <Mail size={15} />;
  };

  const getStatusBadge = (status) => {
    if (status === 'sent') return <span className="badge badge-emerald">Sent</span>;
    if (status === 'failed') return <span className="badge badge-rose">Failed</span>;
    if (status === 'skipped') return <span className="badge badge-subtle">Skipped</span>;
    return <span className="badge badge-indigo">Pending</span>;
  };

  return (
    <div className="glass-card" style={{ padding: '24px 28px', marginBottom: '28px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
        <div>
          <h3 className="heading-lg" style={{ color: 'var(--text-primary)' }}>Marketing Automation Activity</h3>
          <p className="text-subtle">Recent automated communications dispatched to qualified customers</p>
        </div>
        {totalPages > 1 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              onClick={() => loadActivity(page - 1)}
              disabled={page <= 1 || isLoading}
              className="btn btn-ghost"
              style={{ padding: '6px 10px' }}
            >
              <ChevronLeft size={16} />
            </button>
            <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => loadActivity(page + 1)}
              disabled={page >= totalPages || isLoading}
              className="btn btn-ghost"
              style={{ padding: '6px 10px' }}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>

      {isLoading ? (
        <div style={{ padding: '20px 0', color: 'var(--text-muted)' }}>Loading marketing activity...</div>
      ) : items.length === 0 ? (
        <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-subtle)', background: 'var(--table-header-bg)', borderRadius: 'var(--radius-md)' }}>
          No marketing dispatches recorded yet. Activity will populate automatically when customers become newly qualified.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {items.map((item, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '12px 16px',
                background: 'var(--table-header-bg)',
                border: '1px solid var(--panel-border)',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.88rem'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: 'var(--panel-solid)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  {getChannelIcon(item.channel)}
                </div>
                <div>
                  <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                    {item.customer_name || item.recipient || 'Customer'}
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    Channel: {item.channel?.toUpperCase()} • Recipient: {item.recipient || 'N/A'}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                {getStatusBadge(item.status)}
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Clock size={13} />
                  <span>{item.sent_at ? new Date(item.sent_at).toLocaleTimeString() : (item.created_at ? new Date(item.created_at).toLocaleTimeString() : 'N/A')}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
