import React, { useState, useEffect } from 'react';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { getRFMDistribution } from '../../services/api';
import { Users, Crown, Heart, AlertTriangle, Ghost } from 'lucide-react';

const SEGMENT_STYLES = {
  'Champions': { color: '#10b981', icon: Crown, bg: 'rgba(16,185,129,0.12)' },
  'Loyal Customers': { color: '#6366f1', icon: Heart, bg: 'rgba(99,102,241,0.12)' },
  'Potential Loyalists': { color: '#8b5cf6', icon: Users, bg: 'rgba(139,92,246,0.12)' },
  'New Customers': { color: '#3b82f6', icon: Users, bg: 'rgba(59,130,246,0.12)' },
  'Promising': { color: '#06b6d4', icon: Users, bg: 'rgba(6,182,212,0.12)' },
  'Need Attention': { color: '#f59e0b', icon: AlertTriangle, bg: 'rgba(245,158,11,0.12)' },
  'About To Sleep': { color: '#f97316', icon: Ghost, bg: 'rgba(249,115,22,0.12)' },
  'At Risk': { color: '#ef4444', icon: AlertTriangle, bg: 'rgba(239,68,68,0.12)' },
  'Hibernating': { color: '#94a3b8', icon: Ghost, bg: 'rgba(148,163,184,0.12)' },
  'Lost': { color: '#64748b', icon: Ghost, bg: 'rgba(100,116,139,0.12)' },
  'No Orders': { color: '#94a3b8', icon: Users, bg: 'rgba(148,163,184,0.08)' },
};

export const RFMDistribution = () => {
  const { admin } = useAdminAuth();
  const [data, setData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      try {
        const result = await getRFMDistribution(admin?.token);
        setData(result);
      } catch { /* silent */ }
      setIsLoading(false);
    }
    load();
  }, [admin?.token]);

  if (isLoading) {
    return (
      <div className="glass-card" style={{ padding: '24px' }}>
        <div className="skeleton" style={{ height: '150px', borderRadius: '12px' }}></div>
      </div>
    );
  }

  if (!data || !data.segments || Object.keys(data.segments).length === 0) {
    return (
      <div className="glass-card" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
        <Users size={24} style={{ marginBottom: '8px', opacity: 0.5 }} />
        <p>No RFM data available — customers need purchase history</p>
      </div>
    );
  }

  const segments = Object.entries(data.segments).sort((a, b) => b[1] - a[1]);
  const total = data.total_customers_with_orders || 0;

  return (
    <div className="glass-card" style={{ padding: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
        <Crown size={18} style={{ color: '#f59e0b' }} />
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>RFM Segments</h3>
        <span style={{
          marginLeft: 'auto',
          fontSize: '0.75rem',
          color: 'var(--text-muted)',
        }}>
          {total} customers with orders
        </span>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
        {segments.map(([name, count]) => {
          const style = SEGMENT_STYLES[name] || SEGMENT_STYLES['No Orders'];
          const IconComp = style.icon;
          const pct = total > 0 ? ((count / total) * 100).toFixed(1) : '0.0';
          return (
            <div key={name} style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 14px',
              borderRadius: '10px',
              background: style.bg,
              border: `1px solid ${style.color}22`,
              minWidth: '140px',
            }}>
              <IconComp size={16} style={{ color: style.color, flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.2 }}>{name}</div>
                <div style={{ fontSize: '1rem', fontWeight: 700, color: style.color }}>{count} <span style={{ fontSize: '0.7rem', fontWeight: 400, color: 'var(--text-muted)' }}>({pct}%)</span></div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
