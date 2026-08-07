import React from 'react';
import { Users, Target, Sparkles, Activity } from 'lucide-react';
import { CLOTHING_KPIS } from '../../data/mockData';

export const LeadAnalyticsSummary = () => {
  const kpis = CLOTHING_KPIS;

  return (
    <section>
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
            {kpis.totalCustomersText}
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
            {kpis.totalLeads} Leads
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '4px', fontWeight: 600 }}>
            Out of 2,500 Customers • <span style={{ color: 'var(--accent-emerald)', fontWeight: 700 }}>{kpis.leadConversionPct} Conversion</span>
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
            620 Leads
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '4px', fontWeight: 600 }}>
            Out of 1,515 Potential • <span style={{ color: 'var(--accent-emerald)', fontWeight: 700 }}>40.9% Predicted</span>
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
            {kpis.activeToday} Active
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            Browsing clothing store live right now
          </div>
        </div>
      </div>
    </section>
  );
};
