import React from 'react';
import { 
  X, 
  Clock, 
  ShoppingBag, 
  Heart, 
  Mail, 
  MessageSquare, 
  Shirt, 
  CheckCircle2,
  TrendingUp
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';

function formatDate(value) {
  if (!value) return 'No orders';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'No orders';
  return date.toLocaleDateString('en-IN', { month: 'short', day: '2-digit', year: 'numeric' });
}

export const CustomerDetailDrawer = ({ customer, isOpen, onClose }) => {
  if (!customer) return null;

  // Session math for Time Spent analysis
  const sessionMinutes = (customer.sessions || []).map(s => s.minutes || 0);
  const avgTime = sessionMinutes.length ? (sessionMinutes.reduce((a, b) => a + b, 0) / sessionMinutes.length).toFixed(1) : '0.0';
  const longestVisit = sessionMinutes.length ? Math.max(...sessionMinutes) : 0;
  const shortestVisit = sessionMinutes.length ? Math.min(...sessionMinutes) : 0;

  const CustomSessionTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const item = payload[0].payload;
      return (
        <div style={{
          background: 'var(--panel-solid)',
          border: '1px solid var(--panel-border)',
          padding: '12px 16px',
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--panel-shadow)',
          fontSize: '0.82rem',
          color: 'var(--text-primary)',
          maxWidth: '260px'
        }}>
          <div style={{ fontWeight: 800, color: 'var(--accent-indigo)', marginBottom: '4px' }}>{item.date}</div>
          <div><strong>Minutes Spent:</strong> {item.minutes} mins</div>
          <div><strong>Pages Visited:</strong> {item.pagesVisited} pages</div>
          <div style={{ marginTop: '4px', color: 'var(--accent-emerald)', fontWeight: 700 }}>
            <strong>Outcome:</strong> {item.outcome}
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <>
      {/* Background Overlay */}
      <div 
        className={`drawer-overlay ${isOpen ? 'open' : ''}`}
        onClick={onClose}
      />

      {/* Slide-out Drawer Panel */}
      <div className={`drawer-panel ${isOpen ? 'open' : ''}`}>
        {/* Top Header */}
        <div style={{
          padding: '24px 32px',
          borderBottom: '1px solid var(--panel-border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'var(--panel-bg)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <img 
              src={customer.avatar} 
              alt={customer.name}
              style={{ width: '60px', height: '60px', borderRadius: '50%', objectFit: 'cover', border: '3px solid var(--accent-indigo)' }}
            />
            <div>
              <h2 className="heading-lg" style={{ color: 'var(--text-primary)' }}>{customer.name}</h2>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'flex', gap: '12px', marginTop: '2px' }}>
                <span>ID: {customer.id}</span>
                <span>•</span>
                <span>{customer.gender}{customer.age && customer.age !== '-' ? `, ${customer.age} yrs` : ''}</span>
                <span>•</span>
                <span className="badge badge-indigo">{customer.psychographic}</span>
              </div>
            </div>
          </div>

          <button 
            onClick={onClose}
            className="btn btn-ghost"
            style={{ padding: '8px', borderRadius: '50%' }}
          >
            <X size={22} />
          </button>
        </div>

        {/* Scrollable Content */}
        <div style={{ padding: '32px', display: 'flex', flexDirection: 'column', gap: '32px', overflowY: 'auto' }}>
          
          {/* SECTION 1: Customer Profile Header */}
          <div className="glass-card" style={{ padding: '24px', background: 'var(--table-header-bg)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '16px', textAlign: 'center' }}>
              <div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>Customer ID</div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--accent-indigo)', marginTop: '2px' }}>{customer.id}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>Gender & Age</div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: '2px' }}>
                  {customer.gender}{customer.age && customer.age !== '-' ? `, ${customer.age}` : ''}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>Total Orders</div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: '2px' }}>
                  {customer.order_count ?? customer.orders ?? 0} Orders
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>Total Spent</div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--accent-emerald)', marginTop: '2px' }}>
                  ₹{(customer.total_spent || 0).toLocaleString('en-IN')}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>Last Order Date</div>
                <div style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: '2px' }}>
                  {formatDate(customer.last_order_at)}
                </div>
              </div>
            </div>
          </div>

          {/* SECTION 2: Time Spent Analysis */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Clock size={18} style={{ color: 'var(--accent-indigo)' }} />
                  <span>Time Spent Analysis</span>
                </h3>
                <p className="text-subtle">Browsing session duration & engagement history</p>
              </div>
            </div>

            {/* Interactive Session Bar Chart */}
            <div style={{ width: '100%', height: '220px' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={customer.sessions} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--table-border)" vertical={false} />
                  <XAxis dataKey="date" stroke="var(--text-muted)" fontSize={12} tickLine={false} />
                  <YAxis stroke="var(--text-muted)" fontSize={12} tickLine={false} unit="m" />
                  <Tooltip content={<CustomSessionTooltip />} />
                  <Bar dataKey="minutes" radius={[6, 6, 0, 0]} animationDuration={800}>
                    {(customer.sessions || []).map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={index === customer.sessions.length - 1 ? '#4f46e5' : '#94a3b8'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Summary Row Below Graph */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginTop: '20px', borderTop: '1px solid var(--panel-border)', paddingTop: '16px', textAlign: 'center' }}>
              <div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>Average Time</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)' }}>{avgTime} mins</div>
              </div>
              <div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>Longest Visit</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--accent-indigo)' }}>{longestVisit} mins</div>
              </div>
              <div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>Shortest Visit</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-secondary)' }}>{shortestVisit} mins</div>
              </div>
            </div>
          </div>

          {/* SECTION 3: Interest History */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <div style={{ marginBottom: '16px' }}>
              <h3 className="heading-md" style={{ color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <TrendingUp size={18} style={{ color: 'var(--accent-indigo)' }} />
                <span>Interest History Timeline</span>
              </h3>
              <p className="text-subtle">Sequential timeline of clothing product interactions</p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {(customer.interestHistory || []).map((item, idx) => (
                <div 
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '12px 16px',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--table-header-bg)',
                    border: '1px solid var(--panel-border)'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'rgba(79, 70, 229, 0.1)', color: 'var(--accent-indigo)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <Shirt size={16} />
                    </div>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>{item.event}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Category: {item.category}</div>
                    </div>
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                    {item.date}, {item.time}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* SECTION 4: Cart Section */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 className="heading-md" style={{ color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ShoppingBag size={18} style={{ color: 'var(--accent-indigo)' }} />
                <span>Shopping Cart Items</span>
              </h3>
              <span className="badge badge-indigo">{(customer.cartItems || []).length} Products</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {(customer.cartItems || []).map(item => (
                <div key={item.id} style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '14px', borderRadius: 'var(--radius-md)', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)' }}>
                  <img src={item.image} alt={item.name} style={{ width: '56px', height: '56px', borderRadius: '8px', objectFit: 'cover' }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>{item.name}</div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', gap: '12px', marginTop: '4px' }}>
                      <span><strong>Size:</strong> {item.size}</span>
                      <span><strong>Color:</strong> {item.color}</span>
                      <span><strong>Category:</strong> {item.category}</span>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontWeight: 800, fontSize: '1rem', color: 'var(--text-primary)' }}>₹{typeof item.price === 'number' ? item.price.toLocaleString('en-IN') : item.price}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Qty: {item.qty}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* SECTION 5: Likes / Wishlist Section */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 className="heading-md" style={{ color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Heart size={18} style={{ color: 'var(--accent-rose)' }} />
                <span>Liked Products & Wishlist</span>
              </h3>
              <span className="badge badge-rose">{(customer.likedItems || []).length} Liked</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {(customer.likedItems || []).map(item => (
                <div key={item.id} style={{ display: 'flex', alignItems: 'center', gap: '14px', padding: '12px 14px', borderRadius: 'var(--radius-md)', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)' }}>
                  <img src={item.image} alt={item.name} style={{ width: '48px', height: '48px', borderRadius: '8px', objectFit: 'cover' }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-primary)' }}>{item.name}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Category: {item.category}</div>
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Liked: {item.dateLiked}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* SECTION 6: Customer Interest Summary */}
          <div className="glass-card" style={{ padding: '24px', background: 'rgba(79, 70, 229, 0.04)', border: '1px solid rgba(79, 70, 229, 0.2)' }}>
            <h3 className="heading-md" style={{ color: 'var(--accent-indigo)', marginBottom: '8px' }}>
              Customer Interest Summary
            </h3>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-primary)', lineHeight: 1.6 }}>
              "{customer.interestSummary}"
            </p>
          </div>

          {/* SECTION 7: Automated Communication Log & Interactive Dispatch */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Mail size={18} style={{ color: 'var(--accent-indigo)' }} />
                  <span>Automated & Direct Customer Communications</span>
                </h3>
                <p className="text-subtle">High-converting sales emails & SMS communication history for {customer.name}</p>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button 
                  onClick={() => alert(`Sales email dispatched to registered email: ${customer.name} (${customer.id.includes('@') ? customer.id : customer.name + '@gmail.com'})!\n\nSubject: Exclusive 20% OFF Top Clothing Styles just for you!\nBody: Hey ${customer.name}, complete your style upgrade today with coupon MAGNET20!`)}
                  className="btn btn-primary"
                  style={{ padding: '8px 14px', fontSize: '0.82rem', gap: '6px' }}
                >
                  <Mail size={14} />
                  <span>Send Sales Email</span>
                </button>
                <button 
                  onClick={() => alert(`Promotional SMS dispatched to real phone number: ${customer.name} (+91 98765 43210)!\n\nSMS Text: Lead Magnet Offer: Use code MAGNET20 for 20% OFF your clothing order!`)}
                  className="btn btn-secondary"
                  style={{ padding: '8px 14px', fontSize: '0.82rem', gap: '6px', color: 'var(--accent-emerald)', borderColor: 'var(--accent-emerald)' }}
                >
                  <MessageSquare size={14} />
                  <span>Send SMS Coupon</span>
                </button>
              </div>
            </div>

            <div className="grid-2" style={{ gap: '20px' }}>
              {/* Sent Email Card */}
              <div style={{ background: 'var(--table-header-bg)', border: '1px solid var(--panel-border)', padding: '18px', borderRadius: 'var(--radius-lg)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Mail size={16} style={{ color: 'var(--accent-indigo)' }} />
                    <span>Latest Email Communication</span>
                  </div>
                  <span className="badge badge-emerald">
                    <CheckCircle2 size={12} /> Delivered
                  </span>
                </div>

                <div style={{ marginBottom: '8px' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)' }}>To Registered Email</div>
                  <div style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--accent-indigo)' }}>
                    {customer.id.includes('@') ? customer.id : `${customer.name.toLowerCase().replace(/\s+/g, '')}@gmail.com`}
                  </div>
                </div>

                <div style={{ marginBottom: '8px' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)' }}>Subject</div>
                  <div style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--text-primary)' }}>
                    {customer.sentEmail?.subject || `Exclusive 20% OFF Top Clothing Styles for ${customer.name}!`}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)' }}>Message Content</div>
                  <div style={{ background: 'var(--panel-solid)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--panel-border)', fontSize: '0.8rem', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
                    {customer.sentEmail?.body || `Hello ${customer.name},\n\nWe noticed you were checking out our latest clothing catalog! Use exclusive discount code MAGNET20 at checkout for 20% OFF + Free Express Shipping.\n\nShop Now: http://localhost:3000/#/`}
                  </div>
                </div>
              </div>

              {/* Sent SMS Card */}
              <div style={{ background: 'var(--table-header-bg)', border: '1px solid var(--panel-border)', padding: '18px', borderRadius: 'var(--radius-lg)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <MessageSquare size={16} style={{ color: 'var(--accent-emerald)' }} />
                    <span>Latest SMS Communication</span>
                  </div>
                  <span className="badge badge-emerald">
                    <CheckCircle2 size={12} /> Delivered
                  </span>
                </div>

                <div style={{ marginBottom: '8px' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)' }}>To Registered Phone Number</div>
                  <div style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--accent-emerald)' }}>
                    +91 98765 43210
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)' }}>Message Content</div>
                  <div style={{ background: 'var(--panel-solid)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--panel-border)', fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    {customer.sentSms?.text || `Lead Magnet Clothing: Hey ${customer.name}! Complete your order today with code MAGNET20 to get 20% OFF. Link: http://localhost:3000/#/cart`}
                  </div>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </>
  );
};
