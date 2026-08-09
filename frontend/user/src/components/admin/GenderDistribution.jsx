import React, { useState } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import { Check, Users } from 'lucide-react';

const DEMO_BRACKETS = [
  'Male 18–24',
  'Male 25–34',
  'Male 35+',
  'Female 18–24',
  'Female 25–34',
  'Female 35+',
  'Other/Unknown',
];

const DEMO_COLORS = [
  '#3b82f6', // Male 18-24 (blue)
  '#2563eb', // Male 25-34 (darker blue)
  '#1d4ed8', // Male 35+ (deep blue)
  '#ec4899', // Female 18-24 (pink)
  '#db2777', // Female 25-34 (darker pink)
  '#be185d', // Female 35+ (deep pink)
  '#94a3b8', // Other/Unknown (slate)
];

export const GenderDistribution = ({ eventAnalytics, overview, customers = [] }) => {
  const [hoveredCategory, setHoveredCategory] = useState(null);

  // Group real user_profiles by age + gender from MongoDB
  const counts = {
    'Male 18–24': 0,
    'Male 25–34': 0,
    'Male 35+': 0,
    'Female 18–24': 0,
    'Female 25–34': 0,
    'Female 35+': 0,
    'Other/Unknown': 0,
  };

  customers.forEach((c) => {
    const rawGender = String(c.gender || '').trim().toLowerCase();
    const age = parseInt(c.age, 10);
    const gender = rawGender === 'male' ? 'Male' : rawGender === 'female' ? 'Female' : null;

    if (!gender || isNaN(age)) {
      counts['Other/Unknown'] += 1;
    } else if (gender === 'Male') {
      if (age >= 18 && age <= 24) counts['Male 18–24'] += 1;
      else if (age >= 25 && age <= 34) counts['Male 25–34'] += 1;
      else if (age >= 35) counts['Male 35+'] += 1;
      else counts['Other/Unknown'] += 1;
    } else if (gender === 'Female') {
      if (age >= 18 && age <= 24) counts['Female 18–24'] += 1;
      else if (age >= 25 && age <= 34) counts['Female 25–34'] += 1;
      else if (age >= 35) counts['Female 35+'] += 1;
      else counts['Other/Unknown'] += 1;
    }
  });

  const totalProfileCount = Object.values(counts).reduce((a, b) => a + b, 0);

  const chartData = DEMO_BRACKETS.map((bracket, index) => {
    const val = counts[bracket] || 0;
    const pctNumber = totalProfileCount > 0 ? (val / totalProfileCount) * 100 : 0;
    return {
      name: bracket,
      value: val,
      pct: `${pctNumber.toFixed(1)}%`,
      color: DEMO_COLORS[index],
    };
  });

  const totalCustomers = overview?.total_customers || customers.length || 0;
  const totalLeads = overview?.total_leads || 0;

  const demographics = chartData.map((item) => ({
    name: item.name,
    customerCount: item.value,
    pct: item.pct,
    color: item.color,
    totalCustomers,
  }));

  return (
    <div className="glass-card" style={{ padding: '24px 28px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h3 className="heading-lg" style={{ color: 'var(--text-primary)' }}>Customer Demographic Distribution</h3>
          <p className="text-subtle">Real customer age & gender breakdown from MongoDB user profiles</p>
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
                formatter={(value, name) => [`${value} Customers (${chartData.find(c => c.name === name)?.pct})`, name]}
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
                {totalCustomers.toLocaleString('en-IN')}
              </span>
            </div>
            <div style={{
              fontSize: '0.75rem',
              fontWeight: 700,
              color: 'var(--accent-indigo)',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              marginTop: '4px'
            }}>
              <Users size={13} strokeWidth={3} /> Registered Shoppers
            </div>
          </div>
        </div>

        <div style={{ width: '440px', maxWidth: '100%', display: 'flex', flexDirection: 'column', gap: '10px' }}>
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
                  padding: '10px 14px',
                  transition: 'all 0.2s ease',
                  cursor: 'pointer'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: demo.color }} />
                    <span style={{ fontWeight: 700, fontSize: '0.86rem', color: 'var(--text-primary)' }}>{demo.name}</span>
                  </div>
                  <div style={{ fontSize: '0.84rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                    {demo.customerCount} Customers <span style={{ color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.76rem' }}>({demo.pct})</span>
                  </div>
                </div>

                <div style={{
                  width: '100%',
                  height: '6px',
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
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
