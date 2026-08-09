import React from 'react';
import { Users, Target, Sparkles, Activity } from 'lucide-react';

export const LeadAnalyticsSummary = ({ kpis }) => {
  const totalCustomers = kpis?.totalCustomers || 0;
  const totalLeads = kpis?.totalLeads || 0;
  const activeToday = kpis?.activeToday || 0;
  const totalSessions = kpis?.totalSessions || 0;
  const totalEvents = kpis?.totalEvents || 0;
  const conversion = totalCustomers > 0 ? `${((totalLeads / totalCustomers) * 100).toFixed(1)}%` : '0%';

  return (
    <section>
      <div className="grid-4" style={{ gap: '20px' }}>
        <div className="glass-card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Total Customers</span>
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Users size={18} />
            </div>
          </div>
          <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.1rem', fontWeight: 800, color: 'var(--text-primary)' }}>
            {totalCustomers.toLocaleString('en-IN')}
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            Registered clothing shoppers
          </div>
        </div>

        <div className="glass-card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Total Leads</span>
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'rgba(79, 70, 229, 0.1)', color: '#4f46e5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Target size={18} />
            </div>
          </div>
          <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.1rem', fontWeight: 800, color: 'var(--accent-indigo)' }}>
            {totalLeads.toLocaleString('en-IN')} Leads
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '4px', fontWeight: 600 }}>
            Out of {totalCustomers.toLocaleString('en-IN')} Customers - <span style={{ color: 'var(--accent-emerald)', fontWeight: 700 }}>{conversion} Conversion</span>
          </div>
        </div>

        <div className="glass-card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Total Sessions</span>
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'rgba(139, 92, 246, 0.1)', color: '#8b5cf6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Sparkles size={18} />
            </div>
          </div>
          <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.1rem', fontWeight: 800, color: 'var(--accent-indigo)' }}>
            {totalSessions.toLocaleString('en-IN')} Sessions
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '4px', fontWeight: 600 }}>
            Live browsing sessions recorded
          </div>
        </div>

        <div className="glass-card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Active Customers Today</span>
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'rgba(16, 185, 129, 0.1)', color: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Activity size={18} />
            </div>
          </div>
          <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.1rem', fontWeight: 800, color: 'var(--accent-emerald)' }}>
            {activeToday.toLocaleString('en-IN')} Active
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            Browsing clothing store live right now
          </div>
        </div>

        <div className="glass-card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Total Events</span>
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'rgba(79, 70, 229, 0.1)', color: '#4f46e5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Target size={18} />
            </div>
          </div>
          <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.1rem', fontWeight: 800, color: 'var(--accent-indigo)' }}>
            {totalEvents.toLocaleString('en-IN')} Events
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            Behavioral events from MongoDB
          </div>
        </div>
      </div>
    </section>
  );
};
