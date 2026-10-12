import React from 'react';

export const LeadsTable = ({ leads, onSelectLead }) => {
  if (!leads || leads.length === 0) {
    return (
      <section style={{ padding: '24px', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', borderRadius: '4px', marginTop: '24px' }}>
        <h3 className="heading-lg" style={{ color: 'var(--text-primary)', marginBottom: '4px' }}>
          Leads Directory
        </h3>
        <p className="text-subtle" style={{ marginBottom: '20px' }}>
          Captured leads with behavioral scores, segment, and automated marketing dispatches.
        </p>
        <div style={{
          padding: '32px', textAlign: 'center', background: 'var(--bg-app)',
          borderRadius: '4px', border: '1px dashed var(--panel-border)',
          color: 'var(--text-muted)'
        }}>
          <div>No active leads captured yet. Browse products or create sessions to generate leads.</div>
        </div>
      </section>
    );
  }

  return (
    <section style={{ padding: '24px', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', borderRadius: '4px', marginTop: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h3 className="heading-lg" style={{ color: 'var(--text-primary)' }}>
            Leads and Prospect Intelligence
          </h3>
          <p className="text-subtle">
            Captured leads: click any lead row to view communications and behavioral details.
          </p>
        </div>
        <span className="badge badge-primary" style={{ fontSize: '0.82rem', padding: '6px 14px' }}>
          {leads.length} Active Lead{leads.length !== 1 ? 's' : ''}
        </span>
      </div>

      <div style={{ overflowX: 'auto', maxHeight: '420px', overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 6px', fontSize: '0.875rem' }}>
          <thead>
            <tr style={{ background: 'var(--table-header-bg)', color: 'var(--text-secondary)' }}>
              <th style={{ padding: '12px 16px', fontWeight: 700, textAlign: 'left' }}>Lead Target</th>
              <th style={{ padding: '12px 14px', fontWeight: 700, textAlign: 'center' }}>Score</th>
              <th style={{ padding: '12px 14px', fontWeight: 700, textAlign: 'center' }}>Segment</th>
              <th style={{ padding: '12px 14px', fontWeight: 700, textAlign: 'left' }}>Recommended Action</th>
              <th style={{ padding: '12px 14px', fontWeight: 700, textAlign: 'center' }}>Auto Channels</th>
              <th style={{ padding: '12px 16px', fontWeight: 700, textAlign: 'center' }}>Status</th>
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
                      { id: 'cart-1', name: "Levi's Classic Fit Denim Shirt", price: 2499, qty: 1, color: 'Blue', size: 'L', category: 'Shirts', image: 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=500' },
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
                    border: '1px solid var(--panel-border)',
                    cursor: 'pointer'
                  }}
                >
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div>
                        <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.88rem' }}>
                          {lead.visitor_id || 'Clothing Lead Prospect'}
                        </div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          ID: #{String(lead._id || idx + 100).slice(-6).toUpperCase()}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                    <span className="badge badge-primary" style={{ fontWeight: 800, fontSize: '0.82rem' }}>
                      {leadScore}/100
                    </span>
                  </td>
                  <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                    <span className={`badge ${segment === 'Hot' ? 'badge-tertiary' : 'badge-primary'}`} style={{ fontSize: '0.75rem' }}>
                      {segment}
                    </span>
                  </td>
                  <td style={{ padding: '12px 14px', color: 'var(--text-primary)', fontWeight: 600, fontSize: '0.82rem' }}>
                    {nextAction}
                  </td>
                  <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                    <div style={{ display: 'inline-flex', gap: '6px' }}>
                      <span className="badge badge-primary" style={{ padding: '2px 6px', fontSize: '0.72rem' }}>
                        Email
                      </span>
                      <span className="badge badge-primary" style={{ padding: '2px 6px', fontSize: '0.72rem' }}>
                        SMS
                      </span>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                    <span className="badge badge-primary" style={{ fontSize: '0.75rem', padding: '4px 8px' }}>
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
