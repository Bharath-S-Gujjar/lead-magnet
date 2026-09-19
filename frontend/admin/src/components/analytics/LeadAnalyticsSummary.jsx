import React, { useEffect, useState } from 'react';
import { Users, Target, Sparkles, Activity } from 'lucide-react';
import { useAdminAuth } from '../../context/AdminAuthContext';

export const LeadAnalyticsSummary = () => {
  const { admin } = useAdminAuth();
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000').replace(/\/$/, '');

  useEffect(() => {
    let isMounted = true;

    async function loadAnalytics() {
      setIsLoading(true);
      setError('');

      try {
        const response = await fetch(`${apiBaseUrl}/api/analytics/overview`, {
          headers: admin?.token ? { Authorization: `Bearer ${admin.token}` } : {},
        });
        const payload = await response.json();

        if (!response.ok || !payload.success || !payload.data) {
          throw new Error(payload.message || 'Unable to load live analytics.');
        }

        if (isMounted) {
          setAnalytics(payload.data);
        }
      } catch (err) {
        if (isMounted) {
          setAnalytics(null);
          setError(err.message || 'Unable to load live analytics.');
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    loadAnalytics();
    return () => {
      isMounted = false;
    };
  }, [admin?.token, apiBaseUrl]);

  const kpis = {
    totalCustomers: analytics?.total_customers,
    totalLeads: analytics?.total_leads,
    activeCustomersToday: analytics?.active_customers_today,
    predictedFutureLeads: analytics?.predicted_future_leads,
  };
  const displayValue = (value, suffix = '') => value === undefined || value === null ? 'Unavailable' : `${value}${suffix}`;

  return (
    <section>
      {isLoading && (
        <div className="glass-card" style={{ padding: '16px 24px', marginBottom: '20px', color: 'var(--text-secondary)' }}>
          Loading live analytics...
        </div>
      )}
      {error && (
        <div className="glass-card" style={{ padding: '16px 24px', marginBottom: '20px', color: 'var(--accent-rose)' }} role="alert">
          {error}
        </div>
      )}
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
            {displayValue(kpis.totalCustomers)}
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            Registered clothing shoppers
          </div>
        </div>

        {/* Card 2: Total Leads */}
        <div className="glass-card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Total Leads</span>
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'rgba(79, 70, 229, 0.1)', color: '#4f46e5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Target size={18} />
            </div>
          </div>
          <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.1rem', fontWeight: 800, color: 'var(--accent-indigo)' }}>
            {displayValue(kpis.totalLeads, ' Leads')}
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '4px', fontWeight: 600 }}>
            Live lead count from analytics API
          </div>
        </div>

        {/* Card 3: Predicted Future Leads */}
        <div className="glass-card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Predicted Future Leads</span>
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'rgba(139, 92, 246, 0.1)', color: '#8b5cf6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Sparkles size={18} />
            </div>
          </div>
          <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.1rem', fontWeight: 800, color: 'var(--accent-indigo)' }}>
            {displayValue(kpis.predictedFutureLeads, ' Leads')}
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '4px', fontWeight: 600 }}>
            Prediction data is not available from the live endpoint
          </div>
        </div>

        {/* Card 4: Active Customers Today */}
        <div className="glass-card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Active Customers Today</span>
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'rgba(16, 185, 129, 0.1)', color: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Activity size={18} />
            </div>
          </div>
          <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.1rem', fontWeight: 800, color: 'var(--accent-emerald)' }}>
            {displayValue(kpis.activeCustomersToday, ' Active')}
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            Browsing clothing store live right now
          </div>
        </div>
      </div>
    </section>
  );
};
