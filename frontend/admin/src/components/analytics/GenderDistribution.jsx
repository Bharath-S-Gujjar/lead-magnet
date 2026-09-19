import React, { useState, useEffect } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { getAdminLeadDistribution } from '../../services/api';
import { Check, Flame, ThermometerSun, Snowflake } from 'lucide-react';

export const GenderDistribution = () => {
  const { admin } = useAdminAuth();
  const [distData, setDistData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hoveredCategory, setHoveredCategory] = useState(null);

  useEffect(() => {
    let isMounted = true;
    async function loadDistribution() {
      setIsLoading(true);
      try {
        const data = await getAdminLeadDistribution(admin?.token);
        if (isMounted) setDistData(data);
      } catch (err) {
        if (isMounted) setDistData(null);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }
    loadDistribution();
    return () => { isMounted = false; };
  }, [admin?.token]);

  const total = distData?.total || 0;
  const segments = distData?.segments || { hot: 0, warm: 0, cold: 0 };
  const qualification = distData?.qualification || { qualified: 0, not_qualified: 0 };

  const chartData = [
    { name: "Hot Leads", value: segments.hot, color: "#ef4444", pct: total ? `${Math.round((segments.hot / total) * 100)}%` : "0%" },
    { name: "Warm Leads", value: segments.warm, color: "#f59e0b", pct: total ? `${Math.round((segments.warm / total) * 100)}%` : "0%" },
    { name: "Cold Leads", value: segments.cold, color: "#3b82f6", pct: total ? `${Math.round((segments.cold / total) * 100)}%` : "0%" },
  ];

  const categories = [
    {
      name: "Hot Leads",
      count: segments.hot,
      color: "#ef4444",
      icon: Flame,
      pct: total ? `${Math.round((segments.hot / total) * 100)}%` : "0%",
      description: "High intent, checkout attempts, active cart items"
    },
    {
      name: "Warm Leads",
      count: segments.warm,
      color: "#f59e0b",
      icon: ThermometerSun,
      pct: total ? `${Math.round((segments.warm / total) * 100)}%` : "0%",
      description: "Moderate activity, product interactions, wishlist additions"
    },
    {
      name: "Cold Leads",
      count: segments.cold,
      color: "#3b82f6",
      icon: Snowflake,
      pct: total ? `${Math.round((segments.cold / total) * 100)}%` : "0%",
      description: "Low engagement or inactive customer profiles"
    }
  ];

  return (
    <div className="glass-card" style={{ padding: '24px 28px', marginBottom: '28px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h3 className="heading-lg" style={{ color: 'var(--text-primary)' }}>Customer Lead Distribution</h3>
          <p className="text-subtle">Real-time segmentation and qualification breakdown derived from customer lead state</p>
        </div>
        <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
          Total Customers Evaluated: <strong>{total}</strong>
        </div>
      </div>

      {isLoading ? (
        <div style={{ padding: '24px', color: 'var(--text-muted)' }}>Loading lead distribution...</div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-start', flexWrap: 'wrap', gap: '48px' }}>
          
          {/* Doughnut Chart */}
          <div style={{ width: '220px', height: '220px', position: 'relative', flexShrink: 0 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={62}
                  outerRadius={88}
                  paddingAngle={4}
                  dataKey="value"
                  animationDuration={1000}
                  stroke="none"
                >
                  {chartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: 'var(--panel-solid)',
                    border: '1px solid var(--panel-border)',
                    borderRadius: 'var(--radius-md)',
                    boxShadow: 'var(--panel-shadow)',
                    fontSize: '0.85rem'
                  }}
                  formatter={(value, name) => [`${value} Customers (${chartData.find(c => c.name === name)?.pct})`, name]}
                />
              </PieChart>
            </ResponsiveContainer>

            {/* Center Display */}
            <div style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              textAlign: 'center',
              pointerEvents: 'none',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '2px', lineHeight: 1 }}>
                <span style={{ fontFamily: 'var(--font-heading)', fontSize: '1.9rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
                  {qualification.qualified}
                </span>
                <span style={{ fontFamily: 'var(--font-heading)', fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-muted)' }}>
                  /{total}
                </span>
              </div>
              <div style={{
                fontSize: '0.75rem',
                fontWeight: 700,
                color: 'var(--accent-emerald)',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                marginTop: '4px'
              }}>
                <Check size={13} strokeWidth={3} /> Qualified Leads
              </div>
            </div>
          </div>

          {/* Progress Cards */}
          <div style={{ width: '440px', maxWidth: '100%', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {categories.map((cat) => {
              const isHovered = hoveredCategory === cat.name;
              const Icon = cat.icon;
              return (
                <div
                  key={cat.name}
                  onMouseEnter={() => setHoveredCategory(cat.name)}
                  onMouseLeave={() => setHoveredCategory(null)}
                  style={{
                    background: isHovered ? 'rgba(79, 70, 229, 0.04)' : 'var(--table-header-bg)',
                    border: isHovered ? '1px solid var(--accent-indigo)' : '1px solid var(--panel-border)',
                    borderRadius: 'var(--radius-md)',
                    padding: '12px 16px',
                    transition: 'all 0.2s ease',
                    cursor: 'pointer'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Icon size={16} style={{ color: cat.color }} />
                      <span style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-primary)' }}>{cat.name}</span>
                    </div>
                    <div style={{ fontSize: '0.85rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                      {cat.count} Customers <span style={{ color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.78rem' }}>({cat.pct})</span>
                    </div>
                  </div>

                  <div style={{
                    width: '100%',
                    height: '7px',
                    background: 'rgba(148, 163, 184, 0.16)',
                    borderRadius: 'var(--radius-full)',
                    overflow: 'hidden'
                  }}>
                    <div style={{
                      width: cat.pct,
                      height: '100%',
                      background: cat.color,
                      borderRadius: 'var(--radius-full)',
                      transition: 'width 0.8s cubic-bezier(0.16, 1, 0.3, 1)'
                    }} />
                  </div>

                  {isHovered && (
                    <div style={{
                      marginTop: '8px',
                      fontSize: '0.78rem',
                      color: 'var(--text-secondary)'
                    }}>
                      {cat.description}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
