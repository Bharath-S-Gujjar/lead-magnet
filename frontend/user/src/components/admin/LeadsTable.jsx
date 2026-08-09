import React from 'react';
import { Target, Mail, MessageSquare, User, Sparkles, Send, TrendingUp } from 'lucide-react';

export const LeadsTable = ({ leads, onSelectLead }) => {
  if (!leads || leads.length === 0) {
    return (
      <section className="glass-card" style={{ padding: '32px', marginTop: '24px' }}>
        <h3 className="heading-lg" style={{ color: 'var(--text-primary)', marginBottom: '4px' }}>
          Leads & Prospect Intelligence Directory
        </h3>
        <p className="text-subtle" style={{ marginBottom: '20px' }}>
          Captured leads with behavioral scores, segment, and automated marketing dispatches.
        </p>
        <div style={{
          padding: '32px', textAlign: 'center', background: 'var(--table-header-bg)',
          borderRadius: 'var(--radius-lg)', border: '1px dashed var(--panel-border)',
          color: 'var(--text-muted)'
        }}>
          <Target size={36} style={{ marginBottom: '10px', opacity: 0.5 }} />
          <div>No active leads captured yet. Browse products or create sessions to generate leads.</div>
        </div>
      </section>
    );
  }

  return (
    <section className="glass-card" style={{ padding: '32px', marginTop: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h3 className="heading-lg" style={{ color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Target size={20} style={{ color: 'var(--accent-indigo)' }} />
            <span>Leads & Active Prospect Intelligence</span>
          </h3>
          <p className="text-subtle">
            Captured leads from MongoDB — click any lead row to view sent sales emails, SMS log & dispatch offers.
          </p>
        </div>
        <span className="badge badge-indigo" style={{ fontSize: '0.82rem', padding: '6px 16px' }}>
          {leads.length} Active Lead{leads.length !== 1 ? 's' : ''}
        </span>
      </div>

      <div style={{ overflowX: 'auto', maxHeight: '420px', overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 8px', fontSize: '0.875rem' }}>
          <thead>
            <tr style={{ background: 'var(--table-header-bg)', color: 'var(--text-secondary)' }}>
              <th style={{ padding: '14px 18px', borderRadius: 'var(--radius-md) 0 0 var(--radius-md)', fontWeight: 700, textAlign: 'left' }}>Lead Target</th>
              <th style={{ padding: '14px 16px', fontWeight: 700, textAlign: 'center' }}>Lead Score</th>
              <th style={{ padding: '14px 16px', fontWeight: 700, textAlign: 'center' }}>Segment</th>
              <th style={{ padding: '14px 16px', fontWeight: 700, textAlign: 'left' }}>Recommended Action</th>
              <th style={{ padding: '14px 16px', fontWeight: 700, textAlign: 'center' }}>Auto Email & SMS</th>
              <th style={{ padding: '14px 18px', borderRadius: '0 var(--radius-md) var(--radius-md) 0', fontWeight: 700, textAlign: 'center' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {leads.map((lead, idx) => {
              const leadId = lead.visitor_id || lead.email || `lead-${idx + 1}`;
              const leadScore = lead.score ?? 85;
              const segment = lead.segment || 'Hot Prospect';
              const nextAction = lead.next_action || 'Send 20% OFF Clothing Coupon Email & SMS';
              const status = lead.status || 'Active';

              return (
                <tr
                  key={lead._id || idx}
                  onClick={() => onSelectLead && onSelectLead({
                    id: leadId,
                    name: lead.visitor_id || 'Active Clothing Prospect',
                    avatar: `https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(leadId)}`,
                    gender: lead.gender || 'Shopper',
                    age: lead.age || '25',
                    orders: 0,
                    total_spent: 0,
                    cartItemsCount: 2,
                    likedItemsCount: 3,
                    psychographic: segment,
                    sessions: [],
                    interestHistory: [],
                    cartItems: [
                      { id: 'cart-1', name: 'Levi\'s Classic Fit Denim Shirt', price: 2499, qty: 1, color: 'Blue', size: 'L', category: 'Shirts', image: 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=500' },
                      { id: 'cart-2', name: 'HRX Premium Cotton Hoodie', price: 1799, qty: 1, color: 'Black', size: 'M', category: 'Hoodies', image: 'https://images.unsplash.com/photo-1556905055-8f358a7a47b2?w=500' }
                    ],
                    likedItems: [
                      { id: 'like-1', name: 'Zara Summer Cotton Dress', category: 'Dresses', dateLiked: 'Today', image: 'https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=500' }
                    ],
                    sentEmail: {
                      status: 'Delivered',
                      subject: `Special Offer for ${leadId}: 20% OFF Your Favorite Clothing Items!`,
                      body: `Hi there!\n\nWe saw you browsing our premium clothing collection! Use promo code MAGNET20 at checkout for an instant 20% discount on your order.\n\nShop Now: http://localhost:3000/#/cart`
                    },
                    sentSms: {
                      status: 'Delivered',
                      text: `Lead Magnet Clothing: Complete your order today with code MAGNET20 to get 20% OFF + Free Express Shipping!`
                    }
                  })}
                  style={{
                    background: 'var(--panel-solid)',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.02)',
                    border: '1px solid var(--panel-border)',
                    cursor: 'pointer',
                    transition: 'transform 0.15s ease'
                  }}
                >
                  <td style={{ padding: '14px 18px', borderRadius: 'var(--radius-md) 0 0 var(--radius-md)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div style={{ width: '34px', height: '34px', borderRadius: '50%', background: 'rgba(79, 70, 229, 0.15)', color: 'var(--accent-indigo)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <User size={16} />
                      </div>
                      <div>
                        <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.88rem' }}>
                          {lead.visitor_id || 'Clothing Lead Prospect'}
                        </div>
                        <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                          ID: #{String(lead._id || idx + 100).slice(-6).toUpperCase()}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                    <span className="badge badge-indigo" style={{ fontWeight: 800, fontSize: '0.85rem' }}>
                      <TrendingUp size={12} style={{ marginRight: '4px' }} />
                      {leadScore}/100
                    </span>
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                    <span className={`badge ${segment === 'Hot' ? 'badge-rose' : 'badge-emerald'}`} style={{ fontSize: '0.78rem', padding: '4px 12px' }}>
                      <Sparkles size={11} style={{ marginRight: '4px' }} />
                      {segment}
                    </span>
                  </td>
                  <td style={{ padding: '14px 16px', color: 'var(--text-primary)', fontWeight: 600, fontSize: '0.84rem' }}>
                    {nextAction}
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                    <div style={{ display: 'inline-flex', gap: '8px' }}>
                      <span className="badge badge-indigo" title="Automated Sales Email Sent" style={{ padding: '4px 8px' }}>
                        <Mail size={12} /> Email
                      </span>
                      <span className="badge badge-emerald" title="Automated SMS Promo Sent" style={{ padding: '4px 8px' }}>
                        <MessageSquare size={12} /> SMS
                      </span>
                    </div>
                  </td>
                  <td style={{ padding: '14px 18px', borderRadius: '0 var(--radius-md) var(--radius-md) 0', textAlign: 'center' }}>
                    <span className="badge badge-emerald" style={{ fontSize: '0.75rem', padding: '4px 10px' }}>
                      {status}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
};
