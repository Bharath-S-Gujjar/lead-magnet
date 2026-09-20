import React, { useState } from 'react';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { simulateLeadScore } from '../../services/api';
import { FlaskConical, AlertCircle, Zap } from 'lucide-react';

const FEATURE_OPTIONS = [
  { key: 'checkout_attempts', label: 'Checkout Attempts', type: 'number' },
  { key: 'product_interactions', label: 'Product Interactions', type: 'number' },
  { key: 'cart_value', label: 'Cart Value (₹)', type: 'number' },
  { key: 'cart_item_count', label: 'Cart Items', type: 'number' },
  { key: 'products_viewed', label: 'Products Viewed', type: 'number' },
  { key: 'orders_count', label: 'Orders Count', type: 'number' },
  { key: 'total_order_value', label: 'Total Order Value (₹)', type: 'number' },
  { key: 'page_views_count', label: 'Page Views', type: 'number' },
  { key: 'high_intent_page_visits', label: 'High-Intent Visits', type: 'number' },
  { key: 'sessions_count', label: 'Session Count', type: 'number' },
  { key: 'days_since_last_activity', label: 'Days Since Last Activity', type: 'number' },
];

export const WhatIfSimulator = () => {
  const { admin } = useAdminAuth();
  const [customerId, setCustomerId] = useState('');
  const [overrides, setOverrides] = useState({});
  const [result, setResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (key, value) => {
    if (value === '' || value === null || value === undefined) {
      const next = { ...overrides };
      delete next[key];
      setOverrides(next);
    } else {
      setOverrides({ ...overrides, [key]: parseFloat(value) || 0 });
    }
  };

  const handleSimulate = async () => {
    if (Object.keys(overrides).length === 0) {
      setError('Set at least one feature override to simulate');
      return;
    }
    setIsLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await simulateLeadScore({
        token: admin?.token,
        customer_id: customerId || null,
        feature_overrides: overrides,
      });
      setResult(res);
    } catch (err) {
      setError(err.message || 'Simulation failed');
    }
    setIsLoading(false);
  };

  const getSegmentColor = (segment) => {
    if (segment === 'Hot') return '#ef4444';
    if (segment === 'Warm') return '#f59e0b';
    return '#6366f1';
  };

  return (
    <div className="glass-card" style={{ padding: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
        <FlaskConical size={18} style={{ color: '#8b5cf6' }} />
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>What-If Simulator</h3>
        <span style={{
          marginLeft: 'auto',
          fontSize: '0.65rem',
          padding: '3px 8px',
          borderRadius: '20px',
          background: 'rgba(139,92,246,0.15)',
          color: '#8b5cf6',
          fontWeight: 600,
        }}>
          SIMULATION ONLY
        </span>
      </div>

      {/* Customer ID (optional) */}
      <div style={{ marginBottom: '12px' }}>
        <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
          Base Customer ID (optional — uses their features as baseline)
        </label>
        <input
          type="text"
          value={customerId}
          onChange={e => setCustomerId(e.target.value)}
          placeholder="Leave empty for zero baseline"
          style={{
            width: '100%',
            padding: '8px 12px',
            borderRadius: '8px',
            border: '1px solid rgba(255,255,255,0.1)',
            background: 'rgba(255,255,255,0.05)',
            color: 'var(--text-primary)',
            fontSize: '0.8rem',
            outline: 'none',
          }}
        />
      </div>

      {/* Feature overrides grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '8px', marginBottom: '16px' }}>
        {FEATURE_OPTIONS.map(feat => (
          <div key={feat.key}>
            <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', marginBottom: '2px' }}>
              {feat.label}
            </label>
            <input
              type="number"
              value={overrides[feat.key] !== undefined ? overrides[feat.key] : ''}
              onChange={e => handleChange(feat.key, e.target.value)}
              placeholder="—"
              style={{
                width: '100%',
                padding: '6px 10px',
                borderRadius: '6px',
                border: '1px solid rgba(255,255,255,0.08)',
                background: 'rgba(255,255,255,0.03)',
                color: 'var(--text-primary)',
                fontSize: '0.8rem',
                outline: 'none',
              }}
            />
          </div>
        ))}
      </div>

      {/* Simulate button */}
      <button
        onClick={handleSimulate}
        disabled={isLoading}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '10px 20px',
          borderRadius: '8px',
          border: 'none',
          background: 'linear-gradient(135deg, #8b5cf6, #6366f1)',
          color: '#fff',
          fontSize: '0.85rem',
          fontWeight: 600,
          cursor: isLoading ? 'wait' : 'pointer',
          opacity: isLoading ? 0.7 : 1,
        }}
      >
        <Zap size={14} />
        {isLoading ? 'Simulating...' : 'Run Simulation'}
      </button>

      {error && (
        <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '6px', color: '#ef4444', fontSize: '0.8rem' }}>
          <AlertCircle size={14} /> {error}
        </div>
      )}

      {/* Result display */}
      {result && (
        <div style={{
          marginTop: '16px',
          padding: '16px',
          borderRadius: '10px',
          background: 'rgba(139,92,246,0.08)',
          border: '1px solid rgba(139,92,246,0.2)',
        }}>
          <div style={{ fontSize: '0.7rem', color: '#8b5cf6', fontWeight: 600, marginBottom: '10px', textTransform: 'uppercase' }}>
            ⚡ Simulated Result
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
            <div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Score</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)' }}>{result.lead_score}</div>
            </div>
            <div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Probability</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                {result.lead_probability !== undefined ? `${(result.lead_probability * 100).toFixed(1)}%` : '—'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Segment</div>
              <div style={{
                fontSize: '1rem',
                fontWeight: 700,
                color: getSegmentColor(result.lead_segment),
                marginTop: '4px',
              }}>
                {result.lead_segment || '—'}
              </div>
            </div>
          </div>
          <div style={{
            marginTop: '10px',
            fontSize: '0.65rem',
            color: 'var(--text-muted)',
            fontStyle: 'italic',
          }}>
            {result.simulation_label}
          </div>
        </div>
      )}
    </div>
  );
};
