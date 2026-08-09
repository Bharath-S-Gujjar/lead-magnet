import React, { useState } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import { Check } from 'lucide-react';

const COLORS = ['#ec4899', '#3b82f6', '#f59e0b', '#10b981', '#8b5cf6'];

export const GenderDistribution = ({ eventAnalytics, overview }) => {
  const [hoveredCategory, setHoveredCategory] = useState(null);
  const categoryCounts = eventAnalytics?.category_counts || [];
  const totalCustomers = overview?.total_customers || overview?.total_profiles || 0;
  const totalLeads = overview?.total_leads || 0;
  const totalCategoryEvents = categoryCounts.reduce((sum, item) => sum + item.count, 0);
  const chartData = (categoryCounts.length ? categoryCounts : [{ category: 'Uncategorized', count: totalCustomers || 0 }]).map((item, index) => ({
    name: item.category || 'Uncategorized',
    value: item.count,
    pct: totalCategoryEvents > 0 ? `${((item.count / totalCategoryEvents) * 100).toFixed(1)}%` : '0%',
    color: COLORS[index % COLORS.length],
  }));

  const demographics = chartData.map((item) => ({
    name: item.name,
    leads: item.value,
    totalLeads,
    pct: item.pct,
    color: item.color,
    totalCustomers,
    conversion: totalCustomers > 0 ? `${((item.value / totalCustomers) * 100).toFixed(1)}%` : '0%',
  }));

  return (
    <div className="glass-card" style={{ padding: '24px 28px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h3 className="heading-lg" style={{ color: 'var(--text-primary)' }}>Customer Distribution (Demographic Split)</h3>
          <p className="text-subtle">Real customer interest distribution from tracked clothing events</p>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-start', flexWrap: 'wrap', gap: '48px' }}>
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
                formatter={(value, name) => [`${value.toLocaleString()} Events (${chartData.find(c => c.name === name)?.pct})`, name]}
              />
            </PieChart>
          </ResponsiveContainer>

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
                {totalLeads.toLocaleString('en-IN')}
              </span>
              <span style={{ fontFamily: 'var(--font-heading)', fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-muted)' }}>
                /{totalCustomers.toLocaleString('en-IN')}
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

        <div style={{ width: '440px', maxWidth: '100%', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {demographics.map((demo) => {
            const isHovered = hoveredCategory === demo.name;
            return (
              <div 
                key={demo.name}
                onMouseEnter={() => setHoveredCategory(demo.name)}
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
                    <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: demo.color }} />
                    <span style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-primary)' }}>{demo.name}</span>
                  </div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                    {demo.leads} Events <span style={{ color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.78rem' }}>({demo.pct})</span>
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
                    width: demo.pct,
                    height: '100%',
                    background: demo.color,
                    borderRadius: 'var(--radius-full)',
                    transition: 'width 0.8s cubic-bezier(0.16, 1, 0.3, 1)'
                  }} />
                </div>

                {isHovered && (
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '16px',
                    marginTop: '10px',
                    paddingTop: '8px',
                    borderTop: '1px dashed var(--panel-border)',
                    fontSize: '0.78rem',
                    color: 'var(--text-secondary)',
                    animation: 'fadeIn 0.2s ease'
                  }}>
                    <span><strong>Total Customers:</strong> {demo.totalCustomers.toLocaleString()}</span>
                    <span>-</span>
                    <span><strong>Total Leads:</strong> {demo.totalLeads.toLocaleString()}</span>
                    <span>-</span>
                    <span><strong>Event Share:</strong> <strong style={{ color: 'var(--accent-emerald)' }}>{demo.conversion}</strong></span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
