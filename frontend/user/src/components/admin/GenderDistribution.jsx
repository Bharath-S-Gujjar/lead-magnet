import React, { useState } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';

const DEMO_BRACKETS = [
  'Male 18-24',
  'Male 25-34',
  'Male 35+',
  'Female 18-24',
  'Female 25-34',
  'Female 35+',
  'Other/Unknown',
];

const DEMO_COLORS = [
  '#9CAF88', // Sage green (Primary)
  '#849770', // Sage green deep
  '#6f805e', // Sage green dark
  '#CC5500', // Burnt orange (Tertiary)
  '#b34b00', // Burnt orange deep
  '#e06b1a', // Burnt orange vibrant
  '#A7A7A7', // Slate silver (Secondary)
];

export const GenderDistribution = ({ eventAnalytics, overview, customers = [] }) => {
  const [hoveredCategory, setHoveredCategory] = useState(null);

  // Group real user_profiles by age + gender from MongoDB
  const counts = {
    'Male 18-24': 0,
    'Male 25-34': 0,
    'Male 35+': 0,
    'Female 18-24': 0,
    'Female 25-34': 0,
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
      if (age >= 18 && age <= 24) counts['Male 18-24'] += 1;
      else if (age >= 25 && age <= 34) counts['Male 25-34'] += 1;
      else if (age >= 35) counts['Male 35+'] += 1;
      else counts['Other/Unknown'] += 1;
    } else if (gender === 'Female') {
      if (age >= 18 && age <= 24) counts['Female 18-24'] += 1;
      else if (age >= 25 && age <= 34) counts['Female 25-34'] += 1;
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

  const demographics = chartData.map((item) => ({
    name: item.name,
    customerCount: item.value,
    pct: item.pct,
    color: item.color,
    totalCustomers,
  }));

  return (
    <div className="product-card" style={{ padding: '28px 32px', background: 'var(--panel-solid)' }}>
      {/* Centered Header */}
      <div style={{ textAlign: 'center', marginBottom: '24px' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
          <span className="badge badge-primary" style={{ fontSize: '0.72rem' }}>
            DEMOGRAPHICS
          </span>
          <span className="badge badge-tertiary" style={{ fontSize: '0.72rem' }}>
            AI SEGMENTATION
          </span>
        </div>
        <h3 className="heading-lg" style={{ color: 'var(--text-primary)', margin: '0 0 6px 0' }}>
          Customer Demographic Distribution
        </h3>
        <p className="text-subtle" style={{ margin: 0 }}>
          Real customer age and gender breakdown from user profiles
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '28px' }}>
        {/* Centered Chart */}
        <div style={{ width: '240px', height: '240px', position: 'relative', margin: '0 auto' }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                innerRadius={68}
                outerRadius={96}
                paddingAngle={4}
                dataKey="value"
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
                  borderRadius: '4px',
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
            <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--color-tertiary, #CC5500)', lineHeight: 1 }}>
              {totalCustomers.toLocaleString('en-IN')}
            </div>
            <div style={{
              fontSize: '0.72rem',
              fontWeight: 700,
              color: 'var(--color-primary-dark, #6f805e)',
              marginTop: '4px'
            }}>
              Shoppers
            </div>
          </div>
        </div>

        {/* Centered Demographic Grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '12px',
          width: '100%',
          maxWidth: '820px',
          margin: '0 auto'
        }}>
          {demographics.map((demo) => {
            const isHovered = hoveredCategory === demo.name;
            return (
              <div 
                key={demo.name}
                onMouseEnter={() => setHoveredCategory(demo.name)}
                onMouseLeave={() => setHoveredCategory(null)}
                style={{
                  background: isHovered ? 'var(--table-row-hover)' : 'var(--table-header-bg)',
                  border: isHovered ? `1px solid ${demo.color}` : '1px solid var(--panel-border)',
                  borderRadius: 'var(--radius-sm, 4px)',
                  padding: '12px 14px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ width: '8px', height: '8px', borderRadius: '2px', background: demo.color }} />
                    <span style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--text-primary)' }}>{demo.name}</span>
                  </div>
                  <div style={{ fontSize: '0.82rem', fontWeight: 800, color: demo.color }}>
                    {demo.pct}
                  </div>
                </div>

                <div style={{
                  width: '100%',
                  height: '5px',
                  background: 'rgba(167, 167, 167, 0.2)',
                  borderRadius: '2px',
                  overflow: 'hidden'
                }}>
                  <div style={{
                    width: demo.pct,
                    height: '100%',
                    background: demo.color,
                    borderRadius: '2px'
                  }} />
                </div>

                <div style={{ marginTop: '4px', fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                  {demo.customerCount} Active Profile{demo.customerCount === 1 ? '' : 's'}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default GenderDistribution;
