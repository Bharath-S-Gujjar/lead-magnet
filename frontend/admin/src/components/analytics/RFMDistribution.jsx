import React, { useState, useEffect } from 'react';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { getRFMDistribution } from '../../services/api';
import { Users, Crown, Heart, AlertTriangle, Ghost } from 'lucide-react';

const SEGMENT_STYLES = {
  'Champions': { color: '#9CAF88', icon: Crown, bg: 'rgba(156, 175, 136, 0.15)' },
  'Loyal Customers': { color: '#6f805e', icon: Heart, bg: 'rgba(111, 128, 94, 0.15)' },
  'Potential Loyalists': { color: '#849770', icon: Users, bg: 'rgba(132, 151, 112, 0.15)' },
  'New Customers': { color: '#A7A7A7', icon: Users, bg: 'rgba(167, 167, 167, 0.15)' },
  'Promising': { color: '#7a8e6b', icon: Users, bg: 'rgba(122, 142, 107, 0.15)' },
  'Need Attention': { color: '#e06b1a', icon: AlertTriangle, bg: 'rgba(224, 107, 26, 0.15)' },
  'About To Sleep': { color: '#CC5500', icon: Ghost, bg: 'rgba(204, 85, 0, 0.15)' },
  'At Risk': { color: '#b34b00', icon: AlertTriangle, bg: 'rgba(179, 75, 0, 0.15)' },
  'Hibernating': { color: '#8a8a8a', icon: Ghost, bg: 'rgba(138, 138, 138, 0.15)' },
  'Lost': { color: '#686868', icon: Ghost, bg: 'rgba(104, 104, 104, 0.15)' },
  'No Orders': { color: '#A7A7A7', icon: Users, bg: 'rgba(167, 167, 167, 0.08)' },
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
      <div className="glass-card dashboard-card">
        <div className="skeleton" style={{ height: '150px', borderRadius: '12px' }}></div>
      </div>
    );
  }

  if (!data || !data.segments || Object.keys(data.segments).length === 0) {
    return (
      <div className="glass-card dashboard-card" style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
        <Users size={24} style={{ marginBottom: '8px', opacity: 0.5 }} />
        <p>No RFM data available — customers need purchase history</p>
      </div>
    );
  }

  const segments = Object.entries(data.segments).sort((a, b) => b[1] - a[1]);
  const total = data.total_customers_with_orders || 0;

  return (
    <div className="glass-card dashboard-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
        <Crown size={18} style={{ color: 'var(--color-tertiary, #CC5500)' }} />
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
