import React, { useEffect, useState } from 'react';
import { Users, Target, Activity, Flame, MailCheck, AlertCircle, RefreshCw } from 'lucide-react';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { getAdminIntelligenceOverview } from '../../services/api';

export const LeadAnalyticsSummary = ({ onRefresh }) => {
  const { admin } = useAdminAuth();
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  const loadData = async () => {
    setIsLoading(true);
    setError('');
    try {
      const data = await getAdminIntelligenceOverview(admin?.token);
      setOverview(data);
    } catch (err) {
      if (err.status === 401) {
        setError('Session expired. Please log in again.');
      } else if (err.status === 403) {
        setError('You are not authorized to view admin intelligence.');
      } else {
        setError(err.message || 'Unable to load live dashboard metrics.');
      }
      setOverview(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [admin?.token]);

  const displayVal = (val, suffix = '') => {
    if (val === undefined || val === null) return 'Unavailable';
    return `${val}${suffix}`;
  };

  const customers = overview?.customers || {};
  const leads = overview?.leads || {};
  const marketing = overview?.marketing || {};

  return (
    <section style={{ marginBottom: '28px' }}>
      {/* Header bar with Refresh button */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div>
          <h2 className="heading-lg" style={{ color: 'var(--text-primary)', marginBottom: '2px' }}>
            Live Intelligence Summary
          </h2>
          <p className="text-subtle" style={{ fontSize: '0.85rem' }}>
            Canonical customer behavior, lead qualification state, and automated marketing performance
          </p>
        </div>
        <button
          onClick={() => {
            loadData();
            if (onRefresh) onRefresh();
          }}
          className="btn btn-ghost"
          disabled={isLoading}
          style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem' }}
        >
          <RefreshCw size={14} className={isLoading ? 'spin' : ''} />
          <span>Refresh Data</span>
        </button>
      </div>

      {isLoading && (
        <div className="glass-card" style={{ padding: '16px 24px', marginBottom: '20px', color: 'var(--text-secondary)' }}>
          Loading real-time intelligence KPIs...
        </div>
      )}

      {error && (
        <div className="glass-card" style={{ padding: '16px 24px', marginBottom: '20px', color: 'var(--accent-rose)', display: 'flex', alignItems: 'center', gap: '10px' }} role="alert">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* KPI Cards Grid */}
      <div className="grid-4" style={{ gap: '20px' }}>
        {/* Card 1: Total Customers */}
        <div className="glass-card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Total Customers</span>
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Users size={18} />
            </div>
          </div>
          <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.1rem', fontWeight: 800, color: 'var(--text-primary)' }}>
            {displayVal(customers.total)}
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px', display: 'flex', gap: '12px' }}>
            <span>Active Today: <strong>{displayVal(customers.active_today)}</strong></span>
            <span>•</span>
            <span>New Today: <strong>{displayVal(customers.new_today)}</strong></span>
          </div>
        </div>

        {/* Card 2: Total Qualified Leads */}
        <div className="glass-card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Qualified Leads</span>
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'rgba(79, 70, 229, 0.1)', color: '#4f46e5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Target size={18} />
            </div>
          </div>
          <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.1rem', fontWeight: 800, color: 'var(--accent-indigo)' }}>
            {displayVal(leads.total_qualified)}
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Newly Qualified Today: <strong>{displayVal(leads.newly_qualified_today)}</strong>
          </div>
        </div>

        {/* Card 3: Hot Lead Segment */}
        <div className="glass-card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Hot Leads</span>
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Flame size={18} />
            </div>
          </div>
          <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.1rem', fontWeight: 800, color: '#ef4444' }}>
            {displayVal(leads.hot)}
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px', display: 'flex', gap: '10px' }}>
            <span>Warm: <strong>{displayVal(leads.warm)}</strong></span>
            <span>•</span>
            <span>Cold: <strong>{displayVal(leads.cold)}</strong></span>
          </div>
        </div>

        {/* Card 4: Marketing Dispatches */}
        <div className="glass-card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Communications Sent</span>
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'rgba(16, 185, 129, 0.1)', color: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <MailCheck size={18} />
            </div>
          </div>
          <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.1rem', fontWeight: 800, color: 'var(--accent-emerald)' }}>
            {displayVal(marketing.communications_sent)}
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px', display: 'flex', gap: '8px' }}>
            <span>Events: <strong>{displayVal(marketing.automation_events)}</strong></span>
            <span>•</span>
            <span>Failed: <strong>{displayVal(marketing.communications_failed)}</strong></span>
            <span>•</span>
            <span>Skipped: <strong>{displayVal(marketing.communications_skipped)}</strong></span>
          </div>
        </div>
      </div>
    </section>
  );
};
