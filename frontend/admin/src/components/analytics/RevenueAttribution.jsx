import React, { useState, useEffect } from 'react';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { getRevenueAttribution } from '../../services/api';
import { DollarSign, Target, TrendingUp, AlertCircle } from 'lucide-react';

export const RevenueAttribution = () => {
  const { admin } = useAdminAuth();
  const [data, setData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      try {
        const result = await getRevenueAttribution(admin?.token);
        setData(result);
      } catch { /* silent */ }
      setIsLoading(false);
    }
    load();
  }, [admin?.token]);

  if (isLoading) {
    return (
      <div className="glass-card" style={{ padding: '24px' }}>
        <div className="skeleton" style={{ height: '100px', borderRadius: '12px' }}></div>
      </div>
    );
  }

  if (!data) return null;

  const cards = [
    {
      label: 'Qualified Leads',
      value: data.total_qualified_leads || 0,
      icon: Target,
      color: '#6366f1',
      bg: 'rgba(99,102,241,0.12)',
    },
    {
      label: 'Converted to Purchase',
      value: data.qualified_with_purchase || 0,
      suffix: ` (${data.qualified_to_purchase_conversion_rate || 0}%)`,
      icon: TrendingUp,
      color: '#10b981',
      bg: 'rgba(16,185,129,0.12)',
    },
    {
      label: 'Attributed Revenue',
      value: `₹${(data.attributed_revenue || 0).toLocaleString()}`,
      icon: DollarSign,
      color: '#f59e0b',
      bg: 'rgba(245,158,11,0.12)',
    },
    {
      label: 'Attributed Orders',
      value: data.attributed_orders || 0,
      icon: DollarSign,
      color: '#8b5cf6',
      bg: 'rgba(139,92,246,0.12)',
    },
  ];

  return (
    <div className="glass-card" style={{ padding: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
        <DollarSign size={18} style={{ color: '#f59e0b' }} />
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Lead → Revenue Attribution</h3>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '12px' }}>
        {cards.map(card => {
          const IconComp = card.icon;
          return (
            <div key={card.label} style={{
              padding: '14px',
              borderRadius: '10px',
              background: card.bg,
              border: `1px solid ${card.color}22`,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
                <IconComp size={14} style={{ color: card.color }} />
                <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>{card.label}</span>
              </div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: card.color }}>
                {card.value}
                {card.suffix && <span style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--text-muted)' }}>{card.suffix}</span>}
              </div>
            </div>
          );
        })}
      </div>

      {data.attribution_disclaimer && (
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '6px',
          padding: '8px 12px',
          borderRadius: '8px',
          background: 'rgba(245,158,11,0.08)',
          fontSize: '0.7rem',
          color: 'var(--text-muted)',
          lineHeight: 1.4,
        }}>
          <AlertCircle size={12} style={{ marginTop: '2px', flexShrink: 0, color: '#f59e0b' }} />
          {data.attribution_disclaimer}
        </div>
      )}
    </div>
  );
};
