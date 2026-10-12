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

  // Brand Palette: Tertiary (#CC5500), Primary (#9CAF88), Secondary (#A7A7A7)
  const chartData = [
    { name: "Hot Leads", value: segments.hot || 0, color: "#CC5500", pct: total ? `${Math.round((segments.hot / total) * 100)}%` : "0%" },
    { name: "Warm Leads", value: segments.warm || 0, color: "#9CAF88", pct: total ? `${Math.round((segments.warm / total) * 100)}%` : "0%" },
    { name: "Cold Leads", value: segments.cold || 0, color: "#A7A7A7", pct: total ? `${Math.round((segments.cold / total) * 100)}%` : "0%" },
  ];

  const categories = [
    {
      name: "Hot Leads",
      count: segments.hot || 0,
      color: "#CC5500",
      icon: Flame,
      pct: total ? `${Math.round((segments.hot / total) * 100)}%` : "0%",
      description: "High intent, checkout attempts, active cart items",
      badgeClass: "badge-tertiary"
    },
    {
      name: "Warm Leads",
      count: segments.warm || 0,
      color: "#9CAF88",
      icon: ThermometerSun,
      pct: total ? `${Math.round((segments.warm / total) * 100)}%` : "0%",
      description: "Moderate activity, product interactions, wishlist additions",
      badgeClass: "badge-primary"
    },
    {
      name: "Cold Leads",
      count: segments.cold || 0,
      color: "#A7A7A7",
      icon: Snowflake,
      pct: total ? `${Math.round((segments.cold / total) * 100)}%` : "0%",
      description: "Low engagement or inactive customer profiles",
      badgeClass: "badge-secondary"
    }
  ];

  return (
    <div className="product-card dashboard-card">
      {/* Header */}
      <div style={{ textAlign: 'center', marginBottom: '24px' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
          <span className="badge badge-tertiary" style={{ fontSize: '0.72rem' }}>
            SEGMENTATION AI
          </span>
          <span className="badge badge-primary" style={{ fontSize: '0.72rem' }}>
            LIVE FEED
          </span>
        </div>
        <h3 className="heading-lg" style={{ color: 'var(--text-primary)', margin: '0 0 6px 0' }}>
          Customer Lead Distribution
        </h3>
        <p className="text-subtle" style={{ margin: 0, maxWidth: '620px', marginLeft: 'auto', marginRight: 'auto' }}>
          Real-time segmentation and qualification breakdown derived from customer lead state
        </p>
      </div>

      {isLoading ? (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
          Loading lead distribution...
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '28px' }}>
          
          {/* Centered Doughnut Chart */}
          <div style={{ width: '250px', height: '250px', position: 'relative', margin: '0 auto' }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={72}
                  outerRadius={100}
                  paddingAngle={5}
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
                    borderRadius: 'var(--radius-sm, 4px)',
                    fontSize: '0.85rem',
                    color: 'var(--text-primary)'
                  }}
                  formatter={(value, name) => [`${value} Customers (${chartData.find(c => c.name === name)?.pct})`, name]}
                />
              </PieChart>
            </ResponsiveContainer>

            {/* Center Display Badge */}
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
                <span style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--color-tertiary, #CC5500)', letterSpacing: '-0.02em' }}>
                  {qualification.qualified}
                </span>
                <span style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-muted)' }}>
                  /{total}
                </span>
              </div>
              <div style={{
                fontSize: '0.74rem',
                fontWeight: 700,
                color: 'var(--color-primary-dark, #6f805e)',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                marginTop: '4px'
              }}>
                <Check size={13} strokeWidth={3} /> Qualified Leads
              </div>
            </div>
          </div>

          {/* Centered 3-Column Lead Category Cards */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '16px',
            width: '100%',
            maxWidth: '820px',
            margin: '0 auto'
          }}>
            {categories.map((cat) => {
              const isHovered = hoveredCategory === cat.name;
              const Icon = cat.icon;
              return (
                <div
                  key={cat.name}
                  onMouseEnter={() => setHoveredCategory(cat.name)}
                  onMouseLeave={() => setHoveredCategory(null)}
                  style={{
                    background: 'var(--table-header-bg)',
                    border: isHovered ? `1px solid ${cat.color}` : '1px solid var(--panel-border)',
                    borderRadius: 'var(--radius-md, 6px)',
                    padding: '16px',
                    transition: 'all 0.2s ease',
                    cursor: 'pointer',
                    boxShadow: isHovered ? '0 4px 14px rgba(0,0,0,0.06)' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Icon size={18} style={{ color: cat.color }} />
                      <span style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>{cat.name}</span>
                    </div>
                    <span style={{
                      fontSize: '0.75rem',
                      fontWeight: 800,
                      color: cat.color,
                      background: `${cat.color}18`,
                      padding: '2px 8px',
                      borderRadius: '4px',
                      border: `1px solid ${cat.color}40`
                    }}>
                      {cat.pct}
                    </span>
                  </div>

                  <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)', marginBottom: '8px' }}>
                    {cat.count} <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>Customers</span>
                  </div>

                  {/* Colored Progress Bar */}
                  <div style={{
                    width: '100%',
                    height: '6px',
                    background: 'rgba(167, 167, 167, 0.2)',
                    borderRadius: '4px',
                    overflow: 'hidden',
                    marginBottom: '8px'
                  }}>
                    <div style={{
                      width: cat.pct,
                      height: '100%',
                      background: cat.color,
                      borderRadius: '4px',
                      transition: 'width 0.8s cubic-bezier(0.16, 1, 0.3, 1)'
                    }} />
                  </div>

                  <div style={{
                    fontSize: '0.75rem',
                    color: 'var(--text-secondary)',
                    lineHeight: 1.35
                  }}>
                    {cat.description}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default GenderDistribution;
