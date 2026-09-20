import React, { useState, useEffect } from 'react';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { getFunnelAnalytics } from '../../services/api';
import { Filter, TrendingDown, ArrowRight } from 'lucide-react';

export const FunnelAnalytics = () => {
  const { admin } = useAdminAuth();
  const [data, setData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      try {
        const result = await getFunnelAnalytics(admin?.token);
        setData(result);
      } catch { /* silent */ }
      setIsLoading(false);
    }
    load();
  }, [admin?.token]);

  if (isLoading) {
    return (
      <div className="glass-card" style={{ padding: '24px' }}>
        <div className="skeleton" style={{ height: '200px', borderRadius: '12px' }}></div>
      </div>
    );
  }

  if (!data || !data.stages || data.stages.length === 0) {
    return (
      <div className="glass-card" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
        <Filter size={24} style={{ marginBottom: '8px', opacity: 0.5 }} />
        <p>No funnel data available yet</p>
      </div>
    );
  }

  const maxCount = Math.max(...data.stages.map(s => s.count), 1);
  const colors = ['#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd', '#ddd6fe', '#ede9fe'];

  return (
    <div className="glass-card" style={{ padding: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
        <Filter size={18} style={{ color: 'var(--accent-primary)' }} />
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Purchase Funnel</h3>
        {data.summary && (
          <span style={{
            marginLeft: 'auto',
            fontSize: '0.75rem',
            padding: '4px 10px',
            borderRadius: '20px',
            background: 'rgba(99,102,241,0.15)',
            color: 'var(--accent-primary)',
            fontWeight: 600,
          }}>
            {data.summary.overall_conversion_rate}% overall conversion
          </span>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {data.stages.map((stage, idx) => {
          const barWidth = Math.max(8, (stage.count / maxCount) * 100);
          return (
            <div key={stage.stage} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{ width: '130px', fontSize: '0.8rem', color: 'var(--text-secondary)', textAlign: 'right', flexShrink: 0 }}>
                {stage.stage}
              </div>
              <div style={{ flex: 1, position: 'relative' }}>
                <div style={{
                  height: '28px',
                  width: `${barWidth}%`,
                  background: `linear-gradient(90deg, ${colors[idx] || colors[5]}, ${colors[Math.min(idx + 1, 5)]})`,
                  borderRadius: '6px',
                  display: 'flex',
                  alignItems: 'center',
                  paddingLeft: '10px',
                  transition: 'width 0.6s ease',
                }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#fff' }}>
                    {stage.count.toLocaleString()}
                  </span>
                </div>
              </div>
              <div style={{ width: '70px', fontSize: '0.7rem', color: 'var(--text-muted)', flexShrink: 0 }}>
                {idx > 0 && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                    <TrendingDown size={11} />
                    {stage.drop_off_rate}%
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
