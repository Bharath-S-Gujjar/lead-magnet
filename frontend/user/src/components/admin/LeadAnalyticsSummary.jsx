import React, { useState } from 'react';

export const LeadAnalyticsSummary = ({ kpis }) => {
  const [activeFilter, setActiveFilter] = useState('realtime');
  const [statusNotice, setStatusNotice] = useState('');

  const totalCustomers = kpis?.totalCustomers || 0;
  const totalLeads = kpis?.totalLeads || 0;
  const activeToday = kpis?.activeToday || 0;
  const totalSessions = kpis?.totalSessions || 0;
  const totalEvents = kpis?.totalEvents || 0;
  const conversion = totalCustomers > 0 ? `${((totalLeads / totalCustomers) * 100).toFixed(1)}%` : '0%';

  const handleAction = (label) => {
    setStatusNotice(`${label} updated in real-time.`);
    setTimeout(() => setStatusNotice(''), 3000);
  };

  return (
    <section style={{
      background: 'var(--panel-solid)',
      border: '1px solid var(--panel-border)',
      borderRadius: 'var(--radius-md, 6px)',
      padding: '24px',
      display: 'flex',
      flexDirection: 'column',
      gap: '20px'
    }}>
      {/* Section Header with Live Status & Action Buttons */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '16px',
        borderBottom: '1px solid var(--panel-border)',
        paddingBottom: '16px'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              backgroundColor: 'var(--color-primary, #9CAF88)',
              boxShadow: '0 0 0 3px rgba(156, 175, 136, 0.3)',
              display: 'inline-block'
            }} />
            <h2 className="heading-lg" style={{ color: 'var(--text-primary)', margin: 0 }}>
              Live Intelligence Summary
            </h2>
            <span className="badge badge-primary" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>
              Live Stream
            </span>
          </div>
          <p className="text-subtle" style={{ marginTop: '4px' }}>
            Real-time shopper behavioral analytics, high-intent lead conversion rates, and session intelligence.
          </p>
        </div>

        {/* Interactive Action Buttons with Uiverse.io hover animations */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => { setActiveFilter('realtime'); handleAction('Real-time sync'); }}
            className={`btn ${activeFilter === 'realtime' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '0.55em 1.4em', fontSize: '0.8rem' }}
          >
            Realtime
          </button>
          <button
            type="button"
            onClick={() => { setActiveFilter('today'); handleAction('Today window'); }}
            className={`btn ${activeFilter === 'today' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '0.55em 1.4em', fontSize: '0.8rem' }}
          >
            Today
          </button>
          <button
            type="button"
            onClick={() => { setActiveFilter('week'); handleAction('7-Day window'); }}
            className={`btn ${activeFilter === 'week' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '0.55em 1.4em', fontSize: '0.8rem' }}
          >
            7 Days
          </button>
          <button
            type="button"
            onClick={() => handleAction('Intelligence CSV export')}
            className="btn btn-tertiary"
            style={{ padding: '0.55em 1.4em', fontSize: '0.8rem' }}
          >
            Export CSV
          </button>
        </div>
      </div>

      {/* Live notification feedback */}
      {statusNotice && (
        <div style={{
          padding: '8px 14px',
          background: 'var(--color-primary-light, rgba(156, 175, 136, 0.15))',
          border: '1px solid var(--color-primary, #9CAF88)',
          borderRadius: '4px',
          fontSize: '0.82rem',
          fontWeight: 600,
          color: 'var(--text-primary)'
        }}>
          {statusNotice}
        </div>
      )}

      {/* Metric Cards Grid with Standard Colours & Interactive Buttons */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '16px' }}>

        {/* 1. Total Customers (Primary #9CAF88) */}
        <div style={{
          padding: '20px',
          background: 'var(--bg-app)',
          border: '1px solid var(--panel-border)',
          borderTop: '3px solid var(--color-primary, #9CAF88)',
          borderRadius: 'var(--radius-md, 6px)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          gap: '14px'
        }}>
          <div>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' }}>
              Total Customers
            </div>
            <div style={{ fontSize: '1.9rem', fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1.1 }}>
              {totalCustomers.toLocaleString('en-IN')}
            </div>
            <div style={{ fontSize: '0.78rem', color: 'var(--color-primary-dark, #6f805e)', fontWeight: 600, marginTop: '6px' }}>
              Registered shoppers
            </div>
          </div>
          <button
            type="button"
            onClick={() => handleAction('Customer directory filter')}
            className="btn btn-secondary"
            style={{ width: '100%', padding: '0.5em 1em', fontSize: '0.75rem', borderRadius: '4px' }}
          >
            View Directory
          </button>
        </div>

        {/* 2. Total Leads (Tertiary #CC5500) */}
        <div style={{
          padding: '20px',
          background: 'var(--bg-app)',
          border: '1px solid var(--panel-border)',
          borderTop: '3px solid var(--color-tertiary, #CC5500)',
          borderRadius: 'var(--radius-md, 6px)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          gap: '14px'
        }}>
          <div>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' }}>
              High-Intent Leads
            </div>
            <div style={{ fontSize: '1.9rem', fontWeight: 800, color: 'var(--color-tertiary, #CC5500)', lineHeight: 1.1 }}>
              {totalLeads.toLocaleString('en-IN')}
            </div>
            <div style={{ fontSize: '0.78rem', color: 'var(--color-tertiary, #CC5500)', fontWeight: 700, marginTop: '6px' }}>
              {conversion} Conversion Rate
            </div>
          </div>
          <button
            type="button"
            onClick={() => handleAction('High-intent leads filter')}
            className="btn btn-tertiary"
            style={{ width: '100%', padding: '0.5em 1em', fontSize: '0.75rem', borderRadius: '4px' }}
          >
            Inspect Leads
          </button>
        </div>

        {/* 3. Total Sessions (Secondary #A7A7A7) */}
        <div style={{
          padding: '20px',
          background: 'var(--bg-app)',
          border: '1px solid var(--panel-border)',
          borderTop: '3px solid var(--color-secondary, #A7A7A7)',
          borderRadius: 'var(--radius-md, 6px)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          gap: '14px'
        }}>
          <div>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' }}>
              Total Sessions
            </div>
            <div style={{ fontSize: '1.9rem', fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1.1 }}>
              {totalSessions.toLocaleString('en-IN')}
            </div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', fontWeight: 600, marginTop: '6px' }}>
              Store visits logged
            </div>
          </div>
          <button
            type="button"
            onClick={() => handleAction('Session telemetry')}
            className="btn btn-secondary"
            style={{ width: '100%', padding: '0.5em 1em', fontSize: '0.75rem', borderRadius: '4px' }}
          >
            View Sessions
          </button>
        </div>

        {/* 4. Active Today (Tertiary #CC5500) */}
        <div style={{
          padding: '20px',
          background: 'var(--bg-app)',
          border: '1px solid var(--panel-border)',
          borderTop: '3px solid var(--color-tertiary, #CC5500)',
          borderRadius: 'var(--radius-md, 6px)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          gap: '14px'
        }}>
          <div>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' }}>
              Active Today
            </div>
            <div style={{ fontSize: '1.9rem', fontWeight: 800, color: 'var(--color-tertiary, #CC5500)', lineHeight: 1.1 }}>
              {activeToday.toLocaleString('en-IN')}
            </div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', fontWeight: 600, marginTop: '6px' }}>
              Live in store right now
            </div>
          </div>
          <button
            type="button"
            onClick={() => handleAction('Real-time visitors list')}
            className="btn btn-tertiary"
            style={{ width: '100%', padding: '0.5em 1em', fontSize: '0.75rem', borderRadius: '4px' }}
          >
            Live Monitor
          </button>
        </div>

        {/* 5. Total Events (Primary #9CAF88) */}
        <div style={{
          padding: '20px',
          background: 'var(--bg-app)',
          border: '1px solid var(--panel-border)',
          borderTop: '3px solid var(--color-primary, #9CAF88)',
          borderRadius: 'var(--radius-md, 6px)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          gap: '14px'
        }}>
          <div>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' }}>
              Total Events
            </div>
            <div style={{ fontSize: '1.9rem', fontWeight: 800, color: 'var(--color-primary-dark, #6f805e)', lineHeight: 1.1 }}>
              {totalEvents.toLocaleString('en-IN')}
            </div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600, marginTop: '6px' }}>
              Behavioral click logs
            </div>
          </div>
          <button
            type="button"
            onClick={() => handleAction('Event stream')}
            className="btn btn-primary"
            style={{ width: '100%', padding: '0.5em 1em', fontSize: '0.75rem', borderRadius: '4px' }}
          >
            Analyze Events
          </button>
        </div>

      </div>
    </section>
  );
};
